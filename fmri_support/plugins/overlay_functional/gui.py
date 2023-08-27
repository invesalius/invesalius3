import wx
from pubsub import pub as Publisher
from invesalius.gui.utils import calc_width_needed

class FunctionalOverlayGUI(wx.Dialog):
    def __init__(
        self,
        parent,
        title="Display Functional Overlay",
        style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
    ):
        super().__init__(parent, -1, title=title, style=style)
        self.pixel_value = 0
        self._init_gui()

    def _init_gui(self):
        self.surfaces_combo = wx.ComboBox(self, -1, style=wx.CB_READONLY)
        self.surfaces_combo.SetMinClientSize(
            (calc_width_needed(self.surfaces_combo, 25), -1)
        )
        self.surfaces_combo.Append("TimeFrame")
        self.surfaces_combo.Append("Yeo-7")
        self.surfaces_combo.Append("Yeo-17")
        self.surfaces_combo.Append("Seedbased")
        self.surfaces_combo.Append("Gradients-Connectivity")
        

        btn_close = wx.Button(self, wx.ID_CLOSE)

        self.surfaces_combo.Bind(wx.EVT_COMBOBOX, self.onSelect)
        btn_close.Bind(wx.EVT_BUTTON, self.OnClickClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.surfaces_combo, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(btn_close, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def onSelect(self, evt):
        self.choice_morph = self.surfaces_combo.GetValue()
        print(self.choice_morph)

    def OnClickClose(self, evt):
        self.Close()

    def OnClose(self, evt):
        Publisher.sendMessage("Disable actual style")
        self.Destroy()

    def set_pixel_value(self, pixel_value):
        self.pixel_value = pixel_value
        self.lbl_pixel_value.SetLabel(f"Value: {self.pixel_value}.")
