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

import numpy as np
import wx
import wx.lib.hyperlink as hl
import wx.lib.masked.numctrl
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.bases as db
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.trackers as dt
import invesalius.data.trigger as trig
import invesalius.gui.dialogs as dlg
import invesalius.gui.widgets.foldpanelbar as fpb
import invesalius.gui.widgets.colourselect as csel

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

        # Fold panel and its style settings
        # FIXME: If we dont insert a value in size or if we set wx.DefaultSize,
        # the fold_panel doesnt show. This means that, for some reason, Sizer
        # is not working properly in this panel. It might be on some child or
        # parent panel. Perhaps we need to insert the item into the sizer also...
        # Study this.

        fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                      (10, 293), 0, fpb.FPB_SINGLE_FOLD)

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Navigation panel
        item = fold_panel.AddFoldPanel(_("Neuronavigation"), collapsed=True)
        ntw = NeuronavigationPanel(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        # Fold 2 - Markers panel
        item = fold_panel.AddFoldPanel(_("Extra tools"), collapsed=True)
        mtw = MarkersPanel(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, mtw, Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)


        # Check box for camera update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Update camera in volume"))
        checkcamera = wx.CheckBox(self, -1, _('Volume camera'))
        checkcamera.SetToolTip(tooltip)
        checkcamera.SetValue(True)
        checkcamera.Bind(wx.EVT_CHECKBOX, partial(self.UpdateVolumeCamera, ctrl=checkcamera))

        # Check box for camera update in volume rendering during navigation
        tooltip = wx.ToolTip(_("Enable external trigger for creating markers"))
        checktrigger = wx.CheckBox(self, -1, _('External trigger'))
        checktrigger.SetToolTip(tooltip)
        checktrigger.SetValue(False)
        checktrigger.Bind(wx.EVT_CHECKBOX, partial(self.UpdateExternalTrigger, ctrl=checktrigger))

        if sys.platform != 'win32':
            checkcamera.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
            checktrigger.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        line_sizer = wx.BoxSizer(wx.HORIZONTAL)
        line_sizer.Add(checkcamera, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Add(checktrigger, 1,wx.ALIGN_RIGHT | wx.RIGHT | wx.LEFT, 5)
        line_sizer.Fit(self)

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 0, wx.GROW|wx.EXPAND)
        sizer.Add(line_sizer, 1, wx.GROW | wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

    def UpdateExternalTrigger(self, evt, ctrl):
        Publisher.sendMessage('Update trigger state', ctrl.GetValue())

    def UpdateVolumeCamera(self, evt, ctrl):
        Publisher.sendMessage('Update volume camera state', ctrl.GetValue())




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
            self.btns_coord[n] = wx.ToggleButton(self, k, label=lab, size=wx.Size(30, 23))
            self.btns_coord[n].SetToolTip(tips_img[n])
            self.btns_coord[n].Bind(wx.EVT_TOGGLEBUTTON, self.OnImageFiducials)

        # Push buttons for tracker fiducials
        btns_trk = const.BTNS_TRK
        tips_trk = const.TIPS_TRK

        for k in btns_trk:
            n = btns_trk[k].keys()[0]
            lab = btns_trk[k].values()[0]
            self.btns_coord[n] = wx.Button(self, k, label=lab, size=wx.Size(30, 23))
            self.btns_coord[n].SetToolTip(tips_trk[n-3])
            # Excepetion for event of button that set image coordinates
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

        # Sizers to group all GUI objects
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
        Publisher.subscribe(self.UpdateImageCoordinates, 'Set ball reference position')
        Publisher.subscribe(self.OnDisconnectTracker, 'Disconnect tracker')
        Publisher.subscribe(self.OnStylusButton, 'PLH Stylus Button On')

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

    def UpdateTriggerState (self, pubsub_evt):
        self.trigger_state = pubsub_evt.data

    def OnDisconnectTracker(self, pubsub_evt):
        if self.tracker_id:
            dt.TrackerConnection(self.tracker_id, 'disconnect')

    def OnStylusButton(self, pubsub_evt):
        if self.trigger_state:
            Publisher.sendMessage('Create marker')

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
            self.trk_init = dt.TrackerConnection(self.tracker_id, 'disconnect')
            self.tracker_id = choice
            if not self.trk_init[0]:
                self.trk_init = dt.TrackerConnection(self.tracker_id, 'connect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, self.trk_init[1])
                    ctrl.SetSelection(0)
                    print "Tracker not connected!"
                else:
                    ctrl.SetSelection(self.tracker_id)
                    print "Tracker connected!"
        elif choice == 6:
            if trck:
                self.trk_init = dt.TrackerConnection(self.tracker_id, 'disconnect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, 'disconnect')
                    self.tracker_id = 0
                    ctrl.SetSelection(self.tracker_id)
                    print "Tracker disconnected!"
                else:
                    print "Tracker still connected!"
            else:
                ctrl.SetSelection(self.tracker_id)

        else:
            # If trk_init is None try to connect. If doesn't succeed show dialog.
            if choice:
                self.tracker_id = choice
                self.trk_init = dt.TrackerConnection(self.tracker_id, 'connect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, self.trk_init[1])
                    self.tracker_id = 0
                    ctrl.SetSelection(self.tracker_id)
        Publisher.sendMessage('Update status text in GUI', _("Ready"))

    def OnChoiceRefMode(self, evt, ctrl):
        # When ref mode is changed the tracker coords are set to zero
        self.ref_mode_id = evt.GetSelection()
        self.ResetTrackerFiducials()
        # Some trackers do not accept restarting within this time window
        # TODO: Improve the restarting of trackers after changing reference mode
        # self.OnChoiceTracker(None, ctrl)
        print "Reference mode changed!"

    def OnSetImageCoordinates(self, evt):
        # FIXME: Cross does not update in last clicked slice, only on the other two
        btn_id = const.BTNS_TRK[evt.GetId()].keys()[0]

        wx, wy, wz = self.numctrls_coord[btn_id][0].GetValue(), \
                     self.numctrls_coord[btn_id][1].GetValue(), \
                     self.numctrls_coord[btn_id][2].GetValue()

        Publisher.sendMessage('Set ball reference position', (wx, wy, wz))
        Publisher.sendMessage('Set camera in volume', (wx, wy, wz))
        Publisher.sendMessage('Co-registered points', (wx, wy, wz))
        Publisher.sendMessage('Update cross position', (wx, wy, wz))

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
            coord = dco.GetCoordinates(self.trk_init, self.tracker_id, self.ref_mode_id)
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

        nav_id = btn_nav.GetValue()
        if nav_id:
            if np.isnan(self.fiducials).any():
                dlg.InvalidFiducials()
                btn_nav.SetValue(False)

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

                Publisher.sendMessage("Navigation Status", True)
                Publisher.sendMessage("Toggle Cross", const.SLICE_STATE_CROSS)
                Publisher.sendMessage("Hide current mask")

                self.correg = dcr.Coregistration((minv, n, q1, q2), nav_id, tracker_mode)

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

            Publisher.sendMessage("Navigation Status", False)

    def ResetTrackerFiducials(self):
        for m in range(3, 6):
            for n in range(0, 3):
                self.numctrls_coord[m][n].SetValue(0.0)


class MarkersPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.__bind_events()

        self.current_coord = 0, 0, 0
        self.list_coord = []
        self.marker_ind = 0

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

        btn_delete_all = wx.Button(self, -1, label=_('Delete all markers'), size=wx.Size(135, 23))
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
        self.lc.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnListEditMarkerId)

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
        Publisher.subscribe(self.OnDeleteSingleMarker, 'Delete fiducial marker')
        Publisher.subscribe(self.OnCreateMarker, 'Create marker')

    def UpdateCurrentCoord(self, pubsub_evt):
        self.current_coord = pubsub_evt.data

    def OnListEditMarkerId(self, evt):
        menu_id = wx.Menu()
        menu_id.Append(-1, _('Edit ID'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuEditMarkerId)
        self.PopupMenu(menu_id)
        menu_id.Destroy()

    def OnMenuEditMarkerId(self, evt):
        id_label = dlg.EnterMarkerID(self.lc.GetItemText(self.lc.GetFocusedItem(), 4))
        list_index = self.lc.GetFocusedItem()
        self.lc.SetStringItem(list_index, 4, id_label)
        # Add the new ID to exported list
        self.list_coord[list_index][7] = str(id_label)

    def OnDeleteAllMarkers(self, pubsub_evt):
        self.list_coord = []
        self.marker_ind = 0
        Publisher.sendMessage('Remove all markers', self.lc.GetItemCount())
        self.lc.DeleteAllItems()

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
                self.DeleteMarker()
        else:
            if self.lc.GetFocusedItem() is not -1:
                self.DeleteMarker()
            elif not self.lc.GetItemCount():
                pass
            else:
                dlg.NoMarkerSelected()

    def DeleteMarker(self):
        index = self.lc.GetFocusedItem()
        del self.list_coord[index]
        self.lc.DeleteItem(index)
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
                content = [s.rstrip() for s in open(filepath)]
                for data in content:
                    line = [s for s in data.split()]
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
                properties = str('%.3f' %list_slice1[3]) + "\t" + str('%.3f' %list_slice1[4]) + "\t" + str('%.3f' %list_slice1[5]) + "\t" + str('%.1f' %list_slice1[6]) + "\t" + list_slice1[7]
                line = coord + "\t" + properties + "\n"
                list_slice = self.list_coord[1:]

                for value in list_slice:
                    coord = str('%.3f' %value[0]) + "\t" + str('%.3f' %value[1]) + "\t" + str('%.3f' %value[2])
                    properties = str('%.3f' %value[3]) + "\t" + str('%.3f' %value[4]) + "\t" + str('%.3f' %value[5]) + "\t" + str('%.1f' %value[6]) + "\t" + value[7]
                    line = line + coord + "\t" + properties + "\n"

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
        line = [coord[0], coord[1], coord[2], colour[0], colour[1], colour[2], self.marker_size, marker_id]

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
