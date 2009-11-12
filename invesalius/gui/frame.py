#--------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------
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
#--------------------------------------------------------------------

import math
import os.path
import sys

import wx
import wx.aui
import wx.lib.pubsub as ps

import constants as const
import default_tasks as tasks
import default_viewers as viewers
import import_panel as imp

# Object toolbar
OBJ_TOOLS = [ID_ZOOM, ID_ZOOM_SELECT, ID_ROTATE, ID_MOVE, 
ID_CONTRAST] = [wx.NewId() for number in range(5)]
MODE_BY_ID = {ID_ZOOM: const.MODE_ZOOM,
              ID_ZOOM_SELECT: const.MODE_ZOOM_SELECTION,
              ID_ROTATE: const.MODE_ROTATE,
              ID_MOVE: const.MODE_MOVE,
              ID_CONTRAST: const.MODE_WW_WL}

# Slice toolbar
SLICE_TOOLS = [ID_SLICE_SCROLL, ID_CROSS] = [wx.NewId() for number in range(2)]
SLICE_MODE_BY_ID = {ID_SLICE_SCROLL: const.MODE_SLICE_SCROLL,
                    ID_CROSS: const.MODE_SLICE_CROSS}

class Frame(wx.Frame):
    def __init__(self, prnt):
        wx.Frame.__init__(self, id=-1, name='', parent=prnt,
              pos=wx.Point(0, 0),
              size=wx.Size(1024, 768), #size = wx.DisplaySize(),
              style=wx.DEFAULT_FRAME_STYLE, title='InVesalius 3')
        self.Center(wx.BOTH)
        self.SetIcon(wx.Icon(os.path.join(const.ICON_DIR, "invesalius.ico"),
                             wx.BITMAP_TYPE_ICO))

        # Set menus, status and task bar
        self.SetMenuBar(MenuBar(self))
        self.SetStatusBar(StatusBar(self))

        # TEST: Check what happens in each OS when starting widget bellow
        # win32:  Show icon at "Notification Area" on "Task Bar"
        # darwin: Show icon on Dock
        # linux2: ? - TODO: find what it does
        #TaskBarIcon(self)

        # Create aui manager and insert content in it
        self.__init_aui()

        # Initialize bind to pubsub events
        self.__bind_events()
        self.__bind_events_wx()


    def __bind_events(self):
        ps.Publisher().subscribe(self.ShowContentPanel, 'Show content panel')
        ps.Publisher().subscribe(self.ShowImportPanel, "Show import panel in frame")
        ps.Publisher().subscribe(self.UpdateAui, "Update AUI")
        ps.Publisher().subscribe(self.ShowTask, 'Show task panel')
        ps.Publisher().subscribe(self.HideTask, 'Hide task panel')
        ps.Publisher().subscribe(self.SetProjectName, 'Set project name')
        ps.Publisher().subscribe(self.ShowContentPanel, 'Cancel DICOM load')
        ps.Publisher().subscribe(self.HideImportPanel, 'Hide import panel')

    def SetProjectName(self, pubsub_evt):
        proj_name = pubsub_evt.data
        if sys.platform != 'darwin':
            self.SetTitle("%s - InVesalius 3"%(proj_name))
        else:
            self.SetTitle("%s"%(proj_name))

    def UpdateAui(self, pubsub_evt):
        self.aui_manager.Update()

    def __bind_events_wx(self):
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MENU, self.OnMenuClick)
    
    def __init_aui(self):

        # Tell aui_manager to manage this frame
        aui_manager = self.aui_manager = wx.aui.AuiManager()
        aui_manager.SetManagedWindow(self)

        # Add panels to manager
        aui_manager.AddPane(tasks.Panel(self), wx.aui.AuiPaneInfo().
                          Name("Tasks").CaptionVisible(False))
                          # TEST: Check if above works well in all supported OS
                          # or if we nwwd to insert information bellow
                          #Caption("Task panel").CaptionVisible(False)).
                          #CloseButton(False).Floatable(False).
                          #Layer(1).Left().MaximizeButton(False).Name("Task").
                          #Position(0))
                          

        aui_manager.AddPane(viewers.Panel(self), wx.aui.AuiPaneInfo().
                          Caption("Data panel").CaptionVisible(False).
                          Centre().CloseButton(False).Floatable(False).
                          Hide().Layer(1).MaximizeButton(True).Name("Data").
                          Position(1))


        aui_manager.AddPane(imp.Panel(self), wx.aui.AuiPaneInfo().
                          Name("Import").Centre().Hide().
                          MaximizeButton(True).Floatable(True).
                          Caption("Preview medical data to be reconstructed").
                          CaptionVisible(True))


        # Add toolbars to manager

        if sys.platform == 'win32':
            t1 = ProjectToolBar(self)
            t2 = LayoutToolBar(self)
            t3 = ObjectToolBar(self)
            t4 = SliceToolBar(self)
        else:
            t4 = ProjectToolBar(self)
            t3 = LayoutToolBar(self)
            t2 = ObjectToolBar(self)
            t1 = SliceToolBar(self)

        aui_manager.AddPane(t1, wx.aui.AuiPaneInfo().
                          Name("General Features Toolbar").
                          ToolbarPane().Top().Floatable(False).
                          LeftDockable(False).RightDockable(False))

        aui_manager.AddPane(t2, wx.aui.AuiPaneInfo().
                          Name("Layout Toolbar").
                          ToolbarPane().Top().Floatable(False).
                          LeftDockable(False).RightDockable(False))

        aui_manager.AddPane(t3, wx.aui.AuiPaneInfo().
                          Name("Project Toolbar").
                          ToolbarPane().Top().Floatable(False).
                          LeftDockable(False).RightDockable(False))

        aui_manager.AddPane(t4, wx.aui.AuiPaneInfo().
                          Name("Slice Toolbar").
                          ToolbarPane().Top().Floatable(False).
                          LeftDockable(False).RightDockable(False))

        aui_manager.Update()

        self.perspective_all = aui_manager.SavePerspective()

        self.aui_manager = aui_manager

    def ShowImportPanel(self, evt_pubsub):
        #ps.Publisher().sendMessage("Load data to import panel", path)

        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(1)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(0)
        aui_manager.Update()

    def HideImportPanel(self, evt_pubsub):
        print "HideImportPanel"

        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()



    def ShowContentPanel(self, evt_pubsub):
        print "ShowContentPanel"
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)
        aui_manager.GetPane("Data").Show(1)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def OnSize(self, evt):
       ps.Publisher().sendMessage(('ProgressBar Reposition'))
       evt.Skip()
       
    def OnMenuClick(self, evt):
        ps.Publisher().sendMessage(("Run menu item",
                                    str(evt.GetId())))
    
    def ShowTask(self, pubsub_evt):
        self.aui_manager.GetPane("Tasks").Show()
        self.aui_manager.Update()
    
    def HideTask(self, pubsub_evt):
        self.aui_manager.GetPane("Tasks").Hide()
        self.aui_manager.Update()
    

    #def OnClose(self):
    #    # TODO: implement this, based on wx.Demo
    #    pass
