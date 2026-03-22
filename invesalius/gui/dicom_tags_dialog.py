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

import csv

import wx

from invesalius.i18n import tr as _


class DicomTagsDialog(wx.Dialog):
    """
    Dialog to display all DICOM tags from the currently loaded image.
    Shows Tag, Name, and Value in a searchable list with export capabilities.
    """

    def __init__(self, parent, data_image, tag_labels):
        """
        Initialize the DICOM Tags dialog.

        Args:
            parent: Parent window
            data_image: Dictionary containing DICOM tags in format data_image[group][element]
            tag_labels: Dictionary mapping tag strings to tag names
        """
        super().__init__(
            id=-1,
            name="",
            parent=parent,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            title=_("DICOM Tags Information"),
            size=(800, 600),
        )
        self.Center(wx.BOTH)

        self.data_image = data_image
        self.tag_labels = tag_labels
        self.all_tags = []

        self._init_gui()
        self._populate_tags()

    def _init_gui(self):
        """Initialize the GUI components."""
        panel = wx.Panel(self)

        # Search box
        search_label = wx.StaticText(panel, -1, _("Search:"))
        self.search_ctrl = wx.SearchCtrl(panel, -1, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowCancelButton(True)
        self.search_ctrl.SetDescriptiveText(_("Filter tags..."))

        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        search_sizer.Add(self.search_ctrl, 1, wx.EXPAND)

        # List control for tags
        self.list_ctrl = wx.ListCtrl(
            panel, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES
        )

        # Add columns
        self.list_ctrl.InsertColumn(0, _("Tag"), width=120)
        self.list_ctrl.InsertColumn(1, _("Name"), width=300)
        self.list_ctrl.InsertColumn(2, _("Value"), width=350)

        # Buttons
        btn_export = wx.Button(panel, -1, _("Export to CSV..."))
        btn_close = wx.Button(panel, wx.ID_CLOSE, _("Close"))

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(btn_export, 0, wx.RIGHT, 5)
        button_sizer.AddStretchSpacer()
        button_sizer.Add(btn_close, 0)

        # Main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 10)
        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(main_sizer)

        # Layout
        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)

        # Bind events
        self.search_ctrl.Bind(wx.EVT_TEXT, self._on_search)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        btn_export.Bind(wx.EVT_BUTTON, self._on_export)
        btn_close.Bind(wx.EVT_BUTTON, self._on_close)

    def _populate_tags(self):
        """Populate the list with all DICOM tags from data_image."""
        self.all_tags = []

        # Skip the 'invesalius' and 'spacing' special keys
        skip_keys = {"invesalius", "spacing"}

        # Iterate through all groups and elements
        for group_key in sorted(self.data_image.keys()):
            if group_key in skip_keys:
                continue

            group_dict = self.data_image[group_key]
            if not isinstance(group_dict, dict):
                continue

            for element_key in sorted(group_dict.keys()):
                value = group_dict[element_key]

                # Format tag as (GGGG,EEEE)
                try:
                    group_hex = f"{int(group_key):04X}"
                    element_hex = f"{int(element_key):04X}"
                    tag_str = f"({group_hex},{element_hex})"
                except (ValueError, TypeError):
                    continue

                # Get tag name from tag_labels
                pipe_tag = f"{group_hex}|{element_hex}"
                tag_name = self.tag_labels.get(pipe_tag, _("Unknown"))

                # Convert value to string
                value_str = str(value) if value is not None else ""

                self.all_tags.append((tag_str, tag_name, value_str))

        # Display all tags
        self._display_tags(self.all_tags)

    def _display_tags(self, tags):
        """Display the given list of tags in the list control."""
        self.list_ctrl.DeleteAllItems()

        for tag_str, tag_name, value_str in tags:
            index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), tag_str)
            self.list_ctrl.SetItem(index, 1, tag_name)
            self.list_ctrl.SetItem(index, 2, value_str)

    def _on_search(self, event):
        """Filter tags based on search text."""
        search_text = self.search_ctrl.GetValue().lower()

        if not search_text:
            self._display_tags(self.all_tags)
            return

        # Filter tags that match search text in any column
        filtered_tags = [
            (tag, name, value)
            for tag, name, value in self.all_tags
            if search_text in tag.lower()
            or search_text in name.lower()
            or search_text in value.lower()
        ]

        self._display_tags(filtered_tags)

    def _on_search_cancel(self, event):
        """Clear search and show all tags."""
        self.search_ctrl.SetValue("")
        self._display_tags(self.all_tags)

    def _on_export(self, event):
        """Export all visible tags to CSV file."""
        wildcard = "CSV files (*.csv)|*.csv"
        dlg = wx.FileDialog(
            self,
            message=_("Export DICOM tags to CSV"),
            defaultFile="dicom_tags.csv",
            wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )

        if dlg.ShowModal() == wx.ID_OK:
            filepath = dlg.GetPath()
            try:
                with open(filepath, "w", newline="", encoding="utf-8-sig") as csvfile:
                    writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
                    # Write header
                    writer.writerow(["Tag", "Name", "Value"])

                    # Write data
                    for i in range(self.list_ctrl.GetItemCount()):
                        tag = self.list_ctrl.GetItemText(i, 0)
                        name = self.list_ctrl.GetItemText(i, 1)
                        value = self.list_ctrl.GetItemText(i, 2)
                        
                        # Clean up the value to handle special characters
                        try:
                            # Replace problematic characters
                            value_clean = value.replace('\x00', '').replace('\r', ' ').replace('\n', ' ')
                            writer.writerow([tag, name, value_clean])
                        except Exception:
                            # If there's still an encoding issue, use repr
                            writer.writerow([tag, name, repr(value)])

                wx.MessageBox(
                    _("DICOM tags exported successfully to:\n{}").format(filepath),
                    _("Success"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            except Exception as e:
                wx.MessageBox(
                    _("Error exporting DICOM tags:\n{}").format(str(e)),
                    _("Error"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )

        dlg.Destroy()

    def _on_close(self, event):
        """Close the dialog."""
        self.Close()
