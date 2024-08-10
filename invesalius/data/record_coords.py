# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------

import threading
import time

import wx
from numpy import array, asarray, hstack, savetxt, vstack

import invesalius.gui.dialogs as dlg
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class Record(threading.Thread):
    """
    Thread created to save obj coords with software during neuronavigation
    """

    def __init__(self, nav_id, timestamp):
        threading.Thread.__init__(self)
        self.nav_id = nav_id
        self.coord = None
        self.timestamp = timestamp
        self.coord_list = array([])
        self.__bind_events()
        self._pause_ = False
        self.start()

    def __bind_events(self):
        # Publisher.subscribe(self.UpdateCurrentCoords, 'Co-registered points')
        Publisher.subscribe(self.UpdateCurrentCoords, "Set cross focal point")

    def UpdateCurrentCoords(self, position):
        self.coord = asarray(position)

    def stop(self):
        self._pause_ = True
        # save coords dialog
        filename = dlg.ShowLoadSaveDialog(
            message=_("Save coords as..."),
            wildcard=_("Coordinates files (*.csv)|*.csv"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            default_filename="coords.csv",
            save_ext="csv",
        )
        if filename:
            savetxt(
                filename,
                self.coord_list,
                delimiter=",",
                fmt="%.4f",
                header="time, x, y, z, a, b, g",
                comments="",
            )

    def run(self):
        initial_time = time.time()
        while self.nav_id:
            relative_time = asarray(time.time() - initial_time)
            time.sleep(self.timestamp)
            if self.coord_list.size == 0:
                self.coord_list = hstack((relative_time, self.coord))
            else:
                self.coord_list = vstack((self.coord_list, hstack((relative_time, self.coord))))
            if self._pause_:
                return
