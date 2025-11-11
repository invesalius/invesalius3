import os
import sys

import wx
import wx.aui
import wx.lib.agw.fourwaysplitter as fws
import wx.lib.colourselect as csel
import wx.lib.platebtn as pbtn

import invesalius.constants as const
import invesalius.data.viewer_volume as volume_viewer
import invesalius.project as project
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
from invesalius.utils import Singleton

RAYCASTING_TOOLS = wx.NewIdRef()

ID_TO_NAME = {}
ID_TO_TOOL = {}
ID_TO_TOOL_ITEM = {}
TOOL_STATE = {}
ID_TO_ITEMSLICEMENU = {}
ID_TO_ITEM_3DSTEREO = {}
ID_TO_STEREO_NAME = {}

ICON_SIZE = (32, 32)


class NavigationWindowManager(metaclass=Singleton):
    def __init__(self, parent_wx_window, aui_manager):
        self.parent = parent_wx_window
        self.aui_manager = aui_manager
        self.nav_windows = {}
        self.CoilAssociation = []
        self.multitargetMode = False

        # Init DualNavigation mode, It is a provisional way to navigate with two simultaneous targets.
        self.create_navigation_window()
        self.create_navigation_window(False)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnSetSimultaneousMode, "Set simultaneous multicoil mode")
        Publisher.subscribe(self.UpdateArrowPose, "Update object arrow matrix")
        Publisher.subscribe(
            self.UpdateEfieldPointLocation, "Update point location for e-field calculation"
        )
        Publisher.subscribe(self.GetEnorm, "Get enorm")
        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")
        Publisher.subscribe(self.OnUpdateCoilPose, "Update coil pose")

    def GetEnorm(self, enorm_data, plot_vector, coil_name):
        window = self.getWindowByCoil(coil_name)
        if window:
            window.volume_interaction.volume_viewer_instance.GetEnorm(enorm_data, plot_vector)

    def UpdateEfieldPointLocation(self, m_img, coord, queue_IDs, coil_name):
        window = self.getWindowByCoil(coil_name)
        if window:
            window.volume_interaction.volume_viewer_instance.UpdateEfieldPointLocation(
                m_img, coord, queue_IDs
            )

    def UpdateArrowPose(self, m_img, coord, flag, coil_name):
        window = self.getWindowByCoil(coil_name)
        if window:
            window.volume_interaction.volume_viewer_instance.UpdateArrowPose(m_img, coord, flag)

    def getWindowByCoil(self, coil_name):
        if self.multitargetMode:
            window = None
            for reg_window in self.nav_windows.values():
                if reg_window["coil"] == coil_name:
                    window = reg_window["window"]
                    break
        else:
            window = self.nav_windows[0]["window"]

        return window

    def OnUpdateCoilPose(self, m_img, coord, robot_ID, coil_name):
        window = self.getWindowByCoil(coil_name)
        if window:
            window.volume_interaction.volume_viewer_instance.OnUpdateCoilPose(
                m_img, coord, robot_ID, coil_name
            )

    def SetTarget(self, marker, robot_ID):
        window = self.getWindowByCoil(marker.coil)
        if window:
            window.volume_interaction.volume_viewer_instance.OnSetTarget(marker, robot_ID)
            window.volume_interaction.volume_viewer_instance.SetTargetMode(True)
            self.update_layout()

    def UnsetTarget(self, marker, robot_ID):
        window = self.getWindowByCoil(marker.coil)
        if window:
            window.volume_interaction.volume_viewer_instance.OnUnsetTarget(marker, robot_ID)
            window.volume_interaction.volume_viewer_instance.SetTargetMode(False)
            self.update_layout()

    def OnSetSimultaneousMode(self, state, coils_list):
        self.CoilAssociation = coils_list
        if state:
            for i, coil in enumerate(self.CoilAssociation):
                self.nav_windows[i]["coil"] = coil
                pane_info = self.aui_manager.GetPane(self.nav_windows[i]["window"])
                pane_info.Caption(_("Volume") + f" - {coil}")
        else:
            pane_info = self.aui_manager.GetPane(self.nav_windows[0]["window"])
            pane_info.Caption(_("Volume"))

    def create_navigation_window(self, showSensors=True):
        new_window = VolumeViewerCover(self.parent, showSensors)
        self.nav_windows[len(self.nav_windows)] = {"window": new_window, "coil": None}
        return new_window

    def add_window_to_layout(self, window, row):
        info = (
            wx.aui.AuiPaneInfo()
            .Name(f"Volume_{window.GetId()}")
            .Caption(_("Volume"))
            .Centre()
            .Row(row)
            .MaximizeButton(True)
            .CloseButton(False)
        )
        info.Hide() if row > 1 else None
        self.aui_manager.AddPane(window, info)

    def destroy_navigation_window(self, window_id):
        if window_id in self.nav_windows:
            window = self.nav_windows[window_id]
            self.aui_manager.DetachPane(window)
            window.CleanupAndDestroy()
            del self.nav_windows[window_id]
            self.update_layout()

    def update_layout(self):
        num_windows = len(self.nav_windows)
        if num_windows == 0:
            return

        for i, window in enumerate(self.nav_windows.values()):
            pane_info = self.aui_manager.GetPane(window["window"])
            pane_info.Row(1).Layer(i)

        self.aui_manager.Update()

        scale_factor = 0.84 if self.multitargetMode else 1
        zoom_raycasting = 1.8 if self.multitargetMode else 2

        Publisher.sendMessage("Update size sensors", scale_factor=scale_factor)
        Publisher.sendMessage("Render volume viewer")
        Publisher.sendMessage("Render raycasting", zoom_raycasting=zoom_raycasting)

    def SetDualMode(self, state):
        window = self.nav_windows[len(self.nav_windows) - 1]["window"]
        self.multitargetMode = state
        print("Set dual mode:", state)
        if state:
            self.aui_manager.GetPane(window).Show()
        else:
            self.aui_manager.GetPane(window).Hide()
        self.update_layout()

    def GetMainView(self):
        if self.multitargetMode:
            return None
        else:
            return self.nav_windows[0]["window"]


