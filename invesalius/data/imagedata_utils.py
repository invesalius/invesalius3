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
import numpy
import vtk
import vtkgdcm
from wx.lib.pubsub import pub as Publisher

from scipy.ndimage import shift, zoom
from vtk.util import numpy_support

import invesalius.constants as const
from invesalius.data import vtk_utils as vtk_utils
import invesalius.reader.bitmap_reader as bitmap_reader
import invesalius.utils as utils
import invesalius.data.converters as converters

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
    resample.SetOutputSpacing(spacing[0] * factor_x, spacing[1] * factor_y, spacing[2])
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


def read_dcm_slice_as_np(filename, resolution_percentage=1.0):
    """
    read a dicom slice file and return the slice as numpy ndarray
    """
    dcm_reader = vtkgdcm.vtkGDCMImageReader()
    dcm_reader.SetFileName(filename)
    dcm_reader.Update()
    image = dcm_reader.GetOutput()
    if resolution_percentage < 1.0:
        image = ResampleImage2D(image, resolution_percentage=resolution_percentage)
    dx, dy, dz = image.GetDimensions()
    im_array = numpy_support.vtk_to_numpy(image.GetPointData().GetScalars())
    im_array.shape = dy, dx
    return im_array


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

def ViewGDCM(imagedata):
    viewer = vtkgdcm.vtkImageColorViewer()
    viewer.SetInput(reader.GetOutput())
    viewer.SetColorWindow(500.)
    viewer.SetColorLevel(50.)
    viewer.Render()

    import time
    time.sleep(5)



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


def create_dicom_thumbnails(filename, window=None, level=None):
    rvtk = vtkgdcm.vtkGDCMImageReader()
    rvtk.SetFileName(filename)
    rvtk.Update()

    img = rvtk.GetOutput()
    if window is None or level is None:
        _min, _max = img.GetScalarRange()
        window = _max - _min
        level = _min + window / 2

    dx, dy, dz = img.GetDimensions()

    if dz > 1:
        thumbnail_paths = []
        for i in xrange(dz):
            img_slice = ExtractVOI(img, 0, dx-1, 0, dy-1, i, i+1)

            colorer = vtk.vtkImageMapToWindowLevelColors()
            colorer.SetInputData(img_slice)
            colorer.SetWindow(window)
            colorer.SetLevel(level)
            colorer.SetOutputFormatToRGB()
            colorer.Update()

            resample = vtk.vtkImageResample()
            resample.SetInputData(colorer.GetOutput())
            resample.SetAxisMagnificationFactor ( 0, 0.25 )
            resample.SetAxisMagnificationFactor ( 1, 0.25 )
            resample.SetAxisMagnificationFactor ( 2, 1 )
            resample.Update()

            thumbnail_path = tempfile.mktemp()

            write_png = vtk.vtkPNGWriter()
            write_png.SetInputData(resample.GetOutput())
            write_png.SetFileName(thumbnail_path)
            write_png.Write()

            thumbnail_paths.append(thumbnail_path)

        return thumbnail_paths
    else:
        colorer = vtk.vtkImageMapToWindowLevelColors()
        colorer.SetInputData(img)
        colorer.SetWindow(window)
        colorer.SetLevel(level)
        colorer.SetOutputFormatToRGB()
        colorer.Update()

        resample = vtk.vtkImageResample()
        resample.SetInputData(colorer.GetOutput())
        resample.SetAxisMagnificationFactor ( 0, 0.25 )
        resample.SetAxisMagnificationFactor ( 1, 0.25 )
        resample.SetAxisMagnificationFactor ( 2, 1 )
        resample.Update()

        thumbnail_path = tempfile.mktemp()

        write_png = vtk.vtkPNGWriter()
        write_png.SetInputData(resample.GetOutput())
        write_png.SetFileName(thumbnail_path)
        write_png.Write()

        return thumbnail_path


