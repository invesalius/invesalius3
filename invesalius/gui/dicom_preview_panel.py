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

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

#TODO: To create a beautiful API
import time

import wx
import vtk

from vtk.util import  numpy_support
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

import constants as const
from reader import dicom_reader
import data.vtk_utils as vtku

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

class DicomInfo(object):
    """
    Keep the informations and the image used by preview.
    """
    def __init__(self, id, dicom, title, subtitle):
        self.id = id
        self.dicom = dicom
        self.title = title
        self.subtitle = subtitle
        self._preview = None
    
    @property
    def preview(self):
        if self._preview:
            return self._preview
        else:
            colorer = vtk.vtkImageMapToWindowLevelColors()
            colorer.SetInput(self.dicom.image.imagedata)
            colorer.SetWindow(float(self.dicom.image.window))
            colorer.SetLevel(float(self.dicom.image.level))
            colorer.SetOutputFormatToRGB()
            colorer.Update()

            width, height, z = colorer.GetOutput().GetDimensions()

            r = colorer.GetOutput().GetPointData().GetScalars()
            ni = numpy_support.vtk_to_numpy(r)
            img = wx.ImageFromBuffer(width, height, ni)
            img = img.Rescale(PREVIEW_WIDTH, PREVIEW_HEIGTH).Mirror(False)
            self._preview = wx.BitmapFromImage(img)
            return self._preview


