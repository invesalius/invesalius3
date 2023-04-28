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

import queue
import threading
import time

from typing import Any, Optional, Tuple
from invesalius import constants
from invesalius.pubsub import pub as Publisher


class SerialPortConnection(threading.Thread):
    def __init__(self, com_port: Optional[str], baud_rate: int, serial_port_queue: queue.Queue, event: threading.Event, sleep_nav: float) -> None:
        """
        Thread created to communicate using the serial port to interact with software during neuronavigation.
        """
        threading.Thread.__init__(self, name='Serial port')

        self.connection: Optional[Any] = None
        self.stylusplh: bool = False

        self.com_port: Optional[str] = com_port
        self.baud_rate: int = baud_rate
        self.serial_port_queue: queue.Queue = serial_port_queue
        self.event: threading.Event = event
        self.sleep_nav: float = sleep_nav

    def Connect(self) -> None:
        if self.com_port is None:
            print("Serial port init error: COM port is unset.")
            return
        try:
            import serial
            self.connection = serial.Serial(self.com_port, baudrate=self.baud_rate, timeout=0)
            print("Connection to port {} opened.".format(self.com_port))

            Publisher.sendMessage('Serial port connection', state=True)
        except:
            print("Serial port init error: Connecting to port {} failed.".format(self.com_port))

    def Disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            print("Connection to port {} closed.".format(self.com_port))

            Publisher.sendMessage('Serial port connection', state=False)

    def SendPulse(self) -> None:
        try:
            self.connection.send_break(constants.PULSE_DURATION_IN_MILLISECONDS / 1000)
            Publisher.sendMessage('Serial port pulse triggered')
        except:
            print("Error: Serial port could not be written into.")

    def run(self) -> None:
        while not self.event.is_set():
            trigger_on: bool = False
            try:
                lines: bytes = self.connection.readlines()
                if lines:
                    trigger_on = True
            except:
                print("Error: Serial port could not be read.")

            if self.stylusplh:
                trigger_on = True
                self.stylusplh = False

            try:
                self.serial_port_queue.put_nowait(trigger_on)
            except queue.Full:
                print("Error: Serial port queue full.")

            time.sleep(self.sleep_nav)

            # XXX: This is needed here because the serial port queue has to be read
            #      at least as fast as it is written into, otherwise it will eventually
            #      become full. Reading is done in another thread, which has the same
            #      sleeping parameter sleep_nav between consecutive runs as this thread.
            #      However, a single run of that thread takes longer to finish than a
            #      single run of this thread, causing that thread to lag behind. Hence,
            #      the additional sleeping here to ensure that this thread lags behind the
            #      other thread and not the other way around. However, it would be nice to
            #      handle the timing dependencies between the threads in a more robust way.
            #
            time.sleep(0.3)
        else:
            self.Disconnect()
    