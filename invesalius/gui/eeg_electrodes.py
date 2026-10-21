"""EEG electrode table and montage export controls."""

import os

import wx
import wx.lib.platebtn as pbtn

import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.data.eeg_montage import export_montage, get_export_paths
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class EEGElectrodePage(wx.Panel):
    """Data notebook page that presents the registered EEG electrodes."""

    def __init__(self, parent, eeg_electrodes, navigation_on=False):
        super().__init__(parent)
        self.eeg_electrodes = eeg_electrodes

        self.listctrl = EEGElectrodeListCtrl(
            self,
            eeg_electrodes,
            navigation_on=navigation_on,
        )
        self.buttonctrl = EEGElectrodeButtonControlPanel(self, eeg_electrodes, self.listctrl)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.listctrl, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.buttonctrl, 0, wx.EXPAND | wx.TOP, 2)
        self.SetSizer(sizer)
        self.RefreshElectrodes()

    def RefreshElectrodes(self):
        self.listctrl.RefreshElectrodes()
        self.buttonctrl.UpdateButtons()

    def SetNavigationStatus(self, navigation_on):
        self.listctrl.SetNavigationStatus(navigation_on)


class EEGElectrodeButtonControlPanel(wx.Panel):
    """Removal controls that apply only to EEG electrodes."""

    def __init__(self, parent, eeg_electrodes, listctrl):
        super().__init__(parent, pos=wx.Point(0, 50), size=wx.Size(256, 22))
        self.eeg_electrodes = eeg_electrodes
        self.listctrl = listctrl

        self.visible_bitmap = self._LoadBitmap("object_visible.png")
        self.invisible_bitmap = self._LoadBitmap("object_invisible.png")
        remove_bitmap = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_remove.png"), wx.BITMAP_TYPE_PNG
        )
        export_bitmap = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "surface_export_original_min.png"),
            wx.BITMAP_TYPE_PNG,
        )

        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        self.remove_button = pbtn.PlateButton(
            self, wx.ID_ANY, "", remove_bitmap, style=button_style, size=wx.Size(24, 20)
        )
        self.remove_button.SetToolTip(_("Delete selected EEG electrodes"))
        self.export_button = pbtn.PlateButton(
            self,
            wx.ID_ANY,
            "",
            export_bitmap,
            style=button_style,
            size=wx.Size(24, 20),
        )
        self.export_button.SetToolTip(_("Export EEG montage"))
        labels_bitmap = self._LoadBitmap("text_original.png")
        labels_pressed_bitmap = self._LoadBitmap("text_inverted_original.png")
        self.labels_button = wx.BitmapToggleButton(
            self,
            wx.ID_ANY,
            labels_bitmap,
            size=wx.Size(24, 20),
        )
        self.labels_button.SetBitmapPressed(labels_pressed_bitmap)
        self.labels_button.SetValue(self.eeg_electrodes.labels_visible)
        self.visibility_button = wx.BitmapButton(self, size=wx.Size(24, 20))

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.remove_button, 0, wx.GROW | wx.EXPAND | wx.LEFT)
        sizer.Add(self.export_button, 0, wx.GROW | wx.EXPAND | wx.LEFT, 2)
        sizer.Add(self.labels_button, 0, wx.GROW | wx.EXPAND | wx.LEFT, 2)
        sizer.AddStretchSpacer()
        sizer.Add(self.visibility_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        self.SetSizer(sizer)
        self.Fit()

        self.remove_button.Bind(wx.EVT_BUTTON, self.OnDeleteSelected)
        self.export_button.Bind(wx.EVT_BUTTON, self.OnExport)
        self.labels_button.Bind(wx.EVT_TOGGLEBUTTON, self.OnToggleLabels)
        self.visibility_button.Bind(wx.EVT_BUTTON, self.OnToggleVisibility)
        self.listctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSelectionChanged)
        self.listctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnSelectionChanged)

    def UpdateButtons(self):
        self.remove_button.Enable(self.listctrl.GetFirstSelected() != wx.NOT_FOUND)
        self.export_button.Enable(bool(self.eeg_electrodes.electrodes))
        self.labels_button.SetValue(self.eeg_electrodes.labels_visible)
        self._UpdateLabelsButtonTooltip()
        self.UpdateVisibilityButton()

    @staticmethod
    def _LoadBitmap(icon_name):
        image = wx.Image(os.path.join(inv_paths.ICON_DIR, icon_name))
        return wx.Bitmap(image.Scale(16, 16))

    def UpdateVisibilityButton(self):
        electrodes = self.eeg_electrodes.electrodes
        has_visible_electrodes = any(electrode.visible for electrode in electrodes)
        self.visibility_button.SetBitmap(
            self.visible_bitmap if has_visible_electrodes else self.invisible_bitmap
        )
        tooltip = (
            _("Hide all EEG electrodes") if has_visible_electrodes else _("Show all EEG electrodes")
        )
        self.visibility_button.SetToolTip(tooltip)
        self.visibility_button.Enable(bool(electrodes))

    def OnToggleVisibility(self, _evt):
        if any(electrode.visible for electrode in self.eeg_electrodes.electrodes):
            self.eeg_electrodes.set_all_visible(False)
        else:
            self.eeg_electrodes.set_all_visible(True)

    def OnToggleLabels(self, _evt):
        self.eeg_electrodes.set_labels_visible(self.labels_button.GetValue())
        self._UpdateLabelsButtonTooltip()

    def _UpdateLabelsButtonTooltip(self):
        tooltip = (
            _("Hide EEG electrode labels")
            if self.eeg_electrodes.labels_visible
            else _("Show EEG electrode labels")
        )
        self.labels_button.SetToolTip(tooltip)

    def OnSelectionChanged(self, evt):
        self.UpdateButtons()
        evt.Skip()

    def OnDeleteSelected(self, _evt):
        electrodes = self.listctrl.GetSelectedElectrodes()
        if not electrodes:
            return

        message = (
            _("Delete selected EEG electrode?")
            if len(electrodes) == 1
            else _("Delete the selected EEG electrodes ({count})?").format(count=len(electrodes))
        )
        result = dlg.ShowConfirmationDialog(msg=message)
        if result == wx.ID_OK:
            self.eeg_electrodes.remove_many(electrode.electrode_uuid for electrode in electrodes)

    def OnExport(self, _evt):
        session = ses.Session()
        export_selection = dlg.ShowEEGMontageExportDialog(
            self,
            default_directory=session.GetConfig("last_directory_eeg_montage", ""),
        )
        if export_selection is None:
            return

        output_path, export_format = export_selection
        output_directory, filename = os.path.split(output_path)
        try:
            existing_paths = [
                path
                for path in get_export_paths(
                    output_directory,
                    export_format,
                    filename,
                )
                if path.exists()
            ]
            if existing_paths:
                result = dlg.ShowConfirmationDialog(
                    msg=_("The montage export files already exist. Overwrite them?")
                )
                if result != wx.ID_OK:
                    return

            export_montage(
                self.eeg_electrodes.electrodes, output_directory, export_format, filename
            )
            session.SetConfig("last_directory_eeg_montage", output_directory)
            wx.MessageBox(
                _("EEG montage exported successfully."),
                _("Success"),
                wx.OK | wx.ICON_INFORMATION,
            )
        except (OSError, ValueError) as error:
            wx.MessageBox(str(error), _("Export error"), wx.OK | wx.ICON_ERROR)