# ------------------------------------------------------------------------------
# TODO: what will appear on ivMenuBar?
# Menu items ID's, necessary to bind events on them


class MenuBar(wx.MenuBar):
    def __init__(self, parent=None):
        wx.MenuBar.__init__(self)

        self.parent = parent

        self.__init_items()
        self.__bind_events()

    def __init_items(self):

        file_menu = wx.Menu()
        file_menu.Append(const.ID_FILE_IMPORT, "Import...")
        file_menu.Append(101, "Exit")

        view_menu = wx.Menu()
        view_menu.Append(101, "Fullscreen")

        tools_menu = wx.Menu()

        options_menu = wx.Menu()

        help_menu = wx.Menu()

        # TODO: Check what is necessary under MacOS to show Groo and not Python
        # first menu item... Didn't manage to solve it up to now, the 3 lines
        # bellow are a frustated test, based on wxPython Demo
        # TODO: Google about this
        test_menu = wx.Menu()
        test_item = test_menu.Append(-1, '&About Groo', 'Groo RULES!!!')
        wx.App.SetMacAboutMenuItemId(test_item.GetId())

        self.Append(file_menu, "File")
        self.Append(view_menu, "View")
        self.Append(tools_menu, "Tools")
        self.Append(options_menu, "Options")
        self.Append(help_menu, "Help")

    def __bind_events(self):
        # TODO: in future, possibly when wxPython 2.9 is available,
        # events should be binded directly from wx.Menu / wx.MenuBar
        # message "Binding events of wx.MenuBar" on [wxpython-users]
        # mail list in Oct 20 2008
        #self.parent.Bind(wx.EVT_MENU, self.OnNew, id=ID_NEW)
        #self.parent.Bind(wx.EVT_MENU, self.OnOpen, id=ID_OPEN)
        pass

    def OnNew(self, event):
        print "New"
        ps.Publisher().sendMessage(('NEW PROJECT'))
        event.Skip()

    def OnOpen(self, event):
        print "Open"
        event.Skip()

