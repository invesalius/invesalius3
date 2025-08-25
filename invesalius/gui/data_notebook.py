# -*- coding: UTF-8 -*-
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
import os
import sys

try:
    import Image
except ImportError:
    from PIL import Image

import wx
import wx.grid

#  import invesalius.gui.widgets.listctrl as listmix
import wx.lib.platebtn as pbtn
import wx.lib.scrolledpanel as scrolled

import invesalius.constants as const
import invesalius.data.slice_ as slice_
import invesalius.gui.dialogs as dlg
from invesalius import inv_paths, project
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

BTN_NEW, BTN_REMOVE, BTN_DUPLICATE, BTN_OPEN = (wx.NewIdRef() for i in range(4))

TYPE = {
    const.LINEAR: _("Linear"),
    const.ANGULAR: _("Angular"),
    const.DENSITY_ELLIPSE: _("Density Ellipse"),
    const.DENSITY_POLYGON: _("Density Polygon"),
}

LOCATION = {
    const.SURFACE: _("3D"),
    const.AXIAL: _("Axial"),
    const.CORONAL: _("Coronal"),
    const.SAGITAL: _("Sagittal"),
}


# Panel that initializes notebook and related tabs
class NotebookPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        book = wx.Notebook(self, -1, style=wx.BK_DEFAULT)
        # TODO: check under Windows and Linux
        # this was necessary under cOS:
        # if wx.Platform == "__WXMAC__":
        if sys.platform != "win32":
            book.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        book.AddPage(MaskPage(book), _("Masks"))
        book.AddPage(SurfacePage(book), _("3D surfaces"))
        book.AddPage(MeasurePage(book), _("Measures"))
        # book.AddPage(AnnotationsListCtrlPanel(book), _("Notes"))

        book.SetSelection(0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(book, 0, wx.EXPAND)
        self.SetSizer(sizer)

        book.Refresh()
        self.book = book

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self._FoldSurface, "Fold surface task")
        Publisher.subscribe(self._FoldSurface, "Fold surface page")
        Publisher.subscribe(self._FoldMeasure, "Fold measure task")
        Publisher.subscribe(self._FoldMask, "Fold mask task")
        Publisher.subscribe(self._FoldMask, "Fold mask page")

    def _FoldSurface(self):
        """
        Fold surface notebook page.
        """
        self.book.SetSelection(1)

    def _FoldMeasure(self):
        """
        Fold measure notebook page.
        """
        self.book.SetSelection(2)

    def _FoldMask(self):
        """
        Fold mask notebook page.
        """
        self.book.SetSelection(0)


class MeasurePage(wx.Panel):
    """
    Page related to mask items.
    """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.__init_gui()

    def __init_gui(self):
        # listctrl were existing masks will be listed
        self.listctrl = MeasuresListCtrlPanel(self, size=wx.Size(256, 100))
        # button control with tools (eg. remove, add new, etc)
        self.buttonctrl = MeasureButtonControlPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.listctrl, 0, wx.EXPAND)
        sizer.Add(self.buttonctrl, 0, wx.EXPAND | wx.TOP, 2)
        self.SetSizer(sizer)
        self.Fit()


class MeasureButtonControlPanel(wx.Panel):
    """
    Button control panel that includes data notebook operations.
    TODO: Enhace interface with parent class - it is really messed up
    """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50), size=wx.Size(256, 22))
        self.parent = parent
        self.__init_gui()

    def __init_gui(self):
        # Bitmaps to be used in plate buttons
        BMP_NEW = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "data_new.png"), wx.BITMAP_TYPE_PNG)
        BMP_REMOVE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_remove.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_DUPLICATE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_duplicate.png"), wx.BITMAP_TYPE_PNG
        )

        # Plate buttons based on previous bitmaps
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_new = pbtn.PlateButton(
            self, BTN_NEW, "", BMP_NEW, style=button_style, size=wx.Size(24, 20)
        )
        button_new.SetToolTip(_("Create a new measure"))

        button_remove = pbtn.PlateButton(
            self, BTN_REMOVE, "", BMP_REMOVE, style=button_style, size=wx.Size(24, 20)
        )
        button_remove.SetToolTip(_("Remove measure"))

        button_duplicate = pbtn.PlateButton(
            self, BTN_DUPLICATE, "", BMP_DUPLICATE, style=button_style, size=wx.Size(24, 20)
        )
        button_duplicate.SetToolTip(_("Duplicate measure"))
        button_duplicate.Disable()

        # Add all controls to gui
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_new, 0, wx.GROW | wx.EXPAND | wx.LEFT)
        sizer.Add(button_remove, 0, wx.GROW | wx.EXPAND)
        sizer.Add(button_duplicate, 0, wx.GROW | wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        menu = wx.Menu()
        menu.Append(const.MEASURE_LINEAR, _("Measure distance"))
        menu.Append(const.MEASURE_ANGULAR, _("Measure angle"))
        menu.Bind(wx.EVT_MENU, self.OnMenu)
        self.menu = menu

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnButton)

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnNew()
        elif id == BTN_REMOVE:
            self.OnRemove()
        elif id == BTN_DUPLICATE:
            self.OnDuplicate()

    def OnNew(self):
        self.PopupMenu(self.menu)

    def OnMenu(self, evt):
        id = evt.GetId()
        if id == const.MEASURE_LINEAR:
            Publisher.sendMessage("Set tool linear measure")
        else:
            Publisher.sendMessage("Set tool angular measure")

    def OnRemove(self):
        self.parent.listctrl.RemoveMeasurements()

    def OnDuplicate(self):
        selected_items = self.parent.listctrl.GetSelected()
        if selected_items:
            Publisher.sendMessage("Duplicate measurement", selected_items)
        else:
            dlg.MaskSelectionRequiredForDuplication()


