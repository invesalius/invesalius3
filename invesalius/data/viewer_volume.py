#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import os
import sys

import numpy as np
from numpy.core.umath_tests import inner1d
import wx
import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.bases as bases
import invesalius.data.vtk_utils as vtku
import invesalius.project as prj
import invesalius.style as st
import invesalius.utils as utils
import invesalius.data.measures as measures

if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

PROP_MEASURE = 0.8

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.interaction_style = st.StyleStateManager()

        self.initial_focus = None

        self.staticballs = []

        style = vtk.vtkInteractorStyleTrackballCamera()
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
        self.text.SetValue("")
        self.ren.AddActor(self.text.actor)


        self.slice_plane = None

        self.view_angle = None

        self.__bind_events()
        self.__bind_events_wx()

        self.mouse_pressed = 0
        self.on_wl = False

        self.picker = vtk.vtkPointPicker()
        interactor.SetPicker(self.picker)
        self.seed_points = []

        self.points_reference = []

        self.measure_picker = vtk.vtkPropPicker()
        #self.measure_picker.SetTolerance(0.005)
        self.measures = []

        self._last_state = 0

        self.repositioned_axial_plan = 0
        self.repositioned_sagital_plan = 0
        self.repositioned_coronal_plan = 0
        self.added_actor = 0

        self.camera_state = True

        self.ball_actor = None
        self._mode_cross = False
        self._to_show_ball = 0
        self._ball_ref_visibility = False

        self.sen1 = False
        self.sen2 = False

        self.timer = False
        self.index = False

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor,
                                 'Load surface actor into viewer')
        Publisher.subscribe(self.RemoveActor,
                                'Remove surface actor from viewer')
        Publisher.subscribe(self.OnShowSurface, 'Show surface')
        Publisher.subscribe(self.UpdateRender,
                                 'Render volume viewer')
        Publisher.subscribe(self.ChangeBackgroundColour,
                        'Change volume viewer background colour')
        # Raycating - related
        Publisher.subscribe(self.LoadVolume,
                                 'Load volume into viewer')
        Publisher.subscribe(self.UnloadVolume,
                                 'Unload volume')
        Publisher.subscribe(self.OnSetWindowLevelText,
                            'Set volume window and level text')
        Publisher.subscribe(self.OnHideRaycasting,
                                'Hide raycasting volume')
        Publisher.subscribe(self.OnShowRaycasting,
                                'Update raycasting preset')
        ###
        Publisher.subscribe(self.AppendActor,'AppendActor')
        Publisher.subscribe(self.SetWidgetInteractor, 
                                'Set Widget Interactor')
        Publisher.subscribe(self.OnSetViewAngle,
                                'Set volume view angle')

        Publisher.subscribe(self.OnDisableBrightContrast,
                                 'Set interaction mode '+
                                  str(const.MODE_SLICE_EDITOR))

        Publisher.subscribe(self.OnExportSurface, 'Export surface to file')

        Publisher.subscribe(self.LoadSlicePlane, 'Load slice plane')

        Publisher.subscribe(self.ResetCamClippingRange, 'Reset cam clipping range')
        Publisher.subscribe(self.SetVolumeCamera, 'Set camera in volume')
        Publisher.subscribe(self.SetVolumeCameraState, 'Update volume camera state')

        Publisher.subscribe(self.OnEnableStyle, 'Enable style')
        Publisher.subscribe(self.OnDisableStyle, 'Disable style')

        Publisher.subscribe(self.OnHideText,
                                 'Hide text actors on viewers')

        Publisher.subscribe(self.AddActors, 'Add actors ' + str(const.SURFACE))
        Publisher.subscribe(self.RemoveActors, 'Remove actors ' + str(const.SURFACE))

        Publisher.subscribe(self.OnShowText,
                                 'Show text actors on viewers')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')

        Publisher.subscribe(self.RemoveAllActor, 'Remove all volume actors')
        
        Publisher.subscribe(self.OnExportPicture,'Export picture to file')

        Publisher.subscribe(self.OnStartSeed,'Create surface by seeding - start')
        Publisher.subscribe(self.OnEndSeed,'Create surface by seeding - end')

        Publisher.subscribe(self.SetStereoMode, 'Set stereo mode')
    
        Publisher.subscribe(self.Reposition3DPlane, 'Reposition 3D Plane')
        
        Publisher.subscribe(self.RemoveVolume, 'Remove Volume')

        Publisher.subscribe(self.SetBallReferencePosition,
                            'Set ball reference position')
        Publisher.subscribe(self._check_ball_reference, 'Enable style')
        Publisher.subscribe(self._uncheck_ball_reference, 'Disable style')

        Publisher.subscribe(self.OnSensors, 'Sensors ID')
        Publisher.subscribe(self.OnRemoveSensorsID, 'Remove sensors ID')

        # Related to marker creation in navigation tools
        Publisher.subscribe(self.AddMarker, 'Add marker')
        Publisher.subscribe(self.HideAllMarkers, 'Hide all markers')
        Publisher.subscribe(self.ShowAllMarkers, 'Show all markers')
        Publisher.subscribe(self.RemoveAllMarkers, 'Remove all markers')
        Publisher.subscribe(self.RemoveMarker, 'Remove marker')
        Publisher.subscribe(self.BlinkMarker, 'Blink Marker')
        Publisher.subscribe(self.StopBlinkMarker, 'Stop Blink Marker')

    def SetStereoMode(self, pubsub_evt):
        mode = pubsub_evt.data
        ren_win = self.interactor.GetRenderWindow()
        
        if mode == const.STEREO_OFF:
            ren_win.StereoRenderOff()
        else:

            if mode == const.STEREO_RED_BLUE:
                ren_win.SetStereoTypeToRedBlue()
            elif mode == const.STEREO_CRISTAL:
                ren_win.SetStereoTypeToCrystalEyes()
            elif mode == const.STEREO_INTERLACED:
                ren_win.SetStereoTypeToInterlaced()
            elif mode == const.STEREO_LEFT:
                ren_win.SetStereoTypeToLeft()
            elif mode == const.STEREO_RIGHT:
                ren_win.SetStereoTypeToRight()
            elif mode == const.STEREO_DRESDEN:
                ren_win.SetStereoTypeToDresden()
            elif mode == const.STEREO_CHECKBOARD:
                ren_win.SetStereoTypeToCheckerboard()
            elif mode == const.STEREO_ANAGLYPH:
                ren_win.SetStereoTypeToAnaglyph()

            ren_win.StereoRenderOn()
        
        self.interactor.Render()

    def _check_ball_reference(self, pubsub_evt):
        st = pubsub_evt.data
        if st == const.SLICE_STATE_CROSS:
            self._mode_cross = True
            self._check_and_set_ball_visibility()
            self.interactor.Render()

    def _uncheck_ball_reference(self, pubsub_evt):
        st = pubsub_evt.data
        if st == const.SLICE_STATE_CROSS:
            self._mode_cross = False
            self.RemoveBallReference()
            self.interactor.Render()

    def OnSensors(self, pubsub_evt):
        probe_id = pubsub_evt.data[0]
        ref_id = pubsub_evt.data[1]
        if not self.sen1:
            self.CreateSensorID()

        if probe_id:
            colour1 = (0, 1, 0)
        else:
            colour1 = (1, 0, 0)
        if ref_id:
            colour2 = (0, 1, 0)
        else:
            colour2 = (1, 0, 0)

        self.sen1.SetColour(colour1)
        self.sen2.SetColour(colour2)
        self.Refresh()

    def CreateSensorID(self):
        sen1 = vtku.Text()
        sen1.SetSize(const.TEXT_SIZE_LARGE)
        sen1.SetPosition((const.X, const.Y))
        sen1.ShadowOff()
        sen1.SetValue("O")
        self.sen1 = sen1
        self.ren.AddActor(sen1.actor)

        sen2 = vtku.Text()
        sen2.SetSize(const.TEXT_SIZE_LARGE)
        sen2.SetPosition((const.X+0.04, const.Y))
        sen2.ShadowOff()
        sen2.SetValue("O")
        self.sen2 = sen2
        self.ren.AddActor(sen2.actor)

        self.interactor.Render()

    def OnRemoveSensorsID(self, pubsub_evt):
        if self.sen1:
            self.ren.RemoveActor(self.sen1.actor)
            self.ren.RemoveActor(self.sen2.actor)
            self.sen1 = self.sen2 = False
            self.interactor.Render()

    def OnShowSurface(self, pubsub_evt):
        index, value = pubsub_evt.data
        if value:
            self._to_show_ball += 1
        else:
            self._to_show_ball -= 1
        self._check_and_set_ball_visibility()

    def OnStartSeed(self, pubsub_evt):
        index = pubsub_evt.data
        self.seed_points = []
    
    def OnEndSeed(self, pubsub_evt):
        Publisher.sendMessage("Create surface from seeds",
                                    self.seed_points) 

    def OnExportPicture(self, pubsub_evt):
        Publisher.sendMessage('Begin busy cursor')
        id, filename, filetype = pubsub_evt.data
        if id == const.VOLUME:
            if filetype == const.FILETYPE_POV:
                renwin = self.interactor.GetRenderWindow()
                image = vtk.vtkWindowToImageFilter()
                image.SetInput(renwin)
                writer = vtk.vtkPOVExporter()
                writer.SetFileName(filename.encode(const.FS_ENCODE))
                writer.SetRenderWindow(renwin)
                writer.Write()
            else:
                #Use tiling to generate a large rendering.
                image = vtk.vtkRenderLargeImage()
                image.SetInput(self.ren)
                image.SetMagnification(1)
                image.Update()

                image = image.GetOutput()

                # write image file
                if (filetype == const.FILETYPE_BMP):
                    writer = vtk.vtkBMPWriter()
                elif (filetype == const.FILETYPE_JPG):
                    writer =  vtk.vtkJPEGWriter()
                elif (filetype == const.FILETYPE_PNG):
                    writer = vtk.vtkPNGWriter()
                elif (filetype == const.FILETYPE_PS):
                    writer = vtk.vtkPostScriptWriter()
                elif (filetype == const.FILETYPE_TIF):
                    writer = vtk.vtkTIFFWriter()
                    filename = u"%s.tif"%filename.strip(".tif")

                writer.SetInputData(image)
                writer.SetFileName(filename.encode(const.FS_ENCODE))
                writer.Write()

            if not os.path.exists(filename):
                wx.MessageBox(_("InVesalius was not able to export this picture"), _("Export picture error"))

        Publisher.sendMessage('End busy cursor')

    def OnCloseProject(self, pubsub_evt):
        if self.raycasting_volume:
            self.raycasting_volume = False

        if  self.slice_plane:
            self.slice_plane.Disable()
            self.slice_plane.DeletePlanes()
            del self.slice_plane
            Publisher.sendMessage('Uncheck image plane menu')
            self.mouse_pressed = 0
            self.on_wl = False
            self.slice_plane = 0

        self.interaction_style.Reset()
        self.SetInteractorStyle(const.STATE_DEFAULT)
        self._last_state = const.STATE_DEFAULT

    def OnHideText(self, pubsub_evt):
        self.text.Hide()
        self.interactor.Render()

    def OnShowText(self, pubsub_evt):
        if self.on_wl:
            self.text.Show()
            self.interactor.Render()

    def AddActors(self, pubsub_evt):
        "Inserting actors"
        actors = pubsub_evt.data[0]
        for actor in actors:
            self.ren.AddActor(actor)

    def RemoveVolume(self, pub_evt):
        volumes = self.ren.GetVolumes()
        if (volumes.GetNumberOfItems()):
            self.ren.RemoveVolume(volumes.GetLastProp())
            self.interactor.Render()
            self._to_show_ball -= 1
            self._check_and_set_ball_visibility()

    def RemoveActors(self, pubsub_evt):
        "Remove a list of actors"
        actors = pubsub_evt.data[0]
        for actor in actors:
            self.ren.RemoveActor(actor)

    def AddPointReference(self, position, radius=1, colour=(1, 0, 0)):
        """
        Add a point representation in the given x,y,z position with a optional
        radius and colour.
        """
        point = vtk.vtkSphereSource()
        point.SetCenter(position)
        point.SetRadius(radius)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(point.GetOutput())

        p = vtk.vtkProperty()
        p.SetColor(colour)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(p)
        actor.PickableOff()

        self.ren.AddActor(actor)
        self.points_reference.append(actor)

    def RemoveAllPointsReference(self):
        for actor in self.points_reference:
            self.ren.RemoveActor(actor)
        self.points_reference = []

    def RemovePointReference(self, point):
        """
        Remove the point reference. The point argument is the position that is
        added.
        """
        actor = self.points_reference.pop(point)
        self.ren.RemoveActor(actor)

    def AddMarker(self, pubsub_evt):
        """
        Markers create by navigation tools and
        rendered in volume viewer.
        """
        self.ball_id = pubsub_evt.data[0]
        ballsize = pubsub_evt.data[1]
        ballcolour = pubsub_evt.data[2]
        coord = pubsub_evt.data[3]
        x, y, z = bases.flip_x(coord)

        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(ballsize)
        ball_ref.SetCenter(x, y, z)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtk.vtkProperty()
        prop.SetColor(ballcolour)

        #adding a new actor for the present ball
        self.staticballs.append(vtk.vtkActor())

        self.staticballs[self.ball_id].SetMapper(mapper)
        self.staticballs[self.ball_id].SetProperty(prop)

        self.ren.AddActor(self.staticballs[self.ball_id])
        self.ball_id = self.ball_id + 1
        #self.UpdateRender()
        self.Refresh()
        
    def HideAllMarkers(self, pubsub_evt):
        ballid = pubsub_evt.data
        for i in range(0, ballid):
            self.staticballs[i].SetVisibility(0)
        self.UpdateRender()

    def ShowAllMarkers(self, pubsub_evt):
        ballid = pubsub_evt.data
        for i in range(0, ballid):
            self.staticballs[i].SetVisibility(1)
        self.UpdateRender()

    def RemoveAllMarkers(self, pubsub_evt):
        ballid = pubsub_evt.data
        for i in range(0, ballid):
            self.ren.RemoveActor(self.staticballs[i])
        self.staticballs = []
        self.UpdateRender()

    def RemoveMarker(self, pubsub_evt):
        index = pubsub_evt.data
        for i in reversed(index):
            self.ren.RemoveActor(self.staticballs[i])
            del self.staticballs[i]
            self.ball_id = self.ball_id - 1
        self.UpdateRender()

    def BlinkMarker(self, pubsub_evt):
        if self.timer:
            self.timer.Stop()
            self.staticballs[self.index].SetVisibility(1)
        self.index = pubsub_evt.data
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.blink, self.timer)
        self.timer.Start(500)
        self.timer_count = 0

    def blink(self, evt):
        self.staticballs[self.index].SetVisibility(int(self.timer_count % 2))
        self.Refresh()
        self.timer_count += 1

    def StopBlinkMarker(self, pubsub_evt):
        if self.timer:
            self.timer.Stop()
            if pubsub_evt.data == None:
                self.staticballs[self.index].SetVisibility(1)
                self.Refresh()
            self.index = False

    def CreateBallReference(self):
        """
        Red sphere on volume visualization to reference center of
        cross in slice planes.
        The sphere's radius will be scale times bigger than the average of
        image spacing values.
        """
        scale = 3.0
        proj = prj.Project()
        s = proj.spacing
        r = (s[0] + s[1] + s[2]) / 3.0 * scale

        ball_source = vtk.vtkSphereSource()
        ball_source.SetRadius(r)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_source.GetOutputPort())

        self.ball_actor = vtk.vtkActor()
        self.ball_actor.SetMapper(mapper)
        self.ball_actor.GetProperty().SetColor(1, 0, 0)

        self.ren.AddActor(self.ball_actor)

    def ActivateBallReference(self):
        self._mode_cross = True
        self._ball_ref_visibility = True
        if self._to_show_ball:
            if not self.ball_actor:
                self.CreateBallReference()

    def RemoveBallReference(self):
        self._mode_cross = False
        self._ball_ref_visibility = False
        if self.ball_actor:
            self.ren.RemoveActor(self.ball_actor)
            self.ball_actor = None

    def SetBallReferencePosition(self, pubsub_evt):
        if self._to_show_ball:
            if not self.ball_actor:
                self.ActivateBallReference()

            coord = pubsub_evt.data
            x, y, z = bases.flip_x(coord)
            self.ball_actor.SetPosition(x, y, z)

        else:
            self.RemoveBallReference()

    def __bind_events_wx(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        pass

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
              const.STATE_SPIN:
                    {
                    "MouseMoveEvent": self.OnSpinMove,
                    "LeftButtonPressEvent": self.OnSpinClick,
                    "LeftButtonReleaseEvent": self.OnReleaseSpinClick,
                    },
              const.STATE_WL:
                    { 
                    "MouseMoveEvent": self.OnWindowLevelMove,
                    "LeftButtonPressEvent": self.OnWindowLevelClick,
                    "LeftButtonReleaseEvent":self.OnWindowLevelRelease
                    },
              const.STATE_DEFAULT:
                    {
                    },
              const.VOLUME_STATE_SEED:
                    {
                    "LeftButtonPressEvent": self.OnInsertSeed
                    },
              const.STATE_MEASURE_DISTANCE:
                  {
                  "LeftButtonPressEvent": self.OnInsertLinearMeasurePoint
                  },
              const.STATE_MEASURE_ANGLE:
                  {
                  "LeftButtonPressEvent": self.OnInsertAngularMeasurePoint
                  }
              }

        if self._last_state in (const.STATE_MEASURE_DISTANCE,
                const.STATE_MEASURE_ANGLE):
            if self.measures and not self.measures[-1].text_actor:
                del self.measures[-1]

        if state == const.STATE_WL:
            self.on_wl = True
            if self.raycasting_volume:
                self.text.Show()
                self.interactor.Render()
        else:
            self.on_wl = False
            self.text.Hide()
            self.interactor.Render()

        if state in (const.STATE_MEASURE_DISTANCE,
                const.STATE_MEASURE_ANGLE):
            self.interactor.SetPicker(self.measure_picker)

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

        self._last_state = state

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

    def OnWindowLevelMove(self, obj, evt):
        if self.onclick and self.raycasting_volume:
            mouse_x, mouse_y = self.interactor.GetEventPosition()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            Publisher.sendMessage('Set raycasting relative window and level',
                (diff_x, diff_y))
            Publisher.sendMessage('Refresh raycasting widget points', None)
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

    def OnEnableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        if (state in const.VOLUME_STYLES):
            new_state = self.interaction_style.AddState(state)
            self.SetInteractorStyle(new_state)
        else:
            new_state = self.interaction_style.RemoveState(state)
            self.SetInteractorStyle(new_state)

    def OnDisableStyle(self, pubsub_evt):
        state = pubsub_evt.data
        new_state = self.interaction_style.RemoveState(state)
        self.SetInteractorStyle(new_state)

    def ResetCamClippingRange(self, pubsub_evt):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()

    def SetVolumeCameraState(self, pubsub_evt):
        self.camera_state = pubsub_evt.data

    def SetVolumeCamera(self, pubsub_evt):
        if self.camera_state:
            #TODO: exclude dependency on initial focus
            cam_focus = np.array(bases.flip_x(pubsub_evt.data))
            cam = self.ren.GetActiveCamera()

            if self.initial_focus is None:
                self.initial_focus = np.array(cam.GetFocalPoint())

            cam_pos0 = np.array(cam.GetPosition())
            cam_focus0 = np.array(cam.GetFocalPoint())

            v0 = cam_pos0 - cam_focus0
            v0n = np.sqrt(inner1d(v0, v0))

            v1 = (cam_focus - self.initial_focus)
            v1n = np.sqrt(inner1d(v1, v1))
            if not v1n:
                v1n = 1.0
            cam_pos = (v1/v1n)*v0n + cam_focus

            cam.SetFocalPoint(cam_focus)
            cam.SetPosition(cam_pos)

        # It works without doing the reset. Check with trackers if there is any difference.
        # Need to be outside condition for sphere marker position update
        # self.ren.ResetCameraClippingRange()
        # self.ren.ResetCamera()
        #self.interactor.Render()
        self.Refresh()

    def OnExportSurface(self, pubsub_evt):
        filename, filetype = pubsub_evt.data
        if filetype not in (const.FILETYPE_STL,
                            const.FILETYPE_VTP,
                            const.FILETYPE_PLY,
                            const.FILETYPE_STL_ASCII):
            if _has_win32api:
                utils.touch(filename)
                win_filename = os.path.join(filename)
                self._export_surface(win_filename.encode(const.FS_ENCODE), filetype)
            else:
                self._export_surface(filename, filetype)

    def _export_surface(self, filename, filetype):
        fileprefix = filename.split(".")[-2]
        renwin = self.interactor.GetRenderWindow()

        if filetype == const.FILETYPE_RIB:
            writer = vtk.vtkRIBExporter()
            writer.SetFilePrefix(fileprefix)
            writer.SetTexturePrefix(fileprefix)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_VRML:
            writer = vtk.vtkVRMLExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_X3D:
            writer = vtk.vtkX3DExporter()
            writer.SetInput(renwin)
            writer.SetFileName(filename)
            writer.Update()
            writer.Write()
        elif filetype == const.FILETYPE_OBJ:
            writer = vtk.vtkOBJExporter()
            writer.SetFilePrefix(fileprefix)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_IV:
            writer = vtk.vtkIVExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
            writer.Write()

    def OnEnableBrightContrast(self, pubsub_evt):
        style = self.style
        style.AddObserver("MouseMoveEvent", self.OnMove)
        style.AddObserver("LeftButtonPressEvent", self.OnClick)
        style.AddObserver("LeftButtonReleaseEvent", self.OnRelease)

    def OnDisableBrightContrast(self, pubsub_evt):
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        self.style = style

    def OnSetWindowLevelText(self, pubsub_evt):
        if self.raycasting_volume:
            ww, wl = pubsub_evt.data
            self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

    def OnShowRaycasting(self, pubsub_evt):
        if not self.raycasting_volume:
            self.raycasting_volume = True
            self._to_show_ball += 1
            self._check_and_set_ball_visibility()
            if self.on_wl:
                self.text.Show()

    def OnHideRaycasting(self, pubsub_evt):
        self.raycasting_volume = False
        self.text.Hide()
        self._to_show_ball -= 1
        self._check_and_set_ball_visibility()

    def OnSize(self, evt):
        self.UpdateRender()
        self.Refresh()
        self.interactor.UpdateWindowUI()
        self.interactor.Update()
        evt.Skip()

    def ChangeBackgroundColour(self, pubsub_evt):
        colour = pubsub_evt.data
        self.ren.SetBackground(colour)
        self.UpdateRender()

    def LoadActor(self, pubsub_evt):
        actor = pubsub_evt.data
        self.added_actor = 1
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
        self._to_show_ball += 1
        self._check_and_set_ball_visibility()

    def RemoveActor(self, pubsub_evt):
        utils.debug("RemoveActor")
        actor = pubsub_evt.data
        ren = self.ren
        ren.RemoveActor(actor)
        self.interactor.Render()
        self._to_show_ball -= 1
        self._check_and_set_ball_visibility()

    def RemoveAllActor(self, pubsub_evt):
        utils.debug("RemoveAllActor")
        self.ren.RemoveAllProps()
        Publisher.sendMessage('Render volume viewer')

    def LoadSlicePlane(self, pubsub_evt):
        self.slice_plane = SlicePlane()

    def LoadVolume(self, pubsub_evt):
        self.raycasting_volume = True
        self._to_show_ball += 1

        volume = pubsub_evt.data[0]
        colour = pubsub_evt.data[1]
        ww, wl = pubsub_evt.data[2]

        self.light = self.ren.GetLights().GetNextItem()

        self.ren.AddVolume(volume)
        self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

        if self.on_wl:
            self.text.Show()
        else:
            self.text.Hide()

        self.ren.SetBackground(colour)

        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
        else:
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()

        self._check_and_set_ball_visibility()
        self.UpdateRender()

    def UnloadVolume(self, pubsub_evt):
        volume = pubsub_evt.data
        self.ren.RemoveVolume(volume)
        del volume
        self.raycasting_volume = False
        self._to_show_ball -= 1
        self._check_and_set_ball_visibility()

    def OnSetViewAngle(self, evt_pubsub):
        view = evt_pubsub.data
        self.SetViewAngle(view)

    def SetViewAngle(self, view):
        cam = self.ren.GetActiveCamera()
        cam.SetFocalPoint(0,0,0)

        proj = prj.Project()
        orig_orien = proj.original_orientation

        xv,yv,zv = const.VOLUME_POSITION[const.AXIAL][0][view]
        xp,yp,zp = const.VOLUME_POSITION[const.AXIAL][1][view]

        cam.SetViewUp(xv,yv,zv)
        cam.SetPosition(xp,yp,zp)

        self.ren.ResetCameraClippingRange() 
        self.ren.ResetCamera()
        self.interactor.Render()

    def ShowOrientationCube(self):
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

    def UpdateRender(self, evt_pubsub=None):
        self.interactor.Render()

    def SetWidgetInteractor(self, evt_pubsub=None):
        evt_pubsub.data.SetInteractor(self.interactor._Iren)

    def AppendActor(self, evt_pubsub=None):
        self.ren.AddActor(evt_pubsub.data)

    def OnInsertSeed(self, obj, evt):
        x,y = self.interactor.GetEventPosition()
        #x,y = obj.GetLastEventPosition()
        self.picker.Pick(x, y, 0, self.ren)
        point_id = self.picker.GetPointId()
        self.seed_points.append(point_id)
        self.interactor.Render()

    def OnInsertLinearMeasurePoint(self, obj, evt):
        x,y = self.interactor.GetEventPosition()
        self.measure_picker.Pick(x, y, 0, self.ren)
        x, y, z = self.measure_picker.GetPickPosition()
        
        proj = prj.Project()
        radius = min(proj.spacing) * PROP_MEASURE
        if self.measure_picker.GetActor(): 
            # if not self.measures or self.measures[-1].IsComplete():
                # m = measures.LinearMeasure(self.ren)
                # m.AddPoint(x, y, z)
                # self.measures.append(m)
            # else:
                # m = self.measures[-1]
                # m.AddPoint(x, y, z)
                # if m.IsComplete():
                    # Publisher.sendMessage("Add measure to list", 
                            # (u"3D", _(u"%.3f mm" % m.GetValue())))
            Publisher.sendMessage("Add measurement point",
                    ((x, y,z), const.LINEAR, const.SURFACE, radius))
            self.interactor.Render()

    def OnInsertAngularMeasurePoint(self, obj, evt):
        x,y = self.interactor.GetEventPosition()
        self.measure_picker.Pick(x, y, 0, self.ren)
        x, y, z = self.measure_picker.GetPickPosition()

        proj = prj.Project()
        radius = min(proj.spacing) * PROP_MEASURE
        if self.measure_picker.GetActor(): 
            # if not self.measures or self.measures[-1].IsComplete():
                # m = measures.AngularMeasure(self.ren)
                # m.AddPoint(x, y, z)
                # self.measures.append(m)
            # else:
                # m = self.measures[-1]
                # m.AddPoint(x, y, z)
                # if m.IsComplete():
                    # index = len(self.measures) - 1
                    # name = "M"
                    # colour = m.colour
                    # type_ = _("Angular")
                    # location = u"3D"
                    # value = u"%.2f˚"% m.GetValue()
                    # msg =  'Update measurement info in GUI',
                    # Publisher.sendMessage(msg,
                                               # (index, name, colour,
                                                # type_, location,
                                                # value))
            Publisher.sendMessage("Add measurement point",
                    ((x, y,z), const.ANGULAR, const.SURFACE, radius))
            self.interactor.Render()

    def Reposition3DPlane(self, evt_pubsub):
        position = evt_pubsub.data
        if not(self.added_actor) and not(self.raycasting_volume):
            if not(self.repositioned_axial_plan) and (position == 'Axial'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_axial_plan = 1

            elif not(self.repositioned_sagital_plan) and (position == 'Sagital'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_sagital_plan = 1

            elif not(self.repositioned_coronal_plan) and (position == 'Coronal'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_coronal_plan = 1

    def _check_and_set_ball_visibility(self):
        #TODO: When creating Raycasting volume and cross is pressed, it is not
        # automatically creating the ball reference.
        if self._mode_cross:
            if self._to_show_ball > 0 and not self._ball_ref_visibility:
                self.ActivateBallReference()
                self.interactor.Render()
            elif not self._to_show_ball and self._ball_ref_visibility:
                self.RemoveBallReference()
                self.interactor.Render()

class SlicePlane:
    def __init__(self):
        project = prj.Project()
        self.original_orientation = project.original_orientation
        self.Create()
        self.enabled = False
        self.__bind_evt()

    def __bind_evt(self):
        Publisher.subscribe(self.Enable, 'Enable plane')
        Publisher.subscribe(self.Disable, 'Disable plane')
        Publisher.subscribe(self.ChangeSlice, 'Change slice from slice plane')
        Publisher.subscribe(self.UpdateAllSlice, 'Update all slice')

    def Create(self):
        plane_x = self.plane_x = vtk.vtkImagePlaneWidget()
        plane_x.InteractionOff()
        #Publisher.sendMessage('Input Image in the widget', 
                                                #(plane_x, 'SAGITAL'))
        plane_x.SetPlaneOrientationToXAxes()
        plane_x.TextureVisibilityOn()
        plane_x.SetLeftButtonAction(0)
        plane_x.SetRightButtonAction(0)
        plane_x.SetMiddleButtonAction(0)
        cursor_property = plane_x.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        plane_y = self.plane_y = vtk.vtkImagePlaneWidget()
        plane_y.DisplayTextOff()
        #Publisher.sendMessage('Input Image in the widget', 
                                                #(plane_y, 'CORONAL'))
        plane_y.SetPlaneOrientationToYAxes()
        plane_y.TextureVisibilityOn()
        plane_y.SetLeftButtonAction(0)
        plane_y.SetRightButtonAction(0)
        plane_y.SetMiddleButtonAction(0)
        prop1 = plane_y.GetPlaneProperty()
        cursor_property = plane_y.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        plane_z = self.plane_z = vtk.vtkImagePlaneWidget()
        plane_z.InteractionOff()
        #Publisher.sendMessage('Input Image in the widget', 
                                                #(plane_z, 'AXIAL'))
        plane_z.SetPlaneOrientationToZAxes()
        plane_z.TextureVisibilityOn()
        plane_z.SetLeftButtonAction(0)
        plane_z.SetRightButtonAction(0)
        plane_z.SetMiddleButtonAction(0)
       
        cursor_property = plane_z.GetCursorProperty()
        cursor_property.SetOpacity(0) 


        prop3 = plane_z.GetPlaneProperty()
        prop3.SetColor(1, 0, 0)
        
        selected_prop3 = plane_z.GetSelectedPlaneProperty() 
        selected_prop3.SetColor(1,0,0)
    
        prop1 = plane_x.GetPlaneProperty()
        prop1.SetColor(0, 0, 1)

        selected_prop1 = plane_x.GetSelectedPlaneProperty()           
        selected_prop1.SetColor(0, 0, 1)
        
        prop2 = plane_y.GetPlaneProperty()
        prop2.SetColor(0, 1, 0)

        selected_prop2 = plane_y.GetSelectedPlaneProperty()           
        selected_prop2.SetColor(0, 1, 0)

        Publisher.sendMessage('Set Widget Interactor', plane_x)
        Publisher.sendMessage('Set Widget Interactor', plane_y)
        Publisher.sendMessage('Set Widget Interactor', plane_z)

        self.Render()

    def Enable(self, evt_pubsub=None):
        if (evt_pubsub):
            label = evt_pubsub.data
            if(label == "Axial"):
                self.plane_z.On()
            elif(label == "Coronal"):
                self.plane_y.On()
            elif(label == "Sagital"):
                self.plane_x.On()
        
            Publisher.sendMessage('Reposition 3D Plane', label)

        else:
            self.plane_z.On()
            self.plane_x.On()
            self.plane_y.On()
            Publisher.sendMessage('Set volume view angle', const.VOL_ISO)
        self.Render()

    def Disable(self, evt_pubsub=None):
        if (evt_pubsub):
            label = evt_pubsub.data
            if(label == "Axial"):
                self.plane_z.Off()
            elif(label == "Coronal"):
                self.plane_y.Off()
            elif(label == "Sagital"):
                self.plane_x.Off()
        else:
            self.plane_z.Off()
            self.plane_x.Off()
            self.plane_y.Off()

        self.Render()

    def Render(self):
        Publisher.sendMessage('Render volume viewer')    

    def ChangeSlice(self, pubsub_evt = None):
        orientation, number = pubsub_evt.data

        if  orientation == "CORONAL" and self.plane_y.GetEnabled():
            Publisher.sendMessage('Update slice 3D', (self.plane_y,orientation))
            self.Render()
        elif orientation == "SAGITAL" and self.plane_x.GetEnabled():
            Publisher.sendMessage('Update slice 3D', (self.plane_x,orientation))
            self.Render()
        elif orientation == 'AXIAL' and self.plane_z.GetEnabled() :
            Publisher.sendMessage('Update slice 3D', (self.plane_z,orientation))
            self.Render()

    def UpdateAllSlice(self, pubsub_evt):
        Publisher.sendMessage('Update slice 3D', (self.plane_y,"CORONAL"))
        Publisher.sendMessage('Update slice 3D', (self.plane_x,"SAGITAL"))
        Publisher.sendMessage('Update slice 3D', (self.plane_z,"AXIAL"))
               

    def DeletePlanes(self):
        del self.plane_x
        del self.plane_y
        del self.plane_z 
    

