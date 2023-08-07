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
import invesalius.data.coregistration as dcr
import invesalius.data.tracker_connection as tc
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher
from invesalius.i18n import tr as _


class Tracker():
    def __init__(self):
        self.tracker_connection = None
        self.tracker_id = const.DEFAULT_TRACKER

        self.tracker_fiducials = np.full([3, 3], np.nan)
        self.tracker_fiducials_raw = np.zeros((6, 6))
        self.m_tracker_fiducials_raw = np.zeros((6, 4, 4))

        self.tracker_connected = False

        self.thread_coord = None

        self.event_coord = threading.Event()

        self.TrackerCoordinates = dco.TrackerCoordinates()

        self.LoadState()

    def SaveState(self):
        tracker_id = self.tracker_id
        tracker_fiducials = self.tracker_fiducials.tolist()
        tracker_fiducials_raw = self.tracker_fiducials_raw.tolist()
        marker_tracker_fiducials_raw = self.m_tracker_fiducials_raw.tolist()
        configuration = self.tracker_connection.GetConfiguration() if self.tracker_connection else None

        state = {
            'tracker_id': tracker_id,
            'tracker_fiducials': tracker_fiducials,
            'tracker_fiducials_raw': tracker_fiducials_raw,
            'marker_tracker_fiducials_raw': marker_tracker_fiducials_raw,
            'configuration': configuration,
        }
        session = ses.Session()
        session.SetState('tracker', state)

    def LoadState(self):
        session = ses.Session()
        state = session.GetState('tracker')

        if state is None:
            return

        tracker_id = state['tracker_id']
        tracker_fiducials = np.array(state['tracker_fiducials'])
        tracker_fiducials_raw = np.array(state['tracker_fiducials_raw'])
        m_tracker_fiducials_raw = np.array(state['marker_tracker_fiducials_raw'])
        configuration = state['configuration']

        self.tracker_id = tracker_id
        self.tracker_fiducials = tracker_fiducials
        self.tracker_fiducials_raw = tracker_fiducials_raw
        self.m_tracker_fiducials_raw = m_tracker_fiducials_raw

        self.SetTracker(
            tracker_id=self.tracker_id,
            configuration=configuration
        )

    def SetTracker(self, tracker_id, configuration=None):
        if tracker_id:
            self.tracker_connection = tc.CreateTrackerConnection(tracker_id)

            # Configure tracker.
            if configuration is not None:
                success = self.tracker_connection.SetConfiguration(configuration)
            else:
                success = self.tracker_connection.Configure()

            if not success:
                self.tracker_connection = None
                return

            # Connect to tracker.

            # XXX: Unfortunately, PolhemusTracker forms a special case here, as configuring
            #   it happens with a different workflow than the other trackers. (See
            #   PolhemusTrackerConnection class for a more detailed explanation.)
            if isinstance(self.tracker_connection, tc.PolhemusTrackerConnection):
                reconfigure = configuration is None
                self.tracker_connection.Connect(reconfigure)
            else:
                self.tracker_connection.Connect()

            # Check that the connection was successful.
            if not self.tracker_connection.IsConnected():
                dlg.ShowNavigationTrackerWarning(tracker_id, self.tracker_connection.GetLibMode())

                self.tracker_id = 0
                self.tracker_connected = False
            else:
                self.tracker_id = tracker_id
                self.tracker_connected = True
                self.thread_coord = dco.ReceiveCoordinates(self.tracker_connection, self.tracker_id, self.TrackerCoordinates,
                                       self.event_coord)
                self.thread_coord.start()

            self.SaveState()

    def DisconnectTracker(self):
        if self.tracker_connected:
            Publisher.sendMessage('Update status text in GUI',
                                    label=_("Disconnecting tracker ..."))
            Publisher.sendMessage('Remove sensors ID')
            Publisher.sendMessage('Remove object data')

            # Stop thread for reading tracker coordinates. Do it before disconnecting
            # the tracker to avoid reading coordinates from already disconnected tracker.
            if self.thread_coord:
                self.event_coord.set()
                self.thread_coord.join()
                self.event_coord.clear()

            self.tracker_connection.Disconnect()
            if not self.tracker_connection.IsConnected():
                self.tracker_connected = False
                self.tracker_id = 0

                Publisher.sendMessage('Update status text in GUI',
                                        label=_("Tracker disconnected"))
                print("Tracker disconnected!")
            else:
                Publisher.sendMessage('Update status text in GUI',
                                        label=_("Tracker still connected"))
                print("Tracker still connected!")

    def IsTrackerInitialized(self):
        return self.tracker_connection and self.tracker_id and self.tracker_connected

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

        self.SaveState()

    def ResetTrackerFiducials(self):
        for m in range(3):
            self.tracker_fiducials[m, :] = [np.nan, np.nan, np.nan]

        self.SaveState()

    def GetTrackerFiducials(self):
        return self.tracker_fiducials, self.tracker_fiducials_raw

    def GetTrackerFiducialForUI(self, index, coordinate_index):
        value = self.tracker_fiducials[index, coordinate_index]
        if np.isnan(value):
            value = 0

        return value

    def GetMatrixTrackerFiducials(self):
        m_probe_ref_left = np.linalg.inv(self.m_tracker_fiducials_raw[1]) @ self.m_tracker_fiducials_raw[0]
        m_probe_ref_right = np.linalg.inv(self.m_tracker_fiducials_raw[3]) @ self.m_tracker_fiducials_raw[2]
        m_probe_ref_nasion = np.linalg.inv(self.m_tracker_fiducials_raw[5]) @ self.m_tracker_fiducials_raw[4]

        return [m_probe_ref_left.tolist(), m_probe_ref_right.tolist(), m_probe_ref_nasion.tolist()]

    def GetTrackerId(self):
        return self.tracker_id

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
