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
import platform
import sys
import webbrowser

import wx

try:
    from wx.adv import TaskBarIcon as wx_TaskBarIcon
except ImportError:
    from wx import TaskBarIcon as wx_TaskBarIcon

import wx.aui
from wx.lib.pubsub import pub as Publisher
import wx.lib.agw.toasterbox as TB
import wx.lib.popupctl as pc

from wx.lib.agw.aui.auibar import AuiToolBar, AUI_TB_PLAIN_BACKGROUND

import invesalius.constants as const
import invesalius.gui.default_tasks as tasks
import invesalius.gui.default_viewers as viewers
import invesalius.gui.dialogs as dlg
import invesalius.gui.import_panel as imp
import invesalius.gui.import_bitmap_panel as imp_bmp
import invesalius.gui.import_network_panel as imp_net
import invesalius.project as prj
import invesalius.session as ses
import invesalius.utils as utils
import invesalius.gui.preferences as preferences
# Layout tools' IDs - this is used only locally, therefore doesn't
# need to be defined in constants.py
VIEW_TOOLS = [ID_LAYOUT, ID_TEXT] =\
                                [wx.NewId() for number in range(2)]



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
        wx.Frame.__init__(self, id=-1, name='', parent=prnt,
              pos=wx.Point(0, 0),
              size=wx.Size(1024, 748), #size = wx.DisplaySize(),
              style=wx.DEFAULT_FRAME_STYLE, title='InVesalius 3')
        self.Center(wx.BOTH)
        icon_path = os.path.join(const.ICON_DIR, "invesalius.ico")
        self.SetIcon(wx.Icon(icon_path, wx.BITMAP_TYPE_ICO))

        self.mw = None


        if sys.platform != 'darwin':
            self.Maximize()

        self.sizeChanged = True
        #Necessary update AUI (statusBar in special)
        #when maximized in the Win 7 and XP
        self.SetSize(self.GetSize())
        #self.SetSize(wx.Size(1024, 748))

        self._show_navigator_message = True

        #to control check and unckeck of menu view -> interpolated_slices
        main_menu = MenuBar(self)

        self.actived_interpolated_slices = main_menu.view_menu
        self.actived_navigation_mode = main_menu.mode_menu

        # Set menus, status and task bar
        self.SetMenuBar(main_menu)
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
        sub = Publisher.subscribe
        sub(self._BeginBusyCursor, 'Begin busy cursor')
        sub(self._ShowContentPanel, 'Cancel DICOM load')
        sub(self._EndBusyCursor, 'End busy cursor')
        sub(self._HideContentPanel, 'Hide content panel')
        sub(self._HideImportPanel, 'Hide import panel')
        sub(self._HideTask, 'Hide task panel')
        sub(self._SetProjectName, 'Set project name')
        sub(self._ShowContentPanel, 'Show content panel')
        sub(self._ShowImportPanel, 'Show import panel in frame')
        #sub(self._ShowHelpMessage, 'Show help message')
        sub(self._ShowImportNetwork, 'Show retrieve dicom panel')
        sub(self._ShowImportBitmap, 'Show import bitmap panel in frame')
        sub(self._ShowTask, 'Show task panel')
        sub(self._UpdateAUI, 'Update AUI')
        sub(self._Exit, 'Exit')

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_IDLE, self.OnIdle)
        self.Bind(wx.EVT_MENU, self.OnMenuClick)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        #self.Bind(wx.EVT_MOVE, self.OnMove)

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

        # This is the DICOM import panel. When the two panels above as dicom        # are shown, this should be hiden
        caption = _("Preview medical data to be reconstructed")
        aui_manager.AddPane(imp.Panel(self), wx.aui.AuiPaneInfo().
                          Name("Import").CloseButton(False).Centre().Hide().
                          MaximizeButton(False).Floatable(True).
                          Caption(caption).CaptionVisible(True))

        caption = _("Preview bitmap to be reconstructed")
        aui_manager.AddPane(imp_bmp.Panel(self), wx.aui.AuiPaneInfo().
                          Name("ImportBMP").CloseButton(False).Centre().Hide().
                          MaximizeButton(False).Floatable(True).
                          Caption(caption).CaptionVisible(True))

        ncaption = _("Retrieve DICOM from PACS")
        aui_manager.AddPane(imp_net.Panel(self), wx.aui.AuiPaneInfo().
                          Name("Retrieve").Centre().Hide().
                          MaximizeButton(True).Floatable(True).
                          Caption(ncaption).CaptionVisible(True))

        # Add toolbars to manager
        # This is pretty tricky -- order on win32 is inverted when
        # compared to linux2 & darwin
        if sys.platform == 'win32':
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

        aui_manager.AddPane(t5, wx.aui.AuiPaneInfo().
                          Name("History Toolbar").
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
        if hasattr(sys,"frozen") and sys.platform == 'darwin':
            sys.exit(0)

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
        Publisher.sendMessage("Set layout button full")
        aui_manager = self.aui_manager
        aui_manager.GetPane("Import").Show(0)
        
        aui_manager.GetPane("ImportBMP").Show(0)

        aui_manager.GetPane("Data").Show(1)
        aui_manager.GetPane("Tasks").Show(1)
        aui_manager.Update()

    def _ShowImportNetwork(self, evt_pubsub):
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

    def _ShowImportBitmap(self, evt_pubsub):
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

    def _ShowHelpMessage(self, evt_pubsub):
        aui_manager = self.aui_manager
        pos = aui_manager.GetPane("Data").window.GetScreenPosition()
        msg =  evt_pubsub.data
        self.mw = MessageWatershed(self, msg)
        self.mw.SetPosition(pos)
        self.mw.Show()

    def _ShowImportPanel(self, evt_pubsub):
        """
        Show only DICOM import panel. as dicom        """
        Publisher.sendMessage("Set layout button data only")
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
        Publisher.sendMessage('Close Project')

    def OnClose(self, evt):
        """
        Close all project data.
        """
        Publisher.sendMessage('Close Project')
        Publisher.sendMessage('Disconnect tracker')
        s = ses.Session()
        if not s.IsOpen() or not s.project_path:
            Publisher.sendMessage('Exit')
        self.aui_manager.UnInit()

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
        elif id == const.ID_DICOM_NETWORK:
            self.ShowRetrieveDicomPanel()
        elif id in (const.ID_FLIP_X, const.ID_FLIP_Y, const.ID_FLIP_Z):
            axis = {const.ID_FLIP_X: 2,
                    const.ID_FLIP_Y: 1,
                    const.ID_FLIP_Z: 0}[id]
            self.FlipVolume(axis)
        elif id in (const.ID_SWAP_XY, const.ID_SWAP_XZ, const.ID_SWAP_YZ):
            axes = {const.ID_SWAP_XY: (2, 1),
                    const.ID_SWAP_XZ: (2, 0),
                    const.ID_SWAP_YZ: (1, 0)}[id]
            self.SwapAxes(axes)
        elif id == wx.ID_UNDO:
            self.OnUndo()
        elif id == wx.ID_REDO:
            self.OnRedo()

        elif id == const.ID_BOOLEAN_MASK:
            self.OnMaskBoolean()
        elif id == const.ID_CLEAN_MASK:
            self.OnCleanMask()

        elif id == const.ID_REORIENT_IMG:
            self.OnReorientImg()

        elif id == const.ID_MASK_DENSITY_MEASURE:
            ddlg = dlg.MaskDensityDialog(self)
            ddlg.Show()

        elif id == const.ID_THRESHOLD_SEGMENTATION:
            Publisher.sendMessage("Show panel", const.ID_THRESHOLD_SEGMENTATION)
            Publisher.sendMessage('Disable actual style')
            Publisher.sendMessage('Enable style', const.STATE_DEFAULT)

        elif id == const.ID_MANUAL_SEGMENTATION:
            Publisher.sendMessage("Show panel", const.ID_MANUAL_SEGMENTATION)
            Publisher.sendMessage('Disable actual style')
            Publisher.sendMessage('Enable style', const.SLICE_STATE_EDITOR)

        elif id == const.ID_WATERSHED_SEGMENTATION:
            Publisher.sendMessage("Show panel", const.ID_WATERSHED_SEGMENTATION)
            Publisher.sendMessage('Disable actual style')
            Publisher.sendMessage('Enable style', const.SLICE_STATE_WATERSHED)

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

        elif id == const.ID_VIEW_INTERPOLATED:
            st = self.actived_interpolated_slices.IsChecked(const.ID_VIEW_INTERPOLATED)
            if st:
                self.OnInterpolatedSlices(True)
            else:
                self.OnInterpolatedSlices(False)

        elif id == const.ID_MODE_NAVIGATION:
            st = self.actived_navigation_mode.IsChecked(const.ID_MODE_NAVIGATION)
            self.OnNavigationMode(st)

        elif id == const.ID_CROP_MASK:
            self.OnCropMask()

        elif id == const.ID_CREATE_SURFACE:
            Publisher.sendMessage('Open create surface dialog')

        elif id == const.ID_CREATE_MASK:
            Publisher.sendMessage('New mask from shortcut')

    def OnInterpolatedSlices(self, status):
        Publisher.sendMessage('Set interpolated slices', status)

    def OnNavigationMode(self, status):
        if status and self._show_navigator_message and sys.platform != 'win32':
            wx.MessageBox(_('Currently the Navigation mode is only working on Windows'), 'Info', wx.OK | wx.ICON_INFORMATION)
            self._show_navigator_message = False
        Publisher.sendMessage('Set navigation mode', status)
        if not status:
            Publisher.sendMessage('Remove sensors ID')

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
        Publisher.sendMessage(('ProgressBar Reposition'))
        self.sizeChanged = False


    def OnMove(self, evt):
        aui_manager = self.aui_manager
        pos = aui_manager.GetPane("Data").window.GetScreenPosition()
        self.mw.SetPosition(pos)

    def ShowPreferences(self):

        self.preferences.Center()
        
        if self.preferences.ShowModal() == wx.ID_OK:
            values = self.preferences.GetPreferences()
            self.preferences.Close()

            ses.Session().rendering = values[const.RENDERING]
            ses.Session().surface_interpolation = values[const.SURFACE_INTERPOLATION]
            ses.Session().language = values[const.LANGUAGE]
            ses.Session().slice_interpolation = values[const.SLICE_INTERPOLATION]
            ses.Session().WriteSessionFile()

            Publisher.sendMessage('Remove Volume')
            Publisher.sendMessage('Reset Reaycasting')
            Publisher.sendMessage('Update Slice Interpolation')
            Publisher.sendMessage('Update Slice Interpolation MenuBar')
            Publisher.sendMessage('Update Navigation Mode MenuBar')
            Publisher.sendMessage('Update Surface Interpolation')

    def ShowAbout(self):
        """
        Shows about dialog.
        """
        dlg.ShowAboutDialog(self)

    def SaveProject(self):
        """
        Save project.
        """
        Publisher.sendMessage('Show save dialog', False)

    def ShowGettingStarted(self):
        """
        Show getting started window.
        """
        if ses.Session().language == 'pt_BR':
            user_guide = "user_guide_pt_BR.pdf"
        else:
            user_guide = "user_guide_en.pdf"

        path = os.path.join(const.DOC_DIR,
                            user_guide)
        if sys.platform == 'darwin':
            path = r'file://' + path
        webbrowser.open(path)

    def ShowImportDicomPanel(self):
        """
        Show import DICOM panel. as dicom        """
        Publisher.sendMessage('Show import directory dialog')

    def ShowImportOtherFiles(self, id_file):
        """
        Show import Analyze, NiFTI1 or PAR/REC dialog.
        """
        Publisher.sendMessage('Show import other files dialog', id_file)

    def ShowRetrieveDicomPanel(self):
        Publisher.sendMessage('Show retrieve dicom panel')

    def ShowOpenProject(self):
        """
        Show open project dialog.
        """
        Publisher.sendMessage('Show open project dialog')

    def ShowSaveAsProject(self):
        """
        Show save as dialog.
        """
        Publisher.sendMessage('Show save dialog', True)

    def ShowBitmapImporter(self):
        """
        Tiff, BMP, JPEG and PNG
        """
        Publisher.sendMessage('Show bitmap dialog', True)

    def FlipVolume(self, axis):
        Publisher.sendMessage('Flip volume', axis)
        Publisher.sendMessage('Reload actual slice')

    def SwapAxes(self, axes):
        Publisher.sendMessage('Swap volume axes', axes)
        Publisher.sendMessage('Update scroll')
        Publisher.sendMessage('Reload actual slice')

    def OnUndo(self):
        Publisher.sendMessage('Undo edition')

    def OnRedo(self):
        Publisher.sendMessage('Redo edition')

    def OnMaskBoolean(self):
        Publisher.sendMessage('Show boolean dialog')

    def OnCleanMask(self):
        Publisher.sendMessage('Clean current mask')
        Publisher.sendMessage('Reload actual slice')

    def OnReorientImg(self):
        Publisher.sendMessage('Enable style', const.SLICE_STATE_REORIENT)
        rdlg = dlg.ReorientImageDialog()
        rdlg.Show()

    def OnFillHolesManually(self):
        Publisher.sendMessage('Enable style', const.SLICE_STATE_MASK_FFILL)

    def OnFillHolesAutomatically(self):
        fdlg = dlg.FillHolesAutoDialog(_(u"Fill holes automatically"))
        fdlg.Show()

    def OnRemoveMaskParts(self):
        Publisher.sendMessage('Enable style', const.SLICE_STATE_REMOVE_MASK_PARTS)

    def OnSelectMaskParts(self):
        Publisher.sendMessage('Enable style', const.SLICE_STATE_SELECT_MASK_PARTS)

    def OnFFillSegmentation(self):
        Publisher.sendMessage('Enable style', const.SLICE_STATE_FFILL_SEGMENTATION)

    def OnInterpolatedSlices(self, status):
        Publisher.sendMessage('Set interpolated slices', status)
    
    def OnCropMask(self):
        Publisher.sendMessage('Enable style', const.SLICE_STATE_CROP_MASK)

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
                             const.ID_MASK_DENSITY_MEASURE,
                             const.ID_CREATE_SURFACE,
                             const.ID_CREATE_MASK]
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
        sub(self.OnEnableNavigation, "Navigation status")

        sub(self.OnAddMask, "Add mask")
        sub(self.OnRemoveMasks, "Remove masks")
        sub(self.OnShowMask, "Show mask")
        sub(self.OnUpdateSliceInterpolation, "Update Slice Interpolation MenuBar")
        sub(self.OnUpdateNavigationMode, "Update Navigation Mode MenuBar")

        self.num_masks = 0

    def __init_items(self):
        """
        Create all menu and submenus, and add them to self.
        """
        # TODO: This definetely needs improvements... ;)

        #Import Others Files
        others_file_menu = wx.Menu()
        others_file_menu.Append(const.ID_ANALYZE_IMPORT, _("Analyze 7.5"))
        others_file_menu.Append(const.ID_NIFTI_IMPORT, _("NIfTI 1"))
        others_file_menu.Append(const.ID_PARREC_IMPORT, _("PAR/REC"))
        others_file_menu.Append(const.ID_TIFF_JPG_PNG, u"TIFF,BMP,JPG or PNG (\xb5CT)")

        # FILE
        file_menu = wx.Menu()
        app = file_menu.Append
        app(const.ID_DICOM_IMPORT, _("Import DICOM...\tCtrl+I"))
        #app(const.ID_DICOM_NETWORK, _("Retrieve DICOM from PACS"))
        file_menu.AppendMenu(const.ID_IMPORT_OTHERS_FILES, _("Import other files..."), others_file_menu)
        app(const.ID_PROJECT_OPEN, _("Open project...\tCtrl+O"))
        app(const.ID_PROJECT_SAVE, _("Save project\tCtrl+S"))
        app(const.ID_PROJECT_SAVE_AS, _("Save project as...\tCtrl+Shift+S"))
        app(const.ID_PROJECT_CLOSE, _("Close project"))
        file_menu.AppendSeparator()
        #app(const.ID_PROJECT_INFO, _("Project Information..."))
        #file_menu.AppendSeparator()
        #app(const.ID_SAVE_SCREENSHOT, _("Save Screenshot"))
        #app(const.ID_PRINT_SCREENSHOT, _("Print Screenshot"))
        #file_menu.AppendSeparator()
        #app(1, "C:\InvData\sample.inv")
        #file_menu.AppendSeparator()
        app(const.ID_EXIT, _("Exit\tCtrl+Q"))

        file_edit = wx.Menu()
        d = const.ICON_DIR
        if not(sys.platform == 'darwin'):
            # Bitmaps for show/hide task panel item
            p = os.path.join(d, "undo_menu.png")
            self.BMP_UNDO = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

            p = os.path.join(d, "redo_menu.png")
            self.BMP_REDO = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

            file_edit_item_undo = wx.MenuItem(file_edit, wx.ID_UNDO,  _("Undo\tCtrl+Z"))
            file_edit_item_undo.SetBitmap(self.BMP_UNDO)
            file_edit.AppendItem(file_edit_item_undo)
            file_edit_item_undo.Enable(False)

            file_edit_item_redo = wx.MenuItem(file_edit, wx.ID_REDO,  _("Redo\tCtrl+Y"))
            file_edit_item_redo.SetBitmap(self.BMP_REDO)
            file_edit.AppendItem(file_edit_item_redo)
            file_edit_item_redo.Enable(False)
        else:
            file_edit.Append(wx.ID_UNDO, _("Undo\tCtrl+Z")).Enable(False)
            file_edit.Append(wx.ID_REDO, _("Redo\tCtrl+Y")).Enable(False)
        #app(const.ID_EDIT_LIST, "Show Undo List...")
        #################################################################

        # Tool menu
        tools_menu = wx.Menu()

        # Mask Menu
        mask_menu = wx.Menu()

        self.new_mask_menu = mask_menu.Append(const.ID_CREATE_MASK, _(u"New\tCtrl+Shift+M"))
        self.new_mask_menu.Enable(False)

        self.bool_op_menu = mask_menu.Append(const.ID_BOOLEAN_MASK, _(u"Boolean operations\tCtrl+Shift+B"))
        self.bool_op_menu.Enable(False)

        self.clean_mask_menu = mask_menu.Append(const.ID_CLEAN_MASK, _(u"Clean Mask\tCtrl+Shift+A"))
        self.clean_mask_menu.Enable(False)

        mask_menu.AppendSeparator()

        self.fill_hole_mask_menu = mask_menu.Append(const.ID_FLOODFILL_MASK, _(u"Fill holes manually\tCtrl+Shift+H"))
        self.fill_hole_mask_menu.Enable(False)

        self.fill_hole_auto_menu = mask_menu.Append(const.ID_FILL_HOLE_AUTO, _(u"Fill holes automatically\tCtrl+Shift+J"))
        self.fill_hole_mask_menu.Enable(False)

        mask_menu.AppendSeparator()

        self.remove_mask_part_menu = mask_menu.Append(const.ID_REMOVE_MASK_PART, _(u"Remove parts\tCtrl+Shift+K"))
        self.remove_mask_part_menu.Enable(False)

        self.select_mask_part_menu = mask_menu.Append(const.ID_SELECT_MASK_PART, _(u"Select parts\tCtrl+Shift+L"))
        self.select_mask_part_menu.Enable(False)

        mask_menu.AppendSeparator()

        self.crop_mask_menu = mask_menu.Append(const.ID_CROP_MASK, _("Crop"))
        self.crop_mask_menu.Enable(False)

        # Segmentation Menu
        segmentation_menu = wx.Menu()
        self.threshold_segmentation = segmentation_menu.Append(const.ID_THRESHOLD_SEGMENTATION, _(u"Threshold\tCtrl+Shift+T"))
        self.manual_segmentation = segmentation_menu.Append(const.ID_MANUAL_SEGMENTATION, _(u"Manual segmentation\tCtrl+Shift+E"))
        self.watershed_segmentation = segmentation_menu.Append(const.ID_WATERSHED_SEGMENTATION, _(u"Watershed\tCtrl+Shift+W"))
        self.ffill_segmentation = segmentation_menu.Append(const.ID_FLOODFILL_SEGMENTATION, _(u"Region growing\tCtrl+Shift+G"))
        self.ffill_segmentation.Enable(False)

        # Surface Menu
        surface_menu = wx.Menu()
        self.create_surface = surface_menu.Append(const.ID_CREATE_SURFACE, (u"New\tCtrl+Shift+C"))
        self.create_surface.Enable(False)

        # Image menu
        image_menu = wx.Menu()

        # Flip
        flip_menu = wx.Menu()
        flip_menu.Append(const.ID_FLIP_X, _("Right - Left")).Enable(False)
        flip_menu.Append(const.ID_FLIP_Y, _("Anterior - Posterior")).Enable(False)
        flip_menu.Append(const.ID_FLIP_Z, _("Top - Bottom")).Enable(False)

        swap_axes_menu = wx.Menu()
        swap_axes_menu.Append(const.ID_SWAP_XY, _("From Right-Left to Anterior-Posterior")).Enable(False)
        swap_axes_menu.Append(const.ID_SWAP_XZ, _("From Right-Left to Top-Bottom")).Enable(False)
        swap_axes_menu.Append(const.ID_SWAP_YZ, _("From Anterior-Posterior to Top-Bottom")).Enable(False)

        image_menu.AppendMenu(wx.NewId(), _('Flip'), flip_menu)
        image_menu.AppendMenu(wx.NewId(), _('Swap axes'), swap_axes_menu)

        mask_density_menu = image_menu.Append(const.ID_MASK_DENSITY_MEASURE, _(u'Mask Density measure'))
        reorient_menu = image_menu.Append(const.ID_REORIENT_IMG, _(u'Reorient image\tCtrl+Shift+R'))

        reorient_menu.Enable(False)
        tools_menu.AppendMenu(-1, _(u'Image'), image_menu)
        tools_menu.AppendMenu(-1,  _(u"Mask"), mask_menu)
        tools_menu.AppendMenu(-1, _(u"Segmentation"), segmentation_menu)
        tools_menu.AppendMenu(-1, _(u"Surface"), surface_menu)

        #View
        self.view_menu = view_menu = wx.Menu()
        view_menu.Append(const.ID_VIEW_INTERPOLATED, _(u'Interpolated slices'), "", wx.ITEM_CHECK)


        v = self.SliceInterpolationStatus()
        self.view_menu.Check(const.ID_VIEW_INTERPOLATED, v)

        self.actived_interpolated_slices = self.view_menu

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

        #Mode
        self.mode_menu = mode_menu = wx.Menu()
        mode_menu.Append(const.ID_MODE_NAVIGATION, _(u'Navigation mode'), "", wx.ITEM_CHECK)

        v = self.NavigationModeStatus()
        self.mode_menu.Check(const.ID_MODE_NAVIGATION, v)

        self.actived_navigation_mode = self.mode_menu

        # HELP
        help_menu = wx.Menu()
        help_menu.Append(const.ID_START, _("Getting started..."))
        #help_menu.Append(108, "User Manual...")
        help_menu.AppendSeparator()
        help_menu.Append(const.ID_ABOUT, _("About..."))
        #help_menu.Append(107, "Check For Updates Now...")

        #if platform.system() == 'Darwin':
           #wx.App.SetMacAboutMenuItemId(const.ID_ABOUT)
           #wx.App.SetMacExitMenuItemId(const.ID_EXIT)

        # Add all menus to menubar
        self.Append(file_menu, _("File"))
        self.Append(file_edit, _("Edit"))
        self.Append(view_menu, _(u"View"))
        self.Append(tools_menu, _(u"Tools"))
        #self.Append(tools_menu, "Tools")
        self.Append(options_menu, _("Options"))
        self.Append(mode_menu, _("Mode"))
        self.Append(help_menu, _("Help"))


    def SliceInterpolationStatus(self):
        
        status = int(ses.Session().slice_interpolation)
        
        if status == 0:
            v = True
        else:
            v = False

        return v

    def NavigationModeStatus(self):
        status = int(ses.Session().mode)

        if status == 1:
            return True
        else:
            return False

    def OnUpdateSliceInterpolation(self, pubsub_evt):
        v = self.SliceInterpolationStatus()
        self.view_menu.Check(const.ID_VIEW_INTERPOLATED, v)

    def OnUpdateNavigationMode(self, pubsub_evt):
        v = self.NavigationModeStatus()
        self.mode_menu.Check(const.ID_MODE_NAVIGATION, v)

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

    def OnEnableUndo(self, pubsub_evt):
        value = pubsub_evt.data
        if value:
            self.FindItemById(wx.ID_UNDO).Enable(True)
        else:
            self.FindItemById(wx.ID_UNDO).Enable(False)

    def OnEnableRedo(self, pubsub_evt):
        value = pubsub_evt.data
        if value:
            self.FindItemById(wx.ID_REDO).Enable(True)
        else:
            self.FindItemById(wx.ID_REDO).Enable(False)

    def OnEnableNavigation(self, pubsub_evt):
        """
        Disable mode menu when navigation is on.
        :param pubsub_evt: Navigation status
        """
        value = pubsub_evt.data
        if value:
            self.FindItemById(const.ID_MODE_NAVIGATION).Enable(False)
        else:
            self.FindItemById(const.ID_MODE_NAVIGATION).Enable(True)

    def OnAddMask(self, pubsub_evt):
        self.num_masks += 1
        self.bool_op_menu.Enable(self.num_masks >= 2)

    def OnRemoveMasks(self, pubsub_evt):
        self.num_masks -= len(pubsub_evt.data)
        self.bool_op_menu.Enable(self.num_masks >= 2)

    def OnShowMask(self, pubsub_evt):
        index, value = pubsub_evt.data
        self.clean_mask_menu.Enable(value)
        self.crop_mask_menu.Enable(value)


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
        sub(self._Layout, 'ProgressBar Reposition')

    def _Layout(self, evt_pubsub=None):
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
        sub = Publisher.subscribe
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

