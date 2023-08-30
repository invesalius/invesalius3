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

import numpy as np

import invesalius.session as ses
from invesalius.pubsub import pub as Publisher


class Image():
    def __init__(self):
        self.image_fiducials = np.full([3, 3], np.nan)

        self.LoadState()

    def SaveState(self):
        state = {
            'image_fiducials': self.image_fiducials.tolist(),
        }
        session = ses.Session()
        session.SetState('image', state)

    def LoadState(self):
        session = ses.Session()
        state = session.GetState('image')

        if state is None:
            return

        image_fiducials = np.array(state['image_fiducials'])
        self.image_fiducials = image_fiducials

    def SetImageFiducial(self, fiducial_index, position):
        self.image_fiducials[fiducial_index, :] = position
        print("Image fiducial {} set to coordinates {}".format(fiducial_index, position))

        self.SaveState()

    def GetImageFiducials(self):
        return self.image_fiducials
    
    def ResetImageFiducials(self):
        self.image_fiducials = np.full([3, 3], np.nan)
        Publisher.sendMessage("Reset image fiducials")
        self.SaveState()

    def GetImageFiducialForUI(self, fiducial_index, coordinate):
        value = self.image_fiducials[fiducial_index, coordinate]
        if np.isnan(value):
            value = 0

        return value

    def AreImageFiducialsSet(self):
        return not np.isnan(self.image_fiducials).any()

    def IsImageFiducialSet(self, fiducial_index):
        return not np.isnan(self.image_fiducials)[fiducial_index].any()
