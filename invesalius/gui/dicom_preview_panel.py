#!/usr/bin/env python
# -*- coding: UTF-8 -*-

#TODO: To create a beautiful API
import wx
import vtk
import vtkgdcm

from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from reader import dicom_reader

myEVT_SELECT = wx.NewEventType()
# This event occurs when the user select a preview
EVT_SELECT = wx.PyEventBinder(myEVT_SELECT, 1)

myEVT_SELECT_SERIE = wx.NewEventType()
# This event occurs when the user select a preview
EVT_SELECT_SERIE = wx.PyEventBinder(myEVT_SELECT_SERIE, 1)

class PreviewEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id):
        wx.PyCommandEvent.__init__(self, evtType, id)

    def GetSelectID(self):
        return self.SelectedID

    def SetSelectedID(self, id):
        self.SelectedID = id


class SerieEvent(PreviewEvent):
    def __init__(self , evtType, id):
        super(SerieEvent, self).__init__(evtType, id)

class Preview(wx.Panel):
    """
    Where the images will be showed.
    """
    def __init__(self, parent):
        super(Preview, self).__init__(parent)
        # Will it be white?
        self.SetBackgroundColour((255, 255, 255))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)
        self._init_ui()
        self._init_vtk()
        self._bind_events()

    def _init_ui(self):
        self.title = wx.StaticText(self, -1, "Image", 
                                         style=wx.ALIGN_CENTER)

        self.subtitle = wx.StaticText(self, -1, "Image", 
                                         style=wx.ALIGN_CENTER)

        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=(70, 70))

        self.sizer.Add(self.title, 0, wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.subtitle, 0, wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.interactor, 0, wx.ALIGN_CENTER_HORIZONTAL\
                       | wx.ALL, 5)

    def _init_vtk(self):
        self.actor = vtk.vtkImageActor()

        self.render = vtk.vtkRenderer()

        self.interactor.SetInteractorStyle(None)
        self.interactor.GetRenderWindow().AddRenderer(self.render)

        self.render.AddActor(self.actor)


    def _bind_events(self):
        self.Bind( wx.EVT_LEFT_DCLICK, self.OnSelect)

    def OnSelect(self, evt):
        evt = PreviewEvent(myEVT_SELECT, self.GetId())
        evt.SetSelectedID(self.ID)
        self.GetEventHandler().ProcessEvent(evt)

    def SetTitle(self, title):
        self.title.SetLabel(title)

    def SetSubtitle(self, subtitle):
        self.subtitle.SetLabel(subtitle)

    def SetImage(self, image_file):
        """
        Set a Image to preview.
        """
        self.SetTitle(image_file[3])
        self.SetSubtitle(image_file[4])
        self.ID = image_file[5]

        image_reader = vtkgdcm.vtkGDCMImageReader()
        image_reader.SetFileName(image_file[0])
        image = image_reader.GetOutput()

        scale = image.GetScalarRange()
        
        cast = vtk.vtkImageMapToWindowLevelColors()
        #cast.SetShift(abs(scale[0]))
        #cast.SetScale(255.0/(scale[1] - scale[0]))
        #cast.ClampOverflowOn()
        cast.SetInput(image)
        #cast.SetOutputScalarTypeToUnsignedChar()
        try:
            window = float(image_file[1])
            level = float(image_file[2])
        except TypeError:
            #TODO: These values are good?
            level = 230
            window = 150
        
        cast.SetWindow(window)
        cast.SetLevel(level)
        self.actor.SetInput(cast.GetOutput())
        self.render.ResetCamera()
        #self.interactor.Render()


