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
import os
import Queue
import threading
import tempfile
import sys
import vtk
import re
import constants as const
import wx

from wx.lib.pubsub import pub as Publisher
from multiprocessing import cpu_count

from vtk.util import numpy_support
from scipy import misc
import numpy
import imghdr

from data import converters

#flag to control vtk error in read files
no_error = True 
vtk_error = False

class Singleton:

    def __init__(self,klass):
        self.klass = klass
        self.instance = None
            
    def __call__(self,*args,**kwds):
        if self.instance == None:
            self.instance = self.klass(*args,**kwds)
        return self.instance

@Singleton
class BitmapData:

    def __init__(self):
        self.data = None

    def GetData(self):
        return self.data

class BitmapFiles:

    def __init__(self):
        self.bitmapfiles = []

    def Add(self, bmp):
        self.bitmapfiles.append(bmp)

    def Sort(self, x):

        c_re = re.compile('\d+')

        if len(c_re.findall(x[0])) > 0:
            return c_re.findall(x[0])[-1] 
        else:
            return '0'

    def GetValues(self):
        bmpfile = self.bitmapfiles
        bmpfile.sort(key = self.Sort)

        bmp_data = BitmapData()
        bmp_data.data = bmpfile

        return bmpfile

class LoadBitmap:

    def __init__(self, bmp_file, filepath):
        self.bmp_file = bmp_file
        if sys.platform == 'win32':
            self.filepath = filepath.encode(utils.get_system_encoding())
        else:
            self.filepath = filepath
        
        self.run()
    
    def run(self):
        global vtk_error

        #----- verify extension ------------------
        #ex = self.filepath.split('.')[-1]
        extension = VerifyDataType(self.filepath)

        file_name = self.filepath.split(os.path.sep)[-1]

        #if extension == 'bmp':
        #    reader = vtk.vtkBMPReader()
        n_array = ReadBitmap(self.filepath)
        
        image = converters.to_vtk(n_array, spacing=(1,1,1),\
                slice_number=1, orientation="AXIAL")


        #reader.SetFileName(self.filepath)
        #reader.Update()

        extent = image.GetExtent()
        x = extent[1]
        y = extent[3]

        img = vtk.vtkImageResample()
        img.SetInputData(image)
        img.SetAxisMagnificationFactor ( 0, 0.25 )
        img.SetAxisMagnificationFactor ( 1, 0.25 )
        img.SetAxisMagnificationFactor ( 2, 1 )    
        img.Update()

        tp = img.GetOutput().GetScalarTypeAsString()

        image_copy = vtk.vtkImageData()
        image_copy.DeepCopy(img.GetOutput())
        
        thumbnail_path = tempfile.mktemp()

        write_png = vtk.vtkPNGWriter()
        write_png.SetInputConnection(img.GetOutputPort())
        write_png.AddObserver("WarningEvent", VtkErrorPNGWriter)
        write_png.SetFileName(thumbnail_path)
        write_png.Write()

        if vtk_error:
            img = vtk.vtkImageCast()
            img.SetInputData(image_copy)
            img.SetOutputScalarTypeToUnsignedShort()
            #img.SetClampOverflow(1)
            img.Update()

            write_png = vtk.vtkPNGWriter()
            write_png.SetInputConnection(img.GetOutputPort())
            write_png.SetFileName(thumbnail_path)
            write_png.Write()
    
            vtk_error = False

        id = wx.NewId()

        bmp_item = [self.filepath, thumbnail_path, extension, x, y,\
                                str(x) + ' x ' + str(y), file_name, id]
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
                filepath = os.path.join(dirpath, name)
                counter += 1
                if gui:
                    yield (counter,nfiles)
                #LoadDicom(grouper, filepath)
                LoadBitmap(bmp_file, filepath)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        for name in filenames:
            filepath = str(os.path.join(dirpath, name))
            counter += 1
            if gui:
                yield (counter,nfiles)
            #q.put(filepath)

    #for t in threads:
    #    q.put(0)

    #for t in threads:
    #    t.join()

    #TODO: Is this commented update necessary?
    #grouper.Update()
    yield bmp_file.GetValues()


class ProgressBitmapReader:
    def __init__(self):
        Publisher.subscribe(self.CancelLoad, "Cancel bitmap load")

    def CancelLoad(self, evt_pubsub):
        self.running = False
        self.stoped = True

    def SetWindowEvent(self, frame):
        self.frame = frame          

    def SetDirectoryPath(self, path,recursive=True):
        self.running = True
        self.stoped = False
        self.GetBitmaps(path,recursive)

    def UpdateLoadFileProgress(self,cont_progress):
        Publisher.sendMessage("Update bitmap load", cont_progress)

    def EndLoadFile(self, bitmap_list):
        Publisher.sendMessage("End bitmap load", bitmap_list)

    def GetBitmaps(self, path, recursive):

        #if not const.VTK_WARNING:
        #    log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
        #    fow = vtk.vtkFileOutputWindow()
        #    fow.SetFileName(log_path)
        #    ow = vtk.vtkOutputWindow()
        #    ow.SetInstance(fow)

        y = yGetBitmaps(path, recursive)
        for value_progress in y:
            if not self.running:
                break
            if isinstance(value_progress, tuple):
                self.UpdateLoadFileProgress(value_progress)
            else:
                self.EndLoadFile(value_progress)

        #Is necessary in the case user cancel
        #the load, ensure that dicomdialog is closed
        if(self.stoped):
            self.UpdateLoadFileProgress(None)
            self.stoped = False   

def VtkErrorPNGWriter(obj, f):
    global vtk_error
    vtk_error = True

def ScipyRead(filepath):
    try:
        r = misc.imread(filepath, flatten=True)
        dt = r.dtype 

        if dt == "float32":   
            
            shift=-r.max()/2
            simage = numpy.zeros_like(r, dtype='int16')
            simage[:] = r.astype('int32') + shift

            return simage
        else:
            return r
    except(IOError):
        return False

def VtkRead(filepath, t):
    
    global no_error

    if t == "bmp":
        reader = vtk.vtkBMPReader()

    elif t == "tiff" or t == "tif":
        reader = vtk.vtkTIFFReader()

    elif t == "png":
        reader = vtk.vtkPNGReader()
    
    elif t == "jpeg" or t == "jpg":
        reader = vtk.vtkJPEGReader()

    else:
        return False

    reader.AddObserver("ErrorEvent", VtkErrorToPy)
    reader.SetFileName(filepath)
    reader.Update()
    
    if no_error:
        image = reader.GetOutput()
        extent = reader.GetDataExtent()
       
        #if reader.GetNumberOfScalarComponents() > 1:
        luminanceFilter = vtk.vtkImageLuminance()
        luminanceFilter.SetInputData(image)
        luminanceFilter.Update()

        img_array = numpy_support.vtk_to_numpy(luminanceFilter.GetOutput().GetPointData().GetScalars())
        img_array.shape = (extent[3] + 1,extent[1] + 1)

        return img_array
    else:
        no_error = True
        return False


def ReadBitmap(filepath): 
    
    t = VerifyDataType(filepath)

    if t == False:
        return False

    img_array = VtkRead(filepath, t)
    
    if not(isinstance(img_array, numpy.ndarray)):
        
        no_error = True
        
        img_array = ScipyRead(filepath)
        
        if not(isinstance(img_array, numpy.ndarray)):
            return False

    return img_array
            

def VtkErrorToPy(obj, evt):
    global no_error
    no_error = False


def VerifyDataType(filepath):
    try:
        t = imghdr.what(filepath)
        return t
    except IOError:
        return False
