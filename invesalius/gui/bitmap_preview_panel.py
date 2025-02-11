import time

import numpy
import wx
from vtkmodules.vtkImagingColor import vtkImageMapToWindowLevelColors
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleImage
from vtkmodules.vtkRenderingCore import vtkImageActor, vtkRenderer
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

import invesalius.constants as const
import invesalius.data.converters as converters
import invesalius.data.vtk_utils as vtku
import invesalius.reader.bitmap_reader as bitmap_reader
import invesalius.utils as utils
from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

NROWS = 3
NCOLS = 6
NUM_PREVIEWS = NCOLS * NROWS
PREVIEW_WIDTH = 70
PREVIEW_HEIGTH = 70

PREVIEW_BACKGROUND = (255, 255, 255)  # White

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
    def __init__(self, evtType, id):
        super().__init__(evtType, id)

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
    def __init__(self, evtType, id):
        super().__init__(evtType, id)


class BitmapInfo:
    """
    Keep the informations and the image used by preview.
    """

    def __init__(self, data):
        # self.id = id
        self.id = data[7]
        self.title = data[6]
        self.data = data
        self.pos = data[8]
        self._preview = None
        self.selected = False
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
        super().__init__(parent)
        self._bind_events()
        self.image = None
        self.last_size = (10, 10)

    def _bind_events(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def _build_bitmap(self, image):
        bmp = wx.Bitmap(image)
        return bmp

    def _image_resize(self, image):
        self.Update()
        self.Layout()
        new_size = self.GetSize()
        # This is necessary due to darwin problem #
        if new_size != (0, 0):
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
        super().__init__(parent)
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
        self.sizer.Add(self.title, 0, wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.subtitle, 0, wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.image_viewer, 1, wx.ALIGN_CENTRE_HORIZONTAL | wx.SHAPED | wx.ALL, 5)
        self.sizer.Fit(self)

        self.SetSizer(self.sizer)

        self.Layout()
        self.Update()
        self.Fit()
        self.SetAutoLayout(1)

    def _bind_events(self):
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnDClick)
        self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)

        self.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.title.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.subtitle.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.image_viewer.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)

    def SetBitmapToPreview(self, bitmap_info):
        if self.bitmap_info:
            self.bitmap_info.release_thumbnail()

        self.bitmap_info = bitmap_info
        self.SetTitle(self.bitmap_info.title[-10:])
        self.SetSubtitle("")

        image = self.bitmap_info.preview

        self.image_viewer.SetImage(image)
        self.select_on = bitmap_info.selected
        self.Select()
        self.Update()

    def SetTitle(self, title):
        self.title.SetLabel(title)

    def SetSubtitle(self, subtitle):
        self.subtitle.SetLabel(subtitle)

    def OnEnter(self, evt):
        if not self.select_on:
            try:
                c = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
            except AttributeError:
                c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNFACE)
            self.SetBackgroundColour(c)

    def OnLeave(self, evt):
        if not self.select_on:
            c = PREVIEW_BACKGROUND
            self.SetBackgroundColour(c)

    def OnSelect(self, evt):
        shift_pressed = False
        if evt.shiftDown:
            shift_pressed = True

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

        Publisher.sendMessage("Set bitmap in preview panel", pos=self.bitmap_info.pos)

        evt.Skip()

    def OnSize(self, evt):
        if self.bitmap_info:
            self.SetBitmapToPreview(self.bitmap_info)
        evt.Skip()

    def Select(self, on=True):
        if self.select_on:
            try:
                c = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            except AttributeError:
                c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        else:
            c = PREVIEW_BACKGROUND
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
        super().__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
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
        sizer.Add(self.grid, 1, wx.EXPAND | wx.GROW | wx.ALL, 2)

        background_sizer = wx.BoxSizer(wx.HORIZONTAL)
        background_sizer.Add(sizer, 1, wx.EXPAND | wx.GROW | wx.ALL, 2)
        background_sizer.Add(scroll, 0, wx.EXPAND | wx.GROW)
        self.SetSizer(background_sizer)
        background_sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = background_sizer

        self._Add_Panels_Preview()
        self._bind_events()
        self._bind_pub_sub_events()

    def _Add_Panels_Preview(self):
        self.previews = []
        for i in range(NROWS):
            for j in range(NCOLS):
                p = Preview(self)
                p.Bind(EVT_PREVIEW_CLICK, self.OnSelect)

                self.previews.append(p)
                self.grid.Add(p, 1, flag=wx.EXPAND)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)

    def _bind_pub_sub_events(self):
        Publisher.subscribe(self.RemovePanel, "Remove preview panel")

    def OnSelect(self, evt):
        my_evt = SerieEvent(myEVT_CLICK_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())

        if self.selected_dicom:
            self.selected_dicom.selected = self.selected_dicom is evt.GetEventObject().bitmap_info
            self.selected_panel.select_on = self.selected_panel is evt.GetEventObject()
            self.selected_panel.Select()
        self.selected_panel = evt.GetEventObject()
        self.selected_dicom = self.selected_panel.bitmap_info
        self.GetEventHandler().ProcessEvent(my_evt)
        evt.Skip()

    def SetBitmapFiles(self, data):
        self.files = []

        bitmap = bitmap_reader.BitmapData()
        bitmap.SetData(data)

        pos = 0
        for d in data:
            d.append(pos)
            info = BitmapInfo(d)
            self.files.append(info)
            pos += 1

        scroll_range = len(self.files) // NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range += 1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
        self._display_previews()

    def RemovePanel(self, data):
        for p, f in zip(self.previews, self.files):
            if p.bitmap_info is not None:
                if data in p.bitmap_info.data[0]:
                    self.files.remove(f)
                    p.Hide()
                    self._display_previews()
                    Publisher.sendMessage(
                        "Update max of slidebar in single preview image", max_value=len(self.files)
                    )

                    self.Update()
                    self.Layout()

        for n, p in enumerate(self.previews):
            if p.bitmap_info is not None:
                if p.IsShown():
                    p.bitmap_info.pos = n

    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + NUM_PREVIEWS
        if len(self.files) < final:
            for i in range(final - len(self.files)):
                try:
                    self.previews[-i - 1].Hide()
                except IndexError:
                    utils.debug("doesn't exist!")
                    pass
            self.nhidden_last_display = final - len(self.files)
        else:
            if self.nhidden_last_display:
                for i in range(self.nhidden_last_display):
                    try:
                        self.previews[-i - 1].Show()
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
        d = evt.GetWheelDelta() // evt.GetWheelRotation()
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
        text_image_size = vtku.TextZero()
        text_image_size.SetPosition(const.TEXT_POS_LEFT_UP)
        text_image_size.SetValue("")
        text_image_size.SetSymbolicSize(wx.FONTSIZE_SMALL)
        self.text_image_size = text_image_size

        text_image_location = vtku.TextZero()
        #  text_image_location.SetVerticalJustificationToBottom()
        text_image_location.SetPosition(const.TEXT_POS_LEFT_DOWN)
        text_image_location.SetValue("")
        text_image_location.bottom_pos = True
        text_image_location.SetSymbolicSize(wx.FONTSIZE_SMALL)
        self.text_image_location = text_image_location

        text_patient = vtku.TextZero()
        #  text_patient.SetJustificationToRight()
        text_patient.SetPosition(const.TEXT_POS_RIGHT_UP)
        text_patient.SetValue("")
        text_patient.right_pos = True
        text_patient.SetSymbolicSize(wx.FONTSIZE_SMALL)
        self.text_patient = text_patient

        text_acquisition = vtku.TextZero()
        #  text_acquisition.SetJustificationToRight()
        #  text_acquisition.SetVerticalJustificationToBottom()
        text_acquisition.SetPosition(const.TEXT_POS_RIGHT_DOWN)
        text_acquisition.SetValue("")
        text_acquisition.right_pos = True
        text_acquisition.bottom_pos = True
        text_acquisition.SetSymbolicSize(wx.FONTSIZE_SMALL)
        self.text_acquisition = text_acquisition

        self.renderer = vtkRenderer()
        self.renderer.SetLayer(0)

        cam = self.renderer.GetActiveCamera()

        self.canvas_renderer = vtkRenderer()
        self.canvas_renderer.SetLayer(1)
        self.canvas_renderer.SetActiveCamera(cam)
        self.canvas_renderer.SetInteractive(0)
        self.canvas_renderer.PreserveDepthBufferOn()

        style = vtkInteractorStyleImage()

        self.interactor = wxVTKRenderWindowInteractor(self.panel, -1, size=wx.Size(340, 340))
        self.interactor.SetRenderWhenDisabled(True)
        self.interactor.GetRenderWindow().SetNumberOfLayers(2)
        self.interactor.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor.GetRenderWindow().AddRenderer(self.canvas_renderer)
        self.interactor.SetInteractorStyle(style)
        self.interactor.Render()

        self.canvas = CanvasRendererCTX(self, self.renderer, self.canvas_renderer)
        self.canvas.draw_list.append(self.text_image_size)
        self.canvas.draw_list.append(self.text_image_location)
        self.canvas.draw_list.append(self.text_patient)
        self.canvas.draw_list.append(self.text_acquisition)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.interactor, 1, wx.GROW | wx.EXPAND)
        sizer.Fit(self.panel)
        self.panel.SetSizer(sizer)
        self.Layout()
        self.Update()

    def __init_gui(self):
        self.panel = wx.Panel(self, -1)

        slider = wx.Slider(
            self, id=-1, value=0, minValue=0, maxValue=99, style=wx.SL_HORIZONTAL | wx.SL_AUTOTICKS
        )
        slider.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider.SetTickFreq(1)
        self.slider = slider

        checkbox = wx.CheckBox(self, -1, _("Auto-play"))
        self.checkbox = checkbox

        in_sizer = wx.BoxSizer(wx.HORIZONTAL)
        in_sizer.Add(slider, 1, wx.GROW | wx.EXPAND)
        in_sizer.Add(checkbox, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel, 20, wx.GROW | wx.EXPAND)
        sizer.Add(in_sizer, 1, wx.GROW | wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def __bind_evt_gui(self):
        self.slider.Bind(wx.EVT_SLIDER, self.OnSlider)
        self.checkbox.Bind(wx.EVT_CHECKBOX, self.OnCheckBox)

    def __bind_pubsub(self):
        Publisher.subscribe(self.ShowBitmapByPosition, "Set bitmap in preview panel")
        Publisher.subscribe(
            self.UpdateMaxValueSliderBar, "Update max of slidebar in single preview image"
        )
        Publisher.subscribe(self.ShowBlackSlice, "Show black slice in single preview image")

    def ShowBitmapByPosition(self, pos):
        if pos is not None:
            self.ShowSlice(int(pos))

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
        if not (self.nimages - pos):
            pos = 0
        self.slider.SetValue(pos)
        self.ShowSlice(pos)
        time.sleep(0.2)
        if self.ischecked:
            try:
                wx.Yield()
            # TODO: temporary fix necessary in the Windows XP 64 Bits
            # BUG in wxWidgets http://trac.wxwidgets.org/ticket/10896
            except wx.PyAssertionError:
                utils.debug("wx._core.PyAssertionError")
            finally:
                wx.CallAfter(self.OnRun)

    def SetBitmapFiles(self, data):
        # self.dicom_list = group.GetHandSortedList()
        self.bitmap_list = data
        self.current_index = 0
        self.nimages = len(data)
        # GUI
        self.slider.SetMax(self.nimages - 1)
        self.slider.SetValue(0)
        self.ShowSlice()

    def UpdateMaxValueSliderBar(self, max_value):
        self.slider.SetMax(max_value - 1)
        self.slider.Refresh()
        self.slider.Update()

    def ShowBlackSlice(self, pub_sub):
        n_array = numpy.zeros((100, 100))

        self.text_image_size.SetValue("")

        image = converters.to_vtk(n_array, spacing=(1, 1, 1), slice_number=1, orientation="AXIAL")

        colorer = vtkImageMapToWindowLevelColors()
        colorer.SetInputData(image)
        colorer.Update()

        if self.actor is None:
            self.actor = vtkImageActor()
            self.renderer.AddActor(self.actor)

        # PLOT IMAGE INTO VIEWER
        self.actor.SetInputData(colorer.GetOutput())
        self.renderer.ResetCamera()
        self.interactor.Render()

        # Setting slider position
        self.slider.SetValue(0)

    def ShowSlice(self, index=0):
        bitmap = self.bitmap_list[index]

        # UPDATE GUI
        ## Text related to size
        value = STR_SIZE % (bitmap[3], bitmap[4])
        self.text_image_size.SetValue(value)

        value1 = ""
        value2 = ""

        value = f"{value1}\n{value2}"
        self.text_image_location.SetValue(value)

        # self.text_patient.SetValue(value)
        self.text_patient.SetValue("")

        # self.text_acquisition.SetValue(value)
        self.text_acquisition.SetValue("")

        n_array = bitmap_reader.ReadBitmap(bitmap[0])

        image = converters.to_vtk(n_array, spacing=(1, 1, 1), slice_number=1, orientation="AXIAL")

        # ADJUST CONTRAST
        window_level = n_array.max() / 2
        window_width = n_array.max()

        colorer = vtkImageMapToWindowLevelColors()
        colorer.SetInputData(image)
        colorer.SetWindow(float(window_width))
        colorer.SetLevel(float(window_level))
        colorer.Update()

        if self.actor is None:
            self.actor = vtkImageActor()
            self.renderer.AddActor(self.actor)

        # PLOT IMAGE INTO VIEWER
        self.actor.SetInputData(colorer.GetOutput())
        self.renderer.ResetCamera()
        self.interactor.Render()

        # Setting slider position
        self.slider.SetValue(index)
