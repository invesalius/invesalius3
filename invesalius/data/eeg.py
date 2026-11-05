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
from math import floor, isfinite, log10
from pathlib import Path
from struct import pack, unpack
from tempfile import TemporaryDirectory
from time import time_ns
from uuid import uuid4

import h5py
import nibabel as nib
import numpy as np
from scipy.io import loadmat
from scipy.sparse import csc_matrix, csr_matrix, issparse
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from invesalius.data.time_series import TimeAxis
from invesalius.i18n import tr as _
from invesalius.reader.others_reader import read_image

# Electrodes and montage exports


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


# Source data models and import requirements


@dataclass
class SourceData:
    axis: TimeAxis
    vertices: np.ndarray
    values: "np.ndarray | _H5SourceValues"
    unit: str = "a.u."
    measure: str = "amplitude"
    method: str = ""

    def __post_init__(self):
        self.vertices = np.asarray(self.vertices)
        if (
            self.vertices.ndim != 1
            or self.vertices.dtype.kind not in "iu"
            or np.any(self.vertices < 0)
            or len(np.unique(self.vertices)) != len(self.vertices)
            or self.values.shape != (self.axis.n_frames, len(self.vertices))
            or self.values.dtype.kind not in "iuf"
        ):
            raise ValueError(
                "Source values must be real samples with unique nonnegative vertex IDs."
            )
        self.vertices.flags.writeable = False
        if isinstance(self.values, np.ndarray):
            self.values.flags.writeable = False

    def read_frame(self, frame_index):
        return self.values[self.axis.check_index(frame_index)]


@dataclass
class CorticalSourceSeries:
    sources: tuple[SourceData, ...]
    points: np.ndarray
    triangles: np.ndarray
    vertex_sources: np.ndarray
    scalar_range: tuple[float, float]
    name: str
    unit: str
    global_rms: np.ndarray
    hemisphere_sizes: tuple[int, ...]
    surface_to_project_ras: np.ndarray
    subject_files: dict[str, dict[str, Path]] = field(default_factory=dict)
    measure: str = "amplitude"
    method: str = ""
    source_unit: str = ""
    display_unit: str = ""
    automatic_scale: bool = True
    vertex_hemispheres: np.ndarray | None = None
    brainstorm_surface: Path | None = None
    brainstorm_sphere: np.ndarray | None = None

    @property
    def unit_choices(self):
        moments = ("A.m", "nA.m", "pA.m")
        physical = tuple(f"({unit})^2" for unit in moments) if self.measure == "power" else moments
        return tuple(
            dict.fromkeys(("a.u.", "1", *physical, self.unit, self.source_unit or self.unit))
        )

    @property
    def display_units(self):
        physical = self.unit_choices[2:5]
        unit = self.source_unit or self.unit
        return physical if unit in physical else (unit,)

    @property
    def display_scale(self):
        """Return a presentation factor and exponent fixed over the entire recording."""
        units = self.display_units
        unit = self.source_unit or self.unit
        target = self.display_unit or unit
        conversion = 1.0
        if target != unit:
            if target not in units:
                raise ValueError("Source and display units must describe the same quantity.")
            power = 2 if self.measure == "power" else 1
            prefixes = (0, -9, -12)
            conversion = 10.0 ** (
                power * (prefixes[units.index(unit)] - prefixes[units.index(target)])
            )
        peak = max(abs(value) for value in self.scalar_range) * conversion
        if not isfinite(peak):
            raise ValueError("The selected unit exceeds the supported numeric range.")
        exponent = 3 * floor(log10(peak) / 3) if self.automatic_scale and peak > 0 else 0
        exponent = max(-300, min(300, exponent))
        factor = conversion / 10.0**exponent
        if not isfinite(factor) or factor <= 0:
            raise ValueError("The selected display scale exceeds the supported numeric range.")
        return factor, exponent

    @property
    def display_title(self):
        exponent = self.display_scale[1]
        quantity = _("Power") if self.measure == "power" else _("Amplitude")
        title = f"{quantity} ({self.display_unit or self.source_unit or self.unit})"
        superscript = str(exponent).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
        return title + (f" 10{superscript}" if exponent else "")

    @property
    def axis(self):
        return self.sources[0].axis

    @property
    def has_hemispheres(self):
        return self.vertex_hemispheres is not None or len(self.hemisphere_sizes) == 2

    def read_frame(self, frame_index):
        """Return source samples in their imported order, without spatial resampling."""
        return np.concatenate([source.read_frame(frame_index) for source in self.sources])

    def read_source(self, source_index):
        """Read a source's time course using the same source order as read_frame."""
        source_index = operator.index(source_index)
        for source in self.sources:
            if 0 <= source_index < len(source.vertices):
                return source.values[:, source_index]
            source_index -= len(source.vertices)
        raise IndexError("Source index is outside the source series.")

    def source_label(self, source_index):
        for index, source in enumerate(self.sources):
            if 0 <= source_index < len(source.vertices):
                vertex = int(source.vertices[source_index])
                if self.vertex_hemispheres is not None:
                    return f"{('LH', 'RH')[self.vertex_hemispheres[vertex]]} {vertex + 1}"
                prefix = ("LH", "RH")[index] if self.has_hemispheres else "Source"
                return f"{prefix} {vertex if self.has_hemispheres else vertex + 1}"
            source_index -= len(source.vertices)
        raise IndexError("Source index is outside the source series.")

    @property
    def representations(self):
        if self.brainstorm_surface is not None:
            if self.brainstorm_sphere is None:
                return (self.base_representation,)
            return (self.base_representation,) + tuple(
                name
                for name in ("pial", "white", "mid", "inflated")
                if name != self.base_representation and self.subject_files.get(name)
            )
        return (self.base_representation,) + tuple(
            name
            for name in ("white", "inflated")
            if all(side in self.subject_files.get(name, {}) for side in ("lh", "rh"))
        )

    @property
    def base_representation(self):
        if self.brainstorm_surface is not None:
            for name in ("pial", "white", "mid", "inflated"):
                if self.brainstorm_surface.stem.startswith(f"tess_cortex_{name}_"):
                    return name
            return "surface"
        return "pial" if len(self.hemisphere_sizes) == 2 else "surface"

    def read_surface(self, representation):
        """Return display geometry, source mapping and hemisphere IDs."""
        hemispheres = self.vertex_hemispheres
        if hemispheres is None and len(self.hemisphere_sizes) == 2:
            hemispheres = np.repeat(np.array([0, 1], dtype=np.int8), self.hemisphere_sizes)
        if representation == self.base_representation:
            return self.points, self.triangles, self.vertex_sources, hemispheres
        if representation not in self.representations:
            raise ValueError("The cortical representation has no compatible anatomy metadata.")
        if self.brainstorm_surface is not None:
            return _read_brainstorm_display_surface(self, representation)
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
        return registered, self.triangles, self.vertex_sources, hemispheres


