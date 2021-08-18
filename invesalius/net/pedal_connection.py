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
from threading import Thread

import mido

from invesalius.utils import Singleton

class PedalConnection(Thread, metaclass=Singleton):
    """
    Connect to the trigger pedal via MIDI, and allow adding callbacks for the pedal
    being pressed or released.

    Started by calling PedalConnection().start()
    """
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True

        self.in_use = False

        self._midi_in = None
        self._active_inputs = None
        self._callbacks = {}

    def _midi_to_pedal(self, msg):
        # TODO: At this stage, interpret all note_on messages as the pedal being pressed,
        #       and note_off messages as the pedal being released. Later, use the correct
        #       message types and be more stringent about the messages.
        #
        if msg.type == 'note_on':
            if not self._callbacks:
                print("Pedal pressed, no callbacks registered")
            else:
                for callback in self._callbacks.values():
                    callback(True)

        elif msg.type == 'note_off':
            if not self._callbacks:
                print("Pedal released, no callbacks registered")
            else:
                for callback in self._callbacks.values():
                    callback(False)

        else:
            print("Unknown message type received from MIDI device")

    def _connect_if_disconnected(self):
        if self._midi_in is None and len(self._midi_inputs) > 0:
            self._active_input = self._midi_inputs[0]
            self._midi_in = mido.open_input(self._active_input)
            self._midi_in._rt.ignore_types(False, False, False)
            self._midi_in.callback = self._midi_to_pedal

            print("Connected to MIDI device")

    def _check_disconnected(self):
        if self._midi_in is not None:
            if self._active_input not in self._midi_inputs:
                self._midi_in = None

                print("Disconnected from MIDI device")

    def _update_midi_inputs(self):
        self._midi_inputs = mido.get_input_names()

    def is_connected(self):
        return self._midi_in is not None

    def add_callback(self, name, callback):
        self._callbacks[name] = callback

    def remove_callback(self, name):
        if name in self._callbacks:
            del self._callbacks[name]

    def run(self):
        self.in_use = True
        while True:
            self._update_midi_inputs()
            self._check_disconnected()
            self._connect_if_disconnected()
            time.sleep(1.0)
