#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import os
import pathlib

import wx
from wx.lib.pubsub import pub as Publisher

HAS_THEANO = True
HAS_PLAIDML = True

try:
    import theano
except ImportError:
    HAS_THEANO = False

local_user_plaidml = pathlib.Path("~/.local/share/plaidml/").expanduser().absolute()
if local_user_plaidml.exists():
    os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
    os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("~/.local/lib/libplaidml.so").expanduser().absolute())

try:
    import plaidml
except ImportError:
    HAS_PLAIDML = False

from invesalius.segmentation.brain import segment



class BrainSegmenterDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, _(u"Brain segmentation"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
        backends = []
        if HAS_PLAIDML:
            backends.append("PlaidML")
        if HAS_THEANO:
            backends.append("Theano")
        self.segmenter = segment.BrainSegmenter()

        self.cb_backends = wx.ComboBox(self, wx.ID_ANY, choices=backends, value=backends[0], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        w, h = self.CalcSizeFromTextSize("MM" * (1 + max(len(i) for i in backends)))
        self.cb_backends.SetMinClientSize((w, -1))
        self.chk_use_gpu = wx.CheckBox(self, wx.ID_ANY, "Use GPU")
        self.sld_threshold = wx.Slider(self, wx.ID_ANY, 75, 0, 100)
        w, h = self.CalcSizeFromTextSize("M" * 20)
        self.sld_threshold.SetMinClientSize((w, -1))
        self.txt_threshold = wx.TextCtrl(self, wx.ID_ANY, "")
        w, h = self.CalcSizeFromTextSize("MMMMM")
        self.txt_threshold.SetMinClientSize((w, -1))
        self.progress = wx.Gauge(self, -1)
        self.btn_segment = wx.Button(self, wx.ID_ANY, "Segment")
        self.btn_stop = wx.Button(self, wx.ID_ANY, _("Stop"))
        self.btn_stop.Disable()

        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))

        self.__do_layout()
        self.__set_events()

    def __do_layout(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_3 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_backends = wx.BoxSizer(wx.HORIZONTAL)
        label_1 = wx.StaticText(self, wx.ID_ANY, "Backend")
        sizer_backends.Add(label_1, 0, wx.ALIGN_CENTER, 0)
        sizer_backends.Add(self.cb_backends, 1, wx.LEFT, 5)
        main_sizer.Add(sizer_backends, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.chk_use_gpu, 0, wx.ALL, 5)
        label_5 = wx.StaticText(self, wx.ID_ANY, "Level of certainty")
        main_sizer.Add(label_5, 0, wx.ALL, 5)
        sizer_3.Add(self.sld_threshold, 1, wx.ALIGN_CENTER | wx.BOTTOM | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer_3.Add(self.txt_threshold, 0, wx.ALL, 5)
        main_sizer.Add(sizer_3, 0, wx.EXPAND, 0)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons.Add(self.btn_stop, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_buttons.Add(self.btn_segment, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 5)
        main_sizer.Add(sizer_buttons, 0, wx.ALIGN_BOTTOM | wx.ALIGN_RIGHT | wx.ALL, 0)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        main_sizer.SetSizeHints(self)
        self.Layout()
        self.Centre()

    def __set_events(self):
        self.sld_threshold.Bind(wx.EVT_SCROLL, self.OnScrollThreshold)
        self.txt_threshold.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.btn_segment.Bind(wx.EVT_BUTTON, self.OnSegment)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.OnStop)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def CalcSizeFromTextSize(self, text):
        dc = wx.WindowDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(text)
        return width, height

    def OnScrollThreshold(self, evt):
        value = self.sld_threshold.GetValue()
        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))

    def OnKillFocus(self, evt):
        value = self.txt_threshold.GetValue()
        value = value.replace('%', '')
        try:
            value = int(value)
        except ValueError:
            value = self.sld_threshold.GetValue()
        self.sld_threshold.SetValue(value)
        self.txt_threshold.SetValue("{:3d}%".format(value))

    def OnSegment(self, evt):
        import invesalius.data.slice_ as slc
        image = slc.Slice().matrix
        backend = self.cb_backends.GetValue()
        use_gpu = self.chk_use_gpu.GetValue()
        prob_threshold = self.sld_threshold.GetValue() / 100.0
        self.btn_stop.Enable()
        self.btn_segment.Disable()
        self.segmenter.segment(image, prob_threshold, backend, use_gpu, self.SetProgress, self.AfterSegment)

    def OnStop(self, evt):
        self.segmenter.stop = True
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        self.progress.SetValue(0)

    def AfterSegment(self):
        Publisher.sendMessage('Reload actual slice')

    def SetProgress(self, progress):
        self.progress.SetValue(progress * 100)
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
