#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import importlib
import multiprocessing
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import numpy as np
import wx
from pubsub import pub as Publisher

import invesalius.data.slice_ as slc
from invesalius.segmentation.brain import segment, utils

HAS_THEANO = bool(importlib.util.find_spec("theano"))
HAS_PLAIDML = bool(importlib.util.find_spec("plaidml"))
PLAIDML_DEVICES = {}


if HAS_PLAIDML:
    with multiprocessing.Pool(1) as p:
        try:
            PLAIDML_DEVICES = p.apply(utils.get_plaidml_devices)
        except Exception as err:
            print(err)
            PLAIDML_DEVICES = {}
            HAS_PLAIDML = False


class BrainSegmenterDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(
            self,
            parent,
            -1,
            _(u"Brain segmentation"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )
        backends = []
        if HAS_PLAIDML:
            backends.append("PlaidML")
        if HAS_THEANO:
            backends.append("Theano")
        #  self.segmenter = segment.BrainSegmenter()
        #  self.pg_dialog = None
        self.plaidml_devices = PLAIDML_DEVICES

        self.ps = None
        self.segmented = False
        self.mask = None

        self.cb_backends = wx.ComboBox(
            self,
            wx.ID_ANY,
            choices=backends,
            value=backends[0],
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        w, h = self.CalcSizeFromTextSize("MM" * (1 + max(len(i) for i in backends)))
        self.cb_backends.SetMinClientSize((w, -1))
        self.chk_use_gpu = wx.CheckBox(self, wx.ID_ANY, _("Use GPU"))
        if HAS_PLAIDML:
            self.lbl_device = wx.StaticText(self, -1, _("Device"))
            self.cb_devices = wx.ComboBox(
                self,
                wx.ID_ANY,
                choices=list(self.plaidml_devices.keys()),
                value=list(self.plaidml_devices.keys())[0],
                style=wx.CB_DROPDOWN | wx.CB_READONLY,
            )
        self.sld_threshold = wx.Slider(self, wx.ID_ANY, 75, 0, 100)
        w, h = self.CalcSizeFromTextSize("M" * 20)
        self.sld_threshold.SetMinClientSize((w, -1))
        self.txt_threshold = wx.TextCtrl(self, wx.ID_ANY, "")
        w, h = self.CalcSizeFromTextSize("MMMMM")
        self.txt_threshold.SetMinClientSize((w, -1))
        self.chk_new_mask = wx.CheckBox(self, wx.ID_ANY, _("Create new mask"))
        self.chk_new_mask.SetValue(True)
        self.progress = wx.Gauge(self, -1)
        self.lbl_progress_caption = wx.StaticText(self, -1, _("Elapsed time:"))
        self.lbl_time = wx.StaticText(self, -1, _("00:00:00"))
        self.btn_segment = wx.Button(self, wx.ID_ANY, _("Segment"))
        self.btn_stop = wx.Button(self, wx.ID_ANY, _("Stop"))
        self.btn_stop.Disable()
        self.btn_close = wx.Button(self, wx.ID_CLOSE)

        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))

        self.elapsed_time_timer = wx.Timer()

        self.__do_layout()
        self.__set_events()

    def __do_layout(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_3 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_backends = wx.BoxSizer(wx.HORIZONTAL)
        label_1 = wx.StaticText(self, wx.ID_ANY, _("Backend"))
        sizer_backends.Add(label_1, 0, wx.ALIGN_CENTER, 0)
        sizer_backends.Add(self.cb_backends, 1, wx.LEFT, 5)
        main_sizer.Add(sizer_backends, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.chk_use_gpu, 0, wx.ALL, 5)
        sizer_devices = wx.BoxSizer(wx.HORIZONTAL)
        if HAS_PLAIDML:
            sizer_devices.Add(self.lbl_device, 0, wx.ALIGN_CENTER, 0)
            sizer_devices.Add(self.cb_devices, 1, wx.LEFT, 5)
        main_sizer.Add(sizer_devices, 0, wx.ALL | wx.EXPAND, 5)
        label_5 = wx.StaticText(self, wx.ID_ANY, _("Level of certainty"))
        main_sizer.Add(label_5, 0, wx.ALL, 5)
        sizer_3.Add(
            self.sld_threshold,
            1,
            wx.BOTTOM | wx.EXPAND | wx.LEFT | wx.RIGHT,
            5,
        )
        sizer_3.Add(self.txt_threshold, 0, wx.ALL, 5)
        main_sizer.Add(sizer_3, 0, wx.EXPAND, 0)
        main_sizer.Add(self.chk_new_mask, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)
        time_sizer = wx.BoxSizer(wx.HORIZONTAL)
        time_sizer.Add(self.lbl_progress_caption, 0, wx.EXPAND, 0)
        time_sizer.Add(self.lbl_time, 1, wx.EXPAND | wx.LEFT, 5)
        main_sizer.Add(time_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons.Add(
            self.btn_close, 0, wx.ALIGN_BOTTOM | wx.ALL, 5
        )
        sizer_buttons.Add(
            self.btn_stop, 0, wx.ALIGN_BOTTOM | wx.ALL, 5
        )
        sizer_buttons.Add(
            self.btn_segment, 0, wx.ALIGN_BOTTOM | wx.ALL, 5
        )
        main_sizer.Add(sizer_buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 0)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        main_sizer.SetSizeHints(self)

        self.main_sizer = main_sizer

        self.OnSetBackend()
        self.HideProgress()

        self.Layout()
        self.Centre()

    def __set_events(self):
        self.cb_backends.Bind(wx.EVT_COMBOBOX, self.OnSetBackend)
        self.sld_threshold.Bind(wx.EVT_SCROLL, self.OnScrollThreshold)
        self.txt_threshold.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.btn_segment.Bind(wx.EVT_BUTTON, self.OnSegment)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.OnStop)
        self.btn_close.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.elapsed_time_timer.Bind(wx.EVT_TIMER, self.OnTickTimer)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def apply_segment_threshold(self):
        threshold = self.sld_threshold.GetValue() / 100.0
        if self.ps is not None:
            self.ps.apply_segment_threshold(threshold)
            slc.Slice().discard_all_buffers()
            Publisher.sendMessage("Reload actual slice")

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
        if self.segmented:
            self.apply_segment_threshold()

    def OnKillFocus(self, evt):
        value = self.txt_threshold.GetValue()
        value = value.replace("%", "")
        try:
            value = int(value)
        except ValueError:
            value = self.sld_threshold.GetValue()
        self.sld_threshold.SetValue(value)
        self.txt_threshold.SetValue("{:3d}%".format(value))

        if self.segmented:
            self.apply_segment_threshold()

    def OnSegment(self, evt):
        self.ShowProgress()
        self.t0 = time.time()
        self.elapsed_time_timer.Start(1000)
        image = slc.Slice().matrix
        backend = self.cb_backends.GetValue()
        try:
            device_id = self.plaidml_devices[self.cb_devices.GetValue()]
        except (KeyError, AttributeError):
            device_id = "llvm_cpu.0"
        create_new_mask = self.chk_new_mask.GetValue()
        use_gpu = self.chk_use_gpu.GetValue()
        prob_threshold = self.sld_threshold.GetValue() / 100.0
        self.btn_close.Disable()
        self.btn_stop.Enable()
        self.btn_segment.Disable()
        self.chk_new_mask.Disable()

        try:
            self.ps = segment.SegmentProcess(image, create_new_mask, backend, device_id, use_gpu)
            self.ps.start()
        except (multiprocessing.ProcessError, OSError, ValueError) as err:
            self.OnStop(None)
            self.HideProgress()
            dlg = wx.MessageDialog(
                None,
                "It was not possible to start brain segmentation because:"
                + "\n"
                + str(err),
                "Brain segmentation error",
                wx.ICON_ERROR | wx.OK,
            )
            dlg.ShowModal()

    def OnStop(self, evt):
        if self.ps is not None:
            self.ps.terminate()
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        self.chk_new_mask.Enable()
        self.elapsed_time_timer.Stop()

    def OnBtnClose(self, evt):
        self.Close()

    def AfterSegment(self):
        self.segmented = True
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Disable()
        self.chk_new_mask.Disable()
        self.elapsed_time_timer.Stop()
        self.apply_segment_threshold()

    def SetProgress(self, progress):
        self.progress.SetValue(progress * 100)
        wx.GetApp().Yield()

    def OnTickTimer(self, evt):
        fmt = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        if self.ps is not None:
            if not self.ps.is_alive() and self.ps.exception is not None:
                error, traceback = self.ps.exception
                self.OnStop(None)
                self.HideProgress()
                dlg = wx.MessageDialog(
                    None,
                    "It was not possible to use brain segmentation because:"
                    + "\n"
                    + str(error)
                    + "\n"
                    + traceback,
                    "Brain segmentation error",
                    wx.ICON_ERROR | wx.OK,
                )
                dlg.ShowModal()
                return

            progress = self.ps.get_completion()
            if progress == np.Inf:
                progress = 1
                self.AfterSegment()
            if progress < 0:
                progress = 0
            if progress > 1:
                progress = 1
            self.SetProgress(float(progress))

    def OnClose(self, evt):
        #  self.segmenter.stop = True
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        self.chk_new_mask.Enable()
        self.progress.SetValue(0)

        if self.ps is not None:
            self.ps.terminate()
            self.ps = None

        self.Destroy()

    def HideProgress(self):
        self.progress.Hide()
        self.lbl_progress_caption.Hide()
        self.lbl_time.Hide()
        self.main_sizer.Fit(self)
        self.main_sizer.SetSizeHints(self)

    def ShowProgress(self):
        self.progress.Show()
        self.lbl_progress_caption.Show()
        self.lbl_time.Show()
        self.main_sizer.Fit(self)
        self.main_sizer.SetSizeHints(self)


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