class SourceImportRequired(ValueError):
    """Request a missing companion file or an explicit choice without depending on wx."""

    def __init__(self, key, message, choices=()):
        super().__init__(message)
        self.key = key
        self.choices = tuple(choices)


class MissingSurfaceGeometryError(ValueError):
    """A reference MRI is needed because the surface has no usable volume metadata."""


# Source import pipeline


def read_source_config(filename):
    """Read a source reconstruction configuration from JSON."""
    filename = Path(filename)
    with filename.open(encoding="utf-8") as stream:
        config = json.load(stream)
    return read_source_reconstruction(config, filename.parent)


def read_source_reconstruction(config, base_dir="."):
    """Validate the signal, mesh and alignment before changing the project."""
    base_dir = Path(base_dir)
    if not isinstance(config, dict):
        raise ValueError("Source configuration must be a dictionary.")
    signal_key = "signal" if "signal" in config else "stc"
    required = (signal_key, "scanner_ras_to_project_ras")
    if any(key not in config for key in required):
        raise ValueError(f"Source configuration requires: {', '.join(required)}.")
    for key in (signal_key, "unit", "subject_dir"):
        if key in config and (not isinstance(config[key], str) or not config[key].strip()):
            raise ValueError(f"Source configuration '{key}' must be a nonempty string.")
    if "subject_dir" in config:
        config = dict(config)
        config["subject_dir"] = str((base_dir / Path(config["subject_dir"]).expanduser()).resolve())
    filename = base_dir / config[signal_key]
    sources, mesh = read_source_data(filename, config)
    unit = _signal_unit(config.get("unit", sources[0].unit))
    method = sources[0].method
    if unit.lower() in ("dspm", "sloreta", "eloreta"):
        method = unit
        unit = "1" if unit.lower() == "dspm" else "a.u."
    name = config.get("name", filename.stem.removesuffix("-lh").removesuffix("-rh"))
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Source name must be a nonempty string.")
    registration = _affine(config["scanner_ras_to_project_ras"])
    mesh_metadata = {}
    if mesh is None:
        points, triangles, source_vertices, hemisphere_sizes, subject_files, surface_to_scanner = (
            _read_freesurfer_source_mesh(config, base_dir, sources)
        )
    else:
        points, triangles, surface_to_scanner = mesh[:3]
        mesh_metadata = mesh[3] if len(mesh) == 4 else {}
        source_vertices = np.concatenate([source.vertices for source in sources])
        hemisphere_sizes, subject_files = (), mesh_metadata.get("subject_files", {})
    surface_to_project = _affine(registration @ surface_to_scanner)
    scalar_range, global_rms = _source_statistics(sources)
    vertex_sources = _vertex_sources(points, triangles, source_vertices)
    registered_points = nib.affines.apply_affine(surface_to_project, points)
    if not np.isfinite(registered_points).all():
        raise ValueError("Registered source geometry must be finite.")
    return CorticalSourceSeries(
        sources,
        registered_points,
        triangles,
        vertex_sources,
        scalar_range,
        name,
        unit,
        global_rms,
        hemisphere_sizes=hemisphere_sizes,
        surface_to_project_ras=surface_to_project,
        subject_files=subject_files,
        measure=sources[0].measure,
        method=method,
        source_unit=unit,
        display_unit=unit,
        vertex_hemispheres=mesh_metadata.get("vertex_hemispheres"),
        brainstorm_surface=mesh_metadata.get("brainstorm_surface"),
        brainstorm_sphere=mesh_metadata.get("brainstorm_sphere"),
    )


def read_source_data(filename, config):
    """Detect cortical source formats by their container and documented field signatures."""
    filename = Path(filename).expanduser().resolve()
    if filename.suffix.lower() == ".stc":
        return read_stc_pair(filename), None
    if h5py.is_hdf5(filename):
        with h5py.File(filename, "r") as stream:
            if "mnepython" in stream:
                return _read_mne_h5(filename, config), None
    elif filename.suffix.lower() != ".mat":
        raise ValueError("Select an STC, MNE H5, or Brainstorm/FieldTrip MAT source file.")
    candidates = _mat_source_candidates(_read_mat_file(filename))
    if not candidates:
        raise ValueError("No Brainstorm or FieldTrip source reconstruction was found in this file.")
    selected = _source_choice(
        config,
        "source_variable",
        "Select the source reconstruction stored in this MAT file.",
        tuple(candidates),
    )
    data = candidates[selected]
    if "ImageGridAmp" in data or "ImagingKernel" in data:
        return _read_brainstorm_source(filename, data, config)
    return _read_fieldtrip_source(filename, data, config)


# Shared source import helpers


