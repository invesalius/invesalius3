# -*- coding: UTF-8 -*-
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
"""EEG/MEG electrodes, montage exports and cortical source reconstruction."""

import csv
import json
import operator
from dataclasses import asdict, dataclass, field
from math import isfinite
from pathlib import Path
from struct import pack, unpack
from tempfile import TemporaryDirectory
from time import time_ns
from uuid import uuid4

import nibabel as nib
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from invesalius.data.time_series import TimeAxis
from invesalius.i18n import tr as _
from invesalius.reader.others_reader import read_image


@dataclass
class EEGElectrode:
    position: list[float]
    label: str
    orientation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    colour: list[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    size: float = 2.0
    visible: bool = True
    session_id: int = 1
    electrode_uuid: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        for values in (self.position, self.orientation, self.colour):
            if len(values) != 3 or not all(isfinite(value) for value in values):
                raise ValueError("Electrode coordinates and colours require three finite numbers.")
        if not isfinite(self.size) or self.size <= 0:
            raise ValueError("Electrode size must be positive and finite.")
        if any(value < 0 or value > 1 for value in self.colour):
            raise ValueError("Electrode colour components must be between 0 and 1.")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("An electrode needs a nonempty label.")
        if not isinstance(self.electrode_uuid, str) or not self.electrode_uuid:
            raise ValueError("An electrode needs a nonempty UUID.")

    def to_dict(self):
        return asdict(self)


class EEGMontage:
    """Serialize electrode montages and their MRI coordinate metadata."""

    @staticmethod
    def get_export_paths(
        output_dir: str, export_format: str, filename: str | None = None
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
        if export_format in ("HPTS", "SFP", "ELC", "FIF"):
            montage_path = (
                output_path
                / Path(filename or "eeg_montage").with_suffix(f".{export_format.lower()}").name
            )
            paths = [montage_path]
            if export_format == "FIF":
                stem = montage_path.stem
                if stem.endswith(("-dig", "_dig")):
                    stem = stem[:-4]
                montage_path = montage_path.with_name(f"{stem}-dig.fif")
                paths = [montage_path, montage_path.with_name(f"{stem}-trans.fif")]
            return paths + [montage_path.with_name(f"{montage_path.stem}_registration.json")]
        raise ValueError(f"Unsupported EEG montage export format: {export_format}")

    @staticmethod
    def export_montage(
        electrodes, output_dir: str, export_format: str, filename: str | None = None
    ) -> list[str]:
        """Export a montage and mandatory registration metadata as one file set."""
        if not electrodes:
            raise ValueError("There are no EEG electrodes to export.")

        output_path = Path(output_dir)
        paths = EEGMontage.get_export_paths(output_path, export_format, filename)
        export_format = export_format.upper()
        world_electrodes = EEGMontage._get_world_electrodes(electrodes)
        EEGMontage._validate_export_labels(world_electrodes, single_token=export_format == "HPTS")
        fiducials = EEGMontage._get_world_fiducials()
        metadata = EEGMontage._registration_metadata(electrodes, fiducials)
        metadata.update(ExportFormat=export_format, ExportedFiles=[path.name for path in paths])
        output_path.mkdir(parents=True, exist_ok=True)
        # Serialize everything before replacing existing files, so validation
        # failures do not leave a montage without its required registration metadata.
        with TemporaryDirectory(prefix="eeg-export-", dir=output_path) as staging:
            staged_paths = [Path(staging) / path.name for path in paths]
            if export_format == "BIDS":
                EEGMontage._export_bids(*staged_paths[:2], world_electrodes, fiducials)
            elif export_format == "FIF":
                EEGMontage._export_fif(*staged_paths[:2], world_electrodes, metadata)
            else:
                EEGMontage._export_text(staged_paths[0], export_format, world_electrodes, fiducials)
            staged_paths[-1].write_text(
                json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
            for staged, destination in zip(staged_paths, paths):
                staged.replace(destination)
        return [str(path) for path in paths]

    @staticmethod
    def _export_bids(electrodes_path, coordsystem_path, electrodes, fiducials):
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
            "AnatomicalLandmarkCoordinates": {
                name: [round(value, 2) for value in position]
                for name, position in fiducials.items()
            },
            "DigitizationMethod": "InVesalius Navigator - EEG electrode digitization",
        }

        with electrodes_path.open("w", encoding="utf-8", newline="") as electrodes_file:
            writer = csv.writer(electrodes_file, delimiter="\t", lineterminator="\n")
            writer.writerow(("name", "x", "y", "z"))
            writer.writerows(
                (name, *(round(value, 2) for value in position)) for name, position in electrodes
            )

        with coordsystem_path.open("w", encoding="utf-8") as coordsystem_file:
            json.dump(coordsystem, coordsystem_file, indent=2)

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

    @staticmethod
    def _export_text(path, export_format, electrodes, fiducials):
        """Write HPTS/SFP rows or ASA ELC sections in Scanner RAS mm."""
        labels = {
            "HPTS": (("LPA", "cardinal 1"), ("NAS", "cardinal 2"), ("RPA", "cardinal 3")),
            "SFP": (("NAS", "FidNz"), ("LPA", "FidT9"), ("RPA", "FidT10")),
            "ELC": (("LPA", "LPA"), ("NAS", "Nz"), ("RPA", "RPA")),
        }[export_format]
        if export_format == "HPTS":
            electrodes = [(f"eeg {name}", position) for name, position in electrodes]
        else:
            reserved = [label for _name, label in labels]
            if export_format == "SFP":
                reserved.append("headshape")
            EEGMontage._validate_export_labels(electrodes, reserved=reserved, single_token=True)
        points = [
            (label, fiducials[name]) for name, label in labels if name in fiducials
        ] + electrodes
        if export_format == "ELC":
            lines = [
                "# ASA electrode file",
                "# Coordinate system: MRI Scanner RAS",
                "UnitPosition mm",
                f"NumberPositions= {len(points)}",
                "Positions",
            ]
            lines.extend(f"{x:.6f} {y:.6f} {z:.6f}" for _name, (x, y, z) in points)
            lines.extend(["Labels", *(name for name, _position in points)])
        else:
            lines = (
                ["# Digitized points exported by InVesalius 3", "# Coordinate system: Scanner RAS"]
                if export_format == "HPTS"
                else []
            )
            precision = 2 if export_format == "HPTS" else 6
            lines.extend(
                f"{name} {x:.{precision}f} {y:.{precision}f} {z:.{precision}f}"
                for name, (x, y, z) in points
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_fiff(path, tags):
        """Write the sequential FIFF subset used by digitization and transform files.

        Tags have big-endian int32 (kind, type, byte count, next) headers.
        Numeric IDs and layouts follow the FIFF dictionary, not a Python API:
        https://github.com/mne-tools/fiff-constants
        """
        seconds, microseconds = divmod(time_ns() // 1000, 1000000)
        file_id = pack(">i", 0x10004) + uuid4().bytes[:8] + pack(">ii", seconds, microseconds)
        headers = [
            (100, 31, file_id),  # FILE_ID / ID_STRUCT: FIFF 1.4, ID, timestamp
            (101, 3, pack(">i", -1)),  # DIR_POINTER: scan sequential tags
            (106, 3, pack(">i", -1)),  # FREE_LIST: none
        ]
        with path.open("wb") as stream:
            for kind, data_type, data in (*headers, *tags):
                stream.write(pack(">4i", kind, data_type, len(data), 0) + data)
                pad = (4 - len(data) % 4) % 4
                if pad:
                    stream.write(b"\x00" * pad)
            stream.write(pack(">4i", 108, 0, 0, -1))

    @staticmethod
    def _export_fif(path, trans_path, electrodes, metadata):
        """Write head-frame DigMontage points and a head->Scanner-RAS transform."""
        from invesalius.data.bases import ras_to_head_matrix

        fiducials = metadata["AnatomicalLandmarksScannerRAS_mm"]
        if not all(name in fiducials for name in ("NAS", "LPA", "RPA")):
            raise ValueError(
                "FIF export requires NAS, LPA and RPA. Use a Scanner RAS text export when a head frame is unavailable."
            )
        ras_to_head = ras_to_head_matrix(
            *(np.asarray(fiducials[name]) * 1e-3 for name in ("NAS", "LPA", "RPA"))
        )
        mm_to_head = ras_to_head @ np.diag([1e-3, 1e-3, 1e-3, 1.0])
        EEGMontage._validate_export_labels(electrodes)
        names = [name for name, _position in electrodes]
        if any("{COLON}" in name for name in names):
            raise ValueError(
                "FIF electrode labels cannot contain the reserved substring '{COLON}'."
            )
        # ISOTRAK block (107), with an explicit HEAD coordinate frame (4).
        tags = [(104, 3, pack(">i", 107)), (3506, 3, pack(">i", 4))]
        points = [
            (1, index, fiducials[name]) for index, name in ((1, "LPA"), (2, "NAS"), (3, "RPA"))
        ]
        points.extend((3, index, position) for index, (_name, position) in enumerate(electrodes, 1))
        for kind, identifier, position in points:
            head_position = mm_to_head @ [*position, 1.0]
            tags.append((213, 33, pack(">ii3f", kind, identifier, *head_position[:3])))
        # FIFF strings are Latin-1; modern readers restore escaped colons.
        name_list = ":".join(name.replace(":", "{COLON}") for name in names)
        try:
            encoded_names = name_list.encode("latin1")
        except UnicodeEncodeError as error:
            raise ValueError(
                "FIF requires Latin-1 electrode labels. Use a text export for these labels."
            ) from error
        tags.extend(
            [
                (3507, 10, encoded_names),
                (105, 3, pack(">i", 107)),
            ]
        )
        EEGMontage._write_fiff(path, tags)
        head_to_ras = np.linalg.inv(ras_to_head)
        # COORD_TRANS_STRUCT: from/to frames, forward R/t, inverse R/t (meters).
        transform = pack(">ii", 4, 2002)  # HEAD -> RAS, not FreeSurfer MRI (5)
        for matrix in (head_to_ras, ras_to_head):
            transform += (
                np.concatenate((matrix[:3, :3].ravel(), matrix[:3, 3])).astype(">f4").tobytes()
            )
        EEGMontage._write_fiff(trans_path, [(222, 35, transform)])
        metadata.update(
            {
                "DestinationCoordinateSystem": "MNE head",
                "DestinationCoordinateUnits": "m",
                "ExportedCoordinateSystem": "MNE head",
                "ExportedCoordinateUnits": "m",
                "MNEChannelNames": names,
                "MNEHeadConvention": "+X LPA->RPA; +Y toward NAS perpendicular to X; +Z superior. Origin: projection of NAS onto LPA-RPA.",
                "AdditionalTransformations": [
                    EEGMontage._transform_metadata(
                        "MRI Scanner RAS", "MNE head", mm_to_head, "mm", "m"
                    ),
                    EEGMontage._transform_metadata(
                        "MNE head", "MRI Scanner RAS", head_to_ras, "m", "m"
                    ),
                ],
                "MNETransformFile": {
                    "File": trans_path.name,
                    "From": "head",
                    "To": "ras",
                    "Units": "m",
                    "Description": "Head->Scanner RAS; compose with matching FreeSurfer geometry before surface-RAS source modeling.",
                },
            }
        )

    @staticmethod
    def _transform_metadata(source, destination, matrix, source_units="mm", destination_units="mm"):
        """Describe a directed positional affine; invalid or absent matrices stay null."""
        if matrix is not None:
            matrix = np.asarray(matrix, dtype=float)
            if (
                matrix.shape != (4, 4)
                or not np.isfinite(matrix).all()
                or not np.allclose(matrix[3], [0, 0, 0, 1])
                or np.linalg.matrix_rank(matrix[:3, :3]) != 3
            ):
                matrix = None
        return {
            "SourceCoordinateSystem": source,
            "DestinationCoordinateSystem": destination,
            "SourceCoordinateUnits": source_units,
            "DestinationCoordinateUnits": destination_units,
            "Matrix": matrix.tolist() if matrix is not None else None,
            "Direction": f"{source} -> {destination}",
        }

    @staticmethod
    def _registration_metadata(electrodes, fiducials):
        """Describe export transforms, explicitly marking unretained tracker provenance."""
        import invesalius
        from invesalius.data.slice_ import Slice
        from invesalius.project import Project

        image, project = Slice(), Project()
        # Recover the positional affine using exactly the existing conversion.
        # Slice.affine is inverse, spacing-scaled geometry, not a voxel affine.
        points = [
            EEGMontage._get_world_position(point)
            for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        ]
        matrix = np.eye(4)
        matrix[:3, 3] = points[0]
        matrix[:3, :3] = np.asarray(points[1:]).T - np.asarray(points[0])[:, None]
        image_to_ras = EEGMontage._transform_metadata("InVesalius image", "MRI Scanner RAS", matrix)
        if image_to_ras["Matrix"] is None:
            raise ValueError("The project does not have a valid MRI world coordinate system.")
        return {
            "Software": "InVesalius Navigator",
            "SoftwareVersion": str(invesalius.__version__),
            "MetadataVersion": 2,
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
                    "ElectrodeUUID": electrode.electrode_uuid,
                    "CaptureRegistration": None,
                }
                for electrode in electrodes
            ],
            "RegistrationAvailability": (
                "Capture-time tracker registration, ICP settings and raw tracker/reference samples "
                "are not retained. Exported positions are already registered image coordinates. "
                "Scalp projection is non-affine."
            ),
            "AnatomicalLandmarksScannerRAS_mm": fiducials,
            "AnatomicalLandmarkSource": "Current project image fiducials, unchanged",
            "ScannerRASToSurfaceRAS": EEGMontage._transform_metadata(
                "MRI Scanner RAS", "FreeSurfer surface RAS", None
            ),
            "SurfaceRASAvailability": "Matching FreeSurfer vox2ras/vox2ras_tkr geometry is not retained; Scanner RAS is not surface RAS.",
            "ExportedCoordinateSystem": "MRI Scanner RAS",
            "ExportedCoordinateUnits": "mm",
            "AdditionalTransformations": [],
        }

    @staticmethod
    def _get_world_position(position) -> list[float]:
        """Convert and validate a position with the shared MRI world-coordinate utility."""
        from invesalius.data import imagedata_utils

        position, _orientation = imagedata_utils.convert_invesalius_to_world(position, (0, 0, 0))
        if any(value is None or not isfinite(float(value)) for value in position):
            raise ValueError("The project does not have a valid MRI world coordinate system.")
        return [float(value) for value in position]

    @staticmethod
    def _get_world_electrodes(electrodes) -> list[tuple[str, tuple[float, float, float]]]:
        return [
            (electrode.label, tuple(EEGMontage._get_world_position(electrode.position)))
            for electrode in sorted(electrodes, key=lambda electrode: electrode.label)
        ]

    @staticmethod
    def _get_world_fiducials() -> dict[str, list[float]]:
        from invesalius.project import Project

        fiducials = {}
        fiducial_names = ((2, "NAS"), (0, "LPA"), (1, "RPA"))
        for index, name in fiducial_names:
            position = Project().image_fiducials[index]
            if any(not isfinite(float(value)) for value in position):
                continue
            try:
                fiducials[name] = EEGMontage._get_world_position(position)
            except ValueError:
                continue
        return fiducials


@dataclass
class STC:
    axis: TimeAxis
    vertices: np.ndarray
    values: np.ndarray

    def read_frame(self, frame_index):
        return self.values[self.axis.check_index(frame_index)]


def read_stc(filename):
    """Validate the header and map values read-only, loading one frame at a time.

    The big-endian layout is tmin/dt (float32 milliseconds), vertex count
    (uint32), vertex IDs (uint32), frame count (uint32), then float32 values
    in frame-major order. Reference: mne-python/mne/source_estimate.py::_read_stc.
    """
    with Path(filename).open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        if size < 16:
            raise ValueError("Truncated STC header.")
        t0, dt, n_vertices = unpack(">ffI", stream.read(12))
        offset = 16 + 4 * n_vertices
        if offset > size:
            raise ValueError("Truncated STC vertex list.")
        vertices = np.fromfile(stream, dtype=">u4", count=n_vertices)
        n_frames = unpack(">I", stream.read(4))[0]
        axis = TimeAxis(t0 / 1000, dt / 1000, n_frames)
        if size != offset + 4 * n_vertices * n_frames:
            raise ValueError("STC file size does not match its vertex and frame counts.")
        if len(np.unique(vertices)) != n_vertices:
            raise ValueError("STC vertex IDs must be unique.")
        vertices.flags.writeable = False
        values = (
            np.memmap(stream, dtype=">f4", mode="r", offset=offset, shape=(n_frames, n_vertices))
            if n_vertices
            else np.empty((n_frames, 0), dtype=">f4")
        )
        values.flags.writeable = False
    return STC(axis, vertices, values)


def read_stc_pair(filename):
    """Load the matching lh/rh files and require a common time axis."""
    filename = Path(filename)
    if not filename.name.endswith(("-lh.stc", "-rh.stc")):
        raise ValueError("Select a cortical STC file ending in '-lh.stc' or '-rh.stc'.")
    stem = filename.name[:-7]
    pair = tuple(read_stc(filename.with_name(f"{stem}-{side}.stc")) for side in ("lh", "rh"))
    left, right = pair
    if left.axis != right.axis:
        raise ValueError("The STC hemispheres have different time axes.")
    if not len(left.vertices) + len(right.vertices):
        raise ValueError("The STC pair does not contain any sources.")
    return pair


def discover_subject_files(subject_dir):
    """Find cortical surfaces and curvature in a FreeSurfer/FastSurfer subject directory."""
    subject_dir = Path(subject_dir).expanduser().resolve()
    surface_dir = subject_dir / "surf"
    if not subject_dir.is_dir() or not surface_dir.is_dir():
        raise ValueError(
            "Select a FreeSurfer/FastSurfer subject folder containing a 'surf' directory."
        )
    files = {}
    for kind in ("pial", "white", "inflated", "curv"):
        files[kind] = {}
        for side in ("lh", "rh"):
            path = surface_dir / f"{side}.{kind}"
            if path.is_file():
                files[kind][side] = path
    return files


@dataclass
class CorticalSourceSeries:
    hemispheres: tuple[STC, STC]
    points: np.ndarray
    triangles: np.ndarray
    vertex_sources: np.ndarray
    scalar_range: tuple[float, float]
    name: str
    unit: str
    global_rms: np.ndarray
    hemisphere_sizes: tuple[int, int]
    surface_to_project_ras: np.ndarray
    subject_files: dict[str, dict[str, Path]] = field(default_factory=dict)

    @property
    def axis(self):
        return self.hemispheres[0].axis

    def read_frame(self, frame_index):
        """Return the sampled sources, in lh then rh order, without spatial resampling."""
        return np.concatenate([stc.read_frame(frame_index) for stc in self.hemispheres])

    def read_source(self, source_index):
        """Read a source's original time course, using read_frame's lh-then-rh source order."""
        source_index = operator.index(source_index)
        for stc in self.hemispheres:
            if 0 <= source_index < len(stc.vertices):
                return stc.values[:, source_index]
            source_index -= len(stc.vertices)
        raise IndexError("Source index is outside the source series.")

    @property
    def representations(self):
        return ("pial",) + tuple(
            name
            for name in ("white", "inflated")
            if all(side in self.subject_files.get(name, {}) for side in ("lh", "rh"))
        )

    def read_surface_points(self, representation):
        """Read display coordinates while keeping pial's vertex IDs and topology."""
        if representation == "pial":
            return self.points
        if representation not in self.representations:
            raise ValueError("The cortical representation requires files for both hemispheres.")
        points = []
        offset = 0
        for side, count in zip(("lh", "rh"), self.hemisphere_sizes):
            vertices, faces = nib.freesurfer.read_geometry(self.subject_files[representation][side])
            reference = (
                self.triangles[
                    (self.triangles[:, 0] >= offset) & (self.triangles[:, 0] < offset + count)
                ]
                - offset
            )
            if (
                vertices.shape != (count, 3)
                or not np.isfinite(vertices).all()
                or not np.array_equal(faces, reference)
            ):
                raise ValueError(
                    f"The {side} {representation} surface is incompatible with the pial mesh."
                )
            points.append(vertices)
            offset += count
        if representation == "inflated":
            # Inflated hemispheres can overlap in surface RAS; separate them only for display.
            left, right = points
            gap = 0.05 * max(np.ptp(left[:, 0]), np.ptp(right[:, 0]))
            shift = max(0.0, left[:, 0].max() - right[:, 0].min() + gap) / 2
            left[:, 0] -= shift
            right[:, 0] += shift
        registered = nib.affines.apply_affine(self.surface_to_project_ras, np.concatenate(points))
        if not np.isfinite(registered).all():
            raise ValueError("The cortical representation has invalid project coordinates.")
        return registered


def _affine(matrix):
    matrix = np.asarray(matrix, dtype=float)
    if (
        matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix[3], [0, 0, 0, 1])
        or np.linalg.matrix_rank(matrix[:3, :3]) != 3
    ):
        raise ValueError("Registration must be a finite, invertible 4x4 positional affine.")
    return matrix


class MissingSurfaceGeometryError(ValueError):
    """A reference MRI is needed because the surface has no usable volume metadata."""


def _surface_to_scanner_ras(metadata):
    required = ("volume", "voxelsize", "xras", "yras", "zras", "cras")
    valid = str(metadata.get("valid", "")).split()
    if not valid or valid[0] != "1" or any(key not in metadata for key in required):
        raise MissingSurfaceGeometryError(
            "The cortical surface has no valid volume metadata. Select its matching FreeSurfer MRI."
        )
    volume = np.asarray(metadata["volume"], dtype=float)
    spacing = np.asarray(metadata["voxelsize"], dtype=float)
    directions = np.asarray([metadata[key] for key in ("xras", "yras", "zras")], dtype=float)
    center = np.asarray(metadata["cras"], dtype=float)
    if (
        volume.shape != (3,)
        or spacing.shape != (3,)
        or directions.shape != (3, 3)
        or center.shape != (3,)
        or not all(np.isfinite(value).all() for value in (volume, spacing, directions, center))
        or np.any(volume <= 0)
        or np.any(volume > np.iinfo(np.int32).max)
        or np.any(volume != np.floor(volume))
        or np.any(spacing <= 0)
        or not np.allclose(directions @ directions.T, np.eye(3), atol=1e-4)
    ):
        raise ValueError("Invalid reference-volume geometry in the cortical surface metadata.")
    header = nib.freesurfer.mghformat.MGHHeader()
    header.set_data_shape(tuple(int(size) for size in volume))
    header.set_zooms(tuple(float(size) for size in spacing))
    header["Mdc"] = directions
    header["Pxyz_c"] = center
    return _affine(_affine(header.get_affine()) @ np.linalg.inv(_affine(header.get_vox2ras_tkr())))


def _vertex_sources(points, triangles, source_vertices):
    """Assign the nearest sampled source along mesh edges, never across a sulcus."""
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    lengths = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    graph = csr_matrix(
        (np.tile(lengths, 2), (edges.T.ravel(), edges[:, ::-1].T.ravel())),
        shape=(len(points), len(points)),
    )
    _, _, nearest = dijkstra(
        graph, indices=source_vertices, min_only=True, return_predecessors=True
    )
    rows = np.full(len(points), -1, dtype=np.int64)
    rows[source_vertices] = np.arange(len(source_vertices))
    mapped = nearest >= 0
    result = np.full(len(points), -1, dtype=np.int64)
    result[mapped] = rows[nearest[mapped]]
    return result


def _source_statistics(hemispheres):
    minimum, maximum = float("inf"), float("-inf")
    rms = np.zeros(hemispheres[0].axis.n_frames, dtype=np.float64)
    for stc in hemispheres:
        if not len(stc.vertices):
            continue
        frames_per_chunk = max(1, 1_000_000 // len(stc.vertices))
        for start in range(0, stc.axis.n_frames, frames_per_chunk):
            chunk = stc.values[start : start + frames_per_chunk]
            if not np.isfinite(chunk).all():
                raise ValueError("STC source values must be finite.")
            minimum = min(minimum, float(chunk.min()))
            maximum = max(maximum, float(chunk.max()))
            # Square in float64 to preserve tiny amplitudes and avoid float32 overflow.
            rms[start : start + len(chunk)] += np.square(chunk, dtype=np.float64).sum(axis=1)
    rms /= sum(len(stc.vertices) for stc in hemispheres)
    np.sqrt(rms, out=rms)
    rms.flags.writeable = False
    return (minimum, maximum), rms


def read_source_config(filename):
    """Read a source reconstruction configuration from JSON."""
    filename = Path(filename)
    with filename.open(encoding="utf-8") as stream:
        config = json.load(stream)
    return read_source_reconstruction(config, filename.parent)


def read_source_reconstruction(config, base_dir="."):
    """Validate the complete import before any project or viewer state is changed.

    Surface volume metadata supplies the geometry unless a matching FreeSurfer
    MGH/MGZ reference is provided. scanner_ras_to_project_ras registers its coordinates
    to those of the project's anatomical image; all spatial units are mm.
    """
    base_dir = Path(base_dir)
    if not isinstance(config, dict):
        raise ValueError("Source configuration must be a dictionary.")
    anatomy_keys = ("subject_dir",) if "subject_dir" in config else ("lh_surface", "rh_surface")
    required = ("stc", "unit", "scanner_ras_to_project_ras", *anatomy_keys)
    if any(key not in config for key in required):
        raise ValueError(f"Source configuration requires: {', '.join(required)}.")
    for key in ("stc", "unit", *anatomy_keys):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"Source configuration '{key}' must be a nonempty string.")
    subject_files = {}
    if "subject_dir" in config:
        subject_files = discover_subject_files(base_dir / config["subject_dir"])
        surface_paths = subject_files["pial"]
        missing = [f"surf/{side}.pial" for side in ("lh", "rh") if side not in surface_paths]
        if missing:
            raise ValueError(
                f"Subject folder is missing required cortical surfaces: {', '.join(missing)}."
            )
    else:
        surface_paths = {side: base_dir / config[f"{side}_surface"] for side in ("lh", "rh")}
    name = config.get("name", Path(config["stc"]).name[:-7])
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Source name must be a nonempty string.")
    registration = _affine(config["scanner_ras_to_project_ras"])
    hemispheres = read_stc_pair(base_dir / config["stc"])
    surface_to_scanner = None
    if "mri" in config:
        if not isinstance(config["mri"], str) or not config["mri"].strip():
            raise ValueError("Source configuration 'mri' must be a nonempty string.")
        mri = read_image(base_dir / config["mri"])
        if not isinstance(mri, nib.freesurfer.mghformat.MGHImage):
            raise ValueError("Source MRI reference must be a FreeSurfer MGH or MGZ image.")
        surface_to_scanner = _affine(
            _affine(mri.affine) @ np.linalg.inv(_affine(mri.header.get_vox2ras_tkr()))
        )
    points, triangles, source_vertices = [], [], []
    offset = 0
    for side, stc in zip(("lh", "rh"), hemispheres):
        surface_path = surface_paths[side]
        if "mri" in config:
            vertices, faces = nib.freesurfer.read_geometry(surface_path)
        else:
            vertices, faces, metadata = nib.freesurfer.read_geometry(
                surface_path, read_metadata=True
            )
        if (
            vertices.ndim != 2
            or vertices.shape[1] != 3
            or not len(vertices)
            or not np.isfinite(vertices).all()
            or faces.ndim != 2
            or faces.shape[1] != 3
            or not len(faces)
            or faces.min() < 0
            or faces.max() >= len(vertices)
        ):
            raise ValueError(f"Invalid {side} cortical surface geometry.")
        if len(stc.vertices) and stc.vertices.max() >= len(vertices):
            raise ValueError(f"STC vertex IDs exceed the {side} surface vertex count.")
        if "mri" not in config:
            geometry = _surface_to_scanner_ras(metadata)
            if surface_to_scanner is not None and not np.allclose(
                geometry, surface_to_scanner, rtol=1e-5, atol=1e-4
            ):
                raise ValueError(
                    "The cortical hemispheres have different reference-volume geometry."
                )
            surface_to_scanner = geometry
        points.append(vertices)
        triangles.append(faces.astype(np.int64) + offset)
        source_vertices.append(stc.vertices.astype(np.int64) + offset)
        offset += len(vertices)
    hemisphere_sizes = tuple(len(vertices) for vertices in points)
    points = np.concatenate(points)
    triangles = np.concatenate(triangles)
    source_vertices = np.concatenate(source_vertices)
    surface_to_project = _affine(registration @ surface_to_scanner)
    scalar_range, global_rms = _source_statistics(hemispheres)
    vertex_sources = _vertex_sources(points, triangles, source_vertices)
    registered_points = nib.affines.apply_affine(surface_to_project, points)
    if not np.isfinite(registered_points).all():
        raise ValueError("Registered source geometry must be finite.")
    return CorticalSourceSeries(
        hemispheres,
        registered_points,
        triangles,
        vertex_sources,
        scalar_range,
        name,
        config["unit"],
        global_rms,
        hemisphere_sizes=hemisphere_sizes,
        surface_to_project_ras=surface_to_project,
        subject_files=subject_files,
    )
