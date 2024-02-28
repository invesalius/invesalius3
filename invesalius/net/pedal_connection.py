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
from functools import partial

import wx

import invesalius.constants as const
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton, debug

HAS_PEDAL_CONNECTION = True
try:
    import mido
except ImportError:
    HAS_PEDAL_CONNECTION = False


class PedalConnector:
    """
    Interface for using any type of pedal (midi, neuronavigation_api, keystroke)
    """
    def __init__(self, neuronavigation_api=None, window=None):

        self.pedal_connection = MidiPedal() if HAS_PEDAL_CONNECTION else None
        self.neuronavigation_api = neuronavigation_api
        self.frame = None

        if const.KEYSTROKE_PEDAL_ENABLED:
            self._set_frame(window)
            self.panel_callbacks = {}

    def _set_frame(self, panel):
        try:
            while panel is not None and panel.GetId() != const.ID_FRAME:
                panel = panel.GetParent()
        except Exception as err:
            debug("PedalConnector could not find frame: " + str(err))

        self.frame = panel

    def _bind_callbacks_to_panel(self, panel):
        panel_id = panel.GetId()
        self.panel_callbacks.update({panel_id: {}})

        def OnKeyPress(evt, state):
            key_code = evt.GetKeyCode()
            if key_code == const.KEYSTROKE_PEDAL_KEY:
                for name in list(self.panel_callbacks[panel_id].keys()):
                    callback, remove_when_released = self.panel_callbacks[panel_id][name]
                    callback(state)
                    if remove_when_released:
                        self.panel_callbacks[panel_id].pop(name)
            evt.Skip()
        panel.Bind(wx.EVT_CHAR_HOOK, partial(OnKeyPress, state=True))

    def add_callback(self, name, callback, remove_when_released=False, panel=None):

        if self.pedal_connection is not None:
            self.pedal_connection.add_callback(name, callback, remove_when_released)

        if self.neuronavigation_api is not None:
            self.neuronavigation_api.add_pedal_callback(name, callback, remove_when_released)

        panel = panel or self.frame
        if panel is not None and const.KEYSTROKE_PEDAL_ENABLED:
            panel_id = panel.GetId()
            if panel_id not in self.panel_callbacks:
                self._bind_callbacks_to_panel(panel)

            self.panel_callbacks[panel_id].update({name: (callback, remove_when_released)})

    def remove_callback(self, name, panel=None):

        if self.pedal_connection is not None:
            self.pedal_connection.remove_callback(name)

        if self.neuronavigation_api is not None:
            self.neuronavigation_api.remove_pedal_callback(name)

        panel = panel or self.frame
        if panel is not None and const.KEYSTROKE_PEDAL_ENABLED:
            self.panel_callbacks[panel.GetId()].pop(name)


class MidiPedal(Thread, metaclass=Singleton):
    """
    Connect to the trigger pedal via MIDI, and allow adding callbacks for the pedal
    being pressed or released.

    Started by calling MidiPedal().start()
    """
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True

        self.in_use = False

        self._midi_in = None
        self._active_inputs = None
        self._callback_infos = []

    def _midi_to_pedal(self, msg):
        # TODO: At this stage, interpret all note_on messages as the pedal being pressed,
        #       and note_off messages as the pedal being released. Later, use the correct
        #       message types and be more stringent about the messages.
        #
        if msg.type == 'note_on':
            state = True

        elif msg.type == 'note_off':
            state = False

        else:
            print("Unknown message type received from MIDI device")
            return

        Publisher.sendMessage('Pedal state changed', state=state)
        for callback_info in self._callback_infos:
            callback = callback_info['callback']
            callback(state)

        if not state:
            self._callback_infos = [callback_info for callback_info in self._callback_infos if not callback_info['remove_when_released']]

    def _connect_if_disconnected(self):
        if self._midi_in is None and len(self._midi_inputs) > 0:
            self._active_input = self._midi_inputs[0]
            self._midi_in = mido.open_input(self._active_input)
            self._midi_in._rt.ignore_types(False, False, False)
            self._midi_in.callback = self._midi_to_pedal

            Publisher.sendMessage('Pedal connection', state=True)

            print("Connected to MIDI device")

    def _check_disconnected(self):
        if self._midi_in is not None:
            if self._active_input not in self._midi_inputs:
                self._midi_in = None

                Publisher.sendMessage('Pedal connection', state=False)

                print("Disconnected from MIDI device")

    def _update_midi_inputs(self):
        self._midi_inputs = mido.get_input_names()

    def is_connected(self):
        return self._midi_in is not None

    def add_callback(self, name, callback, remove_when_released=False):
        self._callback_infos.append({
            'name': name,
            'callback': callback,
            'remove_when_released': remove_when_released,
        })

    def remove_callback(self, name):
        self._callback_infos = [callback_info for callback_info in self._callback_infos if callback_info['name'] != name]

    def run(self):
        self.in_use = True
        while True:
            self._update_midi_inputs()
            self._check_disconnected()
            self._connect_if_disconnected()
            time.sleep(1.0)
