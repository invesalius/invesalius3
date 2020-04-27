#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------
import sys
import os

import wx
import wx.lib.agw.fourwaysplitter as fws
from pubsub import pub as Publisher

import invesalius.data.viewer_slice as slice_viewer
import invesalius.data.viewer_volume as volume_viewer
import invesalius.project as project
import invesalius.gui.widgets.slice_menu as slice_menu_


from invesalius.gui.widgets.clut_raycasting import CLUTRaycastingWidget, \
        EVT_CLUT_POINT_RELEASE, EVT_CLUT_CURVE_SELECT, \
        EVT_CLUT_CURVE_WL_CHANGE

from invesalius.constants import ID_TO_BMP
from invesalius import inv_paths

import invesalius.session as ses
import invesalius.constants as const

class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                          size=wx.Size(744, 656))

        self.__init_aui_manager()
        self.__bind_events_wx()
        self.__bind_events()
        #self.__init_four_way_splitter()
        #self.__init_mix()

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
        s1 = wx.aui.AuiPaneInfo().Centre().Row(0).\
             Name("Axial Slice").Caption(_("Axial slice")).\
             MaximizeButton(True).CloseButton(False)

        p2 = slice_viewer.Viewer(self, "CORONAL")
        s2 = wx.aui.AuiPaneInfo().Centre().Row(0).\
             Name("Coronal Slice").Caption(_("Coronal slice")).\
             MaximizeButton(True).CloseButton(False)

        p3 = slice_viewer.Viewer(self, "SAGITAL")
        s3 = wx.aui.AuiPaneInfo().Centre().Row(1).\
             Name("Sagittal Slice").Caption(_("Sagittal slice")).\
             MaximizeButton(True).CloseButton(False)

        p4 = VolumeViewerCover(self)
        #p4 = volume_viewer.Viewer(self)
        s4 = wx.aui.AuiPaneInfo().Row(1).Name("Volume").\
             Bottom().Centre().Caption(_("Volume")).\
             MaximizeButton(True).CloseButton(False)

        self.s4 = s4
        self.p4 = p4

        menu = slice_menu_.SliceMenu()
        p1.SetPopupMenu(menu)
        p2.SetPopupMenu(menu)
        p3.SetPopupMenu(menu)


        if sys.platform == 'win32' or wx.VERSION >= (4, 1):
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

        if int(ses.Session().mode) != const.MODE_NAVIGATOR:
            Publisher.sendMessage('Deactive target button')

    def __bind_events_wx(self):
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_MAXIMIZE, self.OnMaximize)
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_RESTORE, self.OnRestore)

    def __bind_events(self):
        Publisher.subscribe(self._Exit, 'Exit')

    def OnMaximize(self, evt):
        if evt.GetPane().name == self.s4.name:
            Publisher.sendMessage('Show raycasting widget')

    def OnRestore(self, evt):
        if evt.GetPane().name == self.s4.name:
            Publisher.sendMessage('Hide raycasting widget')

    def __init_four_way_splitter(self):

        splitter = fws.FourWaySplitter(self, style=wx.SP_LIVE_UPDATE)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

        p1 = slice_viewer.Viewer(self, "AXIAL")
        splitter.AppendWindow(p1)

        p2 = slice_viewer.Viewer(self, "CORONAL")
        splitter.AppendWindow(p2)

        p3 = slice_viewer.Viewer(self, "SAGITAL")
        splitter.AppendWindow(p3)

        p4 = volume_viewer.Viewer(self)
        splitter.AppendWindow(p4)

    def _Exit(self):
        self.aui_manager.UnInit()

    def __init_mix(self):
        aui_manager = wx.aui.AuiManager()
        aui_manager.SetManagedWindow(self)


        splitter = fws.FourWaySplitter(self, style=wx.SP_LIVE_UPDATE)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)


        p1 = slice_viewer.Viewer(self, "AXIAL")
        aui_manager.AddPane(p1,
                                 wx.aui.AuiPaneInfo().
                                 Name("Axial Slice").Caption(_("Axial slice")).
                                 MaximizeButton(True).CloseButton(False))

        p2 = slice_viewer.Viewer(self, "CORONAL")
        aui_manager.AddPane(p2,
                                 wx.aui.AuiPaneInfo().
                                 Name("Coronal Slice").Caption(_("Coronal slice")).
                                 MaximizeButton(True).CloseButton(False))

        p3 = slice_viewer.Viewer(self, "SAGITAL")
        aui_manager.AddPane(p3,
                                 wx.aui.AuiPaneInfo().
                                 Name("Sagittal Slice").Caption(_("Sagittal slice")).
                                 MaximizeButton(True).CloseButton(False))

        #p4 = volume_viewer.Viewer(self)
        aui_manager.AddPane(VolumeViewerCover,
                                 wx.aui.AuiPaneInfo().
                                 Name("Volume").Caption(_("Volume")).
                                 MaximizeButton(True).CloseButton(False))

        splitter.AppendWindow(p1)
        splitter.AppendWindow(p2)
        splitter.AppendWindow(p3)
        splitter.AppendWindow(p4)


        aui_manager.Update()