def CreateImageData(filelist, zspacing, xyspacing,size,
                                bits, use_dcmspacing):
    message = _("Generating multiplanar visualization...")

    if not const.VTK_WARNING:
        log_path = os.path.join(const.USER_LOG_DIR, 'vtkoutput.txt')
        fow = vtk.vtkFileOutputWindow()
        fow.SetFileName(log_path)
        ow = vtk.vtkOutputWindow()
        ow.SetInstance(fow)

    x,y = size
    px, py = utils.predict_memory(len(filelist), x, y, bits)

    utils.debug("Image Resized to >>> %f x %f" % (px, py))

    if (x == px) and (y == py):
        const.REDUCE_IMAGEDATA_QUALITY = 0
    else:
        const.REDUCE_IMAGEDATA_QUALITY = 1

    if not(const.REDUCE_IMAGEDATA_QUALITY):
        update_progress= vtk_utils.ShowProgress(1, dialog_type = "ProgressDialog")

        array = vtk.vtkStringArray()
        for x in xrange(len(filelist)):
            array.InsertValue(x,filelist[x])

        reader = vtkgdcm.vtkGDCMImageReader()
        reader.SetFileNames(array)
        reader.AddObserver("ProgressEvent", lambda obj,evt:
                     update_progress(reader,message))
        reader.Update()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(reader.GetOutput())
        if (use_dcmspacing):
            spacing = xyspacing
            spacing[2] = zspacing
        else:
            spacing = imagedata.GetSpacing()

        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)
    else:

        update_progress= vtk_utils.ShowProgress(2*len(filelist),
                                            dialog_type = "ProgressDialog")

        # Reformat each slice and future append them
        appender = vtk.vtkImageAppend()
        appender.SetAppendAxis(2) #Define Stack in Z


        # Reformat each slice
        for x in xrange(len(filelist)):
            # TODO: We need to check this automatically according
            # to each computer's architecture
            # If the resolution of the matrix is too large
            reader = vtkgdcm.vtkGDCMImageReader()
            reader.SetFileName(filelist[x])
            reader.AddObserver("ProgressEvent", lambda obj,evt:
                         update_progress(reader,message))
            reader.Update()

            if (use_dcmspacing):
                spacing = xyspacing
                spacing[2] = zspacing
            else:
                spacing = reader.GetOutput().GetSpacing()

            tmp_image = vtk.vtkImageData()
            tmp_image.DeepCopy(reader.GetOutput())
            tmp_image.SetSpacing(spacing[0], spacing[1], zspacing)
            tmp_image.Update()

            #Resample image in x,y dimension
            slice_imagedata = ResampleImage2D(tmp_image, px, py, update_progress)
            #Stack images in Z axes
            appender.AddInput(slice_imagedata)
            #appender.AddObserver("ProgressEvent", lambda obj,evt:update_progress(appender))
            appender.Update()

        spacing = appender.GetOutput().GetSpacing()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(appender.GetOutput())
        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)

    imagedata.AddObserver("ProgressEvent", lambda obj,evt:
                 update_progress(imagedata,message))
    imagedata.Update()

    return imagedata


class ImageCreator:
    def __init__(self):
        self.running = True
        Publisher.subscribe(self.CancelImageDataLoad, "Cancel DICOM load")

    def CancelImageDataLoad(self, evt_pusub):
        utils.debug("Canceling")
        self.running = False

    def CreateImageData(self, filelist, zspacing, size, bits):
        message = _("Generating multiplanar visualization...")

        if not const.VTK_WARNING:
            log_path = os.path.join(const.USER_LOG_DIR, 'vtkoutput.txt')
            fow = vtk.vtkFileOutputWindow()
            fow.SetFileName(log_path)
            ow = vtk.vtkOutputWindow()
            ow.SetInstance(fow)

        x,y = size
        px, py = utils.predict_memory(len(filelist), x, y, bits)
        utils.debug("Image Resized to >>> %f x %f" % (px, py))

        if (x == px) and (y == py):
            const.REDUCE_IMAGEDATA_QUALITY = 0
        else:
            const.REDUCE_IMAGEDATA_QUALITY = 1

        if not(const.REDUCE_IMAGEDATA_QUALITY):
            update_progress= vtk_utils.ShowProgress(1, dialog_type = "ProgressDialog")

            array = vtk.vtkStringArray()
            for x in xrange(len(filelist)):
                if not self.running:
                    return False
                array.InsertValue(x,filelist[x])

            if not self.running:
                return False
            reader = vtkgdcm.vtkGDCMImageReader()
            reader.SetFileNames(array)
            reader.AddObserver("ProgressEvent", lambda obj,evt:
                         update_progress(reader,message))
            reader.Update()

            if not self.running:
                reader.AbortExecuteOn()
                return False
            # The zpacing is a DicomGroup property, so we need to set it
            imagedata = vtk.vtkImageData()
            imagedata.DeepCopy(reader.GetOutput())
            spacing = imagedata.GetSpacing()
            imagedata.SetSpacing(spacing[0], spacing[1], zspacing)
        else:

            update_progress= vtk_utils.ShowProgress(2*len(filelist),
                                                dialog_type = "ProgressDialog")

            # Reformat each slice and future append them
            appender = vtk.vtkImageAppend()
            appender.SetAppendAxis(2) #Define Stack in Z


            # Reformat each slice
            for x in xrange(len(filelist)):
                # TODO: We need to check this automatically according
                # to each computer's architecture
                # If the resolution of the matrix is too large
                if not self.running:
                    return False
                reader = vtkgdcm.vtkGDCMImageReader()
                reader.SetFileName(filelist[x])
                reader.AddObserver("ProgressEvent", lambda obj,evt:
                             update_progress(reader,message))
                reader.Update()

                #Resample image in x,y dimension
                slice_imagedata = ResampleImage2D(reader.GetOutput(), px, py, update_progress)
                #Stack images in Z axes
                appender.AddInput(slice_imagedata)
                #appender.AddObserver("ProgressEvent", lambda obj,evt:update_progress(appender))
                appender.Update()

            # The zpacing is a DicomGroup property, so we need to set it
            if not self.running:
                return False
            imagedata = vtk.vtkImageData()
            imagedata.DeepCopy(appender.GetOutput())
            spacing = imagedata.GetSpacing()

            imagedata.SetSpacing(spacing[0], spacing[1], zspacing)

        imagedata.AddObserver("ProgressEvent", lambda obj,evt:
                     update_progress(imagedata,message))
        imagedata.Update()

        return imagedata

