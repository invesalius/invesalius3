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
import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
import wx.lib.pubsub as ps
import constants as const

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        style =  vtk.vtkInteractorStyleTrackballCamera()

        iren = wxVTKRenderWindowInteractor(self, -1, size = self.GetSize())
        iren.SetInteractorStyle(style)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(iren, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Layout()

        # It would be more correct (API-wise) to call iren.Initialize() and
        # iren.Start() here, but Initialize() calls RenderWindow.Render().
        # That Render() call will get through before we can setup the
        # RenderWindow() to render via the wxWidgets-created context; this
        # causes flashing on some platforms and downright breaks things on
        # other platforms.  Instead, we call widget.Enable().  This means
        # that the RWI::Initialized ivar is not set, but in THIS SPECIFIC CASE,
        # that doesn't matter.
        iren.Enable(1)

        ren = vtk.vtkRenderer()
        iren.GetRenderWindow().AddRenderer(ren)

        self.iren = iren
        self.ren = ren

        self.__bind_events()
        self.__bind_events_wx()
        
        self.first_reposition_actor = 0

    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadActor, 'Load surface actor into viewer')
        ps.Publisher().subscribe(self.UpdateRender, 'Render volume viewer')
        ps.Publisher().subscribe(self.ChangeBackgroundColour,
                                'Change volume viewer background colour')
        ps.Publisher().subscribe(self.LoadVolume, 'Load volume into viewer')
        ps.Publisher().subscribe(self.AppendActor,'AppendActor')
        ps.Publisher().subscribe(self.SetWidgetInteractor, 'Set Widget Interactor')
        ps.Publisher().subscribe(self.RepositionActor, 'Reposition Actor')
        
        
    def __bind_events_wx(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        pass
        
    def OnSize(self, evt):
        print "viewer_volume :: OnSize"
        self.UpdateRender()
        self.Refresh()
        print dir(self.iren)
        self.iren.UpdateWindowUI()
        self.iren.Update()
        evt.Skip()
        
    def LoadVolume(self, pubsub_evt):
        volume, colour = pubsub_evt.data
        self.light = self.ren.GetLights().GetNextItem()
        self.ren.AddVolume(volume)
        if not (self.first_reposition_actor):
            self.RepositionActor()
            self.first_reposition_actor = 1
        else:
            ren.ResetCamera()
            ren.ResetCameraClippingRange()  
        self.UpdateRender()

    def ChangeBackgroundColour(self, pubsub_evt):
        colour = pubsub_evt.data
        self.ren.SetBackground(colour)
        self.UpdateRender()

    def LoadActor(self, pubsub_evt):
        actor = pubsub_evt.data
        
        ren = self.ren
        ren.AddActor(actor)
        
        if not (self.first_reposition_actor):
            self.RepositionActor()
            self.first_reposition_actor = 1
        else:
            ren.ResetCamera()
            ren.ResetCameraClippingRange()

        self.iren.Render()

    def RepositionActor(self, evt_pubsub=None):
        
        if (evt_pubsub):
            position = evt_pubsub.data
        else:
            position = "FRONT"
            
        cam = self.ren.GetActiveCamera()
        cam.SetFocalPoint(0,0,0)
        
        xv,yv,zv = const.AXIAL_VOLUME_CAM_VIEW_UP[position]
        xp,yp,zp = const.AXIAL_VOLUME_CAM_POSITION[position]
        
        cam.SetViewUp(xv,yv,zv)
        cam.SetPosition(xp,yp,zp)
        
        self.ren.ResetCameraClippingRange() 
        self.ren.ResetCamera()
        self.iren.Render()

    def UpdateRender(self, evt_pubsub=None):
        self.iren.Render()

    def CreatePlanes(self):

        imagedata = self.imagedata
        ren = self.ren
        iren = self.iren

        import ivVolumeWidgets as vw
        axial_plane = vw.Plane()
        axial_plane.SetRender(ren)
        axial_plane.SetInteractor(iren)
        axial_plane.SetOrientation(vw.AXIAL)
        axial_plane.SetInput(imagedata)
        axial_plane.Show()
        axial_plane.Update()

        coronal_plane = vw.Plane()
        coronal_plane.SetRender(ren)
        coronal_plane.SetInteractor(iren)
        coronal_plane.SetOrientation(vw.CORONAL)
        coronal_plane.SetInput(imagedata)
        coronal_plane.Show()
        coronal_plane.Update()

        sagital_plane = vw.Plane()
        sagital_plane.SetRender(ren)
        sagital_plane.SetInteractor(iren)
        sagital_plane.SetOrientation(vw.SAGITAL)
        sagital_plane.SetInput(imagedata)
        sagital_plane.Show()
        sagital_plane.Update()
    
    def SetWidgetInteractor(self, evt_pubsub=None):
        evt_pubsub.data.SetInteractor(self.iren._Iren)
        
    def AppendActor(self, evt_pubsub=None):
        self.ren.AddActor(evt_pubsub.data)