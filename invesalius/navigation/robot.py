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
import invesalius.data.bases as db
from invesalius.pubsub import pub as Publisher


class RobotCoordinates:
    """
    Class to set/get robot coordinates. Robot coordinates are acquired in ControlRobot thread.
    The class is required to avoid acquisition conflict with different threads (coordinates and navigation)
    """
    def __init__(self):
        self.coord = 6*[0]
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetRobotCoordinates, 'Update Robot Coordinates')

    def SetRobotCoordinates(self, coord):
        self.coord = coord

    def GetRobotCoordinates(self):
        coil_robot_in_tracker = db.transform_robot_to_tracker().transformation_tracker_to_robot(self.coord)
        if coil_robot_in_tracker is None:
            coil_robot_in_tracker = self.coord

        return coil_robot_in_tracker
