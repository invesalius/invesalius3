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

from math import cos, sin
import os
import sys

import numpy as np
from numpy.core.umath_tests import inner1d
import wx
import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from wx.lib.pubsub import pub as Publisher
import random
from scipy.spatial import distance

import invesalius.constants as const
import invesalius.data.bases as bases
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.project as prj
import invesalius.style as st
import invesalius.utils as utils

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

        # axes = vtk.vtkAxesActor()
        # axes.SetXAxisLabelText('x')
        # axes.SetYAxisLabelText('y')
        # axes.SetZAxisLabelText('z')
        # axes.SetTotalLength(50, 50, 50)
        #
        # self.ren.AddActor(axes)


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

        self.camera_state = const.CAM_MODE

        self.nav_status = False

        self.ball_actor = None
        self.obj_actor = None
        self.obj_axes = None
        self.obj_name = False
        self.obj_state = None
        self.obj_actor_list = None
        self.arrow_actor_list = None

        # self.obj_axes = None

        self._mode_cross = False
        self._to_show_ball = 0
        self._ball_ref_visibility = False

        self.sen1 = False
        self.sen2 = False

        self.timer = False
        self.index = False

        self.target_coord = None
        self.aim_actor = None
        self.dummy_coil_actor = None
        self.target_mode = False
        self.anglethreshold = const.COIL_ANGLES_THRESHOLD
        self.distthreshold = const.COIL_COORD_THRESHOLD

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
        Publisher.subscribe(self.SetVolumeCamera, 'Co-registered points')
        # Publisher.subscribe(self.SetVolumeCamera, 'Set camera in volume')
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

        # Related to object tracking during neuronavigation
        Publisher.subscribe(self.OnNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateObjectOrientation, 'Update object matrix')
        Publisher.subscribe(self.UpdateTrackObjectState, 'Update track object state')
        Publisher.subscribe(self.UpdateShowObjectState, 'Update show object state')

        Publisher.subscribe(self.ActivateTargetMode, 'Target navigation mode')
        Publisher.subscribe(self.OnUpdateObjectTargetGuide, 'Update object matrix')
        Publisher.subscribe(self.OnUpdateTargetCoordinates, 'Update target')
        Publisher.subscribe(self.OnRemoveTarget, 'Disable or enable coil tracker')
        # Publisher.subscribe(self.UpdateObjectTargetView, 'Co-registered points')
        Publisher.subscribe(self.OnTargetMarkerTransparency, 'Set target transparency')
        Publisher.subscribe(self.OnUpdateAngleThreshold, 'Update angle threshold')
        Publisher.subscribe(self.OnUpdateDistThreshold, 'Update dist threshold')

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

    def _check_ball_reference(self, style):
        if style == const.SLICE_STATE_CROSS:
            self._mode_cross = True
            self._check_and_set_ball_visibility()
            self.interactor.Render()

    def _uncheck_ball_reference(self, style):
        if style == const.SLICE_STATE_CROSS:
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
        id, filename, filetype = pubsub_evt.data
        if id == const.VOLUME:
            Publisher.sendMessage('Begin busy cursor')
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)
                self._export_picture(id, win_filename, filetype)
            else:
                self._export_picture(id, filename, filetype)
            Publisher.sendMessage('End busy cursor')

    def _export_picture(self, id, filename, filetype):
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


    def OnCloseProject(self):
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

    def OnHideText(self):
        self.text.Hide()
        self.interactor.Render()

    def OnShowText(self):
        if self.on_wl:
            self.text.Show()
            self.interactor.Render()

    def AddActors(self, actors):
        "Inserting actors"
        for actor in actors:
            self.ren.AddActor(actor)

    def RemoveVolume(self, pub_evt):
        volumes = self.ren.GetVolumes()
        if (volumes.GetNumberOfItems()):
            self.ren.RemoveVolume(volumes.GetLastProp())
            self.interactor.Render()
            self._to_show_ball -= 1
            self._check_and_set_ball_visibility()

    def RemoveActors(self, actors):
        "Remove a list of actors"
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
        Markers created by navigation tools and rendered in volume viewer.
        """
        self.ball_id = pubsub_evt.data[0]
        ballsize = pubsub_evt.data[1]
        ballcolour = pubsub_evt.data[2][:3]
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
        self.Bind(wx.EVT_TIMER, self.OnBlinkMarker, self.timer)
        self.timer.Start(500)
        self.timer_count = 0

    def OnBlinkMarker(self, evt):
        self.staticballs[self.index].SetVisibility(int(self.timer_count % 2))
        self.Refresh()
        self.timer_count += 1

    def StopBlinkMarker(self, pubsub_evt):
        if self.timer:
            self.timer.Stop()
            if pubsub_evt.data is None:
                self.staticballs[self.index].SetVisibility(1)
                self.Refresh()
            self.index = False

    def OnTargetMarkerTransparency(self, pubsub_evt):
        status = pubsub_evt.data[0]
        index = pubsub_evt.data[1]
        if status:
            self.staticballs[index].GetProperty().SetOpacity(1)
            # self.staticballs[index].GetProperty().SetOpacity(0.4)
        else:
            self.staticballs[index].GetProperty().SetOpacity(1)

    def OnUpdateAngleThreshold(self, pubsub_evt):
        self.anglethreshold = pubsub_evt.data

    def OnUpdateDistThreshold(self, pubsub_evt):
        self.distthreshold = pubsub_evt.data

    def ActivateTargetMode(self, pubsub_evt):
        self.target_mode = pubsub_evt.data
        if self.target_coord and self.target_mode:
            self.CreateTargetAim()

            # Create a line
            self.ren.SetViewport(0, 0, 0.75, 1)
            self.ren2 = vtk.vtkRenderer()

            self.interactor.GetRenderWindow().AddRenderer(self.ren2)
            self.ren2.SetViewport(0.75, 0, 1, 1)
            self.CreateTextDistance()

            obj_polydata = self.CreateObjectPolyData(self.obj_name)

            normals = vtk.vtkPolyDataNormals()
            normals.SetInputData(obj_polydata)
            normals.SetFeatureAngle(80)
            normals.AutoOrientNormalsOn()
            normals.Update()

            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(normals.GetOutput())
            mapper.ScalarVisibilityOff()
            mapper.ImmediateModeRenderingOn()  # improve performance

            obj_roll = vtk.vtkActor()
            obj_roll.SetMapper(mapper)
            obj_roll.SetPosition(0, 25, -30)
            obj_roll.RotateX(-60)
            obj_roll.RotateZ(180)

            obj_yaw = vtk.vtkActor()
            obj_yaw.SetMapper(mapper)
            obj_yaw.SetPosition(0, -115, 5)
            obj_yaw.RotateZ(180)

            obj_pitch = vtk.vtkActor()
            obj_pitch.SetMapper(mapper)
            obj_pitch.SetPosition(5, -265, 5)
            obj_pitch.RotateY(90)
            obj_pitch.RotateZ(180)

            arrow_roll_z1 = self.CreateArrowActor([-50, -35, 12], [-50, -35, 50])
            arrow_roll_z1.GetProperty().SetColor(1, 1, 0)
            arrow_roll_z1.RotateX(-60)
            arrow_roll_z1.RotateZ(180)
            arrow_roll_z2 = self.CreateArrowActor([50, -35, 0], [50, -35, -50])
            arrow_roll_z2.GetProperty().SetColor(1, 1, 0)
            arrow_roll_z2.RotateX(-60)
            arrow_roll_z2.RotateZ(180)

            arrow_yaw_y1 = self.CreateArrowActor([-50, -35, 0], [-50, 5, 0])
            arrow_yaw_y1.GetProperty().SetColor(0, 1, 0)
            arrow_yaw_y1.SetPosition(0, -150, 0)
            arrow_yaw_y1.RotateZ(180)
            arrow_yaw_y2 = self.CreateArrowActor([50, -35, 0], [50, -75, 0])
            arrow_yaw_y2.GetProperty().SetColor(0, 1, 0)
            arrow_yaw_y2.SetPosition(0, -150, 0)
            arrow_yaw_y2.RotateZ(180)

            arrow_pitch_x1 = self.CreateArrowActor([0, 65, 38], [0, 65, 68])
            arrow_pitch_x1.GetProperty().SetColor(1, 0, 0)
            arrow_pitch_x1.SetPosition(0, -300, 0)
            arrow_pitch_x1.RotateY(90)
            arrow_pitch_x1.RotateZ(180)
            arrow_pitch_x2 = self.CreateArrowActor([0, -55, 5], [0, -55, -30])
            arrow_pitch_x2.GetProperty().SetColor(1, 0, 0)
            arrow_pitch_x2.SetPosition(0, -300, 0)
            arrow_pitch_x2.RotateY(90)
            arrow_pitch_x2.RotateZ(180)

            self.obj_actor_list = obj_roll, obj_yaw, obj_pitch
            self.arrow_actor_list = arrow_roll_z1, arrow_roll_z2, arrow_yaw_y1, arrow_yaw_y2,\
                                     arrow_pitch_x1, arrow_pitch_x2

            for ind in self.obj_actor_list:
                self.ren2.AddActor(ind)

            for ind in self.arrow_actor_list:
                self.ren2.AddActor(ind)

            self.ren.ResetCamera()
            self.SetCameraTarget()
            #self.ren.GetActiveCamera().Zoom(4)

            self.ren2.ResetCamera()
            self.ren2.GetActiveCamera().Zoom(2)
            self.ren2.InteractiveOff()
            self.interactor.Render()

        else:
            self.DisableCoilTracker()

    def OnUpdateObjectTargetGuide(self, pubsub_evt):
        coord = pubsub_evt.data[1]
        if self.target_coord and self.target_mode:

            target_dist = distance.euclidean(coord[0:3],
                                             (self.target_coord[0], -self.target_coord[1], self.target_coord[2]))

            # self.txt.SetCoilDistanceValue(target_dist)
            self.textSource.SetText('Dist: ' + str("{:06.2f}".format(target_dist)) + ' mm')
            self.ren.ResetCamera()
            self.SetCameraTarget()
            if target_dist > 100:
                target_dist = 100
            # ((-0.0404*dst) + 5.0404) is the linear equation to normalize the zoom between 1 and 5 times with
            # the distance between 1 and 100 mm
            self.ren.GetActiveCamera().Zoom((-0.0404 * target_dist) + 5.0404)

            if target_dist <= self.distthreshold:
                thrdist = True
                self.aim_actor.GetProperty().SetColor(0, 1, 0)
            else:
                thrdist = False
                self.aim_actor.GetProperty().SetColor(1, 1, 1)

            coordx = self.target_coord[3] - coord[3]
            if coordx > const.ARROW_UPPER_LIMIT:
                coordx = const.ARROW_UPPER_LIMIT
            elif coordx < -const.ARROW_UPPER_LIMIT:
                coordx = -const.ARROW_UPPER_LIMIT
            coordx = const.ARROW_SCALE * coordx

            coordy = self.target_coord[4] - coord[4]
            if coordy > const.ARROW_UPPER_LIMIT:
                coordy = const.ARROW_UPPER_LIMIT
            elif coordy < -const.ARROW_UPPER_LIMIT:
                coordy = -const.ARROW_UPPER_LIMIT
            coordy = const.ARROW_SCALE * coordy

            coordz = self.target_coord[5] - coord[5]
            if coordz > const.ARROW_UPPER_LIMIT:
                coordz = const.ARROW_UPPER_LIMIT
            elif coordz < -const.ARROW_UPPER_LIMIT:
                coordz = -const.ARROW_UPPER_LIMIT
            coordz = const.ARROW_SCALE * coordz

            for ind in self.arrow_actor_list:
                self.ren2.RemoveActor(ind)

            if self.anglethreshold * const.ARROW_SCALE > coordx > -self.anglethreshold * const.ARROW_SCALE:
                thrcoordx = True
                self.obj_actor_list[0].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordx = False
                self.obj_actor_list[0].GetProperty().SetColor(1, 1, 1)

            offset = 5

            arrow_roll_x1 = self.CreateArrowActor([-55, -35, offset], [-55, -35, offset - coordx])
            arrow_roll_x1.RotateX(-60)
            arrow_roll_x1.RotateZ(180)
            arrow_roll_x1.GetProperty().SetColor(1, 1, 0)

            arrow_roll_x2 = self.CreateArrowActor([55, -35, offset], [55, -35, offset + coordx])
            arrow_roll_x2.RotateX(-60)
            arrow_roll_x2.RotateZ(180)
            arrow_roll_x2.GetProperty().SetColor(1, 1, 0)

            if self.anglethreshold * const.ARROW_SCALE > coordz > -self.anglethreshold * const.ARROW_SCALE:
                thrcoordz = True
                self.obj_actor_list[1].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordz = False
                self.obj_actor_list[1].GetProperty().SetColor(1, 1, 1)

            offset = -35

            arrow_yaw_z1 = self.CreateArrowActor([-55, offset, 0], [-55, offset - coordz, 0])
            arrow_yaw_z1.SetPosition(0, -150, 0)
            arrow_yaw_z1.RotateZ(180)
            arrow_yaw_z1.GetProperty().SetColor(0, 1, 0)

            arrow_yaw_z2 = self.CreateArrowActor([55, offset, 0], [55, offset + coordz, 0])
            arrow_yaw_z2.SetPosition(0, -150, 0)
            arrow_yaw_z2.RotateZ(180)
            arrow_yaw_z2.GetProperty().SetColor(0, 1, 0)

            if self.anglethreshold * const.ARROW_SCALE > coordy > -self.anglethreshold * const.ARROW_SCALE:
                thrcoordy = True
                self.obj_actor_list[2].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordy = False
                self.obj_actor_list[2].GetProperty().SetColor(1, 1, 1)

            offset = 38
            arrow_pitch_y1 = self.CreateArrowActor([0, 65, offset], [0, 65, offset + coordy])
            arrow_pitch_y1.SetPosition(0, -300, 0)
            arrow_pitch_y1.RotateY(90)
            arrow_pitch_y1.RotateZ(180)
            arrow_pitch_y1.GetProperty().SetColor(1, 0, 0)

            offset = 5
            arrow_pitch_y2 = self.CreateArrowActor([0, -55, offset], [0, -55, offset - coordy])
            arrow_pitch_y2.SetPosition(0, -300, 0)
            arrow_pitch_y2.RotateY(90)
            arrow_pitch_y2.RotateZ(180)
            arrow_pitch_y2.GetProperty().SetColor(1, 0, 0)

            if thrdist and thrcoordx and thrcoordy and thrcoordz:
                self.dummy_coil_actor.GetProperty().SetColor(0, 1, 0)
            else:
                self.dummy_coil_actor.GetProperty().SetColor(1, 1, 1)

            self.arrow_actor_list = arrow_roll_x1, arrow_roll_x2, arrow_yaw_z1, arrow_yaw_z2, \
                                    arrow_pitch_y1, arrow_pitch_y2

            for ind in self.arrow_actor_list:
                self.ren2.AddActor(ind)

            self.Refresh()

    def OnUpdateTargetCoordinates(self, pubsub_evt):
        self.target_coord = pubsub_evt.data[0:6]
        self.target_coord[1] = -self.target_coord[1]
        self.CreateTargetAim()

    def OnRemoveTarget(self, pubsub_evt):
        status = pubsub_evt.data
        if not status:
            self.target_mode = None
            self.target_coord = None
            self.RemoveTargetAim()
            self.DisableCoilTracker()

    def CreateTargetAim(self):
        if self.aim_actor:
            self.RemoveTargetAim()
            self.aim_actor = None

        self.textSource = vtk.vtkVectorText()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(self.textSource.GetOutputPort())
        tactor = vtk.vtkFollower()
        tactor.SetMapper(mapper)
        tactor.GetProperty().SetColor(1.0, 0.25, 0.0)
        tactor.SetScale(5)
        tactor.SetPosition(self.target_coord[0]+10, self.target_coord[1]+30, self.target_coord[2]+20)
        self.ren.AddActor(tactor)
        self.tactor = tactor
        tactor.SetCamera(self.ren.GetActiveCamera())


        # v3, M_plane_inv = self.Plane(self.target_coord[0:3], self.pTarget)
        # mat4x4 = vtk.vtkMatrix4x4()
        # for i in range(4):
        #     mat4x4.SetElement(i, 0, M_plane_inv[i][0])
        #     mat4x4.SetElement(i, 1, M_plane_inv[i][1])
        #     mat4x4.SetElement(i, 2, M_plane_inv[i][2])
        #     mat4x4.SetElement(i, 3, M_plane_inv[i][3])

        a, b, g = np.radians(self.target_coord[3:])
        r_ref = tr.euler_matrix(a, b, g, 'sxyz')
        t_ref = tr.translation_matrix(self.target_coord[:3])
        m_img = np.asmatrix(tr.concatenate_matrices(t_ref, r_ref))

        m_img_vtk = vtk.vtkMatrix4x4()

        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        self.m_img_vtk = m_img_vtk

        filename = os.path.join(const.OBJ_DIR, "aim.stl")

        reader = vtk.vtkSTLReader()
        reader.SetFileName(filename)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())

        # Transform the polydata
        transform = vtk.vtkTransform()
        transform.SetMatrix(m_img_vtk)
        #transform.SetMatrix(mat4x4)
        transformPD = vtk.vtkTransformPolyDataFilter()
        transformPD.SetTransform(transform)
        transformPD.SetInputConnection(reader.GetOutputPort())
        transformPD.Update()
        # mapper transform
        mapper.SetInputConnection(transformPD.GetOutputPort())

        aim_actor = vtk.vtkActor()
        aim_actor.SetMapper(mapper)
        aim_actor.GetProperty().SetColor(1, 1, 1)
        aim_actor.GetProperty().SetOpacity(0.6)
        self.aim_actor = aim_actor
        self.ren.AddActor(aim_actor)

        obj_polydata = self.CreateObjectPolyData(os.path.join(const.OBJ_DIR, "magstim_fig8_coil_no_handle.stl"))

        transform = vtk.vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtk.vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        obj_mapper = vtk.vtkPolyDataMapper()
        obj_mapper.SetInputData(normals.GetOutput())
        obj_mapper.ScalarVisibilityOff()
        obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.dummy_coil_actor = vtk.vtkActor()
        self.dummy_coil_actor.SetMapper(obj_mapper)
        self.dummy_coil_actor.GetProperty().SetOpacity(0.4)
        self.dummy_coil_actor.SetVisibility(1)
        self.dummy_coil_actor.SetUserMatrix(m_img_vtk)

        self.ren.AddActor(self.dummy_coil_actor)

        self.Refresh()

    def RemoveTargetAim(self):
        self.ren.RemoveActor(self.aim_actor)
        self.ren.RemoveActor(self.dummy_coil_actor)
        self.ren.RemoveActor(self.tactor)
        self.Refresh()

    def CreateTextDistance(self):
        txt = vtku.Text()
        txt.SetSize(const.TEXT_SIZE_EXTRA_LARGE)
        txt.SetPosition((0.76, 0.05))
        txt.ShadowOff()
        txt.BoldOn()
        self.txt = txt
        self.ren2.AddActor(txt.actor)

    def DisableCoilTracker(self):
        try:
            self.ren.SetViewport(0, 0, 1, 1)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren2)
            self.SetViewAngle(const.VOL_FRONT)
            self.ren.RemoveActor(self.txt.actor)
            self.CreateTargetAim()
            self.interactor.Render()
        except:
            None

    def CreateArrowActor(self, startPoint, endPoint):
        # Compute a basis
        normalizedX = [0 for i in range(3)]
        normalizedY = [0 for i in range(3)]
        normalizedZ = [0 for i in range(3)]

        # The X axis is a vector from start to end
        math = vtk.vtkMath()
        math.Subtract(endPoint, startPoint, normalizedX)
        length = math.Norm(normalizedX)
        math.Normalize(normalizedX)

        # The Z axis is an arbitrary vector cross X
        arbitrary = [0 for i in range(3)]
        arbitrary[0] = random.uniform(-10, 10)
        arbitrary[1] = random.uniform(-10, 10)
        arbitrary[2] = random.uniform(-10, 10)
        math.Cross(normalizedX, arbitrary, normalizedZ)
        math.Normalize(normalizedZ)

        # The Y axis is Z cross X
        math.Cross(normalizedZ, normalizedX, normalizedY)
        matrix = vtk.vtkMatrix4x4()

        # Create the direction cosine matrix
        matrix.Identity()
        for i in range(3):
            matrix.SetElement(i, 0, normalizedX[i])
            matrix.SetElement(i, 1, normalizedY[i])
            matrix.SetElement(i, 2, normalizedZ[i])

        # Apply the transforms arrow 1
        transform_1 = vtk.vtkTransform()
        transform_1.Translate(startPoint)
        transform_1.Concatenate(matrix)
        transform_1.Scale(length, length, length)
        # source
        arrowSource1 = vtk.vtkArrowSource()
        arrowSource1.SetTipResolution(50)
        # Create a mapper and actor
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(arrowSource1.GetOutputPort())
        # Transform the polydata
        transformPD = vtk.vtkTransformPolyDataFilter()
        transformPD.SetTransform(transform_1)
        transformPD.SetInputConnection(arrowSource1.GetOutputPort())
        # mapper transform
        mapper.SetInputConnection(transformPD.GetOutputPort())
        # actor
        actor_arrow = vtk.vtkActor()
        actor_arrow.SetMapper(mapper)

        return actor_arrow

    def CenterOfMass(self):
        proj = prj.Project()
        surface = proj.surface_dict[0].polydata
        barycenter = [0.0, 0.0, 0.0]
        n = surface.GetNumberOfPoints()
        for i in range(n):
            point = surface.GetPoint(i)
            barycenter[0] += point[0]
            barycenter[1] += point[1]
            barycenter[2] += point[2]
        barycenter[0] /= n
        barycenter[1] /= n
        barycenter[2] /= n

        return barycenter

    def Plane(self, x0, pTarget):
        v3 = np.array(pTarget) - x0  # normal to the plane
        v3 = v3 / np.linalg.norm(v3)  # unit vector

        d = np.dot(v3, x0)
        # prevents division by zero.
        if v3[0] == 0.0:
            v3[0] = 1e-09

        x1 = np.array([(d - v3[1] - v3[2]) / v3[0], 1, 1])
        v2 = x1 - x0
        v2 = v2 / np.linalg.norm(v2)  # unit vector
        v1 = np.cross(v3, v2)
        v1 = v1 / np.linalg.norm(v1)  # unit vector
        x2 = x0 + v1
        # calculates the matrix for the change of coordinate systems (from canonical to the plane's).
        # remember that, in np.dot(M,p), even though p is a line vector (e.g.,np.array([1,2,3])), it is treated as a column for the dot multiplication.
        M_plane_inv = np.array([[v1[0], v2[0], v3[0], x0[0]],
                                [v1[1], v2[1], v3[1], x0[1]],
                                [v1[2], v2[2], v3[2], x0[2]],
                                [0, 0, 0, 1]])

        return v3, M_plane_inv

    def SetCameraTarget(self):
        cam_focus = self.target_coord[0:3]
        cam = self.ren.GetActiveCamera()

        oldcamVTK = vtk.vtkMatrix4x4()
        oldcamVTK.DeepCopy(cam.GetViewTransformMatrix())

        newvtk = vtk.vtkMatrix4x4()
        newvtk.Multiply4x4(self.m_img_vtk, oldcamVTK, newvtk)

        transform = vtk.vtkTransform()
        transform.SetMatrix(newvtk)
        transform.Update()
        cam.ApplyTransform(transform)

        cam.Roll(90)

        cam_pos0 = np.array(cam.GetPosition())
        cam_focus0 = np.array(cam.GetFocalPoint())
        v0 = cam_pos0 - cam_focus0
        v0n = np.sqrt(inner1d(v0, v0))

        v1 = (cam_focus[0] - cam_focus0[0], cam_focus[1] - cam_focus0[1], cam_focus[2] - cam_focus0[2])
        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1 / v1n) * v0n + cam_focus
        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)


    def CreateBallReference(self):
        """
        Red sphere on volume visualization to reference center of
        cross in slice planes.
        The sphere's radius will be scale times bigger than the average of
        image spacing values.
        """
        scale = 2.0
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

    def CreateObjectPolyData(self, filename):
        """
        Coil for navigation rendered in volume viewer.
        """
        filename = utils.decode(filename, const.FS_ENCODE)
        if filename:
            if filename.lower().endswith('.stl'):
                reader = vtk.vtkSTLReader()
            elif filename.lower().endswith('.ply'):
                reader = vtk.vtkPLYReader()
            elif filename.lower().endswith('.obj'):
                reader = vtk.vtkOBJReader()
            elif filename.lower().endswith('.vtp'):
                reader = vtk.vtkXMLPolyDataReader()
            else:
                wx.MessageBox(_("File format not reconized by InVesalius"), _("Import surface error"))
                return
        else:
            filename = os.path.join(const.OBJ_DIR, "magstim_fig8_coil.stl")
            reader = vtk.vtkSTLReader()

        if _has_win32api:
            obj_name = win32api.GetShortPathName(filename).encode(const.FS_ENCODE)
        else:
            obj_name = filename.encode(const.FS_ENCODE)

        reader.SetFileName(obj_name)
        reader.Update()
        obj_polydata = reader.GetOutput()

        if obj_polydata.GetNumberOfPoints() == 0:
            wx.MessageBox(_("InVesalius was not able to import this surface"), _("Import surface error"))
            obj_polydata = None

        return obj_polydata

    def AddObjectActor(self, obj_name):
        """
        Coil for navigation rendered in volume viewer.
        """

        obj_polydata = self.CreateObjectPolyData(obj_name)

        transform = vtk.vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtk.vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        obj_mapper = vtk.vtkPolyDataMapper()
        obj_mapper.SetInputData(normals.GetOutput())
        obj_mapper.ScalarVisibilityOff()
        obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.obj_actor = vtk.vtkActor()
        self.obj_actor.SetMapper(obj_mapper)
        self.obj_actor.GetProperty().SetOpacity(0.9)
        self.obj_actor.SetVisibility(0)

        self.ren.AddActor(self.obj_actor)

        # self.obj_axes = vtk.vtkAxesActor()
        # self.obj_axes.SetShaftTypeToCylinder()
        # self.obj_axes.SetXAxisLabelText("x")
        # self.obj_axes.SetYAxisLabelText("y")
        # self.obj_axes.SetZAxisLabelText("z")
        # self.obj_axes.SetTotalLength(50.0, 50.0, 50.0)

        # self.ren.AddActor(self.obj_axes)

    def OnNavigationStatus(self, pubsub_evt):
        self.nav_status = pubsub_evt.data
        self.pTarget = self.CenterOfMass()
        if self.obj_actor and self.nav_status:
            self.obj_actor.SetVisibility(self.obj_state)
            if not self.obj_state:
                self.Refresh()

    def UpdateObjectOrientation(self, pubsub_evt):

        m_img = pubsub_evt.data[0]

        m_img[:3, -1] = np.asmatrix(bases.flip_x_m((m_img[0, -1], m_img[1, -1], m_img[2, -1]))).reshape([3, 1])

        m_img_vtk = vtk.vtkMatrix4x4()

        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        self.obj_actor.SetUserMatrix(m_img_vtk)
        # self.obj_axes.SetUserMatrix(m_rot_vtk)

        self.Refresh()

    def UpdateTrackObjectState(self, pubsub_evt):
        if pubsub_evt.data[0]:
            self.obj_name = pubsub_evt.data[1]

            if not self.obj_actor:
                self.AddObjectActor(self.obj_name)

        else:
            if self.obj_actor:
                self.ren.RemoveActor(self.obj_actor)
                self.obj_actor = None

        self.Refresh()

    def UpdateShowObjectState(self, pubsub_evt):
        self.obj_state = pubsub_evt.data
        if self.obj_actor and not self.obj_state:
            self.obj_actor.SetVisibility(self.obj_state)
            self.Refresh()

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

    def OnEnableStyle(self, style):
        if (style in const.VOLUME_STYLES):
            new_state = self.interaction_style.AddState(style)
            self.SetInteractorStyle(new_state)
        else:
            new_state = self.interaction_style.RemoveState(style)
            self.SetInteractorStyle(new_state)

    def OnDisableStyle(self, style):
        new_state = self.interaction_style.RemoveState(style)
        self.SetInteractorStyle(new_state)

    def ResetCamClippingRange(self, pubsub_evt):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()

    def SetVolumeCameraState(self, pubsub_evt):
        self.camera_state = pubsub_evt.data

    def SetVolumeCamera(self, pubsub_evt):
        if self.camera_state:
            # TODO: exclude dependency on initial focus
            cam_focus = np.array(bases.flip_x(pubsub_evt.data[1][:3]))
            cam = self.ren.GetActiveCamera()

            if self.initial_focus is None:
                self.initial_focus = np.array(cam.GetFocalPoint())

            cam_pos0 = np.array(cam.GetPosition())
            cam_focus0 = np.array(cam.GetFocalPoint())
            v0 = cam_pos0 - cam_focus0
            v0n = np.sqrt(inner1d(v0, v0))

            if self.obj_state:
                v1 = (cam_focus[0] - self.pTarget[0], cam_focus[1] - self.pTarget[1], cam_focus[2] - self.pTarget[2])
            else:
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
                win_filename = win32api.GetShortPathName(filename)
                self._export_surface(win_filename, filetype)
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
        self.ren.SetBackground(colour[:3])
        self.UpdateRender()

    def LoadActor(self, actor):
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

    def RemoveActor(self, actor):
        utils.debug("RemoveActor")
        ren = self.ren
        ren.RemoveActor(actor)
        self.interactor.Render()
        self._to_show_ball -= 1
        self._check_and_set_ball_visibility()

    def RemoveAllActor(self):
        utils.debug("RemoveAllActor")
        self.ren.RemoveAllProps()
        Publisher.sendMessage('Render volume viewer')

    def LoadSlicePlane(self):
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

    def SetWidgetInteractor(self, widget=None):
        widget.SetInteractor(self.interactor._Iren)

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
                                  position=(x, y,z),
                                  type=const.LINEAR,
                                  location=const.SURFACE,
                                  radius=radius)
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
                                  position=(x, y,z),
                                  type=const.ANGULAR,
                                  location=const.SURFACE,
                                  radius=radius)
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

        Publisher.sendMessage('Set Widget Interactor', widget=plane_x)
        Publisher.sendMessage('Set Widget Interactor', widget=plane_y)
        Publisher.sendMessage('Set Widget Interactor', widget=plane_z)

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

    def ChangeSlice(self, orientation, index):
        if  orientation == "CORONAL" and self.plane_y.GetEnabled():
            Publisher.sendMessage('Update slice 3D',
                                  widget=self.plane_y,
                                  orientation=orientation)
            self.Render()
        elif orientation == "SAGITAL" and self.plane_x.GetEnabled():
            Publisher.sendMessage('Update slice 3D', 
                                  widget=self.plane_x,
                                  orientation=orientation)
            self.Render()
        elif orientation == 'AXIAL' and self.plane_z.GetEnabled() :
            Publisher.sendMessage('Update slice 3D',
                                  widget=self.plane_z,
                                  orientation=orientation)
            self.Render()

    def UpdateAllSlice(self):
        Publisher.sendMessage('Update slice 3D',
                              widget=self.plane_y,
                              orientation="CORONAL")
        Publisher.sendMessage('Update slice 3D',
                              widget=self.plane_x,
                              orientation="SAGITAL")
        Publisher.sendMessage('Update slice 3D',
                              widget=self.plane_z,
                              orientation="AXIAL")
               

    def DeletePlanes(self):
        del self.plane_x
        del self.plane_y
        del self.plane_z 
    

