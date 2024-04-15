#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------

from enum import Enum

from wx import ID_OK
import numpy as np
import wx

import invesalius.constants as const
import invesalius.data.coregistration as dcr
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher
from invesalius.i18n import tr as _
from invesalius.utils import Singleton
from invesalius.navigation.tracker import Tracker


class RobotObjective(Enum):
    NONE = 0
    TRACK_TARGET = 1
    MOVE_AWAY_FROM_HEAD = 2


# Only one robot will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Robot(metaclass=Singleton):
    def __init__(self, tracker, navigation, icp):
        self.tracker = tracker
        self.navigation = navigation
        self.icp = icp

        self.enabled_in_gui = False

        self.robot_status = False
        self.robot_ip = None
        self.matrix_tracker_to_robot = None
        self.robot_coregistration_dialog = None

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
        Publisher.subscribe(self.AbortRobotConfiguration, 'Robot to Neuronavigation: Close robot dialog')
        Publisher.subscribe(self.OnRobotStatus, 'Robot to Neuronavigation: Robot connection status')
        Publisher.subscribe(self.SetObjectiveByRobot, 'Robot to Neuronavigation: Set objective')

        Publisher.subscribe(self.SetTarget, 'Set target')
        Publisher.subscribe(self.UnsetTarget, 'Unset target')

        Publisher.subscribe(self.TrackerFiducialsSet, 'Tracker fiducials set')

    def SaveConfig(self):
        matrix_tracker_to_robot = self.matrix_tracker_to_robot.tolist()

        state = {
            'robot_ip': self.robot_ip,
            'tracker_to_robot': matrix_tracker_to_robot
        }
        session = ses.Session()
        session.SetConfig('robot', state)

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig('robot')

        if state is None:
            return False

        self.robot_ip = state['robot_ip']
        self.matrix_tracker_to_robot = np.array(state['tracker_to_robot'])

        return True
        
    def OnRobotStatus(self, data):
        if data:
            self.robot_status = data

    def RegisterRobot(self):
        Publisher.sendMessage('End busy cursor')
        if not self.robot_status:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
            return

        self.robot_coregistration_dialog = dlg.RobotCoregistrationDialog(
            robot=self,
            tracker=self.tracker
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

    def AbortRobotConfiguration(self):
        if self.robot_coregistration_dialog:
            self.robot_coregistration_dialog.Destroy()

    def IsConnected(self):
        return self.robot_status
    
    def SetRobotIP(self, data):
        if data is not None:
            self.robot_ip = data

    def ConnectToRobot(self):
        Publisher.sendMessage('Neuronavigation to Robot: Connect to robot', robot_IP=self.robot_ip)
        print("Connected to robot")

    def InitializeRobot(self):
        Publisher.sendMessage('Neuronavigation to Robot: Set robot transformation matrix', data=self.matrix_tracker_to_robot.tolist())
        print("Robot initialized")

    def SendTargetToRobot(self):
        # If the target is not set, return early.
        if self.target is None:
            return False

        # Compute the target in tracker coordinate system.
        coord_raw, markers_flag = self.tracker.TrackerCoordinates.GetCoordinates()

        # TODO: This is done here for now because the robot code expects the y-coordinate to be flipped. When this
        #   is removed, the robot code should be updated similarly, and vice versa. Create a copy of self.target by
        #   to avoid modifying it.
        target = self.target[:]
        target[1] = -target[1]
        
        # XXX: These are needed for computing the target in tracker coordinate system. Ensure that they are set.
        if self.navigation.m_change is None or self.navigation.obj_data is None:
            return False

        m_target = dcr.image_to_tracker(self.navigation.m_change, coord_raw, target, self.icp, self.navigation.obj_data)

        Publisher.sendMessage('Neuronavigation to Robot: Set target',
            target=m_target.tolist(),
        )

    def TrackerFiducialsSet(self):
        tracker_fiducials = self.tracker.GetMatrixTrackerFiducials()
        Publisher.sendMessage('Neuronavigation to Robot: Set tracker fiducials', tracker_fiducials=tracker_fiducials)
        
    def SetObjective(self, objective):
        # If the objective is already set to the same value, return early.
        # This is done to avoid sending the same objective to the robot repeatedly.
        if self.objective == objective:
            return

        self.objective = objective
        Publisher.sendMessage('Neuronavigation to Robot: Set objective', objective=objective.value)

    def SetObjectiveByRobot(self, objective):
        if objective is None:
            return

        self.objective = RobotObjective(objective)
        if self.objective == RobotObjective.TRACK_TARGET:
            # Unpress 'Move away from robot' button when the robot is tracking the target.
            Publisher.sendMessage('Press move away button', pressed=False)

        elif self.objective == RobotObjective.MOVE_AWAY_FROM_HEAD:
            # Unpress 'Track target' button when the robot is moving away from head.
            Publisher.sendMessage('Press robot button', pressed=False)
            
        elif self.objective == RobotObjective.NONE:
            # Unpress 'Track target' and 'Move away from robot' buttons when the robot has no objective.
            Publisher.sendMessage('Press robot button', pressed=False)
            Publisher.sendMessage('Press move away button', pressed=False)

    def UnsetTarget(self, marker):
        self.target = None
        Publisher.sendMessage('Neuronavigation to Robot: Unset target')

    def SetTarget(self, marker):
        coord = marker.position + marker.orientation

        # TODO: The coordinate systems of slice viewers and volume viewer should be unified, so that this coordinate
        #   flip wouldn't be needed.
        coord[1] = -coord[1]

        self.target = coord
        self.SendTargetToRobot()
