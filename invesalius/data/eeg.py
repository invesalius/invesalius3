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
"""EEG electrode data and montage import/export."""

import csv
import json
from dataclasses import asdict, dataclass, field
from math import isfinite
from pathlib import Path
from struct import pack, unpack
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
    distance_mm: float | None = None
    montage_name: str | None = None

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
        if self.distance_mm is not None and (
            not isinstance(self.distance_mm, (int, float))
            or not isfinite(self.distance_mm)
            or self.distance_mm < 0
        ):
            raise ValueError("Matching distances must be finite and nonnegative.")
        if self.montage_name is not None and (
            not isinstance(self.montage_name, str) or not self.montage_name.strip()
        ):
            raise ValueError("A montage name must be a nonempty string.")

    @property
    def display_colour(self):
        if self.distance_mm is None:
            return self.colour if self.montage_name is None else (0.5, 0.5, 0.5)
        if self.distance_mm < 5.0:
            return (0.0, 1.0, 0.0)
        if self.distance_mm < 10.0:
            return (1.0, 1.0, 0.0)
        return (1.0, 0.0, 0.0)

    def to_dict(self):
        return asdict(self)


class EEGMontage:
    """Match electrode templates and serialize montages with MRI coordinate metadata."""

    @staticmethod
    def get_templates() -> dict:
        from invesalius import inv_paths

        path = inv_paths.INV_TOP_DIR / "navigation" / "eeg_montages.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(catalog, dict)
            or catalog.get("units") != "m"
            or not isinstance(catalog.get("montages"), dict)
            or not catalog["montages"]
        ):
            raise ValueError(_("Invalid EEG montage template catalog."))
        return catalog["montages"]

    @staticmethod
    def match_template(template, positions, fiducials) -> tuple[list[str], np.ndarray]:
        """Return unique labels and residuals in capture order, without modifying captures.

        Positions and fiducials are in InVesalius image mm; fiducial order is LPA, RPA, Nasion.
        """
        from scipy.optimize import linear_sum_assignment
        from scipy.spatial.distance import cdist, pdist

        from invesalius.data.transformations import affine_matrix_from_points

        positions = np.asarray(positions, dtype=float)
        fiducials = np.asarray(fiducials, dtype=float)
        if fiducials.shape != (3, 3) or not np.isfinite(fiducials).all():
            raise ValueError(_("Register image fiducials (Left Ear, Right Ear, Nasion) first."))
        if (
            positions.ndim != 2
            or positions.shape[1] != 3
            or len(positions) < 3
            or not np.isfinite(positions).all()
        ):
            raise ValueError(_("Auto labelling requires at least three finite EEG positions."))
        if (
            not isinstance(template, dict)
            or not isinstance(template.get("electrodes"), dict)
            or not isinstance(template.get("fiducials"), dict)
        ):
            raise ValueError(_("Invalid EEG montage template coordinates."))
        try:
            labels = list(template["electrodes"])
            # The bundled templates use meters and anterior +Y; image coordinates use mm and -Y.
            template_positions = np.asarray(list(template["electrodes"].values()), dtype=float)
            template_positions = template_positions * (1000, -1000, 1000)
            template_fiducials = np.asarray(
                [template["fiducials"][name] for name in ("lpa", "rpa", "nasion")], dtype=float
            ) * (1000, -1000, 1000)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(_("Invalid EEG montage template coordinates.")) from error
        if (
            template.get("units") != "m"
            or template_positions.shape != (len(labels), 3)
            or template_fiducials.shape != (3, 3)
            or not np.isfinite(template_positions).all()
            or not np.isfinite(template_fiducials).all()
            or not labels
            or any(not isinstance(label, str) or not label.strip() for label in labels)
        ):
            raise ValueError(_("Invalid EEG montage template coordinates."))
        if len(positions) > len(labels):
            raise ValueError(
                _("There are more captured electrodes than channels in this template.")
            )
        for points in (positions, fiducials, template_fiducials, template_positions):
            if np.linalg.matrix_rank(points - points.mean(axis=0)) < 2:
                raise ValueError(_("EEG positions and fiducials must not be collinear."))
            if pdist(points).min() < 1e-6:
                raise ValueError(_("Duplicate EEG positions or fiducials cannot be matched."))

        transform = affine_matrix_from_points(
            template_fiducials.T, fiducials.T, shear=False, scale=True
        )
        best_error = float("inf")
        for iteration in range(6):
            aligned = template_positions @ transform[:3, :3].T + transform[:3, 3]
            costs = cdist(positions, aligned)
            rows, columns = linear_sum_assignment(costs)
            distances = costs[rows, columns]
            mean_error = float(distances.mean())
            if mean_error >= best_error:
                break
            improvement = best_error - mean_error
            best_error = mean_error
            best_columns, best_distances = columns.copy(), distances.copy()
            if improvement < 0.1 or iteration == 5:
                break
            good = distances < 50.0
            source = template_positions[columns[good]]
            target = positions[rows[good]]
            if len(source) < 3 or any(
                np.linalg.matrix_rank(points - points.mean(axis=0)) < 2
                for points in (source, target)
            ):
                break
            transform = affine_matrix_from_points(source.T, target.T, shear=False, scale=True)

        return [labels[index] for index in best_columns], best_distances

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
    def read_montage(filename) -> list[EEGElectrode]:
        """Read an InVesalius export with its registration sidecar into the current MRI."""
        path = Path(filename)
        export_format = "BIDS" if path.suffix.lower() == ".tsv" else path.suffix[1:].upper()
        paths = EEGMontage.get_export_paths(path.parent, export_format, path.name)
        if not paths[-1].is_file():
            raise ValueError(
                _("Keep the matching *_registration.json file beside the exported EEG montage.")
            )
        metadata = json.loads(paths[-1].read_text(encoding="utf-8"))
        current_matrix = EEGMontage._image_to_scanner_ras_matrix()
        try:
            source_matrix = np.asarray(metadata["ImageToScannerRAS"]["Matrix"], dtype=float)
            if source_matrix.shape != (4, 4) or not np.allclose(
                source_matrix, current_matrix, rtol=1e-6, atol=1e-4
            ):
                raise ValueError(_("Open the MRI project used to export this EEG montage."))
            if metadata["ExportFormat"] != export_format:
                raise ValueError(_("The EEG montage format does not match its registration file."))
            if export_format == "FIF":
                electrodes = EEGMontage._read_fif(path)
                transforms = [
                    item
                    for item in metadata["AdditionalTransformations"]
                    if item["SourceCoordinateSystem"] == "MNE head"
                    and item["DestinationCoordinateSystem"] == "MRI Scanner RAS"
                    and item["SourceCoordinateUnits"] == item["DestinationCoordinateUnits"] == "m"
                ]
                if len(transforms) != 1:
                    raise ValueError(_("The FIF montage requires a head-to-Scanner-RAS transform."))
                transform = np.asarray(transforms[0]["Matrix"], dtype=float)
                if EEGMontage._transform_metadata("head", "ras", transform)["Matrix"] is None:
                    raise ValueError(_("Invalid FIF coordinate transform."))
                if (
                    metadata["ExportedCoordinateSystem"] != "MNE head"
                    or metadata["ExportedCoordinateUnits"] != "m"
                ):
                    raise ValueError(_("The FIF montage must use MNE head coordinates in meters."))
                electrodes = [
                    (name, (transform @ [*position, 1])[:3] * 1000) for name, position in electrodes
                ]
            else:
                if (
                    metadata["ExportedCoordinateSystem"] != "MRI Scanner RAS"
                    or metadata["ExportedCoordinateUnits"] != "mm"
                ):
                    raise ValueError(_("The EEG montage must use Scanner RAS coordinates in mm."))
                electrodes = EEGMontage._read_text_montage(path, export_format)
            details = {item["Name"]: item for item in metadata.get("ElectrodeRegistrations", [])}
        except (KeyError, TypeError, IndexError, csv.Error) as error:
            raise ValueError(_("Invalid EEG montage registration metadata.")) from error
        if not electrodes:
            raise ValueError(_("There are no EEG electrodes in this montage."))
        EEGMontage._validate_export_labels(electrodes)
        world_to_image = np.linalg.inv(current_matrix)
        return [
            EEGElectrode(
                label=name,
                position=(world_to_image @ [*position, 1])[:3].tolist(),
                distance_mm=details.get(name, {}).get("DistanceMM"),
                montage_name=details.get(name, {}).get("MontageName"),
            )
            for name, position in electrodes
        ]

    @staticmethod
    def _read_text_montage(path, export_format):
        if export_format == "BIDS":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, delimiter="\t")
                if not {"name", "x", "y", "z"}.issubset(reader.fieldnames or ()):
                    raise ValueError(_("The EEG TSV file needs name, x, y and z columns."))
                return [
                    (row["name"], [float(row[axis]) for axis in ("x", "y", "z")]) for row in reader
                ]
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if export_format == "ELC":
            if "UnitPosition mm" not in lines:
                raise ValueError(_("The exported ELC montage must use millimeters."))
            counts = [
                line.split("=", 1)[1] for line in lines if line.startswith("NumberPositions=")
            ]
            if len(counts) != 1:
                raise ValueError(_("The ELC montage needs one NumberPositions entry."))
            count = int(counts[0])
            start = lines.index("Positions") + 1
            end = lines.index("Labels")
            if end - start != count or len(lines) - end - 1 != count:
                raise ValueError(_("ELC position and label counts do not match."))
            return [
                (name, EEGMontage._read_xyz(position))
                for name, position in zip(lines[end + 1 :], lines[start:end])
                if name not in ("LPA", "Nz", "RPA")
            ]
        electrodes = []
        for line in lines:
            fields = line.split()
            if export_format == "HPTS":
                if len(fields) != 5 or fields[0] not in ("cardinal", "eeg"):
                    raise ValueError(_("Invalid HPTS montage row."))
                kind, name, *coordinates = fields
                position = EEGMontage._read_xyz(" ".join(coordinates))
                if kind == "cardinal":
                    continue
            else:
                if len(fields) != 4:
                    raise ValueError(_("Invalid SFP montage row."))
                name, *coordinates = fields
                position = EEGMontage._read_xyz(" ".join(coordinates))
                if name in ("FidNz", "FidT9", "FidT10", "headshape"):
                    continue
            electrodes.append((name, position))
        return electrodes

    @staticmethod
    def _read_xyz(text):
        values = [float(value) for value in text.split()]
        if len(values) != 3 or not all(isfinite(value) for value in values):
            raise ValueError(_("EEG positions require three finite coordinates."))
        return values

    @staticmethod
    def _read_fif(path):
        # shortcut: read sequential FIFF digitization exports; use a full reader for external FIF files.
        names, frame, points = None, None, []
        file_size = path.stat().st_size
        with path.open("rb") as stream:
            while stream.tell() < file_size:
                header = stream.read(16)
                if len(header) != 16:
                    raise ValueError(_("Truncated FIF tag header."))
                kind, data_type, size, next_tag = unpack(">4i", header)
                if size < 0 or size > file_size - stream.tell() or next_tag not in (0, -1):
                    raise ValueError(_("Invalid or unsupported FIF tag layout."))
                if kind in (213, 3506, 3507):
                    data = stream.read(size)
                    if kind == 213 and data_type == 33 and size == 20:
                        point_kind, identifier, x, y, z = unpack(">ii3f", data)
                        if point_kind == 3:
                            points.append((identifier, [x, y, z]))
                    elif kind == 3506 and data_type == 3 and size == 4:
                        frame = unpack(">i", data)[0]
                    elif kind == 3507 and data_type == 10:
                        names = [
                            name.replace("{COLON}", ":")
                            for name in data.decode("latin1").split(":")
                        ]
                    else:
                        raise ValueError(_("Invalid FIF digitization tag."))
                else:
                    stream.seek(size, 1)
                if next_tag == -1:
                    break
        points.sort(key=lambda point: point[0])
        if (
            frame != 4
            or names is None
            or [identifier for identifier, _position in points] != list(range(1, len(names) + 1))
        ):
            raise ValueError(
                _("FIF electrode names, identifiers or head coordinate frame are invalid.")
            )
        return [(name, position) for name, (_identifier, position) in zip(names, points)]

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
                not isinstance(name, str)
                or not name
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
        matrix = EEGMontage._image_to_scanner_ras_matrix()
        image_to_ras = EEGMontage._transform_metadata("InVesalius image", "MRI Scanner RAS", matrix)
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
                    "DistanceMM": electrode.distance_mm,
                    "MontageName": electrode.montage_name,
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
    def _image_to_scanner_ras_matrix():
        # Recover the positional affine using the existing conversion, including its image Y flip.
        points = [
            EEGMontage._get_world_position(point)
            for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        ]
        matrix = np.eye(4)
        matrix[:3, 3] = points[0]
        matrix[:3, :3] = np.asarray(points[1:]).T - np.asarray(points[0])[:, None]
        if EEGMontage._transform_metadata("image", "ras", matrix)["Matrix"] is None:
            raise ValueError(_("The project does not have a valid MRI world coordinate system."))
        return matrix

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
