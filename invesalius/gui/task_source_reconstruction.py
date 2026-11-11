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

"""Import cortical source reconstructions and control their surface display.

Collect source files, anatomy and optional MRI alignment, requesting missing inputs
as readers report them. Send display changes to the EEG/MEG painting mode through
pubsub and reflect its current state in the task panel.
"""

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
from invesalius.data.visualization.surface_painting_visualizer import SurfacePainting
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.reader.others_reader import read_image


class TaskPanel(wx.Panel):
    """Expose import, cortical representation, hemisphere and signal-unit controls.

    Follow the registered EEG/MEG mode's availability and display state so these
    controls operate on the same reconstruction shown on the Brain surface.
    """

    def __init__(self, parent):
        super().__init__(parent)

        button = wx.Button(self, label=_("Manage source reconstructions..."))
        button.SetToolTip(_("Add or remove EEG/MEG cortical source reconstructions."))
        button.Bind(wx.EVT_BUTTON, self.OnImport)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(button, 0, wx.ALL | wx.EXPAND, 7)
        display_row = wx.BoxSizer(wx.HORIZONTAL)
        self.display_label = wx.StaticText(self, label=_("Display:"))
        display_row.Add(self.display_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self._representation_labels = {
            "pial": _("Pial"),
            "white": _("White"),
            "mid": _("Midthickness"),
            "inflated": _("Inflated"),
            "surface": _("Surface"),
        }
        self._representations = ("surface",)
        self.representation = wx.Choice(self, choices=[self._representation_labels["surface"]])
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
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        self._import_settings = {}
        self._mode = SurfacePainting().modes.get("EEG/MEG")
        self._sync_display_controls()

    def OnImport(self, event):
        with ImportSourceDialog(wx.GetApp().GetTopWindow(), self._import_settings) as dialog:
            dialog.ShowModal()

    def OnCloseProject(self):
        self._import_settings.clear()

    def OnSourceChanged(self, mode):
        self._mode = mode
        self._sync_display_controls()

    def _sync_display_controls(self):
        mode = self._mode
        loaded = mode is not None and mode.series is not None
        representations = mode.series.representations if loaded else ("surface",)
        if representations != self._representations:
            self._representations = representations
            self.representation.SetItems(
                [self._representation_labels[key] for key in representations]
            )
        selected = representations.index(mode.representation if loaded else "surface")
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
    """Collect and validate the files and transforms needed to import a reconstruction.

    Add source files using shared anatomy and alignment, and remove loaded data sets.
    Request missing reader inputs separately for each file, keeping successful imports
    when a later file fails or is cancelled.
    """

    def __init__(self, parent, settings=None):
        super().__init__(
            parent,
            title=_("EEG/MEG source reconstructions"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._automatic_alignment = None
        self._reference_mri = None
        self._mode = SurfacePainting().modes.get("EEG/MEG")
        self._settings = settings if settings is not None else {}
        self._shared_files = {}
        self.pending_files = []
        self._source_rows = ()
        self.files = {}
        self.file_labels = {}
        source_header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, label=_("Reconstructions"))
        title.SetFont(title.GetFont().Bold())
        source_header.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        source_header.AddStretchSpacer()
        add_signal = wx.Button(self, label=_("Add files..."))
        add_signal.Bind(wx.EVT_BUTTON, self.OnAddSignals)
        source_header.Add(add_signal, 0, wx.RIGHT, 6)
        self.remove_source = wx.Button(self, label=_("Remove"))
        self.remove_source.SetName(_("Remove selected reconstruction"))
        self.remove_source.Enable(False)
        self.remove_source.Bind(wx.EVT_BUTTON, self.OnRemoveSource)
        source_header.Add(self.remove_source, 0)
        main_sizer.Add(source_header, 0, wx.EXPAND | wx.ALL, 12)
        self.reconstruction_list = wx.ListCtrl(
            self, size=(350, 90), style=wx.LC_REPORT | wx.LC_SINGLE_SEL
        )
        self.reconstruction_list.SetName(_("Reconstructions"))
        self.reconstruction_list.InsertColumn(0, _("Name"))
        self.reconstruction_list.InsertColumn(1, _("Status"), width=self.FromDIP(120))
        self.reconstruction_list.Bind(wx.EVT_SIZE, self.OnSourcesSize)
        self.reconstruction_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSourceSelected)
        self.reconstruction_list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnSourceSelected)
        main_sizer.Add(self.reconstruction_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        surface_title = wx.StaticText(self, label=_("Surfaces"))
        surface_title.SetFont(surface_title.GetFont().Bold())
        main_sizer.Add(surface_title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        form = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        form.AddGrowableCol(1)
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
        main_sizer.Add(form, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.detected = wx.CollapsiblePane(
            self,
            label=_("Detected surfaces"),
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE,
        )
        self.subject_table = wx.FlexGridSizer(cols=3, vgap=4, hgap=24)
        self.subject_table.AddGrowableCol(0)
        self._build_subject_table(brainstorm=False)
        detected_sizer = wx.BoxSizer(wx.VERTICAL)
        detected_sizer.Add(self.subject_table, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 8)
        self.detected.GetPane().SetSizer(detected_sizer)
        self.detected.Collapse()
        self.subject_summary = wx.StaticText(
            self,
            label=_("Select the subject folder, or use the surface included in the source file."),
        )
        self.subject_summary.Wrap(self.FromDIP(620))
        self.subject_summary.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        )
        main_sizer.Add(self.subject_summary, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        main_sizer.Add(self.detected, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

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
        self.FindWindow(wx.ID_OK).Enable(False)
        self.FindWindow(wx.ID_CANCEL).SetLabel(_("Close"))
        main_sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.Bind(wx.EVT_BUTTON, self.OnImport, id=wx.ID_OK)
        self.SetSizer(main_sizer)
        self.SetMinSize(self.FromDIP((680, -1)))
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.CenterOnParent()
        self._restore_import_settings()
        self.subject.Bind(wx.EVT_DIRPICKER_CHANGED, self.OnSubjectChanged)
        self.subject.GetTextCtrl().Bind(wx.EVT_TEXT, self.OnSubjectChanged)
        for key in ("lh_surface", "rh_surface"):
            self.files[key].Bind(wx.EVT_FILEPICKER_CHANGED, self.OnManualSurfaceChanged)
            self.files[key].GetTextCtrl().Bind(wx.EVT_TEXT, self.OnManualSurfaceChanged)
        self.detected.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnLayoutChanged)
        self.manual.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnLayoutChanged)
        self.advanced.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnLayoutChanged)
        Publisher.subscribe(self.OnReconstructionsChanged, "Source reconstruction changed")
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
        self._sync_reconstructions()

    def _restore_import_settings(self):
        if not self._settings:
            return
        self.subject.SetPath(self._settings["subject"])
        for key, path in self._settings["surfaces"].items():
            self.files[key].SetPath(path)
        if self.subject.GetPath().strip():
            self.OnSubjectChanged()
        else:
            self.OnManualSurfaceChanged()
        self._reference_mri = self._settings["reference_mri"]
        self._automatic_alignment = self._settings["automatic_alignment"]
        self.registration.SetPath(self._settings["registration"])
        self.alignment_mode.SetSelection(self._settings["alignment_mode"])
        self._shared_files.update(self._settings["shared_files"])
        self.OnRegistrationMode(None)

    def _save_import_settings(self, config):
        for key in ("fieldtrip_surface", "mri"):
            if key in config:
                self._shared_files[key] = config[key]
        self._settings.update(
            subject=self.subject.GetPath(),
            surfaces={key: picker.GetPath() for key, picker in self.files.items()},
            reference_mri=self._reference_mri,
            automatic_alignment=self._automatic_alignment,
            registration=self.registration.GetPath(),
            alignment_mode=self.alignment_mode.GetSelection(),
            shared_files=self._shared_files.copy(),
        )

    def OnAddSignals(self, event):
        with wx.FileDialog(
            self,
            message=_("Select source reconstruction files"),
            wildcard=_("Source reconstruction (*.stc;*.h5;*.mat)|*.stc;*.h5;*.mat"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            for filename in dialog.GetPaths():
                path = Path(filename)
                # An STC hemisphere pair is one reconstruction.
                if path.name.endswith("-rh.stc"):
                    path = path.with_name(path.name[:-7] + "-lh.stc")
                if str(path) not in self.pending_files:
                    self.pending_files.append(str(path))
        self._sync_reconstructions()

    def OnSourcesSize(self, event):
        event.Skip()
        width = self.reconstruction_list.GetClientSize().width - self.FromDIP(122)
        self.reconstruction_list.SetColumnWidth(0, max(self.FromDIP(120), width))

    def OnSourceSelected(self, event=None):
        index = self.reconstruction_list.GetFirstSelected()
        self.remove_source.Enable(index != wx.NOT_FOUND)
        loaded_count = len(self._mode.reconstructions) if self._mode is not None else 0
        pending_index = index - loaded_count
        tooltip = (
            self.pending_files[pending_index]
            if 0 <= pending_index < len(self.pending_files)
            else ""
        )
        self.reconstruction_list.SetToolTip(tooltip)

    def OnReconstructionsChanged(self, mode):
        self._mode = mode
        self._sync_reconstructions()

    def _sync_reconstructions(self):
        loaded = self._mode.reconstructions if self._mode is not None else ()
        rows = tuple((series.name, _("Imported")) for series in loaded) + tuple(
            (Path(filename).name, _("To import")) for filename in self.pending_files
        )
        if rows != self._source_rows:
            selection = self.reconstruction_list.GetFirstSelected()
            self._source_rows = rows
            self.reconstruction_list.DeleteAllItems()
            for index, (name, status) in enumerate(rows):
                self.reconstruction_list.InsertItem(index, name)
                self.reconstruction_list.SetItem(index, 1, status)
            if rows and selection != wx.NOT_FOUND:
                self.reconstruction_list.Select(min(selection, len(rows) - 1))
        self.OnSourceSelected()
        self.FindWindow(wx.ID_OK).Enable(bool(self.pending_files))

    def OnRemoveSource(self, event):
        index = self.reconstruction_list.GetFirstSelected()
        if index == wx.NOT_FOUND:
            return
        try:
            loaded_count = len(self._mode.reconstructions) if self._mode is not None else 0
            if index < loaded_count:
                self._mode.remove_reconstruction(index)
            else:
                self.pending_files.pop(index - loaded_count)
            self._sync_reconstructions()
        except Exception as error:
            with dlg.ErrorMessageBox(
                self, _("Error removing reconstruction"), str(error)
            ) as dialog:
                dialog.ShowModal()

    def OnDestroy(self, event):
        if event.GetEventObject() is self:
            Publisher.unsubscribe_owner(self)
        event.Skip()

    def _resize_dialog(self):
        for section in (self.detected, self.manual, self.advanced):
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
        rows = [
            ("pial", _("Pial")),
            ("white", _("White")),
            ("mid", _("Midthickness")),
            ("inflated", _("Inflated")),
        ]
        if brainstorm:
            rows.insert(0, ("cortex", _("Cortex (default)")))
        else:
            rows.append(("curv", _("Curvature")))
        table.SetCols(len(titles))
        parent = self.detected.GetPane()
        for title in titles:
            heading = wx.StaticText(parent, label=title)
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

    def OnSubjectChanged(self, event=None):
        self._shared_files.clear()
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
            self._show_subject_files({}, _("Use the source mesh or select surfaces manually."))
        else:
            try:
                files = discover_subject_files(subject_path)
                if "brainstorm" in files:
                    message = _("Brainstorm anatomy detected.")
                else:
                    for side, path in files["pial"].items():
                        self.files[f"{side}_surface"].SetPath(str(path))
                    missing = [f"{side}.pial" for side in ("lh", "rh") if side not in files["pial"]]
                    if "workbench" in files:
                        message = _("Workbench anatomy detected.")
                    elif missing:
                        message = _("Required files not found:") + " " + ", ".join(missing)
                    else:
                        message = _("Pial surfaces found.")
                self._show_subject_files(files, message)
            except (OSError, ValueError) as error:
                self._show_subject_files({}, str(error))
        if event is not None:
            event.Skip()

    def OnManualSurfaceChanged(self, event=None):
        if not self.subject.GetPath().strip():
            self._shared_files.clear()
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
                _("Using manually selected surfaces."),
            )
        if event is not None:
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
            with AlignmentPreviewDialog(self, fixed, aligned, spacing) as preview:
                if preview.ShowModal() != wx.ID_OK:
                    return
            self._automatic_alignment = (key, matrix)
            self.alignment_status.SetLabel(_("Alignment reviewed and ready to import."))
        except Exception as error:
            with dlg.ErrorMessageBox(self, _("Error aligning MRI"), str(error)) as dialog:
                dialog.ShowModal()

    def GetValue(self):
        if not self.pending_files:
            raise ValueError(_("Select at least one source reconstruction file."))
        for filename in self.pending_files:
            if not Path(filename).is_file():
                raise ValueError(_("Source file not found:") + " " + filename)
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
            for signal in self.pending_files[:]:
                if not self._import_signal(dict(config, signal=signal)):
                    return
                self.pending_files.pop(0)
                self._sync_reconstructions()
        except Exception as error:
            with dlg.ErrorMessageBox(
                self, _("Error importing EEG/MEG source reconstruction"), str(error)
            ) as dialog:
                dialog.ShowModal()
            return
        self.EndModal(wx.ID_OK)
        Publisher.sendMessage("Maximize volume viewer")

    def _import_signal(self, config):
        reused_surface = None
        for key, path in self._shared_files.items():
            if key not in config and Path(path).is_file():
                config[key] = path
                if key == "fieldtrip_surface" and not config.get("surface_file"):
                    reused_surface = path
        while True:
            try:
                with wx.BusyCursor():
                    Publisher.sendMessage("Load source reconstruction", config=config)
                self._save_import_settings(config)
                return True
            except SourceImportRequired as request:
                if request.choices:
                    with wx.SingleChoiceDialog(
                        self, str(request), _("Source reconstruction"), list(request.choices)
                    ) as dialog:
                        if dialog.ShowModal() != wx.ID_OK:
                            return False
                        config[request.key] = dialog.GetStringSelection()
                else:
                    matrix = request.key == "source_to_scanner_ras"
                    wildcard = _("MATLAB files (*.mat)|*.mat")
                    if matrix:
                        wildcard = _("Text matrix (*.txt;*.csv)|*.txt;*.csv")
                    elif request.key in ("lh_surface", "rh_surface"):
                        wildcard = _("All files (*.*)|*.*")
                    with wx.FileDialog(
                        self,
                        message=str(request),
                        wildcard=wildcard,
                        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
                    ) as dialog:
                        if dialog.ShowModal() != wx.ID_OK:
                            return False
                        path = Path(dialog.GetPath()).resolve()
                    config[request.key] = (
                        np.loadtxt(
                            path, delimiter="," if path.suffix.lower() == ".csv" else None
                        ).tolist()
                        if matrix
                        else str(path)
                    )
                    if request.key == "fieldtrip_surface":
                        reused_surface = None
            except MissingSurfaceGeometryError:
                reference = self._select_reference_mri(
                    _("Surface metadata missing: select the matching FreeSurfer MRI")
                )
                if reference is None:
                    return False
                config["mri"] = str(reference)
            except ValueError:
                if reused_surface is None:
                    raise
                # A cached FieldTrip mesh must still match the new source positions.
                config.pop("fieldtrip_surface", None)
                reused_surface = None


class AlignmentPreviewDialog(wx.Dialog):
    """Preview the reference MRI against the project before accepting registration.

    Overlay orthogonal slices of the fixed and aligned volumes so the user can
    inspect the calculated transform before it is used for source geometry.
    """

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
