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
from vtkmodules.vtkCommonDataModel import vtkPiecewiseFunction
from vtkmodules.vtkImagingCore import vtkImageFlip
from vtkmodules.vtkRenderingCore import (
    vtkColorTransferFunction,
    vtkVolume,
    vtkVolumeProperty,
)
from vtkmodules.vtkRenderingVolume import (
    vtkFixedPointVolumeRayCastMapper,
    vtkGPUVolumeRayCastMapper,
)

import invesalius.session as ses


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