class VolumeInteraction(wx.Panel):
    def __init__(self, parent, id):
        super(VolumeInteraction, self).__init__(parent, id)
        self.can_show_raycasting_widget = 0
        self.__init_aui_manager()
        #sizer = wx.BoxSizer(wx.HORIZONTAL)
        #sizer.Add(volume_viewer.Viewer(self), 1, wx.EXPAND|wx.GROW)
        #self.SetSizer(sizer)
        self.__bind_events()
        self.__bind_events_wx()
        #sizer.Fit(self)

    def __init_aui_manager(self):
        self.aui_manager = wx.aui.AuiManager()
        self.aui_manager.SetManagedWindow(self)

        p1 = volume_viewer.Viewer(self)
        s1 = wx.aui.AuiPaneInfo().Centre().\
                CloseButton(False).MaximizeButton(False).CaptionVisible(0)
        self.s1 = s1

        self.clut_raycasting = CLUTRaycastingWidget(self, -1)
        self.s2 = wx.aui.AuiPaneInfo().Bottom().BestSize((200, 200)).\
                CloseButton(False).MaximizeButton(False).CaptionVisible(0).\
                Hide()

        self.aui_manager.AddPane(p1, s1)
        self.aui_manager.AddPane(self.clut_raycasting, self.s2)
        self.aui_manager.Update()

    def __bind_events_wx(self):
        self.clut_raycasting.Bind(EVT_CLUT_POINT_RELEASE, self.OnPointChanged)
        self.clut_raycasting.Bind(EVT_CLUT_CURVE_SELECT, self.OnCurveSelected)
        self.clut_raycasting.Bind(EVT_CLUT_CURVE_WL_CHANGE,
                                  self.OnChangeCurveWL)
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        #self.Bind(wx.EVT_MAXIMIZE, self.OnMaximize)

    def __bind_events(self):
        Publisher.subscribe(self.ShowRaycastingWidget,
                                'Show raycasting widget')
        Publisher.subscribe(self.HideRaycastingWidget,
                                'Hide raycasting widget')
        Publisher.subscribe(self.OnSetRaycastPreset,
                                'Update raycasting preset')
        Publisher.subscribe(self.RefreshPoints,
                                'Refresh raycasting widget points')
        Publisher.subscribe(self.LoadHistogram,
                                'Load histogram')
        Publisher.subscribe(self._Exit, 'Exit')

    def __update_curve_wwwl_text(self, curve):
        ww, wl = self.clut_raycasting.GetCurveWWWl(curve)
        Publisher.sendMessage('Set raycasting wwwl', ww=ww, wl=wl, curve=curve)

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
        Publisher.sendMessage('Set raycasting refresh')
        Publisher.sendMessage('Set raycasting curve', curve=evt.GetCurve())
        Publisher.sendMessage('Render volume viewer')

    def OnCurveSelected(self, evt):
        Publisher.sendMessage('Set raycasting curve', curve=evt.GetCurve())
        Publisher.sendMessage('Render volume viewer')

    def OnChangeCurveWL(self, evt):
        curve = evt.GetCurve()
        self.__update_curve_wwwl_text(curve)
        Publisher.sendMessage('Render volume viewer')

    def OnSetRaycastPreset(self):
        preset = project.Project().raycasting_preset
        p = self.aui_manager.GetPane(self.clut_raycasting)
        self.clut_raycasting.SetRaycastPreset(preset)
        if self.clut_raycasting.to_draw_points and \
           self.can_show_raycasting_widget:
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


import wx.lib.platebtn as pbtn
import wx.lib.buttons as btn
from pubsub import pub as Publisher
import wx.lib.colourselect as csel

