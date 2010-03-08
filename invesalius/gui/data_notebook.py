#!/usr/bin/env python
# -*- coding: UTF-8 -*- 
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

import Image

import wx
import wx.grid
import wx.lib.flatnotebook as fnb
import wx.lib.platebtn as pbtn
import wx.lib.pubsub as ps

import constants as const
import gui.dialogs as dlg
import gui.widgets.listctrl as listmix
import utils as ul


BTN_NEW, BTN_REMOVE, BTN_DUPLICATE = [wx.NewId() for i in xrange(3)]

TYPE = {const.LINEAR: _(u"Linear"),
        const.ANGULAR: _(u"Angular"),
        }

LOCATION = {const.SURFACE: _(u"3D"),
            const.AXIAL: _(u"Axial"),
            const.CORONAL: _(u"Coronal"),
            const.SAGITAL: _(u"Sagittal")
        }

# Panel that initializes notebook and related tabs
class NotebookPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 200))
                        
        book = wx.Notebook(self, -1,style= wx.BK_DEFAULT)
        # TODO: check under Windows and Linux
        # this was necessary under cOS:
        #if wx.Platform == "__WXMAC__":
        if sys.platform != 'win32':
            book.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        book.AddPage(MaskPage(book), _("Masks"))
        book.AddPage(SurfacePage(book), _("3D Surfaces"))
        book.AddPage(MeasurePage(book), _("Measures"))
        #book.AddPage(AnnotationsListCtrlPanel(book), _("Notes"))
        
        book.SetSelection(0)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(book, 1, wx.EXPAND)
        self.SetSizer(sizer)
        
        book.Refresh()
        self.book = book

        self.__bind_events()

    def __bind_events(self):
        ps.Publisher().subscribe(self._FoldSurface,
                                 'Fold surface task')
        ps.Publisher().subscribe(self._FoldSurface,
                                 'Fold surface page')
        ps.Publisher().subscribe(self._FoldMeasure,
                                 'Fold measure task')
        ps.Publisher().subscribe(self._FoldMask,
                                 'Fold mask task')
        ps.Publisher().subscribe(self._FoldMask,
                                 'Fold mask page')


    def _FoldSurface(self, pubusb_evt):
        """
        Fold surface notebook page.
        """
        self.book.SetSelection(1)

    def _FoldMeasure(self, pubsub_evt):
        """
        Fold measure notebook page.
        """
        self.book.SetSelection(2)


    def _FoldMask(self, pubsub_evt):
        """
        Fold mask notebook page.
        """
        self.book.SetSelection(0)

class MeasurePage(wx.Panel):
    """
    Page related to mask items.
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 140))
        self.__init_gui()

    def __init_gui(self):
        # listctrl were existing masks will be listed
        self.listctrl = MeasuresListCtrlPanel(self, size=wx.Size(256, 100))
        # button control with tools (eg. remove, add new, etc)
        self.buttonctrl = MeasureButtonControlPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.listctrl, 0, wx.EXPAND)
        sizer.Add(self.buttonctrl, 0, wx.EXPAND| wx.TOP, 2)
        self.SetSizer(sizer)
        self.Fit()




class MeasureButtonControlPanel(wx.Panel):
    """
    Button control panel that includes data notebook operations.
    TODO: Enhace interface with parent class - it is really messed up
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 22))
        self.parent = parent
        self.__init_gui()

    def __init_gui(self):
        
        # Bitmaps to be used in plate buttons
        BMP_NEW = wx.Bitmap("../icons/data_new.png",
                            wx.BITMAP_TYPE_PNG)
        BMP_REMOVE = wx.Bitmap("../icons/data_remove.png",
                                wx.BITMAP_TYPE_PNG)
        BMP_DUPLICATE = wx.Bitmap("../icons/data_duplicate.png",
                                wx.BITMAP_TYPE_PNG)

        # Plate buttons based on previous bitmaps
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_new = pbtn.PlateButton(self, BTN_NEW, "",
                                     BMP_NEW,
                                     style=button_style,
                                     size = wx.Size(18, 18))
        self.button_new = button_new
        button_remove = pbtn.PlateButton(self, BTN_REMOVE, "",
                                         BMP_REMOVE,
                                         style=button_style,
                                         size = wx.Size(18, 18))
        button_duplicate = pbtn.PlateButton(self, BTN_DUPLICATE, "",
                                            BMP_DUPLICATE,
                                            style=button_style,
                                            size = wx.Size(18, 18))
        button_duplicate.Disable()

        # Add all controls to gui
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_new, 0, wx.GROW|wx.EXPAND|wx.LEFT)
        sizer.Add(button_remove, 0, wx.GROW|wx.EXPAND)
        sizer.Add(button_duplicate, 0, wx.GROW|wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        menu = wx.Menu()
        item = wx.MenuItem(menu, const.MEASURE_LINEAR,
                            _("Measure distance"))
        menu.AppendItem(item)
        item = wx.MenuItem(menu, const.MEASURE_ANGULAR,
                            _("Measure angle"))
        menu.AppendItem(item)
        menu.Bind(wx.EVT_MENU, self.OnMenu)
        self.menu = menu

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnButton)

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnNew()
        elif id == BTN_REMOVE:
            self.OnRemove()
        elif id ==  BTN_DUPLICATE:
            self.OnDuplicate()

    def OnNew(self):
        self.PopupMenu(self.menu)
        
    def OnMenu(self, evt):
        id = evt.GetId()
        if id == const.MEASURE_LINEAR:
            ps.Publisher().sendMessage('Set tool linear measure')
        else:
            ps.Publisher().sendMessage('Set tool angular measure')

    def OnRemove(self):
        self.parent.listctrl.RemoveMeasurements()

    def OnDuplicate(self):
        selected_items = self.parent.listctrl.GetSelected()
        if selected_items:
            ps.Publisher().sendMessage('Duplicate measurement', selected_items)
        else:
           dlg.MaskSelectionRequiredForDuplication() 





