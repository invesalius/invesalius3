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

import threading
from time import sleep

from numpy import mat
import wx
from wx.lib.pubsub import pub as Publisher

import invesalius.data.coordinates as dco

# TODO: Optimize navigation thread. Remove the infinite loop and optimize sleep.


class Coregistration(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, bases, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.bases = bases
        self.nav_id = nav_id
        self.trck_info = trck_info
        self._pause_ = False
        self.start()
        
    def stop(self):
        self._pause_ = True
       
    def run(self):
        m_inv = self.bases[0]
        n = self.bases[1]
        q1 = self.bases[2]
        q2 = self.bases[3]
        trck_init = self.trck_info[0]
        trck_id = self.trck_info[1]
        trck_mode = self.trck_info[2]

        while self.nav_id:
            trck_coord = dco.GetCoordinates(trck_init, trck_id, trck_mode)
            trck_xyz = mat([[trck_coord[0]], [trck_coord[1]], [trck_coord[2]]])

            img = q1 + (m_inv*n)*(trck_xyz - q2)

            coord = (float(img[0]), float(img[1]), float(img[2]), trck_coord[3],
                     trck_coord[4], trck_coord[5])

            # Tried several combinations and different locations to send the messages,
            # however only this one does not block the GUI during navigation.
            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', coord[0:3])
            wx.CallAfter(Publisher.sendMessage, 'Set camera in volume', coord[0:3])

            # TODO: Optimize the value of sleep for each tracking device.
            # Debug tracker is not working with 0.175 so changed to 0.2
            # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
            sleep(.3)
            # sleep(0.175)

            if self._pause_:
                return
