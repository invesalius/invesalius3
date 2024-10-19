# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------

# -*- coding: UTF-8 -*-

# TODO: To create a beautiful API
import sys
import time

import wx
from vtkmodules.vtkImagingColor import vtkImageMapToWindowLevelColors
from vtkmodules.vtkImagingCore import vtkImageFlip
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleImage
from vtkmodules.vtkIOImage import vtkPNGReader
from vtkmodules.vtkRenderingCore import vtkImageActor, vtkRenderer
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

import invesalius.constants as const
import invesalius.data.vtk_utils as vtku
import invesalius.reader.dicom_reader as dicom_reader
import invesalius.utils as utils
from invesalius.data import converters, imagedata_utils
from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

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


class DicomInfo:
    """
    Keep the informations and the image used by preview.
    """

    def __init__(self, id, dicom, title, subtitle, n=0):
        self.id = id
        self.dicom = dicom
        self.title = title
        self.subtitle = subtitle
        self._preview = None
        self.selected = False
        self.filename = ""
        self._slice = n

    @property
    def preview(self):
        if not self._preview:
            if isinstance(self.dicom.image.thumbnail_path, list):
                bmp = wx.Bitmap(self.dicom.image.thumbnail_path[self._slice], wx.BITMAP_TYPE_PNG)
            else:
                bmp = wx.Bitmap(self.dicom.image.thumbnail_path, wx.BITMAP_TYPE_PNG)
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
        self.dicom_info = None
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
        # self.interactor.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        # self.panel.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        # self.title.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)
        # self.subtitle.Bind( wx.EVT_LEFT_DCLICK, self.OnDClick)

        self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        # self.interactor.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        # self.panel.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        # self.title.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        # self.subtitle.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)

        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        # self.interactor.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        # self.panel.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        # self.title.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
        # self.subtitle.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)

        self.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.title.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.subtitle.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        self.image_viewer.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)

        # self.Bind(wx.EVT_SIZE, self.OnSize)

    def SetDicomToPreview(self, dicom_info):
        """
        Set a dicom to preview.
        """
        if self.dicom_info:
            self.dicom_info.release_thumbnail()

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

    def SetTitle(self, title):
        self.title.SetLabel(title)

    def SetSubtitle(self, subtitle):
        self.subtitle.SetLabel(subtitle)

    def OnEnter(self, evt):
        if not self.select_on:
            # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHILIGHT)
            c = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)

            self.SetBackgroundColour(c)

    def OnLeave(self, evt):
        if not self.select_on:
            c = PREVIEW_BACKGROUND
            self.SetBackgroundColour(c)

    def OnSelect(self, evt):
        shift_pressed = False
        if evt.shiftDown:
            shift_pressed = True

        # dicom_id = self.dicom_info.id
        self.select_on = True
        self.dicom_info.selected = True
        ##c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNHIGHLIGHT)
        ##c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HOTLIGHT)
        # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        ##c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_GRADIENTACTIVECAPTION)
        # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNSHADOW)
        # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_ACTIVEBORDER)
        # *c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DLIGHT)
        # *c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHILIGHT)
        # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHIGHLIGHT)
        # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DDKSHADOW)
        # c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DSHADOW)
        # self.SetBackgroundColour(c)
        self.Select()

        # Generating a EVT_PREVIEW_CLICK event
        my_evt = SerieEvent(myEVT_PREVIEW_CLICK, self.GetId())
        my_evt.SetSelectedID(self.dicom_info.id)
        my_evt.SetItemData(self.dicom_info.dicom)
        my_evt.SetShiftStatus(shift_pressed)
        my_evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(my_evt)
        evt.Skip()

    def OnSize(self, evt):
        if self.dicom_info:
            self.SetDicomToPreview(self.dicom_info)
        evt.Skip()

    def Select(self, on=True):
        if self.select_on:
            try:
                c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            except AttributeError:
                c = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        else:
            c = PREVIEW_BACKGROUND
        self.SetBackgroundColour(c)
        self.Refresh()

    def OnDClick(self, evt):
        my_evt = SerieEvent(myEVT_PREVIEW_DBLCLICK, self.GetId())
        my_evt.SetSelectedID(self.dicom_info.id)
        my_evt.SetItemData(self.dicom_info.dicom)
        my_evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(my_evt)


class DicomPreviewSeries(wx.Panel):
    """A dicom series preview panel"""

    def __init__(self, parent):
        super().__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        # self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        # self.SetSizer(self.sizer)
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

    def _Add_Panels_Preview(self):
        self.previews = []
        for i in range(NROWS):
            for j in range(NCOLS):
                p = Preview(self)
                p.Bind(EVT_PREVIEW_CLICK, self.OnSelect)
                # if (i == j == 0):
                # self._show_shadow(p)
                # p.Hide()
                self.previews.append(p)
                self.grid.Add(p, 1, flag=wx.EXPAND)

    # def _show_shadow(self, preview):
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
            self.selected_dicom.selected = self.selected_dicom is evt.GetEventObject().dicom_info
            self.selected_panel.select_on = self.selected_panel is evt.GetEventObject()
            self.selected_panel.Select()
        self.selected_panel = evt.GetEventObject()
        self.selected_dicom = self.selected_panel.dicom_info
        self.GetEventHandler().ProcessEvent(my_evt)

    def SetPatientGroups(self, patient):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
        group_list = patient.GetGroups()
        self.group_list = group_list
        n = 0
        for group in group_list:
            info = DicomInfo(
                (group.dicom.patient.id, group.dicom.acquisition.serie_number),
                group.dicom,
                group.title,
                _("%d images") % (group.nslices),
            )
            self.files.append(info)
            n += 1

        scroll_range = len(self.files) // NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range += 1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
        self._display_previews()

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
            p.SetDicomToPreview(f)
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


