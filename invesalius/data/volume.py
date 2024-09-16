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
import plistlib
import weakref

from packaging.version import Version
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkVersion
from vtkmodules.vtkCommonDataModel import vtkPiecewiseFunction, vtkPlane
from vtkmodules.vtkFiltersSources import vtkPlaneSource
from vtkmodules.vtkImagingCore import vtkImageFlip, vtkImageShiftScale
from vtkmodules.vtkImagingGeneral import vtkImageConvolve
from vtkmodules.vtkImagingStatistics import vtkImageAccumulate
from vtkmodules.vtkInteractionWidgets import vtkImagePlaneWidget
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkColorTransferFunction,
    vtkPolyDataMapper,
    vtkVolume,
    vtkVolumeProperty,
)
from vtkmodules.vtkRenderingVolume import (
    vtkFixedPointVolumeRayCastMapper,
    vtkGPUVolumeRayCastMapper,
)
from vtkmodules.vtkRenderingVolumeOpenGL2 import vtkOpenGLGPUVolumeRayCastMapper

import invesalius.constants as const
import invesalius.data.converters as converters
import invesalius.data.slice_ as slice_
import invesalius.data.vtk_utils as vtk_utils
import invesalius.project as prj
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

Kernels = {
    "Basic Smooth 5x5": [
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        4.0,
        4.0,
        4.0,
        1.0,
        1.0,
        4.0,
        12.0,
        4.0,
        1.0,
        1.0,
        4.0,
        4.0,
        4.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
    ]
}

SHADING = {
    "Default": {
        "ambient": 0.15,
        "diffuse": 0.9,
        "specular": 0.3,
        "specularPower": 15,
    },
    "Glossy Vascular": {
        "ambient": 0.15,
        "diffuse": 0.28,
        "specular": 1.42,
        "specularPower": 50,
    },
    "Glossy Bone": {
        "ambient": 0.15,
        "diffuse": 0.24,
        "specular": 1.17,
        "specularPower": 6.98,
    },
    "Endoscopy": {
        "ambient": 0.12,
        "diffuse": 0.64,
        "specular": 0.73,
        "specularPower": 50,
    },
}


