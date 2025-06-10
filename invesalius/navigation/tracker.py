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

import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, cast

import numpy as np
from numpy.typing import NDArray  # Added for proper ndarray type annotations

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.tracker_connection as tc
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


# Only one tracker will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Tracker(metaclass=Singleton):
    def __init__(self) -> None:
        self.tracker_connection: Optional[tc.TrackerConnection] = None
        self.tracker_id: int = const.DEFAULT_TRACKER

        self.tracker_fiducials: NDArray[np.float64] = np.full([3, 3], np.nan)
        self.tracker_fiducials_raw: NDArray[np.float64] = np.zeros((6, 6))
        self.m_tracker_fiducials_raw: NDArray[np.float64] = np.zeros((6, 4, 4))

        self.tracker_connected: bool = False

        self.thread_coord: Optional[threading.Thread] = None

        self.event_coord: threading.Event = threading.Event()

        self.TrackerCoordinates: dco.TrackerCoordinates = dco.TrackerCoordinates()

        try:
            self.LoadState()
        except:  # noqa: E722
            ses.Session().DeleteStateFile()

    def SaveConfig(self):
        tracker_configuration = self.tracker_connection.configuration
        if tracker_configuration:
            com_port = tracker_configuration.get("com_port", "")
            fn_probe = tracker_configuration.get("probe_dir", "")
            fn_ref = tracker_configuration.get("ref_dir", "")
            fn_objs = tracker_configuration.get("obj_dirs", [])
            if fn_probe and fn_ref and fn_objs:
                session = ses.Session()
                session.SetConfig("last_ndi_com_port", com_port)
                session.SetConfig("last_ndi_probe_marker", fn_probe)
                session.SetConfig("last_ndi_ref_marker", fn_ref)
                session.SetConfig("last_ndi_obj_markers", fn_objs)

    def SaveState(self) -> None:
        tracker_id: int = self.tracker_id
        tracker_fiducials = self.tracker_fiducials.tolist()
        tracker_fiducials_raw = self.tracker_fiducials_raw.tolist()
        marker_tracker_fiducials_raw = self.m_tracker_fiducials_raw.tolist()
        configuration: Optional[Dict[str, object]] = (
            self.tracker_connection.GetConfiguration() if self.tracker_connection else None
        )

        state: Dict[str, object] = {
            "tracker_id": tracker_id,
            "tracker_fiducials": tracker_fiducials,
            "tracker_fiducials_raw": tracker_fiducials_raw,
            "marker_tracker_fiducials_raw": marker_tracker_fiducials_raw,
            "configuration": configuration,
        }
        session = ses.Session()
        session.SetState("tracker", state)

    def LoadState(self) -> None:
        session = ses.Session()
        state: Optional[Dict[str, object]] = session.GetState("tracker")
        if state is None:
            return

        from typing import cast

        tracker_id: int = cast(int, state["tracker_id"])
        tracker_fiducials: NDArray[np.float64] = np.array(state["tracker_fiducials"])
        tracker_fiducials_raw: NDArray[np.float64] = np.array(state["tracker_fiducials_raw"])
        m_tracker_fiducials_raw: NDArray[np.float64] = np.array(
            state["marker_tracker_fiducials_raw"]
        )
        configuration: Optional[Dict[str, object]] = cast(
            Optional[Dict[str, object]], state["configuration"]
        )  # Modified: cast configuration

        self.tracker_id = tracker_id
        self.tracker_fiducials = tracker_fiducials
        self.tracker_fiducials_raw = tracker_fiducials_raw
        self.m_tracker_fiducials_raw = m_tracker_fiducials_raw

        self.SetTracker(tracker_id=self.tracker_id, configuration=configuration)

    def SetTracker(
        self, tracker_id: int, n_coils: int = 1, configuration: Optional[Dict[str, object]] = None
    ) -> None:
        if tracker_id:
            self.tracker_connection = tc.CreateTrackerConnection(tracker_id, n_coils)

            # Configure tracker.
            if configuration is not None:
                success: bool = self.tracker_connection.SetConfiguration(configuration)
            else:
                success: bool = self.tracker_connection.Configure()

            if not success:
                self.tracker_connection = None
                return

            # Connect to tracker.

            # XXX: Unfortunately, PolhemusTracker forms a special case here, as configuring
            #   it happens with a different workflow than the other trackers. (See
            #   PolhemusTrackerConnection class for a more detailed explanation.)
            if isinstance(self.tracker_connection, tc.PolhemusTrackerConnection):
                reconfigure: bool = configuration is None
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
                self.thread_coord = dco.ReceiveCoordinates(
                    self.tracker_connection,
                    self.tracker_id,
                    self.TrackerCoordinates,
                    self.event_coord,
                )
                if self.thread_coord is not None:
                    self.thread_coord.start()

            self.CheckSaveCoils()
            # Save last ndi configuration
            self.SaveConfig()
            self.SaveState()

    def DisconnectTracker(self) -> None:
        if self.tracker_connected:
            Publisher.sendMessage("Update status text in GUI", label=_("Disconnecting tracker ..."))
            Publisher.sendMessage("Remove sensors ID")
            Publisher.sendMessage("Remove object data")

            # Stop thread for reading tracker coordinates. Do it before disconnecting
            # the tracker to avoid reading coordinates from already disconnected tracker.
            if self.thread_coord:
                self.event_coord.set()
                self.thread_coord.join()
                self.event_coord.clear()

            assert self.tracker_connection is not None
            self.tracker_connection.Disconnect()
            if not self.tracker_connection.IsConnected():
                self.tracker_connected = False
                self.tracker_id = 0

                Publisher.sendMessage("Update status text in GUI", label=_("Tracker disconnected"))
                print("Tracker disconnected!")
            else:
                Publisher.sendMessage(
                    "Update status text in GUI", label=_("Tracker still connected")
                )
                print("Tracker still connected!")

    def IsTrackerInitialized(self) -> bool:
        return bool(self.tracker_connection and self.tracker_id and self.tracker_connected)

    def IsTrackerFiducialSet(self, fiducial_index: int) -> bool:
        return not np.isnan(self.tracker_fiducials)[fiducial_index].any()

    def AreTrackerFiducialsSet(self) -> bool:
        return not np.isnan(self.tracker_fiducials).any()

    def GetTrackerCoordinates(
        self, ref_mode_id: int, n_samples: int = 1
    ) -> Tuple[Tuple[bool, ...], NDArray[np.float64], NDArray[np.float64]]:
        coord_raw_samples: Dict[int, NDArray[np.float64]] = {}
        coord_samples: Dict[int, NDArray[np.float64]] = {}

        for i in range(n_samples):
            coord_raw, marker_visibilities = self.TrackerCoordinates.GetCoordinates()

            if ref_mode_id == const.DYNAMIC_REF:
                coord = dco.dynamic_reference_m(coord_raw[0, :], coord_raw[1, :])
            else:
                coord = coord_raw[0, :]
                coord[2] = -coord[2]

            coord_raw_samples[i] = coord_raw
            coord_samples[i] = coord

        coord_raw_avg: NDArray[np.float64] = np.median(list(coord_raw_samples.values()), axis=0)
        coord_avg: NDArray[np.float64] = np.median(list(coord_samples.values()), axis=0)

        return marker_visibilities, coord_avg, coord_raw_avg

    def SetTrackerFiducial(self, ref_mode_id: int, fiducial_index: int) -> bool:
        marker_visibilities, coord, coord_raw = self.GetTrackerCoordinates(
            ref_mode_id=ref_mode_id,
            n_samples=const.CALIBRATION_TRACKER_SAMPLES,
        )

        # If probe or head markers are not visible, show a warning and return early.
        probe_visible, head_visible, *coils_visible = marker_visibilities

        if not probe_visible:
            dlg.ShowNavigationTrackerWarning(0, "probe marker not visible")
            return False

        if not head_visible:
            dlg.ShowNavigationTrackerWarning(0, "head marker not visible")
            return False

        # Update tracker fiducial with tracker coordinates
        self.tracker_fiducials[fiducial_index, :] = coord[0:3]

        assert 0 <= fiducial_index <= 2, f"Fiducial index out of range (0-2): {fiducial_index}"

        self.tracker_fiducials_raw[2 * fiducial_index, :] = coord_raw[0, :]
        self.tracker_fiducials_raw[2 * fiducial_index + 1, :] = coord_raw[1, :]

        self.m_tracker_fiducials_raw[2 * fiducial_index, :] = dcr.compute_marker_transformation(
            coord_raw, 0
        )
        self.m_tracker_fiducials_raw[2 * fiducial_index + 1, :] = dcr.compute_marker_transformation(
            coord_raw, 1
        )

        print(f"Set tracker fiducial {fiducial_index} to coordinates {coord[0:3]}.")

        self.SaveState()

        return True

    def ResetTrackerFiducials(self) -> None:
        for m in range(3):
            self.tracker_fiducials[m, :] = [np.nan, np.nan, np.nan]
        Publisher.sendMessage("Reset tracker fiducials")
        self.SaveState()

    def GetTrackerFiducials(self) -> Tuple[NDArray[np.float64], NDArray[np.float64]]:
        return self.tracker_fiducials, self.tracker_fiducials_raw

    def GetTrackerFiducialForUI(self, index: int, coordinate_index: int) -> float:
        value: float = float(self.tracker_fiducials[index, coordinate_index])
        if np.isnan(value):
            value = 0

        return value

    def GetMatrixTrackerFiducials(self) -> List[List[float]]:
        m_probe_ref_left: NDArray[np.float64] = (
            np.linalg.inv(self.m_tracker_fiducials_raw[1]) @ self.m_tracker_fiducials_raw[0]
        )
        m_probe_ref_right: NDArray[np.float64] = (
            np.linalg.inv(self.m_tracker_fiducials_raw[3]) @ self.m_tracker_fiducials_raw[2]
        )
        m_probe_ref_nasion: NDArray[np.float64] = (
            np.linalg.inv(self.m_tracker_fiducials_raw[5]) @ self.m_tracker_fiducials_raw[4]
        )

        return [m_probe_ref_left.tolist(), m_probe_ref_right.tolist(), m_probe_ref_nasion.tolist()]

    def GetTrackerId(self) -> int:
        return self.tracker_id

    def get_trackers(self) -> List[str]:
        return cast(List[str], const.TRACKERS)

    def CheckSaveCoils(self):
        session = ses.Session()

        # 1) Read the old and new marker lists
        old_dirs = session.GetConfig("last_ndi_obj_markers", [])
        new_conf = self.tracker_connection.GetConfiguration() if self.tracker_connection else {}
        new_dirs = new_conf.get("obj_dirs", [])

        # If nothing changed, do nothing
        if new_dirs == old_dirs:
            return

        # 2) Load current registration
        regs = session.GetConfig("coil_registrations", {})

        # 3) Build a new registrations dict
        new_regs: Dict[str, Dict] = {}

        for new_idx, path_str in enumerate(new_dirs):
            base_name = Path(path_str).stem
            new_obj_id = new_idx + 2

            # If it existed before, find the old registration
            if path_str in old_dirs:
                old_idx = old_dirs.index(path_str)
                old_obj_id = old_idx + 2

                # Find the key with the old obj_id
                old_key = next((k for k, v in regs.items() if v.get("obj_id") == old_obj_id), None)
                if old_key:
                    # Copy the entire data block and only update obj_id
                    entry = regs[old_key].copy()
                    entry["obj_id"] = new_obj_id
                    new_regs[old_key] = entry
                    continue

            # If it didn't exist before, create a basic entry
            new_regs[base_name] = {"obj_id": new_obj_id}

        # 4) Save back to session
        session.SetConfig("coil_registrations", new_regs)
