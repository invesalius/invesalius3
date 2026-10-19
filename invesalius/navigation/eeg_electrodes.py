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
from copy import deepcopy
from dataclasses import dataclass, replace
from math import dist, isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

import numpy as np

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
    registration: dict | None = None

    @property
    def needs_confirmation(self) -> bool:
        return self.distance_mm > MAX_SCALP_PROJECTION_DISTANCE_MM


class EEGElectrodeManager(metaclass=Singleton):
    """Create and manage EEG electrodes stored in the central marker collection."""

    def __init__(self, markers: MarkersControl | None = None) -> None:
        self.markers = markers if markers is not None else MarkersControl()
        self.surface_geometry = SurfaceGeometry()
        self.registration_active = False
        self.labels_visible = True
        self.navigation_on = False
        self._probe_position = None
        self._probe_pose_time = 0.0
        self._capture_registration = None
        self._electrode_registrations = {}
        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self.update_probe_pose, "Update probe pose")
        Publisher.subscribe(self.on_navigation_status, "Navigation status")
        Publisher.subscribe(self.on_capture_registration, "EEG capture registration")
        Publisher.subscribe(self.on_navigation_mode, "Set navigation mode")
        Publisher.subscribe(self.reset, "Close project data")

    def on_navigation_mode(self, status: bool) -> None:
        if not status:
            self.reset()

    def reset(self) -> None:
        """Discard EEG data, keeping subscriptions so the singleton can be reused."""
        self.navigation_on = False
        self._probe_position = None
        self._probe_pose_time = 0.0
        self._capture_registration = None
        self._electrode_registrations.clear()
        self.set_registration_active(False)
        self.clear()

    def on_navigation_status(self, nav_status, vis_status):
        self.navigation_on = nav_status
        self._probe_position = None
        self._capture_registration = None

    def on_capture_registration(self, matrix, use_icp, icp_matrix, reference_mode, tracker_id):
        """Snapshot the same positional registration supplied to the navigation worker."""
        source = (
            "Reference-relative tracker, Z reflected" if reference_mode else "Tracker, Z reflected"
        )
        registration = self._transform_metadata(source, "InVesalius image", matrix)
        icp = self._transform_metadata(
            "InVesalius viewer", "InVesalius viewer, ICP corrected", icp_matrix if use_icp else None
        )
        effective = registration["Matrix"]
        if use_icp:
            # bases.transform_icp applies ICP in viewer coordinates (Y reflected).
            flip_y = np.diag([1.0, -1.0, 1.0, 1.0])
            effective = (
                flip_y @ np.asarray(icp["Matrix"]) @ flip_y @ np.asarray(effective)
                if effective is not None and icp["Matrix"] is not None
                else None
            )
        self._capture_registration = {
            "TrackerID": int(tracker_id) if tracker_id is not None else None,
            "ReferenceMode": "dynamic" if reference_mode else "static",
            "OriginalDigitizedCoordinateSystem": "Tracker device coordinates, mm",
            "RawDigitizedCoordinates": None,
            "RawTrackerToReferenceMatrix": None,
            "FiducialRegistration": registration,
            "ICPEnabled": bool(use_icp),
            "ICP": icp,
            "Registration": self._transform_metadata(
                source, "InVesalius image, registered", effective
            ),
        }

    def update_probe_pose(self, m_img, coord, probe_visible, head_visible):
        """Use the coregistered probe tip and tracking validity from the same sample."""
        self._probe_position = None
        if self.navigation_on and probe_visible and head_visible:
            self._probe_position = list(coord[:3])
            self._probe_pose_time = monotonic()

    def get_capture_position(self) -> list[float]:
        """Only allow digitization with a recent, valid probe/head tracking sample."""
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
                output_path / f"{stem}_registration.json",
            ]
        if export_format in ("HPTS", "SFP", "ELC"):
            suffix = f".{export_format.lower()}"
            montage_path = (
                output_path / Path(filename or f"eeg_montage{suffix}").with_suffix(suffix).name
            )
            return [montage_path, montage_path.with_name(f"{montage_path.stem}_registration.json")]
        raise ValueError(f"Unsupported EEG montage export format: {export_format}")

    def export_montage(
        self, output_dir: str, export_format: str, filename: str | None = None
    ) -> list[str]:
        """Export a montage and mandatory registration metadata as one file set."""
        if not self.electrodes:
            raise ValueError("There are no EEG electrodes to export.")

        output_path = Path(output_dir)
        paths = self.get_export_paths(output_path, export_format, filename)
        export_format = export_format.upper()
        metadata = self._registration_metadata()
        metadata["ExportFormat"] = export_format
        metadata["ExportedFiles"] = [path.name for path in paths]
        output_path.mkdir(parents=True, exist_ok=True)
        # Serialize everything before replacing existing files, so validation
        # failures do not leave a montage without its required registration metadata.
        with TemporaryDirectory(prefix="eeg-export-", dir=output_path) as staging:
            staging_path = Path(staging)
            if export_format == "BIDS":
                self._export_bids(staging_path, filename)
            elif export_format == "HPTS":
                self._export_hpts(staging_path, filename)
            elif export_format in ("SFP", "ELC"):
                self._export_cartesian(
                    staging_path / paths[0].name,
                    export_format,
                    metadata["AnatomicalLandmarksScannerRAS_mm"],
                )
            metadata_path = staging_path / paths[-1].name
            metadata_path.write_text(
                json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
            for path in paths:
                (staging_path / path.name).replace(path)
        return [str(path) for path in paths]

    def _export_bids(self, output_dir: Path, filename: str | None = None) -> list[str]:
        electrodes_path, coordsystem_path, _registration_path = self.get_export_paths(
            output_dir, "BIDS", filename
        )
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
        hpts_path, _registration_path = self.get_export_paths(output_dir, "HPTS", filename)
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

    @staticmethod
    def _validate_export_labels(electrodes, reserved=(), single_token=False):
        """Reject labels that readers would split, discard or interpret as fiducials."""
        seen = set()
        for name, _position in electrodes:
            if (
                not name
                or name != name.strip()
                or any(character in name for character in "\r\n\t\x00")
                or (
                    single_token and (any(character.isspace() for character in name) or "#" in name)
                )
            ):
                raise ValueError(f"Invalid electrode label for this export format: {name!r}.")
            if name in seen or name in reserved:
                raise ValueError(f"Duplicate or reserved electrode label: {name!r}.")
            seen.add(name)

    def _export_cartesian(self, path, export_format, fiducials):
        """Write SFP rows or ASA ELC sections in Scanner RAS mm."""
        electrodes = self._get_world_electrodes()
        labels = (
            (("NAS", "FidNz"), ("LPA", "FidT9"), ("RPA", "FidT10"))
            if export_format == "SFP"
            else (("LPA", "LPA"), ("NAS", "Nz"), ("RPA", "RPA"))
        )
        reserved = [label for _name, label in labels] + (
            ["headshape"] if export_format == "SFP" else []
        )
        self._validate_export_labels(electrodes, reserved=reserved, single_token=True)
        points = [
            (label, fiducials[name]) for name, label in labels if name in fiducials
        ] + electrodes
        if export_format == "SFP":
            lines = [f"{name} {x:.6f} {y:.6f} {z:.6f}" for name, (x, y, z) in points]
        else:
            lines = [
                "# ASA electrode file",
                "# Coordinate system: MRI Scanner RAS",
                "UnitPosition mm",
                f"NumberPositions= {len(points)}",
                "Positions",
            ]
            lines.extend(f"{x:.6f} {y:.6f} {z:.6f}" for _name, (x, y, z) in points)
            lines.extend(["Labels", *(name for name, _position in points)])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _transform_metadata(source, destination, matrix, source_units="mm", destination_units="mm"):
        """Describe a directed positional affine; invalid or absent matrices stay null."""
        if matrix is not None:
            matrix = np.asarray(matrix, dtype=float)
            matrix = (
                matrix.tolist()
                if (
                    matrix.shape == (4, 4)
                    and np.isfinite(matrix).all()
                    and np.allclose(matrix[3], [0, 0, 0, 1])
                    and np.linalg.matrix_rank(matrix[:3, :3]) == 3
                )
                else None
            )
        return {
            "SourceCoordinateSystem": source,
            "DestinationCoordinateSystem": destination,
            "SourceCoordinateUnits": source_units,
            "DestinationCoordinateUnits": destination_units,
            "Matrix": matrix,
            "Direction": f"{source} -> {destination}",
        }

    def _registration_metadata(self):
        """Export available capture provenance without substituting current registration."""
        import invesalius
        from invesalius.data.imagedata_utils import convert_invesalius_to_world
        from invesalius.data.slice_ import Slice
        from invesalius.project import Project

        image, project = Slice(), Project()
        # Recover the positional affine using exactly the existing conversion.
        # Slice.affine is inverse, spacing-scaled geometry, not a voxel affine.
        points = [
            convert_invesalius_to_world(point, (0, 0, 0))[0]
            for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        ]
        matrix = np.eye(4)
        if any(value is None for point in points for value in point):
            raise ValueError("The project does not have a valid MRI world coordinate system.")
        matrix[:3, 3] = points[0]
        matrix[:3, :3] = np.asarray(points[1:]).T - np.asarray(points[0])[:, None]
        image_to_ras = self._transform_metadata("InVesalius image", "MRI Scanner RAS", matrix)
        if image_to_ras["Matrix"] is None:
            raise ValueError("The project does not have a valid MRI world coordinate system.")
        return {
            "Software": "InVesalius Navigator",
            "SoftwareVersion": str(invesalius.__version__),
            "MetadataVersion": 1,
            "SourceCoordinateSystem": "InVesalius image, registered",
            "SourceCoordinateUnits": "mm",
            "DestinationCoordinateSystem": "MRI Scanner RAS",
            "DestinationCoordinateUnits": "mm",
            "MRIConvention": "Scanner RAS: +X right, +Y anterior, +Z superior",
            "MRIReferenceImage": {
                "ProjectName": project.name or None,
                "ActiveImageVersion": project.active_image_version,
                "OriginalImageFile": None,
                "ArrayShapeZYX": list(image.matrix.shape),
                "SpacingXYZ_mm": [float(value) for value in image.spacing],
            },
            "MatrixConvention": "Row-major 4x4; p_destination = M @ [x,y,z,1]. Upper-left 3x3: linear part; last column: translation in destination units. Apply products rightmost first.",
            "ImageToScannerRAS": image_to_ras,
            "ElectrodeRegistrations": [
                {
                    "Name": electrode.label,
                    "MarkerUUID": str(electrode.marker_uuid),
                    "CaptureRegistration": self._electrode_registrations.get(electrode.marker_uuid),
                }
                for electrode in self.electrodes
            ],
            "RegistrationAvailability": "Null capture provenance: restored/manually created marker. Raw tracker/reference samples are not retained. Scalp projection is non-affine.",
            "AnatomicalLandmarksScannerRAS_mm": self._get_world_fiducials(round_positions=False),
            "AnatomicalLandmarkSource": "Current project image fiducials, unchanged",
            "ScannerRASToSurfaceRAS": self._transform_metadata(
                "MRI Scanner RAS", "FreeSurfer surface RAS", None
            ),
            "SurfaceRASAvailability": "Matching FreeSurfer vox2ras/vox2ras_tkr geometry is not retained; Scanner RAS is not surface RAS.",
            "ExportedCoordinateSystem": "MRI Scanner RAS",
            "ExportedCoordinateUnits": "mm",
            "AdditionalTransformations": [],
        }

    def _get_world_electrodes(self) -> list[tuple[str, tuple[float, float, float]]]:
        from invesalius.data import imagedata_utils

        world_electrodes = []
        for electrode in sorted(self.electrodes, key=lambda electrode: electrode.label):
            position, _orientation = imagedata_utils.convert_invesalius_to_world(
                position=electrode.position,
                orientation=(0.0, 0.0, 0.0),
            )
            if any(value is None or not isfinite(float(value)) for value in position):
                raise ValueError("The project does not have a valid MRI world coordinate system.")
            world_electrodes.append((electrode.label, tuple(float(value) for value in position)))
        return world_electrodes

    @staticmethod
    def _get_world_fiducials(round_positions: bool = True) -> dict[str, list[float]]:
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
            fiducials[name] = [
                round(float(value), 2) if round_positions else float(value)
                for value in position_world
            ]
        return fiducials

    @property
    def electrodes(self) -> list[Marker]:
        """Return the EEG electrode markers in their current marker-list order."""
        return self.markers.GetMarkersByType(MarkerType.EEG_ELECTRODE)

    def create(
        self,
        position: Sequence[float],
        *,
        label: str | None = None,
        orientation: Sequence[float] = (0.0, 0.0, 0.0),
        colour: Sequence[float] = (0.0, 1.0, 0.0),
        size: float = 2.0,
        visible: bool = True,
        focus: bool = False,
        session_id: int = 1,
    ) -> Marker:
        """Create, persist and return one EEG electrode marker."""
        electrode = self.markers.CreateMarker(
            position=position,
            orientation=orientation,
            colour=colour,
            size=size,
            label=label if label is not None else self.next_label(),
            marker_type=MarkerType.EEG_ELECTRODE,
            visible=visible,
            session_id=session_id,
        )
        self.markers.AddMarker(electrode, focus=focus)
        return electrode

    def prepare_capture(self, position: Sequence[float] | None = None) -> ScalpProjection:
        """Validate navigation/tracking and prepare the electrode's scalp pose."""
        probe_position = self.get_capture_position()
        capture = self.project_to_scalp(probe_position if position is None else position)
        return replace(capture, registration=deepcopy(self._capture_registration))

    def create_from_capture(self, capture: ScalpProjection, **marker_options) -> Marker:
        """Create the confirmed capture without sampling or projecting it again."""
        electrode = self.create(capture.position, orientation=capture.orientation, **marker_options)
        self._electrode_registrations[electrode.marker_uuid] = deepcopy(capture.registration)
        return electrode

    def create_many(
        self, positions: Iterable[Sequence[float]], *, visible: bool = True
    ) -> list[Marker]:
        """Create EEG electrodes for each position."""
        return [self.create(position, visible=visible) for position in positions]

    def project_to_scalp(self, position: Sequence[float]) -> ScalpProjection:
        """Project a tracker position onto the shared smoothed scalp surface."""
        original_position = list(position)
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

    def remove_many(self, marker_uuids: Iterable[str]) -> int:
        """Remove the selected EEG electrodes and return the number removed."""
        selected_uuids = set(marker_uuids)
        marker_ids = [
            electrode.marker_id
            for electrode in self.electrodes
            if electrode.marker_uuid in selected_uuids
        ]
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
