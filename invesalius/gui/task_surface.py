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
import wx.lib.colourselect as csel
import wx.lib.hyperlink as hl
import wx.lib.platebtn as pbtn
import wx.lib.pubsub as ps

import gui.widgets.foldpanelbar as fpb

#INTERPOLATION_MODE_LIST = ["Cubic", "Linear", "NearestNeighbor"]
QUALITY_LIST = ["Low", "Medium", "High", "Optimal *", "Custom"]
SURFACE_LIST = []
MASK_LIST = ["Mask 1"]
MIN_TRANSPARENCY = 0
MAX_TRANSPARENCY = 100

#############
BTN_NEW = wx.NewId()
MENU_SQUARE = wx.NewId()
MENU_CIRCLE = wx.NewId()

OP_LIST = ["Draw", "Erase", "Threshold"]


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

        # select mask - combo
        # mesh quality - combo?
        # apply button
        # Contour - slider
        # enable / disable Fill holes

class InnerTaskPanel(wx.Panel):        
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = self.GetBackgroundColour()
        self.SetBackgroundColour(wx.Colour(255,255,255))
        self.SetAutoLayout(1)


        BMP_ADD = wx.Bitmap("../icons/object_add.png", wx.BITMAP_TYPE_PNG)
        BMP_ADD.SetWidth(25)
        BMP_ADD.SetHeight(25)
        
        # Button for creating new surface
        button_new_surface = pbtn.PlateButton(self, BTN_NEW, "", BMP_ADD, style=\
                                   pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_NOBG)
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Fixed hyperlink items
        tooltip = wx.ToolTip("Create 3D surface based on a mask")
        link_new_surface = hl.HyperLinkCtrl(self, -1, "Create new 3D surface")
        link_new_surface.SetUnderlines(False, False, False)
        link_new_surface.SetColours("BLACK", "BLACK", "BLACK")
        link_new_surface.SetToolTip(tooltip)
        link_new_surface.AutoBrowse(False)
        link_new_surface.UpdateLink()
        link_new_surface.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkNewSurface)

        # Create horizontal sizers to represent lines in the panel
        line_new = wx.BoxSizer(wx.HORIZONTAL)
        line_new.Add(link_new_surface, 1, wx.EXPAND|wx.GROW| wx.TOP|wx.RIGHT, 4)
        line_new.Add(button_new_surface, 0, wx.ALL|wx.EXPAND|wx.GROW, 0)

        # Folde panel which contains surface properties and quality
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)

        # Button to fold to select region task
        button_next = wx.Button(self, -1, "Next step")
        button_next.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        #button_next.Bind(wx.EVT_BUTTON, self.OnButtonNextTask)
        
        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_new, 0,wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        main_sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND|wx.ALL, 5)
        main_sizer.Add(button_next, 0, wx.ALIGN_RIGHT|wx.RIGHT|wx.BOTTOM, 5)
        main_sizer.Fit(self)
        
        self.SetSizer(main_sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = main_sizer
        
    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnLinkNewSurface()

    def OnButtonNextTask(self, evt):
        self.OnLinkNewSurface()
        if evt:
            evt.Skip()
            
    def OnLinkNewSurface(self, evt=None):
        dlg = NewSurfaceDialog(self, -1, 'InVesalius 3.0 - New surface')
        if dlg.ShowModal() == wx.ID_OK:
            print "TODO: Send Signal - Create 3d surface %s \n" % dlg.GetValue()
            dlg.Destroy()
        if evt:
            evt.Skip()
            
class NewSurfaceDialog(wx.Dialog):
    def __init__(self, parent, ID, title, size=wx.DefaultSize,
            pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE, 
            useMetal=False):

        # Instead of calling wx.Dialog.__init__ we precreate the dialog
        # so we can set an extra style that must be set before
        # creation, and then we create the GUI object using the Create
        # method.
        pre = wx.PreDialog()
        pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        pre.Create(parent, ID, title, pos, (500,300), style)

        # This next step is the most important, it turns this Python
        # object into the real wrapper of the dialog (instead of pre)
        # as far as the wxPython extension is concerned.
        self.PostCreate(pre)

        # This extra style can be set after the UI object has been created.
        if 'wxMac' in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # Now continue with the normal construction of the dialog
        # contents
                
        # Label related to mask name
        label_mask = wx.StaticText(self, -1, "Select mask to be used for creating 3D surface:")

        # Combo related to mask name
        combo_surface_name = wx.ComboBox(self, -1, "", choices= MASK_LIST,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_surface_name.SetSelection(0)
        combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_surface_name = combo_surface_name


        label_surface = wx.StaticText(self, -1, "Set new surface name:")

        text = wx.TextCtrl(self, -1, "", size=(80,-1))
        text.SetHelpText("Name the new surface to be created")
        text.SetValue("Default 3D")
        self.text = text
                
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label_mask, 0, wx.ALL|wx.GROW|wx.EXPAND, 5)
        sizer.Add(combo_surface_name, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 10)
        sizer.Add(label_surface, 0, wx.ALL|wx.GROW|wx.EXPAND, 5)
        sizer.Add(text, 0, wx.GROW|wx.EXPAND|wx.RIGHT|wx.LEFT, 10)

        btnsizer = wx.StdDialogButtonSizer()
        
        #if wx.Platform != "__WXMSW__":
        #    btn = wx.ContextHelpButton(self)
        #    btnsizer.AddButton(btn)
        
        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT|wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def GetValue(self):
        return self.text.GetValue() +"| mask: "+ MASK_LIST[self.combo_surface_name.GetSelection()]
                        
class FoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(50,50))
        self.SetBackgroundColour(wx.Colour(0,255,0))
        
        inner_panel = InnerFoldPanel(self)
        
        sizer = wx.BoxSizer(wx.VERTICAL)        
        sizer.Add(inner_panel, 1, wx.EXPAND|wx.GROW, 2)
        sizer.Fit(self)
        
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
class InnerFoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(wx.Colour(221, 221, 221, 255))
        #self.SetBackgroundColour(wx.Colour(0,0,0))
        
        # Fold panel and its style settings
        # FIXME: If we dont insert a value in size or if we set wx.DefaultSize,
        # the fold_panel doesnt show. This means that, for some reason, Sizer
        # is not working properly in this panel. It might be on some child or
        # parent panel. Perhaps we need to insert the item into the sizer also...
        # Study this.
        fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                      (10, 170), 0,fpb.FPB_SINGLE_FOLD)

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_RECTANGLE)
        style.SetSecondColour(wx.Colour(255,255,255))

        # Fold 1 - Surface properties
        item = fold_panel.AddFoldPanel("Surface properties", collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, SurfaceProperties(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))
        
        # Fold 2 - Surface quality
        item = fold_panel.AddFoldPanel("Surface quality", collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, QualityAdjustment(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        #fold_panel.Expand(fold_panel.GetFoldPanel(1))

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self)
              
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class SurfaceProperties(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(50,240))
        self.SetBackgroundColour(wx.Colour(221, 221, 221, 255))
        
        ## LINE 1
        
        # Combo related to mask naem
        combo_surface_name = wx.ComboBox(self, -1, "", choices= SURFACE_LIST,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_surface_name.SetSelection(0)
        combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        self.combo_surface_name = combo_surface_name
        
        # Mask colour
        button_colour= csel.ColourSelect(self, -1,colour=(0,0,255),size=(-1,22))
        button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_colour = button_colour
        
        # Sizer which represents the first line
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(combo_surface_name, 1, wx.EXPAND|wx.GROW|wx.TOP|wx.RIGHT, 2)
        line1.Add(button_colour, 0, wx.TOP|wx.LEFT|wx.RIGHT, 2)    
        
        
        ## LINE 2
        
        text_transparency = wx.StaticText(self, -1, "Transparency:")
        
        slider_transparency = wx.Slider(self, -1, 0, MIN_TRANSPARENCY,
                                        MAX_TRANSPARENCY, 
                                        style=wx.SL_HORIZONTAL)#|wx.SL_AUTOTICKS)
        slider_transparency.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider_transparency.Bind(wx.EVT_SLIDER, self.OnTransparency)
        self.slider_transparency = slider_transparency
        
        
        ## MIX LINE 2 AND 3
        flag_link = wx.EXPAND|wx.GROW|wx.RIGHT
        flag_slider = wx.EXPAND | wx.GROW| wx.LEFT|wx.TOP
        flag_combo = wx.EXPAND | wx.GROW| wx.LEFT
        
        fixed_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=2, vgap=4)
        fixed_sizer.AddMany([ (text_transparency, 0, flag_link, 0),
                              (slider_transparency, 1, flag_slider,4)])
     
        # LINE 4
        #cb = wx.CheckBox(self, -1, "Fill largest surface holes")
        #cb.SetValue(True)
        
        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(line1, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        sizer.Add(fixed_sizer, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        #sizer.Add(cb, 0, wx.GROW|wx.EXPAND|wx.RIGHT|wx.LEFT|wx.TOP|wx.BOTTOM, 5)
        sizer.Fit(self)
        
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
        self.__bind_events()
        
    def __bind_events(self):
        ps.Publisher().subscribe(self.InsertNewSurface,
                                'Update surface info in GUI')
        ps.Publisher().subscribe(self.ChangeMaskName,
                                'Change surface name')


    def ChangeMaskName(self, pubsub_evt):
        index, name = pubsub_evt.data
        self.combo_surface_name.SetString(index, name)
        self.combo_surface_name.Refresh()

    def InsertNewSurface(self, pubsub_evt):
        name = pubsub_evt.data[1]
        colour = [value*255 for value in pubsub_evt.data[2]]
        transparency = 100*pubsub_evt.data[4]
        index = self.combo_surface_name.Append(name)
        self.combo_surface_name.SetSelection(index) 
        self.button_colour.SetColour(colour)
        self.slider_transparency.SetValue(transparency)
        
    def OnComboName(self, evt):
        print "TODO: Send Signal - Change 3D surface selected: %s" % (evt.GetString())

    def OnSelectColour(self, evt):
        colour = [value/255.0 for value in evt.GetValue()]
        ps.Publisher().sendMessage('Set surface colour',
                                    (self.combo_surface_name.GetSelection(),
                                    colour))

    def OnTransparency(self, evt):
        print evt.GetInt()
        transparency = evt.GetInt()/float(MAX_TRANSPARENCY)
        # FIXME: In Mac OS/X, wx.Slider (wx.Python 2.8.10) has problem on the
        # right-limit as reported on http://trac.wxwidgets.org/ticket/4555.
        # This problem is in wx.Widgets and therefore we'll simply overcome it:
        if (wx.Platform == "__WXMAC__"):
            transparency = evt.GetInt()/(0.96*float(MAX_TRANSPARENCY))
        ps.Publisher().sendMessage('Set surface transparency',
                                  (self.combo_surface_name.GetSelection(),
                                  transparency))

class QualityAdjustment(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(50,240))
        self.SetBackgroundColour(wx.Colour(221, 221, 221, 255))
        
        # LINE 1
        combo_quality = wx.ComboBox(self, -1, "", choices= QUALITY_LIST,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_quality.SetSelection(3)
        combo_quality.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        #combo_quality.Bind(wx.EVT_COMBOBOX, self.OnComboQuality)   
        
        # LINE 2
        check_decimate = wx.CheckBox(self, -1, "")
        
        text_decimate = wx.StaticText(self, -1, "Decimate resolution:")
        
        spin_decimate = wx.SpinCtrl(self, -1, "", (30, 50))
        spin_decimate.SetRange(1,100)
        spin_decimate.SetValue(30)
        #spin_decimate.Bind(wx.EVT_TEXT, self.OnDecimate)

        # LINE 3
        check_smooth = wx.CheckBox(self, -1, "")
        
        text_smooth = wx.StaticText(self, -1, "Smooth iterations:")
        
        spin_smooth = wx.SpinCtrl(self, -1, "", (30, 50))
        spin_smooth.SetRange(1,100)
        spin_smooth.SetValue(0)
        
        # MIXED LINE 2 AND 3
        flag_link = wx.EXPAND|wx.GROW|wx.RIGHT|wx.LEFT
        flag_slider = wx.EXPAND | wx.GROW| wx.LEFT|wx.TOP
        flag_combo = wx.EXPAND | wx.GROW| wx.LEFT
        
        fixed_sizer = wx.FlexGridSizer(rows=2, cols=3, hgap=2, vgap=0)
        fixed_sizer.AddMany([ (check_decimate, 0, flag_combo, 2),
                              (text_decimate, 0, flag_slider, 7),
                              (spin_decimate, 1, flag_link,14),
                              (check_smooth, 0, flag_combo, 2),
                              (text_smooth, 0, flag_slider, 7),
                              (spin_smooth, 1, flag_link, 14)])
        fixed_sizer.AddGrowableCol(2)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(combo_quality, 1, wx.EXPAND|wx.GROW|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        sizer.Add(fixed_sizer, 0, wx.LEFT|wx.RIGHT, 5)
        sizer.Fit(self)
        
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
    def OnComboQuality(self, evt):
        print "TODO: Send Signal - Change surface quality: %s" % (evt.GetString())
        
    def OnDecimate(self, evt):
        print "TODO: Send Signal - Decimate: %s" % float(self.spin.GetValue())/100
        