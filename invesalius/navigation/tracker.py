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

import numpy as np
import threading

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.trackers as dt
import invesalius.gui.dialogs as dlg
import invesalius.data.coregistration as dcr
from invesalius.pubsub import pub as Publisher


class Tracker():
    def __init__(self):
        self.trk_init = None
        self.tracker_id = const.DEFAULT_TRACKER

        self.tracker_fiducials = np.full([3, 3], np.nan)
        self.tracker_fiducials_raw = np.zeros((6, 6))
        self.m_tracker_fiducials_raw = np.zeros((6, 4, 4))

        self.tracker_connected = False

        self.thread_coord = None

        self.event_coord = threading.Event()
        self.event_robot = threading.Event()

        self.TrackerCoordinates = dco.TrackerCoordinates()

    def SetTracker(self, new_tracker):
        if new_tracker:
            self.DisconnectTracker()

            self.trk_init = dt.TrackerConnection(new_tracker, None, 'connect')
            if not all(list(self.trk_init)):
                dlg.ShowNavigationTrackerWarning(self.tracker_id, self.trk_init[1])

                self.tracker_id = 0
                self.tracker_connected = False
            else:
                self.tracker_id = new_tracker
                self.tracker_connected = True
                self.thread_coord = dco.ReceiveCoordinates(self.trk_init, self.tracker_id, self.TrackerCoordinates,
                                       self.event_coord)
                self.thread_coord.start()

    def DisconnectTracker(self):
        if self.tracker_connected:
            self.ResetTrackerFiducials()
            Publisher.sendMessage('Update status text in GUI',
                                    label=_("Disconnecting tracker ..."))
            Publisher.sendMessage('Remove sensors ID')
            Publisher.sendMessage('Remove object data')
            Publisher.sendMessage('Robot navigation mode', robot_mode=False)
            self.trk_init = dt.TrackerConnection(self.tracker_id, self.trk_init[0], 'disconnect')
            if not self.trk_init[0]:
                self.tracker_connected = False
                self.tracker_id = 0

                if self.thread_coord:
                    self.event_coord.set()
                    self.event_robot.set()
                    self.thread_coord.join()
                    self.event_coord.clear()
                    self.event_robot.clear()


                Publisher.sendMessage('Update status text in GUI',
                                        label=_("Tracker disconnected"))
                print("Tracker disconnected!")
            else:
                Publisher.sendMessage('Update status text in GUI',
                                        label=_("Tracker still connected"))
                print("Tracker still connected!")

    def ConnectToRobot(self, robot):
        if robot.OnRobotConnection():
            Publisher.sendMessage('Robot navigation mode', robot_mode=True)

    def IsTrackerInitialized(self):
        return self.trk_init and self.tracker_id and self.tracker_connected

    def AreTrackerFiducialsSet(self):
        return not np.isnan(self.tracker_fiducials).any()

    def GetTrackerCoordinates(self, ref_mode_id, n_samples=1):
        coord_raw_samples = {}
        coord_samples = {}

        for i in range(n_samples):
            coord_raw, markers_flag = self.TrackerCoordinates.GetCoordinates()

            if ref_mode_id == const.DYNAMIC_REF:
                coord = dco.dynamic_reference_m(coord_raw[0, :], coord_raw[1, :])
            else:
                coord = coord_raw[0, :]
                coord[2] = -coord[2]

            coord_raw_samples[i] = coord_raw
            coord_samples[i] = coord

        coord_raw_avg = np.median(list(coord_raw_samples.values()), axis=0)
        coord_avg = np.median(list(coord_samples.values()), axis=0)

        return coord_avg, coord_raw_avg

    def SetTrackerFiducial(self, ref_mode_id, fiducial_index):
        coord, coord_raw = self.GetTrackerCoordinates(
            ref_mode_id=ref_mode_id,
            n_samples=const.CALIBRATION_TRACKER_SAMPLES,
        )

        # Update tracker fiducial with tracker coordinates
        self.tracker_fiducials[fiducial_index, :] = coord[0:3]

        assert 0 <= fiducial_index <= 2, "Fiducial index out of range (0-2): {}".format(fiducial_index)

        self.tracker_fiducials_raw[2 * fiducial_index, :] = coord_raw[0, :]
        self.tracker_fiducials_raw[2 * fiducial_index + 1, :] = coord_raw[1, :]

        self.m_tracker_fiducials_raw[2 * fiducial_index, :] = dcr.compute_marker_transformation(coord_raw, 0)
        self.m_tracker_fiducials_raw[2 * fiducial_index + 1, :] = dcr.compute_marker_transformation(coord_raw, 1)

        print("Set tracker fiducial {} to coordinates {}.".format(fiducial_index, coord[0:3]))

    def ResetTrackerFiducials(self):
        for m in range(3):
            self.tracker_fiducials[m, :] = [np.nan, np.nan, np.nan]

    def GetTrackerFiducials(self):
        return self.tracker_fiducials, self.tracker_fiducials_raw

    def GetMatrixTrackerFiducials(self):
        m_probe_ref_left = np.linalg.inv(self.m_tracker_fiducials_raw[1]) @ self.m_tracker_fiducials_raw[0]
        m_probe_ref_right = np.linalg.inv(self.m_tracker_fiducials_raw[3]) @ self.m_tracker_fiducials_raw[2]
        m_probe_ref_nasion = np.linalg.inv(self.m_tracker_fiducials_raw[5]) @ self.m_tracker_fiducials_raw[4]

        return [m_probe_ref_left.tolist(), m_probe_ref_right.tolist(), m_probe_ref_nasion.tolist()]

    def GetTrackerInfo(self):
        return self.trk_init, self.tracker_id

    def UpdateUI(self, selection_ctrl, numctrls_fiducial, txtctrl_fre):
        if self.tracker_connected:
            selection_ctrl.SetSelection(self.tracker_id)
        else:
            selection_ctrl.SetSelection(0)

        # Update tracker location in the UI.
        for m in range(3):
            coord = self.tracker_fiducials[m, :]
            for n in range(0, 3):
                value = 0.0 if np.isnan(coord[n]) else float(coord[n])
                numctrls_fiducial[m][n].SetValue(value)

        txtctrl_fre.SetValue('')
        txtctrl_fre.SetBackgroundColour('WHITE')

    def get_trackers(self):
        return const.TRACKERS