class VolumeViewerCover(wx.Panel):
    def __init__(self, parent, showSensors):
        wx.Panel.__init__(self, parent)

        self.volume_interaction = VolumeInteraction(self, -1, showSensors=showSensors)
        self.volume_tool_panel = VolumeToolPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.volume_interaction, 1, wx.EXPAND | wx.GROW)
        sizer.Add(self.volume_tool_panel, 0, wx.EXPAND | wx.GROW)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

    def CleanupAndDestroy(self):
        self.volume_interaction.Cleanup()
        self.volume_tool_panel.Cleanup()
        self.Destroy()


class VolumeInteraction(wx.Panel):
    def __init__(self, parent, id, showSensors):
        super().__init__(parent, id)
        self.can_show_raycasting_widget = 0
        self.showSensors = showSensors
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

        p1 = volume_viewer.Viewer(self, showSensors=self.showSensors)
        self.volume_viewer_instance = p1
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
        Publisher.subscribe(self.OnRenderRaycasting, "Render raycasting")
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

    def OnRenderRaycasting(self, zoom_raycasting):
        self.clut_raycasting.Refresh()
        self.aui_manager.Update()
        if self.volume_viewer_instance.target_coord is None:
            return
        self.volume_viewer_instance.ren.ResetCamera()
        self.volume_viewer_instance.target_guide_renderer.ResetCamera()
        self.volume_viewer_instance.target_guide_renderer.GetActiveCamera().Zoom(zoom_raycasting)
        self.volume_viewer_instance.UpdateRender()

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

    def Cleanup(self):
        Publisher.unsubscribe(self.ShowRaycastingWidget, "Show raycasting widget")
        Publisher.unsubscribe(self.HideRaycastingWidget, "Hide raycasting widget")
        Publisher.unsubscribe(self.OnSetRaycastPreset, "Update raycasting preset")
        Publisher.unsubscribe(self.RefreshPoints, "Refresh raycasting widget points")
        Publisher.unsubscribe(self.LoadHistogram, "Load histogram")
        Publisher.unsubscribe(self._Exit, "Exit")

        if self.volume_viewer_instance:
            self.volume_viewer_instance.Cleanup()


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

    def Cleanup(self):
        Publisher.unsubscribe(self.ChangeButtonColour, "Change volume viewer gui colour")
        Publisher.unsubscribe(self.DisablePreset, "Close project data")
        Publisher.unsubscribe(self.Uncheck, "Uncheck image plane menu")