class Volume:
    def __init__(self):
        self.config = None
        self.exist = None
        self.color_transfer = None
        self.opacity_transfer_func = None
        self.ww = None
        self.wl = None
        self.curve = 0
        self.plane = None
        self.plane_on = False
        self.volume = None
        self.image = None
        self.loaded_image = 0
        self.to_reload = False
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnHideVolume, "Hide raycasting volume")
        Publisher.subscribe(self.OnUpdatePreset, "Update raycasting preset")
        Publisher.subscribe(self.OnSetCurve, "Set raycasting curve")
        Publisher.subscribe(self.OnSetWindowLevel, "Set raycasting wwwl")
        Publisher.subscribe(self.Refresh, "Set raycasting refresh")
        Publisher.subscribe(
            self.OnSetRelativeWindowLevel, "Set raycasting relative window and level"
        )
        Publisher.subscribe(self.OnEnableTool, "Enable raycasting tool")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.ChangeBackgroundColour, "Change volume viewer background colour")

        Publisher.subscribe(self.ResetRayCasting, "Reset Raycasting")

        Publisher.subscribe(self.OnFlipVolume, "Flip volume")

    def ResetRayCasting(self):
        if self.exist:
            self.exist = None
            self.LoadVolume()

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        # if self.plane:
        #    self.plane = None
        #    Publisher.sendMessage('Remove surface actor from viewer', self.plane_actor)
        if self.plane:
            self.plane.DestroyObjs()
            del self.plane
            self.plane = 0

        if self.exist:
            self.exist = None
            Publisher.sendMessage("Remove surface actor from viewer", actor=self.volume)
            Publisher.sendMessage("Disable volume cut menu")
            Publisher.sendMessage("Unload volume", volume=self.volume)

            del self.image
            del self.imagedata
            del self.final_imagedata
            del self.volume
            del self.color_transfer
            del self.opacity_transfer_func
            del self.volume_properties
            del self.volume_mapper
            self.volume = None
            self.exist = False
            self.loaded_image = False
            self.image = None
            self.final_imagedata = None
            self.opacity_transfer_func = None
            self.color_transfer = None
            Publisher.sendMessage("Render volume viewer")

    def OnLoadVolume(self, label):
        label = label
        # self.LoadConfig(label)
        self.LoadVolume()

    def OnHideVolume(self):
        print("Hide Volume")
        self.volume.SetVisibility(0)
        if self.plane and self.plane_on:
            self.plane.Disable()
        Publisher.sendMessage("Render volume viewer")

    def OnShowVolume(self):
        print("Show volume")
        if self.exist:
            print("Volume exists")
            self.volume.SetVisibility(1)
            if self.plane and self.plane_on:
                self.plane.Enable()
            Publisher.sendMessage("Render volume viewer")
        else:
            print("Volume doesnt exit")
            Publisher.sendMessage("Load raycasting preset", preset_name=const.RAYCASTING_LABEL)
            self.LoadConfig()
            self.LoadVolume()
            self.exist = 1

    def OnUpdatePreset(self):
        self.__load_preset_config()

        if self.config:
            if self.to_reload:
                self.exist = False
                Publisher.sendMessage("Unload volume", volume=self.volume)

            if self.exist:
                self.__load_preset()
                self.volume.SetVisibility(1)
                # Publisher.sendMessage('Render volume viewer')
            else:
                self.LoadVolume()
                self.CalculateHistogram()
                self.exist = 1

            colour = self.GetBackgroundColour()
            Publisher.sendMessage("Change volume viewer background colour", colour=colour)
            Publisher.sendMessage("Change volume viewer gui colour", colour=colour)
        else:
            Publisher.sendMessage("Unload volume", volume=self.volume)
            del self.image
            del self.imagedata
            del self.final_imagedata
            del self.volume
            del self.color_transfer
            del self.opacity_transfer_func
            del self.volume_properties
            del self.volume_mapper
            self.volume = None
            self.exist = False
            self.loaded_image = False
            self.image = None
            self.final_imagedata = None
            self.opacity_transfer_func = None
            self.color_transfer = None
            Publisher.sendMessage("Render volume viewer")

    def OnFlipVolume(self, axis):
        print("Flipping Volume")
        self.loaded_image = False
        del self.image
        self.image = None
        self.to_reload = True

    def __load_preset_config(self):
        self.config = prj.Project().raycasting_preset

    def __update_colour_table(self):
        if self.config["advancedCLUT"]:
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
        self.volume_mapper.SetInputData(imagedata)

        # Update other information
        self.SetShading()
        self.SetTypeRaycasting()

    def OnSetCurve(self, curve):
        self.curve = curve
        self.CalculateWWWL()
        ww = self.ww
        wl = self.wl
        Publisher.sendMessage("Set volume window and level text", ww=ww, wl=wl)

    def OnSetRelativeWindowLevel(self, diff_wl, diff_ww):
        ww = self.ww + diff_ww
        wl = self.wl + diff_wl
        Publisher.sendMessage("Set volume window and level text", ww=ww, wl=wl)
        self.SetWWWL(ww, wl)
        self.ww = ww
        self.wl = wl

    def OnSetWindowLevel(self, ww, wl, curve):
        self.curve = curve
        self.SetWWWL(ww, wl)

    def SetWWWL(self, ww, wl):
        if self.config["advancedCLUT"]:
            try:
                curve = self.config["16bitClutCurves"][self.curve]
            except IndexError:
                self.curve = 0
                curve = self.config["16bitClutCurves"][self.curve]

            p1 = curve[0]
            p2 = curve[-1]
            half = (p2["x"] - p1["x"]) / 2.0
            middle = p1["x"] + half

            shiftWL = wl - middle
            shiftWW = p1["x"] + shiftWL - (wl - 0.5 * ww)

            factor = 1.0
            for n, i in enumerate(curve):
                factor = abs(i["x"] - middle) / half
                factor = max(factor, 0)
                i["x"] += shiftWL
                if n < len(curve) / 2.0:
                    i["x"] -= shiftWW * factor
                else:
                    i["x"] += shiftWW * factor
        else:
            self.config["wl"] = wl
            self.config["ww"] = ww

        self.__update_colour_table()

    def CalculateWWWL(self):
        """
        Get the window width & level from the selected curve
        """
        try:
            curve = self.config["16bitClutCurves"][self.curve]
        except IndexError:
            self.curve -= 1
            curve = self.config["16bitClutCurves"][self.curve]
        first_point = curve[0]["x"]
        last_point = curve[-1]["x"]
        self.ww = last_point - first_point
        self.wl = first_point + self.ww / 2.0

    def Refresh(self):
        self.__update_colour_table()

    def Create16bColorTable(self, scale):
        if self.color_transfer:
            color_transfer = self.color_transfer
        else:
            color_transfer = vtkColorTransferFunction()
        color_transfer.RemoveAllPoints()
        curve_table = self.config["16bitClutCurves"]
        color_table = self.config["16bitClutColors"]
        colors = []
        for i, element in enumerate(curve_table):
            for j, lopacity in enumerate(element):
                gray_level = lopacity["x"]
                r = color_table[i][j]["red"]
                g = color_table[i][j]["green"]
                b = color_table[i][j]["blue"]

                colors.append((gray_level, r, g, b))
                color_transfer.AddRGBPoint(self.TranslateScale(scale, gray_level), r, g, b)
        self.color_transfer = color_transfer

    def Create8bColorTable(self, scale):
        if self.color_transfer:
            color_transfer = self.color_transfer
        else:
            color_transfer = vtkColorTransferFunction()
        color_transfer.RemoveAllPoints()
        color_preset = self.config["CLUT"]
        if color_preset != "No CLUT":
            path = os.path.join(
                inv_paths.RAYCASTING_PRESETS_DIRECTORY, "color_list", color_preset + ".plist"
            )
            with open(path, "rb") as f:
                p = plistlib.load(f, fmt=plistlib.FMT_XML)

            r = p["Red"]
            g = p["Green"]
            b = p["Blue"]
            colors = list(zip(r, g, b))
        else:
            # Grayscale from black to white
            colors = [(i, i, i) for i in range(256)]

        ww = self.config["ww"]
        wl = self.TranslateScale(scale, self.config["wl"])
        init = wl - ww / 2.0
        inc = ww / (len(colors) - 1.0)
        for n, rgb in enumerate(colors):
            color_transfer.AddRGBPoint(init + n * inc, *[i / 255.0 for i in rgb])

        self.color_transfer = color_transfer

    def CreateOpacityTable(self, scale):
        if self.opacity_transfer_func:
            opacity_transfer_func = self.opacity_transfer_func
        else:
            opacity_transfer_func = vtkPiecewiseFunction()
        opacity_transfer_func.RemoveAllPoints()
        curve_table = self.config["16bitClutCurves"]
        opacities = []

        ww = self.config["ww"]
        wl = self.config["wl"]
        self.ww = ww
        self.wl = wl

        # l1 = wl - ww / 2.0
        # l2 = wl + ww / 2.0

        # k1 = 0.0
        # k2 = 1.0

        opacity_transfer_func.AddSegment(0, 0, 2**16 - 1, 0)

        for i, element in enumerate(curve_table):
            for j, lopacity in enumerate(element):
                gray_level = lopacity["x"]
                # if gray_level <= l1:
                #    opacity = k1
                # elif gray_level > l2:
                #    opacity = k2
                # else:
                opacity = lopacity["y"]
                opacities.append((gray_level, opacity))
                opacity_transfer_func.AddPoint(self.TranslateScale(scale, gray_level), opacity)
        self.opacity_transfer_func = opacity_transfer_func

    def Create8bOpacityTable(self, scale):
        if self.opacity_transfer_func:
            opacity_transfer_func = self.opacity_transfer_func
        else:
            opacity_transfer_func = vtkPiecewiseFunction()
        opacity_transfer_func.RemoveAllPoints()

        ww = self.config["ww"]
        wl = self.TranslateScale(scale, self.config["wl"])

        l1 = wl - ww / 2.0
        l2 = wl + ww / 2.0

        self.ww = ww
        self.wl = self.config["wl"]

        opacity_transfer_func.RemoveAllPoints()
        opacity_transfer_func.AddSegment(0, 0, 2**16 - 1, 0)

        # k1 = 0.0
        # k2 = 1.0

        opacity_transfer_func.AddPoint(l1, 0)
        opacity_transfer_func.AddPoint(l2, 1)

        self.opacity_transfer_func = opacity_transfer_func
        return opacity_transfer_func

    def GetBackgroundColour(self):
        colour = (
            self.config["backgroundColorRedComponent"],
            self.config["backgroundColorGreenComponent"],
            self.config["backgroundColorBlueComponent"],
        )
        return colour

    def ChangeBackgroundColour(self, colour):
        if self.config:
            self.config["backgroundColorRedComponent"] = colour[0] * 255
            self.config["backgroundColorGreenComponent"] = colour[1] * 255
            self.config["backgroundColorBlueComponent"] = colour[2] * 255

    def SetShading(self):
        if self.config["useShading"]:
            self.volume_properties.ShadeOn()
        else:
            self.volume_properties.ShadeOff()

        shading = SHADING[self.config["shading"]]
        self.volume_properties.SetAmbient(shading["ambient"])
        self.volume_properties.SetDiffuse(shading["diffuse"])
        self.volume_properties.SetSpecular(shading["specular"])
        self.volume_properties.SetSpecularPower(shading["specularPower"])

    def SetTypeRaycasting(self):
        if self.volume_mapper.IsA("vtkFixedPointVolumeRayCastMapper") or self.volume_mapper.IsA(
            "vtkGPUVolumeRayCastMapper"
        ):
            if self.config.get("MIP", False):
                self.volume_mapper.SetBlendModeToMaximumIntensity()
            else:
                self.volume_mapper.SetBlendModeToComposite()
        else:
            if self.config.get("MIP", False):
                raycasting_function = vtkVolumeRayCastMIPFunction()  # noqa: F821
            else:
                raycasting_function = vtkVolumeRayCastCompositeFunction()  # noqa: F821
                raycasting_function.SetCompositeMethodToInterpolateFirst()

            session = ses.Session()
            if not session.GetConfig("rendering"):
                self.volume_mapper.SetVolumeRayCastFunction(raycasting_function)

    def ApplyConvolution(self, imagedata, update_progress=None):
        number_filters = len(self.config["convolutionFilters"])
        if number_filters:
            if not (update_progress):
                update_progress = vtk_utils.ShowProgress(number_filters)
            for filter in self.config["convolutionFilters"]:
                convolve = vtkImageConvolve()
                convolve.SetInputData(imagedata)
                convolve.SetKernel5x5([i / 60.0 for i in Kernels[filter]])
                #  convolve.ReleaseDataFlagOn()

                convolve_ref = weakref.ref(convolve)

                convolve_ref().AddObserver(
                    "ProgressEvent",
                    lambda obj, evt: update_progress(convolve_ref(), "Rendering..."),
                )
                convolve.Update()
                del imagedata
                imagedata = convolve.GetOutput()
                del convolve
                # convolve.GetOutput().ReleaseDataFlagOn()
        return imagedata

    def LoadImage(self):
        slice_data = slice_.Slice()
        n_array = slice_data.matrix
        spacing = slice_data.spacing
        slice_number = 0
        orientation = "AXIAL"

        image = converters.to_vtk(n_array, spacing, slice_number, orientation)
        self.image = image

    def LoadVolume(self):
        # image = imagedata_utils.to_vtk(n_array, spacing, slice_number, orientation)

        if not self.loaded_image:
            self.LoadImage()
            self.loaded_image = 1

        image = self.image

        number_filters = len(self.config["convolutionFilters"])

        # if prj.Project().original_orientation == const.AXIAL:
        #     flip_image = True
        # else:
        #     flip_image = False

        # if (flip_image):
        update_progress = vtk_utils.ShowProgress(2 + number_filters)
        # Flip original vtkImageData
        flip = vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        #  flip.ReleaseDataFlagOn()

        flip_ref = weakref.ref(flip)
        flip_ref().AddObserver(
            "ProgressEvent", lambda obj, evt: update_progress(flip_ref(), "Rendering...")
        )
        flip.Update()
        image = flip.GetOutput()

        scale = image.GetScalarRange()
        self.scale = scale

        cast = vtkImageShiftScale()
        cast.SetInputData(image)
        cast.SetShift(abs(scale[0]))
        cast.SetOutputScalarTypeToUnsignedShort()
        #  cast.ReleaseDataFlagOn()
        cast_ref = weakref.ref(cast)
        cast_ref().AddObserver(
            "ProgressEvent", lambda obj, evt: update_progress(cast_ref(), "Rendering...")
        )
        cast.Update()
        image2 = cast

        self.imagedata = image2
        if self.config["advancedCLUT"]:
            self.Create16bColorTable(scale)
            self.CreateOpacityTable(scale)
        else:
            self.Create8bColorTable(scale)
            self.Create8bOpacityTable(scale)

        image2 = self.ApplyConvolution(image2.GetOutput(), update_progress)
        self.final_imagedata = image2

        # Changed the vtkVolumeRayCast to vtkFixedPointVolumeRayCastMapper
        # because it's faster and the image is better
        # TODO: To test if it's true.
        session = ses.Session()
        if not session.GetConfig("rendering"):
            volume_mapper = vtkFixedPointVolumeRayCastMapper()
            # volume_mapper.AutoAdjustSampleDistancesOff()
            self.volume_mapper = volume_mapper
            volume_mapper.IntermixIntersectingGeometryOn()
        else:
            volume_mapper = vtkOpenGLGPUVolumeRayCastMapper()
            volume_mapper.UseJitteringOn()
            self.volume_mapper = volume_mapper

        self.SetTypeRaycasting()
        volume_mapper.SetInputData(image2)

        # TODO: Look to this
        # volume_mapper_hw = vtkVolumeTextureMapper3D()
        # volume_mapper_hw.SetInput(image2)

        # Cut Plane
        # CutPlane(image2, volume_mapper)

        # self.color_transfer = color_transfer

        volume_properties = vtkVolumeProperty()
        # volume_properties.IndependentComponentsOn()
        volume_properties.SetInterpolationTypeToLinear()
        volume_properties.SetColor(self.color_transfer)

        try:
            volume_properties.SetScalarOpacity(self.opacity_transfer_func)
        except NameError:
            pass

        if not self.volume_mapper.IsA("vtkGPUVolumeRayCastMapper"):
            # Using these lines to improve the raycasting quality. These values
            # seems related to the distance from ray from raycasting.
            # TODO: Need to see values that improve the quality and don't decrease
            # the performance. 2.0 seems to be a good value to pix_diag
            pix_diag = 2.0
            volume_mapper.SetImageSampleDistance(0.25)
            volume_mapper.SetSampleDistance(pix_diag / 5.0)
            volume_properties.SetScalarOpacityUnitDistance(pix_diag)

        self.volume_properties = volume_properties

        self.SetShading()

        volume = vtkVolume()
        volume.SetMapper(volume_mapper)
        volume.SetProperty(volume_properties)
        self.volume = volume

        colour = self.GetBackgroundColour()

        self.exist = 1

        if self.plane:
            self.plane.SetVolumeMapper(volume_mapper)

        Publisher.sendMessage(
            "Load volume into viewer", volume=volume, colour=colour, ww=self.ww, wl=self.wl
        )

        del flip
        del cast

    def OnEnableTool(self, tool_name, flag):
        if tool_name == _("Cut plane"):
            if self.plane:
                if flag:
                    self.plane_on = True
                    self.plane.Enable()
                else:
                    self.plane_on = False
                    self.plane.Disable()
            else:
                #  self.final_imagedata.Update()
                self.plane_on = True
                self.plane = CutPlane(self.final_imagedata, self.volume_mapper)

    def CalculateHistogram(self):
        image = self.image
        r = int(image.GetScalarRange()[1] - image.GetScalarRange()[0])
        accumulate = vtkImageAccumulate()
        accumulate.SetInputData(image)
        accumulate.SetComponentExtent(0, r - 1, 0, 0, 0, 0)
        accumulate.SetComponentOrigin(image.GetScalarRange()[0], 0, 0)
        #  accumulate.ReleaseDataFlagOn()
        accumulate.Update()
        n_image = numpy_support.vtk_to_numpy(accumulate.GetOutput().GetPointData().GetScalars())
        del accumulate
        init, end = image.GetScalarRange()
        Publisher.sendMessage("Load histogram", histogram=n_image, init=init, end=end)

    def TranslateScale(self, scale, value):
        # if value < 0:
        #    valor = 2**16 - abs(value)
        # else:
        #    valor = value
        return value - scale[0]


