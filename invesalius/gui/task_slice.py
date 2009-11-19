
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

import wx
import wx.lib.colourselect as csel
import wx.lib.hyperlink as hl
import wx.lib.platebtn as pbtn
import wx.lib.pubsub as ps

import data.mask as mask
import constants as const
import gui.widgets.gradient as grad
import gui.widgets.foldpanelbar as fpb
from project import Project

BTN_NEW = wx.NewId()

MENU_BRUSH_SQUARE = wx.NewId()
MENU_BRUSH_CIRCLE = wx.NewId()

MENU_BRUSH_ADD = wx.NewId()
MENU_BRUSH_DEL = wx.NewId()
MENU_BRUSH_THRESH = wx.NewId()

MASK_LIST = []

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

        # Image(s) for buttons
        BMP_ADD = wx.Bitmap("../icons/object_add.png", wx.BITMAP_TYPE_PNG)
        BMP_ADD.SetWidth(25)
        BMP_ADD.SetHeight(25)

        # Button for creating new surface
        button_new_mask = pbtn.PlateButton(self, BTN_NEW, "", BMP_ADD, style=\
                                   pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT)
        self.Bind(wx.EVT_BUTTON, self.OnButton)


        # Fixed hyperlink items
        tooltip = wx.ToolTip("Create mask for slice segmentation and edition")
        link_new_mask = hl.HyperLinkCtrl(self, -1, "Create new mask")
        link_new_mask.SetUnderlines(False, False, False)
        link_new_mask.SetColours("BLACK", "BLACK", "BLACK")
        link_new_mask.SetToolTip(tooltip)
        link_new_mask.AutoBrowse(False)
        link_new_mask.UpdateLink()
        link_new_mask.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkNewMask)

        # Create horizontal sizers to represent lines in the panel
        line_new = wx.BoxSizer(wx.HORIZONTAL)
        line_new.Add(link_new_mask, 1, wx.EXPAND|wx.GROW| wx.TOP|wx.RIGHT, 4)
        line_new.Add(button_new_mask, 0, wx.ALL|wx.EXPAND|wx.GROW, 0)


        # Fold panel which contains mask properties and edition tools
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_BACKGROUND)
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_APPWORKSPACE)
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNFACE)
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_DESKTOP)
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_SCROLLBAR)
        #print wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUHILIGHT)
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)
        self.fold_panel = fold_panel

        # Button to fold to select region task
        button_next = wx.Button(self, -1, "Create 3D surface")
        if sys.platform != 'win32':
            button_next.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        button_next.Bind(wx.EVT_BUTTON, self.OnButtonNextTask)

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_new, 0,wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        main_sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND|wx.ALL, 5)
        main_sizer.Add(button_next, 0,
                       wx.ALIGN_RIGHT|wx.RIGHT|wx.LEFT|wx.BOTTOM, 5)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = main_sizer

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnLinkNewMask()

    def OnButtonNextTask(self, evt):
        ps.Publisher().sendMessage('Create surface from index',
                                    self.GetMaskSelected())

    def OnLinkNewMask(self, evt=None):
        dlg = wx.TextEntryDialog(self, 'Name of new mask:',
                                 'InVesalius 3.0 - New mask')
        dlg.CenterOnScreen()
        default_mask_name = const.MASK_NAME_PATTERN %(mask.Mask.general_index+2)
        dlg.SetValue(default_mask_name)

        if dlg.ShowModal() == wx.ID_OK:
            print "TODO: Send Signal - New mask"
            mask_name = dlg.GetValue()
            ps.Publisher().sendMessage('Create new mask', mask_name)
        if evt:
            evt.Skip()

    def GetMaskSelected(self):
        return self.fold_panel.GetMaskSelected()

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

        self.inner_panel = inner_panel

    def GetMaskSelected(self):
        x = self.inner_panel.GetMaskSelected()
        return self.inner_panel.GetMaskSelected()

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
                                      (10, 170), 0,fpb.FPB_SINGLE_FOLD)

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        # Fold 1 - Mask properties
        item = fold_panel.AddFoldPanel("Mask properties", collapsed=True)
        self.mask_prop_panel = MaskProperties(item)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, self.mask_prop_panel, Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        # Fold 2 - Advanced edition tools
        item = fold_panel.AddFoldPanel("Advanced edition tools", collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, EditionTools(item), Spacing= 0,
                                      leftSpacing=0, rightSpacing=0)
        #fold_panel.Expand(fold_panel.GetFoldPanel(1))

        # Panel sizer to expand fold panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

    def GetMaskSelected(self):
        x= self.mask_prop_panel.GetMaskSelected()
        return self.mask_prop_panel.GetMaskSelected()

