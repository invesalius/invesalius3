#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------

import multiprocessing
import time

import wx
import wx.lib.agw.customtreectrl as CT

import invesalius.data.slice_ as slc
from invesalius.gui import dialogs
from invesalius.gui.deep_learning_seg_dialog import (
    HAS_TINYGRAD,
    HAS_TORCH,
    DeepLearningSegmenterDialog,
)
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

# Backend labels shown in the combo. Replaces base's Pytorch/Tinygrad.
TOTALSEG_BACKENDS = []
if HAS_TORCH:
    TOTALSEG_BACKENDS.append("JIT")
TOTALSEG_BACKENDS.append("ONNX")


def _all_tasks():
    from invesalius.segmentation.deep_learning.totalseg.merge import MULTIPART_TASKS
    from invesalius.segmentation.deep_learning.totalseg.weights import TASK_REGISTRY

    return list(TASK_REGISTRY.keys()) + list(MULTIPART_TASKS.keys())


def _task_labels(task, cache_only=False):
    from invesalius.segmentation.deep_learning.totalseg import labels as _labels
    from invesalius.segmentation.deep_learning.totalseg import merge as _merge

    if _merge.is_multipart(task):
        # Composite unified labels currently derive from part sidecars; if any
        # part sidecar isn't cached, treat the whole set as unavailable rather
        # than partially populating the tree.
        try:
            labels_dict = _merge.get_unified_labels(task)
        except FileNotFoundError:
            return {}, {}
    else:
        try:
            labels_dict = _labels.get_labels(task, cache_only=cache_only)
        except FileNotFoundError:
            return {}, {}
    return labels_dict, _labels.categorize_labels(labels_dict)