class MaskPage(wx.Panel):
    """
    Page related to mask items.
    """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.categories = {}
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)
        self.__init_gui()

        Publisher.subscribe(self.AddMask, "Add mask")
        Publisher.subscribe(self.RefreshMasks, "Refresh Masks")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.EditMaskThreshold, "Set mask threshold in notebook")
        Publisher.subscribe(self.EditMaskColour, "Change mask colour in notebook")
        Publisher.subscribe(self.OnChangeCurrentMask, "Change mask selected")
        Publisher.subscribe(self.__hide_current_mask, "Hide current mask")
        Publisher.subscribe(self.__show_current_mask, "Show current mask")
        Publisher.subscribe(self.update_current_colour, "Set GUI items colour")
        Publisher.subscribe(self.update_select_all_checkbox, "Update mask select all checkbox")

    def __init_gui(self):
        # button control with tools (eg. remove, add new, etc)
        self.buttonctrl = ButtonControlPanel(self)

        self.scroll_panel = scrolled.ScrolledPanel(self)
        self.scroll_panel.SetupScrolling()

        # sizer for scrollable content
        self.scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll_panel.SetSizer(self.scroll_sizer)

        self.sizer.Add(self.scroll_panel, 1, wx.EXPAND | wx.ALL, 2)
        self.sizer.Add(self.buttonctrl, 0, wx.EXPAND | wx.TOP, 2)

        self.create_category("General")

    def create_category_header(self, parent, category):
        """Create header panel with category controls"""
        header_panel = wx.Panel(parent)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Category label
        category_label = wx.StaticText(header_panel, label=category)
        category_label.SetFont(category_label.GetFont().Bold())

        # Spacer to push controls to the right
        header_sizer.Add(category_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)

        # Create image list for visibility icons
        visibility_imagelist = wx.ImageList(16, 16)
        invisible_image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_invisible.png"))
        invisible_bitmap = wx.Bitmap(invisible_image.Scale(16, 16))
        visible_image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_visible.png"))
        visible_bitmap = wx.Bitmap(visible_image.Scale(16, 16))
        visibility_imagelist.Add(invisible_bitmap)
        visibility_imagelist.Add(visible_bitmap)

        # Visibility toggle button with icon
        visibility_btn = wx.BitmapButton(header_panel, size=(24, 24))
        visibility_btn.SetBitmap(visible_bitmap)
        visibility_btn.SetToolTip("Toggle visibility for all masks in this category")
        visibility_btn.Bind(wx.EVT_BUTTON, lambda evt: self.on_category_visibility_toggle(category))

        # Select all checkbox
        select_all_cb = wx.CheckBox(header_panel, label="", style=wx.CHK_3STATE)
        select_all_cb.SetToolTip("Select/Unselect all masks in this category")
        select_all_cb.Bind(
            wx.EVT_CHECKBOX, lambda evt: self.on_category_select_all(category, evt.IsChecked())
        )

        # Add controls to header
        header_sizer.Add(visibility_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        header_sizer.Add(select_all_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        header_panel.SetSizer(header_sizer)

        return header_panel, visibility_btn, select_all_cb, invisible_bitmap, visible_bitmap

    def create_category(self, category):
        # Create CollapsiblePane
        collapsible_pane = wx.CollapsiblePane(
            self.scroll_panel,
            label="",  # We'll use custom header
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE,
        )
        collapsible_pane.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnPaneChanged)

        # Create custom header with controls
        header_panel, visibility_btn, select_all_cb, invisible_bitmap, visible_bitmap = (
            self.create_category_header(self.scroll_panel, category)
        )

        # Get the pane window for the list
        pane_window = collapsible_pane.GetPane()

        listctrl = MasksListCtrlPanel(pane_window, size=wx.Size(256, 100))
        listctrl.category = category
        pane_sizer = wx.BoxSizer(wx.VERTICAL)
        pane_sizer.Add(listctrl, 1, wx.EXPAND)
        pane_window.SetSizer(pane_sizer)

        self.categories[category] = {
            "pane": collapsible_pane,
            "header": header_panel,
            "visibility_btn": visibility_btn,
            "select_all_cb": select_all_cb,
            "list": listctrl,
            "invisible_bitmap": invisible_bitmap,
            "visible_bitmap": visible_bitmap,
        }

        self.scroll_sizer.Add(header_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 2)
        self.scroll_sizer.Add(collapsible_pane, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
        collapsible_pane.Expand()

        return listctrl

    def on_category_visibility_toggle(self, category):
        """Toggle visibility for all masks in the given category"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]
        visibility_btn = self.categories[category]["visibility_btn"]
        invisible_bitmap = self.categories[category]["invisible_bitmap"]
        visible_bitmap = self.categories[category]["visible_bitmap"]

        is_visible = False
        for local_pos in listctrl.mask_list_index.values():
            try:
                item = listctrl.GetItem(local_pos, 0)
                if item.GetImage() == 1:  # 1 = visible
                    is_visible = True
                    break
            except wx.wxAssertionError:
                continue

        # toggle visibility for all masks in this category, if any is visible, hide all, otherwise show all
        for global_mask_id, local_pos in listctrl.mask_list_index.items():
            new_visibility = not is_visible
            listctrl.SetItemImage(local_pos, int(new_visibility))
            Publisher.sendMessage("Show mask", index=global_mask_id, value=new_visibility)

        if new_visibility:
            visibility_btn.SetBitmap(visible_bitmap)
        else:
            visibility_btn.SetBitmap(invisible_bitmap)

    def on_category_select_all(self, category, select_all):
        """Select or unselect all masks in the given category"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]

        for global_mask_id, local_pos in listctrl.mask_list_index.items():
            if select_all:
                listctrl.SetItemState(local_pos, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            else:
                listctrl.SetItemState(local_pos, 0, wx.LIST_STATE_SELECTED)

        self.update_select_all_checkbox(category)

    def update_select_all_checkbox(self, category):
        """Update the select all checkbox state based on current selection"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]
        select_all_cb = self.categories[category]["select_all_cb"]

        total_items = listctrl.GetItemCount()

        if total_items == 0:
            select_all_cb.Set3StateValue(wx.CHK_UNCHECKED)
        else:
            selected_items = len(listctrl.GetSelected())

            if selected_items == 0:
                select_all_cb.Set3StateValue(wx.CHK_UNCHECKED)
            elif selected_items == total_items:
                select_all_cb.Set3StateValue(wx.CHK_CHECKED)
            else:
                select_all_cb.Set3StateValue(wx.CHK_UNDETERMINED)

        # check across all categories to determine the global state
        all_selected_indices = []
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            selected = listctrl.GetSelected()
            all_selected_indices.extend(selected)

        Publisher.sendMessage("Update selected masks list", indices=all_selected_indices)

        is_batch_mode = len(all_selected_indices) > 1
        Publisher.sendMessage("Select all masks changed", select_all_active=is_batch_mode)

    def AddMask(self, mask):
        category = getattr(mask, "category", "General")
        if category not in self.categories:
            self.create_category(category)

        self.categories[category]["list"].AddMask(mask)
        self.update_scroll_layout()

        self.update_select_all_checkbox(category)

    def RefreshMasks(self, clear_project=False):
        """Destroy all components and clear sizer"""

        self.scroll_sizer.Clear(delete_windows=True)
        self.categories.clear()

        self.create_category("General")

        if not clear_project:
            mask_dict = project.Project().mask_dict
            for i in sorted(mask_dict.keys()):
                mask = mask_dict[i]
                self.AddMask(mask)
        self.update_scroll_layout()

    def OnPaneChanged(self, evt):
        self.update_scroll_layout()

    def update_scroll_layout(self):
        """Update scroll panel layout"""
        self.scroll_sizer.Layout()
        min_size = self.scroll_sizer.GetMinSize()
        self.scroll_panel.SetVirtualSize(min_size)
        self.scroll_panel.FitInside()
        self.Layout()

    def update_current_colour(self, colour):
        """Handle updating the current mask colour in the respective category list"""
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if hasattr(listctrl, "current_index") and listctrl.current_index >= 0:
                listctrl.update_current_colour(colour)

    def __hide_current_mask(self):
        """Handle hiding the current mask in the respective category list"""
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if hasattr(listctrl, "current_index") and listctrl.current_index >= 0:
                listctrl.__hide_current_mask()

    def __show_current_mask(self):
        """Handle showing the current mask in the respective category list"""
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if hasattr(listctrl, "current_index") and listctrl.current_index >= 0:
                listctrl.__show_current_mask()

    def OnChangeCurrentMask(self, index):
        """Handle mask selection change in the appropriate category list"""
        selected_listctrl = None
        local_idx_to_select = -1
        selected_category = None

        for category, category_info in self.categories.items():
            listctrl = category_info["list"]
            if index in listctrl.mask_list_index:
                selected_listctrl = listctrl
                selected_category = category
                local_idx_to_select = listctrl.mask_list_index[index]
                break

        if selected_listctrl and local_idx_to_select != -1:
            for category_info in self.categories.values():
                listctrl = category_info["list"]
                if listctrl is not selected_listctrl:
                    for local_idx in listctrl.mask_list_index.values():
                        listctrl.SetItemImage(local_idx, 0)

            selected_listctrl.OnChangeCurrentMask(local_idx_to_select)

            if selected_category:
                self.update_select_all_checkbox(selected_category)

    def EditMaskThreshold(self, index, threshold_range):
        """Edit mask threshold in the appropriate category list"""
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if index in listctrl.mask_list_index:
                listctrl.EditMaskThreshold(index, threshold_range)
                return

    def EditMaskColour(self, index, colour):
        """Edit mask colour in the appropriate category list"""
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if index in listctrl.mask_list_index:
                listctrl.EditMaskColour(index, colour)
                return

    def OnCloseProject(self):
        self.RefreshMasks(clear_project=True)


class ButtonControlPanel(wx.Panel):
    """
    Button control panel that includes data notebook operations.
    TODO: Enhace interface with parent class - it is really messed up
    """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50), size=wx.Size(256, 22))
        self.parent = parent
        self.__init_gui()

    def __init_gui(self):
        # Bitmaps to be used in plate buttons
        BMP_NEW = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "data_new.png"), wx.BITMAP_TYPE_PNG)
        BMP_REMOVE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_remove.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_DUPLICATE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_duplicate.png"), wx.BITMAP_TYPE_PNG
        )

        # Plate buttons based on previous bitmaps
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_new = pbtn.PlateButton(
            self, BTN_NEW, "", BMP_NEW, style=button_style, size=wx.Size(24, 20)
        )
        button_new.SetToolTip(_("Create a new mask"))

        button_remove = pbtn.PlateButton(
            self, BTN_REMOVE, "", BMP_REMOVE, style=button_style, size=wx.Size(24, 20)
        )
        button_remove.SetToolTip(_("Remove mask"))

        button_duplicate = pbtn.PlateButton(
            self, BTN_DUPLICATE, "", BMP_DUPLICATE, style=button_style, size=wx.Size(24, 20)
        )
        button_duplicate.SetToolTip(_("Duplicate mask"))

        # Add all controls to gui
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_new, 0, wx.GROW | wx.EXPAND | wx.LEFT)
        sizer.Add(button_remove, 0, wx.GROW | wx.EXPAND)
        sizer.Add(button_duplicate, 0, wx.GROW | wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnButton)

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnNew()
        elif id == BTN_REMOVE:
            self.OnRemove()
        elif id == BTN_DUPLICATE:
            self.OnDuplicate()

    def OnNew(self):
        dialog = dlg.NewMask()

        try:
            if dialog.ShowModal() == wx.ID_OK:
                ok = 1
            else:
                ok = 0
        except wx.PyAssertionError:  # TODO FIX: win64
            ok = 1

        if ok:
            mask_name, thresh, colour = dialog.GetValue()
            if mask_name:
                Publisher.sendMessage(
                    "Create new mask", mask_name=mask_name, thresh=thresh, colour=colour
                )
        dialog.Destroy()

    def OnRemove(self):
        focused_list = self.FindFocus()
        if isinstance(focused_list, MasksListCtrlPanel):
            focused_list.RemoveMasks()

    def OnDuplicate(self):
        focused_list = self.FindFocus()
        if isinstance(focused_list, MasksListCtrlPanel):
            selected_items = focused_list.GetSelected()
        if selected_items:
            Publisher.sendMessage("Duplicate masks", mask_indexes=selected_items)
        else:
            dlg.MaskSelectionRequiredForDuplication()


class InvListCtrl(wx.ListCtrl):
    def __init__(
        self,
        parent,
        ID=-1,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=wx.LC_REPORT | wx.LC_EDIT_LABELS,
    ):
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style=style)
        self.__bind_events_wx()

    def __bind_events_wx(self):
        self.Bind(wx.EVT_LEFT_DOWN, self.OnClickItem)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnDblClickItem)

    def CreateColourBitmap(self, colour):
        """
        Create a wx Image with a mask colour.
        colour: colour in rgb format(0 - 1)
        """
        image = self.image_gray
        new_image = Image.new("RGB", image.size)
        for x in range(image.size[0]):
            for y in range(image.size[1]):
                pixel_colour = [int(i * image.getpixel((x, y))) for i in colour]
                new_image.putpixel((x, y), tuple(pixel_colour))

        wx_image = wx.Image(new_image.size[0], new_image.size[1])
        try:
            wx_image.SetData(new_image.tostring())
        except Exception:
            wx_image.SetData(new_image.tobytes())
        return wx.Bitmap(wx_image.Scale(16, 16))

    def OnClickItem(self, evt):
        self._click_check = False
        item_idx, flag = self.HitTest(evt.GetPosition())
        if item_idx > -1:
            column_clicked = self.get_column_clicked(evt.GetPosition())
            if column_clicked == 0:
                self._click_check = True
                item = self.GetItem(item_idx, 0)
                flag = not bool(item.GetImage())
                self.SetItemImage(item_idx, int(flag))
                self.OnCheckItem(item_idx, flag)
                return
            elif column_clicked == 1:
                self.OnChangeColor(item_idx)
                return
            elif column_clicked == 5:
                self.OnChangeTransparency(item_idx)
                return
            if evt:
                evt.Skip()

    def OnChangeColor(self, item_idx):
        pass

    def OnChangeTransparency(self, item_idx):
        pass

    def OnDblClickItem(self, evt):
        self._click_check = False
        item_idx, flag = self.HitTest(evt.GetPosition())
        if item_idx > -1:
            column_clicked = self.get_column_clicked(evt.GetPosition())
            if column_clicked == 2:
                item = self.GetItem(item_idx, 2)
                item.SetId(item_idx)
                self.enter_edition(item)
                return
        evt.Skip()

    def enter_edition(self, item):
        ctrl = self.EditLabel(item.GetId())
        w, h = ctrl.GetClientSize()
        w = self.GetColumnWidth(2)
        ctrl.SetClientSize(w, h)
        ctrl.SetValue(item.GetText())
        ctrl.SelectAll()

    def get_column_clicked(self, position):
        epx, epy = position
        wpx, wpy = self.GetPosition()
        width_sum = 0
        for i in range(self.GetColumnCount()):
            width_sum += self.GetColumnWidth(i)
            if (epx - wpx) <= width_sum:
                return i
        return -1


class MasksListCtrlPanel(InvListCtrl):
    def __init__(
        self,
        parent,
        ID=-1,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=wx.LC_REPORT | wx.LC_EDIT_LABELS,
    ):
        super().__init__(parent, ID, pos, size, style=style)
        self._click_check = False
        self.mask_list_index = {}
        self.current_index = 0
        self.current_color = [255, 255, 255]
        self.__init_columns()
        self.__init_image_list()
        self.__bind_events_wx()
        self.__bind_events()

    def __bind_events_wx(self):
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEditLabel)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyEvent)
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.on_mouse_right_click)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_selection_changed)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_selection_changed)

    def __bind_events(self):
        Publisher.subscribe(self.OnCloseProject, "Close project data")

    def on_selection_changed(self, evt):
        """Handle selection changes in the mask list"""
        if hasattr(self, "category"):
            Publisher.sendMessage("Update mask select all checkbox", category=self.category)
        else:
            print("Selection changed but 'category' attribute not found on self.")
        if evt:
            evt.Skip()

    def on_mouse_right_click(self, event):
        start_idx = 1
        focused_item = self.GetFocusedItem()

        # Create the context menu and add all the menu items
        mask_context_menu = wx.Menu()

        colour_id = mask_context_menu.Append(start_idx, _("Change color"))
        mask_context_menu.Bind(wx.EVT_MENU, self.change_mask_color, colour_id)

        duplicate_id = mask_context_menu.Append(start_idx + 1, _("Duplicate"))
        mask_context_menu.Bind(wx.EVT_MENU, self.duplicate_masks, duplicate_id)

        mask_context_menu.AppendSeparator()

        delete_id = mask_context_menu.Append(start_idx + 2, _("Delete"))
        mask_context_menu.Bind(wx.EVT_MENU, self.delete_mask, delete_id)

        # Select the focused mask and show it in the slice viewer
        Publisher.sendMessage("Change mask selected", index=focused_item)
        Publisher.sendMessage("Show mask", index=focused_item, value=True)

        self.PopupMenu(mask_context_menu)
        mask_context_menu.Destroy()

    def update_current_colour(self, colour):
        self.current_colour = colour

    def OnChangeColor(self, item_idx):
        """Open color picker for the clicked mask"""
        global_mask_id = None
        for mask_id, local_pos in self.mask_list_index.items():
            if local_pos == item_idx:
                global_mask_id = mask_id
                break

        if global_mask_id is None:
            return

        Publisher.sendMessage("Change mask selected", index=global_mask_id)
        self.change_mask_color(None)

    def change_mask_color(self, event):
        current_color = self.current_color

        new_color = dlg.ShowColorDialog(color_current=current_color)

        if not new_color:
            return

        Publisher.sendMessage("Change mask colour", colour=new_color)

    def duplicate_masks(self, event):
        selected_items = self.GetSelected()
        if selected_items:
            Publisher.sendMessage("Duplicate masks", mask_indexes=selected_items)
        else:
            dlg.MaskSelectionRequiredForDuplication()

    def delete_mask(self, event):
        result = dlg.ShowConfirmationDialog(msg=_("Delete mask?"))
        if result != wx.ID_OK:
            return
        self.RemoveMasks()

    def OnKeyEvent(self, event):
        keycode = event.GetKeyCode()
        # Delete key
        if (sys.platform == "darwin") and (keycode == wx.WXK_BACK):
            self.RemoveMasks()
        elif keycode == wx.WXK_DELETE:
            self.RemoveMasks()

    def RemoveMasks(self):
        """
        Remove selected items.
        """
        selected_items = self.GetSelected()

        if selected_items:
            Publisher.sendMessage("Remove masks", mask_indexes=selected_items)
            Publisher.sendMessage("Refresh Masks")
        else:
            dlg.MaskSelectionRequiredForRemoval()

    def OnCloseProject(self):
        self.DeleteAllItems()
        self.mask_list_index = {}

    def OnChangeCurrentMask(self, index):
        try:
            self.SetItemImage(index, 1)
            self.current_index = index
        except wx.PyAssertionError:
            # in SetItem(): invalid item index in SetItem
            pass
        for local_idx in self.mask_list_index.values():
            if local_idx != index:
                self.SetItemImage(local_idx, 0)

    def __hide_current_mask(self):
        if self.mask_list_index:
            self.SetItemImage(self.current_index, 0)

    def __show_current_mask(self):
        if self.mask_list_index:
            self.SetItemImage(self.current_index, 1)

    def __init_columns(self):
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(2, _("Name"))
        self.InsertColumn(3, _("Threshold"), wx.LIST_FORMAT_RIGHT)

        self.SetColumnWidth(0, 25)
        self.SetColumnWidth(1, 25)
        self.SetColumnWidth(2, 95)
        self.SetColumnWidth(3, 90)

        # Set tooltip to inform users about color clicking
        self.SetToolTip(_("Change mask color"))

    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_invisible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.imagelist.Add(bitmap)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_visible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.imagelist.Add(bitmap)

        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

        self.image_gray = Image.open(os.path.join(inv_paths.ICON_DIR, "object_colour.png"))

    def OnEditLabel(self, evt):
        if not evt.IsEditCancelled():
            index = evt.GetIndex()
            self.SetItem(index, 2, evt.GetLabel())
            print("GGG")
            Publisher.sendMessage("Change mask name", index=evt.GetIndex(), name=evt.GetLabel())
        evt.Skip()

    def OnCheckItem(self, index, flag):
        print(f" OnCheckItem called with index: {index}, flag: {flag}")

        global_idx = -1
        for g_id, l_id in self.mask_list_index.items():
            if l_id == index:
                global_idx = g_id
                break

        if global_idx == -1:
            print(f" OnCheckItem: global_idx not found for local index {index}")
            return

        print(f" OnCheckItem: global_idx = {global_idx}")

        if flag:
            Publisher.sendMessage("Change mask selected", index=global_idx)
            self.current_index = index

        Publisher.sendMessage("Show mask", index=global_idx, value=flag)

        # Also trigger selection update since this affects the overall selection state
        print(" OnCheckItem: triggering selection update")
        self.on_selection_changed(None)

    def InsertNewItem(self, index=0, label=_("Mask"), threshold="(1000, 4500)", colour=None):
        image = self.CreateColourBitmap(colour)
        image_index = self.imagelist.Add(image)

        self.InsertItem(index, "")
        self.SetItemImage(index, 1)
        self.SetItem(index, 1, "", imageId=image_index)
        self.SetItem(index, 2, label)
        self.SetItem(index, 3, threshold)
        #  self.SetItemImage(index, 1)
        #  for key in self.mask_list_index.keys():
        #  if key != index:
        #  self.SetItemImage(key, 0)
        #  self.current_index = index

    def AddMask(self, mask):
        if mask.index not in self.mask_list_index:
            local_position = len(self.mask_list_index)
            self.mask_list_index[mask.index] = local_position
            self.InsertNewItem(local_position, mask.name, str(mask.threshold_range), mask.colour)

    def EditMaskThreshold(self, global_mask_id, threshold_range):
        if global_mask_id in self.mask_list_index:
            local_pos = self.mask_list_index[global_mask_id]
            try:
                if 0 <= local_pos < self.GetItemCount():
                    self.SetItem(local_pos, 3, str(threshold_range))
            except wx.wxAssertionError:
                pass  # ignore assertion errors for invalid indices

    def EditMaskColour(self, global_mask_id, colour):
        if global_mask_id in self.mask_list_index:
            local_pos = self.mask_list_index[global_mask_id]
            try:
                if 0 <= local_pos < self.GetItemCount():
                    self.imagelist.Replace(local_pos + 2, self.CreateColourBitmap(colour))
                    self.RefreshItem(local_pos)
            except wx.wxAssertionError:
                pass  # ignore assertion errors for invalid indices

    def GetSelected(self):
        """
        Return all items selected (highlighted).
        """
        selected = []
        for global_mask_id, local_pos in self.mask_list_index.items():
            if self.IsSelected(local_pos):
                selected.append(global_mask_id)
        selected.sort(reverse=True)
        return selected


# -------------------------------------------------
# -------------------------------------------------
class SurfacePage(wx.Panel):
    """
    Page related to surface items.
    """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.categories = {}
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        self.__init_gui()

        Publisher.subscribe(self.AddSurface, "Update surface info in GUI")
        Publisher.subscribe(self.RepopulateSurfaces, "Repopulate surfaces")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.EditSurfaceTransparency, "Set surface transparency")
        Publisher.subscribe(self.EditSurfaceColour, "Set surface colour")
        Publisher.subscribe(self.OnShowSingle, "Show single surface")
        Publisher.subscribe(self.OnShowMultiple, "Show multiple surfaces")
        Publisher.subscribe(self.update_current_surface_data, "Update surface info in GUI")
        Publisher.subscribe(self.update_select_all_checkbox, "Update surface select all checkbox")

    def __init_gui(self):
        # button control with tools (eg. remove, add new, etc)
        self.buttonctrl = SurfaceButtonControlPanel(self)

        # Create scrolled panel for categories
        self.scroll_panel = scrolled.ScrolledPanel(self)
        self.scroll_panel.SetupScrolling()

        # Sizer for scrollable content
        self.scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll_panel.SetSizer(self.scroll_sizer)

        self.sizer.Add(self.scroll_panel, 1, wx.EXPAND | wx.ALL, 2)
        self.sizer.Add(self.buttonctrl, 0, wx.EXPAND | wx.TOP, 2)

        self.create_category("General")

    def create_category_header(self, parent, category):
        """Create header panel with category controls"""
        header_panel = wx.Panel(parent)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Category label
        category_label = wx.StaticText(header_panel, label=category)
        category_label.SetFont(category_label.GetFont().Bold())

        # Spacer to push controls to the right
        header_sizer.Add(category_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)

        # Create image list for visibility icons
        visibility_imagelist = wx.ImageList(16, 16)
        invisible_image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_invisible.png"))
        invisible_bitmap = wx.Bitmap(invisible_image.Scale(16, 16))
        visible_image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_visible.png"))
        visible_bitmap = wx.Bitmap(visible_image.Scale(16, 16))
        visibility_imagelist.Add(invisible_bitmap)
        visibility_imagelist.Add(visible_bitmap)

        # Visibility toggle button with icon
        visibility_btn = wx.BitmapButton(header_panel, size=(24, 24))
        visibility_btn.SetBitmap(visible_bitmap)
        visibility_btn.SetToolTip("Toggle visibility for all surfaces in this category")
        visibility_btn.Bind(wx.EVT_BUTTON, lambda evt: self.on_category_visibility_toggle(category))

        # Select all checkbox
        select_all_cb = wx.CheckBox(header_panel, label="", style=wx.CHK_3STATE)
        select_all_cb.SetToolTip("Select/Unselect all surfaces in this category")
        select_all_cb.Bind(
            wx.EVT_CHECKBOX, lambda evt: self.on_category_select_all(category, evt.IsChecked())
        )

        # Add controls to header
        header_sizer.Add(visibility_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        header_sizer.Add(select_all_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        header_panel.SetSizer(header_sizer)

        return header_panel, visibility_btn, select_all_cb, invisible_bitmap, visible_bitmap

    def create_category(self, category):
        # Create CollapsiblePane
        collapsible_pane = wx.CollapsiblePane(
            self.scroll_panel,
            label="",  # We'll use custom header
            style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE,
        )
        collapsible_pane.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.OnPaneChanged)

        # Create custom header with controls
        header_panel, visibility_btn, select_all_cb, invisible_bitmap, visible_bitmap = (
            self.create_category_header(self.scroll_panel, category)
        )

        # Get the pane window for the list
        pane_window = collapsible_pane.GetPane()

        listctrl = SurfacesListCtrlPanel(pane_window, size=wx.Size(256, 100), category=category)
        pane_sizer = wx.BoxSizer(wx.VERTICAL)
        pane_sizer.Add(listctrl, 1, wx.EXPAND)
        pane_window.SetSizer(pane_sizer)

        # Store references including the new controls
        self.categories[category] = {
            "pane": collapsible_pane,
            "header": header_panel,
            "visibility_btn": visibility_btn,
            "select_all_cb": select_all_cb,
            "list": listctrl,
            "invisible_bitmap": invisible_bitmap,
            "visible_bitmap": visible_bitmap,
        }

        # Add header and collapsible pane to scroll sizer
        self.scroll_sizer.Add(header_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 2)
        self.scroll_sizer.Add(collapsible_pane, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
        collapsible_pane.Expand()

        return listctrl

    def on_category_visibility_toggle(self, category):
        """Toggle visibility for all surfaces in the given category"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]
        visibility_btn = self.categories[category]["visibility_btn"]
        invisible_bitmap = self.categories[category]["invisible_bitmap"]
        visible_bitmap = self.categories[category]["visible_bitmap"]

        is_visible = False
        for local_pos in listctrl.surface_list_index.values():
            try:
                item = listctrl.GetItem(local_pos, 0)
                if item.GetImage() == 1:  # 1 = visible
                    is_visible = True
                    break
            except wx.wxAssertionError:
                continue

        for global_surface_id, local_pos in listctrl.surface_list_index.items():
            new_visibility = not is_visible
            listctrl.SetItemImage(local_pos, int(new_visibility))
            Publisher.sendMessage(
                "Show surface", index=global_surface_id, visibility=new_visibility
            )

        # Update the button icon based on the new visibility state
        if new_visibility:
            visibility_btn.SetBitmap(visible_bitmap)
        else:
            visibility_btn.SetBitmap(invisible_bitmap)

    def on_category_select_all(self, category, select_all):
        """Select or unselect all surfaces in the given category"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]

        for local_pos in listctrl.surface_list_index.values():
            if select_all:
                listctrl.SetItemState(local_pos, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            else:
                listctrl.SetItemState(local_pos, 0, wx.LIST_STATE_SELECTED)

    def update_select_all_checkbox(self, category):
        """Update the select all checkbox state based on current selection"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]
        select_all_cb = self.categories[category]["select_all_cb"]

        total_items = len(listctrl.surface_list_index)
        if total_items == 0:
            select_all_cb.Set3StateValue(wx.CHK_UNCHECKED)
            return

        selected_items = len(listctrl.GetSelected())

        if selected_items == 0:
            select_all_cb.Set3StateValue(wx.CHK_UNCHECKED)
        elif selected_items == total_items:
            select_all_cb.Set3StateValue(wx.CHK_CHECKED)
        else:
            select_all_cb.Set3StateValue(wx.CHK_UNDETERMINED)

    def _update_visibility_button_icon(self, category):
        """Update the visibility button icon based on current visibility state"""
        if category not in self.categories:
            return

        listctrl = self.categories[category]["list"]
        visibility_btn = self.categories[category]["visibility_btn"]
        invisible_bitmap = self.categories[category]["invisible_bitmap"]
        visible_bitmap = self.categories[category]["visible_bitmap"]

        # Check if any items are visible
        any_visible = False
        for local_pos in listctrl.surface_list_index.values():
            try:
                item = listctrl.GetItem(local_pos, 0)
                if item.GetImage() == 1:  # 1 = visible
                    any_visible = True
                    break
            except wx.wxAssertionError:
                continue

        # Update button icon
        if any_visible:
            visibility_btn.SetBitmap(visible_bitmap)
        else:
            visibility_btn.SetBitmap(invisible_bitmap)

    def AddSurface(self, surface):
        category = getattr(surface, "category", "General")
        if category not in self.categories:
            self.create_category(category)

        self.categories[category]["list"].InsertSurfaceItem(surface)
        self.update_scroll_layout()
        self.update_select_all_checkbox(category)

        # Update visibility button icon
        self._update_visibility_button_icon(category)

    def RepopulateSurfaces(self, clear_project=False):
        # Properly destroy all components and clear sizer
        self.scroll_sizer.Clear(delete_windows=True)
        self.categories.clear()

        if not clear_project:
            self.create_category("General")
            surface_dict = project.Project().surface_dict
            for i in sorted(surface_dict.keys()):
                surface = surface_dict[i]
                self.AddSurface(surface)
        else:
            # Just create an empty General category for clean state
            self.create_category("General")

        self.update_scroll_layout()

    def OnPaneChanged(self, evt):
        self.update_scroll_layout()

    def update_scroll_layout(self):
        """Update scroll panel layout"""
        self.scroll_sizer.Layout()
        min_size = self.scroll_sizer.GetMinSize()
        self.scroll_panel.SetVirtualSize(min_size)
        self.scroll_panel.FitInside()
        self.Layout()

    def OnCloseProject(self):
        self.RepopulateSurfaces(clear_project=True)

    def EditSurfaceColour(self, surface_index, colour):
        """Edit surface colour in the appropriate category list"""
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if surface_index in listctrl.surface_list_index:
                listctrl.EditSurfaceColour(surface_index, colour)
                return

    def EditSurfaceTransparency(self, surface_index, transparency):
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            if surface_index in listctrl.surface_list_index:
                listctrl.EditSurfaceTransparency(surface_index, transparency)
                return

    def update_current_surface_data(self, surface):
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            listctrl.update_current_surface_data(surface)

    def OnShowSingle(self, index, visibility):
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            for key in list(listctrl.surface_list_index.keys()):
                show = (key == index) and visibility
                local_idx = listctrl.surface_list_index[key]
                listctrl.SetItemImage(local_idx, int(show))
                if listctrl.GetItemImage(local_idx) != int(show):
                    Publisher.sendMessage("Show surface", index=key, visibility=show)

    def OnShowMultiple(self, index_list, visibility):
        for category_info in self.categories.values():
            listctrl = category_info["list"]
            for key in list(listctrl.surface_list_index.keys()):
                show = (key in index_list) and visibility
                local_idx = listctrl.surface_list_index[key]
                listctrl.SetItemImage(local_idx, int(show))
                if listctrl.GetItemImage(local_idx) != int(show):
                    Publisher.sendMessage("Show surface", index=key, visibility=show)


class SurfaceButtonControlPanel(wx.Panel):
    """
    Button control panel that includes data notebook operations.
    TODO: Enhace interface with parent class - it is really messed up
    """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50), size=wx.Size(256, 22))
        self.parent = parent
        self.__init_gui()

    def __init_gui(self):
        # Bitmaps to be used in plate buttons
        BMP_NEW = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "data_new.png"), wx.BITMAP_TYPE_PNG)
        BMP_REMOVE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_remove.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_DUPLICATE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "data_duplicate.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_OPEN = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "load_mesh.png"), wx.BITMAP_TYPE_PNG)

        # Plate buttons based on previous bitmaps
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_new = pbtn.PlateButton(
            self, BTN_NEW, "", BMP_NEW, style=button_style, size=wx.Size(24, 20)
        )
        button_new.SetToolTip(_("Create a new surface"))

        button_remove = pbtn.PlateButton(
            self, BTN_REMOVE, "", BMP_REMOVE, style=button_style, size=wx.Size(24, 20)
        )
        button_remove.SetToolTip(_("Remove surface"))

        button_duplicate = pbtn.PlateButton(
            self, BTN_DUPLICATE, "", BMP_DUPLICATE, style=button_style, size=wx.Size(24, 20)
        )
        button_duplicate.SetToolTip(_("Duplicate surface"))

        button_open = pbtn.PlateButton(
            self, BTN_OPEN, "", BMP_OPEN, style=button_style, size=wx.Size(24, 20)
        )
        button_open.SetToolTip(_("Import a surface file into InVesalius"))

        # Add all controls to gui
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_new, 0, wx.GROW | wx.EXPAND | wx.LEFT)
        sizer.Add(button_remove, 0, wx.GROW | wx.EXPAND)
        sizer.Add(button_duplicate, 0, wx.GROW | wx.EXPAND)
        sizer.Add(button_open, 0, wx.GROW | wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnButton)

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnNew()
        elif id == BTN_REMOVE:
            self.OnRemove()
        elif id == BTN_DUPLICATE:
            self.OnDuplicate()
        elif id == BTN_OPEN:
            self.OnOpenMesh()

    def OnNew(self):
        sl = slice_.Slice()
        dialog = dlg.SurfaceCreationDialog(
            None, -1, _("New surface"), mask_edited=sl.current_mask.was_edited
        )
        try:
            if dialog.ShowModal() == wx.ID_OK:
                ok = 1
            else:
                ok = 0
        except wx.PyAssertionError:  # TODO FIX: win64
            ok = 1

        if ok:
            surface_options = dialog.GetValue()

            Publisher.sendMessage("Create surface from index", surface_parameters=surface_options)
        dialog.Destroy()

    def OnRemove(self):
        focused_list = self.FindFocus()
        if isinstance(focused_list, SurfacesListCtrlPanel):
            focused_list.RemoveSurfaces()

    def OnDuplicate(self):
        focused_list = self.FindFocus()
        if isinstance(focused_list, SurfacesListCtrlPanel):
            selected_items = focused_list.GetSelected()
        if selected_items:
            Publisher.sendMessage("Duplicate surfaces", surface_indexes=selected_items)
        else:
            dlg.SurfaceSelectionRequiredForDuplication()

    def OnOpenMesh(self):
        filename = dlg.ShowImportMeshFilesDialog()
        if filename:
            Publisher.sendMessage("Import surface file", filename=filename)


