#!/usr/bin/env python3
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
#-------------------------------------------------------------------------

import time

import socketio
import wx

from invesalius.pubsub import pub as Publisher

class RemoteControl:
    def __init__(self, remote_host):
        self._remote_host = remote_host
        self._connected = False
        self._sio = None

    def _on_connect(self):
        print("Connected to {}".format(self._remote_host))
        self._connected = True

    def _on_disconnect(self):
        print("Disconnected")
        self._connected = False

    def _to_neuronavigation(self, msg):
        topic = msg["topic"]
        data = msg["data"]
        if data is None:
            data = {}

        #print("Received an event into topic '{}' with data {}".format(topic, str(data)))
        Publisher.sendMessage_no_hook(
            topicName=topic,
            **data
        )

    def _to_neuronavigation_wrapper(self, msg):
        # wx.CallAfter wrapping is needed to make messages that update WxPython UI work properly, as the
        # Socket.IO listener runs inside a thread. (See WxPython and thread-safety for more information.)
        wx.CallAfter(self._to_neuronavigation, msg)

    def connect(self):
        self._sio = socketio.Client()

        self._sio.on('connect', self._on_connect)
        self._sio.on('disconnect', self._on_disconnect)
        self._sio.on('to_neuronavigation', self._to_neuronavigation_wrapper)

        self._sio.connect(self._remote_host)
        self._sio.emit('restart_robot_main_loop')

        while not self._connected:
            print("Connecting...")
            time.sleep(1.0)

        def _emit(topic, data):
            #print("Emitting data {} to topic {}".format(data, topic))
            try:
                if isinstance(topic, str):
                    self._sio.emit("from_neuronavigation", {
                        "topic": topic,
                        "data": data,
                    })
            except TypeError:
                pass
            except socketio.exceptions.BadNamespaceError:
                pass

        Publisher.add_sendMessage_hook(_emit)
