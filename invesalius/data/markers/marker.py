import copy
import dataclasses
import uuid
from enum import Enum

import invesalius.data.imagedata_utils as imagedata_utils


class MarkerType(Enum):
    """Enum for marker types. The values are used to visually distinguish
    between different types of markers. The values are used in the
    'marker_type' field of the Marker class. The enum values are:

    LANDMARK: a point of interest, e.g. a point on the brain surface.
    BRAIN_TARGET: a target point and orientation on the brain surface.
    COIL_TARGET: a target point and orientation (= pose) of the coil.
    COIL_POSE: a point and orientation (= pose) of the coil; otherwise similar to COIL_TARGET,
        but created to store the coil pose after a stimulation pulse is delivered. Visualized
        differently from COIL_TARGET.
    """

    FIDUCIAL = 0
    LANDMARK = 1
    BRAIN_TARGET = 2
    COIL_TARGET = 3
    COIL_POSE = 4

    @property
    def human_readable(self):
        """Returns a human-readable name for the enum member."""
        # Dictionary mapping enum values to human-readable names.
        names = {
            MarkerType.FIDUCIAL: "Fiducial",
            MarkerType.LANDMARK: "Landmark",
            MarkerType.BRAIN_TARGET: "Brain Target",
            MarkerType.COIL_TARGET: "Coil Target",
            MarkerType.COIL_POSE: "Coil Pose",
        }
        # Return the human-readable name for the enum member.
        return names[self]


