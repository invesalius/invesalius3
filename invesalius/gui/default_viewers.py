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

import wx
import wx.lib.agw.fourwaysplitter as fws
import wx.lib.pubsub as ps

import data.viewer_slice as slice_viewer
import data.viewer_volume as volume_viewer
import project
import widgets.slice_menu as slice_menu_

from gui.widgets.clut_raycasting import CLUTRaycastingWidget, \
        EVT_CLUT_POINT_RELEASE, EVT_CLUT_CURVE_SELECT, \
        EVT_CLUT_CURVE_WL_CHANGE

from constants import ID_TO_BMP

class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                          size=wx.Size(744, 656))

        self.__init_aui_manager()
        self.__bind_events_wx()
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


        if sys.platform == 'win32':
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

    def __bind_events_wx(self):
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_MAXIMIZE, self.OnMaximize)
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_RESTORE, self.OnRestore)

    def OnMaximize(self, evt):
        if evt.GetPane().name == self.s4.name:
            ps.Publisher().sendMessage('Show raycasting widget', None)

    def OnRestore(self, evt):
        if evt.GetPane().name == self.s4.name:
            ps.Publisher().sendMessage('Hide raycasting widget', None)

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
        ps.Publisher().subscribe(self.ShowRaycastingWidget,
                                'Show raycasting widget')
        ps.Publisher().subscribe(self.HideRaycastingWidget,
                                'Hide raycasting widget')
        ps.Publisher().subscribe(self.OnSetRaycastPreset,
                                'Update raycasting preset')
        ps.Publisher().subscribe(self.RefreshPoints,
                                'Refresh raycasting widget points')
        ps.Publisher().subscribe(self.LoadHistogram,
                                'Load histogram')

    def __update_curve_wwwl_text(self, curve):
        ww, wl = self.clut_raycasting.GetCurveWWWl(curve)
        ps.Publisher().sendMessage('Set raycasting wwwl', (ww, wl, curve))

    def ShowRaycastingWidget(self, evt_pubsub=None):
        self.can_show_raycasting_widget = 1
        if self.clut_raycasting.to_draw_points:
            p = self.aui_manager.GetPane(self.clut_raycasting)
            p.Show()
            self.aui_manager.Update()

    def HideRaycastingWidget(self, evt_pubsub=None):
        self.can_show_raycasting_widget = 0
        p = self.aui_manager.GetPane(self.clut_raycasting)
        p.Hide()
        self.aui_manager.Update()

    def OnPointChanged(self, evt):
        print "Removed"
        ps.Publisher.sendMessage('Set raycasting refresh', None)
        ps.Publisher.sendMessage('Set raycasting curve', evt.GetCurve())
        ps.Publisher().sendMessage('Render volume viewer')

    def OnCurveSelected(self, evt):
        ps.Publisher.sendMessage('Set raycasting curve', evt.GetCurve())
        ps.Publisher().sendMessage('Render volume viewer')

    def OnChangeCurveWL(self, evt):
        curve = evt.GetCurve()
        self.__update_curve_wwwl_text(curve)
        ps.Publisher().sendMessage('Render volume viewer')

    def OnSetRaycastPreset(self, evt_pubsub):
        preset = project.Project().raycasting_preset
        print "Preset >>>", preset
        p = self.aui_manager.GetPane(self.clut_raycasting)
        self.clut_raycasting.SetRaycastPreset(preset)
        if self.clut_raycasting.to_draw_points and \
           self.can_show_raycasting_widget:
            p.Show()
        else:
            p.Hide()
        self.aui_manager.Update()

    def LoadHistogram(self, pubsub_evt):
        histogram = pubsub_evt.data[0]
        init, end = pubsub_evt.data[1]
        self.clut_raycasting.SetRange((init, end))
        self.clut_raycasting.SetHistogramArray(histogram, (init, end))

    def RefreshPoints(self, pubsub_evt):
        self.clut_raycasting.CalculatePixelPoints()
        self.clut_raycasting.Refresh()

import wx.lib.platebtn as pbtn
import wx.lib.buttons as btn
import wx.lib.pubsub as ps

import constants as const
import widgets.colourselect as csel

[BUTTON_RAYCASTING, BUTTON_VIEW, BUTTON_SLICE_PLANE] = [wx.NewId() for num in xrange(3)]
RAYCASTING_TOOLS = wx.NewId()