class ProjectToolBar(AuiToolBar):
    """
    Toolbar related to general invesalius.project operations, including: import, as project    open, save and saveas, among others.
    """
    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            agwStyle=style)
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
        sub = Publisher.subscribe
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
        self.AddTool(const.ID_DICOM_IMPORT,
                          "",
                          BMP_IMPORT,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string =_("Import DICOM files...\tCtrl+I"))
        #self.AddLabelTool(const.ID_DICOM_LOAD_NET,
        #                   "Load medical image...",
        #                   BMP_NET)
        self.AddTool(const.ID_PROJECT_OPEN,
                          "",
                          BMP_OPEN,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string =_("Open InVesalius project..."))
        self.AddTool(const.ID_PROJECT_SAVE,
                          "",
                          BMP_SAVE,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string = _("Save InVesalius project"))
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
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize, agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        # Used to enable/disable menu items if project is opened or
        # not. Eg. save should only be available if a project is open
        self.enable_items = [const.STATE_WL, const.STATE_PAN,
                             const.STATE_SPIN, const.STATE_ZOOM_SL,
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
        sub(self._UntoggleAllItems, 'Untoggle object toolbar items')
        sub(self._ToggleLinearMeasure, "Set tool linear measure")
        sub(self._ToggleAngularMeasure, "Set tool angular measure")
        sub(self.ToggleItem, 'Toggle toolbar item')

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

            BMP_ELLIPSE = wx.ArtProvider.GetBitmap(wx.ART_HELP, wx.ART_TOOLBAR, (48, 48))

            BMP_POLYGON = wx.ArtProvider.GetBitmap(wx.ART_GO_DOWN, wx.ART_TOOLBAR, (48, 48))

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

            BMP_ELLIPSE = wx.ArtProvider.GetBitmap(wx.ART_HELP, wx.ART_TOOLBAR, (32, 32))

            BMP_POLYGON = wx.ArtProvider.GetBitmap(wx.ART_GO_DOWN, wx.ART_TOOLBAR, (32, 32))

            #path = os.path.join(d, "tool_annotation.png")
            #BMP_ANNOTATE = wx.Bitmap(path, wx.BITMAP_TYPE_PNG)

        # Create tool items based on bitmaps
        self.AddTool(const.STATE_ZOOM,
                          "",
                          BMP_ZOOM,
                          wx.NullBitmap,
                          short_help_string =_("Zoom"),
                          kind = wx.ITEM_CHECK)
        self.AddTool(const.STATE_ZOOM_SL,
                          "",
                          BMP_ZOOM_SELECT,
                          wx.NullBitmap,
                          short_help_string = _("Zoom based on selection"),
                          kind = wx.ITEM_CHECK)
        self.AddTool(const.STATE_SPIN,
                          "",
                          BMP_ROTATE,
                          wx.NullBitmap,
                          short_help_string = _("Rotate"),
                          kind = wx.ITEM_CHECK)
        self.AddTool(const.STATE_PAN,
                          "",
                          BMP_MOVE,
                          wx.NullBitmap,
                          short_help_string = _("Move"),
                          kind = wx.ITEM_CHECK)
        self.AddTool(const.STATE_WL,
                          "",
                          BMP_CONTRAST,
                          wx.NullBitmap,
                          short_help_string = _("Constrast"),
                          kind = wx.ITEM_CHECK)
        self.AddTool(const.STATE_MEASURE_DISTANCE,
                        "",
                        BMP_DISTANCE,
                        wx.NullBitmap,
                        short_help_string = _("Measure distance"),
                        kind = wx.ITEM_CHECK)
        self.AddTool(const.STATE_MEASURE_ANGLE,
                        "",
                        BMP_ANGLE,
                        wx.NullBitmap,
                        short_help_string = _("Measure angle"),
                        kind = wx.ITEM_CHECK)

        self.AddTool(const.STATE_MEASURE_DENSITY_ELLIPSE,
                        "",
                        BMP_ELLIPSE,
                        wx.NullBitmap,
                        short_help_string = _("Measure density ellipse"),
                        kind = wx.ITEM_CHECK)

        self.AddTool(const.STATE_MEASURE_DENSITY_POLYGON,
                        "",
                        BMP_POLYGON,
                        wx.NullBitmap,
                        short_help_string = _("Measure density polygon"),
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
        self.Refresh()

    def _UntoggleAllItems(self, pubsub_evt=None):
        """
        Untoggle all items on toolbar.
        """
        for id in const.TOOL_STATES:
            state = self.GetToolToggled(id)
            if state:
                self.ToggleTool(id, False)
        self.Refresh()

    def _ToggleLinearMeasure(self, pubsub_evt):
        """
        Force measure distance tool to be toggled and bind pubsub
        events to other classes whici are interested on this.
        """
        id = const.STATE_MEASURE_DISTANCE
        self.ToggleTool(id, True)
        Publisher.sendMessage('Enable style', id)
        Publisher.sendMessage('Untoggle slice toolbar items')
        for item in const.TOOL_STATES:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)


    def _ToggleAngularMeasure(self, pubsub_evt):
        """
        Force measure angle tool to be toggled and bind pubsub
        events to other classes which are interested on this.
        """
        id = const.STATE_MEASURE_ANGLE
        self.ToggleTool(id, True)
        Publisher.sendMessage('Enable style', id)
        Publisher.sendMessage('Untoggle slice toolbar items')
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
        if state and ((id == const.STATE_MEASURE_DISTANCE) or\
                (id == const.STATE_MEASURE_ANGLE)):
            Publisher.sendMessage('Fold measure task')

        if state:
            Publisher.sendMessage('Enable style', id)
            Publisher.sendMessage('Untoggle slice toolbar items')
        else:
            Publisher.sendMessage('Disable style', id)

        for item in const.TOOL_STATES:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)
        evt.Skip()

    def ToggleItem(self, evt):
        _id, value = evt.data
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
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        self.enable_items = [const.SLICE_STATE_SCROLL,
                             const.SLICE_STATE_CROSS,]
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

        self.sst = self.AddToggleTool(const.SLICE_STATE_SCROLL,
                          BMP_SLICE,#, kind=wx.ITEM_CHECK)
                          wx.NullBitmap,
                          toggle=True,
                          short_help_string=_("Scroll slices"))

        self.sct = self.AddToggleTool(const.SLICE_STATE_CROSS,
                          BMP_CROSS,#, kind=wx.ITEM_CHECK)
                          wx.NullBitmap,
                          toggle=True,
                          short_help_string=_("Slices' cross intersection"))

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        sub(self._EnableState, "Enable state project")
        sub(self._UntoggleAllItems, 'Untoggle slice toolbar items')
        sub(self.OnToggle, 'Toggle Cross')
        sub(self.ToggleItem, 'Toggle toolbar item')

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
        self.Refresh()

    def _UntoggleAllItems(self, pubsub_evt=None):
        """
        Untoggle all items on toolbar.
        """
        for id in const.TOOL_SLICE_STATES:
            state = self.GetToolToggled(id)
            if state:
                self.ToggleTool(id, False)
                if id == const.SLICE_STATE_CROSS:
                    msg = 'Set cross visibility'
                    Publisher.sendMessage(msg, 0)
        self.Refresh()

    def OnToggle(self, evt):
        """
        Update status of other items on toolbar (only one item
        should be toggle each time).
        """
        if hasattr(evt, 'data'):
            id = evt.data
            if not self.GetToolToggled(id):
                self.ToggleTool(id, True)
                self.Refresh()
        else:
            id = evt.GetId()
            evt.Skip()

        state = self.GetToolToggled(id)

        if state:
            Publisher.sendMessage('Enable style', id)
            Publisher.sendMessage('Untoggle object toolbar items')
        else:
            Publisher.sendMessage('Disable style', id)

        for item in self.enable_items:
            state = self.GetToolToggled(item)
            if state and (item != id):
                self.ToggleTool(item, False)
        #self.ToggleTool(const.SLICE_STATE_SCROLL, self.GetToolToggled(const.SLICE_STATE_CROSS))
        #self.Update()
        ##self.sst.SetToggle(self.sct.IsToggled())
        ##print ">>>", self.sst.IsToggled()
        #print ">>>", self.sst.GetState()

    def ToggleItem(self, evt):
        _id, value = evt.data
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

