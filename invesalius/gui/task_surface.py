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
import wx.lib.scrolledpanel as scrolled

import invesalius.constants as const
import invesalius.data.slice_ as slice_
import invesalius.gui.dialogs as dlg
from invesalius import inv_paths
from invesalius.gui.widgets.inv_spinctrl import InvSpinCtrl
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

# INTERPOLATION_MODE_LIST = ["Cubic", "Linear", "NearestNeighbor"]
MIN_TRANSPARENCY = 0
MAX_TRANSPARENCY = 100

#############
BTN_NEW = wx.NewIdRef()
MENU_SQUARE = wx.NewIdRef()
MENU_CIRCLE = wx.NewIdRef()

OP_LIST = [_("Draw"), _("Erase"), _("Threshold")]


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 0, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

        # select mask - combo
        # mesh quality - combo?
        # apply button
        # Contour - slider
        # enable / disable Fill holes


class InnerTaskPanel(scrolled.ScrolledPanel):
    def __init__(self, parent):
        scrolled.ScrolledPanel.__init__(self, parent)
        default_colour = self.GetBackgroundColour()
        backgroud_colour = wx.Colour(255, 255, 255)
        self.SetBackgroundColour(backgroud_colour)
        self.SetAutoLayout(1)

        BMP_ADD = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "object_add.png"), wx.BITMAP_TYPE_PNG)
        # BMP_ADD.SetWidth(25)
        # BMP_ADD.SetHeight(25)

        # Button for creating new surface
        button_new_surface = pbtn.PlateButton(
            self, BTN_NEW, "", BMP_ADD, style=pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        )
        button_new_surface.SetBackgroundColour(self.GetBackgroundColour())
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Fixed hyperlink items
        tooltip = _("Create 3D surface based on a mask")
        link_new_surface = hl.HyperLinkCtrl(self, -1, _("Create new 3D surface"))
        link_new_surface.SetUnderlines(False, False, False)
        link_new_surface.SetBold(True)
        link_new_surface.SetColours("BLACK", "BLACK", "BLACK")
        link_new_surface.SetBackgroundColour(self.GetBackgroundColour())
        link_new_surface.SetToolTip(tooltip)
        link_new_surface.AutoBrowse(False)
        link_new_surface.UpdateLink()
        link_new_surface.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkNewSurface)

        Publisher.subscribe(self.OnLinkNewSurface, "Open create surface dialog")
        # Create horizontal sizers to represent lines in the panel
        line_new = wx.BoxSizer(wx.HORIZONTAL)
        line_new.Add(link_new_surface, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT, 4)
        line_new.Add(button_new_surface, 0, wx.ALL | wx.EXPAND | wx.GROW, 0)

        # Folde panel which contains surface properties and quality
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)

        # Button to fold to select region task
        button_next = wx.Button(self, -1, _("Next step"))
        if sys.platform != "win32":
            button_next.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        button_next.Bind(wx.EVT_BUTTON, self.OnButtonNextTask)

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_new, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(fold_panel, 0, wx.GROW | wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(button_next, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 5)
        main_sizer.Fit(self)

        self.SetSizerAndFit(main_sizer)
        self.Update()
        # self.SetAutoLayout(1)

        self.sizer = main_sizer

        self.SetupScrolling()

        self.Bind(wx.EVT_SIZE, self.OnSize)

    def OnSize(self, evt):
        self.SetupScrolling()

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnLinkNewSurface()

    def OnButtonNextTask(self, evt):
        if evt:
            Publisher.sendMessage("Fold export task")
            evt.Skip()

    def OnLinkNewSurface(self, evt=None):
        try:
            evt = evt.data
            evt = None
        except Exception:
            pass

        # import invesalius.gui.dialogs as dlg
        sl = slice_.Slice()

        if sl.current_mask is None:
            dlg.InexistentMask()
            return

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
            ## Retrieve information from dialog
            # (mask_index, surface_name, surface_quality, fill_holes,\
            # keep_largest) = dialog.GetValue()

            ## Retrieve information from mask
            # proj = prj.Project()
            # mask = proj.mask_dict[mask_index]

            ## Send all information so surface can be created
            # surface_data = [proj.imagedata,
            # mask.colour,
            # mask.threshold_range,
            # mask.edited_points,
            # False, # overwrite
            # surface_name,
            # surface_quality,
            # fill_holes,
            # keep_largest]

            surface_options = dialog.GetValue()

            Publisher.sendMessage("Create surface from index", surface_parameters=surface_options)
        dialog.Destroy()
        if evt:
            evt.Skip()


class FoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(50, 700))

        inner_panel = InnerFoldPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 0, wx.EXPAND | wx.GROW, 2)
        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)


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
        fold_panel = fpb.FoldPanelBar(
            self, -1, wx.DefaultPosition, wx.DefaultSize, 0, fpb.FPB_SINGLE_FOLD
        )

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Surface properties
        item = fold_panel.AddFoldPanel(_("Surface properties"), collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(
            item, SurfaceProperties(item), spacing=0, leftSpacing=0, rightSpacing=0
        )

        # Fold 2 - Surface tools
        item = fold_panel.AddFoldPanel(_("Advanced options"), collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(
            item, SurfaceTools(item), spacing=0, leftSpacing=0, rightSpacing=0
        )

        # fold_panel.AddFoldPanelWindow(item, QualityAdjustment(item), Spacing= 0,
        #                              leftSpacing=0, rightSpacing=0)
        # fold_panel.Expand(fold_panel.GetFoldPanel(1))

        self.fold_panel = fold_panel
        self.__bind_evt()

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 1, wx.GROW | wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

        fold_panel.Expand(fold_panel.GetFoldPanel(1))
        self.ResizeFPB()
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

    def __bind_evt(self):
        self.fold_panel.Bind(fpb.EVT_CAPTIONBAR, self.OnFoldPressCaption)

    def OnFoldPressCaption(self, evt):
        evt.Skip()
        wx.CallAfter(self.ResizeFPB)

    def ResizeFPB(self):
        sizeNeeded = self.fold_panel.GetPanelsLength(0, 0)[2]
        self.fold_panel.SetMinSize((self.fold_panel.GetSize()[0], sizeNeeded))
        self.fold_panel.SetSize((self.fold_panel.GetSize()[0], sizeNeeded))


BTN_LARGEST = wx.NewIdRef()
BTN_SPLIT = wx.NewIdRef()
BTN_SEEDS = wx.NewIdRef()


class SurfaceTools(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        # self.SetBackgroundColour(wx.Colour(255,255,255))
        self.SetAutoLayout(1)

        # Fixed hyperlink items
        tooltip = _("Automatically select largest disconnected region and create new surface")
        link_largest = hl.HyperLinkCtrl(self, -1, _("Select largest surface"))
        link_largest.SetUnderlines(False, False, False)
        link_largest.SetColours("BLACK", "BLACK", "BLACK")
        link_largest.SetToolTip(tooltip)
        link_largest.AutoBrowse(False)
        link_largest.UpdateLink()
        link_largest.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkLargest)

        tooltip = _("Automatically select disconnected regions and create a new surface per region")
        link_split_all = hl.HyperLinkCtrl(self, -1, _("Split all disconnected surfaces"))
        link_split_all.SetUnderlines(False, False, False)
        link_split_all.SetColours("BLACK", "BLACK", "BLACK")
        link_split_all.SetToolTip(tooltip)
        link_split_all.AutoBrowse(False)
        link_split_all.UpdateLink()
        link_split_all.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkSplit)

        tooltip = _("Manually insert seeds of regions of interest and create a new surface")
        link_seeds = hl.HyperLinkCtrl(self, -1, _("Select regions of interest..."))
        link_seeds.SetUnderlines(False, False, False)
        link_seeds.SetColours("BLACK", "BLACK", "BLACK")
        link_seeds.SetToolTip(tooltip)
        link_seeds.AutoBrowse(False)
        link_seeds.UpdateLink()
        link_seeds.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkSeed)

        # Image(s) for buttons
        img_largest = wx.Image(
            os.path.join(inv_paths.ICON_DIR, "connectivity_largest.png"), wx.BITMAP_TYPE_PNG
        )
        img_largest.Rescale(25, 25)
        bmp_largest = img_largest.ConvertToBitmap()

        img_split_all = wx.Image(
            os.path.join(inv_paths.ICON_DIR, "connectivity_split_all.png"), wx.BITMAP_TYPE_PNG
        )
        img_split_all.Rescale(25, 25)
        bmp_split_all = img_split_all.ConvertToBitmap()

        img_seeds = wx.Image(
            os.path.join(inv_paths.ICON_DIR, "connectivity_manual.png"), wx.BITMAP_TYPE_PNG
        )
        img_seeds.Rescale(25, 25)
        bmp_seeds = img_seeds.ConvertToBitmap()

        # Buttons related to hyperlinks
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_style_plus = button_style | pbtn.PB_STYLE_TOGGLE

        button_split = pbtn.PlateButton(self, BTN_SPLIT, "", bmp_split_all, style=button_style)
        button_largest = pbtn.PlateButton(self, BTN_LARGEST, "", bmp_largest, style=button_style)
        button_seeds = pbtn.PlateButton(self, BTN_SEEDS, "", bmp_seeds, style=button_style_plus)

        self.button_seeds = button_seeds

        # When using PlaneButton, it is necessary to bind events from parent win
        self.Bind(wx.EVT_BUTTON, self.OnButton)
        self.Bind(wx.EVT_TOGGLEBUTTON, self.OnToggleButton)

        # Tags and grid sizer for fixed items
        flag_link = wx.EXPAND | wx.GROW | wx.LEFT | wx.TOP
        flag_button = wx.EXPAND | wx.GROW

        # fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=2, vgap=0)
        fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=2, vgap=0)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany(
            [
                (link_largest, 1, flag_link, 3),
                (button_largest, 0, flag_button),
                (link_seeds, 1, flag_link, 3),
                (button_seeds, 0, flag_button),
                (link_split_all, 1, flag_link, 3),
                (button_split, 0, flag_button),
            ]
        )

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(fixed_sizer, 0, wx.GROW | wx.EXPAND | wx.TOP, 5)

        # Update main sizer and panel layout
        self.SetSizerAndFit(main_sizer)
        self.Update()
        self.sizer = main_sizer

    def OnLinkLargest(self, evt):
        self.SelectLargest()

    def OnLinkSplit(self, evt):
        self.SplitSurface()

    def OnLinkSeed(self, evt):
        self.button_seeds._SetState(not self.button_seeds.GetState())
        self.button_seeds.Refresh()
        self.SelectSeed()

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_LARGEST:
            self.SelectLargest()
        elif id == BTN_SPLIT:
            self.SplitSurface()
        else:
            self.SelectSeed()

    def OnToggleButton(self, evt):
        id = evt.GetId()
        if id == BTN_SEEDS:
            self.button_seeds._SetState(self.button_seeds.IsPressed())
            self.button_seeds.Refresh()
            self.SelectSeed()

    def SelectLargest(self):
        Publisher.sendMessage("Create surface from largest region")

    def SplitSurface(self):
        Publisher.sendMessage("Split surface")

    def SelectSeed(self):
        if self.button_seeds.GetState() == 1:
            self.StartSeeding()
        else:
            self.EndSeeding()

    def StartSeeding(self):
        print("Start Seeding")
        Publisher.sendMessage("Enable style", style=const.VOLUME_STATE_SEED)
        Publisher.sendMessage("Create surface by seeding - start")

    def EndSeeding(self):
        print("End Seeding")
        Publisher.sendMessage("Disable style", style=const.VOLUME_STATE_SEED)
        Publisher.sendMessage("Create surface by seeding - end")


