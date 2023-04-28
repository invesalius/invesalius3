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
from typing import List, Dict, Any, Union, Optional, Callable

import mido

from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class PedalConnection(Thread, metaclass=Singleton):
    """
    Connect to the trigger pedal via MIDI, and allow adding callbacks for the pedal
    being pressed or released.

    Started by calling PedalConnection().start()
    """

    def __init__(self) -> None:
        Thread.__init__(self)
        self.daemon = True

        self.in_use: bool = False

        self._midi_in: Optional[mido.MidiFile] = None
        self._active_inputs: Optional[str] = None
        self._callback_infos: List[Dict[str, Any]] = []

    def _midi_to_pedal(self, msg: mido.Message) -> None:
        # TODO: At this stage, interpret all note_on messages as the pedal being pressed,
        #       and note_off messages as the pedal being released. Later, use the correct
        #       message types and be more stringent about the messages.
        #
        if msg.type == 'note_on':
            state: bool = True

        elif msg.type == 'note_off':
            state: bool = False

        else:
            print("Unknown message type received from MIDI device")
            return

        Publisher.sendMessage('Pedal state changed', state=state)
        for callback_info in self._callback_infos:
            callback: Callable[[bool], None] = callback_info['callback']
            callback(state)

        if not state:
            self._callback_infos = [callback_info for callback_info in self._callback_infos if not callback_info['remove_when_released']]

    def _connect_if_disconnected(self) -> None:
        if self._midi_in is None and len(self._midi_inputs) > 0:
            self._active_input: str = self._midi_inputs[0]
            self._midi_in: mido.MidiFile = mido.open_input(self._active_input)
            self._midi_in._rt.ignore_types(False, False, False)
            self._midi_in.callback = self._midi_to_pedal

            Publisher.sendMessage('Pedal connection', state=True)

            print("Connected to MIDI device")

    def _check_disconnected(self) -> None:
        if self._midi_in is not None:
            if self._active_input not in self._midi_inputs:
                self._midi_in = None

                Publisher.sendMessage('Pedal connection', state=False)

                print("Disconnected from MIDI device")

    def _update_midi_inputs(self) -> None:
        self._midi_inputs: List[str] = mido.get_input_names()

    def is_connected(self) -> bool:
        return self._midi_in is not None

    def add_callback(self, name: str, callback: Callable[[bool], None], remove_when_released: Optional[bool] = False) -> None:
        self._callback_infos.append({
            'name': name,
            'callback': callback,
            'remove_when_released': remove_when_released,
        })

    def remove_callback(self, name: str) -> None:
        self._callback_infos = [callback_info for callback_info in self._callback_infos if callback_info['name'] != name]

    def run(self) -> None:
        self.in_use: bool = True
        while True:
            self._update_midi_inputs()
            self._check_disconnected()
            self._connect_if_disconnected()
            time.sleep(1.0)

