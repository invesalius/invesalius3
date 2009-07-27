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

import dicom
import dicom_grouper
from data.imagedata_utils import ResampleImage2D

import constants as const
def LoadImages(dir_):
    #  TODO!!! SUPER GAMBIARRA!!! DO THIS BETTER

    #if 0:
    fow = vtk.vtkFileOutputWindow()
    fow.SetFileName('vtk_output.txt')
    ow = vtk.vtkOutputWindow ()
    ow.SetInstance (fow)

    dcm_files, acquisition_modality = GetDicomFiles(dir_)

    dcm_series = dicom_grouper.ivDicomGroups()
    dcm_series.SetFileList(dcm_files)
    dcm_series.Update()

    groups = dcm_series.GetOutput()

    tmp_list = []
    list_files = []

    for x in xrange(len(groups.keys())):
        key = groups.keys()[x]

        for y in xrange(len(groups[key][0])):

            file = groups[key][0][y][8]
            tmp_list.append(file)

        list_files.append([len(tmp_list), key])
        tmp_list = []

    if list_files:
        key =  max(list_files)[1]
    else:
        return None

    file_list = []
    for x in xrange(len(groups[key][0])):
        file_list.append(groups[key][0][x][8])

    tilt = groups[key][0][x][11]
    spacing = groups[key][1][14]
    spacing_z = groups[key][1][30]


    #Organize reversed image
    sorter = gdcm.IPPSorter()
    sorter.SetComputeZSpacing(True)
    sorter.SetZSpacingTolerance(1e-10)
    sorter.Sort(file_list)

    #Getting organized image
    files = sorter.GetFilenames()

    array = vtk.vtkStringArray()

    #Case Reduce Matrix of the Image
    reduce_matrix = 0

    img_app = vtk.vtkImageAppend()
    img_app.SetAppendAxis(2) #Define Stack in Z

    for x in xrange(len(files)):
        if not(reduce_matrix):
            array.InsertValue(x,files[x])
        else:
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

    img_axial = vtk.vtkImageData()

    if (reduce_matrix):
        img_axial.DeepCopy(img_app.GetOutput())
        img_axial.SetSpacing(img_axial.GetSpacing()[0],\
                             img_axial.GetSpacing()[1],\
                             spacing_z)
    else:
        read = vtkgdcm.vtkGDCMImageReader()
        read.SetFileNames(array)
        read.Update()

        img_axial.DeepCopy(read.GetOutput())
        img_axial.SetSpacing(spacing, spacing, spacing_z)

    img_axial.Update()

    thresh_min, thresh_max = img_axial.GetScalarRange()
    const.THRESHOLD_INVALUE = thresh_max
    const.THRESHOLD_OUTVALUE = thresh_min

    return img_axial, acquisition_modality, tilt

def GetDicomFiles(path, recursive = False):
    #  TODO!!! SUPER GAMBIARRA!!! DO THIS BETTER
    """
    Separate only files of a DICOM Determined
    directory. You can go recursively within
    the directory. (recursive = True)
    """
    result = []
    acquisition_modality = None

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
                    acquisition_modality = read_dicom.GetAcquisitionModality()
                    result.append(path)
    else:
        files = glob.glob(path + os.sep + "*")
        for x in xrange(len(files)):
            read_dicom = dicom.Parser()
            if (read_dicom.SetFileName(files[x])):
                result.append(files[x])
                acquisition_modality = read_dicom.GetAcquisitionModality()
        #  TODO!!! SUPER GAMBIARRA!!! DO THIS BETTER
    return result, acquisition_modality