def _signal_unit(value):
    if not isinstance(value, str) or not value.strip():
        return "a.u."
    value = value.strip()
    compact = value.replace(" ", "").replace("*", ".").replace("·", ".").replace("²", "^2")
    for unit in ("A.m", "nA.m", "pA.m"):
        if compact in (unit, unit.replace(".", "")):
            return unit
        if compact in (
            f"({unit})^2",
            f"({unit.replace('.', '')})^2",
            f"{unit.replace('.', '')}^2",
            unit.replace(".", "^2.") + "^2",
            unit.replace(".", "^2") + "^2",
        ):
            return f"({unit})^2"
    return value


def _source_choice(config, key, message, choices):
    if not choices:
        raise ValueError(f"No supported source data is available for {key}.")
    selected = config.get(key)
    if selected is None and len(choices) == 1:
        return choices[0]
    if selected is None:
        raise SourceImportRequired(key, message, choices)
    if selected not in choices:
        raise ValueError(f"Invalid source import selection for {key}.")
    return selected


def _source_axis(times):
    times = np.asarray(times)
    if times.dtype.kind not in "iuf" or times.ndim > 2:
        raise ValueError("Source times must be a real vector in seconds.")
    if times.ndim == 2 and min(times.shape) != 1:
        raise ValueError("Source times must be a vector in seconds.")
    times = times.ravel().astype(float)
    if not len(times) or not np.isfinite(times).all():
        raise ValueError("Source times must be nonempty and finite.")
    dt = float(times[1] - times[0]) if len(times) > 1 else 1.0
    axis = TimeAxis(float(times[0]), dt, len(times))
    if not np.allclose(times, axis.t0 + np.arange(len(times)) * dt, rtol=1e-6, atol=1e-9):
        raise ValueError("Source playback requires uniformly sampled, increasing times.")
    return axis


def _has_source_values(value):
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return bool(np.prod(value.shape)) if issparse(value) else bool(np.size(value))


def _source_component(config):
    return _source_choice(
        config,
        "source_component",
        "Vector source data: select a component or the vector magnitude for visualization.",
        ("Component 1", "Component 2", "Component 3", "Magnitude"),
    )


def _source_companion(filename, config, key, message, reference=""):
    if config.get(key):
        path = Path(config[key])
        return path if path.is_absolute() else filename.parent / path
    if isinstance(reference, str) and reference:
        relative = Path(reference.replace("\\", "/"))
        candidates = [filename.parent / relative, filename.parent / relative.name]
        for parent in list(filename.parents)[:4]:
            candidates.extend(
                (parent / relative, parent / "anat" / relative, parent / "data" / relative)
            )
        for path in candidates:
            if path.is_file():
                return path
    raise SourceImportRequired(key, message)


def _scalar_source_values(data, count, axis, config, components=1):
    data = data.toarray() if issparse(data) else np.asarray(data)
    if data.dtype.kind not in "iuf" or components not in (1, 3):
        raise ValueError("Only real scalar or three-component source time courses are supported.")
    if data.shape != (count * components, axis.n_frames):
        if data.ndim > 1 or data.size != count * components * axis.n_frames:
            raise ValueError("Source values do not match their positions and time samples.")
        data = data.reshape(count * components, axis.n_frames)
    if components == 3:
        component = _source_component(config)
        data = data.reshape(count, 3, axis.n_frames)
        data = (
            np.linalg.norm(data, axis=1)
            if component == "Magnitude"
            else data[:, ("Component 1", "Component 2", "Component 3").index(component), :]
        )
    return data.T


