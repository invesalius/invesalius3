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

import time
import serial
from threading import Thread


from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton

class PedalConnectionSerial(Thread, metaclass=Singleton):
    """
    Connect to the trigger pedal via serial, and allow adding callbacks for the pedal
    being pressed or released.

    Started by calling PedalConnectionSerial().start()
    """
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        
        self.in_use = False

        self._pedal_connected = None
        self._callback_infos = []
        self.ports = ['COM0','COM2','COM1''COM3','COM4','COM5','COM6','COM7','COM8','COM9']

    def _read_pedal(self):
        # TODO: At this stage, interpret all note_on messages as the pedal being pressed,
        #       and note_off messages as the pedal being released. Later, use the correct
        #       message types and be more stringent about the messages.
        #
        if self._pedal_connected:
            try: 
                val = self.serial.read()
                if len(val) == 0:
                    return
                elif val[0] == 1:
                    state = True
                elif val[0] == 7:
                    state = False
                else:
                    print("Unknown message type received from Serial device")
                    return

                Publisher.sendMessage('Pedal state changed', state=state)
                for callback_info in self._callback_infos:
                    callback = callback_info['callback']
                    callback(state)

                if not state:
                    self._callback_infos = [callback_info for callback_info in self._callback_infos if not callback_info['remove_when_released']]
            
            except serial.serialutil.SerialException:
                    self._pedal_connected = False


    def _connect_if_disconnected(self):
        """
        Recover connection to lost device.
        """
        if self._pedal_connected is None:
            
            for port in self.ports:
                try:
                    self.serial.port = port
                    self.serial.open()
                    self._pedal_connected = True
                    Publisher.sendMessage('Pedal connection', state=True)
                    print("Connected to serial device")

                    return
                except serial.serialutil.SerialException:
                    continue
        

    def _check_disconnected(self):
        if self._pedal_connected is not None:
            if not self._pedal_connected:
                self._pedal_connected= None
                Publisher.sendMessage('Pedal connection', state=False)

                print("Disconnected from Serial device")

    def is_connected(self):
        return self._pedal_connected

    def add_callback(self, name, callback, remove_when_released=False):
        self._callback_infos.append({
            'name': name,
            'callback': callback,
            'remove_when_released': remove_when_released,
        })

    def remove_callback(self, name):
        self._callback_infos = [callback_info for callback_info in self._callback_infos if callback_info['name'] != name]

    def run(self):
        self.serial = serial.Serial(timeout = 0.1)
        self.in_use = True
        Publisher.sendMessage('Pedal connection', state=True)
        while True:
            self._check_disconnected()
            self._connect_if_disconnected()
            self._read_pedal()
