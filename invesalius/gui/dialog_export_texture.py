import time

import wx

from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class ExportTextureFormatDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(
            parent,
            title=_("Export 3D Surface from Volume Rendering"),
            style=wx.DEFAULT_DIALOG_STYLE,
        )

        self.surface_index = None
        self.format = "OBJ"
        self._init_ui()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Format selection
        self.rb_format = wx.RadioBox(
            panel,
            label=_("Format:"),
            choices=[_("Wavefront OBJ"), _("VRML")],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        self.rb_format.SetSelection(0)
        vbox.Add(self.rb_format, flag=wx.EXPAND | wx.ALL, border=10)

        # Buttons
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)

        panel.SetSizer(vbox)
        vbox.Fit(panel)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.Layout()

    def GetValues(self):
        fmt = "OBJ" if self.rb_format.GetSelection() == 0 else "VRML"
        return None, fmt


class ExportTextureProgressDialog(wx.Dialog):
    def __init__(self, parent, title=_("Generating Surface Texture")):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
        self._start_time = time.time()
        self._export_filename = None
        self._export_success = False
        self._init_ui()
        self._bind_events()
        self._start_timer()

    def _init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.st_status = wx.StaticText(panel, label=_("Starting export..."))
        font = self.st_status.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.st_status.SetFont(font)
        vbox.Add(self.st_status, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=15)

        self.gauge = wx.Gauge(panel, range=100, size=(350, 22))
        vbox.Add(self.gauge, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border=15)

        # Timer label
        self.st_timer = wx.StaticText(panel, label=_("Elapsed: 0:00"))
        timer_font = self.st_timer.GetFont()
        timer_font.SetPointSize(timer_font.GetPointSize() - 1)
        self.st_timer.SetFont(timer_font)
        self.st_timer.SetForegroundColour(wx.Colour(120, 120, 120))
        vbox.Add(self.st_timer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=15)

        panel.SetSizer(vbox)
        vbox.Fit(panel)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.Layout()

        # Force minimum width
        self.SetMinSize(wx.Size(380, -1))
        self.Fit()
        self.CentreOnParent()

    def _start_timer(self):
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self._timer.Start(1000)  # Update every second

    def _on_timer(self, event):
        elapsed = time.time() - self._start_time
        minutes = int(elapsed) // 60
        seconds = int(elapsed) % 60
        self.st_timer.SetLabel(_(f"Elapsed: {minutes}:{seconds:02d}"))

    def _bind_events(self):
        Publisher.subscribe(self.OnUpdateProgress, "Update texture export progress")

    def OnUpdateProgress(self, progress, status=""):
        wx.CallAfter(self._update_progress_threadsafe, progress, status)

    def _update_progress_threadsafe(self, progress, status=""):
        if status:
            self.st_status.SetLabel(status)
        self.gauge.SetValue(min(progress, 100))

        if progress >= 100:
            self._timer.Stop()
            elapsed = time.time() - self._start_time
            minutes = int(elapsed) // 60
            seconds = int(elapsed) % 60
            self.st_timer.SetLabel(_(f"Completed in {minutes}:{seconds:02d}"))

            # Check if export was successful (not an error status)
            is_error = "error" in status.lower() if status else False
            self._export_success = not is_error
            self.EndModal(wx.ID_OK)

    def Destroy(self):
        self._timer.Stop()
        Publisher.unsubscribe(self.OnUpdateProgress, "Update texture export progress")
        super().Destroy()