class SurfacesListCtrlPanel(InvListCtrl):
    def __init__(
        self,
        parent,
        ID=-1,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=wx.LC_REPORT | wx.LC_EDIT_LABELS,
        category="General",
    ):
        super().__init__(parent, ID, pos, size, style=style)
        self._click_check = False
        self.category = category
        self.__init_columns()
        self.__init_image_list()
        self.__init_evt()
        self.__bind_events_wx()

        # Color of the currently selected surface when opening context menu, default is white
        self.current_color = [255, 255, 255]
        self.current_transparency = 0
        self.surface_list_index = {}
        self.surface_bmp_idx_to_name = {}

    def __init_evt(self):
        pass

    def __bind_events_wx(self):
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEditLabel)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_selection_changed)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_selection_changed)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyEvent)
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.on_mouse_right_click)

    def on_selection_changed(self, evt):
        Publisher.sendMessage("Update surface select all checkbox", category=self.category)
        if evt:
            evt.Skip()

    def on_mouse_right_click(self, event):
        start_idx = 1
        focused_idx = self.GetFocusedItem()

        # Select the surface that was clicked
        Publisher.sendMessage("Change surface selected", surface_index=focused_idx)

        # Create the context menu and add all the menu items
        surface_context_menu = wx.Menu()

        colour_id = surface_context_menu.Append(start_idx, _("Change color"))
        surface_context_menu.Bind(wx.EVT_MENU, self.change_surface_color, colour_id)

        transparency_id = surface_context_menu.Append(start_idx + 1, _("Change transparency"))
        surface_context_menu.Bind(wx.EVT_MENU, self.change_transparency, transparency_id)

        duplicate_id = surface_context_menu.Append(start_idx + 2, _("Duplicate"))
        surface_context_menu.Bind(wx.EVT_MENU, self.duplicate_surface, duplicate_id)

        surface_context_menu.AppendSeparator()

        delete_id = surface_context_menu.Append(start_idx + 3, _("Delete"))
        surface_context_menu.Bind(wx.EVT_MENU, self.delete_surface, delete_id)

        self.PopupMenu(surface_context_menu)
        surface_context_menu.Destroy()

    def update_current_surface_data(self, surface):
        self.current_color = [int(255 * c) for c in surface.colour][:3]
        self.current_transparency = int(100 * surface.transparency)

    def OnChangeColor(self, item_idx):
        global_surface_id = None
        for surface_id, local_pos in self.surface_list_index.items():
            if local_pos == item_idx:
                global_surface_id = surface_id
                break

        if global_surface_id is None:
            return

        Publisher.sendMessage("Change surface selected", surface_index=global_surface_id)
        self.change_surface_color(None)

    def change_surface_color(self, event):
        focused_idx = self.GetFocusedItem()
        current_color = self.current_color

        new_color = dlg.ShowColorDialog(color_current=current_color)

        if not new_color:
            return

        new_vtk_color = [c / 255.0 for c in new_color]

        Publisher.sendMessage("Set surface colour", surface_index=focused_idx, colour=new_vtk_color)

        Publisher.sendMessage("Change surface selected", surface_index=focused_idx)

    def OnChangeTransparency(self, item_idx):
        global_surface_id = None
        for surface_id, local_pos in self.surface_list_index.items():
            if local_pos == item_idx:
                global_surface_id = surface_id
                break

        if global_surface_id is None:
            return

        Publisher.sendMessage("Change surface selected", surface_index=global_surface_id)
        self.change_transparency(None)

    def change_transparency(self, event):
        focused_idx = self.GetFocusedItem()
        initial_value = self.current_transparency

        transparency_dialog = dlg.SurfaceTransparencyDialog(
            self,
            surface_index=focused_idx,
            transparency=initial_value,
        )

        if transparency_dialog.ShowModal() == wx.ID_OK:
            new_value = transparency_dialog.get_value()
        else:
            new_value = initial_value

        transparency_dialog.Destroy()

        Publisher.sendMessage(
            "Set surface transparency", surface_index=focused_idx, transparency=new_value / 100.0
        )

        Publisher.sendMessage("Change surface selected", surface_index=focused_idx)

    def duplicate_surface(self, event):
        selected_items = self.GetSelected()
        if selected_items:
            Publisher.sendMessage("Duplicate surfaces", surface_indexes=selected_items)
        else:
            dlg.SurfaceSelectionRequiredForDuplication()

    def delete_surface(self, event):
        result = dlg.ShowConfirmationDialog(msg=_("Delete surface?"))
        if result != wx.ID_OK:
            return
        self.RemoveSurfaces()

    def OnKeyEvent(self, event):
        keycode = event.GetKeyCode()
        # Delete key
        if (sys.platform == "darwin") and (keycode == wx.WXK_BACK):
            self.RemoveSurfaces()
        elif keycode == wx.WXK_DELETE:
            self.RemoveSurfaces()

    def RemoveSurfaces(self):
        """
        Remove item given its index.
        """
        selected_items = self.GetSelected()
        if selected_items:
            Publisher.sendMessage("Remove surfaces", surface_indexes=selected_items)
            Publisher.sendMessage("Repopulate surfaces")
        else:
            dlg.SurfaceSelectionRequiredForRemoval()

    def OnCloseProject(self):
        self.DeleteAllItems()
        self.surface_list_index = {}
        self.surface_bmp_idx_to_name = {}

    def OnItemSelected_(self, evt):
        # Note: DON'T rename to OnItemSelected!!!
        # Otherwise the parent's method will be overwritten and other
        # things will stop working, e.g.: OnCheckItem

        # last_surface_index = evt.Index
        # Publisher.sendMessage('Change measurement selected', last_index)
        evt.Skip()

    def GetSelected(self):
        """
        Return all items selected (highlighted).
        """
        selected = []
        for global_surface_id, local_pos in self.surface_list_index.items():
            if self.IsSelected(local_pos):
                selected.append(global_surface_id)
        selected.sort(reverse=True)
        return selected

    def __init_columns(self):
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(2, _("Name"))
        self.InsertColumn(3, _("Volume (mm³)"))
        self.InsertColumn(4, _("Area (mm²)"))
        self.InsertColumn(5, _("Transparency"), wx.LIST_FORMAT_RIGHT)

        self.SetColumnWidth(0, 25)
        self.SetColumnWidth(1, 25)
        self.SetColumnWidth(2, 85)
        self.SetColumnWidth(3, 85)
        self.SetColumnWidth(4, 85)
        self.SetColumnWidth(5, 80)

    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_invisible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.imagelist.Add(bitmap)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_visible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.imagelist.Add(bitmap)

        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

        self.image_gray = Image.open(os.path.join(inv_paths.ICON_DIR, "object_colour.png"))

    def OnBeginLabelEdit(self, evt):
        if evt.GetColumn() == 1:
            evt.Skip()
        else:
            evt.Veto()

    def OnEditLabel(self, evt):
        if not evt.IsEditCancelled():
            index = evt.GetIndex()
            self.SetItem(index, 1, evt.GetLabel())
            Publisher.sendMessage("Change surface name", index=evt.GetIndex(), name=evt.GetLabel())
        evt.Skip()

    def OnCheckItem(self, index, flag):
        global_idx = -1
        for g_id, l_id in self.surface_list_index.items():
            if l_id == index:
                global_idx = g_id
                break

        if global_idx == -1:
            return

        Publisher.sendMessage("Show surface", index=global_idx, visibility=flag)

    def InsertSurfaceItem(self, surface):
        index = surface.index
        name = surface.name
        colour = surface.colour
        volume = f"{surface.volume:.3f}"
        area = f"{surface.area:.3f}"
        transparency = f"{int(100 * surface.transparency)}%"

        if index not in self.surface_list_index:
            image = self.CreateColourBitmap(colour)
            image_index = self.imagelist.Add(image)

            local_position = self.GetItemCount()
            self.surface_list_index[index] = local_position

            self.InsertNewItem(
                local_position, name, volume, area, transparency, colour, image_index
            )
        else:
            local_position = self.surface_list_index[index]
            self.UpdateItemInfo(local_position, name, volume, area, transparency, colour)

    def InsertNewItem(
        self,
        index=0,
        label="Surface 1",
        volume="0 mm3",
        area="0 mm2",
        transparency="0%%",
        colour=None,
        image_index=0,
    ):
        self.InsertItem(index, "")
        self.SetItemImage(index, 1)
        self.SetItem(index, 1, "", imageId=image_index)
        self.SetItem(index, 2, label)
        self.SetItem(index, 3, volume)
        self.SetItem(index, 4, area)
        self.SetItem(index, 5, transparency)
        self.SetItemImage(index, 1)

    def UpdateItemInfo(
        self,
        index=0,
        label="Surface 1",
        volume="0 mm3",
        area="0 mm2",
        transparency="0%%",
        colour=None,
    ):
        self.SetItem(index, 2, label)
        self.SetItem(index, 3, volume)
        self.SetItem(index, 4, area)
        self.SetItem(index, 5, transparency)
        self.SetItemImage(index, 1)

    def EditSurfaceTransparency(self, surface_index, transparency):
        if surface_index in self.surface_list_index:
            local_pos = self.surface_list_index[surface_index]
            self.SetItem(local_pos, 5, f"{int(transparency * 100)}%")

    def EditSurfaceColour(self, surface_index, colour):
        if surface_index in self.surface_list_index:
            local_pos = self.surface_list_index[surface_index]
            image = self.CreateColourBitmap(colour)
            item = self.GetItem(local_pos, 1)
            image_index = item.GetImage()
            if image_index != -1:
                self.imagelist.Replace(image_index, image)
                self.RefreshItem(local_pos)