class MaskPage(wx.Panel):
    """
    Page related to mask items.
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 140))
        self.__init_gui()

    def __init_gui(self):
        # listctrl were existing masks will be listed
        self.listctrl = MasksListCtrlPanel(self, size=wx.Size(256, 100))
        # button control with tools (eg. remove, add new, etc)
        self.buttonctrl = ButtonControlPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.listctrl, 0, wx.EXPAND)
        sizer.Add(self.buttonctrl, 0, wx.EXPAND| wx.TOP, 2)
        self.SetSizer(sizer)
        self.Fit()


class ButtonControlPanel(wx.Panel):
    """
    Button control panel that includes data notebook operations.
    TODO: Enhace interface with parent class - it is really messed up
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 22))
        self.parent = parent
        self.__init_gui()

    def __init_gui(self):
        
        # Bitmaps to be used in plate buttons
        BMP_NEW = wx.Bitmap("../icons/data_new.png",
                            wx.BITMAP_TYPE_PNG)
        BMP_REMOVE = wx.Bitmap("../icons/data_remove.png",
                                wx.BITMAP_TYPE_PNG)
        BMP_DUPLICATE = wx.Bitmap("../icons/data_duplicate.png",
                                wx.BITMAP_TYPE_PNG)

        # Plate buttons based on previous bitmaps
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_new = pbtn.PlateButton(self, BTN_NEW, "",
                                     BMP_NEW,
                                     style=button_style,
                                     size = wx.Size(18, 18))
        button_remove = pbtn.PlateButton(self, BTN_REMOVE, "",
                                         BMP_REMOVE,
                                         style=button_style,
                                         size = wx.Size(18, 18))
        button_duplicate = pbtn.PlateButton(self, BTN_DUPLICATE, "",
                                            BMP_DUPLICATE,
                                            style=button_style,
                                            size = wx.Size(18, 18))

        # Add all controls to gui
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_new, 0, wx.GROW|wx.EXPAND|wx.LEFT)
        sizer.Add(button_remove, 0, wx.GROW|wx.EXPAND)
        sizer.Add(button_duplicate, 0, wx.GROW|wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnButton)

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnNew()
        elif id == BTN_REMOVE:
            self.OnRemove()
        elif id ==  BTN_DUPLICATE:
            self.OnDuplicate()

    def OnNew(self):
        dialog = dlg.NewMask()

        try:
            if dialog.ShowModal() == wx.ID_OK:
                ok = 1
            else:
                ok = 0
        except(wx._core.PyAssertionError): #TODO FIX: win64
            ok = 1

        if ok:
            mask_name, thresh, colour = dialog.GetValue()
            if mask_name:
                ps.Publisher().sendMessage('Create new mask',
                                            (mask_name, thresh, colour))

    def OnRemove(self):
        self.parent.listctrl.RemoveMasks()

    def OnDuplicate(self):
        selected_items = self.parent.listctrl.GetSelected()
        if selected_items:
            ps.Publisher().sendMessage('Duplicate masks', selected_items)
        else:
           dlg.MaskSelectionRequiredForDuplication() 