class Preview(wx.Panel):
    """
    The little previews.
    """
    def __init__(self, parent):
        super(Preview, self).__init__(parent, style=wx.SUNKEN_BORDER)
        # Will it be white?
        self.select_on = False
        self._init_ui()
        self._bind_events()

    def _init_ui(self):
        self.title = wx.StaticText(self, -1, _("Image"))
        self.subtitle = wx.StaticText(self, -1, _("Image"))
        self.image_viewer = wx.StaticBitmap(self, -1, size=(70, 70))

        #self.panel = wx.Panel(self, -1)

        self.SetBackgroundColour(PREVIEW_BACKGROUND)
        
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.title, 0,
                        wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.subtitle, 0,
                        wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.image_viewer, 0, wx.ALIGN_CENTER_HORIZONTAL)
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
        #self.interactor.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        #self.panel.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        #self.title.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)
        #self.subtitle.Bind(wx.EVT_LEFT_DOWN, self.OnSelect)

    def SetDicomToPreview(self, dicom_info):
        """
        Set a dicom to preview.
        """
        self.SetTitle(dicom_info.title)
        self.SetSubtitle(dicom_info.subtitle)
        self.ID = dicom_info.id
        image = dicom_info.preview
        self.image_viewer.SetBitmap(image)
        self.data = dicom_info.id
        self.Update()

    def SetTitle(self, title):
        self.title.SetLabel(title)

    def SetSubtitle(self, subtitle):
        self.subtitle.SetLabel(subtitle)

    def OnEnter(self, evt):
        if not self.select_on:
            #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHILIGHT)
            c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            self.SetBackgroundColour(c)

    def OnLeave(self, evt):
        if not self.select_on:
            c = (255,255,255)
            self.SetBackgroundColour(c)

    def OnSelect(self, evt):
        print "OnSelect"
        self.select_on = True
        ##c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNHIGHLIGHT)
        ##c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HOTLIGHT)
        #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        ##c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_GRADIENTACTIVECAPTION)
        #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_BTNSHADOW)
        #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_ACTIVEBORDER)
        #*c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DLIGHT)
        #*c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHILIGHT)
        #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DHIGHLIGHT)
        #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DDKSHADOW)
        #c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DSHADOW)
        #self.SetBackgroundColour(c)
        self.Select()

    def Select(self, on=True):
        if self.select_on:
            c = wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        else:
            c = (255,255,255)
        self.SetBackgroundColour(c)

    def OnDClick(self, evt):
        evt = PreviewEvent(myEVT_SELECT, self.GetId())
        evt.SetSelectedID(self.ID)
        evt.SetItemData(self.data)
        self.GetEventHandler().ProcessEvent(evt)

    def ShowShadow(self):
        self._nImgSize = 16
        nPadding = 4
        print "ShowShadow"
        dc = wx.BufferedPaintDC(self)
        style = self.GetParent().GetWindowStyleFlag()

        backBrush = wx.WHITE_BRUSH
        if 1: #style & INB_BORDER:
            borderPen = wx.Pen(wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DSHADOW))
        #else:
        #    borderPen = wx.TRANSPARENT_PEN

        size = self.GetSize()

        # Background
        dc.SetBrush(backBrush)

        borderPen.SetWidth(1)
        dc.SetPen(borderPen)
        dc.DrawRectangle(0, 0, size.x, size.y)
        #bUsePin = (style & INB_USE_PIN_BUTTON and [True] or [False])[0]

        borderPen = wx.BLACK_PEN
        borderPen.SetWidth(1)
        dc.SetPen(borderPen)
        dc.DrawLine(0, size.y, size.x, size.y)
        dc.DrawPoint(0, size.y)

        clientSize = 0
        #bUseYcoord = (style & INB_RIGHT or style & INB_LEFT)
        bUseYcoord = 1

        if bUseYcoord:
            clientSize = size.GetHeight()
        else:
            clientSize = size.GetWidth()

        if 1:
            # Default values for the surronounding rectangle
            # around a button
            rectWidth = self._nImgSize * 2  # To avoid the recangle to 'touch' the borders
            rectHeight = self._nImgSize * 2

            # Incase the style requires non-fixed button (fit to text)
            # recalc the rectangle width
            if 1:
            #if style & INB_FIT_BUTTON and \
            #   not ((style & INB_LEFT) or (style & INB_RIGHT)) and \
            #   not self._pagesInfoVec[i].GetCaption() == "" and \
            #   not (style & INB_SHOW_ONLY_IMAGES):


                #rectWidth = ((textWidth + nPadding * 2) > rectWidth and [nPadding * 2 + textWidth] or [rectWidth])[0]

                rectWidth = ((nPadding * 2) > rectWidth and [nPadding * 2] or [rectWidth])[0]
                # Make the width an even number
                if rectWidth % 2 != 0:
                    rectWidth += 1

            # If Pin button is used, consider its space as well (applicable for top/botton style)
            # since in the left/right, its size is already considered in 'pos'
            #pinBtnSize = (bUsePin and [20] or [0])[0]

            #if pos + rectWidth + pinBtnSize > clientSize:
            #    break

            # Calculate the button rectangle
            modRectWidth =  rectWidth - 2# or [rectWidth])[0]
            modRectHeight = rectHeight# or [rectHeight - 2])[0]

            pos = rectWidth

            if bUseYcoord:
                buttonRect = wx.Rect(1, pos, modRectWidth, modRectHeight)
            else:
                buttonRect = wx.Rect(pos , 1, modRectWidth, modRectHeight)

    def ShowShadow2(self):
        pass