[BUTTON_RAYCASTING, BUTTON_VIEW, BUTTON_SLICE_PLANE, BUTTON_3D_STEREO, BUTTON_TARGET] = [wx.NewId() for num in range(5)]
RAYCASTING_TOOLS = wx.NewId()

ID_TO_NAME = {}
ID_TO_TOOL = {}
ID_TO_TOOL_ITEM = {}
TOOL_STATE = {}
ID_TO_ITEMSLICEMENU = {}
ID_TO_ITEM_3DSTEREO = {}
ID_TO_STEREO_NAME = {}


class VolumeViewerCover(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(VolumeInteraction(self, -1), 1, wx.EXPAND|wx.GROW)
        sizer.Add(VolumeToolPanel(self), 0, wx.EXPAND|wx.GROW)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class VolumeToolPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        # VOLUME RAYCASTING BUTTON
        BMP_RAYCASTING = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "volume_raycasting.png"),
                                    wx.BITMAP_TYPE_PNG)

        BMP_SLICE_PLANE = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "slice_plane.png"),
                                    wx.BITMAP_TYPE_PNG)


        BMP_3D_STEREO = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "3D_glasses.png"),
                                    wx.BITMAP_TYPE_PNG)

        BMP_TARGET = wx.Bitmap(os.path.join(inv_paths.ICON_DIR, "target.png"),
                                    wx.BITMAP_TYPE_PNG)


        button_raycasting = pbtn.PlateButton(self, BUTTON_RAYCASTING,"",
                BMP_RAYCASTING, style=pbtn.PB_STYLE_SQUARE,
                size=(32,32))

        button_stereo = pbtn.PlateButton(self, BUTTON_3D_STEREO,"",
                BMP_3D_STEREO, style=pbtn.PB_STYLE_SQUARE,
                    size=(32,32))

        button_slice_plane = self.button_slice_plane = pbtn.PlateButton(self, BUTTON_SLICE_PLANE,"",
        BMP_SLICE_PLANE, style=pbtn.PB_STYLE_SQUARE,
        size=(32,32))

        button_target = self.button_target = pbtn.PlateButton(self, BUTTON_TARGET,"",
        BMP_TARGET, style=pbtn.PB_STYLE_SQUARE|pbtn.PB_STYLE_TOGGLE,
        size=(32,32))
        self.button_target.Enable(0)

        self.button_raycasting = button_raycasting
        self.button_stereo = button_stereo

        # VOLUME VIEW ANGLE BUTTON
        BMP_FRONT = wx.Bitmap(ID_TO_BMP[const.VOL_FRONT][1],
                              wx.BITMAP_TYPE_PNG)
        button_view = pbtn.PlateButton(self, BUTTON_VIEW, "",
                                        BMP_FRONT, size=(32,32),
                                        style=pbtn.PB_STYLE_SQUARE)
        self.button_view = button_view

        # VOLUME COLOUR BUTTON
        if sys.platform.startswith('linux'):
            size = (32,32)
            sp = 2
        else:
            size = (24,24)
            sp = 5

        button_colour= csel.ColourSelect(self, 111,colour=(0,0,0),
                                        size=size)
        self.button_colour = button_colour

        # SIZER TO ORGANIZE ALL
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(button_colour, 0, wx.ALL, sp)
        sizer.Add(button_raycasting, 0, wx.TOP|wx.BOTTOM, 1)
        sizer.Add(button_view, 0, wx.TOP|wx.BOTTOM, 1)
        sizer.Add(button_slice_plane, 0, wx.TOP|wx.BOTTOM, 1)
        sizer.Add(button_stereo, 0, wx.TOP|wx.BOTTOM, 1)
        sizer.Add(button_target, 0, wx.TOP | wx.BOTTOM, 1)

        self.navigation_status = False
        self.status_target_select = False
        self.status_obj_tracker = False

        sizer.Fit(self)

        self.SetSizer(sizer)
        self.SetAutoLayout(1)
        self.Update()
        self.Refresh()

        self.__init_menus()
        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events(self):
        Publisher.subscribe(self.ChangeButtonColour,
                                 'Change volume viewer gui colour')
        Publisher.subscribe(self.DisablePreset, 'Close project data')
        Publisher.subscribe(self.Uncheck, 'Uncheck image plane menu')
        Publisher.subscribe(self.DisableVolumeCutMenu, 'Disable volume cut menu')
        Publisher.subscribe(self.StatusTargetSelect, 'Disable or enable coil tracker')
        Publisher.subscribe(self.StatusObjTracker, 'Status target button')
        Publisher.subscribe(self.ActiveTarget, 'Active target button')
        Publisher.subscribe(self.DeactiveTarget, 'Deactive target button')
        
    def DisablePreset(self):
        self.off_item.Check(1)


    def __bind_events_wx(self):
        self.button_slice_plane.Bind(wx.EVT_LEFT_DOWN, self.OnButtonSlicePlane)
        self.button_raycasting.Bind(wx.EVT_LEFT_DOWN, self.OnButtonRaycasting)
        self.button_view.Bind(wx.EVT_LEFT_DOWN, self.OnButtonView)
        self.button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_stereo.Bind(wx.EVT_LEFT_DOWN, self.OnButtonStereo)
        self.button_target.Bind(wx.EVT_LEFT_DOWN, self.OnButtonTarget)

    def OnButtonRaycasting(self, evt):
        # MENU RELATED TO RAYCASTING TYPES
        self.button_raycasting.PopupMenu(self.menu_raycasting)

    def OnButtonStereo(self, evt):
        self.button_stereo.PopupMenu(self.stereo_menu)

    def OnButtonView(self, evt):
        self.button_view.PopupMenu(self.menu_view)

    def OnButtonSlicePlane(self, evt):
        self.button_slice_plane.PopupMenu(self.slice_plane_menu)

    def StatusObjTracker(self, status):
        self.status_obj_tracker = status
        self.StatusNavigation()

    def StatusTargetSelect(self, status):
        self.status_target_select = status
        self.StatusNavigation()

    def ActiveTarget(self):
        self.button_target.Show()

    def DeactiveTarget(self):
        self.button_target.Hide()

    def StatusNavigation(self):
        if self.status_target_select and self.status_obj_tracker:
            self.button_target.Enable(1)
        else:
            self.OnButtonTarget(False)
            self.button_target.Enable(0)

    def OnButtonTarget(self, evt):
        if not self.button_target.IsPressed() and evt is not False:
            self.button_target._pressed = True
            Publisher.sendMessage('Target navigation mode', target_mode=self.button_target._pressed)
            Publisher.sendMessage('Change camera checkbox', status=self.button_target._pressed)
        elif self.button_target.IsPressed() or evt is False:
            self.button_target._pressed = False
            Publisher.sendMessage('Target navigation mode', target_mode=self.button_target._pressed)
            Publisher.sendMessage('Change camera checkbox', status=self.button_target._pressed)

    def OnSavePreset(self, evt):
        d = wx.TextEntryDialog(self, _("Preset name"))
        if d.ShowModal() == wx.ID_OK:
            preset_name = d.GetValue()
            Publisher.sendMessage("Save raycasting preset", preset_name=preset_name)

    def __init_menus(self):
        # MENU RELATED TO RAYCASTING TYPES
        menu = self.menu = wx.Menu()
        #print "\n\n"
        #print ">>>>", const.RAYCASTING_TYPES.sort()
        #print "\n\n"
        for name in const.RAYCASTING_TYPES:
            id = wx.NewId()
            item = wx.MenuItem(menu, id, name, kind=wx.ITEM_RADIO)
            menu.Append(item)
            if name == const.RAYCASTING_OFF_LABEL:
                self.off_item = item
                item.Check(1)
            ID_TO_NAME[id] = name

        menu.AppendSeparator()
        # MENU RELATED TO RAYCASTING TOOLS
        self.id_cutplane = None
        submenu = wx.Menu()
        for name in const.RAYCASTING_TOOLS:
           id = wx.NewId()
           if not(self.id_cutplane):
               self.id_cutplane = id
           
           item = wx.MenuItem(submenu, id, name, kind=wx.ITEM_CHECK)
           submenu.Append(item)
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
        if sys.platform != 'win32':
            submenu.Bind(wx.EVT_MENU, self.OnMenuRaycasting)
        menu.Bind(wx.EVT_MENU, self.OnMenuRaycasting)

        # VOLUME VIEW ANGLE BUTTON
        menu = wx.Menu()
        for id in ID_TO_BMP:
            bmp =  wx.Bitmap(ID_TO_BMP[id][1], wx.BITMAP_TYPE_PNG)
            item = wx.MenuItem(menu, id, ID_TO_BMP[id][0])
            item.SetBitmap(bmp)
            menu.Append(item)
        menu.Bind(wx.EVT_MENU, self.OnMenuView)
        self.menu_view = menu

        #SLICE PLANES BUTTON
        self.slice_plane_menu = slice_plane_menu = wx.Menu()
        itens = ["Axial", "Coronal", "Sagital"]

        for value in itens:
            new_id = wx.NewId()

            item = wx.MenuItem(slice_plane_menu, new_id, value,
                                            kind = wx.ITEM_CHECK)
            ID_TO_ITEMSLICEMENU[new_id] = item
            slice_plane_menu.Append(item)

        slice_plane_menu.Bind(wx.EVT_MENU, self.OnMenuPlaneSlice)


        #3D Stereo Buttons
        self.stereo_menu = stereo_menu = wx.Menu()
        itens = [const.STEREO_OFF, const.STEREO_RED_BLUE,const.STEREO_ANAGLYPH, const.STEREO_CRISTAL, 
                 const.STEREO_INTERLACED, const.STEREO_LEFT, const.STEREO_RIGHT, const.STEREO_DRESDEN, 
                 const.STEREO_CHECKBOARD]
 
        for value in itens:
            new_id = wx.NewId()

            item = wx.MenuItem(stereo_menu, new_id, value, 
                                                kind = wx.ITEM_RADIO)

            ID_TO_ITEM_3DSTEREO[new_id] = item
            ID_TO_STEREO_NAME[new_id] = value 
            stereo_menu.Append(item)

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
                presets += [filename.split(".")[0] for filename in
                            os.listdir(folder) if
                            os.path.isfile(os.path.join(folder,filename))]

    def OnMenuPlaneSlice(self, evt):

        id = evt.GetId()
        item = ID_TO_ITEMSLICEMENU[id]
        checked = item.IsChecked()
        label = item.GetItemLabelText()

        if not (checked):
            Publisher.sendMessage('Disable plane', plane_label=label)
        else:
            Publisher.sendMessage('Enable plane', plane_label=label)

    def OnMenuStereo(self, evt):
        id = evt.GetId() 
        mode = ID_TO_STEREO_NAME[id]
        Publisher.sendMessage('Set stereo mode', mode=mode)


    def Uncheck(self):
        for item in self.slice_plane_menu.GetMenuItems():
            if (item.IsChecked()):
                item.Check(0)
    
    def ChangeButtonColour(self, colour):
        colour = [i*255 for i in colour]
        self.button_colour.SetColour(colour)

    def OnMenuRaycasting(self, evt):
        """Events from raycasting menu."""
        id = evt.GetId()
        if id in ID_TO_NAME.keys():
            # Raycassting type was selected
            name = ID_TO_NAME[id]
            Publisher.sendMessage('Load raycasting preset',
                                  preset_name=ID_TO_NAME[id])
            # Enable or disable tools
            if name != const.RAYCASTING_OFF_LABEL:
                self.menu_raycasting.Enable(RAYCASTING_TOOLS, 1)
            else:
                self.menu_raycasting.Enable(RAYCASTING_TOOLS, 0)

        else:
            # Raycasting tool
            # TODO: In future, when more tools are available
            item = ID_TO_TOOL_ITEM[id]
            #if not item.IsChecked():
            #    for i in ID_TO_TOOL_ITEM.values():
            #        if i is not item:
            #            i.Check(0)
            if not TOOL_STATE[id]:
                Publisher.sendMessage('Enable raycasting tool',
                                      tool_name=ID_TO_TOOL[id], flag=1)
                TOOL_STATE[id] = True
                item.Check(1)
            else:
                Publisher.sendMessage('Enable raycasting tool',
                                      tool_name=ID_TO_TOOL[id], flag=0)
                TOOL_STATE[id] = False
                item.Check(0)


    def OnMenuView(self, evt):
        """Events from button menus."""
        bmp = wx.Bitmap(ID_TO_BMP[evt.GetId()][1], wx.BITMAP_TYPE_PNG)
        self.button_view.SetBitmapSelected(bmp)

        Publisher.sendMessage('Set volume view angle',
                              view=evt.GetId())
        self.Refresh()

    def OnSelectColour(self, evt):
        colour = c = [i/255.0 for i in evt.GetValue()]
        Publisher.sendMessage('Change volume viewer background colour', colour=colour)

