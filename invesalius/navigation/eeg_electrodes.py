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

"""Domain operations for EEG electrode markers.

The navigation and data panels consume the marker events emitted by
``MarkersControl`` without owning electrode or scalp-projection state.
"""

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import dist, isfinite
from pathlib import Path
from time import monotonic

from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.data.markers.surface_geometry import (
    SCALP_NORMAL_AVERAGING_RADIUS_MM,
    SurfaceGeometry,
)
from invesalius.i18n import tr as _
from invesalius.navigation.markers import MarkersControl
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton

MAX_SCALP_PROJECTION_DISTANCE_MM = 3.0
# Reject a cached pose if navigation has stopped delivering tracking samples.
MAX_PROBE_POSE_AGE_SECONDS = 1.0


@dataclass(frozen=True)
class ScalpProjection:
    position: list[float]
    orientation: list[float]
    normal: tuple[float, float, float]
    distance_mm: float


class EEGElectrodeManager(metaclass=Singleton):
    """Create and manage EEG electrodes stored in the central marker collection."""

    def __init__(self, markers: MarkersControl | None = None) -> None:
        self.markers = markers if markers is not None else MarkersControl()
        self.surface_geometry = SurfaceGeometry()
        self.registration_active = False
        self.labels_visible = True
        self._probe_position = None
        self._probe_pose_time = 0.0
        Publisher.subscribe(self.update_probe_tracking, "Update probe tracking")
        Publisher.subscribe(self.on_navigation_status, "Navigation status")

    def on_navigation_status(self, nav_status, vis_status):
        self._probe_position = None
        self._probe_pose_time = 0.0

    def update_probe_tracking(self, coord, probe_visible, head_visible):
        """Cache the probe tip independently of the object followed by the pointer."""
        self._probe_position = None
        self._probe_pose_time = monotonic()
        if probe_visible and head_visible:
            try:
                self._probe_position = self._validate_coordinate(coord[:3], "position")
            except (TypeError, ValueError):
                pass

    def get_capture_position(self) -> list[float]:
        """Only allow digitization with a recent, valid probe/head tracking sample."""
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

    def set_registration_active(self, active: bool) -> None:
        """Enable or disable creation of EEG electrode markers."""
        self.registration_active = bool(active)
        Publisher.sendMessage("EEG registration mode changed", active=self.registration_active)

    def prepare_scalp_surface(self) -> bool:
        """Create the shared smoothed scalp data when it is not cached yet."""
        return self.surface_geometry.GetSmoothedScalpSurface() is not None

    def set_labels_visible(self, visible: bool) -> None:
        """Show or hide the labels of every EEG electrode."""
        self.labels_visible = bool(visible)
        Publisher.sendMessage(
            "Set EEG electrode labels visibility",
            markers=self.electrodes,
            visible=self.labels_visible,
        )

    def get_export_paths(
        self, output_dir: str, export_format: str, filename: str | None = None
    ) -> list[Path]:
        """Return the files produced by a montage export."""
        output_path = Path(output_dir)
        export_format = export_format.upper()
        if export_format == "BIDS":
            stem = Path(filename or "sub-01_electrodes.tsv").stem
            for suffix in ("_electrodes", "_coordsystem"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            if not stem.startswith("sub-") or stem == "sub-":
                raise ValueError(
                    _(
                        "Use a BIDS filename starting with 'sub-', for example sub-01_electrodes.tsv."
                    )
                )
            return [
                output_path / f"{stem}_electrodes.tsv",
                output_path / f"{stem}_coordsystem.json",
            ]
        if export_format == "HPTS":
            return [output_path / Path(filename or "eeg_montage.hpts").with_suffix(".hpts").name]
        raise ValueError(f"Unsupported EEG montage export format: {export_format}")

    def export_montage(
        self, output_dir: str, export_format: str, filename: str | None = None
    ) -> list[str]:
        """Export all EEG electrodes in BIDS or MNE HPTS format."""
        if not self.electrodes:
            raise ValueError("There are no EEG electrodes to export.")

        output_path = Path(output_dir)
        self.get_export_paths(output_path, export_format, filename)
        output_path.mkdir(parents=True, exist_ok=True)
        export_format = export_format.upper()
        if export_format == "BIDS":
            return self._export_bids(output_path, filename)
        if export_format == "HPTS":
            return self._export_hpts(output_path, filename)
        raise ValueError(f"Unsupported EEG montage export format: {export_format}")

    def _export_bids(self, output_dir: Path, filename: str | None = None) -> list[str]:
        electrodes_path, coordsystem_path = self.get_export_paths(output_dir, "BIDS", filename)
        world_electrodes = self._get_world_electrodes()
        coordinate_description = (
            "Scanner RAS coordinate system derived from the subject MRI affine transformation."
        )
        coordsystem = {
            "EEGCoordinateSystem": "Other",
            "EEGCoordinateUnits": "mm",
            "EEGCoordinateSystemDescription": coordinate_description,
            "AnatomicalLandmarkCoordinateSystem": "Other",
            "AnatomicalLandmarkCoordinateUnits": "mm",
            "AnatomicalLandmarkCoordinateSystemDescription": coordinate_description,
            "AnatomicalLandmarkCoordinates": self._get_world_fiducials(),
            "DigitizationMethod": "InVesalius Navigator - EEG electrode digitization",
        }

        with electrodes_path.open("w", encoding="utf-8", newline="") as electrodes_file:
            writer = csv.DictWriter(
                electrodes_file,
                fieldnames=("name", "x", "y", "z"),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            for name, position in world_electrodes:
                writer.writerow(
                    {
                        "name": name,
                        "x": round(position[0], 2),
                        "y": round(position[1], 2),
                        "z": round(position[2], 2),
                    }
                )

        with coordsystem_path.open("w", encoding="utf-8") as coordsystem_file:
            json.dump(coordsystem, coordsystem_file, indent=2)

        return [str(electrodes_path), str(coordsystem_path)]

    def _export_hpts(self, output_dir: Path, filename: str | None = None) -> list[str]:
        (hpts_path,) = self.get_export_paths(output_dir, "HPTS", filename)
        lines = [
            "# Digitized points exported by InVesalius 3",
            "# Coordinate system: Scanner RAS",
        ]

        fiducials = self._get_world_fiducials()
        for name, fiducial_id in (("LPA", 1), ("NAS", 2), ("RPA", 3)):
            if name in fiducials:
                position = fiducials[name]
                lines.append(
                    f"cardinal {fiducial_id} {position[0]:.2f} {position[1]:.2f} {position[2]:.2f}"
                )

        for name, position in self._get_world_electrodes():
            lines.append(f"eeg {name} {position[0]:.2f} {position[1]:.2f} {position[2]:.2f}")

        hpts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [str(hpts_path)]

    def _get_world_electrodes(self) -> list[tuple[str, tuple[float, float, float]]]:
        from invesalius.data import imagedata_utils

        world_electrodes = []
        for electrode in sorted(self.electrodes, key=self._get_export_name):
            position, _orientation = imagedata_utils.convert_invesalius_to_world(
                position=electrode.position,
                orientation=(0.0, 0.0, 0.0),
            )
            if any(value is None or not isfinite(float(value)) for value in position):
                raise ValueError("The project does not have a valid MRI world coordinate system.")
            world_electrodes.append(
                (self._get_export_name(electrode), tuple(float(value) for value in position))
            )
        return world_electrodes

    @staticmethod
    def _get_world_fiducials() -> dict[str, list[float]]:
        from invesalius.data import imagedata_utils
        from invesalius.project import Project

        fiducials = {}
        fiducial_names = ((2, "NAS"), (0, "LPA"), (1, "RPA"))
        for index, name in fiducial_names:
            position = Project().image_fiducials[index]
            if any(not isfinite(float(value)) for value in position):
                continue
            position_world, _orientation = imagedata_utils.convert_invesalius_to_world(
                position=position,
                orientation=(0.0, 0.0, 0.0),
            )
            if any(value is None or not isfinite(float(value)) for value in position_world):
                continue
            fiducials[name] = [round(float(value), 2) for value in position_world]
        return fiducials

    @staticmethod
    def _get_export_name(electrode: Marker) -> str:
        return electrode.eeg_matched_name or electrode.label

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
        session_id: int = 1,
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
            session_id=session_id,
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

    def project_to_scalp(self, position: Sequence[float]) -> ScalpProjection:
        """Project a tracker position onto the shared smoothed scalp surface."""
        original_position = self._validate_coordinate(position, "position")
        viewer_position = original_position.copy()
        viewer_position[1] *= -1

        closest_point, closest_normal = self.surface_geometry.GetClosestPointOnSurface(
            "scalp",
            viewer_position,
            smooth_radius=SCALP_NORMAL_AVERAGING_RADIUS_MM,
        )
        projected_position = list(closest_point)
        projected_position[1] *= -1
        orientation = list(self.surface_geometry.OrientationFromNormal(closest_normal))

        return ScalpProjection(
            position=projected_position,
            orientation=orientation,
            normal=closest_normal,
            distance_mm=dist(original_position, projected_position),
        )

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
        coordinate = [float(value) for value in values]
        if len(coordinate) != 3:
            raise ValueError(f"{name} must contain exactly three values")
        if not all(isfinite(value) for value in coordinate):
            raise ValueError(_("Coordinates must contain only finite numbers."))
        return coordinate
