#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import wx
import vtk
import vtkgdcm

from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
#from reader import dicom_reader

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


class DicomLoader(object):
    """
    Responsible for load dicom files. A dictionary like behavior
    """
    def __init__(self):
        self.loaded_dicoms = {}

    def __getitem__(self, filename):
        """
        Especial method to behave like dictionary
        """
        try:
            return self.loaded_dicoms[filename]
        except KeyError:
            #print "Except"
            self._load_dicom_files(filename)
            return self.loaded_dicoms[filename]

    def _load_dicom_files(self, filename, window=150, level=230):
        reader = vtkgdcm.vtkGDCMImageReader()
        reader.SetFileName(filename)
        imagedata = reader.GetOutput()

        scale = imagedata.GetScalarRange()
        
        cast = vtk.vtkImageMapToWindowLevelColors()
        cast.SetInput(imagedata)
        cast.SetWindow(float(window))
        cast.SetLevel(float(level))

        self.loaded_dicoms[filename] = cast.GetOutput()


class Preview(wx.Panel):
    """
    Where the images will be showed.
    """
    dicom_loader = DicomLoader()
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

    def SetImage(self, image_data):
        """
        Set a Image to preview.
        """
        filename, window, level, title, subtitle = image_data
        print image_data
        self.SetTitle(title)
        self.SetSubtitle(subtitle)
        #self.ID = image_file[5] # todo: check if this is necessary
        
        # TODO: enhace interface
        imagedata = Preview.dicom_loader[filename]
        self.actor.SetInput(imagedata)
        self.render.ResetCamera()

class DicomPreviewSeries(wx.Panel):
    """A dicom series preview panel"""
    def __init__(self, parent):
        super(DicomPreviewSeries, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.sizer)
        self.displayed_position = 0
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

    def SetDicomDirectory(self, directory):
        print "SetDicomDirectory"
        self.directory = directory
        self.series = dicom_reader.GetSeries(directory)[0]
        print "keys", [key[0] for key in self.series.keys()]
        
        s = self.series
        for k in s.keys():
            print "------ PESSOA ---------"
            print "%s (%d series)"%(k[0], len(s[k])-1)
            for ns in range(1,len(s[k])):
                print "------ SERIE ---------"
                print "unnamed"
                print "age %s" %(s[k][ns][8])
                print "date acquired %s %s" %(s[k][ns][0], s[k][ns][4])
                print "birthdate %s" %(s[k][ns][23])
                print "institution %s" %(s[k][ns][6]) 

        # TODO: I need to improve this
        self.files = [(self.series[i][0][0][8], # Filename
                       self.series[i][0][0][12], # Window Level
                       self.series[i][0][0][13], # Window Width
                       "unnamed", #% (n + 1), # Title
                       "%d Images" % len(self.series[i][0]), # Subtitle
                       i) for n, i in enumerate(self.series)]

    def SetDicomSeries(self, files):
        self.files = files
        scroll_range = len(files)/5
        if scroll_range * 5 < len(files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, 3, scroll_range, 5)
        self._display_previews()

    def _display_previews(self):
        initial = self.displayed_position * 5
        final = initial + 15
        for f, p in zip(self.files[initial:final], self.previews):
            print "--------"
            print "f:", f
            print "p: ", p
            p.SetImage(f)
            p.Show()

    def OnScroll(self, evt):
        self.displayed_position = evt.GetPosition()
        [i.Hide() for i in self.previews]
        self._display_previews()


class DicomPreview(wx.Panel):
    """A dicom preview panel"""
    def __init__(self, parent):
        super(DicomPreview, self).__init__(parent)
        # TODO: 3 pixels between the previews is a good idea?
        # I have to test.
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.sizer)
        self.displayed_position = 0
        self.nhidden_last_display = 0
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
                #p.Hide()
                self.previews.append(p)
                self.grid.Add(p, i, j)

    def _bind_events(self):
        # When the user scrolls the window
        self.Bind(wx.EVT_SCROLL, self.OnScroll)

    def SetDicomDirectory(self, directory):
        self.directory = directory
        self.series = dicom_reader.GetSeries(directory)[0]

    def SetDicomSerie(self, serie):
        k = serie
        self.files = [(i[8],
                       i[12],
                       i[13],
                       "Image %d" % (n + 1), # Title
                       "%s"% str(i[3][2]), # Spacing
                        n)for n, i in enumerate(self.series[k][0])]
        scroll_range = len(self.files)/5
        if scroll_range * 5 < len(self.files):
            scroll_range +=1
        self.scroll.SetScrollbar(0, 3, scroll_range, 5)
        self._display_previews()

    def _display_previews(self):
        initial = self.displayed_position * 5
        final = initial + 15
    
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
            p.SetImage(f)
            p.interactor.Render()

    def OnScroll(self, evt):
        if self.displayed_position != evt.GetPosition():
            self.displayed_position = evt.GetPosition()
            self._display_previews()
