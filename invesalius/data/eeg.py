"""EEG electrode data and montage exports."""

import csv
import json
from dataclasses import asdict, dataclass, field
from math import isfinite
from pathlib import Path
from struct import pack
from tempfile import TemporaryDirectory
from time import time_ns
from uuid import uuid4

import numpy as np

from invesalius.i18n import tr as _


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
