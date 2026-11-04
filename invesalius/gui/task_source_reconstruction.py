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

import os

import wx

import invesalius.gui.dialogs as dlg
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)

        button = wx.Button(self, label=_("Import STC configuration..."))
        button.SetToolTip(
            _("Load the configuration for an EEG/MEG cortical source reconstruction.")
        )
        button.Bind(wx.EVT_BUTTON, self.OnImport)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(button, 0, wx.ALL | wx.EXPAND, 7)
        hint = wx.StaticText(
            self,
            label=_("Select EEG/MEG in the brain's Color map mode to display the reconstruction."),
        )
        hint.Wrap(300)
        sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)
        self.SetSizerAndFit(sizer)

    def OnImport(self, event):
        filename = dlg.ShowLoadSaveDialog(
            message=_("Import EEG/MEG source reconstruction"),
            current_dir=os.getcwd(),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
            wildcard=_("Source reconstruction configuration (*.json)|*.json"),
        )
        if not filename:
            return
        try:
            with wx.BusyCursor():
                Publisher.sendMessage("Load source reconstruction", filename=filename)
        except Exception as error:
            with dlg.ErrorMessageBox(
                self, _("Error importing EEG/MEG source reconstruction"), str(error)
            ) as dialog:
                dialog.ShowModal()
