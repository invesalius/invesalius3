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

import numpy as np
import wx
import wx.lib.hyperlink as hl
import wx.lib.masked.numctrl
import wx.lib.foldpanelbar as fpb
from wx.lib.pubsub import pub as Publisher
import wx.lib.colourselect as csel
import wx.lib.platebtn as pbtn

from time import sleep

import invesalius.constants as const
import invesalius.data.bases as db
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.trackers as dt
import invesalius.data.trigger as trig
import invesalius.data.record_coords as rec
import invesalius.gui.dialogs as dlg

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
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.__bind_events()
        # Fold panel and its style settings
        # FIXME: If we dont insert a value in size or if we set wx.DefaultSize,
        # the fold_panel doesnt show. This means that, for some reason, Sizer
        # is not working properly in this panel. It might be on some child or
        # parent panel. Perhaps we need to insert the item into the sizer also...
        # Study this.
        displaySize = wx.DisplaySize()
        if displaySize[1] > 768:
            fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                          (10, 350), 0, fpb.FPB_SINGLE_FOLD)
        else:
            fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                          (10, 320), 0, fpb.FPB_SINGLE_FOLD)
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
        item = fold_panel.AddFoldPanel(_("Extra tools"), collapsed=True)
        mtw = MarkersPanel(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, mtw, spacing= 0,
                                      leftSpacing=0, rightSpacing=0)


        # Check box for camera update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Update camera in volume"))
        checkcamera = wx.CheckBox(self, -1, _('Vol. camera'))
        checkcamera.SetToolTip(tooltip)
        checkcamera.SetValue(const.CAM_MODE)
        checkcamera.Bind(wx.EVT_CHECKBOX, self.UpdateVolumeCamera)
        self.checkcamera = checkcamera

        # Check box for trigger monitoring to create markers from serial port
        tooltip = wx.ToolTip(_("Enable external trigger for creating markers"))
        checktrigger = wx.CheckBox(self, -1, _('Ext. trigger'))
        checktrigger.SetToolTip(tooltip)
        checktrigger.SetValue(False)
        checktrigger.Bind(wx.EVT_CHECKBOX, partial(self.UpdateExternalTrigger, ctrl=checktrigger))
        self.checktrigger = checktrigger

        # Check box for object position and orientation update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Show and track TMS coil"))
        checkobj = wx.CheckBox(self, -1, _('Show coil'))
        checkobj.SetToolTip(tooltip)
        checkobj.SetValue(False)
        checkobj.Bind(wx.EVT_CHECKBOX, partial(self.UpdateShowObject, ctrl=checkobj))
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

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
    def __bind_events(self):
        Publisher.subscribe(self.OnCheckStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateVolumeCamera, 'Target navigation mode')

    def OnCheckStatus(self, pubsub_evt):
        status = pubsub_evt.data
        if status:
            self.checktrigger.Enable(False)
            self.checkobj.Enable(False)
        else:
            self.checktrigger.Enable(True)
            self.checkobj.Enable(True)

    def UpdateExternalTrigger(self, evt, ctrl):
        Publisher.sendMessage('Update trigger state', ctrl.GetValue())

    def UpdateShowObject(self, evt, ctrl):
        Publisher.sendMessage('Update object tracking state', ctrl.GetValue())

    def UpdateVolumeCamera(self, evt):
        if hasattr(evt, 'data'):
            if evt.data is True:
                self.checkcamera.SetValue(0)
        Publisher.sendMessage('Update volume camera state', self.checkcamera.GetValue())


class NeuronavigationPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
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
        self.obj_show = False
        self.obj_reg = None
        self.obj_reg_status = False

        self.tracker_id = const.DEFAULT_TRACKER
        self.ref_mode_id = const.DEFAULT_REF_MODE

        # Initialize list of buttons and numctrls for wx objects
        self.btns_coord = [None] * 7
        self.numctrls_coord = [list(), list(), list(), list(), list(), list(), list()]

        # ComboBox for spatial tracker device selection
        tooltip = wx.ToolTip(_("Choose the tracking device"))
        choice_trck = wx.ComboBox(self, -1, "",
                                  choices=const.TRACKER, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_trck.SetToolTip(tooltip)
        choice_trck.SetSelection(const.DEFAULT_TRACKER)
        choice_trck.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceTracker, ctrl=choice_trck))

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
            n = btns_img[k].keys()[0]
            lab = btns_img[k].values()[0]
            self.btns_coord[n] = wx.ToggleButton(self, k, label=lab, size=wx.Size(45, 23))
            self.btns_coord[n].SetToolTip(wx.ToolTip(tips_img[n]))
            self.btns_coord[n].Bind(wx.EVT_TOGGLEBUTTON, self.OnImageFiducials)

        # Push buttons for tracker fiducials
        btns_trk = const.BTNS_TRK
        tips_trk = const.TIPS_TRK

        for k in btns_trk:
            n = btns_trk[k].keys()[0]
            lab = btns_trk[k].values()[0]
            self.btns_coord[n] = wx.Button(self, k, label=lab, size=wx.Size(45, 23))
            self.btns_coord[n].SetToolTip(wx.ToolTip(tips_trk[n-3]))
            # Exception for event of button that set image coordinates
            if n == 6:
                self.btns_coord[n].Bind(wx.EVT_BUTTON, self.OnSetImageCoordinates)
            else:
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

        # Toggle button for neuronavigation
        tooltip = wx.ToolTip(_("Start navigation"))
        btn_nav = wx.ToggleButton(self, -1, _("Navigate"), size=wx.Size(80, -1))
        btn_nav.SetToolTip(tooltip)
        btn_nav.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnNavigate, btn=(btn_nav, choice_trck, choice_ref, txtctrl_fre)))

        # Image and tracker coordinates number controls
        for m in range(0, 7):
            for n in range(0, 3):
                self.numctrls_coord[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1))

        # Sizer to group all GUI objects
        choice_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        choice_sizer.AddMany([(choice_trck, wx.LEFT),
                              (choice_ref, wx.RIGHT)])

        coord_sizer = wx.GridBagSizer(hgap=5, vgap=5)

        for m in range(0, 7):
            coord_sizer.Add(self.btns_coord[m], pos=wx.GBPosition(m, 0))
            for n in range(0, 3):
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
        Publisher.subscribe(self.UpdateObjectState, 'Update object tracking state')
        Publisher.subscribe(self.UpdateImageCoordinates, 'Set ball reference position')
        Publisher.subscribe(self.OnDisconnectTracker, 'Disconnect tracker')
        Publisher.subscribe(self.UpdateObjectRegistration, 'Update object registration')

    def LoadImageFiducials(self, pubsub_evt):
        marker_id = pubsub_evt.data[0]
        coord = pubsub_evt.data[1]
        for n in const.BTNS_IMG_MKS:
            btn_id = const.BTNS_IMG_MKS[n].keys()[0]
            fid_id = const.BTNS_IMG_MKS[n].values()[0]
            if marker_id == fid_id and not self.btns_coord[btn_id].GetValue():
                self.btns_coord[btn_id].SetValue(True)
                self.fiducials[btn_id, :] = coord[0:3]
                for m in [0, 1, 2]:
                    self.numctrls_coord[btn_id][m].SetValue(coord[m])

    def UpdateImageCoordinates(self, pubsub_evt):
        # TODO: Change from world coordinates to matrix coordinates. They are better for multi software communication.
        self.current_coord = pubsub_evt.data
        for m in [0, 1, 2, 6]:
            if m == 6 and self.btns_coord[m].IsEnabled():
                for n in [0, 1, 2]:
                    self.numctrls_coord[m][n].SetValue(self.current_coord[n])
            elif m != 6 and not self.btns_coord[m].GetValue():
                # btn_state = self.btns_coord[m].GetValue()
                # if not btn_state:
                for n in [0, 1, 2]:
                    self.numctrls_coord[m][n].SetValue(self.current_coord[n])

    def UpdateObjectRegistration(self, pubsub_evt):
        self.obj_reg = pubsub_evt.data
        self.obj_reg_status = True

    def UpdateObjectState(self, pubsub_evt):
        self.obj_show = pubsub_evt.data

    def UpdateTriggerState(self, pubsub_evt):
        self.trigger_state = pubsub_evt.data

    def OnDisconnectTracker(self, pubsub_evt):
        if self.tracker_id:
            dt.TrackerConnection(self.tracker_id, self.trk_init[0], 'disconnect')

    def OnChoiceTracker(self, evt, ctrl):
        Publisher.sendMessage('Update status text in GUI', _("Configuring tracker ..."))
        if evt:
            choice = evt.GetSelection()
        else:
            choice = self.tracker_id

        if self.trk_init:
            trck = self.trk_init[0]
        else:
            trck = None

        # Conditions check if click was on current selection and if any other tracker
        # has been initialized before
        if trck and choice != 6:
            self.ResetTrackerFiducials()
            Publisher.sendMessage('Update status text in GUI', _("Disconnecting tracker..."))
            Publisher.sendMessage('Remove sensors ID')
            self.trk_init = dt.TrackerConnection(self.tracker_id, trck, 'disconnect')
            self.tracker_id = choice
            if not self.trk_init[0] and choice:
                Publisher.sendMessage('Update status text in GUI', _("Tracker disconnected successfully"))
                self.trk_init = dt.TrackerConnection(self.tracker_id, None, 'connect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, self.trk_init[1])
                    ctrl.SetSelection(0)
                    print "Tracker not connected!"
                else:
                    Publisher.sendMessage('Update status text in GUI', _("Ready"))
                    ctrl.SetSelection(self.tracker_id)
                    print "Tracker connected!"
        elif choice == 6:
            if trck:
                Publisher.sendMessage('Update status text in GUI', _("Disconnecting tracker ..."))
                Publisher.sendMessage('Remove sensors ID')
                self.trk_init = dt.TrackerConnection(self.tracker_id, trck, 'disconnect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, 'disconnect')
                    self.tracker_id = 0
                    ctrl.SetSelection(self.tracker_id)
                    Publisher.sendMessage('Update status text in GUI', _("Tracker disconnected"))
                    print "Tracker disconnected!"
                else:
                    Publisher.sendMessage('Update status text in GUI', _("Tracker still connected"))
                    print "Tracker still connected!"
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
                else:
                    Publisher.sendMessage('Update status text in GUI', _("Ready"))

        Publisher.sendMessage('Update tracker initializer', (self.tracker_id, self.trk_init, self.ref_mode_id))

    def OnChoiceRefMode(self, evt, ctrl):
        # When ref mode is changed the tracker coordinates are set to zero
        self.ref_mode_id = evt.GetSelection()
        self.ResetTrackerFiducials()
        # Some trackers do not accept restarting within this time window
        # TODO: Improve the restarting of trackers after changing reference mode
        # self.OnChoiceTracker(None, ctrl)
        Publisher.sendMessage('Update tracker initializer', (self.tracker_id, self.trk_init, self.ref_mode_id))
        print "Reference mode changed!"

    def OnSetImageCoordinates(self, evt):
        # FIXME: Cross does not update in last clicked slice, only on the other two
        btn_id = const.BTNS_TRK[evt.GetId()].keys()[0]

        ux, uy, uz = self.numctrls_coord[btn_id][0].GetValue(),\
                     self.numctrls_coord[btn_id][1].GetValue(),\
                     self.numctrls_coord[btn_id][2].GetValue()

        Publisher.sendMessage('Set ball reference position', (ux, uy, uz))
        # Publisher.sendMessage('Set camera in volume', (ux, uy, uz))
        Publisher.sendMessage('Co-registered points', (None, (ux, uy, uz, 0., 0., 0.)))
        Publisher.sendMessage('Update cross position', (ux, uy, uz))

    def OnImageFiducials(self, evt):
        btn_id = const.BTNS_IMG_MKS[evt.GetId()].keys()[0]
        marker_id = const.BTNS_IMG_MKS[evt.GetId()].values()[0]

        if self.btns_coord[btn_id].GetValue():
            coord = self.numctrls_coord[btn_id][0].GetValue(),\
                    self.numctrls_coord[btn_id][1].GetValue(),\
                    self.numctrls_coord[btn_id][2].GetValue()

            self.fiducials[btn_id, :] = coord[0:3]
            Publisher.sendMessage('Create marker', (coord, marker_id))
        else:
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(self.current_coord[n])

            self.fiducials[btn_id, :] = np.nan
            Publisher.sendMessage('Delete fiducial marker', marker_id)

    def OnTrackerFiducials(self, evt):
        btn_id = const.BTNS_TRK[evt.GetId()].keys()[0]
        coord = None

        if self.trk_init and self.tracker_id:
            coord_raw = dco.GetCoordinates(self.trk_init, self.tracker_id, self.ref_mode_id)
            if self.ref_mode_id:
                coord = dco.dynamic_reference(coord_raw[0, :], coord_raw[1, :])
            else:
                coord = coord_raw[0, :]

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
        txtctrl_fre = btn[3]

        self.fiducials = np.array([[10.5, 109.2, 22.],
                                   [171.9, 109.2, 22.],
                                   [91.8, 5.3, 22.],
                                   [-90.01125233, -68.99572909, -95.67216954],
                                   [-78.32915385, 76.10023779, -92.9506228],
                                   [6.00091345, 1.14540308, -61.00970923]])

        nav_id = btn_nav.GetValue()
        if nav_id:
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

                m, q1, minv = db.base_creation(self.fiducials[0:3, :])
                n, q2, ninv = db.base_creation(self.fiducials[3::, :])
                bases_coreg = (minv, n, q1, q2)

                tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id
                # FIXME: FRE is taking long to calculate so it updates on GUI delayed to navigation - I think its fixed
                # TODO: Exhibit FRE in a warning dialog and only starts navigation after user clicks ok
                fre = db.calculate_fre(self.fiducials, minv, n, q1, q2)

                txtctrl_fre.SetValue(str(round(fre, 2)))
                if fre <= 3:
                    txtctrl_fre.SetBackgroundColour('GREEN')
                else:
                    txtctrl_fre.SetBackgroundColour('RED')

                if self.trigger_state:
                    self.trigger = trig.Trigger(nav_id)

                Publisher.sendMessage("Navigation status", True)
                Publisher.sendMessage("Toggle Cross", const.SLICE_STATE_CROSS)
                Publisher.sendMessage("Hide current mask")

                if self.obj_show:
                    if self.obj_reg_status:
                        # obj_reg[0] is object 3x3 fiducial matrix and obj_reg[1] is 3x3 orientation matrix
                        obj_fiducials = self.obj_reg[0]
                        obj_orients = self.obj_reg[1]
                        obj_ref_id = self.obj_reg[2]

                        obj_center_trck, obj_sensor_trck, fiducials = db.object_registration(obj_fiducials)
                        # obj_center_img, obj_sensor_trck, m_inv_trck, obj_center_trck, obj_sensor_img = db.object_registration(obj_fiducials, bases_coreg)
                        obj_sensor_orient = obj_orients[4, :]
                        obj_data = obj_center_trck, obj_sensor_trck, obj_ref_id, fiducials

                        # Only the m_inv is needed for change of basis
                        # Publisher.sendMessage('Update object initial orientation',
                        #                       (m_inv_trck, obj_sensor_orient, obj_center_img))
                        # Publisher.sendMessage('Update object initial orientation',
                        #                       (fiducials, obj_sensor_orient))
                        if self.ref_mode_id:
                            self.correg = dcr.CoregistrationObjectDynamic(bases_coreg, nav_id, tracker_mode, obj_data)
                        else:
                            self.correg = dcr.CoregistrationObjectStatic(bases_coreg, nav_id, tracker_mode, obj_data)
                    else:
                        dlg.InvalidObjectRegistration()

                else:
                    if self.ref_mode_id:
                        self.correg = dcr.CoregistrationDynamic(bases_coreg, nav_id, tracker_mode)
                    else:
                        self.correg = dcr.CoregistrationStatic(bases_coreg, nav_id, tracker_mode)

        else:
            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn_nav.SetToolTip(tooltip)

            # Enable all navigation buttons
            choice_ref.Enable(True)
            choice_trck.Enable(True)
            for btn_c in self.btns_coord:
                btn_c.Enable(True)

            if self.trigger_state:
                self.trigger.stop()

            self.correg.stop()

            Publisher.sendMessage("Navigation status", False)

    def ResetTrackerFiducials(self):
        for m in range(3, 6):
            self.fiducials[m, :] = [np.nan, np.nan, np.nan]
            for n in range(0, 3):
                self.numctrls_coord[m][n].SetValue(0.0)


class ObjectRegistrationPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.coil_list = const.COIL

        self.nav_prop = None
        self.obj_fiducials = None
        self.obj_orients = None
        self.obj_ref_mode = None
        self.obj_name = None

        self.SetAutoLayout(1)
        self.__bind_events()

        # Button for creating new coil
        BMP_ADD = wx.Bitmap(os.path.join(const.ICON_DIR, "object_add.png"), wx.BITMAP_TYPE_PNG)
        btn_new_obj = pbtn.PlateButton(self, BTN_NEW, "", BMP_ADD,
                                           style=pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT)
        btn_new_obj.SetBackgroundColour(self.GetBackgroundColour())
        self.Bind(wx.EVT_BUTTON, self.OnLinkCreate, btn_new_obj)

        # Fixed hyperlink items
        tooltip = wx.ToolTip(_("Create new coil"))
        link_new_obj = hl.HyperLinkCtrl(self, -1, _("Create new coil"))
        link_new_obj.SetUnderlines(False, False, False)
        link_new_obj.SetBold(True)
        link_new_obj.SetColours("BLACK", "BLACK", "BLACK")
        link_new_obj.SetBackgroundColour(self.GetBackgroundColour())
        link_new_obj.SetToolTip(tooltip)
        link_new_obj.AutoBrowse(False)
        link_new_obj.UpdateLink()
        link_new_obj.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkCreate)

        # Create horizontal sizers to represent lines in the panel
        line_new = wx.BoxSizer(wx.HORIZONTAL)
        line_new.Add(link_new_obj, 1, wx.EXPAND|wx.GROW| wx.TOP|wx.RIGHT, 4)
        line_new.Add(btn_new_obj, 0, wx.ALL|wx.EXPAND|wx.GROW, 0)

        # Button for import coil
        BMP_LOAD = wx.Bitmap(os.path.join(const.ICON_DIR, "file_import.png"), wx.BITMAP_TYPE_PNG)
        btn_load_reg = pbtn.PlateButton(self, BTN_IMPORT_LOCAL, "", BMP_LOAD,
                                        style=pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT)
        btn_load_reg.SetBackgroundColour(self.GetBackgroundColour())
        self.Bind(wx.EVT_BUTTON, self.OnLinkLoad, btn_load_reg)

        # Fixed hyperlink items
        tooltip = wx.ToolTip(_("Load coil configuration file"))
        link_load_obj = hl.HyperLinkCtrl(self, -1, _("Load coil configuration"))
        link_load_obj.SetUnderlines(False, False, False)
        link_load_obj.SetBold(True)
        link_load_obj.SetColours("BLACK", "BLACK", "BLACK")
        link_load_obj.SetBackgroundColour(self.GetBackgroundColour())
        link_load_obj.SetToolTip(tooltip)
        link_load_obj.AutoBrowse(False)
        link_load_obj.UpdateLink()
        link_load_obj.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkLoad)

        # Create horizontal sizers to represent lines in the panel
        line_import = wx.BoxSizer(wx.HORIZONTAL)
        line_import.Add(link_load_obj, 1, wx.EXPAND|wx.GROW| wx.TOP|wx.RIGHT, 4)
        line_import.Add(btn_load_reg, 0, wx.ALL|wx.EXPAND|wx.GROW, 0)

        # Save button for object registration
        tooltip = wx.ToolTip(_(u"Save object registration file"))
        btn_save = wx.Button(self, -1, _(u"Save"), size=wx.Size(65, 23))
        btn_save.SetToolTip(tooltip)
        btn_save.Bind(wx.EVT_BUTTON, self.ShowSaveObjectDialog)

        # Create a horizontal sizer to represent button save
        line_save = wx.BoxSizer(wx.HORIZONTAL)
        line_save.Add(btn_save, 1, wx.LEFT| wx.TOP | wx.RIGHT, 4)

        # Change angles threshold
        text_angles = wx.StaticText(self, -1, _("Angle threshold [degrees]:"))
        spin_size_angles = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_size_angles.SetRange(1, 99)
        spin_size_angles.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_angles.Bind(wx.EVT_TEXT, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))
        spin_size_angles.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))

        # Change dist threshold
        text_dist = wx.StaticText(self, -1, _("Distance threshold [mm]:"))
        spin_size_dist = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_size_dist.SetRange(1, 99)
        spin_size_dist.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_dist.Bind(wx.EVT_TEXT, partial(self.OnSelectDistThreshold, ctrl=spin_size_dist))
        spin_size_dist.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectDistThreshold, ctrl=spin_size_dist))

        # Create a horizontal sizer to threshold configs
        line_angle_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_angle_threshold.AddMany([(text_angles, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
                                      (spin_size_angles, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)])

        line_dist_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_dist_threshold.AddMany([(text_dist, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
                                      (spin_size_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)])

        # Check box for trigger monitoring to create markers from serial port
        checkrecordcoords = wx.CheckBox(self, -1, _('Record coordinates'))
        checkrecordcoords.SetToolTip(tooltip)
        checkrecordcoords.SetValue(False)
        checkrecordcoords.Enable(0)
        checkrecordcoords.Bind(wx.EVT_CHECKBOX, partial(self.RecordCoords, ctrl=checkrecordcoords))
        self.checkrecordcoords = checkrecordcoords

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_new, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_import, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_save, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_angle_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(line_dist_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        main_sizer.Add(checkrecordcoords, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.UpdateTrackerInit, 'Update tracker initializer')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')

    def UpdateTrackerInit(self, pubsub_evt):
        self.nav_prop = pubsub_evt.data

    def UpdateNavigationStatus(self, pubsub_evt):
        nav_status = pubsub_evt.data
        if nav_status:
            self.checkrecordcoords.Enable(1)
        else:
            self.RecordCoords(nav_status, self.checkrecordcoords)
            self.checkrecordcoords.SetValue(False)
            self.checkrecordcoords.Enable(0)

    def OnSelectAngleThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update angle threshold', ctrl.GetValue())

    def OnSelectDistThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update dist threshold', ctrl.GetValue())

    def RecordCoords(self, evt, ctrl):
        if ctrl.GetValue() and evt:
            self.thr_record = rec.Record(ctrl.GetValue())
        elif ctrl.GetValue() and not evt:
            self.thr_record.stop()
        elif not ctrl.GetValue() and evt:
            self.thr_record.stop()
        elif not ctrl.GetValue() and not evt:
            None

    def OnComboCoil(self, evt):
        # coil_name = evt.GetString()
        coil_index = evt.GetSelection()
        Publisher.sendMessage('Change selected coil', self.coil_list[coil_index][1])

    def OnLinkCreate(self, event=None):

        if self.nav_prop:
            dialog = dlg.ObjectCalibrationDialog(self.nav_prop)
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name = dialog.GetValue()
                    if np.isfinite(self.obj_fiducials).all() and np.isfinite(self.obj_orients).all():
                        Publisher.sendMessage('Update object registration',
                                              (self.obj_fiducials, self.obj_orients, self.obj_ref_mode))
                        Publisher.sendMessage('Create object polydata', self.obj_name)
                        Publisher.sendMessage('Update status text in GUI', _("Ready"))

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

            Publisher.sendMessage('Update object registration',
                                  (self.obj_fiducials, self.obj_orients, self.obj_ref_mode))
            Publisher.sendMessage('Create object polydata', self.obj_name)
            Publisher.sendMessage('Update status text in GUI', _("Ready"))
        else:
            wx.MessageBox(_("InVesalius was not able to import this registration file"), _("Import error"))

    def ShowSaveObjectDialog(self, evt):
        if np.isnan(self.obj_fiducials).any() or np.isnan(self.obj_orients).any():
            wx.MessageBox(_("Digitize all object fiducials before saving"), _("Save error"))
        else:
            filename = dlg.ShowSaveRegistrationDialog("object_registration.obr")
            hdr = 'Object' + "\t" + self.obj_name + "\t" + 'Reference' + "\t" + str('%d' % self.obj_ref_mode)
            data = np.hstack([self.obj_fiducials, self.obj_orients])
            np.savetxt(filename, data, fmt='%.4f', delimiter='\t', newline='\n', header=hdr)


class MarkersPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.__bind_events()

        self.current_coord = 0, 0, 0
        self.current_angle = 0, 0, 0
        self.list_coord = []
        self.marker_ind = 0
        self.tgt_flag = self.tgt_index = None
        self.nav_status = False

        self.marker_colour = (0.0, 0.0, 1.)
        self.marker_size = 4

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
        self.lc.SetColumnWidth(4, 50)
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
        Publisher.subscribe(self.UpdateCurrentCoord, 'Set ball reference position')
        Publisher.subscribe(self.UpdateCurrentAngle, 'Co-registered points')
        Publisher.subscribe(self.OnDeleteSingleMarker, 'Delete fiducial marker')
        Publisher.subscribe(self.OnCreateMarker, 'Create marker')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')

    def UpdateCurrentCoord(self, pubsub_evt):
        self.current_coord = pubsub_evt.data

    def UpdateCurrentAngle(self, pubsub_evt):
        self.current_angle = pubsub_evt.data[1][3:]

    def UpdateNavigationStatus(self, pubsub_evt):
        if pubsub_evt.data is False:
            sleep(0.5)
            self.current_angle = 0, 0, 0
            self.nav_status = False
        else:
            self.nav_status = True

    def OnMouseRightDown(self, evt):
        self.OnListEditMarkerId(self.nav_status)

    def OnListEditMarkerId(self, status):
        menu_id = wx.Menu()
        edit_id = menu_id.Append(0, _('Edit ID'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuEditMarkerId, edit_id)
        target_menu = menu_id.Append(1, _('Set as target'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuSetTarget, target_menu)
        target_menu.Enable(status)
        self.PopupMenu(menu_id)
        menu_id.Destroy()

    def OnItemBlink(self, evt):
        Publisher.sendMessage('Blink Marker', self.lc.GetFocusedItem())

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
        self.lc.SetStringItem(list_index, 4, id_label)
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
            Publisher.sendMessage('Set target transparency', [False, self.tgt_index])
            self.lc.SetStringItem(self.tgt_index, 4, '')
            # Add the new ID to exported list
            if len(self.list_coord[self.tgt_index]) > 8:
                self.list_coord[self.tgt_index][10] = str('')
            else:
                self.list_coord[self.tgt_index][7] = str('')

        self.tgt_index = self.lc.GetFocusedItem()
        self.lc.SetItemBackgroundColour(self.tgt_index, 'RED')
        Publisher.sendMessage('Update target', self.list_coord[self.tgt_index])
        Publisher.sendMessage('Set target transparency', [True, self.tgt_index])
        Publisher.sendMessage('Disable or enable coil tracker', True)
        self.OnMenuEditMarkerId('TARGET')
        self.tgt_flag = True
        dlg.NewTarget()

    def OnDeleteAllMarkers(self, pubsub_evt):
        result = dlg.DeleteAllMarkers()
        if result == wx.ID_OK:
            self.list_coord = []
            self.marker_ind = 0
            Publisher.sendMessage('Remove all markers', self.lc.GetItemCount())
            self.lc.DeleteAllItems()
            Publisher.sendMessage('Stop Blink Marker', 'DeleteAll')

            if self.tgt_flag:
                self.tgt_flag = self.tgt_index = None
                Publisher.sendMessage('Disable or enable coil tracker', False)
                dlg.DeleteTarget()

    def OnDeleteSingleMarker(self, evt):
        # OnDeleteSingleMarker is used for both pubsub and button click events
        # Pubsub is used for fiducial handle and button click for all others

        if hasattr(evt, 'data'):
            marker_id = evt.data
            if self.lc.GetItemCount():
                for id_n in range(self.lc.GetItemCount()):
                    item = self.lc.GetItem(id_n, 4)
                    if item.GetText() == marker_id:
                        for i in const.BTNS_IMG_MKS:
                            if marker_id in const.BTNS_IMG_MKS[i].values()[0]:
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
                Publisher.sendMessage('Disable or enable coil tracker', False)
                dlg.DeleteTarget()
            self.DeleteMarker(index)
        else:
            dlg.NoMarkerSelected()

    def DeleteMarker(self, index):
        for i in reversed(index):
            del self.list_coord[i]
            self.lc.DeleteItem(i)
            for n in range(0, self.lc.GetItemCount()):
                self.lc.SetStringItem(n, 0, str(n+1))
            self.marker_ind -= 1
        Publisher.sendMessage('Remove marker', index)

    def OnCreateMarker(self, evt):
        # OnCreateMarker is used for both pubsub and button click events
        # Pubsub is used for markers created with fiducial buttons, trigger and create marker button
        if hasattr(evt, 'data'):
            if evt.data is not None:
                self.CreateMarker(evt.data[0], (0.0, 1.0, 0.0), self.marker_size, evt.data[1])
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
                        coord = float(line[0]), float(line[1]), float(line[2])
                        colour = float(line[6]), float(line[7]), float(line[8])
                        size = float(line[9])

                        if len(line) == 11:
                            for i in const.BTNS_IMG_MKS:
                                if line[10] in const.BTNS_IMG_MKS[i].values()[0]:
                                    Publisher.sendMessage('Load image fiducials', (line[10], coord))
                                elif line[10] == 'TARGET':
                                    target = count_line
                        else:
                            line.append("")

                        self.CreateMarker(coord, colour, size, line[10])
                        if target is not None:
                            self.OnMenuSetTarget(target)

                    else:
                        coord = float(line[0]), float(line[1]), float(line[2])
                        colour = float(line[3]), float(line[4]), float(line[5])
                        size = float(line[6])

                        if len(line) == 8:
                            for i in const.BTNS_IMG_MKS:
                                if line[7] in const.BTNS_IMG_MKS[i].values()[0]:
                                    Publisher.sendMessage('Load image fiducials', (line[7], coord))
                        else:
                            line.append("")
                        self.CreateMarker(coord, colour, size, line[7])
                    count_line += 1
            except:
                dlg.InvalidMarkersFile()

    def OnMarkersVisibility(self, evt, ctrl):

        if ctrl.GetValue():
            Publisher.sendMessage('Hide all markers',  self.lc.GetItemCount())
            ctrl.SetLabel('Show')
        else:
            Publisher.sendMessage('Show all markers',  self.lc.GetItemCount())
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

        Publisher.sendMessage('Add marker', (self.marker_ind, size, colour,  coord))

        self.marker_ind += 1

        # List of lists with coordinates and properties of a marker

        line = [coord[0], coord[1], coord[2], self.current_angle[0], self.current_angle[1], self.current_angle[2], colour[0], colour[1], colour[2], size, marker_id]

        # Adding current line to a list of all markers already created
        if not self.list_coord:
            self.list_coord = [line]
        else:
            self.list_coord.append(line)

        # Add item to list control in panel
        num_items = self.lc.GetItemCount()
        self.lc.InsertStringItem(num_items, str(num_items + 1))
        self.lc.SetStringItem(num_items, 1, str(round(coord[0], 2)))
        self.lc.SetStringItem(num_items, 2, str(round(coord[1], 2)))
        self.lc.SetStringItem(num_items, 3, str(round(coord[2], 2)))
        self.lc.SetStringItem(num_items, 4, str(marker_id))
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
