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

import dataclasses
from functools import partial
import itertools
import time

import nibabel as nb
import numpy as np
try:
    import Trekker
    has_trekker = True
except ImportError:
    has_trekker = False

try:
    import invesalius.data.elfin as elfin
    import invesalius.data.elfin_processing as elfin_process
    has_robot = True
except ImportError:
    has_robot = False

import wx

try:
    import wx.lib.agw.foldpanelbar as fpb
except ImportError:
    import wx.lib.foldpanelbar as fpb

import wx.lib.colourselect as csel
import wx.lib.masked.numctrl
from invesalius.pubsub import pub as Publisher

import invesalius.constants as const

if has_trekker:
    import invesalius.data.brainmesh_handler as brain

import invesalius.data.imagedata_utils as imagedata_utils
import invesalius.data.slice_ as sl
import invesalius.data.tractography as dti
import invesalius.data.record_coords as rec
import invesalius.data.vtk_utils as vtk_utils
import invesalius.data.bases as db
import invesalius.data.coregistration as dcr
import invesalius.gui.dialogs as dlg
import invesalius.project as prj
import invesalius.session as ses

from invesalius import utils
from invesalius.gui import utils as gui_utils
from invesalius.navigation.icp import ICP
from invesalius.navigation.navigation import Navigation
from invesalius.navigation.tracker import Tracker
from invesalius.data.converters import to_vtk

from invesalius.net.neuronavigation_api import NeuronavigationApi

HAS_PEDAL_CONNECTION = True
try:
    from invesalius.net.pedal_connection import PedalConnection
except ImportError:
    HAS_PEDAL_CONNECTION = False

BTN_NEW = wx.NewId()
BTN_IMPORT_LOCAL = wx.NewId()


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND|wx.GROW|wx.BOTTOM|wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = self.GetBackgroundColour()
        background_colour = wx.Colour(255,255,255)
        self.SetBackgroundColour(background_colour)

        txt_nav = wx.StaticText(self, -1, _('Select fiducials and navigate'),
                                size=wx.Size(90, 20))
        txt_nav.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))

        # Create horizontal sizer to represent lines in the panel
        txt_sizer = wx.BoxSizer(wx.HORIZONTAL)
        txt_sizer.Add(txt_nav, 1, wx.EXPAND|wx.GROW, 5)

        # Fold panel which contains navigation configurations
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)

        # Add line sizer into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(txt_sizer, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.AddSpacer(5)
        main_sizer.Fit(self)

        self.SetSizerAndFit(main_sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = main_sizer


class FoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerFoldPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 0, wx.EXPAND|wx.GROW)
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

        self.__bind_events()
        # Fold panel and its style settings
        # FIXME: If we dont insert a value in size or if we set wx.DefaultSize,
        # the fold_panel doesnt show. This means that, for some reason, Sizer
        # is not working properly in this panel. It might be on some child or
        # parent panel. Perhaps we need to insert the item into the sizer also...
        # Study this.

        fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                      (10, 330), 0, fpb.FPB_SINGLE_FOLD)

        # Initialize Navigation, Tracker and PedalConnection objects here so that they are available to several panels.
        #
        tracker = Tracker()
        pedal_connection = PedalConnection() if HAS_PEDAL_CONNECTION else None
        icp = ICP()
        neuronavigation_api = NeuronavigationApi()
        navigation = Navigation(
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )
        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Navigation panel
        item = fold_panel.AddFoldPanel(_("Neuronavigation"), collapsed=True)
        ntw = NeuronavigationPanel(
            parent=item,
            navigation=navigation,
            tracker=tracker,
            icp=icp,
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, spacing=0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        # Fold 2 - Object registration panel
        item = fold_panel.AddFoldPanel(_("Object registration"), collapsed=True)
        otw = ObjectRegistrationPanel(
            parent=item,
            tracker=tracker,
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, otw, spacing=0,
                                      leftSpacing=0, rightSpacing=0)

        # Fold 3 - Markers panel
        item = fold_panel.AddFoldPanel(_("Markers"), collapsed=True)
        mtw = MarkersPanel(item, navigation, tracker, icp)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, mtw, spacing= 0,
                                      leftSpacing=0, rightSpacing=0)

        # Fold 4 - Tractography panel
        if has_trekker:
            item = fold_panel.AddFoldPanel(_("Tractography"), collapsed=True)
            otw = TractographyPanel(item)

            fold_panel.ApplyCaptionStyle(item, style)
            fold_panel.AddFoldPanelWindow(item, otw, spacing=0,
                                          leftSpacing=0, rightSpacing=0)

        # Fold 5 - DBS
        self.dbs_item = fold_panel.AddFoldPanel(_("Deep Brain Stimulation"), collapsed=True)
        dtw = DbsPanel(self.dbs_item) #Atribuir nova var, criar panel

        fold_panel.ApplyCaptionStyle(self.dbs_item, style)
        fold_panel.AddFoldPanelWindow(self.dbs_item, dtw, spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        self.dbs_item.Hide()

        # Fold 6 - Sessions
        item = fold_panel.AddFoldPanel(_("Sessions"), collapsed=False)
        stw = SessionPanel(item)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, stw, spacing= 0,
                                      leftSpacing=0, rightSpacing=0)

        # Check box for camera update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Update camera in volume"))
        checkcamera = wx.CheckBox(self, -1, _('Vol. camera'))
        checkcamera.SetToolTip(tooltip)
        checkcamera.SetValue(const.CAM_MODE)
        checkcamera.Bind(wx.EVT_CHECKBOX, self.OnVolumeCamera)
        self.checkcamera = checkcamera

        # Check box to use serial port to trigger pulse signal and create markers
        tooltip = wx.ToolTip(_("Enable serial port communication to trigger pulse and create markers"))
        checkbox_serial_port = wx.CheckBox(self, -1, _('Serial port'))
        checkbox_serial_port.SetToolTip(tooltip)
        checkbox_serial_port.SetValue(False)
        checkbox_serial_port.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableSerialPort, ctrl=checkbox_serial_port))
        self.checkbox_serial_port = checkbox_serial_port

        # Check box for object position and orientation update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Show and track TMS coil"))
        checkobj = wx.CheckBox(self, -1, _('Show coil'))
        checkobj.SetToolTip(tooltip)
        checkobj.SetValue(False)
        checkobj.Disable()
        checkobj.Bind(wx.EVT_CHECKBOX, self.OnShowObject)
        self.checkobj = checkobj

        #  if sys.platform != 'win32':
        self.checkcamera.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        checkbox_serial_port.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        checkobj.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(checkcamera, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Add(checkbox_serial_port, 0, wx.ALIGN_CENTER)
        line_sizer.Add(checkobj, 0, wx.RIGHT | wx.LEFT, 5)
        line_sizer.Fit(self)

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 0, wx.GROW|wx.EXPAND)
        sizer.Add(line_sizer, 1, wx.GROW | wx.EXPAND)
        sizer.Fit(self)

        self.track_obj = False

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
    def __bind_events(self):
        Publisher.subscribe(self.OnCheckStatus, 'Navigation status')
        Publisher.subscribe(self.OnShowObject, 'Update track object state')
        Publisher.subscribe(self.OnVolumeCamera, 'Change camera checkbox')
        Publisher.subscribe(self.OnEnableVolumeCameraCheckBox, 'Enable volume camera checkbox')
        Publisher.subscribe(self.OnShowDbs, "Active dbs folder")
        Publisher.subscribe(self.OnHideDbs, "Deactive dbs folder")

    def OnShowDbs(self):
        self.dbs_item.Show()

    def OnHideDbs(self):
        self.dbs_item.Hide()

    def OnCheckStatus(self, nav_status, vis_status):
        if nav_status:
            self.checkbox_serial_port.Enable(False)
            self.checkobj.Enable(False)
        else:
            self.checkbox_serial_port.Enable(True)
            if self.track_obj:
                self.checkobj.Enable(True)

    def OnEnableSerialPort(self, evt, ctrl):
        if ctrl.GetValue():
            from wx import ID_OK
            dlg_port = dlg.SetCOMPort(select_baud_rate=False)

            if dlg_port.ShowModal() != ID_OK:
                ctrl.SetValue(False)
                return

            com_port = dlg_port.GetCOMPort()
            baud_rate = 115200

            Publisher.sendMessage('Update serial port', serial_port_in_use=True, com_port=com_port, baud_rate=baud_rate)
        else:
            Publisher.sendMessage('Update serial port', serial_port_in_use=False)

    def OnShowObject(self, evt=None, flag=None, obj_name=None, polydata=None, use_default_object=True):
        if not evt:
            if flag:
                self.checkobj.Enable(True)
                self.checkobj.SetValue(True)
                self.track_obj = True
                Publisher.sendMessage('Status target button', status=True)
            else:
                self.checkobj.Enable(False)
                self.checkobj.SetValue(False)
                self.track_obj = False
                Publisher.sendMessage('Status target button', status=False)

        Publisher.sendMessage('Update show object state', state=self.checkobj.GetValue())

    def OnVolumeCamera(self, evt=None, status=None):
        if not evt:
            self.checkcamera.SetValue(status)
        Publisher.sendMessage('Update volume camera state', camera_state=self.checkcamera.GetValue())

    def OnEnableVolumeCameraCheckBox(self, status=None):
        self.checkcamera.Enable(status)