class SingleImagePreview(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.__init_gui()
        self.__init_vtk()
        self.__bind_evt_gui()
        self.dicom_list = []
        self.nimages = 1
        self.current_index = 0
        self.window_width = const.WINDOW_LEVEL["Bone"][0]
        self.window_level = const.WINDOW_LEVEL["Bone"][1]

    def __init_vtk(self):
        actor = vtk.vtkImageActor()
        self.actor = actor

        text_image_size = vtku.Text()
        text_image_size.SetPosition(const.TEXT_POS_LEFT_UP)
        text_image_size.SetValue(_("image size"))
        self.text_image_size = text_image_size

        text_image_location = vtku.Text()
        text_image_location.SetVerticalJustificationToBottom()
        text_image_location.SetPosition(const.TEXT_POS_LEFT_DOWN)
        text_image_location.SetValue("localization")
        self.text_image_location = text_image_location

        value = _("id\nprotocol")
        text_patient = vtku.Text()
        text_patient.SetJustificationToRight()
        text_patient.SetPosition(const.TEXT_POS_RIGHT_UP)
        text_patient.SetValue(value)
        self.text_patient = text_patient

        value = _("date time\n Made in InVesalius")
        text_acquisition = vtku.Text()
        text_acquisition.SetJustificationToRight()
        text_acquisition.SetVerticalJustificationToBottom()
        text_acquisition.SetPosition(const.TEXT_POS_RIGHT_DOWN)
        text_acquisition.SetValue(value)
        self.text_acquisition = text_acquisition

        renderer = vtk.vtkRenderer()
        renderer.AddActor(actor)
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
                print "wx._core.PyAssertionError"
            finally:
                wx.CallAfter(self.OnRun)

    def SetDicomGroup(self, group):
        self.dicom_list = group.GetHandSortedList()
        self.current_index = 0
        self.nimages = len(self.dicom_list)
        # GUI
        self.slider.SetMax(self.nimages-1)
        print self.nimages
        self.slider.SetValue(0)
        self.ShowSlice()

    def ShowSlice(self, index = 0):
        print "ShowSlice"
        dicom = self.dicom_list[index]

        # UPDATE GUI
        ## Text related to size
        value = STR_SIZE %(dicom.image.size[0], dicom.image.size[1])
        self.text_image_size.SetValue(value)

        ## Text related to slice position
        value1 = STR_SPC %(dicom.image.spacing[2])
        value2 = STR_LOCAL %(dicom.image.position[2])
        value = "%s\n%s" %(value1, value2)
        self.text_image_location.SetValue(value)

        ## Text related to patient/ acquisiiton data
        value = STR_PATIENT %(dicom.patient.id,\
                              dicom.acquisition.protocol_name)
        self.text_patient.SetValue(value)

        ## Text related to acquisition date and time
        value = STR_ACQ % (dicom.acquisition.date,
                            dicom.acquisition.time)
        self.text_acquisition.SetValue(value)

        # READ FILE
        #filename = dicom.image.file
        #reader = vtkgdcm.vtkGDCMImageReader()
        #reader.SetFileName(filename)

        # ADJUST CONTRAST
        window_level = dicom.image.level
        window_width = dicom.image.window
        colorer = vtk.vtkImageMapToWindowLevelColors()
        colorer.SetInput(dicom.image.imagedata)
        colorer.SetWindow(float(window_width))
        colorer.SetLevel(float(window_level))

        # PLOT IMAGE INTO VIEWER
        self.actor.SetInput(colorer.GetOutput())
        self.renderer.ResetCamera()
        self.interactor.Render()

    def __del__(self):
        print "---------> morri"



myEVT_SELECT = wx.NewEventType()
# This event occurs when the user select a preview
EVT_SELECT = wx.PyEventBinder(myEVT_SELECT, 1)

myEVT_SELECT_SERIE = wx.NewEventType()
# This event occurs when the user select a preview
EVT_SELECT_SERIE = wx.PyEventBinder(myEVT_SELECT_SERIE, 1)

myEVT_CLICK = wx.NewEventType()
EVT_CLICK = wx.PyEventBinder(myEVT_CLICK, 1)

class PreviewEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id):
        wx.PyCommandEvent.__init__(self, evtType, id)

    def GetSelectID(self):
        return self.SelectedID

    def SetSelectedID(self, id):
        self.SelectedID = id

    def GetItemData(self):
        return self.data

    def SetItemData(self, data):
        self.data = data


class SerieEvent(PreviewEvent):
    def __init__(self , evtType, id):
        super(SerieEvent, self).__init__(evtType, id)



