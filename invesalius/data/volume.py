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
import plistlib
import os

import vtk
import wx
import wx.lib.pubsub as ps

import constants as const
from data import vtk_utils
import project as prj

Kernels = { 
    "Basic Smooth 5x5" : [1.0, 1.0, 1.0, 1.0, 1.0,
                          1.0, 4.0, 4.0, 4.0, 1.0,
                          1.0, 4.0, 12.0, 4.0, 1.0,
                          1.0, 4.0, 4.0, 4.0, 1.0,
                          1.0, 1.0, 1.0, 1.0, 1.0]
}

SHADING = {
    "Default": {
        "ambient"       :0.15,
        "diffuse"       :0.9,
        "specular"      :0.3,
        "specularPower" :15,
    },

    "Glossy Vascular":{
        "ambient"       :0.15,
        "diffuse"       :0.28,
        "specular"      :1.42,
        "specularPower" :50,
    },

    "Glossy Bone": {
        "ambient"       :0.15,
        "diffuse"       :0.24,
        "specular"      :1.17,
        "specularPower" :6.98,
    },

    "Endoscopy": {
        "ambient"       :0.12,
        "diffuse"       :0.64,
        "specular"      :0.73,
        "specularPower" :50,
    }
}


class Volume():
    
    def __init__(self):
        self.config = None
        self.exist = None
        self.color_transfer = None
        self.opacity_transfer_func = None
        self.ww = None
        self.wl = None
        self.n = 0
        self.plane = None
        self.plane_on = False
        
        self.__bind_events()
        
    def __bind_events(self):
        ps.Publisher().subscribe(self.OnHideVolume,
                                'Hide raycasting volume')
        ps.Publisher().subscribe(self.OnUpdatePreset,
                                'Update raycasting preset')
        ps.Publisher().subscribe(self.OnSetWindowLevel,
                                'Set raycasting wwwl')
        ps.Publisher().subscribe(self.Refresh,
                                'Set raycasting refresh')
        ps.Publisher().subscribe(self.OnSetRelativeWindowLevel,
                                 'Set raycasting relative window and level')
        ps.Publisher().subscribe(self.OnEnableTool,
                                 'Enable raycasting tool')

    def OnLoadVolume(self, pubsub_evt):
        label = pubsub_evt.data
        #self.LoadConfig(label)
        self.LoadVolume()

    def OnHideVolume(self, pubsub_evt):
        self.volume.SetVisibility(0)
        if (self.plane and self.plane_on):
            self.plane.Disable()
        ps.Publisher().sendMessage('Render volume viewer')

    def OnShowVolume(self, pubsub_evt):
        if self.exist:
            self.volume.SetVisibility(1)
            if (self.plane and self.plane_on):
                self.plane.Enable()
            ps.Publisher().sendMessage('Render volume viewer')
        else:
            ps.Publisher.sendMessage('Load raycasting preset', const.RAYCASTING_LABEL)
            self.LoadConfig()
            self.LoadVolume()
            self.exist = 1

    def OnUpdatePreset(self, pubsub_evt):
        self.__load_preset_config()
        if self.exist:
            self.__load_preset()
            self.volume.SetVisibility(1)
            ps.Publisher().sendMessage('Render volume viewer')
        else:
            self.LoadVolume()
            self.exist = 1

        if (self.plane and self.plane_on):
            self.plane.Enable()

    def __load_preset_config(self):
        self.config = prj.Project().raycasting_preset

    def __update_colour_table(self):
        if self.config['advancedCLUT']:
            self.Create16bColorTable(self.scale)
            self.CreateOpacityTable(self.scale)
        else:
            self.Create8bColorTable(self.scale)
            self.Create8bOpacityTable(self.scale)

    def __load_preset(self):   
        # Update colour table
        self.__update_colour_table()

        # Update convolution filter
        original_imagedata = self.imagedata.GetOutput()
        imagedata = self.ApplyConvolution(original_imagedata)
        self.volume_mapper.SetInput(imagedata)

        # Update other information
        self.SetShading()
        colour = self.GetBackgroundColour()
        ps.Publisher.sendMessage('Change volume viewer background colour', colour)
        ps.Publisher.sendMessage('Change volume viewer gui colour', colour)


    def OnSetRelativeWindowLevel(self, pubsub_evt):
        diff_ww, diff_wl = pubsub_evt.data
        ww = self.ww + diff_ww
        wl = self.wl + diff_wl
        ps.Publisher().sendMessage('Set volume window and level text',
                                    (ww, wl))
        self.SetWWWL(ww, wl)
        self.ww = ww
        self.wl = wl

    def OnSetWindowLevel(self, pubsub_evt):
        ww, wl, n = pubsub_evt.data
        self.n = n
        self.SetWWWL(ww,wl)

    def SetWWWL(self, ww, wl):
        
        if self.config['advancedCLUT']:
            curve = self.config['16bitClutCurves'][self.n]

            p1 = curve[0]
            p2 = curve[-1]
            half = (p2['x'] - p1['x']) / 2.0
            middle = p1['x'] + half

            shiftWL = wl - middle
            shiftWW = p1['x'] + shiftWL - (wl - 0.5 * ww)

            factor = 1.0
            for n,i in enumerate(curve):
                factor = abs(i['x'] - middle) / half
                if factor < 0:
                    factor = 0
                i['x'] += shiftWL
                if n < len(curve)/2.0:
                    i['x'] -= shiftWW * factor
                else:
                    i['x'] += shiftWW * factor
        else:
            self.config['wl'] = wl
            self.config['ww'] = ww

        self.__update_colour_table()
        ps.Publisher().sendMessage('Render volume viewer')

    def Refresh(self, pubsub_evt):
        self.__update_colour_table()

