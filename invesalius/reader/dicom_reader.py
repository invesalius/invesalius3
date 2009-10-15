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
import glob
import os

import vtk
import vtkgdcm
import gdcm

import constants as const
import dicom
import dicom_grouper
from data.imagedata_utils import ResampleImage2D

def LoadImages(dir_):
    #  TODO!!! SUPER GAMBIARRA!!! DO THIS BETTER

    patient_group = GetDicomFiles(dir_)
    print "1111111111111"
    #select the series with the largest 
    #number of slices.
    nslices_old = 0
    for patient in patient_group:
        group_list = patient.GetGroups()
        for group in group_list:
            nslices = group.nslices
            print "nslices:", nslices
            if (nslices >= nslices_old):
                dicoms = group.GetList()
                spacing = group.spacing
                nslices_old = nslices
    print "22222222222222"
    
    file_list = []
    for dicom in dicoms:
        file_list.append(dicom.image.file)



    #Coronal Crash. necessary verify
    if (dicom.image.orientation_label <> "CORONAL"):
        #Organize reversed image
        sorter = gdcm.IPPSorter()
        sorter.SetComputeZSpacing(True)
        sorter.SetZSpacingTolerance(1e-10)
        sorter.Sort(file_list)

        #Getting organized image
        files = sorter.GetFilenames()

    print "33333333333"

    array = vtk.vtkStringArray()

    img_app = vtk.vtkImageAppend()
    img_app.SetAppendAxis(2) #Define Stack in Z

    if not(const.REDUCE_IMAGEDATA_QUALITY):
        print "not reduce"
        for x in xrange(len(files)):
            array.InsertValue(x,files[x])

        read = vtkgdcm.vtkGDCMImageReader()
        read.SetFileNames(array)
        read.Update()

        image_data = vtk.vtkImageData()
        image_data.DeepCopy(read.GetOutput())
        
        image_data.SetSpacing(spacing)
    else:
        print "reduce"
        for x in xrange(len(files)):
            #SIf the resolution of the
            #matrix is very large
            read = vtkgdcm.vtkGDCMImageReader()
            read.SetFileName(files[x])
            read.Update()

            #Resample image in x,y dimension
            img = ResampleImage2D(read.GetOutput(), 256)

            #Stack images in Z axes
            img_app.AddInput(img)
            img_app.Update()


        print "444444444444444"
        image_data = vtk.vtkImageData()
        image_data.DeepCopy(img_app.GetOutput())
        image_data.SetSpacing(image_data.GetSpacing()[0],\
                         image_data.GetSpacing()[1], spacing)
        print "555555555"

    image_data.Update()
    print "66666666666666"

    return image_data, dicom

def GetDicomFilesOld(path, recursive = False):
    #  TODO!!! SUPER GAMBIARRA!!! DO THIS BETTER
    """
    Separate only files of a DICOM Determined
    directory. You can go recursively within
    the directory. (recursive = True)
    """
    result = []

    if (recursive == True):

        if os.path.isdir(path) and not os.path.islink(path):

            files = os.listdir(path)

            for file in files:
                path_ = os.path.join(path, file)
                FindDicom(path_, True)
        else:
            read_dicom = dicom.Parser()
            if(read_dicom.SetFileName(path)):
                if (read_dicom.GetImagePosition()):
                    result.append(path)
    else:
        files = glob.glob(path + os.sep + "*")
        for x in xrange(len(files)):
            read_dicom = dicom.Parser()
            if (read_dicom.SetFileName(files[x])):
                result.append(files[x])
        #  TODO!!! SUPER GAMBIARRA!!! DO THIS BETTER
    return result

def GetSeries(path):
    """
    Return DICOM group of files inside given directory.
    """
    dcm_files = GetDicomFiles(path)

    dcm_series = dicom_grouper.DicomGroups()
    dcm_series.SetFileList(dcm_files)
    dcm_series.Update()

    return dcm_series.GetOutput()

def GetDicomFiles(directory, recursive=True):
    """
    Return all full paths to DICOM files inside given directory.
    """
    grouper = dicom_grouper.DicomPatientGrouper()

    nfiles = 0
    # Find total number of files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            nfiles += len(filenames)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        nfiles = len(filenames)
    print "TOTAL FILES:", nfiles

    # Retrieve only DICOM files, splited into groups
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            print "@: ",dirpath
            for name in filenames:
                filepath = str(os.path.join(dirpath, name))
                parser = dicom.Parser()
                if parser.SetFileName(filepath):
                    dcm = dicom.Dicom()
                    dcm.SetParser(parser)
                    grouper.AddFile(dcm)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        print "@: ",dirpath
        for name in filenames:
            filepath = str(os.path.join(dirpath, name))
            parser = dicom.Parser()
            if parser.SetFileName(filepath):
                dcm = dicom.Dicom()
                dcm.SetParser(parser)
                grouper.AddFile(dcm)

    return grouper.GetPatientsGroups()
            
