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
        if not all(
            [v is not None for v in [left, right, anterior, init_coord_coil, init_coil_angle]]
        ):
            print("Erro: Dados de registro inicial incompletos.")
            return

        left, right, anterior = map(np.array, [left, right, anterior])

        init_coord_coil = np.array(init_coord_coil, dtype=float)
        init_coil_angle = np.array(init_coil_angle, dtype=float)

        center_P_clean = (left + right) / 2.0
        depth_vector_P = anterior - center_P_clean

        # Pontos originais (6)
        points_of_interest_world = {
            "left": left,
            "right": right,
            "anterior": anterior,
            "center": center_P_clean,
            "quintet_left": left + depth_vector_P,
            "quintet_right": right + depth_vector_P,
        }

        # Pontos intermediários laterais (3)
        points_of_interest_world["mid_left_center"] = (left + center_P_clean) / 2.0
        points_of_interest_world["mid_right_center"] = (right + center_P_clean) / 2.0
        points_of_interest_world["mid_left_right"] = (left + right) / 2.0

        # Pontos em profundidade (4)
        points_of_interest_world["mid_anterior_center"] = (anterior + center_P_clean) / 2.0
        points_of_interest_world["deep_left"] = left + 2 * depth_vector_P
        points_of_interest_world["deep_right"] = right + 2 * depth_vector_P
        points_of_interest_world["deep_center"] = center_P_clean + depth_vector_P

        # Pontos quintet intermediários (3)
        center_deep = center_P_clean + depth_vector_P
        points_of_interest_world["mid_quintet_left_center"] = (
            points_of_interest_world["quintet_left"] + center_deep
        ) / 2.0
        points_of_interest_world["mid_quintet_right_center"] = (
            points_of_interest_world["quintet_right"] + center_deep
        ) / 2.0
        points_of_interest_world["mid_quintet_left_right"] = (
            points_of_interest_world["quintet_left"] + points_of_interest_world["quintet_right"]
        ) / 2.0

        # Pontos de borda (4)
        points_of_interest_world["edge_left_anterior"] = (left + anterior) / 2.0
        points_of_interest_world["edge_right_anterior"] = (right + anterior) / 2.0
        points_of_interest_world["quarter_left"] = center_P_clean + 0.75 * (left - center_P_clean)
        points_of_interest_world["quarter_right"] = center_P_clean + 0.75 * (right - center_P_clean)

        # Total: 20 pontos virtuais (6 originais + 14 novos)
        R_world_to_marker = Rotation.from_euler("ZYX", init_coil_angle, degrees=True).as_matrix().T

        self.shifts_center_coil = {
            name: R_world_to_marker @ (p_world - init_coord_coil)
            for name, p_world in points_of_interest_world.items()
        }

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
        coils_name = self.GetAllCoilsRobots()
        if not all(coils_name):
            return None

        points_of_interesting_all = []
        for coil_name in coils_name:
            robot = self.GetRobotByCoil(coil_name=coil_name)

            # Obter coordenadas do tracker
            coords, _ = robot.tracker.TrackerCoordinates.GetCoordinates(robot_ID=robot.robot_name)

            pose_idx = 2 if robot.robot_name == "robot_1" else 3
            pose_coil_atual = coords[pose_idx]

            t_atual = pose_coil_atual[:3]
            angles_atual = pose_coil_atual[3:]

            R_atual = Rotation.from_euler("ZYX", angles_atual, degrees=True).as_matrix()

            points_world = [
                R_atual @ shift_local + t_atual for shift_local in robot.shifts_center_coil.values()
            ]
            if pose_idx == 3:
                pass
            points_of_interesting_all.append(points_world)

        if len(points_of_interesting_all) < 2:
            return None

        # Otimização: calcular distância mínima sem criar lista completa
        # Com 20 pontos, evitamos criar lista de 400 elementos
        min_distance = float("inf")
        for p1 in points_of_interesting_all[0]:
            for p2 in points_of_interesting_all[1]:
                # np.linalg.norm é mais rápido que scipy.spatial.distance.euclidean
                dist = np.linalg.norm(p1 - p2)
                if dist < min_distance:
                    min_distance = dist
                    # Early exit se distância já for muito próxima de zero
                    if min_distance < 1e-6:
                        return min_distance

        return min_distance if min_distance != float("inf") else None

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

    def UpdateCoilsDistance(self, coords):
        if self.RobotCoilAssociation and len(self.RobotCoilAssociation) > 1:
            distance_coils = self.CalculateCoilDistance()
            if distance_coils:
                robots = self.GetAllRobots()
                for robot_ID in robots.keys():
                    Publisher.sendMessage(
                        "Neuronavigation to Robot: Dynamically update distance coils",
                        distance=distance_coils,
                        robot_ID=robot_ID,
                    )
