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


import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
import wx
import wx.lib.pubsub as ps

import data.slice_ as sl

import project

class Viewer(wx.Panel):

    def __init__(self, prnt, orientation='AXIAL'):
        wx.Panel.__init__(self, prnt, size=wx.Size(320, 300))

        self.__init_gui()
        self.__config_interactor()

        self.orientation = orientation
        self.slice_number = 0

        self.__bind_events()
        self.__bind_events_wx()

    def __init_gui(self):
        interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())

        scroll = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        self.scroll = scroll

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(sizer)

        sizer.Add(scroll, 0, wx.EXPAND|wx.GROW)
        sizer.Add(interactor, 1, wx.EXPAND|wx.GROW)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.interactor = interactor

    def __config_interactor(self):
        style = vtk.vtkInteractorStyleImage()
        ren = vtk.vtkRenderer()

        interactor = self.interactor
        interactor.SetInteractorStyle(style)
        interactor.GetRenderWindow().AddRenderer(ren)

        self.cam = ren.GetActiveCamera()

        self.ren = ren

    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadImagedata, 'Load slice to viewer')
        ps.Publisher().subscribe(self.SetColour, 'Change mask colour')
        ps.Publisher().subscribe(self.UpdateRender, 'Update slice viewer')
        ps.Publisher().subscribe(self.SetScrollPosition, ('Set scroll position', 
                                                     self.orientation))

    def __bind_events_wx(self):
        self.scroll.Bind(wx.EVT_SCROLL, self.OnScrollBar)
        #self.interactor.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)

    def LoadImagedata(self, pubsub_evt):
        imagedata = pubsub_evt.data
        self.SetInput(imagedata)

    def SetInput(self, imagedata):
        self.imagedata = imagedata
        ren = self.ren
        interactor = self.interactor

        # Slice pipeline, to be inserted into current viewer
        slice_ = sl.Slice()
        if slice_.imagedata is None:
            slice_.SetInput(imagedata)

        actor = vtk.vtkImageActor()
        actor.SetInput(slice_.GetOutput())
        self.actor = actor

        ren.AddActor(actor)
        self.__update_camera()

        max_slice_number = actor.GetSliceNumberMax()
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        self.__update_camera()

    def __update_camera(self):
        cam = self.cam

        orientation = self.orientation

        if orientation == "AXIAL":
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(0, 0, 1)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 1, 0)
        elif orientation == "CORONAL":
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(0, -1, 0)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 0, 1)
        elif orientation == "SAGITAL":
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(1, 0, 0)
            cam.ComputeViewPlaneNormal()
            cam.SetViewUp(0, 0, 1)

        cam.OrthogonalizeViewUp()
        self.__update_display_extent()
        cam.ParallelProjectionOn()
        self.ren.ResetCamera()
        self.ren.Render()

    def __update_display_extent(self):
        actor = self.actor
        slice_number = self.slice_number
        extent = self.imagedata.GetWholeExtent()
        if self.orientation == "AXIAL":
            xs = extent[1] - extent[0] + 1
            ys = extent[3] - extent[2] + 1
            actor.SetDisplayExtent(extent[0], extent[1],
                                   extent[2], extent[3],
                                   slice_number, slice_number)
        elif self.orientation == "CORONAL":
            xs = extent[1] - extent[0] + 1
            ys = extent[5] - extent[4] + 1
            actor.SetDisplayExtent(extent[0], extent[1],
                                    slice_number,slice_number,
                                    extent[4], extent[5])
        elif self.orientation == "SAGITAL":
            xs = extent[3] - extent[2] + 1
            ys = extent[5] - extent[4] + 1
            actor.SetDisplayExtent(slice_number, slice_number,
                                    extent[2], extent[3],
                                    extent[4], extent[5])

        self.ren.ResetCameraClippingRange()
        self.ren.Render()

    def UpdateRender(self, evt):
        self.interactor.Render()

    def SetScrollPosition(self, pubsub_evt):
        value = pubsub_evt.data
        position = self.scroll.GetThumbPosition()
        position += value
        self.scroll.SetThumbPosition(position)
        self.OnScrollBar()

    def OnScrollBar(self, evt=None):
        pos = self.scroll.GetThumbPosition()
        self.SetSliceNumber(pos)
        self.interactor.Render()
        if evt:
            evt.Skip()

    def SetSliceNumber(self, index):
        self.slice_number = index
        self.__update_display_extent()

    def SetColour(self, pubsub_evt):
        colour_wx = pubsub_evt.data
        colour_vtk = [colour/float(255) for colour in colour_wx]
        #self.editor.SetColour(colour_vtk)
        self.interactor.Render()

