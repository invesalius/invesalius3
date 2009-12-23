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
from gui.widgets.clut_raycasting import CLUTRaycastingWidget
import style as st

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.interaction_style = st.StyleStateManager()

        style =  vtk.vtkInteractorStyleTrackballCamera()
        self.style = style

        interactor = wxVTKRenderWindowInteractor(self, -1, size = self.GetSize())
        interactor.SetInteractorStyle(style)
        self.interactor = interactor

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(interactor, 1, wx.EXPAND)
        self.sizer = sizer
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
        self.ren = ren

        self.raycasting_volume = False

        self.onclick = False

        self.text = vtku.Text()

        self.view_angle = None

        self.__bind_events()
        self.__bind_events_wx()
        
        self.mouse_pressed = 0
    
    def SetInteractorStyle(self, state):
        action = {
              const.STATE_PAN:
                    {
                    "MouseMoveEvent": self.OnPanMove,
                    "LeftButtonPressEvent": self.OnPanClick,
                    "LeftButtonReleaseEvent": self.OnReleasePanClick
                    },
              const.STATE_ZOOM:
                    {
                    "MouseMoveEvent": self.OnZoomMove,
                    "LeftButtonPressEvent": self.OnZoomClick,
                    "LeftButtonReleaseEvent": self.OnReleaseZoomClick,
                    },
              #const.STATE_SPIN:
              #      {
              #      "MouseMoveEvent": self.OnSpinMove,
              #      "LeftButtonPressEvent": self.OnSpinClick,
              #      "LeftButtonReleaseEvent": self.OnReleaseSpinClick,
              #      },
              const.STATE_SPIN:
                    {
                    },
              const.STATE_WL:
                    { 
                    "MouseMoveEvent": self.OnWindowLevelMove,
                    "LeftButtonPressEvent": self.OnWindowLevelClick,
                    "LeftButtonReleaseEvent":self.OnWindowLevelRelease
                    },
                const.STATE_DEFAULT:
                    {
                    }
              }
    
        if (state == const.STATE_ZOOM_SL):
            style = vtk.vtkInteractorStyleRubberBandZoom()
            self.interactor.SetInteractorStyle(style)
            self.style = style
        else:
            style = vtk.vtkInteractorStyleTrackballCamera()
            self.interactor.SetInteractorStyle(style)
            self.style = style  
                      
            # Check each event available for each mode
            for event in action[state]:
                # Bind event
              style.AddObserver(event,action[state][event])
    
    def OnSpinMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Spin()
            evt.OnRightButtonDown()

    def OnSpinClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartSpin()
        
    def OnReleaseSpinClick(self,evt,obj):
        self.mouse_pressed = 0
        evt.EndSpin()
        
    def OnZoomMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnZoomClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartDolly()
        
    def OnReleaseZoomClick(self,evt,obj):
        self.mouse_pressed = 0
        evt.EndDolly()
                 
            
    def OnPanMove(self, evt, obj):
        if (self.mouse_pressed):
            evt.Pan()
            evt.OnRightButtonDown()

    def OnPanClick(self, evt, obj):
        self.mouse_pressed = 1
        evt.StartPan()
        
    def OnReleasePanClick(self,evt,obj):
        self.mouse_pressed = 0
        evt.EndPan()
        
    def SetStyle(self, pubsub_evt):
        print "SetStyle"
        mode = pubsub_evt.data

        if (mode == const.MODE_ZOOM_SELECTION):
             self.SetMode('ZOOMSELECT')
        elif(mode == const.MODE_MOVE):
            self.SetMode('PAN')
        elif(mode == const.MODE_ZOOM):
            self.SetMode('ZOOM')
        elif(mode == const.MODE_ROTATE):
            self.SetMode('SPIN')
        elif(mode == const.MODE_WW_WL):
            self.SetMode('WINDOWLEVEL')


    def SetNewMode(self, pubsub_evt):
       mode = pubsub_evt.topic[1]
       
       if (mode == const.MODE_ZOOM_SELECTION):
            self.SetMode('ZOOMSELECT')
       elif(mode == const.MODE_MOVE):
           self.SetMode('PAN')
       elif(mode == const.MODE_ZOOM):
           self.SetMode('ZOOM')
       elif(mode == const.MODE_ROTATE):
           self.SetMode('SPIN')
       elif(mode == const.MODE_WW_WL):
           self.SetMode('WINDOWLEVEL')
           
    def OnWindowLevelMove(self, obj, evt):
        if self.onclick and self.raycasting_volume:
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            ps.Publisher().sendMessage('Set raycasting relative window and level',
                (diff_x, diff_y))
            ps.Publisher().sendMessage('Refresh raycasting widget points', None)
            self.interactor.Render()

    def OnWindowLevelClick(self, obj, evt):
        if const.RAYCASTING_WWWL_BLUR:
            self.style.StartZoom()
        self.onclick = True
        mouse_x, mouse_y = self.interactor.GetEventPosition()
        self.last_x, self.last_y = mouse_x, mouse_y

    def OnWindowLevelRelease(self, obj, evt):
        self.onclick = False
        if const.RAYCASTING_WWWL_BLUR:
            self.style.EndZoom()

    def ShowOrientationCube(self):
        print "ORIENTATION CUBE!"
        cube = vtk.vtkAnnotatedCubeActor()
        cube.GetXMinusFaceProperty().SetColor(1,0,0)
        cube.GetXPlusFaceProperty().SetColor(1,0,0)
        cube.GetYMinusFaceProperty().SetColor(0,1,0)
        cube.GetYPlusFaceProperty().SetColor(0,1,0)
        cube.GetZMinusFaceProperty().SetColor(0,0,1)
        cube.GetZPlusFaceProperty().SetColor(0,0,1)
        cube.GetTextEdgesProperty().SetColor(0,0,0)

        # anatomic labelling
        cube.SetXPlusFaceText ("A")
        cube.SetXMinusFaceText("P")
        cube.SetYPlusFaceText ("L")
        cube.SetYMinusFaceText("R")
        cube.SetZPlusFaceText ("S")
        cube.SetZMinusFaceText("I")

        axes = vtk.vtkAxesActor()
        axes.SetShaftTypeToCylinder()
        axes.SetTipTypeToCone()
        axes.SetXAxisLabelText("X")
        axes.SetYAxisLabelText("Y")
        axes.SetZAxisLabelText("Z")
        #axes.SetNormalizedLabelPosition(.5, .5, .5)

        orientation_widget = vtk.vtkOrientationMarkerWidget()
        orientation_widget.SetOrientationMarker(cube)
        orientation_widget.SetViewport(0.85,0.85,1.0,1.0)
        #orientation_widget.SetOrientationMarker(axes)
        orientation_widget.SetInteractor(self.interactor)
        orientation_widget.SetEnabled(1)
        orientation_widget.On()
        orientation_widget.InteractiveOff()
        

    def __bind_events(self):
        ps.Publisher().subscribe(self.LoadActor,
                                 'Load surface actor into viewer')
        ps.Publisher().subscribe(self.UpdateRender,
                                 'Render volume viewer')
        ps.Publisher().subscribe(self.ChangeBackgroundColour,
                        'Change volume viewer background colour')
        # Raycating - related
        ps.Publisher().subscribe(self.LoadVolume,
                                 'Load volume into viewer')
        ps.Publisher().subscribe(self.OnSetWindowLevelText,
                            'Set volume window and level text')
        ps.Publisher().subscribe(self.OnHideRaycasting,
                                'Hide raycasting volume')
        ps.Publisher().subscribe(self.OnShowRaycasting,
                                'Update raycasting preset')
        ###
        ps.Publisher().subscribe(self.AppendActor,'AppendActor')
        ps.Publisher().subscribe(self.SetWidgetInteractor, 
                                'Set Widget Interactor')
        ps.Publisher().subscribe(self.OnSetViewAngle,
                                'Set volume view angle')

        ps.Publisher().subscribe(self.SetNewMode, 
                          ('Set interaction mode', const.MODE_WW_WL)) 
        ps.Publisher().subscribe(self.OnDisableBrightContrast,
                                 ('Set interaction mode',
                                  const.MODE_SLICE_EDITOR))
        
        ps.Publisher().subscribe(self.OnExportSurface, 'Export surface to file')
        
        ps.Publisher().subscribe(self.LoadSlicePlane, 'Load slice plane')
        
        ps.Publisher().subscribe(self.ResetCamClippingRange, 'Reset cam clipping range')
        

        ps.Publisher().subscribe(self.OnEnableStyle, 'Enable style')
        ps.Publisher().subscribe(self.OnDisableStyle, 'Disable style')


    def OnEnableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.VOLUME_STYLES):
            new_state = self.interaction_style.AddState(state)
            self.SetInteractorStyle(new_state)
        else:
            #level = const.STYLE_LEVEL[state]
            new_state = self.interaction_style.RemoveState(state)
            self.SetInteractorStyle(new_state)

    def OnDisableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        new_state = self.interaction_style.RemoveState(state)
        self.SetInteractorStyle(new_state)

                
    def ResetCamClippingRange(self, pubsub_evt):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()
        

    def OnExportSurface(self, pubsub_evt):
        filename, filetype = pubsub_evt.data
        renwin = self.interactor.GetRenderWindow()

        if filetype == const.FILETYPE_RIB:
            writer = vtk.vtkIVExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
        elif filetype == const.FILETYPE_VRML:
            writer = vtk.vtkVRMLExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
        elif filetype == const.FILETYPE_OBJ:
            writer = vtk.vtkOBJExporter()
            writer.SetFilePrefix(filename.split(".")[-2])
            writer.SetInput(renwin)
        else: # const.FILETYPE_IV:
            writer = vtk.vtkIVExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
        writer.Write()



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
        if self.raycasting_volume:
            ww, wl = pubsub_evt.data
            self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

    def OnShowRaycasting(self, pubsub_evt):
        self.raycasting_volume = True
        self.text.Show()

    def OnHideRaycasting(self, pubsub_evt):
        self.raycasting_volume = False
        self.text.Hide()

    def LoadVolume(self, pubsub_evt):
        self.raycasting_volume = True

        volume = pubsub_evt.data[0]
        colour = pubsub_evt.data[1]
        ww, wl = pubsub_evt.data[2]
        
        self.light = self.ren.GetLights().GetNextItem()
        
        self.ren.AddVolume(volume)
        self.text.SetValue("WL: %d  WW: %d"%(wl, ww))
        self.ren.AddActor(self.text.actor)
        self.ren.SetBackground(colour)
        
        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
        else:
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()

        self.UpdateRender()

    def LoadSlicePlane(self, pubsub_evt):
        self.slice_plane = SlicePlane()

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

        #self.ShowOrientationCube()

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
    
    def SetWidgetInteractor(self, evt_pubsub=None):
        evt_pubsub.data.SetInteractor(self.interactor._Iren)

    def AppendActor(self, evt_pubsub=None):
        self.ren.AddActor(evt_pubsub.data)

