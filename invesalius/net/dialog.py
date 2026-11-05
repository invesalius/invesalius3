import time

import wx


class SurfaceProgressWindow:
    def __init__(self):
        self.dlg = None

    def Show(self):
        self.dlg = wx.ProgressDialog(
            "InVesalius",
            _("Downloading Images"),
            parent=wx.GetApp().GetTopWindow(),
            style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME,
        )
        wx.CallAfter(self.pulsate)

    def WasCancelled(self):
        if self.dlg:
            return self.dlg.WasCancelled()

    def Update(self, msg="Downloading"):
        if self.dlg:
            self.dlg.Pulse(msg)

    def Close(self):
        if self.dlg:
            self.dlg.Destroy()
            self.dlg = None

    def pulsate(self):
        while self.dlg:
            time.sleep(0.1)
            self.Update()
