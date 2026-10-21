"""Capture, store and manage EEG electrodes without the marker collection."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import dist
from time import monotonic

import invesalius.session as ses
from invesalius.data.eeg_electrode import EEGElectrode
from invesalius.data.markers.surface_geometry import (
    SCALP_NORMAL_AVERAGING_RADIUS_MM,
    SurfaceGeometry,
)
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton

MAX_SCALP_PROJECTION_DISTANCE_MM = 3.0
MAX_PROBE_POSE_AGE_SECONDS = 1.0


@dataclass(frozen=True)
class ScalpProjection:
    position: list[float]
    orientation: list[float]
    normal: tuple[float, float, float]
    distance_mm: float

    @property
    def needs_confirmation(self) -> bool:
        return self.distance_mm > MAX_SCALP_PROJECTION_DISTANCE_MM


class EEGElectrodeManager(metaclass=Singleton):
    def __init__(self):
        self._electrodes: dict[str, EEGElectrode] = {}
        self.surface_geometry = SurfaceGeometry()
        self.registration_active = False
        self.labels_visible = True
        self.navigation_on = False
        self._probe_position = None
        self._probe_pose_time = 0.0
        self.LoadState()
        Publisher.subscribe(self.update_probe_pose, "Update probe pose")
        Publisher.subscribe(self.on_navigation_status, "Navigation status")
        Publisher.subscribe(self.on_navigation_mode, "Set navigation mode")
        Publisher.subscribe(self.reset, "Close project data")

    @property
    def electrodes(self) -> list[EEGElectrode]:
        return list(self._electrodes.values())

    def get(self, electrode_uuid: str) -> EEGElectrode | None:
        return self._electrodes.get(electrode_uuid)

    def SaveState(self):
        ses.Session().SetState("eeg_electrodes", [item.to_dict() for item in self.electrodes])

    def LoadState(self):
        session = ses.Session()
        electrodes = [EEGElectrode(**data) for data in session.GetState("eeg_electrodes", [])]
        marker_state = session.GetState("markers", []) or []
        # Migrate before MarkersControl reads the old EEG type (5), which master does not know.
        legacy = [data for data in marker_state if data.get("marker_type") == 5]
        migrated = [EEGElectrode.from_legacy_marker(data) for data in legacy]
        self._electrodes = {item.electrode_uuid: item for item in migrated + electrodes}
        if legacy:
            self.SaveState()
            session.SetState(
                "markers", [data for data in marker_state if data.get("marker_type") != 5]
            )

    def on_navigation_mode(self, status):
        if not status:
            self.reset()

    def reset(self):
        self.navigation_on = False
        self._probe_position = None
        self._probe_pose_time = 0.0
        self.set_registration_active(False)
        self.clear()

    def on_navigation_status(self, nav_status, vis_status):
        self.navigation_on = bool(nav_status)
        self._probe_position = None

    def update_probe_pose(self, m_img, coord, probe_visible, head_visible):
        self._probe_position = None
        if self.navigation_on and probe_visible and head_visible:
            self._probe_position = list(coord[:3])
            self._probe_pose_time = monotonic()

    def get_capture_position(self):
        if not self.navigation_on:
            raise RuntimeError(_("Start navigation before registering EEG electrodes."))
        if (
            self._probe_position is None
            or monotonic() - self._probe_pose_time > MAX_PROBE_POSE_AGE_SECONDS
        ):
            raise RuntimeError(
                _(
                    "Cannot register an EEG electrode: make sure the probe and head reference are tracked."
                )
            )
        return self._probe_position.copy()

    def set_registration_active(self, active):
        self.registration_active = bool(active)
        Publisher.sendMessage("EEG registration mode changed", active=self.registration_active)

    def prepare_scalp_surface(self):
        return self.surface_geometry.GetSmoothedScalpSurface() is not None

    def set_labels_visible(self, visible):
        self.labels_visible = bool(visible)
        Publisher.sendMessage("Set EEG electrode labels visibility", visible=self.labels_visible)

    def create(
        self,
        position: Sequence[float],
        *,
        label=None,
        orientation=(0.0, 0.0, 0.0),
        colour=(0.0, 1.0, 0.0),
        size=2.0,
        visible=True,
        focus=False,
        session_id=1,
    ):
        electrode = EEGElectrode(
            position=list(position),
            label=label if label is not None else self.next_label(),
            orientation=list(orientation),
            colour=list(colour),
            size=size,
            visible=bool(visible),
            session_id=session_id,
        )
        self._electrodes[electrode.electrode_uuid] = electrode
        self.SaveState()
        Publisher.sendMessage("EEG electrodes changed")
        if focus:
            Publisher.sendMessage("Select EEG electrode", electrode_uuid=electrode.electrode_uuid)
        return electrode

    def prepare_capture(self, position: Sequence[float] | None = None) -> ScalpProjection:
        probe_position = self.get_capture_position()
        return self.project_to_scalp(probe_position if position is None else position)

    def create_from_capture(self, capture: ScalpProjection, **options) -> EEGElectrode:
        return self.create(capture.position, orientation=capture.orientation, **options)

    def project_to_scalp(self, position: Sequence[float]) -> ScalpProjection:
        original_position = list(position)
        viewer_position = original_position.copy()
        viewer_position[1] *= -1
        closest_point, closest_normal = self.surface_geometry.GetClosestPointOnSurface(
            "scalp", viewer_position, smooth_radius=SCALP_NORMAL_AVERAGING_RADIUS_MM
        )
        projected_position = list(closest_point)
        projected_position[1] *= -1
        return ScalpProjection(
            position=projected_position,
            orientation=list(self.surface_geometry.OrientationFromNormal(closest_normal)),
            normal=closest_normal,
            distance_mm=dist(original_position, projected_position),
        )

    def remove_many(self, electrode_uuids: Iterable[str]) -> int:
        removed = 0
        for electrode_uuid in set(electrode_uuids):
            if self._electrodes.pop(electrode_uuid, None) is not None:
                removed += 1
        if removed:
            self.SaveState()
            Publisher.sendMessage("EEG electrodes changed")
        return removed

    def clear(self):
        return self.remove_many(self._electrodes)

    def set_visible(self, electrode_uuid, visible):
        electrode = self.get(electrode_uuid)
        if electrode is None:
            return False
        electrode.visible = bool(visible)
        self.SaveState()
        Publisher.sendMessage("EEG electrodes changed")
        return True

    def set_all_visible(self, visible):
        for electrode in self._electrodes.values():
            electrode.visible = bool(visible)
        if self._electrodes:
            self.SaveState()
            Publisher.sendMessage("EEG electrodes changed")

    def next_label(self):
        labels = {electrode.label for electrode in self._electrodes.values()}
        index = 1
        while f"E{index}" in labels:
            index += 1
        return f"E{index}"
