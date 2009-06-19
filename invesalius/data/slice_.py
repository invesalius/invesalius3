import random

import vtk
import wx.lib.pubsub as ps

import constants as const
from mask import Mask
from project import Project
from utils import Singleton


class Slice(object):
    __metaclass__= Singleton
    # Only one project will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it

    def __init__(self):
        self.imagedata = None
        self.__bind_events()

    def __bind_events(self):
        ps.Publisher().subscribe(self.SetThresholdRange, 'Set threshold values')
        #ps.Publisher().subscribe(self.SetEditionThresholdRange,
        #                         'Set edition threshold values')
        ps.Publisher().subscribe(self.OnChangeCurrentMaskColour,
                                 'Change mask colour')
        ps.Publisher().subscribe(self.AddMask, 'Create new mask')
        ps.Publisher().subscribe(self.OnChangeCurrentMask, 'Change mask selected')
        ps.Publisher().subscribe(self.CreateSurfaceFromIndex,
                                 'Create surface from index')
        ps.Publisher().subscribe(self.UpdateCursorPosition,
                                 'Update cursor position in slice')

    def CreateSurfaceFromIndex(self, pubsub_evt):
        mask_index = pubsub_evt.data

        proj = Project()
        mask = proj.mask_dict[mask_index]
    
        # This is very important. Do not use masks' imagedata. It would mess up
        # surface quality event when using contour
        imagedata = self.imagedata
        
        colour = mask.colour
        threshold = mask.threshold_range

        ps.Publisher().sendMessage('Create surface', (imagedata,colour,threshold))

    def OnChangeCurrentMaskColour(self, pubsub_evt):
        colour_wx = pubsub_evt.data
        colour_vtk = [c/255.0 for c in colour_wx]
        self.ChangeCurrentMaskColour(colour_vtk)

    def OnChangeCurrentMask(self, pubsub_evt):

        mask_index = pubsub_evt.data

        # This condition is not necessary in Linux, only under mac and windows
        # in these platforms, because the combobox event is binded when the
        # same item is selected again.
        if mask_index != self.current_mask.index:
            proj = Project()
            future_mask = proj.GetMask(mask_index)

            self.current_mask = future_mask

            colour = future_mask.colour
            self.ChangeCurrentMaskColour(colour)

            imagedata = future_mask.imagedata
            self.img_colours_mask.SetInput(imagedata)

            ps.Publisher().sendMessage('Set mask threshold in notebook',
                                        (self.current_mask.index,
                                            self.current_mask.threshold_range))
            ps.Publisher().sendMessage('Set threshold values in gradient',
                                        self.current_mask.threshold_range)
            ps.Publisher().sendMessage('Update slice viewer')

    def ChangeCurrentMaskColour(self, colour):
        try:
            self.current_mask
        except AttributeError:
            pass
        else:
            (r,g,b) = colour
            scalar_range = int(self.imagedata.GetScalarRange()[1])
            self.current_mask.colour = colour

            self.lut_mask.SetTableValue(1, r, g, b, 1.0)
            self.lut_mask.SetTableValue(scalar_range - 1, r, g, b, 1.0)

            colour_wx = [r*255, g*255, b*255]
            ps.Publisher().sendMessage('Change mask colour in notebook',
                                       (self.current_mask.index, (r,g,b)))
            ps.Publisher().sendMessage('Set GUI items colour', colour_wx)
            ps.Publisher().sendMessage('Update slice viewer')


    def GetOutput(self):
        return self.blend_imagedata.GetOutput()

    def SetInput(self, imagedata):
        self.imagedata = imagedata
        self.extent = imagedata.GetExtent()

        imagedata_bg = self.__create_background(imagedata)
        imagedata_mask = self.__create_mask(imagedata)

        mask_opacity = self.current_mask.opacity

        # blend both imagedatas, so it can be inserted into viewer
        blend_imagedata = vtk.vtkImageBlend()
        blend_imagedata.SetBlendModeToNormal()
        blend_imagedata.SetOpacity(0, 1)
        blend_imagedata.SetOpacity(1, mask_opacity)
        blend_imagedata.SetInput(0, imagedata_bg)
        blend_imagedata.SetInput(1, imagedata_mask)
        blend_imagedata.SetBlendModeToNormal()
        blend_imagedata.GetOutput().ReleaseDataFlagOn()
        #self.blend_imagedata = blend_imagedata


        #blend_imagedata.GetExtent()

        # global values
        CURSOR_X = 0 # SAGITAL
        CURSOR_Y = 0 # CORONAL
        CURSOR_Z = 0 # AXIAL

        CURSOR_VALUE = 4095
        CURSOR_RADIUS = 1000

        cross = vtk.vtkImageCursor3D()
        cross.GetOutput().ReleaseDataFlagOn()
        cross.SetInput(blend_imagedata.GetOutput())   
        cross.SetCursorPosition(CURSOR_X, CURSOR_Y, CURSOR_Z)
        cross.SetCursorValue(CURSOR_VALUE)
        cross.SetCursorRadius(CURSOR_RADIUS)                                         
        cross.Modified()
        self.cross = cross
        
        cast = vtk.vtkImageCast()        
        cast.SetInput(cross.GetOutput())
        cast.GetOutput().SetUpdateExtentToWholeExtent()
        cast.SetOutputScalarTypeToUnsignedChar()        
        cast.Update()
        
        self.blend_imagedata = cast


    def UpdateCursorPosition(self, pubsub_evt):

        new_pos = pubsub_evt.data
        self.cross.SetCursorPosition(new_pos)
        self.cross.Modified()
        self.blend_imagedata.Update()
        ps.Publisher().sendMessage('Update slice viewer', None)
        
        

    def __create_background(self, imagedata):

        thresh_min, thresh_max = imagedata.GetScalarRange()
        ps.Publisher().sendMessage('Update threshold limits list', (thresh_min,
                                    thresh_max))

        # map scalar values into colors
        lut_bg = vtk.vtkLookupTable()
        lut_bg.SetTableRange(thresh_min, thresh_max)
        lut_bg.SetSaturationRange(0, 0)
        lut_bg.SetHueRange(0, 0)
        lut_bg.SetValueRange(0, 1)
        lut_bg.Build()

        # map the input image through a lookup table
        img_colours_bg = vtk.vtkImageMapToColors()
        img_colours_bg.SetOutputFormatToRGBA()
        img_colours_bg.SetLookupTable(lut_bg)
        img_colours_bg.SetInput(imagedata)

        return img_colours_bg.GetOutput()

    def AddMask(self, pubsub_evt):
        mask_name = pubsub_evt.data
        self.CreateMask(name=mask_name)
        self.ChangeCurrentMaskColour(self.current_mask.colour)

    def CreateMask(self, imagedata=None, name=None):

        future_mask = Mask()

        # this is not the first mask, so we will import data from old imagedata
        if imagedata is None:

            old_mask = self.current_mask

            imagedata = old_mask.imagedata

            future_mask.threshold_range = old_mask.threshold_range

        # if not defined in the method call, this will have been computed on
        # previous if
        #future_mask.imagedata = imagedata
        future_mask.imagedata = vtk.vtkImageData()
        future_mask.imagedata.DeepCopy(imagedata)
        future_mask.imagedata.Update()

        # when this is not the first instance, user will have defined a name
        if name is not None:
            future_mask.name = name

        # insert new mask into project and retrieve its index
        proj = Project()
        proj.AddMask(future_mask.index, future_mask)


        imagedata1 = proj.mask_dict[0].imagedata

        # update gui related to mask
        ps.Publisher().sendMessage('Add mask',
                                    (future_mask.index,
                                     future_mask.name,
                                     future_mask.threshold_range,
                                     future_mask.colour))

        self.current_mask = future_mask



    def __create_mask(self, imagedata):
        # create new mask instance and insert it into project
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

        # threshold pipeline
        mask_thresh_imagedata = self.__create_mask_threshold(imagedata)
        current_mask.imagedata.DeepCopy(mask_thresh_imagedata)

        #import time
        #viewer = vtk.vtkImageViewer()
        #viewer.SetInput(mask_thresh_imagedata)
        #viewer.SetColorWindow(400)
        #viewer.SetColorLevel(200)
        #viewer.Render()
        #time.sleep(5)


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

    def SetThresholdRange(self, evt_pubsub):
        thresh_min, thresh_max = evt_pubsub.data

        self.img_thresh_mask.SetInput(self.imagedata)
        self.img_thresh_mask.ThresholdBetween(float(thresh_min),
                                              float(thresh_max))
        self.img_thresh_mask.Update()

        imagedata = self.img_thresh_mask.GetOutput()

        self.current_mask.imagedata.DeepCopy(imagedata)

        self.img_colours_mask.SetInput(self.current_mask.imagedata)

        # save new data inside current mask
        self.current_mask.threshold_range = (thresh_min, thresh_max)

        ps.Publisher().sendMessage('Set mask threshold in notebook',
                                   (self.current_mask.index,
                                     self.current_mask.threshold_range))
        ps.Publisher().sendMessage('Update slice viewer')

    #def SetEditionThresholdRange(self, evt):
    #    thresh_min, thresh_max = evt.data
    #    self.current_mask.edition_threshold_range = thresh_min, thresh_max

    def ErasePixel(self, x, y, z):
        """
        Delete pixel, based on x, y and z position coordinates.
        """
        colour = imagedata.GetScalarRange()[0]
        self.imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        self.imagedata.Update()

    def DrawPixel(self, x, y, z, colour=None):
        """
        Draw pixel, based on x, y and z position coordinates.
        """
        if colour is None:
            colour = imagedata.GetScalarRange()[1]
        self.imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)

    def EditPixelBasedOnThreshold(self, x, y, z):
        """
        Erase or draw pixel based on edition threshold range.
        """
        pixel_colour = self.imagedata.GetScalarComponentAsDouble(x, y, z, 0)
        thresh_min, thresh_max = self.current_mask.edition_threshold_range

        if (pixel_colour >= thresh_min) and (pixel_colour <= thresh_max):
            self.DrawPixel(x, y, z, pixel_colour)
            # TODO: See if the code bellow is really necessary
            #if (pixel_colour <= 0):
            #    self.DrawPixel(x, y, z, 1)
            #else:
            #    self.DrawPixel(x, y, z, pixel_colour)
        else:
            self.ErasePixel(x, y, z)
