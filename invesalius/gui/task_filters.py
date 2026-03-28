# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------

import sys

import wx

from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        inner = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.filters_panel = FiltersPanel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.filters_panel, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        self.Layout()
        self.Update()


class FiltersPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self._dialog = None
        self._init_gui()

    def _init_gui(self):
        self.btn_open = wx.Button(self, -1, _("Open Image Filters\u2026"))
        if sys.platform != "win32":
            self.btn_open.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.btn_open, 0, wx.EXPAND | wx.ALL, 4)
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.btn_open.Bind(wx.EVT_BUTTON, self._on_open)

        Publisher.subscribe(self._on_project_close, "Close project data")

    def _on_open(self, evt):
        # Only one dialog at a time — reuse if still alive
        if self._dialog and self._dialog.IsShown():
            self._dialog.Raise()
            return
        from invesalius.gui.dialogs import ImageFilterDialog

        self._dialog = ImageFilterDialog()
        self._dialog.Show()

    def _on_project_close(self):
        if self._dialog:
            try:
                self._dialog.Close()
            except Exception:
                pass
            self._dialog = None
