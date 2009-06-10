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

import wx
import wx.lib.hyperlink as hl
import wx.lib.platebtn as pbtn
import wx.lib.embeddedimage as emb

BTN_MEASURE_LINEAR = wx.NewId()
BTN_MEASURE_ANGULAR = wx.NewId()
BTN_ANNOTATION = wx.NewId()

Devil = emb.PyEmbeddedImage(
    "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"
    "kwAAAABJRU5ErkJggg==")


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        
        inner_panel = InnerTaskPanel(self)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)
                
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
class InnerTaskPanel(wx.Panel):        
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(wx.Colour(255,255,255))
        self.SetAutoLayout(1)

        # Counter for projects loaded in current GUI
        self.proj_count = 0
        
        # Floating items (to be inserted)
        self.float_hyper_list = []

        # Fixed text and hyperlink items
        tooltip = wx.ToolTip("Measure distances")
        txt_measure = wx.StaticText(self, -1, "Measure")
        txt_measure.SetToolTip(tooltip)

        tooltip = wx.ToolTip("Add text annotations")
        txt_annotation = hl.HyperLinkCtrl(self, -1,"Add text annotations")
        txt_annotation.SetUnderlines(False, False, False)
        txt_annotation.SetColours("BLACK", "BLACK", "BLACK")
        txt_annotation.SetToolTip(tooltip)
        txt_annotation.AutoBrowse(False)
        txt_annotation.UpdateLink()
        txt_annotation.Bind(hl.EVT_HYPERLINK_LEFT, self.OnTextAnnotation)
        
        # Image(s) for buttons
        bitmap = Devil.GetBitmap() # 32, 32
        bitmap.SetWidth(20)
        bitmap.SetHeight(20)
        
        # Buttons related to hyperlinks
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_NOBG
        
        button_measure_linear = pbtn.PlateButton(self, BTN_MEASURE_LINEAR, "",
                                               bitmap, style=button_style)
        button_measure_angular = pbtn.PlateButton(self, BTN_MEASURE_ANGULAR, "", 
                                              bitmap, style=button_style)

        button_annotation = pbtn.PlateButton(self, BTN_ANNOTATION, "", 
                                              bitmap, style=button_style)

        # When using PlaneButton, it is necessary to bind events from parent win
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Tags and grid sizer for fixed items
        flag_link = wx.EXPAND|wx.GROW|wx.LEFT|wx.TOP
        flag_button = wx.EXPAND | wx.GROW

        sizer = wx.GridBagSizer(hgap=0, vgap=0)
        sizer.Add(txt_measure,pos=(0,0),flag=wx.GROW|wx.EXPAND|wx.TOP,border=3)
        sizer.Add(button_measure_linear,pos=(0,1),flag=wx.GROW|wx.EXPAND)
        sizer.Add(button_measure_angular,pos=(0,2),flag=wx.GROW|wx.EXPAND)
        sizer.Add(txt_annotation, pos=(1,0),flag=wx.GROW|wx.EXPAND)
        sizer.Add(button_annotation, pos=(1,2),span=(2,1), flag=wx.GROW|wx.EXPAND)
        sizer.AddGrowableCol(0)
        
        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(sizer, 0, wx.GROW|wx.EXPAND)
        main_sizer.Fit(self)
        
        # Update main sizer and panel layout        
        self.SetSizer(sizer)
        self.Fit()
        self.sizer = main_sizer

    def OnTextAnnotation(self, evt=None):
        print "TODO: Send Signal - Add text annotation (both 2d and 3d)"
        
    def OnLinkLinearMeasure(self):
        print "TODO: Send Signal - Add linear measure (both 2d and 3d)"

    def OnLinkAngularMeasure(self):
        print "TODO: Send Signal - Add angular measure (both 2d and 3d)"
                
    def OnButton(self, evt):
        id = evt.GetId()
        
        if id == BTN_MEASURE_LINEAR:
            self.OnLinkLinearMeasure()
        elif id == BTN_MEASURE_ANGULAR:
            self.OnLinkAngularMeasure()
        else: # elif id == BTN_ANNOTATION:
            self.OnTextAnnotation()
        

        