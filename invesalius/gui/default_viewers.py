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
import wx.lib.agw.fourwaysplitter as fws
import wx.lib.colourselect as csel
import wx.lib.platebtn as pbtn

import invesalius.constants as const
import invesalius.data.viewer_slice as slice_viewer
import invesalius.data.viewer_volume as volume_viewer
import invesalius.gui.widgets.slice_menu as slice_menu_
import invesalius.project as project
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.constants import ID_TO_BMP
from invesalius.gui.widgets.clut_raycasting import (
    EVT_CLUT_CURVE_SELECT,
    EVT_CLUT_CURVE_WL_CHANGE,
    EVT_CLUT_POINT_RELEASE,
    CLUTRaycastingWidget,
)
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50), size=wx.Size(744, 656))

        self.__init_aui_manager()
        self.__bind_events_wx()
        self.__bind_events()
        # self.__init_four_way_splitter()
        # self.__init_mix()

    def __init_aui_manager(self):
        self.aui_manager = wx.aui.AuiManager()
        self.aui_manager.SetManagedWindow(self)

        # TODO: Testar mais e verificar melhor opcao

        # Position
        # volume          | pos = 0
        # sagital         | pos = 1
        # coronal         | pos = 2
        # axial           | pos = 3
        # Automatico: assim que painel eh inserido ele ocupa local mais acima na janela (menor numero de posicao)

        # Layer
        # Layer 0 | Layer 1 | Layer 2 | ...
        # Automatico: todos sao colocados no mesmo layer

        # O que eh o Dockable?

        # Row
        # Row 0 | Row 1
        # Idem ao layer

        # Como funciona Direction?

        # Primeira alternativa:
        # modo: 2 no Layer 0, 2 no Layer 1 por exemplo - posicao automatica (ao inves de Layer pode ser utilizado Row)
        # problema: sash control soh aparece no sentido ertical
        # tentativa de solucionar problema seria utilizar Fixed, mas qdo se aciona maximizar nao maximiza inteiro

        p1 = slice_viewer.Viewer(self, "AXIAL")
        s1 = (
            wx.aui.AuiPaneInfo()
            .Centre()
            .Row(0)
            .Name("Axial Slice")
            .Caption(_("Axial slice"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        p2 = slice_viewer.Viewer(self, "CORONAL")
        s2 = (
            wx.aui.AuiPaneInfo()
            .Centre()
            .Row(0)
            .Name("Coronal Slice")
            .Caption(_("Coronal slice"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        p3 = slice_viewer.Viewer(self, "SAGITAL")
        s3 = (
            wx.aui.AuiPaneInfo()
            .Centre()
            .Row(1)
            .Name("Sagittal Slice")
            .Caption(_("Sagittal slice"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        p4 = VolumeViewerCover(self)
        # p4 = volume_viewer.Viewer(self)
        s4 = (
            wx.aui.AuiPaneInfo()
            .Row(1)
            .Name("Volume")
            .Bottom()
            .Centre()
            .Caption(_("Volume"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        self.s4 = s4
        self.p4 = p4

        menu = slice_menu_.SliceMenu()
        p1.SetPopupMenu(menu)
        p2.SetPopupMenu(menu)
        p3.SetPopupMenu(menu)

        if sys.platform == "win32" or wx.VERSION >= (4, 1):
            self.aui_manager.AddPane(p1, s1)
            self.aui_manager.AddPane(p2, s2)
            self.aui_manager.AddPane(p3, s3)
            self.aui_manager.AddPane(p4, s4)
        else:
            self.aui_manager.AddPane(p4, s4)
            self.aui_manager.AddPane(p3, s3)
            self.aui_manager.AddPane(p2, s2)
            self.aui_manager.AddPane(p1, s1)

        self.aui_manager.Update()

        session = ses.Session()
        if session.GetConfig("mode") != const.MODE_NAVIGATOR:
            Publisher.sendMessage("Hide target button")

    def __bind_events_wx(self):
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_MAXIMIZE, self.OnMaximize)
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_RESTORE, self.OnRestore)

    def __bind_events(self):
        Publisher.subscribe(self.MaximizeViewerVolume, "Set target mode")
        Publisher.subscribe(self._Exit, "Exit")

    def MaximizeViewerVolume(self, enabled=True):
        if enabled:
            self.aui_manager.MaximizePane(
                self.aui_manager.GetAllPanes()[-1]
            )  # Viewer volume is the last pane
            Publisher.sendMessage("Show raycasting widget")
        else:
            self.aui_manager.RestoreMaximizedPane()
            Publisher.sendMessage("Hide raycasting widget")
        self.aui_manager.Update()

    def OnMaximize(self, evt):
        if evt.GetPane().name == self.s4.name:
            Publisher.sendMessage("Show raycasting widget")

    def OnRestore(self, evt):
        if evt.GetPane().name == self.s4.name:
            Publisher.sendMessage("Hide raycasting widget")

    def _Exit(self):
        self.aui_manager.UnInit()


class VolumeInteraction(wx.Panel):
    def __init__(self, parent, id):
        super().__init__(parent, id)
        self.can_show_raycasting_widget = 0
        self.__init_aui_manager()
        # sizer = wx.BoxSizer(wx.HORIZONTAL)
        # sizer.Add(volume_viewer.Viewer(self), 1, wx.EXPAND|wx.GROW)
        # self.SetSizer(sizer)
        self.__bind_events()
        self.__bind_events_wx()
        # sizer.Fit(self)

    def __init_aui_manager(self):
        self.aui_manager = wx.aui.AuiManager()
        self.aui_manager.SetManagedWindow(self)

        p1 = volume_viewer.Viewer(self)
        s1 = (
            wx.aui.AuiPaneInfo().Centre().CloseButton(False).MaximizeButton(False).CaptionVisible(0)
        )
        self.s1 = s1

        self.clut_raycasting = CLUTRaycastingWidget(self, -1)
        self.s2 = (
            wx.aui.AuiPaneInfo()
            .Bottom()
            .BestSize((200, 200))
            .CloseButton(False)
            .MaximizeButton(False)
            .CaptionVisible(0)
            .Hide()
        )

        self.aui_manager.AddPane(p1, s1)
        self.aui_manager.AddPane(self.clut_raycasting, self.s2)
        self.aui_manager.Update()

    def __bind_events_wx(self):
        self.clut_raycasting.Bind(EVT_CLUT_POINT_RELEASE, self.OnPointChanged)
        self.clut_raycasting.Bind(EVT_CLUT_CURVE_SELECT, self.OnCurveSelected)
        self.clut_raycasting.Bind(EVT_CLUT_CURVE_WL_CHANGE, self.OnChangeCurveWL)
        # self.Bind(wx.EVT_SIZE, self.OnSize)
        # self.Bind(wx.EVT_MAXIMIZE, self.OnMaximize)

    def __bind_events(self):
        Publisher.subscribe(self.ShowRaycastingWidget, "Show raycasting widget")
        Publisher.subscribe(self.HideRaycastingWidget, "Hide raycasting widget")
        Publisher.subscribe(self.OnSetRaycastPreset, "Update raycasting preset")
        Publisher.subscribe(self.RefreshPoints, "Refresh raycasting widget points")
        Publisher.subscribe(self.LoadHistogram, "Load histogram")
        Publisher.subscribe(self._Exit, "Exit")

    def __update_curve_wwwl_text(self, curve):
        ww, wl = self.clut_raycasting.GetCurveWWWl(curve)
        Publisher.sendMessage("Set raycasting wwwl", ww=ww, wl=wl, curve=curve)

    def ShowRaycastingWidget(self):
        self.can_show_raycasting_widget = 1
        if self.clut_raycasting.to_draw_points:
            p = self.aui_manager.GetPane(self.clut_raycasting)
            p.Show()
            self.aui_manager.Update()

    def HideRaycastingWidget(self):
        self.can_show_raycasting_widget = 0
        p = self.aui_manager.GetPane(self.clut_raycasting)
        p.Hide()
        self.aui_manager.Update()

    def OnPointChanged(self, evt):
        Publisher.sendMessage("Set raycasting refresh")
        Publisher.sendMessage("Set raycasting curve", curve=evt.GetCurve())
        Publisher.sendMessage("Render volume viewer")

    def OnCurveSelected(self, evt):
        Publisher.sendMessage("Set raycasting curve", curve=evt.GetCurve())
        Publisher.sendMessage("Render volume viewer")

    def OnChangeCurveWL(self, evt):
        curve = evt.GetCurve()
        self.__update_curve_wwwl_text(curve)
        Publisher.sendMessage("Render volume viewer")

    def OnSetRaycastPreset(self):
        preset = project.Project().raycasting_preset
        p = self.aui_manager.GetPane(self.clut_raycasting)
        self.clut_raycasting.SetRaycastPreset(preset)
        if self.clut_raycasting.to_draw_points and self.can_show_raycasting_widget:
            p.Show()
        else:
            p.Hide()
        self.aui_manager.Update()

    def LoadHistogram(self, histogram, init, end):
        self.clut_raycasting.SetRange((init, end))
        self.clut_raycasting.SetHistogramArray(histogram, (init, end))

    def RefreshPoints(self):
        self.clut_raycasting.CalculatePixelPoints()
        self.clut_raycasting.Refresh()

    def _Exit(self):
        self.aui_manager.UnInit()


RAYCASTING_TOOLS = wx.NewIdRef()

ID_TO_NAME = {}
ID_TO_TOOL = {}
ID_TO_TOOL_ITEM = {}
TOOL_STATE = {}
ID_TO_ITEMSLICEMENU = {}
ID_TO_ITEM_3DSTEREO = {}
ID_TO_STEREO_NAME = {}

ICON_SIZE = (32, 32)


class VolumeViewerCover(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(VolumeInteraction(self, -1), 1, wx.EXPAND | wx.GROW)
        sizer.Add(VolumeToolPanel(self), 0, wx.EXPAND | wx.GROW)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class VolumeToolPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        # VOLUME RAYCASTING BUTTON
        BMP_RAYCASTING = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("volume_raycasting.png")), wx.BITMAP_TYPE_PNG
        )
        BMP_SLICE_PLANE = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("slice_plane.png")), wx.BITMAP_TYPE_PNG
        )
        BMP_3D_STEREO = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("3D_glasses.png")), wx.BITMAP_TYPE_PNG
        )
        # BMP_TARGET = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("target.png")), wx.BITMAP_TYPE_PNG)

        self.button_raycasting = pbtn.PlateButton(
            self, -1, "", BMP_RAYCASTING, style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        self.button_raycasting.SetToolTip("Raycasting view")
        self.button_stereo = pbtn.PlateButton(
            self, -1, "", BMP_3D_STEREO, style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        self.button_stereo.SetToolTip("Real 3D")
        self.button_slice_plane = pbtn.PlateButton(
            self, -1, "", BMP_SLICE_PLANE, style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        self.button_slice_plane.SetToolTip("Slices into 3D")
        # self.button_target = pbtn.PlateButton(self, -1,"", BMP_TARGET, style=pbtn.PB_STYLE_SQUARE|pbtn.PB_STYLE_TOGGLE, size=ICON_SIZE)
        # self.button_target.Enable(0)

        # VOLUME VIEW ANGLE BUTTON
        BMP_FRONT = wx.Bitmap(ID_TO_BMP[const.VOL_FRONT][1], wx.BITMAP_TYPE_PNG)
        self.button_view = pbtn.PlateButton(
            self, -1, "", BMP_FRONT, size=(32, 32), style=pbtn.PB_STYLE_SQUARE
        )
        self.button_view.SetToolTip("View plane")

        # VOLUME COLOUR BUTTON
        if sys.platform.startswith("linux"):
            size = (32, 32)
            sp = 2
        else:
            size = (24, 24)
            sp = 5

        self.button_colour = csel.ColourSelect(self, -1, colour=(0, 0, 0), size=size)
        self.button_colour.SetToolTip("Background Colour")

        # SIZER TO ORGANIZE ALL
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.button_colour, 0, wx.ALL, sp)
        sizer.Add(self.button_raycasting, 0, wx.TOP | wx.BOTTOM, 1)
        sizer.Add(self.button_view, 0, wx.TOP | wx.BOTTOM, 1)
        sizer.Add(self.button_slice_plane, 0, wx.TOP | wx.BOTTOM, 1)
        sizer.Add(self.button_stereo, 0, wx.TOP | wx.BOTTOM, 1)
        # sizer.Add(self.button_target, 0, wx.TOP | wx.BOTTOM, 1)
        #  sizer.Add(self.button_3d_mask, 0, wx.TOP | wx.BOTTOM, 1)

        self.navigation_status = False

        # Conditions for enabling Target button:
        self.target_selected = False
        self.track_obj = False

        sizer.Fit(self)

        self.SetSizer(sizer)
        self.SetAutoLayout(1)
        self.Update()
        self.Refresh()

        self.__init_menus()
        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events(self):
        Publisher.subscribe(self.ChangeButtonColour, "Change volume viewer gui colour")
        Publisher.subscribe(self.DisablePreset, "Close project data")
        Publisher.subscribe(self.Uncheck, "Uncheck image plane menu")

    def DisablePreset(self):
        self.off_item.Check(1)

    def __bind_events_wx(self):
        self.button_slice_plane.Bind(wx.EVT_LEFT_DOWN, self.OnButtonSlicePlane)
        self.button_raycasting.Bind(wx.EVT_LEFT_DOWN, self.OnButtonRaycasting)
        self.button_view.Bind(wx.EVT_LEFT_DOWN, self.OnButtonView)
        self.button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_stereo.Bind(wx.EVT_LEFT_DOWN, self.OnButtonStereo)
        # self.button_target.Bind(wx.EVT_LEFT_DOWN, self.OnButtonTarget)

    def OnButtonRaycasting(self, evt):
        # MENU RELATED TO RAYCASTING TYPES
        self.button_raycasting.PopupMenu(self.menu_raycasting)

    def OnButtonStereo(self, evt):
        self.button_stereo.PopupMenu(self.stereo_menu)

    def OnButtonView(self, evt):
        self.button_view.PopupMenu(self.menu_view)

    def OnButtonSlicePlane(self, evt):
        self.button_slice_plane.PopupMenu(self.slice_plane_menu)

    def OnSavePreset(self, evt):
        d = wx.TextEntryDialog(self, _("Preset name"))
        if d.ShowModal() == wx.ID_OK:
            preset_name = d.GetValue()
            Publisher.sendMessage("Save raycasting preset", preset_name=preset_name)

    def __init_menus(self):
        # MENU RELATED TO RAYCASTING TYPES
        menu = self.menu = wx.Menu()
        # print "\n\n"
        # print ">>>>", const.RAYCASTING_TYPES.sort()
        # print "\n\n"
        for name in const.RAYCASTING_TYPES:
            id = wx.NewIdRef()
            item = menu.Append(id, name, kind=wx.ITEM_RADIO)
            if name == const.RAYCASTING_OFF_LABEL:
                self.off_item = item
                item.Check(1)
            ID_TO_NAME[id] = name

        menu.AppendSeparator()
        # MENU RELATED TO RAYCASTING TOOLS
        self.id_cutplane = None
        submenu = wx.Menu()
        for name in const.RAYCASTING_TOOLS:
            id = wx.NewIdRef()
            if not (self.id_cutplane):
                self.id_cutplane = id
            item = submenu.Append(id, name, kind=wx.ITEM_CHECK)
            ID_TO_TOOL[id] = name
            ID_TO_TOOL_ITEM[id] = item
            TOOL_STATE[id] = False
        self.submenu_raycasting_tools = submenu
        menu.Append(RAYCASTING_TOOLS, _("Tools"), submenu)
        menu.Enable(RAYCASTING_TOOLS, 0)

        self.menu_raycasting = menu
        # In MacOS X and Windows, binding parent menu is enough. But
        # not in GNU Linux - in the last it is necessary to bind the
        # submenu
        if sys.platform != "win32":
            submenu.Bind(wx.EVT_MENU, self.OnMenuRaycasting)
        menu.Bind(wx.EVT_MENU, self.OnMenuRaycasting)

        # VOLUME VIEW ANGLE BUTTON
        menu = wx.Menu()
        for id in ID_TO_BMP:
            bmp = wx.Bitmap(ID_TO_BMP[id][1], wx.BITMAP_TYPE_PNG)
            item = menu.Append(id, ID_TO_BMP[id][0])
            item.SetBitmap(bmp)
        menu.Bind(wx.EVT_MENU, self.OnMenuView)
        self.menu_view = menu

        # SLICE PLANES BUTTON
        self.slice_plane_menu = slice_plane_menu = wx.Menu()
        itens = ["Axial", "Coronal", "Sagital"]

        for value in itens:
            new_id = wx.NewIdRef()

            item = slice_plane_menu.Append(new_id, value, kind=wx.ITEM_CHECK)
            ID_TO_ITEMSLICEMENU[new_id] = item

        slice_plane_menu.Bind(wx.EVT_MENU, self.OnMenuPlaneSlice)

        # 3D Stereo Buttons
        self.stereo_menu = stereo_menu = wx.Menu()
        itens = [
            const.STEREO_OFF,
            const.STEREO_RED_BLUE,
            const.STEREO_ANAGLYPH,
            const.STEREO_CRISTAL,
            const.STEREO_INTERLACED,
            const.STEREO_LEFT,
            const.STEREO_RIGHT,
            const.STEREO_DRESDEN,
            const.STEREO_CHECKBOARD,
        ]

        for value in itens:
            new_id = wx.NewIdRef()
            item = stereo_menu.Append(new_id, value, kind=wx.ITEM_RADIO)
            ID_TO_ITEM_3DSTEREO[new_id] = item
            ID_TO_STEREO_NAME[new_id] = value

        stereo_menu.Bind(wx.EVT_MENU, self.OnMenuStereo)

        self.Fit()
        self.Update()

    def DisableVolumeCutMenu(self):
        self.menu.Enable(RAYCASTING_TOOLS, 0)
        item = ID_TO_TOOL_ITEM[self.id_cutplane]
        item.Check(0)

    def BuildRaycastingMenu(self):
        presets = []
        for folder in const.RAYCASTING_PRESETS_FOLDERS:
            presets += [
                filename.split(".")[0]
                for filename in os.listdir(folder)
                if os.path.isfile(os.path.join(folder, filename))
            ]

    def OnMenuPlaneSlice(self, evt):
        id = evt.GetId()
        item = ID_TO_ITEMSLICEMENU[id]
        checked = item.IsChecked()
        label = item.GetItemLabelText()

        if not (checked):
            Publisher.sendMessage("Disable plane", plane_label=label)
        else:
            Publisher.sendMessage("Enable plane", plane_label=label)

    def OnMenuStereo(self, evt):
        id = evt.GetId()
        mode = ID_TO_STEREO_NAME[id]
        Publisher.sendMessage("Set stereo mode", mode=mode)

    def Uncheck(self):
        for item in self.slice_plane_menu.GetMenuItems():
            if item.IsChecked():
                item.Check(0)

    def ChangeButtonColour(self, colour):
        colour = [i * 255 for i in colour]
        self.button_colour.SetColour(colour)

    def OnMenuRaycasting(self, evt):
        """Events from raycasting menu."""
        id = evt.GetId()
        if id in ID_TO_NAME.keys():
            # Raycassting type was selected
            name = ID_TO_NAME[id]
            Publisher.sendMessage("Load raycasting preset", preset_name=ID_TO_NAME[id])
            # Enable or disable tools
            if name != const.RAYCASTING_OFF_LABEL:
                self.menu_raycasting.Enable(RAYCASTING_TOOLS, 1)
            else:
                self.menu_raycasting.Enable(RAYCASTING_TOOLS, 0)

        else:
            # Raycasting tool
            # TODO: In future, when more tools are available
            item = ID_TO_TOOL_ITEM[id]
            # if not item.IsChecked():
            #    for i in ID_TO_TOOL_ITEM.values():
            #        if i is not item:
            #            i.Check(0)
            if not TOOL_STATE[id]:
                Publisher.sendMessage("Enable raycasting tool", tool_name=ID_TO_TOOL[id], flag=1)
                TOOL_STATE[id] = True
                item.Check(1)
            else:
                Publisher.sendMessage("Enable raycasting tool", tool_name=ID_TO_TOOL[id], flag=0)
                TOOL_STATE[id] = False
                item.Check(0)

    def OnMenuView(self, evt):
        """Events from button menus."""
        bmp = wx.Bitmap(ID_TO_BMP[evt.GetId()][1], wx.BITMAP_TYPE_PNG)
        self.button_view.SetBitmapSelected(bmp)

        Publisher.sendMessage("Set volume view angle", view=evt.GetId())
        self.Refresh()

    def OnSelectColour(self, evt):
        colour = [i / 255.0 for i in evt.GetValue()]
        Publisher.sendMessage("Change volume viewer background colour", colour=colour)
