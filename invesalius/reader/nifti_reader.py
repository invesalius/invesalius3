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

from nibabel import Nifti1Image, squeeze_image

def ReadNifti(filename):
    nft = squeeze_image(Nifti1Image.from_filename(filename))
    return nft

def ReadDirectory(dir_):
    """ 
    Looking for nifti files in the given directory
    """
    imagedata = None
    for root, sub_folders, files in os.walk(dir_):
        for file in files:
            if file.split(".")[-1] == "nii":
                filename = os.path.join(root,file)
                imagedata = ReadNifti(filename)
                imagedata.update_header()
                return imagedata
    return imagedata
