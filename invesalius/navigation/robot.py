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
import wx

import invesalius.gui.dialogs as dlg
from invesalius.pubsub import pub as Publisher


class Robot():
    def __init__(self, tracker):
        """
        Class to establish the connection between the robot and InVesalius
        :param tracker: tracker.py  instance
        """
        self.tracker = tracker
        self.trk_init = None

        self.robot_coordinates = RobotCoordinates()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnSetRobotCoordinates, 'Update Robot Coordinates')

    def OnSetRobotCoordinates(self, coord):
        self.robot_coordinates.SetRobotCoordinates(coord)

    def OnRobotConnection(self):
        dlg_ip = dlg.SetRobotIP()
        if dlg_ip.ShowModal() == wx.ID_OK:
            robot_IP = dlg_ip.GetValue()
            Publisher.sendMessage('Connect to robot', robot_IP=robot_IP)
            dlg_correg_robot = dlg.CreateTransformationMatrixRobot(self.tracker, self.robot_coordinates)
            if dlg_correg_robot.ShowModal() == wx.ID_OK:
                m_tracker_to_robot = dlg_correg_robot.GetValue()
                Publisher.sendMessage('Update robot transformation matrix', m_tracker_to_robot=m_tracker_to_robot.tolist())
                return True
        return False

class RobotCoordinates:
    """
    Class to set/get robot coordinates. Robot coordinates are acquired in ControlRobot thread.
    The class is required to avoid acquisition conflict with different threads (coordinates and navigation)
    """
    def __init__(self):
        self.coord = 6*[0]

    def SetRobotCoordinates(self, coord):
        self.coord = coord

    def GetRobotCoordinates(self):
        return self.coord