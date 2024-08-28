# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
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
# --------------------------------------------------------------------

import errno
import math
import os.path
import platform
import subprocess
import sys
import webbrowser

import wx
import wx.aui
import wx.lib.popupctl as pc
from wx.lib.agw.aui.auibar import AUI_TB_PLAIN_BACKGROUND, AuiToolBar

import invesalius.constants as const
import invesalius.gui.default_tasks as tasks
import invesalius.gui.default_viewers as viewers
import invesalius.gui.dialogs as dlg
import invesalius.gui.import_bitmap_panel as imp_bmp
import invesalius.gui.import_panel as imp
import invesalius.gui.log as log
import invesalius.gui.preferences as preferences

#  import invesalius.gui.import_network_panel as imp_net
import invesalius.project as prj
import invesalius.session as ses
import invesalius.utils as utils
from invesalius import inv_paths
from invesalius.gui import project_properties
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

try:
    from wx.adv import TaskBarIcon as wx_TaskBarIcon
except ImportError:
    from wx import TaskBarIcon as wx_TaskBarIcon


# Layout tools' IDs - this is used only locally, therefore doesn't
# need to be defined in constants.py
VIEW_TOOLS = [ID_LAYOUT, ID_TEXT, ID_RULER] = [wx.NewIdRef() for number in range(3)]

WILDCARD_EXPORT_SLICE = (
    "HDF5 (*.hdf5)|*.hdf5|" "NIfTI 1 (*.nii)|*.nii|" "Compressed NIfTI (*.nii.gz)|*.nii.gz"
)

IDX_EXT = {0: ".hdf5", 1: ".nii", 2: ".nii.gz"}


class MessageWatershed(wx.PopupWindow):
    def __init__(self, prnt, msg):
        wx.PopupWindow.__init__(self, prnt, -1)
        self.txt = wx.StaticText(self, -1, msg)

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer.Add(self.txt, 1, wx.EXPAND)
        self.SetSizer(self.sizer)

        self.sizer.Fit(self)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)