# ------------------------------------------------------------------
# ------------------------------------------------------------------
# ------------------------------------------------------------------

class LayoutToolBar(AuiToolBar):
    """
    Toolbar related to general layout/ visualization configuration
    e.g: show/hide task panel and show/hide text on viewers.
    """
    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            agwStyle=style)

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
        sub = Publisher.subscribe
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

        self.AddTool(ID_LAYOUT,
                          "",
                          self.BMP_WITHOUT_MENU,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string= _("Hide task panel"))
        self.AddTool(ID_TEXT,
                          "",
                          self.BMP_WITH_TEXT,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string= _("Hide text"))

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
        self.Refresh()

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
            state = self.GetToolToggled(item)
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
            Publisher.sendMessage('Show task panel')
            self.SetToolShortHelp(ID_LAYOUT,_("Hide task panel"))
            self.ontool_layout = False
        else:
            self.bitmap = self.BMP_WITH_MENU
            self.SetToolNormalBitmap(ID_LAYOUT,self.BMP_WITH_MENU)
            Publisher.sendMessage('Hide task panel')
            self.SetToolShortHelp(ID_LAYOUT, _("Show task panel"))
            self.ontool_layout = True

    def ToggleText(self):
        """
        Based on previous text item state, toggle it.
        """
        if self.ontool_text:
            self.SetToolNormalBitmap(ID_TEXT,self.BMP_WITH_TEXT)
            Publisher.sendMessage('Hide text actors on viewers')
            self.SetToolShortHelp(ID_TEXT,_("Show text"))
            Publisher.sendMessage('Update AUI')
            self.ontool_text = False
        else:
            self.SetToolNormalBitmap(ID_TEXT, self.BMP_WITHOUT_TEXT)
            Publisher.sendMessage('Show text actors on viewers')
            self.SetToolShortHelp(ID_TEXT,_("Hide text"))
            Publisher.sendMessage('Update AUI')
            self.ontool_text = True


