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
import sys


from collections import OrderedDict

import wx
from invesalius.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.slice_ as sl
import invesalius.presets as presets
from invesalius.gui.dialogs import ClutImagedataDialog
from invesalius.i18n import tr as _

PROJECTIONS_ID = OrderedDict(
    (
        (_("Normal"), const.PROJECTION_NORMAL),
        (_("MaxIP"), const.PROJECTION_MaxIP),
        (_("MinIP"), const.PROJECTION_MinIP),
        (_("MeanIP"), const.PROJECTION_MeanIP),
        (_("MIDA"), const.PROJECTION_MIDA),
        (_("Contour MaxIP"), const.PROJECTION_CONTOUR_MIP),
        (_("Contour MIDA"), const.PROJECTION_CONTOUR_MIDA),
    )
)


class SliceMenu(wx.Menu):
    def __init__(self):
        wx.Menu.__init__(self)
        self.ID_TO_TOOL_ITEM = {}
        self.cdialog = None

        # ------------ Sub menu of the window and level ----------
        submenu_wl = wx.Menu()

        self._gen_event = True

        # Window and level from DICOM
        new_id = self.id_wl_first = wx.NewIdRef()
        wl_item = submenu_wl.Append(new_id, _("Default"), kind=wx.ITEM_RADIO)
        self.ID_TO_TOOL_ITEM[new_id] = wl_item

        # Case the user change window and level
        new_id = self.other_wl_id = wx.NewIdRef()
        wl_item = submenu_wl.Append(new_id, _("Manual"), kind=wx.ITEM_RADIO)
        self.ID_TO_TOOL_ITEM[new_id] = wl_item

        for name in const.WINDOW_LEVEL:
            if not (name == _("Default") or name == _("Manual")):
                new_id = wx.NewIdRef()
                wl_item = submenu_wl.Append(new_id, name, kind=wx.ITEM_RADIO)
                self.ID_TO_TOOL_ITEM[new_id] = wl_item

        # ----------- Sub menu of the save and load options ---------
        # submenu_wl.AppendSeparator()
        # options = [_("Save current values"),
        #           _("Save current values as..."),_("Load values")]

        # for name in options:
        #    new_id = wx.NewIdRef()
        #    wl_item = wx.MenuItem(submenu_wl, new_id,\
        #                    name)
        #    submenu_wl.Append(wl_item)
        #    self.ID_TO_TOOL_ITEM[new_id] = wl_item

        # ------------ Sub menu of the pseudo colors ----------------
        if sys.platform.startswith("linux"):
            mkind = wx.ITEM_CHECK
        else:
            mkind = wx.ITEM_RADIO

        self.pseudo_color_items = {}
        submenu_pseudo_colours = wx.Menu()
        self.pseudo_color_items = {}
        new_id = self.id_pseudo_first = wx.NewIdRef()
        color_item = submenu_pseudo_colours.Append(new_id, _("Default "), kind=mkind)
        color_item.Check(1)
        self.ID_TO_TOOL_ITEM[new_id] = color_item
        self.pseudo_color_items[new_id] = color_item

        for name in sorted(const.SLICE_COLOR_TABLE):
            if not (name == _("Default ")):
                new_id = wx.NewIdRef()
                color_item = submenu_pseudo_colours.Append(new_id, name, kind=mkind)
                self.ID_TO_TOOL_ITEM[new_id] = color_item
                self.pseudo_color_items[new_id] = color_item

        self.plist_presets = presets.get_wwwl_presets()
        for name in sorted(self.plist_presets):
            new_id = wx.NewIdRef()
            color_item = submenu_pseudo_colours.Append(new_id, name, kind=mkind)
            self.ID_TO_TOOL_ITEM[new_id] = color_item
            self.pseudo_color_items[new_id] = color_item

        new_id = wx.NewIdRef()
        color_item = submenu_pseudo_colours.Append(new_id, _("Custom"), kind=mkind)
        self.ID_TO_TOOL_ITEM[new_id] = color_item
        self.pseudo_color_items[new_id] = color_item

        # --------------- Sub menu of the projection type ---------------------
        self.projection_items = {}
        submenu_projection = wx.Menu()
        for name in PROJECTIONS_ID:
            new_id = wx.NewIdRef()
            projection_item = submenu_projection.Append(
                new_id, name, kind=wx.ITEM_RADIO
            )
            self.ID_TO_TOOL_ITEM[new_id] = projection_item
            self.projection_items[PROJECTIONS_ID[name]] = projection_item

        flag_tiling = False
        # ------------ Sub menu of the image tiling ---------------
        submenu_image_tiling = wx.Menu()
        for name in sorted(const.IMAGE_TILING):
            new_id = wx.NewIdRef()
            image_tiling_item = submenu_image_tiling.Append(
                new_id, name, kind=wx.ITEM_RADIO
            )
            self.ID_TO_TOOL_ITEM[new_id] = image_tiling_item

            # Save first id item
            if not (flag_tiling):
                self.id_tiling_first = new_id
                flag_tiling = True

        # Add sub itens in the menu
        self.Append(-1, _("Window width and level"), submenu_wl)
        self.Append(-1, _("Pseudo color"), submenu_pseudo_colours)
        self.Append(-1, _("Projection type"), submenu_projection)
        ###self.Append(-1, _("Image Tiling"), submenu_image_tiling)

        # It doesn't work in Linux
        self.Bind(wx.EVT_MENU, self.OnPopup)
        # In Linux the bind must be putted in the submenu
        if sys.platform.startswith("linux") or sys.platform == "darwin":
            submenu_wl.Bind(wx.EVT_MENU, self.OnPopup)
            submenu_pseudo_colours.Bind(wx.EVT_MENU, self.OnPopup)
            submenu_image_tiling.Bind(wx.EVT_MENU, self.OnPopup)
            submenu_projection.Bind(wx.EVT_MENU, self.OnPopup)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.CheckWindowLevelOther, "Check window and level other")
        Publisher.subscribe(self.FirstItemSelect, "Select first item from slice menu")
        Publisher.subscribe(self._close, "Close project data")

        Publisher.subscribe(self._check_projection_menu, "Check projection menu")

    def FirstItemSelect(self):
        item = self.ID_TO_TOOL_ITEM[self.id_wl_first]
        item.Check(True)

        for i in self.pseudo_color_items:
            it = self.pseudo_color_items[i]
            if it.IsChecked():
                it.Check(False)
        item = self.ID_TO_TOOL_ITEM[self.id_pseudo_first]
        item.Check(True)

        #  item = self.ID_TO_TOOL_ITEM[self.id_tiling_first]
        #  item.Check(True)

    def CheckWindowLevelOther(self):
        item = self.ID_TO_TOOL_ITEM[self.other_wl_id]
        item.Check()

    def _check_projection_menu(self, projection_id):
        item = self.projection_items[projection_id]
        item.Check()

    def OnPopup(self, evt):
        id = evt.GetId()
        item = self.ID_TO_TOOL_ITEM[evt.GetId()]
        key = item.GetItemLabelText()
        if key in const.WINDOW_LEVEL.keys():
            window, level = const.WINDOW_LEVEL[key]
            Publisher.sendMessage(
                "Bright and contrast adjustment image", window=window, level=level
            )
            Publisher.sendMessage(
                "Update window level value", window=window, level=level
            )
            #  Publisher.sendMessage('Update window and level text',
            #  "WL: %d  WW: %d"%(level, window))
            Publisher.sendMessage("Update slice viewer")

            # Necessary update the slice plane in the volume case exists
            Publisher.sendMessage("Render volume viewer")

        elif key in const.SLICE_COLOR_TABLE.keys():
            values = const.SLICE_COLOR_TABLE[key]
            Publisher.sendMessage(
                "Change colour table from background image", values=values
            )
            Publisher.sendMessage("Update slice viewer")

            if sys.platform.startswith("linux"):
                for i in self.pseudo_color_items:
                    it = self.pseudo_color_items[i]
                    it.Check(False)

                item.Check()
            self.HideClutDialog()
            self._gen_event = True

        elif key in self.plist_presets:
            values = presets.get_wwwl_preset_colours(self.plist_presets[key])
            Publisher.sendMessage(
                "Change colour table from background image from plist", values=values
            )
            Publisher.sendMessage("Update slice viewer")

            if sys.platform.startswith("linux"):
                for i in self.pseudo_color_items:
                    it = self.pseudo_color_items[i]
                    it.Check(False)

                item.Check()
            self.HideClutDialog()
            self._gen_event = True

        elif key in const.IMAGE_TILING.keys():
            values = const.IMAGE_TILING[key]
            Publisher.sendMessage("Set slice viewer layout", layout=values)
            Publisher.sendMessage("Update slice viewer")

        elif key in PROJECTIONS_ID:
            pid = PROJECTIONS_ID[key]
            Publisher.sendMessage("Set projection type", projection_id=pid)
            Publisher.sendMessage("Reload actual slice")

        elif key == _("Custom"):
            if self.cdialog is None:
                slc = sl.Slice()
                histogram = slc.histogram
                init = int(slc.matrix.min())
                end = int(slc.matrix.max())
                nodes = slc.nodes
                self.cdialog = ClutImagedataDialog(histogram, init, end, nodes)
                self.cdialog.Show()
            else:
                self.cdialog.Show(self._gen_event)

            if sys.platform.startswith("linux"):
                for i in self.pseudo_color_items:
                    it = self.pseudo_color_items[i]
                    it.Check(False)

                item.Check()
            item = self.ID_TO_TOOL_ITEM[evt.GetId()]
            item.Check(True)
            self._gen_event = False

        evt.Skip()

    def HideClutDialog(self):
        if self.cdialog:
            self.cdialog.Hide()

    def _close(self):
        if self.cdialog:
            self.cdialog.Destroy()
            self.cdialog = None
