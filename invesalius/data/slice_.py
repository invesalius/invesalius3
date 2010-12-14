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
import numpy
import vtk
import wx.lib.pubsub as ps

import constants as const
import imagedata_utils as iu
from mask import Mask
import style as st
from project import Project
import session as ses
import utils

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
        self.imagedata = None
        self.current_mask = None
        self.blend_filter = None
        self.matrix = None

        self.buffer_slices = {"AXIAL": SliceBuffer(),
                              "CORONAL": SliceBuffer(),
                              "SAGITAL": SliceBuffer()}

        self.num_gradient = 0
        self.interaction_style = st.StyleStateManager()

        self.__bind_events()

    def __bind_events(self):
        # General slice control
        ps.Publisher().subscribe(self.CreateSurfaceFromIndex,
                                 'Create surface from index')
        # Mask control
        ps.Publisher().subscribe(self.__add_mask_thresh, 'Create new mask')
        ps.Publisher().subscribe(self.__select_current_mask,
                                 'Change mask selected')
        # Mask properties
        ps.Publisher().subscribe(self.__set_current_mask_edition_threshold,
                                 'Set edition threshold values')
        ps.Publisher().subscribe(self.__set_current_mask_threshold,
                                 'Set threshold values')
        ps.Publisher().subscribe(self.__set_current_mask_threshold_actual_slice,
                                 'Changing threshold values')
        ps.Publisher().subscribe(self.__set_current_mask_colour,
                                'Change mask colour')
        ps.Publisher().subscribe(self.__set_mask_name, 'Change mask name')
        ps.Publisher().subscribe(self.__show_mask, 'Show mask')

        # Operations related to slice editor
        ps.Publisher().subscribe(self.__erase_mask_pixel, 'Erase mask pixel')
        ps.Publisher().subscribe(self.__edit_mask_pixel, 'Edit mask pixel')
        ps.Publisher().subscribe(self.__add_mask_pixel, 'Add mask pixel')

        ps.Publisher().subscribe(self.__set_current_mask_threshold_limits,
                                        'Update threshold limits')

        ps.Publisher().subscribe(self.UpdateWindowLevelBackground,\
                                 'Bright and contrast adjustment image')

        ps.Publisher().subscribe(self.UpdateColourTableBackground,\
                                 'Change colour table from background image')

        ps.Publisher().subscribe(self.InputImageWidget, 'Input Image in the widget')
        ps.Publisher().subscribe(self.OnExportMask,'Export mask to file')

        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')

        ps.Publisher().subscribe(self.OnEnableStyle, 'Enable style')
        ps.Publisher().subscribe(self.OnDisableStyle, 'Disable style')

        ps.Publisher().subscribe(self.OnRemoveMasks, 'Remove masks')
        ps.Publisher().subscribe(self.OnDuplicateMasks, 'Duplicate masks')

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

                ps.Publisher().sendMessage('Reload actual slice')

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
            # create new mask
            self.CreateMask(imagedata = original_mask.imagedata,
                            name = new_name,
                            colour = original_mask.colour,
                            opacity = original_mask.opacity,
                            threshold_range = original_mask.threshold_range,
                            edition_threshold_range = original_mask.edition_threshold_range,
                            edited_points = original_mask.edited_points)


    def OnEnableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.SLICE_STYLES):
            new_state = self.interaction_style.AddState(state)
            ps.Publisher().sendMessage('Set slice interaction style', new_state)


    def OnDisableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.SLICE_STYLES):
            new_state = self.interaction_style.RemoveState(state)
            ps.Publisher().sendMessage('Set slice interaction style', new_state)

            if (state == const.SLICE_STATE_EDITOR):
                ps.Publisher().sendMessage('Set interactor default cursor')


    def OnCloseProject(self, pubsub_evt):
        self.CloseProject()

    def CloseProject(self):
        self.imagedata = None
        self.current_mask = None
        ps.Publisher().sendMessage('Select first item from slice menu')
        #self.blend_filter = None
        #self.blend_filter = None
        #self.num_gradient = 0


    def __set_current_mask_threshold_limits(self, pubsub_evt):
        thresh_min = pubsub_evt.data[0]
        thresh_max  = pubsub_evt.data[1]
        if self.current_mask:
            index = self.current_mask.index
            self.SetMaskEditionThreshold(index, (thresh_min, thresh_max))



    #---------------------------------------------------------------------------
    # BEGIN PUBSUB_EVT METHODS
    #---------------------------------------------------------------------------
    #def __get_mask_data_for_surface_creation(self, pubsub_evt):
    #    mask_index = pubsub_evt.data
    #    CreateSurfaceFromIndex

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
        ps.Publisher().sendMessage('Reload actual slice')

    def __select_current_mask(self, pubsub_evt):
        mask_index = pubsub_evt.data
        self.SelectCurrentMask(mask_index)
    #---------------------------------------------------------------------------
    def __set_current_mask_edition_threshold(self, evt_pubsub):
        if self.current_mask:
            threshold_range = evt_pubsub.data
            index = self.current_mask.index
            self.SetMaskEditionThreshold(index, threshold_range)

    def __set_current_mask_threshold(self, evt_pubsub):
        threshold_range = evt_pubsub.data
        index = self.current_mask.index
        #self.SetMaskThreshold(index, threshold_range)
        #Clear edited points
        self.current_mask.edited_points = {}
        self.num_gradient += 1
        self.current_mask.matrix[0, :, :] = 0
        self.current_mask.matrix[:, 0, :] = 0
        self.current_mask.matrix[:, :, 0] = 0

    def __set_current_mask_threshold_actual_slice(self, evt_pubsub):
        threshold_range = evt_pubsub.data
        index = self.current_mask.index
        for orientation in self.buffer_slices:
            self.buffer_slices[orientation].discard_vtk_mask()
            self.SetMaskThreshold(index, threshold_range,
                                  self.buffer_slices[orientation].index,
                                  orientation)
        #Clear edited points
        self.current_mask.edited_points = {}
        self.num_gradient += 1

        ps.Publisher().sendMessage('Reload actual slice')

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
    #---------------------------------------------------------------------------
    def __erase_mask_pixel(self, pubsub_evt):
        positions = pubsub_evt.data
        for position in positions:
            self.ErasePixel(position)

    def __edit_mask_pixel(self, pubsub_evt):
        positions = pubsub_evt.data
        for position in positions:
            self.EditPixelBasedOnThreshold(position)

    def __add_mask_pixel(self, pubsub_evt):
        positions = pubsub_evt.data
        for position in positions:
            self.DrawPixel(position)
    #---------------------------------------------------------------------------
    # END PUBSUB_EVT METHODS
    #---------------------------------------------------------------------------

    def GetSlices(self, orientation, slice_number):
        if self.buffer_slices[orientation].index == slice_number:
            if self.buffer_slices[orientation].vtk_image:
                image = self.buffer_slices[orientation].vtk_image
            else:
                n_image = self.GetImageSlice(orientation, slice_number)
                image = iu.to_vtk(n_image, self.spacing, slice_number, orientation)
                image = self.do_ww_wl(image)
            if self.current_mask and self.current_mask.is_shown:
                if self.buffer_slices[orientation].vtk_mask:
                    print "Getting from buffer"
                    mask = self.buffer_slices[orientation].vtk_mask
                else:
                    print "Do not getting from buffer"
                    n_mask = self.GetMaskSlice(orientation, slice_number)
                    mask = iu.to_vtk(n_mask, self.spacing, slice_number, orientation)
                    mask = self.do_colour_mask(mask)
                final_image = self.do_blend(image, mask)
            else:
                final_image = image
        else:
            n_image = self.GetImageSlice(orientation, slice_number)
            image = iu.to_vtk(n_image, self.spacing, slice_number, orientation)
            image = self.do_ww_wl(image)

            if self.current_mask and self.current_mask.is_shown:
                n_mask = self.GetMaskSlice(orientation, slice_number)
                mask = iu.to_vtk(n_mask, self.spacing, slice_number, orientation)
                mask = self.do_colour_mask(mask)
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

        return final_image

    def GetImageSlice(self, orientation, slice_number):
        if self.buffer_slices[orientation].index == slice_number \
           and self.buffer_slices[orientation].image is not None:
            n_image = self.buffer_slices[orientation].image
        else:
            if orientation == 'AXIAL':
                n_image = numpy.array(self.matrix[slice_number])
            elif orientation == 'CORONAL':
                n_image = numpy.array(self.matrix[..., slice_number, ...])
            elif orientation == 'SAGITAL':
                n_image = numpy.array(self.matrix[..., ..., slice_number])
        return n_image

    def GetMaskSlice(self, orientation, slice_number):
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
                self.current_mask.matrix[n, 1:, 1:] = \
                        self.do_threshold_to_a_slice(self.GetImageSlice(orientation,
                                                                        slice_number))
                self.current_mask.matrix[n, 0, 0] = 1
            n_mask = numpy.array(self.current_mask.matrix[n, 1:, 1:])

        elif orientation == 'CORONAL':
            if self.current_mask.matrix[0, n, 0] == 0:
                self.current_mask.matrix[1:, n, 1:] = \
                        self.do_threshold_to_a_slice(self.GetImageSlice(orientation,
                                                                        slice_number))
                self.current_mask.matrix[0, n, 0] = 1
            n_mask = numpy.array(self.current_mask.matrix[1:, n, 1:])

        elif orientation == 'SAGITAL':
            if self.current_mask.matrix[0, 0, n] == 0:
                self.current_mask.matrix[1:, 1:, n] = \
                        self.do_threshold_to_a_slice(self.GetImageSlice(orientation,
                                                                        slice_number))
                self.current_mask.matrix[0, 0, n] = 1
            n_mask = numpy.array(self.current_mask.matrix[1:, 1:, n])
        return n_mask

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
        #scalar_range = int(self.imagedata.GetScalarRange()[1])
        #self.lut_mask.SetTableValue(0, 0, 0, 0, 0.0)
        #self.lut_mask.SetTableValue(scalar_range - 1, r, g, b, 1.0)

        colour_wx = [r*255, g*255, b*255]
        ps.Publisher().sendMessage('Change mask colour in notebook',
                                    (index, (r,g,b)))
        ps.Publisher().sendMessage('Set GUI items colour', colour_wx)
        if update:
            ps.Publisher().sendMessage('Update slice viewer')

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
        thresh_min, thresh_max = threshold_range

        if self.current_mask.index == index:
            ## Update pipeline (this must be here, so pipeline is not broken)
            #self.img_thresh_mask.SetInput(self.imagedata)
            #self.img_thresh_mask.ThresholdBetween(float(thresh_min),
                                                  #float(thresh_max))
            #self.img_thresh_mask.Update()

            ## Create imagedata copy so the pipeline is not broken
            #imagedata = self.img_thresh_mask.GetOutput()
            #self.current_mask.imagedata.DeepCopy(imagedata)
            #self.current_mask.threshold_range = threshold_range

            ## Update pipeline (this must be here, so pipeline is not broken)
            #self.img_colours_mask.SetInput(self.current_mask.imagedata)

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
                self.buffer_slices[orientation].mask = 255 * ((slice_ >= thresh_min) & (slice_ <= thresh_max))

            # Update viewer
            #ps.Publisher().sendMessage('Update slice viewer')

            # Update data notebook (GUI)
            ps.Publisher().sendMessage('Set mask threshold in notebook',
                                (self.current_mask.index,
                                self.current_mask.threshold_range))
        else:
            proj = Project()
            proj.mask_dict[index].threshold_range = threshold_range

        proj = Project()
        proj.mask_dict[self.current_mask.index].threshold_range = threshold_range


    def ShowMask(self, index, value):
        "Show a mask given its index and 'show' value (0: hide, other: show)"
        proj = Project()
        proj.mask_dict[index].is_shown = value
        if (index == self.current_mask.index):
            for buffer_ in self.buffer_slices.values():
                buffer_.discard_vtk_mask()
                buffer_.discard_mask()
            ps.Publisher().sendMessage('Reload actual slice')
    #---------------------------------------------------------------------------
    def ErasePixel(self, position):
        "Delete pixel, based on x, y and z position coordinates."
        x, y, z = round(position[0],0), round(position[1],0),position[2]
        colour = self.imagedata.GetScalarRange()[0]
        imagedata = self.current_mask.imagedata
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        self.current_mask.edited_points[(x, y, z)] = colour

        session = ses.Session()
        session.ChangeProject()


    def DrawPixel(self, position, colour=None):
        "Draw pixel, based on x, y and z position coordinates."
        x, y, z = round(position[0],0), round(position[1],0),position[2]
        colour = self.imagedata.GetScalarRange()[1]
        imagedata = self.current_mask.imagedata
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        self.current_mask.edited_points[(x, y, z)] = colour

        session = ses.Session()
        session.ChangeProject()


    def EditPixelBasedOnThreshold(self, position):
        "Erase or draw pixel based on edition threshold range."
        x, y, z = round(position[0],0), round(position[1],0),position[2]
        colour = self.imagedata.GetScalarComponentAsDouble(x, y, z, 0)
        thresh_min, thresh_max = self.current_mask.edition_threshold_range
        if (colour >= thresh_min) and (colour <= thresh_max):
            self.DrawPixel(position, colour)
        else:
            self.ErasePixel(position)

        session = ses.Session()
        session.ChangeProject()


    #---------------------------------------------------------------------------
    def SelectCurrentMask(self, index):
        "Insert mask data, based on given index, into pipeline."
        # This condition is not necessary in Linux, only under mac and windows
        # because combobox event is binded when the same item is selected again.
        #if index != self.current_mask.index:
        print "SelectCurrentMask"
        print "index:", index
        proj = Project()
        future_mask = proj.GetMask(index)
        future_mask.is_shown = True
        self.current_mask = future_mask

        colour = future_mask.colour
        #index = future_mask.index
        print index
        self.SetMaskColour(index, colour, update=False)

        self.buffer_slices = {"AXIAL": SliceBuffer(),
                              "CORONAL": SliceBuffer(),
                              "SAGITAL": SliceBuffer()}

        ps.Publisher().sendMessage('Set mask threshold in notebook',
                                    (index,
                                        self.current_mask.threshold_range))
        ps.Publisher().sendMessage('Set threshold values in gradient',
                                    self.current_mask.threshold_range)
        ps.Publisher().sendMessage('Select mask name in combo', index)
        ps.Publisher().sendMessage('Update slice viewer')
    #---------------------------------------------------------------------------

    def CreateSurfaceFromIndex(self, pubsub_evt):
        mask_index, overwrite_surface = pubsub_evt.data


        proj = Project()
        mask = proj.mask_dict[mask_index]

        # This is very important. Do not use masks' imagedata. It would mess up
        # surface quality event when using contour
        colour = mask.colour
        threshold = mask.threshold_range
        edited_points = mask.edited_points

        self.SetMaskThreshold(mask.index, threshold)

        mask.matrix.flush()

        ps.Publisher().sendMessage('Create surface', (mask, self.spacing))

    def GetOutput(self):
        return self.blend_filter.GetOutput()

    def SetInput(self, imagedata, mask_dict):
        self.imagedata = imagedata
        self.extent = imagedata.GetExtent()

        imagedata_bg = self.__create_background(imagedata)

        if not mask_dict:
            imagedata_mask = self.__build_mask(imagedata, create=True)
        else:
            self.__load_masks(imagedata, mask_dict)
            imagedata_mask = self.img_colours_mask.GetOutput()

        mask_opacity = self.current_mask.opacity

        # blend both imagedatas, so it can be inserted into viewer
        blend_filter = vtk.vtkImageBlend()
        blend_filter.SetBlendModeToNormal()
        blend_filter.SetOpacity(0, 1)
        if self.current_mask.is_shown:
            blend_filter.SetOpacity(1, mask_opacity)
        else:
            blend_filter.SetOpacity(1, 0)
        blend_filter.SetInput(0, imagedata_bg)
        blend_filter.SetInput(1, imagedata_mask)
        blend_filter.SetBlendModeToNormal()
        blend_filter.GetOutput().ReleaseDataFlagOn()
        self.blend_filter = blend_filter

        self.window_level = vtk.vtkImageMapToWindowLevelColors()
        self.window_level.SetInput(self.imagedata)

    def __create_background(self, imagedata):
        thresh_min, thresh_max = imagedata.GetScalarRange()
        ps.Publisher().sendMessage('Update threshold limits list', (thresh_min,
                                    thresh_max))

        # map scalar values into colors
        lut_bg = self.lut_bg = vtk.vtkLookupTable()
        lut_bg.SetTableRange(thresh_min, thresh_max)
        lut_bg.SetSaturationRange(0, 0)
        lut_bg.SetHueRange(0, 0)
        lut_bg.SetValueRange(0, 1)
        lut_bg.Build()

        # map the input image through a lookup table
        img_colours_bg = self.img_colours_bg = vtk.vtkImageMapToColors()
        img_colours_bg.SetOutputFormatToRGBA()
        img_colours_bg.SetLookupTable(lut_bg)
        img_colours_bg.SetInput(imagedata)

        return img_colours_bg.GetOutput()

    def UpdateWindowLevelBackground(self, pubsub_evt):
        
        window, level = pubsub_evt.data
        self.window_width = window
        self.window_level = level

        for buffer_ in self.buffer_slices.values():
            buffer_.discard_vtk_image()

        ps.Publisher().sendMessage('Reload actual slice')

        #window_level = self.window_level

        #if not((window == window_level.GetWindow()) and\
                #(level == window_level.GetLevel())):

            #window_level.SetWindow(window)
            #window_level.SetLevel(level)
            #window_level.SetOutputFormatToLuminance()
            #window_level.Update()

            #thresh_min, thresh_max = window_level.GetOutput().GetScalarRange()
            #self.lut_bg.SetTableRange(thresh_min, thresh_max)
            #self.img_colours_bg.SetInput(window_level.GetOutput())

    def UpdateColourTableBackground(self, pubsub_evt):
        values = pubsub_evt.data

        if (values[0]):
            self.lut_bg.SetNumberOfColors(values[0])

        self.lut_bg.SetSaturationRange(values[1])
        self.lut_bg.SetHueRange(values[2])
        self.lut_bg.SetValueRange(values[3])

        thresh_min, thresh_max = self.window_level.GetOutput().GetScalarRange()
        self.lut_bg.SetTableRange(thresh_min, thresh_max)


    def InputImageWidget(self, pubsub_evt):
        #widget = pubsub_evt.data

        #flip = vtk.vtkImageFlip()
        #flip.SetInput(self.window_level.GetOutput())
        #flip.SetFilteredAxis(1)
        #flip.FlipAboutOriginOn()
        #flip.Update()

        #widget.SetInput(flip.GetOutput())
        pass


    def CreateMask(self, imagedata=None, name=None, colour=None,
                    opacity=None, threshold_range=None,
                    edition_threshold_range = None,
                    edited_points=None):
        
        # TODO: mask system to new system.
        future_mask = Mask()
        future_mask.create_mask(self.matrix.shape)

        if colour:
            future_mask.colour = colour
        if opacity:
            future_mask.opacity = opacity
        if edition_threshold_range:
            future_mask.edition_threshold_range = edition_threshold_range
        if edited_points:
            future_mask.edited_points = edited_points

        ## this is not the first mask, so we will import data from old imagedata
        #if imagedata is None:
            #old_mask = self.current_mask
            #imagedata = old_mask.imagedata
            #future_mask.threshold_range = old_mask.threshold_range

        #if threshold_range:
            #future_mask.threshold_range = threshold_range
            #future_mask.imagedata = self.__create_mask_threshold(self.imagedata, 
                                                    #threshold_range)
        #else:
            #future_mask.imagedata = vtk.vtkImageData()
            #future_mask.imagedata.DeepCopy(imagedata)
            #future_mask.imagedata.Update()


        ## when this is not the first instance, user will have defined a name
        #if name is not None:
            #future_mask.name = name
            #if future_mask.is_shown:
                #self.blend_filter.SetOpacity(1, future_mask.opacity)
            #else:
                #self.blend_filter.SetOpacity(1, 0)
            #self.blend_filter.Update()

        # insert new mask into project and retrieve its index
        proj = Project()
        index = proj.AddMask(future_mask)
        future_mask.index = index
        #if threshold_range:
            #self.SetMaskThreshold(index, threshold_range)
            #future_mask.edited_points = {}

        ## update gui related to mask
        ps.Publisher().sendMessage('Add mask',
                                    (future_mask.index,
                                     future_mask.name,
                                     future_mask.threshold_range,
                                     future_mask.colour))

        self.current_mask = future_mask

        print self.current_mask.matrix

        ps.Publisher().sendMessage('Change mask selected', future_mask.index)
        ps.Publisher().sendMessage('Update slice viewer')


    def __load_masks(self, imagedata, mask_dict):
        keys = mask_dict.keys()
        keys.sort()
        for key in keys:
            mask = mask_dict[key]

            # update gui related to mask
            utils.debug("__load_masks")
            utils.debug('THRESHOLD_RANGE %s'% mask.threshold_range)
            ps.Publisher().sendMessage('Add mask',
                                    (mask.index,
                                     mask.name,
                                     mask.threshold_range,
                                     mask.colour))

        self.current_mask = mask
        self.__build_mask(imagedata, False)

        ps.Publisher().sendMessage('Change mask selected', mask.index)
        ps.Publisher().sendMessage('Update slice viewer')

    def do_ww_wl(self, image):
        print "WW, WL", self.window_width, self.window_level
        print image.GetScalarRange()
        colorer = vtk.vtkImageMapToWindowLevelColors()
        colorer.SetInput(image)
        colorer.SetWindow(self.window_width)
        colorer.SetLevel(self.window_level)
        colorer.SetOutputFormatToRGB()
        colorer.Update()

        return colorer.GetOutput()

    def do_threshold_to_a_slice(self, slice_matrix):
        """ 
        Based on the current threshold bounds generates a threshold mask to
        given slice_matrix.
        """
        thresh_min, thresh_max = self.current_mask.threshold_range
        m= numpy.logical_and(slice_matrix >= thresh_min, slice_matrix <= thresh_max) * 255
        return m

    def do_colour_mask(self, imagedata):
        scalar_range = int(imagedata.GetScalarRange()[1])
        r, g, b = self.current_mask.colour

        # map scalar values into colors
        lut_mask = vtk.vtkLookupTable()
        lut_mask.SetNumberOfColors(255)
        lut_mask.SetHueRange(const.THRESHOLD_HUE_RANGE)
        lut_mask.SetSaturationRange(1, 1)
        lut_mask.SetValueRange(0, 1)
        lut_mask.SetNumberOfTableValues(256)
        lut_mask.SetTableValue(0, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(1, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(2, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(255, r, g, b, 1.0)
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
        # blend both imagedatas, so it can be inserted into viewer
        print "Blending Spacing", imagedata.GetSpacing(), mask.GetSpacing()

        blend_imagedata = vtk.vtkImageBlend()
        blend_imagedata.SetBlendModeToNormal()
        # blend_imagedata.SetOpacity(0, 1.0)
        blend_imagedata.SetOpacity(1, 0.8)
        blend_imagedata.SetInput(imagedata)
        blend_imagedata.AddInput(mask)
        blend_imagedata.Update()

        # return colorer.GetOutput()

        return blend_imagedata.GetOutput()


    def __build_mask(self, imagedata, create=True):
        # create new mask instance and insert it into project
        if create:
            self.CreateMask(imagedata=imagedata)
        current_mask = self.current_mask

        # properties to be inserted into pipeline
        scalar_range = int(imagedata.GetScalarRange()[1])
        r,g,b = current_mask.colour

        # map scalar values into colors
        lut_mask = vtk.vtkLookupTable()
        lut_mask.SetNumberOfTableValues(1)
        lut_mask.SetNumberOfColors(1)
        lut_mask.SetHueRange(const.THRESHOLD_HUE_RANGE)
        lut_mask.SetSaturationRange(1, 1)
        lut_mask.SetValueRange(1, 1)
        lut_mask.SetNumberOfTableValues(scalar_range)
        lut_mask.SetTableValue(1, r, g, b, 1.0)
        lut_mask.SetTableValue(scalar_range - 1, r, g, b, 1.0)
        lut_mask.SetRampToLinear()
        lut_mask.Build()
        self.lut_mask = lut_mask

        mask_thresh_imagedata = self.__create_mask_threshold(imagedata)

        if create:
            # threshold pipeline
            current_mask.imagedata.DeepCopy(mask_thresh_imagedata)
        else:
            mask_thresh_imagedata = self.current_mask.imagedata

        # map the input image through a lookup table
        img_colours_mask = vtk.vtkImageMapToColors()
        img_colours_mask.SetOutputFormatToRGBA()
        img_colours_mask.SetLookupTable(lut_mask)

        img_colours_mask.SetInput(mask_thresh_imagedata)

        self.img_colours_mask = img_colours_mask

        return img_colours_mask.GetOutput()


    def __create_mask_threshold(self, imagedata, threshold_range=None):
        if not threshold_range:
            thresh_min, thresh_max = self.current_mask.threshold_range
        else:
            thresh_min, thresh_max = threshold_range

        # flexible threshold
        img_thresh_mask = vtk.vtkImageThreshold()
        img_thresh_mask.SetInValue(const.THRESHOLD_INVALUE)
        img_thresh_mask.SetInput(imagedata)
        img_thresh_mask.SetOutValue(const.THRESHOLD_OUTVALUE)
        img_thresh_mask.ThresholdBetween(float(thresh_min), float(thresh_max))
        img_thresh_mask.Update()
        self.img_thresh_mask = img_thresh_mask

        # copy of threshold output
        imagedata_mask = vtk.vtkImageData()
        imagedata_mask.DeepCopy(img_thresh_mask.GetOutput())
        imagedata_mask.Update()

        return imagedata_mask


    def OnExportMask(self, pubsub_evt):
        #imagedata = self.current_mask.imagedata
        imagedata = self.imagedata
        filename, filetype = pubsub_evt.data
        if (filetype == const.FILETYPE_IMAGEDATA):
            iu.Export(imagedata, filename)
