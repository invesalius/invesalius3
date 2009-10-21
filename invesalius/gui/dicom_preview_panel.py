#!/usr/bin/env python
# -*- coding: UTF-8 -*-

#TODO: To create a beautiful API
import wx
import vtk
import vtkgdcm

import wx.lib.agw.buttonpanel as bp
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from reader import dicom_reader



NROWS = 3
NCOLS = 6
MAX_VALUE = NCOLS*NROWS


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

#class Preview(wx.Panel):
    """
    Where the images will be showed.
    """
    def __init__(self, parent):
        super(Preview, self).__init__(parent)
        # Will it be white?
        self.SetBackgroundColour((255, 255, 255))
        self._init_ui()
        self._init_vtk()
        self._bind_events()

    def _init_ui(self):

        self.title = wx.StaticText(self, -1, "Image", 
                                         style=wx.ALIGN_CENTER)

        self.subtitle = wx.StaticText(self, -1, "Image", 
                                         style=wx.ALIGN_CENTER)

        self.panel = wx.Panel(self, -1)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.AddSpacer(2)
        self.sizer.Add(self.title, 1,
                        wx.GROW|wx.EXPAND|wx. ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.subtitle, 1,
                        wx.GROW|wx.EXPAND|wx.ALIGN_CENTER_HORIZONTAL)
        self.sizer.Add(self.panel, 5, wx.GROW|wx.EXPAND|wx.ALL, 4)
        self.sizer.Fit(self)


        self.SetSizer(self.sizer)


        self.Layout()
        self.Update()
        self.Fit()
        self.SetAutoLayout(1)


    def _init_vtk(self):

        self.interactor = wxVTKRenderWindowInteractor(self.panel, -1, size=(70, 70))
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.interactor, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self.panel)

        self.panel.SetSizer(sizer)

        self.panel.Layout()
        self.panel.Update()
        self.panel.SetAutoLayout(1)
        
        self.actor = vtk.vtkImageActor()

        self.render = vtk.vtkRenderer()
        self.render.AddActor(self.actor)

        self.interactor.SetInteractorStyle(None)
        self.interactor.GetRenderWindow().AddRenderer(self.render)


    def _bind_events(self):
        self.Bind( wx.EVT_LEFT_DCLICK, self.OnSelect)
        self.interactor.Bind( wx.EVT_LEFT_DCLICK, self.OnSelect)
        self.panel.Bind( wx.EVT_LEFT_DCLICK, self.OnSelect)
        self.title.Bind( wx.EVT_LEFT_DCLICK, self.OnSelect)
        self.subtitle.Bind( wx.EVT_LEFT_DCLICK, self.OnSelect)


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

        self.Layout()
        self.Update()

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
        self.interactor.Render()




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
                #p.Hide()
                self.previews.append(p)
                self.grid.Add(p, 1, flag=wx.EXPAND)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)
        self.Bind(EVT_SELECT, self.OnSelect)

    def OnSelect(self, evt):
        my_evt = SerieEvent(myEVT_SELECT_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        self.GetEventHandler().ProcessEvent(my_evt)

    def SetPatientGroups(self, patient):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
        group_list = patient.GetGroups()
        print "LEN:", len(group_list)
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
            
        scroll_range = len(self.files)/NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)
        self._display_previews()

    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + MAX_VALUE
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
            p.SetImage(f)
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
        self.directory = directory
        self.series = dicom_reader.GetSeries(directory)[0]

    def SetPatientGroups(self, patient):
        self.group_list = patient.GetGroups()

    def SetDicomSerie(self, pos):
        self.files = []
        self.displayed_position = 0
        self.nhidden_last_display = 0
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
            info = (dicom.image.file,
                    dicom.image.window,
                    dicom.image.level,
                    "Image %d" % (dicom.image.number),
                    "%.2f" % (dicom.image.position[2]),
                    n)
            self.files.append(info)
            n+=1

        scroll_range = len(self.files)/NCOLS
        if scroll_range * NCOLS < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, NROWS, scroll_range, NCOLS)

        self._display_previews()


    def _display_previews(self):
        initial = self.displayed_position * NCOLS
        final = initial + MAX_VALUE
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
            p.SetImage(f)
            #p.interactor.Render()

        for f, p in zip(self.files[initial:final], self.previews):
            p.Show()


    def OnScroll(self, evt):
        if self.displayed_position != evt.GetPosition():
            self.displayed_position = evt.GetPosition()
            self._display_previews()