def _source_statistics(hemispheres):
    if not sum(len(source.vertices) for source in hemispheres):
        raise ValueError("The source reconstruction does not contain any sources.")
    minimum, maximum = float("inf"), float("-inf")
    rms = np.zeros(hemispheres[0].axis.n_frames, dtype=np.float64)
    for stc in hemispheres:
        if not len(stc.vertices):
            continue
        frames_per_chunk = max(1, 1_000_000 // len(stc.vertices))
        for start in range(0, stc.axis.n_frames, frames_per_chunk):
            chunk = stc.values[start : start + frames_per_chunk]
            if not np.isfinite(chunk).all():
                raise ValueError("Source values must be finite.")
            minimum = min(minimum, float(chunk.min()))
            maximum = max(maximum, float(chunk.max()))
            # Square in float64 to preserve tiny amplitudes and avoid float32 overflow.
            rms[start : start + len(chunk)] += np.square(chunk, dtype=np.float64).sum(axis=1)
    rms /= sum(len(stc.vertices) for stc in hemispheres)
    np.sqrt(rms, out=rms)
    rms.flags.writeable = False
    return (minimum, maximum), rms


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


def _validate_source_mesh(points, triangles):
    points, triangles = np.asarray(points), np.asarray(triangles)
    if triangles.ndim == 1 and triangles.size == 3:
        triangles = triangles.reshape(1, 3)
    if (
        points.dtype.kind not in "iuf"
        or points.ndim != 2
        or points.shape[1] != 3
        or not len(points)
        or not np.isfinite(points).all()
        or triangles.dtype.kind not in "iuf"
        or triangles.ndim != 2
        or triangles.shape[1] != 3
        or not len(triangles)
        or not np.isfinite(triangles).all()
        or np.any(triangles != np.floor(triangles))
        or triangles.min() < 0
        or triangles.max() >= len(points)
    ):
        raise ValueError("Source geometry requires finite vertices and valid triangular faces.")
    return points.astype(float), triangles.astype(np.int64)


def _vertex_sources(points, triangles, source_vertices):
    """Assign the nearest sampled source along mesh edges, never across a sulcus."""
    if len(source_vertices) == len(points):
        result = np.empty(len(points), dtype=np.int64)
        result[source_vertices] = np.arange(len(source_vertices))
        return result
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


# Source anatomy


def discover_subject_files(subject_dir):
    """Find source anatomy in a FreeSurfer/FastSurfer or Brainstorm subject directory."""
    subject_dir = Path(subject_dir).expanduser().resolve()
    surface_dir = subject_dir / "surf"
    if not surface_dir.is_dir():
        catalog = subject_dir / "brainstormsubject.mat"
        if catalog.is_file():
            data = _read_mat_file(catalog, ("Cortex", "Anatomy"))
            anatomy = {
                key: _brainstorm_subject_path(subject_dir, data.get(field))
                for key, field in (("surface_file", "Cortex"), ("brainstorm_mri", "Anatomy"))
            }
            files = _brainstorm_surface_files(subject_dir)
            files.update(brainstorm=anatomy, cortex={"default": anatomy["surface_file"]})
            return files
        raise ValueError(
            "Select a subject folder containing FreeSurfer/FastSurfer 'surf' or Brainstorm 'brainstormsubject.mat'."
        )
    files = {}
    for kind in ("pial", "white", "inflated", "curv"):
        files[kind] = {}
        for side in ("lh", "rh"):
            path = surface_dir / f"{side}.{kind}"
            if path.is_file():
                files[kind][side] = path
    return files


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


def _read_freesurfer_source_mesh(config, base_dir, sources):
    anatomy_keys = ("subject_dir",) if "subject_dir" in config else ("lh_surface", "rh_surface")
    for key in anatomy_keys:
        if key not in config:
            raise SourceImportRequired(key, f"Select the cortical surface for {key}.")
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"Source configuration '{key}' must be a nonempty path.")
    subject_files = {}
    if "subject_dir" in config:
        subject_files = discover_subject_files(base_dir / config["subject_dir"])
        if "brainstorm" in subject_files:
            raise ValueError(
                "STC/MNE H5 require their original FreeSurfer surfaces; Brainstorm cortical vertex IDs are not interchangeable."
            )
        surface_paths = subject_files["pial"]
        missing = [f"surf/{side}.pial" for side in ("lh", "rh") if side not in surface_paths]
        if missing:
            raise ValueError(
                f"Subject folder is missing required cortical surfaces: {', '.join(missing)}."
            )
    else:
        surface_paths = {side: base_dir / config[f"{side}_surface"] for side in ("lh", "rh")}
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
    for side, stc in zip(("lh", "rh"), sources):
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
            raise ValueError(f"Source vertex IDs exceed the {side} surface vertex count.")
        if "mri" not in config:
            geometry = _surface_to_scanner_ras(metadata)
            if surface_to_scanner is not None and not np.allclose(
                geometry, surface_to_scanner, rtol=1e-5, atol=1e-4
            ):
                raise ValueError("The cortical sources have different reference-volume geometry.")
            surface_to_scanner = geometry
        points.append(vertices)
        triangles.append(faces.astype(np.int64) + offset)
        source_vertices.append(stc.vertices.astype(np.int64) + offset)
        offset += len(vertices)
    hemisphere_sizes = tuple(len(vertices) for vertices in points)
    points = np.concatenate(points)
    triangles = np.concatenate(triangles)
    source_vertices = np.concatenate(source_vertices)
    return points, triangles, source_vertices, hemisphere_sizes, subject_files, surface_to_scanner


# STC and MNE H5 readers


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
    return SourceData(axis, vertices, values)


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


class _H5SourceValues:
    """Read only the requested time samples from an MNE HDF5 dataset."""

    def __init__(self, filename, dataset, start, stop, component):
        self.filename = filename
        self.dataset = dataset.name
        self.start = start
        self.shape = (dataset.shape[-1], stop - start)
        self.dtype = dataset.dtype
        self.component = component

    def __getitem__(self, key):
        frames, source = key if isinstance(key, tuple) else (key, slice(None))
        rows = slice(self.start, self.start + self.shape[1])
        if not isinstance(source, slice):
            rows = self.start + operator.index(source)
        with h5py.File(self.filename, "r") as stream:
            dataset = stream[self.dataset]
            if self.component is None:
                values = dataset[rows, frames]
            elif self.component == "Magnitude":
                values = np.linalg.norm(
                    dataset[rows, :, frames], axis=1 if isinstance(rows, slice) else 0
                )
            else:
                values = dataset[
                    rows,
                    ("Component 1", "Component 2", "Component 3").index(self.component),
                    frames,
                ]
        return np.asarray(values).T


def _read_mne_h5(filename, config):
    with h5py.File(filename, "r") as stream:
        root = stream["mnepython"]
        if "key_src_type" in root:
            kind = root["key_src_type"][()]
            if not isinstance(kind, str):
                kind = (
                    kind.decode()
                    if isinstance(kind, bytes)
                    else np.asarray(kind).tobytes().decode()
                )
            if kind != "surface":
                raise ValueError("MNE volume and mixed source spaces require a volume renderer.")
        vertices = root.get("key_vertices")
        if not isinstance(vertices, h5py.Group) or set(vertices.keys()) != {"idx_0", "idx_1"}:
            raise ValueError("MNE cortical H5 data must identify both hemispheres.")
        vertices = [vertices[f"idx_{index}"][()] for index in range(2)]
        data = root["key_data"]
        count = sum(len(value) for value in vertices)
        if data.ndim not in (2, 3) or data.shape[0] != count or not count:
            raise ValueError("MNE source data dimensions do not match the cortical vertices.")
        component = None
        if data.ndim == 3:
            if data.shape[1] != 3:
                raise ValueError("MNE vector source data must have three components.")
            component = _source_component(config)
        t0 = float(root["key_tmin"][()].item())
        dt = float(root["key_tstep"][()].item())
        axis = TimeAxis(t0, 1.0 if data.shape[-1] == 1 and dt == 0 else dt, data.shape[-1])
        sources = []
        start = 0
        for vertex_ids in vertices:
            stop = start + len(vertex_ids)
            sources.append(
                SourceData(
                    axis, vertex_ids, _H5SourceValues(filename, data, start, stop, component)
                )
            )
            start = stop
    return tuple(sources)