# -------------------------------------------------
# -------------------------------------------------


class MeasuresListCtrlPanel(InvListCtrl):
    def __init__(
        self,
        parent,
        ID=-1,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=wx.LC_REPORT | wx.LC_EDIT_LABELS,
    ):
        super().__init__(parent, ID, pos, size, style=style)
        self._click_check = False
        self.__init_columns()
        self.__init_image_list()
        self.__init_evt()
        self.__bind_events_wx()
        self._list_index = {}
        self._bmp_idx_to_name = {}

    def __init_evt(self):
        Publisher.subscribe(self.AddItem_, "Update measurement info in GUI")
        Publisher.subscribe(self.EditItemColour, "Set measurement colour")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnShowSingle, "Show single measurement")
        Publisher.subscribe(self.OnShowMultiple, "Show multiple measurements")
        Publisher.subscribe(self.OnLoadData, "Load measurement dict")
        Publisher.subscribe(self.OnRemoveGUIMeasure, "Remove GUI measurement")

    def __bind_events_wx(self):
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEditLabel)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected_)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyEvent)

    def OnKeyEvent(self, event):
        keycode = event.GetKeyCode()
        # Delete key
        if (sys.platform == "darwin") and (keycode == wx.WXK_BACK):
            self.RemoveMeasurements()
        elif keycode == wx.WXK_DELETE:
            self.RemoveMeasurements()

    def OnRemoveGUIMeasure(self, measure_index):
        if measure_index in self._list_index:
            self.DeleteItem(measure_index)

            old_dict = self._list_index
            new_dict = {}
            j = 0
            for i in old_dict:
                if i != measure_index:
                    new_dict[j] = old_dict[i]
                    j += 1
            self._list_index = new_dict

    def RemoveMeasurements(self):
        """
        Remove items selected.
        """
        # it is necessary to update internal dictionary
        # that maps bitmap given item index
        selected_items = self.GetSelected()
        selected_items.sort(reverse=True)

        old_dict = self._list_index
        if selected_items:
            for index in selected_items:
                new_dict = {}
                self.DeleteItem(index)
                for i in old_dict:
                    if i < index:
                        new_dict[i] = old_dict[i]
                    if i > index:
                        new_dict[i - 1] = old_dict[i]
                old_dict = new_dict
            self._list_index = new_dict
            Publisher.sendMessage("Remove measurements", indexes=selected_items)
        else:
            dlg.MeasureSelectionRequiredForRemoval()

    def OnCloseProject(self):
        self.DeleteAllItems()
        self._list_index = {}
        self._bmp_idx_to_name = {}

    def OnItemSelected_(self, evt):
        # Note: DON'T rename to OnItemSelected!!!
        # Otherwise the parent's method will be overwritten and other
        # things will stop working, e.g.: OnCheckItem

        # last_index = evt.Index
        #  Publisher.sendMessage('Change measurement selected',
        #  last_index)
        evt.Skip()

    def GetSelected(self):
        """
        Return all items selected (highlighted).
        """
        selected = []
        for index in self._list_index:
            if self.IsSelected(index):
                selected.append(index)
        # it is important to revert items order, so
        # listctrl update is ok
        selected.sort(reverse=True)

        return selected

    def __init_columns(self):
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, _("Name"))
        self.InsertColumn(2, _("Location"))
        self.InsertColumn(3, _("Type"))
        self.InsertColumn(4, _("Value"), wx.LIST_FORMAT_RIGHT)

        self.SetColumnWidth(0, 25)
        self.SetColumnWidth(1, 65)
        self.SetColumnWidth(2, 55)
        self.SetColumnWidth(3, 50)
        self.SetColumnWidth(4, 75)

    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_invisible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.imagelist.Add(bitmap)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_visible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.imagelist.Add(bitmap)

        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

        self.image_gray = Image.open(os.path.join(inv_paths.ICON_DIR, "object_colour.png"))

    def OnBeginLabelEdit(self, evt):
        if evt.GetColumn() == 1:
            evt.Skip()
        else:
            evt.Veto()

    def OnEditLabel(self, evt):
        if not evt.IsEditCancelled():
            index = evt.GetIndex()
            self.SetItem(index, 1, evt.GetLabel())
            Publisher.sendMessage(
                "Change measurement name", index=evt.GetIndex(), name=evt.GetLabel()
            )
        evt.Skip()

    def OnCheckItem(self, index, flag):
        Publisher.sendMessage("Show measurement", index=index, visibility=flag)

    def OnShowSingle(self, index, visibility):
        for key in self._list_index.keys():
            if key != index:
                self.SetItemImage(key, not visibility)
                Publisher.sendMessage("Show measurement", index=key, visibility=not visibility)
        self.SetItemImage(index, visibility)
        Publisher.sendMessage("Show measurement", index=index, visibility=visibility)

    def OnShowMultiple(self, index_list, visibility):
        for key in self._list_index.keys():
            if key not in index_list:
                self.SetItemImage(key, not visibility)
                Publisher.sendMessage("Show measurement", index=key, visibility=not visibility)
        for index in index_list:
            self.SetItemImage(index, visibility)
            Publisher.sendMessage("Show measurement", index=index, visibility=visibility)

    def OnLoadData(self, measurement_dict, spacing=(1.0, 1.0, 1.0)):
        for i in sorted(measurement_dict):
            m = measurement_dict[i]
            image = self.CreateColourBitmap(m.colour)
            image_index = self.imagelist.Add(image)

            # index_list = self._list_index.keys()
            self._list_index[m.index] = image_index

            colour = [255 * c for c in m.colour]
            type = TYPE[m.type]
            location = LOCATION[m.location]
            if m.type == const.LINEAR:
                value = f"{m.value:.2f} mm"
            elif m.type == const.ANGULAR:
                value = f"{m.value:.2f}°"
            else:
                value = f"{m.value:.3f}"
            self.InsertNewItem(m.index, m.name, colour, location, type, value)

            if not m.visible:
                self.SetItemImage(i, False)

    def AddItem_(self, index, name, colour, location, type_, value):
        if index not in self._list_index:
            image = self.CreateColourBitmap(colour)
            image_index = self.imagelist.Add(image)

            index_list = self._list_index.keys()
            self._list_index[index] = image_index

            if (index in index_list) and index_list:
                try:
                    self.UpdateItemInfo(index, name, colour, location, type_, value)
                except wx.wxAssertionError:
                    self.InsertNewItem(index, name, colour, location, type_, value)
            else:
                self.InsertNewItem(index, name, colour, location, type_, value)
        else:
            try:
                self.UpdateItemInfo(index, name, colour, location, type_, value)
            except wx.wxAssertionError:
                self.InsertNewItem(index, name, colour, location, type_, value)

    def InsertNewItem(
        self,
        index=0,
        label="Measurement 1",
        colour=None,
        location="SURFACE",
        type_="LINEAR",
        value="0 mm",
    ):
        self.InsertItem(index, "")
        self.SetItem(index, 1, label, imageId=self._list_index[index])
        self.SetItem(index, 2, location)
        self.SetItem(index, 3, type_)
        self.SetItem(index, 4, value)
        self.SetItemImage(index, 1)
        self.Refresh()

    def UpdateItemInfo(
        self,
        index=0,
        label="Measurement 1",
        colour=None,
        location="SURFACE",
        type_="LINEAR",
        value="0 mm",
    ):
        self.SetItem(index, 1, label, imageId=self._list_index[index])
        self.SetItem(index, 2, location)
        self.SetItem(index, 3, type_)
        self.SetItem(index, 4, value)
        self.SetItemImage(index, 1)
        self.Refresh()

    def EditItemColour(self, measure_index, colour):
        """ """
        image = self.CreateColourBitmap(colour)
        image_index = self._list_index[measure_index]
        self.imagelist.Replace(image_index, image)
        self.Refresh()


