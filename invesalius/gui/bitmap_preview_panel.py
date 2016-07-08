import wx
import vtk
import vtkgdcm
import time

from vtk.util import  numpy_support
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from wx.lib.pubsub import pub as Publisher

import constants as const
import data.vtk_utils as vtku
from data import converters
from reader import bitmap_reader
import utils

NROWS = 3
NCOLS = 6
NUM_PREVIEWS = NCOLS*NROWS
PREVIEW_WIDTH = 70
PREVIEW_HEIGTH = 70

PREVIEW_BACKGROUND = (255, 255, 255) # White

STR_SIZE = _("Image size: %d x %d")
STR_SPC = _("Spacing: %.2f")
STR_LOCAL = _("Location: %.2f")
STR_PATIENT = "%s\n%s"
STR_ACQ = _("%s %s\nMade in InVesalius")

myEVT_PREVIEW_CLICK = wx.NewEventType()
EVT_PREVIEW_CLICK = wx.PyEventBinder(myEVT_PREVIEW_CLICK, 1)

myEVT_PREVIEW_DBLCLICK = wx.NewEventType()
EVT_PREVIEW_DBLCLICK = wx.PyEventBinder(myEVT_PREVIEW_DBLCLICK, 1)

myEVT_CLICK_SLICE = wx.NewEventType()
# This event occurs when the user select a preview
EVT_CLICK_SLICE = wx.PyEventBinder(myEVT_CLICK_SLICE, 1)

myEVT_CLICK_SERIE = wx.NewEventType()
# This event occurs when the user select a preview
EVT_CLICK_SERIE = wx.PyEventBinder(myEVT_CLICK_SERIE, 1)

myEVT_CLICK = wx.NewEventType()
EVT_CLICK = wx.PyEventBinder(myEVT_CLICK, 1)


class SelectionEvent(wx.PyCommandEvent):
    pass


class PreviewEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id):
        super(PreviewEvent, self).__init__(evtType, id)

    def GetSelectID(self):
        return self.SelectedID

    def SetSelectedID(self, id):
        self.SelectedID = id

    def GetItemData(self):
        return self.data

    def GetPressedShift(self):
        return self.pressed_shift
    
    def SetItemData(self, data):
        self.data = data

    def SetShiftStatus(self, status):
        self.pressed_shift = status
    

class SerieEvent(PreviewEvent):
    def __init__(self , evtType, id):
        super(SerieEvent, self).__init__(evtType, id)


class BitmapInfo(object):
    """
    Keep the informations and the image used by preview.
    """
    def __init__(self, data):
        #self.id = id
        self.id = data[7]
        self.title = data[6]
        self.data = data
        self.pos = data[8]
        #self.subtitle = subtitle
        self._preview = None
        self.selected = False
        #self.filename = ""
        self.thumbnail_path = data[1]

    @property
    def preview(self):
        
        if not self._preview:
            bmp = wx.Bitmap(self.thumbnail_path, wx.BITMAP_TYPE_PNG)
            self._preview = bmp.ConvertToImage()
        return self._preview
        
    def release_thumbnail(self):
        self._preview = None

