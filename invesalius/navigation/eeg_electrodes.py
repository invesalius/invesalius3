# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------

"""Domain operations for EEG electrode markers.

This module intentionally has no GUI or VTK dependencies. The navigation and
data panels can consume the marker events emitted by ``MarkersControl`` without
owning the electrode state.
"""

from collections.abc import Iterable, Sequence

from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.navigation.markers import MarkersControl
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class EEGElectrodeManager(metaclass=Singleton):
    """Create and manage EEG electrodes stored in the central marker collection."""

    def __init__(self, markers: MarkersControl | None = None) -> None:
        self.markers = markers if markers is not None else MarkersControl()
        self.registration_active = False

    def set_registration_active(self, active: bool) -> None:
        """Enable or disable creation of EEG electrode markers."""
        self.registration_active = bool(active)
        Publisher.sendMessage("EEG registration mode changed", active=self.registration_active)

    @property
    def electrodes(self) -> list[Marker]:
        """Return the EEG electrode markers in their current marker-list order."""
        return self.markers.GetMarkersByType(MarkerType.EEG_ELECTRODE)

    def create(
        self,
        position: Sequence[float],
        *,
        label: str | None = None,
        orientation: Sequence[float] | None = None,
        colour: Sequence[float] = (0.0, 1.0, 0.0),
        size: float = 2.0,
        visible: bool = True,
        focus: bool = False,
        matched_name: str | None = None,
        distance_mm: float | None = None,
        confidence: str | None = None,
    ) -> Marker:
        """Create, persist and return one EEG electrode marker."""
        electrode = Marker(
            label=label or self.next_label(),
            marker_type=MarkerType.EEG_ELECTRODE,
            size=size,
            visible=visible,
            eeg_matched_name=matched_name,
            eeg_distance_mm=distance_mm,
            eeg_confidence=confidence,
        )
        electrode.position = self._validate_coordinate(position, "position")
        electrode.orientation = self._validate_coordinate(
            orientation if orientation is not None else (0.0, 0.0, 0.0),
            "orientation",
        )
        electrode.colour = self._validate_coordinate(colour, "colour")
        self.markers.AddMarker(electrode, focus=focus)
        return electrode

    def create_many(
        self, positions: Iterable[Sequence[float]], *, visible: bool = True
    ) -> list[Marker]:
        """Create EEG electrodes for each position."""
        return [self.create(position, visible=visible) for position in positions]

    def remove(self, marker_uuid: str) -> bool:
        """Remove one EEG electrode identified by UUID."""
        electrode = self._find_electrode(marker_uuid)
        if electrode is None:
            return False

        self.markers.DeleteMarker(electrode.marker_id)
        return True

    def clear(self) -> int:
        """Remove every EEG electrode and return the number removed."""
        marker_ids = [electrode.marker_id for electrode in self.electrodes]
        if marker_ids:
            self.markers.DeleteMultiple(marker_ids)
        return len(marker_ids)

    def set_visible(self, marker_uuid: str, visible: bool) -> bool:
        """Show or hide one EEG electrode."""
        electrode = self._find_electrode(marker_uuid)
        if electrode is None:
            return False

        self.markers.SetVisibility(electrode.marker_id, visible)
        return True

    def set_all_visible(self, visible: bool) -> int:
        """Show or hide every EEG electrode and return the number changed."""
        marker_ids = [electrode.marker_id for electrode in self.electrodes]
        if marker_ids:
            self.markers.SetMultipleVisibility(marker_ids, visible)
        return len(marker_ids)

    def show_all(self) -> int:
        return self.set_all_visible(True)

    def hide_all(self) -> int:
        return self.set_all_visible(False)

    def next_label(self) -> str:
        """Return the next available anonymous electrode label (E1, E2, ...)."""
        labels = {electrode.label for electrode in self.electrodes}
        index = 1
        while f"E{index}" in labels:
            index += 1
        return f"E{index}"

    def _find_electrode(self, marker_uuid: str) -> Marker | None:
        marker = self.markers.FindByUUID(marker_uuid)
        if marker is None or marker.marker_type != MarkerType.EEG_ELECTRODE:
            return None
        return marker

    @staticmethod
    def _validate_coordinate(values: Sequence[float], name: str) -> list[float]:
        coordinate = list(values)
        if len(coordinate) != 3:
            raise ValueError(f"{name} must contain exactly three values")
        return coordinate
