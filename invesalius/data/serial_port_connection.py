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
import time

import wx
from invesalius.pubsub import pub as Publisher


class SerialPortConnection(threading.Thread):

    def __init__(self, serial_port_queue, event, sle):
        """
        Thread created to communicate using the serial port to interact with software during neuronavigation.
        """
        threading.Thread.__init__(self, name='Serial port')

        self.serial_port = None
        self.stylusplh = False

        try:
            import serial
            self.serial_port = serial.Serial('COM5', baudrate=115200, timeout=0)
        except:
            print("Serial port init error: Connection with port COM failed")

        self.serial_port_queue = serial_port_queue
        self.event = event
        self.sle = sle

    def run(self):
        while not self.event.is_set():
            trigger_on = False
            try:
                self.serial_port.write(b'0')
                time.sleep(0.3)

                lines = self.serial_port.readlines()
                if lines:
                    trigger_on = True

                if self.stylusplh:
                    trigger_on = True
                    self.stylusplh = False

                self.serial_port_queue.put_nowait(trigger_on)
                time.sleep(self.sle)
            except:
                print("Trigger not read, error")
        else:
            if self.serial_port:
                self.serial_port.close()