class SurfaceProperties(scrolled.ScrolledPanel):
    def __init__(self, parent):
        scrolled.ScrolledPanel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.surface_list = []

        ## LINE 1

        # Combo related to mask naem
        combo_surface_name = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        self.combo_surface_name = combo_surface_name

        # Mask colour
        button_colour = csel.ColourSelect(self, -1, colour=(0, 0, 255), size=(22, -1))
        button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_colour = button_colour

        # Sizer which represents the first line
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(combo_surface_name, 1, wx.LEFT | wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT, 7)
        line1.Add(button_colour, 0, wx.TOP | wx.RIGHT, 7)

        ## LINE 2

        text_transparency = wx.StaticText(self, -1, _("Transparency:"))

        slider_transparency = wx.Slider(
            self, -1, 0, MIN_TRANSPARENCY, MAX_TRANSPARENCY, style=wx.SL_HORIZONTAL
        )  # |wx.SL_AUTOTICKS)
        slider_transparency.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider_transparency.Bind(wx.EVT_SLIDER, self.OnTransparency)
        self.slider_transparency = slider_transparency

        ## MIX LINE 2 AND 3
        flag_link = wx.EXPAND | wx.GROW | wx.RIGHT
        flag_slider = wx.EXPAND | wx.GROW | wx.LEFT | wx.TOP
        # flag_combo = wx.EXPAND | wx.GROW | wx.LEFT

        fixed_sizer = wx.BoxSizer(wx.HORIZONTAL)
        fixed_sizer.AddMany(
            [(text_transparency, 0, flag_link, 0), (slider_transparency, 1, flag_slider, 4)]
        )

        # LINE 4
        # cb = wx.CheckBox(self, -1, "Fill largest surface holes")
        # cb.SetValue(True)

        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(line1, 1, wx.GROW | wx.EXPAND | wx.TOP, 10)
        sizer.Add(fixed_sizer, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)
        # sizer.Add(cb, 0, wx.GROW|wx.EXPAND|wx.RIGHT|wx.LEFT|wx.TOP|wx.BOTTOM, 5)
        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        # self.SetAutoLayout(1)

        self.SetupScrolling()

        self.Bind(wx.EVT_SIZE, self.OnResize)

        self.__bind_events()

    def OnResize(self, evt):
        self.SetupScrolling()

    def __bind_events(self):
        Publisher.subscribe(self.InsertNewSurface, "Update surface info in GUI")
        Publisher.subscribe(self.ChangeSurfaceName, "Change surface name")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnRemoveSurfaces, "Remove surfaces")

    def OnRemoveSurfaces(self, surface_indexes):
        s = self.combo_surface_name.GetSelection()
        ns = 0

        old_dict = self.surface_list
        new_dict = []
        i = 0
        for n, (name, index) in enumerate(old_dict):
            if n not in surface_indexes:
                new_dict.append([name, i])
                if s == n:
                    ns = i
                i += 1
        self.surface_list = new_dict

        self.combo_surface_name.SetItems([n[0] for n in self.surface_list])

        if self.surface_list:
            self.combo_surface_name.SetSelection(ns)

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        n = self.combo_surface_name.GetCount()
        for i in range(n - 1, -1, -1):
            self.combo_surface_name.Delete(i)
        self.surface_list = []

    def ChangeSurfaceName(self, index, name):
        self.surface_list[index][0] = name
        self.combo_surface_name.SetString(index, name)

    def InsertNewSurface(self, surface):
        index = surface.index
        name = surface.name
        colour = [int(value * 255) for value in surface.colour]
        i = 0
        try:
            i = self.surface_list.index([name, index])
            overwrite = True
        except ValueError:
            overwrite = False

        if overwrite:
            self.surface_list[i] = [name, index]
        else:
            self.surface_list.append([name, index])
            i = len(self.surface_list) - 1

        self.combo_surface_name.SetItems([n[0] for n in self.surface_list])
        self.combo_surface_name.SetSelection(i)
        transparency = 100 * surface.transparency
        # print("Button color: ", colour)
        self.button_colour.SetColour(colour)
        self.slider_transparency.SetValue(int(transparency))
        #  Publisher.sendMessage('Update surface data', (index))

    def OnComboName(self, evt):
        # surface_name = evt.GetString()
        surface_index = evt.GetSelection()
        Publisher.sendMessage(
            "Change surface selected", surface_index=self.surface_list[surface_index][1]
        )

    def OnSelectColour(self, evt):
        colour = [value / 255.0 for value in evt.GetValue()]
        Publisher.sendMessage(
            "Set surface colour",
            surface_index=self.combo_surface_name.GetSelection(),
            colour=colour,
        )

    def OnTransparency(self, evt):
        transparency = evt.GetInt() / float(MAX_TRANSPARENCY)
        Publisher.sendMessage(
            "Set surface transparency",
            surface_index=self.combo_surface_name.GetSelection(),
            transparency=transparency,
        )


