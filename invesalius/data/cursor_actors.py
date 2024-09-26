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

import math

import numpy
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkLookupTable, vtkVersion
from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkImagingCore import vtkImageMapToColors
from vtkmodules.vtkRenderingCore import (
    vtkImageActor,
    vtkImageProperty,
    vtkImageSlice,
    vtkImageSliceMapper,
)

import invesalius.constants as const

ORIENTATION = {"AXIAL": 2, "CORONAL": 1, "SAGITAL": 0}


def to_vtk(n_array, spacing, slice_number, orientation):
    """
    It transforms a numpy array into a vtkImageData.
    """
    # TODO Merge this function with imagedata_utils.to_vtk to eliminate
    # duplicated code
    try:
        dz, dy, dx = n_array.shape
    except ValueError:
        dy, dx = n_array.shape
        dz = 1

    v_image = numpy_support.numpy_to_vtk(n_array.flat)

    if orientation == "AXIAL":
        extent = (0, dx - 1, 0, dy - 1, slice_number, slice_number + dz - 1)
    elif orientation == "SAGITAL":
        extent = (slice_number, slice_number + dx - 1, 0, dy - 1, 0, dz - 1)
    elif orientation == "CORONAL":
        extent = (0, dx - 1, slice_number, slice_number + dy - 1, 0, dz - 1)

    image = vtkImageData()
    image.SetOrigin(0, 0, 0)
    image.SetSpacing(spacing)
    image.SetDimensions(dx, dy, dz)
    image.SetExtent(extent)
    #  image.SetNumberOfScalarComponents(1)
    #  image.SetScalarType(numpy_support.get_vtk_array_type(n_array.dtype))
    image.AllocateScalars(numpy_support.get_vtk_array_type(n_array.dtype), 1)
    #  image.Update()
    image.GetCellData().SetScalars(v_image)
    image.GetPointData().SetScalars(v_image)
    #  image.Update()

    image_copy = vtkImageData()
    image_copy.DeepCopy(image)
    #  image_copy.Update()

    return image_copy


