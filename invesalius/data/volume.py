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
import wx.lib.pubsub as ps

from project import Project

Kernels = { 
    "Basic Smooth 5x5" : [1.0, 1.0, 1.0, 1.0, 1.0,
                          1.0, 4.0, 4.0, 4.0, 1.0,
                          1.0, 4.0, 12.0, 4.0, 1.0,
                          1.0, 4.0, 4.0, 4.0, 1.0,
                          1.0, 1.0, 1.0, 1.0, 1.0]
}


PRESETS = ["Airways", "Airways II", "Bone + Skin", "Bone + Skin II", "Dark Bone",
"Gold Bone", "Skin On Blue", "Skin On Blue II", "Soft + Skin", "Soft + Skin II",
"Soft + Skin III", "Yellow Bone"]

class Volume():
    
    def __init__(self):
        self.config = None
        self.exist = None
        
        self.__bind_events()
        
    def __bind_events(self):
        #ps.Publisher().subscribe(self.OnLoadVolume, 'Create volume raycasting')
        ps.Publisher().subscribe(self.OnShowVolume,
                                'Show raycasting volume')
        ps.Publisher().subscribe(self.OnHideVolume,
                                'Hide raycasting volume')


    def OnLoadVolume(self, pubsub_evt):
        label = pubsub_evt.data
        self.LoadConfig(label)
        self.LoadVolume()

    def LoadConfig(self, label):
        if not label:
            label = "Skin on Blue"

        path = os.path.abspath("../presets/raycasting/"+label+".plist")
        self.config = plistlib.readPlist(path)
        
    def OnHideVolume(self, pubsub_evt):
        self.volume.SetVisibility(0)
        ps.Publisher().sendMessage('Render volume viewer')
        
    def OnShowVolume(self, pubsub_evt):
        if self.exist:        
            self.volume.SetVisibility(1)
            ps.Publisher().sendMessage('Render volume viewer')
        else:
            self.LoadConfig(None)
            self.LoadVolume()
            self.exist = 1
            
        
#***************
    def Create16bColorTable(self, scale):
        color_transfer = vtk.vtkColorTransferFunction()
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
        return color_transfer

    def Create8bColorTable(self):
        color_transfer = vtk.vtkColorTransferFunction()
        color_preset = self.config['CLUT']
        p = plistlib.readPlist( os.path.join('ColorList', color_preset + '.plist'))
        r = p['Red']
        g = p['Green']
        b = p['Blue']
        colors = zip(r,g,b)
        for i,rgb in enumerate(colors):
            color_transfer.AddRGBPoint(i, *rgb)
        return color_transfer

    def CreateOpacityTable(self, scale):
        opacity_transfer_func = vtk.vtkPiecewiseFunction()
        curve_table = self.config['16bitClutCurves']
        opacities = []

        ww = self.config['ww']
        wl = self.config['wl']

        l1 = wl - ww/2.0
        l2 = wl + ww/2.0

        k1 = 0.0
        k2 = 1.0

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
        return opacity_transfer_func

    def Create8bOpacityTable(self):
        opacity_transfer_func = vtk.vtkPiecewiseFunction()
        opacities = []

        ww = self.config['ww']
        wl = self.config['wl']

        print ww, wl

        l1 = wl - ww/2.0
        l2 = wl + ww/2.0

        k1 = 0.0
        k2 = 1.0

        opacity_transfer_func.AddPoint(0, 0)
        opacity_transfer_func.AddPoint(l1-1, 0)
        opacity_transfer_func.AddPoint(l1, 1)
        opacity_transfer_func.AddPoint(l2, 1)
        opacity_transfer_func.AddPoint(l2+1, 0)
        opacity_transfer_func.AddPoint(255, 0)

        return opacity_transfer_func

    def CreateBackgroundColor(self):
        color_background = (self.config['backgroundColorRedComponent'],
                            self.config['backgroundColorGreenComponent'],
                            self.config['backgroundColorBlueComponent'])
        return color_background


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



    def LoadVolume(self):
        proj = Project()
        image = proj.imagedata

        # Flip original vtkImageData
        flip = vtk.vtkImageFlip()
        flip.SetInput(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.Update()
        
        image = flip.GetOutput()


        scale = image.GetScalarRange()

        cast = vtk.vtkImageShiftScale()
        cast.SetInput(image)
        if self.config['advancedCLUT']:
            cast.SetShift(abs(scale[0]))
            #cast.SetScale(2**16-1)
            cast.SetOutputScalarTypeToUnsignedShort()
            #scale = image.GetScalarRange()
            color_transfer = self.Create16bColorTable(scale)
            opacity_transfer_func = self.CreateOpacityTable(scale)
            cast.Update()
            image2 = cast
        else:
            cast.SetShift(abs(scale[0]))
            cast.SetScale(255.0/(scale[1] - scale[0]))
            cast.SetOutputScalarTypeToUnsignedChar()
            color_transfer = self.Create8bColorTable()
            opacity_transfer_func = self.Create8bOpacityTable()
            cast.Update()
            image2 = cast
        #cast.ClampOverflowOff()

        convolve = vtk.vtkImageConvolve()
        convolve.SetInput(image2.GetOutput())
        convolve.SetKernel5x5([i/60.0 for i in Kernels[self.config['convolutionFilters'][0]]])
        convolve.Update()

        image2 = convolve
        
        composite_function = vtk.vtkVolumeRayCastCompositeFunction()
        composite_function.SetCompositeMethodToClassifyFirst()

        gradientEstimator = vtk.vtkFiniteDifferenceGradientEstimator()
        gradientEstimator.SetGradientMagnitudeScale(1)

        volume_mapper = vtk.vtkVolumeRayCastMapper()
        #volume_mapper.AutoAdjustSampleDistancesOff()
        volume_mapper.SetInput(image2.GetOutput())
        volume_mapper.SetVolumeRayCastFunction(composite_function)
        volume_mapper.SetGradientEstimator(gradientEstimator)
        volume_mapper.IntermixIntersectingGeometryOn()

        #clip = vtk.vtkPlane()

        #volume_mapper.AddClippingPlane(clip)

        self.color_transfer = color_transfer

        volume_properties = vtk.vtkVolumeProperty()
        #volume_properties.IndependentComponentsOn()
        if self.config['useShading']:
            volume_properties.ShadeOn()
        else:
            volume_properties.ShadeOff()
        volume_properties.SetAmbient(0.1)
        volume_properties.SetDiffuse(0.6)
        volume_properties.SetSpecular(0.5)
        volume_properties.SetSpecularPower(44.0)

        volume_properties.SetInterpolationTypeToLinear()
        volume_properties.SetColor(color_transfer)

        try:
            volume_properties.SetScalarOpacity(opacity_transfer_func)
        except NameError:
            pass

        self.volume_properties = volume_properties

        volume = vtk.vtkVolume()
        volume.SetMapper(volume_mapper)
        volume.SetProperty(volume_properties)
        self.volume = volume
        
        colour = self.CreateBackgroundColor()
        ps.Publisher().sendMessage('Load volume into viewer', (volume, colour))
        

    def TranslateScale(self, scale, value):
        #if value < 0:
        #    valor = 2**16 - abs(value)
        #else:
        #    valor = value
        
        return value - scale[0]





