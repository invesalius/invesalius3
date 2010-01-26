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
import random

import vtk
import wx.lib.pubsub as ps

import constants as const
import imagedata_utils as iu
from mask import Mask
import style as st
from project import Project
import session as ses
from utils import Singleton


class Slice(object):
    __metaclass__= Singleton
    # Only one slice will be initialized per time (despite several viewers
    # show it from distinct perspectives).
    # Therefore, we use Singleton design pattern for implementing it.

    def __init__(self):
        self.imagedata = None
        self.current_mask = None
        self.blend_filter = None

        self.num_gradient = 0
        self.interaction_style = st.StyleStateManager()

        self.__bind_events()

    def __bind_events(self):
        # Slice properties
        ps.Publisher().subscribe(self.UpdateCursorPosition,
                                 'Update cursor position in slice')
        ps.Publisher().subscribe(self.UpdateCursorPositionSingleAxis,
                                 'Update cursor single position in slice')

        # General slice control
        ps.Publisher().subscribe(self.CreateSurfaceFromIndex,
                                 'Create surface from index')
        # Mask control
        ps.Publisher().subscribe(self.__add_mask, 'Create new mask')
        ps.Publisher().subscribe(self.__select_current_mask,
                                 'Change mask selected')
        # Mask properties
        ps.Publisher().subscribe(self.__set_current_mask_edition_threshold,
                                 'Set edition threshold values')
        ps.Publisher().subscribe(self.__set_current_mask_threshold,
                                 'Set threshold values')
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
        session = ses.Session()
        #FIXME: find a better way to implement this
        if (self.num_gradient >= 2) or \
        (session.project_status != const.PROJ_OPEN):
            threshold_range = evt_pubsub.data
            index = self.current_mask.index
            self.SetMaskThreshold(index, threshold_range)
            #Clear edited points
            self.current_mask.edited_points = {}
        self.num_gradient += 1
            
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


    def SetMaskColour(self, index, colour, update=True):
        "Set a mask colour given its index and colour (RGB 0-1 values)"
        proj = Project()
        proj.mask_dict[index].colour = colour

        (r,g,b) = colour
        scalar_range = int(self.imagedata.GetScalarRange()[1])
        self.lut_mask.SetTableValue(1, r, g, b, 1.0)
        self.lut_mask.SetTableValue(scalar_range - 1, r, g, b, 1.0)

        colour_wx = [r*255, g*255, b*255]
        ps.Publisher().sendMessage('Change mask colour in notebook',
                                    (self.current_mask.index, (r,g,b)))
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

    def SetMaskThreshold(self, index, threshold_range):
        """
        Set a mask threshold range given its index and tuple of min and max
        threshold values.
        """
        thresh_min, thresh_max = threshold_range

        if self.current_mask.index == index:
            # Update pipeline (this must be here, so pipeline is not broken)
            self.img_thresh_mask.SetInput(self.imagedata)
            self.img_thresh_mask.ThresholdBetween(float(thresh_min),
                                                  float(thresh_max))
            self.img_thresh_mask.Update()

            # Create imagedata copy so the pipeline is not broken
            imagedata = self.img_thresh_mask.GetOutput()
            self.current_mask.imagedata.DeepCopy(imagedata)
            self.current_mask.threshold_range = threshold_range

            # Update pipeline (this must be here, so pipeline is not broken)
            self.img_colours_mask.SetInput(self.current_mask.imagedata)

            # Update viewer
            ps.Publisher().sendMessage('Update slice viewer')

            # Update data notebook (GUI)
            ps.Publisher().sendMessage('Set mask threshold in notebook',
                                (self.current_mask.index,
                                self.current_mask.threshold_range))
        else:
            proj = Project()
            proj.mask_dict[index].threshold_range = threshold_range
       
        proj = Project()
        proj.mask_dict[self.current_mask.index].threshold_range = threshold_range
   
        session = ses.Session()
        session.ChangeProject()


 

    def ShowMask(self, index, value):
        "Show a mask given its index and 'show' value (0: hide, other: show)"
        proj = Project()
        proj.mask_dict[index].is_shown = value
        if (index == self.current_mask.index):
            if value:
                self.blend_filter.SetOpacity(1, self.current_mask.opacity)
            else:
                self.blend_filter.SetOpacity(1, 0)
            self.blend_filter.Update()
            ps.Publisher().sendMessage('Update slice viewer')
    #---------------------------------------------------------------------------
    def ErasePixel(self, position):
        "Delete pixel, based on x, y and z position coordinates."
        x, y, z = position
        colour = self.imagedata.GetScalarRange()[0]
        imagedata = self.current_mask.imagedata
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        self.current_mask.edited_points[(x, y, z)] = colour
        
        session = ses.Session()
        session.ChangeProject()


    def DrawPixel(self, position, colour=None):
        "Draw pixel, based on x, y and z position coordinates."
        x, y, z = position
        colour = self.imagedata.GetScalarRange()[1]
        imagedata = self.current_mask.imagedata
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        self.current_mask.edited_points[(x, y, z)] = colour

        session = ses.Session()
        session.ChangeProject()


    def EditPixelBasedOnThreshold(self, position):
        "Erase or draw pixel based on edition threshold range."
        x, y, z = position
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
        if self.current_mask and self.blend_filter:
            proj = Project()
            future_mask = proj.GetMask(index)

            self.current_mask = future_mask

            colour = future_mask.colour
            index = future_mask.index
            self.SetMaskColour(index, colour, update=False)

            imagedata = future_mask.imagedata
            self.img_colours_mask.SetInput(imagedata)

            if self.current_mask.is_shown:
                self.blend_filter.SetOpacity(1, self.current_mask.opacity)
            else:

                self.blend_filter.SetOpacity(1, 0)
            self.blend_filter.Update()

            ps.Publisher().sendMessage('Set mask threshold in notebook',
                                        (self.current_mask.index,
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
        imagedata = self.imagedata

        colour = mask.colour
        threshold = mask.threshold_range
        edited_points = mask.edited_points

        ps.Publisher().sendMessage('Create surface',
                                   (imagedata,colour,threshold,
                                    edited_points, overwrite_surface))

    def GetOutput(self):
        return self.cross.GetOutput()



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

        # global values
        CURSOR_X = -1 # SAGITAL
        CURSOR_Y = -1 # CORONAL
        CURSOR_Z = -1 # AXIAL

        CURSOR_VALUE = 4095
        CURSOR_RADIUS = 1000

        cross = vtk.vtkImageCursor3D()
        cross.GetOutput().ReleaseDataFlagOn()
        cross.SetInput(blend_filter.GetOutput())
        cross.SetCursorPosition(CURSOR_X, CURSOR_Y, CURSOR_Z)
        cross.SetCursorValue(CURSOR_VALUE)
        cross.SetCursorRadius(CURSOR_RADIUS)
        cross.Modified()
        self.cross = cross

        self.window_level = vtk.vtkImageMapToWindowLevelColors()
        self.window_level.SetInput(self.imagedata)


    def UpdateCursorPosition(self, pubsub_evt):

        new_pos = pubsub_evt.data
        self.cross.SetCursorPosition(new_pos)
        self.cross.Modified()
        self.cross.Update()
        ps.Publisher().sendMessage('Update slice viewer')

    def UpdateCursorPositionSingleAxis(self, pubsub_evt):
        axis_pos = pubsub_evt.data
        x, y, z = self.cross.GetCursorPosition()
        new_pos = [x,y,z]
        for key in axis_pos:
            new_pos[key] = axis_pos[key]
        self.cross.SetCursorPosition(new_pos)
        self.cross.Modified()
        self.cross.Update()
        ps.Publisher().sendMessage('Update slice viewer')


    def __create_background(self, imagedata):
        self.imagedata = imagedata

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
        window_level = self.window_level

        if not((window == window_level.GetWindow()) and\
                (level == window_level.GetLevel())):

            window_level.SetWindow(window)
            window_level.SetLevel(level)
            window_level.SetOutputFormatToLuminance()
            window_level.Update()

            thresh_min, thresh_max = window_level.GetOutput().GetScalarRange()
            self.lut_bg.SetTableRange(thresh_min, thresh_max)
            self.img_colours_bg.SetInput(window_level.GetOutput())

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
        widget = pubsub_evt.data
        
        flip = vtk.vtkImageFlip()
        flip.SetInput(self.window_level.GetOutput())
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.Update()
        
        widget.SetInput(flip.GetOutput())
 
    
    def CreateMask(self, imagedata=None, name=None):

        future_mask = Mask()

        # this is not the first mask, so we will import data from old imagedata
        if imagedata is None:

            old_mask = self.current_mask

            imagedata = old_mask.imagedata

            future_mask.threshold_range = old_mask.threshold_range

        # if not defined in the method call, this will have been computed on
        # previous if
        future_mask.imagedata = vtk.vtkImageData()
        future_mask.imagedata.DeepCopy(imagedata)
        future_mask.imagedata.Update()

        # when this is not the first instance, user will have defined a name
        if name is not None:
            future_mask.name = name
            if future_mask.is_shown:
                self.blend_filter.SetOpacity(1, future_mask.opacity)
            else:
                self.blend_filter.SetOpacity(1, 0)
            self.blend_filter.Update()

        # insert new mask into project and retrieve its index
        proj = Project()
        index = proj.AddMask(future_mask)
        future_mask.index = index

        # update gui related to mask
        ps.Publisher().sendMessage('Add mask',
                                    (future_mask.index,
                                     future_mask.name,
                                     future_mask.threshold_range,
                                     future_mask.colour))

        self.current_mask = future_mask

        ps.Publisher().sendMessage('Change mask selected', future_mask.index)
        ps.Publisher().sendMessage('Update slice viewer')


    def __load_masks(self, imagedata, mask_dict):
        keys = mask_dict.keys()
        keys.sort()
        for key in keys:
            mask = mask_dict[key]
        
            # update gui related to mask
            print "__load_masks"
            print 'THRESHOLD_RANGE', mask.threshold_range
            ps.Publisher().sendMessage('Add mask',
                                    (mask.index,
                                     mask.name,
                                     mask.threshold_range,
                                     mask.colour))

        self.current_mask = mask
        self.__build_mask(imagedata, False)

        ps.Publisher().sendMessage('Change mask selected', mask.index)
        ps.Publisher().sendMessage('Update slice viewer')

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


    def __create_mask_threshold(self, imagedata):
        thresh_min, thresh_max = self.current_mask.threshold_range

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




