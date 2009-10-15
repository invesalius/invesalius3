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
import data.imagedata_utils as iu

def LoadImages(dir_):

    patient_group = GetDicomGroups(dir_)
    filelist, dicom, zspacing = SelectLargerDicomGroup(patient_group)
    filelist = SortFiles(filelist, dicom)
    imagedata = CreateImageData(filelist, zspacing)
    
    return imagedata, dicom


def SelectLargerDicomGroup(patient_group):
    nslices_old = 0
    for patient in patient_group:
        group_list = patient.GetGroups()
        for group in group_list:
            nslices = group.nslices
            print "nslices:", nslices
            if (nslices >= nslices_old):
                dicoms = group.GetList()
                zspacing = group.zspacing
                nslices_old = nslices

    filelist = []
    for dicom in dicoms:
        filelist.append(dicom.image.file)
    return filelist, dicom, zspacing

def SortFiles(filelist, dicom):
    # Sort slices
    # FIXME: Coronal Crash. necessary verify
    if (dicom.image.orientation_label <> "CORONAL"):
        #Organize reversed image
        sorter = gdcm.IPPSorter()
        sorter.SetComputeZSpacing(True)
        sorter.SetZSpacingTolerance(1e-10)
        sorter.Sort(filelist)

        #Getting organized image
        filelist = sorter.GetFilenames()

    return filelist


def CreateImageData(filelist, zspacing):

    if not(const.REDUCE_IMAGEDATA_QUALITY):
        array = vtk.vtkStringArray()
        for x in xrange(len(filelist)):
            array.InsertValue(x,filelist[x])

        reader = vtkgdcm.vtkGDCMImageReader()
        reader.SetFileNames(array)
        reader.Update()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(reader.GetOutput())
        spacing = imagedata.GetSpacing()
        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)
    else:
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
            reader.Update()

            #Resample image in x,y dimension
            slice_imagedata = iu.ResampleImage2D(reader.GetOutput(), 256)

            #Stack images in Z axes
            appender.AddInput(slice_imagedata)
            appender.Update()

        # The zpacing is a DicomGroup property, so we need to set it
        imagedata = vtk.vtkImageData()
        imagedata.DeepCopy(appender.GetOutput())
        spacing = imagedata.GetSpacing()

        imagedata.SetSpacing(spacing[0], spacing[1], zspacing)

    imagedata.Update()
    return imagedata

def GetSeries(path):
    """
    Return DICOM group of files inside given directory.
    """
    dcm_files = GetDicomFiles(path)

    dcm_series = dicom_grouper.DicomGroups()
    dcm_series.SetFileList(dcm_files)
    dcm_series.Update()

    return dcm_series.GetOutput()

def GetDicomGroups(directory, recursive=True):
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
            