class HistoryToolBar(AuiToolBar):
    """
    Toolbar related to general layout/ visualization configuration
    e.g: show/hide task panel and show/hide text on viewers.
    """
    def __init__(self, parent):
        style = AUI_TB_PLAIN_BACKGROUND
        AuiToolBar.__init__(self, parent, -1, wx.DefaultPosition,
                            wx.DefaultSize,
                            agwStyle=style)

        self.SetToolBitmapSize(wx.Size(32,32))

        self.parent = parent
        self.__init_items()
        self.__bind_events()
        self.__bind_events_wx()

        self.ontool_layout = False
        self.ontool_text = True
        #self.enable_items = [ID_TEXT]

        self.Realize()
        #self.SetStateProjectClose()

    def __bind_events(self):
        """
        Bind events related to pubsub.
        """
        sub = Publisher.subscribe
        #sub(self._EnableState, "Enable state project")
        #sub(self._SetLayoutWithTask, "Set layout button data only")
        #sub(self._SetLayoutWithoutTask, "Set layout button full")
        sub(self.OnEnableUndo, "Enable undo")
        sub(self.OnEnableRedo, "Enable redo")

    def __bind_events_wx(self):
        """
        Bind normal events from wx (except pubsub related).
        """
        #self.Bind(wx.EVT_TOOL, self.OnToggle)
        wx.EVT_TOOL( self, wx.ID_UNDO, self.OnUndo )
        wx.EVT_TOOL( self, wx.ID_REDO, self.OnRedo )

    def __init_items(self):
        """
        Add tools into toolbar.
        """
        d = const.ICON_DIR
        if sys.platform == 'darwin':
            # Bitmaps for show/hide task panel item
            p = os.path.join(d, "undo_original.png")
            self.BMP_UNDO = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

            p = os.path.join(d, "redo_original.png")
            self.BMP_REDO = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

        else:
            # Bitmaps for show/hide task panel item
            p = os.path.join(d, "undo_small.png")
            self.BMP_UNDO = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

            p = os.path.join(d, "redo_small.png")
            self.BMP_REDO = wx.Bitmap(p, wx.BITMAP_TYPE_PNG)

        self.AddTool(wx.ID_UNDO,
                          "",
                          self.BMP_UNDO,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string= _("Undo"))

        self.AddTool(wx.ID_REDO,
                          "",
                          self.BMP_REDO,
                          wx.NullBitmap,
                          wx.ITEM_NORMAL,
                          short_help_string=_("Redo"))

        self.EnableTool(wx.ID_UNDO, False)
        self.EnableTool(wx.ID_REDO, False)

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
        self.Refresh()

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

    def OnUndo(self, event):
        Publisher.sendMessage('Undo edition')

    def OnRedo(self, event):
        Publisher.sendMessage('Redo edition')

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
            state = self.GetToolToggled(item)
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
            Publisher.sendMessage('Show task panel')
            self.SetToolShortHelp(ID_LAYOUT,_("Hide task panel"))
            self.ontool_layout = False
        else:
            self.bitmap = self.BMP_WITH_MENU
            self.SetToolNormalBitmap(ID_LAYOUT,self.BMP_WITH_MENU)
            Publisher.sendMessage('Hide task panel')
            self.SetToolShortHelp(ID_LAYOUT, _("Show task panel"))
            self.ontool_layout = True

    def ToggleText(self):
        """
        Based on previous text item state, toggle it.
        """
        if self.ontool_text:
            self.SetToolNormalBitmap(ID_TEXT,self.BMP_WITH_TEXT)
            Publisher.sendMessage('Hide text actors on viewers')
            self.SetToolShortHelp(ID_TEXT,_("Show text"))
            Publisher.sendMessage('Update AUI')
            self.ontool_text = False
        else:
            self.SetToolNormalBitmap(ID_TEXT, self.BMP_WITHOUT_TEXT)
            Publisher.sendMessage('Show text actors on viewers')
            self.SetToolShortHelp(ID_TEXT,_("Hide text"))
            Publisher.sendMessage('Update AUI')
            self.ontool_text = True

    def OnEnableUndo(self, pubsub_evt):
        value = pubsub_evt.data
        if value:
            self.EnableTool(wx.ID_UNDO, True)
        else:
            self.EnableTool(wx.ID_UNDO, False)
        self.Refresh()

    def OnEnableRedo(self, pubsub_evt):
        value = pubsub_evt.data
        if value:
            self.EnableTool(wx.ID_REDO, True)
        else:
            self.EnableTool(wx.ID_REDO, False)
        self.Refresh()
