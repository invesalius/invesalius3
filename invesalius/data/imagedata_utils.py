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
import vtk
import vtkgdcm
import wx.lib.pubsub as ps

import constants as const
from data import vtk_utils


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

def ResampleImage2D(imagedata, xy_dimension, 
                        update_progress = None):
    """
    Resample vtkImageData matrix.
    """
    extent = imagedata.GetExtent()
    spacing = imagedata.GetSpacing()

    if extent[1]==extent[3]:
        f = extent[1]
        x = 0
        y = 1

    elif extent[1]==extent[5]:
        f = extent[1]
        x=0
        y=2

    elif extent[3]==extent[5]:
        f = extent[3]
        x = 1
        y = 2

    factor = xy_dimension/float(f+1)

    resample = vtk.vtkImageResample()
    resample.SetInput(imagedata)
    resample.SetAxisMagnificationFactor(0, factor)
    resample.SetAxisMagnificationFactor(1, factor)
    resample.SetOutputSpacing(spacing[0] * factor, spacing[1] * factor, spacing[2])
    if (update_progress):
        message = "Generating multiplanar visualization..."
        resample.AddObserver("ProgressEvent", lambda obj,
                             evt:update_progress(resample,message))
    resample.Update()


    return resample.GetOutput()

def FixGantryTilt(imagedata, tilt):
    """
    Fix gantry tilt given a vtkImageData and the tilt value. Return new
    vtkImageData.
    """

    # Retrieve data from original imagedata
    extent = [int(value) for value in imagedata.GetExtent()]
    origin = imagedata.GetOrigin()
    spacing = [float(value) for value in imagedata.GetSpacing()]

    n_slices = int(extent[5])
    new_zspacing = math.cos(tilt*(math.acos(-1.0)/180.0)) * spacing[2] #zspacing
    translate_coef = math.tan(tilt*math.pi/180.0)*new_zspacing*(n_slices-1)

    # Class responsible for translating data
    reslice = vtk.vtkImageReslice()
    reslice.SetInput(imagedata)
    reslice.SetInterpolationModeToLinear()
    # Translation will create new pixels. Let's set new pixels' colour to black.
    reslice.SetBackgroundLevel(imagedata.GetScalarRange()[0])

    # Class responsible for append translated data
    append = vtk.vtkImageAppend()
    append.SetAppendAxis(2)

    # Translate and append each slice
    for i in xrange(n_slices+1):
        slice_imagedata = vtk.vtkImageData()
        value = math.tan(tilt*math.pi/180.0) * new_zspacing * i
        new_origin1 = origin[1] + value - translate_coef
        # Translate data
        reslice.SetOutputOrigin(origin[0], new_origin1, origin[2])
        reslice.SetOutputExtent(extent[0], extent[1], extent[2], extent[3], i,i)
        reslice.Update()
        # Append data
        slice_imagedata.DeepCopy(reslice.GetOutput())
        slice_imagedata.UpdateInformation()

        append.AddInput(slice_imagedata)

    append.Update()

    # Final imagedata
    imagedata = vtk.vtkImageData()
    imagedata.DeepCopy(append.GetOutput())
    imagedata.SetSpacing(spacing[0], spacing[1], new_zspacing)
    imagedata.SetExtent(extent)
    imagedata.UpdateInformation()

    return imagedata


def BuildEditedImage(imagedata, points):
    """
    Editing the original image in accordance with the edit
    points in the editor, it is necessary to generate the
    vtkPolyData via vtkContourFilter
    """
    for point in points:
        x, y, z = point
        colour = points[point]
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        imagedata.Update()

    return imagedata

def Export(imagedata, filename, bin=False):
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(filename)
    if bin:
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAscii()
    writer.SetInput(imagedata)
    writer.Write()

def Import(filename):
    reader = vtk.vtkXMLImageDataReader()
    reader.SetFileName(filename)
    #reader.WholeSlicesOn()
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
    voi.SetInput(imagedata)
    voi.SetSampleRate(1, 1, 1)
    voi.Update()  
    return voi.GetOutput()

def CreateImageData(filelist, zspacing):
    message = "Generating multiplanar visualization..."
    if not(const.REDUCE_IMAGEDATA_QUALITY):
        update_progress= vtk_utils.ShowProgress(1)

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

            #Resample image in x,y dimension
            slice_imagedata = ResampleImage2D(reader.GetOutput(), 256, update_progress)

            #Stack images in Z axes
            appender.AddInput(slice_imagedata)
            #appender.AddObserver("ProgressEvent", lambda obj,evt:update_progress(appender))
            appender.Update()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(appender.GetOutput())
        spacing = imagedata.GetSpacing()

        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)

    imagedata.AddObserver("ProgressEvent", lambda obj,evt:
                 update_progress(imagedata,message))
    imagedata.Update()
    
    return imagedata


class ImageCreator:
    def __init__(self):
        ps.Publisher().sendMessage("Cancel imagedata load", self.CancelImageDataLoad)
        
    def CancelImageDataLoad(self, evt_pusub):
        self.running = evt_pusub.data
        
    def CreateImageData(filelist, zspacing):
        message = "Generating multiplanar visualization..."
        if not(const.REDUCE_IMAGEDATA_QUALITY):
            update_progress= vtk_utils.ShowProgress(1)
    
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
    
                #Resample image in x,y dimension
                slice_imagedata = ResampleImage2D(reader.GetOutput(), 256, update_progress)
    
                #Stack images in Z axes
                appender.AddInput(slice_imagedata)
                #appender.AddObserver("ProgressEvent", lambda obj,evt:update_progress(appender))
                appender.Update()
    
            # The zpacing is a DicomGroup property, so we need to set it
            imagedata = vtk.vtkImageData()
            imagedata.DeepCopy(appender.GetOutput())
            spacing = imagedata.GetSpacing()
    
            imagedata.SetSpacing(spacing[0], spacing[1], zspacing)
    
        imagedata.AddObserver("ProgressEvent", lambda obj,evt:
                     update_progress(imagedata,message))
        imagedata.Update()
        
        return imagedata
    

