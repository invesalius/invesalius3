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
from typing import Any, Dict, List, Optional

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher


# XXX: First steps towards decoupling robot and tracker, which were previously
#   tightly coupled; not fully finished, but whenever possible, robot-related
#   functionality should be gathered here.

class Robot():
    def __init__(self, tracker: Any) -> None:
        self.tracker = tracker

        self.matrix_tracker_to_robot: Optional[np.ndarray] = None

        success: bool = self.LoadState()
        if success:
            self.InitializeRobot()

        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self.AbortRobotConfiguration, 'Dialog robot destroy')

    def SaveState(self) -> None:
        matrix_tracker_to_robot: List[List[float]] = self.matrix_tracker_to_robot.tolist()

        state: Dict[str, List[List[float]]] = {
            'tracker_to_robot': matrix_tracker_to_robot,
        }
        session: ses.Session = ses.Session()
        session.SetState('robot', state)

    def LoadState(self) -> bool:
        session: ses.Session = ses.Session()
        state: Optional[Dict[str, List[List[float]]]] = session.GetState('robot')

        if state is None:
            return False

        self.matrix_tracker_to_robot = np.array(state['tracker_to_robot'])
        return True

    def ConfigureRobot(self) -> bool:
        self.robot_coregistration_dialog: dlg.RobotCoregistrationDialog = dlg.RobotCoregistrationDialog(self.tracker)

        # Show dialog and store relevant output values.
        status: int = self.robot_coregistration_dialog.ShowModal()
        matrix_tracker_to_robot: Optional[np.ndarray] = self.robot_coregistration_dialog.GetValue()

        # Destroy the dialog.
        self.robot_coregistration_dialog.Destroy()

        if status != wx.ID_OK:
            wx.MessageBox(_("Unable to connect to the robot."), _("InVesalius 3"))
            return False

        self.matrix_tracker_to_robot = matrix_tracker_to_robot

        self.SaveState()

        return True

    def AbortRobotConfiguration(self) -> None:
        if self.robot_coregistration_dialog:
            self.robot_coregistration_dialog.Destroy()

    def InitializeRobot(self) -> None:
        Publisher.sendMessage('Robot navigation mode', robot_mode=True)
        Publisher.sendMessage('Load robot transformation matrix', data=self.matrix_tracker_to_robot.tolist())

    def DisconnectRobot(self) -> None:
        Publisher.sendMessage('Robot navigation mode', robot_mode=False)
