"""Digitized EEG electrodes, independent of navigation targets and markers."""

from dataclasses import asdict, dataclass, field
from math import isfinite
from uuid import uuid4


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

    @classmethod
    def from_legacy_marker(cls, data):
        """Read EEG records written by the former marker-based implementation."""
        return cls(
            position=data.get("position", [data.get(axis, 0.0) for axis in "xyz"]),
            orientation=data.get(
                "orientation", [data.get(axis) or 0.0 for axis in ("alpha", "beta", "gamma")]
            ),
            colour=data.get(
                "colour", [data.get(axis, default) for axis, default in zip("rgb", (0.0, 1.0, 0.0))]
            ),
            label=data.get("eeg_matched_name") or data["label"],
            size=data.get("size", 2.0),
            visible=data.get("visible", True),
            session_id=data.get("session_id", 1),
            electrode_uuid=data.get("marker_uuid") or str(uuid4()),
        )