#***************
    def Create16bColorTable(self, scale):
        if self.color_transfer:
            color_transfer = self.color_transfer
        else:
            color_transfer = vtk.vtkColorTransferFunction()
        color_transfer.RemoveAllPoints()
        curve_table = self.config['16bitClutCurves']
        color_table = self.config['16bitClutColors']
        colors = []
        for i, l in enumerate(curve_table):
            for j, lopacity in enumerate(l):
                gray_level = lopacity['x']
                r = color_table[i][j]['red']
                g = color_table[i][j]['green']
                b = color_table[i][j]['blue']

                colors.append((gray_level, r, g, b))
                color_transfer.AddRGBPoint(
                    self.TranslateScale(scale, gray_level), 
                    r, g, b)
        self.color_transfer = color_transfer

    def Create8bColorTable(self, scale):
        if self.color_transfer:
            color_transfer = self.color_transfer
        else:
            color_transfer = vtk.vtkColorTransferFunction()
        color_transfer.RemoveAllPoints()
        color_preset = self.config['CLUT']
        if color_preset != "No CLUT":
            p = plistlib.readPlist(
                os.path.join(const.RAYCASTING_PRESETS_DIRECTORY,
                             'color_list', color_preset + '.plist'))
            r = p['Red']
            g = p['Green']
            b = p['Blue']
            colors = zip(r,g,b)
            ww = self.config['ww']
            wl = self.TranslateScale(scale, self.config['wl'])
            init = wl - ww/2.0
            inc = ww / (len(colors) - 1.0)
            for n,rgb in enumerate(colors):
                color_transfer.AddRGBPoint(init + n * inc, *[i/255.0 for i in rgb])
        self.color_transfer = color_transfer

    def CreateOpacityTable(self, scale):
        if self.opacity_transfer_func:
            opacity_transfer_func = self.opacity_transfer_func
        else:
            opacity_transfer_func = vtk.vtkPiecewiseFunction()
        opacity_transfer_func.RemoveAllPoints()
        curve_table = self.config['16bitClutCurves']
        opacities = []

        ww = self.config['ww']
        wl = self.config['wl']
        self.ww = ww
        self.wl = wl

        l1 = wl - ww/2.0
        l2 = wl + ww/2.0

        k1 = 0.0
        k2 = 1.0

        opacity_transfer_func.AddSegment(0, 0, 2**16-1, 0)

        for i, l in enumerate(curve_table):
            for j, lopacity in enumerate(l):
                gray_level = lopacity['x']
                #if gray_level <= l1:
                #    opacity = k1
                #elif gray_level > l2:
                #    opacity = k2
                #else:
                opacity = lopacity['y']
                opacities.append((gray_level, opacity))
                opacity_transfer_func.AddPoint(
                    self.TranslateScale(scale, gray_level), opacity)
        self.opacity_transfer_func = opacity_transfer_func

    def Create8bOpacityTable(self, scale):
        if self.opacity_transfer_func:
            opacity_transfer_func = self.opacity_transfer_func
        else:
            opacity_transfer_func = vtk.vtkPiecewiseFunction()
        opacity_transfer_func.RemoveAllPoints()
        opacities = []

        ww = self.config['ww']
        wl = self.TranslateScale(scale, self.config['wl'])

        l1 = wl - ww/2.0
        l2 = wl + ww/2.0

        self.ww = ww
        self.wl = self.config['wl']

        opacity_transfer_func.RemoveAllPoints()
        opacity_transfer_func.AddSegment(0, 0, 2**16-1, 0)

        k1 = 0.0
        k2 = 1.0

        opacity_transfer_func.AddPoint(l1, 0)
        opacity_transfer_func.AddPoint(l2, 1)

        self.opacity_transfer_func = opacity_transfer_func
        return opacity_transfer_func

    def GetBackgroundColour(self):
        colour = (self.config['backgroundColorRedComponent'],
                            self.config['backgroundColorGreenComponent'],
                            self.config['backgroundColorBlueComponent'])
        return colour

    def BuildTable():
        curve_table = p['16bitClutCurves']
        color_background = (p['backgroundColorRedComponent'],
                            p['backgroundColorGreenComponent'],
                            p['backgroundColorBlueComponent'])
        color_background = [i for i in color_background]
        opacities = []
        colors = []

        for i, l in enumerate(curve_table):
            for j, lopacity in enumerate(l):
                gray_level = lopacity['x']
                opacity = lopacity['y']

                opacities.append((gray_level, opacity))

                r = color_table[i][j]['red']
                g = color_table[i][j]['green']
                b = color_table[i][j]['blue']

                colors.append((gray_level, r, g, b))

        return colors, opacities, color_background, p['useShading']

    def SetShading(self):
        if self.config['useShading']:
            self.volume_properties.ShadeOn()
        else:
            self.volume_properties.ShadeOff()
        
        shading = SHADING[self.config['shading']]
        self.volume_properties.SetAmbient(shading['ambient'])
        self.volume_properties.SetDiffuse(shading['diffuse'])
        self.volume_properties.SetSpecular(shading['specular'])
        self.volume_properties.SetSpecularPower(shading['specularPower'])

    def ApplyConvolution(self, imagedata):
        number_filters = len(self.config['convolutionFilters'])
        if number_filters:
            update_progress= vtk_utils.ShowProgress(number_filters)
            for filter in self.config['convolutionFilters']:
                convolve = vtk.vtkImageConvolve()
                convolve.SetInput(imagedata)
                convolve.SetKernel5x5([i/60.0 for i in Kernels[filter]])
                convolve.AddObserver("ProgressEvent", lambda obj,evt:
                                     update_progress(convolve, "%s ..." % filter))
                imagedata = convolve.GetOutput()
                convolve.GetOutput().ReleaseDataFlagOn()
        return imagedata

    def LoadVolume(self):
        proj = prj.Project()
        image = proj.imagedata

        update_progress= vtk_utils.ShowProgress(4)

        # Flip original vtkImageData
        flip = vtk.vtkImageFlip()
        flip.SetInput(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.AddObserver("ProgressEvent", lambda obj,evt:
                            update_progress(flip, "Fliping ..."))
        flip.Update()
        
        image = flip.GetOutput()

        scale = image.GetScalarRange()
        self.scale = scale

        cast = vtk.vtkImageShiftScale()
        cast.SetInput(image)
        cast.SetShift(abs(scale[0]))
        cast.SetOutputScalarTypeToUnsignedShort()
        cast.AddObserver("ProgressEvent", lambda obj,evt:
                            update_progress(cast, "Casting ..."))
        cast.Update()
        image2 = cast
        self.imagedata = image2
        if self.config['advancedCLUT']:
            self.Create16bColorTable(scale)
            self.CreateOpacityTable(scale)
        else:
            self.Create8bColorTable(scale)
            self.Create8bOpacityTable(scale)
        image2 = self.ApplyConvolution(image2.GetOutput())
        self.final_imagedata = image2

        composite_function = vtk.vtkVolumeRayCastCompositeFunction()
        composite_function.SetCompositeMethodToInterpolateFirst()

        gradientEstimator = vtk.vtkFiniteDifferenceGradientEstimator()
        gradientEstimator.SetGradientMagnitudeScale(1)

        # Changed the vtkVolumeRayCast to vtkFixedPointVolumeRayCastMapper
        # because it's faster and the image is better
        # TODO: To test if it's true.
        if const.TYPE_RAYCASTING_MAPPER:
            volume_mapper = vtk.vtkVolumeRayCastMapper()
            #volume_mapper.AutoAdjustSampleDistancesOff()
            volume_mapper.SetInput(image2)
            volume_mapper.SetVolumeRayCastFunction(composite_function)
            #volume_mapper.SetGradientEstimator(gradientEstimator)
            volume_mapper.IntermixIntersectingGeometryOn()
        else:
            volume_mapper = vtk.vtkFixedPointVolumeRayCastMapper()
            #volume_mapper.AutoAdjustSampleDistancesOff()
            volume_mapper.SetInput(image2)
            volume_mapper.IntermixIntersectingGeometryOn()

        volume_mapper.AddObserver("ProgressEvent", lambda obj,evt:
                                  update_progress(volume_mapper, "Mapper ..."))
        self.volume_mapper = volume_mapper

        # TODO: Look to this
        #volume_mapper = vtk.vtkVolumeTextureMapper2D()
        #volume_mapper.SetInput(image2.GetOutput())

        #Cut Plane
        #CutPlane(image2, volume_mapper)
        
        #self.color_transfer = color_transfer

        volume_properties = vtk.vtkVolumeProperty()
        #volume_properties.IndependentComponentsOn()
        if self.config['useShading']:
            volume_properties.ShadeOn()
        else:
            volume_properties.ShadeOff()

        volume_properties.SetInterpolationTypeToLinear()
        volume_properties.SetColor(self.color_transfer)

        try:
            volume_properties.SetScalarOpacity(self.opacity_transfer_func)
        except NameError:
            pass

        # Using these lines to improve the raycasting quality. These values
        # seems related to the distance from ray from raycasting.
        # TODO: Need to see values that improve the quality and don't decrease
        # the performance. 2.0 seems to be a good value to pix_diag
        pix_diag = 2.0
        volume_mapper.SetImageSampleDistance(0.25)
        volume_mapper.SetSampleDistance(pix_diag / 5.0)
        volume_properties.SetScalarOpacityUnitDistance(pix_diag)

        self.volume_properties = volume_properties

        volume = vtk.vtkVolume()
        volume.SetMapper(volume_mapper)
        volume.SetProperty(volume_properties)
        volume.AddObserver("ProgressEvent", lambda obj,evt:
                                  update_progress(volume, "Volume ..."))
        self.volume = volume
        
        colour = self.GetBackgroundColour()

        ps.Publisher().sendMessage('Load volume into viewer',
                                    (volume, colour, (self.ww, self.wl)))

    def OnEnableTool(self, pubsub_evt):
        print "OnEnableTool"
        tool_name, enable = pubsub_evt.data
        if tool_name == "Cut plane":
            if self.plane:
                if enable:
                    print "Enable"
                    self.plane_on = True
                    self.plane.Enable()
                else:
                    print "Disable"
                    self.plane_on = False
                    self.plane.Disable()
            else:
                print "Enable"
                self.plane_on = True
                self.plane = CutPlane(self.final_imagedata,
                                      self.volume_mapper)


    def TranslateScale(self, scale, value):
        #if value < 0:
        #    valor = 2**16 - abs(value)
        #else:
        #    valor = value 
        return value - scale[0]
   
        
class CutPlane: 
    def __init__(self, img, volume_mapper):
        self.img = img
        self.volume_mapper = volume_mapper
        self.Create()
        self.__bind_events()
    
    def __bind_events(self):
        ps.Publisher().subscribe(self.Reset,
                                'Reset Cut Plane')
        ps.Publisher().subscribe(self.Enable,
                                'Enable Cut Plane')
        ps.Publisher().subscribe(self.Disable,
                                'Disable Cut Plane')
            
    def Create(self):
        self.plane_widget = plane_widget = vtk.vtkImagePlaneWidget()
        plane_widget.SetInput(self.img)
        plane_widget.SetPlaneOrientationToXAxes()
        #plane_widget.SetResliceInterpolateToLinear()
        plane_widget.TextureVisibilityOff()
        #Set left mouse button to move and rotate plane
        plane_widget.SetLeftButtonAction(1)
        #SetColor margin to green
        margin_property = plane_widget.GetMarginProperty()
        margin_property.SetColor(0,0.8,0)
        #Disable cross
        cursor_property = plane_widget.GetCursorProperty()
        cursor_property.SetOpacity(0) 
        self.plane_source = plane_source = vtk.vtkPlaneSource()
        plane_source.SetOrigin(plane_widget.GetOrigin())
        plane_source.SetPoint1(plane_widget.GetPoint1())
        plane_source.SetPoint2(plane_widget.GetPoint2())
        plane_source.SetNormal(plane_widget.GetNormal())
        plane_mapper = vtk.vtkPolyDataMapper()
        plane_mapper.SetInput(plane_source.GetOutput())
        self.plane_actor = plane_actor = vtk.vtkActor()
        plane_actor.SetMapper(plane_mapper)
        plane_actor.GetProperty().BackfaceCullingOn()
        plane_actor.GetProperty().SetOpacity(0)
        plane_widget.AddObserver("InteractionEvent", self.Update)
        ps.Publisher().sendMessage('AppendActor', self.plane_actor)
        ps.Publisher().sendMessage('Set Widget Interactor', self.plane_widget)
        plane_actor.SetVisibility(1)
        plane_widget.On() 
        self.plane = plane = vtk.vtkPlane()
        plane.SetNormal(self.plane_source.GetNormal())
        plane.SetOrigin(self.plane_source.GetOrigin())
        self.volume_mapper.AddClippingPlane(plane) 
        #Storage First Position
        self.origin = plane_widget.GetOrigin()
        self.p1 = plane_widget.GetPoint1()
        self.p2 = plane_widget.GetPoint2()
        self.normal = plane_widget.GetNormal()
        
    def Update(self, a, b):        
        plane_source = self.plane_source
        plane_widget = self.plane_widget
        plane_source.SetOrigin(plane_widget.GetOrigin())
        plane_source.SetPoint1(plane_widget.GetPoint1())
        plane_source.SetPoint2(plane_widget.GetPoint2())
        plane_source.SetNormal(plane_widget.GetNormal())        
        self.plane_actor.VisibilityOn()
        self.plane.SetNormal(plane_source.GetNormal())
        self.plane.SetOrigin(plane_source.GetOrigin())
        ps.Publisher().sendMessage('Render volume viewer', None)
        
    def Enable(self, evt_pubsub=None):
        self.plane_widget.On()
        self.plane_actor.VisibilityOn()
        self.volume_mapper.RemoveClippingPlane(self.plane)
        ps.Publisher().sendMessage('Render volume viewer', None)
        
    def Disable(self,evt_pubsub=None):
        self.plane_widget.Off() 
        self.plane_actor.VisibilityOff()
        self.volume_mapper.AddClippingPlane(self.plane)
        ps.Publisher().sendMessage('Render volume viewer', None)
        
    def Reset(self, evt_pubsub=None):
        plane_source = self.plane_source
        plane_widget = self.plane_widget
        plane_source.SetOrigin(self.origin)
        plane_source.SetPoint1(self.p1)
        plane_source.SetPoint2(self.p2)
        plane_source.SetNormal(self.normal)        
        self.plane_actor.VisibilityOn() 
        self.plane.SetNormal(self.normal)
        self.plane.SetOrigin(self.origin)
        ps.Publisher().sendMessage('Render volume viewer', None)     

