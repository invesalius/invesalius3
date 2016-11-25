<<<<<<< HEAD
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

import os
import sys

import serial
import wx
import wx.lib.hyperlink as hl
import wx.lib.masked.numctrl
import wx.lib.platebtn as pbtn
from wx.lib.pubsub import pub as Publisher

import data.bases as db
import data.co_registration as dcr
import project

IR1 = wx.NewId()
IR2 = wx.NewId()
IR3 = wx.NewId()
PR1 = wx.NewId()
PR2 = wx.NewId()
PR3 = wx.NewId()
Neuronavigate = wx.NewId()
Corregistration = wx.NewId()
GetPoint = wx.NewId()

class TaskPanel(wx.Panel):
    """
    This panel works as a "frame", drawing a white margin arround 
    the panel that really matters (InnerTaskPanel).
    """
    def __init__(self, parent):
        # note: don't change this class!!!
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 8)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class InnerTaskPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320,300))
        self.SetBackgroundColour(wx.Colour(221, 221, 221, 255))
        self.SetAutoLayout(1)
        self.__bind_events()

        self.aux_img_ref1 = 0
        self.aux_img_ref2 = 0
        self.aux_img_ref3 = 0
        self.flagpoint = 0
        self.aux_plh_ref1 = 1
        self.aux_plh_ref2 = 1
        self.aux_plh_ref3 = 1
        self.a = 0, 0, 0
        self.coord1a = (0, 0, 0)
        self.coord2a = (0, 0, 0)
        self.coord3a = (0, 0, 0)
        self.coord1b = (0, 0, 0)
        self.coord2b = (0, 0, 0)
        self.coord3b = (0, 0, 0)
        self.correg = None
                

        self.button_img_ref1 = wx.ToggleButton(self, IR1, label = 'TEI', size = wx.Size(30,23))
        self.button_img_ref1.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton1)
        
        self.button_img_ref2 = wx.ToggleButton(self, IR2, label = 'TDI', size = wx.Size(30,23))
        self.button_img_ref2.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton2)
        
        self.button_img_ref3 = wx.ToggleButton(self, IR3, label = 'FNI', size = wx.Size(30,23))
        self.button_img_ref3.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton3)

        self.button_plh_ref1 = wx.Button(self, PR1, label = 'TEP', size = wx.Size(30,23))
        self.button_plh_ref2 = wx.Button(self, PR2, label = 'TDP', size = wx.Size(30,23))
        self.button_plh_ref3 = wx.Button(self, PR3, label = 'FNP', size = wx.Size(30,23))
        self.button_crg = wx.Button(self, Corregistration, label = 'Corregistrate')
        self.button_getpoint = wx.Button(self, GetPoint, label = 'GP', size = wx.Size(23,23))
        self.Bind(wx.EVT_BUTTON, self.Buttons)
                       
        self.button_neuronavigate = wx.ToggleButton(self, Neuronavigate, "Neuronavigate")
        self.button_neuronavigate.Bind(wx.EVT_TOGGLEBUTTON, self.Neuronavigate_ToggleButton)
        
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
        self.numCtrl1g = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1g', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2g = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2g', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3g = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3g', parent=self, integerWidth = 4, fractionWidth = 1)

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
        RefPlh_sizer1.AddMany([ (self.button_plh_ref1, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1d, wx.RIGHT),
                                (self.numCtrl2d),
                                (self.numCtrl3d, wx.LEFT)])
        
        RefPlh_sizer2 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer2.AddMany([ (self.button_plh_ref2, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1e, 0, wx.RIGHT),
                                (self.numCtrl2e),
                                (self.numCtrl3e, 0, wx.LEFT)])
        
        RefPlh_sizer3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer3.AddMany([ (self.button_plh_ref3, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1f, wx.RIGHT),
                                (self.numCtrl2f),
                                (self.numCtrl3f, wx.LEFT)])
        
        Buttons_sizer4 = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        Buttons_sizer4.AddMany([ (self.button_crg, wx.RIGHT),
                                (self.button_neuronavigate, wx.LEFT)])
        
        GetPoint_sizer5 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        GetPoint_sizer5.AddMany([ (self.button_getpoint, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1g, wx.RIGHT),
                                (self.numCtrl2g),
                                (self.numCtrl3g, wx.LEFT)])
        
        text = wx.StaticText(self, -1, 'Neuronavigator')
        
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
        Ref_sizer.AddMany([ (text, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer1, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer2, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer3, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer1, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer2, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer3, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (Buttons_sizer4, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (GetPoint_sizer5, 0, wx.ALIGN_CENTER_HORIZONTAL)])
        
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(Ref_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the image")
        self.button_img_ref1.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the image")
        self.button_img_ref2.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the image")
        self.button_img_ref3.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the space")
        self.button_plh_ref1.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the space")
        self.button_plh_ref2.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the space")
        self.button_plh_ref3.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1a.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1b.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1c.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1d.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1e.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1f.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1g.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2a.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2b.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2c.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2d.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2e.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2f.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2g.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3a.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3b.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3c.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3d.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3e.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3f.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3g.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Corregistration of the real position with the image position")
        self.button_crg.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Neuronavigation")
        self.button_neuronavigate.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Get Cross Center Coordinates")
        self.button_getpoint.SetToolTip(tooltip)
        
    def __bind_events(self):
        Publisher.subscribe(self.__update_points_img, 'Update cross position')
        Publisher.subscribe(self.__update_points_plh, 'Update plh position')
         
    def __update_points_img(self, pubsub_evt):
        x, y, z = pubsub_evt.data[1]
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

        
    def __update_points_plh(self, pubsub_evt):
        coord = pubsub_evt.data   
        if self.aux_plh_ref1 == 0:    
            self.numCtrl1d.SetValue(coord[0])
            self.numCtrl2d.SetValue(coord[1])
            self.numCtrl3d.SetValue(coord[2])
            self.aux_plh_ref1 = 1
        if self.aux_plh_ref2 == 0:    
            self.numCtrl1e.SetValue(coord[0])
            self.numCtrl2e.SetValue(coord[1])
            self.numCtrl3e.SetValue(coord[2])
            self.aux_plh_ref2 = 1
        if self.aux_plh_ref3 == 0:
            self.numCtrl1f.SetValue(coord[0])
            self.numCtrl2f.SetValue(coord[1])
            self.numCtrl3f.SetValue(coord[2])
            self.aux_plh_ref3 = 1
           
    def Buttons(self, evt):
        id = evt.GetId()
        x, y, z = self.a
        if id == PR1:
            self.aux_plh_ref1 = 0
            self.coord1b = self.Coordinates()
            coord = self.coord1b
        elif id == PR2:
            self.aux_plh_ref2 = 0
            self.coord2b = self.Coordinates()
            coord = self.coord2b
        elif id == PR3:
            self.aux_plh_ref3 = 0
            self.coord3b = self.Coordinates()
            coord = self.coord3b
        elif id == GetPoint:
            x, y, z = self.a
            self.numCtrl1g.SetValue(x)
            self.numCtrl2g.SetValue(y)
            self.numCtrl3g.SetValue(z)
            info = self.a, self.flagpoint
            self.SaveCoordinates(info)
            self.flagpoint = 1 
        elif id == Corregistration and self.aux_img_ref1 == 1 and self.aux_img_ref2 == 1 and self.aux_img_ref3 == 1:
            print "Coordenadas Imagem: ", self.coord1a, self.coord2a, self.coord3a
            print "Coordenadas Polhemus: ", self.coord1b, self.coord2b, self.coord3b
            
            self.M, self.q1, self.Minv = db.Bases(self.coord1a, self.coord2a, self.coord3a).Basecreation()
            self.N, self.q2, self.Ninv = db.Bases(self.coord1b, self.coord2b, self.coord3b).Basecreation()
                
        if self.aux_plh_ref1 == 0 or self.aux_plh_ref2 == 0 or self.aux_plh_ref3 == 0:
            Publisher.sendMessage('Update plh position', coord)         
   
    def Coordinates(self):
        #Get Polhemus points for base creation       
        ser = serial.Serial(0)
        ser.write("Y")       
        ser.write("P")
        str = ser.readline()
        ser.write("Y")
        str = str.replace("\r\n","")
        str = str.replace("-"," -")
        aostr = [s for s in str.split()]
        #aoflt -> 0:letter 1:x 2:y 3:z
        aoflt = [float(aostr[1]), float(aostr[2]), float(aostr[3]),
                  float(aostr[4]), float(aostr[5]), float(aostr[6])]      
        ser.close()
        #Unit change: inches to millimeters
        x = 25.4
        y = 25.4
        z = -25.4

        coord = (aoflt[0]*x, aoflt[1]*y, aoflt[2]*z)
        return coord
    
    def Img_Ref_ToggleButton1(self, evt):
        id = evt.GetId()
        flag1 = self.button_img_ref1.GetValue()
        x, y, z = self.a
        if flag1 == True:
            self.coord1a = x, y, z
            self.aux_img_ref1 = 1
        elif flag1 == False:
            self.aux_img_ref1 = 0
            self.coord1a = (0, 0, 0)
            self.numCtrl1a.SetValue(x)
            self.numCtrl2a.SetValue(y)
            self.numCtrl3a.SetValue(z)
            
    def Img_Ref_ToggleButton2(self, evt):
        id = evt.GetId()
        flag2 = self.button_img_ref2.GetValue()
        x, y, z = self.a
        if flag2 == True:
            self.coord2a = x, y, z
            self.aux_img_ref2 = 1
        elif flag2 == False:
            self.aux_img_ref2 = 0
            self.coord2a = (0, 0, 0)
            self.numCtrl1b.SetValue(x)
            self.numCtrl2b.SetValue(y)
            self.numCtrl3b.SetValue(z)
            
    def Img_Ref_ToggleButton3(self, evt):
        id = evt.GetId()
        flag3 = self.button_img_ref3.GetValue()
        x, y, z = self.a
        if flag3 == True:
            self.coord3a = x, y, z
            self.aux_img_ref3 = 1
        elif flag3 == False:
            self.aux_img_ref3 = 0
            self.coord3a = (0, 0, 0)
            self.numCtrl1c.SetValue(x)
            self.numCtrl2c.SetValue(y)
            self.numCtrl3c.SetValue(z)
      
    def Neuronavigate_ToggleButton(self, evt):
        id = evt.GetId()
        flag4 = self.button_neuronavigate.GetValue()
        bases = self.Minv, self.N, self.q1, self.q2
        if flag4 == True:
            self.correg = dcr.Corregister(bases, flag4)
        elif flag4 == False:
            self.correg.stop()
    
    def SaveCoordinates(self, info):
        #Create a file and write the points given by getpoint's button 
        x, y, z = info[0]
        flag = info[1]

        if flag == 0:
            text_file = open("points.txt", "w")
            line = str('%.2f' %x) + "\t" + str('%.2f' %y) + "\t" + str('%.2f' %z) + "\n"
            text_file.writelines(line)
            text_file.close()
        else:
            text_file = open("points.txt", "r")
            filedata = text_file.read()
            line = filedata + str('%.2f' %x) + "\t" + str('%.2f' %y) + "\t" + str('%.2f' %z) + "\n"
            text_file = open("points.txt", "w")
            text_file.write(line)
            text_file.close()
        
=======
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

import os
import sys

import serial
import wx
import wx.lib.hyperlink as hl
import wx.lib.masked.numctrl
import wx.lib.platebtn as pbtn
from wx.lib.pubsub import pub as Publisher

import invesalius.data.bases as db
import invesalius.data.co_registration as dcr
import invesalius.project as project
IR1 = wx.NewId()
IR2 = wx.NewId()
IR3 = wx.NewId()
PR1 = wx.NewId()
PR2 = wx.NewId()
PR3 = wx.NewId()
Neuronavigate = wx.NewId()
Corregistration = wx.NewId()
GetPoint = wx.NewId()

class TaskPanel(wx.Panel):
    """
    This panel works as a "frame", drawing a white margin arround 
    the panel that really matters (InnerTaskPanel).
    """
    def __init__(self, parent):
        # note: don't change this class!!!
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 8)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class InnerTaskPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320,300))
        self.SetBackgroundColour(wx.Colour(221, 221, 221, 255))
        self.SetAutoLayout(1)
        self.__bind_events()

        self.aux_img_ref1 = 0
        self.aux_img_ref2 = 0
        self.aux_img_ref3 = 0
        self.flagpoint = 0
        self.aux_plh_ref1 = 1
        self.aux_plh_ref2 = 1
        self.aux_plh_ref3 = 1
        self.a = 0, 0, 0
        self.coord1a = (0, 0, 0)
        self.coord2a = (0, 0, 0)
        self.coord3a = (0, 0, 0)
        self.coord1b = (0, 0, 0)
        self.coord2b = (0, 0, 0)
        self.coord3b = (0, 0, 0)
        self.correg = None
                

        self.button_img_ref1 = wx.ToggleButton(self, IR1, label = 'TEI', size = wx.Size(30,23))
        self.button_img_ref1.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton1)
        
        self.button_img_ref2 = wx.ToggleButton(self, IR2, label = 'TDI', size = wx.Size(30,23))
        self.button_img_ref2.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton2)
        
        self.button_img_ref3 = wx.ToggleButton(self, IR3, label = 'FNI', size = wx.Size(30,23))
        self.button_img_ref3.Bind(wx.EVT_TOGGLEBUTTON, self.Img_Ref_ToggleButton3)

        self.button_plh_ref1 = wx.Button(self, PR1, label = 'TEP', size = wx.Size(30,23))
        self.button_plh_ref2 = wx.Button(self, PR2, label = 'TDP', size = wx.Size(30,23))
        self.button_plh_ref3 = wx.Button(self, PR3, label = 'FNP', size = wx.Size(30,23))
        self.button_crg = wx.Button(self, Corregistration, label = 'Corregistrate')
        self.button_getpoint = wx.Button(self, GetPoint, label = 'GP', size = wx.Size(23,23))
        self.Bind(wx.EVT_BUTTON, self.Buttons)
                       
        self.button_neuronavigate = wx.ToggleButton(self, Neuronavigate, "Neuronavigate")
        self.button_neuronavigate.Bind(wx.EVT_TOGGLEBUTTON, self.Neuronavigate_ToggleButton)
        
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
        self.numCtrl1g = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl1g', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl2g = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl2g', parent=self, integerWidth = 4, fractionWidth = 1)
        self.numCtrl3g = wx.lib.masked.numctrl.NumCtrl(
            name='numCtrl3g', parent=self, integerWidth = 4, fractionWidth = 1)

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
        RefPlh_sizer1.AddMany([ (self.button_plh_ref1, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1d, wx.RIGHT),
                                (self.numCtrl2d),
                                (self.numCtrl3d, wx.LEFT)])
        
        RefPlh_sizer2 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer2.AddMany([ (self.button_plh_ref2, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1e, 0, wx.RIGHT),
                                (self.numCtrl2e),
                                (self.numCtrl3e, 0, wx.LEFT)])
        
        RefPlh_sizer3 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        RefPlh_sizer3.AddMany([ (self.button_plh_ref3, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1f, wx.RIGHT),
                                (self.numCtrl2f),
                                (self.numCtrl3f, wx.LEFT)])
        
        Buttons_sizer4 = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        Buttons_sizer4.AddMany([ (self.button_crg, wx.RIGHT),
                                (self.button_neuronavigate, wx.LEFT)])
        
        GetPoint_sizer5 = wx.FlexGridSizer(rows=1, cols=4, hgap=5, vgap=5)
        GetPoint_sizer5.AddMany([ (self.button_getpoint, 0, wx.GROW|wx.EXPAND),
                                (self.numCtrl1g, wx.RIGHT),
                                (self.numCtrl2g),
                                (self.numCtrl3g, wx.LEFT)])
        
        text = wx.StaticText(self, -1, 'Neuronavigator')
        
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
        Ref_sizer.AddMany([ (text, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer1, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer2, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefImg_sizer3, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer1, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer2, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (RefPlh_sizer3, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (Buttons_sizer4, 0, wx.ALIGN_CENTER_HORIZONTAL),
                            (GetPoint_sizer5, 0, wx.ALIGN_CENTER_HORIZONTAL)])
        
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(Ref_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.sizer = main_sizer
        self.SetSizer(main_sizer)
        self.Fit()

        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the image")
        self.button_img_ref1.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the image")
        self.button_img_ref2.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the image")
        self.button_img_ref3.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the space")
        self.button_plh_ref1.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the space")
        self.button_plh_ref2.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Pick the coordinates x, y, z in the space")
        self.button_plh_ref3.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1a.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1b.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1c.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1d.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1e.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1f.SetToolTip(tooltip)
        tooltip = wx.ToolTip("X Coordinate")
        self.numCtrl1g.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2a.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2b.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2c.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2d.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2e.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2f.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Y Coordinate")
        self.numCtrl2g.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3a.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3b.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3c.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3d.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3e.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3f.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Z Coordinate")
        self.numCtrl3g.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Corregistration of the real position with the image position")
        self.button_crg.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Neuronavigation")
        self.button_neuronavigate.SetToolTip(tooltip)
        tooltip = wx.ToolTip("Get Cross Center Coordinates")
        self.button_getpoint.SetToolTip(tooltip)
        
    def __bind_events(self):
        Publisher.subscribe(self.__update_points_img, 'Update cross position')
        Publisher.subscribe(self.__update_points_plh, 'Update plh position')
         
    def __update_points_img(self, pubsub_evt):
        x, y, z = pubsub_evt.data[1]
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

        
    def __update_points_plh(self, pubsub_evt):
        coord = pubsub_evt.data   
        if self.aux_plh_ref1 == 0:    
            self.numCtrl1d.SetValue(coord[0])
            self.numCtrl2d.SetValue(coord[1])
            self.numCtrl3d.SetValue(coord[2])
            self.aux_plh_ref1 = 1
        if self.aux_plh_ref2 == 0:    
            self.numCtrl1e.SetValue(coord[0])
            self.numCtrl2e.SetValue(coord[1])
            self.numCtrl3e.SetValue(coord[2])
            self.aux_plh_ref2 = 1
        if self.aux_plh_ref3 == 0:
            self.numCtrl1f.SetValue(coord[0])
            self.numCtrl2f.SetValue(coord[1])
            self.numCtrl3f.SetValue(coord[2])
            self.aux_plh_ref3 = 1
           
    def Buttons(self, evt):
        id = evt.GetId()
        x, y, z = self.a
        if id == PR1:
            self.aux_plh_ref1 = 0
            self.coord1b = self.Coordinates()
            coord = self.coord1b
        elif id == PR2:
            self.aux_plh_ref2 = 0
            self.coord2b = self.Coordinates()
            coord = self.coord2b
        elif id == PR3:
            self.aux_plh_ref3 = 0
            self.coord3b = self.Coordinates()
            coord = self.coord3b
        elif id == GetPoint:
            x, y, z = self.a
            self.numCtrl1g.SetValue(x)
            self.numCtrl2g.SetValue(y)
            self.numCtrl3g.SetValue(z)
            info = self.a, self.flagpoint
            self.SaveCoordinates(info)
            self.flagpoint = 1 
        elif id == Corregistration and self.aux_img_ref1 == 1 and self.aux_img_ref2 == 1 and self.aux_img_ref3 == 1:
            print "Coordenadas Imagem: ", self.coord1a, self.coord2a, self.coord3a
            print "Coordenadas Polhemus: ", self.coord1b, self.coord2b, self.coord3b
            
            self.M, self.q1, self.Minv = db.Bases(self.coord1a, self.coord2a, self.coord3a).Basecreation()
            self.N, self.q2, self.Ninv = db.Bases(self.coord1b, self.coord2b, self.coord3b).Basecreation()
                
        if self.aux_plh_ref1 == 0 or self.aux_plh_ref2 == 0 or self.aux_plh_ref3 == 0:
            Publisher.sendMessage('Update plh position', coord)         
   
    def Coordinates(self):
        #Get Polhemus points for base creation       
        ser = serial.Serial(0)
        ser.write("Y")       
        ser.write("P")
        str = ser.readline()
        ser.write("Y")
        str = str.replace("\r\n","")
        str = str.replace("-"," -")
        aostr = [s for s in str.split()]
        #aoflt -> 0:letter 1:x 2:y 3:z
        aoflt = [float(aostr[1]), float(aostr[2]), float(aostr[3]),
                  float(aostr[4]), float(aostr[5]), float(aostr[6])]      
        ser.close()
        #Unit change: inches to millimeters
        x = 25.4
        y = 25.4
        z = -25.4

        coord = (aoflt[0]*x, aoflt[1]*y, aoflt[2]*z)
        return coord
    
    def Img_Ref_ToggleButton1(self, evt):
        id = evt.GetId()
        flag1 = self.button_img_ref1.GetValue()
        x, y, z = self.a
        if flag1 == True:
            self.coord1a = x, y, z
            self.aux_img_ref1 = 1
        elif flag1 == False:
            self.aux_img_ref1 = 0
            self.coord1a = (0, 0, 0)
            self.numCtrl1a.SetValue(x)
            self.numCtrl2a.SetValue(y)
            self.numCtrl3a.SetValue(z)
            
    def Img_Ref_ToggleButton2(self, evt):
        id = evt.GetId()
        flag2 = self.button_img_ref2.GetValue()
        x, y, z = self.a
        if flag2 == True:
            self.coord2a = x, y, z
            self.aux_img_ref2 = 1
        elif flag2 == False:
            self.aux_img_ref2 = 0
            self.coord2a = (0, 0, 0)
            self.numCtrl1b.SetValue(x)
            self.numCtrl2b.SetValue(y)
            self.numCtrl3b.SetValue(z)
            
    def Img_Ref_ToggleButton3(self, evt):
        id = evt.GetId()
        flag3 = self.button_img_ref3.GetValue()
        x, y, z = self.a
        if flag3 == True:
            self.coord3a = x, y, z
            self.aux_img_ref3 = 1
        elif flag3 == False:
            self.aux_img_ref3 = 0
            self.coord3a = (0, 0, 0)
            self.numCtrl1c.SetValue(x)
            self.numCtrl2c.SetValue(y)
            self.numCtrl3c.SetValue(z)
      
    def Neuronavigate_ToggleButton(self, evt):
        id = evt.GetId()
        flag4 = self.button_neuronavigate.GetValue()
        bases = self.Minv, self.N, self.q1, self.q2
        if flag4 == True:
            self.correg = dcr.Corregister(bases, flag4)
        elif flag4 == False:
            self.correg.stop()
    
    def SaveCoordinates(self, info):
        #Create a file and write the points given by getpoint's button 
        x, y, z = info[0]
        flag = info[1]

        if flag == 0:
            text_file = open("points.txt", "w")
            line = str('%.2f' %x) + "\t" + str('%.2f' %y) + "\t" + str('%.2f' %z) + "\n"
            text_file.writelines(line)
            text_file.close()
        else:
            text_file = open("points.txt", "r")
            filedata = text_file.read()
            line = filedata + str('%.2f' %x) + "\t" + str('%.2f' %y) + "\t" + str('%.2f' %z) + "\n"
            text_file = open("points.txt", "w")
            text_file.write(line)
            text_file.close()
        
>>>>>>> 6a586fc72c48af4e4392c6b478be75b06a8889f8
