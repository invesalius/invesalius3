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

import vtk
import nibabel as nib

import invesalius.constants as const


def ReadOthers(dir_):
    """
    Read the given Analyze, NIfTI, Compressed NIfTI or PAR/REC file,
    remove singleton image dimensions and convert image orientation to
    RAS+ canonical coordinate system. Analyze header does not support
    affine transformation matrix, though cannot be converted automatically
    to canonical orientation.

    :param dir_: file path
    :return: imagedata object
    """

    if not const.VTK_WARNING:
        log_path = os.path.join(const.LOG_FOLDER, 'vtkoutput.txt')
        fow = vtk.vtkFileOutputWindow()
        fow.SetFileName(log_path)
        ow = vtk.vtkOutputWindow()
        ow.SetInstance(fow)

    imagedata = nib.squeeze_image(nib.load(dir_))
    imagedata = nib.as_closest_canonical(imagedata)
    imagedata.update_header()

    return imagedata