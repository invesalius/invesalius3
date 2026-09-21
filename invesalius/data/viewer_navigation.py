# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------
# from math import cos, sin
import os
import queue
import time

import numpy as np
import wx
from scipy.spatial import distance
from vtkmodules.vtkCommonColor import vtkColorSeries, vtkNamedColors

# TODO: Check that these imports are not used -- vtkLookupTable, vtkMinimalStandardRandomSequence, vtkPoints, vtkUnsignedCharArray
from vtkmodules.vtkCommonCore import (
    mutable,
    vtkDoubleArray,
    vtkIdList,
    vtkLookupTable,
    vtkPoints,
    vtkUnsignedCharArray,
)
from vtkmodules.vtkCommonDataModel import (
    vtkPolyData,
)
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkGlyph3D, vtkPolyDataNormals
from vtkmodules.vtkFiltersModeling import vtkBandedPolyDataContourFilter
from vtkmodules.vtkFiltersSources import (
    vtkArrowSource,
    vtkSphereSource,
)
from vtkmodules.vtkIOGeometry import vtkSTLReader
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkCompositePolyDataMapper,
    vtkPolyDataMapper,
    vtkRenderer,
)

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.data.visualization.coil_visualizer import CoilVisualizer
from invesalius.data.visualization.marker_visualizer import MarkerVisualizer
from invesalius.data.visualization.probe_visualizer import ProbeVisualizer
from invesalius.data.visualization.robot_force_visualizer import RobotForceVisualizer
from invesalius.data.visualization.vector_field_visualizer import VectorFieldVisualizer
from invesalius.i18n import tr as _
from invesalius.math_utils import inner1d
from invesalius.navigation.robot import Robots
from invesalius.pubsub import pub as Publisher


class NavigationRenderer:
    """Track navigation props added to the volume renderer."""

    def __init__(self, renderer):
        self.renderer = renderer
        self._active = False
        self._props = {}

    def __getattr__(self, name):
        return getattr(self.renderer, name)

    def _add(self, method, prop):
        is_new = not self.renderer.HasViewProp(prop)
        getattr(self.renderer, method)(prop)
        if is_new:
            self._props[prop] = prop.GetVisibility()
            if not self._active:
                prop.SetVisibility(False)

    def _remove(self, method, prop):
        getattr(self.renderer, method)(prop)
        self._props.pop(prop, None)

    def AddActor(self, actor):
        self._add("AddActor", actor)

    def AddActor2D(self, actor):
        self._add("AddActor2D", actor)

    def AddViewProp(self, prop):
        self._add("AddViewProp", prop)

    def RemoveActor(self, actor):
        self._remove("RemoveActor", actor)

    def RemoveActor2D(self, actor):
        self._remove("RemoveActor2D", actor)

    def RemoveViewProp(self, prop):
        self._remove("RemoveViewProp", prop)

    def set_active(self, active):
        if self._active == active:
            return
        if active:
            for prop, visibility in self._props.items():
                if not self.renderer.HasViewProp(prop):
                    self.renderer.AddViewProp(prop)
                prop.SetVisibility(visibility)
        else:
            for prop in self._props:
                self._props[prop] = prop.GetVisibility()
                prop.SetVisibility(False)
        self._active = active

    def dispose(self):
        for prop in self._props:
            self.renderer.RemoveViewProp(prop)
        self._props.clear()
        self._active = False


