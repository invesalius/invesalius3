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
from time import sleep

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

        # Initialize global variables
        self.correg = None
        self.trk_init = None
        self.current_coord = 0, 0, 0
        self.fiducials = np.full([6, 3], np.nan)

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
        choice_trck.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceTracker, choice_trck=choice_trck))

        # ComboBox for tracker reference mode
        tooltip = wx.ToolTip(_("Choose the navigation reference mode"))
        choice_ref = wx.ComboBox(self, -1, "",
                                 choices=const.REF_MODE, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_ref.SetSelection(const.DEFAULT_REF_MODE)
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceRefMode, choice_trck=choice_trck))

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

        # Target registration error text box
        tooltip = wx.ToolTip(_("Target registration error"))
        txtctrl_tre = wx.TextCtrl(self, value="")
        txtctrl_tre.SetEditable(0)
        txtctrl_tre.SetToolTip(tooltip)

        # Toggle button for neuronavigation
        tooltip = wx.ToolTip(_("Start navigation"))
        btn_nav = wx.ToggleButton(self, -1, _("Neuronavigate"))
        btn_nav.SetToolTip(tooltip)
        btn_nav.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnNavigate, btn=(btn_nav, choice_trck, choice_ref, txtctrl_tre)))

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

        nav_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        nav_sizer.AddMany([(txtctrl_tre, wx.LEFT|wx.RIGHT),
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
        Publisher.subscribe(self.UpdateImageCoordinates, 'Set ball reference position')
        Publisher.subscribe(self.LoadImageFiducials, 'Load Fiducials')

    def UpdateImageCoordinates(self, pubsub_evt):
        # Updating using message cross position does not update during navigation
        self.current_coord = pubsub_evt.data
        for m in [0, 1, 2, 6]:
            if m == 6:
                for n in [0, 1, 2]:
                    self.numctrls_coord[m][n].SetValue(self.current_coord[n])
            else:
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

    def OnSetImageCoordinates(self, evt):
        btn_id = const.BTNS_TRK[evt.GetId()].keys()[0]

        wx, wy, wz = self.numctrls_coord[btn_id][0].GetValue(), \
                     self.numctrls_coord[btn_id][1].GetValue(), \
                     self.numctrls_coord[btn_id][2].GetValue()

        Publisher.sendMessage('Set ball reference position', (wx, wy, wz))
        Publisher.sendMessage('Set camera in volume', (wx, wy, wz))
        Publisher.sendMessage('Co-registered points', (wx, wy, wz))
        Publisher.sendMessage('Update cross position', (wx, wy, wz))

    def OnImageFiducials(self, evt):
        btn_id = const.BTNS_IMG[evt.GetId()].keys()[0]
        marker_id = const.BTNS_IMG[evt.GetId()].values()[0]

        if self.btns_coord[btn_id].GetValue():
            coord = self.numctrls_coord[btn_id][0].GetValue(),\
                    self.numctrls_coord[btn_id][1].GetValue(),\
                    self.numctrls_coord[btn_id][2].GetValue()
            # if btn_id != 6:
            self.fiducials[btn_id, :] = coord[0:3]
            Publisher.sendMessage('Create fiducial markers', (coord, marker_id))
        else:
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(self.current_coord[n])
            # if btn_id != 6:
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
            # print 'coord: ', coord
            # print 'fids: ', self.fiducials
            for n in [0, 1, 2]:
                self.numctrls_coord[btn_id][n].SetValue(float(coord[n]))

    def OnNavigate(self, evt, btn):
        btn_nav = btn[0]
        choice_trck = btn[1]
        choice_ref = btn[2]
        txtctrl_tre = btn[3]

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
                # FIXME: FRE is taking long to calculate so it updates on GUI delayed to navigation - i think its fixed
                # TODO: Exhibit FRE in a warning dialog and only starts navigation after user clicks ok
                fre = self.CalculateFRE(minv, n, q1, q2)

                txtctrl_tre.SetValue("FRE: " + str(round(fre, 2)))
                if fre <= 3:
                    txtctrl_tre.SetBackgroundColour('GREEN')
                else:
                    txtctrl_tre.SetBackgroundColour('RED')

                self.correg = dcr.Coregistration((minv, n, q1, q2), nav_id, tracker_mode)

        else:
            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn_nav.SetToolTip(tooltip)

            # Enable all navigation buttons
            choice_ref.Enable(True)
            choice_trck.Enable(True)
            for btn_c in self.btns_coord:
                btn_c.Enable(True)

            self.correg.stop()

    def CalculateFRE(self, minv, n, q1, q2):

        img = np.zeros([3, 3])
        dist = np.zeros([3, 1])

        p1 = np.mat(self.fiducials[3, :]).reshape(3, 1)
        p2 = np.mat(self.fiducials[4, :]).reshape(3, 1)
        p3 = np.mat(self.fiducials[5, :]).reshape(3, 1)

        img[0, :] = np.asarray((q1 + (minv * n) * (p1 - q2)).reshape(1, 3))
        img[1, :] = np.asarray((q1 + (minv * n) * (p2 - q2)).reshape(1, 3))
        img[2, :] = np.asarray((q1 + (minv * n) * (p3 - q2)).reshape(1, 3))

        dist[0] = np.sqrt(np.sum(np.power((img[0, :] - self.fiducials[0, :]), 2)))
        dist[1] = np.sqrt(np.sum(np.power((img[1, :] - self.fiducials[1, :]), 2)))
        dist[2] = np.sqrt(np.sum(np.power((img[2, :] - self.fiducials[2, :]), 2)))

        return float(np.sqrt(np.sum(dist ** 2) / 3))

    def OnChoiceTracker(self, evt, choice_trck):
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
                    choice_trck.SetSelection(0)
                    print "Tracker not connected!"
                else:
                    choice_trck.SetSelection(self.tracker_id)
                    print "Tracker connected!"
        elif choice == 6:
            if trck:
                self.trk_init = dt.TrackerConnection(self.tracker_id, 'disconnect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, 'disconnect')
                    self.tracker_id = 0
                    choice_trck.SetSelection(self.tracker_id)
                    print "Tracker disconnected!"
                else:
                    print "Tracker still connected!"
            else:
                choice_trck.SetSelection(self.tracker_id)

        else:
            # If trk_init is None try to connect. If doesn't succeed show dialog.
            if choice:
                self.tracker_id = choice
                self.trk_init = dt.TrackerConnection(self.tracker_id, 'connect')
                if not self.trk_init[0]:
                    dlg.NavigationTrackerWarning(self.tracker_id, self.trk_init[1])
                    self.tracker_id = 0
                    choice_trck.SetSelection(self.tracker_id)

    def OnChoiceRefMode(self, evt, choice_trck):
        # When ref mode is changed the tracker coords are set to zero, self.aux_trck is the flag that sets it
        self.ref_mode_id = evt.GetSelection()
        self.ResetTrackerFiducials()
        self.OnChoiceTracker(None, choice_trck)
        print "Reference mode changed!"

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
        
        self.ijk = 0, 0, 0
        self.flagpoint1 = 0
        self.ballid = 0
        self.colour = 0.0, 0.0, 1.0
        self.fiducial_color = 0.0, 1.0, 0.0
        self.fiducial_flag = 0
        self.fiducial_ID = ""

        # Change marker size
        spin_marker_size = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_marker_size.SetRange(1, 99)
        spin_marker_size.SetValue(const.MARKER_SIZE)
        # spin_marker_size.Bind(wx.EVT_TEXT, self.OnMarkerSize)
        self.spin = spin_marker_size

        # Marker colour select
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


    def __bind_events(self):
        Publisher.subscribe(self.GetPoint, 'Set ball reference position')
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