# MATLAB container decoding


def _read_mat_file(filename, fields=None):
    if not h5py.is_hdf5(filename):
        return loadmat(filename, simplify_cells=True, variable_names=fields)
    with h5py.File(filename, "r") as stream:

        def read(node, ancestors=()):
            if node.name in ancestors or len(ancestors) > 32:
                raise ValueError("Cyclic or excessively nested MATLAB data.")
            ancestors = (*ancestors, node.name)
            if isinstance(node, h5py.Group):
                if "MATLAB_sparse" in node.attrs:
                    shape = (int(node.attrs["MATLAB_sparse"]), len(node["jc"]) - 1)
                    return csc_matrix(
                        (node["data"][()], node["ir"][()], node["jc"][()]), shape=shape
                    )
                return {key: read(node[key], ancestors) for key in node if not key.startswith("#")}
            value = node[()]
            if node.attrs.get("MATLAB_empty", 0):
                return np.empty(0)
            if h5py.check_dtype(ref=node.dtype) is not None:
                if value.size == 1:
                    reference = value.flat[0]
                    return read(stream[reference], ancestors) if reference else np.empty(0)
                result = np.empty(value.size, dtype=object)
                for index, reference in enumerate(value.T.flat):
                    result[index] = read(stream[reference], ancestors) if reference else np.empty(0)
                return result.reshape(value.T.shape)
            matlab_class = node.attrs.get("MATLAB_class", b"")
            if matlab_class in (b"char", "char"):
                return "".join(chr(int(char)) for char in value.T.ravel())
            if matlab_class in (b"logical", "logical"):
                value = value.astype(bool)
            if value.dtype.names and {"real", "imag"}.issubset(value.dtype.names):
                value = value["real"] + 1j * value["imag"]
            return value.T.squeeze()

        return {
            key: read(stream[key])
            for key in stream
            if not key.startswith("#") and (fields is None or key in fields)
        }


def _mat_source_candidates(data, prefix="", depth=0):
    if not isinstance(data, dict) or depth > 12:
        return {}
    brainstorm = "Time" in data and ("ImageGridAmp" in data or "ImagingKernel" in data)
    fieldtrip = "pos" in data and any(key in data for key in ("mom", "pow", "avg"))
    if brainstorm or fieldtrip:
        return {prefix or "(root)": data}
    candidates = {}
    for key, value in data.items():
        if not key.startswith("__") and key not in ("cfg", "History"):
            candidates.update(
                _mat_source_candidates(value, f"{prefix}.{key}".lstrip("."), depth + 1)
            )
    return candidates


# Brainstorm source reconstruction


def _brainstorm_surface_files(folder):
    return {
        kind: {
            path.name: path
            for path in sorted(folder.glob(f"tess_cortex_{kind}_*.mat"))
            if path.is_file()
        }
        for kind in ("pial", "white", "mid", "inflated")
    }


def _brainstorm_structs(value, label):
    if isinstance(value, dict):
        names = value.get(label)
        if isinstance(names, np.ndarray) and names.dtype.kind == "O" and names.size > 1:
            for index in range(names.size):
                yield {
                    key: item.ravel()[index]
                    if isinstance(item, np.ndarray)
                    and item.dtype.kind == "O"
                    and item.size == names.size
                    else item
                    for key, item in value.items()
                }
        else:
            yield value
    else:
        for item in np.asarray(value, dtype=object).ravel():
            if isinstance(item, dict):
                yield item


def _brainstorm_hemispheres(mesh, count):
    hemispheres = np.full(count, -1, dtype=np.int8)
    for atlas in _brainstorm_structs(mesh.get("Atlas", []), "Name"):
        if str(atlas.get("Name", "")).strip().lower() != "structures":
            continue
        for scout in _brainstorm_structs(atlas.get("Scouts", []), "Label"):
            side = {
                "cortex l": 0,
                "lh": 0,
                "01_lhemi l": 0,
                "cortex r": 1,
                "rh": 1,
                "01_rhemi r": 1,
            }.get(str(scout.get("Label", "")).strip().lower())
            if side is None:
                continue
            vertices = np.asarray(scout.get("Vertices", [])).ravel()
            if (
                not vertices.size
                or vertices.dtype.kind not in "iuf"
                or not np.isfinite(vertices).all()
                or np.any(vertices != np.floor(vertices))
                or vertices.min() < 1
                or vertices.max() > count
            ):
                raise ValueError("Invalid Brainstorm cortical hemisphere vertex IDs.")
            vertices = vertices.astype(np.int64) - 1
            if len(np.unique(vertices)) != len(vertices) or np.any(hemispheres[vertices] != -1):
                raise ValueError("Brainstorm cortical hemisphere vertex IDs must not overlap.")
            hemispheres[vertices] = side
    return hemispheres if np.all(hemispheres >= 0) and len(np.unique(hemispheres)) == 2 else None


def _brainstorm_sphere(mesh, hemispheres):
    if hemispheres is None:
        return None
    registration = mesh.get("Reg", {})
    sphere = registration.get("Sphere", {}) if isinstance(registration, dict) else {}
    if not isinstance(sphere, dict) or not _has_source_values(sphere.get("Vertices", [])):
        return None
    # shortcut: sphere remapping requires hemisphere blocks; add legacy interleaved layouts when needed.
    if np.count_nonzero(np.diff(hemispheres)) != 1:
        return None
    vertices = np.asarray(sphere["Vertices"])
    if (
        vertices.shape != (len(hemispheres), 3)
        or vertices.dtype.kind not in "iuf"
        or not np.isfinite(vertices).all()
    ):
        raise ValueError("Brainstorm registered sphere vertices must match the cortical mesh.")
    radius = np.linalg.norm(vertices, axis=1)
    if not np.isfinite(radius).all() or np.any(radius <= 0):
        raise ValueError("Brainstorm registered sphere vertices must have positive, finite radii.")
    return vertices / radius[:, None]


