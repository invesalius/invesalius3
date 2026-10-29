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
import os
import time

import numpy as np
import wx
from vtkmodules.vtkFiltersSources import (
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
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.data.navigation_scene import NavigationScene
from invesalius.data.visualization.eeg_visualizer import EEGElectrodeVisualizer
from invesalius.data.visualization.probe_visualizer import ProbeVisualizer
from invesalius.data.visualization.vector_field_visualizer import VectorFieldVisualizer
from invesalius.math_utils import inner1d
from invesalius.navigation.eeg_electrodes import EEGElectrodeManager
from invesalius.navigation.efield_navigation import EFieldNavigation
from invesalius.pubsub import pub as Publisher


class NavigationView:
    """Add navigation behavior to an existing volume viewer."""

    def __init__(self, view, *, markers=(), main_coil=None):
        self.view = view
        self._active = False
        self._disposed = False
        self._volume_state = None
        self._navigation_camera_settings = None
        self._navigation_interaction_state = None
        self._navigation_renderers = []
        self._nav_status = False
        self.scene = NavigationScene(view.ren, view.actor_factory)
        self.scenes = [self.scene]
        self.scenes_by_coil = {}
        self.ren = self.scene.ren
        self._associate_scene_with_coil(self.scene, main_coil)

        self._initialize_navigation_data()
        self._initialize_sensor_data()
        self._initialize_navigation_state()
        self._initialize_navigation_visualizers()
        self._create_navigation_renderer()
        self._bind_events()
        self._restore_navigation_markers(markers)
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
        return self.scene.target_mode

    @target_mode.setter
    def target_mode(self, value):
        self.scene.target_mode = value
        if self._active:
            self.view.target_mode = value

    @property
    def target_coord(self):
        return self.scene.target_coord

    @target_coord.setter
    def target_coord(self, value):
        self.scene.target_coord = value

    @property
    def coil_visualizer(self):
        """Return the coil visualizer owned by the primary scene."""
        return self.scene.coil_visualizer

    @property
    def obj_projection_arrow_actor(self):
        """Return the projection arrow owned by the primary scene."""
        return self.scene.obj_projection_arrow_actor

    @obj_projection_arrow_actor.setter
    def obj_projection_arrow_actor(self, actor):
        self.scene.obj_projection_arrow_actor = actor

    @property
    def object_orientation_torus_actor(self):
        """Return the orientation torus owned by the primary scene."""
        return self.scene.object_orientation_torus_actor

    @object_orientation_torus_actor.setter
    def object_orientation_torus_actor(self, actor):
        self.scene.object_orientation_torus_actor = actor

    def _associate_scene_with_coil(self, scene, coil_name):
        if scene.coil_name == coil_name:
            return

        if scene.coil_name is not None:
            self.scenes_by_coil.pop(scene.coil_name, None)

        if coil_name is not None:
            self.scenes_by_coil[coil_name] = scene

        # Changing the live coil keeps the current target and its coordinates.
        scene.refresh_target_coil()
        scene.set_coil(coil_name)

    def _get_scene_for_coil(self, coil_name):
        return self.scenes_by_coil.get(coil_name)

    def _get_scene_for_update(self, coil_name):
        if coil_name is None:
            return self.scene
        return self._get_scene_for_coil(coil_name)

    def activate(self):
        if self._disposed or self._active:
            return
        first_activation = self._navigation_camera_settings is None
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
            if renderer is not self.scene.target_guide_renderer or self.target_mode:
                self._attach_renderer(renderer)
        self._apply_scene_viewport()
        if self.target_mode:
            self.scene.reset_target_guide_camera()
        if first_activation:
            self._initialize_navigation_ui()
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
        self.probe_visualizer.dispose()
        self.eeg_visualizer.dispose()
        self.vector_field_visualizer.dispose()
        self.efield.dispose()
        for scene in self.scenes:
            scene.dispose()
        for renderer in self._navigation_renderers:
            self._detach_renderer(renderer)
        self._navigation_renderers.clear()
        self.scenes_by_coil.clear()
        self.scenes.clear()
        self.view.target_guide_renderer = None

    def _add_scene_renderer(self, renderer):
        if renderer not in self._navigation_renderers:
            self._navigation_renderers.append(renderer)
        if self._active and (renderer is not self.scene.target_guide_renderer or self.target_mode):
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
        self.view.target_guide_renderer = self.scene.target_guide_renderer

        self._add_scene_renderer(self.scene.target_guide_renderer)
        self.ren.AddActor(self.fps_text.actor)
        self.fps_text.Hide()

    def _apply_scene_viewport(self):
        self.view._apply_scene_viewport()
        if self.target_mode:
            self._set_renderer_viewport(self.ren, (0.0, 0.0, 0.75, 1.0))
            self._set_renderer_viewport(self.scene.target_guide_renderer, (0.75, 0.0, 1.0, 1.0))
        else:
            self._set_renderer_viewport(self.scene.target_guide_renderer, (0.0, 0.0, 1.0, 1.0))

        for name, viewport in (
            ("ren_probe", (0.01, 0.79, 0.15, 0.97)),
            ("ren_ref", (0.01, 0.57, 0.15, 0.79)),
            ("ren_obj", (0.01, 0.40, 0.15, 0.57)),
        ):
            renderer = getattr(self, name, None)
            if renderer is not None:
                self._set_renderer_viewport(renderer, viewport)

        for scene in self.scenes:
            if scene.robot_force_visualizer is not None:
                self._set_renderer_viewport(
                    scene.robot_force_visualizer.ren_force, (0.01, 0.23, 0.15, 0.35)
                )

    def _initialize_navigation_state(self):
        self.obj_axes = None
        self.coil_path = False
        self.show_coil = False

        # self.obj_axes = None
        self._to_show_ball = 0
        self.highlighted_marker_index = None

        self.probe = False
        self.ref = False
        self.obj = False

        self.dummy_probe_actor = None
        self.dummy_ref_actor = None
        self.dummy_obj_actor = None

        # Set the angle and distance thresholds.
        session = ses.Session()
        angle_threshold = session.GetConfig("angle_threshold", const.DEFAULT_ANGLE_THRESHOLD)
        distance_threshold = session.GetConfig(
            "distance_threshold", const.DEFAULT_DISTANCE_THRESHOLD
        )

        self.angle_threshold = angle_threshold
        self.distance_threshold = distance_threshold

        self.angle_arrow_projection_threshold = const.COIL_ANGLE_ARROW_PROJECTION_THRESHOLD

        self.actor_peel = None

    def _initialize_navigation_visualizers(self):
        self.projection_actor = None

        # An object that can be used to create vector fields in the 3D viewer.
        self.vector_field_visualizer = VectorFieldVisualizer(
            actor_factory=self.actor_factory,
        )

        navigation_state = ses.Session().GetConfig("navigation", {})
        for scene in self.scenes:
            scene.initialize_visualizers(
                self.vector_field_visualizer,
                interactor=self.interactor,
                track_object=navigation_state.get("track_coil", False),
            )
            self._add_scene_renderer(scene.robot_force_visualizer.ren_force)

        self.probe_visualizer = ProbeVisualizer(self.ren)
        self.eeg_electrodes = EEGElectrodeManager()
        self.eeg_visualizer = EEGElectrodeVisualizer(
            self.ren, self.actor_factory, self.eeg_electrodes
        )
        self.OnEEGRegistrationModeChanged(self.eeg_electrodes.registration_active)
        for scene in self.scenes:
            self.probe_visualizer.add_renderer(scene.ren)

        self.seed_offset = const.SEED_OFFSET
        self.efield = EFieldNavigation(
            self.scene, self.interactor, self.actor_factory, self.Refresh
        )

    def _restore_navigation_markers(self, markers):
        markers = tuple(markers)
        for scene in self.scenes:
            scene.restore_markers(markers)

    def _initialize_navigation_ui(self):
        # Restore target mode after activation so cameras use the attached renderers.
        enabled = self.scene.target_marker is not None
        self.SetTargetMode(enabled=enabled)
        Publisher.sendMessage("Press target mode button", pressed=enabled)

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
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")
        Publisher.subscribe(self.OnEEGRegistrationModeChanged, "EEG registration mode changed")
        Publisher.subscribe(self.UpdateEEGCamera, "Update probe pose")
        Publisher.subscribe(self.UpdateArrowPose, "Update object arrow matrix")
        Publisher.subscribe(self.TrackObject, "Track object")
        Publisher.subscribe(self.SetTargetMode, "Set target mode")
        Publisher.subscribe(self.OnUpdateCoilPoses, "Update coil poses")
        Publisher.subscribe(self.OnSelectCoil, "Select coil")
        Publisher.subscribe(self.OnMainCoilChanged, "Main coil changed")
        Publisher.subscribe(self.OnSetTarget, "Set target")
        Publisher.subscribe(self.OnUnsetTarget, "Unset target")
        Publisher.subscribe(self.OnUpdateAngleThreshold, "Update angle threshold")
        Publisher.subscribe(self.OnUpdateDistanceThreshold, "Update distance threshold")
        Publisher.subscribe(self.OnUpdateTracts, "Update tracts")
        Publisher.subscribe(self.OnRemoveTracts, "Remove tracts")
        Publisher.subscribe(self.UpdateSeedOffset, "Update seed offset")
        Publisher.subscribe(self.UpdateMarkerOffsetState, "Update marker offset state")
        Publisher.subscribe(self.AddPeeledSurface, "Update peel")
        Publisher.subscribe(self.UpdatePeelVisibility, "Update peel visibility")
        Publisher.subscribe(self.GetPeelCenters, "Get peel centers and normals")
        Publisher.subscribe(self.InitLocatorViewer, "Get init locator")

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

    def EnableTargetMode(self, scene=None):
        scene = scene or self.scene
        was_enabled = scene.target_mode
        scene.enable_target_mode(hide_projection=bool(self.actor_peel))
        if scene is self.scene and self._active:
            self.view.target_mode = scene.target_mode
        if self._active:
            self._attach_renderer(scene.target_guide_renderer)
        self._apply_scene_viewport()
        if scene.target_mode and not was_enabled:
            scene.initialize_target_cameras()
        if not self.nav_status:
            self.UpdateRender()

    def DisableTargetMode(self, scene=None):
        scene = scene or self.scene
        scene.disable_target_mode(show_projection=bool(self.actor_peel))
        if scene is self.scene and self._active:
            self.view.target_mode = False
        self._apply_scene_viewport()
        self._detach_renderer(scene.target_guide_renderer)
        if not self.nav_status:
            self.UpdateRender()

    def SetTargetMode(self, enabled=False):
        if self.target_coord is None:
            return
        if enabled:
            self.EnableTargetMode(self.scene)
        else:
            self.DisableTargetMode(self.scene)

    def OnUpdateCoilPoses(self, m_imgs, coords):
        for scene in self.scenes:
            coil_name = scene.coil_name
            if coil_name not in m_imgs or coil_name not in coords:
                continue
            targeting = scene.update_coil_pose(
                m_imgs[coil_name],
                coords[coil_name],
                angle_threshold=self.angle_threshold,
                distance_threshold=self.distance_threshold,
            )
            if targeting is None:
                continue
            coil_at_target, displacement = targeting
            wx.CallAfter(
                Publisher.sendMessage,
                "Coil at target",
                state=coil_at_target,
                displacement=displacement,
                coil_name=coil_name,
            )

    def OnSelectCoil(self, coil_name, coil_registration):
        if coil_registration is not None:
            for scene in self.scenes:
                if scene.coil_name == coil_name:
                    scene.refresh_target_coil()

    def OnMainCoilChanged(self, coil_name):
        if len(self.scenes) == 1:
            self._associate_scene_with_coil(self.scene, coil_name)

    def OnUnsetTarget(self, marker):
        for scene in self.scenes:
            if scene.target_marker is marker:
                self.DisableTargetMode(scene)
                scene.unset_target()

    def OnSetTarget(self, marker):
        self.scene.set_target(marker)

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

    def AddPeeledSurface(self, flag, actor):
        """Update the peel; pose updates position and display coil projection actors."""
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

        if not self.nav_status:
            self.UpdateRender()

    def GetPeelCenters(self, centers, normals):
        self.peel_centers = centers
        self.peel_normals = normals

    def UpdatePeelVisibility(self, visible):
        if not visible:
            for scene in self.scenes:
                scene.ren.RemoveActor(scene.obj_projection_arrow_actor)
                scene.ren.RemoveActor(scene.object_orientation_torus_actor)

    def InitLocatorViewer(self, locator):
        self.locator = locator

    def ShowCoilProjection(self, intersectingCellIds, p1, coil_norm, coil_dir, scene=None):
        scene = scene or self.scene
        renderer = scene.ren
        projection_arrow = scene.obj_projection_arrow_actor
        orientation_torus = scene.object_orientation_torus_actor
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

                    renderer.AddActor(projection_arrow)
                    renderer.AddActor(orientation_torus)
                    projection_arrow.SetPosition(closestPoint)
                    projection_arrow.SetOrientation(coil_dir)

                    orientation_torus.SetPosition(closestPoint)
                    orientation_torus.SetOrientation(coil_dir)

                    # change color of arrow and disk according to angle
                    if angle < self.angle_arrow_projection_threshold:
                        orientation_torus.GetProperty().SetDiffuseColor(
                            [51 / 255, 176 / 255, 102 / 255]
                        )
                        projection_arrow.GetProperty().SetColor([55 / 255, 120 / 255, 163 / 255])
                    else:
                        orientation_torus.GetProperty().SetDiffuseColor(
                            [240 / 255, 146 / 255, 105 / 255]
                        )
                        projection_arrow.GetProperty().SetColor([240 / 255, 146 / 255, 105 / 255])
        else:
            renderer.RemoveActor(projection_arrow)
            renderer.RemoveActor(orientation_torus)

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        self.scene.tracts_status = vis_status[1]

        if self.nav_status:
            self.scene.pTarget = self.CenterOfMass()
            self.efield.visualizer.RemoveEfieldVectorActor()

        if not self.eeg_electrodes.registration_active:
            self.scene.camera_show_object = None
        self._update_fps_visibility()
        if not self.nav_status:
            self.UpdateRender()

    def UpdateSeedOffset(self, data):
        self.seed_offset = data

    def UpdateMarkerOffsetState(self, create=False):
        self._update_scene_marker_offset_state(self.scene, create)

    def _update_scene_marker_offset_state(self, scene, create):
        if create:
            if not scene.mark_actor:
                scene.mark_actor = self.actor_factory.CreateBall(
                    position=[0.0, 0.0, 0.0],
                    colour=[0.0, 1.0, 1.0],
                    size=1.5,
                )
                scene.ren.AddActor(scene.mark_actor)
        else:
            if scene.mark_actor:
                scene.ren.RemoveActor(scene.mark_actor)
                scene.mark_actor = None
        if not self.nav_status:
            self.UpdateRender()

    def UpdateArrowPose(self, m_img, coord, flag, coil_name=None):
        scene = self._get_scene_for_update(coil_name)
        if scene is None or scene.obj_projection_arrow_actor is None:
            return

        [coil_dir, norm, coil_norm, p1] = tr.coil_projection_ray(m_img, coord)

        if self.actor_peel is not None and self.actor_peel.GetVisibility():
            scene.ren.RemoveActor(scene.obj_projection_arrow_actor)
            scene.ren.RemoveActor(scene.object_orientation_torus_actor)
            intersectingCellIds = vtku.find_cells_along_line(p1, norm, self.locator)
            self.ShowCoilProjection(intersectingCellIds, p1, coil_norm, coil_dir, scene=scene)

    def TrackObject(self, enabled=False):
        for scene in self.scenes:
            scene.track_object(enabled)

    def OnUpdateTracts(
        self,
        root=None,
        affine_vtk=None,
        coord_offset=None,
        coord_offset_w=None,
        coil_name=None,
    ):
        scene = self._get_scene_for_update(coil_name)
        if scene is None:
            return

        scene.tracts_status = True
        self.efield.visualizer.RemoveEfieldEdges()
        mapper = vtkCompositePolyDataMapper()
        mapper.SetInputDataObject(root)

        scene.actor_tracts = vtkActor()
        scene.actor_tracts.SetMapper(mapper)
        scene.actor_tracts.SetUserMatrix(affine_vtk)

        scene.ren.AddActor(scene.actor_tracts)
        if scene.mark_actor:
            scene.mark_actor.SetPosition(coord_offset)
        self.Refresh()

    def OnRemoveTracts(self, coil_name=None):
        scenes = self.scenes if coil_name is None else [self._get_scene_for_coil(coil_name)]
        for scene in scenes:
            if scene is None:
                continue
            if scene.actor_tracts:
                scene.ren.RemoveActor(scene.actor_tracts)
                scene.actor_tracts = None
                self.Refresh()
            scene.tracts_status = False

    def SetVolumetricCamera(self, enabled, scene=None):
        scene = scene or self.scene
        scene.use_volumetric_camera = enabled
        scene.camera_show_object = None

    def OnEEGRegistrationModeChanged(self, active):
        self.SetVolumetricCamera(active)
        if active:
            self.scene.camera_show_object = True

    def UpdateEEGCamera(self, m_img, coord, probe_visible, head_visible):
        if not (self.eeg_electrodes.registration_active and probe_visible and head_visible):
            return
        position = np.asarray(coord[:3], dtype=float).copy()
        position[1] *= -1
        self.VolumetricCamera(position)

    def VolumetricCamera(self, cam_focus, scene=None):
        scene = scene or self.scene
        # TODO: exclude dependency on initial focus
        # cam_focus = np.array(bases.flip_x(position[:3]))
        # cam_focus = np.array(bases.flip_x(position))
        cam = scene.ren.GetActiveCamera()

        if scene.initial_focus is None:
            scene.initial_focus = np.array(cam.GetFocalPoint())

        cam_pos0 = np.array(cam.GetPosition())
        cam_focus0 = np.array(cam.GetFocalPoint())
        v0 = cam_pos0 - cam_focus0
        v0n = np.sqrt(inner1d(v0, v0))

        if scene.camera_show_object is None:
            scene.camera_show_object = scene.coil_visualizer.show_coil

        if scene.camera_show_object:
            v1 = np.array(
                [
                    cam_focus[0] - scene.pTarget[0],
                    cam_focus[1] - scene.pTarget[1],
                    cam_focus[2] - scene.pTarget[2],
                ]
            )
        else:
            v1 = cam_focus - scene.initial_focus

        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1 / v1n) * v0n + cam_focus

        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)
