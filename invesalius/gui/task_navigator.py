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
import wx.lib.masked.numctrl
from wx.lib.pubsub import pub as Publisher

import constants as const
import data.bases as db
import data.corregistration as dcr
import data.trackers as dt
import data.coordinates as dco
import gui.dialogs as dlg
import gui.widgets.foldpanelbar as fpb
import gui.widgets.colourselect as csel


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
        wx.Panel.__init__(self, parent, size=wx.Size(0,310))
        default_color = self.GetBackgroundColour()
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        self.SetAutoLayout(1)

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
        item = fold_panel.AddFoldPanel(_("Object Registration"), collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ObjectWNeuronavigation(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)

        # Fold 3 - Surface tools
        item = fold_panel.AddFoldPanel(_("Extra Tools"), collapsed=True)
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
INO = wx.NewId()
Neuronavigate = wx.NewId()
FineCorregistration = wx.NewId()
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
        self.aux_trck_ref1 = 1
        self.aux_trck_ref2 = 1
        self.aux_trck_ref3 = 1
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
        
        #Combo Box
        choice_tracker = wx.ComboBox(self, -1, "", size=(130, 23),
                                     choices = const.TRACKER, style = wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_tracker.SetSelection(const.DEFAULT_TRACKER)
        choice_tracker.Bind(wx.EVT_COMBOBOX, self.OnChoiceTracker)
        
        choice_ref_mode = wx.ComboBox(self, -1, "", size=(120, 23),
                                     choices = const.REF_MODE, style = wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_ref_mode.SetSelection(const.DEFAULT_REF_MODE)
        choice_ref_mode.Bind(wx.EVT_COMBOBOX, self.OnChoiceRefMode)
        
        
        self.button_img_ref1 = wx.ToggleButton(self, IR1, label = _('LTI'), size = wx.Size(30,23))
        self.button_img_ref1.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton1)
        
        self.button_img_ref2 = wx.ToggleButton(self, IR2, label = _('RTI'), size = wx.Size(30,23))
        self.button_img_ref2.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton2)
        
        self.button_img_ref3 = wx.ToggleButton(self, IR3, label = _('RI'), size = wx.Size(30,23))
        self.button_img_ref3.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton3)
        
        #self.button_img_inio = wx.ToggleButton(self, INO, label = 'INO', size = wx.Size(30,23))
        #self.button_img_inio.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Inio_ToggleButton)
        
        self.button_trck_ref1 = wx.Button(self, TR1, label = _('LTT'), size = wx.Size(30,23))
        self.button_trck_ref2 = wx.Button(self, TR2, label = _('RTT'), size = wx.Size(30,23))
        self.button_trck_ref3 = wx.Button(self, TR3, label = _('NT'), size = wx.Size(30,23))
        
        
        self.button_crg = wx.Button(self, FineCorregistration, label=_('Accurate Corregistrate'))
        self.Bind(wx.EVT_BUTTON, self.Buttons)
                       
        self.button_neuronavigate = wx.ToggleButton(self, Neuronavigate, _("Neuronavigate"))
        self.button_neuronavigate.Bind(wx.EVT_TOGGLEBUTTON, self.Neuronavigate_ToggleButton)
        
        #self.numCtrl1I = wx.lib.masked.numctrl.NumCtrl(
        #    name='numCtrl1I', parent=self, integerWidth = 4, fractionWidth = 1)
        #self.numCtrl2I = wx.lib.masked.numctrl.NumCtrl(
        #    name='numCtrl2I', parent=self, integerWidth = 4, fractionWidth = 1)
        #self.numCtrl3I = wx.lib.masked.numctrl.NumCtrl(
        #    name='numCtrl3I', parent=self, integerWidth = 4, fractionWidth = 1)
        
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

        choice_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        choice_sizer.AddMany([ (choice_tracker, wx.LEFT),
                                (choice_ref_mode, wx.RIGHT)])
        
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
        #line3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        #line3.AddMany([(self.button_img_inio),
        #               (self.numCtrl1I),
        #               (self.numCtrl2I),
        #               (self.numCtrl3I)])
        
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
                            #(line3, 0,wx.ALIGN_CENTER_HORIZONTAL),
                            (Buttons_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)])
        
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(Ref_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

    def __bind_events(self):
        Publisher.subscribe(self.__update_points_img, 'Update cross position')
        Publisher.subscribe(self.__update_points_trck, 'Update tracker position')
                 
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
        #if self.aux_img__INO_ref == 0:
        #    self.numCtrl1I.SetValue(x)
        #    self.numCtrl2I.SetValue(y)
        #    self.numCtrl3I.SetValue(z)

    def __update_points_trck(self, pubsub_evt):
        coord = pubsub_evt.data   
        if self.aux_trck_ref1 == 0:    
            self.numCtrl1d.SetValue(coord[0])
            self.numCtrl2d.SetValue(coord[1])
            self.numCtrl3d.SetValue(coord[2])
            self.aux_trck_ref1 = 1
        if self.aux_trck_ref2 == 0:    
            self.numCtrl1e.SetValue(coord[0])
            self.numCtrl2e.SetValue(coord[1])
            self.numCtrl3e.SetValue(coord[2])
            self.aux_trck_ref2 = 1
        if self.aux_trck_ref3 == 0:
            self.numCtrl1f.SetValue(coord[0])
            self.numCtrl2f.SetValue(coord[1])
            self.numCtrl3f.SetValue(coord[2])
            self.aux_trck_ref3 = 1
           
    def Buttons(self, evt):
        id = evt.GetId()
        x, y, z = self.a
        if id == TR1:
            self.aux_trck_ref1 = 0
            self.coord1b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
            coord = self.coord1b[0:3]
        elif id == TR2:
            self.aux_trck_ref2 = 0
            self.coord2b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
            coord = self.coord2b[0:3]
        elif id == TR3:
            self.aux_trck_ref3 = 0
            self.coord3b = dco.Coordinates(self.trk_init, self.tracker_id, self.ref_mode_id).Returns()
            coord = self.coord3b[0:3]            
        elif id == FineCorregistration:
            self.Corregistration()
            dialog = dlg.FineCalibration(self, -1, _('InVesalius 3 - Calibration'))
                        
        if self.aux_trck_ref1 == 0 or self.aux_trck_ref2 == 0 or self.aux_trck_ref3 == 0:
            Publisher.sendMessage('Update tracker position', coord)         
    
    def Img_Ref_ToggleButton1(self, evt):
        img_id = self.button_img_ref1.GetValue()
        #this fixed points are from dicom2 exam
        x, y, z = self.a
#        x, y, z = 201.1, 113.3, 31.5
        if img_id == True:
            self.coord1a = x, y, z
            self.aux_img_ref1 = 1
            Publisher.sendMessage("Create fiducial markers", (self.coord1a, "LTI"))

        elif img_id == False:
            self.aux_img_ref1 = 0
            self.coord1a = (0, 0, 0)
            self.numCtrl1a.SetValue(x)
            self.numCtrl2a.SetValue(y)
            self.numCtrl3a.SetValue(z)
            
    def Img_Ref_ToggleButton2(self, evt):
        img_id = self.button_img_ref2.GetValue()
        #this fixed points are from dicom2 exam
        x, y, z = self.a
#        x, y, z = 50.4, 113.3, 30.0
        if img_id == True:
            self.coord2a = x, y, z
            self.aux_img_ref2 = 1
            Publisher.sendMessage("Create fiducial markers", (self.coord2a, "RTI"))
        elif img_id == False:
            self.aux_img_ref2 = 0
            self.coord2a = (0, 0, 0)
            self.numCtrl1b.SetValue(x)
            self.numCtrl2b.SetValue(y)
            self.numCtrl3b.SetValue(z)
            
    def Img_Ref_ToggleButton3(self, evt):
        img_id = self.button_img_ref3.GetValue()
        #this fixed points are from dicom2 exam
        x, y, z = self.a
#        x, y, z = 123.4, 207.4, 67.5
        if img_id == True:
            self.coord3a = x, y, z
            self.aux_img_ref3 = 1
            Publisher.sendMessage("Create fiducial markers", (self.coord3a, "RI"))
        elif img_id == False:
            self.aux_img_ref3 = 0
            self.coord3a = (0, 0, 0)
            self.numCtrl1c.SetValue(x)
            self.numCtrl2c.SetValue(y)
            self.numCtrl3c.SetValue(z)
    
#    def Img_Inio_ToggleButton(self, evt):
#        img_id = self.button_img_inio.GetValue()
#        x, y, z = self.a
#        if img_id == True:
#            self.img_inio = x, y, z
#            self.aux_img__INO_ref = 1
#            print self.img_inio
#        elif img_id == False:
#            self.aux_img__INO_ref = 0
#            self.img_inio = (0, 0, 0)
#            self.numCtrl1I.SetValue(x)
#            self.numCtrl2I.SetValue(y)
#            self.numCtrl3I.SetValue(z)
            
    def Neuronavigate_ToggleButton(self, evt):
        nav_id = self.button_neuronavigate.GetValue()
        self.Corregistration() 
        bases = self.Minv, self.N, self.q1, self.q2
        tracker_mode = self.trk_init, self.tracker_id, self.ref_mode_id
        if nav_id == True:
            self.correg = dcr.Corregistration(bases, nav_id, tracker_mode)
        elif nav_id == False:
            self.correg.stop()
            
    def OnChoiceTracker(self, evt):
        trck_id = evt.GetSelection()

        # self.trk_init = dco.Tracker().ReturnTracker(trck_id)
        self.trk_init = dt.Tracker(trck_id)

        # if self.tracker_id == 0:
        #     self.trk_init = dtrk.Tracker_Init().PolhemusISO_init()
        #     print self.trk_init
        #
        # elif self.tracker_id == 1:
        #     self.trk_init = dtrk.Tracker_Init().Polhemus_init()
        #     print self.trk_init
        #
        # elif self.tracker_id == 2:
        #     #review this close command: when for example
        #     #you jump from MTC to Zebris, it will try
        #     #to close the MTC, but it doesnt have a close attribute
        #     #self.trk_init.close()
        #     self.trk_init = dtrk.Tracker_Init().Claron_init()
        #     print self.trk_init
        # elif self.tracker_id == 3:
        #     self.trk_init = dtrk.Tracker_Init().Zebris_init()
        #     print self.trk_init
            
        print "Tracker changed!"
    
    def OnChoiceRefMode(self, evt):
        self.ref_mode_id = evt.GetSelection()
        print "Ref_Mode changed!" 
        
    def Corregistration(self):
      
        if self.aux_img_ref1 and self.aux_img_ref2 and self.aux_img_ref3:
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

        text_choice = wx.StaticText(self, -1, _("Select the Object:"))  
        #Line 2      
        choice_object = wx.ComboBox(self, -1, _("Select the Object:"),
                                         size=(97, 23),
                                         choices = const.COILS,
                                         style = wx.CB_DROPDOWN|wx.CB_READONLY|wx.CB_SORT)
        choice_object.SetSelection(const.DEFAULT_COIL)
        choice_object.Bind(wx.EVT_COMBOBOX, self.OnChoiceObject)
             
        #Line 3
        correg_object= wx.Button(self, -1, label=_('Object Registration'), size = wx.Size(125,23))
        correg_object.Bind(wx.EVT_BUTTON, self.OnCorregObject)
         
        self.button_img_inio = wx.ToggleButton(self, IR3, label = _('INO'), size = wx.Size(30,23))
        self.button_img_inio.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Inio_ToggleButton)
         
        self.showObj = wx.CheckBox(self, -1, _('Show Object'), (10, 10))
        self.showObj.SetValue(False)
        wx.EVT_CHECKBOX(self, self.showObj.GetId(), self.ShowObject)    

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
        main_sizer.Add(self.showObj, 0,  wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.TOP, 5)
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
            
              
    def ShowObject(self, evt):
        Publisher.sendMessage('Hide Show Object', self.showObj.Value)
             
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

        create_markers = wx.Button(self, -1, label=_('Create Marker'), size=wx.Size(135, 23))
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

        del_markers = wx.Button(self, -1, label=_('Delete All Markers'), size=wx.Size(135, 23))
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
        self.lc.SetColumnWidth(0, 25)
        self.lc.SetColumnWidth(1, 50)
        self.lc.SetColumnWidth(2, 50)
        self.lc.SetColumnWidth(3, 50)
        self.lc.SetColumnWidth(4, 50)

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
        Publisher.subscribe(self.Fiducial_markers, 'Create fiducial markers')

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
        line = coord[0] , coord[1] , coord[2] , colour[0], colour[1], colour[2], self.spin.GetValue(), self.fiducial_ID
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
        if self.lc.GetFocusedItem() is not -1:
            index = self.lc.GetFocusedItem()
            del self.list_coord[index]
            self.lc.DeleteItem(index)
            for x in range(0,self.lc.GetItemCount()):
                self.lc.SetStringItem(x, 0, str(x+1))
            self.ballid = self.ballid - 1
            Publisher.sendMessage('Remove Single Marker', index)
        else:
            print "No data selected"
    
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
        print "Reading the points!"
        #TODO: ver bug de fazer load dos pontos sem ter clicado na cruz antes (criacao de ator e tal)
        
        filepath = dlg.ShowLoadMarkersDialog()
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
                else:
                    self.fiducial_flag = 0
                self.CreateMarker(coord, colour, size)
        except:
            dlg.InvalidTxt()
            raise ValueError('Invalid Txt File')

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
        print "Save the points!"

        filename = dlg.ShowSaveMarkersDialog("Markers.txt")
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
    
    
    def OnSelectColour(self, evt):
        self.colour = [value/255.0 for value in self.marker_colour.GetValue()]