# ------------------------------------------------------------------
class ProgressBar(wx.Gauge):

   def __init__(self, parent):
      wx.Gauge.__init__(self, parent, -1, 100)
      self.parent = parent
      self.Reposition()
      self.__bind_events()

   def __bind_events(self):
      ps.Publisher().subscribe(self.Reposition,
                                'ProgressBar Reposition')

   def UpdateValue(self, value):
      #value = int(math.ceil(evt_pubsub.data[0]))
      self.SetValue(int(value))

      if (value >= 99):
         self.SetValue(0)

      self.Refresh()
      self.Update()

   def Reposition(self, evt_pubsub = None):
      rect = self.Parent.GetFieldRect(2)
      self.SetPosition((rect.x + 2, rect.y + 2))
      self.SetSize((rect.width - 4, rect.height - 4))

# ------------------------------------------------------------------
class StatusBar(wx.StatusBar):
    def __init__(self, parent):
        wx.StatusBar.__init__(self, parent, -1)
        self.SetFieldsCount(3)
        self.SetStatusWidths([-2,-2,-1])
        self.SetStatusText("Ready", 0)
        self.SetStatusText("", 1)
        self.SetStatusText("", 2)

        self.progress_bar = ProgressBar(self)

        self.__bind_events()

    def __bind_events(self):
        ps.Publisher().subscribe(self.UpdateStatus,
                                 'Update status in GUI')
        ps.Publisher().subscribe(self.UpdateStatusLabel,
                                 'Update status text in GUI')

    def UpdateStatus(self, pubsub_evt):
        value, label = pubsub_evt.data
        self.progress_bar.UpdateValue(value)
        self.SetStatusText(label, 0)
        if (int(value) >= 99):
            self.SetStatusText("",0)
        if sys.platform != 'linux2':
            wx.Yield()
        

    def UpdateStatusLabel(self, pubsub_evt):
        label = pubsub_evt.data
        self.SetStatusText(label, 0)


# ------------------------------------------------------------------

class TaskBarIcon(wx.TaskBarIcon):
    def __init__(self, parent=None):
        wx.TaskBarIcon.__init__(self)
        self.frame = parent

        icon = wx.Icon(os.path.join(const.ICON_DIR, "invesalius.ico"),
                       wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon, "InVesalius")
        self.imgidx = 1

        # bind some events
        self.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnTaskBarActive)

    def OnTaskBarActivate(self):
        pass

# ------------------------------------------------------------------