def _read_brainstorm_display_surface(series, representation):
    expected = series.brainstorm_surface.name.replace(
        f"_{series.base_representation}_", f"_{representation}_", 1
    )
    path = min(
        series.subject_files[representation].values(),
        key=lambda item: (item.name != expected, not item.stem.endswith("_low"), item.name),
    )
    mesh = _read_mat_file(path, ("Vertices", "Faces", "Atlas", "Reg"))
    points, triangles = _validate_source_mesh(
        mesh.get("Vertices", []), np.asarray(mesh.get("Faces", [])) - 1
    )
    hemispheres = _brainstorm_hemispheres(mesh, len(points))
    sphere = _brainstorm_sphere(mesh, hemispheres)
    if sphere is None:
        raise ValueError(
            "This Brainstorm representation requires cortical Structures and registered Sphere metadata."
        )
    rows, columns, weights = [], [], []
    for side in (0, 1):
        original = np.flatnonzero(series.vertex_hemispheres == side)
        displayed = np.flatnonzero(hemispheres == side)
        distances, neighbors = cKDTree(series.brainstorm_sphere[original]).query(
            sphere[displayed], k=min(8, len(original))
        )
        distances = distances.reshape(len(displayed), -1)
        neighbors = neighbors.reshape(len(displayed), -1)
        # Shepard interpolation stays within each hemisphere and preserves exact correspondences.
        weight = 1.0 / np.maximum(distances, 1e-12) ** 2
        exact = distances[:, 0] <= 1e-10
        weight[exact] = 0
        weight[exact, 0] = 1
        weight /= weight.sum(axis=1, keepdims=True)
        rows.append(np.repeat(displayed, neighbors.shape[1]))
        columns.append(series.vertex_sources[original[neighbors]].ravel())
        weights.append(weight.ravel())
    mapping = csr_matrix(
        (np.concatenate(weights), (np.concatenate(rows), np.concatenate(columns))),
        shape=(len(points), sum(len(source.vertices) for source in series.sources)),
    )
    points = nib.affines.apply_affine(series.surface_to_project_ras, points * 1000.0)
    if not np.isfinite(points).all():
        raise ValueError("The cortical representation has invalid project coordinates.")
    return points, triangles, mapping, hemispheres


def _brainstorm_subject_path(subject_dir, reference):
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("The Brainstorm anatomy catalog must specify Cortex and Anatomy files.")
    relative = Path(reference.strip().replace("\\", "/"))
    for path in (subject_dir / relative, subject_dir / relative.name):
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(f"Brainstorm anatomy file not found in '{subject_dir}': {reference}")


def _brainstorm_to_ras(filename, surface_path, config):
    if "source_to_scanner_ras" in config:
        return _affine(config["source_to_scanner_ras"])
    anatomy = sorted(surface_path.parent.glob("subjectimage*.mat"))
    reference = str(anatomy[0]) if len(anatomy) == 1 else ""
    path = _source_companion(
        filename,
        config,
        "brainstorm_mri",
        "Select the Brainstorm MRI MAT containing SCS, Voxsize and InitTransf.",
        reference,
    )
    mri = _read_mat_file(path, ("SCS", "Voxsize", "InitTransf"))
    scs = mri.get("SCS", {})
    if not isinstance(scs, dict) or not all(key in scs for key in ("R", "T")):
        raise ValueError("The Brainstorm MRI does not contain its MRI-to-SCS transformation.")
    spacing = np.asarray(mri.get("Voxsize", []), dtype=float).ravel()
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("The Brainstorm MRI has invalid voxel spacing.")
    initial = np.asarray(mri.get("InitTransf", []), dtype=object)
    if initial.size == 2:
        initial = initial.reshape(1, 2)
    if initial.ndim != 2 or initial.shape[1] != 2:
        raise ValueError("The Brainstorm MRI has no usable InitTransf table.")
    world = next((value for label, value in initial if str(label).lower() == "vox2ras"), None)
    if world is None:
        raise ValueError("The Brainstorm MRI has no vox2ras transformation.")
    mri_to_scs = np.eye(4)
    mri_to_scs[:3, :3] = np.asarray(scs["R"], dtype=float)
    mri_to_scs[:3, 3] = np.asarray(scs["T"], dtype=float).reshape(3)
    # Brainstorm MRI voxel coordinates are one-based; input and output here are millimeters.
    origin = np.eye(4)
    origin[:3, 3] = -1
    return _affine(
        _affine(world) @ origin @ np.diag([*(1 / spacing), 1]) @ np.linalg.inv(_affine(mri_to_scs))
    )


