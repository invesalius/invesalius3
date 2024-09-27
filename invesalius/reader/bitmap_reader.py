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
import imghdr
import os
import re
import sys
import tempfile

import numpy
import wx
from imageio import imread
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow
from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkImagingColor import vtkImageLuminance
from vtkmodules.vtkImagingCore import vtkImageCast, vtkImageResample
from vtkmodules.vtkIOImage import (
    vtkBMPReader,
    vtkJPEGReader,
    vtkPNGReader,
    vtkPNGWriter,
    vtkTIFFReader,
)

import invesalius.constants as const
import invesalius.data.converters as converters
import invesalius.utils as utils
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher

# flag to control vtk error in read files
no_error = True
vtk_error = False

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False


class Singleton:
    def __init__(self, klass):
        self.klass = klass
        self.instance = None

    def __call__(self, *args, **kwds):
        if self.instance is None:
            self.instance = self.klass(*args, **kwds)
        return self.instance


@Singleton
class BitmapData:
    def __init__(self):
        self.data = None

    def GetData(self):
        return self.data

    def SetData(self, data):
        self.data = data

    def GetOnlyBitmapPath(self):
        paths = [item[0] for item in self.data]
        return paths

    def GetFirstBitmapSize(self):
        return (self.data[0][3], self.data[0][4])

    def IsAllBitmapSameSize(self):
        sizes = [item[5] for item in self.data]

        k = {}
        for v in sizes:
            k[v] = ""

        if len(k.keys()) > 1:
            return False
        else:
            return True

    def GetFirstPixelSize(self):
        path = self.data[0][0]
        size = ReadBitmap(path).dtype.itemsize * 8

        return size

    def RemoveFileByPath(self, path):
        for d in self.data:
            if path in d:
                self.data.remove(d)

    def GetIndexByPath(self, path):
        for i, v in enumerate(self.data):
            if path in v:
                return i


class BitmapFiles:
    def __init__(self):
        self.bitmapfiles = []

    def Add(self, bmp):
        self.bitmapfiles.append(bmp)

    def Sort(self, x):
        c_re = re.compile("\d+")
        if len(c_re.findall(x[6])) > 0:
            return [int(i) for i in c_re.findall(x[6])]
        else:
            return [str(x[6])]

    def GetValues(self):
        bmpfile = self.bitmapfiles
        bmpfile.sort(key=self.Sort)

        bmp_data = BitmapData()
        bmp_data.data = bmpfile

        return bmpfile


class LoadBitmap:
    def __init__(self, bmp_file, filepath):
        self.bmp_file = bmp_file
        # self.filepath = utils.decode(filepath, const.FS_ENCODE)
        self.filepath = filepath

        self.run()

    def run(self):
        global vtk_error

        # ----- verify extension ------------------
        extension = VerifyDataType(self.filepath)

        file_name = self.filepath.decode(const.FS_ENCODE).split(os.path.sep)[-1]

        n_array = ReadBitmap(self.filepath)

        if not (isinstance(n_array, numpy.ndarray)):
            return False

        image = converters.to_vtk(n_array, spacing=(1, 1, 1), slice_number=1, orientation="AXIAL")

        dim = image.GetDimensions()
        x = dim[0]
        y = dim[1]

        img = vtkImageResample()
        img.SetInputData(image)
        img.SetAxisMagnificationFactor(0, 0.25)
        img.SetAxisMagnificationFactor(1, 0.25)
        img.SetAxisMagnificationFactor(2, 1)
        img.Update()

        # tp = img.GetOutput().GetScalarTypeAsString()

        image_copy = vtkImageData()
        image_copy.DeepCopy(img.GetOutput())

        fd, thumbnail_path = tempfile.mkstemp()

        write_png = vtkPNGWriter()
        write_png.SetInputConnection(img.GetOutputPort())
        write_png.AddObserver("WarningEvent", VtkErrorPNGWriter)
        write_png.SetFileName(thumbnail_path)
        write_png.Write()

        if vtk_error:
            img = vtkImageCast()
            img.SetInputData(image_copy)
            img.SetOutputScalarTypeToUnsignedShort()
            # img.SetClampOverflow(1)
            img.Update()

            write_png = vtkPNGWriter()
            write_png.SetInputConnection(img.GetOutputPort())
            write_png.SetFileName(thumbnail_path)
            write_png.Write()

            vtk_error = False

        id = wx.NewIdRef()

        bmp_item = [
            self.filepath,
            thumbnail_path,
            extension,
            x,
            y,
            str(x) + " x " + str(y),
            file_name,
            id,
        ]
        os.close(fd)
        self.bmp_file.Add(bmp_item)


def yGetBitmaps(directory, recursive=True, gui=True):
    """
    Return all full paths to DICOM files inside given directory.
    """
    nfiles = 0
    # Find total number of files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            nfiles += len(filenames)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        nfiles = len(filenames)

    counter = 0
    bmp_file = BitmapFiles()

    # Retrieve only TIFF, BMP, JPEG and PNG files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                filepath = os.path.join(dirpath, name).encode(const.FS_ENCODE)
                counter += 1
                if gui:
                    yield (counter, nfiles)
                LoadBitmap(bmp_file, filepath)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        for name in filenames:
            filepath = str(os.path.join(dirpath, name)).encode(const.FS_ENCODE)
            counter += 1
            if gui:
                yield (counter, nfiles)

    yield bmp_file.GetValues()