class DicomPaintPanel(wx.Panel):
    def __init__(self, parent):
        super(DicomPaintPanel, self).__init__(parent)
        self._bind_events()
        self.image = None
        self.last_size = (10,10)

    def _bind_events(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def _build_bitmap(self, image):
        bmp = wx.BitmapFromImage(image)
        return bmp

    def _image_resize(self, image):
        self.Update()
        self.Layout()
        new_size = self.GetSize()
        # This is necessary due to darwin problem #
        if new_size != (0,0):
            self.last_size = new_size
            return image.Scale(*new_size)
        else:
            return image.Scale(*self.last_size)

    def SetImage(self, image):
        self.image = image
        r_img = self._image_resize(image)
        self.bmp = self._build_bitmap(r_img)
        self.Refresh()

    def OnPaint(self, evt):
        if self.image:
            dc = wx.PaintDC(self)
            dc.Clear()
            dc.DrawBitmap(self.bmp, 0, 0)

    def OnSize(self, evt):
        if self.image:
            self.bmp = self._build_bitmap(self._image_resize(self.image))
        self.Refresh()
        evt.Skip()


class Preview(wx.Panel):
    """
    The little previews.
    """
    def __init__(self, parent):
        super(Preview, self).__init__(parent)
        # Will it be white?
        self.select_on = False
        self.bitmap_info = None
        self._init_ui()
        self._bind_events()

    def _init_ui(self):
        self.SetBackgroundColour(PREVIEW_BACKGROUND)

        self.title = wx.StaticText(self, -1, _("Image"))
        self.subtitle = wx.StaticText(self, -1, _("Image"))
        self.image_viewer = DicomPaintPanel(self)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.title, 0,
                        wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.subtitle, 0,
                        wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.image_viewer, 1, wx.ALIGN_CENTRE_HORIZONTAL \
                       | wx.SHAPED | wx.ALL, 5)
        self.sizer.Fit(self)

        self.SetSizer(self.sizer)

        self.Layout()
        self.Update()
        self.Fit()
        self.SetAutoLayout(1)

    def _bind_events(self):
        self.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        #self.interactor.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        #self.panel.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        #self.title.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        #self.subtitle.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)

        self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        #self.interactor.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        #self.panel.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        #self.title.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        #self.subtitle.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)

        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        #self.interactor.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        #self.panel.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        #self.title.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        #self.subtitle.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)

        self.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.title.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.subtitle.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.image_viewer.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)

        #self.Bind(wx.EVT_SIZE, self.OnSize)

    def SetBitmapToPreview(self, bitmap_info):
        """
        Set a dicom to preview.
        """
    
        """
        self.dicom_info = dicom_info
        self.SetTitle(dicom_info.title)
        self.SetSubtitle(dicom_info.subtitle)
        self.ID = dicom_info.id
        dicom_info.size = self.image_viewer.GetSize()
        image = dicom_info.preview
        self.image_viewer.SetImage(image)
        self.data = dicom_info.id
        self.select_on = dicom_info.selected
        self.Select()
        self.Update()
        """



        if self.bitmap_info:
            self.bitmap_info.release_thumbnail()

        self.bitmap_info = bitmap_info
        self.SetTitle(self.bitmap_info.title[-10:])
        self.SetSubtitle('')

        ##self.ID = bitmap_info.id
        ##bitmap_info.size = self.image_viewer.GetSize()
        image = self.bitmap_info.preview
        
        self.image_viewer.SetImage(image)
        #self.data = bitmap_info.id
        self.select_on = bitmap_info.selected
        self.Select()
        self.Update()

    def SetTitle(self, title):
        self.title.SetLabel(title)

    def SetSubtitle(self, subtitle):
        self.subtitle.SetLabel(subtitle)

    def OnEnter(self, evt):
        if not self.select_on:
            #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHILIGHT)
            c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNFACE)
            self.SetBackgroundColour(c)

    def OnLeave(self, evt):
        if not self.select_on:
            c = (PREVIEW_BACKGROUND)
            self.SetBackgroundColour(c)

    def OnSelect(self, evt):

        shift_pressed = False
        if evt.m_shiftDown:
            shift_pressed = True

        dicom_id = self.bitmap_info.id
        self.select_on = True
        self.bitmap_info.selected = True
        self.Select()

        # Generating a EVT_PREVIEW_CLICK event
        my_evt = SerieEvent(myEVT_PREVIEW_CLICK, self.GetId())

        my_evt.SetSelectedID(self.bitmap_info.id)
        my_evt.SetItemData(self.bitmap_info.data)

        my_evt.SetShiftStatus(shift_pressed)
        my_evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(my_evt)

        Publisher.sendMessage('Set bitmap in preview panel', self.bitmap_info.pos)

        evt.Skip()
        

    def OnSize(self, evt):
        if self.bitmap_info:
            self.SetBitmapToPreview(self.bitmap_info)
        evt.Skip()

    def Select(self, on=True):
        if self.select_on:
            c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        else:
            c = (PREVIEW_BACKGROUND)
        self.SetBackgroundColour(c)
        self.Refresh()

    def OnDClick(self, evt):
        my_evt = SerieEvent(myEVT_PREVIEW_DBLCLICK, self.GetId())
        my_evt.SetSelectedID(self.bitmap_info.id)
        my_evt.SetItemData(self.bitmap_info.data)
        my_evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(my_evt)
        evt.Skip()


