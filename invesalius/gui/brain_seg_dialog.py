#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import importlib
import os
import pathlib
import sys

import wx
from wx.lib.pubsub import pub as Publisher

# Linux if installed plaidml with pip3 install --user
if sys.platform.startswith("linux"):
    local_user_plaidml = pathlib.Path("~/.local/share/plaidml/").expanduser().absolute()
    if local_user_plaidml.exists():
        os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
        os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("~/.local/lib/libplaidml.so").expanduser().absolute())
# Mac if using python3 from homebrew
elif sys.platform == "darwin":
    local_user_plaidml = pathlib.Path("/usr/local/share/plaidml")
    if local_user_plaidml.exists():
        os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
        os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("/usr/local/lib/libplaidml.dylib").expanduser().absolute())

HAS_THEANO = bool(importlib.util.find_spec("theano"))
HAS_PLAIDML = bool(importlib.util.find_spec("plaidml"))
PLAIDML_DEVICES = {}

import invesalius.data.slice_ as slc
from invesalius.segmentation.brain import segment
from invesalius.segmentation.brain import utils

try:
    import theano
except ImportError:
    HAS_THEANO = False

try:
    import plaidml
except ImportError:
    HAS_PLAIDML = False

if HAS_PLAIDML:
    try:
        PLAIDML_DEVICES = utils.get_plaidml_devices()
    except OSError:
        HAS_PLAIDML = False


class BrainSegmenterDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, _(u"Brain segmentation"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        backends = []
        if HAS_PLAIDML:
            backends.append("PlaidML")
        if HAS_THEANO:
            backends.append("Theano")
        self.segmenter = segment.BrainSegmenter()
        #  self.pg_dialog = None
        self.plaidml_devices = PLAIDML_DEVICES
        self.cb_backends = wx.ComboBox(self, wx.ID_ANY, choices=backends, value=backends[0], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        w, h = self.CalcSizeFromTextSize("MM" * (1 + max(len(i) for i in backends)))
        self.cb_backends.SetMinClientSize((w, -1))
        self.chk_use_gpu = wx.CheckBox(self, wx.ID_ANY, _("Use GPU"))
        if HAS_PLAIDML:
            self.lbl_device = wx.StaticText(self, -1, _("Device"))
            self.cb_devices = wx.ComboBox(self, wx.ID_ANY, choices=list(self.plaidml_devices.keys()), value=list(self.plaidml_devices.keys())[0],style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.sld_threshold = wx.Slider(self, wx.ID_ANY, 75, 0, 100)
        w, h = self.CalcSizeFromTextSize("M" * 20)
        self.sld_threshold.SetMinClientSize((w, -1))
        self.txt_threshold = wx.TextCtrl(self, wx.ID_ANY, "")
        w, h = self.CalcSizeFromTextSize("MMMMM")
        self.txt_threshold.SetMinClientSize((w, -1))
        self.progress = wx.Gauge(self, -1)
        self.btn_segment = wx.Button(self, wx.ID_ANY, _("Segment"))
        self.btn_stop = wx.Button(self, wx.ID_ANY, _("Stop"))
        self.btn_stop.Disable()
        self.btn_close = wx.Button(self, wx.ID_CLOSE)

        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))

        self.__do_layout()
        self.__set_events()

    def __do_layout(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_3 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_backends = wx.BoxSizer(wx.HORIZONTAL)
        label_1 = wx.StaticText(self, wx.ID_ANY, _("Backend"))
        sizer_backends.Add(label_1, 0, wx.ALIGN_CENTER, 0)
        sizer_backends.Add(self.cb_backends, 1, wx.LEFT, 0)
        main_sizer.Add(sizer_backends, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.chk_use_gpu, 0, wx.ALL, 5)
        sizer_devices = wx.BoxSizer(wx.HORIZONTAL)
        if HAS_PLAIDML:
            sizer_devices.Add(self.lbl_device, 0, wx.ALIGN_CENTER, 0)
            sizer_devices.Add(self.cb_devices, 1, wx.LEFT, 5)
        main_sizer.Add(sizer_devices, 0, wx.ALL | wx.EXPAND, 5)
        label_5 = wx.StaticText(self, wx.ID_ANY, _("Level of certainty"))
        main_sizer.Add(label_5, 0, wx.ALL, 5)
        sizer_3.Add(self.sld_threshold, 1, wx.ALIGN_CENTER | wx.BOTTOM | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer_3.Add(self.txt_threshold, 0, wx.ALL, 5)
        main_sizer.Add(sizer_3, 0, wx.EXPAND, 0)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons.Add(self.btn_close, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_buttons.Add(self.btn_stop, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_buttons.Add(self.btn_segment, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 5)
        main_sizer.Add(sizer_buttons, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 0)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        main_sizer.SetSizeHints(self)

        self.main_sizer = main_sizer

        self.OnSetBackend()

        self.Layout()
        self.Centre()

    def __set_events(self):
        self.cb_backends.Bind(wx.EVT_COMBOBOX, self.OnSetBackend)
        self.sld_threshold.Bind(wx.EVT_SCROLL, self.OnScrollThreshold)
        self.txt_threshold.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.btn_segment.Bind(wx.EVT_BUTTON, self.OnSegment)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.OnStop)
        self.btn_close.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def CalcSizeFromTextSize(self, text):
        dc = wx.WindowDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(text)
        return width, height

    def OnSetBackend(self, evt=None):
        if self.cb_backends.GetValue().lower() == "plaidml":
            if HAS_PLAIDML:
                self.lbl_device.Show()
                self.cb_devices.Show()
            self.chk_use_gpu.Hide()
        else:
            if HAS_PLAIDML:
                self.lbl_device.Hide()
                self.cb_devices.Hide()
            self.chk_use_gpu.Show()

        self.main_sizer.Fit(self)
        self.main_sizer.SetSizeHints(self)

    def OnScrollThreshold(self, evt):
        value = self.sld_threshold.GetValue()
        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))
        if self.segmenter.segmented:
            threshold = value / 100.0
            self.segmenter.set_threshold(threshold)
            image = slc.Slice().discard_all_buffers()
            Publisher.sendMessage('Reload actual slice')

    def OnKillFocus(self, evt):
        value = self.txt_threshold.GetValue()
        value = value.replace('%', '')
        try:
            value = int(value)
        except ValueError:
            value = self.sld_threshold.GetValue()
        self.sld_threshold.SetValue(value)
        self.txt_threshold.SetValue("{:3d}%".format(value))

        if self.segmenter.segmented:
            threshold = value / 100.0
            self.segmenter.set_threshold(threshold)
            image = slc.Slice().discard_all_buffers()
            Publisher.sendMessage('Reload actual slice')

    def OnSegment(self, evt):
        image = slc.Slice().matrix
        backend = self.cb_backends.GetValue()
        try:
            device_id = self.plaidml_devices[self.cb_devices.GetValue()]
        except (KeyError, AttributeError):
            device_id = "llvm_cpu.0"
        use_gpu = self.chk_use_gpu.GetValue()
        prob_threshold = self.sld_threshold.GetValue() / 100.0
        self.btn_close.Disable()
        self.btn_stop.Enable()
        self.btn_segment.Disable()
        self.segmenter.segment(image, prob_threshold, backend, device_id, use_gpu, self.SetProgress, self.AfterSegment)

    def OnStop(self, evt):
        self.segmenter.stop = True
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        evt.Skip()

    def OnBtnClose(self, evt):
        self.Close()

    def AfterSegment(self):
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Disable()
        Publisher.sendMessage('Reload actual slice')

    def SetProgress(self, progress):
        self.progress.SetValue(progress * 100)
        #  self.pg_dialog.Update(progress * 100)
        wx.GetApp().Yield()

    def OnClose(self, evt):
        self.segmenter.stop = True
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        self.progress.SetValue(0)
        self.Destroy()


class MyApp(wx.App):
    def OnInit(self):
        self.dlg_brain_seg = MyDialog(None, wx.ID_ANY, "")
        self.SetTopWindow(self.dlg_brain_seg)
        self.dlg_brain_seg.ShowModal()
        self.dlg_brain_seg.Destroy()
        return True

if __name__ == "__main__":
    app = MyApp(0)
    app.MainLoop()
