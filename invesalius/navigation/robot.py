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
        self.robots = {
            "robot_1": Robot("robot_1", tracker, navigation, icp),
        }
        self.active = "robot_1"  # Default active robot
        self.SendIDs()

        if self.navigation.n_coils > 1:
            self.CreateSecondRobot()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.GetAllCoilsRobots, "Request update Robot Coil Association")

    def SendIDs(self):
        RobotIds = list(self.robots.keys())
        Publisher.sendMessage("Set robot IDs", robotIDs=RobotIds)

    def CreateSecondRobot(self):
        if "robot_2" not in self.robots:
            self.robots["robot_2"] = Robot("robot_2", self.tracker, self.navigation, self.icp)
            print("Second robot setup panel created")
        self.SendIDs()

    def GetRobot(self, name: str):
        return self.robots.get(name)

    def GetActive(self):
        return self.GetRobot(self.active)

    def GetAllCoilsRobots(self):
        RobotCoilAssociation = {}
        for robot_id in self.robots:
            robot_obj = self.robots[robot_id]
            if robot_obj.IsConnected():
                RobotCoilAssociation[robot_obj.coil_name] = robot_obj.robot_name

        Publisher.sendMessage(
            "Update Robot Coil Association", robotCoilAssociation=RobotCoilAssociation
        )

        return RobotCoilAssociation

    def SetActive(self, name: str):
        if name in self.robots:
            self.active = name
        else:
            raise ValueError(f"Robot '{name}' does not exist.")
        print(f"Active robot set to: {self.active}")

    def GetInactive(self):
        robot_name = [name for name in self.robots if name != self.active]
        return self.GetRobot(robot_name[0])

    # Future usage: to rename robots in the GUI
    def RenameRobot(self, old_name: str, new_name: str):
        if old_name in self.robots:
            if new_name not in self.robots:
                self.robots[new_name] = self.robots.pop(old_name)
                if self.active == old_name:
                    self.active = new_name
            else:
                raise ValueError(f"Robot '{new_name}' already exists.")
        else:
            raise ValueError(f"Robot '{old_name}' does not exist.")

    def GetRobotByCoil(self, coil_name):
        for robot in self.robots.values():
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
        for robot_name, robot in self.robots.items():
            robot.SendTargetToRobot()

    def SetAllRobotsNoObjective(self):
        for robot_name, robot in self.robots.items():
            robot.SetObjective(RobotObjective.NONE)

    def AllIsReady(self):
        allReady = []
        for robot_name, robot in self.robots.items():
            allReady.append(robot.IsReady())

        return all(allReady)
