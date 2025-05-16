from invesalius import utils
from invesalius.data.slice_ import Slice
from invesalius.data.mask import Mask
from scipy.ndimage import generate_binary_structure
import numpy as np
from invesalius.project import Project  # Import the Project class
from invesalius_cy import floodfill
from invesalius.pubsub import pub as Publisher
from invesalius import constants as const
from vtk import vtkWorldPointPicker

CON3D = {6: 1, 18: 2, 26: 3}


class SelectPartConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.mask = None
        self.con_3d = 6
        self.dlg_visible = False
        self.mask_name = ""


class SelectMaskParts():
    def __init__(self, slice):
        

        self.state_code = const.SLICE_STATE_SELECT_MASK_PARTS


        self.picker = vtkWorldPointPicker()
        self.slice = slice

        self.config = SelectPartConfig()
        self.dlg = None

        # InVesalius uses the following values to mark selected parts in a
        # mask:
        # 255 - Threshold
        # 254 - Manual edition and  floodfill
        # 253 - Watershed
        self.t0 = 253
        self.t1 = 255
        self.fill_value = 254

        import invesalius.data.mask as mask

        default_name = const.MASK_NAME_PATTERN % (mask.Mask.general_index + 2)

        self.config.mask_name = default_name

    def CleanUp(self):
        self.config.mask.name = self.config.mask_name
        self.slice._add_mask_into_proj(self.config.mask)
        self.slice.SelectCurrentMask(self.config.mask.index)
        Publisher.sendMessage("Change mask selected", index=self.config.mask.index)


    def OnSelect(self, obj, evt, x,y,z):

        print(x, y, z)

        mask = self.slice.current_mask.matrix[1:, 1:, 1:]

        bstruct = np.array(generate_binary_structure(3, CON3D[self.config.con_3d]), dtype="uint8")
        self.slice.do_threshold_to_all_slices()

        if self.config.mask is None:
            self._create_new_mask()


        floodfill.floodfill_threshold(
            mask,
            [[x, y, z]],
            self.t0,
            self.t1,
            self.fill_value,
            bstruct,
            self.config.mask.matrix[1:, 1:, 1:],
        )

        self.slice.aux_matrices["SELECT"] = self.config.mask.matrix[1:, 1:, 1:]
        self.slice.to_show_aux = "SELECT"

        self.config.mask.was_edited = True
        Publisher.sendMessage("Reload actual slice")

    def _create_new_mask(self):
        mask = self.slice.create_new_mask(show=False, add_to_project=False)
        mask.was_edited = True
        mask.matrix[0, :, :] = 1
        mask.matrix[:, 0, :] = 1
        mask.matrix[:, :, 0] = 1

        self.config.mask = mask
