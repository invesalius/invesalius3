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
from invesalius.data.imagedata_utils import register_image_to_volume
from invesalius.data.source_reconstruction import (
    MissingSurfaceGeometryError,
    SourceImportRequired,
    discover_freesurfer_surfaces,
    discover_subject_files,
)
from invesalius.data.visualization.surface_painting import SurfacePainting
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.reader.others_reader import read_image


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
            "mid": _("Mid"),
            "inflated": _("Inflated"),
            "surface": _("Surface"),
        }
        self._representations = ("pial",)
        self.representation = wx.Choice(self, choices=[self._representation_labels["pial"]])
        self.representation.SetSelection(0)
        self.representation.SetToolTip(
            _("Select EEG/MEG color mapping on Brain to change its cortical representation.")
        )
        self.representation.Bind(wx.EVT_CHOICE, self.OnDisplayChanged)
        display_row.Add(self.representation, 1, wx.EXPAND)
        self.left = wx.CheckBox(self, label=_("Left"))
        self.right = wx.CheckBox(self, label=_("Right"))
        for checkbox in (self.left, self.right):
            checkbox.SetValue(True)
            checkbox.Bind(wx.EVT_CHECKBOX, self.OnDisplayChanged)
            display_row.Add(checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        sizer.Add(display_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)
        unit_row = wx.BoxSizer(wx.HORIZONTAL)
        unit_row.Add(
            wx.StaticText(self, label=_("Unit:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6
        )
        self.signal_unit = wx.ComboBox(self, choices=["a.u."], style=wx.CB_READONLY)
        self.signal_unit.SetName(_("Imported signal unit"))
        self.signal_unit.SetToolTip(
            _(
                "Unit of the imported samples (1 = dimensionless). Changing it corrects their interpretation without modifying the samples."
            )
        )
        self.display_unit = wx.Choice(self, choices=["a.u."])
        self.display_unit.SetName(_("Display unit"))
        self.display_unit.SetToolTip(_("Convert the displayed values to a compatible unit."))
        unit_row.Add(self.signal_unit, 1)
        unit_row.Add(
            wx.StaticText(self, label="→"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5
        )
        unit_row.Add(self.display_unit, 1)
        for control in (self.signal_unit, self.display_unit):
            control.Bind(
                wx.EVT_COMBOBOX if control is self.signal_unit else wx.EVT_CHOICE,
                self.OnSignalDisplayChanged,
            )
        self.scale = wx.Choice(self, choices=[_("Auto scale"), _("Original scale")])
        self.scale.SetToolTip(
            _("Use one display multiplier for the entire series. Imported values are preserved.")
        )
        self.scale.Bind(wx.EVT_CHOICE, self.OnSignalDisplayChanged)
        unit_row.Add(self.scale, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        sizer.Add(unit_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 7)
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
        for control in (self.display_label, self.representation):
            if control.IsEnabled() != active:
                control.Enable(active)
        hemispheres = active and mode.series.has_hemispheres
        for control in (self.left, self.right):
            if control.IsEnabled() != hemispheres:
                control.Enable(hemispheres)
        series = mode.series if loaded else None
        for control, choices, selected in (
            (
                self.signal_unit,
                series.unit_choices if loaded else ("a.u.",),
                (series.source_unit or series.unit) if loaded else "a.u.",
            ),
            (
                self.display_unit,
                series.display_units if loaded else ("a.u.",),
                series.display_unit if loaded else "a.u.",
            ),
        ):
            if tuple(control.GetItems()) != choices:
                control.SetItems(list(choices))
            if control.GetStringSelection() != selected:
                control.SetStringSelection(selected)
            control.Enable(loaded)
        self.scale.Enable(loaded)
        self.scale.SetSelection(0 if not loaded or series.automatic_scale else 1)

    def OnSignalDisplayChanged(self, event):
        if self._mode is None or self._mode.series is None:
            return
        unit = self.signal_unit.GetStringSelection()
        display_unit = (
            unit
            if event.GetEventObject() is self.signal_unit
            else self.display_unit.GetStringSelection()
        )
        try:
            Publisher.sendMessage(
                "Set source reconstruction signal display",
                unit=unit,
                display_unit=display_unit,
                automatic_scale=self.scale.GetSelection() == 0,
            )
        except ValueError as error:
            with dlg.ErrorMessageBox(
                wx.GetApp().GetTopWindow(), _("Error changing signal units"), str(error)
            ) as dialog:
                dialog.ShowModal()
        finally:
            self._sync_display_controls()

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
        self.file_labels = {"signal": _("Source signal:")}
        form = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        form.AddGrowableCol(1)
        form.Add(wx.StaticText(self, label=self.file_labels["signal"]), 0, wx.ALIGN_CENTER_VERTICAL)
        signal_row = wx.BoxSizer(wx.HORIZONTAL)
        self.files["signal"] = wx.FilePickerCtrl(
            self,
            message=_("Select an STC, MNE H5, or Brainstorm/FieldTrip MAT source file"),
            wildcard=_("Source reconstruction (*.stc;*.h5;*.mat)|*.stc;*.h5;*.mat"),
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL | wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST,
        )
        self.files["signal"].SetToolTip(
            _(
                "Format is detected automatically. STC files require the matching hemisphere in the same directory."
            )
        )
        signal_row.Add(self.files["signal"], 1, wx.EXPAND)
        form.Add(signal_row, 1, wx.EXPAND)
        form.Add(wx.StaticText(self, label=_("Subject:")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.subject = wx.DirPickerCtrl(
            self,
            message=_("Select a FreeSurfer/FastSurfer, Workbench or Brainstorm subject folder"),
            style=wx.DIRP_USE_TEXTCTRL | wx.DIRP_SMALL | wx.DIRP_DIR_MUST_EXIST,
        )
        self.subject.SetToolTip(
            _(
                "STC/MNE H5 use FreeSurfer surfaces. FieldTrip MAT can use matching Workbench midthickness, pial and white surfaces. Brainstorm MAT can use a Brainstorm anatomy folder."
            )
        )
        form.Add(self.subject, 1, wx.EXPAND)
        main_sizer.Add(form, 0, wx.EXPAND | wx.ALL, 12)

        detected = wx.StaticBoxSizer(wx.VERTICAL, self, _("Detected files"))
        self.detected = detected
        self.subject_table = wx.FlexGridSizer(cols=3, vgap=6, hgap=24)
        self.subject_table.AddGrowableCol(0)
        self._build_subject_table(brainstorm=False)
        detected.Add(self.subject_table, 0, wx.EXPAND | wx.ALL, 10)
        main_sizer.Add(detected, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.subject_summary = wx.StaticText(
            self,
            label=_(
                "Select a FreeSurfer/FastSurfer, Workbench or Brainstorm subject folder, or use the mesh associated with the source MAT file."
            ),
        )
        self.subject_summary.Wrap(self.FromDIP(620))
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

    def _build_subject_table(self, brainstorm):
        table = self.subject_table
        table.Clear(delete_windows=True)
        self._subject_table_brainstorm = brainstorm
        sides = ("combined",) if brainstorm else ("lh", "rh")
        titles = (_("Surface"), _("Files")) if brainstorm else (_("Surface"), _("Left"), _("Right"))
        rows = (
            (
                ("cortex", _("Cortex (default)")),
                ("pial", _("Pial")),
                ("white", _("White")),
                ("mid", _("Mid")),
                ("inflated", _("Inflated")),
            )
            if brainstorm
            else (
                ("mid", _("Mid")),
                ("pial", _("Pial")),
                ("white", _("White")),
                ("inflated", _("Inflated")),
                ("curv", _("Curvature")),
            )
        )
        table.SetCols(len(titles))
        parent = self.detected.GetStaticBox()
        for title in titles:
            heading = wx.StaticText(parent, label=title)
            heading.SetFont(heading.GetFont().Bold())
            table.Add(heading, 0, wx.ALIGN_CENTER_VERTICAL)
        self.subject_cells = {}
        for kind, label in rows:
            table.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            for side in sides:
                cell = wx.StaticText(parent, label="\u2014")
                cell.SetMinSize(self.FromDIP((72, -1)))
                cell.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
                self.subject_cells[kind, side] = cell
                table.Add(cell, 0, wx.ALIGN_CENTER_VERTICAL)

    def _show_subject_files(self, files, message):
        anatomy = files.get("brainstorm")
        if self._subject_table_brainstorm != (anatomy is not None):
            self._build_subject_table(brainstorm=anatomy is not None)
        absent = _("Missing") if self.subject.GetPath().strip() else "\u2014"
        for (kind, side), cell in self.subject_cells.items():
            available = files.get(kind, {})
            paths = list(available.values()) if side == "combined" else [available.get(side)]
            if side != "combined":
                code = {"lh": "L", "rh": "R"}[side]
                paths.extend(
                    path
                    for path in files.get("workbench", {}).get(kind, {}).values()
                    if f".{code}." in path.name
                )
            paths = [path for path in paths if path is not None]
            label = _("Found") if paths else absent
            if len(paths) > 1:
                label += f" ({len(paths)})"
            cell.SetLabel(label)
            cell.SetToolTip("\n".join(str(path) for path in paths))
            cell.SetForegroundColour(
                wx.SystemSettings.GetColour(
                    wx.SYS_COLOUR_WINDOWTEXT if paths else wx.SYS_COLOUR_GRAYTEXT
                )
            )
        self.subject_summary.SetLabel(message)
        self.subject_summary.SetToolTip(
            "\n".join(str(path) for path in anatomy.values()) if anatomy is not None else ""
        )
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
                if "brainstorm" in files:
                    anatomy = files["brainstorm"]
                    message = (
                        f"{_('Brainstorm default cortex:')} {anatomy['surface_file'].name}\n"
                        f"{_('Coordinates (MRI metadata only):')} {anatomy['brainstorm_mri'].name}"
                    )
                else:
                    for side, path in files["pial"].items():
                        self.files[f"{side}_surface"].SetPath(str(path))
                    missing = [f"{side}.pial" for side in ("lh", "rh") if side not in files["pial"]]
                    if "workbench" in files:
                        message = _(
                            "FieldTrip can use the matching Workbench surfaces. STC/MNE H5 use native FreeSurfer surfaces."
                        )
                    elif missing:
                        message = _("Required files not found:") + " " + ", ".join(missing)
                    else:
                        message = _(
                            "Uses surface coordinates in the current anatomy. Pial is used for visualization."
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
                discover_freesurfer_surfaces(pial),
                _("Uses surface coordinates in the current anatomy."),
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
                    moving_image = read_image(path)
                    outcome.put(
                        register_image_to_volume(
                            moving_image.dataobj, moving_image.affine, data, affine, cancelled
                        )
                    )
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
            matrix, fixed, aligned, spacing = result
            if key != self._alignment_inputs()[3]:
                raise ValueError(
                    _("The project or reference MRI changed. Calculate alignment again.")
                )
            with AlignmentPreviewDialog(
                wx.GetApp().GetTopWindow(), fixed, aligned, spacing
            ) as preview:
                if preview.ShowModal() != wx.ID_OK:
                    return
            self._automatic_alignment = (key, matrix)
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
            if key in ("lh_surface", "rh_surface") and not picker.GetPath().strip():
                continue
            path = Path(picker.GetPath()).expanduser()
            if not picker.GetPath().strip() or not path.is_file():
                if key in ("lh_surface", "rh_surface"):
                    self.manual.Expand()
                    self._resize_dialog()
                picker.SetFocus()
                raise ValueError(_("Select an existing file for:") + " " + self.file_labels[key])
            config[key] = str(path.resolve())
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
            while True:
                try:
                    with wx.BusyCursor():
                        Publisher.sendMessage("Load source reconstruction", config=config)
                    break
                except SourceImportRequired as request:
                    parent = wx.GetApp().GetTopWindow()
                    if request.choices:
                        with wx.SingleChoiceDialog(
                            parent, str(request), _("Source reconstruction"), list(request.choices)
                        ) as dialog:
                            if dialog.ShowModal() != wx.ID_OK:
                                return
                            config[request.key] = dialog.GetStringSelection()
                    else:
                        matrix = request.key == "source_to_scanner_ras"
                        wildcard = _("MATLAB files (*.mat)|*.mat")
                        if matrix:
                            wildcard = _("Text matrix (*.txt;*.csv)|*.txt;*.csv")
                        elif request.key in ("lh_surface", "rh_surface"):
                            wildcard = _("All files (*.*)|*.*")
                        with wx.FileDialog(
                            parent,
                            message=str(request),
                            wildcard=wildcard,
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
                        ) as dialog:
                            if dialog.ShowModal() != wx.ID_OK:
                                return
                            path = Path(dialog.GetPath()).resolve()
                        config[request.key] = (
                            np.loadtxt(
                                path, delimiter="," if path.suffix.lower() == ".csv" else None
                            ).tolist()
                            if matrix
                            else str(path)
                        )
                except MissingSurfaceGeometryError:
                    reference = self._select_reference_mri(
                        _("Surface metadata missing: select the matching FreeSurfer MRI")
                    )
                    if reference is None:
                        return
                    config["mri"] = str(reference)
        except Exception as error:
            with dlg.ErrorMessageBox(
                self, _("Error importing EEG/MEG source reconstruction"), str(error)
            ) as dialog:
                dialog.ShowModal()
            return
        self.EndModal(wx.ID_OK)


class AlignmentPreviewDialog(wx.Dialog):
    def __init__(self, parent, fixed, aligned, spacing):
        super().__init__(
            parent,
            title=_("Review MRI alignment"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.spacing = spacing
        self.images = (fixed, aligned)
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
            maximum = fixed.shape[axis] - 1
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
        spacing = self.spacing
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