class BitmapPreviewSeries(wx.Panel):
    """A dicom series preview panel"""
    def __init__(self, parent):
        super(BitmapPreviewSeries, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        #self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        #self.SetSizer(self.sizer)
        self.displayed_position = 0
        self.nhidden_last_display = 0
        self.selected_dicom = None
        self.selected_panel = None
        self._init_ui()

    def _init_ui(self):
        scroll = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        self.scroll = scroll

        self.grid = wx.GridSizer(rows=NROWS, cols=NCOLS, vgap=3, hgap=3)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.AddSizer(self.grid, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)

        background_sizer = wx.BoxSizer(wx.HORIZONTAL)
        background_sizer.AddSizer(sizer, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)
        background_sizer.Add(scroll, 0, wx.EXPAND|wx.GROW)
        self.SetSizer(background_sizer)
        background_sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = background_sizer

        self._Add_Panels_Preview()
        self._bind_events()

    def _Add_Panels_Preview(self):
        self.previews = []
        for i in xrange(NROWS):
            for j in xrange(NCOLS):
                p = Preview(self)
                p.Bind(EVT_PREVIEW_CLICK, self.OnSelect)
                #if (i == j == 0):
                    #self._show_shadow(p)
                #p.Hide()
                self.previews.append(p)
                self.grid.Add(p, 1, flag=wx.EXPAND)

    #def _show_shadow(self, preview):
    #    preview.ShowShadow()

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)

    def OnSelect(self, evt):
        my_evt = SerieEvent(myEVT_CLICK_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())

        if self.selected_dicom:
            self.selected_dicom.selected = self.selected_dicom is \
                    evt.GetEventObject().bitmap_info
            self.selected_panel.select_on = self.selected_panel is evt.GetEventObject()
            self.selected_panel.Select()
        self.selected_panel = evt.GetEventObject()
        self.selected_dicom = self.selected_panel.bitmap_info
        self.GetEventHandler().ProcessEvent(my_evt)
        evt.Skip()

    def SetBitmapFiles(self, data):
        #self.files = data
        self.files = []
        
        bitmap = bitmap_reader.BitmapData()
        bitmap.SetData(data)

        pos = 0
        for d in data:
            d.append(pos)
            info = BitmapInfo(d)
            self.files.append(info)
            pos += 1

        scroll_range = len(self.files)/NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
        self._display_previews()

    
    #def SetPatientGroups(self, patient):
    #    self.files = []
    #    self.displayed_position = 0
    #    self.nhidden_last_display = 0
    #    group_list = patient.GetGroups()
    #    self.group_list = group_list
    #    n = 0
    #    for group in group_list:
    #        info = BitmapInfo((group.dicom.patient.id,
    #                          group.dicom.acquisition.serie_number),
    #                         group.dicom,
    #                         group.title,
    #                         _("%d images") %(group.nslices))
    #        self.files.append(info)
    #        n+=1
    #    scroll_range = len(self.files)/NCOLS
    #    if scroll_range * NCOLS < len(self.files):
    #        scroll_range +=1
    #    self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
    #    self._display_previews()


    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + NUM_PREVIEWS
        if len(self.files) < final:
            for i in xrange(final-len(self.files)):
                try:
                    self.previews[-i-1].Hide()
                except IndexError:
                    utils.debug("doesn't exist!")
                    pass
            self.nhidden_last_display = final-len(self.files)
        else:
            if self.nhidden_last_display:
                for i in xrange(self.nhidden_last_display):
                    try:
                        self.previews[-i-1].Show()
                    except IndexError:
                        utils.debug("doesn't exist!")
                        pass
                self.nhidden_last_display = 0

        for f, p in zip(self.files[initial:final], self.previews):
            p.SetBitmapToPreview(f)
            if f.selected:
                self.selected_panel = p

        for f, p in zip(self.files[initial:final], self.previews):
            p.Show()


    def OnScroll(self, evt=None):
        if evt:
            if self.displayed_position != evt.GetPosition():
                self.displayed_position = evt.GetPosition()
        else:
            if self.displayed_position != self.scroll.GetThumbPosition():
                self.displayed_position = self.scroll.GetThumbPosition()
        self._display_previews()

    def OnWheel(self, evt):
        d = evt.GetWheelDelta() / evt.GetWheelRotation()
        self.scroll.SetThumbPosition(self.scroll.GetThumbPosition() - d)
        self.OnScroll()


