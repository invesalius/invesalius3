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
        default_color = self.GetBackgroundColour()
        backgroud_colour = wx.Colour(255,255,255)
        self.SetBackgroundColour(backgroud_colour)
        self.SetAutoLayout(1)

        # wx.Panel.__init__(self, parent, size=wx.Size(0,310)) - in usp-navegador
        # wx.Panel.__init__(self, parent, size=wx.Size(0,310)) - in master_merge-rmatsuda
        text_nav = wx.StaticText(self, -1, _('Configure spatial tracker and coregistrate'),
                                 size=wx.Size(90, 20))

        # Create horizontal sizer to represent lines in the panel
        line_new = wx.BoxSizer(wx.HORIZONTAL)
        line_new.Add(text_nav, 1, wx.EXPAND|wx.GROW, 5)

        # Fold panel which contains navigation configurations
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_color)

        # Add line sizer into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_new, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 5)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

        self.sizer = main_sizer


class FoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(wx.Colour(0,255,0))

        inner_panel = InnerFoldPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 0, wx.EXPAND|wx.GROW)
        sizer.Fit(self)

        self.SetSizer(sizer)
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
                                      (10, 320), 0,fpb.FPB_SINGLE_FOLD)

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Surface properties
        item = fold_panel.AddFoldPanel(_("Neuronavigation"), collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, NeuronavigationTools(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        # Fold 2 - Object properties
        item = fold_panel.AddFoldPanel(_("Object registration"), collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ObjectWNeuronavigation(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)

        # Fold 3 - Surface tools
        item = fold_panel.AddFoldPanel(_("Extra tools"), collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, Markers(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

IR1 = wx.NewId()
IR2 = wx.NewId()
IR3 = wx.NewId()
TR1 = wx.NewId()
TR2 = wx.NewId()
TR3 = wx.NewId()
T = wx.NewId()
Neuronavigate = wx.NewId()
# FineCorregistration = wx.NewId()
class NeuronavigationTools(wx.Panel):
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
        self.a = 0, 0, 0
        self.coord1a = (0, 0, 0)
        self.coord2a = (0, 0, 0)
        self.coord3a = (0, 0, 0)
        self.coord1b = (0, 0, 0)
        self.coord2b = (0, 0, 0)
        self.coord3b = (0, 0, 0)
        self.correg = None
        self.filename = None
        self.c1 = None
        self.tracker_id = const.DEFAULT_TRACKER
        self.ref_mode_id = const.DEFAULT_REF_MODE

        self.trk_init = None
        self.plhButton = False

        #Combo Box
        self.choice_tracker = wx.ComboBox(self, -1, "",
                                     choices = const.TRACKER, style = wx.CB_DROPDOWN|wx.CB_READONLY)
        self.choice_tracker.SetSelection(const.DEFAULT_TRACKER)
        self.choice_tracker.Bind(wx.EVT_COMBOBOX, self.OnChoiceTracker)

        tooltip = wx.ToolTip(_("Choose the navigation reference mode"))
        self.choice_ref_mode = wx.ComboBox(self, -1, "",
                                     choices = const.REF_MODE, style = wx.CB_DROPDOWN|wx.CB_READONLY)
        self.choice_ref_mode.SetSelection(const.DEFAULT_REF_MODE)
        self.choice_ref_mode.SetToolTip(tooltip)
        self.choice_ref_mode.Bind(wx.EVT_COMBOBOX, self.OnChoiceRefMode)

        #Toggle Buttons for ref images
        tooltip = wx.ToolTip(_("Select left auricular tragus at image"))
        self.button_img_ref1 = wx.ToggleButton(self, IR1, label = _('LTI'), size = wx.Size(30,23))
        self.button_img_ref1.SetToolTip(tooltip)
        self.button_img_ref1.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton1)

        tooltip = wx.ToolTip(_("Select right auricular tragus at image"))
        self.button_img_ref2 = wx.ToggleButton(self, IR2, label = _('RTI'), size = wx.Size(30,23))
        self.button_img_ref2.SetToolTip(tooltip)
        self.button_img_ref2.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton2)

        tooltip = wx.ToolTip(_("Select nasion at image"))
        self.button_img_ref3 = wx.ToggleButton(self, IR3, label = _('NI'), size = wx.Size(30,23))
        self.button_img_ref3.SetToolTip(tooltip)
        self.button_img_ref3.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton3)

        #self.button_img_inio = wx.Button(self, INO, label='INO', size=wx.Size(30, 23))
        tooltip = wx.ToolTip(_("Select target point at image for target registration error calculation"))
        self.button_img_T = wx.ToggleButton(self, T, label = 'T', size = wx.Size(30,23))
        self.button_img_T.SetToolTip(tooltip)
        self.button_img_T.Bind(wx.EVT_TOGGLEBUTTON, self.Img_T_ToggleButton)

        #Buttons for ref tracker
        tooltip = wx.ToolTip(_("Select left auricular tragus with spatial tracker"))
        self.button_trck_ref1 = wx.Button(self, TR1, label = _('LTT'), size = wx.Size(30,23))
        self.button_trck_ref1.SetToolTip(tooltip)
        tooltip = wx.ToolTip(_("Select right auricular tragus with spatial tracker"))
        self.button_trck_ref2 = wx.Button(self, TR2, label = _('RTT'), size = wx.Size(30,23))
        self.button_trck_ref2.SetToolTip(tooltip)
        tooltip = wx.ToolTip(_("Select nasion with spatial tracker"))
        self.button_trck_ref3 = wx.Button(self, TR3, label = _('NT'), size = wx.Size(30,23))
        self.button_trck_ref3.SetToolTip(tooltip)

        #Error text box
        self.button_crg = wx.TextCtrl(self, value="")
        self.button_crg.SetEditable(0)
        self.Bind(wx.EVT_BUTTON, self.Buttons)

        tooltip = wx.ToolTip(_("Start neuronavigation"))
        self.button_neuronavigate = wx.ToggleButton(self, Neuronavigate, _("Neuronavigate"))
        self.button_neuronavigate.SetToolTip(tooltip)
        self.button_neuronavigate.Bind(wx.EVT_TOGGLEBUTTON, self.Neuronavigate_ToggleButton)

        self.numCtrl1I = wx.lib.masked.numctrl.NumCtrl(
           name='numCtrl1I', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2I = wx.lib.masked.numctrl.NumCtrl(
           name='numCtrl2I', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3I = wx.lib.masked.numctrl.NumCtrl(
           name='numCtrl3I', parent=self, integerWidth = 4, fractionWidth = 1)

        self.numCtrl1a = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1a', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2a = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2a', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3a = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3a', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl1b = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1b', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2b = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2b', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3b = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3b', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl1c = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1c', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2c = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2c', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3c = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3c', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl1d = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1d', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2d = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2d', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3d = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3d', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl1e = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1e', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2e = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2e', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3e = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3e', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl1f = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1f', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2f = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2f', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3f = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3f', parent=self, integerWidth = 4, fractionWidth = 1)

        self.numCtrl1d.SetEditable(False)
        self.numCtrl2d.SetEditable(False)
        self.numCtrl3d.SetEditable(False)
        self.numCtrl1e.SetEditable(False)
        self.numCtrl2e.SetEditable(False)
        self.numCtrl3e.SetEditable(False)
        self.numCtrl1f.SetEditable(False)
        self.numCtrl2f.SetEditable(False)
        self.numCtrl3f.SetEditable(False)

        choice_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        choice_sizer.AddMany([ (self.choice_tracker, wx.LEFT),
                                (self.choice_ref_mode, wx.RIGHT)])

        RefImg_sizer1 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefImg_sizer1.AddMany([ (self.button_img_ref1),
                                (self.numCtrl1a),
                                (self.numCtrl2a),
                                (self.numCtrl3a)])

        RefImg_sizer2 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefImg_sizer2.AddMany([ (self.button_img_ref2),
                                (self.numCtrl1b),
                                (self.numCtrl2b),
                                (self.numCtrl3b)])

        RefImg_sizer3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefImg_sizer3.AddMany([ (self.button_img_ref3),
                                (self.numCtrl1c),
                                (self.numCtrl2c),
                                (self.numCtrl3c)])

        RefPlh_sizer1 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer1.AddMany([ (self.button_trck_ref1, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1d, wx.RIGHT),
                                (self.numCtrl2d),
                                (self.numCtrl3d, wx.LEFT)])

        RefPlh_sizer2 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer2.AddMany([ (self.button_trck_ref2, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1e, 0, wx.RIGHT),
                                (self.numCtrl2e),
                                (self.numCtrl3e, 0, wx.LEFT)])

        RefPlh_sizer3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer3.AddMany([ (self.button_trck_ref3, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1f, wx.RIGHT),
                                (self.numCtrl2f),
                                (self.numCtrl3f, wx.LEFT)])

        line3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        line3.AddMany([(self.button_img_T),
                      (self.numCtrl1I),
                      (self.numCtrl2I),
                      (self.numCtrl3I)])

        Buttons_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        Buttons_sizer.AddMany([(self.button_crg, wx.LEFT|wx.RIGHT),
                               (self.button_neuronavigate, wx.LEFT|wx.RIGHT)])

        Ref_sizer = wx.FlexGridSizer(rows=9, cols=1, hgap=5, vgap=5)
        Ref_sizer.AddGrowableCol(0, 1)
        Ref_sizer.AddGrowableRow(0, 1)
        Ref_sizer.AddGrowableRow(1, 1)
        Ref_sizer.AddGrowableRow(2, 1)
        Ref_sizer.AddGrowableRow(3, 1)
        Ref_sizer.AddGrowableRow(4, 1)
        Ref_sizer.AddGrowableRow(5, 1)
        Ref_sizer.AddGrowableRow(6, 1)
        Ref_sizer.AddGrowableRow(7, 1)
        Ref_sizer.AddGrowableRow(8, 1)
        Ref_sizer.SetFlexibleDirection(wx.BOTH)
        Ref_sizer.AddMany([ (choice_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer1, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer2, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer3, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer1, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer2, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer3, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (line3, 0,wx.ALIGN_CENTER_HORIZONTAL),
                            (Buttons_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)])

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(Ref_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

    def __bind_events(self):
        Publisher.subscribe(self.__update_points_img, 'Update cross position')
        Publisher.subscribe(self.__update_points_trck, 'Update tracker position')
        Publisher.subscribe(self.__load_points_img, 'Load Fiducial')
        Publisher.subscribe(self.__StylusStatus, 'Stylus Button')

    def __update_points_img(self, pubsub_evt):
        x, y, z = pubsub_evt.data
        self.a = x, y, z
        if self.aux_img_ref1 == 0:
            self.numCtrl1a.SetValue(x)
            self.numCtrl2a.SetValue(y)
            self.numCtrl3a.SetValue(z)
        if self.aux_img_ref2 == 0:
            self.numCtrl1b.SetValue(x)
            self.numCtrl2b.SetValue(y)
            self.numCtrl3b.SetValue(z)
        if self.aux_img_ref3 == 0:
            self.numCtrl1c.SetValue(x)
            self.numCtrl2c.SetValue(y)
            self.numCtrl3c.SetValue(z)
        if self.aux_img__T_ref == 0:
           self.numCtrl1I.SetValue(x)
           self.numCtrl2I.SetValue(y)
           self.numCtrl3I.SetValue(z)

    def __update_points_trck(self, pubsub_evt):
        coord = pubsub_evt.data
        if self.aux_trck_ref1 == 1:
            self.numCtrl1d.SetValue(coord[0])
            self.numCtrl2d.SetValue(coord[1])
            self.numCtrl3d.SetValue(coord[2])
            self.aux_trck1 = 1
            self.aux_trck_ref1 = 0
        if self.aux_trck_ref2 == 1:
            self.numCtrl1e.SetValue(coord[0])
            self.numCtrl2e.SetValue(coord[1])
            self.numCtrl3e.SetValue(coord[2])
            self.aux_trck2 = 1
            self.aux_trck_ref2 = 0
        if self.aux_trck_ref3 == 1:
            self.numCtrl1f.SetValue(coord[0])
            self.numCtrl2f.SetValue(coord[1])
            self.numCtrl3f.SetValue(coord[2])
            self.aux_trck3 = 1
            self.aux_trck_ref3 = 0

    def __load_points_img(self, pubsub_evt):
        load = pubsub_evt.data[0]
        coord = pubsub_evt.data[1]
        if load == "LTI":
            self.Load_Ref_LTI(coord)
        elif load == "RTI":
            self.Load_Ref_RTI(coord)
        elif load == "NI":
            self.Load_Ref_NI(coord)

    def __StylusStatus(self, pubsub_evt):
        self.plhButton = pubsub_evt.data

    def Load_Ref_LTI(self,coord):
        img_id = self.button_img_ref1.GetValue()
        x, y, z = coord
        if img_id == False:
            self.numCtrl1a.SetValue(x)
            self.numCtrl2a.SetValue(y)
            self.numCtrl3a.SetValue(z)
            self.coord1a = x, y, z
            self.button_img_ref1.SetValue(True)
            self.aux_img_ref1 = 1
        else:
            None

    def Load_Ref_RTI(self,coord):
        img_id = self.button_img_ref2.GetValue()
        x, y, z = coord
        if img_id == False:
            self.numCtrl1b.SetValue(x)
            self.numCtrl2b.SetValue(y)
            self.numCtrl3b.SetValue(z)
            self.coord2a = x, y, z
            self.button_img_ref2.SetValue(True)
            self.aux_img_ref2 = 1
        else:
            None

    def Load_Ref_NI(self,coord):
        img_id = self.button_img_ref3.GetValue()
        x, y, z = coord
        if img_id == False:
            self.numCtrl1c.SetValue(x)
            self.numCtrl2c.SetValue(y)
            self.numCtrl3c.SetValue(z)
            self.coord3a = x, y, z
            self.button_img_ref3.SetValue(True)
            self.aux_img_ref3 = 1
        else:
            None

    def Buttons(self, evt):
        id = evt.GetId()
        x, y, z = self.a
        if id == TR1:
            if self.trk_init and (self.tracker_id != 0):
                self.aux_trck_ref1 = 1
                self.coord1b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
                coord = self.coord1b[0:3]
            else:
                dlg.TrackerNotConnected(self.tracker_id)

        elif id == TR2:
            if self.trk_init and (self.tracker_id != 0):
                self.aux_trck_ref2 = 1
                self.coord2b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
                coord = self.coord2b[0:3]
            else:
                dlg.TrackerNotConnected(self.tracker_id)
        elif id == TR3:
            if self.trk_init and (self.tracker_id != 0):
                self.aux_trck_ref3 = 1
                self.coord3b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
                coord = self.coord3b[0:3]
            else:
                dlg.TrackerNotConnected(self.tracker_id)

        if self.aux_trck_ref1 == 1 or self.aux_trck_ref2 == 1 or self.aux_trck_ref3 == 1:
            Publisher.sendMessage('Update tracker position', coord)

    def Img_Ref_ToggleButton1(self, evt):
        img_id = self.button_img_ref1.GetValue()
        #this fixed points are from dicom2 exam
        x, y, z = self.a
#        x, y, z = 201.1, 113.3, 31.5
        if img_id == True:
            #This condition allows the user writes the image coords
            if self.numCtrl1a.GetValue() != round(x, 1) or self.numCtrl2a.GetValue() != round(y,1) or self.numCtrl3a.GetValue() != round(z, 1):
                self.coord1a = self.numCtrl1a.GetValue(), self.numCtrl2a.GetValue(), self.numCtrl3a.GetValue()
                Publisher.sendMessage('Set camera in volume for Navigation', self.coord1a)
                Publisher.sendMessage('Co-registered Points', self.coord1a)
                self.aux_img_ref1 = 1
                Publisher.sendMessage("Create fiducial markers", (self.coord1a, "LTI"))
            else:
                self.coord1a = x, y, z
                self.aux_img_ref1 = 1
                Publisher.sendMessage("Create fiducial markers", (self.coord1a, "LTI"))

        elif img_id == False:
            self.aux_img_ref1 = 0
            self.coord1a = (0, 0, 0)
            self.numCtrl1a.SetValue(x)
            self.numCtrl2a.SetValue(y)
            self.numCtrl3a.SetValue(z)
            Publisher.sendMessage("Delete fiducial marker", "LTI")

    def Img_Ref_ToggleButton2(self, evt):
        img_id = self.button_img_ref2.GetValue()
        #this fixed points are from dicom2 exam
        x, y, z = self.a
#        x, y, z = 50.4, 113.3, 30.0
        if img_id == True:
            #This condition allows the user writes the image coords
            if self.numCtrl1b.GetValue() != round(x, 1) or self.numCtrl2b.GetValue() != round(y,1) or self.numCtrl3b.GetValue() != round(z, 1):
                self.coord2a = self.numCtrl1b.GetValue(), self.numCtrl2b.GetValue(), self.numCtrl3b.GetValue()
                Publisher.sendMessage('Set camera in volume for Navigation', self.coord2a)
                Publisher.sendMessage('Co-registered Points', self.coord2a)
                self.aux_img_ref2 = 1
                Publisher.sendMessage("Create fiducial markers", (self.coord2a, "RTI"))
            else:
                self.coord2a = x, y, z
                self.aux_img_ref2 = 1
                Publisher.sendMessage("Create fiducial markers", (self.coord2a, "RTI"))

        elif img_id == False:
            self.aux_img_ref2 = 0
            self.coord2a = (0, 0, 0)
            self.numCtrl1b.SetValue(x)
            self.numCtrl2b.SetValue(y)
            self.numCtrl3b.SetValue(z)
            Publisher.sendMessage("Delete fiducial marker", "RTI")

    def Img_Ref_ToggleButton3(self, evt):
        img_id = self.button_img_ref3.GetValue()
        #this fixed points are from dicom2 exam
        x, y, z = self.a
#        x, y, z = 123.4, 207.4, 67.5
        if img_id == True:
            #This condition allows the user writes the image coords
            if self.numCtrl1c.GetValue() != round(x, 1) or self.numCtrl2c.GetValue() != round(y,1) or self.numCtrl3c.GetValue() != round(z, 1):
                self.coord3a = self.numCtrl1c.GetValue(), self.numCtrl2c.GetValue(), self.numCtrl3c.GetValue()
                Publisher.sendMessage('Set camera in volume for Navigation', self.coord3a)
                Publisher.sendMessage('Co-registered Points', self.coord3a)
                self.aux_img_ref3 = 1
                Publisher.sendMessage("Create fiducial markers", (self.coord3a, "NI"))
            else:
                self.coord3a = x, y, z
                self.aux_img_ref3 = 1
                Publisher.sendMessage("Create fiducial markers", (self.coord3a, "NI"))

        elif img_id == False:
            self.aux_img_ref3 = 0
            self.coord3a = (0, 0, 0)
            self.numCtrl1c.SetValue(x)
            self.numCtrl2c.SetValue(y)
            self.numCtrl3c.SetValue(z)
            Publisher.sendMessage("Delete fiducial marker", "NI")

    def Img_T_ToggleButton(self, evt):
           img_id = self.button_img_T.GetValue()
           x, y, z = self.a
           if img_id == True:
               # This condition allows the user writes the image coords
               if self.numCtrl1I.GetValue() != round(x,1) or self.numCtrl2I.GetValue() != round(y,1) or self.numCtrl3I.GetValue() != round(z,1):
                   self.img_T = self.numCtrl1I.GetValue(), self.numCtrl2I.GetValue(), self.numCtrl3I.GetValue()
                   Publisher.sendMessage('Set camera in volume for Navigation', self.img_T)
                   Publisher.sendMessage('Co-registered Points', self.img_T)
                   self.aux_img__T_ref = 1
                   self.coordT = np.array([self.numCtrl1I.GetValue(),self.numCtrl2I.GetValue(),self.numCtrl3I.GetValue()])
               else:
                   self.img_T = x, y, z
                   self.aux_img__T_ref = 1
                   self.coordT = np.array([x,y,z])
           elif img_id == False:
               self.aux_img__T_ref = 0
               self.img_T = (0, 0, 0)
               self.numCtrl1I.SetValue(x)
               self.numCtrl2I.SetValue(y)
               self.numCtrl3I.SetValue(z)

    def Neuronavigate_ToggleButton(self, evt):
        nav_id = self.button_neuronavigate.GetValue()
        if nav_id == True:
            if self.aux_trck1 and self.aux_trck2 and self.aux_trck3 and self.aux_img_ref1 and self.aux_img_ref2 and self.aux_img_ref3:
                tooltip = wx.ToolTip(_("Stop neuronavigation"))
                self.button_neuronavigate.SetToolTip(tooltip)
                self.Enable_Disable_buttons(False)
                self.Coregister()
                bases = self.Minv, self.N, self.q1, self.q2
                tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id, self.plhButton
                self.Calculate_FRE()
                self.correg = dcr.Coregistration(bases, nav_id, tracker_mode)
                #self.plh = tms.PLHbutton(nav_id)
                self.TMS = tms.Trigger(nav_id)
            else:
                dlg.InvalidReferences()
                self.button_neuronavigate.SetValue(False)
        elif nav_id == False:
            self.Enable_Disable_buttons(True)
            tooltip = wx.ToolTip(_("Start neuronavigation"))
            self.button_neuronavigate.SetToolTip(tooltip)
            self.correg.stop()
            #self.plh.stop()
            self.TMS.stop()

    def Enable_Disable_buttons(self,status):
        self.choice_ref_mode.Enable(status)
        self.choice_tracker.Enable(status)
        self.button_img_ref1.Enable(status)
        self.button_img_ref2.Enable(status)
        self.button_img_ref3.Enable(status)

    def Calculate_FRE(self):

        p1 = np.matrix([[self.coord1b[0]],[self.coord1b[1]],[self.coord1b[2]]])
        p2 = np.matrix([[self.coord2b[0]],[self.coord2b[1]],[self.coord2b[2]]])
        p3 = np.matrix([[self.coord3b[0]],[self.coord3b[1]],[self.coord3b[2]]])

        img1 = self.q1 + (self.Minv * self.N) * (p1 - self.q2)
        img2 = self.q1 + (self.Minv * self.N) * (p2 - self.q2)
        img3 = self.q1 + (self.Minv * self.N) * (p3 - self.q2)

        ED1=np.sqrt((((img1[0]-self.coord1a[0])**2) + ((img1[1]-self.coord1a[1])**2) +((img1[2]-self.coord1a[2])**2)))
        ED2=np.sqrt((((img2[0]-self.coord2a[0])**2) + ((img2[1]-self.coord2a[1])**2) +((img2[2]-self.coord2a[2])**2)))
        ED3=np.sqrt((((img3[0]-self.coord3a[0])**2) + ((img3[1]-self.coord3a[1])**2) +((img3[2]-self.coord3a[2])**2)))

        FRE = float(np.sqrt((ED1**2 + ED2**2 + ED3**2)/3))

        #TRE calculation
        # if self.aux_img__T_ref == 1:
        #     N1 = ([self.coord1a[0], self.coord2a[0], self.coord3a[0]])
        #     norm1 = [float(i) / sum(N1) for i in N1]
        #     N2 = ([self.coord1a[1], self.coord2a[1], self.coord3a[1]])
        #     norm2 = [float(i) / sum(N2) for i in N2]
        #     N3 = ([self.coord1a[2], self.coord2a[2], self.coord3a[2]])
        #     norm3 = [float(i) / sum(N3) for i in N3]
        #
        #     plhT = np.matrix([[self.coordT[0]], [self.coordT[1]], [self.coordT[2]]])
        #     #imgT = self.q1 + (self.Minv * self.N) * (plhT - self.q2)
        #     #imgT = np.array([float(imgT[0]), float(imgT[1]), float(imgT[2])])
        #     centroid = np.array([(self.coord1a[0] + self.coord2a[0] + self.coord3a[0]) / 3, (self.coord1a[1] + self.coord2a[1] + self.coord3a[1]) / 3, (self.coord1a[2] + self.coord2a[2] + self.coord3a[2]) / 3])
        #     #Difference between the target point (after coregister) with the fiducials centroid
        #     #dif_vector = imgT - centroid
        #     dif_vector = plhT - centroid
        #
        #     er1 = np.linalg.norm(np.cross(norm1, dif_vector))
        #     er2 = np.linalg.norm(np.cross(norm2, dif_vector))
        #     er3 = np.linalg.norm(np.cross(norm3, dif_vector))
        #
        #     err1 = err2 = err3 = 0
        #
        #     for i in range(0, 3):
        #         # Difference between each fiducial with the fiducials centroid
        #         diff_vector = [self.coord1a[i] - centroid[0], self.coord2a[i] - centroid[0], self.coord3a[i] - centroid[0]]
        #
        #         err1 += (np.linalg.norm(np.cross(norm1, diff_vector)))** 2
        #         err2 += (np.linalg.norm(np.cross(norm2, diff_vector)))** 2
        #         err3 += (np.linalg.norm(np.cross(norm3, diff_vector)))** 2
        #
        #     f1 = np.sqrt(err1 / 3)
        #     f2 = np.sqrt(err2 / 3)
        #     f3 = np.sqrt(err3 / 3)
        #
        #     SUM = ((er1 ** 2) / (f1 ** 2)) + ((er2 ** 2) / (f2 ** 2)) + ((er3 ** 2) / (f3 ** 2))
        #     TREf = np.sqrt((FRE ** 2) * (1 + (SUM / 3)))
        #
        #     self.button_crg.SetValue("FRE: " + str(round(FRE, 2))+" TRE: " + str(round(TREf, 2)))
        #
        # else:
        #     self.button_crg.SetValue("FRE: " + str(round(FRE, 2)))
        self.button_crg.SetValue("FRE: " + str(round(FRE, 2)))
        if FRE <= 3:
            self.button_crg.SetBackgroundColour('GREEN')
        else:
            self.button_crg.SetBackgroundColour('RED')

    def OnChoiceTracker(self, evt):
        #this condition check if the trackers is already connected and disconnect this tracker
        if (self.tracker_id == evt.GetSelection()) and (self.trk_init is not None) and (self.tracker_id != 0):
            dlg.TrackerAlreadyConnected()
            self.tracker_rem_id = self.tracker_id
            self.RemoveTracker()
            self.choice_tracker.SetSelection(0)
            self.SetTrackerFiducialsNone()
            self.tracker_id = 0
        else:
            self.tracker_id = evt.GetSelection()
            if self.tracker_id != 0:
                trck = {1 : dt.Tracker().ClaronTracker,
                        2 : dt.Tracker().PlhFastrak,
                        3 : dt.Tracker().PlhIsotrakII,
                        4 : dt.Tracker().PlhPatriot,
                        5 : dt.Tracker().ZebrisCMS20}
                self.tracker_rem_id = self.tracker_id
                self.trk_init = trck[self.tracker_id]()
                if self.trk_init is None:
                    self.RemoveTracker()
                    self.choice_tracker.SetSelection(0)
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
                4: dt.RemoveTracker().PlhPatriot,
                5: dt.RemoveTracker().ZebrisCMS20}
        rem = remove_trck[self.tracker_rem_id]()
        self.trk_init = None

    def OnChoiceRefMode(self, evt):
        self.ref_mode_id = evt.GetSelection()
        print "Ref_Mode changed!"
        #When ref mode is changed the tracker coords are set as null, self.aux_trck is the flag that sets it
        self.SetTrackerFiducialsNone()

    def SetTrackerFiducialsNone(self):
        self.numCtrl1d.SetValue(0)
        self.numCtrl2d.SetValue(0)
        self.numCtrl3d.SetValue(0)
        self.aux_trck1 = 0

        self.numCtrl1e.SetValue(0)
        self.numCtrl2e.SetValue(0)
        self.numCtrl3e.SetValue(0)
        self.aux_trck2 = 0

        self.numCtrl1f.SetValue(0)
        self.numCtrl2f.SetValue(0)
        self.numCtrl3f.SetValue(0)
        self.aux_trck3 = 0

    def Coregister(self):
        self.M, self.q1, self.Minv = db.base_creation(self.coord1a,
                                                      self.coord2a,
                                                      self.coord3a)
        self.N, self.q2, self.Ninv = db.base_creation(self.coord1b,
                                                      self.coord2b,
                                                      self.coord3b)
        Publisher.sendMessage('Corregistrate Object', [self.Minv,
                                                       self.N,
                                                       self.q1,
                                                       self.q2,
                                                       self.trk_init,
                                                       self.tracker_id,
                                                       self.ref_mode_id,
                                                       self.a,
                                                       self.coord3a])

#===============================================================================
#===============================================================================
class ObjectWNeuronavigation(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)
        self.object_id = const.COILS
        self.aux_img__INO_ref=0
        self.showObj = None

        self.__bind_events()


        #Line 1

        text_choice = wx.StaticText(self, -1, _("Select the object:"))
        #Line 2
        choice_object = wx.ComboBox(self, -1, _("Select the object:"),
                                         size=(97, 23),
                                         choices = const.COILS,
                                         style = wx.CB_DROPDOWN|wx.CB_READONLY|wx.CB_SORT)
        choice_object.SetSelection(const.DEFAULT_COIL)
        choice_object.Bind(wx.EVT_COMBOBOX, self.OnChoiceObject)

        #Line 3
        correg_object= wx.Button(self, -1, label=_('Object registration'), size = wx.Size(125,23))
        correg_object.Bind(wx.EVT_BUTTON, self.OnCorregObject)
         
        self.button_img_inio = wx.ToggleButton(self, IR3, label = _('INO'), size = wx.Size(30,23))
        self.button_img_inio.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Inio_ToggleButton)
         
        self.plhButton = wx.CheckBox(self, -1, _('Activate Polhemus stylus button'), (10, 10))
        self.plhButton.SetValue(False)
        wx.EVT_CHECKBOX(self, self.plhButton.GetId(), self.PlhButton)

        self.numCtrl1I = wx.lib.masked.numctrl.NumCtrl(
             name='numCtrl1I', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2I = wx.lib.masked.numctrl.NumCtrl(
             name='numCtrl2I', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3I = wx.lib.masked.numctrl.NumCtrl(
             name='numCtrl3I', parent=self, integerWidth = 4, fractionWidth = 1)

        line2 = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        line2.AddMany([(choice_object, 1,wx.EXPAND|wx.LEFT|wx.TOP),
                       (correg_object, 1, wx.GROW|wx.EXPAND|wx.RIGHT|wx.TOP)])
         
        line3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        line3.AddMany([(self.button_img_inio),
                        (self.numCtrl1I),
                        (self.numCtrl2I),
                        (self.numCtrl3I)])
         
        main_sizer = wx.BoxSizer(wx.VERTICAL)        
        main_sizer.Add(text_choice, 0,wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP|wx.BOTTOM, 5)        
        main_sizer.Add(line2, 0,  wx.ALIGN_CENTER, 5)                  
        main_sizer.Add(line3, 0,  wx.ALIGN_CENTER|wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.TOP, 5)
        main_sizer.Add(self.plhButton, 0,  wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.TOP, 5)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

    def Img_Inio_ToggleButton(self, evt):
        img_id = self.button_img_inio.GetValue()
        x, y, z = self.a
        if img_id == True:
            self.img_inio = x, y, z
            self.aux_img__INO_ref = 1
            print self.img_inio
        elif img_id == False:
            self.aux_img__INO_ref = 0
            self.img_inio = (0, 0, 0)
            self.numCtrl1I.SetValue(x)
            self.numCtrl2I.SetValue(y)
            self.numCtrl3I.SetValue(z)

    def __bind_events(self):
        Publisher.subscribe(self.correget, 'Corregistrate Object')
        Publisher.subscribe(self.LoadParamObj, 'Load Param Obj')
        Publisher.subscribe(self.__update_points_img_INO, 'Update cross position')

    def __update_points_img_INO(self, pubsub_evt):
        x, y, z = pubsub_evt.data
        self.a = x, y, z
        if self.aux_img__INO_ref == 0:
            self.numCtrl1I.SetValue(x)
            self.numCtrl2I.SetValue(y)
            self.numCtrl3I.SetValue(z)

    def correget(self, pubsub_evt):
        self.Minv=pubsub_evt.data[0]
        self.N=pubsub_evt.data[1]
        self.q1=pubsub_evt.data[2]
        self.q2=pubsub_evt.data[3]
        self.trk_init=pubsub_evt.data[4]
        self.tracker_id=pubsub_evt.data[5]
        self.ref_mode_id=pubsub_evt.data[6]
        self.a=pubsub_evt.data[7]
        self.coord3a=pubsub_evt.data[8]
        #self.img_inio=pubsub_evt.data[9]

    def OnChoiceObject(self, evt):
        self.object_id = evt.GetSelection()
        self.object_name = self.choice_object.GetValue()
##        if self.object_name == " Add new object...":
##
##            self.choice_object.Append("")
##
##            self.choice_object.Update()
##
        print self.object_name

    def OnCorregObject(self, evt):
        id = evt.GetId()
        coil_orient = None
        bases = self.Minv, self.N, self.q1, self.q2
        tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id
        nav_prop = bases, tracker_mode, self.tracker_id
        self.dialog = dlg.ObjectCalibration(self, -1,
                                            _('InVesalius 3 - Calibration'),
                                            nav_prop = nav_prop)
        try:
            if self.dialog.ShowModal() == wx.ID_OK:
              
                coil_orient, self.coil_axis = self.dialog.GetValue
                self.showObj.SetValue(True)
                self.angle_tracking()
                Publisher.sendMessage('Change Init Coil Angle', coil_orient)
                Publisher.sendMessage('Track Coil Angle', (self.coil_axis,
                                                           self.ap_axis))
        except wx.core.PyAssertionError:  # TODO FIX: win64
            None
#         print "coil_orient: ", coil_orient

#
    def LoadParamObj(self, pubsub_evt):
        coil_orient, self.coil_axis = self.dialog.GetValue
        self.showObj.SetValue(True)
        self.angle_tracking()
        Publisher.sendMessage('Track Coil Angle', (self.coil_axis,
                                                   self.ap_axis))
        Publisher.sendMessage('Change Init Coil Angle', coil_orient)
            
              
    def PlhButton(self, evt):
        #TODO: PLHbutton checkbox
        None
        #wx.CallAfter(Publisher.sendMessage, 'Stylus Button', self.plhButton.Value)
        #Publisher.sendMessage('Hide Show Object', self.showObj.Value)

    def angle_tracking(self):
        # self.ap_axis = db.AP_calculus(self.img_inio, self.coord3a)
        # print self.ap_axis
        p1 = np.array(self.img_inio[0:2])
        p2 = np.array(self.coord3a[0:2])
        # return p1 - p2
        self.ap_axis = p1 - p2

#===============================================================================
#===============================================================================        
class Markers(wx.Panel):
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
        ID = dlg.enter_ID(self.lc.GetItemText(self.lc.GetFocusedItem(), 4))
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

        Publisher.sendMessage('Create ball', (self.ballid, size, colour,  coord))
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
            #adding actual line to a list of all markers already created
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
        Publisher.sendMessage('Remove Markers', self.lc.GetItemCount())
        self.lc.DeleteAllItems()
        self.ballid = 0

    def DelSingleMarker(self, pubsub_evt):
        ##this try is to remove the toggle=false fiducial marker, doesnt matter the order
        try:
            id = pubsub_evt.data
            for idx in range(self.lc.GetItemCount()):
                item = self.lc.GetItem(idx, 4)
                if item.GetText() == id:
                    if id == "LTI":
                        self.lc.Focus(item.GetId())
                        break
                    if id == "RTI":
                        self.lc.Focus(item.GetId())
                        break
                    if id == "NI":
                        self.lc.Focus(item.GetId())
                        break
        except:
            None

        if self.lc.GetFocusedItem() is not -1:
            index = self.lc.GetFocusedItem()
            del self.list_coord[index]
            self.lc.DeleteItem(index)
            for x in range(0,self.lc.GetItemCount()):
                self.lc.SetStringItem(x, 0, str(x+1))
            self.ballid = self.ballid - 1
            Publisher.sendMessage('Remove Single Marker', index)
        else:
            dlg.NoDataSelected()
    
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
                        Publisher.sendMessage('Load Fiducial', (self.fiducial_ID,coord))
                    else:
                        self.fiducial_flag = 0
                    self.CreateMarker(coord, colour, size)
            except:
                dlg.InvalidTxt()
                raise ValueError('Invalid Txt File')
        else:
            None

    def OnMarkersVisibility(self, evt):
        ballid = self.lc.GetItemCount()
        flag5 = self.markers_visibility.GetValue()
        if flag5 == True:
            Publisher.sendMessage('Hide balls',  ballid)
            self.markers_visibility.SetLabel('Show')
        elif flag5 == False:
            Publisher.sendMessage('Show balls',  ballid)
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

