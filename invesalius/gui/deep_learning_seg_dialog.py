#!/usr/bin/env python3
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

import invesalius.data.slice_ as slc
from invesalius.gui import dialogs
from invesalius.pubsub import pub as Publisher
from invesalius.segmentation.deep_learning import segment, utils

from typing import Dict, List, Tuple, Union, Any, Optional, Callable

HAS_THEANO: bool = bool(importlib.util.find_spec("theano"))
HAS_PLAIDML: bool = bool(importlib.util.find_spec("plaidml"))
PLAIDML_DEVICES: Dict[str, str] = {}
TORCH_DEVICES: Dict[str, str] = {}

try:
    import torch

    HAS_TORCH: bool = True
except ImportError:
    HAS_TORCH: bool = False

if HAS_TORCH:
    TORCH_DEVICES: Dict[str, str] = {}
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            name: str = torch.cuda.get_device_name()
            device_id: str = f"cuda:{i}"
            TORCH_DEVICES[name] = device_id
    TORCH_DEVICES["CPU"] = "cpu"


if HAS_PLAIDML:
    with multiprocessing.Pool(1) as p:
        try:
            PLAIDML_DEVICES = p.apply(utils.get_plaidml_devices)
        except Exception as err:
            print(err)
            PLAIDML_DEVICES = {}
            HAS_PLAIDML = False


class DeepLearningSegmenterDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        title: str,
        has_torch: bool = True,
        has_plaidml: bool = True,
        has_theano: bool = True,
        segmenter: Union[None, Any] = None
    ) -> None:
        wx.Dialog.__init__(
            self,
            parent,
            -1,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )
        backends: List[str] = []
        if HAS_TORCH and has_torch:
            backends.append("Pytorch")
        if HAS_PLAIDML and has_plaidml:
            backends.append("PlaidML")
        if HAS_THEANO and has_theano:
            backends.append("Theano")
        self.segmenter: Union[None, Any] = segmenter
        #  self.pg_dialog = None
        self.torch_devices: Dict[str, str] = TORCH_DEVICES
        self.plaidml_devices: Dict[str, str] = PLAIDML_DEVICES

        self.ps: Union[None, Any] = None
        self.segmented: bool = False
        self.mask: Union[None, Any] = None

        self.overlap_options: Tuple[int, int, int, int] = (0, 10, 25, 50)
        self.default_overlap: int = 50

        self.cb_backends: wx.ComboBox = wx.ComboBox(
            self,
            wx.ID_ANY,
            choices=backends,
            value=backends[0],
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        w, h = self.CalcSizeFromTextSize("MM" * (1 + max(len(i) for i in backends)))
        self.cb_backends.SetMinClientSize((w, -1))
        self.chk_use_gpu: wx.CheckBox = wx.CheckBox(self, wx.ID_ANY, _("Use GPU"))
        if HAS_TORCH or HAS_PLAIDML:
            if HAS_TORCH:
                choices: List[str] = list(self.torch_devices.keys())
                value: str = choices[0]
            else:
                choices: List[str] = list(self.plaidml_devices.keys())
                value: str = choices[0]
            self.lbl_device: wx.StaticText = wx.StaticText(self, -1, _("Device"))
            self.cb_devices: wx.ComboBox = wx.ComboBox(
                self,
                wx.ID_ANY,
                choices=choices,
                value=value,
                style=wx.CB_DROPDOWN | wx.CB_READONLY,
            )
        self.sld_threshold: wx.Slider = wx.Slider(self, wx.ID_ANY, 75, 0, 100)
        w, h = self.CalcSizeFromTextSize("M" * 20)
        self.sld_threshold.SetMinClientSize((w, -1))
        self.txt_threshold: wx.TextCtrl = wx.TextCtrl(self, wx.ID_ANY, "")
        w, h = self.CalcSizeFromTextSize("MMMMM")
        self.txt_threshold.SetMinClientSize((w, -1))
        self.chk_new_mask: wx.CheckBox = wx.CheckBox(self, wx.ID_ANY, _("Create new mask"))
        self.chk_new_mask.SetValue(True)
        self.chk_apply_wwwl: wx.CheckBox = wx.CheckBox(self, wx.ID_ANY, _("Apply WW&WL"))
        self.chk_apply_wwwl.SetValue(False)
        self.overlap: wx.RadioBox = wx.RadioBox(
            self,
            -1,
            _("Overlap"),
            choices=[f"{i}%" for i in self.overlap_options],
            style=wx.NO_BORDER | wx.HORIZONTAL,
        )
        self.overlap.SetSelection(self.overlap_options.index(self.default_overlap))
        self.progress: wx.Gauge = wx.Gauge(self, -1)
        self.lbl_progress_caption: wx.StaticText = wx.StaticText(self, -1, _("Elapsed time:"))
        self.lbl_time: wx.StaticText = wx.StaticText(self, -1, _("00:00:00"))
        self.btn_segment: wx.Button = wx.Button(self, wx.ID_ANY, _("Segment"))
        self.btn_stop: wx.Button = wx.Button(self, wx.ID_ANY, _("Stop"))
        self.btn_stop.Disable()
        self.btn_close: wx.Button = wx.Button(self, wx.ID_CLOSE)

        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))

        self.elapsed_time_timer: wx.Timer = wx.Timer()

        self.__do_layout()
        self.__set_events()


    def __do_layout(self) -> None:
        main_sizer: wx.BoxSizer = wx.BoxSizer(wx.VERTICAL)
        sizer_3: wx.BoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer_backends: wx.BoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        label_1: wx.StaticText = wx.StaticText(self, wx.ID_ANY, _("Backend"))
        sizer_backends.Add(label_1, 0, wx.ALIGN_CENTER, 0)
        sizer_backends.Add(self.cb_backends, 1, wx.LEFT, 5)
        main_sizer.Add(sizer_backends, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.chk_use_gpu, 0, wx.ALL, 5)
        sizer_devices: wx.BoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        if HAS_TORCH or HAS_PLAIDML:
            sizer_devices.Add(self.lbl_device, 0, wx.ALIGN_CENTER, 0)
            sizer_devices.Add(self.cb_devices, 1, wx.LEFT, 5)
        main_sizer.Add(sizer_devices, 0, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(self.overlap, 0, wx.ALL | wx.EXPAND, 5)
        label_5: wx.StaticText = wx.StaticText(self, wx.ID_ANY, _("Level of certainty"))
        main_sizer.Add(label_5, 0, wx.ALL, 5)
        sizer_3.Add(
            self.sld_threshold,
            1,
            wx.BOTTOM | wx.EXPAND | wx.LEFT | wx.RIGHT,
            5,
        )
        sizer_3.Add(self.txt_threshold, 0, wx.ALL, 5)
        main_sizer.Add(sizer_3, 0, wx.EXPAND, 0)
        main_sizer.Add(self.chk_apply_wwwl, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.chk_new_mask, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)
        time_sizer: wx.BoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        time_sizer.Add(self.lbl_progress_caption, 0, wx.EXPAND, 0)
        time_sizer.Add(self.lbl_time, 1, wx.EXPAND | wx.LEFT, 5)
        main_sizer.Add(time_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer_buttons: wx.BoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons.Add(self.btn_close, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
        sizer_buttons.Add(self.btn_stop, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
        sizer_buttons.Add(self.btn_segment, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
        main_sizer.Add(sizer_buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 0)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        main_sizer.SetSizeHints(self)

        self.main_sizer: wx.BoxSizer = main_sizer

        self.OnSetBackend()
        self.HideProgress()

        self.Layout()
        self.Centre()

    def __set_events(self) -> None:
        self.cb_backends.Bind(wx.EVT_COMBOBOX, self.OnSetBackend)
        self.sld_threshold.Bind(wx.EVT_SCROLL, self.OnScrollThreshold)
        self.txt_threshold.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.btn_segment.Bind(wx.EVT_BUTTON, self.OnSegment)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.OnStop)
        self.btn_close.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.elapsed_time_timer.Bind(wx.EVT_TIMER, self.OnTickTimer)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def apply_segment_threshold(self) -> None:
        threshold: float = self.sld_threshold.GetValue() / 100.0
        if self.ps is not None:
            self.ps.apply_segment_threshold(threshold)
            slc.Slice().discard_all_buffers()
            Publisher.sendMessage("Reload actual slice")

    def CalcSizeFromTextSize(self, text: str) -> Tuple[int, int]:
        dc: wx.WindowDC = wx.WindowDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(text)
        return width, height

    def OnSetBackend(self, evt: Optional[wx.Event] = None) -> None:
        if self.cb_backends.GetValue().lower() == "pytorch":
            if HAS_TORCH:
                choices: List[str] = list(self.torch_devices.keys())
                self.cb_devices.Clear()
                self.cb_devices.SetItems(choices)
                self.cb_devices.SetValue(choices[0])
                self.lbl_device.Show()
                self.cb_devices.Show()
            self.chk_use_gpu.Hide()
        elif self.cb_backends.GetValue().lower() == "plaidml":
            if HAS_PLAIDML:
                choices: List[str] = list(self.plaidml_devices.keys())
                self.cb_devices.Clear()
                self.cb_devices.SetItems(choices)
                self.cb_devices.SetValue(choices[0])
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

    def OnScrollThreshold(self, evt: wx.ScrollEvent) -> None:
        value: int = self.sld_threshold.GetValue()
        self.txt_threshold.SetValue("{:3d}%".format(self.sld_threshold.GetValue()))
        if self.segmented:
            self.apply_segment_threshold()

    def OnKillFocus(self, evt: wx.FocusEvent) -> None:
        value: str = self.txt_threshold.GetValue()
        value = value.replace("%", "")
        try:
            value = int(value)
        except ValueError:
            value = self.sld_threshold.GetValue()
        self.sld_threshold.SetValue(value)
        self.txt_threshold.SetValue("{:3d}%".format(value))

        if self.segmented:
            self.apply_segment_threshold()
    

    def OnSegment(self, evt: Event) -> None:
        self.ShowProgress()
        self.t0: float = time.time()
        self.elapsed_time_timer.Start(1000)
        image: np.ndarray = slc.Slice().matrix
        backend: str = self.cb_backends.GetValue()
        if backend.lower() == "pytorch":
            try:
                device_id: Union[str, int] = self.torch_devices[self.cb_devices.GetValue()]
            except (KeyError, AttributeError):
                device_id = "cpu"
        else:
            try:
                device_id: str = self.plaidml_devices[self.cb_devices.GetValue()]
            except (KeyError, AttributeError):
                device_id = "llvm_cpu.0"
        apply_wwwl: bool = self.chk_apply_wwwl.GetValue()
        create_new_mask: bool = self.chk_new_mask.GetValue()
        use_gpu: bool = self.chk_use_gpu.GetValue()
        prob_threshold: float = self.sld_threshold.GetValue() / 100.0
        self.btn_close.Disable()
        self.btn_stop.Enable()
        self.btn_segment.Disable()
        self.chk_new_mask.Disable()

        window_width: float = slc.Slice().window_width
        window_level: float = slc.Slice().window_level

        overlap: str = self.overlap_options[self.overlap.GetSelection()]

        try:
            self.ps: multiprocessing.Process = self.segmenter(
                image,
                create_new_mask,
                backend,
                device_id,
                use_gpu,
                overlap,
                apply_wwwl,
                window_width,
                window_level,
            )
            self.ps.start()
        except (multiprocessing.ProcessError, OSError, ValueError) as err:
            self.OnStop(None)
            self.HideProgress()
            dlg: dialogs.ErrorMessageBox = dialogs.ErrorMessageBox(
                None,
                "It was not possible to start brain segmentation because:"
                + "\n"
                + str(err),
                "Brain segmentation error",
                #  wx.ICON_ERROR | wx.OK,
            )
            dlg.ShowModal()

    def OnStop(self, evt: Event) -> None:
        if self.ps is not None:
            self.ps.terminate()
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        self.chk_new_mask.Enable()
        self.elapsed_time_timer.Stop()

    def OnBtnClose(self, evt: Event) -> None:
        self.Close()

    def AfterSegment(self) -> None:
        self.segmented: bool = True
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Disable()
        self.chk_new_mask.Disable()
        self.elapsed_time_timer.Stop()
        self.apply_segment_threshold()

    def SetProgress(self, progress: float) -> None:
        self.progress.SetValue(int(progress * 100))
        wx.GetApp().Yield()

    def OnTickTimer(self, evt: Event) -> None:
        fmt: str = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        if self.ps is not None:
            if not self.ps.is_alive() and self.ps.exception is not None:
                error, traceback = self.ps.exception
                self.OnStop(None)
                self.HideProgress()
                dlg: dialogs.ErrorMessageBox = dialogs.ErrorMessageBox(
                    None,
                    "Brain segmentation error",
                    "It was not possible to use brain segmentation because:"
                    + "\n"
                    + str(error)
                    + "\n"
                    + traceback,
                    #  wx.ICON_ERROR | wx.OK,
                )
                dlg.ShowModal()
                return

            progress: float = self.ps.get_completion()
            if progress == np.Inf:
                progress = 1
                self.AfterSegment()
            progress = max(0, min(progress, 1))
            self.SetProgress(float(progress))

    def OnClose(self, evt: Event) -> None:
        #  self.segmenter.stop = True
        self.btn_stop.Disable()
        self.btn_segment.Enable()
        self.chk_new_mask.Enable()
        self.progress.SetValue(0)

        if self.ps is not None:
            self.ps.terminate()
            self.ps = None

        self.Destroy()

    def HideProgress(self) -> None:
        self.progress.Hide()
        self.lbl_progress_caption.Hide()
        self.lbl_time.Hide()
        self.main_sizer.Fit(self)
        self.main_sizer.SetSizeHints(self)

    def ShowProgress(self) -> None:
        self.progress.Show()
        self.lbl_progress_caption.Show()
        self.lbl_time.Show()
        self.main_sizer.Fit(self)
        self.main_sizer.SetSizeHints(self)


class BrainSegmenterDialog(DeepLearningSegmenterDialog):
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(
            parent=parent,
            title=_("Brain segmentation"),
            has_torch=True,
            has_plaidml=True,
            has_theano=True,
            segmenter = segment.BrainSegmentProcess,
        )


class TracheaSegmenterDialog(DeepLearningSegmenterDialog):
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(
            parent=parent,
            title=_("Trachea segmentation"),
            has_torch=True,
            has_plaidml=False,
            has_theano=False,
            segmenter = segment.TracheaSegmentProcess,
        )