class CursorBase:
    def __init__(self):
        self.colour = (0.0, 0.0, 1.0)
        self.opacity = 1
        self.size = 15.0
        self.unit = "mm"
        self.orientation = "AXIAL"
        self.spacing = (1, 1, 1)
        self.position = (0, 0, 0)
        if vtkVersion().GetVTKVersion() > "5.8.0":
            self.mapper = vtkImageSliceMapper()
            cursor_property = vtkImageProperty()
            cursor_property.SetInterpolationTypeToNearest()
            self.actor = vtkImageSlice()
            self.actor.SetMapper(self.mapper)
            self.actor.SetProperty(cursor_property)
        else:
            self.actor = vtkImageActor()
            self.mapper = None
        self._build_actor()
        self._calculate_area_pixels()

    def SetSize(self, diameter):
        self.radius = diameter / 2.0
        self._build_actor()
        self._calculate_area_pixels()

    def SetUnit(self, unit):
        self.unit = unit
        self._build_actor()
        self._calculate_area_pixels()

    def SetColour(self, colour):
        self.colour = colour
        self._build_actor()

    def SetOrientation(self, orientation):
        self.orientation = orientation
        self._build_actor()
        self._calculate_area_pixels()

    def SetPosition(self, position):
        # Overriding SetPosition method because in rectangles with odd
        # dimensions there is no half position.
        self.position = position
        px, py, pz = position
        sx, sy, sz = self.spacing
        tx = self.actor.GetXRange()[1] - self.actor.GetXRange()[0]
        ty = self.actor.GetYRange()[1] - self.actor.GetYRange()[0]
        tz = self.actor.GetZRange()[1] - self.actor.GetZRange()[0]

        if self.orientation == "AXIAL":
            if self.points.shape[0] % 2:
                y = py - ty / 2.0
            else:
                y = py - ty / 2.0 + self.spacing[1] / 2.0

            if self.points.shape[1] % 2:
                x = px - tx / 2.0
            else:
                x = px - tx / 2.0 + self.spacing[0] / 2.0
            z = pz

            if self.mapper:
                x += sx / 2.0
                y += sy / 2.0

        elif self.orientation == "CORONAL":
            if self.points.shape[0] % 2:
                z = pz - tz / 2.0
            else:
                z = pz - tz / 2.0 + self.spacing[2] / 2.0

            if self.points.shape[1] % 2:
                x = px - tx / 2.0
            else:
                x = px - tx / 2.0 + self.spacing[0] / 2.0
            y = py

            if self.mapper:
                x += sx / 2.0
                z += sz / 2.0

        elif self.orientation == "SAGITAL":
            # height shape is odd
            if self.points.shape[1] % 2:
                y = py - ty / 2.0
            else:
                y = py - ty / 2.0 + self.spacing[1] / 2.0

            if self.points.shape[0] % 2:
                z = pz - tz / 2.0
            else:
                z = pz - tz / 2.0 + self.spacing[2] / 2.0
            x = px

            if self.mapper:
                y += sy / 2.0
                z += sz / 2.0

        else:
            if self.points.shape[0] % 2:
                y = py - ty / 2.0
            else:
                y = py - ty / 2.0 + self.spacing[1] / 2.0

            if self.points.shape[1] % 2:
                x = px - tx / 2.0
            else:
                x = px - tx / 2.0 + self.spacing[0] / 2.0
            z = pz

            if self.mapper:
                x += sx / 2.0
                y += sy / 2.0

        self.actor.SetPosition(x, y, z)

    def SetSpacing(self, spacing):
        self.spacing = spacing
        self._build_actor()
        self._calculate_area_pixels()

    def Show(self, value=1):
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def GetPixels(self):
        return self.points

    def _build_actor(self):
        pass

    def _calculate_area_pixels(self):
        pass

    def _set_colour(self, imagedata, colour):
        # scalar_range = int(imagedata.GetScalarRange()[1])
        r, g, b = colour[:3]

        # map scalar values into colors
        lut_mask = vtkLookupTable()
        lut_mask.SetNumberOfColors(256)
        lut_mask.SetHueRange(const.THRESHOLD_HUE_RANGE)
        lut_mask.SetSaturationRange(1, 1)
        lut_mask.SetValueRange(0, 255)
        lut_mask.SetRange(0, 255)
        lut_mask.SetNumberOfTableValues(256)
        lut_mask.SetTableValue(0, 0, 0, 0, 0.0)
        lut_mask.SetTableValue(1, 1 - r, 1 - g, 1 - b, 0.50)
        lut_mask.SetRampToLinear()
        lut_mask.Build()

        # map the input image through a lookup table
        img_colours_mask = vtkImageMapToColors()
        img_colours_mask.SetLookupTable(lut_mask)
        img_colours_mask.SetOutputFormatToRGBA()
        img_colours_mask.SetInputData(imagedata)
        img_colours_mask.Update()

        return img_colours_mask.GetOutput()