class DicomPreviewSeries(wx.Panel):
    """A dicom series preview panel"""
    def __init__(self, parent):
        super(DicomPreviewSeries, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.sizer)
        self.displayed_position = 0
        self.files = []
        self._init_ui()

    def _init_ui(self):
        self.scroll = wx.ScrollBar(self, style=wx.SB_VERTICAL)
        self.grid = wx.GridSizer(rows=3, cols=5, vgap=3, hgap=3)
        self.sizer.Add(self.grid)
        self.sizer.Add(self.scroll, 0, wx.EXPAND)
        self._Add_Panels_Preview()
        self._bind_events()

    def _Add_Panels_Preview(self):
        self.previews = []
        for i in xrange(3):
            for j in xrange(5):
                p = Preview(self)
                p.Hide()
                self.previews.append(p)
                self.grid.Add(p, i, j)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)
        self.Bind(EVT_SELECT, self.OnSelect)

    def OnSelect(self, evt):
        my_evt = SerieEvent(myEVT_SELECT_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        self.GetEventHandler().ProcessEvent(my_evt)

    def SetPatientGroups(self, patient):
        group_list = patient.GetGroups()
        n = 0
        for group in group_list:
            info = (group.dicom.image.file,
                    float(group.dicom.image.window),
                    float(group.dicom.image.level),
                    group.title,
                    "%d Images" %(group.nslices),
                    n)
            self.files.append(info)
            n+=1
            
        scroll_range = len(self.files)/5
        if scroll_range * 5 < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, 3, scroll_range, 5)

        self._Display_Previews()


    def SetDicomDirectoryOld(self, directory):
        import time
        a = time.time()
        self.directory = directory
        self.series = dicom_reader.GetSeries(directory)[0]
        b = time.time()
        # TODO: I need to improve this
        self.files = [(self.series[i][0][0][8], # Filename
                       self.series[i][0][0][12], # Window Level
                       self.series[i][0][0][13], # Window Width
                       "Serie %d" % (n + 1), # Title
                       "%d Images" % len(self.series[i][0]), # Subtitle
                       n) for n, i in enumerate(self.series)]

        scroll_range = len(self.files)/5
        if scroll_range * 5 < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, 3, scroll_range, 5)

        self._Display_Previews()

    def _Display_Previews(self):
        initial = self.displayed_position * 5
        final = initial + 15
        for f, p in zip(self.files[initial:final], self.previews):
            p.SetImage(f)
            p.Show()

    def OnScroll(self, evt):
        self.displayed_position = evt.GetPosition()
        [i.Hide() for i in self.previews]
        self._Display_Previews()


class DicomPreview(wx.Panel):
    """A dicom preview panel"""
    def __init__(self, parent):
        super(DicomPreview, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.sizer)
        self.displayed_position = 0
        self.files = []
        self._init_ui()

    def _init_ui(self):
        self.scroll = wx.ScrollBar(self, style=wx.SB_VERTICAL)
        self.grid = wx.GridSizer(rows=3, cols=5, vgap=3, hgap=3)
        self.sizer.Add(self.grid)
        self.sizer.Add(self.scroll, 0, wx.EXPAND)
        self._Add_Panels_Preview()
        self._bind_events()

    def _Add_Panels_Preview(self):
        self.previews = []
        for i in xrange(3):
            for j in xrange(5):
                p = Preview(self)
                p.Hide()
                self.previews.append(p)
                self.grid.Add(p, i, j)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)

    def SetDicomDirectory(self, directory):
        self.directory = directory
        self.series = dicom_reader.GetSeries(directory)[0]

    def SetPatientGroups(self, patient):
        self.group_list = patient.GetGroups()

    def SetDicomSerie(self, pos):
        group = self.group_list[pos]
        #dicom_files = group.GetList()
        dicom_files = group.GetHandSortedList()
        n = 0
        for dicom in dicom_files:
            info = (dicom.image.file,
                    dicom.image.window,
                    dicom.image.level,
                    "Image %d" % (dicom.image.number),
                    "%.2f" % (dicom.image.position[2]),
                    n)
            self.files.append(info)
            n+=1

        scroll_range = len(self.files)/5
        if scroll_range * 5 < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, 3, scroll_range, 5)
        self._Display_Previews()

    def SetDicomSerieOld(self, serie):
        k = self.series.keys()[serie]
        self.files = [(i[8],
                       i[12],
                       i[13],
                       "Serie %d" % (n + 1), # Title
                       "%d Images" % n, # Subtitle
                      n)for n, i in enumerate(self.series[k][0])]
        scroll_range = len(self.files)/5
        if scroll_range * 5 < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, 3, scroll_range, 5)
        self._Display_Previews()

    def _Display_Previews(self):
        initial = self.displayed_position * 5
        final = initial + 15
        for f, p in zip(self.files[initial:final], self.previews):
            p.SetImage(f)
            p.Show()

    def OnScroll(self, evt):
        self.displayed_position = evt.GetPosition()
        [i.Hide() for i in self.previews]
        self._Display_Previews()
        self.Update()
        self.Update()