class VolumeMask:
    def __init__(self, mask):
        self.mask = mask
        self.colour = mask.colour
        self._volume_mapper = None
        self._flip = None
        self._color_transfer = None
        self._piecewise_function = None
        self._actor = None

    def create_volume(self):
        if self._actor is None:
            session = ses.Session()
            if not session.GetConfig("rendering"):
                self._volume_mapper = vtkFixedPointVolumeRayCastMapper()
                # volume_mapper.AutoAdjustSampleDistancesOff()
                self._volume_mapper.IntermixIntersectingGeometryOn()
                pix_diag = 2.0
                self._volume_mapper.SetImageSampleDistance(0.25)
                self._volume_mapper.SetSampleDistance(pix_diag / 5.0)
            else:
                self._volume_mapper = vtkGPUVolumeRayCastMapper()
                self._volume_mapper.UseJitteringOn()

                if Version(vtkVersion().GetVTKVersion()) > Version("8.0"):
                    self._volume_mapper.SetBlendModeToIsoSurface()

            #  else:
            #  isosurfaceFunc = vtk.vtkVolumeRayCastIsosurfaceFunction()
            #  isosurfaceFunc.SetIsoValue(127)

            #  self._volume_mapper = vtk.vtkVolumeRayCastMapper()
            #  self._volume_mapper.SetVolumeRayCastFunction(isosurfaceFunc)

            self._flip = vtkImageFlip()
            self._flip.SetInputData(self.mask.imagedata)
            self._flip.SetFilteredAxis(1)
            self._flip.FlipAboutOriginOn()

            self._volume_mapper.SetInputConnection(self._flip.GetOutputPort())
            self._volume_mapper.Update()

            r, g, b = self.colour

            self._color_transfer = vtkColorTransferFunction()
            self._color_transfer.RemoveAllPoints()
            self._color_transfer.AddRGBPoint(0.0, 0, 0, 0)
            self._color_transfer.AddRGBPoint(254.0, r, g, b)
            self._color_transfer.AddRGBPoint(255.0, r, g, b)

            self._piecewise_function = vtkPiecewiseFunction()
            self._piecewise_function.RemoveAllPoints()
            self._piecewise_function.AddPoint(0.0, 0.0)
            self._piecewise_function.AddPoint(127, 1.0)

            self._volume_property = vtkVolumeProperty()
            self._volume_property.SetColor(self._color_transfer)
            self._volume_property.SetScalarOpacity(self._piecewise_function)
            self._volume_property.ShadeOn()
            self._volume_property.SetInterpolationTypeToLinear()
            self._volume_property.SetSpecular(0.75)
            self._volume_property.SetSpecularPower(2)

            if not self._volume_mapper.IsA("vtkGPUVolumeRayCastMapper"):
                self._volume_property.SetScalarOpacityUnitDistance(pix_diag)
            else:
                if Version(vtkVersion().GetVTKVersion()) > Version("8.0"):
                    self._volume_property.GetIsoSurfaceValues().SetValue(0, 127)

            self._actor = vtkVolume()
            self._actor.SetMapper(self._volume_mapper)
            self._actor.SetProperty(self._volume_property)
            self._actor.Update()

    def change_imagedata(self):
        self._flip.SetInputData(self.mask.imagedata)

    def set_colour(self, colour):
        self.colour = colour
        r, g, b = self.colour
        self._color_transfer.RemoveAllPoints()
        self._color_transfer.AddRGBPoint(0.0, 0, 0, 0)
        self._color_transfer.AddRGBPoint(254.0, r, g, b)
        self._color_transfer.AddRGBPoint(255.0, r, g, b)