# *******************************************************************
# *******************************************************************


class AnnotationsListCtrlPanel(wx.ListCtrl):
    # TODO: Remove edimixin, allow only visible and invisible
    def __init__(
        self,
        parent,
        ID=-1,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=wx.LC_REPORT | wx.LC_EDIT_LABELS,
    ):
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style=style)
        self._click_check = False
        self.__init_columns()
        self.__init_image_list()
        self.__init_evt()

        # just testing
        self.Populate()

    def __init_evt(self):
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)

    def __init_columns(self):
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, _("Name"))
        self.InsertColumn(2, _("Type"), wx.LIST_FORMAT_CENTER)
        self.InsertColumn(3, _("Value"))

        self.SetColumnWidth(0, 25)
        self.SetColumnWidth(1, 90)
        self.SetColumnWidth(2, 50)
        self.SetColumnWidth(3, 120)

    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_visible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_check = self.imagelist.Add(bitmap)  # noqa: F841

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_invisible.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_null = self.imagelist.Add(bitmap)  # noqa: F841

        image = wx.Image(os.path.join(inv_paths.ICON_DIR, "object_colour.png"))
        bitmap = wx.Bitmap(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.img_colour = self.imagelist.Add(bitmap)

        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

    def OnItemActivated(self, evt):
        self.ToggleItem(evt.Index)

    def OnCheckItem(self, index, flag):
        # TODO: use pubsub to communicate to models
        if flag:
            print("checked, ", index)
        else:
            print("unchecked, ", index)

    def InsertNewItem(self, index=0, name="Axial 1", type_="2d", value="bla", colour=None):
        self.InsertItem(index, "")
        self.SetItem(index, 1, name, imageId=self.img_colour)
        self.SetItem(index, 2, type_)
        self.SetItem(index, 3, value)

    def Populate(self):
        dict = (
            (0, "Axial 1", "2D", "blalbalblabllablalbla"),
            (1, "Coronal 1", "2D", "hello here we are again"),
            (2, "Volume 1", "3D", "hey ho, lets go"),
        )
        for data in dict:
            self.InsertNewItem(data[0], data[1], data[2], data[3])
