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

    def __init__(self, port, serial_port_queue, event, sleep_nav):
        """
        Thread created to communicate using the serial port to interact with software during neuronavigation.
        """
        threading.Thread.__init__(self, name='Serial port')

        self.connection = None
        self.stylusplh = False

        self.port = port
        self.serial_port_queue = serial_port_queue
        self.event = event
        self.sleep_nav = sleep_nav

    def Enabled(self):
        return self.port is not None

    def Connect(self):
        if self.port is None:
            print("Serial port init error: COM port is unset.")
            return
        try:
            import serial
            self.connection = serial.Serial(self.port, baudrate=115200, timeout=0)
            print("Connection to port {} opened.".format(self.port))
        except:
            print("Serial port init error: Connecting to port {} failed.".format(self.port))

    def run(self):
        while not self.event.is_set():
            trigger_on = False
            try:
                self.connection.write(b'0')
                time.sleep(0.3)

                lines = self.connection.readlines()
                if lines:
                    trigger_on = True

                if self.stylusplh:
                    trigger_on = True
                    self.stylusplh = False

                self.serial_port_queue.put_nowait(trigger_on)
                time.sleep(self.sleep_nav)
            except:
                print("Trigger not read, error")
        else:
            if self.connection:
                self.connection.close()
                print("Connection to port {} closed.".format(self.port))