class NavigationView:
    """Add navigation behavior to an existing volume viewer."""

    def __init__(self, view):
        self.view = view
        self._active = False
        self._disposed = False
        self._volume_state = None
        self._navigation_camera_settings = None
        self._navigation_interaction_state = None
        self._navigation_renderers = []
        self._nav_status = False
        self._target_mode = False
        self.ren = NavigationRenderer(view.ren)

        self._initialize_navigation_data()
        self._initialize_sensor_data()
        self._initialize_navigation_state()
        self._initialize_navigation_visualizers()
        self._create_navigation_renderer()
        self._initialize_navigation_ui()
        self._bind_events()
        self._restore_navigation_markers()
        self._update_fps_visibility()

    def __getattr__(self, name):
        """Use rendering and general-view operations from the owned view."""
        return getattr(self.view, name)

    @property
    def nav_status(self):
        return self._nav_status

    @nav_status.setter
    def nav_status(self, value):
        self._nav_status = value
        if self._active:
            self.view.nav_status = value

    @property
    def target_mode(self):
        return self._target_mode

    @target_mode.setter
    def target_mode(self, value):
        self._target_mode = value
        if self._active:
            self.view.target_mode = value

    def activate(self):
        if self._disposed or self._active:
            return
        self._volume_state = self.view.capture_state()
        if self._navigation_camera_settings is not None:
            self.view.ApplyCameraSettings(self._navigation_camera_settings)
        if self._navigation_interaction_state is not None:
            self.view.interaction_style.stack = self._navigation_interaction_state.copy()
            self.view.SetInteractorStyle(self.view.interaction_style.GetActualState())
        self._active = True
        self.view.nav_status = self.nav_status
        self.view.target_mode = self.target_mode
        self.ren.set_active(True)
        for renderer in self._navigation_renderers:
            if renderer is not self.target_guide_renderer or self.target_mode:
                self._attach_renderer(renderer)
        self._apply_scene_viewport()
        self._update_fps_visibility()
        self.view.UpdateRender()

    def deactivate(self):
        if not self._active:
            return
        self._navigation_camera_settings = self.view.GetCameraSettings()
        self._navigation_interaction_state = self.view.interaction_style.stack.copy()
        self._active = False
        self.view.nav_status = False
        self.view.target_mode = False
        self._update_fps_visibility()
        self.ren.set_active(False)
        for renderer in self._navigation_renderers:
            self._detach_renderer(renderer)
        self.view.restore_state(self._volume_state)
        self._volume_state = None
        self.view.SetSceneViewport((0.0, 0.0, 1.0, 1.0))
        self.view.UpdateRender()

    def dispose(self):
        if self._disposed:
            return
        self.deactivate()
        self._disposed = True
        Publisher.unsubscribe_owner(self)
        self.marker_visualizer.dispose()
        self.coil_visualizer.dispose()
        self.probe_visualizer.dispose()
        self.robot_force_visualizer.dispose()
        self.vector_field_visualizer.dispose()
        self.ren.dispose()
        for renderer in self._navigation_renderers:
            self._detach_renderer(renderer)
        self._navigation_renderers.clear()
        self.view.target_guide_renderer = None

    def _add_scene_renderer(self, renderer):
        if renderer not in self._navigation_renderers:
            self._navigation_renderers.append(renderer)
        if self._active and (renderer is not self.target_guide_renderer or self.target_mode):
            self._attach_renderer(renderer)

    def _remove_scene_renderer(self, renderer):
        self._detach_renderer(renderer)
        if renderer in self._navigation_renderers:
            self._navigation_renderers.remove(renderer)

    def _attach_renderer(self, renderer):
        window = self.interactor.GetRenderWindow()
        if not window.HasRenderer(renderer):
            window.AddRenderer(renderer)

    def _detach_renderer(self, renderer):
        window = self.interactor.GetRenderWindow()
        if window.HasRenderer(renderer):
            window.RemoveRenderer(renderer)

    def _initialize_navigation_data(self):
        self.static_markers_efield = []
        self.plot_vector = None
        self.efield_data_revision = None
        self.position_max_revision = None
        self._fps_last_time = time.monotonic()
        self._fps_frames = 0
        self._fps_text_visible = True
        self.fps_text = vtku.Text()
        self.fps_text.SetSize(const.TEXT_SIZE_SMALL)
        self.fps_text.SetPosition(
            (const.TEXT_POS_LEFT_UP[0], min(0.995, const.TEXT_POS_LEFT_UP[1] + 0.02))
        )
        self.fps_text.SetValue("FPS: --")

    def _initialize_sensor_data(self):
        self.coil_sensor_spheres = []
        self.coil_sensor_sources = []

    def _create_navigation_renderer(self):
        # Render the target guide in a separate renderer, so that it can be
        # rendered on top of the volume.
        self.target_guide_renderer = vtkRenderer()
        self.view.target_guide_renderer = self.target_guide_renderer

        self._add_scene_renderer(self.target_guide_renderer)
        self.ren.AddActor(self.fps_text.actor)
        self.fps_text.Hide()

    def _apply_scene_viewport(self):
        self.view._apply_scene_viewport()
        if self.target_mode:
            self._set_renderer_viewport(self.ren, (0.0, 0.0, 0.75, 1.0))
            self._set_renderer_viewport(self.target_guide_renderer, (0.75, 0.0, 1.0, 1.0))
        else:
            self._set_renderer_viewport(self.target_guide_renderer, (0.0, 0.0, 1.0, 1.0))

        for name, viewport in (
            ("ren_probe", (0.01, 0.79, 0.15, 0.97)),
            ("ren_ref", (0.01, 0.57, 0.15, 0.79)),
            ("ren_obj", (0.01, 0.40, 0.15, 0.57)),
        ):
            renderer = getattr(self, name, None)
            if renderer is not None:
                self._set_renderer_viewport(renderer, viewport)

    def _initialize_navigation_state(self):
        self.obj_axes = None
        self.coil_path = False
        self.show_coil = False
        self.guide_coil_actors = None
        self.guide_arrow_actors = None
        self.pTarget = [0.0, 0.0, 0.0]

        self.distance_text = None
        self.robot_warnings_text = None

        # self.obj_axes = None
        self.mark_actor = None
        self.obj_projection_arrow_actor = None
        self.object_orientation_torus_actor = None
        self._to_show_ball = 0
        self.highlighted_marker_index = None

        self.probe = False
        self.ref = False
        self.obj = False

        self.target_coord = None

        self.dummy_probe_actor = None
        self.dummy_ref_actor = None
        self.dummy_obj_actor = None
        self.target_mode = False
        self._target_camera_last_update = 0.0
        self._target_camera_update_interval = 1.0 / 20.0
        self._target_guide_last_update = 0.0
        self._target_guide_update_interval = 1.0 / 20.0
        self._target_guide_deadband = 2.0
        self._target_guide_last_signature = None

        # Set the angle and distance thresholds.
        session = ses.Session()
        angle_threshold = session.GetConfig("angle_threshold", const.DEFAULT_ANGLE_THRESHOLD)
        distance_threshold = session.GetConfig(
            "distance_threshold", const.DEFAULT_DISTANCE_THRESHOLD
        )

        self.angle_threshold = angle_threshold
        self.distance_threshold = distance_threshold

        self.angle_arrow_projection_threshold = const.COIL_ANGLE_ARROW_PROJECTION_THRESHOLD

        self.actor_tracts = None
        self.actor_peel = None

    def _initialize_navigation_visualizers(self):
        self.projection_actor = None

        # An object that can be used to create vector fields in the 3D viewer.
        self.vector_field_visualizer = VectorFieldVisualizer(
            actor_factory=self.actor_factory,
        )

        # An object to manage visualizing markers in the 3D viewer.
        self.marker_visualizer = MarkerVisualizer(
            renderer=self.ren,
            interactor=self.interactor,
            actor_factory=self.actor_factory,
            vector_field_visualizer=self.vector_field_visualizer,
        )

        # An object to manage visualizing coils in the 3D viewer.
        self.coil_visualizer = CoilVisualizer(
            renderer=self.ren,
            actor_factory=self.actor_factory,
            vector_field_visualizer=self.vector_field_visualizer,
        )

        self.probe_visualizer = ProbeVisualizer(self.ren)
        self.robot_force_visualizer = RobotForceVisualizer(self.interactor)
        self._navigation_renderers.append(self.robot_force_visualizer.ren_force)
        self._detach_renderer(self.robot_force_visualizer.ren_force)
        self.robots = Robots()

        self.seed_offset = const.SEED_OFFSET
        self.radius_list = vtkIdList()
        self.last_efield_cell_id = None
        self.colors_init = vtkUnsignedCharArray()
        self.plot_no_connection = False

        self.old_coord = np.zeros((6,), dtype=float)

        self.efield_mesh = None
        self.max_efield_vector = None
        self.ball_max_vector = None
        self.ball_GoGEfieldVector = None
        self.GoGEfieldVector = None
        self.vectorfield_actor = None
        self.efield_scalar_bar = None
        self.edge_fill_actor = None
        self.edge_actor = None
        self.show_efield_edges = False
        self.tracts_status = False
        # self.dummy_efield_coil_actor = None
        self.target_at_cortex = None
        self.SpreadEfieldFactorTextActor = None
        self.mTMSCoordTextActor = None
        self.EfieldAtTargetLegend = None
        self.ClusterEfieldTextActor = None
        self.enableefieldabovethreshold = False
        self.efield_tools = False
        self.save_automatically = False
        self.positions_above_threshold = None
        self.cell_id_indexes_above_threshold = None

    def _restore_navigation_markers(self):
        from invesalius.navigation.markers import MarkersControl

        for marker in MarkersControl().list:
            self.marker_visualizer.AddMarker(marker, render=False, focus=False)
            if marker.is_target:
                self.marker_visualizer.SetTarget(marker)
                self.OnSetTarget(marker)

    def _initialize_navigation_ui(self):
        Publisher.sendMessage("Press target mode button", pressed=False)

    def _update_fps_visibility(self):
        show_fps = (
            self._fps_text_visible
            and self.nav_status
            and getattr(self, "state", None) == const.STATE_NAVIGATION
        )
        self.fps_text.Show(show_fps)

    def OnHideText(self):
        self._fps_text_visible = False
        self._update_fps_visibility()

    def OnShowText(self):
        self._fps_text_visible = True
        self._update_fps_visibility()

    def UpdateRender(self):
        if self._disposed or not self._active:
            return
        self.view.UpdateRender()
        self._count_rendered_frame()

    def OnRender(self):
        if not self._disposed and self._active:
            self._count_rendered_frame()

    def _count_rendered_frame(self):
        if self.fps_text.actor.GetVisibility():
            end = time.monotonic()
            self._fps_frames += 1
            elapsed = end - self._fps_last_time
            if elapsed >= 0.5:
                fps = self._fps_frames / elapsed
                self._fps_last_time = end
                self._fps_frames = 0
                self.fps_text.SetValue(f"FPS: {fps:0.1f}")

    def _bind_events(self):
        Publisher.subscribe(self.OnHideText, "Hide text actors on viewers")
        Publisher.subscribe(self.OnShowText, "Show text actors on viewers")
        Publisher.subscribe(self.OnRender, "Render volume viewer")
        Publisher.subscribe(self.OnSensors, "Sensors ID")
        Publisher.subscribe(self.OnRemoveSensorsID, "Remove sensors ID")
        Publisher.subscribe(self.DeleteEFieldMarkers, "Delete markers")
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")
        Publisher.subscribe(self.UpdateArrowPose, "Update object arrow matrix")
        Publisher.subscribe(
            self.UpdateEfieldPointLocation, "Update point location for e-field calculation"
        )
        Publisher.subscribe(self.GetEnorm, "Get enorm")
        Publisher.subscribe(self.TrackObject, "Track object")
        Publisher.subscribe(self.SetTargetMode, "Set target mode")
        Publisher.subscribe(self.OnUpdateCoilPose, "Update coil pose")
        Publisher.subscribe(self.OnSetTarget, "Set target")
        Publisher.subscribe(self.OnUnsetTarget, "Unset target")
        Publisher.subscribe(self.OnUpdateAngleThreshold, "Update angle threshold")
        Publisher.subscribe(self.OnUpdateDistanceThreshold, "Update distance threshold")
        Publisher.subscribe(self.OnUpdateTracts, "Update tracts")
        Publisher.subscribe(self.OnUpdateEfieldvis, "Update efield vis")
        Publisher.subscribe(self.InitializeColorArray, "Initialize color array")
        Publisher.subscribe(self.OnRemoveTracts, "Remove tracts")
        Publisher.subscribe(self.UpdateSeedOffset, "Update seed offset")
        Publisher.subscribe(self.UpdateMarkerOffsetState, "Update marker offset state")
        Publisher.subscribe(self.AddPeeledSurface, "Update peel")
        Publisher.subscribe(self.InitEfield, "Initialize E-field brain")
        Publisher.subscribe(self.GetPeelCenters, "Get peel centers and normals")
        Publisher.subscribe(self.InitLocatorViewer, "Get init locator")
        Publisher.subscribe(self.GetEfieldActor, "Send Actor")
        Publisher.subscribe(self.ReturnToDefaultColorActor, "Recolor again")
        Publisher.subscribe(self.SaveEfieldData, "Save Efield data")
        Publisher.subscribe(self.SavedAllEfieldData, "Save all Efield data")
        Publisher.subscribe(self.SaveEfieldTargetData, "Save target data")
        Publisher.subscribe(self.ClearSaveEfieldData, "Clear saved efield data")
        Publisher.subscribe(self.GetTargetSavedEfieldData, "Get target index efield")
        Publisher.subscribe(self.CheckStatusSavedEfieldData, "Check efield data")
        Publisher.subscribe(self.GetNeuronavigationApi, "Get Neuronavigation Api")
        Publisher.subscribe(self.UpdateEfieldPointLocationOffline, "Update interseccion offline")
        Publisher.subscribe(self.MaxEfieldActor, "Show max Efield actor")
        Publisher.subscribe(self.CoGEfieldActor, "Show CoG Efield actor")
        Publisher.subscribe(
            self.CalculateDistanceMaxEfieldCoGE, "Show distance between Max and CoG Efield"
        )
        Publisher.subscribe(self.EfieldVectors, "Show Efield vectors")
        Publisher.subscribe(self.RecolorEfieldActor, "Recolor efield actor")
        Publisher.subscribe(self.GetScalpEfield, "Send scalp index")
        Publisher.subscribe(
            self.OnUpdateRobotWarning, "Robot to Neuronavigation: Update robot warning"
        )
        Publisher.subscribe(self.GetCoilPosition, "Calculate position and rotation")
        Publisher.subscribe(
            self.CreateCortexProjectionOnScalp, "Send efield target position on brain"
        )
        Publisher.subscribe(self.UpdateEfieldThreshold, "Update Efield Threshold")
        Publisher.subscribe(self.UpdateEfieldROISize, "Update Efield ROI size")
        Publisher.subscribe(self.SetEfieldTargetAtCortex, "Set as Efield target at cortex")
        Publisher.subscribe(self.EnableShowEfieldAboveThreshold, "Show area above threshold")
        Publisher.subscribe(self.ShowEfieldContours, "Show Efield contours")
        Publisher.subscribe(self.EnableEfieldTools, "Enable Efield tools")
        Publisher.subscribe(self.ClearTargetAtCortex, "Clear efield target at cortex")
        Publisher.subscribe(self.CoGEforCortexMarker, "Get Cortex position")
        Publisher.subscribe(self.AddCortexMarkerActor, "Add cortex marker actor")
        Publisher.subscribe(self.CortexMarkersVisualization, "Display efield markers at cortex")
        Publisher.subscribe(self.GetTargetPositions, "Get targets Ids for mtms")
        Publisher.subscribe(self.GetTargetPathmTMS, "Send targeting file path")
        Publisher.subscribe(self.GetdIsfromCoord, "Send mtms coords")
        Publisher.subscribe(
            self.EnableSaveAutomaticallyEfieldData, "Save automatically efield data"
        )
        Publisher.subscribe(self.Getdiperdtforreport, "Get diperdt used in efield calculation")
        Publisher.subscribe(self.UpdateTractSeedBasedEfield, "Update tract seed based efield")
        Publisher.subscribe(self.Get_meshes_paths_to_report, "Get path meshes")

    def DeleteEFieldMarkers(self, markers):
        if len(self.static_markers_efield) > 0:
            for i in range(len(self.static_markers_efield)):
                self.ren.RemoveActor(self.static_markers_efield[i][0])
            self.static_markers_efield = []

    def OnSensors(self, marker_visibilities):
        probe_id, ref_id, *coil_ids = marker_visibilities

        if not self.probe:
            self.probe = True
            self.CreateSensorID(len(coil_ids))

        green_color = const.GREEN_COLOR_FLOAT
        red_color = const.RED_COLOR_FLOAT
        yellow_color = const.YELLOW_COLOR_FLOAT

        # Update probe and ref colors
        self.dummy_probe_actor.GetProperty().SetColor(green_color if probe_id else red_color)
        self.dummy_ref_actor.GetProperty().SetColor(green_color if ref_id else red_color)

        # Update main coil icon color
        num_visible = sum(coil_ids)
        if num_visible == 0:
            coil_color = red_color
        elif num_visible < len(coil_ids):
            coil_color = yellow_color
        else:
            coil_color = green_color
        self.dummy_obj_actor.GetProperty().SetColor(coil_color)

        # Update sphere colors
        for i, sphere_actor in enumerate(self.coil_sensor_spheres):
            color = green_color if coil_ids[i] else red_color
            sphere_actor.GetProperty().SetColor(color)

    def CreateSensorID(self, num_coils=0):
        self.coil_sensor_spheres = []
        self.coil_sensor_sources = []

        self.ren_probe = vtkRenderer()
        self.ren_probe.SetLayer(1)

        self._add_scene_renderer(self.ren_probe)
        self._set_renderer_viewport(self.ren_probe, (0.01, 0.79, 0.15, 0.97))
        filename = os.path.join(inv_paths.OBJ_DIR, "stylus.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        reader.Update()
        mapper = vtkPolyDataMapper()
        polydata = reader.GetOutput()
        center = polydata.GetCenter()
        mapper.SetInputData(polydata)
        mapper.SetScalarVisibility(0)

        dummy_probe_actor = vtkActor()
        dummy_probe_actor.SetMapper(mapper)
        dummy_probe_actor.SetOrigin(center)
        dummy_probe_actor.GetProperty().SetColor(1, 1, 1)
        dummy_probe_actor.GetProperty().SetOpacity(1.0)
        self.dummy_probe_actor = dummy_probe_actor

        self.ren_probe.AddActor(dummy_probe_actor)
        self.ren_probe.InteractiveOff()

        self.ren_ref = vtkRenderer()
        self.ren_ref.SetLayer(1)

        self._add_scene_renderer(self.ren_ref)
        self._set_renderer_viewport(self.ren_ref, (0.01, 0.57, 0.15, 0.79))
        filename = os.path.join(inv_paths.OBJ_DIR, "head.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        reader.Update()
        mapper = vtkPolyDataMapper()
        polydata = reader.GetOutput()
        center = polydata.GetCenter()
        mapper.SetInputData(polydata)
        mapper.SetScalarVisibility(0)

        dummy_ref_actor = vtkActor()
        dummy_ref_actor.SetMapper(mapper)
        dummy_ref_actor.SetOrigin(center)
        dummy_ref_actor.GetProperty().SetColor(1, 1, 1)
        dummy_ref_actor.GetProperty().SetOpacity(1.0)
        self.dummy_ref_actor = dummy_ref_actor

        self.ren_ref.AddActor(dummy_ref_actor)
        self.ren_ref.InteractiveOff()

        self.ren_obj = vtkRenderer()
        self.ren_obj.SetLayer(1)

        self._add_scene_renderer(self.ren_obj)
        self._set_renderer_viewport(self.ren_obj, (0.01, 0.40, 0.15, 0.57))
        filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil_no_handle.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        reader.Update()
        mapper = vtkPolyDataMapper()
        polydata = reader.GetOutput()
        center = polydata.GetCenter()
        mapper.SetInputData(polydata)
        mapper.SetScalarVisibility(0)

        dummy_obj_actor = vtkActor()
        dummy_obj_actor.SetMapper(mapper)
        dummy_obj_actor.SetOrigin(center)
        dummy_obj_actor.GetProperty().SetColor(1, 1, 1)
        dummy_obj_actor.GetProperty().SetOpacity(1.0)
        self.dummy_obj_actor = dummy_obj_actor

        self.ren_obj.AddActor(dummy_obj_actor)
        self.ren_obj.InteractiveOff()

        # Create spheres for coils only if there is more than 1 coil
        if num_coils > 1:
            total_width = (num_coils - 1) * 15  # Total width the spheres will occupy
            start_x = -total_width / 2.0

            for i in range(num_coils):
                sphere_source = vtkSphereSource()
                sphere_source.SetRadius(6)
                sphere_source.SetCenter(start_x + i * 15, -40, 0)  # Positioned below the coil icon
                self.coil_sensor_sources.append(sphere_source)

                mapper = vtkPolyDataMapper()
                mapper.SetInputConnection(sphere_source.GetOutputPort())

                actor = vtkActor()
                actor.SetMapper(mapper)
                self.ren_obj.AddActor(actor)
                self.coil_sensor_spheres.append(actor)

    def OnRemoveSensorsID(self):
        if self.probe:
            self.ren_probe.RemoveActor(self.dummy_probe_actor)
            self._remove_scene_renderer(self.ren_probe)
            self.ren_ref.RemoveActor(self.dummy_ref_actor)
            self._remove_scene_renderer(self.ren_ref)
            self.ren_obj.RemoveActor(self.dummy_obj_actor)
            for sphere_actor in self.coil_sensor_spheres:
                self.ren_obj.RemoveActor(sphere_actor)
            self.coil_sensor_spheres = []
            self.coil_sensor_sources = []
            self._remove_scene_renderer(self.ren_obj)
            self.probe = self.ref = self.obj = False
            self.UpdateRender()

    def OnUpdateAngleThreshold(self, angle):
        self.angle_threshold = angle

    def OnUpdateDistanceThreshold(self, dist_threshold):
        print("updated to ", dist_threshold)
        self.distance_threshold = dist_threshold

    def OnUpdateRobotWarning(self, robot_warning, robot_id=None):
        if self.robot_warnings_text is not None:
            self.robot_warnings_text.SetValue(robot_warning)

    def CreateTargetGuide(self):
        if self.guide_arrow_actors:
            for ind in self.guide_arrow_actors:
                self.target_guide_renderer.RemoveActor(ind)

        # Using default coil for target guide model as using self.coil_path can cause custom models to overlap.
        coil_path = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")
        obj_polydata = vtku.CreateObjectPolyData(coil_path)

        normals = vtkPolyDataNormals()
        normals.SetInputData(obj_polydata)
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        mapper.ScalarVisibilityOff()
        # mapper.ImmediateModeRenderingOn()  # improve performance

        obj_roll = vtkActor()
        obj_roll.SetMapper(mapper)
        obj_roll.GetProperty().SetColor(1, 1, 1)
        # obj_roll.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
        # obj_roll.GetProperty().SetSpecular(30)
        # obj_roll.GetProperty().SetSpecularPower(80)
        obj_roll.SetPosition(0, 25, -30)
        obj_roll.RotateX(-60)
        obj_roll.RotateZ(180)

        obj_yaw = vtkActor()
        obj_yaw.SetMapper(mapper)
        obj_yaw.GetProperty().SetColor(1, 1, 1)
        # obj_yaw.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
        # obj_yaw.GetProperty().SetSpecular(30)
        # obj_yaw.GetProperty().SetSpecularPower(80)
        obj_yaw.SetPosition(0, -115, 5)
        obj_yaw.RotateZ(180)

        obj_pitch = vtkActor()
        obj_pitch.SetMapper(mapper)
        obj_pitch.GetProperty().SetColor(1, 1, 1)
        # obj_pitch.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
        # obj_pitch.GetProperty().SetSpecular(30)
        # obj_pitch.GetProperty().SetSpecularPower(80)
        obj_pitch.SetPosition(5, -265, 5)
        obj_pitch.RotateY(90)
        obj_pitch.RotateZ(180)

        arrow_roll_z1 = self.actor_factory.CreateArrow([-50, -35, 12], [-50, -35, 50])
        arrow_roll_z1.GetProperty().SetColor(1, 1, 0)
        arrow_roll_z1.RotateX(-60)
        arrow_roll_z1.RotateZ(180)
        arrow_roll_z2 = self.actor_factory.CreateArrow([50, -35, 0], [50, -35, -50])
        arrow_roll_z2.GetProperty().SetColor(1, 1, 0)
        arrow_roll_z2.RotateX(-60)
        arrow_roll_z2.RotateZ(180)

        arrow_yaw_y1 = self.actor_factory.CreateArrow([-50, -35, 0], [-50, 5, 0])
        arrow_yaw_y1.GetProperty().SetColor(0, 1, 0)
        arrow_yaw_y1.SetPosition(0, -150, 0)
        arrow_yaw_y1.RotateZ(180)
        arrow_yaw_y2 = self.actor_factory.CreateArrow([50, -35, 0], [50, -75, 0])
        arrow_yaw_y2.GetProperty().SetColor(0, 1, 0)
        arrow_yaw_y2.SetPosition(0, -150, 0)
        arrow_yaw_y2.RotateZ(180)

        arrow_pitch_x1 = self.actor_factory.CreateArrow([0, 65, 38], [0, 65, 68])
        arrow_pitch_x1.GetProperty().SetColor(1, 0, 0)
        arrow_pitch_x1.SetPosition(0, -300, 0)
        arrow_pitch_x1.RotateY(90)
        arrow_pitch_x1.RotateZ(180)
        arrow_pitch_x2 = self.actor_factory.CreateArrow([0, -55, 5], [0, -55, -30])
        arrow_pitch_x2.GetProperty().SetColor(1, 0, 0)
        arrow_pitch_x2.SetPosition(0, -300, 0)
        arrow_pitch_x2.RotateY(90)
        arrow_pitch_x2.RotateZ(180)

        self.guide_coil_actors = obj_roll, obj_yaw, obj_pitch
        self.guide_arrow_actors = (
            arrow_roll_z1,
            arrow_roll_z2,
            arrow_yaw_y1,
            arrow_yaw_y2,
            arrow_pitch_x1,
            arrow_pitch_x2,
        )

        for ind in self.guide_coil_actors:
            self.target_guide_renderer.AddActor(ind)

        for ind in self.guide_arrow_actors:
            self.target_guide_renderer.AddActor(ind)

    def EnableTargetMode(self):
        self._attach_renderer(self.target_guide_renderer)

        # Store the current camera settings so that they can be restored when the target mode is disabled.
        self.stored_camera_settings = self.GetCameraSettings()

        # Set the transformation matrix for the target.
        self.m_target = self.CreateVTKObjectMatrix(self.target_coord[:3], self.target_coord[3:])

        if self.actor_peel:
            self.object_orientation_torus_actor.SetVisibility(0)
            self.obj_projection_arrow_actor.SetVisibility(0)

        self.coil_visualizer.AddTargetCoil(self.m_target)

        # Separate the target guide inside this navigation scene's viewport.
        self._apply_scene_viewport()

        # Remove the previous actor for 'distance' text
        if self.distance_text is not None:
            self.ren.RemoveActor(self.distance_text.actor)

        # Create new actor for 'distance' text
        distance_text = self.CreateDistanceText()
        self.ren.AddActor(distance_text.actor)

        # Store the object for 'distance' text so it can be modified when distance changes.
        self.distance_text = distance_text

        # Remove the previous actor for 'distance' text
        if self.robot_warnings_text is not None:
            self.ren.RemoveActor(self.robot_warnings_text.actor)

        # Create new actor for 'distance' text
        robot_warnings_text = self.CreateRobotWarningsText()
        self.ren.AddActor(robot_warnings_text.actor)

        # Store the object for 'distance' text so it can be modified when distance changes.
        self.robot_warnings_text = robot_warnings_text

        self.CreateTargetGuide()
        self._target_camera_last_update = 0.0
        self._target_guide_last_update = 0.0
        self._target_guide_last_signature = None

        self.ren.ResetCamera()
        self.SetCameraTarget()
        # self.ren.GetActiveCamera().Zoom(4)

        self.target_guide_renderer.ResetCamera()
        self.target_guide_renderer.GetActiveCamera().Zoom(2)
        self.target_guide_renderer.InteractiveOff()
        if not self.nav_status:
            self.UpdateRender()

    def DisableTargetMode(self):
        self.target_mode = False

        # Restore the camera settings that were stored when the target mode was enabled.
        if self.stored_camera_settings is not None:
            self.ApplyCameraSettings(self.stored_camera_settings)

        # Remove the target coil.
        self.coil_visualizer.RemoveTargetCoil()

        # Remove all actors from the target guide renderer.
        actors = self.target_guide_renderer.GetActors()
        actors.InitTraversal()
        actor = actors.GetNextItem()
        while actor:
            self.target_guide_renderer.RemoveActor(actor)
            actor = actors.GetNextItem()

        # Reset the main renderer to this navigation scene's full viewport.
        self._apply_scene_viewport()
        self._detach_renderer(self.target_guide_renderer)

        # Remove the actor for 'distance' text.
        if self.distance_text is not None:
            self.ren.RemoveActor(self.distance_text.actor)

        # Remove the actor for 'robot warnings' text.
        if self.robot_warnings_text is not None:
            self.ren.RemoveActor(self.robot_warnings_text.actor)

        self.camera_show_object = None
        self._target_guide_last_signature = None
        if self.actor_peel:
            if self.object_orientation_torus_actor:
                self.object_orientation_torus_actor.SetVisibility(1)
            if self.obj_projection_arrow_actor:
                self.obj_projection_arrow_actor.SetVisibility(1)

        if not self.nav_status:
            self.UpdateRender()

    def SetTargetMode(self, enabled=False):
        # If target is not set before attempting to enable target mode, return without enabling it.
        if self.target_coord is None:
            return

        self.target_mode = enabled

        if enabled:
            self.EnableTargetMode()
        else:
            self.DisableTargetMode()

    def OnUpdateCoilPose(self, m_img, coord):
        # vtk_colors = vtkNamedColors()
        if self.target_coord and self.target_mode:
            now = time.monotonic()
            distance_to_target = distance.euclidean(
                coord[0:3], (self.target_coord[0], -self.target_coord[1], self.target_coord[2])
            )

            formatted_distance = f"Distance: {distance_to_target: >5.1f} mm"

            if self.distance_text is not None:
                self.distance_text.SetValue(formatted_distance)

            if now - self._target_camera_last_update >= self._target_camera_update_interval:
                self.ren.ResetCamera()
                self.SetCameraTarget()
                zoom_distance = min(distance_to_target, 100)
                # ((-0.0404*dst) + 5.0404) is the linear equation to normalize the zoom between 1 and 5 times with
                # the distance between 1 and 100 mm
                self.ren.GetActiveCamera().Zoom((-0.0404 * zoom_distance) + 5.0404)
                self._target_camera_last_update = now

            is_under_distance_threshold = distance_to_target <= self.distance_threshold

            m_img_flip = m_img.copy()
            m_img_flip[1, -1] = -m_img_flip[1, -1]

            # Send displacement to the robot.
            #
            # TODO: Unify naming; displacement is more correct term than distance, it should be used consistently.
            displacement_to_target_robot = dcr.ComputeRelativeDistanceToTarget(
                target_coord=self.target_coord, m_img=m_img_flip
            )

            distance_to_target = displacement_to_target_robot.copy()
            if distance_to_target[3] > const.ARROW_UPPER_LIMIT:
                distance_to_target[3] = const.ARROW_UPPER_LIMIT
            elif distance_to_target[3] < -const.ARROW_UPPER_LIMIT:
                distance_to_target[3] = -const.ARROW_UPPER_LIMIT
            coordrx_arrow = const.ARROW_SCALE * distance_to_target[3]

            if distance_to_target[4] > const.ARROW_UPPER_LIMIT:
                distance_to_target[4] = const.ARROW_UPPER_LIMIT
            elif distance_to_target[4] < -const.ARROW_UPPER_LIMIT:
                distance_to_target[4] = -const.ARROW_UPPER_LIMIT
            coordry_arrow = const.ARROW_SCALE * distance_to_target[4]

            if distance_to_target[5] > const.ARROW_UPPER_LIMIT:
                distance_to_target[5] = const.ARROW_UPPER_LIMIT
            elif distance_to_target[5] < -const.ARROW_UPPER_LIMIT:
                distance_to_target[5] = -const.ARROW_UPPER_LIMIT
            coordrz_arrow = const.ARROW_SCALE * distance_to_target[5]

            if (
                self.angle_threshold * const.ARROW_SCALE
                > coordrx_arrow
                > -self.angle_threshold * const.ARROW_SCALE
            ):
                is_under_x_angle_threshold = True
                self.guide_coil_actors[0].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_x_angle_threshold = False
                self.guide_coil_actors[0].GetProperty().SetColor(1, 1, 1)

            if (
                self.angle_threshold * const.ARROW_SCALE
                > coordrz_arrow
                > -self.angle_threshold * const.ARROW_SCALE
            ):
                is_under_z_angle_threshold = True
                self.guide_coil_actors[1].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_z_angle_threshold = False
                self.guide_coil_actors[1].GetProperty().SetColor(1, 1, 1)

            if (
                self.angle_threshold * const.ARROW_SCALE
                > coordry_arrow
                > -self.angle_threshold * const.ARROW_SCALE
            ):
                is_under_y_angle_threshold = True
                self.guide_coil_actors[2].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_y_angle_threshold = False
                self.guide_coil_actors[2].GetProperty().SetColor(1, 1, 1)

            # Combine all the conditions to check if the coil is at the target.
            coil_at_target = (
                is_under_distance_threshold
                and is_under_x_angle_threshold
                and is_under_y_angle_threshold
                and is_under_z_angle_threshold
            )

            wx.CallAfter(Publisher.sendMessage, "Coil at target", state=coil_at_target)

            robot_active = self.robots.GetActiveRobot()
            # If robot is active, send status and update displacement to target
            if robot_active:
                robot_active.SendStatusCoilAtTarget(coil_at_target)
                robot_active.UpdateDisplacementToTarget(displacement_to_target_robot)

            guide_signature = (
                int(round(coordrx_arrow / self._target_guide_deadband)),
                int(round(coordry_arrow / self._target_guide_deadband)),
                int(round(coordrz_arrow / self._target_guide_deadband)),
            )
            should_update_guide = (
                guide_signature != self._target_guide_last_signature
                and now - self._target_guide_last_update >= self._target_guide_update_interval
            )
            if should_update_guide:
                if self.guide_arrow_actors is not None:
                    for actor in self.guide_arrow_actors:
                        self.target_guide_renderer.RemoveActor(actor)

                offset = 5
                arrow_roll_x1 = self.actor_factory.CreateArrow(
                    [-55, -35, offset], [-55, -35, offset - coordrx_arrow]
                )
                arrow_roll_x1.RotateX(-60)
                arrow_roll_x1.RotateZ(180)
                arrow_roll_x1.GetProperty().SetColor(1, 1, 0)

                arrow_roll_x2 = self.actor_factory.CreateArrow(
                    [55, -35, offset], [55, -35, offset + coordrx_arrow]
                )
                arrow_roll_x2.RotateX(-60)
                arrow_roll_x2.RotateZ(180)
                arrow_roll_x2.GetProperty().SetColor(1, 1, 0)

                offset = -35
                arrow_yaw_z1 = self.actor_factory.CreateArrow(
                    [-55, offset, 0], [-55, offset - coordrz_arrow, 0]
                )
                arrow_yaw_z1.SetPosition(0, -150, 0)
                arrow_yaw_z1.RotateZ(180)
                arrow_yaw_z1.GetProperty().SetColor(0, 1, 0)

                arrow_yaw_z2 = self.actor_factory.CreateArrow(
                    [55, offset, 0], [55, offset + coordrz_arrow, 0]
                )
                arrow_yaw_z2.SetPosition(0, -150, 0)
                arrow_yaw_z2.RotateZ(180)
                arrow_yaw_z2.GetProperty().SetColor(0, 1, 0)

                offset = 38
                arrow_pitch_y1 = self.actor_factory.CreateArrow(
                    [0, 65, offset], [0, 65, offset + coordry_arrow]
                )
                arrow_pitch_y1.SetPosition(0, -300, 0)
                arrow_pitch_y1.RotateY(90)
                arrow_pitch_y1.RotateZ(180)
                arrow_pitch_y1.GetProperty().SetColor(1, 0, 0)

                offset = 5
                arrow_pitch_y2 = self.actor_factory.CreateArrow(
                    [0, -55, offset], [0, -55, offset - coordry_arrow]
                )
                arrow_pitch_y2.SetPosition(0, -300, 0)
                arrow_pitch_y2.RotateY(90)
                arrow_pitch_y2.RotateZ(180)
                arrow_pitch_y2.GetProperty().SetColor(1, 0, 0)

                self.guide_arrow_actors = (
                    arrow_roll_x1,
                    arrow_roll_x2,
                    arrow_yaw_z1,
                    arrow_yaw_z2,
                    arrow_pitch_y1,
                    arrow_pitch_y2,
                )

                for ind in self.guide_arrow_actors:
                    self.target_guide_renderer.AddActor(ind)

                self._target_guide_last_signature = guide_signature
                self._target_guide_last_update = now

    def OnUnsetTarget(self, marker):
        self.DisableTargetMode()

        self.target_coord = None

    def OnSetTarget(self, marker):
        coord = marker.position + marker.orientation

        # TODO: The coordinate systems of slice viewers and volume viewer should be unified, so that this coordinate
        #   flip wouldn't be needed.
        coord[1] = -coord[1]

        # Store the new target coordinates and create a new transformation matrix for the target.
        self.target_coord = coord
        self.m_target = self.CreateVTKObjectMatrix(coord[:3], coord[3:])

        self.coil_visualizer.AddTargetCoil(self.m_target)

        print(f"Target updated to coordinates {coord}")

    def CreateVTKObjectMatrix(self, direction, orientation):
        m_img = dco.coordinates_to_transformation_matrix(
            position=direction,
            orientation=orientation,
            axes="sxyz",
        )
        m_img = np.asmatrix(m_img)

        m_img_vtk = vtkMatrix4x4()

        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        return m_img_vtk

    def CreateRobotWarningsText(self):
        robot_warnings_text = vtku.Text()

        robot_warnings_text.SetSize(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION)
        robot_warnings_text.SetPosition((const.X, 1.02 - const.YZ))
        robot_warnings_text.SetVerticalJustificationToBottom()
        robot_warnings_text.SetColour((1, 1, 0))
        robot_warnings_text.BoldOn()

        return robot_warnings_text

    def CreateDistanceText(self):
        distance_text = vtku.Text()

        distance_text.SetSize(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION)
        distance_text.SetPosition((const.X, 1.0 - const.Y))
        distance_text.SetVerticalJustificationToBottom()
        distance_text.BoldOn()

        return distance_text

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
        # x2 = x0 + v1
        # calculates the matrix for the change of coordinate systems (from canonical to the plane's).
        # remember that, in np.dot(M,p), even though p is a line vector (e.g.,np.array([1,2,3])), it is treated as a column for the dot multiplication.
        M_plane_inv = np.array(
            [
                [v1[0], v2[0], v3[0], x0[0]],
                [v1[1], v2[1], v3[1], x0[1]],
                [v1[2], v2[2], v3[2], x0[2]],
                [0, 0, 0, 1],
            ]
        )

        return v3, M_plane_inv

    def SetCameraTarget(self):
        cam_focus = self.target_coord[0:3]
        cam = self.ren.GetActiveCamera()

        oldcamVTK = vtkMatrix4x4()
        oldcamVTK.DeepCopy(cam.GetViewTransformMatrix())

        newvtk = vtkMatrix4x4()
        newvtk.Multiply4x4(self.m_target, oldcamVTK, newvtk)

        transform = vtkTransform()
        transform.SetMatrix(newvtk)
        transform.Update()
        cam.ApplyTransform(transform)

        cam.Roll(90)

        cam_pos0 = np.array(cam.GetPosition())
        cam_focus0 = np.array(cam.GetFocalPoint())
        v0 = cam_pos0 - cam_focus0
        v0n = np.sqrt(inner1d(v0, v0))

        v1 = np.array(
            [
                cam_focus[0] - cam_focus0[0],
                cam_focus[1] - cam_focus0[1],
                cam_focus[2] - cam_focus0[2],
            ]
        )
        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1 / v1n) * v0n + cam_focus
        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)

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
        p2_norm = (
            p1 - vec_length * coil_norm
        )  # point normal to the coil away from the center by vec_length
        coil_dir = np.array([coord[3], coord[4], coord[5]])

        return coil_dir, p2_norm, coil_norm, p1

    def AddPeeledSurface(self, flag, actor):
        if self.actor_peel:
            self.ren.RemoveActor(self.actor_peel)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.actor_peel = None
            if self.pointer_actor:
                self.pointer_actor.SetVisibility(1)

        if flag and actor:
            self.ren.AddActor(actor)
            self.actor_peel = actor
            self.ren.AddActor(self.object_orientation_torus_actor)
            self.ren.AddActor(self.obj_projection_arrow_actor)

        if not self.nav_status:
            self.UpdateRender()

    def GetPeelCenters(self, centers, normals):
        self.peel_centers = centers
        self.peel_normals = normals

    def InitLocatorViewer(self, locator):
        self.locator = locator

    def RecolorEfieldActor(self):
        self.efield_mesh_normals_viewer.Modified()

    def DrawVectors(self, position, orientation, color, scale_factor=10):
        points = vtkPoints()
        vectors = vtkDoubleArray()
        vectors.SetNumberOfComponents(3)
        points.InsertNextPoint(position)
        vectors.InsertNextTuple3(orientation[0], orientation[1], orientation[2])
        dataset = vtkPolyData()
        dataset.SetPoints(points)
        dataset.GetPointData().SetVectors(vectors)
        arrowSource = vtkArrowSource()
        glyphFilter = vtkGlyph3D()
        glyphFilter.SetSourceConnection(arrowSource.GetOutputPort())
        glyphFilter.SetInputData(dataset)
        glyphFilter.SetScaleFactor(scale_factor)
        glyphFilter.Update()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(glyphFilter.GetOutput())
        Actor = vtkActor()
        Actor.SetMapper(mapper)
        Actor.GetProperty().SetColor(color)
        return Actor

    def HasEfieldVectorData(self):
        return (
            self.efield_mesh is not None
            and self.e_field_norms is not None
            and getattr(self, "Id_list", None) is not None
            and len(self.Id_list) > 0
            and getattr(self, "Idmax", None) is not None
            and getattr(self, "max_efield_array", None) is not None
        )

    def RemoveEfieldTargetingActors(self):
        if self.max_efield_vector is not None:
            self.ren.RemoveActor(self.max_efield_vector)
            self.max_efield_vector = None
        if self.ball_max_vector is not None:
            self.ren.RemoveActor(self.ball_max_vector)
            self.ball_max_vector = None
        if self.GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.GoGEfieldVector = None
        if self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.ball_GoGEfieldVector)
            self.ball_GoGEfieldVector = None
        self.position_max = None
        self.position_max_revision = None
        self.center_gravity_position = None

    def RemoveEfieldVectorActor(self):
        if self.vectorfield_actor is not None:
            self.ren.RemoveActor(self.vectorfield_actor)
            self.vectorfield_actor = None

    def MaxEfieldActor(self):
        if not self.HasEfieldVectorData():
            self.RemoveEfieldTargetingActors()
            return

        vtk_colors = vtkNamedColors()
        if self.max_efield_vector and self.ball_max_vector is not None:
            self.ren.RemoveActor(self.max_efield_vector)
            self.ren.RemoveActor(self.ball_max_vector)
        self.position_max = self.efield_mesh.GetPoint(self.Idmax)
        self.position_max_revision = self.efield_data_revision
        orientation = [self.max_efield_array[0], self.max_efield_array[1], self.max_efield_array[2]]
        self.max_efield_vector = self.DrawVectors(
            self.position_max, orientation, vtk_colors.GetColor3d("Red")
        )
        self.ball_max_vector = self.actor_factory.CreateBall(
            self.position_max, vtk_colors.GetColor3d("Red"), 0.5
        )
        self.ren.AddActor(self.max_efield_vector)
        self.ren.AddActor(self.ball_max_vector)

    def CoGEfieldActor(self):
        if not self.HasEfieldVectorData():
            self.RemoveEfieldTargetingActors()
            return

        vtk_colors = vtkNamedColors()
        if self.GoGEfieldVector and self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.ren.RemoveActor(self.ball_GoGEfieldVector)
        orientation = [self.max_efield_array[0], self.max_efield_array[1], self.max_efield_array[2]]
        if not self.cell_id_indexes_above_threshold:
            return

        self.center_gravity_position = self.FindCenterofGravity(
            self.cell_id_indexes_above_threshold, self.positions_above_threshold
        )
        if self.center_gravity_position is None:
            return

        self.GoGEfieldVector = self.DrawVectors(
            self.center_gravity_position, orientation, vtk_colors.GetColor3d("Blue")
        )
        self.ball_GoGEfieldVector = self.actor_factory.CreateBall(
            self.center_gravity_position, vtk_colors.GetColor3d("Blue"), 0.5
        )
        self.ren.AddActor(self.GoGEfieldVector)
        self.ren.AddActor(self.ball_GoGEfieldVector)

    def CoGEforCortexMarker(self):
        if self.e_field_norms is not None:
            [cell_id_indexes, positions_above_threshold] = self.GetIndexesAboveThreshold(0.98)
            center_gravity_position_for_marker = self.FindCenterofGravity(
                cell_id_indexes, positions_above_threshold
            )
            center_gravity_orientation_for_marker = [
                self.max_efield_array[0],
                self.max_efield_array[1],
                self.max_efield_array[2],
            ]
            Publisher.sendMessage(
                "Update Cortex Marker",
                CoGposition=center_gravity_position_for_marker,
                CoGorientation=center_gravity_orientation_for_marker,
            )

    def AddCortexMarkerActor(self, position_orientation, marker_id):
        vtk_colors = vtkNamedColors()
        marker_actor_brain = self.DrawVectors(
            position_orientation[:3],
            position_orientation[3:],
            vtk_colors.GetColor3d("Orange"),
            scale_factor=3,
        )
        self.static_markers_efield.append([marker_actor_brain, marker_id])
        self.ren.AddActor(marker_actor_brain)
        if self.save_automatically:
            import time

            import invesalius.gui.dialogs as dlg
            import invesalius.project as prj

            proj = prj.Project()
            timestamp = time.localtime(time.time())
            stamp_date = f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
            stamp_time = f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
            sep = "-"

            if self.path_meshes is None:
                import os

                current_folder_path = os.getcwd()
            else:
                current_folder_path = self.path_meshes

            parts = [current_folder_path, "/", stamp_date, stamp_time, proj.name, "Efield"]
            default_filename = sep.join(parts) + ".csv"

            filename = dlg.ShowLoadSaveDialog(
                message=_("Save markers as..."),
                wildcard="(*.csv)|*.csv",
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                default_filename=default_filename,
            )

            if not filename:
                return

            Publisher.sendMessage(
                "Save Efield data",
                filename=filename,
                plot_efield_vectors=self.plot_efield_vectors,
                marker_id=marker_id,
            )

    def EnableSaveAutomaticallyEfieldData(self, enable, path_meshes, plot_efield_vectors):
        self.save_automatically = enable
        self.path_meshes = path_meshes
        self.plot_efield_vectors = plot_efield_vectors

    def CortexMarkersVisualization(self, display_flag):
        for i in range(len(self.static_markers_efield)):
            if display_flag:
                self.ren.AddActor(self.static_markers_efield[i][0])
            else:
                self.ren.RemoveActor(self.static_markers_efield[i][0])

    def CreateTextLegend(self, FontSize, Position):
        TextLegend = vtku.Text()
        TextLegend.SetSize(FontSize)
        TextLegend.SetPosition(Position)
        TextLegend.BoldOn()
        return TextLegend

    def CreateEfieldSpreadLegend(self):
        self.SpreadEfieldFactorTextActor = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.4, 0.9)
        )
        self.ren.AddActor(self.SpreadEfieldFactorTextActor.actor)

    def CalculateDistanceMaxEfieldCoGE(self):
        if (
            getattr(self, "center_gravity_position", None) is None
            or getattr(self, "position_max", None) is None
            or self.SpreadEfieldFactorTextActor is None
        ):
            return

        self.distance_efield = distance.euclidean(self.center_gravity_position, self.position_max)
        self.SpreadEfieldFactorTextActor.SetValue(
            "Spread distance: " + str(f"{self.distance_efield:04.2f}")
        )

    def EfieldVectors(self):
        vtk_colors = vtkNamedColors()
        self.RemoveEfieldVectorActor()
        points = vtkPoints()
        vectors = vtkDoubleArray()
        vectors.SetNumberOfComponents(3)

        for i in range(self.radius_list.GetNumberOfIds()):
            point = self.efield_mesh.GetPoint(self.radius_list.GetId(i))
            points.InsertNextPoint(point)
            vectors.InsertNextTuple3(
                self.e_field_col1[i], self.e_field_col2[i], self.e_field_col3[i]
            )

        dataset = vtkPolyData()
        dataset.SetPoints(points)
        dataset.GetPointData().SetVectors(vectors)

        arrowSource = vtkArrowSource()

        glyphFilter = vtkGlyph3D()
        glyphFilter.SetSourceConnection(arrowSource.GetOutputPort())
        glyphFilter.SetInputData(dataset)
        glyphFilter.SetScaleFactor(2)
        glyphFilter.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(glyphFilter.GetOutput())

        self.vectorfield_actor = vtkActor()
        self.vectorfield_actor.SetMapper(mapper)
        self.vectorfield_actor.GetProperty().SetColor(vtk_colors.GetColor3d("Blue"))

        self.ren.AddActor(self.vectorfield_actor)
        self.interactor.Update()

    def SaveEfieldTargetData(self, target_list_index, position, orientation, plot_efield_vectors):
        if len(self.Id_list) > 0:
            if self.efield_coords is not None:
                import invesalius.data.imagedata_utils as imagedata_utils

                position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                    position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
                    orientation=[
                        self.efield_coords[3],
                        self.efield_coords[4],
                        self.efield_coords[5],
                    ],
                )
                efield_coords_position = [list(position_world), list(orientation_world)]
            enorms_list = list(self.e_field_norms_to_save)
            if plot_efield_vectors:
                if self.plot_no_connection:
                    e_field_vectors = [
                        [list(self.e_field_col1_to_save)],
                        [list(self.e_field_col2_to_save)],
                        [list(self.e_field_col3_to_save)],
                    ]
                else:
                    e_field_vectors = list(self.max_efield_array)
                self.target_radius_list.append(
                    [
                        target_list_index,
                        self.coil_position_Trot,
                        self.coil_position,
                        efield_coords_position,
                        self.efield_coords,
                        enorms_list,
                        e_field_vectors,
                        self.Id_list,
                        self.Idmax,
                        self.focal_factor_members,
                        self.efield_threshold,
                        self.efield_ROISize,
                        self.mtms_coord,
                        self.diperdt,
                        self.ci,
                        self.co,
                        self.path_meshes,
                        self.meshes_file,
                        self.cortex_file,
                        self.coil_model,
                    ]
                )
            else:
                self.target_radius_list.append(
                    [
                        target_list_index,
                        self.Id_list,
                        enorms_list,
                        self.Idmax,
                        self.coil_position,
                        efield_coords_position,
                        self.efield_coords,
                        self.coil_position_Trot,
                    ]
                )

    def ClearSaveEfieldData(self):
        self.target_radius_list.clear()

    def GetTargetSavedEfieldData(self, target_index_list):
        if len(self.target_radius_list) > 0:
            target_index = 0
            for i in range(len(self.target_radius_list)):
                if target_index_list == self.target_radius_list[i][0]:
                    target_index = i
                    self.saved_target_data = self.target_radius_list[target_index]
                    break

    def CreateEfieldmTMSCoorlegend(self):
        self.mTMSCoordTextActor = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.4, 0.2)
        )
        self.ren.AddActor(self.mTMSCoordTextActor.actor)

    def GetTargetPathmTMS(self, targeting_file):
        self.targeting_file = targeting_file

    def GetTargetPositions(self, target1_origin, target2):
        if self.mTMSCoordTextActor is None:
            self.CreateEfieldmTMSCoorlegend()
        self.mtms_coord = None
        x_diff = round(target1_origin[0] - target2[0])
        y_diff = round(target1_origin[1] - target2[1])
        csv_filename = self.targeting_file
        target_numbers = [-x_diff, y_diff, 0]
        self.matching_row = self.find_and_extract_data(csv_filename, target_numbers)
        dIs = self.mTMS_multiplyFactor(1000)
        Publisher.sendMessage("Get dI for mtms", dIs=dIs)
        self.mTMSCoordTextActor.SetValue("mTMS coords: " + str(target_numbers))
        self.mtms_coord = target_numbers

    def GetdIsfromCoord(self, mtms_coord):
        if self.mTMSCoordTextActor is None:
            self.CreateEfieldmTMSCoorlegend()
        self.mtms_coord = None
        self.matching_row = self.find_and_extract_data(self.targeting_file, mtms_coord)
        dIs = self.mTMS_multiplyFactor(1000)
        Publisher.sendMessage("Get dI for mtms", dIs=dIs)
        self.mTMSCoordTextActor.SetValue("mTMS coords: " + str(mtms_coord))
        self.mtms_coord = mtms_coord

    def mTMS_multiplyFactor(self, factor):
        result = []
        for row in self.matching_row:
            convert = float(row) * factor
            result.append(convert)
        return result

    def find_and_extract_data(self, csv_filename, target_numbers):
        import csv

        matching_rows = []

        with open(csv_filename) as csvfile:
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                # Extract the first three numbers from the current row
                first_three_numbers = list(map(float, row[:3]))

                # Check if the first three numbers match the target numbers
                if first_three_numbers == target_numbers:
                    # If there's a match, append the row (excluding the first three numbers)
                    matching_rows = row[3:8]
                    break

        return matching_rows

    def CheckStatusSavedEfieldData(self):
        indexes_saved_list = []
        if len(self.target_radius_list) > 0:
            efield_data_loaded = True
            for i in range(len(self.target_radius_list)):
                indexes_saved_list.append(self.target_radius_list[i][0])
            indexes_saved_list = np.array(indexes_saved_list)
        else:
            efield_data_loaded = False
        Publisher.sendMessage(
            "Get status of Efield saved data",
            efield_data_loaded=efield_data_loaded,
            indexes_saved_list=indexes_saved_list,
        )

    def InitializeColorArray(self):
        self.colors_init.SetNumberOfComponents(3)
        self.colors_init.SetName("Colors")
        color = const.CORTEX_COLOR
        for i in range(self.efield_mesh.GetNumberOfCells()):
            self.colors_init.InsertTuple(i, color)

    def ReturnToDefaultColorActor(self):
        self.RemoveEfieldTargetingActors()
        self.efield_mesh.GetPointData().SetScalars(self.colors_init)
        wx.CallAfter(Publisher.sendMessage, "Initialize color array")
        wx.CallAfter(Publisher.sendMessage, "Recolor efield actor")

    def CreateLUTTableForEfield(self, min, max, highlight_threshold=False):
        lut = vtkLookupTable()
        lut.SetTableRange(min, max)
        colorSeries = vtkColorSeries()
        seriesEnum = colorSeries.BREWER_SEQUENTIAL_BLUE_PURPLE_9
        colorSeries.SetColorScheme(seriesEnum)
        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        n = lut.GetNumberOfTableValues()
        threshold = self.efield_threshold
        if highlight_threshold:
            highlight_rgb = (255, 165, 0)
            for i in range(n):
                norm_val = i / (n - 1)
                if norm_val >= threshold:
                    lut.SetTableValue(i, *(np.array(highlight_rgb) / 255.0), 1.0)
        return lut

    def UpdateEfieldScalarBar(self):
        if self.efield_scalar_bar is None or self.efield_lut is None:
            return

        self.efield_scalar_bar.SetLookupTable(self.efield_lut)
        self.efield_scalar_bar.Modified()
        if not self.ren.HasViewProp(self.efield_scalar_bar):
            self.ren.AddActor2D(self.efield_scalar_bar)

    def GetEfieldMaxMin(self, e_field_norms):
        self.e_field_norms = e_field_norms
        efield_max = np.amax(self.e_field_norms)
        efield_min = np.amin(self.e_field_norms)
        self.efield_min = efield_min
        self.efield_max = efield_max
        # self.Idmax = np.array(self.e_field_norms).argmax()
        wx.CallAfter(Publisher.sendMessage, "Update efield vis")

    def CreateEfieldScalarPolyData(self):
        values = np.asarray(self.e_field_norms, dtype=float)
        n_points = self.efield_mesh.GetNumberOfPoints()

        scalars = vtkDoubleArray()
        scalars.SetName("EFieldNorm")
        scalars.SetNumberOfComponents(1)
        scalars.SetNumberOfTuples(n_points)
        scalars.FillComponent(0, self.efield_min)

        if len(values) == n_points:
            for point_id, value in enumerate(values):
                scalars.SetValue(point_id, value)
        else:
            for point_id, value in zip(self.Id_list, values):
                scalars.SetValue(point_id, value)

        scalar_polydata = vtkPolyData()
        scalar_polydata.DeepCopy(self.efield_mesh)
        scalar_polydata.GetPointData().SetScalars(scalars)
        return scalar_polydata

    def CalculateEdgesEfield(self):
        self.RemoveEfieldEdges()
        if self.efield_max <= self.efield_min:
            return

        named_colors = vtkNamedColors()
        second_lut = self.CreateLUTTableForEfield(self.efield_min, self.efield_max)
        scalar_polydata = self.CreateEfieldScalarPolyData()

        bcf = vtkBandedPolyDataContourFilter()
        bcf.SetInputData(scalar_polydata)
        bcf.ClippingOn()
        bcf.SetScalarModeToValue()

        value_range = self.efield_max - self.efield_min
        contour_values = [
            self.efield_min,
            # self.efield_min + value_range * 0.2,
            self.efield_min + value_range * 0.7,
            self.efield_min + value_range * 0.9,
        ]
        for i, value in enumerate(contour_values):
            bcf.SetValue(i, value)
        bcf.GenerateContourEdgesOn()
        bcf.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(bcf.GetOutputPort())
        mapper.SetLookupTable(second_lut)
        mapper.SetScalarModeToUsePointData()
        mapper.SetScalarRange(self.efield_min, self.efield_max)

        self.edge_fill_actor = vtkActor()
        self.edge_fill_actor.SetMapper(mapper)

        edge_mapper = vtkPolyDataMapper()
        edge_mapper.SetInputData(bcf.GetContourEdgesOutput())
        edge_mapper.SetLookupTable(second_lut)
        edge_mapper.SetScalarRange(self.efield_min, self.efield_max)
        edge_mapper.ScalarVisibilityOff()
        edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()

        self.edge_actor = vtkActor()
        self.edge_actor.SetMapper(edge_mapper)
        self.edge_actor.GetProperty().SetColor(named_colors.GetColor3d("Black"))
        self.edge_actor.GetProperty().SetLineWidth(3.0)
        self.edge_fill_actor.GetProperty().SetOpacity(0)
        self.ren.AddViewProp(self.edge_fill_actor)
        self.ren.AddViewProp(self.edge_actor)

        self.UpdateEfieldScalarBar()

    def RemoveEfieldEdges(self):
        if self.edge_actor is not None:
            self.ren.RemoveViewProp(self.edge_actor)
            self.edge_actor = None
        if self.edge_fill_actor is not None:
            self.ren.RemoveViewProp(self.edge_fill_actor)
            self.edge_fill_actor = None

    def ShowEfieldContours(self, enable):
        self.show_efield_edges = enable
        if not enable:
            self.RemoveEfieldEdges()
            self.Refresh()
            return

        if (
            self.e_field_norms is not None
            and self.efield_mesh is not None
            and self.radius_list.GetNumberOfIds() != 0
            and not self.tracts_status
            and self.actor_tracts is None
        ):
            self.CalculateEdgesEfield()
            self.Refresh()

    def GetIndexesAboveThreshold(self, threshold):
        cell_id_indexes = []
        positions = []
        indexes = [
            index
            for index, value in enumerate(self.e_field_norms)
            if value > self.efield_max * threshold
        ]
        for index, value in enumerate(indexes):
            cell_id_indexes.append(self.Id_list[value])
            positions.append(self.efield_mesh.GetPoint(self.Id_list[value]))
        return [cell_id_indexes, positions]

    def UpdateEfieldThreshold(self, data):
        self.efield_threshold = data

    def UpdateEfieldROISize(self, data):
        self.efield_ROISize = data
        self.radius_list.Reset()
        self.last_efield_cell_id = None

    def EnableEfieldTools(self, enable):
        self.efield_tools = enable
        if self.efield_tools:
            self.CreateEfieldSpreadLegend()
            self.CreateClustersEfieldLegend()
        elif not self.efield_tools and self.ClusterEfieldTextActor is not None:
            self.ren.RemoveActor(self.ClusterEfieldTextActor.actor)
            self.ren.RemoveActor(self.SpreadEfieldFactorTextActor.actor)

    def FindCenterofGravity(self, cell_id_indexes, positions):
        if not cell_id_indexes or not positions:
            return None

        weights = []
        for index, value in enumerate(cell_id_indexes):
            weights.append(self.e_field_norms[index])
        sum_weights = sum(weights)
        if sum_weights == 0:
            return None

        x_weighted = []
        y_weighted = []
        z_weighted = []
        for i, (x, y, z) in enumerate(positions):
            x_weighted.append(x * weights[i])
            y_weighted.append(y * weights[i])
            z_weighted.append(z * weights[i])
        sum_x = sum(x_weighted)
        sum_y = sum(y_weighted)
        sum_z = sum(z_weighted)

        center_gravity_x = sum_x / sum_weights
        center_gravity_y = sum_y / sum_weights
        center_gravity_z = sum_z / sum_weights

        query_point = [center_gravity_x, center_gravity_y, center_gravity_z]
        center_gravity = [0.0, 0.0, 0.0]
        cell_id = mutable(0)
        sub_id = mutable(0)
        distance = mutable(0.0)
        self.locator_efield_cell.FindClosestPoint(
            query_point, center_gravity, cell_id, sub_id, distance
        )
        return center_gravity

    def DetectClustersEfieldSpread(self, points):
        from sklearn.cluster import DBSCAN
        from sklearn.metrics import pairwise_distances

        if (
            points is None
            or len(points) == 0
            or self.distance_efield is None
            or self.ClusterEfieldTextActor is None
            or getattr(self, "Id_list", None) is None
            or len(self.Id_list) == 0
        ):
            return

        points = np.array(points) if isinstance(points, list) else points
        dbscan = DBSCAN(eps=5, min_samples=1).fit(points)
        labels = dbscan.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        core_sample_indices = dbscan.core_sample_indices_
        cluster_centers = points[core_sample_indices, :]
        representative_centers = np.array(
            [
                cluster.mean(axis=0)
                for cluster in np.split(
                    cluster_centers,
                    np.cumsum(np.unique(dbscan.labels_, return_counts=True)[1])[:-1],
                )
            ]
        )
        distances_between_representatives = np.max(pairwise_distances(representative_centers))
        focal_factor = (
            n_clusters / len(self.Id_list)
            + distances_between_representatives / 30
            + self.distance_efield / 15
        )
        focal_factor = 1 / focal_factor
        self.ClusterEfieldTextActor.SetValue(
            "Clusters above "
            + str(int(self.efield_threshold * 100))
            + "% percent: "
            + str(n_clusters)
            + "\n"
            + "Distance: "
            + str(f"{distances_between_representatives:04.2f}")
            + "\n"
            + "Focal Factor: "
            + str(f"{focal_factor:04.2f}")
        )

        self.focal_factor_members = [
            n_clusters,
            n_clusters / len(self.Id_list),
            distances_between_representatives,
            distances_between_representatives / 30,
            self.distance_efield,
            self.distance_efield / 15,
            focal_factor,
        ]

    def CreateClustersEfieldLegend(self):
        self.ClusterEfieldTextActor = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.12, 0.99)
        )
        self.ren.AddActor(self.ClusterEfieldTextActor.actor)

    def EnableShowEfieldAboveThreshold(self, enable):
        self.enableefieldabovethreshold = enable

    def SegmentEfieldMax(self, cell_id_indexes):
        color = [255, 165, 0]
        for j, value in enumerate(cell_id_indexes):
            self.colors_init.InsertTuple(value, color)

    def GetEfieldActor(self, e_field_actor):
        self.efield_actor = e_field_actor

    def FindPointsAroundRadiusEfield(self, cellId):
        radius = int(self.efield_ROISize)
        self.locator_efield.FindPointsWithinRadius(
            radius, self.e_field_mesh_centers.GetPoint(cellId), self.radius_list
        )

    def CreateCortexProjectionOnScalp(self, marker_id, position, orientation):
        self.target_at_cortex = None
        self.scalp_mesh = self.scalp_actor.GetMapper().GetInput()
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.target_at_cortex = position_flip
        point_scalp = self.FindClosestPointToMesh(position_flip, self.scalp_mesh)
        self.CreateEfieldAtTargetLegend()
        Publisher.sendMessage(
            "Create Marker from tangential", point=point_scalp, orientation=orientation
        )

    def ClearTargetAtCortex(self):
        self.target_at_cortex = None
        if self.EfieldAtTargetLegend is not None:
            self.ren.RemoveActor(self.EfieldAtTargetLegend.actor)

    def SetEfieldTargetAtCortex(self, position, orientation):
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.target_at_cortex = position_flip
        self.CreateEfieldAtTargetLegend()

    def ShowEfieldAtCortexTarget(self):
        if self.target_at_cortex is not None:
            index = self.efield_mesh.FindPoint(self.target_at_cortex)
            if index in self.Id_list:
                cell_number = self.Id_list.index(index)
                self.EfieldAtTargetLegend.SetValue(
                    "Efield at Target: " + str(f"{self.e_field_norms[cell_number]:04.2f}")
                )
            else:
                self.EfieldAtTargetLegend.SetValue("Efield at Target: " + str(f"{0:04.2f}"))

    def CreateEfieldAtTargetLegend(self):
        if self.EfieldAtTargetLegend is not None:
            self.ren.RemoveActor(self.EfieldAtTargetLegend.actor)
        self.EfieldAtTargetLegend = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.4, 0.96)
        )
        self.ren.AddActor(self.EfieldAtTargetLegend.actor)

    def FindClosestPointToMesh(self, point, mesh):
        closest_distance = float("inf")
        closest_point = None
        point = np.array(point)
        for i in range(mesh.GetNumberOfCells()):
            distance_sq = np.linalg.norm(np.array(self.scalp_mesh.GetPoint(i)) - point)
            if distance_sq < closest_distance:
                closest_distance = distance_sq
                closest_point = self.scalp_mesh.GetPoint(i)
        return closest_point

    def GetScalpEfield(self, scalp_actor):
        self.scalp_actor = scalp_actor

    def InitEfield(self, e_field_brain):
        self.e_field_mesh_normals = e_field_brain.e_field_mesh_normals
        self.e_field_mesh_centers = e_field_brain.e_field_mesh_centers
        self.locator_efield = e_field_brain.locator_efield
        self.locator_efield_cell = e_field_brain.locator_efield_Cell
        self.efield_mesh = e_field_brain.e_field_mesh
        self.efield_mapper = e_field_brain.efield_mapper
        self.efield_mesh_normals_viewer = vtkPolyDataNormals()
        self.efield_mesh_normals_viewer.SetInputData(self.efield_mesh)
        self.efield_mesh_normals_viewer.SetFeatureAngle(80)
        self.efield_mesh_normals_viewer.AutoOrientNormalsOn()
        self.efield_mesh_normals_viewer.Update()
        self.efield_mapper.SetInputConnection(self.efield_mesh_normals_viewer.GetOutputPort())
        self.efield_mapper.ScalarVisibilityOn()
        self.efield_actor.SetMapper(self.efield_mapper)
        self.efield_actor.GetProperty().SetBackfaceCulling(1)
        self.efield_coords = None
        self.coil_position = None
        self.coil_position_Trot = None
        self.e_field_norms = None
        self.e_field_norms_to_save = None
        self.last_efield_cell_id = None
        self.efield_threshold = const.EFIELD_MAX_RANGE_SCALE
        self.efield_ROISize = const.EFIELD_ROI_SIZE
        self.target_radius_list = []
        self.focal_factor_members = []
        self.distance_efield = None
        self.mtms_coord = []
        # self.diperdt = None

        self.RemoveEfieldTargetingActors()
        self.RemoveEfieldVectorActor()

        if self.efield_scalar_bar is not None:
            self.ren.RemoveActor(self.efield_scalar_bar)

        if self.ClusterEfieldTextActor is not None:
            self.ren.RemoveActor(self.ClusterEfieldTextActor.actor)

        if self.SpreadEfieldFactorTextActor is not None:
            self.ren.RemoveActor(self.SpreadEfieldFactorTextActor.actor)

        self.efield_scalar_bar = e_field_brain.efield_scalar_bar

        if self.edge_actor is not None:
            self.ren.RemoveActor(self.edge_actor)

    def GetNeuronavigationApi(self, neuronavigation_api):
        self.neuronavigation_api = neuronavigation_api

    def ShowEfieldintheintersection(self, intersectingCellIds, p1, coil_norm, coil_dir):
        closestDist = 100
        closestCellId = None
        # if find intersection , calculate angle and add actors
        if intersectingCellIds.GetNumberOfIds() != 0:
            for i in range(intersectingCellIds.GetNumberOfIds()):
                cellId = intersectingCellIds.GetId(i)
                point = np.array(self.e_field_mesh_centers.GetPoint(cellId))
                distance = np.linalg.norm(point - p1)
                if distance < closestDist:
                    closestDist = distance
                    closestCellId = cellId
                    # closestPoint = point
                    # pointnormal = np.array(self.e_field_mesh_normals.GetTuple(cellId))
                    # angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
            if closestCellId is not None and closestCellId != self.last_efield_cell_id:
                self.FindPointsAroundRadiusEfield(closestCellId)
                self.radius_list.Sort()
                self.last_efield_cell_id = closestCellId
        else:
            self.radius_list.Reset()
            self.last_efield_cell_id = None

    def OnUpdateEfieldvis(self):
        if self.radius_list.GetNumberOfIds() != 0:
            self.efield_lut = self.CreateLUTTableForEfield(
                0, self.efield_max, highlight_threshold=self.enableefieldabovethreshold
            )
            [self.cell_id_indexes_above_threshold, self.positions_above_threshold] = (
                self.GetIndexesAboveThreshold(self.efield_threshold)
            )
            self.UpdateEfieldScalarBar()
            if not self.show_efield_edges or self.tracts_status or self.actor_tracts is not None:
                self.RemoveEfieldEdges()
            else:
                self.CalculateEdgesEfield()
            self.colors_init.SetNumberOfComponents(3)
            self.colors_init.Fill(const.CORTEX_COLOR[0])
            for h in range(len(self.Id_list)):
                dcolor = 3 * [0.0]
                index_id = self.Id_list[h]
                self.efield_lut.GetColor(self.e_field_norms[h], dcolor)
                color = 3 * [0.0]
                for j in range(0, 3):
                    color[j] = int(255.0 * dcolor[j])
                self.colors_init.InsertTuple(index_id, color)
            self.efield_mesh.GetPointData().SetScalars(self.colors_init)
            wx.CallAfter(Publisher.sendMessage, "Recolor efield actor")
            self.RemoveEfieldVectorActor()
            wx.CallAfter(Publisher.sendMessage, "Show max Efield actor")
            wx.CallAfter(Publisher.sendMessage, "Show CoG Efield actor")
            if self.efield_tools:
                wx.CallAfter(Publisher.sendMessage, "Show distance between Max and CoG Efield")
                if self.positions_above_threshold is not None:
                    self.DetectClustersEfieldSpread(self.positions_above_threshold)
            if self.enableefieldabovethreshold and self.cell_id_indexes_above_threshold is not None:
                self.SegmentEfieldMax(self.cell_id_indexes_above_threshold)
            self.ShowEfieldAtCortexTarget()
            if self.plot_no_connection:
                wx.CallAfter(Publisher.sendMessage, "Show Efield vectors")
                self.plot_vector = False
                self.plot_no_connection = False
        else:
            wx.CallAfter(Publisher.sendMessage, "Recolor again")

    def UpdateEfieldPointLocation(self, m_img, coord, queue_IDs):
        # TODO: In the future, remove the "put_nowait" and mesh processing to another module (maybe e_field.py)
        # this might work because a python instance from the 3D mesh can be edited in the thread. Check how to extract
        # the instance from the desired mesh for visualization and if it works. Optimally, there should be no
        # processing or threading related commands inside viewer_volume.
        [coil_dir, norm, coil_norm, p1] = self.ObjectArrowLocation(m_img, coord)
        intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        try:
            self.e_field_IDs_queue = queue_IDs
            if self.radius_list.GetNumberOfIds() != 0:
                if np.all(self.old_coord != coord):
                    self.e_field_IDs_queue.put_nowait(self.radius_list)
                self.old_coord = np.array([coord])
        except queue.Full:
            pass

    def UpdateTractSeedBasedEfield(
        self, coord_tracts_queue, fallback_m_img=None, current_revision=None
    ):
        if (
            getattr(self, "position_max", None) is None
            or self.position_max_revision != current_revision
        ):
            if fallback_m_img is not None:
                try:
                    m_img_flip = fallback_m_img.copy()
                    m_img_flip[1, -1] = -m_img_flip[1, -1]
                    coord_tracts_queue.clear()
                    coord_tracts_queue.put_nowait(m_img_flip)
                except queue.Full:
                    pass
            return

        if not np.all(np.isfinite(self.position_max)):
            return

        orientation = [0, 0, 0]
        m_img = tr.compose_matrix(angles=np.radians(orientation), translate=self.position_max)
        try:
            coord_tracts_queue.clear()
            coord_tracts_queue.put_nowait(m_img)
        except queue.Full:
            pass

    def UpdateEfieldPointLocationOffline(self, m_img, coord, list_index):
        [coil_dir, norm, coil_norm, p1] = self.ObjectArrowLocation(m_img, coord)
        intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        id_list = []
        for h in range(self.radius_list.GetNumberOfIds()):
            id_list.append(self.radius_list.GetId(h))
        Publisher.sendMessage("Get ID list", ID_list=id_list)
        self.plot_no_connection = True
        self.list_index_efield_vectors = list_index

    def GetCoilPosition(self, position, orientation):
        m_img = tr.compose_matrix(angles=np.radians(orientation), translate=position)
        m_img_flip = m_img.copy()
        # m_img_flip[1, -1] = -m_img_flip[1, -1]
        cp = m_img_flip[:-1, -1]  # coil center
        cp = cp * 0.001  # convert to meters
        cp = cp.tolist()

        ct1 = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
        ct2 = m_img_flip[:3, 0]  # is from left to right direction of the coil
        coil_dir = m_img_flip[:-1, 0]
        coil_face = m_img_flip[:-1, 1]
        cn = np.cross(coil_dir, coil_face)
        T_rot = np.append(-ct1, ct2, axis=0)
        T_rot = np.append(T_rot, cn, axis=0)  # append
        T_rot = T_rot.tolist()  # to list
        Publisher.sendMessage("Send coil position and rotation", T_rot=T_rot, cp=cp, m_img=m_img)

    def GetEnorm(self, enorm_data, plot_vector, current_revision=None):
        result_revision = enorm_data[5] if len(enorm_data) > 5 else current_revision
        if current_revision is not None and result_revision != current_revision:
            self.RemoveEfieldTargetingActors()
            return

        if enorm_data[3] is None:
            self.RemoveEfieldTargetingActors()
            return

        self.e_field_col1 = []
        self.e_field_col2 = []
        self.e_field_col3 = []
        session = ses.Session()
        self.plot_vector = plot_vector
        self.efield_data_revision = result_revision
        self.coil_position_Trot = enorm_data[0]
        self.coil_position = enorm_data[1]
        self.efield_coords = enorm_data[2]
        self.Id_list = enorm_data[4]
        if session.GetConfig("debug_efield"):
            self.e_field_norms = enorm_data[3][self.Id_list, 0]
            self.e_field_col1 = enorm_data[3][self.Id_list, 1]
            self.e_field_col2 = enorm_data[3][self.Id_list, 2]  # LUKATODO: is this a typo?
            self.e_field_col3 = enorm_data[3][self.Id_list, 3]
            self.Idmax = np.array(self.Id_list[np.array(self.e_field_norms).argmax()])
            max_idx = np.array(self.e_field_norms).argmax()
            self.max_efield_array = [
                self.e_field_col1[max_idx],
                self.e_field_col2[max_idx],
                self.e_field_col3[max_idx],
            ]
            self.e_field_norms_to_save = enorm_data[3][:, 0]
            self.e_field_col1_to_save = enorm_data[3][:, 1]
            self.e_field_col2_to_save = enorm_data[3][:, 2]
            self.e_field_col3_to_save = enorm_data[3][:, 3]
        else:
            if not hasattr(enorm_data[3], "enorm") or not hasattr(enorm_data[3], "mvector"):
                self.RemoveEfieldTargetingActors()
                return

            self.e_field_norms_to_save = enorm_data[3].enorm
            if len(self.e_field_norms_to_save) == 0:
                self.RemoveEfieldTargetingActors()
                return
            if self.Id_list and max(self.Id_list) >= len(self.e_field_norms_to_save):
                self.RemoveEfieldTargetingActors()
                return

            self.e_field_norms = [self.e_field_norms_to_save[i] for i in self.Id_list]
            self.e_field_col1 = enorm_data[3].column1
            self.e_field_col2 = enorm_data[3].column2
            self.e_field_col3 = enorm_data[3].column3
            self.e_field_col1_to_save = enorm_data[3].column1
            self.e_field_col2_to_save = enorm_data[3].column2
            self.e_field_col3_to_save = enorm_data[3].column3
            if len(self.e_field_col1) > 1:
                K = len(self.e_field_norms_to_save)
                col1 = np.asarray(self.e_field_col1, dtype=float)
                col2 = np.asarray(self.e_field_col2, dtype=float)
                col3 = np.asarray(self.e_field_col3, dtype=float)
                N = col1.size // K
                if N > 1:
                    self.e_field_col1 = col1.reshape(N, -1).sum(axis=0)
                    self.e_field_col2 = col2.reshape(N, -1).sum(axis=0)
                    self.e_field_col3 = col3.reshape(N, -1).sum(axis=0)

                self.e_field_col1 = [self.e_field_col1[i] for i in self.Id_list]
                self.e_field_col2 = [self.e_field_col2[i] for i in self.Id_list]
                self.e_field_col3 = [self.e_field_col3[i] for i in self.Id_list]

            self.max_efield_array = enorm_data[3].mvector
            self.Idmax = enorm_data[3].maxindex
            if self.save_automatically and self.plot_no_connection:
                import time

                import invesalius.gui.dialogs as dlg
                import invesalius.project as prj

                proj = prj.Project()
                timestamp = time.localtime(time.time())
                stamp_date = (
                    f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
                )
                stamp_time = (
                    f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
                )
                sep = "-"

                if self.path_meshes is None:
                    import os

                    current_folder_path = os.getcwd()
                else:
                    current_folder_path = self.path_meshes

                parts = [current_folder_path, "/", stamp_date, stamp_time, proj.name, "Efield"]
                default_filename = sep.join(parts) + ".csv"

                filename = dlg.ShowLoadSaveDialog(
                    message=_("Save markers as..."),
                    wildcard="(*.csv)|*.csv",
                    style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                    default_filename=default_filename,
                )

                if not filename:
                    return

                Publisher.sendMessage(
                    "Save Efield data",
                    filename=filename,
                    plot_efield_vectors=self.plot_efield_vectors,
                    marker_id=self.list_index_efield_vectors,
                )
        self.GetEfieldMaxMin(self.e_field_norms)

    def SaveEfieldData(self, filename, plot_efield_vectors, marker_id):
        import csv

        import invesalius.data.imagedata_utils as imagedata_utils

        all_data = []

        header = [
            "Marker ID",
            "Rotation matrix for coil coordinates",
            "Coil center",
            "Coil position in world coordinates",
            "InVesalius coordinates",
            "Enorm",
            "Efield vectors",
            "Enorm cell indexes (ROI)",
            "ID cell max",
            "Focal factors",
            "Efield threshold",
            "Efield ROI size",
            "mTMS coordinates",
            "diperdt",
            "ci",
            "co",
            "path meshes",
            "meshes file",
            "cortex file",
            "coil model file",
        ]
        if self.efield_coords is not None:
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
                orientation=[self.efield_coords[3], self.efield_coords[4], self.efield_coords[5]],
            )
            efield_coords_position = [list(position_world), list(orientation_world)]
        if plot_efield_vectors:
            if self.plot_no_connection:
                e_field_vectors = [
                    [list(self.e_field_col1_to_save)],
                    [list(self.e_field_col2_to_save)],
                    [list(self.e_field_col3_to_save)],
                ]
            else:
                e_field_vectors = list(self.max_efield_array)
            all_data.append(
                [
                    marker_id,
                    self.coil_position_Trot,
                    self.coil_position,
                    efield_coords_position,
                    self.efield_coords,
                    list(self.e_field_norms_to_save),
                    e_field_vectors,
                    self.Id_list,
                    self.Idmax,
                    self.focal_factor_members,
                    self.efield_threshold,
                    self.efield_ROISize,
                    self.mtms_coord,
                    self.diperdt,
                    self.ci,
                    self.co,
                    self.path_meshes,
                    self.meshes_file,
                    self.cortex_file,
                    self.coil_model,
                ]
            )

        else:
            all_data.append(
                [
                    marker_id,
                    self.coil_position_Trot,
                    self.coil_position,
                    efield_coords_position,
                    self.efield_coords,
                    list(self.e_field_norms_to_save),
                ]
            )

        with open(filename, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(all_data)

    def SavedAllEfieldData(self, filename):
        import csv

        header = [
            "Marker ID",
            "Rotation matrix for coil coordinates",
            "Coil center",
            "Coil position in world coordinates",
            "InVesalius coordinates",
            "Enorm",
            "Efield vectors",
            "Enorm cell indexes (ROI)",
            "ID cell Max",
            "Focal factors",
            "Efield threshold",
            "Efield ROI size",
            "mTMS coordinates",
            "diperdt",
            "ci",
            "co",
            "path meshes",
            "meshes file",
            "cortex file",
            "coil model file",
        ]
        all_data = list(self.target_radius_list)
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(all_data)

    def Getdiperdtforreport(self, diperdt, ci, co):
        self.diperdt = diperdt
        self.ci = ci
        self.co = co

    def Get_meshes_paths_to_report(self, path_meshes, cortex_file, meshes_file, coilmodel):
        self.meshes_file = meshes_file
        self.cortex_file = cortex_file
        self.path_meshes = path_meshes
        self.coil_model = coilmodel

    def GetCellIntersection(self, p1, p2, locator):
        # vtk_colors = vtkNamedColors()
        # This find store the triangles that intersect the coil's normal
        intersectingCellIds = vtkIdList()
        locator.FindCellsAlongLine(p1, p2, 0.001, intersectingCellIds)
        return intersectingCellIds

    def ShowCoilProjection(self, intersectingCellIds, p1, coil_norm, coil_dir):
        # vtk_colors = vtkNamedColors()
        closestDist = 50

        # If intersection is was found, calculate angle and add actors.
        if intersectingCellIds.GetNumberOfIds() != 0:
            for i in range(intersectingCellIds.GetNumberOfIds()):
                cellId = intersectingCellIds.GetId(i)
                point = np.array(self.peel_centers.GetPoint(cellId))
                distance = np.linalg.norm(point - p1)

                if distance < closestDist:
                    closestDist = distance
                    closestPoint = point
                    pointnormal = np.array(self.peel_normals.GetTuple(cellId))
                    angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
                    # print('the angle:', angle)

                    self.ren.AddActor(self.obj_projection_arrow_actor)
                    self.ren.AddActor(self.object_orientation_torus_actor)
                    self.obj_projection_arrow_actor.SetPosition(closestPoint)
                    self.obj_projection_arrow_actor.SetOrientation(coil_dir)

                    self.object_orientation_torus_actor.SetPosition(closestPoint)
                    self.object_orientation_torus_actor.SetOrientation(coil_dir)

                    # change color of arrow and disk according to angle
                    if angle < self.angle_arrow_projection_threshold:
                        self.object_orientation_torus_actor.GetProperty().SetDiffuseColor(
                            [51 / 255, 176 / 255, 102 / 255]
                        )
                        self.obj_projection_arrow_actor.GetProperty().SetColor(
                            [55 / 255, 120 / 255, 163 / 255]
                        )
                    else:
                        self.object_orientation_torus_actor.GetProperty().SetDiffuseColor(
                            [240 / 255, 146 / 255, 105 / 255]
                        )
                        self.obj_projection_arrow_actor.GetProperty().SetColor(
                            [240 / 255, 146 / 255, 105 / 255]
                        )
        else:
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        self.tracts_status = vis_status[1]

        if self.nav_status:
            self.pTarget = self.CenterOfMass()
            self.RemoveEfieldVectorActor()

        self.camera_show_object = None
        self._update_fps_visibility()
        if not self.nav_status:
            self.UpdateRender()

    def UpdateSeedOffset(self, data):
        self.seed_offset = data

    def UpdateMarkerOffsetState(self, create=False):
        if create:
            if not self.mark_actor:
                self.mark_actor = self.actor_factory.CreateBall(
                    position=[0.0, 0.0, 0.0],
                    colour=[0.0, 1.0, 1.0],
                    size=1.5,
                )
                self.ren.AddActor(self.mark_actor)
        else:
            if self.mark_actor:
                self.ren.RemoveActor(self.mark_actor)
                self.mark_actor = None
        if not self.nav_status:
            self.UpdateRender()

    def UpdateArrowPose(self, m_img, coord, flag):
        [coil_dir, norm, coil_norm, p1] = self.ObjectArrowLocation(m_img, coord)

        if flag and self.efield_mesh is None:
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator)
            self.ShowCoilProjection(intersectingCellIds, p1, coil_norm, coil_dir)

    def TrackObject(self, enabled):
        if enabled:
            vtk_colors = vtkNamedColors()
            self.obj_projection_arrow_actor = self.actor_factory.CreateArrowUsingDirection(
                position=[0.0, 0.0, 0.0],
                orientation=[0.0, 0.0, 0.0],
                colour=vtk_colors.GetColor3d("Red"),
                length_multiplier=0.8,
            )
            self.object_orientation_torus_actor = self.actor_factory.CreateTorus(
                position=[0.0, 0.0, 0.0],
                orientation=[0.0, 0.0, 0.0],
                colour=vtk_colors.GetColor3d("Red"),
            )
        else:
            self.ren.RemoveActor(self.mark_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)

            self.mark_actor = None
            self.obj_projection_arrow_actor = None
            self.object_orientation_torus_actor = None

    def OnUpdateTracts(self, root=None, affine_vtk=None, coord_offset=None, coord_offset_w=None):
        self.tracts_status = True
        self.RemoveEfieldEdges()
        mapper = vtkCompositePolyDataMapper()
        mapper.SetInputDataObject(root)

        self.actor_tracts = vtkActor()
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
        self.tracts_status = False

    def SetVolumetricCamera(self, enabled):
        self.use_volumetric_camera = enabled
        self.camera_show_object = None

    def VolumetricCamera(self, cam_focus):
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

        if self.camera_show_object is None:
            self.camera_show_object = self.coil_visualizer.show_coil

        if self.camera_show_object:
            v1 = np.array(
                [
                    cam_focus[0] - self.pTarget[0],
                    cam_focus[1] - self.pTarget[1],
                    cam_focus[2] - self.pTarget[2],
                ]
            )
        else:
            v1 = cam_focus - self.initial_focus

        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1 / v1n) * v0n + cam_focus

        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)