def _read_brainstorm_source(filename, data, config):
    if str(data.get("HeadModelType", "surface")).lower() != "surface":
        raise ValueError("Brainstorm volume and mixed source models require a volume renderer.")
    if "subject_dir" in config:
        subject_dir = Path(config["subject_dir"])
        anatomy = discover_subject_files(subject_dir).get("brainstorm")
        if anatomy is not None:
            config = dict(config)
            config.setdefault("brainstorm_mri", str(anatomy["brainstorm_mri"]))
            if not config.get("surface_file"):
                reference = data.get("SurfaceFile", data.get("SourceLoc", ""))
                surface_path = anatomy["surface_file"]
                if isinstance(reference, str) and reference.strip():
                    try:
                        surface_path = _brainstorm_subject_path(subject_dir, reference)
                    except FileNotFoundError as error:
                        raise SourceImportRequired(
                            "surface_file",
                            f"Select the Brainstorm cortex associated with these sources: {reference}",
                        ) from error
                config["surface_file"] = str(surface_path)
    times = data.get("Time", [])
    values = data.get("ImageGridAmp", np.empty(0))
    if _has_source_values(data.get("ZScore", [])):
        raise ValueError(
            "Export full Brainstorm time courses with Z-score normalization already applied."
        )
    if not _has_source_values(values):
        kernel = data.get("ImagingKernel", np.empty(0))
        if np.ndim(kernel) != 2 or not np.prod(kernel.shape):
            raise ValueError(
                "The Brainstorm file has neither source time courses nor an imaging kernel."
            )
        path = _source_companion(
            filename,
            config,
            "data_file",
            "Select the Brainstorm recordings MAT associated with this imaging kernel.",
            data.get("DataFile", ""),
        )
        recording = _read_mat_file(path, ("F", "Time", "nAvg"))
        samples = np.asarray(recording.get("F", []))
        if samples.ndim != 2 or samples.dtype.kind not in "iuf":
            raise ValueError("The recordings must contain a numeric channel-by-time F matrix.")
        if np.size(times) and _source_axis(recording.get("Time", [])) != _source_axis(times):
            raise ValueError("The Brainstorm kernel and recordings have different time axes.")
        times = recording.get("Time", [])
        options = data.get("OPTIONS", {})
        channels = np.asarray(
            options.get("GoodChannel", data.get("GoodChannel", []))
            if isinstance(options, dict)
            else data.get("GoodChannel", [])
        )
        if len(channels.ravel()):
            channels = channels.ravel()
            if (
                channels.dtype.kind not in "iuf"
                or not np.isfinite(channels).all()
                or np.any(channels != np.floor(channels))
                or channels.min() < 1
                or channels.max() > len(samples)
            ):
                raise ValueError("Invalid Brainstorm GoodChannel indices.")
            samples = samples[channels.astype(int) - 1]
        if kernel.shape[1] != samples.shape[0]:
            raise ValueError("The imaging kernel and recordings have different channel counts.")
        values = kernel @ samples
        if str(data.get("Function", "")).lower() in ("dspm", "glsp", "lcmvp"):
            original_average = float(data.get("nAvg", 1))
            recording_average = float(recording.get("nAvg", 1))
            if not all(
                isfinite(value) and value > 0 for value in (original_average, recording_average)
            ):
                raise ValueError("Brainstorm averaging counts must be positive and finite.")
            values = values * np.sqrt(recording_average / original_average)
    axis = _source_axis(times)
    path = _source_companion(
        filename,
        config,
        "surface_file",
        "Select the Brainstorm cortex MAT associated with these sources.",
        data.get("SurfaceFile", data.get("SourceLoc", "")),
    )
    mesh = _read_mat_file(path, ("Vertices", "Faces", "Atlas", "Reg"))
    points, triangles = _validate_source_mesh(
        mesh.get("Vertices", []), np.asarray(mesh.get("Faces", [])) - 1
    )
    points *= 1000.0
    components = np.asarray(data.get("nComponents", 1)).item()
    if components not in (1, 3):
        raise ValueError("Mixed Brainstorm source components require an explicit source model.")
    components = int(components)
    values = _scalar_source_values(values, len(points), axis, config, components)
    method = str(data.get("Function", "")).strip()
    unit = _signal_unit(data.get("DisplayUnits"))
    if unit == "a.u." and method.lower() in ("dspm", "dspm2018", "dspm2018sc"):
        unit = "1"
    source = SourceData(axis, np.arange(len(points)), values, unit=unit, method=method)
    hemispheres = _brainstorm_hemispheres(mesh, len(points))
    return (source,), (
        points,
        triangles,
        _brainstorm_to_ras(filename, path, config),
        {
            "vertex_hemispheres": hemispheres,
            "brainstorm_sphere": _brainstorm_sphere(mesh, hemispheres),
            "brainstorm_surface": path,
            "subject_files": _brainstorm_surface_files(path.parent),
        },
    )


# FieldTrip source reconstruction


