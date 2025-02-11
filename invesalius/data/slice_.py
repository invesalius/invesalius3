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
import os
import tempfile
from typing import TYPE_CHECKING, Optional, Tuple, Union

import numpy as np
from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkImagingColor import vtkImageMapToWindowLevelColors
from vtkmodules.vtkImagingCore import (
    vtkImageBlend,
    vtkImageCast,
    vtkImageFlip,
    vtkImageMapToColors,
)
from vtkmodules.vtkRenderingCore import (
    vtkColorTransferFunction,
    vtkWindowLevelLookupTable,
)

import invesalius.constants as const
import invesalius.data.converters as converters
import invesalius.data.imagedata_utils as iu
import invesalius.session as ses
import invesalius.style as st
import invesalius.utils as utils
from invesalius.data import transformations
from invesalius.data.mask import Mask
from invesalius.i18n import tr as _
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher
from invesalius_cy import mips, transforms

if TYPE_CHECKING:
    from vtkmodules.vtkCommonDataModel import vtkImageData

OTHER = 0
PLIST = 1
WIDGET = 2


class SliceBuffer:
    """
    This class is used as buffer that mantains the vtkImageData and numpy array
    from actual slices from each orientation.
    """

    def __init__(self):
        self.index: int = -1
        self.image: Optional[np.ndarray] = None
        self.mask: Optional[np.ndarray] = None
        self.vtk_image: Optional[vtkImageData] = None
        self.vtk_mask: Optional[vtkImageData] = None

    def discard_vtk_mask(self) -> None:
        self.vtk_mask = None

    def discard_vtk_image(self) -> None:
        self.vtk_image = None

    def discard_mask(self) -> None:
        self.mask = None

    def discard_image(self) -> None:
        self.image = None

    def discard_buffer(self) -> None:
        self.index = -1
        self.image = None
        self.mask = None
        self.vtk_image = None
        self.vtk_mask = None