class DicomPreviewSeries(wx.Panel):
    """A dicom series preview panel"""
    def __init__(self, parent):
        super(DicomPreviewSeries, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        #self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        #self.SetSizer(self.sizer)
        self.displayed_position = 0
        self.nhidden_last_display = 0
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
        self.Bind(EVT_SELECT, self.OnSelect)

    def OnSelect(self, evt):
        my_evt = SerieEvent(myEVT_SELECT_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(self.group_list)
        self.GetEventHandler().ProcessEvent(my_evt)

    def SetPatientGroups(self, patient):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
        group_list = patient.GetGroups()
        self.group_list = group_list
        n = 0
        for group in group_list:
            #info = (group.dicom.image,
            #        float(group.dicom.image.window),
            #        float(group.dicom.image.level),
            #        group.title,
            #        _("%d Images") %(group.nslices),
            #        n,
            #        group_list,
            #        group.dicom)
            info = DicomInfo(n, group.dicom,
                             group.title,
                             _("%d Images") %(group.nslices),
                            )
            self.files.append(info)
            n+=1

        scroll_range = len(self.files)/NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
        self._display_previews()

    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + NUM_PREVIEWS

        if len(self.files) < final:
            for i in xrange(final-len(self.files)):
                try:
                    self.previews[-i-1].Hide()
                except IndexError:
                    #print "doesn't exist!"
                    pass
            self.nhidden_last_display = final-len(self.files)
        else:
            if self.nhidden_last_display:
                for i in xrange(self.nhidden_last_display):
                    try:
                        self.previews[-i-1].Show()
                    except IndexError:
                        #print "doesn't exist!"
                        pass
                self.nhidden_last_display = 0



        for f, p in zip(self.files[initial:final], self.previews):
            #print "f", f
            p.SetDicomToPreview(f)
            #p.interactor.Render()

        for f, p in zip(self.files[initial:final], self.previews):
            p.Show()


    def OnScroll(self, evt):
        if self.displayed_position != evt.GetPosition():
            self.displayed_position = evt.GetPosition()
            self._display_previews()

class DicomPreview(wx.Panel):
    """A dicom preview panel"""
    def __init__(self, parent):
        super(DicomPreview, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        self.displayed_position = 0
        self.nhidden_last_display = 0
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
                #p.Hide()
                self.previews.append(p)
                self.grid.Add(p, 1, flag=wx.EXPAND)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)

    def SetDicomDirectory(self, directory):
        print "Setting Dicom Directory", directory
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
        #dicom_files = group.GetList()
        dicom_files = group.GetHandSortedList()
        n = 0
        for dicom in dicom_files:
            info = DicomInfo(n, dicom, 
                             _("Image %d") % (dicom.image.number),
                             "%.2f" % (dicom.image.position[2]))
            self.files.append(info)
            n+=1

        scroll_range = len(self.files)/NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)

        self._display_previews()

    def SetDicomGroup(self, group):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
        #dicom_files = group.GetList()
        dicom_files = group.GetHandSortedList()
        n = 0
        for dicom in dicom_files:
            info = DicomInfo(n, dicom, 
                    _("Image %d") % (dicom.image.number),
                    "%.2f" % (dicom.image.position[2]),
                            )
            self.files.append(info)
            n+=1

        scroll_range = len(self.files)/NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)

        self._display_previews()

    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + NUM_PREVIEWS
        print "len:", len(self.files)

        if len(self.files) < final:
            for i in xrange(final-len(self.files)):
                print "hide ", i
                try:
                    self.previews[-i-1].Hide()
                except IndexError:
                    #print "doesn't exist!"
                    pass
            self.nhidden_last_display = final-len(self.files)
        else:
            if self.nhidden_last_display:
                for i in xrange(self.nhidden_last_display):
                    try:
                        self.previews[-i-1].Show()
                    except IndexError:
                        #print "doesn't exist!"
                        pass
                self.nhidden_last_display = 0

        for f, p in zip(self.files[initial:final], self.previews):
            p.SetDicomToPreview(f)
            #p.interactor.Render()

        for f, p in zip(self.files[initial:final], self.previews):
            p.Show()


    def OnScroll(self, evt):
        if self.displayed_position != evt.GetPosition():
            self.displayed_position = evt.GetPosition()
            self._display_previews()