class ProgressBitmapReader:
    def __init__(self):
        Publisher.subscribe(self.CancelLoad, "Cancel bitmap load")

    def CancelLoad(self):
        self.running = False
        self.stoped = True

    def SetWindowEvent(self, frame):
        self.frame = frame

    def SetDirectoryPath(self, path, recursive=True):
        self.running = True
        self.stoped = False
        self.GetBitmaps(path, recursive)

    def UpdateLoadFileProgress(self, cont_progress):
        Publisher.sendMessage("Update bitmap load", data=cont_progress)

    def EndLoadFile(self, bitmap_list):
        Publisher.sendMessage("End bitmap load", data=bitmap_list)

    def GetBitmaps(self, path, recursive):
        y = yGetBitmaps(path, recursive)
        for value_progress in y:
            if not self.running:
                break
            if isinstance(value_progress, tuple):
                self.UpdateLoadFileProgress(value_progress)
            else:
                self.EndLoadFile(value_progress)

        self.UpdateLoadFileProgress(None)
        self.stoped = False


def VtkErrorPNGWriter(obj, f):
    global vtk_error
    vtk_error = True


def ScipyRead(filepath):
    try:
        r = imread(filepath, flatten=True)
        dt = r.dtype
        if dt == "float" or dt == "float16" or dt == "float32" or dt == "float64":
            shift = -r.max() / 2
            simage = numpy.zeros_like(r, dtype="int16")
            simage[:] = r.astype("int32") + shift

            return simage
        else:
            return r
    except OSError:
        return False


def VtkRead(filepath, t):
    if not const.VTK_WARNING:
        log_path = os.path.join(inv_paths.USER_LOG_DIR, "vtkoutput.txt")
        fow = vtkFileOutputWindow()
        fow.SetFileName(log_path.encode(const.FS_ENCODE))
        ow = vtkOutputWindow()
        ow.SetInstance(fow)

    global no_error

    if t == "bmp":
        reader = vtkBMPReader()

    elif t == "tiff" or t == "tif":
        reader = vtkTIFFReader()

    elif t == "png":
        reader = vtkPNGReader()

    elif t == "jpeg" or t == "jpg":
        reader = vtkJPEGReader()

    else:
        return False

    reader.AddObserver("ErrorEvent", VtkErrorToPy)
    reader.SetFileName(filepath)
    reader.Update()

    if no_error:
        image = reader.GetOutput()
        dim = image.GetDimensions()

        if reader.GetNumberOfScalarComponents() > 1:
            luminanceFilter = vtkImageLuminance()
            luminanceFilter.SetInputData(image)
            luminanceFilter.Update()

            image = vtkImageData()
            image.DeepCopy(luminanceFilter.GetOutput())

        img_array = numpy_support.vtk_to_numpy(image.GetPointData().GetScalars())
        img_array.shape = (dim[1], dim[0])

        return img_array
    else:
        no_error = True
        return False


def ReadBitmap(filepath):
    t = VerifyDataType(filepath)

    if _has_win32api:
        filepath = win32api.GetShortPathName(filepath)

    if t is False:
        try:
            measures_info = GetPixelSpacingFromInfoFile(filepath)
        except UnicodeDecodeError:
            measures_info = False
        if measures_info:
            Publisher.sendMessage("Set bitmap spacing", spacing=measures_info)

        return False

    img_array = VtkRead(filepath, t)

    if not (isinstance(img_array, numpy.ndarray)):
        # no_error = True

        img_array = ScipyRead(filepath)

        if not (isinstance(img_array, numpy.ndarray)):
            return False

    return img_array


def GetPixelSpacingFromInfoFile(filepath):
    filepath = utils.decode(filepath, const.FS_ENCODE)

    if filepath.endswith(".DS_Store"):
        return False

    try:
        fi = open(filepath)
        lines = fi.readlines()
    except UnicodeDecodeError:
        # fix uCTI from CTI file
        try:
            fi = open(filepath, encoding="iso8859-1")
            lines = fi.readlines()
        except UnicodeDecodeError:
            return False

    measure_scale = "mm"
    values = []

    if len(lines) > 0:
        # info text from avizo
        if "# Avizo Stacked Slices" in lines[0]:
            value = lines[2].split(" ")
            spx = float(value[1])
            spy = float(value[2])
            value = lines[5].split(" ")
            spz = float(value[1])

            return [spx * 0.001, spy * 0.001, spz * 0.001]
        else:
            # info text from skyscan
            for line in lines:
                if "Pixel Size" in line:
                    if "um" in line:
                        measure_scale = "um"

                    value = line.split("=")[-1]
                    values.append(value)

            if len(values) > 0:
                value = values[-1]

                value = value.replace("\n", "")
                value = value.replace("\r", "")

                # convert um to mm (InVesalius default)
                if measure_scale == "um":
                    value = float(value) * 0.001
                    measure_scale = "mm"

                elif measure_scale == "nm":
                    value = float(value) * 0.000001

                return [value, value, value]
            else:
                return False
    else:
        return False


def VtkErrorToPy(obj, evt):
    global no_error
    no_error = False


def VerifyDataType(filepath):
    try:
        filepath = utils.decode(filepath, const.FS_ENCODE)
        t = imghdr.what(filepath)
        if t:
            return t
        else:
            return False
    except OSError:
        return False
