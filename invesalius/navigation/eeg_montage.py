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

"""Load the EEG montage templates bundled with InVesalius.

The readers intentionally use only the Python standard library. Regardless of
the source format, coordinates are returned in millimetres in the native
right-anterior-superior (RAS) coordinate system used by the templates.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from math import cos, isfinite, radians, sin, sqrt
from pathlib import Path

from invesalius import inv_paths

DEFAULT_HEAD_RADIUS_MM = 95.0
SUPPORTED_MONTAGE_EXTENSIONS = (".elc", ".sfp", ".csd", ".txt")

Position = tuple[float, float, float]

_FIDUCIAL_NAMES = {
    "nasion": "nasion",
    "nz": "nasion",
    "fidnz": "nasion",
    "lpa": "lpa",
    "fidt9": "lpa",
    "rpa": "rpa",
    "fidt10": "rpa",
}


class MontageFormatError(ValueError):
    """Raised when a montage file does not follow its expected format."""


@dataclass(frozen=True)
class MontagePoint:
    """A named point from a montage template, expressed in millimetres."""

    label: str
    position: Position


@dataclass(frozen=True)
class EEGMontageTemplate:
    """Normalized electrode positions and anatomical fiducials."""

    name: str
    channels: tuple[MontagePoint, ...]
    fiducials: dict[str, Position]
    source_path: Path
    coordinate_unit: str = "mm"

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(point.label for point in self.channels)

    @property
    def positions(self) -> tuple[Position, ...]:
        return tuple(point.position for point in self.channels)

    @property
    def channel_positions(self) -> dict[str, Position]:
        return {point.label: point.position for point in self.channels}


def get_available_montages(directory: str | Path | None = None) -> list[str]:
    """Return the names of the bundled montage templates."""
    montage_dir = _montage_directory(directory)
    if not montage_dir.is_dir():
        return []

    return sorted(
        {
            path.stem
            for path in montage_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in SUPPORTED_MONTAGE_EXTENSIONS
        },
        key=str.casefold,
    )


def load_montage(name: str, directory: str | Path | None = None) -> EEGMontageTemplate:
    """Load a bundled montage by name, with or without its extension."""
    montage_dir = _montage_directory(directory)
    requested = Path(name).name.casefold()
    requested_suffix = Path(requested).suffix
    requested_stem = (
        Path(requested).stem if requested_suffix in SUPPORTED_MONTAGE_EXTENSIONS else requested
    )
    matches = [
        path
        for path in montage_dir.iterdir()
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED_MONTAGE_EXTENSIONS
        and (path.name.casefold() == requested or path.stem.casefold() == requested_stem)
    ]
    if not matches:
        raise FileNotFoundError(f"EEG montage template not found: {name}")
    if len(matches) > 1:
        filenames = ", ".join(sorted(path.name for path in matches))
        raise ValueError(f"Ambiguous EEG montage name {name!r}: {filenames}")
    return read_montage(matches[0])


def read_montage(path: str | Path) -> EEGMontageTemplate:
    """Read a supported montage file and normalize its coordinates to mm."""
    montage_path = Path(path)
    if not montage_path.is_file():
        raise FileNotFoundError(f"EEG montage file not found: {montage_path}")

    readers = {
        ".elc": _read_elc,
        ".sfp": _read_sfp,
        ".csd": _read_csd,
        ".txt": _read_theta_phi,
    }
    suffix = montage_path.suffix.casefold()
    try:
        reader = readers[suffix]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_MONTAGE_EXTENSIONS)
        raise ValueError(
            f"Unsupported EEG montage format {montage_path.suffix!r}; expected {supported}"
        ) from exc

    points = reader(montage_path)
    channels, fiducials = _separate_fiducials(points, montage_path)
    if not channels:
        raise MontageFormatError(f"{montage_path}: montage has no electrode channels")
    return EEGMontageTemplate(
        name=montage_path.stem,
        channels=tuple(channels),
        fiducials=fiducials,
        source_path=montage_path.resolve(),
    )


def _montage_directory(directory: str | Path | None) -> Path:
    return Path(directory) if directory is not None else inv_paths.EEG_MONTAGES_DIR


def _read_elc(path: Path) -> list[MontagePoint]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    unit = None
    declared_count = None
    positions_index = None
    labels_index = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        lower = stripped.casefold()
        if lower.startswith("unitposition"):
            values = re.split(r"[=\s]+", stripped)
            unit = values[-1].casefold()
        elif lower.startswith("numberpositions"):
            match = re.search(r"(\d+)\s*$", stripped)
            if match:
                declared_count = int(match.group(1))
        elif lower == "positions":
            positions_index = index
        elif lower == "labels":
            labels_index = index

    if unit is None:
        raise MontageFormatError(f"{path}: UnitPosition is missing")
    unit_scale = {"mm": 1.0, "cm": 10.0, "m": 1000.0}.get(unit)
    if unit_scale is None:
        raise MontageFormatError(f"{path}: unsupported position unit {unit!r}")
    if positions_index is None or labels_index is None or positions_index >= labels_index:
        raise MontageFormatError(f"{path}: Positions or Labels section is missing")

    positions = []
    for line_number, line in enumerate(
        lines[positions_index + 1 : labels_index], start=positions_index + 2
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        values = stripped.rsplit(":", 1)[-1].split()
        position = _parse_position(values, path, line_number)
        positions.append(tuple(value * unit_scale for value in position))

    labels = [
        line.strip()
        for line in lines[labels_index + 1 :]
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(positions) != len(labels):
        raise MontageFormatError(
            f"{path}: found {len(positions)} positions but {len(labels)} labels"
        )
    if declared_count is not None and declared_count != len(positions):
        raise MontageFormatError(
            f"{path}: NumberPositions declares {declared_count}, found {len(positions)}"
        )
    return _make_points(labels, positions, path)


def _read_sfp(path: Path) -> list[MontagePoint]:
    labels = []
    positions = []
    for line_number, line in _data_lines(path):
        values = line.split()
        if len(values) < 4:
            raise MontageFormatError(f"{path}:{line_number}: expected label and x y z")
        if values[0].casefold() == "headshape":
            continue
        labels.append(values[0])
        positions.append(_parse_position(values[1:4], path, line_number))

    return _make_points(labels, _scale_to_head_radius(positions, path), path)


def _read_csd(path: Path) -> list[MontagePoint]:
    labels = []
    positions = []
    for line_number, line in _data_lines(path, comment_prefix="//"):
        values = line.split()
        if len(values) < 7:
            raise MontageFormatError(
                f"{path}:{line_number}: expected label, spherical and Cartesian coordinates"
            )
        labels.append(values[0])
        positions.append(_parse_position(values[4:7], path, line_number))

    return _make_points(labels, _scale_to_head_radius(positions, path), path)


def _read_theta_phi(path: Path) -> list[MontagePoint]:
    labels = []
    positions = []
    data = list(_data_lines(path))
    if not data:
        raise MontageFormatError(f"{path}: montage is empty")

    for line_number, line in data[1:]:
        values = line.split()
        if len(values) < 3:
            raise MontageFormatError(f"{path}:{line_number}: expected label, theta and phi")
        try:
            theta = radians(float(values[1]))
            phi = radians(float(values[2]))
        except ValueError as exc:
            raise MontageFormatError(
                f"{path}:{line_number}: theta and phi must be numbers"
            ) from exc
        labels.append(values[0])
        positions.append(
            (
                DEFAULT_HEAD_RADIUS_MM * sin(theta) * cos(phi),
                DEFAULT_HEAD_RADIUS_MM * sin(theta) * sin(phi),
                DEFAULT_HEAD_RADIUS_MM * cos(theta),
            )
        )

    present_fiducials = {_FIDUCIAL_NAMES.get(label.casefold()) for label in labels}
    for fiducial_name, label, theta, phi in (
        ("nasion", "Nasion", 115.0, 90.0),
        ("lpa", "LPA", -115.0, 0.0),
        ("rpa", "RPA", 115.0, 0.0),
    ):
        if fiducial_name not in present_fiducials:
            theta_rad = radians(theta)
            phi_rad = radians(phi)
            labels.append(label)
            positions.append(
                (
                    DEFAULT_HEAD_RADIUS_MM * sin(theta_rad) * cos(phi_rad),
                    DEFAULT_HEAD_RADIUS_MM * sin(theta_rad) * sin(phi_rad),
                    DEFAULT_HEAD_RADIUS_MM * cos(theta_rad),
                )
            )

    return _make_points(labels, positions, path)


def _data_lines(path: Path, comment_prefix: str = "#") -> Iterable[tuple[int, str]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith(comment_prefix):
            yield line_number, stripped


def _parse_position(values: list[str], path: Path, line_number: int) -> Position:
    if len(values) != 3:
        raise MontageFormatError(f"{path}:{line_number}: expected three coordinates")
    try:
        position = tuple(float(value) for value in values)
    except ValueError as exc:
        raise MontageFormatError(f"{path}:{line_number}: coordinates must be numbers") from exc
    if len(position) != 3 or not all(isfinite(value) for value in position):
        raise MontageFormatError(f"{path}:{line_number}: coordinates must be finite")
    return position


def _scale_to_head_radius(positions: list[Position], path: Path) -> list[Position]:
    if not positions:
        return []
    radii = sorted(sqrt(sum(value * value for value in position)) for position in positions)
    middle = len(radii) // 2
    median_radius = radii[middle] if len(radii) % 2 else (radii[middle - 1] + radii[middle]) / 2.0
    if not isfinite(median_radius) or median_radius <= 0.0:
        raise MontageFormatError(f"{path}: montage has an invalid head radius")
    scale = DEFAULT_HEAD_RADIUS_MM / median_radius
    return [tuple(value * scale for value in position) for position in positions]


def _make_points(labels: list[str], positions: list[Position], path: Path) -> list[MontagePoint]:
    if len(labels) != len(positions):
        raise MontageFormatError(f"{path}: label and position counts do not match")

    points = []
    seen = set()
    for label, position in zip(labels, positions):
        label = label.strip()
        if not label:
            raise MontageFormatError(f"{path}: channel label cannot be empty")
        normalized_label = label.casefold()
        if normalized_label in seen:
            raise MontageFormatError(f"{path}: duplicate channel label {label!r}")
        seen.add(normalized_label)
        if not all(isfinite(value) for value in position):
            raise MontageFormatError(f"{path}: coordinates for {label!r} must be finite")
        points.append(MontagePoint(label=label, position=position))
    return points


def _separate_fiducials(
    points: list[MontagePoint], path: Path
) -> tuple[list[MontagePoint], dict[str, Position]]:
    channels = []
    fiducials = {}
    for point in points:
        fiducial_name = _FIDUCIAL_NAMES.get(point.label.casefold())
        if fiducial_name is None:
            channels.append(point)
        elif fiducial_name in fiducials:
            raise MontageFormatError(f"{path}: duplicate {fiducial_name} fiducial")
        else:
            fiducials[fiducial_name] = point.position
    return channels, fiducials