ID_TO_NAME = {}
ID_TO_TOOL = {}
ID_TO_TOOL_ITEM = {}
TOOL_STATE = {}
ID_TO_ITEMSLICEMENU = {}

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
        wx.Panel.__init__(self, parent, size = (10,100))

        # VOLUME RAYCASTING BUTTON
        BMP_RAYCASTING = wx.Bitmap("../icons/volume_raycasting.png",
                                    wx.BITMAP_TYPE_PNG)

        BMP_SLICE_PLANE = wx.Bitmap("../icons/slice_plane.png",
                                    wx.BITMAP_TYPE_PNG)


        button_raycasting = pbtn.PlateButton(self, BUTTON_RAYCASTING,"",
                BMP_RAYCASTING, style=pbtn.PB_STYLE_SQUARE,
                size=(24,24))

        button_slice_plane = self.button_slice_plane = pbtn.PlateButton(self, BUTTON_SLICE_PLANE,"",
        BMP_SLICE_PLANE, style=pbtn.PB_STYLE_SQUARE,
        size=(24,24))

        self.button_raycasting = button_raycasting

        # VOLUME VIEW ANGLE BUTTON
        BMP_FRONT = wx.Bitmap(ID_TO_BMP[const.VOL_FRONT][1],
                              wx.BITMAP_TYPE_PNG)
        button_view = pbtn.PlateButton(self, BUTTON_VIEW, "",
                                        BMP_FRONT, size=(24,24),
                                        style=pbtn.PB_STYLE_SQUARE)
        self.button_view = button_view

        # VOLUME COLOUR BUTTON
        if sys.platform == 'linux2':
            size = (28,28)
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

        sizer.Fit(self)

        self.SetSizer(sizer)
        self.SetAutoLayout(1)
        self.Update()
        self.Refresh()

        self.__init_menus()
        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events(self):
        ps.Publisher().subscribe(self.ChangeButtonColour,
                                 'Change volume viewer gui colour')
        ps.Publisher().subscribe(self.DisablePreset, 'Close project data')
        ps.Publisher().subscribe(self.Uncheck, 'Uncheck image plane menu')
        ps.Publisher().subscribe(self.DisableVolumeCutMenu, 'Disable volume cut menu')
        
    def DisablePreset(self, pubsub_evt):
        self.off_item.Check(1)


    def __bind_events_wx(self):
        self.button_slice_plane.Bind(wx.EVT_LEFT_DOWN, self.OnButtonSlicePlane)
        self.button_raycasting.Bind(wx.EVT_LEFT_DOWN, self.OnButtonRaycasting)
        self.button_view.Bind(wx.EVT_LEFT_DOWN, self.OnButtonView)
        self.button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)

    def OnButtonRaycasting(self, evt):
        # MENU RELATED TO RAYCASTING TYPES
        self.button_raycasting.PopupMenu(self.menu_raycasting)

    def OnButtonView(self, evt):
        self.button_view.PopupMenu(self.menu_view)

    def OnButtonSlicePlane(self, evt):
        self.button_slice_plane.PopupMenu(self.slice_plane_menu)

    def OnSavePreset(self, evt):
        d = wx.TextEntryDialog(self, _("Preset name"))
        if d.ShowModal() == wx.ID_OK:
            preset_name = d.GetValue()
            ps.Publisher().sendMessage(_("Save raycasting preset"),
                                       preset_name)

    def __init_menus(self, pubsub_evt=None):
        # MENU RELATED TO RAYCASTING TYPES
        menu = self.menu = wx.Menu()
        for name in const.RAYCASTING_TYPES:
            id = wx.NewId()
            item = wx.MenuItem(menu, id, name, kind=wx.ITEM_RADIO)
            menu.AppendItem(item)
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
           submenu.AppendItem(item)
           ID_TO_TOOL[id] = name
           ID_TO_TOOL_ITEM[id] = item
           TOOL_STATE[id] = False
        self.submenu_raycasting_tools = submenu
        menu.AppendMenu(RAYCASTING_TOOLS, _("Tools"), submenu)
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
            menu.AppendItem(item)
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
            slice_plane_menu.AppendItem(item)

        slice_plane_menu.Bind(wx.EVT_MENU, self.OnMenuPlaneSlice)

        self.Fit()
        self.Update()
        
    def DisableVolumeCutMenu(self, pusub_evt):
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
        label = item.GetLabel()

        if not (checked):
            ps.Publisher().sendMessage('Disable plane', label)
        else:
            ps.Publisher().sendMessage('Enable plane', label)

    def Uncheck(self, pubsub_evt):        
        for item in self.slice_plane_menu.GetMenuItems():
            if (item.IsChecked()):
                item.Check(0)
    
    def ChangeButtonColour(self, pubsub_evt):
        colour = [i*255 for i in pubsub_evt.data]
        self.button_colour.SetColour(colour)

    def OnMenuRaycasting(self, evt):
        """Events from raycasting menu."""
        id = evt.GetId()
        if id in ID_TO_NAME.keys():
            # Raycassting type was selected
            name = ID_TO_NAME[id]
            ps.Publisher().sendMessage('Load raycasting preset',
                                          ID_TO_NAME[id])
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
                print "item is checked"
                ps.Publisher().sendMessage('Enable raycasting tool',
                                          [ID_TO_TOOL[id],1])
                TOOL_STATE[id] = True
                item.Check(1)
            else:
                print "item is not checked"
                ps.Publisher().sendMessage('Enable raycasting tool',
                                            [ID_TO_TOOL[id],0])
                TOOL_STATE[id] = False
                item.Check(0)


    def OnMenuView(self, evt):
        """Events from button menus."""
        bmp = wx.Bitmap(ID_TO_BMP[evt.GetId()][1], wx.BITMAP_TYPE_PNG)
        self.button_view.SetBitmapSelected(bmp)

        ps.Publisher().sendMessage('Set volume view angle',
                                   evt.GetId())
        self.Refresh()

    def OnSelectColour(self, evt):
        colour = c = [i/255.0 for i in evt.GetValue()]
        ps.Publisher().sendMessage('Change volume viewer background colour', colour)