class ProjectToolBar(wx.ToolBar):
    def __init__(self, parent):
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent

        self.__init_items()
        self.__bind_events()

    def __init_items(self):


        BMP_IMPORT = wx.Bitmap(os.path.join(const.ICON_DIR, "file_import.png"),
                                    wx.BITMAP_TYPE_PNG)
        BMP_NET = wx.Bitmap(os.path.join(const.ICON_DIR,
                                         "file_from_internet.png"),
                                wx.BITMAP_TYPE_PNG)
        BMP_SAVE = wx.Bitmap(os.path.join(const.ICON_DIR, "file_save.png"),
                                    wx.BITMAP_TYPE_PNG)
        BMP_PRINT = wx.Bitmap(os.path.join(const.ICON_DIR, "print.png"),
                                    wx.BITMAP_TYPE_PNG)
        BMP_PHOTO = wx.Bitmap(os.path.join(const.ICON_DIR, "tool_photo.png"),
                                    wx.BITMAP_TYPE_PNG)

        if sys.platform == 'darwin':
            BMP_IMPORT = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                "file_import_original.png"),
                                   wx.BITMAP_TYPE_PNG)
            BMP_NET = wx.Bitmap(os.path.join(const.ICON_DIR,
                                             "file_from_internet_original.png"),
 	                                wx.BITMAP_TYPE_PNG)
            BMP_SAVE = wx.Bitmap(os.path.join(const.ICON_DIR,
                                              "file_save_original.png"),
 	                                 wx.BITMAP_TYPE_PNG)
            BMP_PRINT = wx.Bitmap(os.path.join(const.ICON_DIR,
                                               "print_original.png"),
 	                                    wx.BITMAP_TYPE_PNG)
            BMP_PHOTO = wx.Bitmap(os.path.join(const.ICON_DIR,
                                               "tool_photo_original.png"),
 	                                    wx.BITMAP_TYPE_PNG)
        else:
            BMP_IMPORT = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                "file_import.png"),
                                    wx.BITMAP_TYPE_PNG)
            BMP_NET = wx.Bitmap(os.path.join(const.ICON_DIR,
                                             "file_from_internet.png"),
                                wx.BITMAP_TYPE_PNG)
            BMP_SAVE = wx.Bitmap(os.path.join(const.ICON_DIR, "file_save.png"),
                                  wx.BITMAP_TYPE_PNG)
            BMP_PRINT = wx.Bitmap(os.path.join(const.ICON_DIR, "print.png"),
                                  wx.BITMAP_TYPE_PNG)
            BMP_PHOTO = wx.Bitmap(os.path.join(const.ICON_DIR, "tool_photo.png"),
                                   wx.BITMAP_TYPE_PNG)

        self.AddLabelTool(const.ID_FILE_IMPORT,
                           "Import medical image...",
                           BMP_IMPORT)
        self.AddLabelTool(const.ID_FILE_LOAD_INTERNET,
                           "Load medical image...",
                           BMP_NET)
        self.AddLabelTool(const.ID_FILE_SAVE,
                           "Save InVesalius project",
                           BMP_SAVE)
        self.AddLabelTool(const.ID_FILE_PHOTO,
                           "Take photo of screen",
                           BMP_PHOTO)
        self.AddLabelTool(const.ID_FILE_PRINT,
                           "Print medical image...",
                           BMP_PRINT)

        self.Realize()

    def __bind_events(self):
        self.Bind(wx.EVT_TOOL, self.OnToolSave, id=const.ID_FILE_SAVE)

    def OnToolSave(self, evt):
        print "Saving ..."
        ps.Publisher().sendMessage('Save Project')
# ------------------------------------------------------------------

class ObjectToolBar(wx.ToolBar):
    def __init__(self, parent):
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE)

        self.SetToolBitmapSize(wx.Size(32,32))  
        self.parent = parent

        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

    def __init_items(self):

        if sys.platform == 'darwin':
            BMP_ROTATE = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                "tool_rotate_original.gif"),
                                   wx.BITMAP_TYPE_GIF)
            BMP_MOVE =wx.Bitmap(os.path.join(const.ICON_DIR,
                                             "tool_translate_original.png"),
                                      wx.BITMAP_TYPE_PNG)
            BMP_ZOOM = wx.Bitmap(os.path.join(const.ICON_DIR,
                                              "tool_zoom_original.png"),
                                 wx.BITMAP_TYPE_PNG)
            BMP_ZOOM_SELECT = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                     "tool_zoom_select_original.png"),
                                        wx.BITMAP_TYPE_PNG)
            BMP_CONTRAST = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                  "tool_contrast_original.png"),
                                     wx.BITMAP_TYPE_PNG)
        else:
            
            BMP_ROTATE = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                "tool_rotate.gif"),
                                   wx.BITMAP_TYPE_GIF)
            BMP_MOVE = wx.Bitmap(os.path.join(const.ICON_DIR,
                                              "tool_translate.gif"),
                                   wx.BITMAP_TYPE_GIF)
            BMP_ZOOM = wx.Bitmap(os.path.join(const.ICON_DIR, "tool_zoom.png"),
                                 wx.BITMAP_TYPE_PNG)
            BMP_ZOOM_SELECT = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                     "tool_zoom_select.png"),
                                        wx.BITMAP_TYPE_PNG)
            BMP_CONTRAST = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                  "tool_contrast.png"),
                                     wx.BITMAP_TYPE_PNG)

        self.AddLabelTool(ID_ZOOM,
                           "Zoom",
                           BMP_ZOOM,
                           kind = wx.ITEM_CHECK)

        self.AddLabelTool(ID_ZOOM_SELECT,
                           "Zoom based on selection",
                           BMP_ZOOM_SELECT,
                           kind = wx.ITEM_CHECK)

        self.AddLabelTool(ID_ROTATE,
                           "Rotate", BMP_ROTATE,
                           kind = wx.ITEM_CHECK)

        self.AddLabelTool(ID_MOVE,
                           "Move", BMP_MOVE,
                            kind = wx.ITEM_CHECK)

        self.AddLabelTool(ID_CONTRAST,
                           "Window and Level", BMP_CONTRAST,
                           kind = wx.ITEM_CHECK)
        self.Realize()


    def __bind_events_wx(self):
        self.Bind(wx.EVT_TOOL, self.OnClick)

    def __bind_events(self):
        ps.Publisher().subscribe(self.UntoggleAllItems,
                                 'Untoggle object toolbar items')

    def OnClick(self, evt):
        id = evt.GetId()
        state = self.GetToolState(id)

        if state:
            ps.Publisher().sendMessage(('Set interaction mode',
                                        MODE_BY_ID[id]))
            ps.Publisher().sendMessage('Untoggle slice toolbar items')
        else:
            ps.Publisher().sendMessage(('Set interaction mode',
                                        const.MODE_SLICE_EDITOR))
            
        

        for item in OBJ_TOOLS:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)

        evt.Skip()

    def UntoggleAllItems(self, pubsub_evt=None):
        for id in OBJ_TOOLS:
            state = self.GetToolState(id)
            if state:
                self.ToggleTool(id, False)