class QualityAdjustment(wx.Panel):
    def __init__(self, parent):
        import invesalius.constants as const

        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        # LINE 1

        combo_quality = wx.ComboBox(
            self,
            -1,
            "",
            choices=const.SURFACE_QUALITY.keys()
            or [
                "",
            ],
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        combo_quality.SetSelection(3)
        combo_quality.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        # combo_quality.Bind(wx.EVT_COMBOBOX, self.OnComboQuality)

        # LINE 2
        check_decimate = wx.CheckBox(self, -1, "")

        text_decimate = wx.StaticText(self, -1, _("Decimate resolution:"))

        spin_decimate = InvSpinCtrl(self, -1, value=30, min_value=1, max_value=100, size=(30, 50))
        # spin_decimate.Bind(wx.EVT_TEXT, self.OnDecimate)

        # LINE 3
        check_smooth = wx.CheckBox(self, -1, "")

        text_smooth = wx.StaticText(self, -1, _("Smooth iterations:"))

        spin_smooth = InvSpinCtrl(self, -1, value=0, min_value=1, max_values=100, size=(30, 50))

        # MIXED LINE 2 AND 3
        flag_link = wx.EXPAND | wx.GROW | wx.RIGHT | wx.LEFT
        flag_slider = wx.EXPAND | wx.GROW | wx.LEFT | wx.TOP
        flag_combo = wx.EXPAND | wx.GROW | wx.LEFT

        fixed_sizer = wx.FlexGridSizer(rows=2, cols=3, hgap=2, vgap=0)
        fixed_sizer.AddMany(
            [
                (check_decimate, 0, flag_combo, 2),
                (text_decimate, 0, flag_slider, 7),
                (spin_decimate, 1, flag_link, 14),
                (check_smooth, 0, flag_combo, 2),
                (text_smooth, 0, flag_slider, 7),
                (spin_smooth, 1, flag_link, 14),
            ]
        )
        fixed_sizer.AddGrowableCol(2)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(combo_quality, 1, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        sizer.Add(fixed_sizer, 0, wx.LEFT | wx.RIGHT, 5)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

    def OnComboQuality(self, evt):
        print(f"TODO: Send Signal - Change surface quality: {evt.GetString()}")
