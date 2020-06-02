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

import math
import os
import sys
import tempfile

import gdcm
import imageio
import numpy
import numpy as np
import vtk
from pubsub import pub as Publisher

from scipy.ndimage import shift, zoom
from vtk.util import numpy_support

import invesalius.constants as const
from invesalius.data import vtk_utils as vtk_utils
import invesalius.reader.bitmap_reader as bitmap_reader
import invesalius.utils as utils
import invesalius.data.converters as converters

from invesalius import inv_paths

if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

# TODO: Test cases which are originally in sagittal/coronal orientation
# and have gantry

def ResampleImage3D(imagedata, value):
    """
    Resample vtkImageData matrix.
    """
    spacing = imagedata.GetSpacing()
    extent = imagedata.GetExtent()
    size = imagedata.GetDimensions()

    width = float(size[0])
    height = float(size[1]/value)

    resolution = (height/(extent[1]-extent[0])+1)*spacing[1]

    resample = vtk.vtkImageResample()
    resample.SetInput(imagedata)
    resample.SetAxisMagnificationFactor(0, resolution)
    resample.SetAxisMagnificationFactor(1, resolution)

    return resample.GetOutput()

def ResampleImage2D(imagedata, px=None, py=None, resolution_percentage = None,
                        update_progress = None):
    """
    Resample vtkImageData matrix.
    """

    extent = imagedata.GetExtent()
    spacing = imagedata.GetSpacing()
    dimensions = imagedata.GetDimensions()

    if resolution_percentage:
        factor_x = resolution_percentage
        factor_y = resolution_percentage
    else:
        if abs(extent[1]-extent[3]) < abs(extent[3]-extent[5]):
            f = extent[1]
        elif abs(extent[1]-extent[5]) < abs(extent[1] - extent[3]):
            f = extent[1]
        elif abs(extent[3]-extent[5]) < abs(extent[1] - extent[3]):
            f = extent[3]
        else:
            f = extent[1]

        factor_x = px/float(f+1)
        factor_y = py/float(f+1)

    resample = vtk.vtkImageResample()
    resample.SetInputData(imagedata)
    resample.SetAxisMagnificationFactor(0, factor_x)
    resample.SetAxisMagnificationFactor(1, factor_y)
    #  resample.SetOutputSpacing(spacing[0] * factor_x, spacing[1] * factor_y, spacing[2])
    if (update_progress):
        message = _("Generating multiplanar visualization...")
        resample.AddObserver("ProgressEvent", lambda obj,
                             evt:update_progress(resample,message))
    resample.Update()


    return resample.GetOutput()


def resize_slice(im_array, resolution_percentage):
    """
    Uses ndimage.zoom to resize a slice.

    input:
        im_array: slice as a numpy array.
        resolution_percentage: percentage of resize.
    """
    out = zoom(im_array, resolution_percentage, im_array.dtype, order=2)
    return out


def resize_image_array(image, resolution_percentage, as_mmap=False):
    out = zoom(image, resolution_percentage, image.dtype, order=2)
    if as_mmap:
        fname = tempfile.mktemp(suffix="_resized")
        out_mmap = np.memmap(fname, shape=out.shape, dtype=out.dtype, mode='w+')
        out_mmap[:] = out
        return out_mmap
    return out


def read_dcm_slice_as_np2(filename, resolution_percentage=1.0):
    reader = gdcm.ImageReader()
    reader.SetFileName(filename)
    reader.Read()
    image = reader.GetImage()
    output = converters.gdcm_to_numpy(image)
    if resolution_percentage < 1.0:
        output = zoom(output, resolution_percentage)
    return output


def FixGantryTilt(matrix, spacing, tilt):
    """
    Fix gantry tilt given a vtkImageData and the tilt value. Return new
    vtkImageData.
    """
    angle = numpy.radians(tilt)
    spacing = spacing[0], spacing[1], spacing[2]
    gntan = math.tan(angle)

    for n, slice_ in enumerate(matrix):
        offset = gntan * n * spacing[2]
        matrix[n] = shift(slice_, (-offset/spacing[1], 0), cval=matrix.min())