class EEGElectrodeListCtrl(wx.ListCtrl):
    """EEG electrode table with a clickable visibility column."""

    def __init__(self, parent, eeg_electrodes, navigation_on=False):
        super().__init__(parent, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.eeg_electrodes = eeg_electrodes
        self.electrode_uuids = []
        self.navigation_on = bool(navigation_on)
        self.highlighted_electrode_uuid = None
        self._refreshing = False

        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER, width=25)
        self.InsertColumn(1, _("ID"), width=50)
        self.InsertColumn(2, _("X (mm)"), width=85)
        self.InsertColumn(3, _("Y (mm)"), width=85)
        self.InsertColumn(4, _("Z (mm)"), width=85)

        self.visibility_images = wx.ImageList(16, 16)
        for icon_name in ("object_invisible.png", "object_visible.png"):
            image = wx.Image(os.path.join(inv_paths.ICON_DIR, icon_name))
            self.visibility_images.Add(wx.Bitmap(image.Scale(16, 16)))
        self.SetImageList(self.visibility_images, wx.IMAGE_LIST_SMALL)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected)

    def OnLeftDown(self, evt):
        row, _flags = self.HitTest(evt.GetPosition())
        if row != wx.NOT_FOUND and evt.GetPosition()[0] <= self.GetColumnWidth(0):
            electrode = self._GetElectrode(row)
            if electrode is not None:
                self.eeg_electrodes.set_visible(electrode.electrode_uuid, not electrode.visible)
            return
        evt.Skip()

    def RefreshElectrodes(self):
        selected_uuids = {electrode.electrode_uuid for electrode in self.GetSelectedElectrodes()}
        focused_row = self.GetFocusedItem()
        focused_uuid = (
            self.electrode_uuids[focused_row]
            if 0 <= focused_row < len(self.electrode_uuids)
            else None
        )
        self._refreshing = True
        self.Freeze()
        try:
            self.DeleteAllItems()
            self.electrode_uuids = []

            for electrode in self.eeg_electrodes.electrodes:
                self.electrode_uuids.append(electrode.electrode_uuid)
                row = self.InsertItem(self.GetItemCount(), "", int(electrode.visible))
                self.SetItem(row, 1, electrode.label)

                for column, coordinate in enumerate(electrode.position, start=2):
                    self.SetItem(row, column, f"{coordinate:.2f}")
                if electrode.electrode_uuid in selected_uuids:
                    self.Select(row)
                if electrode.electrode_uuid == focused_uuid:
                    self.Focus(row)
        finally:
            self._refreshing = False
            self.Thaw()
        if self.highlighted_electrode_uuid not in self.electrode_uuids:
            self._ClearHighlight()

    def OnKeyDown(self, evt):
        if evt.CmdDown() and evt.GetKeyCode() == ord("A"):
            self.SetItemState(-1, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            return
        evt.Skip()

    def _GetElectrode(self, row):
        if not 0 <= row < len(self.electrode_uuids):
            return None
        return self.eeg_electrodes.get(self.electrode_uuids[row])

    def GetSelectedElectrodes(self):
        electrodes = []
        row = self.GetFirstSelected()
        while row != wx.NOT_FOUND:
            electrode = self._GetElectrode(row)
            if electrode is not None:
                electrodes.append(electrode)
            row = self.GetNextSelected(row)
        return electrodes

    def SelectElectrode(self, electrode_uuid):
        if electrode_uuid not in self.electrode_uuids:
            return
        row = self.electrode_uuids.index(electrode_uuid)
        self.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
        self.Focus(row)
        self.Select(row)
        self.EnsureVisible(row)

    def SetNavigationStatus(self, navigation_on):
        self.navigation_on = bool(navigation_on)
        if self.navigation_on:
            self._ClearHighlight()

    def OnItemSelected(self, evt):
        if not self._refreshing and not self.navigation_on:
            electrode = self._GetElectrode(evt.GetIndex())
            if electrode is not None:
                Publisher.sendMessage(
                    "Highlight EEG electrode", electrode_uuid=electrode.electrode_uuid
                )
                self.highlighted_electrode_uuid = electrode.electrode_uuid
        evt.Skip()

    def OnItemDeselected(self, evt):
        if self._refreshing:
            evt.Skip()
            return
        electrode = self._GetElectrode(evt.GetIndex())
        if electrode is not None and electrode.electrode_uuid == self.highlighted_electrode_uuid:
            self._ClearHighlight()
        evt.Skip()

    def _ClearHighlight(self):
        if self.highlighted_electrode_uuid is None:
            return
        Publisher.sendMessage("Unhighlight EEG electrode")
        self.highlighted_electrode_uuid = None
