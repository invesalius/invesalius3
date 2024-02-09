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

import threading

from wx import ID_OK
import numpy as np
import wx

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton
from invesalius.navigation.tracker import Tracker

# Only one robot will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Robot(metaclass=Singleton):
    def __init__(self):
        self.tracker = Tracker()

        self.robot_status = None
        self.robot_ip = None
        self.matrix_tracker_to_robot = None
        self.robot_coregistration_dialog = None

        success = self.LoadConfig()
        if success:
            self.ConnectToRobot()
            self.InitializeRobot()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.AbortRobotConfiguration, 'Dialog robot destroy')
        Publisher.subscribe(self.OnRobotStatus, 'Robot connection status')

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
        self.robot_coregistration_dialog = dlg.RobotCoregistrationDialog(self, self.tracker)

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
        Publisher.sendMessage('Connect to robot', robot_IP=self.robot_ip)
        print("Connected to Robot!")

    def InitializeRobot(self):
        Publisher.sendMessage('Robot navigation mode', robot_mode=True)
        Publisher.sendMessage('Load robot transformation matrix', data=self.matrix_tracker_to_robot.tolist())
        print("Robot Initialized!")

    def DisconnectRobot(self):
        Publisher.sendMessage('Robot navigation mode', robot_mode=False)
