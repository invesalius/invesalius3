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

import numpy as np
import wx
import wx.lib.hyperlink as hl
import wx.lib.masked.numctrl
import wx.lib.platebtn as pbtn
from functools import partial
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.bases as db
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.tms_trigger as tms
import invesalius.data.trackers as dt
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
        self.SetAutoLayout(1)

        txt_nav = wx.StaticText(self, -1, _('Select fiducials and navigate'),
                                size=wx.Size(90, 20))

        # Create horizontal sizer to represent lines in the panel
        txt_sizer = wx.BoxSizer(wx.HORIZONTAL)
        txt_sizer.Add(txt_nav, 1, wx.EXPAND|wx.GROW, 5)

        # Fold panel which contains navigation configurations
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)

        # Add line sizer into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(txt_sizer, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 5)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

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
        fold_panel.AddFoldPanelWindow(item, ntw, Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        # Fold 2 - Markers panel
        item = fold_panel.AddFoldPanel(_("Extra tools"), collapsed=True)
        mtw = MarkersPanel(item)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, mtw, Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class NeuronavigationPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.__bind_events()

        self.aux_img_ref1 = 0
        self.aux_img_ref2 = 0
        self.aux_img_ref3 = 0
        self.aux_img__T_ref = 0
        self.aux_trck_ref1 = 0
        self.aux_trck_ref2 = 0
        self.aux_trck_ref3 = 0
        self.aux_trck1 = 0
        self.aux_trck2 = 0
        self.aux_trck3 = 0
        self.current_coord = 0, 0, 0
        self.coord1a = (0, 0, 0)
        self.coord2a = (0, 0, 0)
        self.coord3a = (0, 0, 0)
        self.coord1b = (0, 0, 0)
        self.coord2b = (0, 0, 0)
        self.coord3b = (0, 0, 0)
        self.correg = None
        self.filename = None
        self.c1 = None

        self.fiducials = np.full([6, 3], np.nan)

        self.tracker_id = const.DEFAULT_TRACKER
        self.ref_mode_id = const.DEFAULT_REF_MODE

        self.trk_init = None

        # Initialize list of buttons and numctrls for wx objects
        self.btns_coord = [None] * 7
        self.numctrls_coord = [list(), list(), list(), list(), list(), list(), list()]

        # ComboBox for spatial tracker device selection
        tooltip = wx.ToolTip(_("Choose the tracking device"))
        self.choice_trck = wx.ComboBox(self, -1, "",
                                       choices=const.TRACKER, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        self.choice_trck.SetToolTip(tooltip)
        self.choice_trck.SetSelection(const.DEFAULT_TRACKER)
        self.choice_trck.Bind(wx.EVT_COMBOBOX, self.OnChoiceTracker)

        # ComboBox for tracker reference mode
        tooltip = wx.ToolTip(_("Choose the navigation reference mode"))
        self.choice_ref = wx.ComboBox(self, -1, "",
                                      choices=const.REF_MODE, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        self.choice_ref.SetSelection(const.DEFAULT_REF_MODE)
        self.choice_ref.SetToolTip(tooltip)
        self.choice_ref.Bind(wx.EVT_COMBOBOX, self.OnChoiceRefMode)

        # Toggle buttons for image fiducials
        btns_img = const.BTNS_IMG
        tips_img = const.TIPS_IMG

        for k in btns_img:
            n = btns_img[k].keys()[0]
            lab = btns_img[k].values()[0]
            # Excepetion for reference coordinate in tooltips dictionary
            p = n
            if p == 6:
                p = 3
            self.btns_coord[n] = wx.ToggleButton(self, k, label=lab, size=wx.Size(30, 23))
            self.btns_coord[n].SetToolTip(tips_img[p])
            self.btns_coord[n].Bind(wx.EVT_TOGGLEBUTTON, self.OnImageFiducials)
            # self.btns_coord[n].Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnImageFiducials, num_ctrl=self.numctrls_coord))

        # Push buttons for tracker fiducials
        btns_trk = const.BTNS_TRK
        tips_trk = const.TIPS_TRK

        for k in btns_trk:
            n = btns_trk[k].keys()[0]
            lab = btns_trk[k].values()[0]
            self.btns_coord[n] = wx.Button(self, k, label=lab, size=wx.Size(30, 23))
            self.btns_coord[n].SetToolTip(tips_trk[n-3])
            self.btns_coord[n].Bind(wx.EVT_BUTTON, self.OnTrackerFiducials)
            # self.btns_coord[n].Bind(wx.EVT_BUTTON, partial(self.OnTrackerFiducials, num_ctrl=self.numctrls_coord))

        # Toggle button for neuronavigation
        tooltip = wx.ToolTip(_("Start navigation"))
        btn_nav = wx.ToggleButton(self, -1, _("Neuronavigate"))
        btn_nav.SetToolTip(tooltip)
        btn_nav.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnNavigate, btn=btn_nav))

        # Target registration error text box
        tooltip = wx.ToolTip(_("Target registration error"))
        self.txtctrl_tre = wx.TextCtrl(self, value="")
        self.txtctrl_tre.SetEditable(0)
        self.txtctrl_tre.SetToolTip(tooltip)

        for m in range(0, 7):
            for n in range(0, 3):
                self.numctrls_coord[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1))

        choice_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        choice_sizer.AddMany([(self.choice_trck, wx.LEFT),
                              (self.choice_ref, wx.RIGHT)])

        coord_sizer = wx.GridBagSizer(hgap=5, vgap=5)

        for m in range(0, 7):
            coord_sizer.Add(self.btns_coord[m], pos=wx.GBPosition(m, 0))
            for n in range(0, 3):
                coord_sizer.Add(self.numctrls_coord[m][n], pos=wx.GBPosition(m, n+1))
                if m in [3, 4, 5]:
                    self.numctrls_coord[m][n].SetEditable(False)

        nav_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        nav_sizer.AddMany([(self.txtctrl_tre, wx.LEFT|wx.RIGHT),
                           (btn_nav, wx.LEFT|wx.RIGHT)])

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
        Publisher.subscribe(self.UpdateImageCoordinates, 'Update cross position')
        Publisher.subscribe(self.LoadImageFiducials, 'Load Fiducials')

    def UpdateImageCoordinates(self, pubsub_evt):

        self.current_coord = pubsub_evt.data

        for m in [0, 1, 2, 6]:
            btn_state = self.btns_coord[m].GetValue()
            if not btn_state:
                for n in [0, 1, 2]:
                    self.numctrls_coord[m][n].SetValue(self.current_coord[n])

    def LoadImageFiducials(self, pubsub_evt):
        marker_id = pubsub_evt.data[0]
        coord = pubsub_evt.data[1]
        for n in const.BTNS_IMG:
            btn_id = const.BTNS_IMG[n].keys()[0]
            fid_id = const.BTNS_IMG[n].values()[0]
            if marker_id == fid_id and not self.btns_coord[btn_id].GetValue():
                self.btns_coord[btn_id].SetValue(True)
                for n in [0, 1, 2]:
                    self.numctrls_coord[btn_id][n].SetValue(coord[n])

    def OnImageFiducials(self, evt):
        btn_id = const.BTNS_IMG[evt.GetId()].keys()[0]
        marker_id = const.BTNS_IMG[evt.GetId()].values()[0]
        if self.btns_coord[btn_id].GetValue():
            coord = self.numctrls_coord[btn_id][0].GetValue(),\
                    self.numctrls_coord[btn_id][1].GetValue(),\
                    self.numctrls_coord[btn_id][2].GetValue()
            self.fiducials[btn_id, :] = coord
            Publisher.sendMessage('Create fiducial markers', (coord, marker_id))
        else:
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(self.current_coord[n])
            self.fiducials[btn_id, :] = np.nan
            Publisher.sendMessage('Delete fiducial marker', marker_id)

            # This is how it was done before for each button
            # self.coord1a = x, y, z
            # self.aux_img_ref1 = 1
            # Publisher.sendMessage("Create fiducial markers", (self.coord1a, "LTI"))

            # This was done to allow user writes the image coords
            # xflag = self.numctrls_coord[n][0].GetValue() != round(x, 1)
            # yflag = self.numctrls_coord[n][1].GetValue() != round(y, 1)
            # zflag = self.numctrls_coord[n][2].GetValue() != round(z, 1)
            # if xflag or yflag or zflag:
            #     coord = self.numctrls_coord[n][0].GetValue(), self.numctrls_coord[n][1].GetValue(), \
            #             self.numctrls_coord[n][2].GetValue()
            #     if btn_id == IR1:
            #         self.coord1a = coord
            #         Publisher.sendMessage('Set camera in volume', self.coord1a[0:3])
            #         Publisher.sendMessage('Co-registered Points', self.coord1a)
            #         self.aux_img_ref1 = 1
            #         Publisher.sendMessage("Create fiducial markers", (self.coord1a, "LTI"))
            #     elif btn_id == IR2:
            #         self.coord2a = coord
            #         Publisher.sendMessage('Set camera in volume', self.coord2a[0:3])
            #         Publisher.sendMessage('Co-registered Points', self.coord2a)
            #         self.aux_img_ref2 = 1
            #         Publisher.sendMessage("Create fiducial markers", (self.coord2a, "RTI"))
            #     elif btn_id == IR3:
            #         self.coord3a = coord
            #         Publisher.sendMessage('Set camera in volume', self.coord3a[0:3])
            #         Publisher.sendMessage('Co-registered Points', self.coord3a)
            #         self.aux_img_ref3 = 1
            #         Publisher.sendMessage("Create fiducial markers", (self.coord3a, "NI"))
            #     elif btn_id == T:
            #         self.img_T = coord
            #         Publisher.sendMessage('Set camera in volume', self.img_T[0:3])
            #         Publisher.sendMessage('Co-registered Points', self.img_T)
            #         self.aux_img__T_ref = 1
            #         self.coordT = np.array([coord])

    def OnTrackerFiducials(self, evt):
        btn_id = const.BTNS_TRK[evt.GetId()].keys()[0]
        coord = None
        if self.trk_init and self.tracker_id:
            coord = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
            # This is how it was done before for each button
            # self.aux_trck_ref1 = 1
            # self.coord1b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
            # coord = self.coord1b[0:3]
        else:
            dlg.TrackerNotConnected(self.tracker_id)

        # Update number controls with tracker coordinates
        if coord:
            self.fiducials[btn_id, :] = coord
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(coord[n])

    def OnNavigate(self, evt, btn):
        nav_id = btn.GetValue()
        if nav_id:
            if np.isnan(self.fiducials).any():
                tooltip = wx.ToolTip(_("Stop neuronavigation"))
                btn.SetToolTip(tooltip)

                # Disable all navigation buttons
                self.choice_ref.Enable(False)
                self.choice_trck.Enable(False)
                for btn_c in self.btns_coord:
                    btn_c.Enable(False)

                M, q1, Minv = db.base_creation(self.fiducials[0:3, :])
                N, q2, Ninv = db.base_creation(self.fiducials[3::, :])

                tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id
                self.Calculate_FRE(Minv, N, q1, q2)
                self.correg = dcr.Coregistration((Minv, N, q1, q2), nav_id, tracker_mode)
                self.TMS = tms.Trigger(nav_id)
            else:
                dlg.InvalidFiducials()
                btn.SetValue(False)
        elif not nav_id:
            self.correg.stop()
            self.TMS.stop()

            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn.SetToolTip(tooltip)

            # Enable all navigation buttons
            self.choice_ref.Enable(True)
            self.choice_trck.Enable(True)
            for btn_c in self.btns_coord:
                btn_c.Enable(True)

    def Calculate_FRE(self, Minv, N, q1, q2):
        fids = self.fiducials

        p1 = np.matrix(fids[3, :].reshape(3, 1))
        p2 = np.matrix(fids[4, :].reshape(3, 1))
        p3 = np.matrix(fids[5, :].reshape(3, 1))

        img1 = q1 + (Minv * N) * (p1 - q2)
        img2 = q1 + (Minv * N) * (p2 - q2)
        img3 = q1 + (Minv * N) * (p3 - q2)

        ED1=np.sqrt((((img1[0]-self.coord1a[0])**2) + ((img1[1]-self.coord1a[1])**2) +((img1[2]-self.coord1a[2])**2)))
        ED2=np.sqrt((((img2[0]-self.coord2a[0])**2) + ((img2[1]-self.coord2a[1])**2) +((img2[2]-self.coord2a[2])**2)))
        ED3=np.sqrt((((img3[0]-self.coord3a[0])**2) + ((img3[1]-self.coord3a[1])**2) +((img3[2]-self.coord3a[2])**2)))

        FRE = float(np.sqrt((ED1**2 + ED2**2 + ED3**2)/3))


        self.txtctrl_tre.SetValue("FRE: " + str(round(FRE, 2)))
        if FRE <= 3:
            self.txtctrl_tre.SetBackgroundColour('GREEN')
        else:
            self.txtctrl_tre.SetBackgroundColour('RED')

    def OnChoiceTracker(self, evt):
        # this condition check if the trackers is already connected and disconnect this tracker
        # for PATRIOT it is trying to check serial connection forever... put timeout
        if (self.tracker_id == evt.GetSelection()) and (self.trk_init is not None) and (self.tracker_id != 0):
            dlg.TrackerAlreadyConnected()
            self.tracker_rem_id = self.tracker_id
            self.RemoveTracker()
            self.choice_trck.SetSelection(0)
            self.SetTrackerFiducialsNone()
            self.tracker_id = 0
        else:
            self.tracker_id = evt.GetSelection()
            if self.tracker_id != 0:
                trck = {1 : dt.Tracker().ClaronTracker,
                        2 : dt.Tracker().PlhFastrak,
                        3 : dt.Tracker().PlhIsotrakII,
                        4 : dt.Tracker().PlhPatriot}
                self.tracker_rem_id = self.tracker_id
                self.trk_init = trck[self.tracker_id]()
                if self.trk_init is None:
                    self.RemoveTracker()
                    self.choice_trck.SetSelection(0)
                    self.tracker_id = 0
                    self.tracker_rem_id = 0
                    self.SetTrackerFiducialsNone()
                else:
                    print "Tracker changed!"
            else:
                try:
                    self.RemoveTracker()
                    self.tracker_rem_id = 0
                except:
                    print "No tracker connected"
                self.SetTrackerFiducialsNone()
                print "Select Tracker"

    def RemoveTracker(self):
        remove_trck = {1: dt.RemoveTracker().ClaronTracker,
                       2: dt.RemoveTracker().PlhFastrak,
                       3: dt.RemoveTracker().PlhIsotrakII,
                       4: dt.RemoveTracker().PlhPatriot}
        rem = remove_trck[self.tracker_rem_id]()
        self.trk_init = None

    def OnChoiceRefMode(self, evt):
        self.ref_mode_id = evt.GetSelection()
        print "Ref_Mode changed!"
        #When ref mode is changed the tracker coords are set as null, self.aux_trck is the flag that sets it
        self.SetTrackerFiducialsNone()

    def SetTrackerFiducialsNone(self):
        for i in range(3, 6):
            for j in range(0, 3):
                self.numctrls_coord[i][j].SetValue(0)

        self.aux_trck1 = 0
        self.aux_trck2 = 0
        self.aux_trck3 = 0


class MarkersPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)
        
        self.ijk = 0, 0, 0
        self.flagpoint1 = 0
        self.ballid = 0
        self.colour = 0.0, 0.0, 1.0
        self.fiducial_color = 0.0, 1.0, 0.0
        self.fiducial_flag = 0
        self.fiducial_ID = ""

        ##LINE 1
        # Change marker size
        spin_marker_size = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_marker_size.SetRange(1, 99)
        spin_marker_size.SetValue(const.MARKER_SIZE)
        # spin_marker_size.Bind(wx.EVT_TEXT, self.OnMarkerSize)
        self.spin = spin_marker_size

        # Marker colour
        marker_colour = csel.ColourSelect(self, -1, colour=(0, 0, 255), size=wx.Size(20, 23))
        marker_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.marker_colour = marker_colour

        create_markers = wx.Button(self, -1, label=_('Create marker'), size=wx.Size(135, 23))
        create_markers.Bind(wx.EVT_BUTTON, self.OnCreateMarker)

        line1 = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        line1.AddMany([(spin_marker_size, 1),
                       (marker_colour, 0),
                       (create_markers, 0)])

        ## LINE 2
        save_markers = wx.Button(self, -1, label=_('Save'), size=wx.Size(65, 23))
        save_markers.Bind(wx.EVT_BUTTON, self.OnSaveMarkers)

        load_markers = wx.Button(self, -1, label=_('Load'), size=wx.Size(65, 23))
        load_markers.Bind(wx.EVT_BUTTON, self.OnLoadMarkers)

        self.markers_visibility = wx.ToggleButton(self, -1, _("Hide"), size=wx.Size(65, 23))
        self.markers_visibility.Bind(wx.EVT_TOGGLEBUTTON, self.OnMarkersVisibility)

        line2 = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        line2.AddMany([(save_markers, 1, wx.RIGHT),
                       (load_markers, 0, wx.LEFT | wx.RIGHT),
                       (self.markers_visibility, 0, wx.LEFT)])

        ## Line 3
        del_s_markers = wx.Button(self, -1, label=_('Remove'), size=wx.Size(65, 23))
        del_s_markers.Bind(wx.EVT_BUTTON, self.DelSingleMarker)

        del_markers = wx.Button(self, -1, label=_('Delete all markers'), size=wx.Size(135, 23))
        del_markers.Bind(wx.EVT_BUTTON, self.OnDelMarker)

        line3 = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        line3.AddMany([(del_s_markers, 1, wx.RIGHT),
                       (del_markers, 0, wx.LEFT)])

        ##ListCtrl
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
        self.lc.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.menu)
        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(line1, 0, wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        sizer.Add(line2, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        sizer.Add(line3, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        sizer.Add(self.lc, 0, wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.GetPoint, 'Update cross position')
        Publisher.subscribe(self.DelSingleMarker, 'Delete fiducial marker')
        Publisher.subscribe(self.Fiducial_markers, 'Create fiducial markers')
        Publisher.subscribe(self.OnCreateMarker, 'Create markers')

    def menu(self, evt):
        menu = wx.Menu()
        menu.Append(-1, _('Edit ID'))
        menu.Bind(wx.EVT_MENU, self.EditID)
        self.PopupMenu(menu)
        menu.Destroy()

    def EditID(self,evt):
        ID = dlg.EnterMarkerID(self.lc.GetItemText(self.lc.GetFocusedItem(), 4))
        index = self.lc.GetFocusedItem()
        self.lc.SetStringItem(index, 4, ID)
        #add the new ID to exported list
        self.list_coord[index][7] = str(ID)

    def Fiducial_markers(self, pubsub_evt):
        coord = pubsub_evt.data[0]
        self.fiducial_ID = pubsub_evt.data[1]
        self.fiducial_flag = 1
        self.CreateMarker(coord,self.fiducial_color, self.spin.GetValue())

    def CreateMarker(self, coord_data, colour_data, size_data):
        #Create a file and write the points given by getpoint's button 
        coord = coord_data
        colour = colour_data
        size = size_data

        Publisher.sendMessage('Add marker', (self.ballid, size, colour,  coord))
        self.ballid = self.ballid + 1
        #sum 1 for each coordinate to matlab comprehension
        #coord = coord[0] + 1.0, coord[1] + 1.0, coord[2] + 1.0
        #line with coordinates and properties of a marker
        if self.fiducial_flag == 1:
            self.fiducial_flag = 0
        else:
            self.fiducial_ID = ""
        line = [coord[0] , coord[1] , coord[2] , colour[0], colour[1], colour[2], self.spin.GetValue(), self.fiducial_ID]
        if self.flagpoint1 == 0:
            self.list_coord = [line]
            self.flagpoint1 = 1
        else:
            #adding current line to a list of all markers already created
            self.list_coord.append(line)

        ##ListCtrl
        num_items = self.lc.GetItemCount()
        cont = num_items + 1
        self.lc.InsertStringItem(num_items, str(cont))
        self.lc.SetStringItem(num_items, 1, str(round(coord[0],2)))
        self.lc.SetStringItem(num_items, 2, str(round(coord[1],2)))
        self.lc.SetStringItem(num_items, 3, str(round(coord[2],2)))
        self.lc.SetStringItem(num_items,4, str(self.fiducial_ID))
        self.lc.EnsureVisible(num_items)

    def OnDelMarker(self,pubsub_evt):
        self.list_coord = []
        Publisher.sendMessage('Remove all markers', self.lc.GetItemCount())
        self.lc.DeleteAllItems()
        self.ballid = 0

    def DelSingleMarker(self, pubsub_evt):
        ##this try is to remove the toggle=false fiducial marker, doesnt matter the order
        # try:
        id = pubsub_evt.data
        # print 'id: ', id
        # print 'count: ', self.lc.GetItemCount()
        if self.lc.GetItemCount():
            for idx in range(self.lc.GetItemCount()):
                item = self.lc.GetItem(idx, 4)
                # print 'item: ', item
                # print 'text: ', item.GetText()
                if item.GetText() == id:
                    if id == "LEI":
                        self.lc.Focus(item.GetId())
                        break
                    if id == "REI":
                        self.lc.Focus(item.GetId())
                        break
                    if id == "NAI":
                        self.lc.Focus(item.GetId())
                        break
        # except:
        #     None

        if self.lc.GetFocusedItem() is not -1 and self.lc.GetItemCount():
            index = self.lc.GetFocusedItem()
            del self.list_coord[index]
            self.lc.DeleteItem(index)
            for x in range(0,self.lc.GetItemCount()):
                self.lc.SetStringItem(x, 0, str(x+1))
            self.ballid = self.ballid - 1
            Publisher.sendMessage('Remove marker', index)
        elif not self.lc.GetItemCount():
            None
        else:
            dlg.NoMarkerSelected()
    
    def GetPoint(self, pubsub_evt):
        self.ijk = pubsub_evt.data
        ##print "ijk: ", self.ijk
        
        """pt_id = self.imagedata.FindPoint(self.xyz)
        pt_id = self.ijk
        #print "pt_id: ", pt_id
        
        rest = pt_id%(256*256)
        i = rest/256 + 1 
        j = rest%256 + 1
        k = (pt_id/(256*256)) + 1"""
                   
    def OnCreateMarker(self, evt):
        coord = self.ijk
        self.CreateMarker(coord, self.colour, self.spin.GetValue())

    def OnLoadMarkers(self, evt):
        filepath = dlg.ShowLoadMarkersDialog()
        if filepath is not None:
            try:
                content = [s.rstrip() for s in open(filepath)]
                for data in content:
                    line = [s for s in data.split()]
                    coord = float(line[0]), float(line[1]), float(line[2])
                    colour = float(line[3]), float(line[4]), float(line[5])
                    size = float(line[6])
                    if len(line) == 8:
                        self.fiducial_flag = 1
                        self.fiducial_ID = line[7]
                        Publisher.sendMessage('Load Fiducials', (self.fiducial_ID, coord))
                    else:
                        self.fiducial_flag = 0
                    self.CreateMarker(coord, colour, size)
            except:
                dlg.InvalidMarkersFile()
                # raise ValueError('Invalid Markers File')
        else:
            None

    def OnMarkersVisibility(self, evt):
        ballid = self.lc.GetItemCount()
        flag5 = self.markers_visibility.GetValue()
        if flag5 == True:
            Publisher.sendMessage('Hide all markers',  ballid)
            self.markers_visibility.SetLabel('Show')
        elif flag5 == False:
            Publisher.sendMessage('Show all markers',  ballid)
            self.markers_visibility.SetLabel('Hide')
            
    def OnSaveMarkers(self, evt):
        filename = dlg.ShowSaveMarkersDialog("Markers.txt")
        if filename is not None:
            text_file = open(filename, "w")
            list_slice1 = self.list_coord[0]
            coord = str('%.3f' %self.list_coord[0][0]) + "\t" + str('%.3f' %self.list_coord[0][1]) + "\t" + str('%.3f' %self.list_coord[0][2])
            properties = str('%.3f' %list_slice1[3]) + "\t" + str('%.3f' %list_slice1[4]) + "\t" + str('%.3f' %list_slice1[5]) + "\t" + str('%.1f' %list_slice1[6]) + "\t" + list_slice1[7]
            line = coord + "\t" + properties + "\n"
            list_slice = self.list_coord[1:]
            for i in list_slice:
                #line = line + str('%.3f' %i[0]) + "\t" + str('%.3f' %i[1]) + "\t" + str('%.3f' %i[2]) + "\n"
                coord = str('%.3f' %i[0]) + "\t" + str('%.3f' %i[1]) + "\t" + str('%.3f' %i[2])
                properties = str('%.3f' %i[3]) + "\t" + str('%.3f' %i[4]) + "\t" + str('%.3f' %i[5]) + "\t" + str('%.1f' %i[6]) + "\t" + i[7]
                line = line + coord + "\t" + properties + "\n"
            text_file.writelines(line)
            text_file.close()
        else:
            None
    
    def OnSelectColour(self, evt):
        self.colour = [value/255.0 for value in self.marker_colour.GetValue()]
