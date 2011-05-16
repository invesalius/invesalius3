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
import webbrowser

import wx
import wx.aui
import wx.lib.pubsub as ps

import constants as const
import default_tasks as tasks
import default_viewers as viewers
import gui.dialogs as dlg
import import_panel as imp
import project as prj
import session as ses
import utils
import preferences

# Layout tools' IDs - this is used only locally, therefore doesn't
# need to be defined in constants.py
VIEW_TOOLS = [ID_LAYOUT, ID_TEXT] =\
                                [wx.NewId() for number in range(2)]

class Frame(wx.Frame):
    """
    Main frame of the whole software.
    """
    def __init__(self, prnt):
        """
        Initialize frame, given its parent.
        """
        wx.Frame.__init__(self, id=-1, name='', parent=prnt,
              pos=wx.Point(0, 0),
              size=wx.Size(1024, 748), #size = wx.DisplaySize(),
              style=wx.DEFAULT_FRAME_STYLE, title='InVesalius 3')
        self.Center(wx.BOTH)
        icon_path = os.path.join(const.ICON_DIR, "invesalius.ico")
        self.SetIcon(wx.Icon(icon_path, wx.BITMAP_TYPE_ICO))
        if sys.platform != 'darwin':
            self.Maximize()
            #Necessary update AUI (statusBar in special)
            #when maximized in the Win 7 and XP
            #self.SetSize(self.GetSize())
            self.SetSize(wx.Size(1024, 748))


        # Set menus, status and task bar
        self.SetMenuBar(MenuBar(self))
        self.SetStatusBar(StatusBar(self))

        # Set TaskBarIcon
        #TaskBarIcon(self)

        # Create aui manager and insert content in it
        self.__init_aui()

        self.preferences = preferences.Preferences(self)
        # Initialize bind to pubsub events
        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._BeginBusyCursor, 'Begin busy cursor')
        sub(self._ShowContentPanel, 'Cancel DICOM load')
        sub(self._EndBusyCursor, 'End busy cursor')
        sub(self._HideContentPanel, 'Hide content panel')
        sub(self._HideImportPanel, 'Hide import panel')
        sub(self._HideTask, 'Hide task panel')
        sub(self._SetProjectName, 'Set project name')
        sub(self._ShowContentPanel, 'Show content panel')
        sub(self._ShowImportPanel, 'Show import panel in frame')
        sub(self._ShowTask, 'Show task panel')
        sub(self._UpdateAUI, 'Update AUI')
        sub(self._Exit, 'Exit')

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MENU, self.OnMenuClick)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def __init_aui(self):
        """
        Build AUI manager and all panels inside InVesalius frame.
        """

        # Tell aui_manager to manage this frame
        aui_manager = self.aui_manager = wx.aui.AuiManager()
        aui_manager.SetManagedWindow(self)

        # Add panels to manager

        # First, the task panel, to be on the left fo the frame
        # This will be specific according to InVesalius application
        aui_manager.AddPane(tasks.Panel(self), wx.aui.AuiPaneInfo().
                          Name("Tasks").CaptionVisible(False))

        # Then, add the viewers panel, which will contain slices and
        # volume panels. In future this might also be specific
        # according to InVesalius application (e.g. panoramic
        # visualization, in odontology)
        aui_manager.AddPane(viewers.Panel(self), wx.aui.AuiPaneInfo().
                          Caption(_("Data panel")).CaptionVisible(False).
                          Centre().CloseButton(False).Floatable(False).
                          Hide().Layer(1).MaximizeButton(True).
                          Name("Data").Position(1))

        # This is the DICOM import panel. When the two panels above
        # are shown, this should be hiden
        caption = _("Preview medical data to be reconstructed")
        aui_manager.AddPane(imp.Panel(self), wx.aui.AuiPaneInfo().
                          Name("Import").Centre().Hide().
                          MaximizeButton(True).Floatable(True).
                          Caption(caption).CaptionVisible(True))

        # Add toolbars to manager
        # This is pretty tricky -- order on win32 is inverted when
        # compared to linux2 & darwin
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
        self.aui_manager = aui_manager

        # TODO: Allow saving and restoring perspectives
        self.perspective_all = aui_manager.SavePerspective()

    def _BeginBusyCursor(self, pubsub_evt):
        """
        Start busy cursor.
        Note: _EndBusyCursor should be called after.
        """
        wx.BeginBusyCursor()

    def _EndBusyCursor(self, pubsub_evt):
        """
        End busy cursor.
        Note: _BeginBusyCursor should have been called previously.
        """
        try:
            wx.EndBusyCursor()
        except wx._core.PyAssertionError:
            #no matching wxBeginBusyCursor() for wxEndBusyCursor()
            pass

    def _Exit(self, pubsub_evt):
        """
        Exit InVesalius.
        """
        self.Destroy()
        sys.exit()

    def _HideContentPanel(self, pubsub_evt):
        """
        Hide data and tasks panels.
        """
        aui_manager = self.aui_manager
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _HideImportPanel(self, evt_pubsub):
        """
        Hide import panel and show tasks.
        """
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _HideTask(self, pubsub_evt):
        """
        Hide task panel.
        """
        self.aui_manager.GetPane("Tasks").Hide()
        self.aui_manager.Update()

    def _SetProjectName(self, pubsub_evt):
        """
        Set project name into frame's title.
        """
        proj_name = pubsub_evt.data

        if not(proj_name):
            self.SetTitle("InVesalius 3")
        else:
            self.SetTitle("%s - InVesalius 3"%(proj_name))

    def _ShowContentPanel(self, evt_pubsub):
        """
        Show viewers and task, hide import panel.
        """
        ps.Publisher().sendMessage("Set layout button full")
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)
        aui_manager.GetPane("Data").Show(1)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _ShowImportPanel(self, evt_pubsub):
        """
        Show only DICOM import panel.
        """
        ps.Publisher().sendMessage("Set layout button data only")
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(1)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(0)
        aui_manager.Update()

    def _ShowTask(self, pubsub_evt):
        """
        Show task panel.
        """
        self.aui_manager.GetPane("Tasks").Show()
        self.aui_manager.Update()

    def _UpdateAUI(self, pubsub_evt):
        """
        Refresh AUI panels/data.
        """
        self.aui_manager.Update()

    def CloseProject(self):
        ps.Publisher().sendMessage('Close Project')

    def OnClose(self, evt):
        """
        Close all project data.
        """
        ps.Publisher().sendMessage('Close Project')

    def OnMenuClick(self, evt):
        """
        Capture event from mouse click on menu / toolbar (as both use
        the same ID's)
        """
        id = evt.GetId()

        if id == const.ID_DICOM_IMPORT:
            self.ShowImportDicomPanel()
        elif id == const.ID_PROJECT_OPEN:
            self.ShowOpenProject()
        elif id == const.ID_ANALYZE_IMPORT:
            self.ShowAnalyzeImporter()
        elif id == const.ID_PROJECT_SAVE:
            session = ses.Session()
            if session.temp_item:
                self.ShowSaveAsProject()
            else:
                self.SaveProject()
        elif id == const.ID_PROJECT_SAVE_AS:
            self.ShowSaveAsProject()
        elif id == const.ID_PROJECT_CLOSE:
            self.CloseProject()
        elif id == const.ID_EXIT:
            self.OnClose(None)
        elif id == const.ID_ABOUT:
            self.ShowAbout()
        elif id == const.ID_START:
            self.ShowGettingStarted()
        elif id == const.ID_PREFERENCES:
            self.ShowPreferences()            

    def OnSize(self, evt):
        """
        Refresh GUI when frame is resized.
        """
        ps.Publisher().sendMessage(('ProgressBar Reposition'))
        evt.Skip()

    def ShowPreferences(self):
        if self.preferences.ShowModal():
            values = self.preferences.GetPreferences()
            self.preferences.Close()
        
        ses.Session().rendering = values[const.RENDERING]
        ses.Session().surface_interpolation = values[const.SURFACE_INTERPOLATION]

    def ShowAbout(self):
        """
        Shows about dialog.
        """
        dlg.ShowAboutDialog(self)

    def SaveProject(self):
        """
        Save project.
        """
        ps.Publisher().sendMessage('Show save dialog', False)

    def ShowGettingStarted(self):
        """
        Show getting started window.
        """
        path = os.path.join(const.DOC_DIR,
                            "user_guide_invesalius3a.pdf")
        webbrowser.open(path)

    def ShowImportDicomPanel(self):
        """
        Show import DICOM panel.
        """
        ps.Publisher().sendMessage('Show import directory dialog')

    def ShowOpenProject(self):
        """
        Show open project dialog.
        """
        ps.Publisher().sendMessage('Show open project dialog')

    def ShowSaveAsProject(self):
        """
        Show save as dialog.
        """
        ps.Publisher().sendMessage('Show save dialog', True)
        
    def ShowAnalyzeImporter(self):
        """
        Show save as dialog.
        """
        ps.Publisher().sendMessage('Show analyze dialog', True)

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class MenuBar(wx.MenuBar):
    """
    MenuBar which contains menus used to control project, tools and
    help.
    """
    def __init__(self, parent):
        wx.MenuBar.__init__(self)

        self.parent = parent

        # Used to enable/disable menu items if project is opened or
        # not. Eg. save should only be available if a project is open
        self.enable_items = [const.ID_PROJECT_SAVE,
                             const.ID_PROJECT_SAVE_AS,
                             const.ID_PROJECT_CLOSE]
        self.__init_items()
        self.__bind_events()

        self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        # TODO: in future, possibly when wxPython 2.9 is available,
        # events should be binded directly from wx.Menu / wx.MenuBar
        # message "Binding events of wx.MenuBar" on [wxpython-users]
        # mail list in Oct 20 2008
        sub = ps.Publisher().subscribe
        sub(self.OnEnableState, "Enable state project")

    def __init_items(self):
        """
        Create all menu and submenus, and add them to self.
        """
        # TODO: This definetely needs improvements... ;)
        
        #Import Others Files
        others_file_menu = wx.Menu()
        others_file_menu.Append(const.ID_ANALYZE_IMPORT, "Analyze")

        # FILE
        file_menu = wx.Menu()
        app = file_menu.Append
        app(const.ID_DICOM_IMPORT, _("Import DICOM...\tCtrl+I"))
        file_menu.AppendMenu(const.ID_IMPORT_OTHERS_FILES, _("Import Others Files"), others_file_menu)
        app(const.ID_PROJECT_OPEN, _("Open Project...\tCtrl+O"))
        app(const.ID_PROJECT_SAVE, _("Save Project\tCtrl+S"))
        app(const.ID_PROJECT_SAVE_AS, _("Save Project As..."))
        app(const.ID_PROJECT_CLOSE, _("Close Project"))
        file_menu.AppendSeparator()
        #app(const.ID_PROJECT_INFO, _("Project Information..."))
        #file_menu.AppendSeparator()
        #app(const.ID_SAVE_SCREENSHOT, _("Save Screenshot"))
        #app(const.ID_PRINT_SCREENSHOT, _("Print Screenshot"))
        #file_menu.AppendSeparator()
        #app(1, "C:\InvData\sample.inv")
        #file_menu.AppendSeparator()
        app(const.ID_EXIT, _("Exit"))

        # EDIT
        #file_edit = wx.Menu()
        #app = file_edit.Append
        #app(wx.ID_UNDO, "Undo\tCtrl+Z")
        #app(wx.ID_REDO, "Redo\tCtrl+Y")
        #app(const.ID_EDIT_LIST, "Show Undo List...")

        # VIEW
        #view_tool_menu = wx.Menu()
        #app = view_tool_menu.Append
        #app(const.ID_TOOL_PROJECT, "Project Toolbar")
        #app(const.ID_TOOL_LAYOUT, "Layout Toolbar")
        #app(const.ID_TOOL_OBJECT, "Object Toolbar")
        #app(const.ID_TOOL_SLICE, "Slice Toolbar")

        #view_layout_menu = wx.Menu()
        #app = view_layout_menu.Append
        #app(const.ID_TASK_BAR, "Task Bar")
        #app(const.ID_VIEW_FOUR, "Four View")

        #view_menu = wx.Menu()
        #app = view_menu.Append
        #appm = view_menu.AppendMenu
        #appm(-1, "Toolbars",view_tool_menu)
        #appm(-1, "Layout", view_layout_menu)
        #view_menu.AppendSeparator()
        #app(const.ID_VIEW_FULL, "Fullscreen\tCtrl+F")
        #view_menu.AppendSeparator()
        #app(const.ID_VIEW_TEXT, "2D & 3D Text")
        #view_menu.AppendSeparator()
        #app(const.ID_VIEW_3D_BACKGROUND, "3D Background Colour")

        # TOOLS
        #tools_menu = wx.Menu()

        # OPTIONS
        options_menu = wx.Menu()
        options_menu.Append(const.ID_PREFERENCES, _("Preferences..."))

        # HELP
        help_menu = wx.Menu()
        help_menu.Append(const.ID_START, _("Getting Started..."))
        #help_menu.Append(108, "User Manual...")
        help_menu.AppendSeparator()
        help_menu.Append(const.ID_ABOUT, _("About..."))
        #help_menu.Append(107, "Check For Updates Now...")

        # TODO: Check what is necessary under MacOS to show
        # InVesalius and not Python
        # first menu item... Didn't manage to solve it up to now,
        # the 3 lines bellow are a frustated test, based on wxPython
        # Demo

        # TODO: Google about this
        #test_menu = wx.Menu()
        #item = test_menu.Append(-1,
        #                        &About InVesalius','InVesalius')
        #wx.App.SetMacAboutMenuItemId(item.GetId())

        # Add all menus to menubar
        self.Append(file_menu, _("File"))
        #self.Append(file_edit, "Edit")
        #self.Append(view_menu, "View")
        #self.Append(tools_menu, "Tools")
        self.Append(options_menu, _("Options"))
        self.Append(help_menu, _("Help"))

    def OnEnableState(self, pubsub_evt):
        """
        Based on given state, enables or disables menu items which
        depend if project is open or not.
        """
        state = pubsub_evt.data
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. save) when project is closed.
        """
        for item in self.enable_items:
            self.Enable(item, False)

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. save) when project is opened.
        """
        for item in self.enable_items:
            self.Enable(item, True)

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class ProgressBar(wx.Gauge):
    """
    Progress bar / gauge.
    """

    def __init__(self, parent):
        wx.Gauge.__init__(self, parent, -1, 100)
        self.parent = parent
        self._Layout()

        self.__bind_events()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._Layout, 'ProgressBar Reposition')

    def _Layout(self, evt_pubsub=None):
        """
        Compute new size and position, according to parent resize
        """
        rect = self.parent.GetFieldRect(2)
        self.SetPosition((rect.x + 2, rect.y + 2))
        self.SetSize((rect.width - 4, rect.height - 4))

    def SetPercentage(self, value):
        """
        Set value [0;100] into gauge, moving "status" percentage.
        """
        self.SetValue(int(value))
        if (value >= 99):
            self.SetValue(0)
        self.Refresh()
        self.Update()

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class StatusBar(wx.StatusBar):
    """
    Control general status (both text and gauge)
    """
    def __init__(self, parent):
        wx.StatusBar.__init__(self, parent, -1)

        # General status configurations
        self.SetFieldsCount(3)
        self.SetStatusWidths([-2,-2,-1])
        self.SetStatusText(_("Ready"), 0)
        self.SetStatusText("", 1)
        self.SetStatusText("", 2)

        # Add gaugee
        self.progress_bar = ProgressBar(self)

        self.__bind_events()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._SetProgressValue, 'Update status in GUI')
        sub(self._SetProgressLabel, 'Update status text in GUI')

    def _SetProgressValue(self, pubsub_evt):
        """
        Set both percentage value in gauge and text progress label in
        status.
        """
        value, label = pubsub_evt.data
        self.progress_bar.SetPercentage(value)
        self.SetStatusText(label, 0)
        if (int(value) >= 99):
            self.SetStatusText("",0)
        if sys.platform == 'win32':
            #TODO: temporary fix necessary in the Windows XP 64 Bits
            #BUG in wxWidgets http://trac.wxwidgets.org/ticket/10896
            try:
                #wx.SafeYield()
                wx.Yield()
            except(wx._core.PyAssertionError):
                utils.debug("wx._core.PyAssertionError")

    def _SetProgressLabel(self, pubsub_evt):
        """
        Set text progress label.
        """
        label = pubsub_evt.data
        self.SetStatusText(label, 0)

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class TaskBarIcon(wx.TaskBarIcon):
    """
    TaskBarIcon has different behaviours according to the platform:
        - win32:  Show icon on "Notification Area" (near clock)
        - darwin: Show icon on Dock
        - linux2: Show icon on "Notification Area" (near clock)
    """
    def __init__(self, parent=None):
        wx.TaskBarIcon.__init__(self)
        self.frame = parent

        icon = wx.Icon(os.path.join(const.ICON_DIR, "invesalius.ico"),
                       wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon, "InVesalius")
        self.imgidx = 1

        # bind some events
        self.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnTaskBarActivate)

    def OnTaskBarActivate(self, evt):
        pass

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class ProjectToolBar(wx.ToolBar):
    """
    Toolbar related to general project operations, including: import,
    open, save and saveas, among others.
    """
    def __init__(self, parent):
        style = wx.TB_FLAT|wx.TB_NODIVIDER| wx.TB_DOCKABLE
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            style)
        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent

        # Used to enable/disable menu items if project is opened or
        # not. Eg. save should only be available if a project is open
        self.enable_items = [const.ID_PROJECT_SAVE]

        self.__init_items()
        self.__bind_events()

        self.Realize()
        self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._EnableState, "Enable state project")

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        # Load bitmaps
        d = const.ICON_DIR
        if sys.platform == 'darwin':
            path = os.path.join(d,"file_from_internet_original.png")
            BMP_NET = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "file_import_original.png")
            BMP_IMPORT = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "file_open_original.png")
            BMP_OPEN = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "file_save_original.png")
            BMP_SAVE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "print_original.png")
            BMP_PRINT = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_photo_original.png")
            BMP_PHOTO = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)
        else:
            path = os.path.join(d, "file_from_internet.png")
            BMP_NET = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "file_import.png")
            BMP_IMPORT = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "file_open.png")
            BMP_OPEN = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "file_save.png")
            BMP_SAVE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "print.png")
            BMP_PRINT = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_photo.png")
            BMP_PHOTO = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

        # Create tool items based on bitmaps
        self.AddLabelTool(const.ID_DICOM_IMPORT,
                          "",
                          shortHelp =_("Import DICOM files..."),
                          bitmap=BMP_IMPORT)
        #self.AddLabelTool(const.ID_DICOM_LOAD_NET,
        #                   "Load medical image...",
        #                   BMP_NET)
        self.AddLabelTool(const.ID_PROJECT_OPEN,
                          "",
                          shortHelp =_("Open a InVesalius project..."),
                          bitmap=BMP_OPEN)
        self.AddLabelTool(const.ID_PROJECT_SAVE,
                          "",
                          shortHelp = _("Save InVesalius project"),
                          bitmap=BMP_SAVE)
        #self.AddLabelTool(const.ID_SAVE_SCREENSHOT,
        #                   "Take photo of screen",
        #                   BMP_PHOTO)
        #self.AddLabelTool(const.ID_PRINT_SCREENSHOT,
        #                   "Print medical image...",
        #                   BMP_PRINT)

    def _EnableState(self, pubsub_evt):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        state = pubsub_evt.data
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. save) when project is closed.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, False)

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. save) when project is opened.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, True)



# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class ObjectToolBar(wx.ToolBar):
    """
    Toolbar related to general object operations, including: zoom
    move, rotate, brightness/contrast, etc.
    """
    def __init__(self, parent):
        style =  wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize, style)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        # Used to enable/disable menu items if project is opened or
        # not. Eg. save should only be available if a project is open
        self.enable_items = [const.STATE_WL, const.STATE_PAN,
                             const.STATE_SPIN, const.STATE_ZOOM_SL,
                             const.STATE_ZOOM,
                             const.STATE_MEASURE_DISTANCE,
                             const.STATE_MEASURE_ANGLE,]
                             #const.STATE_ANNOTATE]
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.Realize()
        self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._UntoggleAllItems, 'Untoggle object toolbar items')
        sub(self._ToggleLinearMeasure, "Set tool linear measure")
        sub(self._ToggleAngularMeasure, "Set tool angular measure")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnToggle)

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = const.ICON_DIR
        if sys.platform == 'darwin':
            path = os.path.join(d, "tool_rotate_original.png")
            BMP_ROTATE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_translate_original.png")
            BMP_MOVE =wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_zoom_original.png")
            BMP_ZOOM = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_zoom_select_original.png")
            BMP_ZOOM_SELECT = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_contrast_original.png")
            BMP_CONTRAST = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "measure_line_original.png")
            BMP_DISTANCE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "measure_angle_original.png")
            BMP_ANGLE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            #path = os.path.join(d, "tool_annotation_original.png")
            #BMP_ANNOTATE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

        else:
            path = os.path.join(d, "tool_rotate.png")
            BMP_ROTATE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_translate.png")
            BMP_MOVE =wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_zoom.png")
            BMP_ZOOM = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_zoom_select.png")
            BMP_ZOOM_SELECT = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "tool_contrast.png")
            BMP_CONTRAST = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "measure_line.png")
            BMP_DISTANCE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d, "measure_angle.png")
            BMP_ANGLE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            #path = os.path.join(d, "tool_annotation.png")
            #BMP_ANNOTATE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

        # Create tool items based on bitmaps
        self.AddLabelTool(const.STATE_ZOOM,
                          "",
                          shortHelp =_("Zoom"),
                          bitmap=BMP_ZOOM,
                          kind = wx.ITEM_CHECK)
        self.AddLabelTool(const.STATE_ZOOM_SL,
                          "",
                          shortHelp = _("Zoom based on selection"),
                          bitmap = BMP_ZOOM_SELECT,
                          kind = wx.ITEM_CHECK)
        self.AddLabelTool(const.STATE_SPIN,
                          "",
                          shortHelp = _("Rotate"),
                          bitmap = BMP_ROTATE,
                          kind = wx.ITEM_CHECK)
        self.AddLabelTool(const.STATE_PAN,
                          "",
                          shortHelp = _("Move"),
                          bitmap = BMP_MOVE,
                          kind = wx.ITEM_CHECK)
        self.AddLabelTool(const.STATE_WL,
                          "",
                          shortHelp = _("Constrast"),
                          bitmap = BMP_CONTRAST,
                          kind = wx.ITEM_CHECK)
        self.AddLabelTool(const.STATE_MEASURE_DISTANCE,
                        "",
                        shortHelp = _("Measure distance"),
                        bitmap = BMP_DISTANCE,
                        kind = wx.ITEM_CHECK)
        self.AddLabelTool(const.STATE_MEASURE_ANGLE,
                        "",
                        shortHelp = _("Measure angle"),
                        bitmap = BMP_ANGLE,
                        kind = wx.ITEM_CHECK)
        #self.AddLabelTool(const.STATE_ANNOTATE,
        #                "",
        #                shortHelp = _("Add annotation"),
        #                bitmap = BMP_ANNOTATE,
        #                kind = wx.ITEM_CHECK)

    def _EnableState(self, pubsub_evt):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        state = pubsub_evt.data
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()

    def _UntoggleAllItems(self, pubsub_evt=None):
        """
        Untoggle all items on toolbar.
        """
        for id in const.TOOL_STATES:
            state = self.GetToolState(id)
            if state:
                self.ToggleTool(id, False)

    def _ToggleLinearMeasure(self, pubsub_evt):
        """
        Force measure distance tool to be toggled and bind pubsub
        events to other classes whici are interested on this.
        """
        id = const.STATE_MEASURE_DISTANCE
        self.ToggleTool(id, True)
        ps.Publisher().sendMessage('Enable style', id)
        ps.Publisher().sendMessage('Untoggle slice toolbar items')
        for item in const.TOOL_STATES:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)


    def _ToggleAngularMeasure(self, pubsub_evt):
        """
        Force measure angle tool to be toggled and bind pubsub
        events to other classes which are interested on this.
        """
        id = const.STATE_MEASURE_ANGLE
        self.ToggleTool(id, True)
        ps.Publisher().sendMessage('Enable style', id)
        ps.Publisher().sendMessage('Untoggle slice toolbar items')
        for item in const.TOOL_STATES:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)

    def OnToggle(self, evt):
        """
        Update status of other items on toolbar (only one item
        should be toggle each time).
        """
        id = evt.GetId()
        state = self.GetToolState(id)
        if state and ((id == const.STATE_MEASURE_DISTANCE) or\
                (id == const.STATE_MEASURE_ANGLE)):
            ps.Publisher().sendMessage('Fold measure task')

        if state:
            ps.Publisher().sendMessage('Enable style', id)
            ps.Publisher().sendMessage('Untoggle slice toolbar items')
        else:
            ps.Publisher().sendMessage('Disable style', id)

        for item in const.TOOL_STATES:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)
        evt.Skip()

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. zoom) when project is closed.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, False)
            self._UntoggleAllItems()

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. zoom) when project is opened.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, True)

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class SliceToolBar(wx.ToolBar):
    """
    Toolbar related to 2D slice specific operations, including: cross
    intersection reference and scroll slices.
    """
    def __init__(self, parent):
        style = wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            style)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        self.enable_items = [const.SLICE_STATE_SCROLL,
                             const.SLICE_STATE_CROSS]
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.Realize()
        self.SetStateProjectClose()

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = const.ICON_DIR
        if sys.platform == 'darwin':
            path = os.path.join(d, "slice_original.png")
            BMP_SLICE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d,"cross_original.png")
            BMP_CROSS = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)
        else:
            path = os.path.join(d, "slice.png")
            BMP_SLICE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

            path = os.path.join(d,"cross.png")
            BMP_CROSS = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

        self.AddCheckTool(const.SLICE_STATE_SCROLL,
                          BMP_SLICE,
                          shortHelp = _("Scroll slices"))

        self.AddCheckTool(const.SLICE_STATE_CROSS,
                          BMP_CROSS,
                          shortHelp = _("Slices' cross intersection"))

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._UntoggleAllItems, 'Untoggle slice toolbar items')

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnToggle)

    def _EnableState(self, pubsub_evt):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        state = pubsub_evt.data
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()
            self._UntoggleAllItems()

    def _UntoggleAllItems(self, pubsub_evt=None):
        """
        Untoggle all items on toolbar.
        """
        for id in const.TOOL_SLICE_STATES:
            state = self.GetToolState(id)
            if state:
                self.ToggleTool(id, False)
                if id == const.SLICE_STATE_CROSS:
                    msg = 'Set cross visibility'
                    ps.Publisher().sendMessage(msg, 0)

    def OnToggle(self, evt):
        """
        Update status of other items on toolbar (only one item
        should be toggle each time).
        """
        id = evt.GetId()
        state = self.GetToolState(id)

        if state:
            ps.Publisher().sendMessage('Enable style', id)
            ps.Publisher().sendMessage('Untoggle object toolbar items')
        else:
            ps.Publisher().sendMessage('Disable style', id)

        for item in const.TOOL_SLICE_STATES:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)

        evt.Skip()

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. cross) when project is closed.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, False)

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. cross) when project is opened.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, True)

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class LayoutToolBar(wx.ToolBar):
    """
    Toolbar related to general layout/ visualization configuration
    e.g: show/hide task panel and show/hide text on viewers.
    """
    def __init__(self, parent):
        style = wx.TB_FLAT|wx.TB_NODIVIDER | wx.TB_DOCKABLE
        wx.ToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            style)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.ontool_layout = False
        self.ontool_text = True
        self.enable_items = [ID_TEXT]

        self.Realize()
        self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = ps.Publisher().subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._SetLayoutWithTask, "Set layout button data only")
        sub(self._SetLayoutWithoutTask, "Set layout button full")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnToggle)

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = const.ICON_DIR
        if sys.platform == 'darwin':
            # Bitmaps for show/hide task panel item
            p = os.path.join(d, "layout_data_only_original.gif")
            self.BMP_WITH_MENU = wx.Bitmap(p, wx.BITMAP_TYPE_GIF)

            p = os.path.join(d, "layout_full_original.gif")
            self.BMP_WITHOUT_MENU = wx.Bitmap(p, wx.BITMAP_TYPE_GIF)

            # Bitmaps for show/hide task item
            p = os.path.join(d, "text_inverted_original.png")
            self.BMP_WITHOUT_TEXT = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

            p = os.path.join(d, "text_original.png")
            self.BMP_WITH_TEXT = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

        else:
            # Bitmaps for show/hide task panel item
            p = os.path.join(d, "layout_data_only.gif")
            self.BMP_WITH_MENU = wx.Bitmap(p, wx.BITMAP_TYPE_GIF)

            p = os.path.join(d, "layout_full.gif")
            self.BMP_WITHOUT_MENU = wx.Bitmap(p, wx.BITMAP_TYPE_GIF)

            # Bitmaps for show/hide task item
            p = os.path.join(d, "text_inverted.png")
            self.BMP_WITHOUT_TEXT = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

            p = os.path.join(d, "text.png")
            self.BMP_WITH_TEXT = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

        self.AddLabelTool(ID_LAYOUT,
                          "",
                          bitmap=self.BMP_WITHOUT_MENU,
                          shortHelp= _("Hide task panel"))
        self.AddLabelTool(ID_TEXT,
                          "",
                          bitmap=self.BMP_WITH_TEXT,
                          shortHelp= _("Hide text"))

    def _EnableState(self, pubsub_evt):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        state = pubsub_evt.data
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()

    def _SetLayoutWithoutTask(self, pubsub_evt):
        """
        Set item bitmap to task panel hiden.
        """
        self.SetToolNormalBitmap(ID_LAYOUT,self.BMP_WITHOUT_MENU)

    def _SetLayoutWithTask(self, pubsub_evt):
        """
        Set item bitmap to task panel shown.
        """
        self.SetToolNormalBitmap(ID_LAYOUT,self.BMP_WITH_MENU)

    def OnToggle(self, event):
        """
        Update status of toolbar item (bitmap and help)
        """
        id = event.GetId()
        if id == ID_LAYOUT:
            self.ToggleLayout()
        elif id== ID_TEXT:
            self.ToggleText()

        for item in VIEW_TOOLS:
            state = self.GetToolState(item)
            if state and (item != id):
                self.ToggleTool(item, False)

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. text) when project is closed.
        """
        self.ontool_text = True
        self.ToggleText()
        for tool in self.enable_items:
            self.EnableTool(tool, False)

    def SetStateProjectOpen(self):
        """
        Disable menu items (e.g. text) when project is closed.
        """
        self.ontool_text = False
        self.ToggleText()
        for tool in self.enable_items:
            self.EnableTool(tool, True)

    def ToggleLayout(self):
        """
        Based on previous layout item state, toggle it.
        """
        if self.ontool_layout:
            self.SetToolNormalBitmap(ID_LAYOUT,self.BMP_WITHOUT_MENU)
            ps.Publisher().sendMessage('Show task panel')
            self.SetToolShortHelp(ID_LAYOUT,_("Hide task panel"))
            self.ontool_layout = False
        else:
            self.bitmap = self.BMP_WITH_MENU
            self.SetToolNormalBitmap(ID_LAYOUT,self.BMP_WITH_MENU)
            ps.Publisher().sendMessage('Hide task panel')
            self.SetToolShortHelp(ID_LAYOUT, _("Show task panel"))
            self.ontool_layout = True

    def ToggleText(self):
        """
        Based on previous text item state, toggle it.
        """
        if self.ontool_text:
            self.SetToolNormalBitmap(ID_TEXT,self.BMP_WITH_TEXT)
            ps.Publisher().sendMessage('Hide text actors on viewers')
            self.SetToolShortHelp(ID_TEXT,_("Show text"))
            ps.Publisher().sendMessage('Update AUI')
            self.ontool_text = False
        else:
            self.SetToolNormalBitmap(ID_TEXT, self.BMP_WITHOUT_TEXT)
            ps.Publisher().sendMessage('Show text actors on viewers')
            self.SetToolShortHelp(ID_TEXT,_("Hide text"))
            ps.Publisher().sendMessage('Update AUI')
            self.ontool_text = True

