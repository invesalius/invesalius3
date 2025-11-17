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

import numpy as np
import wx
from scipy.spatial import distance
from scipy.spatial.transform import Rotation

import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class RobotObjective(Enum):
    NONE = 0
    TRACK_TARGET = 1
    MOVE_AWAY_FROM_HEAD = 2


# Only one robot will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Robot:
    def __init__(self, name, tracker, navigation, icp):
        self.tracker = tracker
        self.navigation = navigation
        self.icp = icp
        self.enabled_in_gui = False
        self.coil_name = None
        self.shifts_center_coil = {}
        self.init_coil_angle = []
        self.init_center_coord = []

        self.is_robot_connected = False
        self.robot_name = name
        self.robot_ip = None
        self.robot_ip_options = []
        self.matrix_tracker_to_robot = None
        self.robot_coregistration_dialog = None
        self.target = None

        self.objective = RobotObjective.NONE
        self.target = None

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
        Publisher.subscribe(
            self.AbortRobotConfiguration, "Robot to Neuronavigation: Close robot dialog"
        )
        Publisher.subscribe(
            self.OnRobotConnectionStatus, "Robot to Neuronavigation: Robot connection status"
        )
        Publisher.subscribe(self.SetObjectiveByRobot, "Robot to Neuronavigation: Set objective")

        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")

        Publisher.subscribe(self.TrackerFiducialsSet, "Tracker fiducials set")

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
        self.coil_radius = state.get("coil_radius", None)
        self.robot_ip = state.get("robot_ip", None)

        self.matrix_tracker_to_robot = state.get("tracker_to_robot", None)
        if self.matrix_tracker_to_robot is not None:
            self.matrix_tracker_to_robot = np.array(self.matrix_tracker_to_robot)

        self.robot_ip_options = session.GetConfig("robot_ip_options", [])

        success = self.robot_ip is not None and self.matrix_tracker_to_robot is not None
        return success

    def OnRobotConnectionStatus(self, data, robot_ID):
        if robot_ID != self.robot_name:
            # Ignore messages for other robots.
            return
        # TODO: Is this check necessary?
        if not data:
            return
        if data == "Connected":
            self.is_robot_connected = True

        if self.is_robot_connected:
            Publisher.sendMessage("Enable move away button", enabled=True, robot_ID=robot_ID)
            Publisher.sendMessage("Enable free drive button", enabled=True, robot_ID=robot_ID)
            Publisher.sendMessage("Enable clean errors button", enabled=True, robot_ID=robot_ID)
        else:
            self.is_robot_connected = False

    def RegisterRobot(self):
        Publisher.sendMessage("End busy cursor")
        if not self.is_robot_connected:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
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

    def AbortRobotConfiguration(self, robot_ID):
        if robot_ID != self.robot_name:
            return
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

    def SetInitCoilCoords(
        self, left=None, right=None, anterior=None, init_coord_coil=None, init_coil_angle=None
    ):
        # 1. Validar dados
        if not all(
            [v is not None for v in [left, right, anterior, init_coord_coil, init_coil_angle]]
        ):
            print("Erro: Dados de registro inicial incompletos.")
            return

        left = np.array(left, dtype=float)
        right = np.array(right, dtype=float)
        anterior = np.array(anterior, dtype=float)
        init_coord_coil = np.array(init_coord_coil, dtype=float)
        init_coil_angle = np.array(init_coil_angle, dtype=float)

        center_P_clean = (left + right) / 2.0
        depth_vector_P = anterior - center_P_clean
        quintet_left_P = left + depth_vector_P
        quintet_right_P = right + depth_vector_P

        x_base = depth_vector_P / np.linalg.norm(depth_vector_P)
        y_base = (left - center_P_clean) / np.linalg.norm((left - center_P_clean))
        z_base = np.cross(x_base, y_base)
        y_base = np.cross(x_base, z_base)
        base_vector_right = (x_base, y_base, z_base)
        r = Rotation.from_euler('zyx', init_coil_angle, degrees=True)
        base_vector_marker = r.apply(np.eye(3))

        angles = []
        for idx, vector in enumerate(base_vector_marker):
            print("vector", vector)
            print(base_vector_right[idx])
            dot = np.dot(base_vector_right[idx], vector)
            cos_theta = dot / (np.linalg.norm(base_vector_right[idx]) * np.linalg.norm(vector))
            cos_theta = np.clip(cos_theta, -1.0, 1.0)
            theta = np.arccos(cos_theta)
            angles.append(np.degrees(theta))

        self.shifts_center_coil = {
            "quintet_left": quintet_left_P - init_coord_coil,
            "left": left - init_coord_coil,
            "anterior": anterior - init_coord_coil,
            "quintet_right": quintet_right_P - init_coord_coil,
            "right": right - init_coord_coil,
            "center": center_P_clean - init_coord_coil,
        }

        self.init_coil_angle = init_coil_angle
        self.R_maker = self.CalculateAngleCorrection(angles, [0, 0, 0])

        print("angles", angles)
        print("R_maker", self.R_maker)

    def CalculateAngleCorrection(self, angles_coil, init_angles):
        angles = self.angle_diff_sin_cos(angles_coil, init_angles)
        alpha, beta, gamma = angles
        ca, cb, cg = np.cos([alpha, beta, gamma])
        sa, sb, sg = np.sin([alpha, beta, gamma])
        R = np.array(
            [
                [cb * cg, -cb * sg, sb],
                [sa * sb * cg + ca * sg, -sa * sb * sg + ca * cg, -sa * cb],
                [-ca * sb * cg + sa * sg, ca * sb * sg + sa * cg, ca * cb],
            ]
        )
        return R
    
    
    def angle_diff_sin_cos(self, list_a, list_b):
        """
        Subtrai ângulos (em graus) de duas listas, normaliza o resultado para [-180, 180],
        e retorna arrays com seno e cosseno das diferenças.
        """
        a = np.array(list_a, dtype=float)
        b = np.array(list_b, dtype=float)

        # Subtrai e normaliza para [-180, 180]
        diff = (a - b + 180) % 360 - 180

        # Converte para radianos
        diff_rad = np.radians(diff)

        return diff_rad

    def SendTargetToRobot(self):
        # If the target is not set, return early.
        if self.target is None:
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

    def SetObjectiveByRobot(self, objective, robot_ID):
        if objective is None:
            return

        self.objective = RobotObjective(objective)
        if self.objective == RobotObjective.TRACK_TARGET:
            # Unpress 'Move away from robot' button when the robot is tracking the target.
            Publisher.sendMessage("Press move away button", pressed=False, robot_ID=robot_ID)

        elif self.objective == RobotObjective.MOVE_AWAY_FROM_HEAD:
            # Unpress 'Track target' button when the robot is moving away from head.
            Publisher.sendMessage("Press robot button", pressed=False, robot_ID=robot_ID)

        elif self.objective == RobotObjective.NONE:
            # Unpress 'Track target' and 'Move away from robot' buttons when the robot has no objective.
            Publisher.sendMessage("Press robot button", pressed=False, robot_ID=robot_ID)
            Publisher.sendMessage("Press move away button", pressed=False, robot_ID=robot_ID)

    def UnsetTarget(self, marker, robot_ID):
        if robot_ID != self.robot_name:
            return
        self.target = None
        Publisher.sendMessage("Neuronavigation to Robot: Unset target", robot_ID=self.robot_name)

    def SetTarget(self, marker, robot_ID):
        if robot_ID != self.robot_name or not self.IsConnected():
            return
        coord = marker.position + marker.orientation

        # TODO: The coordinate systems of slice viewers and volume viewer should be unified, so that this coordinate
        #   flip wouldn't be needed.
        coord[1] = -coord[1]

        self.target = coord
        self.SendTargetToRobot()