def bitmap2memmap(files, slice_size, orientation, spacing, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename.
    """
    message = _("Generating multiplanar visualization...")
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
        
        update_progress(cont,message)
        cont += 1

    matrix.flush()
    scalar_range = min_scalar, max_scalar

    return matrix, scalar_range, temp_file



def dcm2memmap(files, slice_size, orientation, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename.
    """
    message = _("Generating multiplanar visualization...")
    update_progress= vtk_utils.ShowProgress(len(files) - 1, dialog_type = "ProgressDialog")

    first_slice = read_dcm_slice_as_np(files[0], resolution_percentage)
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
        im_array = read_dcm_slice_as_np(f, resolution_percentage)

        if orientation == 'CORONAL':
            matrix[:, shape[1] - n - 1, :] = im_array
        elif orientation == 'SAGITTAL':
            # TODO: Verify if it's necessary to add the slices swapped only in
            # sagittal rmi or only in # Rasiane's case or is necessary in all
            # sagittal cases.
            matrix[:, :, n] = im_array
        else:
            matrix[n] = im_array
        update_progress(n, message)

    matrix.flush()
    scalar_range = matrix.min(), matrix.max()

    return matrix, scalar_range, temp_file


def dcmmf2memmap(dcm_file, orientation):
    r = vtkgdcm.vtkGDCMImageReader()
    r.SetFileName(dcm_file)
    r.Update()

    temp_file = tempfile.mktemp()

    o = r.GetOutput()
    x, y, z = o.GetDimensions()
    spacing = o.GetSpacing()

    matrix = numpy.memmap(temp_file, mode='w+', dtype='int16', shape=(z, y, x))

    d = numpy_support.vtk_to_numpy(o.GetPointData().GetScalars())
    d.shape = z, y, x
    if orientation == 'CORONAL':
        matrix.shape = y, z, x
        for n in xrange(z):
            matrix[:, n, :] = d[n]
    elif orientation == 'SAGITTAL':
        matrix.shape = x, z, y
        for n in xrange(z):
            matrix[:, :, n] = d[n]
    else:
        matrix[:] = d

    matrix.flush()
    scalar_range = matrix.min(), matrix.max()

    print "ORIENTATION", orientation

    return matrix, spacing, scalar_range, temp_file


def img2memmap(group):
    """
    From a nibabel image data creates a memmap file in the temp folder and
    returns it and its related filename.
    """

    temp_file = tempfile.mktemp()

    data = group.get_data()
    # Normalize image pixel values and convert to int16
    data = imgnormalize(data)

    # Convert RAS+ to default InVesalius orientation ZYX
    data = numpy.swapaxes(data, 0, 2)
    data = numpy.fliplr(data)

    matrix = numpy.memmap(temp_file, mode='w+', dtype=data.dtype, shape=data.shape)
    matrix[:] = data[:]
    matrix.flush()

    scalar_range = numpy.amin(matrix), numpy.amax(matrix)

    return matrix, scalar_range, temp_file


def imgnormalize(data, srange=(0, 255)):
    """
    Normalize image pixel intensity for int16 gray scale values.

    :param data: image matrix
    :param srange: range for normalization, default is 0 to 255
    :return: normalized pixel intensity matrix
    """

    dataf = numpy.asarray(data)
    rangef = numpy.asarray(srange)
    faux = numpy.ravel(dataf).astype(float)
    minimum = numpy.min(faux)
    maximum = numpy.max(faux)
    lower = rangef[0]
    upper = rangef[1]

    if minimum == maximum:
        datan = numpy.ones(dataf.shape)*(upper + lower) / 2.
    else:
        datan = (faux-minimum)*(upper-lower) / (maximum-minimum) + lower

    datan = numpy.reshape(datan, dataf.shape)
    datan = datan.astype(numpy.int16)

    return datan
