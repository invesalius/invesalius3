from invesalius import utils
from invesalius.data.slice_ import Slice
from invesalius.data.mask import Mask
import numpy as np
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher
from invesalius import constants as const

class CropMaskConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.dlg_visible = False
        self.limits = None  # (xi, xf, yi, yf, zi, zf)

class CropMask:
    def __init__(self, slice):
        self.state_code = const.SLICE_STATE_CROP_MASK
        self.slice = slice
        self.config = CropMaskConfig()

    def set_limits(self, xi, xf, yi, yf, zi, zf):
        """Set crop limits (inclusive) in voxel coordinates."""
        self.config.limits = (xi, xf, yi, yf, zi, zf)

    def crop(self):
        """Perform the crop operation on the current mask using the set limits."""
        if self.config.limits is None:
            raise ValueError("Crop limits not set. Use set_limits() before crop().")

        xi, xf, yi, yf, zi, zf = self.config.limits

        # Adjust for 1-based indexing if needed (as in original code)
        xi += 1
        xf += 1
        yi += 1
        yf += 1
        zi += 1
        zf += 1

        self.slice.do_threshold_to_all_slices()
        cp_mask = self.slice.current_mask.matrix.copy()

        # Crop and assign
        tmp_mask = self.slice.current_mask.matrix[
            zi - 1 : zf + 1, yi - 1 : yf + 1, xi - 1 : xf + 1
        ].copy()

        print("DEBUG: mask matrix type:", type(self.slice.current_mask.matrix))
        print("DEBUG: mask matrix shape:", getattr(self.slice.current_mask.matrix, "shape", None))
        print("DEBUG: mask matrix dtype:", getattr(self.slice.current_mask.matrix, "dtype", None))
        self.slice.current_mask.matrix[:] = 1
        self.slice.current_mask.matrix[
            zi - 1 : zf + 1, yi - 1 : yf + 1, xi - 1 : xf + 1
        ] = tmp_mask

        self.slice.current_mask.save_history(
            0, "VOLUME", self.slice.current_mask.matrix.copy(), cp_mask
        )

        # Discard cached masks and VTK masks for all orientations
        for orient in ["AXIAL", "CORONAL", "SAGITAL"]:
            self.slice.buffer_slices[orient].discard_mask()
            self.slice.buffer_slices[orient].discard_vtk_mask()

        self.slice.current_mask.was_edited = True
        self.slice.current_mask.modified(True)
        Publisher.sendMessage("Reload actual slice")
