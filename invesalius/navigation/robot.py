# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

from enum import Enum
import threading
import time

import numpy as np
import wx
from scipy.spatial.transform import Rotation

import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.i18n import tr as _
from invesalius.math_utils import (
    gjk_distance,
    obb_vertices_from_center_axes,
)
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class RobotObjective(Enum):
    NONE = 0
    TRACK_TARGET = 1
    MOVE_AWAY_FROM_HEAD = 2

# Coil half-thickness in mm. The coil plane is expanded up and down by this
# amount along the surface normal to form a 3D bounding box.
COIL_HALF_THICKNESS = 7.0

# Only one robot will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Robot:
    def __init__(self, name, tracker, navigation, icp):
        self.tracker = tracker
        self.navigation = navigation
        self.icp = icp
        self.enabled_in_gui = False
        self.coil_name = None
        self.obj_ID_Tracker = None
        self.obb_local = None  # OBB definition in marker-local frame: (center, axes_3x3)
        self.init_coil_angle = []
        self.init_center_coord = []

        self.is_robot_connected = False
        self.robot_name = name
        self.robot_ip = None
        self.robot_ip_options = []
        self.matrix_tracker_to_robot = None
        self.robot_coregistration_dialog = None
        self.target = None
        self.robot_init_config = {}

        self.objective = RobotObjective.NONE


        # If tracker already has fiducials set, send them to the robot; this can happen, e.g.,
        # when a pre-existing state is loaded at start-up.
        if self.tracker.AreTrackerFiducialsSet():
            self.TrackerFiducialsSet()

        success = self.LoadConfig()
        if success:
            self.ConnectToRobot()
            self.InitializeRobot()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")
        Publisher.subscribe(self.TrackerFiducialsSet, "Tracker fiducials set")
        Publisher.subscribe(self.OnRobotInitialConfig, "Robot to Neuronavigation: Initial config")

    def SaveIpConfig(self):
        session = ses.Session()
        session.SetConfig("robot_ip_options", self.robot_ip_options)

    def SaveConfig(self, key=None, value=None):
        session = ses.Session()
        robots = session.GetConfig("robots", {})
        if key is None or value is None:
            # Save the whole state
            state = {
                "robot_ip": self.robot_ip,
            }
            if self.coil_name is not None:
                state["robot_coil"] = self.coil_name
        else:
            state = robots.get(self.robot_name, {})
            state[key] = value

        robots[self.robot_name] = state
        session.SetConfig("robots", robots)

    def LoadConfig(self):
        session = ses.Session()

        robots = session.GetConfig("robots", {})
        state = robots.get(self.robot_name, {})

        self.coil_name = state.get("robot_coil", None)
        self.robot_ip = state.get("robot_ip", None)

        matrix_tracker_to_robot = state.get("tracker_to_robot", None)
        if matrix_tracker_to_robot is not None:
            self.matrix_tracker_to_robot = np.array(matrix_tracker_to_robot)

        self.robot_ip_options = session.GetConfig("robot_ip_options", [])

        coil_registration = session.GetConfig("coil_registrations", {}).get(self.coil_name, {})
        self.SetCoilRegistation(coil_registration)

        success = self.robot_ip is not None and self.matrix_tracker_to_robot is not None
        return success

    def SetCoilRegistation(self, coil_registration):
        if coil_registration:
            self.obj_ID_Tracker = coil_registration.get("obj_id", None)

            left_fiducial = coil_registration.get("fiducials")[0]
            right_fiducial = coil_registration.get("fiducials")[1]
            anterior_fiducial = coil_registration.get("fiducials")[2]
            init_coord_coil = coil_registration.get("fiducials")[3]
            init_coil_angle = coil_registration.get("orientations")[3]
            self.SetInitCoilCoords(
                left=left_fiducial,
                right=right_fiducial,
                anterior=anterior_fiducial,
                init_coord_coil=init_coord_coil,
                init_coil_angle=init_coil_angle,
            )

    def OnRobotConnectionStatus(self, data):
        # TODO: Is this check necessary?
        if not data:
            return
        if data == "Connected":
            self.is_robot_connected = True

            Publisher.sendMessage("Enable move away button", enabled=True, robot_ID=self.robot_name)
            Publisher.sendMessage(
                "Enable free drive button", enabled=True, robot_ID=self.robot_name
            )
            Publisher.sendMessage(
                "Enable clean errors button", enabled=True, robot_ID=self.robot_name
            )
        else:
            self.is_robot_connected = False

    def RegisterRobot(self):
        Publisher.sendMessage("End busy cursor")
        if not self.is_robot_connected:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
            return

        if not self.tracker.tracker_connected:
            wx.MessageBox(_("Tracker is not connect."), _("InVesalius 3"))
            return
        self.robot_coregistration_dialog = dlg.RobotCoregistrationDialog(
            robot=self, tracker=self.tracker
        )

        # Show dialog and store relevant output values.
        status = self.robot_coregistration_dialog.ShowModal()
        matrix_tracker_to_robot = self.robot_coregistration_dialog.GetValue()

        # Destroy the dialog.
        self.robot_coregistration_dialog.Destroy()
        self.robot_coregistration_dialog = None

        if status != wx.ID_OK:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
            return False

        self.matrix_tracker_to_robot = matrix_tracker_to_robot
        self.SaveConfig("tracker_to_robot", self.matrix_tracker_to_robot.tolist())
        self.InitializeRobot()

    def AbortRobotConfiguration(self):
        if self.robot_coregistration_dialog:
            self.robot_coregistration_dialog.Destroy()
            self.robot_coregistration_dialog = None

    def IsConnected(self):
        return self.is_robot_connected

    def IsReady(self):  # LUKATODO: use this check before enabling robot for navigation...
        return self.IsConnected() and (self.coil_name in self.navigation.coil_registrations)

    def SetRobotIP(self, data):
        if data is not None:
            self.robot_ip = data

    def ConnectToRobot(self):
        Publisher.sendMessage(
            "Neuronavigation to Robot: Connect to robot",
            robot_IP=self.robot_ip,
            robot_ID=self.robot_name,
        )
        pressure_setpoint = ses.Session().GetConfig("pressure_setpoint", 10.0)
        Publisher.sendMessage(
            "Neuronavigation to Robot: Pressure set point", pressure=pressure_setpoint, robot_ID=self.robot_name
        )
        print("Connected to robot")

    def InitializeRobot(self):
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set robot transformation matrix",
            data=self.matrix_tracker_to_robot.tolist(),
            robot_ID=self.robot_name,
        )
        print("Robot initialized")

    def GetCoilName(self):
        return self.coil_name

    def SetCoilName(self, name):
        self.coil_name = name
        self.SaveConfig("robot_coil", name)
        self.LoadConfig()

        self.UpdateObjIDTracker()
    
    def UpdateObjIDTracker(self):
        session = ses.Session()
        self.obj_ID_Tracker = session.GetConfig("coil_registrations", {}).get(self.coil_name, {}).get("obj_id", None)

    def SetInitCoilCoords(
        self, left=None, right=None, anterior=None, init_coord_coil=None, init_coil_angle=None
    ):
        if not all(
            [v is not None for v in [left, right, anterior, init_coord_coil, init_coil_angle]]
        ):
            return

        left, right, anterior = map(np.array, [left, right, anterior])

        init_coord_coil = np.array(init_coord_coil, dtype=float)
        init_coil_angle = np.array(init_coil_angle, dtype=float)

        center_P_clean = (left + right) / 2.0

        # Coil coordinate system from left, right, anterior fiducials
        # u_vector: width direction (left → right)
        u_vector = right - left
        # v_vector: depth direction (center → anterior)
        v_vector = anterior - center_P_clean

        R_world_to_marker = Rotation.from_euler("ZYX", init_coil_angle, degrees=True).as_matrix().T

        # --- OBB (Oriented Bounding Box) construction ---
        # Build a rectangular block from the coil fiducials:
        #   half_u: half-width  (left → right)
        #   half_v: half-depth  (center → anterior, mirrored to posterior)
        #   half_n: half-height (normal to the coil plane, using COIL_HALF_THICKNESS)
        half_u = u_vector / 2.0
        half_v = v_vector  # anterior - center is already the half-depth

        normal = np.cross(half_u, half_v)
        normal_norm = np.linalg.norm(normal)
        if normal_norm > 1e-9:
            normal_unit = normal / normal_norm
        else:
            normal_unit = np.array([0.0, 0.0, 1.0])
        half_n = normal_unit * COIL_HALF_THICKNESS

        # Transform to marker-local coordinate frame
        obb_center_local = R_world_to_marker @ (center_P_clean - init_coord_coil)
        obb_axes_local = np.array([
            R_world_to_marker @ half_u,
            R_world_to_marker @ half_v,
            R_world_to_marker @ half_n,
        ])
        self.obb_local = (obb_center_local, obb_axes_local)

    def SendTargetToRobot(self):
        # If the target is not set, return early.
        if self.target is None or not self.IsConnected():
            return False

        navigation = self.navigation
        # XXX: These are needed for computing the target in tracker coordinate system. Ensure that they are set.
        if navigation.m_change is None or navigation.obj_datas is None:
            return False

        # Compute the target in tracker coordinate system.
        coord_raw, marker_visibilities = self.tracker.TrackerCoordinates.GetCoordinates(
            robot_ID=self.robot_name
        )

        # TODO: This is done here for now because the robot code expects the y-coordinate to be flipped. When this
        #   is removed, the robot code should be updated similarly, and vice versa. Create a copy of self.target by
        #   to avoid modifying it.
        target = self.target[:]
        target[1] = -target[1]
        m_target = dcr.image_to_tracker(
            navigation.m_change,
            coord_raw,
            target,
            self.icp,
            navigation.obj_datas[self.coil_name],
        )

        Publisher.sendMessage(
            "From Neuronavigation: Send target",
            target=target,
        )

        Publisher.sendMessage(
            "Neuronavigation to Robot: Set target",
            target=m_target.tolist(),
            robot_ID=self.robot_name,
        )

    def TrackerFiducialsSet(self):
        tracker_fiducials = self.tracker.GetMatrixTrackerFiducials()
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set tracker fiducials",
            tracker_fiducials=tracker_fiducials,
            robot_ID=self.robot_name,
        )

    def SetObjective(self, objective):
        # If the objective is already set to the same value, return early.
        # This is done to avoid sending the same objective to the robot repeatedly.
        if self.objective == objective:
            return

        self.objective = objective
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set objective",
            objective=objective.value,
            robot_ID=self.robot_name,
        )

    def SetObjectiveByRobot(self, objective):
        if objective is None:
            return

        self.objective = RobotObjective(objective)
        if self.objective == RobotObjective.TRACK_TARGET:
            # Unpress 'Move away from robot' button when the robot is tracking the target.
            Publisher.sendMessage("Press move away button", pressed=False, robot_ID=self.robot_name)

        elif self.objective == RobotObjective.MOVE_AWAY_FROM_HEAD:
            # Unpress 'Track target' button when the robot is moving away from head.
            Publisher.sendMessage("Press robot button", pressed=False, robot_ID=self.robot_name)

        elif self.objective == RobotObjective.NONE:
            # Unpress 'Track target' and 'Move away from robot' buttons when the robot has no objective.
            Publisher.sendMessage("Press robot button", pressed=False, robot_ID=self.robot_name)
            Publisher.sendMessage("Press move away button", pressed=False, robot_ID=self.robot_name)

    def OnRobotInitialConfig(self, config, robot_ID = None):
        if robot_ID != self.robot_name:
            return
        self.robot_init_config = config

    def UnsetTarget(self, marker, robot_ID):
        if robot_ID != self.robot_name:
            return
        self.target = None
        Publisher.sendMessage("Neuronavigation to Robot: Unset target", robot_ID=self.robot_name)

    def SetTarget(self, marker, robot_ID):
        if robot_ID != self.robot_name:
            return
        coord = marker.position + marker.orientation

        # TODO: The coordinate systems of slice viewers and volume viewer should be unified, so that this coordinate
        #   flip wouldn't be needed.
        coord[1] = -coord[1]

        self.target = coord
        self.SendTargetToRobot()

    def SetPressureSetpoint(self, pressure):
        Publisher.sendMessage("Neuronavigation to Robot: Pressure set point", pressure=pressure, robot_ID= self.robot_name)


