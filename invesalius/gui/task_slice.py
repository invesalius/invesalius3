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

import wx

try:
    import wx.lib.agw.foldpanelbar as fpb
    import wx.lib.agw.hyperlink as hl
except ImportError:
    import wx.lib.foldpanelbar as fpb
    import wx.lib.hyperlink as hl

import wx.lib.colourselect as csel
import wx.lib.platebtn as pbtn

import invesalius.constants as const
import invesalius.data.slice_ as slice_
import invesalius.gui.dialogs as dlg
import invesalius.gui.widgets.gradient as grad
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.gui.widgets.inv_spinctrl import InvSpinCtrl
from invesalius.i18n import tr as _
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher

BTN_NEW = wx.NewIdRef()

MENU_BRUSH_SQUARE = wx.NewIdRef()
MENU_BRUSH_CIRCLE = wx.NewIdRef()

MENU_BRUSH_ADD = wx.NewIdRef()
MENU_BRUSH_DEL = wx.NewIdRef()
MENU_BRUSH_THRESH = wx.NewIdRef()

MENU_UNIT_MM = wx.NewIdRef()
MENU_UNIT_UM = wx.NewIdRef()
MENU_UNIT_PX = wx.NewIdRef()

MASK_LIST = []


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        backgroud_colour = wx.Colour(255, 255, 255)
        self.SetBackgroundColour(backgroud_colour)
        self.SetAutoLayout(1)

        # Image(s) for buttons
        BMP_ADD = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "object_add.png"), wx.BITMAP_TYPE_PNG)
        # BMP_ADD.SetWidth(25)
        # BMP_ADD.SetHeight(25)

        # Button for creating new surface
        button_new_mask = pbtn.PlateButton(
            self, BTN_NEW, "", BMP_ADD, style=pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        )
        button_new_mask.SetBackgroundColour(self.GetBackgroundColour())
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Fixed hyperlink items
        tooltip = _("Create mask for slice segmentation and editing")
        link_new_mask = hl.HyperLinkCtrl(self, -1, _("Create new mask"))
        link_new_mask.SetUnderlines(False, False, False)
        link_new_mask.SetBold(True)
        link_new_mask.SetColours("BLACK", "BLACK", "BLACK")
        link_new_mask.SetBackgroundColour(self.GetBackgroundColour())
        link_new_mask.SetToolTip(tooltip)
        link_new_mask.AutoBrowse(False)
        link_new_mask.UpdateLink()
        link_new_mask.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkNewMask)

        Publisher.subscribe(self.OnLinkNewMask, "New mask from shortcut")

        # Create horizontal sizers to represent lines in the panel
        line_new = wx.BoxSizer(wx.HORIZONTAL)
        line_new.Add(link_new_mask, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT, 4)
        line_new.Add(button_new_mask, 0, wx.ALL | wx.EXPAND | wx.GROW, 0)

        # Fold panel which contains mask properties and edition tools
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_BACKGROUND)
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_APPWORKSPACE)
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNFACE)
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_DESKTOP)
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_SCROLLBAR)
        # print wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUHILIGHT)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)
        self.fold_panel = fold_panel

        # Button to fold to select region task
        button_next = wx.Button(self, -1, _("Create surface"))
        check_box = wx.CheckBox(self, -1, _("Overwrite last surface"))
        self.check_box = check_box
        if sys.platform != "win32":
            button_next.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
            check_box.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        button_next.Bind(wx.EVT_BUTTON, self.OnButtonNextTask)

        next_btn_sizer = wx.BoxSizer(wx.VERTICAL)
        next_btn_sizer.Add(button_next, 1, wx.ALIGN_RIGHT)

        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(check_box, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Add(next_btn_sizer, 1, wx.EXPAND | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Fit(self)

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_new, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(fold_panel, 1, wx.GROW | wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(line_sizer, 0, wx.GROW | wx.EXPAND)
        main_sizer.AddSpacer(5)
        main_sizer.Fit(self)

        self.SetSizerAndFit(main_sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = main_sizer

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnLinkNewMask()

    def OnButtonNextTask(self, evt):
        overwrite = self.check_box.IsChecked()
        algorithm = "Default"
        options = {}
        to_generate = True
        if self.GetMaskSelected() != -1:
            sl = slice_.Slice()
            if sl.current_mask.was_edited:
                dlgs = dlg.SurfaceDialog()
                if dlgs.ShowModal() == wx.ID_OK:
                    algorithm = dlgs.GetAlgorithmSelected()
                    options = dlgs.GetOptions()
                else:
                    to_generate = False

                dlgs.Destroy()

            if to_generate:
                proj = Project()
                for idx in proj.mask_dict:
                    if proj.mask_dict[idx] is sl.current_mask:
                        mask_index = idx
                        break
                else:
                    return

                method = {"algorithm": algorithm, "options": options}
                srf_options = {
                    "index": mask_index,
                    "name": "",
                    "quality": _("Optimal *"),
                    "fill": False,
                    "keep_largest": False,
                    "overwrite": overwrite,
                }

                Publisher.sendMessage(
                    "Create surface from index",
                    surface_parameters={"method": method, "options": srf_options},
                )
                Publisher.sendMessage("Fold surface task")

        else:
            dlg.InexistentMask()

    def OnLinkNewMask(self, evt=None):
        try:
            evt.data
            evt = None
        except Exception:
            pass

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

    def GetMaskSelected(self):
        return self.fold_panel.GetMaskSelected()


class FoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerFoldPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW, 2)
        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.inner_panel = inner_panel

    def GetMaskSelected(self):
        # x = self.inner_panel.GetMaskSelected()
        return self.inner_panel.GetMaskSelected()


class InnerFoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        # Fold panel and its style settings
        # FIXME: If we dont insert a value in size or if we set wx.DefaultSize,
        # the fold_panel doesnt show. This means that, for some reason, Sizer
        # is not working properly in this panel. It might be on some child or
        # parent panel. Perhaps we need to insert the item into the sizer also...
        # Study this.
        # gbs = wx.GridBagSizer()

        # gbs.AddGrowableRow(0, 1)
        # gbs.AddGrowableCol(0, 1)

        # self.gbs = gbs

        self.last_size = None

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        # sizer.Add(gbs, 1, wx.GROW|wx.EXPAND)
        self.SetSizer(sizer)

        fold_panel = fpb.FoldPanelBar(
            self, -1, wx.DefaultPosition, wx.DefaultSize, 0, fpb.FPB_SINGLE_FOLD
        )
        self.fold_panel = fold_panel

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Mask properties
        item = fold_panel.AddFoldPanel(_("Mask properties"), collapsed=True)
        self.mask_prop_panel = MaskProperties(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(
            item, self.mask_prop_panel, spacing=0, leftSpacing=0, rightSpacing=0
        )

        # Fold 2 - Advanced edition tools
        item = fold_panel.AddFoldPanel(_("Manual edition"), collapsed=True)
        etw = EditionTools(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, etw, spacing=0, leftSpacing=0, rightSpacing=0)
        self.__id_editor = item.GetId()
        self.last_panel_opened = None

        # Fold 3 - Watershed
        item = fold_panel.AddFoldPanel(_("Watershed"), collapsed=True)
        wtw = WatershedTool(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, wtw, spacing=0, leftSpacing=0, rightSpacing=0)
        self.__id_watershed = item.GetId()

        sizer.Add(fold_panel, 1, wx.EXPAND)

        fold_panel.Expand(fold_panel.GetFoldPanel(2))
        self.ResizeFPB()
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        sizer.Layout()
        self.Fit()

        self.fold_panel = fold_panel
        self.last_style = None

        self.__bind_evt()
        self.__bind_pubsub_evt()

    def __calc_best_size(self, panel):
        parent = panel.GetParent()
        _ = panel.Reparent(self)

        # gbs = self.gbs
        # fold_panel = self.fold_panel

        # Calculating the size
        # gbs.AddGrowableRow(0, 1)
        # gbs.AddGrowableRow(0, 1)
        # gbs.Add(panel, (0, 0), flag=wx.EXPAND)
        self.GetSizer().Add(panel, 1, wx.EXPAND)
        # self.SetSizerAndFit(self.GetSizer())
        self.GetSizer().Layout()
        self.GetSizer().Fit(self)
        # gbs.Layout()
        # self.Fit()
        # self.GetSizer().Layout()
        size = panel.GetSize()

        # gbs.Remove(0)
        # gbs.RemoveGrowableRow(0)

        self.GetSizer().Remove(0)
        panel.Reparent(parent)
        panel.SetInitialSize(size)

        # if self.last_size is None or self.last_size.GetHeight() < size.GetHeight():
        # self.SetInitialSize(size)

    def __bind_evt(self):
        self.fold_panel.Bind(fpb.EVT_CAPTIONBAR, self.OnFoldPressCaption)

    def __bind_pubsub_evt(self):
        Publisher.subscribe(self.OnRetrieveStyle, "Retrieve task slice style")
        Publisher.subscribe(self.OnDisableStyle, "Disable task slice style")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnColapsePanel, "Show panel")

    def OnFoldPressCaption(self, evt):
        id = evt.GetTag().GetId()
        closed = evt.GetFoldStatus()

        if self.__id_editor == id:
            if closed:
                Publisher.sendMessage("Disable style", style=const.SLICE_STATE_EDITOR)
                self.last_style = None
            else:
                Publisher.sendMessage("Enable style", style=const.SLICE_STATE_EDITOR)
                self.last_style = const.SLICE_STATE_EDITOR
        elif self.__id_watershed == id:
            if closed:
                Publisher.sendMessage("Disable style", style=const.SLICE_STATE_WATERSHED)
                self.last_style = None
            else:
                Publisher.sendMessage("Enable style", style=const.SLICE_STATE_WATERSHED)
                #  Publisher.sendMessage('Show help message', 'Mark the object and the background')
                self.last_style = const.SLICE_STATE_WATERSHED
        else:
            Publisher.sendMessage("Disable style", style=const.SLICE_STATE_EDITOR)
            self.last_style = None

        evt.Skip()
        wx.CallAfter(self.ResizeFPB)

    def ResizeFPB(self):
        sizeNeeded = self.fold_panel.GetPanelsLength(0, 0)[2]
        self.fold_panel.SetMinSize((self.fold_panel.GetSize()[0], sizeNeeded))
        self.fold_panel.SetSize((self.fold_panel.GetSize()[0], sizeNeeded))

    def OnRetrieveStyle(self):
        if self.last_style == const.SLICE_STATE_EDITOR:
            Publisher.sendMessage("Enable style", style=const.SLICE_STATE_EDITOR)

    def OnDisableStyle(self):
        if self.last_style == const.SLICE_STATE_EDITOR:
            Publisher.sendMessage("Disable style", style=const.SLICE_STATE_EDITOR)

    def OnCloseProject(self):
        self.fold_panel.Expand(self.fold_panel.GetFoldPanel(0))

    def OnColapsePanel(self, panel_id):
        panel_seg_id = {
            const.ID_THRESHOLD_SEGMENTATION: 0,
            const.ID_MANUAL_SEGMENTATION: 1,
            const.ID_WATERSHED_SEGMENTATION: 2,
        }

        try:
            _id = panel_seg_id[panel_id]
            self.fold_panel.Expand(self.fold_panel.GetFoldPanel(_id))
            self.Layout()
        except KeyError:
            pass

    def GetMaskSelected(self):
        # x = self.mask_prop_panel.GetMaskSelected()
        return self.mask_prop_panel.GetMaskSelected()


class MaskProperties(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        ## LINE 1

        # Combo related to mask naem
        combo_mask_name = wx.ComboBox(
            self, -1, "", choices=MASK_LIST, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_mask_name.SetSelection(0) # wx.CB_SORT
        if sys.platform != "win32":
            combo_mask_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_mask_name = combo_mask_name

        # Mask colour
        button_colour = csel.ColourSelect(self, 111, colour=(0, 255, 0), size=(22, -1))
        self.button_colour = button_colour

        # Sizer which represents the first line
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(combo_mask_name, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT, 2)
        line1.Add(button_colour, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 2)

        ### LINE 2
        text_thresh = wx.StaticText(self, -1, _("Set predefined or manual threshold:"))

        ### LINE 3
        THRESHOLD_LIST = [
            "",
        ]
        combo_thresh = wx.ComboBox(
            self,
            -1,
            "",  # size=(15,-1),
            choices=THRESHOLD_LIST,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        combo_thresh.SetSelection(0)
        if sys.platform != "win32":
            combo_thresh.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_thresh = combo_thresh

        ## LINE 4
        gradient = grad.GradientCtrl(self, -1, -5000, 5000, 0, 5000, (0, 255, 0, 100))
        self.gradient = gradient

        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(7)
        sizer.Add(line1, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        sizer.AddSpacer(5)
        sizer.Add(text_thresh, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(2)
        sizer.Add(combo_thresh, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT, 5)

        sizer.AddSpacer(5)
        sizer.Add(gradient, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(7)

        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

        # Non GUI stuff

        proj = Project()
        self.threshold_modes = proj.threshold_modes
        self.threshold_modes_names = []
        self.bind_evt_gradient = True
        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events(self):
        Publisher.subscribe(self.AddMask, "Add mask")
        # TODO: Uncomment
        Publisher.subscribe(self.SetThresholdBounds, "Update threshold limits")
        Publisher.subscribe(self.SetThresholdModes, "Set threshold modes")
        Publisher.subscribe(self.SetItemsColour, "Set GUI items colour")
        Publisher.subscribe(self.SetThresholdValues, "Set threshold values in gradient")
        Publisher.subscribe(self.SelectMaskName, "Select mask name in combo")
        Publisher.subscribe(self.ChangeMaskName, "Change mask name")
        Publisher.subscribe(self.OnRemoveMasks, "Remove masks")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.SetThresholdValues2, "Set threshold values")

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        n = self.combo_mask_name.GetCount()
        for i in range(n - 1, -1, -1):
            self.combo_mask_name.Delete(i)
        n = self.combo_thresh.GetCount()
        for i in range(n - 1, -1, -1):
            self.combo_thresh.Delete(i)

    def OnRemoveMasks(self, mask_indexes):
        for i in mask_indexes:
            self.combo_mask_name.Delete(i)

        if self.combo_mask_name.IsEmpty():
            self.combo_mask_name.SetValue("")
            self.Disable()

    def __bind_events_wx(self):
        self.Bind(grad.EVT_THRESHOLD_CHANGED, self.OnSlideChanged, self.gradient)
        self.Bind(grad.EVT_THRESHOLD_CHANGING, self.OnSlideChanging, self.gradient)
        self.combo_thresh.Bind(wx.EVT_COMBOBOX, self.OnComboThresh)
        self.combo_mask_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        self.button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)

    def SelectMaskName(self, index):
        if index >= 0:
            self.combo_mask_name.SetSelection(index)
        else:
            self.combo_mask_name.SetValue("")

    def ChangeMaskName(self, index, name):
        self.combo_mask_name.SetString(index, name)
        self.combo_mask_name.Refresh()

    def SetThresholdValues(self, threshold_range):
        thresh_min, thresh_max = threshold_range
        self.bind_evt_gradient = False
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)

        self.bind_evt_gradient = True
        thresh = (thresh_min, thresh_max)
        if thresh in Project().threshold_modes.values():
            preset_name = Project().threshold_modes.get_key(thresh)
            index = self.threshold_modes_names.index(preset_name)
            self.combo_thresh.SetSelection(index)
        else:
            index = self.threshold_modes_names.index(_("Custom"))
            self.combo_thresh.SetSelection(index)
            Project().threshold_modes[_("Custom")] = (thresh_min, thresh_max)

    def SetThresholdValues2(self, threshold_range):
        thresh_min, thresh_max = threshold_range
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)
        thresh = (thresh_min, thresh_max)
        if thresh in Project().threshold_modes.values():
            preset_name = Project().threshold_modes.get_key(thresh)
            index = self.threshold_modes_names.index(preset_name)
            self.combo_thresh.SetSelection(index)
        else:
            index = self.threshold_modes_names.index(_("Custom"))
            self.combo_thresh.SetSelection(index)
            Project().threshold_modes[_("Custom")] = (thresh_min, thresh_max)

    def SetItemsColour(self, colour):
        self.gradient.SetColour(colour)
        self.button_colour.SetColour(colour)

    def AddMask(self, mask):
        if self.combo_mask_name.IsEmpty():
            self.Enable()
        mask_name = mask.name
        # mask_thresh = mask.threshold_range
        # mask_colour = [int(c * 255) for c in mask.colour]
        _ = self.combo_mask_name.Append(mask_name)
        #  self.combo_mask_name.SetSelection(index)
        #  self.button_colour.SetColour(mask_colour)
        #  self.gradient.SetColour(mask_colour)
        #  self.combo_mask_name.SetSelection(index)

    def GetMaskSelected(self):
        # x = self.combo_mask_name.GetSelection()
        return self.combo_mask_name.GetSelection()

    def SetThresholdModes(self, thresh_modes_names, default_thresh):
        self.combo_thresh.SetItems(thresh_modes_names)
        self.threshold_modes_names = thresh_modes_names
        proj = Project()
        if isinstance(default_thresh, int):
            self.combo_thresh.SetSelection(default_thresh)
            (thresh_min, thresh_max) = self.threshold_modes[thresh_modes_names[default_thresh]]
        elif default_thresh in proj.threshold_modes.keys():
            index = self.threshold_modes_names.index(default_thresh)
            self.combo_thresh.SetSelection(index)
            thresh_min, thresh_max = self.threshold_modes[default_thresh]

        elif default_thresh in proj.threshold_modes.values():
            preset_name = proj.threshold_modes.get_key(default_thresh)
            index = self.threshold_modes_names.index(preset_name)
            self.combo_thresh.SetSelection(index)
            thresh_min, thresh_max = default_thresh
        else:
            index = self.threshold_modes_names.index(_("Custom"))
            self.combo_thresh.SetSelection(index)
            thresh_min, thresh_max = default_thresh
            proj.threshold_modes[_("Custom")] = (thresh_min, thresh_max)

        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)

    def SetThresholdBounds(self, threshold_range):
        thresh_min = threshold_range[0]
        thresh_max = threshold_range[1]
        self.gradient.SetMinRange(thresh_min)
        self.gradient.SetMaxRange(thresh_max)

    def OnComboName(self, evt):
        # mask_name = evt.GetString()
        mask_index = evt.GetSelection()
        Publisher.sendMessage("Change mask selected", index=mask_index)
        Publisher.sendMessage("Show mask", index=mask_index, value=True)

    def OnComboThresh(self, evt):
        (thresh_min, thresh_max) = Project().threshold_modes[evt.GetString()]
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)
        self.OnSlideChanging(None)
        self.OnSlideChanged(None)

    def OnSlideChanged(self, evt):
        thresh_min = self.gradient.GetMinValue()
        thresh_max = self.gradient.GetMaxValue()
        Publisher.sendMessage("Set threshold values", threshold_range=(thresh_min, thresh_max))
        session = ses.Session()
        session.ChangeProject()

    def OnSlideChanging(self, evt):
        thresh_min = self.gradient.GetMinValue()
        thresh_max = self.gradient.GetMaxValue()
        Publisher.sendMessage("Changing threshold values", threshold_range=(thresh_min, thresh_max))
        session = ses.Session()
        session.ChangeProject()

    def OnSelectColour(self, evt):
        colour = evt.GetValue()[:3]
        self.gradient.SetColour(colour)
        Publisher.sendMessage("Change mask colour", colour=colour)


class EditionTools(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.unit = "mm"

        ## LINE 1
        text1 = wx.StaticText(self, -1, _("Choose brush type, size or operation:"))

        ## LINE 2
        menu = wx.Menu()

        CIRCLE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_circle.png"), wx.BITMAP_TYPE_PNG
        )
        item = menu.Append(MENU_BRUSH_CIRCLE, _("Circle"))
        item.SetBitmap(CIRCLE_BMP)

        SQUARE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_square.png"), wx.BITMAP_TYPE_PNG
        )
        item2 = menu.Append(MENU_BRUSH_SQUARE, _("Square"))
        item2.SetBitmap(SQUARE_BMP)

        bmp_brush_format = {const.BRUSH_CIRCLE: CIRCLE_BMP, const.BRUSH_SQUARE: SQUARE_BMP}
        selected_bmp = bmp_brush_format[const.DEFAULT_BRUSH_FORMAT]

        btn_brush_format = pbtn.PlateButton(
            self, wx.ID_ANY, "", selected_bmp, style=pbtn.PB_STYLE_SQUARE
        )
        btn_brush_format.SetMenu(menu)
        self.btn_brush_format = btn_brush_format

        spin_brush_size = InvSpinCtrl(
            self, -1, value=const.BRUSH_SIZE, min_value=1, max_value=1000, spin_button=False
        )
        # To calculate best width to spinctrl
        spin_brush_size.CalcSizeFromTextSize("MMMM")
        spin_brush_size.Bind(wx.EVT_SPINCTRL, self.OnBrushSize)
        self.spin = spin_brush_size

        self.txt_unit = wx.StaticText(self, -1, "mm")
        self.txt_unit.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

        combo_brush_op = wx.ComboBox(
            self,
            -1,
            "",
            size=(15, -1),
            choices=const.BRUSH_OP_NAME,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        combo_brush_op.SetSelection(const.DEFAULT_BRUSH_OP)
        if sys.platform != "win32":
            combo_brush_op.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_brush_op = combo_brush_op

        # Sizer which represents the second line
        line2 = wx.BoxSizer(wx.HORIZONTAL)
        line2.Add(btn_brush_format, 0, wx.EXPAND | wx.GROW | wx.RIGHT, 5)
        line2.Add(spin_brush_size, 0, wx.ALIGN_CENTER_VERTICAL)
        line2.Add(self.txt_unit, 0, wx.ALIGN_CENTER_VERTICAL)
        line2.Add(combo_brush_op, 1, wx.RIGHT | wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 5)

        ## LINE 3
        text_thresh = wx.StaticText(self, -1, _("Brush threshold range:"))

        ## LINE 4
        gradient_thresh = grad.GradientCtrl(self, -1, 0, 5000, 0, 5000, (0, 0, 255, 100))
        self.gradient_thresh = gradient_thresh
        self.bind_evt_gradient = True

        # Add lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(7)
        sizer.Add(text1, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(2)
        sizer.Add(line2, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)
        sizer.Add(text_thresh, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)
        sizer.Add(gradient_thresh, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(7)
        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events_wx(self):
        self.btn_brush_format.Bind(wx.EVT_MENU, self.OnMenu)
        self.Bind(grad.EVT_THRESHOLD_CHANGED, self.OnGradientChanged, self.gradient_thresh)
        self.combo_brush_op.Bind(wx.EVT_COMBOBOX, self.OnComboBrushOp)

    def __bind_events(self):
        Publisher.subscribe(self.SetThresholdBounds, "Update threshold limits")
        Publisher.subscribe(self.ChangeMaskColour, "Change mask colour")
        Publisher.subscribe(self.SetGradientColour, "Add mask")
        Publisher.subscribe(self._set_brush_size, "Set edition brush size")
        Publisher.subscribe(self._set_threshold_range_gui, "Set edition threshold gui")
        Publisher.subscribe(self.ChangeMaskColour, "Set GUI items colour")

    def ChangeMaskColour(self, colour):
        self.gradient_thresh.SetColour(colour)

    def SetGradientColour(self, mask):
        wx_colour = [c * 255 for c in mask.colour]
        self.gradient_thresh.SetColour(wx_colour)

    def SetThresholdValues(self, threshold_range):
        thresh_min, thresh_max = threshold_range
        self.bind_evt_gradient = False
        self.gradient_thresh.SetMinValue(thresh_min)
        self.gradient_thresh.SetMaxValue(thresh_max)
        self.bind_evt_gradient = True

    def SetThresholdBounds(self, threshold_range):
        thresh_min = threshold_range[0]
        thresh_max = threshold_range[1]
        self.gradient_thresh.SetMinRange(thresh_min)
        self.gradient_thresh.SetMaxRange(thresh_max)
        self.gradient_thresh.SetMinValue(thresh_min)
        self.gradient_thresh.SetMaxValue(thresh_max)

    def OnGradientChanged(self, evt):
        thresh_min = self.gradient_thresh.GetMinValue()
        thresh_max = self.gradient_thresh.GetMaxValue()
        if self.bind_evt_gradient:
            Publisher.sendMessage(
                "Set edition threshold values", threshold_range=(thresh_min, thresh_max)
            )

    def OnMenu(self, evt):
        SQUARE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_square.png"), wx.BITMAP_TYPE_PNG
        )
        CIRCLE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_circle.png"), wx.BITMAP_TYPE_PNG
        )

        brush = {MENU_BRUSH_CIRCLE: const.BRUSH_CIRCLE, MENU_BRUSH_SQUARE: const.BRUSH_SQUARE}
        bitmap = {MENU_BRUSH_CIRCLE: CIRCLE_BMP, MENU_BRUSH_SQUARE: SQUARE_BMP}

        self.btn_brush_format.SetBitmap(bitmap[evt.GetId()])

        Publisher.sendMessage("Set brush format", cursor_format=brush[evt.GetId()])

    def OnBrushSize(self, evt):
        """ """
        # FIXME: Using wx.EVT_SPINCTRL in MacOS it doesnt capture changes only
        # in the text ctrl - so we are capturing only changes on text
        # Strangelly this is being called twice
        Publisher.sendMessage("Set edition brush size", size=self.spin.GetValue())

    def OnContextMenu(self, evt):
        print("Context")
        menu = wx.Menu()
        mm_item = menu.AppendRadioItem(MENU_UNIT_MM, "mm")
        um_item = menu.AppendRadioItem(MENU_UNIT_UM, "µm")
        px_item = menu.AppendRadioItem(MENU_UNIT_PX, "px")

        if self.unit == "mm":
            mm_item.Check()
        elif self.unit == "µm":
            um_item.Check()
        else:
            px_item.Check()

        menu.Bind(wx.EVT_MENU, self.OnSetUnit)
        self.txt_unit.PopupMenu(menu)
        menu.Destroy()

    def _set_threshold_range_gui(self, threshold_range):
        self.SetThresholdValues(threshold_range)

    def _set_brush_size(self, size):
        self.spin.SetValue(size)

    def OnComboBrushOp(self, evt):
        brush_op_id = evt.GetSelection()
        Publisher.sendMessage("Set edition operation", operation=brush_op_id)
        if brush_op_id == const.BRUSH_THRESH:
            self.gradient_thresh.Enable()
        else:
            self.gradient_thresh.Disable()

    def OnSetUnit(self, evt):
        if evt.GetId() == MENU_UNIT_MM:
            self.txt_unit.SetLabel("mm")
        elif evt.GetId() == MENU_UNIT_UM:
            self.txt_unit.SetLabel("µm")
        else:
            self.txt_unit.SetLabel("px")
        self.unit = self.txt_unit.GetLabel()
        Publisher.sendMessage("Set edition brush unit", unit=self.unit)


class WatershedTool(EditionTools):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        ## LINE 1
        text1 = wx.StaticText(self, -1, _("Choose brush type, size or operation:"))

        self.unit = "mm"

        ## LINE 2
        menu = wx.Menu()

        CIRCLE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_circle.png"), wx.BITMAP_TYPE_PNG
        )
        item = menu.Append(MENU_BRUSH_CIRCLE, _("Circle"))
        item.SetBitmap(CIRCLE_BMP)

        SQUARE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_square.png"), wx.BITMAP_TYPE_PNG
        )
        item2 = menu.Append(MENU_BRUSH_SQUARE, _("Square"))
        item2.SetBitmap(SQUARE_BMP)

        bmp_brush_format = {const.BRUSH_CIRCLE: CIRCLE_BMP, const.BRUSH_SQUARE: SQUARE_BMP}
        selected_bmp = bmp_brush_format[const.DEFAULT_BRUSH_FORMAT]

        btn_brush_format = pbtn.PlateButton(
            self, wx.ID_ANY, "", selected_bmp, style=pbtn.PB_STYLE_SQUARE
        )
        btn_brush_format.SetMenu(menu)
        self.btn_brush_format = btn_brush_format

        spin_brush_size = InvSpinCtrl(
            self, -1, value=const.BRUSH_SIZE, min_value=1, max_value=1000, spin_button=False
        )
        # To calculate best width to spinctrl
        spin_brush_size.CalcSizeFromTextSize("MMMM")
        spin_brush_size.Bind(wx.EVT_SPINCTRL, self.OnBrushSize)
        self.spin = spin_brush_size

        self.txt_unit = wx.StaticText(self, -1, "mm")
        self.txt_unit.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

        combo_brush_op = wx.ComboBox(
            self,
            -1,
            "",
            size=(15, -1),
            choices=(_("Foreground"), _("Background"), _("Erase")),
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        combo_brush_op.SetSelection(0)
        if sys.platform != "win32":
            combo_brush_op.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_brush_op = combo_brush_op

        # Sizer which represents the second line
        line2 = wx.BoxSizer(wx.HORIZONTAL)
        line2.Add(btn_brush_format, 0, wx.EXPAND | wx.GROW | wx.RIGHT, 5)
        line2.Add(spin_brush_size, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        line2.Add(self.txt_unit, 0, wx.ALIGN_CENTER_VERTICAL)
        line2.Add(combo_brush_op, 1, wx.RIGHT | wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 5)

        ## LINE 3

        ## LINE 4

        # LINE 5
        check_box = wx.CheckBox(self, -1, _("Overwrite mask"))
        ww_wl_cbox = wx.CheckBox(self, -1, _("Use WW&WL"))
        ww_wl_cbox.SetValue(True)
        self.check_box = check_box
        self.ww_wl_cbox = ww_wl_cbox

        # Line 6
        bmp = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "configuration.png"), wx.BITMAP_TYPE_PNG)
        self.btn_wconfig = wx.BitmapButton(
            self, -1, bitmap=bmp, size=(bmp.GetWidth() + 10, bmp.GetHeight() + 10)
        )
        self.btn_exp_watershed = wx.Button(self, -1, _("Expand watershed to 3D"))

        sizer_btns = wx.BoxSizer(wx.HORIZONTAL)
        sizer_btns.Add(self.btn_wconfig, 0, wx.ALIGN_LEFT | wx.LEFT | wx.TOP | wx.DOWN, 5)
        sizer_btns.Add(self.btn_exp_watershed, 0, wx.GROW | wx.EXPAND | wx.ALL, 5)

        # Add lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(7)
        sizer.Add(text1, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(2)
        sizer.Add(line2, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)
        sizer.Add(check_box, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(2)
        sizer.Add(ww_wl_cbox, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)
        sizer.Add(sizer_btns, 0, wx.EXPAND)
        sizer.AddSpacer(7)
        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_events_wx()
        self.__bind_pubsub_evt()

    def __bind_events_wx(self):
        self.btn_brush_format.Bind(wx.EVT_MENU, self.OnMenu)
        self.combo_brush_op.Bind(wx.EVT_COMBOBOX, self.OnComboBrushOp)
        self.check_box.Bind(wx.EVT_CHECKBOX, self.OnCheckOverwriteMask)
        self.ww_wl_cbox.Bind(wx.EVT_CHECKBOX, self.OnCheckWWWL)
        self.btn_exp_watershed.Bind(wx.EVT_BUTTON, self.OnExpandWatershed)
        self.btn_wconfig.Bind(wx.EVT_BUTTON, self.OnConfig)

    def __bind_pubsub_evt(self):
        Publisher.subscribe(self._set_brush_size, "Set watershed brush size")

    def ChangeMaskColour(self, colour):
        self.gradient_thresh.SetColour(colour)

    def SetGradientColour(self, mask):
        vtk_colour = mask.colour
        wx_colour = [c * 255 for c in vtk_colour]
        self.gradient_thresh.SetColour(wx_colour)

    def SetThresholdValues(self, threshold_range):
        thresh_min, thresh_max = threshold_range
        self.bind_evt_gradient = False
        self.gradient_thresh.SetMinValue(thresh_min)
        self.gradient_thresh.SetMaxValue(thresh_max)
        self.bind_evt_gradient = True

    def SetThresholdBounds(self, threshold_range):
        thresh_min = threshold_range[0]
        thresh_max = threshold_range[1]
        self.gradient_thresh.SetMinRange(thresh_min)
        self.gradient_thresh.SetMaxRange(thresh_max)
        self.gradient_thresh.SetMinValue(thresh_min)
        self.gradient_thresh.SetMaxValue(thresh_max)

    def OnMenu(self, evt):
        SQUARE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_square.png"), wx.BITMAP_TYPE_PNG
        )
        CIRCLE_BMP = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "brush_circle.png"), wx.BITMAP_TYPE_PNG
        )

        brush = {MENU_BRUSH_CIRCLE: const.BRUSH_CIRCLE, MENU_BRUSH_SQUARE: const.BRUSH_SQUARE}
        bitmap = {MENU_BRUSH_CIRCLE: CIRCLE_BMP, MENU_BRUSH_SQUARE: SQUARE_BMP}

        self.btn_brush_format.SetBitmap(bitmap[evt.GetId()])

        Publisher.sendMessage("Set watershed brush format", brush_format=brush[evt.GetId()])

    def OnBrushSize(self, evt):
        """ """
        # FIXME: Using wx.EVT_SPINCTRL in MacOS it doesnt capture changes only
        # in the text ctrl - so we are capturing only changes on text
        # Strangelly this is being called twice
        Publisher.sendMessage("Set watershed brush size", size=self.spin.GetValue())

    def OnContextMenu(self, evt):
        print("Context")
        menu = wx.Menu()
        mm_item = menu.AppendRadioItem(MENU_UNIT_MM, "mm")
        um_item = menu.AppendRadioItem(MENU_UNIT_UM, "µm")
        px_item = menu.AppendRadioItem(MENU_UNIT_PX, "px")

        if self.unit == "mm":
            mm_item.Check()
        elif self.unit == "µm":
            um_item.Check()
        else:
            px_item.Check()

        menu.Bind(wx.EVT_MENU, self.OnSetUnit)
        self.txt_unit.PopupMenu(menu)
        menu.Destroy()

    def _set_brush_size(self, size):
        self.spin.SetValue(size)

    def OnSetUnit(self, evt):
        if evt.GetId() == MENU_UNIT_MM:
            self.txt_unit.SetLabel("mm")
        elif evt.GetId() == MENU_UNIT_UM:
            self.txt_unit.SetLabel("µm")
        else:
            self.txt_unit.SetLabel("px")
        self.unit = self.txt_unit.GetLabel()
        Publisher.sendMessage("Set watershed brush unit", unit=self.unit)

    def OnComboBrushOp(self, evt):
        brush_op = self.combo_brush_op.GetValue()
        Publisher.sendMessage("Set watershed operation", operation=brush_op)

    def OnCheckOverwriteMask(self, evt):
        value = self.check_box.GetValue()
        Publisher.sendMessage("Set overwrite mask", flag=value)

    def OnCheckWWWL(self, evt):
        value = self.ww_wl_cbox.GetValue()
        Publisher.sendMessage("Set use ww wl", use_ww_wl=value)

    def OnConfig(self, evt):
        from invesalius.data.styles import WatershedConfig

        config = WatershedConfig()
        dlg.WatershedOptionsDialog(config).Show()

    def OnExpandWatershed(self, evt):
        Publisher.sendMessage("Expand watershed to 3D AXIAL")
