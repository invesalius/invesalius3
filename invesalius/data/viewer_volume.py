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

# from math import cos, sin
import os
import sys
import time

import numpy as np
from numpy.core.umath_tests import inner1d
import wx
import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from invesalius.pubsub import pub as Publisher
import random
from scipy.spatial import distance

from imageio import imsave

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.slice_ as sl
import invesalius.data.styles_3d as styles
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.project as prj
import invesalius.style as st
import invesalius.utils as utils

from invesalius import inv_paths


if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

PROP_MEASURE = 0.8

#  from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX, Polygon

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.interaction_style = st.StyleStateManager()

        self.initial_focus = None

        self.staticballs = []

        self.style = None

        interactor = wxVTKRenderWindowInteractor(self, -1, size = self.GetSize())
        self.interactor = interactor
        self.interactor.SetRenderWhenDisabled(True)

        self.enable_style(const.STATE_DEFAULT)

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
        self.ren = ren

        canvas_renderer = vtk.vtkRenderer()
        canvas_renderer.SetLayer(1)
        canvas_renderer.SetInteractive(0)
        canvas_renderer.PreserveDepthBufferOn()
        self.canvas_renderer = canvas_renderer

        interactor.GetRenderWindow().SetNumberOfLayers(2)
        interactor.GetRenderWindow().AddRenderer(ren)
        interactor.GetRenderWindow().AddRenderer(canvas_renderer)

        self.raycasting_volume = False

        self.onclick = False

        self.text = vtku.TextZero()
        self.text.SetValue("")
        self.text.SetPosition(const.TEXT_POS_LEFT_UP)
        self.ren.AddActor(self.text.actor)

        #  self.polygon = Polygon(None, is_3d=False)

        #  self.canvas = CanvasRendererCTX(self, self.ren, self.canvas_renderer, 'AXIAL')
        #  self.canvas.draw_list.append(self.text)
        #  self.canvas.draw_list.append(self.polygon)
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
        #self.pTarget = [0., 0., 0.]

        # self.obj_axes = None
        self.x_actor = None
        self.y_actor = None
        self.z_actor = None
        self.mark_actor = None
        self.obj_projection_arrow_actor = None
        self.object_orientation_torus_actor = None

        self._mode_cross = False
        self._to_show_ball = 0
        self._ball_ref_visibility = False

        self.probe = False
        self.ref = False
        self.obj = False

        self.timer = False
        self.index = False

        self.target_coord = None
        self.aim_actor = None
        self.dummy_coil_actor = None
        self.target_mode = False
        self.polydata = None
        self.use_default_object = True
        self.anglethreshold = const.COIL_ANGLES_THRESHOLD
        self.distthreshold = const.COIL_COORD_THRESHOLD
        self.angle_arrow_projection_threshold = const.COIL_ANGLE_ARROW_PROJECTION_THRESHOLD

        self.actor_tracts = None
        self.actor_peel = None
        self.seed_offset = const.SEED_OFFSET

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor,
                                 'Load surface actor into viewer')
        Publisher.subscribe(self.RemoveActor,
                                'Remove surface actor from viewer')
        # Publisher.subscribe(self.OnShowSurface, 'Show surface')
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

        Publisher.subscribe(self.SetVolumeCameraState, 'Update volume camera state')

        Publisher.subscribe(self.enable_style, 'Enable style')
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

        Publisher.subscribe(self.UpdateCameraBallPosition, 'Set cross focal point')
        Publisher.subscribe(self._check_ball_reference, 'Enable style')
        Publisher.subscribe(self._uncheck_ball_reference, 'Disable style')

        Publisher.subscribe(self.OnSensors, 'Sensors ID')
        Publisher.subscribe(self.OnRemoveSensorsID, 'Remove sensors ID')

        # Related to marker creation in navigation tools
        Publisher.subscribe(self.AddMarker, 'Add marker')
        Publisher.subscribe(self.HideAllMarkers, 'Hide all markers')
        Publisher.subscribe(self.ShowAllMarkers, 'Show all markers')
        Publisher.subscribe(self.RemoveAllMarkers, 'Remove all markers')
        Publisher.subscribe(self.RemoveMultipleMarkers, 'Remove multiple markers')
        Publisher.subscribe(self.BlinkMarker, 'Blink Marker')
        Publisher.subscribe(self.StopBlinkMarker, 'Stop Blink Marker')
        Publisher.subscribe(self.SetNewColor, 'Set new color')
        Publisher.subscribe(self.SetMarkers, 'Set markers')

        # Related to object tracking during neuronavigation
        Publisher.subscribe(self.OnNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateObjectOrientation, 'Update object matrix')
        Publisher.subscribe(self.UpdateObjectArrowOrientation, 'Update object arrow matrix')
        Publisher.subscribe(self.UpdateTrackObjectState, 'Update track object state')
        Publisher.subscribe(self.UpdateShowObjectState, 'Update show object state')

        Publisher.subscribe(self.ActivateTargetMode, 'Target navigation mode')
        Publisher.subscribe(self.OnUpdateObjectTargetGuide, 'Update object matrix')
        Publisher.subscribe(self.OnUpdateTargetCoordinates, 'Update target')
        Publisher.subscribe(self.OnDisableOrEnableCoilTracker, 'Disable or enable coil tracker')
        Publisher.subscribe(self.OnTargetMarkerTransparency, 'Set target transparency')
        Publisher.subscribe(self.OnUpdateAngleThreshold, 'Update angle threshold')
        Publisher.subscribe(self.OnUpdateDistThreshold, 'Update dist threshold')

        Publisher.subscribe(self.OnUpdateTracts, 'Update tracts')
        Publisher.subscribe(self.OnRemoveTracts, 'Remove tracts')
        Publisher.subscribe(self.UpdateSeedOffset, 'Update seed offset')
        Publisher.subscribe(self.UpdateMarkerOffsetState, 'Update marker offset state')
        Publisher.subscribe(self.UpdateMarkerOffsetPosition, 'Update marker offset')
        Publisher.subscribe(self.AddPeeledSurface, 'Update peel')
        Publisher.subscribe(self.GetPeelCenters, 'Get peel centers and normals')
        Publisher.subscribe(self.Initlocator_viewer, 'Get init locator')

        Publisher.subscribe(self.load_mask_preview, 'Load mask preview')
        Publisher.subscribe(self.remove_mask_preview, 'Remove mask preview')

    def SetStereoMode(self, mode):
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
            # self._check_and_set_ball_visibility()
            #if not self.actor_peel:
            self._ball_ref_visibility = True
            #else:
            #    self._ball_ref_visibility = False
            # if self._to_show_ball:
            if not self.ball_actor: #and not self.actor_peel:
                self.CreateBallReference()
                #self.ball_actor.SetVisibility(1)
            #else:
             #   self.ball_actor.SetVisibility(0)
            self.interactor.Render()

    def _uncheck_ball_reference(self, style):
        if style == const.SLICE_STATE_CROSS:
            self._mode_cross = False
            # self.RemoveBallReference()
            self._ball_ref_visibility = True
            if self.ball_actor:
                self.ren.RemoveActor(self.ball_actor)
                self.ball_actor = None

            self.interactor.Render()

    def OnSensors(self, probe_id, ref_id, obj_id=0):
        if not self.probe:
            self.CreateSensorID()

        if probe_id:
            colour1 = (0, 1, 0)
        else:
            colour1 = (1, 0, 0)
        if ref_id:
            colour2 = (0, 1, 0)
        else:
            colour2 = (1, 0, 0)
        if obj_id:
            colour3 = (0, 1, 0)
        else:
            colour3 = (1, 0, 0)

        self.probe.SetColour(colour1)
        self.ref.SetColour(colour2)
        self.obj.SetColour(colour3)
        self.Refresh()

    def CreateSensorID(self):
        probe = vtku.Text()
        probe.SetSize(const.TEXT_SIZE_LARGE)
        probe.SetPosition((const.X, const.Y))
        probe.ShadowOff()
        probe.SetValue("P")
        self.probe = probe
        self.ren.AddActor(probe.actor)

        ref = vtku.Text()
        ref.SetSize(const.TEXT_SIZE_LARGE)
        ref.SetPosition((const.X+0.04, const.Y))
        ref.ShadowOff()
        ref.SetValue("R")
        self.ref = ref
        self.ren.AddActor(ref.actor)

        obj = vtku.Text()
        obj.SetSize(const.TEXT_SIZE_LARGE)
        obj.SetPosition((const.X+0.08, const.Y))
        obj.ShadowOff()
        obj.SetValue("O")
        self.obj = obj
        self.ren.AddActor(obj.actor)

        self.interactor.Render()

    def OnRemoveSensorsID(self):
        if self.probe:
            self.ren.RemoveActor(self.probe.actor)
            self.ren.RemoveActor(self.ref.actor)
            self.ren.RemoveActor(self.obj.actor)
            self.probe = self.ref = self.obj = False
            self.interactor.Render()

    # def OnShowSurface(self, index, visibility):
    #     if visibility:
    #         self._to_show_ball += 1
    #     else:
    #         self._to_show_ball -= 1
    #     self._check_and_set_ball_visibility()

    def OnStartSeed(self):
        self.seed_points = []

    def OnEndSeed(self):
        Publisher.sendMessage("Create surface from seeds",
                              seeds=self.seed_points)

    def OnExportPicture(self, orientation, filename, filetype):
        if orientation == const.VOLUME:
            Publisher.sendMessage('Begin busy cursor')
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)
                self._export_picture(orientation, win_filename, filetype)
            else:
                self._export_picture(orientation, filename, filetype)
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

    def RemoveVolume(self):
        volumes = self.ren.GetVolumes()
        if (volumes.GetNumberOfItems()):
            self.ren.RemoveVolume(volumes.GetLastProp())
            self.interactor.Render()
            # self._to_show_ball -= 1
            # self._check_and_set_ball_visibility()

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

    def SetMarkers(self, markers):
        """
        Set all markers, overwriting the previous markers.
        """
        self.RemoveAllMarkers(len(self.staticballs))

        target_selected = False
        for marker in markers:

            ball_id = marker["ball_id"]
            size = marker["size"]
            colour = marker["colour"]
            position = marker["position"]
            direction = marker["direction"]
            target = marker["target"]

            self.AddMarker(
                ball_id=ball_id,
                size=size,
                colour=colour,
                coord=position,
            )

            if target:
                Publisher.sendMessage('Update target', coord=position + direction)
                target_selected = True

        if not target_selected:
            self.RemoveTarget()

        self.UpdateRender()

    def AddMarker(self, ball_id, size, colour, coord):
        """
        Markers created by navigation tools and rendered in volume viewer.
        """
        self.ball_id = ball_id
        coord_flip = list(coord)
        coord_flip[1] = -coord_flip[1]

        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(size)
        ball_ref.SetCenter(coord_flip)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtk.vtkProperty()
        prop.SetColor(colour)

        # adding a new actor for the present ball
        self.staticballs.append(vtk.vtkActor())

        self.staticballs[self.ball_id].SetMapper(mapper)
        self.staticballs[self.ball_id].SetProperty(prop)

        self.ren.AddActor(self.staticballs[self.ball_id])
        self.ball_id += 1

        #self.UpdateRender()
        self.Refresh()

    def add_marker(self, coord, color):
        """Simplified version for creating a spherical marker in the 3D scene

        :param coord:
        :param color:
        :return: vtkActor
        """

        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(1.5)
        ball_ref.SetCenter(coord)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtk.vtkProperty()
        prop.SetColor(color)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(prop)
        actor.GetProperty().SetOpacity(1.)

        # ren.AddActor(actor)

        return actor

    def HideAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            self.staticballs[i].SetVisibility(0)
        self.UpdateRender()

    def ShowAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            self.staticballs[i].SetVisibility(1)
        self.UpdateRender()

    def RemoveAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            self.ren.RemoveActor(self.staticballs[i])
        self.staticballs = []
        self.UpdateRender()

    def RemoveMultipleMarkers(self, index):
        for i in reversed(index):
            self.ren.RemoveActor(self.staticballs[i])
            del self.staticballs[i]
            self.ball_id = self.ball_id - 1
        self.UpdateRender()

    def BlinkMarker(self, index):
        if self.timer:
            self.timer.Stop()
            self.staticballs[self.index].SetVisibility(1)
        self.index = index
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnBlinkMarker, self.timer)
        self.timer.Start(500)
        self.timer_count = 0

    def OnBlinkMarker(self, evt):
        self.staticballs[self.index].SetVisibility(int(self.timer_count % 2))
        self.Refresh()
        self.timer_count += 1

    def StopBlinkMarker(self, index=None):
        if self.timer:
            self.timer.Stop()
            if index is None:
                self.staticballs[self.index].SetVisibility(1)
                self.Refresh()
            self.index = False

    def SetNewColor(self, index, color):
        self.staticballs[index].GetProperty().SetColor(color)
        self.Refresh()

    def OnTargetMarkerTransparency(self, status, index):
        if status:
            self.staticballs[index].GetProperty().SetOpacity(1)
            # self.staticballs[index].GetProperty().SetOpacity(0.4)
        else:
            self.staticballs[index].GetProperty().SetOpacity(1)

    def OnUpdateAngleThreshold(self, angle):
        self.anglethreshold = angle

    def OnUpdateDistThreshold(self, dist_threshold):
        self.distthreshold = dist_threshold

    def ActivateTargetMode(self, evt=None, target_mode=None):
        vtk_colors = vtk.vtkNamedColors()
        self.target_mode = target_mode
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
            #mapper.ImmediateModeRenderingOn()  # improve performance

            obj_roll = vtk.vtkActor()
            obj_roll.SetMapper(mapper)
            obj_roll.GetProperty().SetColor(1, 1, 1)
            # obj_roll.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
            # obj_roll.GetProperty().SetSpecular(30)
            # obj_roll.GetProperty().SetSpecularPower(80)
            obj_roll.SetPosition(0, 25, -30)
            obj_roll.RotateX(-60)
            obj_roll.RotateZ(180)

            obj_yaw = vtk.vtkActor()
            obj_yaw.SetMapper(mapper)
            obj_yaw.GetProperty().SetColor(1, 1, 1)
            # obj_yaw.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
            # obj_yaw.GetProperty().SetSpecular(30)
            # obj_yaw.GetProperty().SetSpecularPower(80)
            obj_yaw.SetPosition(0, -115, 5)
            obj_yaw.RotateZ(180)

            obj_pitch = vtk.vtkActor()
            obj_pitch.SetMapper(mapper)
            obj_pitch.GetProperty().SetColor(1, 1, 1)
            # obj_pitch.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
            # obj_pitch.GetProperty().SetSpecular(30)
            # obj_pitch.GetProperty().SetSpecularPower(80)
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

    def OnUpdateObjectTargetGuide(self, m_img, coord):

        vtk_colors = vtk.vtkNamedColors()

        if self.target_coord and self.target_mode:

            target_dist = distance.euclidean(coord[0:3],
                                             (self.target_coord[0], -self.target_coord[1], self.target_coord[2]))

            # self.txt.SetCoilDistanceValue(target_dist)
            self.tdist.SetValue('Distance: ' + str("{:06.2f}".format(target_dist)) + ' mm')
            self.ren.ResetCamera()
            self.SetCameraTarget()
            if target_dist > 100:
                target_dist = 100
            # ((-0.0404*dst) + 5.0404) is the linear equation to normalize the zoom between 1 and 5 times with
            # the distance between 1 and 100 mm
            self.ren.GetActiveCamera().Zoom((-0.0404 * target_dist) + 5.0404)

            if target_dist <= self.distthreshold:
                thrdist = True
                self.aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
            else:
                thrdist = False
                self.aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Yellow'))

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
                # self.obj_actor_list[0].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.obj_actor_list[0].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordx = False
                # self.obj_actor_list[0].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
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
                # self.obj_actor_list[1].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.obj_actor_list[1].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordz = False
                # self.obj_actor_list[1].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
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
                #self.obj_actor_list[2].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.obj_actor_list[2].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordy = False
                #self.obj_actor_list[2].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
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
                self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                Publisher.sendMessage('Coil at target', state=True)
            else:
                self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkOrange'))
                Publisher.sendMessage('Coil at target', state=False)

            self.arrow_actor_list = arrow_roll_x1, arrow_roll_x2, arrow_yaw_z1, arrow_yaw_z2, \
                                    arrow_pitch_y1, arrow_pitch_y2

            for ind in self.arrow_actor_list:
                self.ren2.AddActor(ind)

            self.Refresh()

    def OnUpdateTargetCoordinates(self, coord):
        self.target_coord = coord
        self.target_coord[1] = -self.target_coord[1]
        self.CreateTargetAim()
        Publisher.sendMessage('Target selected', status=True)
        print("Target updated to coordinates {}".format(coord))

    def RemoveTarget(self):
        self.target_mode = None
        self.target_coord = None
        self.RemoveTargetAim()
        Publisher.sendMessage('Target selected', status=False)

    def OnDisableOrEnableCoilTracker(self, status):
        if not status:
            self.RemoveTarget()
            self.DisableCoilTracker()

    def CreateTargetAim(self):
        if self.aim_actor:
            self.RemoveTargetAim()
            self.aim_actor = None

        vtk_colors = vtk.vtkNamedColors()

        m_img = dco.coordinates_to_transformation_matrix(
            position=self.target_coord[:3],
            orientation=self.target_coord[3:],
            axes='sxyz',
        )
        m_img = np.asmatrix(m_img)

        m_img_vtk = vtk.vtkMatrix4x4()

        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        self.m_img_vtk = m_img_vtk

        filename = os.path.join(inv_paths.OBJ_DIR, "aim.stl")

        reader = vtk.vtkSTLReader()
        reader.SetFileName(filename)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())

        # Transform the polydata
        transform = vtk.vtkTransform()
        transform.SetMatrix(m_img_vtk)
        transformPD = vtk.vtkTransformPolyDataFilter()
        transformPD.SetTransform(transform)
        transformPD.SetInputConnection(reader.GetOutputPort())
        transformPD.Update()
        # mapper transform
        mapper.SetInputConnection(transformPD.GetOutputPort())

        aim_actor = vtk.vtkActor()
        aim_actor.SetMapper(mapper)
        aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Yellow'))
        aim_actor.GetProperty().SetSpecular(.2)
        aim_actor.GetProperty().SetSpecularPower(100)
        aim_actor.GetProperty().SetOpacity(1.)
        self.aim_actor = aim_actor
        self.ren.AddActor(aim_actor)

        if self.use_default_object:
            obj_polydata = self.CreateObjectPolyData(os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil_no_handle.stl"))
        else:
            obj_polydata = self.polydata

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
        #obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.dummy_coil_actor = vtk.vtkActor()
        self.dummy_coil_actor.SetMapper(obj_mapper)
        self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkOrange'))
        self.dummy_coil_actor.GetProperty().SetSpecular(0.5)
        self.dummy_coil_actor.GetProperty().SetSpecularPower(10)
        self.dummy_coil_actor.GetProperty().SetOpacity(.3)
        self.dummy_coil_actor.SetVisibility(1)
        self.dummy_coil_actor.SetUserMatrix(m_img_vtk)

        self.ren.AddActor(self.dummy_coil_actor)

        self.Refresh()

    def RemoveTargetAim(self):
        self.ren.RemoveActor(self.aim_actor)
        self.ren.RemoveActor(self.dummy_coil_actor)
        self.Refresh()

    def CreateTextDistance(self):
        tdist = vtku.Text()
        tdist.SetSize(const.TEXT_SIZE_DIST_NAV)
        tdist.SetPosition((const.X, 1.-const.Y))
        tdist.SetVerticalJustificationToBottom()
        tdist.BoldOn()

        self.ren.AddActor(tdist.actor)
        self.tdist = tdist

    def DisableCoilTracker(self):
        try:
            self.ren.SetViewport(0, 0, 1, 1)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren2)
            self.SetViewAngle(const.VOL_FRONT)
            self.ren.RemoveActor(self.tdist.actor)
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
        barycenter = [0.0, 0.0, 0.0]
        proj = prj.Project()
        try:
            surface = proj.surface_dict[0].polydata
        except KeyError:
            print("There is not any surface created")
            return barycenter
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

    # def SetCrossFocalPoint(self, position):
    #     self.UpdateCameraBallPosition(None, position)

    def UpdateCameraBallPosition(self, position):
        #if not self.actor_peel:
        coord_flip = list(position[:3])
        coord_flip[1] = -coord_flip[1]
        self.ball_actor.SetPosition(coord_flip)
        self.SetVolumeCamera(coord_flip)

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
            filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")
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
        vtk_colors = vtk.vtkNamedColors()
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
        #obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.obj_actor = vtk.vtkActor()
        self.obj_actor.SetMapper(obj_mapper)
        self.obj_actor.GetProperty().SetAmbientColor(vtk_colors.GetColor3d('GhostWhite'))
        self.obj_actor.GetProperty().SetSpecular(30)
        self.obj_actor.GetProperty().SetSpecularPower(80)
        self.obj_actor.GetProperty().SetOpacity(.4)
        self.obj_actor.SetVisibility(0)

        self.x_actor = self.add_line([0., 0., 0.], [1., 0., 0.], color=[.0, .0, 1.0])
        self.y_actor = self.add_line([0., 0., 0.], [0., 1., 0.], color=[.0, 1.0, .0])
        self.z_actor = self.add_line([0., 0., 0.], [0., 0., 1.], color=[1.0, .0, .0])

        self.obj_projection_arrow_actor = self.Add_ObjectArrow([0., 0., 0.], [0., 0., 0.], vtk_colors.GetColor3d('Red'),
                                                               8)
        self.object_orientation_torus_actor = self.Add_Torus([0., 0., 0.], [0., 0., 0.],
                                                             vtk_colors.GetColor3d('Red'))

        #self.obj_projection_arrow_actor.SetVisibility(False)
        #self.object_orientation_torus_actor.SetVisibility(False)
        self.ren.AddActor(self.obj_actor)
        self.ren.AddActor(self.x_actor)
        self.ren.AddActor(self.y_actor)
        self.ren.AddActor(self.z_actor)
        self.x_actor.SetVisibility(0)
        self.y_actor.SetVisibility(0)
        self.z_actor.SetVisibility(0)
        #self.ren.AddActor(self.obj_projection_arrow_actor)
        #self.ren.AddActor(self.object_orientation_torus_actor)
        # self.obj_axes = vtk.vtkAxesActor()
        # self.obj_axes.SetShaftTypeToCylinder()
        # self.obj_axes.SetXAxisLabelText("x")
        # self.obj_axes.SetYAxisLabelText("y")
        # self.obj_axes.SetZAxisLabelText("z")
        # self.obj_axes.SetTotalLength(50.0, 50.0, 50.0)

        # self.ren.AddActor(self.obj_axes)

    def Add_Object_Orientation_Disk(self, position, orientation, color=[0.0, 0.0, 1.0]):
        # Create a disk to show target
        disk = vtk.vtkDiskSource()
        disk.SetInnerRadius(5)
        disk.SetOuterRadius(15)
        disk.SetRadialResolution(100)
        disk.SetCircumferentialResolution(100)
        disk.Update()

        disk_mapper = vtk.vtkPolyDataMapper()
        disk_mapper.SetInputData(disk.GetOutput())
        disk_actor = vtk.vtkActor()
        disk_actor.SetMapper(disk_mapper)
        disk_actor.GetProperty().SetColor(color)
        disk_actor.GetProperty().SetOpacity(1)
        disk_actor.SetPosition(position)
        disk_actor.SetOrientation(orientation)

        return disk_actor

    def Add_Torus(self, position, orientation, color=[0.0, 0.0, 1.0]):
        torus = vtk.vtkParametricTorus()
        torus.SetRingRadius(2)
        torus.SetCrossSectionRadius(1)

        torusSource = vtk.vtkParametricFunctionSource()
        torusSource.SetParametricFunction(torus)
        torusSource.Update()

        torusMapper = vtk.vtkPolyDataMapper()
        torusMapper.SetInputConnection(torusSource.GetOutputPort())
        torusMapper.SetScalarRange(0, 360)

        torusActor = vtk.vtkActor()
        torusActor.SetMapper(torusMapper)
        torusActor.GetProperty().SetDiffuseColor(color)
        torusActor.SetPosition(position)
        torusActor.SetOrientation(orientation)

        return torusActor

    def Add_ObjectArrow(self, direction, orientation, color=[0.0, 0.0, 1.0], size=2):
        vtk_colors = vtk.vtkNamedColors()

        arrow = vtk.vtkArrowSource()
        arrow.SetTipResolution(40)
        arrow.SetShaftResolution(40)
        arrow.SetShaftRadius(0.05)
        arrow.SetTipRadius(0.15)
        arrow.SetTipLength(0.35)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(arrow.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(color)
        actor.GetProperty().SetLineWidth(5)
        actor.AddPosition(0, 0, 0)
        actor.SetScale(size)
        actor.SetPosition(direction)
        actor.SetOrientation(orientation)

        return actor

    def ObjectArrowLocation(self, m_img, coord):
        # m_img[:3, 0] is from posterior to anterior direction of the coil
        # m_img[:3, 1] is from left to right direction of the coil
        # m_img[:3, 2] is from bottom to up direction of the coil
        vec_length = 70
        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]
        p1 = m_img_flip[:-1, -1]  # coil center
        coil_dir = m_img_flip[:-1, 0]
        coil_face = m_img_flip[:-1, 1]

        coil_norm = np.cross(coil_dir, coil_face)
        p2_norm = p1 - vec_length * coil_norm # point normal to the coil away from the center by vec_length
        coil_dir = np.array([coord[3], coord[4], coord[5]])

        return coil_dir, p2_norm, coil_norm, p1


    def add_line(self, p1, p2, color=[0.0, 0.0, 1.0]):
        line = vtk.vtkLineSource()
        line.SetPoint1(p1)
        line.SetPoint2(p2)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(line.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(color)

        return actor

    def AddPeeledSurface(self, flag, actor):
        if self.actor_peel:
            self.ren.RemoveActor(self.actor_peel)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.actor_peel = None
            self.ball_actor.SetVisibility(1)

        if flag and actor:
            self.ren.AddActor(actor)
            self.actor_peel = actor
            self.ren.AddActor(self.object_orientation_torus_actor)
            self.ren.AddActor(self.obj_projection_arrow_actor)
        self.Refresh()

    def GetPeelCenters(self, centers, normals):
        self.peel_centers = centers
        self.peel_normals = normals

        self.Refresh()

    def Initlocator_viewer(self, locator):
        self.locator = locator
        self.Refresh()

    def GetCellIntersection(self, p1, p2, coil_norm, coil_dir):

        vtk_colors = vtk.vtkNamedColors()
        # This find store the triangles that intersect the coil's normal
        intersectingCellIds = vtk.vtkIdList()

        #for debugging
        self.x_actor = self.add_line(p1,p2,vtk_colors.GetColor3d('Blue'))
        #self.ren.AddActor(self.x_actor) # remove comment for testing

        self.locator.FindCellsAlongLine(p1, p2, .001, intersectingCellIds)

        closestDist = 50

        #if find intersection , calculate angle and add actors
        if intersectingCellIds.GetNumberOfIds() != 0:
            for i in range(intersectingCellIds.GetNumberOfIds()):
                cellId = intersectingCellIds.GetId(i)
                point = np.array(self.peel_centers.GetPoint(cellId))
                distance = np.linalg.norm(point - p1)

                #print('distance:', distance, point - p1)
                self.ren.RemoveActor(self.y_actor)

                if distance < closestDist:
                    closestDist = distance
                    closestPoint = point
                    pointnormal = np.array(self.peel_normals.GetTuple(cellId))
                    angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
                    #print('the angle:', angle)

                    #for debbuging
                    self.y_actor = self.add_line(closestPoint, closestPoint + 75 * pointnormal,
                                                         vtk_colors.GetColor3d('Yellow'))

                    #self.ren.AddActor(self.y_actor)# remove comment for testing


                    self.ren.AddActor(self.obj_projection_arrow_actor)
                    self.ren.AddActor(self.object_orientation_torus_actor)
                    self.ball_actor.SetVisibility(0)
                    self.obj_projection_arrow_actor.SetPosition(closestPoint)
                    self.obj_projection_arrow_actor.SetOrientation(coil_dir)

                    self.object_orientation_torus_actor.SetPosition(closestPoint)
                    self.object_orientation_torus_actor.SetOrientation(coil_dir)

                    # change color of arrow and disk according to angle
                    if angle < self.angle_arrow_projection_threshold:
                        self.object_orientation_torus_actor.GetProperty().SetDiffuseColor([51/255,176/255,102/255])
                        self.obj_projection_arrow_actor.GetProperty().SetColor([55/255,120/255,163/255])
                    else:
                        self.object_orientation_torus_actor.GetProperty().SetDiffuseColor([240/255,146/255,105/255])
                        self.obj_projection_arrow_actor.GetProperty().SetColor([240/255,146/255,105/255])
                else:
                    self.ren.RemoveActor(self.y_actor)

        else:
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.ren.RemoveActor(self.x_actor)
            self.ball_actor.SetVisibility(1)

            #self.ren.RemoveActor(self.y_actor)
        self.Refresh()

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        self.tracts_status = vis_status[1]

        if self.nav_status:
            self.pTarget = self.CenterOfMass()
            if self.obj_actor:
                self.obj_actor.SetVisibility(self.obj_state)
                #self.x_actor.SetVisibility(self.obj_state)
                #self.y_actor.SetVisibility(self.obj_state)
                #self.z_actor.SetVisibility(self.obj_state)
                #self.object_orientation_torus_actor.SetVisibility(self.obj_state)
                #self.obj_projection_arrow_actor.SetVisibility(self.obj_state)
        self.Refresh()

    def UpdateSeedOffset(self, data):
        self.seed_offset = data

    def UpdateMarkerOffsetState(self, create=False):
        if create:
            if not self.mark_actor:
                self.mark_actor = self.add_marker([0., 0., 0.], color=[0., 1., 1.])
                self.ren.AddActor(self.mark_actor)
        else:
            if self.mark_actor:
                self.ren.RemoveActor(self.mark_actor)
                self.mark_actor = None
        self.Refresh()

    def CreateMarkerOffset(self):
        self.mark_actor = self.add_marker([0., 0., 0.], color=[0., 1., 1.])
        self.ren.AddActor(self.mark_actor)
        self.Refresh()

    def UpdateMarkerOffsetPosition(self, coord_offset):
        self.mark_actor.SetPosition(coord_offset)
        self.Refresh()

    def UpdateObjectOrientation(self, m_img, coord):
        # print("Update object orientation")

        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]

        # translate coregistered coordinate to display a marker where Trekker seed is computed
        # coord_offset = m_img_flip[:3, -1] - self.seed_offset * m_img_flip[:3, 2]

        # print("m_img copy in viewer_vol: {}".format(m_img_copy))

        # m_img[:3, 0] is from posterior to anterior direction of the coil
        # m_img[:3, 1] is from left to right direction of the coil
        # m_img[:3, 2] is from bottom to up direction of the coil

        m_img_vtk = vtku.numpy_to_vtkMatrix4x4(m_img_flip)

        self.obj_actor.SetUserMatrix(m_img_vtk)
        # self.obj_axes.SetUserMatrix(m_rot_vtk)
        self.x_actor.SetUserMatrix(m_img_vtk)
        self.y_actor.SetUserMatrix(m_img_vtk)
        self.z_actor.SetUserMatrix(m_img_vtk)

        self.Refresh()


    def UpdateObjectArrowOrientation(self, m_img, coord, flag):

        [coil_dir, norm, coil_norm, p1 ]= self.ObjectArrowLocation(m_img,coord)

        if flag:
            self.ren.RemoveActor(self.x_actor)
            #self.ren.RemoveActor(self.y_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.GetCellIntersection(p1, norm, coil_norm, coil_dir)
        self.Refresh()

    def UpdateTrackObjectState(self, evt=None, flag=None, obj_name=None, polydata=None, use_default_object=True):
        if flag:
            self.obj_name = obj_name
            self.polydata = polydata
            self.use_default_object = use_default_object
            if not self.obj_actor:
                self.AddObjectActor(self.obj_name)
        else:
            if self.obj_actor:
                self.ren.RemoveActor(self.obj_actor)
                self.ren.RemoveActor(self.x_actor)
                self.ren.RemoveActor(self.y_actor)
                self.ren.RemoveActor(self.z_actor)
                self.ren.RemoveActor(self.mark_actor)
                self.ren.RemoveActor(self.obj_projection_arrow_actor)
                self.ren.RemoveActor(self.object_orientation_torus_actor)
                self.obj_actor = None
                self.x_actor = None
                self.y_actor = None
                self.z_actor = None
                self.mark_actor = None
                self.obj_projection_arrow_actor = None
                self.object_orientation_torus_actor=None
        self.Refresh()

    def UpdateShowObjectState(self, state):
        self.obj_state = state
        if self.obj_actor and not self.obj_state:
            self.obj_actor.SetVisibility(self.obj_state)
            self.x_actor.SetVisibility(self.obj_state)
            self.y_actor.SetVisibility(self.obj_state)
            self.z_actor.SetVisibility(self.obj_state)
            #if self.actor_peel:
            #    self.ball_actor.SetVisibility(0)
            #else:
            #    self.ball_actor.SetVisibility(1)
        self.Refresh()

    def OnUpdateTracts(self, root=None, affine_vtk=None, coord_offset=None):
        mapper = vtk.vtkCompositePolyDataMapper2()
        mapper.SetInputDataObject(root)

        self.actor_tracts = vtk.vtkActor()
        self.actor_tracts.SetMapper(mapper)
        self.actor_tracts.SetUserMatrix(affine_vtk)

        self.ren.AddActor(self.actor_tracts)
        if self.mark_actor:
            self.mark_actor.SetPosition(coord_offset)
        self.Refresh()

    def OnRemoveTracts(self):
        if self.actor_tracts:
            self.ren.RemoveActor(self.actor_tracts)
            self.actor_tracts = None
            self.Refresh()

    def __bind_events_wx(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        #  self.canvas.subscribe_event('LeftButtonPressEvent', self.on_insert_point)
        pass

    def on_insert_point(self, evt):
        pos = evt.position
        self.polygon.append_point(pos)
        self.canvas.Refresh()

        arr = self.canvas.draw_element_to_array([self.polygon,])
        imsave('/tmp/polygon.png', arr)

    def SetInteractorStyle(self, state):
        cleanup = getattr(self.style, 'CleanUp', None)
        if cleanup:
            self.style.CleanUp()

        del self.style

        style = styles.Styles.get_style(state)(self)

        setup = getattr(style, 'SetUp', None)
        if setup:
            style.SetUp()

        self.style = style
        self.interactor.SetInteractorStyle(style)
        self.interactor.Render()

        self.state = state

    def enable_style(self, style):
        if styles.Styles.has_style(style):
            new_state = self.interaction_style.AddState(style)
            self.SetInteractorStyle(new_state)
        else:
            new_state = self.interaction_style.RemoveState(style)
            self.SetInteractorStyle(new_state)

    def OnDisableStyle(self, style):
        new_state = self.interaction_style.RemoveState(style)
        self.SetInteractorStyle(new_state)

    def ResetCamClippingRange(self):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()

    def SetVolumeCameraState(self, camera_state):
        self.camera_state = camera_state

    # def SetVolumeCamera(self, arg, position):
    def SetVolumeCamera(self, cam_focus):
        if self.camera_state:
            # TODO: exclude dependency on initial focus
            # cam_focus = np.array(bases.flip_x(position[:3]))
            # cam_focus = np.array(bases.flip_x(position))
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

    def OnExportSurface(self, filename, filetype):
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

    def OnEnableBrightContrast(self):
        style = self.style
        style.AddObserver("MouseMoveEvent", self.OnMove)
        style.AddObserver("LeftButtonPressEvent", self.OnClick)
        style.AddObserver("LeftButtonReleaseEvent", self.OnRelease)

    def OnDisableBrightContrast(self):
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        self.style = style

    def OnSetWindowLevelText(self, ww, wl):
        if self.raycasting_volume:
            self.text.SetValue("WL: %d  WW: %d"%(wl, ww))
            #  self.canvas.modified = True

    def OnShowRaycasting(self):
        if not self.raycasting_volume:
            self.raycasting_volume = True
            # self._to_show_ball += 1
            # self._check_and_set_ball_visibility()
            if self.on_wl:
                self.text.Show()

    def OnHideRaycasting(self):
        self.raycasting_volume = False
        self.text.Hide()
        # self._to_show_ball -= 1
        # self._check_and_set_ball_visibility()

    def OnSize(self, evt):
        self.UpdateRender()
        self.Refresh()
        self.interactor.UpdateWindowUI()
        self.interactor.Update()
        evt.Skip()

    def ChangeBackgroundColour(self, colour):
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
        # self._to_show_ball += 1
        # self._check_and_set_ball_visibility()

    def RemoveActor(self, actor):
        utils.debug("RemoveActor")
        ren = self.ren
        ren.RemoveActor(actor)
        self.interactor.Render()
        # self._to_show_ball -= 1
        # self._check_and_set_ball_visibility()

    def RemoveAllActor(self):
        utils.debug("RemoveAllActor")
        self.ren.RemoveAllProps()
        Publisher.sendMessage('Render volume viewer')

    def LoadSlicePlane(self):
        self.slice_plane = SlicePlane()

    def LoadVolume(self, volume, colour, ww, wl):
        self.raycasting_volume = True
        # self._to_show_ball += 1
        # self._check_and_set_ball_visibility()

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

        self.UpdateRender()

    def UnloadVolume(self, volume):
        self.ren.RemoveVolume(volume)
        del volume
        self.raycasting_volume = False
        # self._to_show_ball -= 1
        # self._check_and_set_ball_visibility()

    def load_mask_preview(self, mask_3d_actor, flag=True):
        if flag:
            self.ren.AddVolume(mask_3d_actor)
        else:
            self.ren.RemoveVolume(mask_3d_actor)

        if self.ren.GetActors().GetNumberOfItems() == 0 and self.ren.GetVolumes().GetNumberOfItems() == 1:
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()

    def remove_mask_preview(self, mask_3d_actor):
        self.ren.RemoveVolume(mask_3d_actor)

    def OnSetViewAngle(self, view):
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

    def UpdateRender(self):
        self.interactor.Render()

    def SetWidgetInteractor(self, widget=None):
        widget.SetInteractor(self.interactor._Iren)

    def AppendActor(self, actor):
        self.ren.AddActor(actor)

    def Reposition3DPlane(self, plane_label):
        if not(self.added_actor) and not(self.raycasting_volume):
            if not(self.repositioned_axial_plan) and (plane_label == 'Axial'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_axial_plan = 1

            elif not(self.repositioned_sagital_plan) and (plane_label == 'Sagital'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_sagital_plan = 1

            elif not(self.repositioned_coronal_plan) and (plane_label == 'Coronal'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_coronal_plan = 1

    # def _check_and_set_ball_visibility(self):
    #     #TODO: When creating Raycasting volume and cross is pressed, it is not
    #     # automatically creating the ball reference.
    #     # print("mode_cross, show_ball, ball_vis ", self._mode_cross, self._to_show_ball, self._ball_ref_visibility)
    #     if self._mode_cross:
    #         if self._to_show_ball > 0 and not self._ball_ref_visibility:
    #             self.ActivateBallReference()
    #             self.interactor.Render()
    #         elif not self._to_show_ball and self._ball_ref_visibility:
    #             self.RemoveBallReference()
    #             self.interactor.Render()

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

    def Enable(self, plane_label=None):
        if plane_label:
            if(plane_label == "Axial"):
                self.plane_z.On()
            elif(plane_label == "Coronal"):
                self.plane_y.On()
            elif(plane_label == "Sagital"):
                self.plane_x.On()
            Publisher.sendMessage('Reposition 3D Plane', plane_label=plane_label)
        else:
            self.plane_z.On()
            self.plane_x.On()
            self.plane_y.On()
            Publisher.sendMessage('Set volume view angle',
                                  view=const.VOL_ISO)
        self.Render()

    def Disable(self, plane_label=None):
        if plane_label:
            if(plane_label == "Axial"):
                self.plane_z.Off()
            elif(plane_label == "Coronal"):
                self.plane_y.Off()
            elif(plane_label == "Sagital"):
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