class CursorCircle(CursorBase):
    # TODO: Think and try to change this class to an actor
    # CursorCircleActor(vtkActor)
    def __init__(self):
        self.radius = 15.0
        super().__init__()

    def _build_actor(self):
        """
        Function to plot the circle
        """
        r = self.radius
        if self.unit == "µm":
            r /= 1000.0
        if self.unit == "px":
            sx, sy, sz = 1.0, 1.0, 1.0
        else:
            sx, sy, sz = self.spacing
        if self.orientation == "AXIAL":
            xi = math.floor(-r / sx)
            xf = math.ceil(r / sx) + 1
            yi = math.floor(-r / sy)
            yf = math.ceil(r / sy) + 1
            zi = 0
            zf = 1
        elif self.orientation == "CORONAL":
            xi = math.floor(-r / sx)
            xf = math.ceil(r / sx) + 1
            yi = 0
            yf = 1
            zi = math.floor(-r / sz)
            zf = math.ceil(r / sz) + 1
        elif self.orientation == "SAGITAL":
            xi = 0
            xf = 1
            yi = math.floor(-r / sy)
            yf = math.ceil(r / sy) + 1
            zi = math.floor(-r / sz)
            zf = math.ceil(r / sz) + 1

        z, y, x = numpy.ogrid[zi:zf, yi:yf, xi:xf]

        circle_m = (z * sz) ** 2 + (y * sy) ** 2 + (x * sx) ** 2 <= r**2
        circle_i = to_vtk(circle_m.astype("uint8"), self.spacing, 0, self.orientation)
        circle_ci = self._set_colour(circle_i, self.colour)

        if self.mapper is None:
            self.actor.SetInputData(circle_ci)
            self.actor.InterpolateOff()
            self.actor.PickableOff()
            self.actor.SetDisplayExtent(circle_ci.GetExtent())
        else:
            self.mapper.SetInputData(circle_ci)
            self.mapper.BorderOn()

            self.mapper.SetOrientation(ORIENTATION[self.orientation])

    def _calculate_area_pixels(self):
        """
        Return the cursor's pixels.
        """
        r = self.radius
        if self.unit == "µm":
            r /= 1000.0
        if self.unit == "px":
            sx, sy = 1.0, 1.0
        else:
            if self.orientation == "AXIAL":
                sx = self.spacing[0]
                sy = self.spacing[1]
            elif self.orientation == "CORONAL":
                sx = self.spacing[0]
                sy = self.spacing[2]
            elif self.orientation == "SAGITAL":
                sx = self.spacing[1]
                sy = self.spacing[2]

        xi = math.floor(-r / sx)
        xf = math.ceil(r / sx) + 1
        yi = math.floor(-r / sy)
        yf = math.ceil(r / sy) + 1

        y, x = numpy.ogrid[yi:yf, xi:xf]

        index = (y * sy) ** 2 + (x * sx) ** 2 <= r**2
        self.points = index


class CursorRectangle(CursorBase):
    def __init__(self):
        self.radius = 15.0
        super().__init__()

    def _build_actor(self):
        """
        Function to plot the Retangle
        """
        print("Building rectangle cursor", self.orientation)
        r = self.radius
        if self.unit == "µm":
            r /= 1000.0
        if self.unit == "px":
            sx, sy, sz = 1.0, 1.0, 1.0
        else:
            sx, sy, sz = self.spacing
        if self.orientation == "AXIAL":
            x = int(math.floor(2 * r / sx))
            y = int(math.floor(2 * r / sy))
            z = 1
        elif self.orientation == "CORONAL":
            x = int(math.floor(r / sx))
            y = 1
            z = int(math.floor(r / sz))
        elif self.orientation == "SAGITAL":
            x = 1
            y = int(math.floor(r / sy))
            z = int(math.floor(r / sz))

        rectangle_m = numpy.ones((z, y, x), dtype="uint8")
        rectangle_i = to_vtk(rectangle_m, self.spacing, 0, self.orientation)
        rectangle_ci = self._set_colour(rectangle_i, self.colour)

        if self.mapper is None:
            self.actor.SetInputData(rectangle_ci)
            self.actor.InterpolateOff()
            self.actor.PickableOff()
            self.actor.SetDisplayExtent(rectangle_ci.GetExtent())
        else:
            self.mapper.SetInputData(rectangle_ci)
            self.mapper.BorderOn()
            self.mapper.SetOrientation(ORIENTATION[self.orientation])

    def _calculate_area_pixels(self):
        r = self.radius
        if self.unit == "µm":
            r /= 1000.0
        if self.unit == "px":
            sx, sy, sz = 1.0, 1.0, 1.0
        else:
            sx, sy, sz = self.spacing
        if self.orientation == "AXIAL":
            x = int(math.floor(2 * r / sx))
            y = int(math.floor(2 * r / sy))
        elif self.orientation == "CORONAL":
            x = int(math.floor(r / sx))
            y = int(math.floor(r / sz))
        elif self.orientation == "SAGITAL":
            x = int(math.floor(r / sy))
            y = int(math.floor(r / sz))

        self.points = numpy.ones((y, x), dtype="bool")
