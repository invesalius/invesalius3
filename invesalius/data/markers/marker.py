import copy
import dataclasses
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
    version: int = 1
    marker_id: int = 0
    x: float = 0
    y: float = 0
    z: float = 0
    alpha: float = dataclasses.field(default = None)
    beta: float = dataclasses.field(default = None)
    gamma: float = dataclasses.field(default = None)
    r: float = 0
    g: float = 1
    b: float = 0
    size: float = 2
    label: str = '*'
    x_seed: float = 0
    y_seed: float = 0
    z_seed: float = 0
    is_target: bool = False
    is_point_of_interest: bool = False
    session_id: int = 1
    x_cortex: float = 0
    y_cortex: float = 0
    z_cortex: float = 0
    alpha_cortex: float = dataclasses.field(default = None)
    beta_cortex: float = dataclasses.field(default = None)
    gamma_cortex: float = dataclasses.field(default = None)
    marker_type: MarkerType = MarkerType.LANDMARK
    visualization: dict = dataclasses.field(default_factory=dict)

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
        return list((self.r, self.g, self.b),)

    @colour.setter
    def colour(self, new_colour):
        self.r, self.g, self.b = new_colour

    # x_seed, y_seed, z_seed can be jointly accessed as seed
    @property
    def seed(self):
        return list((self.x_seed, self.y_seed, self.z_seed),)

    @seed.setter
    def seed(self, new_seed):
        self.x_seed, self.y_seed, self.z_seed = new_seed

    @property
    def cortex_position_orientation(self):
        return list((self.x_cortex, self.y_cortex, self.z_cortex, self.alpha_cortex, self.beta_cortex, self.gamma_cortex),)

    @cortex_position_orientation.setter
    def cortex_position_orientation(self, new_cortex):
        self.x_cortex, self.y_cortex, self.z_cortex, self.alpha_cortex, self.beta_cortex, self.gamma_cortex = new_cortex

    @classmethod
    def to_csv_header(cls):
        """Return the string containing tab-separated list of field names (header)."""
        res = [field.name for field in dataclasses.fields(cls) if field.name != 'version']
        res.extend(['x_world', 'y_world', 'z_world', 'alpha_world', 'beta_world', 'gamma_world'])
        return '\t'.join(map(lambda x: '\"%s\"' % x, res))

    def to_csv_row(self):
        """Serialize to excel-friendly tab-separated string"""
        res = ''
        for field in dataclasses.fields(self.__class__):
            # Skip the version field, as it won't be stored in the file.
            if field.name == 'version':
                continue

            if field.type is str:
                res += '\"%s\"\t' % getattr(self, field.name)
            elif field.type is MarkerType:
                res += '%s\t' % getattr(self, field.name).value
            else:
                res += '%s\t' % str(getattr(self, field.name))

        if self.alpha is not None and self.beta is not None and self.gamma is not None:
            # Add world coordinates (in addition to the internal ones).
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                position=[self.x, self.y, self.z],
                orientation=[self.alpha, self.beta, self.gamma],
            )

        else:
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                    position=[self.x, self.y, self.z],
                    orientation=[0,0,0],
                )

        res += '\t'.join(map(lambda x: 'N/A' if x is None else str(x), (*position_world, *orientation_world)))
        return res

    def from_csv_row(self, input_str):
        """Deserialize from a tab-separated string. If the string is not 
        properly formatted, might throw an exception and leave the object
        in an inconsistent state."""
        
        columns = MARKER_VERSION_COLUMNS[self.version]
        splitted = input_str.split('\t')

        is_brain_target = False
        is_efield_target = False

        for field, str_val in zip(columns, splitted):
            field_name = field[0]
            var_type = field[1]
            if var_type is float and str_val != 'None':
                value = float(str_val)
            if var_type is float and str_val == 'None':
                value = None
            if var_type is str:
                value = str_val[1:-1] # remove the quotation marks
            if var_type is bool:
                value = str_val == 'True'
            if var_type is int and str_val != 'None':
                value = int(str_val)
            if var_type is MarkerType:
                value = MarkerType(int(str_val))

            if field_name == 'is_brain_target':
                is_brain_target = value

            elif field_name == 'is_efield_target':
                is_efield_target = value

            else:
                setattr(self, field_name, value)

        if self.version in [0, 1]:
            self.marker_type = MarkerType.LANDMARK if self.orientation == [None, None, None] else MarkerType.COIL_TARGET
            if self.label in ['LEI', 'REI', 'NAI']:
                self.marker_type = MarkerType.FIDUCIAL

        if self.version == 0:
            self.cortex_position_orientation = [None, None, None, None, None, None]

        if is_efield_target:
            self.is_point_of_interest = True

        if is_brain_target:
            self.marker_type = MarkerType.BRAIN_TARGET

    def to_dict(self):
        return {
            'position': self.position,
            'orientation': self.orientation,
            'colour': self.colour,
            'size': self.size,
            'label': self.label,
            'is_target': self.is_target,
            'is_point_of_interest': self.is_point_of_interest,
            'marker_type': self.marker_type.value,
            'seed': self.seed,
            'session_id': self.session_id,
            'cortex_position_orientation': self.cortex_position_orientation,
        }

    def duplicate(self):
        """Create a deep copy of this Marker object, without the visualization. Also unset the is_target attribute."""
        # Create a new instance of the Marker class.
        new_marker = Marker()

        # Manually copy all attributes except the visualization.
        for field in dataclasses.fields(self):
            if field.name != 'visualization':
                setattr(new_marker, field.name, copy.deepcopy(getattr(self, field.name)))

        # Set the visualization attribute to an empty dictionary.
        new_marker.visualization = {}

        # Unset the is_target attribute.
        new_marker.is_target = False

        return new_marker


# Dictionary mapping marker version to the list of columns in the marker file.
MARKER_VERSION_COLUMNS = {
    0: (
        ('x', float),
        ('y', float),
        ('z', float),
        ('alpha', float),
        ('beta', float),
        ('gamma', float),
        ('r', float),
        ('g', float),
        ('b', float),
        ('size', float),
        ('label', str),
        ('x_seed', float),
        ('y_seed', float),
        ('z_seed', float),
        ('is_target', bool),
        ('session_id', int),
        ('is_brain_target', bool),
    ),
    1: (
        ('x', float),
        ('y', float),
        ('z', float),
        ('alpha', float),
        ('beta', float),
        ('gamma', float),
        ('r', float),
        ('g', float),
        ('b', float),
        ('size', float),
        ('label', str),
        ('x_seed', float),
        ('y_seed', float),
        ('z_seed', float),
        ('is_target', bool),
        ('session_id', int),
        ('is_brain_target', bool),
        ('is_efield_target', bool),
        ('x_cortex', float),
        ('y_cortex', float),
        ('z_cortex', float),
        ('alpha_cortex', float),
        ('beta_cortex', float),
        ('gamma_cortex', float),
    ),
    2: (
        ('marker_id', int),
        ('x', float),
        ('y', float),
        ('z', float),
        ('alpha', float),
        ('beta', float),
        ('gamma', float),
        ('r', float),
        ('g', float),
        ('b', float),
        ('size', float),
        ('label', str),
        ('x_seed', float),
        ('y_seed', float),
        ('z_seed', float),
        ('is_target', bool),
        ('is_point_of_interest', bool),
        ('session_id', int),
        ('x_cortex', float),
        ('y_cortex', float),
        ('z_cortex', float),
        ('alpha_cortex', float),
        ('beta_cortex', float),
        ('gamma_cortex', float),
        ('marker_type', MarkerType),
    ),
}
