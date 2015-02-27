#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------
import os
import tempfile

import numpy
import vtk
from wx.lib.pubsub import pub as Publisher

import constants as const
import converters
import imagedata_utils as iu
import style as st
import session as ses
import utils

from mask import Mask
from project import Project
from data import mips

OTHER=0
PLIST=1
WIDGET=2


class SliceBuffer(object):
    """ 
    This class is used as buffer that mantains the vtkImageData and numpy array
    from actual slices from each orientation.
    """
    def __init__(self):
        self.index = -1
        self.image = None
        self.mask = None
        self.vtk_image = None
        self.vtk_mask = None

    def discard_vtk_mask(self):
        self.vtk_mask = None

    def discard_vtk_image(self):
        self.vtk_image = None

    def discard_mask(self):
        self.mask = None

    def discard_image(self):
        self.image = None

    def discard_buffer(self):
        self.index = -1
        self.image = None
        self.mask = None
        self.vtk_image = None
        self.vtk_mask = None


class Slice(object):
    __metaclass__= utils.Singleton
    # Only one slice will be initialized per time (despite several viewers
    # show it from distinct perspectives).
    # Therefore, we use Singleton design pattern for implementing it.

    def __init__(self):
        self.current_mask = None
        self.blend_filter = None
        self.histogram = None
        self._matrix = None
        self.aux_matrices = {}
        self.state = const.STATE_DEFAULT

        self.to_show_aux = ''

        self._type_projection = const.PROJECTION_NORMAL
        self.n_border = const.PROJECTION_BORDER_SIZE

        self.spacing = (1.0, 1.0, 1.0)

        self.number_of_colours = 256
        self.saturation_range = (0, 0)
        self.hue_range = (0, 0)
        self.value_range = (0, 1)

        self.buffer_slices = {"AXIAL": SliceBuffer(),
                              "CORONAL": SliceBuffer(),
                              "SAGITAL": SliceBuffer()}

        self.num_gradient = 0
        self.interaction_style = st.StyleStateManager()

        self.values = None
        self.nodes = None

        self.from_ = OTHER
        self.__bind_events()
        self.opacity = 0.8

    @property
    def matrix(self):
        return self._matrix

    @matrix.setter
    def matrix(self, value):
        self._matrix = value
        i, e = value.min(), value.max()
        r = int(e) - int(i)
        self.histogram = numpy.histogram(self._matrix, r, (i, e))[0]

    def __bind_events(self):
        # General slice control
        Publisher.subscribe(self.CreateSurfaceFromIndex,
                                 'Create surface from index')
        # Mask control
        Publisher.subscribe(self.__add_mask_thresh, 'Create new mask')
        Publisher.subscribe(self.__select_current_mask,
                                 'Change mask selected')
        # Mask properties
        Publisher.subscribe(self.__set_current_mask_edition_threshold,
                                 'Set edition threshold values')
        Publisher.subscribe(self.__set_current_mask_threshold,
                                 'Set threshold values')
        Publisher.subscribe(self.__set_current_mask_threshold_actual_slice,
                                 'Changing threshold values')
        Publisher.subscribe(self.__set_current_mask_colour,
                                'Change mask colour')
        Publisher.subscribe(self.__set_mask_name, 'Change mask name')
        Publisher.subscribe(self.__show_mask, 'Show mask')
        Publisher.subscribe(self.__hide_current_mask, 'Hide current mask')

        Publisher.subscribe(self.__set_current_mask_threshold_limits,
                                        'Update threshold limits')

        Publisher.subscribe(self.UpdateWindowLevelBackground,\
                                 'Bright and contrast adjustment image')

        Publisher.subscribe(self.UpdateColourTableBackground,\
                                 'Change colour table from background image')

        Publisher.subscribe(self.UpdateColourTableBackgroundPlist,\
                                 'Change colour table from background image from plist')

        Publisher.subscribe(self.UpdateColourTableBackgroundWidget,\
                                 'Change colour table from background image from widget')

        Publisher.subscribe(self._set_projection_type, 'Set projection type')

        Publisher.subscribe(self.OnExportMask,'Export mask to file')

        Publisher.subscribe(self.OnCloseProject, 'Close project data')

        Publisher.subscribe(self.OnEnableStyle, 'Enable style')
        Publisher.subscribe(self.OnDisableStyle, 'Disable style')

        Publisher.subscribe(self.OnRemoveMasks, 'Remove masks')
        Publisher.subscribe(self.OnDuplicateMasks, 'Duplicate masks')
        Publisher.subscribe(self.UpdateSlice3D,'Update slice 3D')

        Publisher.subscribe(self.OnFlipVolume, 'Flip volume')
        Publisher.subscribe(self.OnSwapVolumeAxes, 'Swap volume axes')

        Publisher.subscribe(self.__undo_edition, 'Undo edition')
        Publisher.subscribe(self.__redo_edition, 'Redo edition')
 
    def GetMaxSliceNumber(self, orientation):
        shape = self.matrix.shape
        
        # Because matrix indexing starts with 0 so the last slice is the shape
        # minu 1.
        if orientation == 'AXIAL':
            return shape[0] - 1
        elif orientation == 'CORONAL':
            return shape[1] - 1
        elif orientation == 'SAGITAL':
            return shape[2] - 1

    def discard_all_buffers(self):
        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_mask()
            buffer_.discard_mask()

    def OnRemoveMasks(self, pubsub_evt):
        selected_items = pubsub_evt.data
        proj = Project()
        for item in selected_items:
            proj.RemoveMask(item)

            # if the deleted mask is the current mask, cleans the current mask
            # and discard from buffer all datas related to mask.
            if self.current_mask is not None and item == self.current_mask.index:
                self.current_mask = None
                
                for buffer_ in self.buffer_slices.values():
                    buffer_.discard_vtk_mask()
                    buffer_.discard_mask()

                Publisher.sendMessage('Reload actual slice')

    def OnDuplicateMasks(self, pubsub_evt):
        selected_items = pubsub_evt.data
        proj = Project()
        mask_dict = proj.mask_dict
        for index in selected_items:
            original_mask = mask_dict[index]
            # compute copy name
            name = original_mask.name
            names_list = [mask_dict[i].name for i in mask_dict.keys()]
            new_name = utils.next_copy_name(name, names_list)

            copy_mask = original_mask.copy(new_name)
            self._add_mask_into_proj(copy_mask)

    def OnEnableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.SLICE_STYLES):
            new_state = self.interaction_style.AddState(state)
            Publisher.sendMessage('Set slice interaction style', new_state)
        self.state = state

    def OnDisableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.SLICE_STYLES):
            new_state = self.interaction_style.RemoveState(state)
            Publisher.sendMessage('Set slice interaction style', new_state)

            if (state == const.SLICE_STATE_EDITOR):
                Publisher.sendMessage('Set interactor default cursor')
            self.state = new_state

    def OnCloseProject(self, pubsub_evt):
        self.CloseProject()

    def CloseProject(self):
        f = self._matrix.filename
        self._matrix._mmap.close()
        self._matrix  = None
        os.remove(f)
        self.current_mask = None

        for name in self.aux_matrices:
            m = self.aux_matrices[name]
            f = m.filename
            m._mmap.close()
            m = None
            os.remove(f)
        self.aux_matrices = {}

        self.values = None
        self.nodes = None
        self.from_= OTHER
        self.state = const.STATE_DEFAULT

        self.number_of_colours = 256
        self.saturation_range = (0, 0)
        self.hue_range = (0, 0)
        self.value_range = (0, 1)

        Publisher.sendMessage('Select first item from slice menu')

    def __set_current_mask_threshold_limits(self, pubsub_evt):
        thresh_min = pubsub_evt.data[0]
        thresh_max  = pubsub_evt.data[1]
        if self.current_mask:
            index = self.current_mask.index
            self.SetMaskEditionThreshold(index, (thresh_min, thresh_max))

    def __add_mask(self, pubsub_evt):
        mask_name = pubsub_evt.data
        self.CreateMask(name=mask_name)
        self.SetMaskColour(self.current_mask.index, self.current_mask.colour)

    def __add_mask_thresh(self, pubsub_evt):
        mask_name = pubsub_evt.data[0]
        thresh = pubsub_evt.data[1]
        colour = pubsub_evt.data[2]
        self.CreateMask(name=mask_name, threshold_range=thresh, colour =colour)
        self.SetMaskColour(self.current_mask.index, self.current_mask.colour)
        self.SelectCurrentMask(self.current_mask.index)
        Publisher.sendMessage('Reload actual slice')

    def __select_current_mask(self, pubsub_evt):
        mask_index = pubsub_evt.data
        self.SelectCurrentMask(mask_index)
    
    def __set_current_mask_edition_threshold(self, evt_pubsub):
        if self.current_mask:
            threshold_range = evt_pubsub.data
            index = self.current_mask.index
            self.SetMaskEditionThreshold(index, threshold_range)

    def __set_current_mask_threshold(self, evt_pubsub):
        threshold_range = evt_pubsub.data
        index = self.current_mask.index
        self.num_gradient += 1
        self.current_mask.matrix[:] = 0
        self.current_mask.clear_history()

        to_reload = False
        if threshold_range != self.current_mask.threshold_range:
            to_reload = True
            for orientation in self.buffer_slices:
                self.buffer_slices[orientation].discard_vtk_mask()
                self.SetMaskThreshold(index, threshold_range,
                                      self.buffer_slices[orientation].index,
                                      orientation)

        # TODO: merge this code with apply_slice_buffer_to_mask
        b_mask = self.buffer_slices["AXIAL"].mask
        n = self.buffer_slices["AXIAL"].index + 1
        self.current_mask.matrix[n, 1:, 1:] = b_mask
        self.current_mask.matrix[n, 0, 0] = 1

        b_mask = self.buffer_slices["CORONAL"].mask
        n = self.buffer_slices["CORONAL"].index + 1
        self.current_mask.matrix[1:, n, 1:] = b_mask
        self.current_mask.matrix[0, n, 0] = 1

        b_mask = self.buffer_slices["SAGITAL"].mask
        n = self.buffer_slices["SAGITAL"].index + 1
        self.current_mask.matrix[1:, 1:, n] = b_mask
        self.current_mask.matrix[0, 0, n] = 1

        if to_reload:
            Publisher.sendMessage('Reload actual slice')

    def __set_current_mask_threshold_actual_slice(self, evt_pubsub):
        threshold_range = evt_pubsub.data
        index = self.current_mask.index
        for orientation in self.buffer_slices:
            self.buffer_slices[orientation].discard_vtk_mask()
            self.SetMaskThreshold(index, threshold_range,
                                  self.buffer_slices[orientation].index,
                                  orientation)
        self.num_gradient += 1

        Publisher.sendMessage('Reload actual slice')

    def __set_current_mask_colour(self, pubsub_evt):
        # "if" is necessary because wx events are calling this before any mask
        # has been created
        if self.current_mask:
            colour_wx = pubsub_evt.data
            colour_vtk = [c/255.0 for c in colour_wx]
            self.SetMaskColour(self.current_mask.index, colour_vtk)

    def __set_mask_name(self, pubsub_evt):
        index, name = pubsub_evt.data
        self.SetMaskName(index, name)

    def __show_mask(self, pubsub_evt):
        # "if" is necessary because wx events are calling this before any mask
        # has been created
        print "__show_mask"
        print "self.current_mask", self.current_mask
        if self.current_mask:
            index, value = pubsub_evt.data
            self.ShowMask(index, value)
            if not value:
                Publisher.sendMessage('Select mask name in combo', -1)

            if self._type_projection != const.PROJECTION_NORMAL:
                self.SetTypeProjection(const.PROJECTION_NORMAL)
                Publisher.sendMessage('Reload actual slice')

    def __hide_current_mask(self, pubsub_evt):
        if self.current_mask:
            index = self.current_mask.index
            value = False
            Publisher.sendMessage('Show mask', (index, value))

    def create_temp_mask(self):
        temp_file = tempfile.mktemp()
        shape = self.matrix.shape
        matrix = numpy.memmap(temp_file, mode='w+', dtype='uint8', shape=shape)
        return temp_file, matrix

    def edit_mask_pixel(self, operation, index, position, radius, orientation):
        mask = self.buffer_slices[orientation].mask
        image = self.buffer_slices[orientation].image
        thresh_min, thresh_max = self.current_mask.edition_threshold_range

        if hasattr(position, '__iter__'):
            py, px = position
            if orientation == 'AXIAL':
                sx = self.spacing[0]
                sy = self.spacing[1]
            elif orientation == 'CORONAL':
                sx = self.spacing[0]
                sy = self.spacing[2]
            elif orientation == 'SAGITAL':
                sx = self.spacing[2]
                sy = self.spacing[1]

        else:
            if orientation == 'AXIAL':
                sx = self.spacing[0]
                sy = self.spacing[1]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == 'CORONAL':
                sx = self.spacing[0]
                sy = self.spacing[2]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == 'SAGITAL':
                sx = self.spacing[2]
                sy = self.spacing[1]
                py = position / mask.shape[1]
                px = position % mask.shape[1]

        cx = index.shape[1] / 2 + 1
        cy = index.shape[0] / 2 + 1
        xi = px - index.shape[1] + cx
        xf = xi + index.shape[1]
        yi = py - index.shape[0] + cy
        yf = yi + index.shape[0]

        if yi < 0:
            index = index[abs(yi):,:]
            yi = 0
        if yf > image.shape[0]:
            index = index[:index.shape[0]-(yf-image.shape[0]), :]
            yf = image.shape[0]

        if xi < 0:
            index = index[:,abs(xi):]
            xi = 0
        if xf > image.shape[1]:
            index = index[:,:index.shape[1]-(xf-image.shape[1])]
            xf = image.shape[1]

        # Verifying if the points is over the image array.
        if (not 0 <= xi <= image.shape[1] and not 0 <= xf <= image.shape[1]) or \
           (not 0 <= yi <= image.shape[0] and not 0 <= yf <= image.shape[0]):
            return


        roi_m = mask[yi:yf,xi:xf]
        roi_i = image[yi:yf, xi:xf]

        # Checking if roi_i has at least one element.
        if roi_i.size:
            if operation == const.BRUSH_THRESH:
                # It's a trick to make points between threshold gets value 254
                # (1 * 253 + 1) and out ones gets value 1 (0 * 253 + 1).
                roi_m[index] = (((roi_i[index] >= thresh_min)
                                 & (roi_i[index] <= thresh_max)) * 253) + 1
            elif operation == const.BRUSH_THRESH_ERASE:
                roi_m[index] = (((roi_i[index] >= thresh_min)
                                 & (roi_i[index] <= thresh_max)) * 1) -1
            elif operation == const.BRUSH_DRAW:
                roi_m[index] = 254
            elif operation == const.BRUSH_ERASE:
                roi_m[index] = 1
            self.buffer_slices[orientation].discard_vtk_mask()


    def GetSlices(self, orientation, slice_number, number_slices,
                  inverted=False, border_size=1.0):
        if self.buffer_slices[orientation].index == slice_number and \
           self._type_projection == const.PROJECTION_NORMAL:
            if self.buffer_slices[orientation].vtk_image:
                image = self.buffer_slices[orientation].vtk_image
            else:
                n_image = self.get_image_slice(orientation, slice_number,
                                               number_slices, inverted,
                                               border_size)
                image = converters.to_vtk(n_image, self.spacing, slice_number, orientation)
                ww_wl_image = self.do_ww_wl(image)
                image = self.do_colour_image(ww_wl_image)
            if self.current_mask and self.current_mask.is_shown:
                if self.buffer_slices[orientation].vtk_mask:
                    print "Getting from buffer"
                    mask = self.buffer_slices[orientation].vtk_mask
                else:
                    print "Do not getting from buffer"
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
            n_image = self.get_image_slice(orientation, slice_number,
                                           number_slices, inverted, border_size)
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
            self.buffer_slices[orientation].image = n_image
            self.buffer_slices[orientation].mask = n_mask
            self.buffer_slices[orientation].vtk_image = image
            self.buffer_slices[orientation].vtk_mask = mask

        if self.to_show_aux == 'watershed' and self.current_mask.is_shown:
            m = self.get_aux_slice('watershed', orientation, slice_number)
            tmp_vimage = converters.to_vtk(m, self.spacing, slice_number, orientation)
            cimage = self.do_custom_colour(tmp_vimage, {0: (0.0, 0.0, 0.0, 0.0),
                                                        1: (0.0, 1.0, 0.0, 1.0),
                                                        2: (1.0, 0.0, 0.0, 1.0)})
            final_image = self.do_blend(final_image, cimage)
        return final_image

    def get_image_slice(self, orientation, slice_number, number_slices=1,
                        inverted=False, border_size=1.0):
        if self.buffer_slices[orientation].index == slice_number \
           and self.buffer_slices[orientation].image is not None:
            n_image = self.buffer_slices[orientation].image
        else:

            if orientation == 'AXIAL':
                if self._type_projection == const.PROJECTION_NORMAL:
                    n_image = numpy.array(self.matrix[slice_number])
                else:
                    tmp_array = numpy.array(self.matrix[slice_number:
                                                        slice_number + number_slices])
                    if inverted:
                        tmp_array = tmp_array[::-1]

                    if self._type_projection == const.PROJECTION_MaxIP:
                        n_image = numpy.array(tmp_array).max(0)
                    elif self._type_projection == const.PROJECTION_MinIP:
                        n_image = numpy.array(tmp_array).min(0)
                    elif self._type_projection == const.PROJECTION_MeanIP:
                        n_image = numpy.array(tmp_array).mean(0)
                    elif self._type_projection == const.PROJECTION_LMIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[1],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.lmip(tmp_array, 0, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_MIDA:
                        n_image = numpy.empty(shape=(tmp_array.shape[1],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.mida(tmp_array, 0, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[1],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 0, self.window_level,
                                               self.window_level, 0, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_LMIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[1],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 0, self.window_level,
                                               self.window_level, 1, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIDA:
                        n_image = numpy.empty(shape=(tmp_array.shape[1],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 0, self.window_level,
                                               self.window_level, 2, n_image)
                    else:
                        n_image = numpy.array(self.matrix[slice_number])

            elif orientation == 'CORONAL':
                if self._type_projection == const.PROJECTION_NORMAL:
                    n_image = numpy.array(self.matrix[..., slice_number, ...])
                else:
                    #if slice_number == 0:
                        #slice_number = 1
                    #if slice_number - number_slices < 0:
                        #number_slices = slice_number
                    tmp_array = numpy.array(self.matrix[..., slice_number: slice_number + number_slices, ...])
                    if inverted:
                        tmp_array = tmp_array[..., ::-1, ...]
                    if self._type_projection == const.PROJECTION_MaxIP:
                        n_image = numpy.array(tmp_array).max(1)
                    elif self._type_projection == const.PROJECTION_MinIP:
                        n_image = numpy.array(tmp_array).min(1)
                    elif self._type_projection == const.PROJECTION_MeanIP:
                        n_image = numpy.array(tmp_array).mean(1)
                    elif self._type_projection == const.PROJECTION_LMIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.lmip(tmp_array, 1, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_MIDA:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.mida(tmp_array, 1, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 1, self.window_level,
                                               self.window_level, 0, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_LMIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 1, self.window_level,
                                               self.window_level, 1, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIDA:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[2]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 1, self.window_level,
                                               self.window_level, 2, n_image)
                    else:
                        n_image = numpy.array(self.matrix[..., slice_number, ...])
            elif orientation == 'SAGITAL':
                if self._type_projection == const.PROJECTION_NORMAL:
                    n_image = numpy.array(self.matrix[..., ..., slice_number])
                else:
                    tmp_array = numpy.array(self.matrix[..., ..., 
                                                        slice_number: slice_number + number_slices])
                    if inverted:
                        tmp_array = tmp_array[..., ..., ::-1]
                    if self._type_projection == const.PROJECTION_MaxIP:
                        n_image = numpy.array(tmp_array).max(2)
                    elif self._type_projection == const.PROJECTION_MinIP:
                        n_image = numpy.array(tmp_array).min(2)
                    elif self._type_projection == const.PROJECTION_MeanIP:
                        n_image = numpy.array(tmp_array).mean(2)
                    elif self._type_projection == const.PROJECTION_LMIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[1]),
                                              dtype=tmp_array.dtype)
                        mips.lmip(tmp_array, 2, self.window_level, self.window_level, n_image)
                    elif self._type_projection == const.PROJECTION_MIDA:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[1]),
                                              dtype=tmp_array.dtype)
                        mips.mida(tmp_array, 2, self.window_level, self.window_level, n_image)

                    elif self._type_projection == const.PROJECTION_CONTOUR_MIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[1]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 2, self.window_level,
                                               self.window_level, 0, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_LMIP:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[1]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 2, self.window_level,
                                               self.window_level, 1, n_image)
                    elif self._type_projection == const.PROJECTION_CONTOUR_MIDA:
                        n_image = numpy.empty(shape=(tmp_array.shape[0],
                                                     tmp_array.shape[1]),
                                              dtype=tmp_array.dtype)
                        mips.fast_countour_mip(tmp_array, border_size, 2, self.window_level,
                                               self.window_level, 2, n_image)
                    else:
                        n_image = numpy.array(self.matrix[..., ..., slice_number])
        return n_image

    def get_mask_slice(self, orientation, slice_number):
        """ 
        It gets the from actual mask the given slice from given orientation
        """
        # It's necessary because the first position for each dimension from
        # mask matrix is used as flags to control if the mask in the
        # slice_number position has been generated.
        if self.buffer_slices[orientation].index == slice_number \
           and self.buffer_slices[orientation].mask is not None:
            return self.buffer_slices[orientation].mask
        n = slice_number + 1
        if orientation == 'AXIAL':
            if self.current_mask.matrix[n, 0, 0] == 0:
                mask = self.current_mask.matrix[n, 1:, 1:]
                mask[:] = self.do_threshold_to_a_slice(self.get_image_slice(orientation,
                                                                         slice_number),
                                                                            mask)
                self.current_mask.matrix[n, 0, 0] = 1
            n_mask = numpy.array(self.current_mask.matrix[n, 1:, 1:],
                                dtype=self.current_mask.matrix.dtype)

        elif orientation == 'CORONAL':
            if self.current_mask.matrix[0, n, 0] == 0:
                mask = self.current_mask.matrix[1:, n, 1:]
                mask[:] = self.do_threshold_to_a_slice(self.get_image_slice(orientation,
                                                                         slice_number),
                                                                            mask)
                self.current_mask.matrix[0, n, 0] = 1
            n_mask = numpy.array(self.current_mask.matrix[1:, n, 1:],
                                dtype=self.current_mask.matrix.dtype)

        elif orientation == 'SAGITAL':
            if self.current_mask.matrix[0, 0, n] == 0:
                mask = self.current_mask.matrix[1:, 1:, n]
                mask[:] = self.do_threshold_to_a_slice(self.get_image_slice(orientation,
                                                                         slice_number),
                                                                            mask)
                self.current_mask.matrix[0, 0, n] = 1
            n_mask = numpy.array(self.current_mask.matrix[1:, 1:, n],
                                dtype=self.current_mask.matrix.dtype)

        return n_mask

    def get_aux_slice(self, name, orientation, n):
        m = self.aux_matrices[name]
        if orientation == 'AXIAL':
            return numpy.array(m[n])
        elif orientation == 'CORONAL':
            return numpy.array(m[:, n, :])
        elif orientation == 'SAGITAL':
            return numpy.array(m[:, :, n])

    def GetNumberOfSlices(self, orientation):
        if orientation == 'AXIAL':
            return self.matrix.shape[0]
        elif orientation == 'CORONAL':
            return self.matrix.shape[1]
        elif orientation == 'SAGITAL':
            return self.matrix.shape[2]

    def SetMaskColour(self, index, colour, update=True):
        "Set a mask colour given its index and colour (RGB 0-1 values)"
        proj = Project()
        proj.mask_dict[index].colour = colour

        (r,g,b) = colour
        colour_wx = [r*255, g*255, b*255]
        Publisher.sendMessage('Change mask colour in notebook',
                                    (index, (r,g,b)))
        Publisher.sendMessage('Set GUI items colour', colour_wx)
        if update:
            # Updating mask colour on vtkimagedata.
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_vtk_mask()
            Publisher.sendMessage('Reload actual slice')

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

    def SetMaskThreshold(self, index, threshold_range, slice_number=None,
                         orientation=None):
        """
        Set a mask threshold range given its index and tuple of min and max
        threshold values.

        If slice_number is None then all the threshold is calculated for all
        slices, otherwise only to indicated slice.
        """
        self.current_mask.was_edited = False
        thresh_min, thresh_max = threshold_range
        print "Threshold"

        if self.current_mask.index == index:
            # TODO: find out a better way to do threshold
            if slice_number is None:
                for n, slice_ in enumerate(self.matrix):
                    m = numpy.ones(slice_.shape, self.current_mask.matrix.dtype)
                    m[slice_ < thresh_min] = 0
                    m[slice_ > thresh_max] = 0
                    m[m == 1] = 255
                    self.current_mask.matrix[n+1, 1:, 1:] = m
            else:
                print "Only one slice"
                slice_ = self.buffer_slices[orientation].image
                self.buffer_slices[orientation].mask = (255 * ((slice_ >= thresh_min) & (slice_ <= thresh_max))).astype('uint8')

            # Update viewer
            #Publisher.sendMessage('Update slice viewer')

            # Update data notebook (GUI)
            Publisher.sendMessage('Set mask threshold in notebook',
                                (self.current_mask.index,
                                self.current_mask.threshold_range))
        else:
            proj = Project()
            proj.mask_dict[index].threshold_range = threshold_range

        proj = Project()
        proj.mask_dict[self.current_mask.index].threshold_range = threshold_range

    def ShowMask(self, index, value):
        "Show a mask given its index and 'show' value (0: hide, other: show)"
        print "Showing Mask"
        proj = Project()
        proj.mask_dict[index].is_shown = value
        proj.mask_dict[index].on_show()

        if (index == self.current_mask.index):
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_vtk_mask()
                buffer_.discard_mask()
            Publisher.sendMessage('Reload actual slice')
    #---------------------------------------------------------------------------

    def SelectCurrentMask(self, index):
        "Insert mask data, based on given index, into pipeline."
        proj = Project()
        future_mask = proj.GetMask(index)
        future_mask.is_shown = True
        self.current_mask = future_mask

        colour = future_mask.colour
        self.SetMaskColour(index, colour, update=False)

        self.buffer_slices = {"AXIAL": SliceBuffer(),
                              "CORONAL": SliceBuffer(),
                              "SAGITAL": SliceBuffer()}

        Publisher.sendMessage('Set mask threshold in notebook',
                                    (index,
                                        self.current_mask.threshold_range))
        Publisher.sendMessage('Set threshold values in gradient',
                                    self.current_mask.threshold_range)
        Publisher.sendMessage('Select mask name in combo', index)
        Publisher.sendMessage('Update slice viewer')
    #---------------------------------------------------------------------------

    def CreateSurfaceFromIndex(self, pubsub_evt):
        print pubsub_evt.data
        surface_parameters = pubsub_evt.data

        proj = Project()
        mask = proj.mask_dict[surface_parameters['options']['index']]

        self.do_threshold_to_all_slices(mask)
        Publisher.sendMessage('Create surface', (self, mask, surface_parameters))

    def GetOutput(self):
        return self.blend_filter.GetOutput()

    def _set_projection_type(self, pubsub_evt):
        tprojection = pubsub_evt.data
        self.SetTypeProjection(tprojection)

    def SetTypeProjection(self, tprojection):
        if self._type_projection != tprojection:
            if self._type_projection == const.PROJECTION_NORMAL:
                Publisher.sendMessage('Hide current mask')

            if tprojection == const.PROJECTION_NORMAL:
                Publisher.sendMessage('Show MIP interface', False)
            else:
                Publisher.sendMessage('Show MIP interface', True)

            self._type_projection = tprojection
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_buffer()

            Publisher.sendMessage('Check projection menu', tprojection)

    def UpdateWindowLevelBackground(self, pubsub_evt):
        window, level = pubsub_evt.data
        self.window_width = window
        self.window_level = level

        for buffer_ in self.buffer_slices.values():
            if self._type_projection in (const.PROJECTION_NORMAL,
                                         const.PROJECTION_MaxIP,
                                         const.PROJECTION_MinIP,
                                         const.PROJECTION_MeanIP,
                                         const.PROJECTION_LMIP):
                buffer_.discard_vtk_image()
            else:
                buffer_.discard_buffer()

        Publisher.sendMessage('Reload actual slice')

    def UpdateColourTableBackground(self, pubsub_evt):
        values = pubsub_evt.data
        self.from_= OTHER
        self.number_of_colours= values[0]
        self.saturation_range = values[1]
        self.hue_range = values[2]
        self.value_range = values[3]
        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_image()
        Publisher.sendMessage('Reload actual slice')

    def UpdateColourTableBackgroundPlist(self, pubsub_evt):
        self.values = pubsub_evt.data
        self.from_= PLIST
        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_image()

        Publisher.sendMessage('Reload actual slice')

    def UpdateColourTableBackgroundWidget(self, pubsub_evt):
        self.nodes = pubsub_evt.data
        self.from_= WIDGET
        for buffer_ in self.buffer_slices.values():
            if self._type_projection in (const.PROJECTION_NORMAL,
                                         const.PROJECTION_MaxIP,
                                         const.PROJECTION_MinIP,
                                         const.PROJECTION_MeanIP,
                                         const.PROJECTION_LMIP):
                buffer_.discard_vtk_image()
            else:
                buffer_.discard_buffer()

        knodes = sorted(self.nodes)
        p0 = knodes[0].value
        pn = knodes[-1].value

        self.window_width = pn - p0
        self.window_level = (pn + p0) / 2

        Publisher.sendMessage('Reload actual slice')

    def UpdateSlice3D(self, pubsub_evt):
        widget, orientation = pubsub_evt.data
        img = self.buffer_slices[orientation].vtk_image
        original_orientation = Project().original_orientation
        cast = vtk.vtkImageCast()
        cast.SetInput(img)
        cast.SetOutputScalarTypeToDouble() 
        cast.ClampOverflowOn()
        cast.Update()

        #if (original_orientation == const.AXIAL):
        flip = vtk.vtkImageFlip()
        flip.SetInput(cast.GetOutput())
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.Update()
        widget.SetInput(flip.GetOutput())
        #else:
            #widget.SetInput(cast.GetOutput())



    def CreateMask(self, imagedata=None, name=None, colour=None,
                    opacity=None, threshold_range=None,
                    edition_threshold_range = None,
                    edited_points=None):
        
        # TODO: mask system to new system.
        future_mask = Mask()
        future_mask.create_mask(self.matrix.shape)

        if name:
            future_mask.name = name
        if colour:
            future_mask.colour = colour
        if opacity:
            future_mask.opacity = opacity
        if edition_threshold_range:
            future_mask.edition_threshold_range = edition_threshold_range
        if edited_points:
            future_mask.edited_points = edited_points
        if threshold_range:
            future_mask.threshold_range = threshold_range

        self._add_mask_into_proj(future_mask)


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
        Publisher.sendMessage('Add mask',
                                    (mask.index,
                                     mask.name,
                                     mask.threshold_range,
                                     mask.colour))

        if show:
            self.current_mask = mask
            Publisher.sendMessage('Change mask selected', mask.index)
            Publisher.sendMessage('Update slice viewer')

    def do_ww_wl(self, image):
        if self.from_ == PLIST:
            lut = vtk.vtkWindowLevelLookupTable()
            lut.SetWindow(self.window_width)
            lut.SetLevel(self.window_level)
            lut.Build()

            i = 0
            for r, g, b in self.values:
                lut.SetTableValue(i, r/255.0, g/255.0, b/255.0, 1.0)
                i += 1

            colorer = vtk.vtkImageMapToColors()
            colorer.SetInput(image)
            colorer.SetLookupTable(lut)
            colorer.SetOutputFormatToRGB()
            colorer.Update()
        elif self.from_ == WIDGET:
            lut  = vtk.vtkColorTransferFunction()

            for n in self.nodes:
                r, g, b = n.colour
                lut.AddRGBPoint(n.value, r/255.0, g/255.0, b/255.0)

            lut.Build()

            colorer = vtk.vtkImageMapToColors()
            colorer.SetLookupTable(lut)
            colorer.SetInput(image)
            colorer.SetOutputFormatToRGB()
            colorer.Update()
        else:
            colorer = vtk.vtkImageMapToWindowLevelColors()
            colorer.SetInput(image)
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
                if factor < 0:
                    factor = 0

                node.value += shiftWL

                if n < len(self.nodes) / 2.0:
                    node.value -= shiftWW * factor
                else:
                    node.value += shiftWW * factor

    def do_threshold_to_a_slice(self, slice_matrix, mask):
        """ 
        Based on the current threshold bounds generates a threshold mask to
        given slice_matrix.
        """
        thresh_min, thresh_max = self.current_mask.threshold_range
        m = (((slice_matrix >= thresh_min) & (slice_matrix <= thresh_max)) * 255)
        m[mask == 1] = 1
        m[mask == 2] = 2
        m[mask == 253] = 253
        m[mask == 254] = 254
        return m.astype('uint8')

    def do_threshold_to_all_slices(self, mask=None):
        """
        Apply threshold to all slices.

        Params:
            - mask: the mask where result of the threshold will be stored.If
              None, it'll be the current mask.
        """
        if mask is None:
            mask = self.current_mask
        for n in xrange(1, mask.matrix.shape[0]):
            if mask.matrix[n, 0, 0] == 0:
                m = mask.matrix[n, 1:, 1:]
                mask.matrix[n, 1:, 1:] = self.do_threshold_to_a_slice(self.matrix[n-1], m)

        mask.matrix.flush()

    def do_colour_image(self, imagedata):
        if self.from_ in (PLIST, WIDGET):
            return imagedata
        else:
            # map scalar values into colors
            lut_bg = vtk.vtkLookupTable()
            lut_bg.SetTableRange(imagedata.GetScalarRange())
            lut_bg.SetSaturationRange(self.saturation_range)
            lut_bg.SetHueRange(self.hue_range)
            lut_bg.SetValueRange(self.value_range)
            lut_bg.Build()

            # map the input image through a lookup table
            img_colours_bg = vtk.vtkImageMapToColors()
            img_colours_bg.SetOutputFormatToRGB()
            img_colours_bg.SetLookupTable(lut_bg)
            img_colours_bg.SetInput(imagedata)
            img_colours_bg.Update()

            return img_colours_bg.GetOutput()

    def do_colour_mask(self, imagedata, opacity):
        scalar_range = int(imagedata.GetScalarRange()[1])
        r, g, b = self.current_mask.colour

        # map scalar values into colors
        lut_mask = vtk.vtkLookupTable()
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
        img_colours_mask = vtk.vtkImageMapToColors()
        img_colours_mask.SetLookupTable(lut_mask)
        img_colours_mask.SetOutputFormatToRGBA()
        img_colours_mask.SetInput(imagedata)
        img_colours_mask.Update()
        # self.img_colours_mask = img_colours_mask

        return img_colours_mask.GetOutput()

    def do_custom_colour(self, imagedata, map_colours):
        # map scalar values into colors
        minv = min(map_colours)
        maxv = max(map_colours)
        ncolours = maxv - minv + 1

        lut_mask = vtk.vtkLookupTable()
        lut_mask.SetNumberOfColors(ncolours)
        lut_mask.SetHueRange(const.THRESHOLD_HUE_RANGE)
        lut_mask.SetSaturationRange(1, 1)
        lut_mask.SetValueRange(minv, maxv)
        lut_mask.SetRange(minv, maxv)
        lut_mask.SetNumberOfTableValues(ncolours)

        for v in map_colours:
            r,g, b,a = map_colours[v]
            lut_mask.SetTableValue(v, r, g, b, a)

        lut_mask.SetRampToLinear()
        lut_mask.Build()
        # self.lut_mask = lut_mask

        # map the input image through a lookup table
        img_colours_mask = vtk.vtkImageMapToColors()
        img_colours_mask.SetLookupTable(lut_mask)
        img_colours_mask.SetOutputFormatToRGBA()
        img_colours_mask.SetInput(imagedata)
        img_colours_mask.Update()
        # self.img_colours_mask = img_colours_mask

        return img_colours_mask.GetOutput()

    def do_blend(self, imagedata, mask):
        """
        blend image with the mask.
        """
        blend_imagedata = vtk.vtkImageBlend()
        blend_imagedata.SetBlendModeToNormal()
        # blend_imagedata.SetOpacity(0, 1.0)
        blend_imagedata.SetOpacity(1, 0.8)
        blend_imagedata.SetInput(imagedata)
        blend_imagedata.AddInput(mask)
        blend_imagedata.Update()

        return blend_imagedata.GetOutput()

    def apply_slice_buffer_to_mask(self, orientation):
        """
        Apply the modifications (edition) in mask buffer to mask.
        """
        b_mask = self.buffer_slices[orientation].mask
        index = self.buffer_slices[orientation].index

        # TODO: Voltar a usar marcacao na mascara
        if orientation == 'AXIAL':
            #if self.current_mask.matrix[index+1, 0, 0] != 2:
            #self.current_mask.save_history(index, orientation,
                                           #self.current_mask.matrix[index+1,1:,1:],
                                               #clean=True)
            p_mask = self.current_mask.matrix[index+1,1:,1:].copy()
            self.current_mask.matrix[index+1,1:,1:] = b_mask
            self.current_mask.matrix[index+1, 0, 0] = 2

        elif orientation == 'CORONAL':
            #if self.current_mask.matrix[0, index+1, 0] != 2:
            #self.current_mask.save_history(index, orientation,
                                           #self.current_mask.matrix[1:, index+1, 1:],
                                           #clean=True)
            p_mask = self.current_mask.matrix[1:, index+1, 1:].copy()
            self.current_mask.matrix[1:, index+1, 1:] = b_mask
            self.current_mask.matrix[0, index+1, 0] = 2

        elif orientation == 'SAGITAL':
            #if self.current_mask.matrix[0, 0, index+1] != 2:
            #self.current_mask.save_history(index, orientation,
                                           #self.current_mask.matrix[1:, 1:, index+1],
                                           #clean=True)
            p_mask = self.current_mask.matrix[1:, 1:, index+1].copy()
            self.current_mask.matrix[1:, 1:, index+1] = b_mask
            self.current_mask.matrix[0, 0, index+1] = 2

        self.current_mask.save_history(index, orientation, b_mask, p_mask)
        self.current_mask.was_edited = True

        for o in self.buffer_slices:
            if o != orientation:
                self.buffer_slices[o].discard_mask()
                self.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage('Reload actual slice')

    def __undo_edition(self, pub_evt):
        buffer_slices = self.buffer_slices
        actual_slices = {"AXIAL": buffer_slices["AXIAL"].index,
                         "CORONAL": buffer_slices["CORONAL"].index,
                         "SAGITAL": buffer_slices["SAGITAL"].index,}
        self.current_mask.undo_history(actual_slices)
        for o in self.buffer_slices:
            self.buffer_slices[o].discard_mask()
            self.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage('Reload actual slice')

    def __redo_edition(self, pub_evt):
        buffer_slices = self.buffer_slices
        actual_slices = {"AXIAL": buffer_slices["AXIAL"].index,
                         "CORONAL": buffer_slices["CORONAL"].index,
                         "SAGITAL": buffer_slices["SAGITAL"].index,}
        self.current_mask.redo_history(actual_slices)
        for o in self.buffer_slices:
            self.buffer_slices[o].discard_mask()
            self.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage('Reload actual slice')

    def _open_image_matrix(self, filename, shape, dtype):
        self.matrix_filename = filename
        self.matrix = numpy.memmap(filename, shape=shape, dtype=dtype, mode='r+')

    def OnFlipVolume(self, pubsub_evt):
        axis = pubsub_evt.data
        if axis == 0:
            self.matrix[:] = self.matrix[::-1]
        elif axis == 1:
            self.matrix[:] = self.matrix[:, ::-1]
        elif axis == 2:
            self.matrix[:] = self.matrix[:, :, ::-1]

        for buffer_ in self.buffer_slices.values():
            buffer_.discard_buffer()

    def OnSwapVolumeAxes(self, pubsub_evt):
        axis0, axis1 = pubsub_evt.data
        self.matrix = self.matrix.swapaxes(axis0, axis1)
        if (axis0, axis1) == (2, 1):
            self.spacing = self.spacing[1], self.spacing[0], self.spacing[2]
        elif (axis0, axis1) == (2, 0):
            self.spacing = self.spacing[2], self.spacing[1], self.spacing[0]
        elif (axis0, axis1) == (1, 0):
            self.spacing = self.spacing[0], self.spacing[2], self.spacing[1]

        for buffer_ in self.buffer_slices.values():
            buffer_.discard_buffer()

        print type(self.matrix)

    def OnExportMask(self, pubsub_evt):
        pass
        ##imagedata = self.current_mask.imagedata
        #imagedata = self.imagedata
        #filename, filetype = pubsub_evt.data
        #if (filetype == const.FILETYPE_IMAGEDATA):
            #iu.Export(imagedata, filename)
