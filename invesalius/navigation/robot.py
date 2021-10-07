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
import queue

import invesalius.data.bases as db
import invesalius.gui.dialogs as dlg
from invesalius.pubsub import pub as Publisher

try:
    import invesalius.data.elfin as elfin
    import invesalius.data.elfin_robot as elfin_process
    has_robot = True
except ImportError:
    has_robot = False

class Robot():
    def __init__(self):
        self.trk_init = None
        self.robottarget_queue = None
        self.objattarget_queue = None
        self.process_tracker = None

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnSendCoordinates, 'Send coord to robot')
        Publisher.subscribe(self.OnUpdateRobotTargetMatrix, 'Robot target matrix')
        Publisher.subscribe(self.OnObjectTarget, 'Coil at target')

    def OnRobotConnection(self, tracker, robotcoordinates):
        if not tracker.trk_init[0][0] or not tracker.trk_init[1][0]:
            dlg.ShowNavigationTrackerWarning(tracker.tracker_id, tracker.trk_init[1])
            tracker.tracker_id = 0
            tracker.tracker_connected = False
        else:
            tracker.trk_init.append(robotcoordinates)
            self.process_tracker = elfin_process.TrackerProcessing()
            dlg_correg_robot = dlg.CreateTransformationMatrixRobot(tracker)
            if dlg_correg_robot.ShowModal() == wx.ID_OK:
                M_tracker_2_robot = dlg_correg_robot.GetValue()
                db.transform_tracker_2_robot.M_tracker_2_robot = M_tracker_2_robot
                self.robot_server = tracker.trk_init[1][0]
                self.trk_init = tracker.trk_init
            else:
                dlg.ShowNavigationTrackerWarning(tracker.tracker_id, 'disconnect')
                tracker.trk_init = None
                tracker.tracker_id = 0
                tracker.tracker_connected = False

        # Publisher.sendMessage('Update tracker initializer',
        #                       nav_prop=(tracker.tracker_id, tracker.trk_init, tracker.TrackerCoordinates, tracker.GetReferenceMode()))

    def StartRobotNavigation(self, tracker, robotcoordinates, coord_queue):
        if tracker.event_robot.is_set():
            tracker.event_robot.clear()
        elfin_process.ControlRobot(self.trk_init, tracker, robotcoordinates,
                                   [coord_queue, self.robottarget_queue,
                                    self.objattarget_queue],
                                   self.process_tracker, tracker.event_robot).start()

    def OnSendCoordinates(self, coord):
        self.robot_server.SendCoordinates(coord)

    def OnUpdateRobotTargetMatrix(self, robot_tracker_flag, m_change_robot2ref):
        try:
            self.robottarget_queue.put_nowait([robot_tracker_flag, m_change_robot2ref])
        except queue.Full:
            print('full target')
            pass

    def OnObjectTarget(self, state):
        try:
            if self.objattarget_queue:
                self.objattarget_queue.put_nowait(state)
        except queue.Full:
            #print('full flag target')
            pass

    def SetRobotQueues(self, queues):
        self.robottarget_queue, self.objattarget_queue = queues