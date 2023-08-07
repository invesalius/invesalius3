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

import numpy as np
import wx

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher
from invesalius.i18n import tr as _


# XXX: First steps towards decoupling robot and tracker, which were previously
#   tightly coupled; not fully finished, but whenever possible, robot-related
#   functionality should be gathered here.

class Robot():
    def __init__(self, tracker):
        self.tracker = tracker

        self.matrix_tracker_to_robot = None
        self.robot_coregistration_dialog = None

        success = self.LoadState()
        if success:
            self.InitializeRobot()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.AbortRobotConfiguration, 'Dialog robot destroy')

    def SaveState(self):
        matrix_tracker_to_robot = self.matrix_tracker_to_robot.tolist()

        state = {
            'tracker_to_robot': matrix_tracker_to_robot,
        }
        session = ses.Session()
        session.SetState('robot', state)

    def LoadState(self):
        session = ses.Session()
        state = session.GetState('robot')

        if state is None:
            return False

        self.matrix_tracker_to_robot = np.array(state['tracker_to_robot'])
        return True

    def ConfigureRobot(self):
        self.robot_coregistration_dialog = dlg.RobotCoregistrationDialog(self.tracker)

        # Show dialog and store relevant output values.
        status = self.robot_coregistration_dialog.ShowModal()
        matrix_tracker_to_robot = self.robot_coregistration_dialog.GetValue()

        # Destroy the dialog.
        self.robot_coregistration_dialog.Destroy()

        if status != wx.ID_OK:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
            return False

        self.matrix_tracker_to_robot = matrix_tracker_to_robot

        self.SaveState()

        return True

    def AbortRobotConfiguration(self):
        if self.robot_coregistration_dialog:
            self.robot_coregistration_dialog.Destroy()

    def InitializeRobot(self):
        Publisher.sendMessage('Robot navigation mode', robot_mode=True)
        Publisher.sendMessage('Load robot transformation matrix', data=self.matrix_tracker_to_robot.tolist())

    def DisconnectRobot(self):
        Publisher.sendMessage('Robot navigation mode', robot_mode=False)