class TotalSegmenterDialog(DeepLearningSegmenterDialog):
    def __init__(self, parent):
        # Deferred so import cost is only paid when the dialog opens.
        from invesalius.segmentation.deep_learning.totalseg.segment_process import TotalSegProcess

        self._task_choices = _all_tasks()
        self._default_task = "ct_total_3mm"
        self._current_labels = {}
        self._current_categories = {}
        self._category_items = {}
        self._class_items = {}

        super().__init__(
            parent=parent,
            title=_("TotalSegmentator (CT / MRI)"),
            has_torch=HAS_TORCH,
            has_tinygrad=HAS_TINYGRAD,
            segmenter=TotalSegProcess,
        )

    def _init_gui(self):
        super()._init_gui()

        # Replace the base's backend labels with JIT / ONNX.
        self.cb_backends.Clear()
        self.cb_backends.SetItems(TOTALSEG_BACKENDS)
        if TOTALSEG_BACKENDS:
            self.cb_backends.SetValue(TOTALSEG_BACKENDS[0])

        self.lbl_task = wx.StaticText(self, -1, _("Task"))
        self.cb_task = wx.ComboBox(
            self,
            wx.ID_ANY,
            choices=self._task_choices,
            value=self._default_task
            if self._default_task in self._task_choices
            else self._task_choices[0],
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )

        # CustomTreeCtrl (not TreeCtrl): checkbox items work on wxPython < 4.1.
        self.tree = CT.CustomTreeCtrl(
            self,
            agwStyle=(
                wx.TR_HAS_BUTTONS
                | wx.TR_HIDE_ROOT
                | wx.TR_LINES_AT_ROOT
                | wx.TR_SINGLE
                | CT.TR_AUTO_CHECK_CHILD
                | CT.TR_AUTO_CHECK_PARENT
            ),
        )
        self.tree.SetMinSize((420, 320))
        self._tree_root = self.tree.AddRoot("root")

        self.btn_check_all = wx.Button(self, wx.ID_ANY, _("Check all"))
        self.btn_uncheck_all = wx.Button(self, wx.ID_ANY, _("Uncheck all"))

        self.lbl_status = wx.StaticText(self, -1, "")

        self._populate_tree(self.cb_task.GetValue())

        # Not applicable to label-map output.
        self.sld_threshold.Hide()
        self.txt_threshold.Hide()
        self.chk_apply_wwwl.Hide()
        self.overlap.Hide()

    def _do_layout(self):
        main = wx.BoxSizer(wx.VERTICAL)

        row_input = wx.BoxSizer(wx.HORIZONTAL)
        row_input.Add(self.lbl_input, 0, wx.ALIGN_CENTER, 0)
        row_input.Add(self.cb_input, 1, wx.LEFT, 5)
        main.Add(row_input, 0, wx.ALL | wx.EXPAND, 5)

        row_task = wx.BoxSizer(wx.HORIZONTAL)
        row_task.Add(self.lbl_task, 0, wx.ALIGN_CENTER, 0)
        row_task.Add(self.cb_task, 1, wx.LEFT, 5)
        main.Add(row_task, 0, wx.ALL | wx.EXPAND, 5)

        row_backend = wx.BoxSizer(wx.HORIZONTAL)
        row_backend.Add(wx.StaticText(self, wx.ID_ANY, _("Backend")), 0, wx.ALIGN_CENTER, 0)
        row_backend.Add(self.cb_backends, 1, wx.LEFT, 5)
        main.Add(row_backend, 0, wx.ALL | wx.EXPAND, 5)

        main.Add(self.chk_use_gpu, 0, wx.ALL, 5)

        row_device = wx.BoxSizer(wx.HORIZONTAL)
        row_device.Add(self.lbl_device, 0, wx.ALIGN_CENTER, 0)
        row_device.Add(self.cb_devices, 1, wx.LEFT, 5)
        main.Add(row_device, 0, wx.ALL | wx.EXPAND, 5)

        tree_box = wx.StaticBox(self, -1, _("Structures to segment"))
        tree_sizer = wx.StaticBoxSizer(tree_box, wx.VERTICAL)
        tree_sizer.Add(self.tree, 1, wx.ALL | wx.EXPAND, 5)
        row_check_btns = wx.BoxSizer(wx.HORIZONTAL)
        row_check_btns.Add(self.btn_check_all, 0, wx.RIGHT, 5)
        row_check_btns.Add(self.btn_uncheck_all, 0, 0, 0)
        tree_sizer.Add(row_check_btns, 0, wx.ALL, 5)
        main.Add(tree_sizer, 1, wx.ALL | wx.EXPAND, 5)

        main.Add(self.chk_new_mask, 0, wx.EXPAND | wx.ALL, 5)

        main.Add(self.lbl_status, 0, wx.EXPAND | wx.ALL, 5)
        main.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)
        row_time = wx.BoxSizer(wx.HORIZONTAL)
        row_time.Add(self.lbl_progress_caption, 0, wx.EXPAND, 0)
        row_time.Add(self.lbl_time, 1, wx.EXPAND | wx.LEFT, 5)
        main.Add(row_time, 0, wx.EXPAND | wx.ALL, 5)

        row_btns = wx.BoxSizer(wx.HORIZONTAL)
        row_btns.Add(self.btn_close, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
        row_btns.Add(self.btn_stop, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
        row_btns.Add(self.btn_segment, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)
        main.Add(row_btns, 0, wx.ALIGN_RIGHT | wx.ALL, 0)

        self.SetSizer(main)
        main.Fit(self)
        main.SetSizeHints(self)
        self.SetMinSize((480, self.GetSize().y))
        self.main_sizer = main
        self.Layout()
        self.Centre()

    def _set_events(self):
        super()._set_events()
        self.cb_task.Bind(wx.EVT_COMBOBOX, self.OnTaskChanged)
        self.btn_check_all.Bind(wx.EVT_BUTTON, self.OnCheckAll)
        self.btn_uncheck_all.Bind(wx.EVT_BUTTON, self.OnUncheckAll)

    # Tree population and interaction

    def _populate_tree(self, task):
        self.tree.DeleteChildren(self._tree_root)
        self._category_items = {}
        self._class_items = {}
        # Sidecar fetch is ~1 KB; model binaries wait for the Segment click.
        try:
            self._current_labels, self._current_categories = _task_labels(task)
        except Exception as e:  # noqa: BLE001
            dialogs.ErrorMessageBox(
                None,
                _("Could not load labels for task '{}': {}").format(task, e),
                _("TotalSegmentator"),
            ).ShowModal()
            return

        for category, class_ids in self._current_categories.items():
            cat_item = self.tree.AppendItem(
                self._tree_root, f"{category} ({len(class_ids)})", ct_type=1
            )
            self._category_items[cat_item] = list(class_ids)
            for class_id in class_ids:
                name = self._current_labels[class_id]
                child = self.tree.AppendItem(cat_item, name, ct_type=1)
                self._class_items[child] = class_id
            self.tree.Expand(cat_item)

    def OnTaskChanged(self, evt):
        self._populate_tree(self.cb_task.GetValue())

    def OnCheckAll(self, evt):
        # Category first, TR_AUTO_CHECK_CHILD cascades to children automatically.
        for cat in list(self._category_items.keys()):
            self.tree.CheckItem(cat, True)

    def OnUncheckAll(self, evt):
        for cat in list(self._category_items.keys()):
            self.tree.CheckItem(cat, False)

    def _collect_selected_class_ids(self):
        ids = []
        for item, class_id in self._class_items.items():
            if self.tree.IsItemChecked(item):
                ids.append(int(class_id))
        return sorted(set(ids))

    # Segmentation lifecycle

    def OnSetBackend(self, evt=None):
        # Base dispatches on pytorch/tinygrad; we use JIT/ONNX. Device list is
        # torch's for both (ONNX Runtime shares the same CUDA device).
        if HAS_TORCH:
            choices = list(self.torch_devices.keys())
            self.cb_devices.Clear()
            self.cb_devices.SetItems(choices)
            if choices:
                self.cb_devices.SetValue(choices[0])
            self.lbl_device.Show()
            self.cb_devices.Show()
        self.chk_use_gpu.Hide()
        self.main_sizer.Fit(self)
        self.main_sizer.SetSizeHints(self)

    def OnScrollThreshold(self, evt):
        # Threshold slider is hidden; wrapper ignores threshold.
        pass

    def OnKillFocus(self, evt):
        pass

    def OnTickTimer(self, evt):
        # Only np.inf triggers AfterSegment. Base's `progress >= 1.0` check is
        # fragile — any callback that momentarily hits 1.0 would fire it early.
        import numpy as _np

        fmt = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        if self.ps is None:
            return

        if not self.ps.is_alive() and self.ps.exception is not None:
            error, traceback = self.ps.exception
            self.OnStop(None)
            self.HideProgress()
            dlg = dialogs.ErrorMessageBox(
                None,
                _("TotalSegmentator error"),
                _("It was not possible to run TotalSegmentator because:")
                + "\n"
                + str(error)
                + "\n"
                + traceback,
            )
            dlg.ShowModal()
            return

        status = getattr(self.ps, "get_status", lambda: "")()
        if status:
            self.lbl_status.SetLabel(status)

        progress = self.ps.get_completion()
        if progress == _np.inf:
            self.SetProgress(1.0)
            self.AfterSegment()
        else:
            # Cap display at 0.99; avoids showing 100% mid-work.
            self.SetProgress(max(0.0, min(progress, 0.99)))

    def apply_segment_threshold(self):
        # Threshold ignored; class IDs drive mask generation.
        if self.ps is not None:
            self.ps.apply_segment_threshold(None)
            slc.Slice().discard_all_buffers()
            Publisher.sendMessage("Reload actual slice")

    def OnSegment(self, evt):
        task = self.cb_task.GetValue()
        selected = self._collect_selected_class_ids()
        if not selected:
            dialogs.ErrorMessageBox(
                None,
                _("Select at least one structure before segmenting."),
                _("TotalSegmentator"),
            ).ShowModal()
            return

        self.lbl_status.SetLabel("")  # clear any stale status from a prior run
        self.ShowProgress()
        self.t0 = time.time()
        self.elapsed_time_timer.Start(1000)

        image = slc.Slice().matrix
        spacing = slc.Slice().spacing
        backend = self.cb_backends.GetValue().lower()
        create_new_mask = self.chk_new_mask.GetValue()

        try:
            device_id = self.torch_devices[self.cb_devices.GetValue()]
        except (KeyError, AttributeError):
            device_id = "cpu"
        use_gpu = "cpu" not in device_id.lower()

        self.btn_close.Disable()
        self.btn_stop.Enable()
        self.btn_segment.Disable()
        self.chk_new_mask.Disable()
        self.cb_backends.Disable()
        self.cb_devices.Disable()
        self.cb_task.Disable()
        self.tree.Disable()
        self.btn_check_all.Disable()
        self.btn_uncheck_all.Disable()

        # id -> name for per-structure mask naming.
        selected_names = {int(cid): self._current_labels[cid] for cid in selected}

        try:
            self.ps = self.segmenter(
                image,
                create_new_mask,
                backend,
                device_id,
                use_gpu,
                task,
                spacing,
                selected_class_ids=selected,
                selected_class_names=selected_names,
            )
            self.ps.start()
        except (multiprocessing.ProcessError, OSError, ValueError) as err:
            self.OnStop(None)
            self.HideProgress()
            dialogs.ErrorMessageBox(
                None,
                _("Could not start TotalSegmentator: ") + str(err),
                _("TotalSegmentator error"),
            ).ShowModal()

    def AfterSegment(self):
        self.segmented = True
        self.btn_close.Enable()
        self.btn_stop.Disable()
        self.btn_segment.Disable()
        self.chk_new_mask.Disable()
        self.cb_backends.Disable()
        self.cb_devices.Disable()
        self.cb_task.Disable()
        self.elapsed_time_timer.Stop()
        self.apply_segment_threshold()

        n = getattr(self.ps, "masks_created", 0) if self.ps else 0
        elapsed = int(time.time() - self.t0)
        mm, ss = divmod(elapsed, 60)
        dlg = wx.MessageDialog(
            self,
            _("Segmentation complete.\n\n{} mask(s) created in {:02d}:{:02d}.").format(n, mm, ss),
            _("TotalSegmentator"),
            wx.OK | wx.ICON_INFORMATION,
        )
        dlg.ShowModal()
        dlg.Destroy()

    def OnStop(self, evt):
        super().OnStop(evt)
        self.cb_backends.Enable()
        self.cb_devices.Enable()
        self.cb_task.Enable()
        self.tree.Enable()
        self.btn_check_all.Enable()
        self.btn_uncheck_all.Enable()
