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

import itk
import ItkVtkGlue
import vtk


def ReadAnalyze(filename):
    reader = itk.ImageFileReader.IUC3.New()
    reader.SetFileName(filename)
    reader.Update()

    x_spacing = reader.GetOutput().GetSpacing().GetElement(0)
    y_spacing = reader.GetOutput().GetSpacing().GetElement(1)
    z_spacing = reader.GetOutput().GetSpacing().GetElement(2) 
    spacing = (x_spacing, y_spacing, z_spacing)

    glue = ItkVtkGlue.ImageToVTKImageFilter.IUC3.New()
    glue.SetInput(reader.GetOutput())
    glue.Update()
    
    imagedata = vtk.vtkImageData()
    imagedata.DeepCopy(glue.GetOutput())
    imagedata.SetSpacing(spacing)

    return imagedata

def ReadDirectory(dir_):
    file_list = []
    imagedata = None
    for root, sub_folders, files in os.walk(dir_):
        for file in files:
            if file.split(".")[-1] == "hdr":
                filename = os.path.join(root,file)
                imagedata = ReadAnalyze(filename)
                return imagedata
    return imagedata