class Robots(metaclass=Singleton):
    def __init__(self, tracker, navigation, icp):
        self.tracker = tracker
        self.navigation = navigation
        self.icp = icp
        # TODO: optimize the dynamic creation of second robot
        self._robots = {
            "robot_1": Robot("robot_1", tracker, navigation, icp),
            "robot_2": Robot("robot_2", tracker, navigation, icp),
        }
        self.active = "robot_1"  # Default active robot
        self.RobotCoilAssociation = {}
        self.BallCreated = False

        if self.navigation.n_coils > 1:
            self.CreateSecondRobot()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.GetAllCoilsRobots, "Request update Robot Coil Association")
        Publisher.subscribe(self.SendTrackerPoses, "From Neuronavigation: Update tracker poses")

    def CalculateCoilDistance(self):
        coils_name = ["robot_1", "robot_2"]

        if all(coils_name):
            points_of_interesting_all = []

            for idx, coil_name in enumerate(coils_name):
                robot = self.GetRobotByCoil(coil_name=coil_name)
                coords, marker_visibilities = robot.tracker.TrackerCoordinates.GetCoordinates(
                    robot_ID=robot.robot_name
                )
                init_coil_angle = robot.init_coil_angle
                shifts_coil = robot.shifts_center_coil
                points_of_interesting = []
                pose_coil = coords[2 + idx]
                R = self.CalculateAngleCorrection(pose_coil[3:], init_coil_angle)
                for shifts_coil_ in shifts_coil.values():
                    point = robot.R_maker @ (R @ shifts_coil_ +  pose_coil[:3])
                    points_of_interesting.append(point)
                points_of_interesting_all.append(points_of_interesting)
            distance_coils = float("inf")
            distance_coils_ = []
            if len(points_of_interesting_all) > 1:
                for idx, points_of_interesting_1 in enumerate(points_of_interesting_all[0]):
                    for idy, points_of_interesting_2 in enumerate(points_of_interesting_all[1]):
                        distance_coils_.append(
                            distance.euclidean(points_of_interesting_1, points_of_interesting_2)
                        )
                        print(idx, idy, distance_coils_[:-1])
                if distance_coils_:
                    distance_coils = min(distance_coils_)

            return distance_coils
        return None

    def UpdaeCoilsPosesView(self, points_of_interesting):
        Publisher.sendMessage("Update dynamic Balls", positions=points_of_interesting)

    def SendTrackerPoses(self, poses, visibilities):
        robots = self.GetAllRobots()
        for robot_ID in robots.keys():
            wx.CallAfter(
                Publisher.sendMessage,
                "From Neuronavigation to robot: Update tracker poses",
                poses=poses,
                visibilities=visibilities,
                robot_ID=robot_ID,
            )

    def CreateSecondRobot(self):
        if self._robots["robot_2"] is None:
            self._robots["robot_2"] = Robot("robot_2", self.tracker, self.navigation, self.icp)
            print("Second robot created")
        return self._robots["robot_2"]

    def DeleteSecondRobot(self):
        if self._robots["robot_2"] is not None:
            del self._robots["robot_2"]
            self._robots["robot_2"] = None

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
            # if robot_obj is not None and robot_obj.IsConnected():
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

    def angle_diff_sin_cos(self, list_a, list_b):
        """
        Subtrai ângulos (em graus) de duas listas, normaliza o resultado para [-180, 180],
        e retorna arrays com seno e cosseno das diferenças.
        """
        a = np.array(list_a, dtype=float)
        b = np.array(list_b, dtype=float)

        # Subtrai e normaliza para [-180, 180]
        diff = (a - b + 180) % 360 - 180

        # Converte para radianos
        diff_rad = np.radians(diff)

        return diff_rad

    def CalculateAngleCorrection(self, angles_coil, init_angles):
        angles = self.angle_diff_sin_cos(angles_coil, init_angles)
        alpha, beta, gamma = angles
        ca, cb, cg = np.cos([alpha, beta, gamma])
        sa, sb, sg = np.sin([alpha, beta, gamma])
        R = np.array(
            [
                [cb * cg, -cb * sg, sb],
                [sa * sb * cg + ca * sg, -sa * sb * sg + ca * cg, -sa * cb],
                [-ca * sb * cg + sa * sg, ca * sb * sg + sa * cg, ca * cb],
            ]
        )
        return R

    def UpdateCoilsDistance(self, coords):
        if self.RobotCoilAssociation and len(self.RobotCoilAssociation) > 1:
            distance_coils = self.CalculateCoilDistance()
            print(distance_coils)
            if distance_coils:
                robots = self.GetAllRobots()
                for robot_ID in robots.keys():
                    Publisher.sendMessage(
                        "Neuronavigation to Robot: Dynamically update distance coils",
                        distance=distance_coils,
                        robot_ID=robot_ID,
                    )