class Robots(metaclass=Singleton):
    def __init__(self, tracker, navigation, icp):
        self.tracker = tracker
        self.navigation = navigation
        self.icp = icp
        # TODO: optimize the dynamic creation of second robot
        self._robots = {
            "robot_1": Robot("robot_1", tracker, navigation, icp),
        }
        self.active = "robot_1"  # Default active robot
        self.RobotCoilAssociation = {}
        self.tracker_coils_id = {}

        self.distance_coils = None
        self.brake_vector = {}
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.threading_coils = threading.Thread(target=self.CalculateCoilDistance, daemon=True)

        if self.navigation.n_coils > 1:
            self.CreateSecondRobot()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.GetAllCoilsRobots, "Request update Robot Coil Association")
        Publisher.subscribe(self.SendTrackerPoses, "From Neuronavigation: Update tracker poses")
        Publisher.subscribe(
            self.AbortRobotConfiguration, "Robot to Neuronavigation: Close robot dialog"
        )
        Publisher.subscribe(
            self.OnRobotConnectionStatus, "Robot to Neuronavigation: Robot connection status"
        )
        Publisher.subscribe(self.SetObjectiveByRobot, "Robot to Neuronavigation: Set objective")

    def SetObjectiveByRobot(self, objective, robot_ID):
        robot = self.GetRobot(robot_ID)
        robot.SetObjectiveByRobot(objective)

    def OnRobotConnectionStatus(self, data, robot_ID):
        robot = self.GetRobot(robot_ID)
        robot.OnRobotConnectionStatus(data)

    def AbortRobotConfiguration(self, robot_ID):
        robot = self.GetRobot(robot_ID)
        robot.AbortRobotConfiguration()

    def ThreadingCoilDistance(self, state: bool):
        if state and not self.threading_coils.is_alive():
            self._stop_event.clear()
            self.threading_coils = threading.Thread(target=self.CalculateCoilDistance, daemon=True)
            self.threading_coils.start()
        elif not state:
            self._stop_event.set()
            if self.threading_coils.is_alive():
                self.threading_coils.join(timeout=2.0)
            with self._lock:
                self.distance_coils = None
                self.brake_vector = {}

    def CalculateCoilDistance(self):
        while not self._stop_event.is_set():
            coils_name = self.GetAllCoilsRobots()
            if not all(coils_name):
                return

            obbs_world = {}  # OBB vertices in world frame for each robot
            coords_all = {}  # Store coords for each robot
            matrix_tracker_to_robot = {}
            skip = False

            for coil_name in coils_name:
                robot = self.GetRobotByCoil(coil_name=coil_name)

                # Skip if OBB was not computed for this coil
                if robot.obb_local is None:
                    skip = True
                    break

                # Get tracker coordinates
                coords, _ = robot.tracker.TrackerCoordinates.GetCoordinates()

                pose_coil_atual = coords[robot.obj_ID_Tracker]

                t_atual = pose_coil_atual[:3]
                angles_atual = pose_coil_atual[3:]

                R_atual = Rotation.from_euler("ZYX", angles_atual, degrees=True).as_matrix()

                # Transform OBB from marker-local to world coordinates
                obb_center_local, obb_axes_local = robot.obb_local
                obb_center_world = R_atual @ obb_center_local + t_atual
                obb_axes_world = (R_atual @ obb_axes_local.T).T  # each row is a half-axis in world

                # Build the 8 vertices of the OBB
                vertices = obb_vertices_from_center_axes(obb_center_world, obb_axes_world)
                obbs_world[robot.robot_name] = vertices

                # Extract the correct rotation matrix from the Tracker-to-Robot mapping
                if robot.matrix_tracker_to_robot is not None:
                    try:
                        # The matrix might be a flattened list or (48, 1) shape from JSON
                        mat = np.array(robot.matrix_tracker_to_robot).reshape(-1, 4)
                        if mat.shape[0] == 12:
                            # Third matrix in the (12, 4) stack is the affine matrix (tracker to robot coordinates)
                            rotation_matrix = mat[8:11, 0:3]
                        else:
                            # Standard 4x4 affine matrix
                            rotation_matrix = mat[:3, :3]
                    except ValueError:
                        rotation_matrix = np.eye(3)
                else:
                    rotation_matrix = np.eye(3)
                
                matrix_tracker_to_robot[robot.robot_name] = rotation_matrix

            if skip or len(obbs_world) < 2:
                return

            # Use GJK to compute minimum distance between the two OBBs
            min_distance, closest_pt_1, closest_pt_2 = gjk_distance(
                obbs_world["robot_1"], obbs_world["robot_2"]
            )

            # Head/subject coordinate (tracker index 1)
            subject_pos = coords[1][:3]

            v1_tracker = self.CalculateBrakeVector(closest_pt_1, closest_pt_2, subject_pos)
            v2_tracker = self.CalculateBrakeVector(closest_pt_2, closest_pt_1, subject_pos)

            brake_vectors = {}
            brake_vectors["robot_1"] = matrix_tracker_to_robot["robot_1"] @ v1_tracker if v1_tracker is not None else None
            brake_vectors["robot_2"] = matrix_tracker_to_robot["robot_2"] @ v2_tracker if v2_tracker is not None else None

            min_distance = 0.5 if min_distance == 0.0 else min_distance

            with self._lock:
                self.distance_coils = min_distance
                self.brake_vector = brake_vectors

            self._stop_event.wait(0.1)

    def CalculateBrakeVector(self, closest_point_coil, closest_point_other, subject_pos):
        """
        Calculate repulsion direction vector.

        The coil should move away from:
        1. The other coil (avoid inter-coil collision)
        2. The subject's head (avoid contact with person)

        Args:
            closest_point_coil: Closest point on this coil [x, y, z]
            closest_point_other: Closest point on the other coil [x, y, z]
            subject_pos: Position of head/subject [x, y, z]

        Returns:
            Direction vector for repulsion (normalized sum of two components)
        """
        # Vector 1: REPEL from other coil
        # Direction: from other_coil → this_coil
        repel_from_other_coil = np.array(closest_point_coil, dtype=float) - np.array(
            closest_point_other, dtype=float
        )

        # Vector 2: REPEL from head/subject
        # Direction: from head → this_coil
        repel_from_subject = np.array(closest_point_coil, dtype=float) - np.array(
            subject_pos, dtype=float
        )

        norm_coil = np.linalg.norm(repel_from_other_coil)
        norm_subject = np.linalg.norm(repel_from_subject)

        if norm_coil > 1e-9 and norm_subject > 1e-9:
            # Sum of normalized vectors: combined repulsion direction
            # Both point "outward" (away from other coil AND head)
            brake_direction = (repel_from_other_coil / norm_coil) + (
                repel_from_subject / norm_subject
            )
            return brake_direction

        return None

    def SendTrackerPoses(self, poses, visibilities):
        robots = self.GetAllRobots()
        for robot_ID, robot in robots.items():
            if robot.obj_ID_Tracker is not None:
                corrected_poses = poses[0], poses[1], poses[robot.obj_ID_Tracker]
                corrected_visibilities = visibilities[0], visibilities[1], visibilities[robot.obj_ID_Tracker]
            else:
                corrected_poses = poses[0], poses[1], poses[2]
                corrected_visibilities = visibilities[0], visibilities[1], visibilities[2]

            wx.CallAfter(
                Publisher.sendMessage,
                "From Neuronavigation to robot: Update tracker poses",
                poses=corrected_poses,
                visibilities=corrected_visibilities,
                robot_ID=robot_ID,
            )

    def CreateSecondRobot(self):
        if "robot_2" not in self._robots:
            self._robots["robot_2"] = Robot("robot_2", self.tracker, self.navigation, self.icp)
            print("Second robot created")
        return self._robots["robot_2"]

    def DeleteSecondRobot(self):
        if self._robots["robot_2"] is not None:
            del self._robots["robot_2"]

    def GetRobot(self, name: str):
        return self._robots.get(name) if self._robots.get(name) is not None else None

    def GetAllRobots(self, actives=True):
        robots = {}
        for robot_id, robot in self._robots.items():
            if robot is not None or not actives:
                robots[robot_id] = robot
        return robots

    def GetActive(self):
        return self.GetRobot(self.active)

    def GetAllCoilsRobots(self):
        for robot_id in self.GetAllRobots().keys():
            robot_obj = self._robots[robot_id]
            self.RobotCoilAssociation[robot_obj.coil_name] = robot_obj.robot_name

        Publisher.sendMessage(
            "Update Robot Coil Association", robotCoilAssociation=self.RobotCoilAssociation
        )

        return self.RobotCoilAssociation

    def SetActive(self, name: str):
        if name in self.GetAllRobots():
            self.active = name
        else:
            raise ValueError(f"Robot '{name}' does not exist.")
        print(f"Active robot set to: {self.active}")

    def GetInactive(self):
        robot_name = [name for name in self.GetAllRobots() if name != self.active]
        return self.GetRobot(robot_name[0])

    # Future usage: to rename robots in the GUI
    def RenameRobot(self, old_name: str, new_name: str):
        if old_name in self.GetAllRobots():
            if new_name not in self.GetAllRobots():
                self._robots[new_name] = self.GetAllRobots().pop(old_name)
                if self.active == old_name:
                    self.active = new_name
            else:
                raise ValueError(f"Robot '{new_name}' already exists.")
        else:
            raise ValueError(f"Robot '{old_name}' does not exist.")

    def GetRobotByCoil(self, coil_name):
        for robot in self.GetAllRobots().values():
            if robot.GetCoilName() == coil_name:
                return robot
        return self.GetActive()

    def SetActiveByCoil(self, coil_name):
        robot = self.GetRobotByCoil(coil_name)
        if robot:
            self.SetActive(robot.robot_name)
            Publisher.sendMessage("Press robot button", pressed=False, robot_ID=robot.robot_name)
            Publisher.sendMessage("Update robot name label", label=robot.robot_name)
        else:
            print(f"No robot found with coil name '{coil_name}'.")

    def SendTargetToAllRobots(self):
        for robot in self.GetAllRobots().values():
            robot.SendTargetToRobot()

    def SetAllRobotsNoObjective(self):
        for robot in self.GetAllRobots().values():
            robot.SetObjective(RobotObjective.NONE)

    def AllIsReady(self):
        allReady = []
        for robot in self.GetAllRobots().values():
            allReady.append(robot.IsReady())

        return all(allReady)

    def UpdateCoilsDistance(self):
        if self.RobotCoilAssociation and len(self.RobotCoilAssociation) > 1: #TODO Improve this logic because we can use just one robot and two coils
            with self._lock:
                distance = self.distance_coils
                brake = dict(self.brake_vector)
            if distance is not None:
                robots = self.GetAllRobots()
                for robot_ID in robots.keys():
                    Publisher.sendMessage(
                        "Neuronavigation to Robot: Dynamically update distance coils",
                        distance=distance,
                        brake_vector=list(brake[robot_ID]),
                        robot_ID=robot_ID,
                    )