class MaskProperties(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(50,240))

        ## LINE 1

        # Combo related to mask naem
        combo_mask_name = wx.ComboBox(self, -1, "", choices= MASK_LIST,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_mask_name.SetSelection(0) # wx.CB_SORT
        if sys.platform != 'win32':
            combo_mask_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_mask_name = combo_mask_name

        # Mask colour
        button_colour= csel.ColourSelect(self, 111,colour=(0,255,0),size=(-1,22))
        self.button_colour = button_colour

        # Sizer which represents the first line
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(combo_mask_name, 1, wx.EXPAND|wx.GROW|wx.TOP|wx.RIGHT, 2)
        line1.Add(button_colour, 0, wx.TOP|wx.LEFT|wx.RIGHT, 2)

        ## LINE 2
        text_thresh = wx.StaticText(self, -1,
                                    "Set predefined or manual threshold:")

        ## LINE 3
        combo_thresh = wx.ComboBox(self, -1, "", size=(15,-1),
                                   choices=[],#THRESHOLD_LIST
                                   style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_thresh.SetSelection(0)
        if sys.platform != 'win32':
            combo_thresh.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_thresh = combo_thresh

        ## LINE 4
        gradient = grad.GradientSlider(self, -1, -5000, 5000, 0, 5000,
                                           (0, 255, 0, 100))
        self.gradient = gradient

        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(line1, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        sizer.Add(text_thresh, 1, wx.GROW|wx.EXPAND|wx.ALL, 5)
        sizer.Add(combo_thresh, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.Add(gradient, 1, wx.EXPAND|wx.TOP|wx.LEFT|wx.RIGHT|wx.BOTTOM, 6)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

        # Non GUI stuff

        proj = Project()
        self.threshold_modes = proj.threshold_modes
        self.bind_evt_gradient = True
        self.__bind_events()
        self.__bind_events_wx()

    def __bind_events(self):
        ps.Publisher().subscribe(self.AddMask, 'Add mask')
        # TODO: Uncomment
        ps.Publisher().subscribe(self.SetThresholdBounds,
                                    'Update threshold limits')
        ps.Publisher().subscribe(self.SetThresholdModes, 'Set threshold modes')
        ps.Publisher().subscribe(self.SetItemsColour, 'Set GUI items colour')
        ps.Publisher().subscribe(self.SetThresholdValues,
                                 'Set threshold values in gradient')
        ps.Publisher().subscribe(self.SelectMaskName, 'Select mask name in combo')
        ps.Publisher().subscribe(self.ChangeMaskName, 'Change mask name')

    def __bind_events_wx(self):
        self.Bind(grad.EVT_THRESHOLD_CHANGE, self.OnSlideChanged, self.gradient)
        self.combo_thresh.Bind(wx.EVT_COMBOBOX, self.OnComboThresh)
        self.combo_mask_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        self.button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)

    def SelectMaskName(self, pubsub_evt):
        index = pubsub_evt.data
        self.combo_mask_name.SetSelection(index)

    def ChangeMaskName(self, pubsub_evt):
        index, name = pubsub_evt.data
        self.combo_mask_name.SetString(index, name)
        self.combo_mask_name.Refresh()

    def SetThresholdValues(self, pubsub_evt):
        thresh_min, thresh_max = pubsub_evt.data
        self.bind_evt_gradient = False
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)
        self.bind_evt_gradient = True

    def SetItemsColour(self, evt_pubsub):
        colour = evt_pubsub.data
        self.gradient.SetColour(colour)
        self.button_colour.SetColour(colour)

    def AddMask(self, evt_pubsub):
        mask_name = evt_pubsub.data[1]
        mask_thresh = evt_pubsub.data[2]
        mask_colour = [int(c*255) for c in evt_pubsub.data[3]]
        index = self.combo_mask_name.Append(mask_name)
        self.combo_mask_name.SetSelection(index)
        self.button_colour.SetColour(mask_colour)
        self.gradient.SetColour(mask_colour)
        self.combo_mask_name.SetSelection(index)

    def GetMaskSelected(self):
        x = self.combo_mask_name.GetSelection()
        return self.combo_mask_name.GetSelection()

    def SetThresholdModes(self, pubsub_evt):
        (thresh_modes_names, default_thresh) = pubsub_evt.data
        self.combo_thresh.SetItems(thresh_modes_names)
        if isinstance(default_thresh, int):
            self.combo_thresh.SetSelection(default_thresh)
            (thresh_min, thresh_max) =\
                self.threshold_modes[thresh_modes_names[default_thresh]]
        else:
           self.combo_thresh.SetSelection(3)
           thresh_min, thresh_max = default_thresh
        
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)

    def SetThresholdBounds(self, pubsub_evt):
        thresh_min = pubsub_evt.data[0]
        thresh_max  = pubsub_evt.data[1]
        self.gradient.SetMinRange(thresh_min)
        self.gradient.SetMaxRange(thresh_max)

    def OnComboName(self, evt):
        mask_name = evt.GetString()
        mask_index = evt.GetSelection()
        ps.Publisher().sendMessage('Change mask selected', mask_index)

    def OnComboThresh(self, evt):
        (thresh_min, thresh_max) = self.threshold_modes[evt.GetString()]
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)

    def OnSlideChanged(self, evt):
        thresh_min = self.gradient.GetMinValue()
        thresh_max = self.gradient.GetMaxValue()
        print "OnSlideChanged", thresh_min, thresh_max
        if self.bind_evt_gradient:
            ps.Publisher().sendMessage('Set threshold values',
                                        (thresh_min, thresh_max))

    def OnSelectColour(self, evt):
        colour = evt.GetValue()
        self.gradient.SetColour(colour)
        ps.Publisher().sendMessage('Change mask colour', colour)

