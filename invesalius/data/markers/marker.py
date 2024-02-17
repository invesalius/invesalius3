import copy
import dataclasses

@dataclasses.dataclass
class Marker:
    """Class for storing markers. @dataclass decorator simplifies
    setting default values, serialization, etc."""
    x : float = 0
    y : float = 0
    z : float = 0
    alpha : float = dataclasses.field(default = None)
    beta : float = dataclasses.field(default = None)
    gamma : float = dataclasses.field(default = None)
    r : float = 0
    g : float = 1
    b : float = 0
    size : float = 2
    label : str = '*'
    x_seed : float = 0
    y_seed : float = 0
    z_seed : float = 0
    is_target : bool = False
    session_id : int = 1
    is_brain_target : bool = False
    is_efield_target: bool = False
    x_cortex: float = 0
    y_cortex: float = 0
    z_cortex: float = 0
    alpha_cortex: float = dataclasses.field(default = None)
    beta_cortex: float = dataclasses.field(default = None)
    gamma_cortex: float = dataclasses.field(default = None)

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
    def to_string_headers(cls):
        """Return the string containing tab-separated list of field names (headers)."""
        res = [field.name for field in dataclasses.fields(cls)]
        res.extend(['x_world', 'y_world', 'z_world', 'alpha_world', 'beta_world', 'gamma_world'])
        return '\t'.join(map(lambda x: '\"%s\"' % x, res))

    def to_string(self):
        """Serialize to excel-friendly tab-separated string"""
        res = ''
        for field in dataclasses.fields(self.__class__):
            if field.type is str:
                res += ('\"%s\"\t' % getattr(self, field.name))
            else:
                res += ('%s\t' % str(getattr(self, field.name)))

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

    def from_string(self, inp_str):
        """Deserialize from a tab-separated string. If the string is not 
        properly formatted, might throw an exception and leave the object
        in an inconsistent state."""
        for field, str_val in zip(dataclasses.fields(self.__class__), inp_str.split('\t')):
            if field.type is float and str_val != 'None':
                setattr(self, field.name, float(str_val))
            if field.type is float and str_val == 'None':
                setattr(self, field.name, None)
            if field.type is float and str_val != 'None':
                setattr(self, field.name, float(str_val))
            if field.type is str:
                setattr(self, field.name, str_val[1:-1]) # remove the quotation marks
            if field.type is bool:
                setattr(self, field.name, str_val=='True')
            if field.type is int and str_val != 'None':
                setattr(self, field.name, int(str_val))

    def to_dict(self):
        return {
            'position': self.position,
            'orientation': self.orientation,
            'colour': self.colour,
            'size': self.size,
            'label': self.label,
            'is_target': self.is_target,
            'is_efield_target' : self.is_efield_target,
            'seed': self.seed,
            'session_id': self.session_id,
            'cortex_position_orientation': self.cortex_position_orientation,
        }

    def duplicate(self):
        """Create a deep copy of this Marker object."""
        return copy.deepcopy(self)