class SingleImagePreview(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.actor = None
        self.__init_gui()
        self.__init_vtk()
        self.__bind_evt_gui()
        self.__bind_pubsub()
        self.dicom_list = []
        self.nimages = 1
        self.current_index = 0
        self.window_width = const.WINDOW_LEVEL[_("Bone")][0]
        self.window_level = const.WINDOW_LEVEL[_("Bone")][1]

    def __init_vtk(self):
        text_image_size = vtku.Text()
        text_image_size.SetPosition(const.TEXT_POS_LEFT_UP)
        text_image_size.SetValue("")
        text_image_size.SetSize(const.TEXT_SIZE_SMALL)
        self.text_image_size = text_image_size

        text_image_location = vtku.Text()
        text_image_location.SetVerticalJustificationToBottom()
        text_image_location.SetPosition(const.TEXT_POS_LEFT_DOWN)
        text_image_location.SetValue("")
        text_image_location.SetSize(const.TEXT_SIZE_SMALL)
        self.text_image_location = text_image_location

        text_patient = vtku.Text()
        text_patient.SetJustificationToRight()
        text_patient.SetPosition(const.TEXT_POS_RIGHT_UP)
        text_patient.SetValue("")
        text_patient.SetSize(const.TEXT_SIZE_SMALL)
        self.text_patient = text_patient

        text_acquisition = vtku.Text()
        text_acquisition.SetJustificationToRight()
        text_acquisition.SetVerticalJustificationToBottom()
        text_acquisition.SetPosition(const.TEXT_POS_RIGHT_DOWN)
        text_acquisition.SetValue("")
        text_acquisition.SetSize(const.TEXT_SIZE_SMALL)
        self.text_acquisition = text_acquisition

        renderer = vtk.vtkRenderer()
        renderer.AddActor(text_image_size.actor)
        renderer.AddActor(text_image_location.actor)
        renderer.AddActor(text_patient.actor)
        renderer.AddActor(text_acquisition.actor)
        self.renderer = renderer

        style = vtk.vtkInteractorStyleImage()

        interactor = wxVTKRenderWindowInteractor(self.panel, -1,
                                    size=wx.Size(340,340))
        interactor.GetRenderWindow().AddRenderer(renderer)
        interactor.SetInteractorStyle(style)
        interactor.Render()
        self.interactor = interactor

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(interactor, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self.panel)
        self.panel.SetSizer(sizer)
        self.Layout()
        self.Update()

    def __init_gui(self):
        self.panel = wx.Panel(self, -1)

        slider = wx.Slider(self,
                            id=-1,
                            value=0,
                            minValue=0,
                            maxValue=99,
                            style=wx.SL_HORIZONTAL|wx.SL_AUTOTICKS)
        slider.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider.SetTickFreq(1, 1)
        self.slider = slider

        checkbox = wx.CheckBox(self, -1, _("Auto-play"))
        self.checkbox = checkbox

        in_sizer = wx.BoxSizer(wx.HORIZONTAL)
        in_sizer.Add(slider, 1, wx.GROW|wx.EXPAND)
        in_sizer.Add(checkbox, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel, 20, wx.GROW|wx.EXPAND)
        sizer.Add(in_sizer, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def __bind_evt_gui(self):
        self.slider.Bind(wx.EVT_SLIDER, self.OnSlider)
        self.checkbox.Bind(wx.EVT_CHECKBOX, self.OnCheckBox)

    def __bind_pubsub(self):
        Publisher.subscribe(self.ShowBitmapByPosition, 'Set bitmap in preview panel')

    def ShowBitmapByPosition(self, evt):
        pos = evt.data 
        self.ShowSlice(pos)


    def OnSlider(self, evt):
        pos = evt.GetInt()
        self.ShowSlice(pos)
        evt.Skip()

    def OnCheckBox(self, evt):
        self.ischecked = evt.IsChecked()
        if evt.IsChecked():
            wx.CallAfter(self.OnRun)
        evt.Skip()

    def OnRun(self):
        pos = self.slider.GetValue()
        pos += 1
        if not (self.nimages- pos):
            pos = 0
        self.slider.SetValue(pos)
        self.ShowSlice(pos)
        time.sleep(0.2)
        if self.ischecked:
            try:
                wx.Yield()
            #TODO: temporary fix necessary in the Windows XP 64 Bits
            #BUG in wxWidgets http://trac.wxwidgets.org/ticket/10896
            except(wx._core.PyAssertionError):
                utils.debug("wx._core.PyAssertionError")
            finally:
                wx.CallAfter(self.OnRun)

    def SetBitmapFiles(self, data):
        #self.dicom_list = group.GetHandSortedList()
        self.bitmap_list = data
        self.current_index = 0
        self.nimages = len(data)
        # GUI
        self.slider.SetMax(self.nimages-1)
        self.slider.SetValue(0)
        self.ShowSlice()

    def ShowSlice(self, index = 0):
        bitmap = self.bitmap_list[index]

        # UPDATE GUI
        ## Text related to size
        value = STR_SIZE %(bitmap[3], bitmap[4])
        self.text_image_size.SetValue(value)

        value1 = ''
        value2 = ''

        value = "%s\n%s" %(value1, value2)
        self.text_image_location.SetValue(value)


        #self.text_patient.SetValue(value)
        self.text_patient.SetValue('')

        #self.text_acquisition.SetValue(value)
        self.text_acquisition.SetValue('')



        n_array = bitmap_reader.ReadBitmap(bitmap[0])
        
        image = converters.to_vtk(n_array, spacing=(1,1,1),\
                slice_number=1, orientation="AXIAL")


        # ADJUST CONTRAST
        window_level = n_array.max()/2
        window_width = n_array.max()
        
        colorer = vtk.vtkImageMapToWindowLevelColors()
        colorer.SetInputData(image)
        colorer.SetWindow(float(window_width))
        colorer.SetLevel(float(window_level))
        colorer.Update()

        if self.actor is None:
            self.actor = vtk.vtkImageActor()
            self.renderer.AddActor(self.actor)

        # PLOT IMAGE INTO VIEWER
        self.actor.SetInputData(colorer.GetOutput())
        self.renderer.ResetCamera()
        self.interactor.Render()

        # Setting slider position
        self.slider.SetValue(index)


#class BitmapPreviewSlice(wx.Panel):
#    def __init__(self, parent):
#        super(BitmapPreviewSlice, self).__init__(parent)
#        # TODO: 3 pixels between the previews is a good idea?
#        # I have to test.
#        self.displayed_position = 0
#        self.nhidden_last_display = 0
#        self.selected_dicom = None
#        self.selected_panel = None
#        self.first_selection = None
#        self.last_selection = None
#        self._init_ui()
#
#    def _init_ui(self):
#        scroll = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
#        self.scroll = scroll
#
#        self.grid = wx.GridSizer(rows=NROWS, cols=NCOLS, vgap=3, hgap=3)
#
#        sizer = wx.BoxSizer(wx.HORIZONTAL)
#        sizer.AddSizer(self.grid, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)
#
#        background_sizer = wx.BoxSizer(wx.HORIZONTAL)
#        background_sizer.AddSizer(sizer, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)
#        background_sizer.Add(scroll, 0, wx.EXPAND|wx.GROW)
#        self.SetSizer(background_sizer)
#        background_sizer.Fit(self)
#
#        self.Layout()
#        self.Update()
#        self.SetAutoLayout(1)
#
#        self.sizer = background_sizer
#
#        self._Add_Panels_Preview()
#        self._bind_events()
#
#    def _Add_Panels_Preview(self):
#        self.previews = []
#        for i in xrange(NROWS):
#            for j in xrange(NCOLS):
#                p = Preview(self)
#                p.Bind(EVT_PREVIEW_CLICK, self.OnPreviewClick)
#                #p.Hide()
#                self.previews.append(p)
#                self.grid.Add(p, 1, flag=wx.EXPAND)
#
#    def _bind_events(self):
#        # When the user scrolls the window
#        self.Bind(wx.EVT_SCROLL, self.OnScroll)
#        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
#
#    def SetDicomDirectory(self, directory):
#        utils.debug("Setting Dicom Directory %s" % directory)
#        self.directory = directory
#        self.series = dicom_reader.GetSeries(directory)[0]
#
#    def SetPatientGroups(self, patient):
#        self.group_list = patient.GetGroups()
#
#
#    #def SetDicomSerie(self, pos):
#    #    self.files = []
#    #    self.displayed_position = 0
#    #    self.nhidden_last_display = 0
#    #    group = self.group_list[pos]
#    #    self.group = group
#    #    #dicom_files = group.GetList()
#    #    dicom_files = group.GetHandSortedList()
#    #    n = 0
#    #    for dicom in dicom_files:
#    #        info = BitmapInfo(n, dicom,
#    #                         _("Image %d") % (dicom.image.number),
#    #                         "%.2f" % (dicom.image.position[2]))
#    #        self.files.append(info)
#    #        n+=1
#
#    #    scroll_range = len(self.files)/NCOLS
#    #    if scroll_range * NCOLS < len(self.files):
#    #        scroll_range +=1
#    #    self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
#    
#    #    self._display_previews()
#
#    #def SetDicomGroup(self, group):
#    #    self.files = []
#    #    self.displayed_position = 0
#    #    self.nhidden_last_display = 0
#    #    #dicom_files = group.GetList()
#    #    dicom_files = group.GetHandSortedList()
#    #    n = 0
#    #    for dicom in dicom_files:
#    #        info = BitmapInfo(n, dicom,
#    #                         _("Image %d") % (dicom.image.number),
#    #                         "%.2f" % (dicom.image.position[2]),
#    #                        )
#    #        self.files.append(info)
#    #        n+=1
#
#    #    scroll_range = len(self.files)/NCOLS
#    #    if scroll_range * NCOLS < len(self.files):
#    #        scroll_range +=1
#    #    self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
#
#    #    self._display_previews()
#
#    #def SetDicomGroup(self, group):
#    #    self.files = []
#    #    self.displayed_position = 0
#    #    self.nhidden_last_display = 0
#    #    #dicom_files = group.GetList()
#    #    dicom_files = group.GetHandSortedList()
#    #    n = 0
#    #    for dicom in dicom_files:
#    #        info = BitmapInfo(n, dicom,
#    #                         _("Image %d") % (dicom.image.number),
#    #                         "%.2f" % (dicom.image.position[2]),
#    #                        )
#    #        self.files.append(info)
#    #        n+=1
#
#    #    scroll_range = len(self.files)/NCOLS
#    #    if scroll_range * NCOLS < len(self.files):
#    #        scroll_range +=1
#    #    self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
#
#    #    self._display_previews()
#
#
#    def _display_previews(self):
#        initial = self.displayed_position * NCOLS
#        final = initial + NUM_PREVIEWS
#        if len(self.files) < final:
#            for i in xrange(final-len(self.files)):
#                try:
#                    self.previews[-i-1].Hide()
#                except IndexError:
#                    utils.debug("doesn't exist!")
#            self.nhidden_last_display = final-len(self.files)
#        else:
#            if self.nhidden_last_display:
#                for i in xrange(self.nhidden_last_display):
#                    try:
#                        self.previews[-i-1].Show()
#                    except IndexError:
#                        utils.debug("doesn't exist!")
#                self.nhidden_last_display = 0
#
#        for f, p in zip(self.files[initial:final], self.previews):
#            p.SetBitmapToPreview(f)
#            if f.selected:
#                self.selected_panel = p
#            #p.interactor.Render()
#
#        for f, p in zip(self.files[initial:final], self.previews):
#            p.Show()
#
#    def OnPreviewClick(self, evt):
#
#        dicom_id = evt.GetSelectID()
#        
#        if self.first_selection is None:
#            self.first_selection = dicom_id
#
#        if self.last_selection is None:
#            self.last_selection = dicom_id  
#
#        
#        if evt.GetPressedShift():
# 
#            if dicom_id < self.first_selection and dicom_id < self.last_selection:
#                self.first_selection = dicom_id
#            else:
#                self.last_selection = dicom_id
#        else:
#            self.first_selection = dicom_id
#            self.last_selection = dicom_id
#
#            for i in xrange(len(self.files)):
#            
#                if i == dicom_id:
#                    self.files[i].selected = True
#                else:
#                    self.files[i].selected = False
#
#
#        my_evt = SerieEvent(myEVT_CLICK_SLICE, self.GetId())
#        my_evt.SetSelectedID(evt.GetSelectID())
#        my_evt.SetItemData(evt.GetItemData())
#
#        if self.selected_dicom:
#            self.selected_dicom.selected = self.selected_dicom is \
#                    evt.GetEventObject().bitmap_info
#            self.selected_panel.select_on = self.selected_panel is evt.GetEventObject()
#            
#            if self.first_selection != self.last_selection:
#                for i in xrange(len(self.files)):
#                    if i >= self.first_selection and i <= self.last_selection:
#                        self.files[i].selected = True
#                    else:
#                        self.files[i].selected = False
#
#            else:
#                self.selected_panel.Select()
#
#        self._display_previews()
#        self.selected_panel = evt.GetEventObject()
#        self.selected_dicom = self.selected_panel.bitmap_info
#        self.GetEventHandler().ProcessEvent(my_evt)
#
#        #Publisher.sendMessage("Selected Import Images", [self.first_selection, \
#        #                                                         self.last_selection])  
#
#    def OnScroll(self, evt=None):
#        if evt:
#            if self.displayed_position != evt.GetPosition():
#                self.displayed_position = evt.GetPosition()
#        else:
#            if self.displayed_position != self.scroll.GetThumbPosition():
#                self.displayed_position = self.scroll.GetThumbPosition()
#        self._display_previews()
#
#    def OnWheel(self, evt):
#        d = evt.GetWheelDelta() / evt.GetWheelRotation()
#        self.scroll.SetThumbPosition(self.scroll.GetThumbPosition() - d)
#        self.OnScroll()


