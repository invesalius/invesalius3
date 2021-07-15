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

from functools import partial
import csv
import os
import queue
import sys
import threading

import nibabel as nb
import numpy as np
try:
    import Trekker
    has_trekker = True
except ImportError:
    has_trekker = False
import wx

try:
    import wx.lib.agw.hyperlink as hl
    import wx.lib.agw.foldpanelbar as fpb
except ImportError:
    import wx.lib.hyperlink as hl
    import wx.lib.foldpanelbar as fpb

import wx.lib.colourselect as csel
import wx.lib.masked.numctrl
from pubsub import pub as Publisher
from time import sleep

import invesalius.constants as const
import invesalius.data.bases as db

if has_trekker:
    import invesalius.data.brainmesh_handler as brain

import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.slice_ as sl
import invesalius.data.trackers as dt
import invesalius.data.tractography as dti
import invesalius.data.transformations as tr
import invesalius.data.trigger as trig
import invesalius.data.record_coords as rec
import invesalius.data.vtk_utils as vtk_utils
import invesalius.gui.dialogs as dlg
import invesalius.project as prj
from invesalius import utils

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
                                      (10, 310), 0, fpb.FPB_SINGLE_FOLD)
        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Navigation panel
        item = fold_panel.AddFoldPanel(_("Neuronavigation"), collapsed=True)
        ntw = NeuronavigationPanel(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, spacing=0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        # Fold 2 - Object registration panel
        item = fold_panel.AddFoldPanel(_("Object registration"), collapsed=True)
        otw = ObjectRegistrationPanel(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, otw, spacing=0,
                                      leftSpacing=0, rightSpacing=0)

        # Fold 3 - Markers panel
        item = fold_panel.AddFoldPanel(_("Markers"), collapsed=True)
        mtw = MarkersPanel(item)

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

        # Check box for camera update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Update camera in volume"))
        checkcamera = wx.CheckBox(self, -1, _('Vol. camera'))
        checkcamera.SetToolTip(tooltip)
        checkcamera.SetValue(const.CAM_MODE)
        checkcamera.Bind(wx.EVT_CHECKBOX, self.OnVolumeCamera)
        self.checkcamera = checkcamera

        # Check box for trigger monitoring to create markers from serial port
        tooltip = wx.ToolTip(_("Enable external trigger for creating markers"))
        checktrigger = wx.CheckBox(self, -1, _('Ext. trigger'))
        checktrigger.SetToolTip(tooltip)
        checktrigger.SetValue(False)
        checktrigger.Bind(wx.EVT_CHECKBOX, partial(self.OnExternalTrigger, ctrl=checktrigger))
        self.checktrigger = checktrigger

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
        checktrigger.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        checkobj.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(checkcamera, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Add(checktrigger, 0, wx.ALIGN_CENTER)
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
        Publisher.subscribe(self.OnShowDbs, "Active dbs folder")
        Publisher.subscribe(self.OnHideDbs, "Deactive dbs folder")

    def OnShowDbs(self):
        self.dbs_item.Show()

    def OnHideDbs(self):
        self.dbs_item.Hide()

    def OnCheckStatus(self, nav_status, vis_status):
        if nav_status:
            self.checktrigger.Enable(False)
            self.checkobj.Enable(False)
        else:
            self.checktrigger.Enable(True)
            if self.track_obj:
                self.checkobj.Enable(True)

    def OnExternalTrigger(self, evt, ctrl):
        Publisher.sendMessage('Update trigger state', trigger_state=ctrl.GetValue())

    def OnShowObject(self, evt=None, flag=None, obj_name=None, polydata=None):
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


class NeuronavigationPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.__bind_events()

        # Initialize global variables
        self.fiducials = np.full([6, 3], np.nan)
        self.fiducials_raw = np.zeros((6, 6))
        self.correg = None
        self.current_coord = 0, 0, 0
        self.trk_init = None
        self.nav_status = False
        self.trigger = None
        self.trigger_state = False
        self.obj_reg = None
        self.obj_reg_status = False
        self.track_obj = False
        self.m_icp = None
        self.fre = None
        self.icp_fre = None
        self.icp = False
        self.event = threading.Event()

        self.coord_queue = QueueCustom(maxsize=1)
        self.icp_queue = QueueCustom(maxsize=1)
        # self.visualization_queue = QueueCustom(maxsize=1)
        self.trigger_queue = QueueCustom(maxsize=1)
        self.coord_tracts_queue = QueueCustom(maxsize=1)
        self.tracts_queue = QueueCustom(maxsize=1)

        # Tractography parameters
        self.trk_inp = None
        self.trekker = None
        self.n_threads = None
        self.view_tracts = False
        self.enable_act = False
        self.act_data = None
        self.n_tracts = const.N_TRACTS
        self.seed_offset = const.SEED_OFFSET
        self.seed_radius = const.SEED_RADIUS
        self.sleep_nav = const.SLEEP_NAVIGATION

        self.tracker_id = const.DEFAULT_TRACKER
        self.ref_mode_id = const.DEFAULT_REF_MODE

        # Initialize list of buttons and numctrls for wx objects
        self.btns_coord = [None, None, None, None, None, None]
        self.numctrls_coord = [[], [], [], [], [], []]

        # ComboBox for spatial tracker device selection
        tooltip = wx.ToolTip(_("Choose the tracking device"))
        choice_trck = wx.ComboBox(self, -1, "",
                                  choices=const.TRACKER, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_trck.SetToolTip(tooltip)
        choice_trck.SetSelection(const.DEFAULT_TRACKER)
        choice_trck.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceTracker, ctrl=choice_trck))
        self.choice_trck = choice_trck

        # ComboBox for tracker reference mode
        tooltip = wx.ToolTip(_("Choose the navigation reference mode"))
        choice_ref = wx.ComboBox(self, -1, "",
                                 choices=const.REF_MODE, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_ref.SetSelection(const.DEFAULT_REF_MODE)
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceRefMode, ctrl=choice_trck))

        # Toggle buttons for image fiducials
        btns_img = const.BTNS_IMG
        tips_img = const.TIPS_IMG

        for k in btns_img:
            n = list(btns_img[k].keys())[0]
            lab = list(btns_img[k].values())[0]
            self.btns_coord[n] = wx.ToggleButton(self, k, label=lab, size=wx.Size(45, 23))
            self.btns_coord[n].SetToolTip(wx.ToolTip(tips_img[n]))
            self.btns_coord[n].Bind(wx.EVT_TOGGLEBUTTON, self.OnImageFiducials)

        # Push buttons for tracker fiducials
        btns_trk = const.BTNS_TRK
        tips_trk = const.TIPS_TRK

        for k in btns_trk:
            n = list(btns_trk[k].keys())[0]
            lab = list(btns_trk[k].values())[0]
            self.btns_coord[n] = wx.Button(self, k, label=lab, size=wx.Size(45, 23))
            self.btns_coord[n].SetToolTip(wx.ToolTip(tips_trk[n-3]))
            self.btns_coord[n].Bind(wx.EVT_BUTTON, self.OnTrackerFiducials)

        # TODO: Find a better allignment between FRE, text and navigate button
        txt_fre = wx.StaticText(self, -1, _('FRE:'))
        txt_icp = wx.StaticText(self, -1, _('Refine:'))

        # Fiducial registration error text box
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
        btn_nav.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnNavigate, btn=(btn_nav, choice_trck, choice_ref)))

        tooltip = wx.ToolTip(_(u"Refine the coregistration"))
        checkicp = wx.CheckBox(self, -1, _(' '))
        checkicp.SetValue(False)
        checkicp.Enable(False)
        checkicp.Bind(wx.EVT_CHECKBOX, partial(self.Oncheckicp, ctrl=checkicp))
        checkicp.SetToolTip(tooltip)
        self.checkicp = checkicp

        # Image and tracker coordinates number controls
        for m in range(len(self.btns_coord)):
            for n in range(3):
                self.numctrls_coord[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1))

        # Sizer to group all GUI objects
        choice_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        choice_sizer.AddMany([(choice_trck, wx.LEFT),
                              (choice_ref, wx.RIGHT)])

        coord_sizer = wx.GridBagSizer(hgap=5, vgap=5)

        for m in range(len(self.btns_coord)):
            coord_sizer.Add(self.btns_coord[m], pos=wx.GBPosition(m, 0))
            for n in range(3):
                coord_sizer.Add(self.numctrls_coord[m][n], pos=wx.GBPosition(m, n+1))
                if m in range(1, 6):
                    self.numctrls_coord[m][n].SetEditable(False)

        nav_sizer = wx.FlexGridSizer(rows=1, cols=5, hgap=5, vgap=5)
        nav_sizer.AddMany([(txt_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (txtctrl_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (btn_nav, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (txt_icp, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (checkicp, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)])

        group_sizer = wx.FlexGridSizer(rows=9, cols=1, hgap=5, vgap=5)
        group_sizer.AddGrowableCol(0, 1)
        group_sizer.AddGrowableRow(0, 1)
        group_sizer.AddGrowableRow(1, 1)
        group_sizer.AddGrowableRow(2, 1)
        group_sizer.SetFlexibleDirection(wx.BOTH)
        group_sizer.AddMany([(choice_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                             (coord_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                             (nav_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)])

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(group_sizer, 1)# wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

    def __bind_events(self):
        Publisher.subscribe(self.LoadImageFiducials, 'Load image fiducials')
        Publisher.subscribe(self.UpdateTriggerState, 'Update trigger state')
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
        Publisher.subscribe(self.EnableACT, 'Enable ACT')
        Publisher.subscribe(self.UpdateACTData, 'Update ACT data')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateTarget, 'Update target')

    def LoadImageFiducials(self, marker_id, coord):
        for n in const.BTNS_IMG_MKS:
            btn_id = list(const.BTNS_IMG_MKS[n].keys())[0]
            fid_id = list(const.BTNS_IMG_MKS[n].values())[0]
            if marker_id == fid_id and not self.btns_coord[btn_id].GetValue():
                self.btns_coord[btn_id].SetValue(True)
                self.fiducials[btn_id, :] = coord[0:3]
                for m in [0, 1, 2]:
                    self.numctrls_coord[btn_id][m].SetValue(coord[m])

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        if nav_status and (self.m_icp is not None):
            self.checkicp.Enable(True)
        else:
            self.checkicp.Enable(False)
            #self.checkicp.SetValue(False)

    def UpdateFRE(self, fre):
        # TODO: Exhibit FRE in a warning dialog and only starts navigation after user clicks ok
        self.txtctrl_fre.SetValue(str(round(fre, 2)))
        if fre <= 3:
            self.txtctrl_fre.SetBackgroundColour('GREEN')
        else:
            self.txtctrl_fre.SetBackgroundColour('RED')

    def UpdateTrekkerObject(self, data):
        # self.trk_inp = data
        self.trekker = data

    def UpdateNumTracts(self, data):
        self.n_tracts = data

    def UpdateSeedOffset(self, data):
        self.seed_offset = data

    def UpdateSeedRadius(self, data):
        self.seed_radius = data

    def UpdateSleep(self, data):
        self.sleep_nav = data

    def UpdateNumberThreads(self, data):
        self.n_threads = data

    def UpdateTractsVisualization(self, data):
        self.view_tracts = data

    def UpdateACTData(self, data):
        self.act_data = data

    def UpdateTarget(self, coord):
        self.target = coord

    def EnableACT(self, data):
        self.enable_act = data

    def UpdateImageCoordinates(self, position):
        # TODO: Change from world coordinates to matrix coordinates. They are better for multi software communication.
        self.current_coord = position
        for m in [0, 1, 2]:
            if not self.btns_coord[m].GetValue():
                for n in [0, 1, 2]:
                    self.numctrls_coord[m][n].SetValue(float(self.current_coord[n]))

    def UpdateObjectRegistration(self, data=None):
        if data:
            self.obj_reg = data
            self.obj_reg_status = True
        else:
            self.obj_reg = None
            self.obj_reg_status = False

    def UpdateTrackObjectState(self, evt=None, flag=None, obj_name=None, polydata=None):
        self.track_obj = flag

    def UpdateTriggerState(self, trigger_state):
        self.trigger_state = trigger_state

    def OnDisconnectTracker(self):
        if self.tracker_id:
            dt.TrackerConnection(self.tracker_id, self.trk_init[0], 'disconnect')

    def OnChoiceTracker(self, evt, ctrl):
        Publisher.sendMessage('Update status text in GUI',
                              label=_("Configuring tracker ..."))
        if hasattr(evt, 'GetSelection'):
            choice = evt.GetSelection()
        else:
            choice = const.DISCTRACK

        if self.trk_init:
            trck = self.trk_init[0]
        else:
            trck = None

        # Conditions check if click was on current selection and if any other tracker
        # has been initialized before
        if trck and choice != const.DISCTRACK:
            self.ResetTrackerFiducials()
            Publisher.sendMessage('Update status text in GUI',
                                  label=_("Disconnecting tracker..."))
            Publisher.sendMessage('Remove sensors ID')
            self.trk_init = dt.TrackerConnection(self.tracker_id, trck, 'disconnect')
            Publisher.sendMessage('Remove object data')
            self.tracker_id = choice
            if not self.trk_init[0] and choice:
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Tracker disconnected successfully"))
                self.trk_init = dt.TrackerConnection(self.tracker_id, None, 'connect')
                if not self.trk_init[0]:
                    dlg.ShowNavigationTrackerWarning(self.tracker_id, self.trk_init[1])
                    ctrl.SetSelection(0)
                    print("Tracker not connected!")
                else:
                    ctrl.SetSelection(self.tracker_id)
                    print("Tracker connected!")
        elif choice == const.DISCTRACK:
            if trck:
                self.ResetTrackerFiducials()
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Disconnecting tracker ..."))
                Publisher.sendMessage('Remove sensors ID')
                Publisher.sendMessage('Remove object data')
                self.trk_init = dt.TrackerConnection(self.tracker_id, trck, 'disconnect')
                if not self.trk_init[0]:
                    if evt is not False:
                        dlg.ShowNavigationTrackerWarning(self.tracker_id, 'disconnect')
                    self.tracker_id = 0
                    ctrl.SetSelection(self.tracker_id)
                    Publisher.sendMessage('Update status text in GUI',
                                          label=_("Tracker disconnected"))
                    print("Tracker disconnected!")
                else:
                    Publisher.sendMessage('Update status text in GUI',
                                          label=_("Tracker still connected"))
                    print("Tracker still connected!")
            else:
                ctrl.SetSelection(self.tracker_id)

        else:
            # If trk_init is None try to connect. If doesn't succeed show dialog.
            if choice:
                self.tracker_id = choice
                self.trk_init = dt.TrackerConnection(self.tracker_id, None, 'connect')
                if not self.trk_init[0]:
                    dlg.ShowNavigationTrackerWarning(self.tracker_id, self.trk_init[1])
                    self.tracker_id = 0
                    ctrl.SetSelection(self.tracker_id)

        Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
        Publisher.sendMessage('Update tracker initializer',
                              nav_prop=(self.tracker_id, self.trk_init, self.ref_mode_id))

    def OnChoiceRefMode(self, evt, ctrl):
        # When ref mode is changed the tracker coordinates are set to zero
        self.ref_mode_id = evt.GetSelection()
        self.ResetTrackerFiducials()
        # Some trackers do not accept restarting within this time window
        # TODO: Improve the restarting of trackers after changing reference mode
        # self.OnChoiceTracker(None, ctrl)
        Publisher.sendMessage('Update tracker initializer',
                              nav_prop=(self.tracker_id, self.trk_init, self.ref_mode_id))
        print("Reference mode changed!")

    def OnImageFiducials(self, evt):
        btn_id = list(const.BTNS_IMG_MKS[evt.GetId()].keys())[0]
        marker_id = list(const.BTNS_IMG_MKS[evt.GetId()].values())[0]

        if self.btns_coord[btn_id].GetValue():
            coord = self.numctrls_coord[btn_id][0].GetValue(),\
                    self.numctrls_coord[btn_id][1].GetValue(),\
                    self.numctrls_coord[btn_id][2].GetValue(), 0, 0, 0

            self.fiducials[btn_id, :] = coord[0:3]
            Publisher.sendMessage('Create marker', coord=coord, marker_id=marker_id)
        else:
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(float(self.current_coord[n]))

            self.fiducials[btn_id, :] = np.nan
            Publisher.sendMessage('Delete fiducial marker', marker_id=marker_id)

    def OnTrackerFiducials(self, evt):
        btn_id = list(const.BTNS_TRK[evt.GetId()].keys())[0]
        coord = None

        if self.trk_init and self.tracker_id:
            # if self.tracker_id == const.DEBUGTRACK:
            #     if btn_id == 3:
            #         coord1 = np.array([-120., 0., 0., 0., 0., 0.])
            #     elif btn_id == 4:
            #         coord1 = np.array([120., 0., 0., 0., 0., 0.])
            #     elif btn_id == 5:
            #         coord1 = np.array([0., 120., 0., 0., 0., 0.])
            #     coord2 = np.zeros([3, 6])
            #     coord_raw = np.vstack([coord1, coord2])
            # else:
            coord_raw = dco.GetCoordinates(self.trk_init, self.tracker_id, self.ref_mode_id)

            if self.ref_mode_id:
                coord = dco.dynamic_reference_m(coord_raw[0, :], coord_raw[1, :])
            else:
                coord = coord_raw[0, :]
                coord[2] = -coord[2]

        else:
            dlg.ShowNavigationTrackerWarning(0, 'choose')

        # Update number controls with tracker coordinates
        if coord is not None:
            self.fiducials[btn_id, :] = coord[0:3]
            if btn_id == 3:
                self.fiducials_raw[0, :] = coord_raw[0, :]
                self.fiducials_raw[1, :] = coord_raw[1, :]
            elif btn_id == 4:
                self.fiducials_raw[2, :] = coord_raw[0, :]
                self.fiducials_raw[3, :] = coord_raw[1, :]
            else:
                self.fiducials_raw[4, :] = coord_raw[0, :]
                self.fiducials_raw[5, :] = coord_raw[1, :]

            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(float(coord[n]))

    def OnICP(self):
        dialog = dlg.ICPCorregistrationDialog(nav_prop=(self.tracker_id, self.trk_init, self.ref_mode_id))
        if dialog.ShowModal() == wx.ID_OK:
            self.m_icp, point_coord, transformed_points, prev_error, final_error = dialog.GetValue()
            #TODO: checkbox in the dialog to transfer the icp points to 3D viewer
            #create markers
            # for i in range(len(point_coord)):
            #     img_coord = point_coord[i][0],-point_coord[i][1],point_coord[i][2], 0, 0, 0
            #     transf_coord = transformed_points[i][0],-transformed_points[i][1],transformed_points[i][2], 0, 0, 0
            #     Publisher.sendMessage('Create marker', coord=img_coord, marker_id=None, colour=(1,0,0))
            #     Publisher.sendMessage('Create marker',  coord=transf_coord, marker_id=None, colour=(0,0,1))
            if self.m_icp is not None:
                dlg.ReportICPerror(prev_error, final_error)
                self.checkicp.Enable(True)
                self.checkicp.SetValue(True)
                self.icp = True
            else:
                self.checkicp.Enable(False)
                self.checkicp.SetValue(False)
                self.icp = False

        return self.m_icp

    def Oncheckicp(self, evt, ctrl):
        if ctrl.GetValue() and evt and (self.m_icp is not None):
            self.icp = True
        else:
            self.icp = False
        self.ctrl_icp()

    def ctrl_icp(self):
        if self.icp:
            self.UpdateFRE(self.icp_fre)
        else:
            self.UpdateFRE(self.fre)
        self.icp_queue.put_nowait([self.icp, self.m_icp])
        #print(self.icp, self.m_icp)

    def OnNavigate(self, evt, btn):
        btn_nav = btn[0]
        choice_trck = btn[1]
        choice_ref = btn[2]
        errors = False

        # initialize jobs list
        jobs_list = []
        vis_components = [self.trigger_state, self.view_tracts]
        vis_queues = [self.coord_queue, self.trigger_queue, self.tracts_queue, self.icp_queue]

        nav_id = btn_nav.GetValue()
        if not nav_id:
            self.event.set()

            # print("coord unfinished: {}, queue {}", self.coord_queue.unfinished_tasks, self.coord_queue.qsize())
            # print("coord_tracts unfinished: {}, queue {}", self.coord_tracts_queue.unfinished_tasks, self.coord_tracts_queue.qsize())
            # print("tracts unfinished: {}, queue {}", self.tracts_queue.unfinished_tasks, self.tracts_queue.qsize())
            self.coord_queue.clear()
            # self.visualization_queue.clear()
            if self.trigger_state:
                self.trigger_queue.clear()
            if self.view_tracts:
                self.coord_tracts_queue.clear()
                self.tracts_queue.clear()

            # print("coord after unfinished: {}, queue {}", self.coord_queue.unfinished_tasks, self.coord_queue.qsize())
            # print("coord_tracts after unfinished: {}, queue {}", self.coord_tracts_queue.unfinished_tasks, self.coord_tracts_queue.qsize())
            # print("tracts after unfinished: {}, queue {}", self.tracts_queue.unfinished_tasks, self.tracts_queue.qsize())
            self.coord_queue.join()
            # self.visualization_queue.join()
            if self.trigger_state:
                self.trigger_queue.join()
            if self.view_tracts:
                self.coord_tracts_queue.join()
                self.tracts_queue.join()

            # print("coord join unfinished: {}, queue {}", self.coord_queue.unfinished_tasks, self.coord_queue.qsize())
            # print("vis join unfinished: {}, queue {}", self.visualization_queue.unfinished_tasks, self.visualization_queue.qsize())

            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn_nav.SetToolTip(tooltip)

            # Enable all navigation buttons
            choice_ref.Enable(True)
            choice_trck.Enable(True)
            for btn_c in self.btns_coord:
                btn_c.Enable(True)

            # if self.trigger_state:
            #     self.trigger.stop()

            Publisher.sendMessage("Navigation status", nav_status=False, vis_status=vis_components)

        else:

            if np.isnan(self.fiducials).any():
                wx.MessageBox(_("Invalid fiducials, select all coordinates."), _("InVesalius 3"))
                btn_nav.SetValue(False)

            elif not self.trk_init[0] or not self.tracker_id:
                dlg.ShowNavigationTrackerWarning(0, 'choose')
                errors = True

            else:
                if self.event.is_set():
                    self.event.clear()

                # prepare GUI for navigation
                Publisher.sendMessage("Navigation status", nav_status=True, vis_status=vis_components)
                Publisher.sendMessage("Toggle Cross", id=const.SLICE_STATE_CROSS)
                Publisher.sendMessage("Hide current mask")
                tooltip = wx.ToolTip(_("Stop neuronavigation"))
                btn_nav.SetToolTip(tooltip)

                # disable all navigation buttons
                choice_ref.Enable(False)
                choice_trck.Enable(False)
                for btn_c in self.btns_coord:
                    btn_c.Enable(False)

                # fiducials matrix
                m_change = tr.affine_matrix_from_points(self.fiducials[3:, :].T, self.fiducials[:3, :].T,
                                                        shear=False, scale=False)
                # initialize spatial tracker parameters
                tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id

                # compute fiducial registration error (FRE)
                if not self.icp_fre:
                    self.fre = db.calculate_fre(self.fiducials_raw, self.fiducials, self.ref_mode_id, m_change)
                    self.UpdateFRE(self.fre)

                if self.track_obj:
                    # if object tracking is selected
                    if not self.obj_reg_status:
                        # check if object registration was performed
                        wx.MessageBox(_("Perform coil registration before navigation."), _("InVesalius 3"))
                        errors = True
                    else:
                        # if object registration was correctly performed continue with navigation
                        # obj_reg[0] is object 3x3 fiducial matrix and obj_reg[1] is 3x3 orientation matrix
                        obj_fiducials, obj_orients, obj_ref_mode, obj_name = self.obj_reg

                        coreg_data = [m_change, obj_ref_mode]

                        if self.ref_mode_id:
                            coord_raw = dco.GetCoordinates(self.trk_init, self.tracker_id, self.ref_mode_id)
                        else:
                            coord_raw = np.array([None])

                        obj_data = db.object_registration(obj_fiducials, obj_orients, coord_raw, m_change)
                        coreg_data.extend(obj_data)

                        queues = [self.coord_queue, self.coord_tracts_queue, self.icp_queue]
                        jobs_list.append(dcr.CoordinateCorregistrate(self.ref_mode_id, tracker_mode, coreg_data,
                                                                     self.view_tracts, queues,
                                                                     self.event, self.sleep_nav, self.tracker_id,
                                                                     self.target))
                else:
                    coreg_data = (m_change, 0)
                    queues = [self.coord_queue, self.coord_tracts_queue, self.icp_queue]
                    jobs_list.append(dcr.CoordinateCorregistrateNoObject(self.ref_mode_id, tracker_mode, coreg_data,
                                                                         self.view_tracts, queues,
                                                                         self.event, self.sleep_nav))

                if not errors:
                    #TODO: Test the trigger thread
                    if self.trigger_state:
                        # self.trigger = trig.Trigger(nav_id)
                        jobs_list.append(trig.TriggerNew(self.trigger_queue, self.event, self.sleep_nav))

                    if self.view_tracts:
                        # initialize Trekker parameters
                        slic = sl.Slice()
                        prj_data = prj.Project()
                        matrix_shape = tuple(prj_data.matrix_shape)
                        affine = slic.affine.copy()
                        affine[1, -1] -= matrix_shape[1]
                        affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(affine)
                        Publisher.sendMessage("Update marker offset state", create=True)
                        self.trk_inp = self.trekker, affine, self.seed_offset, self.n_tracts, self.seed_radius,\
                                       self.n_threads, self.act_data, affine_vtk, matrix_shape[1]
                        # print("Appending the tract computation thread!")
                        queues = [self.coord_tracts_queue, self.tracts_queue]
                        if self.enable_act:
                            jobs_list.append(dti.ComputeTractsACTThread(self.trk_inp, queues, self.event, self.sleep_nav))
                        else:
                            jobs_list.append(dti.ComputeTractsThread(self.trk_inp, queues, self.event, self.sleep_nav))

                    jobs_list.append(UpdateNavigationScene(vis_queues, vis_components,
                                                           self.event, self.sleep_nav))

                    for jobs in jobs_list:
                        # jobs.daemon = True
                        jobs.start()
                        # del jobs

                    if not self.checkicp.GetValue():
                        if dlg.ICPcorregistration(self.fre):
                            m_icp = self.OnICP()
                            self.icp_fre = db.calculate_fre(self.fiducials_raw, self.fiducials, self.ref_mode_id,
                                                            m_change, m_icp)
                            self.ctrl_icp()

    def ResetImageFiducials(self):
        for m in range(0, 3):
            self.btns_coord[m].SetValue(False)
            self.fiducials[m, :] = [np.nan, np.nan, np.nan]
            for n in range(0, 3):
                self.numctrls_coord[m][n].SetValue(0.0)

    def ResetTrackerFiducials(self):
        for m in range(3, 6):
            self.fiducials[m, :] = [np.nan, np.nan, np.nan]
            for n in range(0, 3):
                self.numctrls_coord[m][n].SetValue(0.0)

        self.txtctrl_fre.SetValue('')
        self.txtctrl_fre.SetBackgroundColour('WHITE')

    def ResetIcp(self):
        self.m_icp = None
        self.fre = None
        self.icp_fre = None
        self.icp = False
        self.checkicp.Enable(False)
        self.checkicp.SetValue(False)

    def OnCloseProject(self):
        self.ResetTrackerFiducials()
        self.ResetImageFiducials()
        self.ResetIcp()
        self.OnChoiceTracker(False, self.choice_trck)
        Publisher.sendMessage('Update object registration')
        Publisher.sendMessage('Update track object state', flag=False, obj_name=False)
        Publisher.sendMessage('Delete all markers')
        Publisher.sendMessage("Update marker offset state", create=False)
        Publisher.sendMessage("Remove tracts")
        Publisher.sendMessage("Set cross visibility", visibility=0)
        # TODO: Reset camera initial focus
        Publisher.sendMessage('Reset cam clipping range')


class ObjectRegistrationPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.coil_list = const.COIL

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
        btn_new.Bind(wx.EVT_BUTTON, self.OnLinkCreate)
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
        spin_size_angles = wx.SpinCtrl(self, -1, "", size=wx.Size(50, 23))
        spin_size_angles.SetRange(1, 99)
        spin_size_angles.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_angles.Bind(wx.EVT_TEXT, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))
        spin_size_angles.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))

        # Change dist threshold
        text_dist = wx.StaticText(self, -1, _("Distance threshold [mm]:"))
        spin_size_dist = wx.SpinCtrl(self, -1, "", size=wx.Size(50, 23))
        spin_size_dist.SetRange(1, 99)
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
        Publisher.subscribe(self.UpdateTrackerInit, 'Update tracker initializer')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.OnRemoveObject, 'Remove object data')

    def UpdateTrackerInit(self, nav_prop):
        self.nav_prop = nav_prop

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

    def OnLinkCreate(self, event=None):

        if self.nav_prop:
            dialog = dlg.ObjectCalibrationDialog(self.nav_prop)
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name, polydata = dialog.GetValue()
                    if np.isfinite(self.obj_fiducials).all() and np.isfinite(self.obj_orients).all():
                        self.checktrack.Enable(1)
                        Publisher.sendMessage('Update object registration',
                                              data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
                        Publisher.sendMessage('Update status text in GUI',
                                              label=_("Ready"))
                        # Enable automatically Track object, Show coil and disable Vol. Camera
                        self.checktrack.SetValue(True)
                        Publisher.sendMessage('Update track object state', flag=True, obj_name=self.obj_name, polydata=polydata)
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
                #TODO: Improve method to read the file, using "with" similar to OnLoadParameters
                data = np.loadtxt(filename, delimiter='\t')
                self.obj_fiducials = data[:, :3]
                self.obj_orients = data[:, 3:]

                text_file = open(filename, "r")
                header = text_file.readline().split('\t')
                text_file.close()

                self.obj_name = header[1]
                self.obj_ref_mode = int(header[-1])

                self.checktrack.Enable(1)
                self.checktrack.SetValue(True)
                Publisher.sendMessage('Update object registration',
                                      data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Object file successfully loaded"))
                Publisher.sendMessage('Update track object state', flag=True, obj_name=self.obj_name)
                Publisher.sendMessage('Change camera checkbox', status=False)
                # wx.MessageBox(_("Object file successfully loaded"), _("Load"))
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
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.__bind_events()

        self.current_coord = 0, 0, 0, 0, 0, 0
        self.current_angle = 0, 0, 0
        self.current_seed = 0, 0, 0
        self.list_coord = []
        self.marker_ind = 0
        self.tgt_flag = self.tgt_index = None
        self.nav_status = False

        self.marker_colour = const.MARKER_COLOUR
        self.marker_size = const.MARKER_SIZE

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
        btn_delete_single.Bind(wx.EVT_BUTTON, self.OnDeleteSingleMarker)

        btn_delete_all = wx.Button(self, -1, label=_('Delete all'), size=wx.Size(135, 23))
        btn_delete_all.Bind(wx.EVT_BUTTON, self.OnDeleteAllMarkers)

        sizer_delete = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        sizer_delete.AddMany([(btn_delete_single, 1, wx.RIGHT),
                              (btn_delete_all, 0, wx.LEFT)])

        # List of markers
        self.lc = wx.ListCtrl(self, -1, style=wx.LC_REPORT, size=wx.Size(0,120))
        self.lc.InsertColumn(0, '#')
        self.lc.InsertColumn(1, 'X')
        self.lc.InsertColumn(2, 'Y')
        self.lc.InsertColumn(3, 'Z')
        self.lc.InsertColumn(4, 'ID')
        self.lc.SetColumnWidth(0, 28)
        self.lc.SetColumnWidth(1, 50)
        self.lc.SetColumnWidth(2, 50)
        self.lc.SetColumnWidth(3, 50)
        self.lc.SetColumnWidth(4, 60)
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
        # Publisher.subscribe(self.UpdateCurrentCoord, 'Co-registered points')
        Publisher.subscribe(self.UpdateCurrentCoord, 'Set cross focal point')
        Publisher.subscribe(self.OnDeleteSingleMarker, 'Delete fiducial marker')
        Publisher.subscribe(self.OnDeleteAllMarkers, 'Delete all markers')
        Publisher.subscribe(self.OnCreateMarker, 'Create marker')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateSeedCoordinates, 'Update tracts')

    def UpdateCurrentCoord(self, position):
        self.current_coord = position
        #self.current_angle = pubsub_evt.data[1][3:]

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if not nav_status:
            sleep(0.5)
            #self.current_coord[3:] = 0, 0, 0
            self.nav_status = False
        else:
            self.nav_status = True

    def UpdateSeedCoordinates(self, root=None, affine_vtk=None, coord_offset=(0, 0, 0)):
        self.current_seed = coord_offset

    def OnMouseRightDown(self, evt):
        # TODO: Enable the "Set as target" only when target is created with registered object
        menu_id = wx.Menu()
        edit_id = menu_id.Append(0, _('Edit ID'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuEditMarkerId, edit_id)
        color_id = menu_id.Append(2, _('Edit color'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuSetColor, color_id)
        menu_id.AppendSeparator()
        target_menu = menu_id.Append(1, _('Set as target'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuSetTarget, target_menu)
        # TODO: Create the remove target option so the user can disable the target without removing the marker
        # target_menu_rem = menu_id.Append(3, _('Remove target'))
        # menu_id.Bind(wx.EVT_MENU, self.OnMenuRemoveTarget, target_menu_rem)

        target_menu.Enable(True)
        self.PopupMenu(menu_id)
        menu_id.Destroy()

    def OnItemBlink(self, evt):
        Publisher.sendMessage('Blink Marker', index=self.lc.GetFocusedItem())

    def OnStopItemBlink(self, evt):
        Publisher.sendMessage('Stop Blink Marker')

    def OnMenuEditMarkerId(self, evt):
        list_index = self.lc.GetFocusedItem()
        if evt == 'TARGET':
            id_label = evt
        else:
            id_label = dlg.ShowEnterMarkerID(self.lc.GetItemText(list_index, 4))
            if id_label == 'TARGET':
                id_label = ''
                wx.MessageBox(_("Invalid TARGET ID."), _("InVesalius 3"))
        self.lc.SetItem(list_index, 4, id_label)
        # Add the new ID to exported list
        if len(self.list_coord[list_index]) > 8:
            self.list_coord[list_index][10] = str(id_label)
        else:
            self.list_coord[list_index][7] = str(id_label)

    def OnMenuSetTarget(self, evt):
        if isinstance(evt, int):
            self.lc.Focus(evt)

        if self.tgt_flag:
            self.lc.SetItemBackgroundColour(self.tgt_index, 'white')
            Publisher.sendMessage('Set target transparency', status=False, index=self.tgt_index)
            self.lc.SetItem(self.tgt_index, 4, '')
            # Add the new ID to exported list
            if len(self.list_coord[self.tgt_index]) > 8:
                self.list_coord[self.tgt_index][10] = str('')
            else:
                self.list_coord[self.tgt_index][7] = str('')

        self.tgt_index = self.lc.GetFocusedItem()
        self.lc.SetItemBackgroundColour(self.tgt_index, 'RED')

        Publisher.sendMessage('Update target', coord=self.list_coord[self.tgt_index][:6])
        Publisher.sendMessage('Set target transparency', status=True, index=self.tgt_index)
        Publisher.sendMessage('Disable or enable coil tracker', status=True)
        self.OnMenuEditMarkerId('TARGET')
        self.tgt_flag = True
        wx.MessageBox(_("New target selected."), _("InVesalius 3"))

    def OnMenuSetColor(self, evt):
        index = self.lc.GetFocusedItem()

        color_current = [self.list_coord[index][n] * 255 for n in range(6, 9)]

        color_new = dlg.ShowColorDialog(color_current=color_current)

        if color_new:
            assert len(color_new) == 3
            for n, col in enumerate(color_new):
                self.list_coord[index][n+6] = col/255.0

            Publisher.sendMessage('Set new color', index=index, color=color_new)

    def OnDeleteAllMarkers(self, evt=None):
        if self.list_coord:
            if evt is None:
                result = wx.ID_OK
            else:
                # result = dlg.DeleteAllMarkers()
                result = dlg.ShowConfirmationDialog(msg=_("Remove all markers? Cannot be undone."))

            if result == wx.ID_OK:
                self.list_coord = []
                self.marker_ind = 0
                Publisher.sendMessage('Remove all markers', indexes=self.lc.GetItemCount())
                self.lc.DeleteAllItems()
                Publisher.sendMessage('Stop Blink Marker', index='DeleteAll')

                if self.tgt_flag:
                    self.tgt_flag = self.tgt_index = None
                    Publisher.sendMessage('Disable or enable coil tracker', status=False)
                    if not hasattr(evt, 'data'):
                        wx.MessageBox(_("Target deleted."), _("InVesalius 3"))

    def OnDeleteSingleMarker(self, evt=None, marker_id=None):
        # OnDeleteSingleMarker is used for both pubsub and button click events
        # Pubsub is used for fiducial handle and button click for all others

        if not evt:
            if self.lc.GetItemCount():
                for id_n in range(self.lc.GetItemCount()):
                    item = self.lc.GetItem(id_n, 4)
                    if item.GetText() == marker_id:
                        for i in const.BTNS_IMG_MKS:
                            if marker_id in list(const.BTNS_IMG_MKS[i].values())[0]:
                                self.lc.Focus(item.GetId())
                index = [self.lc.GetFocusedItem()]
        else:
            if self.lc.GetFirstSelected() is not -1:
                index = self.GetSelectedItems()
            else:
                index = None

        #TODO: There are bugs when no marker is selected, test and improve
        if index:
            if self.tgt_flag and self.tgt_index == index[0]:
                self.tgt_flag = self.tgt_index = None
                Publisher.sendMessage('Disable or enable coil tracker', status=False)
                wx.MessageBox(_("No data selected."), _("InVesalius 3"))

            self.DeleteMarker(index)
        else:
            wx.MessageBox(_("Target deleted."), _("InVesalius 3"))

    def DeleteMarker(self, index):
        for i in reversed(index):
            del self.list_coord[i]
            self.lc.DeleteItem(i)
            for n in range(0, self.lc.GetItemCount()):
                self.lc.SetItem(n, 0, str(n+1))
            self.marker_ind -= 1
        Publisher.sendMessage('Remove marker', index=index)

    def OnCreateMarker(self, evt=None, coord=None, marker_id=None, colour=None):
        # OnCreateMarker is used for both pubsub and button click events
        # Pubsub is used for markers created with fiducial buttons, trigger and create marker button
        if not colour:
            colour = self.marker_colour
        if not coord:
            coord = self.current_coord

        if evt is None:
            if coord:
                self.CreateMarker(coord=coord, colour=(0.0, 1.0, 0.0), size=self.marker_size,
                                  marker_id=marker_id, seed=self.current_seed)
            else:
                self.CreateMarker(coord=self.current_coord, colour=colour, size=self.marker_size,
                                  seed=self.current_seed)
        else:
            self.CreateMarker(coord=self.current_coord, colour=colour, size=self.marker_size,
                              seed=self.current_seed)

    def OnLoadMarkers(self, evt):
        filename = dlg.ShowLoadSaveDialog(message=_(u"Load markers"),
                                          wildcard=_("Markers files (*.mks)|*.mks"))
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # marker_path = 'markers.mks'
        # filename = os.path.join(data_dir, marker_path)

        if filename:
            try:
                count_line = self.lc.GetItemCount()
                # content = [s.rstrip() for s in open(filename)]
                with open(filename, 'r') as file:
                    reader = csv.reader(file, delimiter='\t')
                    content = [row for row in reader]

                for line in content:
                    target = None
                    # line = [s for s in data.split()]
                    if len(line) > 8:
                        coord = [float(s) for s in line[:6]]
                        colour = [float(s) for s in line[6:9]]
                        size = float(line[9])
                        # marker_id = line[10]
                        if len(line) > 11:
                            seed = [float(s) for s in line[11:14]]
                        else:
                            seed = 0., 0., 0.

                        # coord = float(line[0]), float(line[1]), float(line[2]), float(line[3]), float(line[4]), float(line[5])
                        # colour = float(line[6]), float(line[7]), float(line[8])
                        # size = float(line[9])

                        if len(line) >= 11:
                            for i in const.BTNS_IMG_MKS:
                                if line[10] in list(const.BTNS_IMG_MKS[i].values())[0]:
                                    Publisher.sendMessage('Load image fiducials', marker_id=line[10], coord=coord)
                                elif line[10] == 'TARGET':
                                    target = count_line
                        else:
                            line.append("")

                        self.CreateMarker(coord, colour, size, line[10], seed)
                        if target is not None:
                            self.OnMenuSetTarget(target)

                    else:
                        coord = float(line[0]), float(line[1]), float(line[2]), 0, 0, 0
                        colour = float(line[3]), float(line[4]), float(line[5])
                        size = float(line[6])

                        if len(line) == 8:
                            for i in const.BTNS_IMG_MKS:
                                if line[7] in list(const.BTNS_IMG_MKS[i].values())[0]:
                                    Publisher.sendMessage('Load image fiducials', marker_id=line[7], coord=coord)
                        else:
                            line.append("")
                        self.CreateMarker(coord, colour, size, line[7])
                    count_line += 1
            except:
                wx.MessageBox(_("Invalid markers file."), _("InVesalius 3"))

    def OnMarkersVisibility(self, evt, ctrl):

        if ctrl.GetValue():
            Publisher.sendMessage('Hide all markers',  indexes=self.lc.GetItemCount())
            ctrl.SetLabel('Show')
        else:
            Publisher.sendMessage('Show all markers',  indexes=self.lc.GetItemCount())
            ctrl.SetLabel('Hide')

    def OnSaveMarkers(self, evt):
        filename = dlg.ShowLoadSaveDialog(message=_(u"Save markers as..."),
                                          wildcard=_("Marker files (*.mks)|*.mks"),
                                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                          default_filename="markers.mks", save_ext="mks")

        if filename:
            if self.list_coord:
                with open(filename, 'w', newline='') as file:
                    writer = csv.writer(file, delimiter='\t')
                    writer.writerows(self.list_coord)
                # text_file = open(filename, "w")
                # list_slice1 = self.list_coord[0]
                # coord = str('%.3f' %self.list_coord[0][0]) + "\t" + str('%.3f' %self.list_coord[0][1]) + "\t" + str('%.3f' %self.list_coord[0][2])
                # angles = str('%.3f' %self.list_coord[0][3]) + "\t" + str('%.3f' %self.list_coord[0][4]) + "\t" + str('%.3f' %self.list_coord[0][5])
                # properties = str('%.3f' %list_slice1[6]) + "\t" + str('%.3f' %list_slice1[7]) + "\t" + str('%.3f' %list_slice1[8]) + "\t" + str('%.1f' %list_slice1[9]) + "\t" + list_slice1[10]
                # line = coord + "\t" + angles + "\t" + properties + "\n"
                # list_slice = self.list_coord[1:]
                #
                # for value in list_slice:
                #     coord = str('%.3f' %value[0]) + "\t" + str('%.3f' %value[1]) + "\t" + str('%.3f' %value[2])
                #     angles = str('%.3f' % value[3]) + "\t" + str('%.3f' % value[4]) + "\t" + str('%.3f' % value[5])
                #     properties = str('%.3f' %value[6]) + "\t" + str('%.3f' %value[7]) + "\t" + str('%.3f' %value[8]) + "\t" + str('%.1f' %value[9]) + "\t" + value[10]
                #     line = line + coord + "\t" + angles + "\t" +properties + "\n"
                #
                # text_file.writelines(line)
                # text_file.close()

    def OnSelectColour(self, evt, ctrl):
        self.marker_colour = [colour/255.0 for colour in ctrl.GetValue()]

    def OnSelectSize(self, evt, ctrl):
        self.marker_size = ctrl.GetValue()

    def CreateMarker(self, coord, colour, size, marker_id="x", seed=(0, 0, 0)):
        # TODO: Use matrix coordinates and not world coordinates as current method.
        # This makes easier for inter-software comprehension.

        Publisher.sendMessage('Add marker', ball_id=self.marker_ind, size=size, colour=colour,  coord=coord[0:3])

        self.marker_ind += 1

        # List of lists with coordinates and properties of a marker
        line = []
        line.extend(coord)
        line.extend(colour)
        line.append(size)
        line.append(marker_id)
        line.extend(seed)

        # line = [coord[0], coord[1], coord[2], coord[3], coord[4], coord[5], colour[0], colour[1], colour[2], size, marker_id]
        # line = [coord[0], coord[1], coord[2], coord[3], coord[4], coord[5],
        #         colour[0], colour[1], colour[2], size, marker_id,
        #         seed[0], seed[1], seed[2]]

        # Adding current line to a list of all markers already created
        if not self.list_coord:
            self.list_coord = [line]
        else:
            self.list_coord.append(line)

        # Add item to list control in panel
        num_items = self.lc.GetItemCount()
        self.lc.InsertItem(num_items, str(num_items + 1))
        self.lc.SetItem(num_items, 1, str(round(coord[0], 2)))
        self.lc.SetItem(num_items, 2, str(round(coord[1], 2)))
        self.lc.SetItem(num_items, 3, str(round(coord[2], 2)))
        self.lc.SetItem(num_items, 4, str(marker_id))
        self.lc.EnsureVisible(num_items)

    def GetSelectedItems(self):
        """    
        Returns a list of the selected items in the list control.
        """
        selection = []
        index = self.lc.GetFirstSelected()
        selection.append(index)
        while len(selection) != self.lc.GetSelectedItemCount():
            index = self.lc.GetNextSelected(index)
            selection.append(index)
        return selection

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

        self.affine = None
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
        self.target = None
        self.tracts_run = None
        self.trekker_cfg = const.TREKKER_CONFIG
        self.nav_status = False

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
        else:
            actor = None
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
        Publisher.sendMessage('Update status text in GUI', label=_("Busy"))
        Publisher.sendMessage('Begin busy cursor')
        mask_path = dlg.ShowImportOtherFilesDialog(const.ID_NIFTI_IMPORT, _("Import brain mask"))
        img_path = dlg.ShowImportOtherFilesDialog(const.ID_NIFTI_IMPORT, _("Import T1 anatomical image"))
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # mask_file = 'Baran_brain_mask.nii'
        # mask_path = os.path.join(data_dir, mask_file)
        # img_file = 'Baran_T1_inFODspace.nii'
        # img_path = os.path.join(data_dir, img_file)

        if not self.affine_vtk:
            slic = sl.Slice()
            prj_data = prj.Project()
            matrix_shape = tuple(prj_data.matrix_shape)
            self.affine = slic.affine.copy()
            self.affine[1, -1] -= matrix_shape[1]
            self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

        try:
            self.brain_peel = brain.Brain(img_path, mask_path, self.n_peels, self.affine_vtk)
            self.brain_actor = self.brain_peel.get_actor(self.peel_depth)
            self.brain_actor.GetProperty().SetOpacity(self.brain_opacity)
            Publisher.sendMessage('Update peel', flag=True, actor=self.brain_actor)
            self.checkpeeling.Enable(1)
            self.checkpeeling.SetValue(True)
            self.spin_opacity.Enable(1)
            Publisher.sendMessage('Update status text in GUI', label=_("Brain model loaded"))
        except:
            wx.MessageBox(_("Unable to load brain mask."), _("InVesalius 3"))

        Publisher.sendMessage('End busy cursor')

    def OnLinkFOD(self, event=None):
        Publisher.sendMessage('Update status text in GUI', label=_("Busy"))
        Publisher.sendMessage('Begin busy cursor')
        filename = dlg.ShowImportOtherFilesDialog(const.ID_NIFTI_IMPORT, msg=_("Import Trekker FOD"))
        # Juuso
        # data_dir = os.environ.get('OneDriveConsumer') + '\\data\\dti'
        # FOD_path = 'sub-P0_dwi_FOD.nii'
        # Baran
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # FOD_path = 'Baran_FOD.nii'
        # filename = os.path.join(data_dir, FOD_path)

        # if not self.affine_vtk:
        #     slic = sl.Slice()
        #     self.affine = slic.affine
        #     self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

        if not self.affine_vtk:
            slic = sl.Slice()
            prj_data = prj.Project()
            matrix_shape = tuple(prj_data.matrix_shape)
            self.affine = slic.affine.copy()
            self.affine[1, -1] -= matrix_shape[1]
            self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

        # try:

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

        Publisher.sendMessage('End busy cursor')

    def OnLoadACT(self, event=None):
        Publisher.sendMessage('Update status text in GUI', label=_("Busy"))
        Publisher.sendMessage('Begin busy cursor')
        filename = dlg.ShowImportOtherFilesDialog(const.ID_NIFTI_IMPORT, msg=_("Import anatomical labels"))
        # Baran
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # act_path = 'Baran_trekkerACTlabels_inFODspace.nii'
        # filename = os.path.join(data_dir, act_path)

        act_data = nb.squeeze_image(nb.load(filename))
        act_data = nb.as_closest_canonical(act_data)
        act_data.update_header()
        act_data_arr = act_data.get_fdata()

        if not self.affine_vtk:
            slic = sl.Slice()
            prj_data = prj.Project()
            matrix_shape = tuple(prj_data.matrix_shape)
            self.affine = slic.affine.copy()
            self.affine[1, -1] -= matrix_shape[1]
            self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

        self.checkACT.Enable(1)
        self.checkACT.SetValue(True)

        Publisher.sendMessage('Update ACT data', data=act_data_arr)
        Publisher.sendMessage('Enable ACT', data=True)
        # Publisher.sendMessage('Create grid', data=act_data_arr, affine=self.affine)
        # Publisher.sendMessage('Update number of threads', data=n_threads)
        # Publisher.sendMessage('Update tracts visualization', data=1)
        Publisher.sendMessage('Update status text in GUI', label=_("Trekker ACT loaded"))

        Publisher.sendMessage('End busy cursor')

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
            dti.compute_tracts(self.trekker, coord_flip, self.affine, self.affine_vtk,
                               self.n_tracts)

    def OnCloseProject(self):
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


class QueueCustom(queue.Queue):
    """
    A custom queue subclass that provides a :meth:`clear` method.
    https://stackoverflow.com/questions/6517953/clear-all-items-from-the-queue
    Modified to a LIFO Queue type (Last-in-first-out). Seems to make sense for the navigation
    threads, as the last added coordinate should be the first to be processed.
    In the first tests in a short run, seems to increase the coord queue size considerably,
    possibly limiting the queue size is good.
    """

    def clear(self):
        """
        Clears all items from the queue.
        """

        with self.mutex:
            unfinished = self.unfinished_tasks - len(self.queue)
            if unfinished <= 0:
                if unfinished < 0:
                    raise ValueError('task_done() called too many times')
                self.all_tasks_done.notify_all()
            self.unfinished_tasks = unfinished
            self.queue.clear()
            self.not_full.notify_all()


class UpdateNavigationScene(threading.Thread):

    def __init__(self, vis_queues, vis_components, event, sle):
        """Class (threading) to update the navigation scene with all graphical elements.

        Sleep function in run method is used to avoid blocking GUI and more fluent, real-time navigation

        :param affine_vtk: Affine matrix in vtkMatrix4x4 instance to update objects position in 3D scene
        :type affine_vtk: vtkMatrix4x4
        :param visualization_queue: Queue instance that manage coordinates to be visualized
        :type visualization_queue: queue.Queue
        :param event: Threading event to coordinate when tasks as done and allow UI release
        :type event: threading.Event
        :param sle: Sleep pause in seconds
        :type sle: float
        """

        threading.Thread.__init__(self, name='UpdateScene')
        self.trigger_state, self.view_tracts = vis_components
        self.coord_queue, self.trigger_queue, self.tracts_queue, self.icp_queue = vis_queues
        self.sle = sle
        self.event = event

    def run(self):
        # count = 0
        while not self.event.is_set():
            got_coords = False
            try:
                coord, m_img, view_obj = self.coord_queue.get_nowait()
                got_coords = True

                # print('UpdateScene: get {}'.format(count))

                # use of CallAfter is mandatory otherwise crashes the wx interface
                if self.view_tracts:
                    bundle, affine_vtk, coord_offset = self.tracts_queue.get_nowait()
                    #TODO: Check if possible to combine the Remove tracts with Update tracts in a single command
                    wx.CallAfter(Publisher.sendMessage, 'Remove tracts')
                    wx.CallAfter(Publisher.sendMessage, 'Update tracts', root=bundle,
                                 affine_vtk=affine_vtk, coord_offset=coord_offset)
                    # wx.CallAfter(Publisher.sendMessage, 'Update marker offset', coord_offset=coord_offset)
                    self.tracts_queue.task_done()

                if self.trigger_state:
                    trigger_on = self.trigger_queue.get_nowait()
                    if trigger_on:
                        wx.CallAfter(Publisher.sendMessage, 'Create marker')
                    self.trigger_queue.task_done()

                #TODO: If using the view_tracts substitute the raw coord from the offset coordinate, so the user
                # see the red cross in the position of the offset marker
                wx.CallAfter(Publisher.sendMessage, 'Update slices position', position=coord[:3])
                wx.CallAfter(Publisher.sendMessage, 'Set cross focal point', position=coord)
                wx.CallAfter(Publisher.sendMessage, 'Update slice viewer')

                if view_obj:
                    wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=coord)

                self.coord_queue.task_done()
                # print('UpdateScene: done {}'.format(count))
                # count += 1

                sleep(self.sle)
            except queue.Empty:
                if got_coords:
                    self.coord_queue.task_done()


class InputAttributes(object):
    # taken from https://stackoverflow.com/questions/2466191/set-attributes-from-dictionary-in-python
    def __init__(self, *initial_data, **kwargs):
        for dictionary in initial_data:
            for key in dictionary:
                setattr(self, key, dictionary[key])
        for key in kwargs:
            setattr(self, key, kwargs[key])