# Only one slice will be initialized per time (despite several viewers
# show it from distinct perspectives).
# Therefore, we use Singleton design pattern for implementing it.
class Slice(metaclass=utils.Singleton):
    def __init__(self):
        self.current_mask: Optional[Mask] = None
        self.blend_filter = None
        self.histogram: Optional[np.ndarray] = None
        self._matrix: Optional[np.ndarray] = None
        self._affine: np.ndarray = np.identity(4)
        self._n_tracts: int = 0
        self._tracker = None
        self.aux_matrices: dict[str, np.ndarray] = {}
        self.aux_matrices_colours: dict[
            str, dict[Union[int, float], Tuple[float, float, float]]
        ] = {}
        self.state = const.STATE_DEFAULT

        self.to_show_aux = ""

        self._type_projection = const.PROJECTION_NORMAL
        self.n_border = const.PROJECTION_BORDER_SIZE

        self.interp_method = 2

        self._spacing = (1.0, 1.0, 1.0)
        self.center = [0, 0, 0]

        self.q_orientation = np.array((1, 0, 0, 0))

        self.number_of_colours = 256
        self.saturation_range = (0, 0)
        self.hue_range = (0, 0)
        self.value_range = (0, 1)

        self.buffer_slices = {
            "AXIAL": SliceBuffer(),
            "CORONAL": SliceBuffer(),
            "SAGITAL": SliceBuffer(),
        }

        self.num_gradient = 0
        self.interaction_style = st.StyleStateManager()

        self.values = None
        self.nodes = None

        self.from_ = OTHER
        self.__bind_events()
        self.opacity: float = 0.8

    @property
    def matrix(self) -> Optional[np.ndarray]:
        return self._matrix

    @matrix.setter
    def matrix(self, value: np.ndarray) -> None:
        self._matrix = value
        i, e = value.min(), value.max()
        r = int(e) - int(i)
        self.histogram = np.histogram(self._matrix, r, (i, e))[0]
        self.center = [(s * d / 2.0) for (d, s) in zip(self.matrix.shape[::-1], self.spacing)]

    @property
    def spacing(self) -> Tuple[float, float, float]:
        return self._spacing

    @spacing.setter
    def spacing(self, value: Tuple[float, float, float]) -> None:
        self._spacing = value
        self.center = [(s * d / 2.0) for (d, s) in zip(self.matrix.shape[::-1], self.spacing)]

    @property
    def affine(self) -> np.ndarray:
        return self._affine

    @affine.setter
    def affine(self, value: np.ndarray) -> None:
        self._affine = value

    @property
    def n_tracts(self) -> int:
        return self._n_tracts

    @n_tracts.setter
    def n_tracts(self, value: int) -> None:
        self._n_tracts = value

    @property
    def tracker(self):
        return self._tracker

    @tracker.setter
    def tracker(self, value):
        self._tracker = value

    def __bind_events(self) -> None:
        # General slice control
        Publisher.subscribe(self.CreateSurfaceFromIndex, "Create surface from index")
        # Mask control
        Publisher.subscribe(self.__add_mask_thresh, "Create new mask")
        Publisher.subscribe(self.__select_current_mask, "Change mask selected")
        # Mask properties
        Publisher.subscribe(
            self.__set_current_mask_edition_threshold, "Set edition threshold values"
        )
        Publisher.subscribe(self.__set_current_mask_threshold, "Set threshold values")
        Publisher.subscribe(
            self.__set_current_mask_threshold_actual_slice, "Changing threshold values"
        )
        Publisher.subscribe(self.__set_current_mask_colour, "Change mask colour")
        Publisher.subscribe(self.__set_mask_name, "Change mask name")
        Publisher.subscribe(self.__show_mask, "Show mask")
        Publisher.subscribe(self.__hide_current_mask, "Hide current mask")
        Publisher.subscribe(self.__show_current_mask, "Show current mask")
        Publisher.subscribe(self.__clean_current_mask, "Clean current mask")

        Publisher.subscribe(self.__export_slice, "Export slice")
        Publisher.subscribe(self.__export_actual_mask, "Export actual mask")

        Publisher.subscribe(self.__set_current_mask_threshold_limits, "Update threshold limits")

        Publisher.subscribe(
            self.UpdateWindowLevelBackground, "Bright and contrast adjustment image"
        )

        Publisher.subscribe(
            self.UpdateColourTableBackground,
            "Change colour table from background image",
        )

        Publisher.subscribe(
            self.UpdateColourTableBackgroundPlist,
            "Change colour table from background image from plist",
        )

        Publisher.subscribe(
            self.UpdateColourTableBackgroundWidget,
            "Change colour table from background image from widget",
        )

        Publisher.subscribe(self._set_projection_type, "Set projection type")

        Publisher.subscribe(self._do_boolean_op, "Do boolean operation")

        Publisher.subscribe(self.OnExportMask, "Export mask to file")

        Publisher.subscribe(self.OnCloseProject, "Close project data")

        Publisher.subscribe(self.OnEnableStyle, "Enable style")
        Publisher.subscribe(self.OnDisableStyle, "Disable style")
        Publisher.subscribe(self.OnDisableActualStyle, "Disable actual style")

        Publisher.subscribe(self.OnRemoveMasks, "Remove masks")
        Publisher.subscribe(self.OnDuplicateMasks, "Duplicate masks")
        Publisher.subscribe(self.UpdateSlice3D, "Update slice 3D")

        Publisher.subscribe(self.OnFlipVolume, "Flip volume")
        Publisher.subscribe(self.OnSwapVolumeAxes, "Swap volume axes")

        Publisher.subscribe(self.__undo_edition, "Undo edition")
        Publisher.subscribe(self.__redo_edition, "Redo edition")

        Publisher.subscribe(self._fill_holes_auto, "Fill holes automatically")

        Publisher.subscribe(self._set_interpolation_method, "Set interpolation method")
        Publisher.subscribe(self.do_threshold_to_all_slices, "Appy threshold all slices")

    def GetMaxSliceNumber(self, orientation: str) -> int:
        shape: Tuple[int, int, int] = self.matrix.shape

        # Because matrix indexing starts with 0 so the last slice is the shape
        # minu 1.
        if orientation == "AXIAL":
            return shape[0] - 1
        elif orientation == "CORONAL":
            return shape[1] - 1
        elif orientation == "SAGITAL":
            return shape[2] - 1
        raise ValueError(f"Invalid orientation: {orientation}")

    def discard_all_buffers(self) -> None:
        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_mask()
            buffer_.discard_mask()

    def OnRemoveMasks(self, mask_indexes):
        proj = Project()
        for item in mask_indexes:
            # if the deleted mask is the current mask, cleans the current mask
            # and discard from buffer all datas related to mask.
            if self.current_mask is not None and item == self.current_mask.index:
                self.current_mask = None

                for buffer_ in self.buffer_slices.values():
                    buffer_.discard_vtk_mask()
                    buffer_.discard_mask()

                Publisher.sendMessage("Show mask", index=item, value=False)
                Publisher.sendMessage("Reload actual slice")
            proj.RemoveMask(item)

    def OnDuplicateMasks(self, mask_indexes):
        proj = Project()
        mask_dict = proj.mask_dict
        for index in mask_indexes:
            original_mask = mask_dict[index]
            # compute copy name
            name = original_mask.name
            names_list = [mask_dict[i].name for i in mask_dict.keys()]
            new_name = utils.next_copy_name(name, names_list)

            copy_mask = original_mask.copy(new_name)
            self._add_mask_into_proj(copy_mask)

    def OnEnableStyle(self, style):
        if style in const.SLICE_STYLES:
            new_state = self.interaction_style.AddState(style)
            Publisher.sendMessage("Set slice interaction style", style=new_state)
        self.state = style

    def OnDisableStyle(self, style):
        if style in const.SLICE_STYLES:
            new_state = self.interaction_style.RemoveState(style)
            Publisher.sendMessage("Set slice interaction style", style=new_state)

            if style == const.SLICE_STATE_EDITOR:
                Publisher.sendMessage("Set interactor default cursor")
            self.state = new_state

    def OnDisableActualStyle(self):
        actual_state = self.interaction_style.GetActualState()
        if actual_state != const.STATE_DEFAULT:
            new_state = self.interaction_style.RemoveState(actual_state)
            Publisher.sendMessage("Set slice interaction style", style=new_state)

            #  if (actual_state == const.SLICE_STATE_EDITOR):
            #  Publisher.sendMessage('Set interactor default cursor')
            self.state = new_state

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        f = self._matrix.filename
        self._matrix._mmap.close()
        self._matrix = None
        os.remove(f)
        self.current_mask = None

        for name in self.aux_matrices:
            m = self.aux_matrices[name]
            try:
                f = m.filename
            except AttributeError:
                continue
            m._mmap.close()
            m = None
            os.remove(f)
        self.aux_matrices = {}

        self.values = None
        self.nodes = None
        self.from_ = OTHER
        self.state = const.STATE_DEFAULT

        self.number_of_colours = 256
        self.saturation_range = (0, 0)
        self.hue_range = (0, 0)
        self.value_range = (0, 1)

        self.interaction_style.Reset()
        self.to_show_aux = ""

        Publisher.sendMessage("Select first item from slice menu")

    def __set_current_mask_threshold_limits(self, threshold_range):
        thresh_min = threshold_range[0]
        thresh_max = threshold_range[1]
        if self.current_mask:
            index = self.current_mask.index
            self.SetMaskEditionThreshold(index, (thresh_min, thresh_max))

    def __add_mask(self, mask_name):
        self.create_new_mask(name=mask_name)
        self.SetMaskColour(self.current_mask.index, self.current_mask.colour)

    def __add_mask_thresh(self, mask_name, thresh, colour):
        self.create_new_mask(name=mask_name, threshold_range=thresh, colour=colour)
        self.SetMaskColour(self.current_mask.index, self.current_mask.colour)
        self.SelectCurrentMask(self.current_mask.index)
        Publisher.sendMessage("Reload actual slice")

    def __select_current_mask(self, index):
        self.SelectCurrentMask(index)

    def __set_current_mask_edition_threshold(self, threshold_range):
        if self.current_mask:
            index = self.current_mask.index
            self.SetMaskEditionThreshold(index, threshold_range)

    def __set_current_mask_threshold(self, threshold_range):
        if self.current_mask is None:
            return
        proj = Project()
        index = proj.mask_dict.get_key(self.current_mask)
        self.num_gradient += 1
        self.current_mask.matrix[:] = 0
        self.current_mask.clear_history()

        if self.current_mask.auto_update_mask and self.current_mask.volume is not None:
            to_reload = True
            self.SetMaskThreshold(index, threshold_range, slice_number=None, orientation=None)
            self.discard_all_buffers()
            Publisher.sendMessage("Reload actual slice")
            self.current_mask.modified(all_volume=True)
            return

        to_reload = False
        if threshold_range != self.current_mask.threshold_range:
            for orientation in self.buffer_slices:
                self.buffer_slices[orientation].discard_vtk_mask()
                self.SetMaskThreshold(
                    index,
                    threshold_range,
                    self.buffer_slices[orientation].index,
                    orientation,
                )

        # TODO: merge this code with apply_slice_buffer_to_mask
        b_mask = self.buffer_slices["AXIAL"].mask
        if b_mask is not None:
            n = self.buffer_slices["AXIAL"].index + 1
            self.current_mask.matrix[n, 1:, 1:] = b_mask
            self.current_mask.matrix[n, 0, 0] = 1

        b_mask = self.buffer_slices["CORONAL"].mask
        if b_mask is not None:
            n = self.buffer_slices["CORONAL"].index + 1
            self.current_mask.matrix[1:, n, 1:] = b_mask
            self.current_mask.matrix[0, n, 0] = 1

        b_mask = self.buffer_slices["SAGITAL"].mask
        if b_mask is not None:
            n = self.buffer_slices["SAGITAL"].index + 1
            self.current_mask.matrix[1:, 1:, n] = b_mask
            self.current_mask.matrix[0, 0, n] = 1

        if to_reload:
            Publisher.sendMessage("Reload actual slice")
        self.current_mask.modified(all_volume=False)

    def __set_current_mask_threshold_actual_slice(self, threshold_range):
        if self.current_mask is None:
            return
        proj = Project()
        index = proj.mask_dict.get_key(self.current_mask)
        for orientation in self.buffer_slices:
            self.buffer_slices[orientation].discard_vtk_mask()
            self.SetMaskThreshold(
                index,
                threshold_range,
                self.buffer_slices[orientation].index,
                orientation,
            )
        self.num_gradient += 1

        Publisher.sendMessage("Reload actual slice")

    def __set_current_mask_colour(self, colour):
        # "if" is necessary because wx events are calling this before any mask
        # has been created
        if self.current_mask:
            colour_vtk = [c / 255.0 for c in colour]
            self.SetMaskColour(self.current_mask.index, colour_vtk)

    def __set_mask_name(self, index, name):
        self.SetMaskName(index, name)

    def __show_mask(self, index, value):
        # "if" is necessary because wx events are calling this before any mask
        # has been created
        if self.current_mask:
            self.ShowMask(index, value)
            if not value:
                Publisher.sendMessage("Select mask name in combo", index=-1)

            if self._type_projection != const.PROJECTION_NORMAL:
                self.SetTypeProjection(const.PROJECTION_NORMAL)
                Publisher.sendMessage("Reload actual slice")

    def __hide_current_mask(self):
        if self.current_mask:
            index = self.current_mask.index
            value = False
            Publisher.sendMessage("Show mask", index=index, value=value)

    def __show_current_mask(self):
        if self.current_mask:
            index = self.current_mask.index
            value = True
            Publisher.sendMessage("Show mask", index=index, value=value)

    def __clean_current_mask(self):
        if self.current_mask:
            self.current_mask.clean()
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_vtk_mask()
                buffer_.discard_mask()
            self.current_mask.clear_history()
            self.current_mask.was_edited = True

            # Marking the project as changed
            session = ses.Session()
            session.ChangeProject()

    def __export_slice(self, filename):
        import h5py

        f = h5py.File(filename, "w")
        f["data"] = self.matrix
        f["spacing"] = self.spacing
        f.flush()
        f.close()

    def __export_actual_mask(self, filename):
        import h5py

        f = h5py.File(filename, "w")
        self.do_threshold_to_all_slices()
        f["data"] = self.current_mask.matrix[1:, 1:, 1:]
        f["spacing"] = self.spacing
        f.flush()
        f.close()

    def create_temp_mask(self):
        temp_fd, temp_file = tempfile.mkstemp()
        shape = self.matrix.shape
        matrix = np.memmap(temp_file, mode="w+", dtype="uint8", shape=shape)
        os.close(temp_fd)
        return temp_file, matrix

    def edit_mask_pixel(self, operation, index, position, radius, orientation):
        mask = self.buffer_slices[orientation].mask
        image = self.buffer_slices[orientation].image
        thresh_min, thresh_max = self.current_mask.edition_threshold_range

        if hasattr(position, "__iter__"):
            px, py = position
            if orientation == "AXIAL":
                sx = self.spacing[0]
                sy = self.spacing[1]
            elif orientation == "CORONAL":
                sx = self.spacing[0]
                sy = self.spacing[2]
            elif orientation == "SAGITAL":
                sx = self.spacing[2]
                sy = self.spacing[1]

        else:
            if orientation == "AXIAL":
                sx = self.spacing[0]
                sy = self.spacing[1]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == "CORONAL":
                sx = self.spacing[0]
                sy = self.spacing[2]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == "SAGITAL":
                sx = self.spacing[2]  # noqa: F841
                sy = self.spacing[1]  # noqa: F841
                py = position / mask.shape[1]
                px = position % mask.shape[1]

        cx = index.shape[1] / 2 + 1
        cy = index.shape[0] / 2 + 1
        xi = int(px - index.shape[1] + cx)
        xf = int(xi + index.shape[1])
        yi = int(py - index.shape[0] + cy)
        yf = int(yi + index.shape[0])

        if yi < 0:
            index = index[abs(yi) :, :]
            yi = 0
        if yf > image.shape[0]:
            index = index[: index.shape[0] - (yf - image.shape[0]), :]
            yf = image.shape[0]

        if xi < 0:
            index = index[:, abs(xi) :]
            xi = 0
        if xf > image.shape[1]:
            index = index[:, : index.shape[1] - (xf - image.shape[1])]
            xf = image.shape[1]

        # Verifying if the points is over the image array.
        if (not 0 <= xi <= image.shape[1] and not 0 <= xf <= image.shape[1]) or (
            not 0 <= yi <= image.shape[0] and not 0 <= yf <= image.shape[0]
        ):
            return

        roi_m = mask[yi:yf, xi:xf]
        roi_i = image[yi:yf, xi:xf]

        # Checking if roi_i has at least one element.
        if roi_i.size:
            if operation == const.BRUSH_THRESH:
                # It's a trick to make points between threshold gets value 254
                # (1 * 253 + 1) and out ones gets value 1 (0 * 253 + 1).
                roi_m[index] = (
                    ((roi_i[index] >= thresh_min) & (roi_i[index] <= thresh_max)) * 253
                ) + 1
            elif operation == const.BRUSH_THRESH_ERASE:
                roi_m[index] = (
                    ((roi_i[index] < thresh_min) | (roi_i[index] > thresh_max)) * 253
                ) + 1
            elif operation == const.BRUSH_THRESH_ADD_ONLY:
                roi_m[((index) & (roi_i >= thresh_min) & (roi_i <= thresh_max))] = 254
            elif operation == const.BRUSH_THRESH_ERASE_ONLY:
                roi_m[((index) & ((roi_i < thresh_min) | (roi_i > thresh_max)))] = 1
            elif operation == const.BRUSH_DRAW:
                roi_m[index] = 254
            elif operation == const.BRUSH_ERASE:
                roi_m[index] = 1
            self.buffer_slices[orientation].discard_vtk_mask()

        # Marking the project as changed
        session = ses.Session()
        session.ChangeProject()

    def GetSlices(self, orientation, slice_number, number_slices, inverted=False, border_size=1.0):
        if (
            self.buffer_slices[orientation].index == slice_number
            and self._type_projection == const.PROJECTION_NORMAL
        ):
            if self.buffer_slices[orientation].vtk_image:
                image = self.buffer_slices[orientation].vtk_image
            else:
                n_image = self.get_image_slice(
                    orientation, slice_number, number_slices, inverted, border_size
                )
                image = converters.to_vtk(n_image, self.spacing, slice_number, orientation)
                ww_wl_image = self.do_ww_wl(image)
                image = self.do_colour_image(ww_wl_image)
            if self.current_mask and self.current_mask.is_shown:
                if self.buffer_slices[orientation].vtk_mask:
                    # Prints that during navigation causes delay in update
                    # print "Getting from buffer"
                    mask = self.buffer_slices[orientation].vtk_mask
                else:
                    # Prints that during navigation causes delay in update
                    # print "Do not getting from buffer"
                    n_mask = self.get_mask_slice(orientation, slice_number)
                    mask = converters.to_vtk(n_mask, self.spacing, slice_number, orientation)
                    mask = self.do_colour_mask(mask, self.opacity)
                    self.buffer_slices[orientation].mask = n_mask
                final_image = self.do_blend(image, mask)
                self.buffer_slices[orientation].vtk_mask = mask
            else:
                final_image = image
            self.buffer_slices[orientation].vtk_image = image
        else:
            n_image = self.get_image_slice(
                orientation, slice_number, number_slices, inverted, border_size
            )
            image = converters.to_vtk(n_image, self.spacing, slice_number, orientation)
            ww_wl_image = self.do_ww_wl(image)
            image = self.do_colour_image(ww_wl_image)

            if self.current_mask and self.current_mask.is_shown:
                n_mask = self.get_mask_slice(orientation, slice_number)
                mask = converters.to_vtk(n_mask, self.spacing, slice_number, orientation)
                mask = self.do_colour_mask(mask, self.opacity)
                final_image = self.do_blend(image, mask)
            else:
                n_mask = None
                final_image = image
                mask = None

            self.buffer_slices[orientation].index = slice_number
            self.buffer_slices[orientation].mask = n_mask
            self.buffer_slices[orientation].vtk_image = image
            self.buffer_slices[orientation].vtk_mask = mask

        if (
            self.to_show_aux == "watershed"
            and self.current_mask is not None
            and self.current_mask.is_shown
        ):
            m = self.get_aux_slice("watershed", orientation, slice_number)
            tmp_vimage = converters.to_vtk(m, self.spacing, slice_number, orientation)
            cimage = self.do_custom_colour(
                tmp_vimage,
                {
                    0: (0.0, 0.0, 0.0, 0.0),
                    1: (0.0, 1.0, 0.0, 1.0),
                    2: (1.0, 0.0, 0.0, 1.0),
                },
            )
            final_image = self.do_blend(final_image, cimage)
        elif self.to_show_aux and self.current_mask:
            m = self.get_aux_slice(self.to_show_aux, orientation, slice_number)
            tmp_vimage = converters.to_vtk(m, self.spacing, slice_number, orientation)
            try:
                colour_table = self.aux_matrices_colours[self.to_show_aux]
            except KeyError:
                colour_table = {
                    0: (0.0, 0.0, 0.0, 0.0),
                    1: (0.0, 0.0, 0.0, 0.0),
                    254: (1.0, 0.0, 0.0, 1.0),
                    255: (1.0, 0.0, 0.0, 1.0),
                }
            aux_image = self.do_custom_colour(tmp_vimage, colour_table)
            final_image = self.do_blend(final_image, aux_image)
        return final_image

    def get_image_slice(
        self,
        orientation,
        slice_number,
        number_slices=1,
        inverted=False,
        border_size=1.0,
    ):
        dz, dy, dx = self.matrix.shape
        if (
            self.buffer_slices[orientation].index == slice_number
            and self.buffer_slices[orientation].image is not None
        ):
            n_image = self.buffer_slices[orientation].image
        else:
            if self._type_projection == const.PROJECTION_NORMAL:
                number_slices = 1

            if np.any(self.q_orientation[1::]):
                cx, cy, cz = self.center
                T0 = transformations.translation_matrix((-cz, -cy, -cx))
                #  Rx = transformations.rotation_matrix(rx, (0, 0, 1))
                #  Ry = transformations.rotation_matrix(ry, (0, 1, 0))
                #  Rz = transformations.rotation_matrix(rz, (1, 0, 0))
                #  #  R = transformations.euler_matrix(rz, ry, rx, 'rzyx')
                #  R = transformations.concatenate_matrices(Rx, Ry, Rz)
                R = transformations.quaternion_matrix(self.q_orientation)
                T1 = transformations.translation_matrix((cz, cy, cx))
                M = transformations.concatenate_matrices(T1, R.T, T0)

            if orientation == "AXIAL":
                tmp_array = np.array(self.matrix[slice_number : slice_number + number_slices])
                if np.any(self.q_orientation[1::]):
                    transforms.apply_view_matrix_transform(
                        self.matrix,
                        self.spacing,
                        M,
                        slice_number,
                        orientation,
                        self.interp_method,
                        self.matrix.min(),
                        tmp_array,
                    )
                if self._type_projection == const.PROJECTION_NORMAL:
                    n_image = tmp_array.reshape(dy, dx)
                else:
                    if inverted:
                        tmp_array = tmp_array[::-1]

                    if self._type_projection == const.PROJECTION_MaxIP:
                        n_image = np.array(tmp_array).max(0)
                    elif self._type_projection == const.PROJECTION_MinIP:
                        n_image = np.array(tmp_array).min(0)
                    elif self._type_projection == const.PROJECTION_MeanIP:
                        n_image = np.array(tmp_array).mean(0)
                    elif self._type_projection == const.PROJECTION_LMIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[1], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.lmip(tmp_array, 0, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_MIDA:
                        n_image = np.empty(
                            shape=(tmp_array.shape[1], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.mida(tmp_array, 0, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[1], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            0,
                            self.window_level,
                            self.window_level,
                            0,
                            n_image,
                        )
                    elif self._type_projection == const.PROJECTION_CONTOUR_LMIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[1], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            0,
                            self.window_level,
                            self.window_level,
                            1,
                            n_image,
                        )
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIDA:
                        n_image = np.empty(
                            shape=(tmp_array.shape[1], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            0,
                            self.window_level,
                            self.window_level,
                            2,
                            n_image,
                        )
                    else:
                        n_image = np.array(self.matrix[slice_number])

            elif orientation == "CORONAL":
                tmp_array = np.array(self.matrix[:, slice_number : slice_number + number_slices, :])
                if np.any(self.q_orientation[1::]):
                    transforms.apply_view_matrix_transform(
                        self.matrix,
                        self.spacing,
                        M,
                        slice_number,
                        orientation,
                        self.interp_method,
                        self.matrix.min(),
                        tmp_array,
                    )

                if self._type_projection == const.PROJECTION_NORMAL:
                    n_image = tmp_array.reshape(dz, dx)
                else:
                    # if slice_number == 0:
                    # slice_number = 1
                    # if slice_number - number_slices < 0:
                    # number_slices = slice_number
                    if inverted:
                        tmp_array = tmp_array[:, ::-1, :]
                    if self._type_projection == const.PROJECTION_MaxIP:
                        n_image = np.array(tmp_array).max(1)
                    elif self._type_projection == const.PROJECTION_MinIP:
                        n_image = np.array(tmp_array).min(1)
                    elif self._type_projection == const.PROJECTION_MeanIP:
                        n_image = np.array(tmp_array).mean(1)
                    elif self._type_projection == const.PROJECTION_LMIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.lmip(tmp_array, 1, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_MIDA:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.mida(tmp_array, 1, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            1,
                            self.window_level,
                            self.window_level,
                            0,
                            n_image,
                        )
                    elif self._type_projection == const.PROJECTION_CONTOUR_LMIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            1,
                            self.window_level,
                            self.window_level,
                            1,
                            n_image,
                        )
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIDA:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[2]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            1,
                            self.window_level,
                            self.window_level,
                            2,
                            n_image,
                        )
                    else:
                        n_image = np.array(self.matrix[:, slice_number, :])
            elif orientation == "SAGITAL":
                tmp_array = np.array(self.matrix[:, :, slice_number : slice_number + number_slices])
                if np.any(self.q_orientation[1::]):
                    transforms.apply_view_matrix_transform(
                        self.matrix,
                        self.spacing,
                        M,
                        slice_number,
                        orientation,
                        self.interp_method,
                        self.matrix.min(),
                        tmp_array,
                    )

                if self._type_projection == const.PROJECTION_NORMAL:
                    n_image = tmp_array.reshape(dz, dy)
                else:
                    if inverted:
                        tmp_array = tmp_array[:, :, ::-1]
                    if self._type_projection == const.PROJECTION_MaxIP:
                        n_image = np.array(tmp_array).max(2)
                    elif self._type_projection == const.PROJECTION_MinIP:
                        n_image = np.array(tmp_array).min(2)
                    elif self._type_projection == const.PROJECTION_MeanIP:
                        n_image = np.array(tmp_array).mean(2)
                    elif self._type_projection == const.PROJECTION_LMIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[1]),
                            dtype=tmp_array.dtype,
                        )
                        mips.lmip(tmp_array, 2, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_MIDA:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[1]),
                            dtype=tmp_array.dtype,
                        )
                        mips.mida(tmp_array, 2, self.window_level, self.window_level, n_image)

                    elif self._type_projection == const.PROJECTION_CONTOUR_MIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[1]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            2,
                            self.window_level,
                            self.window_level,
                            0,
                            n_image,
                        )
                    elif self._type_projection == const.PROJECTION_CONTOUR_LMIP:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[1]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            2,
                            self.window_level,
                            self.window_level,
                            1,
                            n_image,
                        )
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIDA:
                        n_image = np.empty(
                            shape=(tmp_array.shape[0], tmp_array.shape[1]),
                            dtype=tmp_array.dtype,
                        )
                        mips.fast_countour_mip(
                            tmp_array,
                            border_size,
                            2,
                            self.window_level,
                            self.window_level,
                            2,
                            n_image,
                        )
                    else:
                        n_image = np.array(self.matrix[:, :, slice_number])

            self.buffer_slices[orientation].image = n_image
        return n_image

    def get_mask_slice(self, orientation, slice_number):
        """
        It gets the from actual mask the given slice from given orientation
        """
        # It's necessary because the first position for each dimension from
        # mask matrix is used as flags to control if the mask in the
        # slice_number position has been generated.
        if (
            self.buffer_slices[orientation].index == slice_number
            and self.buffer_slices[orientation].mask is not None
        ):
            return self.buffer_slices[orientation].mask
        n = slice_number + 1
        if orientation == "AXIAL":
            if self.current_mask.matrix[n, 0, 0] == 0:
                mask = self.current_mask.matrix[n, 1:, 1:]
                mask[:] = self.do_threshold_to_a_slice(
                    self.get_image_slice(orientation, slice_number), mask
                )
                self.current_mask.matrix[n, 0, 0] = 1
            n_mask = np.array(
                self.current_mask.matrix[n, 1:, 1:],
                dtype=self.current_mask.matrix.dtype,
            )

        elif orientation == "CORONAL":
            if self.current_mask.matrix[0, n, 0] == 0:
                mask = self.current_mask.matrix[1:, n, 1:]
                mask[:] = self.do_threshold_to_a_slice(
                    self.get_image_slice(orientation, slice_number), mask
                )
                self.current_mask.matrix[0, n, 0] = 1
            n_mask = np.array(
                self.current_mask.matrix[1:, n, 1:],
                dtype=self.current_mask.matrix.dtype,
            )

        elif orientation == "SAGITAL":
            if self.current_mask.matrix[0, 0, n] == 0:
                mask = self.current_mask.matrix[1:, 1:, n]
                mask[:] = self.do_threshold_to_a_slice(
                    self.get_image_slice(orientation, slice_number), mask
                )
                self.current_mask.matrix[0, 0, n] = 1
            n_mask = np.array(
                self.current_mask.matrix[1:, 1:, n],
                dtype=self.current_mask.matrix.dtype,
            )

        return n_mask

    def get_aux_slice(self, name, orientation, n):
        m = self.aux_matrices[name]
        if orientation == "AXIAL":
            return np.array(m[n])
        elif orientation == "CORONAL":
            return np.array(m[:, n, :])
        elif orientation == "SAGITAL":
            return np.array(m[:, :, n])

    def GetNumberOfSlices(self, orientation):
        if orientation == "AXIAL":
            return self.matrix.shape[0]
        elif orientation == "CORONAL":
            return self.matrix.shape[1]
        elif orientation == "SAGITAL":
            return self.matrix.shape[2]

    def SetMaskColour(self, index, colour, update=True):
        "Set a mask colour given its index and colour (RGB 0-1 values)"
        proj = Project()
        proj.mask_dict[index].set_colour(colour)
        colour_wx = [int(value * 255) for value in colour]

        Publisher.sendMessage("Change mask colour in notebook", index=index, colour=colour[:3])
        Publisher.sendMessage("Set GUI items colour", colour=colour_wx)
        if update:
            # Updating mask colour on vtkimagedata.
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_vtk_mask()

            Publisher.sendMessage("Reload actual slice")

        session = ses.Session()
        session.ChangeProject()

    def SetMaskName(self, index, name):
        "Rename a mask given its index and the new name"
        proj = Project()
        proj.mask_dict[index].name = name

        session = ses.Session()
        session.ChangeProject()

    def SetMaskEditionThreshold(self, index, threshold_range):
        "Set threshold bounds to be used while editing slice"
        proj = Project()
        proj.mask_dict[index].edition_threshold_range = threshold_range

    def SetMaskThreshold(self, index, threshold_range, slice_number=None, orientation=None):
        """
        Set a mask threshold range given its index and tuple of min and max
        threshold values.

        If slice_number is None then all the threshold is calculated for all
        slices, otherwise only to indicated slice.
        """
        thresh_min, thresh_max = threshold_range

        proj = Project()
        if proj.mask_dict[index] == self.current_mask:
            self.current_mask.was_edited = False
            # TODO: find out a better way to do threshold
            if slice_number is None:
                for n, slice_ in enumerate(self.matrix):
                    print(n)
                    m = np.ones(slice_.shape, self.current_mask.matrix.dtype)
                    m[slice_ < thresh_min] = 0
                    m[slice_ > thresh_max] = 0
                    m[m == 1] = 255
                    self.current_mask.matrix[n + 1, 1:, 1:] = m
            else:
                slice_ = self.buffer_slices[orientation].image
                if slice_ is not None:
                    self.buffer_slices[orientation].mask = (
                        255 * ((slice_ >= thresh_min) & (slice_ <= thresh_max))
                    ).astype("uint8")

            # Update viewer
            # Publisher.sendMessage('Update slice viewer')

            # Update data notebook (GUI)
            Publisher.sendMessage(
                "Set mask threshold in notebook",
                index=index,
                threshold_range=self.current_mask.threshold_range,
            )
        proj.mask_dict[index].threshold_range = threshold_range

    def ShowMask(self, index, value):
        "Show a mask given its index and 'show' value (0: hide, other: show)"
        proj = Project()
        mask = proj.mask_dict[index]
        mask.is_shown = value
        mask.on_show()

        if value:
            threshold_range = mask.threshold_range
            edition_threshold_range = mask.edition_threshold_range
            Publisher.sendMessage(
                "Set edition threshold gui", threshold_range=edition_threshold_range
            )
            Publisher.sendMessage(
                "Set threshold values in gradient", threshold_range=threshold_range
            )

        if mask.index == self.current_mask.index:
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_vtk_mask()
                buffer_.discard_mask()
            Publisher.sendMessage("Reload actual slice")

    # ---------------------------------------------------------------------------

    def SelectCurrentMask(self, index):
        "Insert mask data, based on given index, into pipeline."
        if self.current_mask:
            self.current_mask.is_shown = False
            self.current_mask.on_show()

        proj = Project()
        future_mask = proj.GetMask(index)
        future_mask.is_shown = True
        self.current_mask = future_mask
        # Update the current mask index because is some edge cases
        # it will be incorrect after self.current_mask = future_mask
        self.current_mask.index = index
        self.current_mask.on_show()

        colour = future_mask.colour
        self.SetMaskColour(index, colour, update=False)

        self.buffer_slices = {
            "AXIAL": SliceBuffer(),
            "CORONAL": SliceBuffer(),
            "SAGITAL": SliceBuffer(),
        }

        Publisher.sendMessage(
            "Set mask threshold in notebook",
            index=index,
            threshold_range=self.current_mask.threshold_range,
        )
        Publisher.sendMessage(
            "Set threshold values in gradient",
            threshold_range=self.current_mask.threshold_range,
        )
        Publisher.sendMessage("Select mask name in combo", index=index)
        Publisher.sendMessage("Update slice viewer")

    # ---------------------------------------------------------------------------

    def CreateSurfaceFromIndex(self, surface_parameters):
        proj = Project()
        mask = proj.mask_dict[surface_parameters["options"]["index"]]

        self.do_threshold_to_all_slices(mask)
        Publisher.sendMessage(
            "Create surface",
            slice_=self,
            mask=mask,
            surface_parameters=surface_parameters,
        )

    def GetOutput(self):
        return self.blend_filter.GetOutput()

    def _set_projection_type(self, projection_id):
        self.SetTypeProjection(projection_id)

    def _set_interpolation_method(self, interp_method):
        self.SetInterpolationMethod(interp_method)

    def SetTypeProjection(self, tprojection):
        if self._type_projection != tprojection:
            if self._type_projection == const.PROJECTION_NORMAL:
                Publisher.sendMessage("Hide current mask")

            if tprojection == const.PROJECTION_NORMAL:
                Publisher.sendMessage("Show MIP interface", flag=False)
            else:
                Publisher.sendMessage("Show MIP interface", flag=True)

            self._type_projection = tprojection
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_buffer()

            Publisher.sendMessage("Check projection menu", projection_id=tprojection)

    def SetInterpolationMethod(self, interp_method):
        if self.interp_method != interp_method:
            self.interp_method = interp_method
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_buffer()
            Publisher.sendMessage("Reload actual slice")

    def UpdateWindowLevelBackground(self, window, level):
        self.window_width = window
        self.window_level = level

        for buffer_ in self.buffer_slices.values():
            if self._type_projection in (
                const.PROJECTION_NORMAL,
                const.PROJECTION_MaxIP,
                const.PROJECTION_MinIP,
                const.PROJECTION_MeanIP,
                const.PROJECTION_LMIP,
            ):
                buffer_.discard_vtk_image()
            else:
                buffer_.discard_buffer()

        Publisher.sendMessage("Reload actual slice")

    def UpdateColourTableBackground(self, values):
        self.from_ = OTHER
        self.number_of_colours = values[0]
        self.saturation_range = values[1]
        self.hue_range = values[2]
        self.value_range = values[3]
        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_image()
        Publisher.sendMessage("Reload actual slice")

    def UpdateColourTableBackgroundPlist(self, values):
        self.values = values
        self.from_ = PLIST
        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_image()

        Publisher.sendMessage("Reload actual slice")

    def UpdateColourTableBackgroundWidget(self, nodes):
        self.nodes = nodes
        self.from_ = WIDGET
        for buffer_ in self.buffer_slices.values():
            if self._type_projection in (
                const.PROJECTION_NORMAL,
                const.PROJECTION_MaxIP,
                const.PROJECTION_MinIP,
                const.PROJECTION_MeanIP,
                const.PROJECTION_LMIP,
            ):
                buffer_.discard_vtk_image()
            else:
                buffer_.discard_buffer()

        knodes = sorted(self.nodes)
        p0 = knodes[0].value
        pn = knodes[-1].value

        self.window_width = pn - p0
        self.window_level = (pn + p0) / 2

        Publisher.sendMessage("Reload actual slice")

    def UpdateSlice3D(self, widget, orientation):
        img = self.buffer_slices[orientation].vtk_image
        # original_orientation = Project().original_orientation
        cast = vtkImageCast()
        cast.SetInputData(img)
        cast.SetOutputScalarTypeToDouble()
        cast.ClampOverflowOn()
        cast.Update()

        # if (original_orientation == const.AXIAL):
        flip = vtkImageFlip()
        flip.SetInputConnection(cast.GetOutputPort())
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.Update()
        widget.SetInputConnection(flip.GetOutputPort())
        # else:
        # widget.SetInput(cast.GetOutput())

    def create_new_mask(
        self,
        name=None,
        colour=None,
        opacity=None,
        threshold_range=None,
        edition_threshold_range=None,
        add_to_project=True,
        show=True,
    ):
        """
        Creates a new mask and add it to project.

        Parameters:
            name (string): name of the new mask. If name is None a automatic
                name will be used.
            colour (R, G, B): a RGB tuple of float number.
            opacity (float): a float number, from 0 to 1. If opacity is None
                the default one will be used.
            threshold_range (int, int): a 2-tuple indicating threshold range.
                If None the default one will be used.
            edition_threshold_range (int, int): a 2-tuple indicating threshold
                range. If None the default one will be used.
            show (bool): if this new mask will be showed and set as current
                mask.

        Returns:
            new_mask: The new mask object.
        """
        future_mask = Mask()
        future_mask.create_mask(self.matrix.shape)
        future_mask.spacing = self.spacing

        if name:
            future_mask.name = name
        if colour:
            future_mask.colour = colour
        if opacity:
            future_mask.opacity = opacity
        if edition_threshold_range:
            future_mask.edition_threshold_range = edition_threshold_range
        if threshold_range:
            future_mask.threshold_range = threshold_range

        if add_to_project:
            self._add_mask_into_proj(future_mask, show=show)

        return future_mask

    def _add_mask_into_proj(self, mask, show=True):
        """
        Insert a new mask into project and retrieve its index.

        Params:
            mask: A mask object.
            show: indicate if the mask will be shown.
        """
        proj = Project()
        index = proj.AddMask(mask)
        mask.index = index

        ## update gui related to mask
        Publisher.sendMessage("Add mask", mask=mask)

        if show:
            if self.current_mask:
                self.current_mask.is_shown = False
            self.current_mask = mask
            Publisher.sendMessage("Show mask", index=mask.index, value=True)
            Publisher.sendMessage("Change mask selected", index=mask.index)
            Publisher.sendMessage("Update slice viewer")

    def do_ww_wl(self, image):
        if self.from_ == PLIST:
            lut = vtkWindowLevelLookupTable()
            lut.SetWindow(self.window_width)
            lut.SetLevel(self.window_level)
            lut.Build()

            i = 0
            for r, g, b in self.values:
                lut.SetTableValue(i, r / 255.0, g / 255.0, b / 255.0, 1.0)
                i += 1

            colorer = vtkImageMapToColors()
            colorer.SetInputData(image)
            colorer.SetLookupTable(lut)
            colorer.SetOutputFormatToRGB()
            colorer.Update()
        elif self.from_ == WIDGET:
            lut = vtkColorTransferFunction()

            for n in self.nodes:
                r, g, b = n.colour
                lut.AddRGBPoint(n.value, r / 255.0, g / 255.0, b / 255.0)

            lut.Build()

            colorer = vtkImageMapToColors()
            colorer.SetLookupTable(lut)
            colorer.SetInputData(image)
            colorer.SetOutputFormatToRGB()
            colorer.Update()
        else:
            colorer = vtkImageMapToWindowLevelColors()
            colorer.SetInputData(image)
            colorer.SetWindow(self.window_width)
            colorer.SetLevel(self.window_level)
            colorer.SetOutputFormatToRGB()
            colorer.Update()

        return colorer.GetOutput()

    def _update_wwwl_widget_nodes(self, ww, wl):
        if self.from_ == WIDGET:
            knodes = sorted(self.nodes)

            p1 = knodes[0]
            p2 = knodes[-1]
            half = (p2.value - p1.value) / 2.0
            middle = p1.value + half

            shiftWL = wl - middle
            shiftWW = p1.value + shiftWL - (wl - 0.5 * ww)

            factor = 1.0

            for n, node in enumerate(knodes):
                factor = abs(node.value - middle) / half
                factor = max(factor, 0)

                node.value += shiftWL

                if n < len(self.nodes) / 2.0:
                    node.value -= shiftWW * factor
                else:
                    node.value += shiftWW * factor

    def do_threshold_to_a_slice(self, slice_matrix, mask, threshold=None):
        """
        Based on the current threshold bounds generates a threshold mask to
        given slice_matrix.
        """
        if threshold:
            thresh_min, thresh_max = threshold
        else:
            thresh_min, thresh_max = self.current_mask.threshold_range

        m = ((slice_matrix >= thresh_min) & (slice_matrix <= thresh_max)) * 255
        m[mask == 1] = 1
        m[mask == 2] = 2
        m[mask == 253] = 253
        m[mask == 254] = 254
        return m.astype("uint8")

    def do_threshold_to_all_slices(self, mask=None):
        """
        Apply threshold to all slices.

        Params:
            - mask: the mask where result of the threshold will be stored.If
              None, it'll be the current mask.
        """
        if mask is None:
            mask = self.current_mask
        for n in range(1, mask.matrix.shape[0]):
            if mask.matrix[n, 0, 0] == 0:
                m = mask.matrix[n, 1:, 1:]
                mask.matrix[n, 1:, 1:] = self.do_threshold_to_a_slice(
                    self.matrix[n - 1], m, mask.threshold_range
                )

        mask.matrix.flush()

    def do_colour_image(self, imagedata):
        if self.from_ in (PLIST, WIDGET):
            return imagedata
        else:
            # map scalar values into colors
            _min, _max = iu.get_LUT_value_255(
                np.array((self.matrix.min(), self.matrix.max())),
                self.window_width,
                self.window_level,
            )
            lut_bg = vtkLookupTable()
            lut_bg.SetTableRange(_min, _max)
            lut_bg.SetSaturationRange(self.saturation_range)
            lut_bg.SetHueRange(self.hue_range)
            lut_bg.SetValueRange(self.value_range)
            lut_bg.Build()

            # map the input image through a lookup table
            img_colours_bg = vtkImageMapToColors()
            img_colours_bg.SetOutputFormatToRGB()
            img_colours_bg.SetLookupTable(lut_bg)
            img_colours_bg.SetInputData(imagedata)
            img_colours_bg.Update()

            return img_colours_bg.GetOutput()

    def do_colour_mask(self, imagedata, opacity):
        # scalar_range = int(imagedata.GetScalarRange()[1])
        r, g, b = self.current_mask.colour[:3]

        # map scalar values into colors
        lut_mask = vtkLookupTable()
        lut_mask.SetNumberOfColors(256)
        lut_mask.SetHueRange(const.THRESHOLD_HUE_RANGE)
        lut_mask.SetSaturationRange(1, 1)
        lut_mask.SetValueRange(0, 255)
        lut_mask.SetRange(0, 255)
        lut_mask.SetNumberOfTableValues(256)
        lut_mask.SetTableValue(0, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(1, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(2, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(253, r, g, b, opacity)
        lut_mask.SetTableValue(254, r, g, b, opacity)
        lut_mask.SetTableValue(255, r, g, b, opacity)
        lut_mask.SetRampToLinear()
        lut_mask.Build()
        # self.lut_mask = lut_mask

        # map the input image through a lookup table
        img_colours_mask = vtkImageMapToColors()
        img_colours_mask.SetLookupTable(lut_mask)
        img_colours_mask.SetOutputFormatToRGBA()
        img_colours_mask.SetInputData(imagedata)
        img_colours_mask.Update()
        # self.img_colours_mask = img_colours_mask

        return img_colours_mask.GetOutput()

    def do_custom_colour(self, imagedata, map_colours):
        # map scalar values into colors
        minv = min(map_colours)
        maxv = max(map_colours)
        ncolours = maxv - minv + 1

        lut_mask = vtkLookupTable()
        lut_mask.SetNumberOfColors(ncolours)
        lut_mask.SetHueRange(const.THRESHOLD_HUE_RANGE)
        lut_mask.SetSaturationRange(1, 1)
        lut_mask.SetValueRange(minv, maxv)
        lut_mask.SetRange(minv, maxv)
        lut_mask.SetNumberOfTableValues(ncolours)

        for v in map_colours:
            r, g, b, a = map_colours[v]
            lut_mask.SetTableValue(v, r, g, b, a)

        lut_mask.SetRampToLinear()
        lut_mask.Build()
        # self.lut_mask = lut_mask

        # map the input image through a lookup table
        img_colours_mask = vtkImageMapToColors()
        img_colours_mask.SetLookupTable(lut_mask)
        img_colours_mask.SetOutputFormatToRGBA()
        img_colours_mask.SetInputData(imagedata)
        img_colours_mask.Update()
        # self.img_colours_mask = img_colours_mask

        return img_colours_mask.GetOutput()

    def do_blend(self, imagedata, mask):
        """
        blend image with the mask.
        """
        blend_imagedata = vtkImageBlend()
        blend_imagedata.SetBlendModeToNormal()
        # blend_imagedata.SetOpacity(0, 1.0)
        blend_imagedata.SetOpacity(1, 0.8)
        blend_imagedata.SetInputData(imagedata)
        blend_imagedata.AddInputData(mask)
        blend_imagedata.Update()

        return blend_imagedata.GetOutput()

    def _do_boolean_op(self, operation, mask1, mask2):
        self.do_boolean_op(operation, mask1, mask2)

    def do_boolean_op(self, op, m1, m2):
        name_ops = {
            const.BOOLEAN_UNION: _("Union"),
            const.BOOLEAN_DIFF: _("Diff"),
            const.BOOLEAN_AND: _("Intersection"),
            const.BOOLEAN_XOR: _("XOR"),
        }

        name = f"{name_ops[op]}_{m1.name}_{m2.name}"
        proj = Project()
        mask_dict = proj.mask_dict
        names_list = [mask_dict[i].name for i in mask_dict.keys()]
        new_name = utils.next_copy_name(name, names_list)

        future_mask = Mask()
        future_mask.create_mask(self.matrix.shape)
        future_mask.spacing = self.spacing
        future_mask.name = new_name

        future_mask.matrix[:] = 1
        m = future_mask.matrix[1:, 1:, 1:]

        self.do_threshold_to_all_slices(m1)
        m1 = m1.matrix[1:, 1:, 1:]

        self.do_threshold_to_all_slices(m2)
        m2 = m2.matrix[1:, 1:, 1:]

        if op == const.BOOLEAN_UNION:
            m[:] = ((m1 > 2) + (m2 > 2)) * 255

        elif op == const.BOOLEAN_DIFF:
            m[:] = ((m1 > 2) ^ ((m1 > 2) & (m2 > 2))) * 255

        elif op == const.BOOLEAN_AND:
            m[:] = ((m1 > 2) & (m2 > 2)) * 255

        elif op == const.BOOLEAN_XOR:
            m[:] = np.logical_xor((m1 > 2), (m2 > 2)) * 255

        for o in self.buffer_slices:
            self.buffer_slices[o].discard_mask()
            self.buffer_slices[o].discard_vtk_mask()

        future_mask.was_edited = True
        self._add_mask_into_proj(future_mask)

    def apply_slice_buffer_to_mask(self, orientation):
        """
        Apply the modifications (edition) in mask buffer to mask.
        """
        b_mask = self.buffer_slices[orientation].mask
        index = self.buffer_slices[orientation].index

        # TODO: Voltar a usar marcacao na mascara
        if orientation == "AXIAL":
            # if self.current_mask.matrix[index+1, 0, 0] != 2:
            # self.current_mask.save_history(index, orientation,
            # self.current_mask.matrix[index+1,1:,1:],
            # clean=True)
            p_mask = self.current_mask.matrix[index + 1, 1:, 1:].copy()
            self.current_mask.matrix[index + 1, 1:, 1:] = b_mask
            self.current_mask.matrix[index + 1, 0, 0] = 2

        elif orientation == "CORONAL":
            # if self.current_mask.matrix[0, index+1, 0] != 2:
            # self.current_mask.save_history(index, orientation,
            # self.current_mask.matrix[1:, index+1, 1:],
            # clean=True)
            p_mask = self.current_mask.matrix[1:, index + 1, 1:].copy()
            self.current_mask.matrix[1:, index + 1, 1:] = b_mask
            self.current_mask.matrix[0, index + 1, 0] = 2

        elif orientation == "SAGITAL":
            # if self.current_mask.matrix[0, 0, index+1] != 2:
            # self.current_mask.save_history(index, orientation,
            # self.current_mask.matrix[1:, 1:, index+1],
            # clean=True)
            p_mask = self.current_mask.matrix[1:, 1:, index + 1].copy()
            self.current_mask.matrix[1:, 1:, index + 1] = b_mask
            self.current_mask.matrix[0, 0, index + 1] = 2

        self.current_mask.save_history(index, orientation, b_mask, p_mask)
        self.current_mask.was_edited = True

        for o in self.buffer_slices:
            if o != orientation:
                self.buffer_slices[o].discard_mask()
                self.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage("Reload actual slice")

    def apply_reorientation(self):
        temp_fd, temp_file = tempfile.mkstemp()
        mcopy = np.memmap(temp_file, shape=self.matrix.shape, dtype=self.matrix.dtype, mode="w+")
        mcopy[:] = self.matrix

        cx, cy, cz = self.center
        T0 = transformations.translation_matrix((-cz, -cy, -cx))
        R = transformations.quaternion_matrix(self.q_orientation)
        T1 = transformations.translation_matrix((cz, cy, cx))
        M = transformations.concatenate_matrices(T1, R.T, T0)

        transforms.apply_view_matrix_transform(
            mcopy,
            self.spacing,
            M,
            0,
            "AXIAL",
            self.interp_method,
            mcopy.min(),
            self.matrix,
        )

        del mcopy
        os.close(temp_fd)
        os.remove(temp_file)

        self.q_orientation = np.array((1, 0, 0, 0))
        self.center = [(s * d / 2.0) for (d, s) in zip(self.matrix.shape[::-1], self.spacing)]

        self.__clean_current_mask()
        if self.current_mask:
            self.current_mask.matrix[:] = 0
            self.current_mask.was_edited = False

        for o in self.buffer_slices:
            self.buffer_slices[o].discard_buffer()

        Publisher.sendMessage("Reload actual slice")

    def __undo_edition(self):
        buffer_slices = self.buffer_slices
        actual_slices = {
            "AXIAL": buffer_slices["AXIAL"].index,
            "CORONAL": buffer_slices["CORONAL"].index,
            "SAGITAL": buffer_slices["SAGITAL"].index,
            "VOLUME": 0,
        }
        self.current_mask.undo_history(actual_slices)
        for o in self.buffer_slices:
            self.buffer_slices[o].discard_mask()
            self.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage("Reload actual slice")

    def __redo_edition(self):
        buffer_slices = self.buffer_slices
        actual_slices = {
            "AXIAL": buffer_slices["AXIAL"].index,
            "CORONAL": buffer_slices["CORONAL"].index,
            "SAGITAL": buffer_slices["SAGITAL"].index,
            "VOLUME": 0,
        }
        self.current_mask.redo_history(actual_slices)
        for o in self.buffer_slices:
            self.buffer_slices[o].discard_mask()
            self.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage("Reload actual slice")

    def _open_image_matrix(self, filename, shape, dtype):
        self.matrix_filename = filename
        self.matrix = np.memmap(filename, shape=shape, dtype=dtype, mode="r+")

    def OnFlipVolume(self, axis):
        if axis == 0:
            self.matrix[:] = self.matrix[::-1]
        elif axis == 1:
            self.matrix[:] = self.matrix[:, ::-1]
        elif axis == 2:
            self.matrix[:] = self.matrix[:, :, ::-1]

        for buffer_ in self.buffer_slices.values():
            buffer_.discard_buffer()

    def OnSwapVolumeAxes(self, axes):
        axis0, axis1 = axes
        self.matrix = self.matrix.swapaxes(axis0, axis1)
        if (axis0, axis1) == (2, 1):
            self.spacing = self.spacing[1], self.spacing[0], self.spacing[2]
        elif (axis0, axis1) == (2, 0):
            self.spacing = self.spacing[2], self.spacing[1], self.spacing[0]
        elif (axis0, axis1) == (1, 0):
            self.spacing = self.spacing[0], self.spacing[2], self.spacing[1]

        for buffer_ in self.buffer_slices.values():
            buffer_.discard_buffer()

    def OnExportMask(self, filename, filetype):
        imagedata = self.current_mask.imagedata
        #  imagedata = self.imagedata
        if filetype == const.FILETYPE_IMAGEDATA:
            iu.Export(imagedata, filename)

    def _fill_holes_auto(self, parameters):
        target = parameters["target"]
        conn = parameters["conn"]
        orientation = parameters["orientation"]
        size = parameters["size"]

        if target == "2D":
            index = self.buffer_slices[orientation].index
        else:
            index = 0
            self.do_threshold_to_all_slices()

        self.current_mask.fill_holes_auto(target, conn, orientation, index, size)

        self.buffer_slices["AXIAL"].discard_mask()
        self.buffer_slices["CORONAL"].discard_mask()
        self.buffer_slices["SAGITAL"].discard_mask()

        self.buffer_slices["AXIAL"].discard_vtk_mask()
        self.buffer_slices["CORONAL"].discard_vtk_mask()
        self.buffer_slices["SAGITAL"].discard_vtk_mask()

        self.current_mask.modified(target == "3D")
        Publisher.sendMessage("Reload actual slice")

    def calc_image_density(self, mask=None):
        if mask is None:
            mask = self.current_mask
        self.do_threshold_to_all_slices(mask)
        values = self.matrix[mask.matrix[1:, 1:, 1:] > 127]

        if len(values):
            _min = values.min()
            _max = values.max()
            _mean = values.mean()
            _std = values.std()
            return _min, _max, _mean, _std
        else:
            return 0, 0, 0, 0

    def calc_mask_area(self, mask=None):
        if mask is None:
            mask = self.current_mask

        self.do_threshold_to_all_slices(mask)
        bin_img = mask.matrix[1:, 1:, 1:] > 127

        sx, sy, sz = self.spacing

        kernel = np.zeros((3, 3, 3))
        kernel[1, 1, 1] = 2 * sx * sy + 2 * sx * sz + 2 * sy * sz
        kernel[0, 1, 1] = -(sx * sy)
        kernel[2, 1, 1] = -(sx * sy)

        kernel[1, 0, 1] = -(sx * sz)
        kernel[1, 2, 1] = -(sx * sz)

        kernel[1, 1, 0] = -(sy * sz)
        kernel[1, 1, 2] = -(sy * sz)

        #  area = ndimage.generic_filter(bin_img * 1.0, _conv_area, size=(3, 3, 3), mode='constant', cval=1, extra_arguments=(sx, sy, sz)).sum()
        area = transforms.convolve_non_zero(bin_img * 1.0, kernel, 1).sum()

        return area

    def has_affine(self) -> bool:
        return not np.allclose(self.affine, np.eye(4))


def _conv_area(x: np.ndarray, sx: float, sy: float, sz: float) -> float:
    x = x.reshape((3, 3, 3))
    if x[1, 1, 1]:
        kernel = np.zeros((3, 3, 3))
        kernel[1, 1, 1] = 2 * sx * sy + 2 * sx * sz + 2 * sy * sz
        kernel[0, 1, 1] = -(sx * sy)
        kernel[2, 1, 1] = -(sx * sy)

        kernel[1, 0, 1] = -(sx * sz)
        kernel[1, 2, 1] = -(sx * sz)

        kernel[1, 1, 0] = -(sy * sz)
        kernel[1, 1, 2] = -(sy * sz)

        return (x * kernel).sum()
    else:
        return 0
