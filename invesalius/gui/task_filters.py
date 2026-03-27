# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------

import sys

import wx

from invesalius.gui.widgets.inv_spinctrl import InvFloatSpinCtrl
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 0, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        # Inherit background from parent TaskNavigator
        self.SetAutoLayout(1)

        # Filters content
        self.filters_panel = FiltersPanel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.filters_panel, 0, wx.GROW | wx.EXPAND | wx.TOP, 10)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.Update()


class FiltersPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Filter selection
        txt_filter = wx.StaticText(self, -1, _("Filter type:"))
        self.cb_filter = wx.ComboBox(
            self,
            -1,
            choices=[
                _("Despeckle"),
                _("Border Detection"),
            ],
            style=wx.CB_READONLY,
        )
        self.cb_filter.SetSelection(0)
        if sys.platform != "win32":
            self.cb_filter.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.cb_filter.Bind(wx.EVT_COMBOBOX, self.OnSelectFilter)

        # Parameter label + spinner (only shown for Despeckle)
        self.txt_param = wx.StaticText(self, -1, _("Sensitivity:"))
        self.spin_param = InvFloatSpinCtrl(
            self, -1, value=1.0, min_value=0.1, max_value=10.0, increment=0.1
        )

        # Apply button
        self.btn_apply = wx.Button(self, -1, _("Apply to Volume"))
        self.btn_apply.Bind(wx.EVT_BUTTON, self.OnApply)

        # Layout
        sizer.AddSpacer(10)
        sizer.Add(txt_filter, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        sizer.AddSpacer(5)
        sizer.Add(self.cb_filter, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT, 10)
        sizer.AddSpacer(15)
        sizer.Add(self.txt_param, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        sizer.AddSpacer(5)
        sizer.Add(self.spin_param, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT, 10)
        sizer.AddSpacer(25)
        sizer.Add(self.btn_apply, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10)
        sizer.AddSpacer(10)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        # Subscribe to filter-done event to re-enable button after thread finishes
        Publisher.subscribe(self.OnFilterDone, "Image filter done")

    def OnSelectFilter(self, evt):
        filter_name = self.cb_filter.GetStringSelection()
        show_param = filter_name == _("Despeckle")
        self.txt_param.Show(show_param)
        self.spin_param.Show(show_param)
        self.GetSizer().Layout()
        self.GetParent().GetSizer().Layout()

    def OnApply(self, evt):
        # 0 = Despeckle, 1 = Border Detection (matches slice_.py filter_type 4 & 5)
        selection = self.cb_filter.GetSelection()
        filter_type = 4 + selection  # maps 0→4 (Despeckle), 1→5 (Border Detection)
        value = self.spin_param.GetValue()

        # Disable button with loading feedback – re-enabled by OnFilterDone
        self.btn_apply.Disable()
        self.btn_apply.SetLabel(_("Applying..."))

        # Start the filter in a background thread (non-blocking)
        Publisher.sendMessage("Apply image filter", filter_type=filter_type, value=value)

    def OnFilterDone(self):
        """Called on the main thread when the background filter thread finishes."""
        if self.btn_apply:
            self.btn_apply.SetLabel(_("Apply to Volume"))
            self.btn_apply.Enable()