class MasksListCtrlPanel(wx.ListCtrl, listmix.TextEditMixin):

    def __init__(self, parent, ID=-1, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.LC_REPORT):
        
        # native look and feel for MacOS
        #if wx.Platform == "__WXMAC__":
        #    wx.SystemOptions.SetOptionInt("mac.listctrl.always_use_generic", 0)
        
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style=wx.LC_REPORT)
        listmix.TextEditMixin.__init__(self)
        self.mask_list_index = {}
        self.current_index = 0
        self.__init_columns()
        self.__init_image_list()
        self.__bind_events_wx()
        self.__bind_events()
        
    def __bind_events_wx(self):
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEditLabel)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyEvent)

 
    def __bind_events(self):
        ps.Publisher().subscribe(self.AddMask, 'Add mask')
        ps.Publisher().subscribe(self.EditMaskThreshold,
                                 'Set mask threshold in notebook')
        ps.Publisher().subscribe(self.EditMaskColour,
                                 'Change mask colour in notebook')

        ps.Publisher().subscribe(self.OnChangeCurrentMask, 'Change mask selected')
        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')

    def OnKeyEvent(self, event):
        keycode = event.GetKeyCode()
        # Delete key
        if (sys.platform == 'darwin') and (keycode == wx.WXK_BACK):
            self.RemoveMasks()
        elif (keycode == wx.WXK_DELETE):
            self.RemoveMasks()
    
    def RemoveMasks(self):
        """
        Remove selected items.
        """
        selected_items = self.GetSelected()

        if selected_items:
            ps.Publisher().sendMessage('Remove masks', selected_items)
        else:
            dlg.MaskSelectionRequiredForRemoval()
            return

        # it is necessary to update internal dictionary
        # that maps bitmap given item index
        old_dict = self.mask_list_index
        if selected_items:
            for index in selected_items:
                new_dict = {}
                self.DeleteItem(index)
                for i in old_dict:
                    if i < index:
                        new_dict[i] = old_dict[i]
                    if i > index:
                        new_dict[i-1] = old_dict[i]
                old_dict = new_dict
            self.mask_list_index = new_dict
       
        if new_dict:
            if index == self.current_index:
                self.SetItemImage(0, 1)
                ps.Publisher().sendMessage('Show mask', (0, 1))
                ps.Publisher().sendMessage('Change mask selected', 0)
                for key in new_dict:
                    if key:
                         self.SetItemImage(key, 0)

            elif index < self.current_index:
                self.current_index -= 1
                self.SetItemImage(self.current_index, 1)


    def OnCloseProject(self, pubsub_evt):
        self.DeleteAllItems()
        self.mask_list_index = {}
 
    def OnChangeCurrentMask(self, pubsub_evt):
        mask_index = pubsub_evt.data
        try:
            self.SetItemImage(mask_index, 1)
            self.current_index = mask_index
        except wx._core.PyAssertionError:
            #in SetItem(): invalid item index in SetItem
            pass
        for key in self.mask_list_index.keys():
            if key != mask_index:
                self.SetItemImage(key, 0)

    def __init_columns(self):
        
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, _("Name"))
        self.InsertColumn(2, _("Threshold"), wx.LIST_FORMAT_RIGHT)
        
        self.SetColumnWidth(0, 20)
        self.SetColumnWidth(1, 120)
        self.SetColumnWidth(2, 90)
        
    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image("../icons/object_invisible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_null = self.imagelist.Add(bitmap)

        image = wx.Image("../icons/object_visible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_check = self.imagelist.Add(bitmap)

        self.SetImageList(self.imagelist,wx.IMAGE_LIST_SMALL)

        self.image_gray = Image.open("../icons/object_colour.jpg")
        
    def OnEditLabel(self, evt):
        ps.Publisher().sendMessage('Change mask name',
                                   (evt.GetIndex(), evt.GetLabel()))
        evt.Skip()

    def OnItemActivated(self, evt):
        self.ToggleItem(evt.m_itemIndex)
        
    def OnCheckItem(self, index, flag):
        if flag:
            for key in self.mask_list_index.keys():
                if key != index:
                    self.SetItemImage(key, 0)
            ps.Publisher().sendMessage('Change mask selected',index)
            self.current_index = index
        ps.Publisher().sendMessage('Show mask', (index, flag))

    def CreateColourBitmap(self, colour):
        """
        Create a wx Image with a mask colour.
        colour: colour in rgb format(0 - 1)
        """
        image = self.image_gray
        new_image = Image.new("RGB", image.size)
        for x in xrange(image.size[0]):
            for y in xrange(image.size[1]):
                pixel_colour = [int(i*image.getpixel((x,y)))
                                for i in colour]
                new_image.putpixel((x,y), tuple(pixel_colour))

        wx_image = wx.EmptyImage(new_image.size[0],
                                 new_image.size[1])
        wx_image.SetData(new_image.tostring())
        return wx.BitmapFromImage(wx_image.Scale(16, 16))

    def InsertNewItem(self, index=0, label=_("Mask"), threshold="(1000, 4500)",
                      colour=None):
        self.InsertStringItem(index, "")
        self.SetStringItem(index, 1, label, 
                           imageId=self.mask_list_index[index]) 
        self.SetStringItem(index, 2, threshold)
        self.SetItemImage(index, 1)
        for key in self.mask_list_index.keys():
            if key != index:
                self.SetItemImage(key, 0)
        self.current_index = index
        
    def AddMask(self, pubsub_evt):
        index, mask_name, threshold_range, colour = pubsub_evt.data
        image = self.CreateColourBitmap(colour)
        image_index = self.imagelist.Add(image)
        self.mask_list_index[index] = image_index
        self.InsertNewItem(index, mask_name, str(threshold_range))
                
    def EditMaskThreshold(self, pubsub_evt):
        index, threshold_range = pubsub_evt.data
        self.SetStringItem(index, 2, str(threshold_range))

    def EditMaskColour(self, pubsub_evt):
        index, colour = pubsub_evt.data
        image = self.CreateColourBitmap(colour)
        image_index = self.mask_list_index[index]
        self.imagelist.Replace(image_index, image)
        self.Refresh()

    def GetSelected(self):
        """
        Return all items selected (highlighted).
        """
        selected = []
        for index in self.mask_list_index:
            if self.IsSelected(index):
                selected.append(index)
        # it is important to revert items order, so
        # listctrl update is ok
        selected.sort(reverse=True)
        return selected


#-------------------------------------------------
#-------------------------------------------------
class SurfacePage(wx.Panel):
    """
    Page related to mask items.
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 140))
        self.__init_gui()

    def __init_gui(self):
        # listctrl were existing masks will be listed
        self.listctrl = SurfacesListCtrlPanel(self, size=wx.Size(256, 100))
        # button control with tools (eg. remove, add new, etc)
        self.buttonctrl = SurfaceButtonControlPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.listctrl, 0, wx.EXPAND)
        sizer.Add(self.buttonctrl, 0, wx.EXPAND| wx.TOP, 2)
        self.SetSizer(sizer)
        self.Fit()

class SurfaceButtonControlPanel(wx.Panel):
    """
    Button control panel that includes data notebook operations.
    TODO: Enhace interface with parent class - it is really messed up
    """
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                            size=wx.Size(256, 22))
        self.parent = parent
        self.__init_gui()

    def __init_gui(self):
        
        # Bitmaps to be used in plate buttons
        BMP_NEW = wx.Bitmap("../icons/data_new.png",
                            wx.BITMAP_TYPE_PNG)
        BMP_REMOVE = wx.Bitmap("../icons/data_remove.png",
                                wx.BITMAP_TYPE_PNG)
        BMP_DUPLICATE = wx.Bitmap("../icons/data_duplicate.png",
                                wx.BITMAP_TYPE_PNG)

        # Plate buttons based on previous bitmaps
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT
        button_new = pbtn.PlateButton(self, BTN_NEW, "",
                                     BMP_NEW,
                                     style=button_style,
                                     size = wx.Size(18, 18))
        button_remove = pbtn.PlateButton(self, BTN_REMOVE, "",
                                         BMP_REMOVE,
                                         style=button_style,
                                         size = wx.Size(18, 18))
        button_duplicate = pbtn.PlateButton(self, BTN_DUPLICATE, "",
                                            BMP_DUPLICATE,
                                            style=button_style,
                                            size = wx.Size(18, 18))

        # Add all controls to gui
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_new, 0, wx.GROW|wx.EXPAND|wx.LEFT)
        sizer.Add(button_remove, 0, wx.GROW|wx.EXPAND)
        sizer.Add(button_duplicate, 0, wx.GROW|wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        # Bindings
        self.Bind(wx.EVT_BUTTON, self.OnButton)

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_NEW:
            self.OnNew()
        elif id == BTN_REMOVE:
            self.OnRemove()
        elif id ==  BTN_DUPLICATE:
            self.OnDuplicate()

    def OnNew(self):
        import project as prj

        dialog = dlg.NewSurfaceDialog()
        try:
            if dialog.ShowModal() == wx.ID_OK:
                ok = 1
            else:
                ok = 0
        except(wx._core.PyAssertionError): #TODO FIX: win64
            ok = 1

        if ok:
            (mask_index, surface_name, surface_quality, fill_holes,\
            keep_largest) = dialog.GetValue()

            # Retrieve information from mask
            proj = prj.Project()
            mask = proj.mask_dict[mask_index]

            # Send all information so surface can be created
            surface_data = [proj.imagedata,
                            mask.colour,
                            mask.threshold_range,
                            mask.edited_points,
                            False, # overwrite
                            surface_name,
                            surface_quality,
                            fill_holes,
                            keep_largest]

            ps.Publisher().sendMessage('Create surface', surface_data)

    def OnRemove(self):
        self.parent.listctrl.RemoveSurfaces()


    def OnDuplicate(self):
        selected_items = self.parent.listctrl.GetSelected()
        if selected_items:
            ps.Publisher().sendMessage('Duplicate surfaces', selected_items)
        else:
           dlg.SurfaceSelectionRequiredForDuplication() 


class SurfacesListCtrlPanel(wx.ListCtrl, listmix.TextEditMixin):

    def __init__(self, parent, ID=-1, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.LC_REPORT):
        
        # native look and feel for MacOS
        #if wx.Platform == "__WXMAC__":
        #    wx.SystemOptions.SetOptionInt("mac.listctrl.always_use_generic", 0)
        
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style=wx.LC_REPORT)
        listmix.TextEditMixin.__init__(self)

        self.__init_columns()
        self.__init_image_list()
        self.__init_evt()
        self.__bind_events_wx()
        self.surface_list_index = {}
        self.surface_bmp_idx_to_name = {}

    def __init_evt(self):
        ps.Publisher().subscribe(self.AddSurface,
                                'Update surface info in GUI')
        ps.Publisher().subscribe(self.EditSurfaceTransparency,
                                 'Set surface transparency')
        ps.Publisher().subscribe(self.EditSurfaceColour,
                                 'Set surface colour')
        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')
        ps.Publisher().subscribe(self.OnHideSurface, 'Hide surface items')

        ps.Publisher().subscribe(self.OnShowSingle, 'Show single surface')
        ps.Publisher().subscribe(self.OnShowMultiple, 'Show multiple surfaces') 

    def __bind_events_wx(self):
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEditLabel)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected_)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyEvent)


    def OnKeyEvent(self, event):
        keycode = event.GetKeyCode()
        # Delete key
        if (sys.platform == 'darwin') and (keycode == wx.WXK_BACK):
            self.RemoveSurfaces()
        elif (keycode == wx.WXK_DELETE):
            self.RemoveSurfaces()


    def OnHideSurface(self, pubsub_evt):
        surface_dict = pubsub_evt.data
        for key in surface_dict:
            if not surface_dict[key].is_shown:
                self.SetItemImage(key, False)
            

    def RemoveSurfaces(self):
        """
        Remove item given its index.
        """
        # it is necessary to update internal dictionary
        # that maps bitmap given item index
        selected_items = self.GetSelected()
        old_dict = self.surface_list_index
        if selected_items:
            for index in selected_items:
                new_dict = {}
                self.DeleteItem(index)
                for i in old_dict:
                    if i < index:
                        new_dict[i] = old_dict[i]
                    if i > index:
                        new_dict[i-1] = old_dict[i]
                old_dict = new_dict
            self.surface_list_index = new_dict

            ps.Publisher().sendMessage('Remove surfaces', selected_items)
        else:
           dlg.SurfaceSelectionRequiredForRemoval() 


    def OnCloseProject(self, pubsub_evt):
        self.DeleteAllItems()
        self.surface_list_index = {}
        self.surface_bmp_idx_to_name = {}

    def OnItemSelected_(self, evt):
        # Note: DON'T rename to OnItemSelected!!!
        # Otherwise the parent's method will be overwritten and other
        # things will stop working, e.g.: OnCheckItem

        last_surface_index = evt.m_itemIndex
        ps.Publisher().sendMessage('Change surface selected',
                                    last_surface_index)
        evt.Skip()

    def GetSelected(self):
        """
        Return all items selected (highlighted).
        """
        selected = []
        for index in self.surface_list_index:
            if self.IsSelected(index):
                selected.append(index)
        # it is important to revert items order, so
        # listctrl update is ok
        selected.sort(reverse=True)

        return selected

    def __init_columns(self):
        
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, _("Name"))
        self.InsertColumn(2, _(u"Volume (mm³)"))
        self.InsertColumn(3, _("Transparency"), wx.LIST_FORMAT_RIGHT)
        
        self.SetColumnWidth(0, 20)
        self.SetColumnWidth(1, 85)
        self.SetColumnWidth(2, 85)
        self.SetColumnWidth(3, 80)
        
    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image("../icons/object_invisible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_null = self.imagelist.Add(bitmap)

        image = wx.Image("../icons//object_visible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_check = self.imagelist.Add(bitmap)
        
        self.SetImageList(self.imagelist,wx.IMAGE_LIST_SMALL)

        self.image_gray = Image.open("../icons/object_colour.jpg")


    def OnEditLabel(self, evt):
        ps.Publisher().sendMessage('Change surface name', (evt.GetIndex(), evt.GetLabel()))
        evt.Skip()
        
    def OnItemActivated(self, evt):
        self.ToggleItem(evt.m_itemIndex)
        evt.Skip()

        
    def OnCheckItem(self, index, flag):
        ps.Publisher().sendMessage('Show surface', (index, flag)) 

    def OnShowSingle(self, pubsub_evt):
        index, visibility = pubsub_evt.data
        for key in self.surface_list_index.keys():
            if key != index:
                self.SetItemImage(key, not visibility)
                ps.Publisher().sendMessage('Show surface',
                                            (key, not visibility)) 
        self.SetItemImage(index, visibility)
        ps.Publisher().sendMessage('Show surface',
                                   (index, visibility))

    def OnShowMultiple(self, pubsub_evt):
        index_list, visibility = pubsub_evt.data
        for key in self.surface_list_index.keys():
            if key not in index_list:
                self.SetItemImage(key, not visibility)
                ps.Publisher().sendMessage('Show surface',
                                            (key, not visibility)) 
        for index in index_list:
            self.SetItemImage(index, visibility)
            ps.Publisher().sendMessage('Show surface',
                                       (index, visibility))

    def AddSurface(self, pubsub_evt):
        index = pubsub_evt.data[0]
        name = pubsub_evt.data[1]
        colour = pubsub_evt.data[2]
        volume = "%d"%(int(pubsub_evt.data[3]))
        transparency = "%d%%"%(int(100*pubsub_evt.data[4]))
       
        if index not in self.surface_list_index:
            image = self.CreateColourBitmap(colour)
            image_index = self.imagelist.Add(image)
        
        

            index_list = self.surface_list_index.keys()
            self.surface_list_index[index] = image_index

            if (index in index_list) and index_list:
                self.UpdateItemInfo(index, name, volume, transparency, colour)
            else:
                self.InsertNewItem(index, name, volume, transparency, colour)



    def InsertNewItem(self, index=0, label="Surface 1", volume="0 mm3",
                      transparency="0%%", colour=None):
        self.InsertStringItem(index, "")
        self.SetStringItem(index, 1, label,
                            imageId = self.surface_list_index[index]) 
        self.SetStringItem(index, 2, volume)
        self.SetStringItem(index, 3, transparency)
        self.SetItemImage(index, 1)

    def UpdateItemInfo(self, index=0, label="Surface 1", volume="0 mm3",
                      transparency="0%%", colour=None):
        self.SetStringItem(index, 1, label,
                            imageId = self.surface_list_index[index]) 
        self.SetStringItem(index, 2, volume)
        self.SetStringItem(index, 3, transparency)
        self.SetItemImage(index, 1)

        
    def CreateColourBitmap(self, colour):
        """
        Create a wx Image with a mask colour.
        colour: colour in rgb format(0 - 1)
        """
        image = self.image_gray
        new_image = Image.new("RGB", image.size)
        for x in xrange(image.size[0]):
            for y in xrange(image.size[1]):
                pixel_colour = [int(i*image.getpixel((x,y)))
                                for i in colour]
                new_image.putpixel((x,y), tuple(pixel_colour))

        wx_image = wx.EmptyImage(new_image.size[0],
                                 new_image.size[1])
        wx_image.SetData(new_image.tostring())
        return wx.BitmapFromImage(wx_image.Scale(16, 16))

    def EditSurfaceTransparency(self, pubsub_evt):
        """
        Set actor transparency (oposite to opacity) according to given actor
        index and value.
        """
        index, value = pubsub_evt.data
        self.SetStringItem(index, 3, "%d%%"%(int(value*100)))
        
    def EditSurfaceColour(self, pubsub_evt):
        """
        """
        index, colour = pubsub_evt.data
        image = self.CreateColourBitmap(colour)
        image_index = self.surface_list_index[index]
        self.imagelist.Replace(image_index, image)
        self.Refresh()


#-------------------------------------------------
#-------------------------------------------------

class MeasuresListCtrlPanel(wx.ListCtrl, listmix.TextEditMixin):

    def __init__(self, parent, ID=-1, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.LC_REPORT):
        
        # native look and feel for MacOS
        #if wx.Platform == "__WXMAC__":
        #    wx.SystemOptions.SetOptionInt("mac.listctrl.always_use_generic", 0)
        
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style=wx.LC_REPORT)
        listmix.TextEditMixin.__init__(self)

        self.__init_columns()
        self.__init_image_list()
        self.__init_evt()
        self.__bind_events_wx()
        self._list_index = {}
        self._bmp_idx_to_name = {}

    def __init_evt(self):
        ps.Publisher().subscribe(self.AddItem_,
                                'Update measurement info in GUI')
        ps.Publisher().subscribe(self.EditItemColour,
                                 'Set measurement colour')
        ps.Publisher().subscribe(self.OnCloseProject, 'Close project data')
        ps.Publisher().subscribe(self.OnShowSingle, 'Show single measurement')
        ps.Publisher().subscribe(self.OnShowMultiple, 'Show multiple measurements') 
        ps.Publisher().subscribe(self.OnLoadData, 'Load measurement dict')

    def __bind_events_wx(self):
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEditLabel)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected_)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyEvent)


    def OnKeyEvent(self, event):
        keycode = event.GetKeyCode()
        # Delete key
        if (sys.platform == 'darwin') and (keycode == wx.WXK_BACK):
            self.RemoveMeasurements()
        elif (keycode == wx.WXK_DELETE):
            self.RemoveMeasurements()

    def RemoveMeasurements(self):
        """
        Remove items selected.
        """
        # it is necessary to update internal dictionary
        # that maps bitmap given item index
        selected_items = self.GetSelected()
        selected_items.sort(reverse=True)

        old_dict = self._list_index
        if selected_items:
            for index in selected_items:
                new_dict = {}
                self.DeleteItem(index)
                for i in old_dict:
                    if i < index:
                        new_dict[i] = old_dict[i]
                    if i > index:
                        new_dict[i-1] = old_dict[i]
                old_dict = new_dict
            self._list_index = new_dict
            ps.Publisher().sendMessage('Remove measurements', selected_items)
        else:
           dlg.MeasureSelectionRequiredForRemoval()


    def OnCloseProject(self, pubsub_evt):
        self.DeleteAllItems()
        self._list_index = {}
        self._bmp_idx_to_name = {}

    def OnItemSelected_(self, evt):
        # Note: DON'T rename to OnItemSelected!!!
        # Otherwise the parent's method will be overwritten and other
        # things will stop working, e.g.: OnCheckItem

        last_index = evt.m_itemIndex
        ps.Publisher().sendMessage('Change measurement selected',
                                    last_index)
        evt.Skip()

    def GetSelected(self):
        """
        Return all items selected (highlighted).
        """
        selected = []
        for index in self._list_index:
            if self.IsSelected(index):
                selected.append(index)
        # it is important to revert items order, so
        # listctrl update is ok
        selected.sort(reverse=True)

        return selected

    def __init_columns(self):

        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, _("Name"))
        self.InsertColumn(2, _("Location"))
        self.InsertColumn(3, _("Type"))
        self.InsertColumn(4, _("Value"), wx.LIST_FORMAT_RIGHT)
        
        self.SetColumnWidth(0, 20)
        self.SetColumnWidth(1, 65)
        self.SetColumnWidth(2, 55)
        self.SetColumnWidth(3, 50)
        self.SetColumnWidth(4, 75)
 
    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image("../icons/object_invisible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_null = self.imagelist.Add(bitmap)

        image = wx.Image("../icons/object_visible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_check = self.imagelist.Add(bitmap)
        
        self.SetImageList(self.imagelist,wx.IMAGE_LIST_SMALL)

        self.image_gray = Image.open("../icons/object_colour.jpg")


    def OnEditLabel(self, evt):
        ps.Publisher().sendMessage('Change measurement name', (evt.GetIndex(), evt.GetLabel()))
        evt.Skip()
        
    def OnItemActivated(self, evt):
        self.ToggleItem(evt.m_itemIndex)
        evt.Skip()

        
    def OnCheckItem(self, index, flag):
        ps.Publisher().sendMessage('Show measurement', (index, flag)) 

    def OnShowSingle(self, pubsub_evt):
        index, visibility = pubsub_evt.data
        for key in self._list_index.keys():
            if key != index:
                self.SetItemImage(key, not visibility)
                ps.Publisher().sendMessage('Show measurement',
                                            (key, not visibility)) 
        self.SetItemImage(index, visibility)
        ps.Publisher().sendMessage('Show measurement',
                                   (index, visibility))

    def OnShowMultiple(self, pubsub_evt):
        index_list, visibility = pubsub_evt.data
        for key in self._list_index.keys():
            if key not in index_list:
                self.SetItemImage(key, not visibility)
                ps.Publisher().sendMessage('Show measurement',
                                            (key, not visibility)) 
        for index in index_list:
            self.SetItemImage(index, visibility)
            ps.Publisher().sendMessage('Show measurement',
                                       (index, visibility))

    def OnLoadData(self, pubsub_evt):
        items_dict = pubsub_evt.data
        for i in items_dict:
            m = items_dict[i]
            image = self.CreateColourBitmap(m.colour)
            image_index = self.imagelist.Add(image)
        
            index_list = self._list_index.keys()
            self._list_index[m.index] = image_index

            colour = [255*c for c in m.colour]
            type = TYPE[m.type]
            location = LOCATION[m.location]
            if m.type == const.LINEAR:
                value = (u"%.2f mm") % m.value
            else:
                value = (u"%.2f°") % m.value
            self.InsertNewItem(m.index, m.name, colour, location, type, value)

            if not m.is_shown:
                self.SetItemImage(i, False)

    def AddItem_(self, pubsub_evt):
        index = pubsub_evt.data[0]
        name = pubsub_evt.data[1]
        colour = pubsub_evt.data[2]
        location = pubsub_evt.data[3]
        type_ = pubsub_evt.data[4]
        value = pubsub_evt.data[5]

        if index not in self._list_index:
            image = self.CreateColourBitmap(colour)
            image_index = self.imagelist.Add(image)
        
            index_list = self._list_index.keys()
            self._list_index[index] = image_index

            if (index in index_list) and index_list:
                self.UpdateItemInfo(index, name, colour, location, type_, value)
            else:
                self.InsertNewItem(index, name, colour, location, type_, value)



    def InsertNewItem(self, index=0, label="Measurement 1", colour=None,
                       location="SURFACE", type_="LINEAR", value="0 mm"):
        self.InsertStringItem(index, "")
        self.SetStringItem(index, 1, label,
                            imageId = self._list_index[index]) 
        self.SetStringItem(index, 2, location)
        self.SetStringItem(index, 3, type_)
        self.SetStringItem(index, 4, value)
        self.SetItemImage(index, 1)
        self.Refresh()

    def UpdateItemInfo(self, index=0, label="Measurement 1", colour=None,
                      type_="LINEAR", location="SURFACE", value="0 mm"):
        self.SetStringItem(index, 1, label,
                            imageId = self._list_index[index]) 
        self.SetStringItem(index, 2, type_)
        self.SetStringItem(index, 3, location)
        self.SetStringItem(index, 4, value)
        self.SetItemImage(index, 1)
        self.Refresh()
        
    def CreateColourBitmap(self, colour):
        """
        Create a wx Image with a mask colour.
        colour: colour in rgb format(0 - 1)
        """
        image = self.image_gray
        new_image = Image.new("RGB", image.size)
        for x in xrange(image.size[0]):
            for y in xrange(image.size[1]):
                pixel_colour = [int(i*image.getpixel((x,y)))
                                for i in colour]
                new_image.putpixel((x,y), tuple(pixel_colour))

        wx_image = wx.EmptyImage(new_image.size[0],
                                 new_image.size[1])
        wx_image.SetData(new_image.tostring())
        return wx.BitmapFromImage(wx_image.Scale(16, 16))

    def EditItemColour(self, pubsub_evt):
        """
        """
        index, colour = pubsub_evt.data
        image = self.CreateColourBitmap(colour)
        image_index = self._list_index[index]
        self.imagelist.Replace(image_index, image)
        self.Refresh()



#*******************************************************************
#*******************************************************************

    
class AnnotationsListCtrlPanel(wx.ListCtrl, listmix.TextEditMixin):
    # TODO: Remove edimixin, allow only visible and invisible
    def __init__(self, parent, ID=-1, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.LC_REPORT):
        
        # native look and feel for MacOS
        #if wx.Platform == "__WXMAC__":
        #    wx.SystemOptions.SetOptionInt("mac.listctrl.always_use_generic", 0)
        
        wx.ListCtrl.__init__(self, parent, ID, pos, size, style=wx.LC_REPORT)
        listmix.TextEditMixin.__init__(self)

        self.__init_columns()
        self.__init_image_list()
        self.__init_evt()
        
        # just testing
        self.Populate()
        
    def __init_evt(self):
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)

    def __init_columns(self):
        
        self.InsertColumn(0, "", wx.LIST_FORMAT_CENTER)
        self.InsertColumn(1, _("Name"))
        self.InsertColumn(2, _("Type"), wx.LIST_FORMAT_CENTER)
        self.InsertColumn(3, _("Value"))
        
        self.SetColumnWidth(0, 20)
        self.SetColumnWidth(1, 90)
        self.SetColumnWidth(2, 50)
        self.SetColumnWidth(3, 120)
        
    def __init_image_list(self):
        self.imagelist = wx.ImageList(16, 16)

        image = wx.Image("../icons/object_visible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_check = self.imagelist.Add(bitmap)
        
        image = wx.Image("../icons/object_invisible.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        img_null = self.imagelist.Add(bitmap)

        image = wx.Image("../icons/object_colour.jpg")
        bitmap = wx.BitmapFromImage(image.Scale(16, 16))
        bitmap.SetWidth(16)
        bitmap.SetHeight(16)
        self.img_colour = self.imagelist.Add(bitmap)
        
        self.SetImageList(self.imagelist,wx.IMAGE_LIST_SMALL)

        
    def OnItemActivated(self, evt):
        self.ToggleItem(evt.m_itemIndex)
        
    def OnCheckItem(self, index, flag):
        # TODO: use pubsub to communicate to models
        if flag:
            print "checked, ", index
        else:
            print "unchecked, ", index

    def InsertNewItem(self, index=0, name="Axial 1", type_="2d",
                      value="bla", colour=None):
        self.InsertStringItem(index, "")
        self.SetStringItem(index, 1, name, imageId = self.img_colour) 
        self.SetStringItem(index, 2, type_)
        self.SetStringItem(index, 3, value)
        
    def Populate(self):
        dict = ((0, "Axial 1", "2D", "blalbalblabllablalbla"),
                (1, "Coronal 1", "2D", "hello here we are again"),
                (2, "Volume 1", "3D", "hey ho, lets go"))
        for data in dict:
            self.InsertNewItem(data[0], data[1], data[2], data[3])
