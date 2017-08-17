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

import wx
from wx.lib.pubsub import pub as Publisher


class Trigger(threading.Thread):
    """
    Thread created to use external trigger to interact with software during neuronavigation
    """

    def __init__(self, nav_id):
        threading.Thread.__init__(self)
        self.trigger_init = None
        self.stylusplh = False
        self.COM = False
        self.nav_id = nav_id
        self.__bind_events()
        try:
            import serial

            self.trigger_init = serial.Serial('COM1', baudrate=9600, timeout=0)
            self.COM = True

        except:
            print 'Connection with port COM1 failed.'
            self.COM = False

        self._pause_ = False
        self.start()

    def __bind_events(self):
        Publisher.subscribe(self.OnStylusPLH, 'PLH Stylus Button On')

    def OnStylusPLH(self, pubsuv_evt):
        self.stylusplh = True

    def stop(self):
        self._pause_ = True

    def run(self):
        while self.nav_id:
            if self.COM:
                self.trigger_init.write('0')
                sleep(0.3)
                lines = self.trigger_init.readlines()
                # Following lines can simulate a trigger in 3 sec repetitions
                # sleep(3)
                # lines = True
                if lines:
                    wx.CallAfter(Publisher.sendMessage, 'Create marker')
                    sleep(0.5)

            if self.stylusplh:
                wx.CallAfter(Publisher.sendMessage, 'Create marker')
                sleep(0.5)
                self.stylusplh = False

            sleep(0.175)
            if self._pause_:
                if self.trigger_init:
                    self.trigger_init.close()
                return
