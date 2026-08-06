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

import invesalius.constants as const
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


# The Robot class represents a single robot instance.
class Robot:
    def __init__(self, robot_id, tracker, navigation, icp, coil_name=None):
        self.robot_id = robot_id
        self.tracker = tracker
        self.navigation = navigation
        self.icp = icp
        self.enabled_in_gui = False

        self.coil_name = coil_name
        self.use_pressure_sensor = False
        self.is_robot_connected = False
        self.robot_ip = None
        self.robot_ip_options = []
        self.matrix_tracker_to_robot = None
        self.robot_coregistration_dialog = None
        self.target = None
        self.robot_init_config = {}

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

        Publisher.sendMessage("Neuronavigation to Robot: Request config", robot_id=self.robot_id)

    def __bind_events(self):
        Publisher.subscribe(
            self.AbortRobotConfiguration, "Robot to Neuronavigation: Close robot dialog"
        )
        Publisher.subscribe(
            self.OnRobotConnectionStatus, "Robot to Neuronavigation: Robot connection status"
        )
        Publisher.subscribe(self.SetObjectiveByRobot, "Robot to Neuronavigation: Set objective")
        Publisher.subscribe(self.OnRobotInitialConfig, "Robot to Neuronavigation: Initial config")
        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")

        Publisher.subscribe(self.TrackerFiducialsSet, "Tracker fiducials set")

    def SaveConfig(self, key=None, value=None):
        session = ses.Session()
        config_key = f"robot_{self.robot_id}"
        if key is None or value is None:
            # Save the whole state
            state = {
                "robot_ip": self.robot_ip,
                "robot_ip_options": self.robot_ip_options,
                "tracker_to_robot": self.matrix_tracker_to_robot.tolist()
                if self.matrix_tracker_to_robot is not None
                else None,
                "use_pressure_sensor": self.use_pressure_sensor,
            }
            if self.coil_name is not None:
                state["robot_coil"] = self.coil_name
        else:
            state = session.GetConfig(config_key, {})
            state[key] = value

        session.SetConfig(config_key, state)

    def LoadConfig(self):
        session = ses.Session()
        config_key = f"robot_{self.robot_id}"
        state = session.GetConfig(config_key, {})

        # Fallback to legacy "robot" config for the primary robot (id 0) to maintain backward compatibility
        if not state and self.robot_id == 0:
            state = session.GetConfig("robot", {})

        self.coil_name = state.get("robot_coil", None)

        self.robot_ip = state.get("robot_ip", None)
        self.robot_ip_options = state.get("robot_ip_options", [])

        if not self.robot_ip_options:
            self.robot_ip_options = list(const.ROBOT_IPS)

        self.use_pressure_sensor = state.get("use_pressure_sensor", False)

        self.matrix_tracker_to_robot = state.get("tracker_to_robot", None)
        if self.matrix_tracker_to_robot is not None:
            self.matrix_tracker_to_robot = np.array(self.matrix_tracker_to_robot)

        success = self.robot_ip is not None and self.matrix_tracker_to_robot is not None
        return success

    def OnRobotConnectionStatus(self, data, robot_id=None):
        if robot_id is not None and robot_id != self.robot_id:
            return

        self.is_robot_connected = True if data == "Connected" else False

        # Send to preference active robot connection status
        Publisher.sendMessage("Update robot status connection", status=data, robot_id=self.robot_id)
        Publisher.sendMessage(
            "Enable robot", enabled=self.is_robot_connected, robot_id=self.robot_id
        )

        # If the robot is connected, we add the robot IP to the list of options if it's not already there, and request the robot-side config.
        if self.is_robot_connected:
            if self.robot_ip not in self.robot_ip_options and self.robot_ip is not None:
                self.robot_ip_options.append(self.robot_ip)

            print("Connected to robot")

            # Ensure we fetch the robot-side config early so features like the force/pressure
            # overlay can be initialized without requiring the Preferences dialog to be opened.
            Publisher.sendMessage(
                "Neuronavigation to Robot: Request config", robot_id=self.robot_id
            )
        else:
            self.SetCoilName(None)
            Publisher.sendMessage("Update option main coil", done=True)

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

        if status != wx.ID_OK:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
            return False

        self.matrix_tracker_to_robot = matrix_tracker_to_robot
        self.SaveConfig()
        self.InitializeRobot()

    def AbortRobotConfiguration(self, robot_id=None):
        if robot_id is not None and robot_id != self.robot_id:
            return

        if self.robot_coregistration_dialog:
            self.robot_coregistration_dialog.Destroy()

    def IsConnected(self):
        return self.is_robot_connected

    def IsReady(self):
        return self.IsConnected() and (self.coil_name in self.navigation.coil_registrations)

    def SetRobotIP(self, data):
        if data is not None:
            self.robot_ip = data

    def ConnectToRobot(self, ip=None):
        if ip is not None:
            self.SetRobotIP(ip)

        if self.IsConnected():
            self.is_robot_connected = False
            Publisher.sendMessage(
                "Enable robot", enabled=self.is_robot_connected, robot_id=self.robot_id
            )

        Publisher.sendMessage(
            "Neuronavigation to Robot: Connect to robot",
            robot_IP=self.robot_ip,
            robot_id=self.robot_id,
        )

    def InitializeRobot(self):
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set robot transformation matrix",
            data=self.matrix_tracker_to_robot.tolist(),
            robot_id=self.robot_id,
        )
        self.SetCoilName(self.coil_name) if self.coil_name is not None else "default_coil"
        Publisher.sendMessage("Robot transformation matrix set")
        print("Robot initialized")

    def GetCoilName(self):
        return self.coil_name

    def SetCoilName(self, name):
        self.coil_name = name

        if self.coil_name not in self.navigation.coil_registrations:
            return

        coil_idx = self.navigation.coil_registrations[self.coil_name]["obj_id"]

        Publisher.sendMessage(
            "Neuronavigation to Robot: Set coil index",
            coil_idx=coil_idx,
            robot_id=self.robot_id,
        )
        self.SaveConfig("robot_coil", name)

    def SendTargetToRobot(self):
        if not self.IsReady():
            return

        # If the target is not set, return early.
        if self.target is None or self.navigation.main_coil != self.coil_name:
            return False

        navigation = self.navigation

        # XXX: These are needed for computing the target in tracker coordinate system. Ensure that they are set.
        if navigation.m_change is None or self.coil_name not in self.navigation.obj_datas:
            return False

        # Compute the target in tracker coordinate system.
        coord_raw, marker_visibilities = self.tracker.TrackerCoordinates.GetCoordinates()

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
            robot_id=self.robot_id,
        )

    def TrackerFiducialsSet(self):
        tracker_fiducials = self.tracker.GetMatrixTrackerFiducials()
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set tracker fiducials",
            tracker_fiducials=tracker_fiducials,
            robot_id=self.robot_id,
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
            robot_id=self.robot_id,
        )

        if self.objective == RobotObjective.NONE:
            Publisher.sendMessage(
                "Robot to Neuronavigation: Update robot warning", robot_warning=""
            )

    def SetObjectiveByRobot(self, objective, robot_id=None):
        if robot_id is not None and robot_id != self.robot_id:
            return

        if objective is None:
            return

        self.objective = RobotObjective(objective)
        if self.objective == RobotObjective.TRACK_TARGET:
            # Unpress 'Move away from robot' button when the robot is tracking the target.
            Publisher.sendMessage("Press move away button", pressed=False)

        elif self.objective == RobotObjective.MOVE_AWAY_FROM_HEAD:
            # Unpress 'Track target' button when the robot is moving away from head.
            Publisher.sendMessage("Press robot button", pressed=False)

        elif self.objective == RobotObjective.NONE:
            # Unpress 'Track target' and 'Move away from robot' buttons when the robot has no objective.
            Publisher.sendMessage("Press robot button", pressed=False)
            Publisher.sendMessage("Press move away button", pressed=False)

    def OnRobotInitialConfig(self, config, robot_id=None):
        if robot_id is not None and robot_id != self.robot_id:
            return

        if not config:
            return

        self.robot_init_config = config
        self.UpdatePressureActiveState(config.get("use_pressure_sensor", False))

    def UpdatePressureActiveState(self, active, notify_robot=False):
        self.use_pressure_sensor = active
        self.SaveConfig("use_pressure_sensor", self.use_pressure_sensor)

        Publisher.sendMessage("Set visibility robot force visualizer", visible=active)

        if active:
            pressure_setpoint = ses.Session().GetConfig("pressure_setpoint", 5.0)
            Publisher.sendMessage(
                "Neuronavigation to Robot: Pressure set point",
                pressure=pressure_setpoint,
                robot_id=self.robot_id,
            )

        if notify_robot:
            Publisher.sendMessage(
                "Neuronavigation to Robot: Update config",
                use_pressure_sensor=self.use_pressure_sensor,
                robot_id=self.robot_id,
            )

    def UnsetTarget(self, marker):
        self.target = None
        Publisher.sendMessage("Neuronavigation to Robot: Unset target", robot_id=self.robot_id)

    def SetTarget(self, marker):
        coord = marker.position + marker.orientation

        # TODO: The coordinate systems of slice viewers and volume viewer should be unified, so that this coordinate
        #   flip wouldn't be needed.
        coord[1] = -coord[1]

        self.target = coord
        self.SendTargetToRobot()

    def SetPressureSetpoint(self, pressure):
        Publisher.sendMessage(
            "Neuronavigation to Robot: Pressure set point",
            pressure=pressure,
            robot_id=self.robot_id,
        )

    def CheckConnection(self):
        Publisher.sendMessage(
            "Neuronavigation to Robot: Check connection robot", robot_id=self.robot_id
        )

    def SetFreeDrive(self, enabled):
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set free drive", set=enabled, robot_id=self.robot_id
        )

    def ResetErrors(self):
        if self.objective == RobotObjective.TRACK_TARGET:
            self.SetObjective(RobotObjective.NONE)

        Publisher.sendMessage(
            "Neuronavigation to Robot: Reset errors",
            robot_id=self.robot_id,
        )


class Robots(metaclass=Singleton):
    """
    Manager class for multiple Robot instances.
    Maintains a mapping of robot_id to Robot and coil_name to Robot.
    """

    def __init__(self):
        self.robots_by_id = {}
        self.robots_by_coil = {}
        self.n_robots_created = 0

    def AddRobot(self, tracker, navigation, icp, coil_name=None):
        robot_id = self.n_robots_created
        self.n_robots_created += 1

        new_robot = Robot(robot_id, tracker, navigation, icp, coil_name)
        self.robots_by_id[robot_id] = new_robot
        if coil_name:
            self.robots_by_coil[coil_name] = new_robot
        return new_robot

    def GetActiveRobot(self, main_coil_name):
        return self.robots_by_coil.get(main_coil_name)

    def GetRobot(self, robot_id):
        return self.robots_by_id.get(robot_id)