@dataclasses.dataclass
class Marker:
    """Class for storing markers. @dataclass decorator simplifies
    setting default values, serialization, etc."""

    version: int = 3
    marker_id: int = 0
    x: float = 0
    y: float = 0
    z: float = 0
    alpha: float = dataclasses.field(default=None)
    beta: float = dataclasses.field(default=None)
    gamma: float = dataclasses.field(default=None)
    r: float = 0
    g: float = 1
    b: float = 0
    size: float = 2
    label: str = ""
    x_seed: float = 0
    y_seed: float = 0
    z_seed: float = 0
    is_target: bool = False
    is_point_of_interest: bool = False
    session_id: int = 1
    x_cortex: float = 0
    y_cortex: float = 0
    z_cortex: float = 0
    alpha_cortex: float = dataclasses.field(default=None)
    beta_cortex: float = dataclasses.field(default=None)
    gamma_cortex: float = dataclasses.field(default=None)
    marker_type: MarkerType = MarkerType.LANDMARK
    z_rotation: float = 0.0
    z_offset: float = 0.0
    visualization: dict = dataclasses.field(default_factory=dict)
    marker_uuid: str = ""
    # #TODO: add a reference to original coil marker to relate it to MEP
    # in micro Volts (but scale in milli Volts for display)
    mep_value: float = dataclasses.field(default=None)

    # x, y, z can be jointly accessed as position
    @property
    def position(self):
        return list((self.x, self.y, self.z))

    @position.setter
    def position(self, new_position):
        self.x, self.y, self.z = new_position

    # alpha, beta, gamma can be jointly accessed as orientation
    @property
    def orientation(self):
        return list((self.alpha, self.beta, self.gamma))

    @orientation.setter
    def orientation(self, new_orientation):
        self.alpha, self.beta, self.gamma = new_orientation

    # alpha, beta, gamma can be jointly accessed as orientation
    @property
    def coordinate(self):
        return list((self.x, self.y, self.z, self.alpha, self.beta, self.gamma))

    # r, g, b can be jointly accessed as colour
    @property
    def colour(self):
        return list(
            (self.r, self.g, self.b),
        )

    @colour.setter
    def colour(self, new_colour):
        self.r, self.g, self.b = new_colour

    # access colour in digital 8-bit per channel rgb format
    @property
    def colour8bit(self):
        return [ch * 255 for ch in self.colour]

    @colour8bit.setter
    def colour8bit(self, new_colour):
        self.colour = [s / 255.0 for s in new_colour]

    # x_seed, y_seed, z_seed can be jointly accessed as seed
    @property
    def seed(self):
        return list(
            (self.x_seed, self.y_seed, self.z_seed),
        )

    @seed.setter
    def seed(self, new_seed):
        self.x_seed, self.y_seed, self.z_seed = new_seed

    @property
    def cortex_position_orientation(self):
        return list(
            (
                self.x_cortex,
                self.y_cortex,
                self.z_cortex,
                self.alpha_cortex,
                self.beta_cortex,
                self.gamma_cortex,
            ),
        )

    @cortex_position_orientation.setter
    def cortex_position_orientation(self, new_cortex):
        (
            self.x_cortex,
            self.y_cortex,
            self.z_cortex,
            self.alpha_cortex,
            self.beta_cortex,
            self.gamma_cortex,
        ) = new_cortex

    @classmethod
    def to_csv_header(cls):
        """Return the string containing tab-separated list of field names (header)."""
        res = [
            field.name
            for field in dataclasses.fields(cls)
            if (
                field.name != "version"
                and field.name != "marker_uuid"
                and field.name != "visualization"
            )
        ]
        res.extend(["x_world", "y_world", "z_world", "alpha_world", "beta_world", "gamma_world"])
        return "\t".join(map(lambda x: f'"{x}"', res))

    def to_csv_row(self):
        """Serialize to excel-friendly tab-separated string"""
        res = ""
        for field in dataclasses.fields(self.__class__):
            # Skip version, uuid, and visualization fields, as they won't be stored in the file.
            if (
                field.name == "version"
                or field.name == "marker_uuid"
                or field.name == "visualization"
            ):
                continue

            if field.type is str:
                res += f'"{getattr(self, field.name)}"\t'
            elif field.type is MarkerType:
                res += f"{getattr(self, field.name).value}\t"
            else:
                res += f"{str(getattr(self, field.name))}\t"

        if self.alpha is not None and self.beta is not None and self.gamma is not None:
            # Add world coordinates (in addition to the internal ones).
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                position=[self.x, self.y, self.z],
                orientation=[self.alpha, self.beta, self.gamma],
            )

        else:
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                position=[self.x, self.y, self.z],
                orientation=[0, 0, 0],
            )

        res += "\t".join(
            map(lambda x: "N/A" if x is None else str(x), (*position_world, *orientation_world))
        )
        return res

    def to_dict(self):
        return {
            "position": self.position,
            "orientation": self.orientation,
            "colour": self.colour,
            "size": self.size,
            "label": self.label,
            "is_target": self.is_target,
            "is_point_of_interest": self.is_point_of_interest,
            "marker_type": self.marker_type.value,
            "seed": self.seed,
            "session_id": self.session_id,
            "cortex_position_orientation": self.cortex_position_orientation,
            "z_rotation": self.z_rotation,
            "z_offset": self.z_offset,
            "mep_value": self.mep_value,
        }

    def from_dict(self, d):
        # Account for different versions of the markers dictionary that may not have all the fields.
        #
        # For instance, when stored as a state in state.json, the marker dictionary has the fields 'position' and
        # 'orientation', whereas when stored in a marker file, the fields are 'x', 'y', 'z', 'alpha', 'beta', 'gamma'.
        position = d["position"] if "position" in d else [d["x"], d["y"], d["z"]]
        orientation = (
            d["orientation"] if "orientation" in d else [d["alpha"], d["beta"], d["gamma"]]
        )
        colour = d["colour"] if "colour" in d else [d["r"], d["g"], d["b"]]
        seed = d["seed"] if "seed" in d else [d["x_seed"], d["y_seed"], d["z_seed"]]

        # The old versions of the markers dictionary do not have the 'marker_type' field; in that case, infer the
        # marker type from the label and orientation.
        if "marker_type" in d:
            marker_type = d["marker_type"]
        else:
            if d["label"] in ["LEI", "REI", "NAI"]:
                marker_type = MarkerType.FIDUCIAL.value

            elif orientation == [None, None, None]:
                marker_type = MarkerType.LANDMARK.value

            else:
                marker_type = MarkerType.COIL_TARGET.value

        cortex_position_orientation = (
            d["cortex_position_orientation"]
            if "cortex_position_orientation" in d
            else [
                d["x_cortex"],
                d["y_cortex"],
                d["z_cortex"],
                d["alpha_cortex"],
                d["beta_cortex"],
                d["gamma_cortex"],
            ]
        )

        z_offset = d.get("z_offset", 0.0)
        z_rotation = d.get("z_rotation", 0.0)
        is_point_of_interest = d.get("is_point_of_interest", False)
        mep_value = d.get("mep_value", None)

        self.size = d["size"]
        self.label = d["label"]
        self.is_target = d["is_target"]
        self.session_id = d["session_id"]

        self.position = position
        self.orientation = orientation
        self.colour = colour
        self.seed = seed
        self.is_point_of_interest = is_point_of_interest
        self.marker_type = MarkerType(marker_type)
        self.cortex_position_orientation = cortex_position_orientation
        self.z_offset = z_offset
        self.z_rotation = z_rotation
        self.mep_value = mep_value

        return self

    def duplicate(self):
        """Create a deep copy of this Marker object, without the visualization. Also unset the is_target attribute."""
        # Create a new instance of the Marker class.
        new_marker = Marker()

        # Manually copy all attributes except the visualization and the marker_uuid.
        for field in dataclasses.fields(self):
            if field.name != "visualization" and field.name != "marker_uuid":
                setattr(new_marker, field.name, copy.deepcopy(getattr(self, field.name)))

        # Give the duplicate marker unique uuid
        new_marker.marker_uuid = str(uuid.uuid4())

        # Set the visualization attribute to an empty dictionary.
        new_marker.visualization = {}

        # Unset the is_target attribute.
        new_marker.is_target = False

        return new_marker