def BuildEditedImage(imagedata, points):
    """
    Editing the original image in accordance with the edit
    points in the editor, it is necessary to generate the
    vtkPolyData via vtkContourFilter
    """
    init_values = None
    for point in points:
        x, y, z = point
        colour = points[point]
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        imagedata.Update()

        if not(init_values):
                xi = x
                xf = x
                yi = y
                yf = y
                zi = z
                zf = z
                init_values = 1

        if (xi > x):
            xi = x
        elif(xf < x):
            xf = x

        if (yi > y):
            yi = y
        elif(yf < y):
            yf = y

        if (zi > z):
            zi = z
        elif(zf < z):
            zf = z

    clip = vtk.vtkImageClip()
    clip.SetInput(imagedata)
    clip.SetOutputWholeExtent(xi, xf, yi, yf, zi, zf)
    clip.Update()

    gauss = vtk.vtkImageGaussianSmooth()
    gauss.SetInput(clip.GetOutput())
    gauss.SetRadiusFactor(0.6)
    gauss.Update()

    app = vtk.vtkImageAppend()
    app.PreserveExtentsOn()
    app.SetAppendAxis(2)
    app.SetInput(0, imagedata)
    app.SetInput(1, gauss.GetOutput())
    app.Update()

    return app.GetOutput()


def Export(imagedata, filename, bin=False):
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(filename)
    if bin:
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAscii()
    #writer.SetInput(imagedata)
    #writer.Write()

def Import(filename):
    reader = vtk.vtkXMLImageDataReader()
    reader.SetFileName(filename)
    # TODO: Check if the code bellow is necessary
    reader.WholeSlicesOn()
    reader.Update()

    return reader.GetOutput()

def View(imagedata):
    viewer = vtk.vtkImageViewer()
    viewer.SetInput(imagedata)
    viewer.SetColorWindow(200)
    viewer.SetColorLevel(100)
    viewer.Render()

    import time
    time.sleep(10)


def ExtractVOI(imagedata,xi,xf,yi,yf,zi,zf):
    """
    Cropping the vtkImagedata according
    with values.
    """
    voi = vtk.vtkExtractVOI()
    voi.SetVOI(xi,xf,yi,yf,zi,zf)
    voi.SetInputData(imagedata)
    voi.SetSampleRate(1, 1, 1)
    voi.Update()
    return voi.GetOutput()


def create_dicom_thumbnails(image, window=None, level=None):
    pf = image.GetPixelFormat()
    np_image = converters.gdcm_to_numpy(image, pf.GetSamplesPerPixel() == 1)
    if window is None or level is None:
        _min, _max = np_image.min(), np_image.max()
        window = _max - _min
        level = _min + window / 2

    if image.GetNumberOfDimensions() >= 3:
        thumbnail_paths = []
        for i in range(np_image.shape[0]):
            thumb_image = zoom(np_image[i], 0.25)
            thumb_image = np.array(get_LUT_value_255(thumb_image, window, level), dtype=np.uint8)
            thumbnail_path = tempfile.mktemp(prefix='thumb_', suffix='.png')
            imageio.imsave(thumbnail_path, thumb_image)
            thumbnail_paths.append(thumbnail_path)
        return thumbnail_paths
    else:
        thumbnail_path = tempfile.mktemp(prefix='thumb_', suffix='.png')
        if pf.GetSamplesPerPixel() == 1:
            thumb_image = zoom(np_image, 0.25)
            thumb_image = np.array(get_LUT_value_255(thumb_image, window, level), dtype=np.uint8)
        else:
            thumb_image = zoom(np_image, (0.25, 0.25, 1))
        imageio.imsave(thumbnail_path, thumb_image)
        return thumbnail_path



