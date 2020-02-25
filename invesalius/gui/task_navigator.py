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
import sys
import os
import psutil

import numpy as np
import wx

try:
    import wx.lib.agw.hyperlink as hl
    import wx.lib.agw.foldpanelbar as fpb
except ImportError:
    import wx.lib.hyperlink as hl
    import wx.lib.foldpanelbar as fpb

import wx.lib.masked.numctrl
from wx.lib.pubsub import pub as Publisher
import wx.lib.colourselect as csel
import wx.lib.platebtn as pbtn

from math import cos, sin, pi
from time import sleep, time

import invesalius.data.transformations as tr
import invesalius.constants as const
import invesalius.data.bases as db
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.trackers as dt
import invesalius.data.trigger as trig
import invesalius.data.record_coords as rec
import invesalius.gui.dialogs as dlg
from invesalius import utils

import invesalius.data.slice_ as sl
import invesalius.data.imagedata_utils as image_utils
import invesalius.reader.others_reader as oth
import vtk
import Trekker
import invesalius.data.brainmesh_handler as brain
import concurrent.futures
import queue
import threading

# import invesalius.data.trekker_nothread as dti
import invesalius.data.trekker_data as dti

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

        if sys.platform != 'win32':
            self.checkcamera.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
            checktrigger.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
            checkobj.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(checkcamera, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Add(checktrigger, 0, wx.ALIGN_CENTER)
        line_sizer.Add(checkobj, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.LEFT, 5)
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

    def OnCheckStatus(self, status):
        if status:
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
        self.correg = None
        self.current_coord = 0, 0, 0
        self.trk_init = None
        self.trigger = None
        self.trigger_state = False
        self.obj_reg = None
        self.obj_reg_status = False
        self.track_obj = False
        self.event = threading.Event()

        # Tractography parameters
        self.trk_inp = None
        self.trekker = None
        self.view_tracts = False
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

        nav_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        nav_sizer.AddMany([(txt_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (txtctrl_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                           (btn_nav, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)])

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
        main_sizer.Add(group_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

    def __bind_events(self):
        Publisher.subscribe(self.LoadImageFiducials, 'Load image fiducials')
        Publisher.subscribe(self.UpdateTriggerState, 'Update trigger state')
        Publisher.subscribe(self.UpdateTrackObjectState, 'Update track object state')
        Publisher.subscribe(self.UpdateImageCoordinates, 'Update cross position')
        # Publisher.subscribe(self.UpdateImageCoordinates, 'Set ball reference position')
        Publisher.subscribe(self.OnDisconnectTracker, 'Disconnect tracker')
        Publisher.subscribe(self.UpdateObjectRegistration, 'Update object registration')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.UpdateTrekkerObject, 'Update Trekker object')
        Publisher.subscribe(self.UpdateNumTracts, 'Update number of tracts')
        Publisher.subscribe(self.UpdateSeedOffset, 'Update seed offset')
        Publisher.subscribe(self.UpdateSeedRadius, 'Update seed radius')
        Publisher.subscribe(self.UpdateSleep, 'Update sleep')
        Publisher.subscribe(self.UpdateTractsVisualization, 'Update tracts visualization')

    def LoadImageFiducials(self, marker_id, coord):
        for n in const.BTNS_IMG_MKS:
            btn_id = list(const.BTNS_IMG_MKS[n].keys())[0]
            fid_id = list(const.BTNS_IMG_MKS[n].values())[0]
            if marker_id == fid_id and not self.btns_coord[btn_id].GetValue():
                self.btns_coord[btn_id].SetValue(True)
                self.fiducials[btn_id, :] = coord[0:3]
                for m in [0, 1, 2]:
                    self.numctrls_coord[btn_id][m].SetValue(coord[m])

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

    def UpdateTractsVisualization(self, data):
        self.view_tracts = data

    def UpdateImageCoordinates(self, arg, position):
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
            self.tracker_id = choice
            if not self.trk_init[0] and choice:
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Tracker disconnected successfully"))
                self.trk_init = dt.TrackerConnection(self.tracker_id, None, 'connect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, self.trk_init[1])
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
                self.trk_init = dt.TrackerConnection(self.tracker_id, trck, 'disconnect')
                if not self.trk_init[0]:
                    if evt is not False:
                        dlg.NavigationTrackerWarning(self.tracker_id, 'disconnect')
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
                    dlg.NavigationTrackerWarning(self.tracker_id, self.trk_init[1])
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
            dlg.NavigationTrackerWarning(0, 'choose')

        # Update number controls with tracker coordinates
        if coord is not None:
            self.fiducials[btn_id, :] = coord[0:3]
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(float(coord[n]))

    def OnNavigate(self, evt, btn):
        btn_nav = btn[0]
        choice_trck = btn[1]
        choice_ref = btn[2]

        nav_id = btn_nav.GetValue()
        if not nav_id:
            self.event.set()

            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn_nav.SetToolTip(tooltip)

            # Enable all navigation buttons
            choice_ref.Enable(True)
            choice_trck.Enable(True)
            for btn_c in self.btns_coord:
                btn_c.Enable(True)

            if self.trigger_state:
                self.trigger.stop()

            # self.correg.stop()

            Publisher.sendMessage("Navigation status", status=False)

        else:
            seed = [0., 0., 0.]
            slic = sl.Slice()
            affine = slic.affine
            # tracker = slic.tracker
            # tract = dti.Tractography()
            # tract = self.tract
            # tracker = tract.tracker
            # print("n_tracts!!!!!!!!!!!!: ", tract.n_tracts)
            # print("seed_offse!!!!!!!!!!!!: ", tract.seed_offset)

            # self.trk_inp = tracker, affine, tract.seed_offset, tract.n_tracts
            self.trk_inp = self.trekker, affine, self.seed_offset, self.n_tracts, self.seed_radius

            affine_vtk = vtk.vtkMatrix4x4()
            for row in range(0, 4):
                for col in range(0, 4):
                    affine_vtk.SetElement(row, col, affine[row, col])
            tracts_info = seed, self.trekker, affine, affine_vtk
            # ---


            if np.isnan(self.fiducials).any():
                dlg.InvalidFiducials()
                btn_nav.SetValue(False)

            elif not self.trk_init[0]:
                dlg.NavigationTrackerWarning(0, 'choose')

            else:
                tooltip = wx.ToolTip(_("Stop neuronavigation"))
                btn_nav.SetToolTip(tooltip)

                # Disable all navigation buttons
                choice_ref.Enable(False)
                choice_trck.Enable(False)
                for btn_c in self.btns_coord:
                    btn_c.Enable(False)

                # fids_head_img = np.zeros([3, 3])
                # for ic in range(0, 3):
                #     fids_head_img[ic, :] = np.asarray(db.flip_x_m(self.fiducials[ic, :]))
                #
                # m_head_aux, q_head_aux, m_inv_head_aux = db.base_creation(fids_head_img)
                # m_head = np.asmatrix(np.identity(4))
                # m_head[:3, :3] = m_head_aux[:3, :3]

                m, q1, minv = db.base_creation_old(self.fiducials[:3, :])
                n, q2, ninv = db.base_creation_old(self.fiducials[3:, :])

                m_change = tr.affine_matrix_from_points(self.fiducials[3:, :].T, self.fiducials[:3, :].T,
                                                        shear=False, scale=False)

                # coreg_data = [m_change, m_head]

                tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id
                # FIXME: FRE is taking long to calculate so it updates on GUI delayed to navigation - I think its fixed
                # TODO: Exhibit FRE in a warning dialog and only starts navigation after user clicks ok
                fre = db.calculate_fre(self.fiducials, minv, n, q1, q2)

                self.txtctrl_fre.SetValue(str(round(fre, 2)))
                if fre <= 3:
                    self.txtctrl_fre.SetBackgroundColour('GREEN')
                else:
                    self.txtctrl_fre.SetBackgroundColour('RED')

                if self.trigger_state:
                    self.trigger = trig.Trigger(nav_id)

                Publisher.sendMessage("Navigation status", status=True)
                Publisher.sendMessage("Toggle Cross", id=const.SLICE_STATE_CROSS)
                Publisher.sendMessage("Hide current mask")

                if self.track_obj:
                    if self.obj_reg_status:
                        # obj_reg[0] is object 3x3 fiducial matrix and obj_reg[1] is 3x3 orientation matrix
                        obj_fiducials, obj_orients, obj_ref_mode, obj_name = self.obj_reg

                        if self.trk_init and self.tracker_id:

                            coreg_data = [m_change, obj_ref_mode]

                            if self.ref_mode_id:
                                coord_raw = dco.GetCoordinates(self.trk_init, self.tracker_id, self.ref_mode_id)
                                obj_data = db.object_registration(obj_fiducials, obj_orients, coord_raw, m_change)
                                coreg_data.extend(obj_data)

                                # self.correg = dcr.CoregistrationObjectDynamic(coreg_data, nav_id, tracker_mode, tracts_info)
                                # inp_trk = tracker, position, affine
                                # inp_trk = self.trk_inp

                                if self.event.is_set():
                                    self.event.clear()

                                # sle = .3
                                sle = self.sleep_nav
                                # pipeline = Pipeline()
                                # working with both sets below
                                # pipeline = PipelineTractsCondition()
                                pipeline = PipelineSimple()

                                # this works with sleep of 0.25 for each thread
                                threds = []
                                threds.append(dcr.CoordinateCorregistrate(tracker_mode, coreg_data, pipeline, self.event, sle))
                                # threds.append(dti.ComputeVisualize(self.trk_inp, affine_vtk, pipeline, self.event, sle))
                                if self.view_tracts:
                                    threds.append(dti.ComputeVisualizeParallel(self.trk_inp, affine_vtk, pipeline, self.event, sle))

                                # threds.append(dcr.CoordinateProducer(tracker_mode, pipeline, self.event, sle))
                                # threds.append(dcr.CoregistrationThread(coreg_data, pipeline, self.event, sle))
                                # threds.append(dti.ComputeTractsDev(self.trk_inp, pipeline, self.event, sle))
                                # threds.append(dti.VisualizeTractsDev(affine_vtk, pipeline, self.event, sle))

                                # with NavThreadPool(threds):
                                #     print("Main thread")
                                    # sleep(.005)

                                for th in threds:
                                    th.start()

                                # this works with sleep of 0.25 for each thread
                                # process1 = dcr.CoordinateProducer(tracker_mode, pipeline, self.event, sle)
                                # process2 = dcr.CoregistrationThread(coreg_data, pipeline, self.event, sle)
                                # process3 = dti.ComputeTractsDev(self.trk_inp, pipeline, self.event, sle)
                                # process4 = dti.VisualizeTractsDev(affine_vtk, pipeline, self.event, sle)
                                # process1.start()
                                # process2.start()
                                # process3.start()
                                # process4.start()

                                # Threads using Queue
                                # pipe_coord = queue.LifoQueue(maxsize=1)
                                # pipe_coord2 = queue.LifoQueue(maxsize=1)
                                # pipe_tract = queue.LifoQueue(maxsize=1)
                                # self.event = threading.Event()
                                # with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                                #     print("About start generate_coord\n")
                                #     executor.submit(dcr.GetCoordinatesProducer, tracker_mode, pipe_coord, self.event)
                                #     print("About start corregistrate\n")
                                #     executor.submit(dcr.CoregistrationNoThread, coreg_data, pipe_coord, self.event)
                                #     # print("About start compute_tract\n")
                                #     # executor.submit(dti.TractsThread, self.trk_inp, pipe_coord2, pipe_tract, self.event)
                                #     # print("About start split_simple\n")
                                #     # executor.submit(dti.ComputeTractsChunck, affine_vtk, pipe_tract, self.event)
                            else:
                                coord_raw = np.array([None])
                                obj_data = db.object_registration(obj_fiducials, obj_orients, coord_raw, m_change)
                                coreg_data.extend(obj_data)

                                self.correg = dcr.CoregistrationObjectStatic(coreg_data, nav_id, tracker_mode)

                        else:
                            dlg.NavigationTrackerWarning(0, 'choose')

                    else:
                        dlg.InvalidObjectRegistration()

                else:
                    coreg_data = [m_change, 0]
                    if self.ref_mode_id:
                        # self.correg = dcr.CoregistrationDynamic_old(bases_coreg, nav_id, tracker_mode)
                        self.correg = dcr.CoregistrationDynamic(coreg_data, nav_id, tracker_mode, tracts_info)
                        self.correg.start()
                    else:
                        self.correg = dcr.CoregistrationStatic(coreg_data, nav_id, tracker_mode)

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

    def OnCloseProject(self):
        self.ResetTrackerFiducials()
        self.ResetImageFiducials()
        self.OnChoiceTracker(False, self.choice_trck)
        Publisher.sendMessage('Update object registration')
        Publisher.sendMessage('Update track object state', flag=False, obj_name=False)
        Publisher.sendMessage('Delete all markers')
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
        line_checks.Add(checktrack, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.LEFT, 5)

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

    def UpdateTrackerInit(self, nav_prop):
        self.nav_prop = nav_prop

    def UpdateNavigationStatus(self, status):
        nav_status = status
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
            dlg.NavigationTrackerWarning(0, 'choose')

    def OnLinkLoad(self, event=None):
        filename = dlg.ShowLoadRegistrationDialog()

        if filename:
            data = np.loadtxt(filename, delimiter='\t')
            self.obj_fiducials = data[:, :3]
            self.obj_orients = data[:, 3:]

            text_file = open(filename, "r")
            header = text_file.readline().split('\t')
            text_file.close()

            self.obj_name = header[1]
            self.obj_ref_mode = int(header[-1])

            self.checktrack.Enable(1)
            Publisher.sendMessage('Update object registration',
                                  data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
            Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
            self.checktrack.SetValue(True)
            Publisher.sendMessage('Update track object state', flag=True, obj_name=self.obj_name)
            Publisher.sendMessage('Change camera checkbox', status=False)
            wx.MessageBox(_("Object file successfully loaded"), _("Load"))

    def ShowSaveObjectDialog(self, evt):
        if np.isnan(self.obj_fiducials).any() or np.isnan(self.obj_orients).any():
            wx.MessageBox(_("Digitize all object fiducials before saving"), _("Save error"))
        else:
            filename = dlg.ShowSaveRegistrationDialog("object_registration.obr")
            if filename:
                hdr = 'Object' + "\t" + utils.decode(self.obj_name, const.FS_ENCODE) + "\t" + 'Reference' + "\t" + str('%d' % self.obj_ref_mode)
                data = np.hstack([self.obj_fiducials, self.obj_orients])
                np.savetxt(filename, data, fmt='%.4f', delimiter='\t', newline='\n', header=hdr)
                wx.MessageBox(_("Object file successfully saved"), _("Save"))

    def OnCloseProject(self):
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
        self.list_coord = []
        self.marker_ind = 0
        self.tgt_flag = self.tgt_index = None
        self.nav_status = False

        self.marker_colour = (1.0, 1.0, 0.)
        self.marker_size = 3

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
        group_sizer.Add(self.lc, 0, wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Fit(self)

        self.SetSizer(group_sizer)
        self.Update()

    def __bind_events(self):
        # Publisher.subscribe(self.UpdateCurrentCoord, 'Co-registered points')
        Publisher.subscribe(self.UpdateCurrentCoord, 'Update cross position')
        Publisher.subscribe(self.OnDeleteSingleMarker, 'Delete fiducial marker')
        Publisher.subscribe(self.OnDeleteAllMarkers, 'Delete all markers')
        Publisher.subscribe(self.OnCreateMarker, 'Create marker')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')

    def UpdateCurrentCoord(self, arg, position):
        self.current_coord = position[:]
        #self.current_angle = pubsub_evt.data[1][3:]

    def UpdateNavigationStatus(self, status):
        if not status:
            sleep(0.5)
            #self.current_coord[3:] = 0, 0, 0
            self.nav_status = False
        else:
            self.nav_status = True

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
            id_label = dlg.EnterMarkerID(self.lc.GetItemText(list_index, 4))
            if id_label == 'TARGET':
                id_label = ''
                dlg.InvalidTargetID()
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
        dlg.NewTarget()

    def OnMenuSetColor(self, evt):
        index = self.lc.GetFocusedItem()
        cdata = wx.ColourData()
        cdata.SetColour(wx.Colour(self.list_coord[index][6]*255,self.list_coord[index][7]*255,self.list_coord[index][8]*255))
        dlg = wx.ColourDialog(self, data=cdata)
        dlg.GetColourData().SetChooseFull(True)
        if dlg.ShowModal() == wx.ID_OK:
            self.r, self.g, self.b = dlg.GetColourData().GetColour().Get(includeAlpha=False)
            r = float(self.r) / 255.0
            g = float(self.g) / 255.0
            b = float(self.b) / 255.0
        dlg.Destroy()
        color = [r,g,b]

        Publisher.sendMessage('Set new color', index=index, color=color)

        self.list_coord[index][6] = r
        self.list_coord[index][7] = g
        self.list_coord[index][8] = b

    def OnDeleteAllMarkers(self, evt=None):
        if self.list_coord:
            if evt is None:
                result = wx.ID_OK
            else:
                result = dlg.DeleteAllMarkers()

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
                        dlg.DeleteTarget()

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

        if index:
            if self.tgt_flag and self.tgt_index == index[0]:
                self.tgt_flag = self.tgt_index = None
                Publisher.sendMessage('Disable or enable coil tracker', status=False)
                dlg.DeleteTarget()
            self.DeleteMarker(index)
        else:
            dlg.NoMarkerSelected()

    def DeleteMarker(self, index):
        for i in reversed(index):
            del self.list_coord[i]
            self.lc.DeleteItem(i)
            for n in range(0, self.lc.GetItemCount()):
                self.lc.SetItem(n, 0, str(n+1))
            self.marker_ind -= 1
        Publisher.sendMessage('Remove marker', index=index)

    def OnCreateMarker(self, evt=None, coord=None, marker_id=None):
        # OnCreateMarker is used for both pubsub and button click events
        # Pubsub is used for markers created with fiducial buttons, trigger and create marker button
        if evt is None:
            if coord:
                self.CreateMarker(coord, (0.0, 1.0, 0.0), self.marker_size, marker_id)
            else:
                self.CreateMarker(self.current_coord, self.marker_colour, self.marker_size)
        else:
            self.CreateMarker(self.current_coord, self.marker_colour, self.marker_size)

    def OnLoadMarkers(self, evt):
        filepath = dlg.ShowLoadMarkersDialog()

        if filepath:
            try:
                count_line = self.lc.GetItemCount()
                content = [s.rstrip() for s in open(filepath)]
                for data in content:
                    target = None
                    line = [s for s in data.split()]
                    if len(line) > 8:
                        coord = float(line[0]), float(line[1]), float(line[2]), float(line[3]), float(line[4]), float(line[5])
                        colour = float(line[6]), float(line[7]), float(line[8])
                        size = float(line[9])

                        if len(line) == 11:
                            for i in const.BTNS_IMG_MKS:
                                if line[10] in list(const.BTNS_IMG_MKS[i].values())[0]:
                                    Publisher.sendMessage('Load image fiducials', marker_id=line[10], coord=coord)
                                elif line[10] == 'TARGET':
                                    target = count_line
                        else:
                            line.append("")

                        self.CreateMarker(coord, colour, size, line[10])
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
                dlg.InvalidMarkersFile()

    def OnMarkersVisibility(self, evt, ctrl):

        if ctrl.GetValue():
            Publisher.sendMessage('Hide all markers',  indexes=self.lc.GetItemCount())
            ctrl.SetLabel('Show')
        else:
            Publisher.sendMessage('Show all markers',  indexes=self.lc.GetItemCount())
            ctrl.SetLabel('Hide')

    def OnSaveMarkers(self, evt):
        filename = dlg.ShowSaveMarkersDialog("markers.mks")
        if filename:
            if self.list_coord:
                text_file = open(filename, "w")
                list_slice1 = self.list_coord[0]
                coord = str('%.3f' %self.list_coord[0][0]) + "\t" + str('%.3f' %self.list_coord[0][1]) + "\t" + str('%.3f' %self.list_coord[0][2])
                angles = str('%.3f' %self.list_coord[0][3]) + "\t" + str('%.3f' %self.list_coord[0][4]) + "\t" + str('%.3f' %self.list_coord[0][5])
                properties = str('%.3f' %list_slice1[6]) + "\t" + str('%.3f' %list_slice1[7]) + "\t" + str('%.3f' %list_slice1[8]) + "\t" + str('%.1f' %list_slice1[9]) + "\t" + list_slice1[10]
                line = coord + "\t" + angles + "\t" + properties + "\n"
                list_slice = self.list_coord[1:]

                for value in list_slice:
                    coord = str('%.3f' %value[0]) + "\t" + str('%.3f' %value[1]) + "\t" + str('%.3f' %value[2])
                    angles = str('%.3f' % value[3]) + "\t" + str('%.3f' % value[4]) + "\t" + str('%.3f' % value[5])
                    properties = str('%.3f' %value[6]) + "\t" + str('%.3f' %value[7]) + "\t" + str('%.3f' %value[8]) + "\t" + str('%.1f' %value[9]) + "\t" + value[10]
                    line = line + coord + "\t" + angles + "\t" +properties + "\n"

                text_file.writelines(line)
                text_file.close()

    def OnSelectColour(self, evt, ctrl):
        self.marker_colour = [colour/255.0 for colour in ctrl.GetValue()]

    def OnSelectSize(self, evt, ctrl):
        self.marker_size = ctrl.GetValue()

    def CreateMarker(self, coord, colour, size, marker_id=""):
        # TODO: Use matrix coordinates and not world coordinates as current method.
        # This makes easier for inter-software comprehension.

        Publisher.sendMessage('Add marker', ball_id=self.marker_ind, size=size, colour=colour,  coord=coord[0:3])

        self.marker_ind += 1

        # List of lists with coordinates and properties of a marker

        line = [coord[0], coord[1], coord[2], coord[3], coord[4], coord[5], colour[0], colour[1], colour[2], size, marker_id]

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

        # self.coil_list = const.COIL

        self.affine = None
        self.affine_vtk = None
        self.tracker = None
        # self.tract = dti.Tractography()
        # self.tract.n_tracts = const.N_TRACTS
        # self.tract.seed_offset = const.SEED_OFFSET
        self.n_tracts = const.N_TRACTS
        self.peel_depth = const.PEEL_DEPTH
        self.view_tracts = False
        # self.obj_ref_mode = None
        # self.obj_name = None
        self.seed_offset = const.SEED_OFFSET
        self.seed_radius = const.SEED_RADIUS
        self.sleep_nav = const.SLEEP_NAVIGATION
        self.brain_peel = None
        self.n_peels = const.MAX_PEEL_DEPTH
        self.p_old = np.array([[0., 0., 0.]])
        self.tracts_run = None
        self.trekker_cfg = None
        # self.vezes = 0

        # self.affine_vtk = vtk.vtkMatrix4x4()
        # for row in range(0, 4):
        #     for col in range(0, 4):
        #         self.affine_vtk.SetElement(row, col, self.affine[row, col])

        self.SetAutoLayout(1)
        self.__bind_events()

        # Button for creating new coil
        tooltip = wx.ToolTip(_("Load brain"))
        btn_new = wx.Button(self, -1, _("Load brain"), size=wx.Size(65, 23))
        btn_new.SetToolTip(tooltip)
        btn_new.Enable(1)
        btn_new.Bind(wx.EVT_BUTTON, self.OnLinkBrain)
        self.btn_new = btn_new

        # Button for import config coil file
        tooltip = wx.ToolTip(_("Load FOD"))
        btn_load = wx.Button(self, -1, _("Load FOD"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLinkFOD)
        self.btn_load = btn_load

        # Save button for object registration
        tooltip = wx.ToolTip(_(u"Load parameters"))
        btn_load_cfg = wx.Button(self, -1, _(u"Load"), size=wx.Size(65, 23))
        btn_load_cfg.SetToolTip(tooltip)
        btn_load_cfg.Enable(1)
        btn_load_cfg.Bind(wx.EVT_BUTTON, self.OnLoadParameters)
        self.btn_load_cfg = btn_load_cfg

        # Create a horizontal sizer to represent button save
        line_btns = wx.BoxSizer(wx.HORIZONTAL)
        line_btns.Add(btn_new, 1, wx.LEFT | wx.TOP | wx.RIGHT, 4)
        line_btns.Add(btn_load, 1, wx.LEFT | wx.TOP | wx.RIGHT, 4)
        line_btns.Add(btn_load_cfg, 1, wx.LEFT | wx.TOP | wx.RIGHT, 4)

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
        spin_ntracts.SetRange(1, 200)
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

        # Change seed radius for computing tracts
        text_sleep = wx.StaticText(self, -1, _("Sleep (s):"))
        spin_sleep = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_sleep.Enable(1)
        spin_sleep.SetRange(0, 10.0)
        spin_sleep.SetValue(self.sleep_nav)
        spin_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectSleep, ctrl=spin_sleep))
        spin_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectSleep, ctrl=spin_sleep))

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

        border_last = 1
        line_checks = wx.BoxSizer(wx.HORIZONTAL)
        line_checks.Add(checktracts, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, border_last)
        line_checks.Add(checkpeeling, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.LEFT, border_last)

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
        main_sizer.Add(line_checks, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, border_last)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        # Publisher.subscribe(self.OnUpdateTracts, 'Update cross position')

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

    def OnUpdateTracts(self, arg, position):
        # Tracts
        # wx, wy, wz = position[:3]
        wx, wy, wz = db.flip_x(position[:3])
        p2 = db.flip_x(position[:3])

        if np.any(arg):
            m_img2 = arg.copy()
            m_img2[:3, -1] = np.asmatrix(db.flip_x_m((m_img2[0, -1], m_img2[1, -1], m_img2[2, -1]))).reshape([3, 1])
            norm_vec = m_img2[:3, 2].reshape([1, 3]).tolist()
            p0 = m_img2[:3, -1].reshape([1, 3]).tolist()
            p2 = [x - self.seed_offset * y for x, y in zip(p0[0], norm_vec[0])]
            wx, wy, wz = p2
            # print("m_img in task_nav: {}".format(m_img))
            # m_tract = m_img.copy()
            # m_tract[:3, -1] = np.reshape(np.asarray(p2)[np.newaxis, :], [3, 1])

        # pos_world_aux = np.ones([4, 1])
        # pos_world_aux[:3, -1] = db.flip_x(position)[:3]
        # pos_world = np.linalg.inv(self.affine) @ pos_world_aux
        # seed = pos_world.reshape([1, 4])[0, :3]
        # seed = seed_aux[np.newaxis, :]
        # print("Check the seed: ", (wx, wy, wz))

        # working version
        # if self.checktracts.GetValue():
        #     # start_time = time()
        #     # actor = dti.ComputeTractsSimple(self.tracker, (wx, wy, wz),
        #     #                                 self.affine, self.affine_vtk, self.n_tracts).run()
        #     actor = dti.ComputeTracts(self.tracker, (wx, wy, wz),
        #                                     self.affine, self.affine_vtk, self.n_tracts).run()
        #     # Publisher.sendMessage('Update tracts', flag=True, actor=actor)
        #     # duration = time() - start_time
        #     # print(f"Tracts duration {duration} seconds")

        if self.checktracts.GetValue():
            dist = abs(np.linalg.norm(self.p_old - np.asarray(p2)))
            self.p_old = np.asarray(p2)
            # print("Distancia: ", dist)

            if dist > 3:
                if self.tracts_run:
                    print("Parei")
                    self.tracts_run.stop()
                # self.vezes += 1
                # print("N vezes: ", self.vezes)
                print("Rodei")
                self.tracts_run = dti.ComputeTractsParallel(self.tracker, (wx, wy, wz), self.affine, self.affine_vtk, self.n_tracts)
                self.tracts_run.start()

    def OnLinkBrain(self, event=None):
        Publisher.sendMessage('Begin busy cursor')
        mask_path = dlg.ShowImportOtherFilesDialog(const.ID_TREKKER_MASK)
        # data_dir = os.environ.get('OneDriveConsumer') + '\\data\\dti'
        # mask_file = 'sub-P0_dwi_mask.nii'
        # mask_path = os.path.join(data_dir, mask_file)
        img_path = dlg.ShowImportOtherFilesDialog(const.ID_TREKKER_IMG)
        # img_file = 'sub-P0_T1w_biascorrected.nii'
        # img_path = os.path.join(data_dir, img_file)

        if not self.affine_vtk:
            slic = sl.Slice()
            self.affine = slic.affine
            self.affine_vtk = vtk.vtkMatrix4x4()
            for row in range(0, 4):
                for col in range(0, 4):
                    self.affine_vtk.SetElement(row, col, self.affine[row, col])

        #print("Affine: ", self.affine_vtk)
        # n_peels = 10

        if mask_path and img_path:
            self.brain_peel = brain.Brain(img_path, mask_path, self.n_peels, self.affine_vtk)
            actor = self.brain_peel.get_actor(self.peel_depth)
            Publisher.sendMessage('Update peel', flag=True, actor=actor)
            self.checkpeeling.Enable(1)
            # Publisher.sendMessage('Update object registration',
            #                       data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
            # Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
            self.checkpeeling.SetValue(True)

        Publisher.sendMessage('Update status text in GUI', label=_("Brain model loaded"))
        Publisher.sendMessage('End busy cursor')

    def OnLinkFOD(self, event=None):
        Publisher.sendMessage('Begin busy cursor')
        filename = dlg.ShowImportOtherFilesDialog(const.ID_TREKKER_FOD)
        # data_dir = os.environ.get('OneDriveConsumer') + '\\data\\dti'
        # # data_dir = b'C:\Users\deoliv1\OneDrive\data\dti'
        # FOD_path = 'sub-P0_dwi_FOD.nii'
        # # FOD_path = b"test_fod.nii"
        # filename = os.path.join(data_dir, FOD_path)

        if filename:
            # data_dir = os.environ.get('OneDriveConsumer') + '\\data\\dti'
            # data_dir = b'C:\Users\deoliv1\OneDrive\data\dti'
            # FOD_path = 'sub-P0_dwi_FOD.nii'
            # FOD_path = b"test_fod.nii"
            # full_path = os.path.join(data_dir, FOD_path)
            # slic = sl.Slice()
            # self.affine = slic.affine
            # slic.tracker = Trekker.tracker(filename.encode('utf-8'))
            # slic.tracker.set_seed_maxTrials(1)
            # slic.tracker.set_stepSize(0.1)
            # slic.tracker.set_minFODamp(0.05)
            # slic.tracker.set_probeQuality(3)
            # slic.tracker.set_numberOfThreads(4)

            # self.tract.tracker = Trekker.tracker(filename.encode('utf-8'))
            # self.tract.tracker.seed_maxTrials(1)
            # self.tract.tracker.stepSize(0.1)
            # self.tract.tracker.minFODamp(0.05)
            # self.tract.tracker.probeQuality(3)
            # self.tract.tracker.numberOfThreads(ncores)
            # self.tract.tracker.maxEstInterval(5)
            # self.tract.tracker.minRadiusOfCurvature(0.5)
            # self.tract.tracker.probeLength(0.4)
            # self.tract.tracker.writeInterval(10)

            if self.trekker_cfg:
                self.tracker = Trekker.tracker(filename.encode('utf-8'))
                self.tracker.seed_maxTrials(self.trekker_cfg['seed_max'])
                self.tracker.stepSize(self.trekker_cfg['step_size'])
                self.tracker.minFODamp(self.trekker_cfg['min_fod'])
                self.tracker.probeQuality(self.trekker_cfg['probe_quality'])
                self.tracker.maxEstInterval(self.trekker_cfg['max_interval'])
                self.tracker.minRadiusOfCurvature(self.trekker_cfg['min_radius_curv'])
                self.tracker.probeLength(self.trekker_cfg['probe_length'])
                self.tracker.writeInterval(self.trekker_cfg['write_interval'])

                # check number if number of cores is valid in configuration file,
                # otherwise use the maximum number of threads which is usually 2*N_CPUS
                if isinstance((self.trekker_cfg['numb_threads']), int):
                    if self.trekker_cfg['numb_threads'] <= 2*const.N_CPU:
                        self.tracker.numberOfThreads(self.trekker_cfg['numb_threads'])
                    else:
                        self.tracker.numberOfThreads(2*const.N_CPU)

            Publisher.sendMessage('Update status text in GUI', label=_("Trekker initialized"))

            # group = oth.ReadOthers(filename)
            # if group.affine.any():
            #     if np.sum(slic.affine - group.affine):
            #         slic.affine = image_utils.world2invspace(shape=group.shape, affine=group.affine)
            #         Publisher.sendMessage('Update affine matrix',
            #                               affine=slic.affine, status=True)

            # tracts
            # self.seed = [0., 0., 0.]
            # self.tracker = self.tract.tracker
            # self.tract = self.tract

            # self.affine_vtk = vtk.vtkMatrix4x4()
            # for row in range(0, 4):
            #     for col in range(0, 4):
            #         self.affine_vtk.SetElement(row, col, self.affine[row, col])
            # ---

            self.checktracts.Enable(1)
            self.checktracts.SetValue(True)
            Publisher.sendMessage('Update tracts visualization', data=1)
            # Publisher.sendMessage('Update object registration',
            #                       data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
            # Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
            # Publisher.sendMessage('Update track object state', flag=True, obj_name=self.obj_name)
            # Publisher.sendMessage('Change camera checkbox', status=False)
            # wx.MessageBox(_("Object file successfully loaded"), _("Load"))
            # data = self.tracker, self.affine, self.seed_offset, self.n_tracts
            # tract.n_tracts = self.n_tracts
            Publisher.sendMessage('Update Trekker object', data=self.tracker)
            Publisher.sendMessage('End busy cursor')

    def OnLoadParameters(self, event=None):
        import json
        filename = dlg.ShowLoadDialog(message=_(u"Load Trekker configuration"),
                                      wildcard=_("JSON file (*.json)|*.json"))
        try:
            # Check if filename exists, read the JSON file and check if all parameters match
            # with the required list defined in the constants module
            # if a parameter is missing, raise an error
            if filename:
                with open(filename) as json_file:
                    self.trekker_cfg = json.load(json_file)
                assert all(name in self.trekker_cfg for name in const.TREKKER_CONFIG)
                Publisher.sendMessage('Update status text in GUI', label=_("Trekker config loaded"))

        except (AssertionError, json.decoder.JSONDecodeError):
            # Inform user that file is not compatible
            self.trekker_cfg = const.TREKKER_CONFIG
            wx.MessageBox(_("File incompatible, using default configuration."), _("InVesalius 3"))

    def OnCloseProject(self):
        self.checktracts.SetValue(False)
        self.checktracts.Enable(0)
        self.checkpeeling.SetValue(False)
        self.checkpeeling.Enable(0)

        self.peel_depth = const.PEEL_DEPTH
        self.n_tracts = const.N_TRACTS
        self.timestamp = const.TIMESTAMP


class Pipeline:
    """Class to allow a single element pipeline between producer and consumer.
    """

    def __init__(self):
        self.message = 0
        self.producer_lock = threading.Lock()
        self.consumer_lock = threading.Lock()
        self.consumer_lock.acquire(timeout=1)

    def get_message(self):
        print("Getting message")
        self.consumer_lock.acquire(timeout=1)
        message = self.message
        self.producer_lock.release()
        return message

    def set_message(self, message):
        print("Setting message")
        self.producer_lock.acquire(timeout=1)
        self.message = message
        self.consumer_lock.release()


class PipelineTracts:
    """Class to allow a single element pipeline between producer and consumer.
    """

    def __init__(self):
        self.message = 0
        self.coord_coreg = 0
        self.tracts_list = 0
        # self.producer_lock = threading.Lock()
        # self.consumer_lock = threading.Lock()
        # self.prod_coreg_lock = threading.Lock()
        # self.cons_coreg_lock = threading.Lock()
        # self.prod_tract_lock = threading.Lock()
        # self.cons_tract_lock = threading.Lock()
        self.locks = [threading.Lock() for _ in range(6)]
        self.locks[1].acquire(timeout=1)
        # self.consumer_lock.acquire(timeout=1)

    def get_message(self):
        print("Getting message")
        # self.consumer_lock.acquire(timeout=1)
        self.locks[1].acquire(timeout=1)
        message = self.message
        [item.release() for n, item in enumerate(self.locks) if item.locked() and n != 1]

        # self.cons_coreg_lock.release()
        # self.cons_tract_lock.release()
        #
        # self.producer_lock.release()
        # self.prod_coreg_lock.release()
        # self.prod_tract_lock.release()
        return message

    def set_message(self, message):
        print("Setting message")
        # self.producer_lock.acquire(timeout=1)
        self.locks[0].acquire(timeout=1)
        self.message = message
        [item.release() for n, item in enumerate(self.locks) if item.locked() and n != 0]

        # self.prod_coreg_lock.release()
        # self.prod_tract_lock.release()
        #
        # self.consumer_lock.release()
        # self.cons_coreg_lock.release()
        # self.cons_tract_lock.release()

    def get_coord_coreg(self):
        print("Getting tracts")
        self.locks[3].acquire(timeout=1)
        # self.cons_coreg_lock.acquire(timeout=1)
        coord_coreg = self.coord_coreg
        [item.release() for n, item in enumerate(self.locks) if item.locked() and n != 3]

        # self.consumer_lock.release()
        # self.cons_tract_lock.release()
        #
        # self.producer_lock.release()
        # self.prod_coreg_lock.release()
        # self.prod_tract_lock.release()
        return coord_coreg

    def set_coord_coreg(self, coord_coreg):
        print("Setting tracts")
        # self.prod_coreg_lock.acquire(timeout=1)
        self.locks[2].acquire(timeout=1)
        self.coord_coreg = coord_coreg
        [item.release() for n, item in enumerate(self.locks) if item.locked() and n != 2]

        # self.producer_lock.release()
        # self.prod_tract_lock.release()
        #
        # self.consumer_lock.release()
        # self.cons_coreg_lock.release()
        # self.cons_tract_lock.release()

    def get_tracts_list(self):
        print("Getting tracts")
        # self.cons_tract_lock.acquire(timeout=1)
        self.locks[5].acquire(timeout=1)
        tracts_list = self.tracts_list
        [item.release() for n, item in enumerate(self.locks) if item.locked() and n != 5]
        # self.consumer_lock.release()
        # self.cons_coreg_lock.release()
        #
        # self.producer_lock.release()
        # self.prod_coreg_lock.release()
        # self.prod_tract_lock.release()
        return tracts_list

    def set_tracts_list(self, tracts_list):
        print("Setting tracts")
        # self.prod_tract_lock.acquire(timeout=1)
        self.locks[4].acquire(timeout=1)
        self.tracts_list = tracts_list
        [item.release() for n, item in enumerate(self.locks) if item.locked() and n != 4]
        # self.producer_lock.release()
        # self.prod_coreg_lock.release()
        #
        # self.consumer_lock.release()
        # self.cons_coreg_lock.release()
        # self.cons_tract_lock.release()


class PipelineTractsSimple:
    """Class to allow a single element pipeline between producer and consumer.
    """

    def __init__(self):
        self.message = 0
        self.coord_coreg = 0
        self.tracts_list = 0

        self.locks = threading.Lock()

    def get_message(self):
        print("Getting message")
        with self.locks:
            message = self.message
        return message

    def set_message(self, message):
        print("Setting message")
        with self.locks:
            self.message = message

    def get_coord_coreg(self):
        print("Getting coreg")
        with self.locks:
            coord_coreg = self.coord_coreg
        return coord_coreg

    def set_coord_coreg(self, coord_coreg):
        print("Setting coreg")
        # self.prod_coreg_lock.acquire(timeout=1)
        with self.locks:
            self.coord_coreg = coord_coreg

    def get_tracts_list(self):
        print("Getting tracts")
        with self.locks:
            tracts_list = self.tracts_list
        return tracts_list

    def set_tracts_list(self, tracts_list):
        print("Setting tracts")
        # self.prod_tract_lock.acquire(timeout=1)
        with self.locks:
            self.tracts_list = tracts_list


class PipelineTractsCondition:
    """Class to allow a single element pipeline between producer and consumer.
    """

    def __init__(self):
        self.message = False
        self.coord_coreg = False
        self.tracts_list = False

        self.locks = threading.Lock()
        self.event_coord = threading.Event()
        self.event_coreg = threading.Event()
        self.event_tracts = threading.Event()

    def get_message(self):
        print("Getting message")
        with self.locks:
            if self.event_coord.is_set():
                return self.message
            else:
                return False

    def set_message(self, message):
        print("Setting message")
        with self.locks:
            self.message = message
            self.event_coord.set()

    def get_coord_coreg(self):
        print("Getting coreg")
        with self.locks:
            if self.event_coreg.is_set():
                return self.coord_coreg
            else:
                return False

    def set_coord_coreg(self, coord_coreg):
        print("Setting coreg")
        # self.prod_coreg_lock.acquire(timeout=1)
        with self.locks:
            self.coord_coreg = coord_coreg
            self.event_coreg.set()

    def get_tracts_list(self):
        print("Getting tracts")
        with self.locks:
            # if self.event_tracts.is_set():
            return self.tracts_list
            # else:
            #     return False

    def set_tracts_list(self, tracts_list):
        print("Setting tracts")
        # self.prod_tract_lock.acquire(timeout=1)
        with self.locks:
            self.tracts_list = tracts_list
            self.event_tracts.set()


class PipelineTractsCondition:
    """Class to allow a single element pipeline between producer and consumer.
    """

    def __init__(self):
        self.message = False
        self.coord_coreg = False
        self.tracts_list = False

        self.locks = threading.Lock()
        self.event_coord = threading.Event()
        self.event_coreg = threading.Event()
        self.event_tracts = threading.Event()

    def get_message(self):
        print("Getting message")
        with self.locks:
            if self.event_coord.is_set():
                return self.message
            else:
                return False

    def set_message(self, message):
        print("Setting message")
        with self.locks:
            self.message = message
            self.event_coord.set()

    def get_coord_coreg(self):
        print("Getting coreg")
        with self.locks:
            if self.event_coreg.is_set():
                return self.coord_coreg
            else:
                return False

    def set_coord_coreg(self, coord_coreg):
        print("Setting coreg")
        # self.prod_coreg_lock.acquire(timeout=1)
        with self.locks:
            self.coord_coreg = coord_coreg
            self.event_coreg.set()

    def get_tracts_list(self):
        print("Getting tracts")
        with self.locks:
            # if self.event_tracts.is_set():
            return self.tracts_list
            # else:
            #     return False

    def set_tracts_list(self, tracts_list):
        print("Setting tracts")
        # self.prod_tract_lock.acquire(timeout=1)
        with self.locks:
            self.tracts_list = tracts_list
            self.event_tracts.set()


class NavThreadPool:
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, threads):
        self.threads = threads

    def __enter__(self):
        # self.start()
        for th in self.threads:
            th.start()
        return self

    def __exit__(self, *args, **kwargs):
        print('Force set Thread stop_event')


class PipelineSimple:
    """Class to allow a single element pipeline between producer and consumer.
    """

    def __init__(self):
        self.message = False

        self.locks = threading.Lock()
        self.event = threading.Event()

    def get_message(self):
        # print("Getting message")
        with self.locks:
            if self.event.is_set():
                return self.message
            else:
                return False

    def set_message(self, message):
        # print("Setting message")
        with self.locks:
            self.message = message
            self.event.set()