class EditionTools(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(50,240))
        default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        ## LINE 1
        text1 = wx.StaticText(self, -1, "Choose brush type, size or operation:")

        ## LINE 2
        menu = wx.Menu()

        CIRCLE_BMP = wx.Bitmap("../icons/brush_circle.jpg", wx.BITMAP_TYPE_JPEG)
        item = wx.MenuItem(menu, MENU_BRUSH_CIRCLE, "Circle")
        item.SetBitmap(CIRCLE_BMP)

        SQUARE_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        item2 = wx.MenuItem(menu, MENU_BRUSH_SQUARE, "Square")
        item2.SetBitmap(SQUARE_BMP)

        menu.AppendItem(item)
        menu.AppendItem(item2)

        bmp_brush_format = {const.BRUSH_CIRCLE: CIRCLE_BMP,
                            const.BRUSH_SQUARE: SQUARE_BMP}
        selected_bmp = bmp_brush_format[const.DEFAULT_BRUSH_FORMAT]

        btn_brush_format = pbtn.PlateButton(self, wx.ID_ANY,"", selected_bmp,
                                          style=pbtn.PB_STYLE_SQUARE)
        btn_brush_format.SetMenu(menu)
        self.btn_brush_format = btn_brush_format

        spin_brush_size = wx.SpinCtrl(self, -1, "", (20, 50))
        spin_brush_size.SetRange(1,100)
        spin_brush_size.SetValue(const.BRUSH_SIZE)
        spin_brush_size.Bind(wx.EVT_TEXT, self.OnBrushSize)
        self.spin = spin_brush_size

        combo_brush_op = wx.ComboBox(self, -1, "", size=(15,-1),
                                     choices = const.BRUSH_OP_NAME,
                                     style = wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_brush_op.SetSelection(const.DEFAULT_BRUSH_OP)
        if sys.platform != 'win32':
            combo_brush_op.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_brush_op = combo_brush_op

        # Sizer which represents the second line
        line2 = wx.BoxSizer(wx.HORIZONTAL)
        line2.Add(btn_brush_format, 0, wx.EXPAND|wx.GROW|wx.TOP|wx.RIGHT, 0)
        line2.Add(spin_brush_size, 0, wx.RIGHT, 5)
        line2.Add(combo_brush_op, 1, wx.EXPAND|wx.TOP|wx.RIGHT|wx.LEFT, 5)

        ## LINE 3
        text_thresh = wx.StaticText(self, -1, "Brush threshold range:")

        ## LINE 4
        gradient_thresh = grad.GradientSlider(self, -1, 0, 5000, 0, 5000,
                                       (0, 0, 255, 100))
        self.gradient_thresh = gradient_thresh
        self.bind_evt_gradient = True

        # Add lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(text1, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        sizer.Add(line2, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        sizer.Add(text_thresh, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, 5)
        sizer.Add(gradient_thresh, 0, wx.EXPAND|wx.TOP|wx.LEFT|wx.RIGHT|
                  wx.BOTTOM, 6)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_events()
        self.__bind_events_wx()


    def __bind_events_wx(self):
        self.Bind(wx.EVT_MENU, self.OnMenu)
        self.Bind(grad.EVT_THRESHOLD_CHANGE, self.OnGradientChanged,
                  self.gradient_thresh)
        self.combo_brush_op.Bind(wx.EVT_COMBOBOX, self.OnComboBrushOp)

    def __bind_events(self):
        ps.Publisher().subscribe(self.SetThresholdBounds,
                                        'Update threshold limits')
        ps.Publisher().subscribe(self.ChangeMaskColour, 'Change mask colour')
        ps.Publisher().subscribe(self.SetGradientColour, 'Add mask')

    def ChangeMaskColour(self, pubsub_evt):
        colour = pubsub_evt.data
        self.gradient_thresh.SetColour(colour)

    def SetGradientColour(self, pubsub_evt):
        vtk_colour = pubsub_evt.data[3]
        wx_colour = [c*255 for c in vtk_colour]
        self.gradient_thresh.SetColour(wx_colour)

    def SetThresholdValues(self, pubsub_evt):
        thresh_min, thresh_max = pubsub_evt.data
        self.bind_evt_gradient = False
        self.gradient_thresh.SetMinValue(thresh_min)
        self.gradient_thresh.SetMaxValue(thresh_max)
        self.bind_evt_gradient = True

    def SetThresholdBounds(self, pubsub_evt):
        thresh_min = pubsub_evt.data[0]
        thresh_max  = pubsub_evt.data[1]
        self.gradient_thresh.SetMinRange(thresh_min)
        self.gradient_thresh.SetMaxRange(thresh_max)
        self.gradient_thresh.SetMinValue(thresh_min)
        self.gradient_thresh.SetMaxValue(thresh_max)

    def OnGradientChanged(self, evt):
        thresh_min = self.gradient_thresh.GetMinValue()
        thresh_max = self.gradient_thresh.GetMaxValue()
        if self.bind_evt_gradient:
            ps.Publisher().sendMessage('Set edition threshold values',
                                     (thresh_min, thresh_max))

    def OnMenu(self, evt):
        SQUARE_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        CIRCLE_BMP = wx.Bitmap("../icons/brush_circle.jpg", wx.BITMAP_TYPE_JPEG)

        brush = {MENU_BRUSH_CIRCLE: const.BRUSH_CIRCLE,
                 MENU_BRUSH_SQUARE: const.BRUSH_SQUARE}
        bitmap = {MENU_BRUSH_CIRCLE: CIRCLE_BMP,
                  MENU_BRUSH_SQUARE: SQUARE_BMP}

        self.btn_brush_format.SetBitmap(bitmap[evt.GetId()])

        ps.Publisher().sendMessage('Set brush format', brush[evt.GetId()])

    def OnBrushSize(self, evt):
        """ """
        # FIXME: Using wx.EVT_SPINCTRL in MacOS it doesnt capture changes only
        # in the text ctrl - so we are capturing only changes on text
        # Strangelly this is being called twice
        ps.Publisher().sendMessage('Set edition brush size',self.spin.GetValue())

    def OnComboBrushOp(self, evt):
        brush_op_id = evt.GetSelection()
        ps.Publisher().sendMessage('Set edition operation', brush_op_id)


