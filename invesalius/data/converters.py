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

import gdcm
import numpy as np

from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkCommonCore import (
    vtkPoints,
)
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkPolyData,
    vtkTriangle
)
def to_vtk(
    n_array,
    spacing=(1.0, 1.0, 1.0),
    slice_number=0,
    orientation="AXIAL",
    origin=(0, 0, 0),
    padding=(0, 0, 0),
):
    if orientation == "SAGITTAL":
        orientation = "SAGITAL"

    try:
        dz, dy, dx = n_array.shape
    except ValueError:
        dy, dx = n_array.shape
        dz = 1

    px, py, pz = padding

    v_image = numpy_support.numpy_to_vtk(n_array.flat)

    if orientation == "AXIAL":
        extent = (
            0 - px,
            dx - 1 - px,
            0 - py,
            dy - 1 - py,
            slice_number - pz,
            slice_number + dz - 1 - pz,
        )
    elif orientation == "SAGITAL":
        dx, dy, dz = dz, dx, dy
        extent = (
            slice_number - px,
            slice_number + dx - 1 - px,
            0 - py,
            dy - 1 - py,
            0 - pz,
            dz - 1 - pz,
        )
    elif orientation == "CORONAL":
        dx, dy, dz = dx, dz, dy
        extent = (
            0 - px,
            dx - 1 - px,
            slice_number - py,
            slice_number + dy - 1 - py,
            0 - pz,
            dz - 1 - pz,
        )

    # Generating the vtkImageData
    image = vtkImageData()
    image.SetOrigin(origin)
    image.SetSpacing(spacing)
    image.SetDimensions(dx, dy, dz)
    # SetNumberOfScalarComponents and SetScalrType were replaced by
    # AllocateScalars
    #  image.SetNumberOfScalarComponents(1)
    #  image.SetScalarType(numpy_support.get_vtk_array_type(n_array.dtype))
    image.AllocateScalars(numpy_support.get_vtk_array_type(n_array.dtype), 1)
    image.SetExtent(extent)
    image.GetPointData().SetScalars(v_image)

    image_copy = vtkImageData()
    image_copy.DeepCopy(image)

    return image_copy


def to_vtk_mask(n_array, spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0)):
    dz, dy, dx = n_array.shape
    ox, oy, oz = origin
    sx, sy, sz = spacing

    ox -= sx
    oy -= sy
    oz -= sz

    v_image = numpy_support.numpy_to_vtk(n_array.flat)
    extent = (0, dx - 1, 0, dy - 1, 0, dz - 1)

    # Generating the vtkImageData
    image = vtkImageData()
    image.SetOrigin(ox, oy, oz)
    image.SetSpacing(sx, sy, sz)
    image.SetDimensions(dx - 1, dy - 1, dz - 1)
    # SetNumberOfScalarComponents and SetScalrType were replaced by
    # AllocateScalars
    #  image.SetNumberOfScalarComponents(1)
    #  image.SetScalarType(numpy_support.get_vtk_array_type(n_array.dtype))
    image.AllocateScalars(numpy_support.get_vtk_array_type(n_array.dtype), 1)
    image.SetExtent(extent)
    image.GetPointData().SetScalars(v_image)

    #  image_copy = vtkImageData()
    #  image_copy.DeepCopy(image)

    return image


def np_rgba_to_vtk(n_array, spacing=(1.0, 1.0, 1.0)):
    dy, dx, dc = n_array.shape
    v_image = numpy_support.numpy_to_vtk(n_array.reshape(dy * dx, dc))

    extent = (0, dx - 1, 0, dy - 1, 0, 0)

    # Generating the vtkImageData
    image = vtkImageData()
    image.SetOrigin(0, 0, 0)
    image.SetSpacing(spacing)
    image.SetDimensions(dx, dy, 1)
    # SetNumberOfScalarComponents and SetScalrType were replaced by
    # AllocateScalars
    #  image.SetNumberOfScalarComponents(1)
    #  image.SetScalarType(numpy_support.get_vtk_array_type(n_array.dtype))
    image.AllocateScalars(numpy_support.get_vtk_array_type(n_array.dtype), dc)
    image.SetExtent(extent)
    image.GetPointData().SetScalars(v_image)

    return image


# Based on http://gdcm.sourceforge.net/html/ConvertNumpy_8py-example.html
def gdcm_to_numpy(image, apply_intercep_scale=True):
    map_gdcm_np = {
        gdcm.PixelFormat.SINGLEBIT: np.uint8,
        gdcm.PixelFormat.UINT8: np.uint8,
        gdcm.PixelFormat.INT8: np.int8,
        gdcm.PixelFormat.UINT12: np.uint16,
        gdcm.PixelFormat.INT12: np.int16,
        gdcm.PixelFormat.UINT16: np.uint16,
        gdcm.PixelFormat.INT16: np.int16,
        gdcm.PixelFormat.UINT32: np.uint32,
        gdcm.PixelFormat.INT32: np.int32,
        # gdcm.PixelFormat.FLOAT16:np.float16,
        gdcm.PixelFormat.FLOAT32: np.float32,
        gdcm.PixelFormat.FLOAT64: np.float64,
    }

    pf = image.GetPixelFormat()
    if image.GetNumberOfDimensions() == 3:
        shape = (
            image.GetDimension(2),
            image.GetDimension(1),
            image.GetDimension(0),
            pf.GetSamplesPerPixel(),
        )
    else:
        shape = image.GetDimension(1), image.GetDimension(0), pf.GetSamplesPerPixel()
    dtype = map_gdcm_np[pf.GetScalarType()]
    gdcm_array = image.GetBuffer()
    np_array = np.frombuffer(
        gdcm_array.encode("utf-8", errors="surrogateescape"), dtype=dtype
    )
    if pf.GetScalarType() == gdcm.PixelFormat.SINGLEBIT:
        np_array = np.unpackbits(np_array)
    np_array.shape = shape
    np_array = np_array.squeeze()

    if apply_intercep_scale:
        shift = image.GetIntercept()
        scale = image.GetSlope()
        output = np.empty_like(np_array, np.int16)
        output[:] = scale * np_array + shift
        return output
    else:
        return np_array

def convert_custom_bin_to_vtk(filename):
    import os
    if os.path.exists(filename):
        numbers = np.fromfile(filename, count=3, dtype=np.int32)
        points = np.fromfile(filename, dtype=np.float32)
        elements = np.fromfile(filename, dtype=np.int32)

        points1 = points[3:(numbers[1]) * 3 + 3]*1000
        elements1 = elements[numbers[1] * 3 + 3:]

        points2 = points1.reshape(numbers[1], 3)
        elements2 = elements1.reshape(numbers[2], 3)

        points = vtkPoints()
        triangles = vtkCellArray()
        polydata = vtkPolyData()

        for i in range(len(points2)):
            points.InsertNextPoint(points2[i])
        for i in range(len(elements2)):
            triangle = vtkTriangle()
            triangle.GetPointIds().SetId(0, elements2[i, 0])
            triangle.GetPointIds().SetId(1, elements2[i, 1])
            triangle.GetPointIds().SetId(2, elements2[i, 2])

            triangles.InsertNextCell(triangle)

        polydata.SetPoints(points)
        polydata.SetPolys(triangles)

        return polydata
    else:
        print("File does not exists")
        return