class DicomPreviewSlice(wx.Panel):
    """A dicom preview panel"""

    def __init__(self, parent):
        super().__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        self.displayed_position = 0
        self.nhidden_last_display = 0
        self.selected_dicom = None
        self.selected_panel = None
        self.first_selection = None
        self.last_selection = None
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

    def _Add_Panels_Preview(self):
        self.previews = []
        for i in range(NROWS):
            for j in range(NCOLS):
                p = Preview(self)
                p.Bind(EVT_PREVIEW_CLICK, self.OnPreviewClick)
                # p.Hide()
                self.previews.append(p)
                self.grid.Add(p, 1, flag=wx.EXPAND)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)

    def SetDicomDirectory(self, directory):
        utils.debug(f"Setting Dicom Directory {directory}")
        self.directory = directory
        self.series = dicom_reader.GetSeries(directory)[0]

    def SetPatientGroups(self, patient):
        self.group_list = patient.GetGroups()

    def SetDicomSerie(self, pos):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
        group = self.group_list[pos]
        self.group = group
        # dicom_files = group.GetList()
        dicom_files = group.GetHandSortedList()
        n = 0
        for dicom in dicom_files:
            if isinstance(dicom.image.thumbnail_path, list):
                _slice = 0
                for thumbnail in dicom.image.thumbnail_path:
                    print(thumbnail)
                    info = DicomInfo(
                        n, dicom, _("Image %d") % (n), f"{dicom.image.position[2]:.2f}", _slice
                    )
                    self.files.append(info)
                    n += 1
                    _slice += 1
            else:
                info = DicomInfo(
                    n,
                    dicom,
                    _("Image %d") % (dicom.image.number),
                    f"{dicom.image.position[2]:.2f}",
                )
                self.files.append(info)
                n += 1

        scroll_range = len(self.files) / NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range += 1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)

        self._display_previews()

    def SetDicomGroup(self, group):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
        # dicom_files = group.GetList()
        dicom_files = group.GetHandSortedList()
        n = 0
        for dicom in dicom_files:
            if isinstance(dicom.image.thumbnail_path, list):
                _slice = 0
                for thumbnail in dicom.image.thumbnail_path:
                    print(thumbnail)
                    info = DicomInfo(
                        n, dicom, _("Image %d") % int(n), f"{dicom.image.position[2]:.2f}", _slice
                    )
                    self.files.append(info)
                    n += 1
                    _slice += 1
            else:
                info = DicomInfo(
                    n,
                    dicom,
                    _("Image %d") % int(dicom.image.number),
                    f"{dicom.image.position[2]:.2f}",
                )
                self.files.append(info)
                n += 1

        scroll_range = len(self.files) // NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range += 1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)

        self._display_previews()

    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + NUM_PREVIEWS
        if len(self.files) < final:
            for i in range(final - len(self.files)):
                try:
                    self.previews[-i - 1].Hide()
                except IndexError:
                    utils.debug("doesn't exist!")
            self.nhidden_last_display = final - len(self.files)
        else:
            if self.nhidden_last_display:
                for i in range(self.nhidden_last_display):
                    try:
                        self.previews[-i - 1].Show()
                    except IndexError:
                        utils.debug("doesn't exist!")
                self.nhidden_last_display = 0

        for f, p in zip(self.files[initial:final], self.previews):
            p.SetDicomToPreview(f)
            if f.selected:
                self.selected_panel = p
            # p.interactor.Render()

        for f, p in zip(self.files[initial:final], self.previews):
            p.Show()

    def OnPreviewClick(self, evt):
        dicom_id = evt.GetSelectID()

        if self.first_selection is None:
            self.first_selection = dicom_id

        if self.last_selection is None:
            self.last_selection = dicom_id

        if evt.GetPressedShift():
            if dicom_id < self.first_selection and dicom_id < self.last_selection:
                self.first_selection = dicom_id
            else:
                self.last_selection = dicom_id
        else:
            self.first_selection = dicom_id
            self.last_selection = dicom_id

            for i in range(len(self.files)):
                if i == dicom_id:
                    self.files[i].selected = True
                else:
                    self.files[i].selected = False

        my_evt = SerieEvent(myEVT_CLICK_SLICE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())

        if self.selected_dicom:
            self.selected_dicom.selected = self.selected_dicom is evt.GetEventObject().dicom_info
            self.selected_panel.select_on = self.selected_panel is evt.GetEventObject()

            if self.first_selection != self.last_selection:
                for i in range(len(self.files)):
                    if i >= self.first_selection and i <= self.last_selection:
                        self.files[i].selected = True
                    else:
                        self.files[i].selected = False

            else:
                self.selected_panel.Select()

        self._display_previews()
        self.selected_panel = evt.GetEventObject()
        self.selected_dicom = self.selected_panel.dicom_info
        self.GetEventHandler().ProcessEvent(my_evt)

        Publisher.sendMessage(
            "Selected Import Images", selection=(self.first_selection, self.last_selection)
        )

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
        self.__bind_evt_gui()
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

    def __init_gui(self):
        slider = wx.Slider(
            self, id=-1, value=0, minValue=0, maxValue=99, style=wx.SL_HORIZONTAL | wx.SL_AUTOTICKS
        )
        slider.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider.SetTickFreq(1)
        self.slider = slider

        checkbox = wx.CheckBox(self, -1, _("Auto-play"))
        self.checkbox = checkbox

        self.interactor = wxVTKRenderWindowInteractor(self, -1)
        self.interactor.SetRenderWhenDisabled(True)

        in_sizer = wx.BoxSizer(wx.HORIZONTAL)
        in_sizer.Add(slider, 1, wx.GROW | wx.EXPAND)
        in_sizer.Add(checkbox, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.interactor, 1, wx.GROW | wx.EXPAND)
        sizer.Add(in_sizer, 0, wx.GROW | wx.EXPAND)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def __bind_evt_gui(self):
        self.slider.Bind(wx.EVT_SLIDER, self.OnSlider)
        self.checkbox.Bind(wx.EVT_CHECKBOX, self.OnCheckBox)

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

    def SetDicomGroup(self, group):
        self.dicom_list = group.GetHandSortedList()
        self.current_index = 0
        if len(self.dicom_list) > 1:
            self.nimages = len(self.dicom_list)
        else:
            self.nimages = self.dicom_list[0].image.number_of_frames
        # GUI
        self.slider.SetMax(self.nimages - 1)
        self.slider.SetValue(0)
        self.slider.SetTickFreq(1)
        self.ShowSlice()

    def ShowSlice(self, index=0):
        try:
            dicom = self.dicom_list[index]
        except IndexError:
            dicom = self.dicom_list[0]

        if self.actor is None:
            self.__init_vtk()

        # UPDATE GUI
        ## Text related to size
        value = STR_SIZE % (dicom.image.size[0], dicom.image.size[1])
        self.text_image_size.SetValue(value)

        ## Text related to slice position
        if not (dicom.image.spacing):
            value1 = ""
        else:
            value1 = STR_SPC % (dicom.image.spacing[2])

        if dicom.image.orientation_label == "AXIAL":
            value2 = STR_LOCAL % (dicom.image.position[2])
        elif dicom.image.orientation_label == "CORONAL":
            value2 = STR_LOCAL % (dicom.image.position[1])
        elif dicom.image.orientation_label == "SAGITTAL":
            value2 = STR_LOCAL % (dicom.image.position[0])
        else:
            value2 = ""

        value = f"{value1}\n{value2}"
        self.text_image_location.SetValue(value)

        ## Text related to patient/ acquisiiton data
        value = STR_PATIENT % (dicom.patient.id, dicom.acquisition.protocol_name)
        self.text_patient.SetValue(value)

        ## Text related to acquisition date and time
        value = STR_ACQ % (dicom.acquisition.date, dicom.acquisition.time)
        self.text_acquisition.SetValue(value)

        if isinstance(dicom.image.thumbnail_path, list):
            reader = vtkPNGReader()
            if _has_win32api:
                reader.SetFileName(
                    win32api.GetShortPathName(dicom.image.thumbnail_path[index]).encode(
                        const.FS_ENCODE
                    )
                )
            else:
                reader.SetFileName(dicom.image.thumbnail_path[index])
            reader.Update()

            image = reader.GetOutput()
        else:
            filename = dicom.image.file
            if _has_win32api:
                filename = win32api.GetShortPathName(filename).encode(const.FS_ENCODE)

            np_image = imagedata_utils.read_dcm_slice_as_np2(filename)
            vtk_image = converters.to_vtk(np_image, dicom.image.spacing, 0, "AXIAL")

            # ADJUST CONTRAST
            window_level = dicom.image.level
            window_width = dicom.image.window
            colorer = vtkImageMapToWindowLevelColors()
            colorer.SetInputData(vtk_image)
            colorer.SetWindow(float(window_width))
            colorer.SetLevel(float(window_level))
            colorer.Update()

            image = colorer.GetOutput()

        flip = vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()

        if self.actor is None:
            self.actor = vtkImageActor()
            self.renderer.AddActor(self.actor)

        self.canvas.modified = True

        # PLOT IMAGE INTO VIEWER
        self.actor.SetInputData(flip.GetOutput())
        self.renderer.ResetCamera()
        self.interactor.Render()

        # Setting slider position
        self.slider.SetValue(index)
