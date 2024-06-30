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

import nibabel as nib

from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow

import invesalius.constants as const
from invesalius import inv_paths


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
        log_path = os.path.join(inv_paths.USER_LOG_DIR, 'vtkoutput.txt')
        fow = vtkFileOutputWindow()
        fow.SetFileName(log_path.encode(const.FS_ENCODE))
        ow = vtkOutputWindow()
        ow.SetInstance(fow)

    try:
        imagedata = nib.squeeze_image(nib.load(dir_))
        imagedata = nib.as_closest_canonical(imagedata)
        imagedata.update_header()

        if len(imagedata.shape) == 4:
            import invesalius.gui.dialogs as dlg
            from wx import ID_OK

            dialog = dlg.SelectNiftiVolumeDialog(volumes=[str(n+1) for n in range(imagedata.shape[-1])])
            status = dialog.ShowModal()

            success = status == ID_OK

            if success:
                # selected_option = int(dialog.choice.GetStringSelection())
                selected_volume = dialog.GetVolumeChoice()

                data = imagedata.get_fdata()
                header = imagedata.header.copy()

                selected_volume = data[..., selected_volume]
                header.set_data_shape(selected_volume.shape)

                zooms = list(header.get_zooms())
                new_zooms = zooms[:3]  # Adjust this to your desired zooms
                header.set_zooms(new_zooms)

                imagedata = nib.Nifti1Image(selected_volume, imagedata.affine, header=header)

            else:
                raise ValueError

            dialog.Destroy()

    except(nib.filebasedimages.ImageFileError):
        return False

    return imagedata