class NeuronavigationPanel(wx.Panel):
    def __init__(self, parent, navigation, tracker, icp, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.__bind_events()

        # Initialize global variables
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        self.navigation = navigation
        self.icp = icp
        self.tracker = tracker

        self.nav_status = False
        self.tracker_fiducial_being_set = None
        self.current_coord = 0, 0, 0, None, None, None

        # Initialize list of buttons and numctrls for wx objects
        self.btns_set_fiducial = [None, None, None, None, None, None]
        self.numctrls_fiducial = [[], [], [], [], [], []]

        # ComboBox for spatial tracker device selection
        tracker_options = [_("Select tracker:")] + self.tracker.get_trackers()
        select_tracker_elem = wx.ComboBox(self, -1, "", size=(145, -1),
                                          choices=tracker_options, style=wx.CB_DROPDOWN|wx.CB_READONLY)

        tooltip = wx.ToolTip(_("Choose the tracking device"))
        select_tracker_elem.SetToolTip(tooltip)

        select_tracker_elem.SetSelection(const.DEFAULT_TRACKER)
        select_tracker_elem.Bind(wx.EVT_COMBOBOX, partial(self.OnChooseTracker, ctrl=select_tracker_elem))
        self.select_tracker_elem = select_tracker_elem

        # ComboBox for tracker reference mode
        tooltip = wx.ToolTip(_("Choose the navigation reference mode"))
        choice_ref = wx.ComboBox(self, -1, "",
                                 choices=const.REF_MODE, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_ref.SetSelection(const.DEFAULT_REF_MODE)
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(wx.EVT_COMBOBOX, partial(self.OnChooseReferenceMode, ctrl=select_tracker_elem))
        self.choice_ref = choice_ref

        # Toggle buttons for image fiducials
        for n, fiducial in enumerate(const.IMAGE_FIDUCIALS):
            button_id = fiducial['button_id']
            label = fiducial['label']
            tip = fiducial['tip']

            ctrl = wx.ToggleButton(self, button_id, label=label)
            ctrl.SetMinSize((gui_utils.calc_width_needed(ctrl, 3), -1))
            ctrl.SetToolTip(wx.ToolTip(tip))
            ctrl.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnImageFiducials, n))

            self.btns_set_fiducial[n] = ctrl

        # Push buttons for tracker fiducials
        for n, fiducial in enumerate(const.TRACKER_FIDUCIALS):
            button_id = fiducial['button_id']
            label = fiducial['label']
            tip = fiducial['tip']

            ctrl = wx.ToggleButton(self, button_id, label=label)
            ctrl.SetMinSize((gui_utils.calc_width_needed(ctrl, 3), -1))
            ctrl.SetToolTip(wx.ToolTip(tip))
            ctrl.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnTrackerFiducials, n, ctrl=ctrl))

            self.btns_set_fiducial[n + 3] = ctrl

        # TODO: Find a better alignment between FRE, text and navigate button

        # Fiducial registration error text and checkbox
        txt_fre = wx.StaticText(self, -1, _('FRE:'))
        tooltip = wx.ToolTip(_("Fiducial registration error"))
        txtctrl_fre = wx.TextCtrl(self, value="", size=wx.Size(60, -1), style=wx.TE_CENTRE)
        txtctrl_fre.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        txtctrl_fre.SetBackgroundColour('WHITE')
        txtctrl_fre.SetEditable(0)
        txtctrl_fre.SetToolTip(tooltip)
        self.txtctrl_fre = txtctrl_fre

        # Toggle button for neuronavigation
        tooltip = wx.ToolTip(_("Start navigation"))
        btn_nav = wx.ToggleButton(self, -1, _("Navigate"), size=wx.Size(80, -1))
        btn_nav.SetToolTip(tooltip)
        btn_nav.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnNavigate, btn_nav=btn_nav))

        # "Refine" text and checkbox
        txt_icp = wx.StaticText(self, -1, _('Refine:'))
        tooltip = wx.ToolTip(_(u"Refine the coregistration"))
        checkbox_icp = wx.CheckBox(self, -1, _(' '))
        checkbox_icp.SetValue(False)
        checkbox_icp.Enable(False)
        checkbox_icp.Bind(wx.EVT_CHECKBOX, partial(self.OnCheckboxICP, ctrl=checkbox_icp))
        checkbox_icp.SetToolTip(tooltip)
        self.checkbox_icp = checkbox_icp

        # "Pedal pressed" text and an indicator (checkbox) for pedal press
        if pedal_connection is not None and pedal_connection.in_use:
            txt_pedal_pressed = wx.StaticText(self, -1, _('Pedal pressed:'))
            tooltip = wx.ToolTip(_(u"Is the pedal pressed"))
            checkbox_pedal_pressed = wx.CheckBox(self, -1, _(' '))
            checkbox_pedal_pressed.SetValue(False)
            checkbox_pedal_pressed.Enable(False)
            checkbox_pedal_pressed.SetToolTip(tooltip)

            pedal_connection.add_callback(name='gui', callback=checkbox_pedal_pressed.SetValue)

            self.checkbox_pedal_pressed = checkbox_pedal_pressed
        else:
            txt_pedal_pressed = None
            self.checkbox_pedal_pressed = None

        # "Lock to target" text and checkbox
        tooltip = wx.ToolTip(_(u"Allow triggering stimulation pulse only if the coil is at the target"))
        lock_to_target_text = wx.StaticText(self, -1, _('Lock to target:'))
        lock_to_target_checkbox = wx.CheckBox(self, -1, _(' '))
        lock_to_target_checkbox.SetValue(False)
        lock_to_target_checkbox.Enable(False)
        lock_to_target_checkbox.Bind(wx.EVT_CHECKBOX, partial(self.OnLockToTargetCheckbox, ctrl=lock_to_target_checkbox))
        lock_to_target_checkbox.SetToolTip(tooltip)

        self.lock_to_target_checkbox = lock_to_target_checkbox

        # Image and tracker coordinates number controls
        for m in range(len(self.btns_set_fiducial)):
            for n in range(3):
                self.numctrls_fiducial[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1))

        # Sizers to group all GUI objects
        choice_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        choice_sizer.AddMany([(select_tracker_elem, wx.LEFT),
                              (choice_ref, wx.RIGHT)])

        coord_sizer = wx.GridBagSizer(hgap=5, vgap=5)

        for m in range(len(self.btns_set_fiducial)):
            coord_sizer.Add(self.btns_set_fiducial[m], pos=wx.GBPosition(m, 0))
            for n in range(3):
                coord_sizer.Add(self.numctrls_fiducial[m][n], pos=wx.GBPosition(m, n+1))
                if m in range(1, 6):
                    self.numctrls_fiducial[m][n].SetEditable(False)

        nav_sizer = wx.FlexGridSizer(rows=1, cols=5, hgap=5, vgap=5)
        nav_sizer.AddMany([(txt_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (txtctrl_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (btn_nav, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (txt_icp, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (checkbox_icp, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)])

        checkboxes_sizer = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        checkboxes_sizer.AddMany([(lock_to_target_text, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                                  (lock_to_target_checkbox, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)])

        if pedal_connection is not None and pedal_connection.in_use:
            checkboxes_sizer.AddMany([(txt_pedal_pressed, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                                      (checkbox_pedal_pressed, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)])

        group_sizer = wx.FlexGridSizer(rows=10, cols=1, hgap=5, vgap=5)
        group_sizer.AddGrowableCol(0, 1)
        group_sizer.AddGrowableRow(0, 1)
        group_sizer.AddGrowableRow(1, 1)
        group_sizer.AddGrowableRow(2, 1)
        group_sizer.SetFlexibleDirection(wx.BOTH)
        group_sizer.AddMany([(choice_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                             (coord_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                             (nav_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                             (checkboxes_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)])

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(group_sizer, 1)# wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

    def __bind_events(self):
        Publisher.subscribe(self.LoadImageFiducials, 'Load image fiducials')
        Publisher.subscribe(self.SetImageFiducial, 'Set image fiducial')
        Publisher.subscribe(self.SetTrackerFiducial, 'Set tracker fiducial')
        Publisher.subscribe(self.UpdateTrackObjectState, 'Update track object state')
        Publisher.subscribe(self.UpdateImageCoordinates, 'Set cross focal point')
        Publisher.subscribe(self.OnDisconnectTracker, 'Disconnect tracker')
        Publisher.subscribe(self.UpdateObjectRegistration, 'Update object registration')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.UpdateTrekkerObject, 'Update Trekker object')
        Publisher.subscribe(self.UpdateNumTracts, 'Update number of tracts')
        Publisher.subscribe(self.UpdateSeedOffset, 'Update seed offset')
        Publisher.subscribe(self.UpdateSeedRadius, 'Update seed radius')
        Publisher.subscribe(self.UpdateSleep, 'Update sleep')
        Publisher.subscribe(self.UpdateNumberThreads, 'Update number of threads')
        Publisher.subscribe(self.UpdateTractsVisualization, 'Update tracts visualization')
        Publisher.subscribe(self.UpdatePeelVisualization, 'Update peel visualization')
        Publisher.subscribe(self.EnableACT, 'Enable ACT')
        Publisher.subscribe(self.UpdateACTData, 'Update ACT data')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateTarget, 'Update target')
        Publisher.subscribe(self.OnStartNavigation, 'Start navigation')
        Publisher.subscribe(self.OnStopNavigation, 'Stop navigation')
        Publisher.subscribe(self.OnDialogRobotDestroy, 'Dialog robot destroy')

    def LoadImageFiducials(self, label, coord):
        fiducial = self.GetFiducialByAttribute(const.IMAGE_FIDUCIALS, 'label', label)

        fiducial_index = fiducial['fiducial_index']
        fiducial_name = fiducial['fiducial_name']

        if self.btns_set_fiducial[fiducial_index].GetValue():
            print("Fiducial {} already set, not resetting".format(label))
            return

        Publisher.sendMessage('Set image fiducial', fiducial_name=fiducial_name, coord=coord[0:3])

        self.btns_set_fiducial[fiducial_index].SetValue(True)
        for m in [0, 1, 2]:
            self.numctrls_fiducial[fiducial_index][m].SetValue(coord[m])

    def GetFiducialByAttribute(self, fiducials, attribute_name, attribute_value):
        found = [fiducial for fiducial in fiducials if fiducial[attribute_name] == attribute_value]

        assert len(found) != 0, "No fiducial found for which {} = {}".format(attribute_name, attribute_value)
        return found[0]

    def SetImageFiducial(self, fiducial_name, coord):
        fiducial = self.GetFiducialByAttribute(const.IMAGE_FIDUCIALS, 'fiducial_name', fiducial_name)
        fiducial_index = fiducial['fiducial_index']

        self.navigation.SetImageFiducial(fiducial_index, coord)

    def SetTrackerFiducial(self, fiducial_name):
        if not self.tracker.IsTrackerInitialized():
            dlg.ShowNavigationTrackerWarning(0, 'choose')
            return

        fiducial = self.GetFiducialByAttribute(const.TRACKER_FIDUCIALS, 'fiducial_name', fiducial_name)
        fiducial_index = fiducial['fiducial_index']

        # XXX: The reference mode is fetched from navigation object, however it seems like not quite
        #      navigation-related attribute here, as the reference mode used during the fiducial registration
        #      is more concerned with the calibration than the navigation.
        #
        ref_mode_id = self.navigation.GetReferenceMode()
        self.tracker.SetTrackerFiducial(ref_mode_id, fiducial_index)

        self.ResetICP()
        self.tracker.UpdateUI(self.select_tracker_elem, self.numctrls_fiducial[3:6], self.txtctrl_fre)

    def UpdatePeelVisualization(self, data):
        self.navigation.peel_loaded = data

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        if nav_status and self.icp.m_icp is not None:
            self.checkbox_icp.Enable(True)
        else:
            self.checkbox_icp.Enable(False)

    def UpdateTrekkerObject(self, data):
        # self.trk_inp = data
        self.navigation.trekker = data

    def UpdateNumTracts(self, data):
        self.navigation.n_tracts = data

    def UpdateSeedOffset(self, data):
        self.navigation.seed_offset = data

    def UpdateSeedRadius(self, data):
        self.navigation.seed_radius = data

    def UpdateSleep(self, data):
        self.navigation.UpdateSleep(data)

    def UpdateNumberThreads(self, data):
        self.navigation.n_threads = data

    def UpdateTractsVisualization(self, data):
        self.navigation.view_tracts = data

    def UpdateACTData(self, data):
        self.navigation.act_data = data

    def UpdateTarget(self, coord):
        self.navigation.target = coord

        self.lock_to_target_checkbox.Enable(True)
        self.lock_to_target_checkbox.SetValue(True)
        self.navigation.SetLockToTarget(True)

    def EnableACT(self, data):
        self.navigation.enable_act = data

    def UpdateImageCoordinates(self, position):
        # TODO: Change from world coordinates to matrix coordinates. They are better for multi software communication.
        self.current_coord = position

        for m in [0, 1, 2]:
            if not self.btns_set_fiducial[m].GetValue():
                for n in [0, 1, 2]:
                    self.numctrls_fiducial[m][n].SetValue(float(position[n]))

    def UpdateObjectRegistration(self, data=None):
        self.navigation.obj_reg = data

    def UpdateTrackObjectState(self, evt=None, flag=None, obj_name=None, polydata=None, use_default_object=True):
        self.navigation.track_obj = flag

    def ResetICP(self):
        self.icp.ResetICP()
        self.checkbox_icp.Enable(False)
        self.checkbox_icp.SetValue(False)

    def OnDisconnectTracker(self):
        self.tracker.DisconnectTracker()
        self.ResetICP()
        self.tracker.UpdateUI(self.select_tracker_elem, self.numctrls_fiducial[3:6], self.txtctrl_fre)

    def OnLockToTargetCheckbox(self, evt, ctrl):
        value = ctrl.GetValue()
        self.navigation.SetLockToTarget(value)

    def OnChooseTracker(self, evt, ctrl):
        Publisher.sendMessage('Update status text in GUI',
                              label=_("Configuring tracker ..."))
        if hasattr(evt, 'GetSelection'):
            choice = evt.GetSelection()
        else:
            choice = None

        self.tracker.SetTracker(choice)
        if self.tracker.tracker_id == const.ROBOT:
            self.dlg_correg_robot = dlg.CreateTransformationMatrixRobot(self.tracker)
            if self.dlg_correg_robot.ShowModal() == wx.ID_OK:
                Publisher.sendMessage('Robot navigation mode', robot_mode=True)
            else:
                Publisher.sendMessage('Disconnect tracker')
                wx.MessageBox(_("Not possible to connect to the robot."), _("InVesalius 3"))

        self.ResetICP()
        self.tracker.UpdateUI(ctrl, self.numctrls_fiducial[3:6], self.txtctrl_fre)

        Publisher.sendMessage('Update status text in GUI', label=_("Ready"))

    def OnChooseReferenceMode(self, evt, ctrl):
        self.navigation.SetReferenceMode(evt.GetSelection())

        # When ref mode is changed the tracker coordinates are set to zero
        self.tracker.ResetTrackerFiducials()

        # Some trackers do not accept restarting within this time window
        # TODO: Improve the restarting of trackers after changing reference mode

        self.ResetICP()

        print("Reference mode changed!")

    def OnImageFiducials(self, n, evt):
        fiducial_name = const.IMAGE_FIDUCIALS[n]['fiducial_name']

        # XXX: This is still a bit hard to read, could be cleaned up.
        label = list(const.BTNS_IMG_MARKERS[evt.GetId()].values())[0]

        if self.btns_set_fiducial[n].GetValue():
            coord = self.numctrls_fiducial[n][0].GetValue(),\
                    self.numctrls_fiducial[n][1].GetValue(),\
                    self.numctrls_fiducial[n][2].GetValue(), None, None, None

            Publisher.sendMessage('Set image fiducial', fiducial_name=fiducial_name, coord=coord[0:3])

            colour = (0., 1., 0.)
            size = 2
            seed = 3 * [0.]

            Publisher.sendMessage('Create marker', coord=coord, colour=colour, size=size,
                                   label=label, seed=seed)
        else:
            for m in [0, 1, 2]:
                self.numctrls_fiducial[n][m].SetValue(float(self.current_coord[m]))

            Publisher.sendMessage('Set image fiducial', fiducial_name=fiducial_name, coord=np.nan)
            Publisher.sendMessage('Delete fiducial marker', label=label)

    def OnTrackerFiducials(self, n, evt, ctrl):

        # Do not allow several tracker fiducials to be set at the same time.
        if self.tracker_fiducial_being_set is not None and self.tracker_fiducial_being_set != n:
            ctrl.SetValue(False)
            return

        # Called when the button for setting the tracker fiducial is enabled and either pedal is pressed
        # or the button is pressed again.
        #
        def set_fiducial_callback(state):
            if state:
                fiducial_name = const.TRACKER_FIDUCIALS[n]['fiducial_name']
                Publisher.sendMessage('Set tracker fiducial', fiducial_name=fiducial_name)

                ctrl.SetValue(False)
                self.tracker_fiducial_being_set = None

        if ctrl.GetValue():
            self.tracker_fiducial_being_set = n

            if self.pedal_connection is not None:
                self.pedal_connection.add_callback(
                    name='fiducial',
                    callback=set_fiducial_callback,
                    remove_when_released=True,
                )
        else:
            set_fiducial_callback(True)

            if self.pedal_connection is not None:
                self.pedal_connection.remove_callback(name='fiducial')

    def OnStopNavigation(self):
        select_tracker_elem = self.select_tracker_elem
        choice_ref = self.choice_ref

        self.navigation.StopNavigation()
        if self.tracker.tracker_id == const.ROBOT:
            Publisher.sendMessage('Update robot target', robot_tracker_flag=False,
                                  target_index=None, target=None)

        # Enable all navigation buttons
        choice_ref.Enable(True)
        select_tracker_elem.Enable(True)

        for btn_c in self.btns_set_fiducial:
            btn_c.Enable(True)

    def OnDialogRobotDestroy(self):
        if self.dlg_correg_robot:
            self.dlg_correg_robot.Destroy()

    def CheckFiducialRegistrationError(self):
        self.navigation.UpdateFiducialRegistrationError(self.tracker)
        fre, fre_ok = self.navigation.GetFiducialRegistrationError(self.icp)

        self.txtctrl_fre.SetValue(str(round(fre, 2)))
        if fre_ok:
            self.txtctrl_fre.SetBackgroundColour('GREEN')
        else:
            self.txtctrl_fre.SetBackgroundColour('RED')

        return fre_ok

    def OnStartNavigation(self):
        select_tracker_elem = self.select_tracker_elem
        choice_ref = self.choice_ref

        if not self.tracker.AreTrackerFiducialsSet() or not self.navigation.AreImageFiducialsSet():
            wx.MessageBox(_("Invalid fiducials, select all coordinates."), _("InVesalius 3"))

        elif not self.tracker.IsTrackerInitialized():
            dlg.ShowNavigationTrackerWarning(0, 'choose')
            errors = True

        else:
            # Prepare GUI for navigation.
            Publisher.sendMessage("Toggle Cross", id=const.SLICE_STATE_CROSS)
            Publisher.sendMessage("Hide current mask")

            # Disable all navigation buttons.
            choice_ref.Enable(False)
            select_tracker_elem.Enable(False)
            for btn_c in self.btns_set_fiducial:
                btn_c.Enable(False)

            self.navigation.EstimateTrackerToInVTransformationMatrix(self.tracker)

            if not self.CheckFiducialRegistrationError():
                # TODO: Exhibit FRE in a warning dialog and only starts navigation after user clicks ok
                print("WARNING: Fiducial registration error too large.")

            self.icp.StartICP(self.navigation, self.tracker)
            if self.icp.use_icp:
                self.checkbox_icp.Enable(True)
                self.checkbox_icp.SetValue(True)
                # Update FRE once more after starting the navigation, due to the optional use of ICP,
                # which improves FRE.
                self.CheckFiducialRegistrationError()

            self.navigation.StartNavigation(self.tracker)

    def OnNavigate(self, evt, btn_nav):
        select_tracker_elem = self.select_tracker_elem
        choice_ref = self.choice_ref

        nav_id = btn_nav.GetValue()
        if not nav_id:
            Publisher.sendMessage("Stop navigation")

            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn_nav.SetToolTip(tooltip)
        else:
            Publisher.sendMessage("Start navigation")

            if self.nav_status:
                tooltip = wx.ToolTip(_("Stop neuronavigation"))
                btn_nav.SetToolTip(tooltip)
            else:
                btn_nav.SetValue(False)

    def ResetUI(self):
        for m in range(0, 3):
            self.btns_set_fiducial[m].SetValue(False)
            for n in range(0, 3):
                self.numctrls_fiducial[m][n].SetValue(0.0)

    def OnCheckboxICP(self, evt, ctrl):
        self.icp.SetICP(self.navigation, ctrl.GetValue())
        self.CheckFiducialRegistrationError()

    def OnCloseProject(self):
        self.ResetUI()
        Publisher.sendMessage('Disconnect tracker')
        Publisher.sendMessage('Update object registration')
        Publisher.sendMessage('Update track object state', flag=False, obj_name=False)
        Publisher.sendMessage('Delete all markers')
        Publisher.sendMessage("Update marker offset state", create=False)
        Publisher.sendMessage("Remove tracts")
        Publisher.sendMessage("Set cross visibility", visibility=0)
        # TODO: Reset camera initial focus
        Publisher.sendMessage('Reset cam clipping range')
        self.navigation.StopNavigation()
        self.navigation.__init__(
            pedal_connection=self.pedal_connection,
            neuronavigation_api=self.neuronavigation_api
        )
        self.tracker.__init__()
        self.icp.__init__()


class ObjectRegistrationPanel(wx.Panel):
    def __init__(self, parent, tracker, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.coil_list = const.COIL

        self.tracker = tracker
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        self.nav_prop = None
        self.obj_fiducials = None
        self.obj_orients = None
        self.obj_ref_mode = None
        self.obj_name = None
        self.timestamp = const.TIMESTAMP

        self.SetAutoLayout(1)
        self.__bind_events()

        # Button for creating new coil
        tooltip = wx.ToolTip(_("Create new coil"))
        btn_new = wx.Button(self, -1, _("New"), size=wx.Size(65, 23))
        btn_new.SetToolTip(tooltip)
        btn_new.Enable(1)
        btn_new.Bind(wx.EVT_BUTTON, self.OnCreateNewCoil)
        self.btn_new = btn_new

        # Button for import config coil file
        tooltip = wx.ToolTip(_("Load coil configuration file"))
        btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLinkLoad)
        self.btn_load = btn_load

        # Save button for object registration
        tooltip = wx.ToolTip(_(u"Save object registration file"))
        btn_save = wx.Button(self, -1, _(u"Save"), size=wx.Size(65, 23))
        btn_save.SetToolTip(tooltip)
        btn_save.Enable(1)
        btn_save.Bind(wx.EVT_BUTTON, self.ShowSaveObjectDialog)
        self.btn_save = btn_save

        # Create a horizontal sizer to represent button save
        line_save = wx.BoxSizer(wx.HORIZONTAL)
        line_save.Add(btn_new, 1, wx.LEFT | wx.TOP | wx.RIGHT, 4)
        line_save.Add(btn_load, 1, wx.LEFT | wx.TOP | wx.RIGHT, 4)
        line_save.Add(btn_save, 1, wx.LEFT | wx.TOP | wx.RIGHT, 4)

        # Change angles threshold
        text_angles = wx.StaticText(self, -1, _("Angle threshold [degrees]:"))
        spin_size_angles = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23))
        spin_size_angles.SetRange(0.1, 99)
        spin_size_angles.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_angles.Bind(wx.EVT_TEXT, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))
        spin_size_angles.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))

        # Change dist threshold
        text_dist = wx.StaticText(self, -1, _("Distance threshold [mm]:"))
        spin_size_dist = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23))
        spin_size_dist.SetRange(0.1, 99)
        spin_size_dist.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_dist.Bind(wx.EVT_TEXT, partial(self.OnSelectDistThreshold, ctrl=spin_size_dist))
        spin_size_dist.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectDistThreshold, ctrl=spin_size_dist))

        # Change timestamp interval
        text_timestamp = wx.StaticText(self, -1, _("Timestamp interval [s]:"))
        spin_timestamp_dist = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc = 0.1)
        spin_timestamp_dist.SetRange(0.5, 60.0)
        spin_timestamp_dist.SetValue(self.timestamp)
        spin_timestamp_dist.Bind(wx.EVT_TEXT, partial(self.OnSelectTimestamp, ctrl=spin_timestamp_dist))
        spin_timestamp_dist.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectTimestamp, ctrl=spin_timestamp_dist))
        self.spin_timestamp_dist = spin_timestamp_dist

        # Create a horizontal sizer to threshold configs
        line_angle_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_angle_threshold.AddMany([(text_angles, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
                                      (spin_size_angles, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)])

        line_dist_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_dist_threshold.AddMany([(text_dist, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
                                      (spin_size_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)])

        line_timestamp = wx.BoxSizer(wx.HORIZONTAL)
        line_timestamp.AddMany([(text_timestamp, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
                                      (spin_timestamp_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)])

        # Check box for trigger monitoring to create markers from serial port
        checkrecordcoords = wx.CheckBox(self, -1, _('Record coordinates'))
        checkrecordcoords.SetValue(False)
        checkrecordcoords.Enable(0)
        checkrecordcoords.Bind(wx.EVT_CHECKBOX, partial(self.OnRecordCoords, ctrl=checkrecordcoords))
        self.checkrecordcoords = checkrecordcoords

        # Check box to track object or simply the stylus
        checktrack = wx.CheckBox(self, -1, _('Track object'))
        checktrack.SetValue(False)
        checktrack.Enable(0)
        checktrack.Bind(wx.EVT_CHECKBOX, partial(self.OnTrackObject, ctrl=checktrack))
        self.checktrack = checktrack

        line_checks = wx.BoxSizer(wx.HORIZONTAL)
        line_checks.Add(checkrecordcoords, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, 5)
        line_checks.Add(checktrack, 0, wx.RIGHT | wx.LEFT, 5)

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_save, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.ALIGN_CENTER_HORIZONTAL, 5)
        main_sizer.Add(line_angle_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_dist_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_timestamp, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_checks, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.OnRemoveObject, 'Remove object data')

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if nav_status:
            self.checkrecordcoords.Enable(1)
            self.checktrack.Enable(0)
            self.btn_save.Enable(0)
            self.btn_new.Enable(0)
            self.btn_load.Enable(0)
        else:
            self.OnRecordCoords(nav_status, self.checkrecordcoords)
            self.checkrecordcoords.SetValue(False)
            self.checkrecordcoords.Enable(0)
            self.btn_save.Enable(1)
            self.btn_new.Enable(1)
            self.btn_load.Enable(1)
            if self.obj_fiducials is not None:
                self.checktrack.Enable(1)
                #Publisher.sendMessage('Enable target button', True)

    def OnSelectAngleThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update angle threshold', angle=ctrl.GetValue())

    def OnSelectDistThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update dist threshold', dist_threshold=ctrl.GetValue())

    def OnSelectTimestamp(self, evt, ctrl):
        self.timestamp = ctrl.GetValue()

    def OnRecordCoords(self, evt, ctrl):
        if ctrl.GetValue() and evt:
            self.spin_timestamp_dist.Enable(0)
            self.thr_record = rec.Record(ctrl.GetValue(), self.timestamp)
        elif (not ctrl.GetValue() and evt) or (ctrl.GetValue() and not evt) :
            self.spin_timestamp_dist.Enable(1)
            self.thr_record.stop()
        elif not ctrl.GetValue() and not evt:
            None

    def OnTrackObject(self, evt, ctrl):
        Publisher.sendMessage('Update track object state', flag=evt.GetSelection(), obj_name=self.obj_name)

    def OnComboCoil(self, evt):
        # coil_name = evt.GetString()
        coil_index = evt.GetSelection()
        Publisher.sendMessage('Change selected coil', self.coil_list[coil_index][1])

    def OnCreateNewCoil(self, event=None):

        if self.tracker.IsTrackerInitialized():
            dialog = dlg.ObjectCalibrationDialog(self.tracker, self.pedal_connection)
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name, polydata, use_default_object = dialog.GetValue()

                    self.neuronavigation_api.update_coil_mesh(polydata)

                    if np.isfinite(self.obj_fiducials).all() and np.isfinite(self.obj_orients).all():
                        self.checktrack.Enable(1)
                        Publisher.sendMessage('Update object registration',
                                              data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
                        Publisher.sendMessage('Update status text in GUI',
                                              label=_("Ready"))
                        # Enable automatically Track object, Show coil and disable Vol. Camera
                        self.checktrack.SetValue(True)
                        Publisher.sendMessage(
                            'Update track object state',
                            flag=True,
                            obj_name=self.obj_name,
                            polydata=polydata,
                            use_default_object=use_default_object,
                        )
                        Publisher.sendMessage('Change camera checkbox', status=False)

            except wx._core.PyAssertionError:  # TODO FIX: win64
                pass

        else:
            dlg.ShowNavigationTrackerWarning(0, 'choose')

    def OnLinkLoad(self, event=None):
        filename = dlg.ShowLoadSaveDialog(message=_(u"Load object registration"),
                                          wildcard=_("Registration files (*.obr)|*.obr"))
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # coil_path = 'magstim_coil_dell_laptop.obr'
        # filename = os.path.join(data_dir, coil_path)

        try:
            if filename:
                with open(filename, 'r') as text_file:
                    data = [s.split('\t') for s in text_file.readlines()]

                registration_coordinates = np.array(data[1:]).astype(np.float32)
                self.obj_fiducials = registration_coordinates[:, :3]
                self.obj_orients = registration_coordinates[:, 3:]

                self.obj_name = data[0][1]
                self.obj_ref_mode = int(data[0][-1])

                self.checktrack.Enable(1)
                self.checktrack.SetValue(True)
                Publisher.sendMessage('Update object registration',
                                      data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Object file successfully loaded"))
                Publisher.sendMessage('Update track object state', flag=True, obj_name=self.obj_name)
                Publisher.sendMessage('Change camera checkbox', status=False)
                wx.MessageBox(_("Object file successfully loaded"), _("InVesalius 3"))
        except:
            wx.MessageBox(_("Object registration file incompatible."), _("InVesalius 3"))
            Publisher.sendMessage('Update status text in GUI', label="")

    def ShowSaveObjectDialog(self, evt):
        if np.isnan(self.obj_fiducials).any() or np.isnan(self.obj_orients).any():
            wx.MessageBox(_("Digitize all object fiducials before saving"), _("Save error"))
        else:
            filename = dlg.ShowLoadSaveDialog(message=_(u"Save object registration as..."),
                                              wildcard=_("Registration files (*.obr)|*.obr"),
                                              style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                              default_filename="object_registration.obr", save_ext="obr")
            if filename:
                hdr = 'Object' + "\t" + utils.decode(self.obj_name, const.FS_ENCODE) + "\t" + 'Reference' + "\t" + str('%d' % self.obj_ref_mode)
                data = np.hstack([self.obj_fiducials, self.obj_orients])
                np.savetxt(filename, data, fmt='%.4f', delimiter='\t', newline='\n', header=hdr)
                wx.MessageBox(_("Object file successfully saved"), _("Save"))

    def OnCloseProject(self):
        self.OnRemoveObject()

    def OnRemoveObject(self):
        self.checkrecordcoords.SetValue(False)
        self.checkrecordcoords.Enable(0)
        self.checktrack.SetValue(False)
        self.checktrack.Enable(0)

        self.nav_prop = None
        self.obj_fiducials = None
        self.obj_orients = None
        self.obj_ref_mode = None
        self.obj_name = None
        self.timestamp = const.TIMESTAMP

        Publisher.sendMessage('Update track object state', flag=False, obj_name=False)


class MarkersPanel(wx.Panel):
    @dataclasses.dataclass
    class Marker:
        """Class for storing markers. @dataclass decorator simplifies
        setting default values, serialization, etc."""
        x : float = 0
        y : float = 0
        z : float = 0
        alpha : float = dataclasses.field(default = None)
        beta : float = dataclasses.field(default = None)
        gamma : float = dataclasses.field(default = None)
        r : float = 0
        g : float = 1
        b : float = 0
        size : int = 2
        label : str = '*'
        x_seed : float = 0
        y_seed : float = 0
        z_seed : float = 0
        is_target : bool = False
        session_id : int = 1

        # x, y, z, alpha, beta, gamma can be jointly accessed as coord
        @property
        def coord(self):
            return list((self.x, self.y, self.z, self.alpha, self.beta, self.gamma))

        @coord.setter
        def coord(self, new_coord):
            self.x, self.y, self.z, self.alpha, self.beta, self.gamma = new_coord

        # r, g, b can be jointly accessed as colour
        @property
        def colour(self):
            return list((self.r, self.g, self.b),)

        @colour.setter
        def colour(self, new_colour):
            self.r, self.g, self.b = new_colour

        # x_seed, y_seed, z_seed can be jointly accessed as seed
        @property
        def seed(self):
            return list((self.x_seed, self.y_seed, self.z_seed),)

        @seed.setter
        def seed(self, new_seed):
            self.x_seed, self.y_seed, self.z_seed = new_seed

        @classmethod
        def to_string_headers(cls):
            """Return the string containing tab-separated list of field names (headers)."""
            res = [field.name for field in dataclasses.fields(cls)]
            res.extend(['x_world', 'y_world', 'z_world', 'alpha_world', 'beta_world', 'gamma_world'])
            return '\t'.join(map(lambda x: '\"%s\"' % x, res))

        def to_string(self):
            """Serialize to excel-friendly tab-separated string"""
            res = ''
            for field in dataclasses.fields(self.__class__):
                if field.type is str:
                    res += ('\"%s\"\t' % getattr(self, field.name))
                else:
                    res += ('%s\t' % str(getattr(self, field.name)))

            if self.alpha is not None and self.beta is not None and self.gamma is not None:
                # Add world coordinates (in addition to the internal ones).
                position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                    position=[self.x, self.y, self.z],
                    orientation=[self.alpha, self.beta, self.gamma],
                )

            else:
                position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                      position=[self.x, self.y, self.z],
                      orientation=[0,0,0],
                 )

            res += '\t'.join(map(lambda x: 'N/A' if x is None else str(x), (*position_world, *orientation_world)))
            return res

        def from_string(self, inp_str):
            """Deserialize from a tab-separated string. If the string is not 
            properly formatted, might throw an exception and leave the object
            in an inconsistent state."""
            for field, str_val in zip(dataclasses.fields(self.__class__), inp_str.split('\t')):
                if field.type is float and str_val != 'None':
                    setattr(self, field.name, float(str_val))
                if field.type is float and str_val == 'None':
                    setattr(self, field.name, None)
                if field.type is int:
                    setattr(self, field.name, int(str_val))
                if field.type is str:
                    setattr(self, field.name, str_val[1:-1]) # remove the quotation marks
                if field.type is bool:
                    setattr(self, field.name, str_val=='True')

    def __init__(self, parent, navigation, tracker, icp):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.navigation = navigation
        self.tracker = tracker
        self.icp = icp

        self.__bind_events()

        self.session = ses.Session()

        self.current_coord = [0, 0, 0, None, None, None]
        self.current_seed = 0, 0, 0

        self.markers = []
        self.nav_status = False

        self.marker_colour = const.MARKER_COLOUR
        self.marker_size = const.MARKER_SIZE
        self.arrow_marker_size = const.ARROW_MARKER_SIZE
        self.current_session = 1

        # Change marker size
        spin_size = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_size.SetRange(1, 99)
        spin_size.SetValue(self.marker_size)
        spin_size.Bind(wx.EVT_TEXT, partial(self.OnSelectSize, ctrl=spin_size))
        spin_size.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectSize, ctrl=spin_size))

        # Marker colour select
        select_colour = csel.ColourSelect(self, -1, colour=[255*s for s in self.marker_colour], size=wx.Size(20, 23))
        select_colour.Bind(csel.EVT_COLOURSELECT, partial(self.OnSelectColour, ctrl=select_colour))

        btn_create = wx.Button(self, -1, label=_('Create marker'), size=wx.Size(135, 23))
        btn_create.Bind(wx.EVT_BUTTON, self.OnCreateMarker)

        sizer_create = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        sizer_create.AddMany([(spin_size, 1),
                              (select_colour, 0),
                              (btn_create, 0)])

        # Buttons to save and load markers and to change its visibility as well
        btn_save = wx.Button(self, -1, label=_('Save'), size=wx.Size(65, 23))
        btn_save.Bind(wx.EVT_BUTTON, self.OnSaveMarkers)

        btn_load = wx.Button(self, -1, label=_('Load'), size=wx.Size(65, 23))
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadMarkers)

        btn_visibility = wx.ToggleButton(self, -1, _("Hide"), size=wx.Size(65, 23))
        btn_visibility.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnMarkersVisibility, ctrl=btn_visibility))

        sizer_btns = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        sizer_btns.AddMany([(btn_save, 1, wx.RIGHT),
                            (btn_load, 0, wx.LEFT | wx.RIGHT),
                            (btn_visibility, 0, wx.LEFT)])

        # Buttons to delete or remove markers
        btn_delete_single = wx.Button(self, -1, label=_('Remove'), size=wx.Size(65, 23))
        btn_delete_single.Bind(wx.EVT_BUTTON, self.OnDeleteMultipleMarkers)

        btn_delete_all = wx.Button(self, -1, label=_('Delete all'), size=wx.Size(135, 23))
        btn_delete_all.Bind(wx.EVT_BUTTON, self.OnDeleteAllMarkers)

        sizer_delete = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        sizer_delete.AddMany([(btn_delete_single, 1, wx.RIGHT),
                              (btn_delete_all, 0, wx.LEFT)])

        # List of markers
        self.lc = wx.ListCtrl(self, -1, style=wx.LC_REPORT, size=wx.Size(0,120))
        self.lc.InsertColumn(const.ID_COLUMN, '#')
        self.lc.SetColumnWidth(const.ID_COLUMN, 28)

        self.lc.InsertColumn(const.SESSION_COLUMN, 'Session')
        self.lc.SetColumnWidth(const.SESSION_COLUMN, 52)

        self.lc.InsertColumn(const.LABEL_COLUMN, 'Label')
        self.lc.SetColumnWidth(const.LABEL_COLUMN, 118)

        self.lc.InsertColumn(const.TARGET_COLUMN, 'Target')
        self.lc.SetColumnWidth(const.TARGET_COLUMN, 45)

        if self.session.debug:
            self.lc.InsertColumn(const.X_COLUMN, 'X')
            self.lc.SetColumnWidth(const.X_COLUMN, 45)

            self.lc.InsertColumn(const.Y_COLUMN, 'Y')
            self.lc.SetColumnWidth(const.Y_COLUMN, 45)

            self.lc.InsertColumn(const.Z_COLUMN, 'Z')
            self.lc.SetColumnWidth(const.Z_COLUMN, 45)

        self.lc.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnMouseRightDown)
        self.lc.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemBlink)
        self.lc.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnStopItemBlink)

        # Add all lines into main sizer
        group_sizer = wx.BoxSizer(wx.VERTICAL)
        group_sizer.Add(sizer_create, 0, wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(sizer_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(sizer_delete, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(self.lc, 0, wx.EXPAND | wx.ALL, 5)
        group_sizer.Fit(self)

        self.SetSizer(group_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.UpdateCurrentCoord, 'Set cross focal point')
        Publisher.subscribe(self.OnDeleteMultipleMarkers, 'Delete fiducial marker')
        Publisher.subscribe(self.OnDeleteAllMarkers, 'Delete all markers')
        Publisher.subscribe(self.CreateMarker, 'Create marker')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateSeedCoordinates, 'Update tracts')
        Publisher.subscribe(self.OnChangeCurrentSession, 'Current session changed')

    def __find_target_marker(self):
        """
        Return the index of the marker currently selected as target (there
        should be at most one). If there is no such marker, return None.
        """
        for i in range(len(self.markers)):
            if self.markers[i].is_target:
                return i
                
        return None

    def __get_selected_items(self):
        """    
        Returns a (possibly empty) list of the selected items in the list control.
        """
        selection = []

        next = self.lc.GetFirstSelected()
               
        while next != -1:
            selection.append(next)
            next = self.lc.GetNextSelected(next)

        return selection

    def __delete_multiple_markers(self, index):
        """
        Delete multiple markers indexed by index. index must be sorted in
        the ascending order.
        """
        for i in reversed(index):
            del self.markers[i]
            self.lc.DeleteItem(i)
            for n in range(0, self.lc.GetItemCount()):
                self.lc.SetItem(n, 0, str(n + 1))
        Publisher.sendMessage('Remove multiple markers', index=index)

    def __set_marker_as_target(self, idx):
        """
        Set marker indexed by idx as the new target. idx must be a valid index.
        """
        # Find the previous target
        prev_idx = self.__find_target_marker()

        # If the new target is same as the previous do nothing.
        if prev_idx == idx:
            return

        # Unset the previous target
        if prev_idx is not None:
            self.markers[prev_idx].is_target = False
            self.lc.SetItemBackgroundColour(prev_idx, 'white')
            Publisher.sendMessage('Set target transparency', status=False, index=prev_idx)
            self.lc.SetItem(prev_idx, const.TARGET_COLUMN, "")

        # Set the new target
        self.markers[idx].is_target = True
        self.lc.SetItemBackgroundColour(idx, 'RED')
        self.lc.SetItem(idx, const.TARGET_COLUMN, _("Yes"))

        Publisher.sendMessage('Update target', coord=self.markers[idx].coord)
        Publisher.sendMessage('Set target transparency', status=True, index=idx)
        wx.MessageBox(_("New target selected."), _("InVesalius 3"))

    @staticmethod
    def __list_fiducial_labels():
        """Return the list of marker labels denoting fiducials."""
        return list(itertools.chain(*(const.BTNS_IMG_MARKERS[i].values() for i in const.BTNS_IMG_MARKERS)))

    def UpdateCurrentCoord(self, position):
        self.current_coord = list(position)
        if not self.navigation.track_obj:
            self.current_coord[3:] = None, None, None

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if not nav_status:
            self.nav_status = False
            self.current_coord[3:] = None, None, None
        else:
            self.nav_status = True

    def UpdateSeedCoordinates(self, root=None, affine_vtk=None, coord_offset=(0, 0, 0), coord_offset_w=(0, 0, 0)):
        self.current_seed = coord_offset_w

    def OnMouseRightDown(self, evt):
        # TODO: Enable the "Set as target" only when target is created with registered object
        menu_id = wx.Menu()
        edit_id = menu_id.Append(0, _('Edit label'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuEditMarkerLabel, edit_id)
        color_id = menu_id.Append(1, _('Edit color'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuSetColor, color_id)
        menu_id.AppendSeparator()
        target_menu = menu_id.Append(2, _('Set as target'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuSetTarget, target_menu)
        menu_id.AppendSeparator()

        check_target_angles = all([elem is not None for elem in self.markers[self.lc.GetFocusedItem()].coord[3:]])
        # Enable "Send target to robot" button only if tracker is robot, if navigation is on and if target is not none
        if self.tracker.tracker_id == const.ROBOT:
            send_target_to_robot_compensation = menu_id.Append(3, _('Sets target to robot head move compensation'))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuSetRobotCompensation, send_target_to_robot_compensation)
            send_target_to_robot = menu_id.Append(4, _('Send target from InVesalius to robot'))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuSendTargetToRobot, send_target_to_robot)
            if self.nav_status and check_target_angles:
                send_target_to_robot_compensation.Enable(True)
                send_target_to_robot.Enable(True)
            else:
                send_target_to_robot_compensation.Enable(False)
                send_target_to_robot.Enable(False)

        if check_target_angles:
            target_menu.Enable(True)
        else:
            target_menu.Enable(False)

        # TODO: Create the remove target option so the user can disable the target without removing the marker
        # target_menu_rem = menu_id.Append(3, _('Remove target'))
        # menu_id.Bind(wx.EVT_MENU, self.OnMenuRemoveTarget, target_menu_rem)

        self.PopupMenu(menu_id)
        menu_id.Destroy()

    def OnItemBlink(self, evt):
        Publisher.sendMessage('Blink Marker', index=self.lc.GetFocusedItem())

    def OnStopItemBlink(self, evt):
        Publisher.sendMessage('Stop Blink Marker')

    def OnMenuEditMarkerLabel(self, evt):
        list_index = self.lc.GetFocusedItem()
        if list_index != -1:
            new_label = dlg.ShowEnterMarkerID(self.lc.GetItemText(list_index, const.LABEL_COLUMN))
            self.markers[list_index].label = str(new_label)
            self.lc.SetItem(list_index, const.LABEL_COLUMN, new_label)
        else:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))

    def OnMenuSetTarget(self, evt):
        idx = self.lc.GetFocusedItem()
        if idx != -1:
            self.__set_marker_as_target(idx)
        else:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))

    def OnMenuSetColor(self, evt):
        index = self.lc.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        color_current = [ch * 255 for ch in self.markers[index].colour]

        color_new = dlg.ShowColorDialog(color_current=color_current)

        if color_new:
            assert len(color_new) == 3

            # XXX: Seems like a slightly too early point for rounding; better to round only when the value
            #      is printed to the screen or file.
            #
            self.markers[index].colour = [round(s / 255.0, 3) for s in color_new]

            Publisher.sendMessage('Set new color', index=index, color=color_new)

    def OnMenuSetRobotCompensation(self, evt):
        if isinstance(evt, int):
           self.lc.Focus(evt)

        Publisher.sendMessage('Reset robot process', data=None)
        matrix_tracker_fiducials = self.tracker.GetMatrixTrackerFiducials()
        Publisher.sendMessage('Update tracker fiducials matrix',
                              matrix_tracker_fiducials=matrix_tracker_fiducials)
        Publisher.sendMessage('Update robot target', robot_tracker_flag=True, target_index=self.lc.GetFocusedItem(), target=None)

    def OnMenuSendTargetToRobot(self, evt):
        if isinstance(evt, int):
           self.lc.Focus(evt)
        index = self.lc.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        Publisher.sendMessage('Reset robot process', data=None)
        matrix_tracker_fiducials = self.tracker.GetMatrixTrackerFiducials()
        Publisher.sendMessage('Update tracker fiducials matrix',
                              matrix_tracker_fiducials=matrix_tracker_fiducials)

        target_coord = self.markers[index].coord[:3]
        target = dcr.image_to_tracker(self.navigation.m_change, target_coord, self.icp)

        Publisher.sendMessage('Update robot target', robot_tracker_flag=True, target_index=self.lc.GetFocusedItem(), target=target.tolist())

    def OnDeleteAllMarkers(self, evt=None):
        if evt is not None:
            result = dlg.ShowConfirmationDialog(msg=_("Remove all markers? Cannot be undone."))
            if result != wx.ID_OK:
                return

        if self.__find_target_marker() is not None:
            Publisher.sendMessage('Disable or enable coil tracker', status=False)
            if evt is not None:
                wx.MessageBox(_("Target deleted."), _("InVesalius 3"))
            if self.tracker.tracker_id == const.ROBOT:
                Publisher.sendMessage('Update robot target', robot_tracker_flag=False,
                                      target_index=None, target=None)

        self.markers = []
        Publisher.sendMessage('Remove all markers', indexes=self.lc.GetItemCount())
        self.lc.DeleteAllItems()
        Publisher.sendMessage('Stop Blink Marker', index='DeleteAll')

    def OnDeleteMultipleMarkers(self, evt=None, label=None):
        # OnDeleteMultipleMarkers is used for both pubsub and button click events
        # Pubsub is used for fiducial handle and button click for all others

        # called through pubsub
        if not evt:
            index = []
            
            if label and (label in self.__list_fiducial_labels()):
                for id_n in range(self.lc.GetItemCount()):
                    item = self.lc.GetItem(id_n, const.LABEL_COLUMN)
                    if item.GetText() == label:
                        self.lc.Focus(item.GetId())
                        index = [self.lc.GetFocusedItem()]

        # called from button click
        else:
            index = self.__get_selected_items()

        if index:
            if self.__find_target_marker() in index:
                Publisher.sendMessage('Disable or enable coil tracker', status=False)
                if self.tracker.tracker_id == const.ROBOT:
                    Publisher.sendMessage('Update robot target', robot_tracker_flag=False,
                                          target_index=None, target=None)
                wx.MessageBox(_("Target deleted."), _("InVesalius 3"))

            self.__delete_multiple_markers(index)
        else:
            if evt: # Don't show the warning if called through pubsub
                wx.MessageBox(_("No data selected."), _("InVesalius 3"))

    def OnCreateMarker(self, evt):
        self.CreateMarker()

    def OnLoadMarkers(self, evt):
        """Loads markers from file and appends them to the current marker list.
        The file should contain no more than a single target marker. Also the
        file should not contain any fiducials already in the list."""
        filename = dlg.ShowLoadSaveDialog(message=_(u"Load markers"),
                                          wildcard=const.WILDCARD_MARKER_FILES)
                
        if not filename:
            return
        
        try:
            with open(filename, 'r') as file:
                magick_line = file.readline()
                assert magick_line.startswith(const.MARKER_FILE_MAGICK_STRING)
                ver = int(magick_line.split('_')[-1])
                if ver != 0:
                    wx.MessageBox(_("Unknown version of the markers file."), _("InVesalius 3"))
                    return
                
                file.readline() # skip the header line

                # Read the data lines and create markers
                for line in file.readlines():
                    marker = self.Marker()
                    marker.from_string(line)
                    self.CreateMarker(coord=marker.coord, colour=marker.colour, size=marker.size,
                                      label=marker.label, is_target=False, seed=marker.seed, session_id=marker.session_id)

                    if marker.label in self.__list_fiducial_labels():
                        Publisher.sendMessage('Load image fiducials', label=marker.label, coord=marker.coord)

                    # If the new marker has is_target=True, we first create
                    # a marker with is_target=False, and then call __set_marker_as_target
                    if marker.is_target:
                        self.__set_marker_as_target(len(self.markers) - 1)

        except Exception as e:
            wx.MessageBox(_("Invalid markers file."), _("InVesalius 3"))

    def OnMarkersVisibility(self, evt, ctrl):
        if ctrl.GetValue():
            Publisher.sendMessage('Hide all markers',  indexes=self.lc.GetItemCount())
            ctrl.SetLabel('Show')
        else:
            Publisher.sendMessage('Show all markers',  indexes=self.lc.GetItemCount())
            ctrl.SetLabel('Hide')

    def OnSaveMarkers(self, evt):
        prj_data = prj.Project()
        timestamp = time.localtime(time.time())
        stamp_date = '{:0>4d}{:0>2d}{:0>2d}'.format(timestamp.tm_year, timestamp.tm_mon, timestamp.tm_mday)
        stamp_time = '{:0>2d}{:0>2d}{:0>2d}'.format(timestamp.tm_hour, timestamp.tm_min, timestamp.tm_sec)
        sep = '-'
        parts = [stamp_date, stamp_time, prj_data.name, 'markers']
        default_filename = sep.join(parts) + '.mkss'

        filename = dlg.ShowLoadSaveDialog(message=_(u"Save markers as..."),
                                          wildcard=const.WILDCARD_MARKER_FILES,
                                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                          default_filename=default_filename)

        if not filename:
            return

        try:
            with open(filename, 'w', newline='') as file:
                file.writelines(['%s%i\n' % (const.MARKER_FILE_MAGICK_STRING, const.CURRENT_MARKER_FILE_VERSION)])
                file.writelines(['%s\n' % self.Marker.to_string_headers()])
                file.writelines('%s\n' % marker.to_string() for marker in self.markers)
                file.close()
        except:
            wx.MessageBox(_("Error writing markers file."), _("InVesalius 3"))  

    def OnSelectColour(self, evt, ctrl):
        # TODO: Make sure GetValue returns 3 numbers (without alpha)
        self.marker_colour = [colour / 255.0 for colour in ctrl.GetValue()][:3]

    def OnSelectSize(self, evt, ctrl):
        self.marker_size = ctrl.GetValue()

    def OnChangeCurrentSession(self, new_session_id):
        self.current_session = new_session_id

    def CreateMarker(self, coord=None, colour=None, size=None, label='*', is_target=False, seed=None, session_id=None):
        new_marker = self.Marker()
        new_marker.coord = coord or self.current_coord
        new_marker.colour = colour or self.marker_colour
        new_marker.size = size or self.marker_size
        new_marker.label = label
        new_marker.is_target = is_target
        new_marker.seed = seed or self.current_seed
        new_marker.session_id = session_id or self.current_session

        if self.tracker.tracker_id == const.ROBOT and self.nav_status:
            current_head_robot_target_status = True
        else:
            current_head_robot_target_status = False

        Publisher.sendMessage('Add marker to robot control', data=current_head_robot_target_status)

        # Note that ball_id is zero-based, so we assign it len(self.markers) before the new marker is added
        if all([elem is not None for elem in new_marker.coord[3:]]):
            arrow_flag = True
        else:
            arrow_flag = False

        Publisher.sendMessage('Add marker', marker_id=len(self.markers),
                              size=new_marker.size,
                              colour=new_marker.colour,
                              coord=new_marker.coord,
                              arrow_flag=arrow_flag)


        self.markers.append(new_marker)

        # Add item to list control in panel
        num_items = self.lc.GetItemCount()
        self.lc.InsertItem(num_items, str(num_items + 1))
        self.lc.SetItem(num_items, const.SESSION_COLUMN, str(new_marker.session_id))
        self.lc.SetItem(num_items, const.LABEL_COLUMN, new_marker.label)

        if self.session.debug:
            self.lc.SetItem(num_items, const.X_COLUMN, str(round(new_marker.x, 1)))
            self.lc.SetItem(num_items, const.Y_COLUMN, str(round(new_marker.y, 1)))
            self.lc.SetItem(num_items, const.Z_COLUMN, str(round(new_marker.z, 1)))

        self.lc.EnsureVisible(num_items)

class DbsPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)


class TractographyPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.affine = np.identity(4)
        self.affine_vtk = None
        self.trekker = None
        self.n_tracts = const.N_TRACTS
        self.peel_depth = const.PEEL_DEPTH
        self.view_tracts = False
        self.seed_offset = const.SEED_OFFSET
        self.seed_radius = const.SEED_RADIUS
        self.sleep_nav = const.SLEEP_NAVIGATION
        self.brain_opacity = const.BRAIN_OPACITY
        self.brain_peel = None
        self.brain_actor = None
        self.n_peels = const.MAX_PEEL_DEPTH
        self.p_old = np.array([[0., 0., 0.]])
        self.tracts_run = None
        self.trekker_cfg = const.TREKKER_CONFIG
        self.nav_status = False
        self.peel_loaded = False
        self.SetAutoLayout(1)
        self.__bind_events()

        # Button for import config coil file
        tooltip = wx.ToolTip(_("Load FOD"))
        btn_load = wx.Button(self, -1, _("FOD"), size=wx.Size(50, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLinkFOD)
        # self.btn_load = btn_load

        # Save button for object registration
        tooltip = wx.ToolTip(_(u"Load Trekker configuration parameters"))
        btn_load_cfg = wx.Button(self, -1, _(u"Configure"), size=wx.Size(65, 23))
        btn_load_cfg.SetToolTip(tooltip)
        btn_load_cfg.Enable(1)
        btn_load_cfg.Bind(wx.EVT_BUTTON, self.OnLoadParameters)
        # self.btn_load_cfg = btn_load_cfg

        # Button for creating new coil
        tooltip = wx.ToolTip(_("Load brain visualization"))
        btn_mask = wx.Button(self, -1, _("Brain"), size=wx.Size(50, 23))
        btn_mask.SetToolTip(tooltip)
        btn_mask.Enable(1)
        btn_mask.Bind(wx.EVT_BUTTON, self.OnLinkBrain)
        # self.btn_new = btn_new

        # Button for creating new coil
        tooltip = wx.ToolTip(_("Load anatomical labels"))
        btn_act = wx.Button(self, -1, _("ACT"), size=wx.Size(50, 23))
        btn_act.SetToolTip(tooltip)
        btn_act.Enable(1)
        btn_act.Bind(wx.EVT_BUTTON, self.OnLoadACT)
        # self.btn_new = btn_new

        # Create a horizontal sizer to represent button save
        line_btns = wx.BoxSizer(wx.HORIZONTAL)
        line_btns.Add(btn_load, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns.Add(btn_load_cfg, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns.Add(btn_mask, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns.Add(btn_act, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        # Change peeling depth
        text_peel_depth = wx.StaticText(self, -1, _("Peeling depth (mm):"))
        spin_peel_depth = wx.SpinCtrl(self, -1, "", size=wx.Size(50, 23))
        spin_peel_depth.Enable(1)
        spin_peel_depth.SetRange(0, const.MAX_PEEL_DEPTH)
        spin_peel_depth.SetValue(const.PEEL_DEPTH)
        spin_peel_depth.Bind(wx.EVT_TEXT, partial(self.OnSelectPeelingDepth, ctrl=spin_peel_depth))
        spin_peel_depth.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectPeelingDepth, ctrl=spin_peel_depth))

        # Change number of tracts
        text_ntracts = wx.StaticText(self, -1, _("Number tracts:"))
        spin_ntracts = wx.SpinCtrl(self, -1, "", size=wx.Size(50, 23))
        spin_ntracts.Enable(1)
        spin_ntracts.SetRange(1, 2000)
        spin_ntracts.SetValue(const.N_TRACTS)
        spin_ntracts.Bind(wx.EVT_TEXT, partial(self.OnSelectNumTracts, ctrl=spin_ntracts))
        spin_ntracts.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectNumTracts, ctrl=spin_ntracts))

        # Change seed offset for computing tracts
        text_offset = wx.StaticText(self, -1, _("Seed offset (mm):"))
        spin_offset = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc = 0.1)
        spin_offset.Enable(1)
        spin_offset.SetRange(0, 100.0)
        spin_offset.SetValue(self.seed_offset)
        spin_offset.Bind(wx.EVT_TEXT, partial(self.OnSelectOffset, ctrl=spin_offset))
        spin_offset.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectOffset, ctrl=spin_offset))
        # self.spin_offset = spin_offset

        # Change seed radius for computing tracts
        text_radius = wx.StaticText(self, -1, _("Seed radius (mm):"))
        spin_radius = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_radius.Enable(1)
        spin_radius.SetRange(0, 100.0)
        spin_radius.SetValue(self.seed_radius)
        spin_radius.Bind(wx.EVT_TEXT, partial(self.OnSelectRadius, ctrl=spin_radius))
        spin_radius.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectRadius, ctrl=spin_radius))
        # self.spin_radius = spin_radius

        # Change sleep pause between navigation loops
        text_sleep = wx.StaticText(self, -1, _("Sleep (s):"))
        spin_sleep = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        spin_sleep.Enable(1)
        spin_sleep.SetRange(0.01, 10.0)
        spin_sleep.SetValue(self.sleep_nav)
        spin_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectSleep, ctrl=spin_sleep))
        spin_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectSleep, ctrl=spin_sleep))

        # Change opacity of brain mask visualization
        text_opacity = wx.StaticText(self, -1, _("Brain opacity:"))
        spin_opacity = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_opacity.Enable(0)
        spin_opacity.SetRange(0, 1.0)
        spin_opacity.SetValue(self.brain_opacity)
        spin_opacity.Bind(wx.EVT_TEXT, partial(self.OnSelectOpacity, ctrl=spin_opacity))
        spin_opacity.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectOpacity, ctrl=spin_opacity))
        self.spin_opacity = spin_opacity

        # Create a horizontal sizer to threshold configs
        border = 1
        line_peel_depth = wx.BoxSizer(wx.HORIZONTAL)
        line_peel_depth.AddMany([(text_peel_depth, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                                 (spin_peel_depth, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        line_ntracts = wx.BoxSizer(wx.HORIZONTAL)
        line_ntracts.AddMany([(text_ntracts, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                              (spin_ntracts, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        line_offset = wx.BoxSizer(wx.HORIZONTAL)
        line_offset.AddMany([(text_offset, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                             (spin_offset, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        line_radius = wx.BoxSizer(wx.HORIZONTAL)
        line_radius.AddMany([(text_radius, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                             (spin_radius, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        line_sleep = wx.BoxSizer(wx.HORIZONTAL)
        line_sleep.AddMany([(text_sleep, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                            (spin_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        line_opacity = wx.BoxSizer(wx.HORIZONTAL)
        line_opacity.AddMany([(text_opacity, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                            (spin_opacity, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        # Check box to enable tract visualization
        checktracts = wx.CheckBox(self, -1, _('Enable tracts'))
        checktracts.SetValue(False)
        checktracts.Enable(0)
        checktracts.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableTracts, ctrl=checktracts))
        self.checktracts = checktracts

        # Check box to enable surface peeling
        checkpeeling = wx.CheckBox(self, -1, _('Peel surface'))
        checkpeeling.SetValue(False)
        checkpeeling.Enable(0)
        checkpeeling.Bind(wx.EVT_CHECKBOX, partial(self.OnShowPeeling, ctrl=checkpeeling))
        self.checkpeeling = checkpeeling

        # Check box to enable tract visualization
        checkACT = wx.CheckBox(self, -1, _('ACT'))
        checkACT.SetValue(False)
        checkACT.Enable(0)
        checkACT.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableACT, ctrl=checkACT))
        self.checkACT = checkACT

        border_last = 1
        line_checks = wx.BoxSizer(wx.HORIZONTAL)
        line_checks.Add(checktracts, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, border_last)
        line_checks.Add(checkpeeling, 0, wx.ALIGN_CENTER | wx.RIGHT | wx.LEFT, border_last)
        line_checks.Add(checkACT, 0, wx.RIGHT | wx.LEFT, border_last)

        # Add line sizers into main sizer
        border = 1
        border_last = 10
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, border_last)
        main_sizer.Add(line_peel_depth, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_ntracts, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_offset, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_radius, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_opacity, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_checks, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, border_last)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.OnUpdateTracts, 'Set cross focal point')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')

    def OnSelectPeelingDepth(self, evt, ctrl):
        self.peel_depth = ctrl.GetValue()
        if self.checkpeeling.GetValue():
            actor = self.brain_peel.get_actor(self.peel_depth)
            Publisher.sendMessage('Update peel', flag=True, actor=actor)
            Publisher.sendMessage('Get peel centers and normals', centers=self.brain_peel.peel_centers,
                                  normals=self.brain_peel.peel_normals)
            Publisher.sendMessage('Get init locator', locator=self.brain_peel.locator)
            self.peel_loaded = True
    def OnSelectNumTracts(self, evt, ctrl):
        self.n_tracts = ctrl.GetValue()
        # self.tract.n_tracts = ctrl.GetValue()
        Publisher.sendMessage('Update number of tracts', data=self.n_tracts)

    def OnSelectOffset(self, evt, ctrl):
        self.seed_offset = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage('Update seed offset', data=self.seed_offset)

    def OnSelectRadius(self, evt, ctrl):
        self.seed_radius = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage('Update seed radius', data=self.seed_radius)

    def OnSelectSleep(self, evt, ctrl):
        self.sleep_nav = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage('Update sleep', data=self.sleep_nav)

    def OnSelectOpacity(self, evt, ctrl):
        self.brain_actor.GetProperty().SetOpacity(ctrl.GetValue())
        Publisher.sendMessage('Update peel', flag=True, actor=self.brain_actor)

    def OnShowPeeling(self, evt, ctrl):
        # self.view_peeling = ctrl.GetValue()
        if ctrl.GetValue():
            actor = self.brain_peel.get_actor(self.peel_depth)
            self.peel_loaded = True
            Publisher.sendMessage('Update peel visualization', data=self.peel_loaded)
        else:
            actor = None
            self.peel_loaded = False
            Publisher.sendMessage('Update peel visualization', data= self.peel_loaded)

        Publisher.sendMessage('Update peel', flag=ctrl.GetValue(), actor=actor)

    def OnEnableTracts(self, evt, ctrl):
        self.view_tracts = ctrl.GetValue()
        Publisher.sendMessage('Update tracts visualization', data=self.view_tracts)
        if not self.view_tracts:
            Publisher.sendMessage('Remove tracts')
            Publisher.sendMessage("Update marker offset state", create=False)

    def OnEnableACT(self, evt, ctrl):
        # self.view_peeling = ctrl.GetValue()
        # if ctrl.GetValue():
        #     act_data = self.brain_peel.get_actor(self.peel_depth)
        # else:
        #     actor = None
        Publisher.sendMessage('Enable ACT', data=ctrl.GetValue())

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status

    def OnLinkBrain(self, event=None):
        Publisher.sendMessage('Begin busy cursor')
        inv_proj = prj.Project()
        peels_dlg = dlg.PeelsCreationDlg(wx.GetApp().GetTopWindow())
        ret = peels_dlg.ShowModal()
        method = peels_dlg.method
        if ret == wx.ID_OK:
            slic = sl.Slice()
            ww = slic.window_width
            wl = slic.window_level
            affine = np.eye(4)
            if method == peels_dlg.FROM_FILES:
                try:
                    affine = slic.affine.copy()
                except AttributeError:
                    pass

            self.brain_peel = brain.Brain(self.n_peels, ww, wl, affine, inv_proj)
            if method == peels_dlg.FROM_MASK:
                choices = [i for i in inv_proj.mask_dict.values()]
                mask_index = peels_dlg.cb_masks.GetSelection()
                mask = choices[mask_index]
                self.brain_peel.from_mask(mask)
            else:
                mask_path = peels_dlg.mask_path
                self.brain_peel.from_mask_file(mask_path)
            self.brain_actor = self.brain_peel.get_actor(self.peel_depth)
            self.brain_actor.GetProperty().SetOpacity(self.brain_opacity)
            Publisher.sendMessage('Update peel', flag=True, actor=self.brain_actor)
            Publisher.sendMessage('Get peel centers and normals', centers=self.brain_peel.peel_centers,
                                  normals=self.brain_peel.peel_normals)
            Publisher.sendMessage('Get init locator', locator=self.brain_peel.locator)
            self.checkpeeling.Enable(1)
            self.checkpeeling.SetValue(True)
            self.spin_opacity.Enable(1)
            Publisher.sendMessage('Update status text in GUI', label=_("Brain model loaded"))
            self.peel_loaded = True
            Publisher.sendMessage('Update peel visualization', data= self.peel_loaded)

        peels_dlg.Destroy()
        Publisher.sendMessage('End busy cursor')

    def OnLinkFOD(self, event=None):
        Publisher.sendMessage('Begin busy cursor')
        filename = dlg.ShowImportOtherFilesDialog(const.ID_NIFTI_IMPORT, msg=_("Import Trekker FOD"))
        # Juuso
        # data_dir = os.environ.get('OneDriveConsumer') + '\\data\\dti'
        # FOD_path = 'sub-P0_dwi_FOD.nii'
        # Baran
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # FOD_path = 'Baran_FOD.nii'
        # filename = os.path.join(data_dir, FOD_path)

        if not self.affine_vtk:
            slic = sl.Slice()
            prj_data = prj.Project()
            matrix_shape = tuple(prj_data.matrix_shape)
            spacing = tuple(prj_data.spacing)
            img_shift = spacing[1] * (matrix_shape[1] - 1)
            self.affine = slic.affine.copy()
            self.affine[1, -1] -= img_shift
            self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

        if filename:
            Publisher.sendMessage('Update status text in GUI', label=_("Busy"))
            try:
                self.trekker = Trekker.initialize(filename.encode('utf-8'))
                self.trekker, n_threads = dti.set_trekker_parameters(self.trekker, self.trekker_cfg)

                self.checktracts.Enable(1)
                self.checktracts.SetValue(True)
                self.view_tracts = True

                Publisher.sendMessage('Update Trekker object', data=self.trekker)
                Publisher.sendMessage('Update number of threads', data=n_threads)
                Publisher.sendMessage('Update tracts visualization', data=1)
                Publisher.sendMessage('Update status text in GUI', label=_("Trekker initialized"))
                # except:
                #     wx.MessageBox(_("Unable to initialize Trekker, check FOD and config files."), _("InVesalius 3"))
            except:
                Publisher.sendMessage('Update status text in GUI', label=_("Trekker initialization failed."))
                wx.MessageBox(_("Unable to load FOD."), _("InVesalius 3"))

        Publisher.sendMessage('End busy cursor')

    def OnLoadACT(self, event=None):
        if self.trekker:
            Publisher.sendMessage('Begin busy cursor')
            filename = dlg.ShowImportOtherFilesDialog(const.ID_NIFTI_IMPORT, msg=_("Import anatomical labels"))
            # Baran
            # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
            # act_path = 'Baran_trekkerACTlabels_inFODspace.nii'
            # filename = os.path.join(data_dir, act_path)

            if not self.affine_vtk:
                slic = sl.Slice()
                prj_data = prj.Project()
                matrix_shape = tuple(prj_data.matrix_shape)
                spacing = tuple(prj_data.spacing)
                img_shift = spacing[1] * (matrix_shape[1] - 1)
                self.affine = slic.affine.copy()
                self.affine[1, -1] -= img_shift
                self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

            try:
                Publisher.sendMessage('Update status text in GUI', label=_("Busy"))
                if filename:
                    act_data = nb.squeeze_image(nb.load(filename))
                    act_data = nb.as_closest_canonical(act_data)
                    act_data.update_header()
                    act_data_arr = act_data.get_fdata()

                    self.checkACT.Enable(1)
                    self.checkACT.SetValue(True)

                    # ACT rules should be as follows:
                    self.trekker.pathway_stop_at_entry(filename.encode('utf-8'), -1)  # outside
                    self.trekker.pathway_discard_if_ends_inside(filename.encode('utf-8'), 1)  # wm
                    self.trekker.pathway_discard_if_enters(filename.encode('utf-8'), 0)  # csf

                    Publisher.sendMessage('Update ACT data', data=act_data_arr)
                    Publisher.sendMessage('Enable ACT', data=True)
                    Publisher.sendMessage('Update status text in GUI', label=_("Trekker ACT loaded"))
            except:
                Publisher.sendMessage('Update status text in GUI', label=_("ACT initialization failed."))
                wx.MessageBox(_("Unable to load ACT."), _("InVesalius 3"))

            Publisher.sendMessage('End busy cursor')
        else:
            wx.MessageBox(_("Load FOD image before the ACT."), _("InVesalius 3"))

    def OnLoadParameters(self, event=None):
        import json
        filename = dlg.ShowLoadSaveDialog(message=_(u"Load Trekker configuration"),
                                          wildcard=_("JSON file (*.json)|*.json"))
        try:
            # Check if filename exists, read the JSON file and check if all parameters match
            # with the required list defined in the constants module
            # if a parameter is missing, raise an error
            if filename:
                with open(filename) as json_file:
                    self.trekker_cfg = json.load(json_file)
                assert all(name in self.trekker_cfg for name in const.TREKKER_CONFIG)
                if self.trekker:
                    self.trekker, n_threads = dti.set_trekker_parameters(self.trekker, self.trekker_cfg)
                    Publisher.sendMessage('Update Trekker object', data=self.trekker)
                    Publisher.sendMessage('Update number of threads', data=n_threads)

                Publisher.sendMessage('Update status text in GUI', label=_("Trekker config loaded"))

        except (AssertionError, json.decoder.JSONDecodeError):
            # Inform user that file is not compatible
            self.trekker_cfg = const.TREKKER_CONFIG
            wx.MessageBox(_("File incompatible, using default configuration."), _("InVesalius 3"))
            Publisher.sendMessage('Update status text in GUI', label="")

    def OnUpdateTracts(self, position):
        """
        Minimal working version of tract computation. Updates when cross sends Pubsub message to update.
        Position refers to the coordinates in InVesalius 2D space. To represent the same coordinates in the 3D space,
        flip_x the coordinates and multiply the z coordinate by -1. This is all done in the flix_x function.

        :param arg: event for pubsub
        :param position: list or array with the x, y, and z coordinates in InVesalius space
        """
        # Minimal working version of tract computation
        # It updates when cross updates
        # pass
        if self.view_tracts and not self.nav_status:
            # print("Running during navigation")
            coord_flip = list(position[:3])
            coord_flip[1] = -coord_flip[1]
            dti.compute_and_visualize_tracts(self.trekker, coord_flip, self.affine, self.affine_vtk,
                                             self.n_tracts)

    def OnCloseProject(self):
        self.trekker = None
        self.trekker_cfg = const.TREKKER_CONFIG

        self.checktracts.SetValue(False)
        self.checktracts.Enable(0)
        self.checkpeeling.SetValue(False)
        self.checkpeeling.Enable(0)
        self.checkACT.SetValue(False)
        self.checkACT.Enable(0)

        self.spin_opacity.SetValue(const.BRAIN_OPACITY)
        self.spin_opacity.Enable(0)
        Publisher.sendMessage('Update peel', flag=False, actor=self.brain_actor)

        self.peel_depth = const.PEEL_DEPTH
        self.n_tracts = const.N_TRACTS

        Publisher.sendMessage('Remove tracts')


class SessionPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)
        
        # session count spinner
        self.__spin_session = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        self.__spin_session.SetRange(1, 99)
        self.__spin_session.SetValue(1)

        self.__spin_session.Bind(wx.EVT_TEXT, self.OnSessionChanged)
        self.__spin_session.Bind(wx.EVT_SPINCTRL, self.OnSessionChanged)
                
        sizer_create = wx.FlexGridSizer(rows=1, cols=1, hgap=5, vgap=5)
        sizer_create.AddMany([(self.__spin_session, 1)])

    def OnSessionChanged(self, evt):
        Publisher.sendMessage('Current session changed', new_session_id=self.__spin_session.GetValue())
        

class InputAttributes(object):
    # taken from https://stackoverflow.com/questions/2466191/set-attributes-from-dictionary-in-python
    def __init__(self, *initial_data, **kwargs):
        for dictionary in initial_data:
            for key in dictionary:
                setattr(self, key, dictionary[key])
        for key in kwargs:
            setattr(self, key, kwargs[key])