class CutPlane:
    def __init__(self, img, volume_mapper):
        self.img = img
        self.volume_mapper = volume_mapper
        self.Create()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.Reset, "Reset Cut Plane")
        Publisher.subscribe(self.Enable, "Enable Cut Plane")
        Publisher.subscribe(self.Disable, "Disable Cut Plane")

    def Create(self):
        self.plane_widget = plane_widget = vtkImagePlaneWidget()
        plane_widget.SetInputData(self.img)
        plane_widget.SetPlaneOrientationToXAxes()
        # plane_widget.SetResliceInterpolateToLinear()
        plane_widget.TextureVisibilityOff()
        # Set left mouse button to move and rotate plane
        plane_widget.SetLeftButtonAction(1)
        # SetColor margin to green
        margin_property = plane_widget.GetMarginProperty()
        margin_property.SetColor(0, 0.8, 0)
        # Disable cross
        cursor_property = plane_widget.GetCursorProperty()
        cursor_property.SetOpacity(0)
        self.plane_source = plane_source = vtkPlaneSource()
        plane_source.SetOrigin(plane_widget.GetOrigin())
        plane_source.SetPoint1(plane_widget.GetPoint1())
        plane_source.SetPoint2(plane_widget.GetPoint2())
        plane_source.SetNormal(plane_widget.GetNormal())
        plane_mapper = self.plane_mapper = vtkPolyDataMapper()
        plane_mapper.SetInputData(plane_source.GetOutput())
        self.plane_actor = plane_actor = vtkActor()
        plane_actor.SetMapper(plane_mapper)
        plane_actor.GetProperty().BackfaceCullingOn()
        plane_actor.GetProperty().SetOpacity(0)
        plane_widget.AddObserver("InteractionEvent", self.Update)
        Publisher.sendMessage("AppendActor", actor=self.plane_actor)
        Publisher.sendMessage("Set Widget Interactor", widget=self.plane_widget)
        plane_actor.SetVisibility(1)
        plane_widget.On()
        self.plane = plane = vtkPlane()
        plane.SetNormal(self.plane_source.GetNormal())
        plane.SetOrigin(self.plane_source.GetOrigin())
        self.volume_mapper.AddClippingPlane(plane)
        # Storage First Position
        self.origin = plane_widget.GetOrigin()
        self.p1 = plane_widget.GetPoint1()
        self.p2 = plane_widget.GetPoint2()
        self.normal = plane_widget.GetNormal()

    def SetVolumeMapper(self, volume_mapper):
        self.volume_mapper = volume_mapper
        self.volume_mapper.AddClippingPlane(self.plane)

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
        Publisher.sendMessage("Render volume viewer")

    def Enable(self):
        self.plane_widget.On()
        self.plane_actor.VisibilityOn()
        self.volume_mapper.AddClippingPlane(self.plane)
        Publisher.sendMessage("Render volume viewer")

    def Disable(self):
        self.plane_widget.Off()
        self.plane_actor.VisibilityOff()
        self.volume_mapper.RemoveClippingPlane(self.plane)
        Publisher.sendMessage("Render volume viewer")

    def Reset(self):
        plane_source = self.plane_source
        # plane_widget = self.plane_widget
        plane_source.SetOrigin(self.origin)
        plane_source.SetPoint1(self.p1)
        plane_source.SetPoint2(self.p2)
        plane_source.SetNormal(self.normal)
        self.plane_actor.VisibilityOn()
        self.plane.SetNormal(self.normal)
        self.plane.SetOrigin(self.origin)
        Publisher.sendMessage("Render volume viewer")

    def DestroyObjs(self):
        Publisher.sendMessage("Remove surface actor from viewer", actor=self.plane_actor)
        self.Disable()
        del self.plane_widget
        del self.plane_source
        del self.plane_actor
        del self.normal
        del self.plane