def _read_fieldtrip_source(filename, data, config):
    positions = np.asarray(data["pos"])
    if (
        positions.ndim != 2
        or positions.shape[1] != 3
        or positions.dtype.kind not in "iuf"
        or not np.isfinite(positions).all()
    ):
        raise ValueError("FieldTrip source positions must be a finite N by 3 matrix.")
    unit = str(data.get("unit", "")).strip().lower()
    if unit not in ("m", "cm", "mm"):
        unit = _source_choice(
            config,
            "position_unit",
            "Select the spatial unit of the FieldTrip source positions.",
            ("m", "cm", "mm"),
        )
    positions = positions * {"m": 1000.0, "cm": 10.0, "mm": 1.0}[unit]
    payload = data if any(key in data for key in ("mom", "pow")) else data.get("avg", {})
    if not isinstance(payload, dict):
        raise ValueError("The FieldTrip source measure must be a structure.")
    fields = [key for key in ("mom", "pow") if key in payload and _has_source_values(payload[key])]
    parameter = _source_choice(
        config, "source_parameter", "Select the FieldTrip source measure to visualize.", fields
    )
    dimord = str(
        payload.get(f"{parameter}dimord", data.get(f"{parameter}dimord", data.get("dimord", "")))
    )
    if any(token in dimord for token in ("freq", "rpt", "subj")) or np.size(data.get("freq", [])):
        raise ValueError(
            "Select a single time-domain reconstruction; frequency and trial dimensions cannot be used as time."
        )
    axis = _source_axis(data.get("time", [0.0]))
    inside = np.asarray(data.get("inside", np.ones(len(positions), dtype=bool))).ravel()
    logical = inside.dtype.kind == "b" or (
        inside.dtype == np.uint8 and len(inside) == len(positions) and np.isin(inside, (0, 1)).all()
    )
    if logical:
        if len(inside) != len(positions):
            raise ValueError("FieldTrip inside mask does not match the source positions.")
        active = np.flatnonzero(inside)
    else:
        if (
            inside.dtype.kind not in "iuf"
            or not np.isfinite(inside).all()
            or np.any(inside != np.floor(inside))
            or np.any(inside < 1)
            or np.any(inside > len(positions))
        ):
            raise ValueError("Invalid FieldTrip inside indices.")
        active = inside.astype(int) - 1
    if not len(active) or len(np.unique(active)) != len(active):
        raise ValueError("FieldTrip data must contain unique active source positions.")
    values = payload[parameter]
    if isinstance(values, list) or (isinstance(values, np.ndarray) and values.dtype.kind == "O"):
        cells = list(values) if isinstance(values, list) else list(values.ravel(order="F"))
        if len(cells) != len(positions):
            raise ValueError("FieldTrip source cells do not match the positions.")
        if "inside" not in data:
            active = np.asarray(
                [index for index, cell in enumerate(cells) if np.size(cell)], dtype=np.int64
            )
            if not len(active):
                raise ValueError("The FieldTrip cells do not contain any source time courses.")
        rows = []
        for index in active:
            cell = np.asarray(cells[index])
            if dimord == "{pos}_time_ori":
                cell = cell.T
            elif dimord not in ("", "{pos}_time", "{pos}_ori_time", "pos_time", "pos_ori_time"):
                raise ValueError("Unsupported FieldTrip cell dimensions for a source time course.")
            if cell.size not in (axis.n_frames, 3 * axis.n_frames):
                raise ValueError("An active FieldTrip source is missing a time course.")
            if cell.ndim == 2 and cell.shape[-1] != axis.n_frames:
                raise ValueError("FieldTrip moment cells must have components by time samples.")
            rows.append(cell.reshape(-1, axis.n_frames))
        if len({row.shape[0] for row in rows}) != 1:
            raise ValueError("Mixed scalar and vector FieldTrip sources are not supported.")
        values = _scalar_source_values(
            np.concatenate(rows), len(active), axis, config, rows[0].shape[0]
        )
    else:
        values = np.asarray(values)
        if dimord in ("time_pos",):
            values = values.T
        components = 1
        if parameter == "mom" and values.ndim == 3:
            tokens = dimord.replace("{", "").replace("}", "").split("_")
            if sorted(tokens) != ["ori", "pos", "time"]:
                raise ValueError(
                    "Three-dimensional FieldTrip moments require an explicit pos/ori/time dimord."
                )
            values = values.transpose(*(tokens.index(token) for token in ("pos", "ori", "time")))
            if values.shape != (len(positions), 3, axis.n_frames):
                raise ValueError(
                    "FieldTrip vector moments do not match the source positions and times."
                )
            values = values.reshape(len(positions) * 3, axis.n_frames)
            components = 3
        elif parameter == "mom" and values.shape == (len(positions) * 3, axis.n_frames):
            components = 3
        values = _scalar_source_values(values, len(positions), axis, config, components)[:, active]
    coordinates = str(data.get("coordsys", "")).strip().lower()
    if coordinates == "scanner_ras":
        coordinates = "scanras"
    if "tri" in data:
        points, triangles = _validate_source_mesh(positions, np.asarray(data["tri"]) - 1)
        vertices = active
    else:
        path = _source_companion(
            filename,
            config,
            "surface_file",
            "Select the FieldTrip surface MAT containing pos, tri and its spatial unit.",
        )
        mesh = _read_mat_file(path)
        if (
            "pos" not in mesh
            and len([value for key, value in mesh.items() if not key.startswith("__")]) == 1
        ):
            mesh = next(value for key, value in mesh.items() if not key.startswith("__"))
        mesh_unit = str(mesh.get("unit", "")).strip().lower()
        if mesh_unit not in ("m", "cm", "mm"):
            raise ValueError("The FieldTrip surface must specify its spatial unit.")
        mesh_coordinates = str(mesh.get("coordsys", "")).strip().lower()
        if mesh_coordinates == "scanner_ras":
            mesh_coordinates = "scanras"
        if coordinates and mesh_coordinates and coordinates != mesh_coordinates:
            raise ValueError("The FieldTrip surface and sources use different coordinate systems.")
        coordinates = coordinates or mesh_coordinates
        points, triangles = _validate_source_mesh(
            np.asarray(mesh.get("pos", [])) * {"m": 1000, "cm": 10, "mm": 1}[mesh_unit],
            np.asarray(mesh.get("tri", [])) - 1,
        )
        distances, vertices = cKDTree(points).query(positions[active])
        if np.any(distances > 1e-3):
            raise ValueError(
                "The selected surface does not contain the FieldTrip source positions. Volume sources require a volume renderer."
            )
    if "source_to_scanner_ras" in config:
        transform = _affine(config["source_to_scanner_ras"])
    elif coordinates == "scanras":
        transform = np.eye(4)
    else:
        raise SourceImportRequired(
            "source_to_scanner_ras",
            f"FieldTrip coordinates '{coordinates or 'unspecified'}': select the source-mm to scanner-RAS-mm transformation matrix.",
        )
    signal_unit = _signal_unit(payload.get(f"{parameter}unit", data.get(f"{parameter}unit")))
    cfg = data.get("cfg", {})
    method = str(cfg.get("method", "")) if isinstance(cfg, dict) else ""
    source = SourceData(
        axis,
        np.asarray(vertices, dtype=np.int64),
        values,
        unit=signal_unit,
        measure="power" if parameter == "pow" else "amplitude",
        method=method,
    )
    return (source,), (
        points,
        triangles,
        transform,
    )
