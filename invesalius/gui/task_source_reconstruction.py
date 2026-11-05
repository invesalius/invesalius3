# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

from pathlib import Path
from queue import Queue
from threading import Event, Thread

import numpy as np
import wx

import invesalius.gui.dialogs as dlg
from invesalius.data.eeg import MissingSurfaceGeometryError, discover_subject_files
from invesalius.data.image_registration import register_image_to_volume
from invesalius.data.visualization.surface_painting import SurfacePainting
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)

        button = wx.Button(self, label=_("Import source reconstruction..."))
        button.SetToolTip(_("Select the files for an EEG/MEG cortical source reconstruction."))
        button.Bind(wx.EVT_BUTTON, self.OnImport)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(button, 0, wx.ALL | wx.EXPAND, 7)
        display_row = wx.BoxSizer(wx.HORIZONTAL)
        self.display_label = wx.StaticText(self, label=_("Display:"))
        display_row.Add(self.display_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self._representation_labels = {
            "pial": _("Pial"),
            "white": _("White"),
            "inflated": _("Inflated"),
        }
        self._representations = ("pial",)
        self.representation = wx.Choice(self, choices=[self._representation_labels["pial"]])
        self.representation.SetSelection(0)
        self.representation.SetToolTip(
            _("Select EEG/MEG color mapping on Brain to change its cortical representation.")
        )
        self.representation.Bind(wx.EVT_CHOICE, self.OnDisplayChanged)
        display_row.Add(self.representation, 1, wx.EXPAND)
        sizer.Add(display_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)
        hemisphere_row = wx.BoxSizer(wx.HORIZONTAL)
        self.left = wx.CheckBox(self, label=_("Left"))
        self.right = wx.CheckBox(self, label=_("Right"))
        for checkbox in (self.left, self.right):
            checkbox.SetValue(True)
            checkbox.Bind(wx.EVT_CHECKBOX, self.OnDisplayChanged)
            hemisphere_row.Add(checkbox, 0, wx.RIGHT, 12)
        sizer.Add(hemisphere_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)
        self.SetSizerAndFit(sizer)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
        Publisher.subscribe(self.OnSourceChanged, "Source reconstruction changed")
        self._mode = SurfacePainting().modes.get("EEG/MEG")
        self._sync_display_controls()

    def OnImport(self, event):
        with ImportSourceDialog(wx.GetApp().GetTopWindow()) as dialog:
            dialog.ShowModal()

    def OnSourceChanged(self, mode):
        self._mode = mode
        self._sync_display_controls()

    def _sync_display_controls(self):
        mode = self._mode
        loaded = mode is not None and mode.series is not None
        representations = mode.series.representations if loaded else ("pial",)
        if representations != self._representations:
            self._representations = representations
            self.representation.SetItems(
                [self._representation_labels[key] for key in representations]
            )
        selected = representations.index(mode.representation if loaded else "pial")
        if self.representation.GetSelection() != selected:
            self.representation.SetSelection(selected)
        visible = mode.hemispheres_visible if loaded else (True, True)
        for checkbox, checked in zip((self.left, self.right), visible):
            if checkbox.GetValue() != checked:
                checkbox.SetValue(checked)
        active = loaded and mode.display_active
        for control in (self.display_label, self.representation, self.left, self.right):
            if control.IsEnabled() != active:
                control.Enable(active)

    def OnDisplayChanged(self, event):
        if self._mode is None or not self._mode.display_active:
            self._sync_display_controls()
            return
        index = self.representation.GetSelection()
        if index == wx.NOT_FOUND:
            return
        try:
            with wx.BusyCursor():
                Publisher.sendMessage(
                    "Set source reconstruction display",
                    representation=self._representations[index],
                    left=self.left.GetValue(),
                    right=self.right.GetValue(),
                )
        except Exception as error:
            with dlg.ErrorMessageBox(
                wx.GetApp().GetTopWindow(), _("Error changing source display"), str(error)
            ) as dialog:
                dialog.ShowModal()
        finally:
            self._sync_display_controls()

    def OnDestroy(self, event):
        if event.GetEventObject() is self:
            Publisher.unsubscribe_owner(self)
        event.Skip()


class ImportSourceDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(
            parent,
            title=_("Import EEG/MEG source reconstruction"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._automatic_alignment = None
        self._reference_mri = None
        self.files = {}
        self.file_labels = {"stc": _("STC signal:")}
        form = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        form.AddGrowableCol(1)
        form.Add(wx.StaticText(self, label=_("Subject:")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.subject = wx.DirPickerCtrl(
            self,
            message=_("Select the subject folder containing the surf directory"),
            style=wx.DIRP_USE_TEXTCTRL | wx.DIRP_SMALL | wx.DIRP_DIR_MUST_EXIST,
        )
        self.subject.SetToolTip(
            _(
                "Select a subject folder to detect surfaces automatically. Leave empty to select them manually."
            )
        )
        form.Add(self.subject, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, label=self.file_labels["stc"]), 0, wx.ALIGN_CENTER_VERTICAL)
        signal_row = wx.BoxSizer(wx.HORIZONTAL)
        self.files["stc"] = wx.FilePickerCtrl(
            self,
            message=_("Select either hemisphere of the STC pair"),
            wildcard=_("STC files (*.stc)|*.stc"),
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL | wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST,
        )
        self.files["stc"].SetToolTip(
            _("Select -lh.stc or -rh.stc; the matching file must be in the same directory.")
        )
        signal_row.Add(self.files["stc"], 1, wx.EXPAND)
        signal_row.Add(
            wx.StaticText(self, label=_("Unit:")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT,
            8,
        )
        self.unit = wx.ComboBox(
            self,
            value="dSPM",
            choices=["dSPM", "A.m", "nA.m", "sLORETA", "eLORETA", "a.u."],
            style=wx.CB_DROPDOWN,
            size=self.FromDIP((110, -1)),
        )
        self.unit.SetToolTip(
            _(
                "Unit or method label for the imported values; no conversion is performed. STC files do not store it."
            )
        )
        signal_row.Add(self.unit, 0, wx.EXPAND)
        form.Add(signal_row, 1, wx.EXPAND)
        main_sizer.Add(form, 0, wx.EXPAND | wx.ALL, 12)

        detected = wx.StaticBoxSizer(wx.VERTICAL, self, _("Detected files"))
        table_parent = detected.GetStaticBox()
        table = wx.FlexGridSizer(cols=3, vgap=6, hgap=24)
        table.AddGrowableCol(0)
        for title in (_("Surface"), _("Left"), _("Right")):
            heading = wx.StaticText(table_parent, label=title)
            heading.SetFont(heading.GetFont().Bold())
            table.Add(heading, 0, wx.ALIGN_CENTER_VERTICAL)
        self.subject_cells = {}
        for kind, label in (
            ("pial", _("Pial (required)")),
            ("white", _("White")),
            ("inflated", _("Inflated")),
            ("curv", _("Curvature")),
        ):
            table.Add(wx.StaticText(table_parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            for side in ("lh", "rh"):
                cell = wx.StaticText(table_parent, label="\u2014")
                cell.SetMinSize(self.FromDIP((72, -1)))
                cell.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
                self.subject_cells[kind, side] = cell
                table.Add(cell, 0, wx.ALIGN_CENTER_VERTICAL)
        detected.Add(table, 0, wx.EXPAND | wx.ALL, 10)
        main_sizer.Add(detected, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.subject_summary = wx.StaticText(
            self, label=_("Uses surface coordinates in the current anatomy.")
        )
        self.subject_summary.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        )
        main_sizer.Add(self.subject_summary, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.manual = wx.CollapsiblePane(
            self,
            label=_("Select surfaces manually"),
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE,
        )
        manual_parent = self.manual.GetPane()
        manual_sizer = wx.BoxSizer(wx.VERTICAL)
        manual_sizer.Add(
            wx.StaticText(
                manual_parent,
                label=_("Leave the subject folder empty to select surfaces manually."),
            ),
            0,
            wx.TOP | wx.BOTTOM,
            8,
        )
        manual_form = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        manual_form.AddGrowableCol(1)
        for key, label in (
            ("lh_surface", _("Left pial:")),
            ("rh_surface", _("Right pial:")),
        ):
            picker = wx.FilePickerCtrl(
                manual_parent,
                message=label,
                wildcard=_("All files (*.*)|*.*"),
                style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL | wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST,
            )
            self.files[key] = picker
            self.file_labels[key] = label
            manual_form.Add(wx.StaticText(manual_parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            manual_form.Add(picker, 1, wx.EXPAND)
        manual_sizer.Add(manual_form, 0, wx.EXPAND | wx.BOTTOM, 8)
        manual_parent.SetSizer(manual_sizer)
        self.manual.Collapse()
        main_sizer.Add(self.manual, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.advanced = wx.CollapsiblePane(
            self,
            label=_("Advanced alignment"),
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE,
        )
        advanced_parent = self.advanced.GetPane()
        advanced_sizer = wx.BoxSizer(wx.VERTICAL)
        self.alignment_mode = wx.Choice(
            advanced_parent,
            choices=[
                _("Align automatically to the project"),
                _("Already aligned: same scanner RAS coordinates"),
                _("Load a transformation matrix"),
            ],
        )
        self.alignment_mode.SetSelection(1)
        self.alignment_mode.Bind(wx.EVT_CHOICE, self.OnRegistrationMode)
        advanced_sizer.Add(self.alignment_mode, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 8)
        self.align_button = wx.Button(
            advanced_parent, label=_("Calculate and preview alignment...")
        )
        self.align_button.Bind(wx.EVT_BUTTON, self.OnAlign)
        advanced_sizer.Add(self.align_button, 0, wx.BOTTOM, 8)
        self.alignment_status = wx.StaticText(
            advanced_parent, label=_("Calculate alignment and select its reference MRI.")
        )
        advanced_sizer.Add(self.alignment_status, 0, wx.EXPAND | wx.BOTTOM, 8)
        self.registration_label = wx.StaticText(
            advanced_parent, label=_("MRI-to-project registration (4 x 4 matrix, mm):")
        )
        advanced_sizer.Add(self.registration_label, 0, wx.BOTTOM, 4)
        self.registration = wx.FilePickerCtrl(
            advanced_parent,
            message=_("Select the scanner RAS to project RAS matrix"),
            wildcard=_("Text matrix (*.txt;*.csv)|*.txt;*.csv|All files (*.*)|*.*"),
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL | wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST,
        )
        self.registration.SetToolTip(
            _("Four rows and four columns, separated by whitespace (.txt) or commas (.csv).")
        )
        advanced_sizer.Add(self.registration, 0, wx.EXPAND | wx.BOTTOM, 8)
        advanced_parent.SetSizer(advanced_sizer)
        for control in (
            self.align_button,
            self.alignment_status,
            self.registration_label,
            self.registration,
        ):
            control.Hide()
        self.advanced.Collapse()
        main_sizer.Add(self.advanced, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        main_sizer.AddStretchSpacer()
        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        self.FindWindow(wx.ID_OK).SetLabel(_("Import"))
        main_sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.Bind(wx.EVT_BUTTON, self.OnImport, id=wx.ID_OK)
        self.SetSizer(main_sizer)
        self.SetMinSize(self.FromDIP((680, -1)))
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.CenterOnParent()
        self.subject.Bind(wx.EVT_DIRPICKER_CHANGED, self.OnSubjectChanged)
        self.subject.GetTextCtrl().Bind(wx.EVT_TEXT, self.OnSubjectChanged)
        for key in ("lh_surface", "rh_surface"):
            self.files[key].Bind(wx.EVT_FILEPICKER_CHANGED, self.OnManualSurfaceChanged)
            self.files[key].GetTextCtrl().Bind(wx.EVT_TEXT, self.OnManualSurfaceChanged)
        self.manual.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnLayoutChanged)
        self.advanced.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnLayoutChanged)

    def _resize_dialog(self):
        for section in (self.manual, self.advanced):
            section.GetPane().InvalidateBestSize()
            section.GetPane().Layout()
            section.InvalidateBestSize()
        self.Layout()
        # Sizer dimensions exclude the title bar and borders included by SetSize.
        minimum = self.ClientToWindowSize(self.GetSizer().GetMinSize())
        self.SetSize((max(self.GetSize().width, minimum.width), minimum.height))
        self.Layout()

    def OnLayoutChanged(self, event):
        self._resize_dialog()
        event.Skip()

    def _show_subject_files(self, files, message):
        absent = _("Missing") if self.subject.GetPath().strip() else "\u2014"
        for (kind, side), cell in self.subject_cells.items():
            path = files.get(kind, {}).get(side)
            cell.SetLabel(_("Found") if path else absent)
            cell.SetToolTip(str(path) if path else "")
            cell.SetForegroundColour(
                wx.SystemSettings.GetColour(
                    wx.SYS_COLOUR_WINDOWTEXT if path else wx.SYS_COLOUR_GRAYTEXT
                )
            )
        self.subject_summary.SetLabel(message)
        self.subject_summary.Wrap(self.FromDIP(620))
        self._resize_dialog()

    def OnSubjectChanged(self, event):
        subject_path = self.subject.GetPath().strip()
        for key in ("lh_surface", "rh_surface"):
            self.files[key].SetPath("")
            self.files[key].Enable(not subject_path)
        if self._automatic_alignment is not None:
            self._automatic_alignment = None
            self.alignment_status.SetLabel(
                _("Subject changed. Calculate alignment again if needed.")
            )
        if not subject_path:
            self._show_subject_files({}, _("Uses surface coordinates in the current anatomy."))
        else:
            try:
                files = discover_subject_files(subject_path)
                for side, path in files["pial"].items():
                    self.files[f"{side}_surface"].SetPath(str(path))
                missing = [f"{side}.pial" for side in ("lh", "rh") if side not in files["pial"]]
                message = (
                    _("Required files not found:") + " " + ", ".join(missing)
                    if missing
                    else _(
                        "Uses surface coordinates in the current anatomy. Pial is used for visualization."
                    )
                )
                self._show_subject_files(files, message)
            except (OSError, ValueError) as error:
                self._show_subject_files({}, str(error))
        event.Skip()

    def OnManualSurfaceChanged(self, event):
        if not self.subject.GetPath().strip():
            pial = {}
            for side in ("lh", "rh"):
                path = self.files[f"{side}_surface"].GetPath()
                try:
                    if path.strip() and Path(path).expanduser().is_file():
                        pial[side] = Path(path).expanduser()
                except (OSError, ValueError):
                    continue
            if self._automatic_alignment is not None:
                self._automatic_alignment = None
                self.alignment_status.SetLabel(
                    _("Surfaces changed. Calculate alignment again if needed.")
                )
            self._show_subject_files(
                {"pial": pial}, _("Uses surface coordinates in the current anatomy.")
            )
        event.Skip()

    def OnRegistrationMode(self, event):
        mode = self.alignment_mode.GetSelection()
        self.registration_label.Show(mode == 2)
        self.registration.Show(mode == 2)
        self.align_button.Show(mode == 0)
        self.alignment_status.Show(mode == 0)
        if mode == 0:
            message = (
                _("Alignment reviewed and ready to import.")
                if self._automatic_alignment is not None
                else _("Calculate alignment and select its reference MRI.")
            )
        else:
            message = _("Surface metadata will be used. Automatic alignment is optional.")
        self.alignment_status.SetLabel(message)
        self._resize_dialog()

    def _select_reference_mri(self, message):
        with wx.FileDialog(
            self,
            message=message,
            wildcard=_("FreeSurfer MRI (*.mgz;*.mgh)|*.mgz;*.mgh"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                return Path(dialog.GetPath()).resolve()
        return None

    def _alignment_inputs(self):
        from invesalius.data.slice_ import Slice

        path = self._reference_mri
        if path is None or not path.is_file():
            raise ValueError(_("Select the reference MRI before calculating alignment."))
        slic = Slice()
        data = slic.matrix
        if data is None:
            raise ValueError(_("Open the anatomical volume in the project first."))
        world_to_view = slic.get_world_to_invesalius_vtk_affine()[0]
        spacing = tuple(float(value) for value in slic.spacing)
        # The project's array is ZYX with its Y axis flipped relative to scanner RAS.
        voxel_to_view = np.diag([spacing[0], -spacing[1], spacing[2], 1.0])
        voxel_to_ras = np.linalg.solve(world_to_view, voxel_to_view)
        path = path.resolve()
        stat = path.stat()
        key = (
            str(path),
            stat.st_size,
            stat.st_mtime_ns,
            id(data),
            data.shape,
            voxel_to_ras.tobytes(),
        )
        return path, data, voxel_to_ras, key

    def OnAlign(self, event):
        try:
            reference = self._select_reference_mri(_("Select the FreeSurfer MRI for alignment"))
            if reference is None:
                return
            self._reference_mri = reference
            self._automatic_alignment = None
            self.alignment_status.SetLabel(_("Automatic alignment has not been calculated."))
            path, data, affine, key = self._alignment_inputs()
            cancelled = Event()
            outcome = Queue()

            def calculate():
                try:
                    outcome.put(register_image_to_volume(path, data, affine, cancelled))
                except Exception as error:
                    outcome.put(error)

            worker = Thread(target=calculate, name="RegisterMRI", daemon=True)
            with wx.ProgressDialog(
                _("Align MRI to project"),
                _("Calculating rigid alignment..."),
                parent=self,
                style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME,
            ) as progress:
                worker.start()
                while worker.is_alive():
                    message = (
                        _("Cancelling alignment...")
                        if cancelled.is_set()
                        else _("Calculating rigid alignment...")
                    )
                    keep_going = progress.Pulse(message)[0]
                    if not keep_going:
                        cancelled.set()
                    worker.join(0.05)
            if cancelled.is_set():
                return
            result = outcome.get()
            if isinstance(result, Exception):
                raise result
            if key != self._alignment_inputs()[3]:
                raise ValueError(
                    _("The project or reference MRI changed. Calculate alignment again.")
                )
            with AlignmentPreviewDialog(wx.GetApp().GetTopWindow(), result) as preview:
                if preview.ShowModal() != wx.ID_OK:
                    return
            self._automatic_alignment = (key, result.moving_to_fixed_ras)
            self.alignment_status.SetLabel(_("Alignment reviewed and ready to import."))
        except Exception as error:
            with dlg.ErrorMessageBox(self, _("Error aligning MRI"), str(error)) as dialog:
                dialog.ShowModal()

    def GetValue(self):
        config = {}
        subject_path = self.subject.GetPath().strip()
        if subject_path:
            config["subject_dir"] = str(Path(subject_path).expanduser().resolve())
        for key, picker in self.files.items():
            if "subject_dir" in config and key in ("lh_surface", "rh_surface"):
                continue
            path = Path(picker.GetPath()).expanduser()
            if not picker.GetPath().strip() or not path.is_file():
                if key in ("lh_surface", "rh_surface"):
                    self.manual.Expand()
                    self._resize_dialog()
                picker.SetFocus()
                raise ValueError(_("Select an existing file for:") + " " + self.file_labels[key])
            config[key] = str(path.resolve())
        unit = self.unit.GetValue().strip()
        if not unit:
            raise ValueError(_("Enter the signal unit or label used by the reconstruction."))
        config["unit"] = unit
        mode = self.alignment_mode.GetSelection()
        if mode == 0:
            if self._automatic_alignment is None:
                self.advanced.Expand()
                self._resize_dialog()
                raise ValueError(
                    _("Calculate and review the automatic alignment before importing.")
                )
            key, matrix = self._automatic_alignment
            config["mri"] = str(self._reference_mri)
            if key != self._alignment_inputs()[3]:
                self._automatic_alignment = None
                self.alignment_status.SetLabel(
                    _("Calculate alignment again: the input images changed.")
                )
                raise ValueError(
                    _("The project or reference MRI changed. Calculate alignment again.")
                )
        elif mode == 1:
            matrix = np.eye(4)
        else:
            path = Path(self.registration.GetPath()).expanduser()
            if not self.registration.GetPath().strip() or not path.is_file():
                self.advanced.Expand()
                self._resize_dialog()
                self.registration.SetFocus()
                raise ValueError(_("Select a registration matrix."))
            matrix = np.loadtxt(path, delimiter="," if path.suffix.lower() == ".csv" else None)
        config["scanner_ras_to_project_ras"] = matrix.tolist()
        return config

    def OnImport(self, event):
        try:
            config = self.GetValue()
            try:
                with wx.BusyCursor():
                    Publisher.sendMessage("Load source reconstruction", config=config)
            except MissingSurfaceGeometryError:
                reference = self._select_reference_mri(
                    _("Surface metadata missing: select the matching FreeSurfer MRI")
                )
                if reference is None:
                    return
                config["mri"] = str(reference)
                with wx.BusyCursor():
                    Publisher.sendMessage("Load source reconstruction", config=config)
        except Exception as error:
            with dlg.ErrorMessageBox(
                self, _("Error importing EEG/MEG source reconstruction"), str(error)
            ) as dialog:
                dialog.ShowModal()
            return
        self.EndModal(wx.ID_OK)


class AlignmentPreviewDialog(wx.Dialog):
    def __init__(self, parent, result):
        super().__init__(
            parent,
            title=_("Review MRI alignment"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.result = result
        self.images = (result.fixed, result.aligned)
        self.limits = []
        for image in self.images:
            low, high = np.percentile(image[::4, ::4, ::4], [2, 98])
            if low == high:
                low, high = float(image.min()), float(image.max())
            self.limits.append((low, high))
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        description = wx.StaticText(
            self,
            label=_(
                "Project: red. Aligned MRI: cyan. Review the anatomy in all three views before using this alignment."
            ),
        )
        description.Wrap(760)
        main_sizer.Add(description, 0, wx.ALL, 10)
        views = wx.BoxSizer(wx.HORIZONTAL)
        self.bitmaps = []
        self.sliders = []
        for axis, title in enumerate((_("Axial"), _("Coronal"), _("Sagittal"))):
            column = wx.BoxSizer(wx.VERTICAL)
            column.Add(wx.StaticText(self, label=title), 0, wx.ALIGN_CENTER | wx.BOTTOM, 4)
            bitmap = wx.StaticBitmap(self, size=(240, 240))
            bitmap.SetMinSize((240, 240))
            bitmap.SetBackgroundColour(wx.BLACK)
            self.bitmaps.append(bitmap)
            column.Add(bitmap, 1, wx.ALIGN_CENTER)
            maximum = result.fixed.shape[axis] - 1
            slider = wx.Slider(
                self,
                value=maximum // 2,
                minValue=0,
                maxValue=maximum,
                style=wx.SL_HORIZONTAL | wx.SL_VALUE_LABEL,
            )
            slider.Bind(wx.EVT_SLIDER, self.OnSlice)
            self.sliders.append(slider)
            column.Add(slider, 0, wx.EXPAND | wx.TOP, 5)
            views.Add(column, 1, wx.EXPAND | wx.ALL, 8)
        main_sizer.Add(views, 1, wx.EXPAND)
        main_sizer.Add(wx.StaticText(self, label=_("Overlay (%)")), 0, wx.LEFT | wx.RIGHT, 10)
        self.opacity = wx.Slider(
            self, value=100, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL | wx.SL_VALUE_LABEL
        )
        self.opacity.Bind(wx.EVT_SLIDER, self.OnSlice)
        main_sizer.Add(self.opacity, 0, wx.EXPAND | wx.ALL, 10)
        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        self.FindWindow(wx.ID_OK).SetLabel(_("Use alignment"))
        main_sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(main_sizer)
        self.SetMinSize(self.GetSize())
        self.CenterOnParent()
        self.OnSlice(None)

    def OnSlice(self, event):
        spacing = self.result.spacing
        plane_spacings = (
            (spacing[1], spacing[0]),
            (spacing[2], spacing[0]),
            (spacing[2], spacing[1]),
        )
        opacity = self.opacity.GetValue() / 100.0
        for axis, bitmap in enumerate(self.bitmaps):
            index = self.sliders[axis].GetValue()
            planes = []
            for image, (low, high) in zip(self.images, self.limits):
                plane = np.flipud(np.take(image, index, axis=axis))
                planes.append(np.clip((plane - low) / (high - low), 0, 1))
            fixed, moving = planes
            rgb = np.empty((*fixed.shape, 3), dtype=np.uint8)
            rgb[..., 0] = fixed * 255
            rgb[..., 1] = rgb[..., 2] = ((1 - opacity) * fixed + opacity * moving) * 255
            height, width = fixed.shape
            sy, sx = plane_spacings[axis]
            scale = min(240 / (width * sx), 240 / (height * sy))
            image = wx.Image(width, height, np.ascontiguousarray(rgb).tobytes())
            image = image.Scale(
                max(1, round(width * sx * scale)),
                max(1, round(height * sy * scale)),
                wx.IMAGE_QUALITY_HIGH,
            )
            bitmap.SetBitmap(wx.Bitmap(image))
        self.Layout()