class SlicePlane:
    def __init__(self):
        project = prj.Project()
        self.original_orientation = project.original_orientation
        self.Create()
        self.__bind_evt()
        self.__bind_vtk_evt()
    
    def __bind_evt(self):
        ps.Publisher().subscribe(self.Enable, 'Enable plane')
        ps.Publisher().subscribe(self.Disable, 'Disable plane')
        ps.Publisher().subscribe(self.ChangeSlice, 'Change slice from slice plane')
    
    def __bind_vtk_evt(self):
        self.plane_x.AddObserver("InteractionEvent", self.PlaneEvent)
        self.plane_y.AddObserver("InteractionEvent", self.PlaneEvent)
        self.plane_z.AddObserver("InteractionEvent", self.PlaneEvent)
        
    def PlaneEvent(self, obj, evt):
        
        number = obj.GetSliceIndex()
        plane_axis = obj.GetPlaneOrientation()
        
        if (self.original_orientation == const.AXIAL):
            if (plane_axis == 0):
                orientation = "SAGITAL"
            elif(plane_axis == 1):
                orientation = "CORONAL"
                dimen = obj.GetInput().GetDimensions()
                number = abs(dimen[0] - (number + 1))
            else:
                orientation = "AXIAL"
        
        elif(self.original_orientation == const.SAGITAL):
            if (plane_axis == 0):
                orientation = "CORONAL"
            elif(plane_axis == 1):
                orientation = "AXIAL"
                dimen = obj.GetInput().GetDimensions()
                number = abs(dimen[0] - number)
            else:
                orientation = "SAGITAL"
        else:
            if (plane_axis == 0):
                orientation = "SAGITAL"
            elif(plane_axis == 1):
                orientation = "AXIAL"
                dimen = obj.GetInput().GetDimensions()
                number = abs(dimen[0] - number)
            else:
                orientation = "CORONAL"
        
        
        if (obj.GetSlicePosition() != 0.0):
            ps.Publisher().sendMessage(('Set scroll position', \
                                        orientation), number)
        
    def Create(self):

        plane_x = self.plane_x = vtk.vtkImagePlaneWidget()
        plane_x.DisplayTextOff()
        ps.Publisher().sendMessage('Input Image in the widget', plane_x)
        plane_x.SetPlaneOrientationToXAxes()
        plane_x.TextureVisibilityOn()
        plane_x.SetLeftButtonAction(1)
        plane_x.SetRightButtonAction(0)
        prop1 = plane_x.GetPlaneProperty()
        prop1.SetColor(0, 0, 1)
        cursor_property = plane_x.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        plane_y = self.plane_y = vtk.vtkImagePlaneWidget()
        plane_y.DisplayTextOff()
        ps.Publisher().sendMessage('Input Image in the widget', plane_y)
        plane_y.SetPlaneOrientationToYAxes()
        plane_y.TextureVisibilityOn()
        plane_y.SetLeftButtonAction(1)
        plane_y.SetRightButtonAction(0)
        prop1 = plane_y.GetPlaneProperty()
        prop1.SetColor(0, 1, 0)
        cursor_property = plane_y.GetCursorProperty()
        cursor_property.SetOpacity(0) 
        
        plane_z = self.plane_z = vtk.vtkImagePlaneWidget()
        plane_z.DisplayTextOff()
        ps.Publisher().sendMessage('Input Image in the widget', plane_z)
        plane_z.SetPlaneOrientationToZAxes()
        plane_z.TextureVisibilityOn()
        plane_z.SetLeftButtonAction(1)
        plane_z.SetRightButtonAction(0)
        prop1 = plane_z.GetPlaneProperty()
        prop1.SetColor(1, 0, 0)
        cursor_property = plane_z.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        if(self.original_orientation == const.AXIAL):
            prop3 = plane_z.GetPlaneProperty()
            prop3.SetColor(1, 0, 0)

            prop1 = plane_x.GetPlaneProperty()
            prop1.SetColor(0, 0, 1)
                        
            prop2 = plane_y.GetPlaneProperty()
            prop2.SetColor(0, 1, 0)
                        
        elif(self.original_orientation == const.SAGITAL):
            prop3 = plane_y.GetPlaneProperty()
            prop3.SetColor(1, 0, 0)

            prop1 = plane_z.GetPlaneProperty()
            prop1.SetColor(0, 0, 1)
                        
            prop2 = plane_x.GetPlaneProperty()
            prop2.SetColor(0, 1, 0)
                        
        else:
            prop3 = plane_y.GetPlaneProperty()
            prop3.SetColor(1, 0, 0)

            prop1 = plane_x.GetPlaneProperty()
            prop1.SetColor(0, 0, 1)
                        
            prop2 = plane_z.GetPlaneProperty()
            prop2.SetColor(0, 1, 0)
            
        ps.Publisher().sendMessage('Set Widget Interactor', plane_x)
        ps.Publisher().sendMessage('Set Widget Interactor', plane_y)
        ps.Publisher().sendMessage('Set Widget Interactor', plane_z)
        
        self.Enable()
        self.Disable()
        self.Render()
                
    def Enable(self, evt_pubsub=None):
        if (evt_pubsub):
            label = evt_pubsub.data
            
            if(self.original_orientation == const.AXIAL):
                if(label == "Axial"):
                    self.plane_z.On()
                elif(label == "Coronal"):
                    self.plane_y.On()
                elif(label == "Sagital"):
                    self.plane_x.On()
                    a = self.plane_x.GetTexturePlaneProperty()
                    a.SetBackfaceCulling(0)
                    c = self.plane_x.GetTexture()
                    c.SetRestrictPowerOf2ImageSmaller(1)
                    #print dir(a)
                    
            elif(self.original_orientation == const.SAGITAL):
                if(label == "Axial"):
                    self.plane_y.On()
                elif(label == "Coronal"):
                    self.plane_x.On()
                elif(label == "Sagital"):
                    self.plane_z.On()
            else:
                if(label == "Axial"):
                    self.plane_y.On()
                elif(label == "Coronal"):
                    self.plane_z.On()
                elif(label == "Sagital"):
                    self.plane_x.On()
            
        else:
            self.plane_z.On()
            self.plane_x.On()
            self.plane_y.On()
            ps.Publisher().sendMessage('Set volume view angle', const.VOL_ISO)
        self.Render()

    def Disable(self, evt_pubsub=None):
        if (evt_pubsub):
            label = evt_pubsub.data
            
            if(self.original_orientation == const.AXIAL):
                if(label == "Axial"):
                    self.plane_z.Off()
                elif(label == "Coronal"):
                    self.plane_y.Off()
                elif(label == "Sagital"):
                    self.plane_x.Off()
            
            elif(self.original_orientation == const.SAGITAL):
                if(label == "Axial"):
                    self.plane_y.Off()
                elif(label == "Coronal"):
                    self.plane_x.Off()
                elif(label == "Sagital"):
                    self.plane_z.Off()
            else:
                if(label == "Axial"):
                    self.plane_y.Off()
                elif(label == "Coronal"):
                    self.plane_z.Off()
                elif(label == "Sagital"):
                    self.plane_x.Off()
        else:
            self.plane_z.Off()
            self.plane_x.Off()
            self.plane_y.Off()

        self.Render()

        
    def Render(self):
        ps.Publisher().sendMessage('Render volume viewer')    
    
    def ChangeSlice(self, pubsub_evt = None):
        orientation, number = pubsub_evt.data
        
        if (self.original_orientation == const.AXIAL):
            if (orientation == "CORONAL"):
                self.SetSliceNumber(number, "Y")
            elif(orientation == "SAGITAL"):
                self.SetSliceNumber(number, "X")
            else:
                self.SetSliceNumber(number, "Z")
        
        elif(self.original_orientation == const.SAGITAL):
            if (orientation == "CORONAL"):
                self.SetSliceNumber(number, "X")
            elif(orientation == "SAGITAL"):
                self.SetSliceNumber(number, "Z")
            else:
                self.SetSliceNumber(number, "Y")
        
        else:
            if (orientation == "CORONAL"):
                self.SetSliceNumber(number, "Z")
            elif(orientation == "SAGITAL"):
                self.SetSliceNumber(number, "X")
            else:
                self.SetSliceNumber(number, "Y")
            
        self.Render()
    
    def SetSliceNumber(self, number, axis):
        if (axis == "X"):
            self.plane_x.SetPlaneOrientationToXAxes()
            self.plane_x.SetSliceIndex(number)
        elif(axis == "Y"):
            self.plane_y.SetPlaneOrientationToYAxes()
            self.plane_y.SetSliceIndex(number)
        else:
            self.plane_z.SetPlaneOrientationToZAxes()
            self.plane_z.SetSliceIndex(number)


    def PointId(self, evt, obj):
        #TODO: add in the code
        #   picker = vtk.vtkPointPicker()
        #   interactor.SetPicker(picker)
        #   interactor.AddObserver("left...", self.PointId)
        
        x,y = evt.GetLastEventPosition()
        self.picker.Pick(x, y, 0, self.ren1)
        point_id = self.picker.GetPointId()
        