def array2memmap(arr, filename=None):
    if filename is None:
        filename = tempfile.mktemp(prefix='inv3_', suffix='.dat')
    matrix = numpy.memmap(filename, mode='w+', dtype=arr.dtype, shape=arr.shape)
    matrix[:] = arr[:]
    matrix.flush()
    return matrix


def bitmap2memmap(files, slice_size, orientation, spacing, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename.
    """
    message = _("Generating multiplanar visualization...")
    if len(files) > 1:
        update_progress= vtk_utils.ShowProgress(len(files) - 1, dialog_type = "ProgressDialog")

    temp_file = tempfile.mktemp()

    if orientation == 'SAGITTAL':
        if resolution_percentage == 1.0:
            shape = slice_size[1], slice_size[0], len(files)
        else:
            shape = math.ceil(slice_size[1]*resolution_percentage),\
                    math.ceil(slice_size[0]*resolution_percentage), len(files)

    elif orientation == 'CORONAL':
        if resolution_percentage == 1.0:
            shape = slice_size[1], len(files), slice_size[0]
        else:
            shape = math.ceil(slice_size[1]*resolution_percentage), len(files),\
                                        math.ceil(slice_size[0]*resolution_percentage)
    else:
        if resolution_percentage == 1.0:
            shape = len(files), slice_size[1], slice_size[0]
        else:
            shape = len(files), math.ceil(slice_size[1]*resolution_percentage),\
                                        math.ceil(slice_size[0]*resolution_percentage)


    if resolution_percentage == 1.0:
        matrix = numpy.memmap(temp_file, mode='w+', dtype='int16', shape=shape)
    
    cont = 0
    max_scalar = None
    min_scalar = None

    xy_shape = None
    first_resample_entry = False

    for n, f in enumerate(files):
        image_as_array = bitmap_reader.ReadBitmap(f)

        image = converters.to_vtk(image_as_array, spacing=spacing,\
                                    slice_number=1, orientation=orientation.upper())

        if resolution_percentage != 1.0:
            
            
            image_resized = ResampleImage2D(image, px=None, py=None,\
                                resolution_percentage = resolution_percentage, update_progress = None)

            yx_shape = image_resized.GetDimensions()[1], image_resized.GetDimensions()[0]


            if not(first_resample_entry):
                shape = shape[0], yx_shape[0], yx_shape[1] 
                matrix = numpy.memmap(temp_file, mode='w+', dtype='int16', shape=shape)
                first_resample_entry = True

            image = image_resized

        min_aux, max_aux = image.GetScalarRange()
        if min_scalar is None or min_aux < min_scalar:
            min_scalar = min_aux

        if max_scalar is None or max_aux > max_scalar:
            max_scalar = max_aux

        array = numpy_support.vtk_to_numpy(image.GetPointData().GetScalars())

        if array.dtype == 'uint16':
            array = array - 32768/2
       
        array = array.astype("int16")

        if orientation == 'CORONAL':
            array.shape = matrix.shape[0], matrix.shape[2]
            matrix[:, n, :] = array[:,::-1]
        elif orientation == 'SAGITTAL':
            array.shape = matrix.shape[0], matrix.shape[1]
            # TODO: Verify if it's necessary to add the slices swapped only in
            # sagittal rmi or only in # Rasiane's case or is necessary in all
            # sagittal cases.
            matrix[:, :, n] = array[:,::-1]
        else:
            array.shape = matrix.shape[1], matrix.shape[2]
            matrix[n] = array
        
        if len(files) > 1:
            update_progress(cont,message)
        cont += 1

    matrix.flush()
    scalar_range = min_scalar, max_scalar

    print("MATRIX", matrix.shape)
    return matrix, scalar_range, temp_file


def dcm2memmap(files, slice_size, orientation, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename.
    """
    if len(files) > 1:
        message = _("Generating multiplanar visualization...")
        update_progress= vtk_utils.ShowProgress(len(files) - 1, dialog_type = "ProgressDialog")

    first_slice = read_dcm_slice_as_np2(files[0], resolution_percentage)
    slice_size = first_slice.shape[::-1]

    temp_file = tempfile.mktemp()

    if orientation == 'SAGITTAL':
        shape = slice_size[0], slice_size[1], len(files)
    elif orientation == 'CORONAL':
        shape = slice_size[1], len(files), slice_size[0]
    else:
        shape = len(files), slice_size[1], slice_size[0]

    matrix = numpy.memmap(temp_file, mode='w+', dtype='int16', shape=shape)
    for n, f in enumerate(files):
        im_array = read_dcm_slice_as_np2(f, resolution_percentage)[::-1]

        if orientation == 'CORONAL':
            matrix[:, shape[1] - n - 1, :] = im_array
        elif orientation == 'SAGITTAL':
            # TODO: Verify if it's necessary to add the slices swapped only in
            # sagittal rmi or only in # Rasiane's case or is necessary in all
            # sagittal cases.
            matrix[:, :, n] = im_array
        else:
            matrix[n] = im_array
        if len(files) > 1:
            update_progress(n, message)

    matrix.flush()
    scalar_range = matrix.min(), matrix.max()

    return matrix, scalar_range, temp_file


def dcmmf2memmap(dcm_file, orientation):
    reader = gdcm.ImageReader()
    reader.SetFileName(dcm_file)
    reader.Read()
    image = reader.GetImage()
    xs, ys, zs = image.GetSpacing()
    pf = image.GetPixelFormat()
    np_image = converters.gdcm_to_numpy(image, pf.GetSamplesPerPixel() == 1)
    temp_file = tempfile.mktemp()
    matrix = numpy.memmap(temp_file, mode='w+', dtype='int16', shape=np_image.shape)
    print("Number of dimensions", np_image.shape)
    z, y, x = np_image.shape
    if orientation == 'CORONAL':
        spacing = xs, zs, ys
        matrix.shape = y, z, x
        for n in range(z):
            matrix[:, n, :] = np_image[n][::-1]
    elif orientation == 'SAGITTAL':
        spacing = zs, ys, xs
        matrix.shape = y, x, z
        for n in range(z):
            matrix[:, :, n] = np_image[n][::-1]
    else:
        spacing = xs, ys, zs
        matrix[:] = np_image[:, ::-1, :]

    matrix.flush()
    scalar_range = matrix.min(), matrix.max()

    return matrix, scalar_range, spacing, temp_file


def img2memmap(group):
    """
    From a nibabel image data creates a memmap file in the temp folder and
    returns it and its related filename.
    """

    temp_file = tempfile.mktemp()

    data = group.get_data()
    # Normalize image pixel values and convert to int16
    #  data = imgnormalize(data)

    # Convert RAS+ to default InVesalius orientation ZYX
    data = numpy.swapaxes(data, 0, 2)
    data = numpy.fliplr(data)

    matrix = numpy.memmap(temp_file, mode='w+', dtype=np.int16, shape=data.shape)
    matrix[:] = data[:]
    matrix.flush()

    scalar_range = numpy.amin(matrix), numpy.amax(matrix)

    return matrix, scalar_range, temp_file


def get_LUT_value_255(data, window, level):
    shape = data.shape
    data_ = data.ravel()
    data = np.piecewise(data_,
                        [data_ <= (level - 0.5 - (window-1)/2),
                         data_ > (level - 0.5 + (window-1)/2)],
                        [0, 255, lambda data_: ((data_ - (level - 0.5))/(window-1) + 0.5)*(255)])
    data.shape = shape
    return data


def image_normalize(image, min_=0.0, max_=1.0, output_dtype=np.int16):
    output = np.empty(shape=image.shape, dtype=output_dtype)
    imin, imax = image.min(), image.max()
    output[:] = (image - imin) * ((max_ - min_) / (imax - imin)) + min_
    return output