class Frame(wx.Frame):
    """
    Main frame of the whole software.
    """

    def __init__(self, prnt):
        """
        Initialize frame, given its parent.
        """
        wx.Frame.__init__(
            self,
            id=const.ID_FRAME,
            name="",
            parent=prnt,
            pos=wx.Point(0, 0),
            size=wx.Size(1024, 748),  # size = wx.DisplaySize(),
            style=wx.DEFAULT_FRAME_STYLE,
            title="InVesalius 3",
        )
        self.Center(wx.BOTH)
        icon_path = inv_paths.ICON_DIR.joinpath("invesalius.ico")
        self.SetIcon(wx.Icon(str(icon_path), wx.BITMAP_TYPE_ICO))

        self.mw = None
        self._last_viewer_orientation_focus = const.AXIAL_STR

        if sys.platform != "darwin":
            self.Maximize()

        self.sizeChanged = True
        # Necessary update AUI (statusBar in special)
        # when maximized in the Win 7 and XP
        self.SetSize(self.GetSize())
        # self.SetSize(wx.Size(1024, 748))

        self._show_navigator_message = True

        # to control check and unckeck of menu view -> interpolated_slices
        main_menu = MenuBar(self)

        self.actived_interpolated_slices = main_menu.view_menu
        self.actived_navigation_mode = main_menu.mode_menu
        self.actived_dbs_mode = main_menu.mode_dbs
        self.tools_menu = main_menu.tools_menu

        # Set menus, status and task bar
        self.SetMenuBar(main_menu)
        self.SetStatusBar(StatusBar(self))

        # Set TaskBarIcon
        # TaskBarIcon(self)

        # Create aui manager and insert content in it
        self.__init_aui()

        # Initialize bind to pubsub events
        self.__bind_events()
        self.__bind_events_wx()

        # log.initLogger()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        sub(self._BeginBusyCursor, "Begin busy cursor")
        sub(self._ShowContentPanel, "Cancel DICOM load")
        sub(self._EndBusyCursor, "End busy cursor")
        sub(self._HideContentPanel, "Hide content panel")
        sub(self._HideImportPanel, "Hide import panel")
        sub(self._HideTask, "Hide task panel")
        sub(self._SetProjectName, "Set project name")
        sub(self._ShowContentPanel, "Show content panel")
        sub(self._ShowImportPanel, "Show import panel in frame")
        sub(self.ShowPreferences, "Open preferences menu")
        # sub(self._ShowHelpMessage, 'Show help message')
        sub(self._ShowImportNetwork, "Show retrieve dicom panel")
        sub(self._ShowImportBitmap, "Show import bitmap panel in frame")
        sub(self._ShowTask, "Show task panel")
        sub(self._UpdateAUI, "Update AUI")
        sub(self._UpdateViewerFocus, "Set viewer orientation focus")
        sub(self._Exit, "Exit")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_IDLE, self.OnIdle)
        self.Bind(wx.EVT_MENU, self.OnMenuClick)

        # Close InVesalius main window, hence exit the software.
        self.Bind(wx.EVT_CLOSE, self.OnExit)

        # Bind global key events.
        self.Bind(wx.EVT_CHAR_HOOK, self.OnGlobalKey)

    def OnGlobalKey(self, event):
        """
        Handle all key events at a global level.
        """
        keycode = event.GetKeyCode()

        # If the key is a move marker key, publish a message to move the marker.
        if keycode in const.MOVEMENT_KEYCODES:
            Publisher.sendMessage("Move marker by keyboard", keycode=keycode)
            return

        # Similarly with 'Del' key; publish a message to delete selected markers.
        if keycode == wx.WXK_DELETE:
            Publisher.sendMessage("Delete selected markers")
            return

        # For all other keys, continue with the normal event handling (propagate the event).
        event.Skip()

    def __init_aui(self):
        """
        Build AUI manager and all panels inside InVesalius frame.
        """
        # Tell aui_manager to manage this frame
        aui_manager = self.aui_manager = wx.aui.AuiManager()
        aui_manager.SetManagedWindow(self)

        # XXX: Create viewers panel before task panel: the latter depends on the
        # former already existing - this is because when a state is restored after a
        # crash, we add markers to task panel, which then communicates to the viewers
        # panel by publishing an 'Add marker' message.
        #
        viewers_panel = viewers.Panel(self)
        task_panel = tasks.Panel(self)
        import_panel = imp.Panel(self)
        import_bitmap_panel = imp_bmp.Panel(self)

        # Add panels to manager

        # First, the task panel, to be on the left fo the frame
        # This will be specific according to InVesalius application
        aui_manager.AddPane(task_panel, wx.aui.AuiPaneInfo().Name("Tasks").CaptionVisible(False))

        # Then, add the viewers panel, which will contain slices and
        # volume panels. In future this might also be specific
        # according to InVesalius application (e.g. panoramic
        # visualization, in odontology)
        aui_manager.AddPane(
            viewers_panel,
            wx.aui.AuiPaneInfo()
            .Caption(_("Data panel"))
            .CaptionVisible(False)
            .Centre()
            .CloseButton(False)
            .Floatable(False)
            .Hide()
            .Layer(1)
            .MaximizeButton(True)
            .Name("Data")
            .Position(1),
        )

        # This is the DICOM import panel. When the two panels above as dicom        # are shown, this should be hiden
        caption = _("Preview medical data to be reconstructed")
        aui_manager.AddPane(
            import_panel,
            wx.aui.AuiPaneInfo()
            .Name("Import")
            .CloseButton(False)
            .Centre()
            .Hide()
            .MaximizeButton(False)
            .Floatable(True)
            .Caption(caption)
            .CaptionVisible(True),
        )

        caption = _("Preview bitmap to be reconstructed")
        aui_manager.AddPane(
            import_bitmap_panel,
            wx.aui.AuiPaneInfo()
            .Name("ImportBMP")
            .CloseButton(False)
            .Centre()
            .Hide()
            .MaximizeButton(False)
            .Floatable(True)
            .Caption(caption)
            .CaptionVisible(True),
        )

        #  ncaption = _("Retrieve DICOM from PACS")
        #  aui_manager.AddPane(imp_net.Panel(self), wx.aui.AuiPaneInfo().
        #  Name("Retrieve").Centre().Hide().
        #  MaximizeButton(True).Floatable(True).
        #  Caption(ncaption).CaptionVisible(True))

        # Add toolbars to manager
        # This is pretty tricky -- order on win32 is inverted when
        # compared to linux2 & darwin
        if sys.platform == "win32" or wx.VERSION >= (4, 1):
            t1 = ProjectToolBar(self)
            t2 = HistoryToolBar(self)
            t3 = LayoutToolBar(self)
            t4 = ObjectToolBar(self)
            t5 = SliceToolBar(self)
        else:
            t5 = ProjectToolBar(self)
            t4 = HistoryToolBar(self)
            t3 = LayoutToolBar(self)
            t2 = ObjectToolBar(self)
            t1 = SliceToolBar(self)

        aui_manager.AddPane(
            t1,
            wx.aui.AuiPaneInfo()
            .Name("General Features Toolbar")
            .ToolbarPane()
            .Top()
            .Floatable(False)
            .LeftDockable(False)
            .RightDockable(False),
        )

        aui_manager.AddPane(
            t2,
            wx.aui.AuiPaneInfo()
            .Name("Layout Toolbar")
            .ToolbarPane()
            .Top()
            .Floatable(False)
            .LeftDockable(False)
            .RightDockable(False),
        )

        aui_manager.AddPane(
            t3,
            wx.aui.AuiPaneInfo()
            .Name("Project Toolbar")
            .ToolbarPane()
            .Top()
            .Floatable(False)
            .LeftDockable(False)
            .RightDockable(False),
        )

        aui_manager.AddPane(
            t4,
            wx.aui.AuiPaneInfo()
            .Name("Slice Toolbar")
            .ToolbarPane()
            .Top()
            .Floatable(False)
            .LeftDockable(False)
            .RightDockable(False),
        )

        aui_manager.AddPane(
            t5,
            wx.aui.AuiPaneInfo()
            .Name("History Toolbar")
            .ToolbarPane()
            .Top()
            .Floatable(False)
            .LeftDockable(False)
            .RightDockable(False),
        )

        aui_manager.Update()
        self.aui_manager = aui_manager

        # TODO: Allow saving and restoring perspectives
        self.perspective_all = aui_manager.SavePerspective()

        self.Layout()

    def _BeginBusyCursor(self):
        """
        Start busy cursor.
        Note: _EndBusyCursor should be called after.
        """
        wx.BeginBusyCursor()

    def _EndBusyCursor(self):
        """
        End busy cursor.
        Note: _BeginBusyCursor should have been called previously.
        """
        try:
            wx.EndBusyCursor()
        except wx.PyAssertionError:
            # no matching wxBeginBusyCursor() for wxEndBusyCursor()
            pass

    def _Exit(self):
        """
        Exit InVesalius.
        """
        self.aui_manager.UnInit()
        for child in wx.GetTopLevelWindows():
            child.Destroy()
        self.Destroy()
        if hasattr(sys, "frozen") and sys.platform == "darwin":
            sys.exit(0)

    def _HideContentPanel(self):
        """
        Hide data and tasks panels.
        """
        aui_manager = self.aui_manager
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _HideImportPanel(self):
        """
        Hide import panel and show tasks.
        """
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _HideTask(self):
        """
        Hide task panel.
        """
        self.aui_manager.GetPane("Tasks").Hide()
        self.aui_manager.Update()

    def _SetProjectName(self, proj_name=""):
        """
        Set project name into frame's title.
        """
        if not (proj_name):
            self.SetTitle("InVesalius 3")
        else:
            self.SetTitle("%s - InVesalius 3" % (proj_name))

    def _ShowContentPanel(self):
        """
        Show viewers and task, hide import panel.
        """
        Publisher.sendMessage("Set layout button full")
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)

        aui_manager.GetPane("ImportBMP").Show(0)

        aui_manager.GetPane("Data").Show(1)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _ShowImportNetwork(self):
        """
        Show viewers and task, hide import panel.
        """
        Publisher.sendMessage("Set layout button full")
        aui_manager = self.aui_manager
        aui_manager.GetPane("Retrieve").Show(1)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(0)
        aui_manager.GetPane("Import").Show(0)
        aui_manager.Update()

    def _ShowImportBitmap(self):
        """
        Show viewers and task, hide import panel.
        """
        Publisher.sendMessage("Set layout button full")
        aui_manager = self.aui_manager
        aui_manager.GetPane("ImportBMP").Show(1)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(0)
        aui_manager.GetPane("Import").Show(0)
        aui_manager.Update()

    def _ShowHelpMessage(self, message):
        aui_manager = self.aui_manager
        pos = aui_manager.GetPane("Data").window.GetScreenPosition()
        self.mw = MessageWatershed(self, message)
        self.mw.SetPosition(pos)
        self.mw.Show()

    def _ShowImportPanel(self):
        """
        Show only DICOM import panel. as dicom"""
        Publisher.sendMessage("Set layout button data only")
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(1)
        aui_manager.GetPane("Data").Show(0)
        aui_manager.GetPane("Tasks").Show(0)
        aui_manager.Update()

    def _ShowTask(self):
        """
        Show task panel.
        """
        self.aui_manager.GetPane("Tasks").Show()
        self.aui_manager.Update()

    def _UpdateAUI(self):
        """
        Refresh AUI panels/data.
        """
        self.aui_manager.Update()

    def _UpdateViewerFocus(self, orientation):
        if orientation in (const.AXIAL_STR, const.CORONAL_STR, const.SAGITAL_STR):
            self._last_viewer_orientation_focus = orientation

    def CloseProject(self):
        Publisher.sendMessage("Close Project")

    def ExitDialog(self):
        msg = _("Are you sure you want to exit?")
        if sys.platform == "darwin":
            dialog = wx.RichMessageDialog(
                None, "", msg, wx.ICON_QUESTION | wx.YES_NO | wx.NO_DEFAULT
            )
            dialog.ShowCheckBox("Store session", True)
        else:
            dialog = wx.RichMessageDialog(
                None, msg, "Invesalius 3", wx.ICON_QUESTION | wx.YES_NO | wx.NO_DEFAULT
            )
            dialog.ShowCheckBox("Store session", True)

        answer = dialog.ShowModal()
        save = dialog.IsCheckBoxChecked()
        dialog.Destroy()

        # logger = log.MyLogger()

        if not save and answer == wx.ID_YES:
            log.invLogger.closeLogging()
            return 1  # Exit and delete session
        elif save and answer == wx.ID_YES:
            log.invLogger.closeLogging()
            return 2  # Exit without deleting session
        else:
            return 0  # Don't Exit

    def OnExit(self, evt):
        """
        Exit InVesalius: disconnect tracker and send 'Exit' message.
        """
        status = self.ExitDialog()
        if status:
            Publisher.sendMessage("Disconnect tracker")
            Publisher.sendMessage("Exit")
            if status == 1:
                Publisher.sendMessage("Exit session")

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
            self.ShowImportOtherFiles(id)
        elif id == const.ID_NIFTI_IMPORT:
            self.ShowImportOtherFiles(id)
        elif id == const.ID_PARREC_IMPORT:
            self.ShowImportOtherFiles(id)
        elif id == const.ID_TIFF_JPG_PNG:
            self.ShowBitmapImporter()
        elif id == const.ID_PROJECT_SAVE:
            session = ses.Session()
            if session.temp_item:
                self.ShowSaveAsProject()
            else:
                self.SaveProject()
        elif id == const.ID_PROJECT_SAVE_AS:
            self.ShowSaveAsProject()
        elif id == const.ID_EXPORT_SLICE:
            self.ExportProject()
        elif id == const.ID_PROJECT_PROPERTIES:
            self.ShowProjectProperties()
        elif id == const.ID_PROJECT_CLOSE:
            self.CloseProject()
        elif id == const.ID_EXIT:
            self.OnExit(None)
        elif id == const.ID_ABOUT:
            self.ShowAbout()
        elif id == const.ID_START:
            self.ShowGettingStarted()
        elif id == const.ID_PREFERENCES or id == const.ID_PREFERENCES_TOOLBAR:
            self.ShowPreferences()
        elif id == const.ID_DICOM_NETWORK:
            self.ShowRetrieveDicomPanel()
        elif id in (const.ID_FLIP_X, const.ID_FLIP_Y, const.ID_FLIP_Z):
            axis = {const.ID_FLIP_X: 2, const.ID_FLIP_Y: 1, const.ID_FLIP_Z: 0}[id]
            self.FlipVolume(axis)
        elif id in (const.ID_SWAP_XY, const.ID_SWAP_XZ, const.ID_SWAP_YZ):
            axes = {const.ID_SWAP_XY: (2, 1), const.ID_SWAP_XZ: (2, 0), const.ID_SWAP_YZ: (1, 0)}[
                id
            ]
            self.SwapAxes(axes)
        elif id == wx.ID_UNDO:
            self.OnUndo()
        elif id == wx.ID_REDO:
            self.OnRedo()
        elif id == const.ID_GOTO_SLICE:
            self.OnGotoSlice()
        elif id == const.ID_GOTO_COORD:
            self.GoToDialogScannerCoord()

        elif id == const.ID_BOOLEAN_MASK:
            self.OnMaskBoolean()
        elif id == const.ID_CLEAN_MASK:
            self.OnCleanMask()

        elif id == const.ID_REORIENT_IMG:
            self.OnReorientImg()

        elif id == const.ID_MASK_DENSITY_MEASURE:
            ddlg = dlg.MaskDensityDialog(self)
            ddlg.Show()

        elif id == const.ID_MANUAL_WWWL:
            wwwl_dlg = dlg.ManualWWWLDialog(self)
            wwwl_dlg.Show()

        elif id == const.ID_THRESHOLD_SEGMENTATION:
            Publisher.sendMessage("Show panel", panel_id=const.ID_THRESHOLD_SEGMENTATION)
            Publisher.sendMessage("Disable actual style")
            Publisher.sendMessage("Enable style", style=const.STATE_DEFAULT)

        elif id == const.ID_MANUAL_SEGMENTATION:
            Publisher.sendMessage("Show panel", panel_id=const.ID_MANUAL_SEGMENTATION)
            Publisher.sendMessage("Disable actual style")
            Publisher.sendMessage("Enable style", style=const.SLICE_STATE_EDITOR)

        elif id == const.ID_WATERSHED_SEGMENTATION:
            Publisher.sendMessage("Show panel", panel_id=const.ID_WATERSHED_SEGMENTATION)
            Publisher.sendMessage("Disable actual style")
            Publisher.sendMessage("Enable style", style=const.SLICE_STATE_WATERSHED)

        elif id == const.ID_FLOODFILL_MASK:
            self.OnFillHolesManually()

        elif id == const.ID_FILL_HOLE_AUTO:
            self.OnFillHolesAutomatically()

        elif id == const.ID_REMOVE_MASK_PART:
            self.OnRemoveMaskParts()

        elif id == const.ID_SELECT_MASK_PART:
            self.OnSelectMaskParts()

        elif id == const.ID_FLOODFILL_SEGMENTATION:
            self.OnFFillSegmentation()

        elif id == const.ID_SEGMENTATION_BRAIN:
            self.OnBrainSegmentation()
        elif id == const.ID_SEGMENTATION_TRACHEA:
            self.OnTracheSegmentation()
        elif id == const.ID_SEGMENTATION_MANDIBLE_CT:
            self.OnMandibleCTSegmentation()

        elif id == const.ID_VIEW_INTERPOLATED:
            st = self.actived_interpolated_slices.IsChecked(const.ID_VIEW_INTERPOLATED)
            if st:
                self.OnInterpolatedSlices(True)
            else:
                self.OnInterpolatedSlices(False)

        elif id == const.ID_MODE_NAVIGATION:
            Publisher.sendMessage("Hide dbs folder")
            Publisher.sendMessage("Show target button")
            self.actived_dbs_mode.Check(0)
            st = self.actived_navigation_mode.IsChecked(const.ID_MODE_NAVIGATION)
            self.OnNavigationMode(st)

        elif id == const.ID_MODE_DBS:
            self.OnDbsMode()

        elif id == const.ID_CROP_MASK:
            self.OnCropMask()

        elif id == const.ID_MASK_3D_PREVIEW:
            self.OnEnableMask3DPreview(value=self.tools_menu.IsChecked(const.ID_MASK_3D_PREVIEW))

        elif id == const.ID_MASK_3D_AUTO_RELOAD:
            session = ses.Session()
            session.SetConfig(
                "auto_reload_preview", self.tools_menu.IsChecked(const.ID_MASK_3D_AUTO_RELOAD)
            )

        elif id == const.ID_MASK_3D_RELOAD:
            self.OnUpdateMaskPreview()

        elif id == const.ID_CREATE_SURFACE:
            Publisher.sendMessage("Open create surface dialog")

        elif id == const.ID_CREATE_MASK:
            Publisher.sendMessage("New mask from shortcut")

        elif id == const.ID_PLUGINS_SHOW_PATH:
            self.ShowPluginsFolder()

    def OnDbsMode(self):
        st = self.actived_dbs_mode.IsChecked()
        Publisher.sendMessage("Hide target button")
        if st:
            self.OnNavigationMode(st)
            Publisher.sendMessage("Show dbs folder")
        else:
            self.OnNavigationMode(st)
            Publisher.sendMessage("Hide dbs folder")
        self.actived_navigation_mode.Check(const.ID_MODE_NAVIGATION, 0)

    def OnInterpolatedSlices(self, status):
        Publisher.sendMessage("Set interpolated slices", flag=status)

    def OnNavigationMode(self, status):
        if status and self._show_navigator_message and sys.platform != "win32":
            wx.MessageBox(
                _("Currently the Navigation mode is only working on Windows"),
                "Info",
                wx.OK | wx.ICON_INFORMATION,
            )
            self._show_navigator_message = False
        Publisher.sendMessage("Set navigation mode", status=status)
        if not status:
            Publisher.sendMessage("Remove sensors ID")

    def OnSize(self, evt):
        """
        Refresh GUI when frame is resized.
        """
        evt.Skip()
        self.Reposition()
        self.sizeChanged = True

    def OnIdle(self, evt):
        if self.sizeChanged:
            self.Reposition()

    def Reposition(self):
        Publisher.sendMessage(("ProgressBar Reposition"))
        self.sizeChanged = False

    def OnMove(self, evt):
        aui_manager = self.aui_manager
        pos = aui_manager.GetPane("Data").window.GetScreenPosition()
        self.mw.SetPosition(pos)

    def ShowPreferences(self, page=0):
        preferences_dialog = preferences.Preferences(self, page)
        preferences_dialog.LoadPreferences()
        preferences_dialog.Center()

        if preferences_dialog.ShowModal() == wx.ID_OK:
            values = preferences_dialog.GetPreferences()

            preferences_dialog.Destroy()

            session = ses.Session()

            rendering = values[const.RENDERING]
            surface_interpolation = values[const.SURFACE_INTERPOLATION]
            language = values[const.LANGUAGE]
            slice_interpolation = values[const.SLICE_INTERPOLATION]
            file_logging = values[const.FILE_LOGGING]
            file_logging_level = values[const.FILE_LOGGING_LEVEL]
            append_log_file = values[const.APPEND_LOG_FILE]
            logging_file = values[const.LOGFILE]
            console_logging = values[const.CONSOLE_LOGGING]
            console_logging_level = values[const.CONSOLE_LOGGING_LEVEL]

            session.SetConfig("rendering", rendering)
            session.SetConfig("surface_interpolation", surface_interpolation)
            session.SetConfig("language", language)
            session.SetConfig("slice_interpolation", slice_interpolation)
            session.SetConfig("file_logging", file_logging)
            session.SetConfig("file_logging_level", file_logging_level)
            session.SetConfig("append_log_file", append_log_file)
            session.SetConfig("logging_file", logging_file)
            session.SetConfig("console_logging", console_logging)
            session.SetConfig("console_logging_level", console_logging_level)

            Publisher.sendMessage("Remove Volume")
            Publisher.sendMessage("Reset Raycasting")
            Publisher.sendMessage("Update Slice Interpolation")
            Publisher.sendMessage("Update Slice Interpolation MenuBar")
            Publisher.sendMessage("Update Navigation Mode MenuBar")
            Publisher.sendMessage("Update Surface Interpolation")

    def ShowAbout(self):
        """
        Shows about dialog.
        """
        dlg.ShowAboutDialog(self)

    def SaveProject(self):
        """
        Save project.
        """
        Publisher.sendMessage("Show save dialog", save_as=False)

    def ShowGettingStarted(self):
        """
        Show getting started window.
        """
        webbrowser.open("https://invesalius.github.io/docs/user_guide/user_guide.html")

    def ShowImportDicomPanel(self):
        """
        Show import DICOM panel. as dicom"""
        Publisher.sendMessage("Show import directory dialog")

    def ShowImportOtherFiles(self, id_file):
        """
        Show import Analyze, NiFTI1 or PAR/REC dialog.
        """
        Publisher.sendMessage("Show import other files dialog", id_type=id_file)

    def ShowRetrieveDicomPanel(self):
        Publisher.sendMessage("Show retrieve dicom panel")

    def ShowOpenProject(self):
        """
        Show open project dialog.
        """
        Publisher.sendMessage("Show open project dialog")

    def ShowSaveAsProject(self):
        """
        Show save as dialog.
        """
        Publisher.sendMessage("Show save dialog", save_as=True)

    def ExportProject(self):
        """
        Show save dialog to export slice.
        """
        p = prj.Project()

        session = ses.Session()
        last_directory = session.GetConfig("last_directory_export_prj", "")

        fdlg = wx.FileDialog(
            None,
            "Export slice ...",
            last_directory,  # last used directory
            os.path.split(p.name)[-1],  # initial filename
            WILDCARD_EXPORT_SLICE,
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if fdlg.ShowModal() == wx.ID_OK:
            filename = fdlg.GetPath()
            ext = IDX_EXT[fdlg.GetFilterIndex()]
            dirpath = os.path.split(filename)[0]
            if not filename.endswith(ext):
                filename += ext
            try:
                p.export_project(filename)
            except (OSError, IOError) as err:
                if err.errno == errno.EACCES:
                    message = "It was not possible to save because you don't have permission to write at {}".format(
                        dirpath
                    )
                else:
                    message = "It was not possible to save because"
                d = dlg.ErrorMessageBox(None, "Save project error", "{}:\n{}".format(message, err))
                d.ShowModal()
                d.Destroy()
            else:
                session.SetConfig("last_directory_export_prj", dirpath)

    def ShowProjectProperties(self):
        window = project_properties.ProjectProperties(self)
        if window.ShowModal() == wx.ID_OK:
            p = prj.Project()
            if window.name_txt.GetValue() != p.name:
                p.name = window.name_txt.GetValue()

                session = ses.Session()
                session.ChangeProject()

                self._SetProjectName(p.name)

        window.Destroy()

    def ShowBitmapImporter(self):
        """
        Tiff, BMP, JPEG and PNG
        """
        Publisher.sendMessage("Show bitmap dialog")

    def FlipVolume(self, axis):
        Publisher.sendMessage("Flip volume", axis=axis)
        Publisher.sendMessage("Reload actual slice")

    def SwapAxes(self, axes):
        Publisher.sendMessage("Swap volume axes", axes=axes)
        Publisher.sendMessage("Update scroll")
        Publisher.sendMessage("Reload actual slice")

    def OnUndo(self):
        Publisher.sendMessage("Undo edition")

    def OnRedo(self):
        Publisher.sendMessage("Redo edition")

    def OnGotoSlice(self):
        gt_dialog = dlg.GoToDialog(init_orientation=self._last_viewer_orientation_focus)
        gt_dialog.CenterOnParent()
        gt_dialog.ShowModal()
        self.Refresh()

    def GoToDialogScannerCoord(self):
        gts_dialog = dlg.GoToDialogScannerCoord()
        gts_dialog.CenterOnParent()
        gts_dialog.ShowModal()
        self.Refresh()

    def OnMaskBoolean(self):
        Publisher.sendMessage("Show boolean dialog")

    def OnCleanMask(self):
        Publisher.sendMessage("Clean current mask")
        Publisher.sendMessage("Reload actual slice")

    def OnReorientImg(self):
        Publisher.sendMessage("Enable style", style=const.SLICE_STATE_REORIENT)
        rdlg = dlg.ReorientImageDialog()
        rdlg.Show()

    def OnFillHolesManually(self):
        Publisher.sendMessage("Enable style", style=const.SLICE_STATE_MASK_FFILL)

    def OnFillHolesAutomatically(self):
        fdlg = dlg.FillHolesAutoDialog(_("Fill holes automatically"))
        fdlg.Show()

    def OnRemoveMaskParts(self):
        Publisher.sendMessage("Enable style", style=const.SLICE_STATE_REMOVE_MASK_PARTS)

    def OnSelectMaskParts(self):
        Publisher.sendMessage("Enable style", style=const.SLICE_STATE_SELECT_MASK_PARTS)

    def OnFFillSegmentation(self):
        Publisher.sendMessage("Enable style", style=const.SLICE_STATE_FFILL_SEGMENTATION)

    def OnBrainSegmentation(self):
        from invesalius.gui import deep_learning_seg_dialog

        if (
            deep_learning_seg_dialog.HAS_PLAIDML
            or deep_learning_seg_dialog.HAS_THEANO
            or deep_learning_seg_dialog.HAS_TORCH
        ):
            dlg = deep_learning_seg_dialog.BrainSegmenterDialog(self)
            dlg.Show()
        else:
            dlg = wx.MessageDialog(
                self,
                _(
                    "It's not possible to run brain segmenter because your system doesn't have the following modules installed:"
                )
                + " Torch, PlaidML or Theano",
                "InVesalius 3 - Brain segmenter",
                wx.ICON_INFORMATION | wx.OK,
            )
            dlg.ShowModal()
            dlg.Destroy()

    def OnTracheSegmentation(self):
        from invesalius.gui import deep_learning_seg_dialog

        if deep_learning_seg_dialog.HAS_TORCH:
            dlg = deep_learning_seg_dialog.TracheaSegmenterDialog(self)
            dlg.Show()
        else:
            dlg = wx.MessageDialog(
                self,
                _(
                    "It's not possible to run trachea segmenter because your system doesn't have the following modules installed:"
                )
                + " Torch",
                "InVesalius 3 - Trachea segmenter",
                wx.ICON_INFORMATION | wx.OK,
            )
            dlg.ShowModal()
            dlg.Destroy()

    def OnMandibleCTSegmentation(self):
        from invesalius.gui import deep_learning_seg_dialog

        if deep_learning_seg_dialog.HAS_TORCH:
            dlg = deep_learning_seg_dialog.MandibleSegmenterDialog(self)
            dlg.Show()
        else:
            dlg = wx.MessageDialog(
                self,
                _(
                    "It's not possible to run mandible segmenter because your system doesn't have the following modules installed:"
                )
                + " Torch",
                "InVesalius 3 - Trachea segmenter",
                wx.ICON_INFORMATION | wx.OK,
            )
            dlg.ShowModal()
            dlg.Destroy()

    def OnInterpolatedSlices(self, status):
        Publisher.sendMessage("Set interpolated slices", flag=status)

    def OnCropMask(self):
        Publisher.sendMessage("Enable style", style=const.SLICE_STATE_CROP_MASK)

    def OnEnableMask3DPreview(self, value):
        if value:
            Publisher.sendMessage("Enable mask 3D preview")
        else:
            Publisher.sendMessage("Disable mask 3D preview")

    def OnUpdateMaskPreview(self):
        Publisher.sendMessage("Update mask 3D preview")

    def ShowPluginsFolder(self):
        """
        Show getting started window.
        """
        inv_paths.create_conf_folders()
        path = str(inv_paths.USER_PLUGINS_DIRECTORY)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


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
        self._plugins_menu_ids = {}

        # Used to enable/disable menu items if project is opened or
        # not. Eg. save should only be available if a project is open
        self.enable_items = [
            const.ID_PROJECT_SAVE,
            const.ID_PROJECT_SAVE_AS,
            const.ID_EXPORT_SLICE,
            const.ID_PROJECT_PROPERTIES,
            const.ID_PROJECT_CLOSE,
            const.ID_REORIENT_IMG,
            const.ID_FLOODFILL_MASK,
            const.ID_FILL_HOLE_AUTO,
            const.ID_REMOVE_MASK_PART,
            const.ID_SELECT_MASK_PART,
            const.ID_FLOODFILL_SEGMENTATION,
            const.ID_FLIP_X,
            const.ID_FLIP_Y,
            const.ID_FLIP_Z,
            const.ID_SWAP_XY,
            const.ID_SWAP_XZ,
            const.ID_SWAP_YZ,
            const.ID_THRESHOLD_SEGMENTATION,
            const.ID_MANUAL_SEGMENTATION,
            const.ID_WATERSHED_SEGMENTATION,
            const.ID_THRESHOLD_SEGMENTATION,
            const.ID_FLOODFILL_SEGMENTATION,
            const.ID_SEGMENTATION_BRAIN,
            const.ID_SEGMENTATION_TRACHEA,
            const.ID_SEGMENTATION_MANDIBLE_CT,
            const.ID_MASK_DENSITY_MEASURE,
            const.ID_CREATE_SURFACE,
            const.ID_CREATE_MASK,
            const.ID_GOTO_SLICE,
            const.ID_MANUAL_WWWL,
        ]
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
        sub = Publisher.subscribe
        sub(self.OnEnableState, "Enable state project")
        sub(self.OnEnableUndo, "Enable undo")
        sub(self.OnEnableRedo, "Enable redo")
        sub(self.OnEnableGotoCoord, "Enable Go-to-Coord")
        sub(self.OnEnableNavigation, "Navigation status")

        sub(self.OnAddMask, "Add mask")
        sub(self.OnRemoveMasks, "Remove masks")
        sub(self.OnShowMask, "Show mask")
        sub(self.OnUpdateSliceInterpolation, "Update Slice Interpolation MenuBar")
        sub(self.OnUpdateNavigationMode, "Update Navigation Mode MenuBar")

        sub(self.AddPluginsItems, "Add plugins menu items")

        self.num_masks = 0

    def __init_items(self):
        """
        Create all menu and submenus, and add them to self.
        """
        # TODO: This definetely needs improvements... ;)

        # Import Others Files
        others_file_menu = wx.Menu()
        others_file_menu.Append(const.ID_ANALYZE_IMPORT, _("Analyze 7.5"))
        others_file_menu.Append(const.ID_NIFTI_IMPORT, _("NIfTI 1"))
        others_file_menu.Append(const.ID_PARREC_IMPORT, _("PAR/REC"))
        others_file_menu.Append(const.ID_TIFF_JPG_PNG, "TIFF,BMP,JPG or PNG (\xb5CT)")

        # FILE
        file_menu = wx.Menu()
        app = file_menu.Append
        app(const.ID_DICOM_IMPORT, _("Import DICOM...\tCtrl+I"))
        # app(const.ID_DICOM_NETWORK, _("Retrieve DICOM from PACS"))
        file_menu.Append(const.ID_IMPORT_OTHERS_FILES, _("Import other files..."), others_file_menu)
        app(const.ID_PROJECT_OPEN, _("Open project...\tCtrl+O"))
        app(const.ID_PROJECT_SAVE, _("Save project\tCtrl+S"))
        app(const.ID_PROJECT_SAVE_AS, _("Save project as...\tCtrl+Shift+S"))
        app(const.ID_EXPORT_SLICE, _("Export project"))
        app(const.ID_PROJECT_PROPERTIES, _("Project properties"))
        app(const.ID_PROJECT_CLOSE, _("Close project"))
        file_menu.AppendSeparator()
        # app(const.ID_PROJECT_INFO, _("Project Information..."))
        # file_menu.AppendSeparator()
        # app(const.ID_SAVE_SCREENSHOT, _("Save Screenshot"))
        # app(const.ID_PRINT_SCREENSHOT, _("Print Screenshot"))
        # file_menu.AppendSeparator()
        # app(1, "C:\InvData\sample.inv")
        # file_menu.AppendSeparator()
        app(const.ID_EXIT, _("Exit\tCtrl+Q"))

        file_edit = wx.Menu()

        file_edit.Append(wx.ID_UNDO, _("Undo\tCtrl+Z")).Enable(False)
        file_edit.Append(wx.ID_REDO, _("Redo\tCtrl+Y")).Enable(False)
        file_edit.Append(const.ID_GOTO_SLICE, _("Go to slice ...\tCtrl+G"))
        file_edit.Append(const.ID_GOTO_COORD, _("Go to scanner coord ...\t")).Enable(False)

        # app(const.ID_EDIT_LIST, "Show Undo List...")
        #################################################################

        # Tool menu
        tools_menu = wx.Menu()

        # Mask Menu
        mask_menu = wx.Menu()

        self.new_mask_menu = mask_menu.Append(const.ID_CREATE_MASK, _("New\tCtrl+Shift+M"))
        self.new_mask_menu.Enable(False)

        self.bool_op_menu = mask_menu.Append(
            const.ID_BOOLEAN_MASK, _("Boolean operations\tCtrl+Shift+B")
        )
        self.bool_op_menu.Enable(False)

        self.clean_mask_menu = mask_menu.Append(const.ID_CLEAN_MASK, _("Clean Mask\tCtrl+Shift+A"))
        self.clean_mask_menu.Enable(False)

        mask_menu.AppendSeparator()

        self.fill_hole_mask_menu = mask_menu.Append(
            const.ID_FLOODFILL_MASK, _("Fill holes manually\tCtrl+Shift+H")
        )
        self.fill_hole_mask_menu.Enable(False)

        self.fill_hole_auto_menu = mask_menu.Append(
            const.ID_FILL_HOLE_AUTO, _("Fill holes automatically\tCtrl+Shift+J")
        )
        self.fill_hole_mask_menu.Enable(False)

        mask_menu.AppendSeparator()

        self.remove_mask_part_menu = mask_menu.Append(
            const.ID_REMOVE_MASK_PART, _("Remove parts\tCtrl+Shift+K")
        )
        self.remove_mask_part_menu.Enable(False)

        self.select_mask_part_menu = mask_menu.Append(
            const.ID_SELECT_MASK_PART, _("Select parts\tCtrl+Shift+L")
        )
        self.select_mask_part_menu.Enable(False)

        mask_menu.AppendSeparator()

        self.crop_mask_menu = mask_menu.Append(const.ID_CROP_MASK, _("Crop"))
        self.crop_mask_menu.Enable(False)

        mask_menu.AppendSeparator()

        mask_preview_menu = wx.Menu()

        self.mask_preview = mask_preview_menu.Append(
            const.ID_MASK_3D_PREVIEW, _("Enable") + "\tCtrl+Shift+P", "", wx.ITEM_CHECK
        )
        self.mask_preview.Enable(False)

        self.mask_auto_reload = mask_preview_menu.Append(
            const.ID_MASK_3D_AUTO_RELOAD, _("Auto reload") + "\tCtrl+Shift+D", "", wx.ITEM_CHECK
        )

        session = ses.Session()
        auto_reload_preview = session.GetConfig("auto_reload_preview")

        self.mask_auto_reload.Check(auto_reload_preview)
        self.mask_auto_reload.Enable(False)

        self.mask_preview_reload = mask_preview_menu.Append(
            const.ID_MASK_3D_RELOAD, _("Reload") + "\tCtrl+Shift+R"
        )
        self.mask_preview_reload.Enable(False)

        mask_menu.Append(-1, _("Mask 3D Preview"), mask_preview_menu)

        # Segmentation Menu
        segmentation_menu = wx.Menu()
        self.threshold_segmentation = segmentation_menu.Append(
            const.ID_THRESHOLD_SEGMENTATION, _("Threshold\tCtrl+Shift+T")
        )
        self.manual_segmentation = segmentation_menu.Append(
            const.ID_MANUAL_SEGMENTATION, _("Manual segmentation\tCtrl+Shift+E")
        )
        self.watershed_segmentation = segmentation_menu.Append(
            const.ID_WATERSHED_SEGMENTATION, _("Watershed\tCtrl+Shift+W")
        )
        self.ffill_segmentation = segmentation_menu.Append(
            const.ID_FLOODFILL_SEGMENTATION, _("Region growing\tCtrl+Shift+G")
        )
        self.ffill_segmentation.Enable(False)
        segmentation_menu.AppendSeparator()
        segmentation_menu.Append(const.ID_SEGMENTATION_BRAIN, _("Brain segmentation (MRI T1)"))
        segmentation_menu.Append(const.ID_SEGMENTATION_TRACHEA, _("Trachea segmentation (CT)"))
        segmentation_menu.Append(const.ID_SEGMENTATION_MANDIBLE_CT, _("Mandible segmentation (CT)"))

        # Surface Menu
        surface_menu = wx.Menu()
        self.create_surface = surface_menu.Append(const.ID_CREATE_SURFACE, ("New\tCtrl+Shift+C"))
        self.create_surface.Enable(False)

        # Image menu
        image_menu = wx.Menu()

        # Flip
        flip_menu = wx.Menu()
        flip_menu.Append(const.ID_FLIP_X, _("Right - Left")).Enable(False)
        flip_menu.Append(const.ID_FLIP_Y, _("Anterior - Posterior")).Enable(False)
        flip_menu.Append(const.ID_FLIP_Z, _("Top - Bottom")).Enable(False)

        swap_axes_menu = wx.Menu()
        swap_axes_menu.Append(const.ID_SWAP_XY, _("From Right-Left to Anterior-Posterior")).Enable(
            False
        )
        swap_axes_menu.Append(const.ID_SWAP_XZ, _("From Right-Left to Top-Bottom")).Enable(False)
        swap_axes_menu.Append(const.ID_SWAP_YZ, _("From Anterior-Posterior to Top-Bottom")).Enable(
            False
        )

        image_menu.Append(wx.NewIdRef(), _("Flip"), flip_menu)
        image_menu.Append(wx.NewIdRef(), _("Swap axes"), swap_axes_menu)

        mask_density_menu = image_menu.Append(
            const.ID_MASK_DENSITY_MEASURE, _("Mask Density measure")
        )
        reorient_menu = image_menu.Append(const.ID_REORIENT_IMG, _("Reorient image\tCtrl+Shift+O"))
        image_menu.Append(const.ID_MANUAL_WWWL, _("Set WW&&WL manually"))

        reorient_menu.Enable(False)
        tools_menu.Append(-1, _("Image"), image_menu)
        tools_menu.Append(-1, _("Mask"), mask_menu)
        tools_menu.Append(-1, _("Segmentation"), segmentation_menu)
        tools_menu.Append(-1, _("Surface"), surface_menu)
        self.tools_menu = tools_menu

        # View
        self.view_menu = view_menu = wx.Menu()
        view_menu.Append(const.ID_VIEW_INTERPOLATED, _("Interpolated slices"), "", wx.ITEM_CHECK)

        v = self.SliceInterpolationStatus()
        self.view_menu.Check(const.ID_VIEW_INTERPOLATED, v)

        self.actived_interpolated_slices = self.view_menu

        # view_tool_menu = wx.Menu()
        # app = view_tool_menu.Append
        # app(const.ID_TOOL_PROJECT, "Project Toolbar")
        # app(const.ID_TOOL_LAYOUT, "Layout Toolbar")
        # app(const.ID_TOOL_OBJECT, "Object Toolbar")
        # app(const.ID_TOOL_SLICE, "Slice Toolbar")

        # view_layout_menu = wx.Menu()
        # app = view_layout_menu.Append
        # app(const.ID_TASK_BAR, "Task Bar")
        # app(const.ID_VIEW_FOUR, "Four View")

        # view_menu = wx.Menu()
        # app = view_menu.Append
        # appm = view_menu.Append
        # appm(-1, "Toolbars",view_tool_menu)
        # appm(-1, "Layout", view_layout_menu)
        # view_menu.AppendSeparator()
        # app(const.ID_VIEW_FULL, "Fullscreen\tCtrl+F")
        # view_menu.AppendSeparator()
        # app(const.ID_VIEW_TEXT, "2D & 3D Text")
        # view_menu.AppendSeparator()
        # app(const.ID_VIEW_3D_BACKGROUND, "3D Background Colour")

        # TOOLS
        # tools_menu = wx.Menu()

        # OPTIONS
        options_menu = wx.Menu()
        options_menu.Append(const.ID_PREFERENCES, _("Preferences"))

        # Mode
        self.mode_menu = mode_menu = wx.Menu()
        nav_menu = wx.Menu()
        nav_menu.Append(
            const.ID_MODE_NAVIGATION,
            _("Transcranial Magnetic Stimulation Mode\tCtrl+T"),
            "",
            wx.ITEM_CHECK,
        )
        # Under development
        self.mode_dbs = nav_menu.Append(
            const.ID_MODE_DBS, _("Deep Brain Stimulation Mode\tCtrl+B"), "", wx.ITEM_CHECK
        )
        self.mode_dbs.Enable(0)
        mode_menu.Append(-1, _("Navigation Mode"), nav_menu)

        v = self.NavigationModeStatus()
        self.mode_menu.Check(const.ID_MODE_NAVIGATION, v)

        self.actived_navigation_mode = self.mode_menu

        plugins_menu = wx.Menu()
        plugins_menu.Append(const.ID_PLUGINS_SHOW_PATH, _("Open Plugins folder"))
        self.plugins_menu = plugins_menu

        # HELP
        help_menu = wx.Menu()
        help_menu.Append(const.ID_START, _("Getting started..."))
        # help_menu.Append(108, "User Manual...")
        help_menu.AppendSeparator()
        help_menu.Append(const.ID_ABOUT, _("About..."))
        # help_menu.Append(107, "Check For Updates Now...")

        # if platform.system() == 'Darwin':
        # wx.App.SetMacAboutMenuItemId(const.ID_ABOUT)
        # wx.App.SetMacExitMenuItemId(const.ID_EXIT)

        # Add all menus to menubar
        self.Append(file_menu, _("File"))
        self.Append(file_edit, _("Edit"))
        self.Append(view_menu, _("View"))
        self.Append(tools_menu, _("Tools"))
        self.Append(plugins_menu, _("Plugins"))
        # self.Append(tools_menu, "Tools")
        self.Append(options_menu, _("Options"))
        self.Append(mode_menu, _("Mode"))
        self.Append(help_menu, _("Help"))

        plugins_menu.Bind(wx.EVT_MENU, self.OnPluginMenu)

    def OnPluginMenu(self, evt):
        id = evt.GetId()
        if id != const.ID_PLUGINS_SHOW_PATH:
            try:
                plugin_name = self._plugins_menu_ids[id]["name"]
                print("Loading plugin:", plugin_name)
                Publisher.sendMessage("Load plugin", plugin_name=plugin_name)
            except KeyError:
                print("Invalid plugin")
        evt.Skip()

    def SliceInterpolationStatus(self):
        session = ses.Session()
        slice_interpolation = session.GetConfig("slice_interpolation")

        return slice_interpolation != 0

    def NavigationModeStatus(self):
        session = ses.Session()
        mode = session.GetConfig("mode")

        return mode == 1

    def OnUpdateSliceInterpolation(self):
        v = self.SliceInterpolationStatus()
        self.view_menu.Check(const.ID_VIEW_INTERPOLATED, v)

    def OnUpdateNavigationMode(self):
        v = self.NavigationModeStatus()
        self.mode_menu.Check(const.ID_MODE_NAVIGATION, v)

    def AddPluginsItems(self, items):
        for menu_item in self.plugins_menu.GetMenuItems():
            if menu_item.GetId() != const.ID_PLUGINS_SHOW_PATH:
                self.plugins_menu.DestroyItem(menu_item)

        for item in items:
            _new_id = wx.NewIdRef()
            self._plugins_menu_ids[_new_id] = items[item]
            menu_item = self.plugins_menu.Append(_new_id, item, items[item]["description"])
            menu_item.Enable(items[item]["enable_startup"])

    def OnEnableState(self, state):
        """
        Based on given state, enables or disables menu items which
        depend if project is open or not.
        """
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

        # Disabling plugins menus that needs a project open
        for item in self._plugins_menu_ids:
            if not self._plugins_menu_ids[item]["enable_startup"]:
                self.Enable(item, False)

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. save) when project is opened.
        """
        for item in self.enable_items:
            self.Enable(item, True)

        # Enabling plugins menus that needs a project open
        for item in self._plugins_menu_ids:
            if not self._plugins_menu_ids[item]["enable_startup"]:
                self.Enable(item, True)

    def OnEnableUndo(self, value):
        if value:
            self.FindItemById(wx.ID_UNDO).Enable(True)
        else:
            self.FindItemById(wx.ID_UNDO).Enable(False)

    def OnEnableRedo(self, value):
        if value:
            self.FindItemById(wx.ID_REDO).Enable(True)
        else:
            self.FindItemById(wx.ID_REDO).Enable(False)

    def OnEnableGotoCoord(self, status=True):
        """
        Enable or disable goto coord depending on the imported affine matrix.
        :param status: True for enabling and False for disabling the Go-To-Coord
        """

        self.FindItemById(const.ID_GOTO_COORD).Enable(status)

    def OnEnableNavigation(self, nav_status, vis_status):
        """
        Disable mode menu when navigation is on.
        :param nav_status: Navigation status
        :param vis_status: Status of items visualization during navigation
        """
        value = nav_status
        if value:
            self.FindItemById(const.ID_MODE_NAVIGATION).Enable(False)
        else:
            self.FindItemById(const.ID_MODE_NAVIGATION).Enable(True)

    def OnAddMask(self, mask):
        self.num_masks += 1
        self.bool_op_menu.Enable(self.num_masks >= 2)
        self.mask_preview.Enable(True)
        self.mask_auto_reload.Enable(True)
        self.mask_preview_reload.Enable(True)

    def OnRemoveMasks(self, mask_indexes):
        self.num_masks -= len(mask_indexes)
        self.bool_op_menu.Enable(self.num_masks >= 2)

    def OnShowMask(self, index, value):
        self.clean_mask_menu.Enable(value)
        self.crop_mask_menu.Enable(value)
        self.mask_preview.Enable(value)
        self.mask_auto_reload.Enable(value)
        self.mask_preview_reload.Enable(value)


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
        sub = Publisher.subscribe
        sub(self._Layout, "ProgressBar Reposition")

    def _Layout(self):
        """
        Compute new size and position, according to parent resize
        """
        rect = self.Parent.GetFieldRect(2)
        self.SetPosition((rect.x + 2, rect.y + 2))
        self.SetSize((rect.width - 4, rect.height - 4))
        self.Show()

    def SetPercentage(self, value):
        """
        Set value [0;100] into gauge, moving "status" percentage.
        """
        self.SetValue(int(value))
        if value >= 99:
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
        self.SetStatusWidths([-2, -2, -1])
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
        sub = Publisher.subscribe
        sub(self._SetProgressValue, "Update status in GUI")
        sub(self._SetProgressLabel, "Update status text in GUI")

    def _SetProgressValue(self, value, label):
        """
        Set both percentage value in gauge and text progress label in
        status.
        """
        self.progress_bar.SetPercentage(value)
        self.SetStatusText(label, 0)
        if int(value) >= 99:
            self.SetStatusText("", 0)
        if sys.platform == "win32":
            # TODO: temporary fix necessary in the Windows XP 64 Bits
            # BUG in wxWidgets http://trac.wxwidgets.org/ticket/10896
            try:
                # wx.SafeYield()
                wx.Yield()
            except wx.PyAssertionError:
                utils.debug("wx._core.PyAssertionError")

    def _SetProgressLabel(self, label):
        """
        Set text progress label.
        """
        self.SetStatusText(label, 0)


# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------


class TaskBarIcon(wx_TaskBarIcon):
    """
    TaskBarIcon has different behaviours according to the platform:
        - win32:  Show icon on "Notification Area" (near clock)
        - darwin: Show icon on Dock
        - linux2: Show icon on "Notification Area" (near clock)
    """

    def __init__(self, parent=None):
        wx_TaskBarIcon.__init__(self)
        self.frame = parent

        icon = wx.Icon(os.path.join(inv_paths.ICON_DIR, "invesalius.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon, "InVesalius")
        self.imgidx = 1

        # bind some events
        self.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnTaskBarActivate)

    def OnTaskBarActivate(self, evt):
        pass


# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------


class ProjectToolBar(AuiToolBar):
    """
    Toolbar related to general invesalius.project operations, including: import, as project    open, save and saveas, among others.
    """

    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition, wx.DefaultSize, agwStyle=style)
        self.SetToolBitmapSize(wx.Size(32, 32))

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
        sub = Publisher.subscribe
        sub(self._EnableState, "Enable state project")

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        # Load bitmaps
        d = inv_paths.ICON_DIR

        path = d.joinpath("file_import_original.png")
        BMP_IMPORT = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = d.joinpath("file_open_original.png")
        BMP_OPEN = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = d.joinpath("file_save_original.png")
        BMP_SAVE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = d.joinpath("preferences.png")
        BMP_PREFERENCES = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = d.joinpath("print_original.png")
        BMP_PRINT = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = d.joinpath("tool_photo_original.png")
        BMP_PHOTO = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        # Create tool items based on bitmaps
        self.AddTool(
            const.ID_DICOM_IMPORT,
            "",
            BMP_IMPORT,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Import DICOM files...\tCtrl+I"),
        )
        # self.AddLabelTool(const.ID_DICOM_LOAD_NET,
        #                   "Load medical image...",
        #                   BMP_NET)
        self.AddTool(
            const.ID_PROJECT_OPEN,
            "",
            BMP_OPEN,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Open InVesalius project..."),
        )
        self.AddTool(
            const.ID_PROJECT_SAVE,
            "",
            BMP_SAVE,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Save InVesalius project"),
        )
        self.AddTool(
            const.ID_PREFERENCES_TOOLBAR,
            "",
            BMP_PREFERENCES,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Preferences"),
        )
        # self.AddLabelTool(const.ID_SAVE_SCREENSHOT,
        #                   "Take photo of screen",
        #                   BMP_PHOTO)
        # self.AddLabelTool(const.ID_PRINT_SCREENSHOT,
        #                   "Print medical image...",
        #                   BMP_PRINT)

    def _EnableState(self, state):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()
        self.Refresh()

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. save) when project is closed.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, False)
        self.Refresh()

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. save) when project is opened.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, True)
        self.Refresh()


# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------


class ObjectToolBar(AuiToolBar):
    """
    Toolbar related to general object operations, including: zoom
    move, rotate, brightness/contrast, etc.
    """

    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition, wx.DefaultSize, agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32, 32))

        self.parent = parent
        # Used to enable/disable menu items if project is opened or
        # not. Eg. save should only be available if a project is open
        self.enable_items = [
            const.STATE_WL,
            const.STATE_PAN,
            const.STATE_SPIN,
            const.STATE_ZOOM_SL,
            const.STATE_ZOOM,
            const.STATE_MEASURE_DISTANCE,
            const.STATE_MEASURE_ANGLE,
            const.STATE_MEASURE_DENSITY_ELLIPSE,
            const.STATE_MEASURE_DENSITY_POLYGON,
            # const.STATE_ANNOTATE
        ]
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.Realize()
        self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._UntoggleAllItems, "Untoggle object toolbar items")
        sub(self._ToggleLinearMeasure, "Set tool linear measure")
        sub(self._ToggleAngularMeasure, "Set tool angular measure")
        sub(self.ToggleItem, "Toggle toolbar item")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnToggle)

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = inv_paths.ICON_DIR

        path = os.path.join(d, "tool_rotate_original.png")
        BMP_ROTATE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "tool_translate_original.png")
        BMP_MOVE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "tool_zoom_original.png")
        BMP_ZOOM = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "tool_zoom_select_original.png")
        BMP_ZOOM_SELECT = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "tool_contrast_original.png")
        BMP_CONTRAST = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "measure_line_original.png")
        BMP_DISTANCE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "measure_angle_original.png")
        BMP_ANGLE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "measure_density_ellipse32px.png")
        BMP_ELLIPSE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "measure_density_polygon32px.png")
        BMP_POLYGON = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        # Create tool items based on bitmaps
        self.AddTool(
            const.STATE_ZOOM,
            "",
            BMP_ZOOM,
            wx.NullBitmap,
            short_help_string=_("Zoom"),
            kind=wx.ITEM_CHECK,
        )
        self.AddTool(
            const.STATE_ZOOM_SL,
            "",
            BMP_ZOOM_SELECT,
            wx.NullBitmap,
            short_help_string=_("Zoom based on selection"),
            kind=wx.ITEM_CHECK,
        )
        self.AddTool(
            const.STATE_SPIN,
            "",
            BMP_ROTATE,
            wx.NullBitmap,
            short_help_string=_("Rotate"),
            kind=wx.ITEM_CHECK,
        )
        self.AddTool(
            const.STATE_PAN,
            "",
            BMP_MOVE,
            wx.NullBitmap,
            short_help_string=_("Move"),
            kind=wx.ITEM_CHECK,
        )
        self.AddTool(
            const.STATE_WL,
            "",
            BMP_CONTRAST,
            wx.NullBitmap,
            short_help_string=_("Contrast"),
            kind=wx.ITEM_CHECK,
        )
        self.AddTool(
            const.STATE_MEASURE_DISTANCE,
            "",
            BMP_DISTANCE,
            wx.NullBitmap,
            short_help_string=_("Measure distance"),
            kind=wx.ITEM_CHECK,
        )
        self.AddTool(
            const.STATE_MEASURE_ANGLE,
            "",
            BMP_ANGLE,
            wx.NullBitmap,
            short_help_string=_("Measure angle"),
            kind=wx.ITEM_CHECK,
        )

        self.AddTool(
            const.STATE_MEASURE_DENSITY_ELLIPSE,
            "",
            BMP_ELLIPSE,
            wx.NullBitmap,
            short_help_string=_("Measure density ellipse"),
            kind=wx.ITEM_CHECK,
        )

        self.AddTool(
            const.STATE_MEASURE_DENSITY_POLYGON,
            "",
            BMP_POLYGON,
            wx.NullBitmap,
            short_help_string=_("Measure density polygon"),
            kind=wx.ITEM_CHECK,
        )
        # self.AddLabelTool(const.STATE_ANNOTATE,
        #                "",
        #                shortHelp = _("Add annotation"),
        #                bitmap = BMP_ANNOTATE,
        #                kind = wx.ITEM_CHECK)

    def _EnableState(self, state, registration_active):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        if state and not registration_active:  # checking if registration is NOT active
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()
        self.Refresh()

    def _UntoggleAllItems(self):
        """
        Untoggle all items on toolbar.
        """
        for id in const.TOOL_STATES:
            state = self.GetToolToggled(id)
            if state:
                self.ToggleTool(id, False)
        self.Refresh()

    def _ToggleLinearMeasure(self):
        """
        Force measure distance tool to be toggled and bind pubsub
        events to other classes whici are interested on this.
        """
        id = const.STATE_MEASURE_DISTANCE
        self.ToggleTool(id, True)
        Publisher.sendMessage("Enable style", style=id)
        Publisher.sendMessage("Untoggle slice toolbar items")
        for item in const.TOOL_STATES:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)

    def _ToggleAngularMeasure(self):
        """
        Force measure angle tool to be toggled and bind pubsub
        events to other classes which are interested on this.
        """
        id = const.STATE_MEASURE_ANGLE
        self.ToggleTool(id, True)
        Publisher.sendMessage("Enable style", style=id)
        Publisher.sendMessage("Untoggle slice toolbar items")
        for item in const.TOOL_STATES:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)

    def OnToggle(self, evt):
        """
        Update status of other items on toolbar (only one item
        should be toggle each time).
        """
        id = evt.GetId()
        state = self.GetToolToggled(id)
        if state and ((id == const.STATE_MEASURE_DISTANCE) or (id == const.STATE_MEASURE_ANGLE)):
            Publisher.sendMessage("Fold measure task")

        if state:
            Publisher.sendMessage("Enable style", style=id)
            Publisher.sendMessage("Untoggle slice toolbar items")
        else:
            Publisher.sendMessage("Disable style", style=id)

        for item in const.TOOL_STATES:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)
        evt.Skip()

    def ToggleItem(self, _id, value):
        if _id in self.enable_items:
            self.ToggleTool(_id, value)
            self.Refresh()

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


class SliceToolBar(AuiToolBar):
    """
    Toolbar related to 2D slice specific operations, including: cross
    intersection reference and scroll slices.
    """

    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition, wx.DefaultSize, agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32, 32))

        self.parent = parent
        self.enable_items = [
            const.SLICE_STATE_SCROLL,
            const.SLICE_STATE_CROSS,
        ]
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.Realize()
        self.SetStateProjectClose()

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = inv_paths.ICON_DIR

        path = os.path.join(d, "slice_original.png")
        BMP_SLICE = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        path = os.path.join(d, "cross_original.png")
        BMP_CROSS = wx.Bitmap(str(path), wx.BITMAP_TYPE_PNG)

        self.sst = self.AddToggleTool(
            const.SLICE_STATE_SCROLL,
            BMP_SLICE,  # , kind=wx.ITEM_CHECK)
            wx.NullBitmap,
            toggle=True,
            short_help_string=_("Scroll slices"),
        )

        self.sct = self.AddToggleTool(
            const.SLICE_STATE_CROSS,
            BMP_CROSS,  # , kind=wx.ITEM_CHECK)
            wx.NullBitmap,
            toggle=True,
            short_help_string=_("Slices' cross intersection"),
        )

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._UntoggleAllItems, "Untoggle slice toolbar items")
        sub(self.OnToggle, "Toggle toolbar button")
        sub(self.ToggleItem, "Toggle toolbar item")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnToggle)

    def _EnableState(self, state):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()
            self._UntoggleAllItems()
        self.Refresh()

    def _UntoggleAllItems(self):
        """
        Untoggle all items on toolbar.
        """
        for id in const.TOOL_SLICE_STATES:
            state = self.GetToolToggled(id)
            if state:
                self.ToggleTool(id, False)
                if id == const.SLICE_STATE_CROSS:
                    msg = "Disable style"
                    Publisher.sendMessage(msg, style=const.SLICE_STATE_CROSS)
        self.Refresh()

    def OnToggle(self, evt=None, id=None):
        """
        Update status of other items on toolbar (only one item
        should be toggle each time).
        """
        if id is not None:
            if not self.GetToolToggled(id):
                self.ToggleTool(id, True)
                self.Refresh()
        else:
            id = evt.GetId()
            evt.Skip()

        state = self.GetToolToggled(id)

        if state:
            Publisher.sendMessage("Enable style", style=id)
            Publisher.sendMessage("Untoggle object toolbar items")
        else:
            Publisher.sendMessage("Disable style", style=id)

        # const.STATE_REGISTRATION can be disabled with the same button as const.SLICE_STATE_CROSS
        if id == const.SLICE_STATE_CROSS and not state:
            Publisher.sendMessage("Stop image registration")

        for item in self.enable_items:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)
        # self.ToggleTool(const.SLICE_STATE_SCROLL, self.GetToolToggled(const.SLICE_STATE_CROSS))
        # self.Update()
        ##self.sst.SetToggle(self.sct.IsToggled())
        ##print ">>>", self.sst.IsToggled()
        # print ">>>", self.sst.GetState()

    def ToggleItem(self, _id, value):
        if _id in self.enable_items:
            self.ToggleTool(_id, value)
            self.Refresh()

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. cross) when project is closed.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, False)
        self.Refresh()

    def SetStateProjectOpen(self):
        """
        Enable menu items (e.g. cross) when project is opened.
        """
        for tool in self.enable_items:
            self.EnableTool(tool, True)
        self.Refresh()


class LayoutToolBar(AuiToolBar):
    """
    Toolbar related to general layout. Contains the following buttons:

    - show/hide task panel (= the left UI panel)
    - show/hide text (= the texts indicating the anterior, posterior, etc. directions)
    - show/hide rulers (= the rulers showing the scale on each viewer)
    """

    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition, wx.DefaultSize, agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32, 32))

        self.parent = parent
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.ontool_layout = False
        self.ontool_text = True
        self.ontool_ruler = True
        self.enable_items = [ID_TEXT]

        self.Realize()
        self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._SetLayoutWithTask, "Set layout button data only")
        sub(self._SetLayoutWithoutTask, "Set layout button full")
        sub(self._SendRulerVisibilityStatus, "Send ruler visibility status")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnToggle)

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = inv_paths.ICON_DIR

        # Bitmaps for show/hide task panel item
        p = os.path.join(d, "layout_data_only_original.png")
        self.BMP_WITH_MENU = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        p = os.path.join(d, "layout_full_original.png")
        self.BMP_WITHOUT_MENU = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        # Bitmaps for show/hide task item
        p = os.path.join(d, "text_inverted_original.png")
        self.BMP_WITHOUT_TEXT = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        p = os.path.join(d, "text_original.png")
        self.BMP_WITH_TEXT = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        # Bitmaps for showing/hiding the ruler.
        p = os.path.join(d, "ruler_original_disabled.png")
        self.BMP_WITHOUT_RULER = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        p = os.path.join(d, "ruler_original_enabled.png")
        self.BMP_WITH_RULER = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        self.AddTool(
            ID_LAYOUT,
            "",
            self.BMP_WITHOUT_MENU,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Hide task panel"),
        )
        self.AddTool(
            ID_TEXT,
            "",
            self.BMP_WITH_TEXT,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Hide text"),
        )
        self.AddTool(
            ID_RULER,
            "",
            self.BMP_WITH_RULER,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Hide ruler"),
        )

    def _EnableState(self, state):
        """
        Based on given state, enable or disable menu items which
        depend if project is open or not.
        """
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()
        self.Refresh()

    def _SendRulerVisibilityStatus(self):
        Publisher.sendMessage("Receive ruler visibility status", status=self.ontool_ruler)

    def _SetLayoutWithoutTask(self):
        """
        Set item bitmap to task panel hiden.
        """
        self.SetToolNormalBitmap(ID_LAYOUT, self.BMP_WITHOUT_MENU)

    def _SetLayoutWithTask(self):
        """
        Set item bitmap to task panel shown.
        """
        self.SetToolNormalBitmap(ID_LAYOUT, self.BMP_WITH_MENU)

    def OnToggle(self, event):
        """
        Update status of toolbar item (bitmap and help)
        """
        id = event.GetId()
        if id == ID_LAYOUT:
            self.ToggleLayout()
        elif id == ID_TEXT:
            self.ToggleText()
        elif id == ID_RULER:
            self.ToggleRulers()

        for item in VIEW_TOOLS:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)

    def SetStateProjectClose(self):
        """
        Disable menu items (e.g. text) when project is closed.
        """
        self.ontool_text = True
        self.ontool_ruler = True
        self.ToggleText()
        self.HideRulers()
        for tool in self.enable_items:
            self.EnableTool(tool, False)

    def SetStateProjectOpen(self):
        """
        Disable menu items (e.g. text) when project is closed.
        """
        self.ontool_text = False
        self.ontool_ruler = True
        self.ToggleText()
        self.HideRulers()
        for tool in self.enable_items:
            self.EnableTool(tool, True)

    def ToggleLayout(self):
        """
        Based on previous layout item state, toggle it.
        """
        if self.ontool_layout:
            self.SetToolNormalBitmap(ID_LAYOUT, self.BMP_WITHOUT_MENU)
            Publisher.sendMessage("Show task panel")
            self.SetToolShortHelp(ID_LAYOUT, _("Hide task panel"))
            self.ontool_layout = False
        else:
            self.bitmap = self.BMP_WITH_MENU
            self.SetToolNormalBitmap(ID_LAYOUT, self.BMP_WITH_MENU)
            Publisher.sendMessage("Hide task panel")
            self.SetToolShortHelp(ID_LAYOUT, _("Show task panel"))
            self.ontool_layout = True

    def ToggleText(self):
        """
        Based on previous text item state, toggle it.
        """
        if self.ontool_text:
            self.SetToolNormalBitmap(ID_TEXT, self.BMP_WITH_TEXT)
            Publisher.sendMessage("Hide text actors on viewers")
            self.SetToolShortHelp(ID_TEXT, _("Show text"))
            Publisher.sendMessage("Update AUI")
            self.ontool_text = False
        else:
            self.SetToolNormalBitmap(ID_TEXT, self.BMP_WITHOUT_TEXT)
            Publisher.sendMessage("Show text actors on viewers")
            self.SetToolShortHelp(ID_TEXT, _("Hide text"))
            Publisher.sendMessage("Update AUI")
            self.ontool_text = True

    def ShowRulers(self):
        """
        Show the rulers on the viewers.
        """
        self.SetToolNormalBitmap(ID_RULER, self.BMP_WITH_RULER)
        Publisher.sendMessage("Show rulers on viewers")
        self.SetToolShortHelp(ID_RULER, _("Hide rulers"))
        Publisher.sendMessage("Update AUI")
        self.ontool_ruler = True

    def HideRulers(self):
        """
        Hide the rulers on the viewers.
        """
        self.SetToolNormalBitmap(ID_RULER, self.BMP_WITHOUT_RULER)
        Publisher.sendMessage("Hide rulers on viewers")
        self.SetToolShortHelp(ID_RULER, _("Show rulers"))
        Publisher.sendMessage("Update AUI")
        self.ontool_ruler = False

    def ToggleRulers(self):
        """
        Based on the current ruler state, either show or hide the rulers.
        """
        if self.ontool_ruler:
            self.HideRulers()
        else:
            self.ShowRulers()


class HistoryToolBar(AuiToolBar):
    """
    Toolbar related to project history. Contains undo and redo buttons.
    """

    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition, wx.DefaultSize, agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32, 32))

        self.parent = parent
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.Realize()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        sub(self.OnEnableUndo, "Enable undo")
        sub(self.OnEnableRedo, "Enable redo")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_TOOL, self.OnUndo, id=wx.ID_UNDO)
        self.Bind(wx.EVT_TOOL, self.OnRedo, id=wx.ID_REDO)

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = inv_paths.ICON_DIR

        # Bitmaps for undo/redo buttons
        p = os.path.join(d, "undo_original.png")
        self.BMP_UNDO = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        p = os.path.join(d, "redo_original.png")
        self.BMP_REDO = wx.Bitmap(str(p), wx.BITMAP_TYPE_PNG)

        self.AddTool(
            wx.ID_UNDO,
            "",
            self.BMP_UNDO,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Undo"),
        )

        self.AddTool(
            wx.ID_REDO,
            "",
            self.BMP_REDO,
            wx.NullBitmap,
            wx.ITEM_NORMAL,
            short_help_string=_("Redo"),
        )

        self.EnableTool(wx.ID_UNDO, False)
        self.EnableTool(wx.ID_REDO, False)

    def OnUndo(self, event):
        Publisher.sendMessage("Undo edition")

    def OnRedo(self, event):
        Publisher.sendMessage("Redo edition")

    def OnEnableUndo(self, value):
        if value:
            self.EnableTool(wx.ID_UNDO, True)
        else:
            self.EnableTool(wx.ID_UNDO, False)
        self.Refresh()

    def OnEnableRedo(self, value):
        if value:
            self.EnableTool(wx.ID_REDO, True)
        else:
            self.EnableTool(wx.ID_REDO, False)
        self.Refresh()
