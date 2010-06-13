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
import multiprocessing
import tempfile

import vtk

from nipy.io.imageformats import AnalyzeHeader

def ReadAnalyze(filename):
    print "Reading analyze file:", filename

    # Reading info from analyze header
    header_file = open(filename)
    header = AnalyzeHeader.from_fileobj(header_file)
    xf, yf, zf = header.get_data_shape()[:3]
    data_type = header.get_datatype()
    pixel_spacing = header.get_zooms()[:3]

    # Mapping from numpy type to vtk type.
    anlz_2_vtk_type = {
                       'int16': 'SetDataScalarTypeToShort',
                       'uint16': 'SetDataScalarTypeToUnsignedShort',
                       'float32': 'SetDataScalarTypeToFloat'
                      }

    print header

    reader = vtk.vtkImageReader()
    reader.SetFileName(filename[:-3] + 'img')

    # Setting the endiannes based on the analyze header.
    if header.endianness == '<':
        reader.SetDataByteOrderToLittleEndian()
    elif header.endianness == '>':
        reader.SetDataByteOrderToBigEndian()

    reader.SetFileDimensionality(3)
    reader.SetDataExtent(0, xf-1, 0, yf-1, 0, zf-1)
    reader.SetDataSpacing(pixel_spacing)
    reader.SetHeaderSize(0)
    # reader.SetTransform(transform)
    getattr(reader, anlz_2_vtk_type[data_type])()
    reader.Update()

    return reader.GetOutput()

def ReadDirectory(dir_):
    """ 
    Looking for analyze files in the given directory
    """
    imagedata = None
    for root, sub_folders, files in os.walk(dir_):
        for file in files:
            if file.split(".")[-1] == "hdr":
                filename = os.path.join(root,file)
                imagedata = ReadAnalyze(filename)
                return imagedata
    return imagedata
