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
import project as prj
import data.vtk_utils as vtku

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        style =  vtk.vtkInteractorStyleTrackballCamera()
        self.style = style

        interactor = wxVTKRenderWindowInteractor(self, -1, size = self.GetSize())
        interactor.SetInteractorStyle(style)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(interactor, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Layout()

        # It would be more correct (API-wise) to call interactor.Initialize() and
        # interactor.Start() here, but Initialize() calls RenderWindow.Render().
        # That Render() call will get through before we can setup the
        # RenderWindow() to render via the wxWidgets-created context; this
        # causes flashing on some platforms and downright breaks things on
        # other platforms.  Instead, we call widget.Enable().  This means
        # that the RWI::Initialized ivar is not set, but in THIS SPECIFIC CASE,
        # that doesn't matter.
        interactor.Enable(1)

        ren = vtk.vtkRenderer()
        interactor.GetRenderWindow().AddRenderer(ren)

        self.interactor = interactor
        self.ren = ren

        self.onclick = False

        self.__bind_events()
        self.__bind_events_wx()
        
        self.view_angle = None

    def OnMove(self, obj, evt):
        if self.onclick:
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            ps.Publisher().sendMessage('Set raycasting relative window and level',
                (diff_x, diff_y))
            self.interactor.Render()

    def OnClick(self, obj, evt):
        self.onclick = True
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        self.last_x, self.last_y = mouse_x, mouse_y

    def OnRelease(self, obj, evt):
        self.onclick = False

    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadActor, 'Load surface actor into viewer')
        ps.Publisher().subscribe(self.UpdateRender, 'Render volume viewer')
        ps.Publisher().subscribe(self.ChangeBackgroundColour,
                                'Change volume viewer background colour')
        ps.Publisher().subscribe(self.LoadVolume, 'Load volume into viewer')
        ps.Publisher().subscribe(self.AppendActor,'AppendActor')
        ps.Publisher().subscribe(self.SetWidgetInteractor, 
                                'Set Widget Interactor')
        ps.Publisher().subscribe(self.OnSetViewAngle,
                                'Set volume view angle')
        ps.Publisher().subscribe(self.OnSetWindowLevelText,
                                 'Set volume window and level text')
        ps.Publisher().subscribe(self.OnEnableBrightContrast, 
                                  'Bright and contrast adjustment')
        ps.Publisher().subscribe(self.OnDisableBrightContrast,
                                  'Set Editor Mode')
        
    def __bind_events_wx(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        pass


    def OnEnableBrightContrast(self, pubsub_evt):
        style = self.style
        style.AddObserver("MouseMoveEvent", self.OnMove)
        style.AddObserver("LeftButtonPressEvent", self.OnClick)
        style.AddObserver("LeftButtonReleaseEvent", self.OnRelease)


    def OnDisableBrightContrast(self, pubsub_evt):
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        self.style = style


    def OnSize(self, evt):
        self.UpdateRender()
        self.Refresh()
        self.interactor.UpdateWindowUI()
        self.interactor.Update()
        evt.Skip()
        
    def OnSetWindowLevelText(self, pubsub_evt):
        ww, wl = pubsub_evt.data
        self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

    def LoadVolume(self, pubsub_evt):
        volume = pubsub_evt.data[0]
        self.light = self.ren.GetLights().GetNextItem()
        
        text = vtku.Text()
        self.text = text

        self.ren.AddVolume(volume)
        self.ren.AddActor(text.actor)
        
        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
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
        
        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
            self.view_angle = 1
        else:
            ren.ResetCamera()
            ren.ResetCameraClippingRange()

        self.interactor.Render()

    def OnSetViewAngle(self, evt_pubsub):
        view = evt_pubsub.data
        self.SetViewAngle(view)

    def SetViewAngle(self, view):
        
        cam = self.ren.GetActiveCamera()
        cam.SetFocalPoint(0,0,0)
        
        proj = prj.Project()
        orig_orien = proj.original_orientation
        
        xv,yv,zv = const.VOLUME_POSITION[orig_orien][0][view]
        xp,yp,zp = const.VOLUME_POSITION[orig_orien][1][view]
        
        cam.SetViewUp(xv,yv,zv)
        cam.SetPosition(xp,yp,zp)
        
        self.ren.ResetCameraClippingRange() 
        self.ren.ResetCamera()
        self.interactor.Render()

    def UpdateRender(self, evt_pubsub=None):
        self.interactor.Render()

    def CreatePlanes(self):

        imagedata = self.imagedata
        ren = self.ren
        interactor = self.interactor

        import ivVolumeWidgets as vw
        axial_plane = vw.Plane()
        axial_plane.SetRender(ren)
        axial_plane.SetInteractor(interactor)
        axial_plane.SetOrientation(vw.AXIAL)
        axial_plane.SetInput(imagedata)
        axial_plane.Show()
        axial_plane.Update()

        coronal_plane = vw.Plane()
        coronal_plane.SetRender(ren)
        coronal_plane.SetInteractor(interactor)
        coronal_plane.SetOrientation(vw.CORONAL)
        coronal_plane.SetInput(imagedata)
        coronal_plane.Show()
        coronal_plane.Update()

        sagital_plane = vw.Plane()
        sagital_plane.SetRender(ren)
        sagital_plane.SetInteractor(interactor)
        sagital_plane.SetOrientation(vw.SAGITAL)
        sagital_plane.SetInput(imagedata)
        sagital_plane.Show()
        sagital_plane.Update()
    
    def SetWidgetInteractor(self, evt_pubsub=None):
        evt_pubsub.data.SetInteractor(self.interactor._Iren)
        
    def AppendActor(self, evt_pubsub=None):
        self.ren.AddActor(evt_pubsub.data)