# -------------------------------------------------------------------

class SliceToolBar(wx.ToolBar):
    def __init__(self, parent):
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

    def __init_items(self):
        if sys.platform == 'darwin':
            BMP_SLICE = wx.Bitmap(os.path.join(const.ICON_DIR,
                                               "slice_original.png"),
                                  wx.BITMAP_TYPE_PNG)
        else:
            BMP_SLICE = wx.Bitmap(os.path.join(const.ICON_DIR, "slice.png"),
                                  wx.BITMAP_TYPE_PNG)

        BMP_CROSS = wx.Bitmap(os.path.join(const.ICON_DIR, "cross.png"),
                              wx.BITMAP_TYPE_PNG)

        self.AddLabelTool(ID_SLICE_SCROLL, "Scroll slice",
                           BMP_SLICE, kind = wx.ITEM_CHECK)

        self.AddLabelTool(ID_CROSS, "Cross",
                           BMP_CROSS, kind = wx.ITEM_CHECK)

        self.Realize()

    def __bind_events_wx(self):
        self.Bind(wx.EVT_TOOL, self.OnClick)

    def __bind_events(self):
        ps.Publisher().subscribe(self.UntoggleAllItem,
                                'Untoggle slice toolbar items')

    def OnClick(self, evt):

        id = evt.GetId()
        state = self.GetToolState(id)

        if state:
            ps.Publisher().sendMessage(('Set interaction mode',
                                        SLICE_MODE_BY_ID[id]))
            ps.Publisher().sendMessage('Untoggle object toolbar items')
        else:
            ps.Publisher().sendMessage(('Set interaction mode',
                                        const.MODE_SLICE_EDITOR))


        for item in SLICE_TOOLS:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)

        evt.Skip()


    def UntoggleAllItem(self, pubsub_evt):
        for id in SLICE_TOOLS:
            state = self.GetToolState(id)
            if state:
                self.ToggleTool(id, False)

# ---------------------------------------------------------------------

class LayoutToolBar(wx.ToolBar):
    # TODO: what will appear in menubar?
    def __init__(self, parent):
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        self.__init_items()
        self.__bind_events_wx()

    def __init_items(self):

        if sys.platform == 'darwin':
            BMP_WITHOUT_MENU =\
            wx.Bitmap(os.path.join(const.ICON_DIR,
                                   "layout_data_only_original.gif"),
                               wx.BITMAP_TYPE_GIF)
            BMP_WITH_MENU = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                   "layout_full_original.gif"),
                                  wx.BITMAP_TYPE_GIF)

        else:
            BMP_WITHOUT_MENU = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                      "layout_data_only.gif"),
                                   wx.BITMAP_TYPE_GIF)
            BMP_WITH_MENU = wx.Bitmap(os.path.join(const.ICON_DIR,
                                                   "layout_full.gif"),
                                      wx.BITMAP_TYPE_GIF)

        self.AddLabelTool(101, "Full layout", BMP_WITHOUT_MENU, kind = wx.ITEM_RADIO)
        self.AddLabelTool(102, "Original layout", BMP_WITH_MENU, kind = wx.ITEM_RADIO)
        self.ToggleTool(102, True)
        
        self.Realize()

    def __bind_events_wx(self):
        self.Bind(wx.EVT_TOOL, self.OnClick)
    
    def OnClick(self, evt):
            
        if (evt.GetId() == 101):
            ps.Publisher().sendMessage('Hide task panel')
        else:
            ps.Publisher().sendMessage('Show task panel')
