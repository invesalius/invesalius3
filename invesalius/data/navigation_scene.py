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
from scipy.spatial import distance
from vtkmodules.vtkCommonColor import vtkNamedColors
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer

import invesalius.constants as const
import invesalius.data.coregistration as dcr
import invesalius.data.vtk_utils as vtku
from invesalius import inv_paths
from invesalius.data.visualization.coil_visualizer import CoilVisualizer
from invesalius.data.visualization.marker_visualizer import MarkerVisualizer
from invesalius.data.visualization.robot_force_visualizer import RobotForceVisualizer
from invesalius.i18n import tr as _
from invesalius.math_utils import inner1d
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

    def set_prop_visibility(self, prop, visible):
        """Set managed visibility even while this renderer is inactive."""
        if prop not in self._props:
            return
        self._props[prop] = bool(visible)
        prop.SetVisibility(bool(visible) if self._active else False)

    def owns_prop(self, prop):
        return prop in self._props

    def dispose(self):
        for prop in self._props:
            self.renderer.RemoveViewProp(prop)
        self._props.clear()
        self._active = False


class NavigationScene:
    """Rendering state for a navigation view and its current target.

    The coil identifies the source of live poses, independently of target markers.
    """

    def __init__(self, renderer, actor_factory, coil_name=None):
        self.ren = NavigationRenderer(renderer)
        self.target_guide_renderer = vtkRenderer()
        self.coil_name = coil_name
        self.actor_factory = actor_factory
        self.target_marker = None

        self.target_mode = False
        self.target_coord = None
        self.m_target = None
        self._target_coil_enabled = False
        self.stored_camera_settings = None
        self.initial_focus = None
        self.camera_show_object = None
        self.use_volumetric_camera = False
        self.coil_visualizer = None
        self.marker_visualizer = None
        self.robot_force_visualizer = None

        self.guide_coil_actors = None
        self.guide_arrow_actors = None
        self.obj_projection_arrow_actor = None
        self.object_orientation_torus_actor = None
        self.distance_text = None
        self.robot_warnings_text = None
        self.coil_name_text = self.create_coil_name_text(coil_name)
        self.update_coil_label()
        self.ren.AddActor(self.coil_name_text.actor)
        self.ren.set_prop_visibility(self.coil_name_text.actor, False)
        self.pTarget = [0.0, 0.0, 0.0]
        self.actor_tracts = None
        self.tracts_status = False
        self.mark_actor = None

        self.target_camera_last_update = 0.0
        self.target_camera_update_interval = 1.0 / 20.0
        self.target_guide_last_update = 0.0
        self.target_guide_update_interval = 1.0 / 20.0
        self.target_guide_deadband = 2.0
        self.target_guide_last_signature = None

        self._bind_events()

    def _bind_events(self):
        Publisher.subscribe(self.OnRobotForceVisibility, "Set visibility robot force visualizer")
        Publisher.subscribe(self.OnUpdateRobotWarning, "Update robot warning")
        Publisher.subscribe(self.OnUpdateRobotForceData, "Send force sensor data")

    def get_camera_settings(self):
        camera = self.ren.GetActiveCamera()
        return {
            "position": camera.GetPosition(),
            "focal_point": camera.GetFocalPoint(),
            "view_up": camera.GetViewUp(),
            "clipping_range": camera.GetClippingRange(),
            "view_angle": camera.GetViewAngle(),
            "parallel_scale": camera.GetParallelScale(),
        }

    def apply_camera_settings(self, settings):
        camera = self.ren.GetActiveCamera()
        camera.SetPosition(settings["position"])
        camera.SetFocalPoint(settings["focal_point"])
        camera.SetViewUp(settings["view_up"])
        camera.SetClippingRange(settings["clipping_range"])
        camera.SetViewAngle(settings["view_angle"])
        camera.SetParallelScale(settings["parallel_scale"])

    def dispose(self):
        Publisher.unsubscribe_owner(self)
        if self.coil_visualizer is not None:
            self.coil_visualizer.dispose()
        if self.marker_visualizer is not None:
            self.marker_visualizer.dispose()
        if self.robot_force_visualizer is not None:
            self.robot_force_visualizer.dispose()
        self.ren.dispose()
        self.clear_target_guide()

    def initialize_visualizers(
        self,
        vector_field_visualizer,
        interactor,
        track_object=False,
        publish_cortex_markers=True,
    ):
        self.marker_visualizer = MarkerVisualizer(
            renderer=self.ren,
            interactor=interactor,
            actor_factory=self.actor_factory,
            vector_field_visualizer=vector_field_visualizer,
            coil_name=self.coil_name,
            publish_cortex_markers=publish_cortex_markers,
        )
        self.robot_force_visualizer = RobotForceVisualizer()
        self._refresh_robot_force_state()
        self.coil_visualizer = CoilVisualizer(
            renderer=self.ren,
            actor_factory=self.actor_factory,
            vector_field_visualizer=vector_field_visualizer,
        )
        self.track_object(track_object)

    def set_coil(self, coil_name, robot=None):
        """Change the live coil before the view restores its associated target."""
        self.coil_name = coil_name
        self.update_coil_label()
        if self.marker_visualizer is not None:
            self.marker_visualizer.coil_name = coil_name

    def set_coil_name_visibility(self, visible):
        self.ren.set_prop_visibility(self.coil_name_text.actor, visible)

    def restore_markers(self, markers):
        for marker in markers:
            self.marker_visualizer.AddMarker(marker, render=False, focus=False)
            if marker.is_target and marker.coil_name == self.coil_name:
                self.set_target(marker)

    def _refresh_robot_force_state(self):
        if self.robot_force_visualizer is None:
            return
        self.robot_force_visualizer.reset()

    def update_robot_force(self, force):
        if self.robot_force_visualizer is not None:
            self.robot_force_visualizer.update_force(force)

    def set_robot_force_visibility(self, visible):
        if self.robot_force_visualizer is not None:
            self.robot_force_visualizer.set_visibility(visible)

    def update_robot_warning(self, warning):
        if self.robot_warnings_text is not None:
            self.robot_warnings_text.SetValue(warning)

    def set_target(self, marker):
        coord = marker.position + marker.orientation
        # Slice and volume viewers currently use opposite Y directions.
        coord[1] = -coord[1]
        self.target_marker = marker
        self.update_coil_label()
        self.marker_visualizer.SetTarget(marker)
        self.target_coord = coord
        self.m_target = self.actor_factory.CreateVTKObjectMatrix(coord[:3], coord[3:])
        self._target_coil_enabled = True
        self.refresh_target_coil()

    def refresh_target_coil(self):
        """Restore the requested target model using the matrix owned by this scene."""
        if self._target_coil_enabled and self.m_target is not None:
            self.coil_visualizer.AddTargetCoil(self.m_target, self.coil_name)

    def unset_target(self):
        if self.target_marker is not None:
            self.marker_visualizer.UnsetTarget(self.target_marker)
        self._target_coil_enabled = False
        self.target_marker = None
        self.update_coil_label()
        self.target_coord = None
        self.m_target = None

    def update_coil_label(self):
        target_label = (
            self.target_marker.label if self.target_marker is not None else _("No target")
        )
        self.coil_name_text.SetValue(f"{self.coil_name or ''} · {target_label}")

    def create_target_guide(self):
        self.clear_target_guide()

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

    def clear_target_guide(self):
        self.target_guide_renderer.RemoveAllViewProps()
        self.guide_coil_actors = None
        self.guide_arrow_actors = None
        self.target_guide_last_signature = None

    def enable_target_mode(self, hide_projection=False):
        if self.target_coord is None or self.target_mode:
            return
        self.target_mode = True
        self.marker_visualizer.UpdateTargetMode(True)

        # Store the current camera settings so that they can be restored when the target mode is disabled.
        self.stored_camera_settings = self.get_camera_settings()

        # Set the transformation matrix for the target.
        self.m_target = self.actor_factory.CreateVTKObjectMatrix(
            self.target_coord[:3], self.target_coord[3:]
        )

        if hide_projection:
            if self.object_orientation_torus_actor is not None:
                self.object_orientation_torus_actor.SetVisibility(0)
            if self.obj_projection_arrow_actor is not None:
                self.obj_projection_arrow_actor.SetVisibility(0)

        self._target_coil_enabled = True
        self.refresh_target_coil()

        # Remove the previous actor for 'distance' text
        if self.distance_text is not None:
            self.ren.RemoveActor(self.distance_text.actor)

        # Create new actor for 'distance' text
        distance_text = self.create_distance_text()
        self.ren.AddActor(distance_text.actor)

        # Store the object for 'distance' text so it can be modified when distance changes.
        self.distance_text = distance_text

        # Remove the previous actor for 'distance' text
        if self.robot_warnings_text is not None:
            self.ren.RemoveActor(self.robot_warnings_text.actor)

        # Create new actor for 'distance' text
        robot_warnings_text = self.create_robot_warnings_text()
        self.ren.AddActor(robot_warnings_text.actor)

        # Store the object for 'distance' text so it can be modified when distance changes.
        self.robot_warnings_text = robot_warnings_text

        self.create_target_guide()
        self.target_camera_last_update = 0.0
        self.target_guide_last_update = 0.0
        self.target_guide_last_signature = None

    def initialize_target_cameras(self):
        """Frame the target after the view has applied the scene viewports."""
        self.ren.ResetCamera()
        self.set_camera_target()
        self.reset_target_guide_camera()

    def reset_target_guide_camera(self):
        """Fit the guide using its current renderer size and aspect ratio."""
        self.target_guide_renderer.ResetCamera()
        self.target_guide_renderer.GetActiveCamera().Zoom(2)
        self.target_guide_renderer.InteractiveOff()

    def disable_target_mode(self, show_projection=False):
        if self.target_mode and self.stored_camera_settings is not None:
            self.apply_camera_settings(self.stored_camera_settings)
        self.target_mode = False
        self.marker_visualizer.UpdateTargetMode(False)
        self.stored_camera_settings = None
        self._target_coil_enabled = False
        self.coil_visualizer.RemoveTargetCoil()
        self.clear_target_guide()
        for text in (self.distance_text, self.robot_warnings_text):
            if text is not None:
                self.ren.RemoveActor(text.actor)
        self.distance_text = None
        self.robot_warnings_text = None
        self.camera_show_object = None
        if show_projection:
            for actor in (self.object_orientation_torus_actor, self.obj_projection_arrow_actor):
                if actor is not None:
                    actor.SetVisibility(True)

    def update_coil_pose(self, m_img, coord, angle_threshold, distance_threshold):
        # vtk_colors = vtkNamedColors()
        if self.target_coord and self.target_mode:
            now = time.monotonic()
            distance_to_target = distance.euclidean(
                coord[0:3],
                (self.target_coord[0], -self.target_coord[1], self.target_coord[2]),
            )

            formatted_distance = f"Distance: {distance_to_target: >5.1f} mm"

            if self.distance_text is not None:
                self.distance_text.SetValue(formatted_distance)

            if now - self.target_camera_last_update >= self.target_camera_update_interval:
                self.ren.ResetCamera()
                self.set_camera_target()
                zoom_distance = min(distance_to_target, 100)
                # ((-0.0404*dst) + 5.0404) is the linear equation to normalize the zoom between 1 and 5 times with
                # the distance between 1 and 100 mm
                self.ren.GetActiveCamera().Zoom((-0.0404 * zoom_distance) + 5.0404)
                self.target_camera_last_update = now

            is_under_distance_threshold = distance_to_target <= distance_threshold

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
                angle_threshold * const.ARROW_SCALE
                > coordrx_arrow
                > -angle_threshold * const.ARROW_SCALE
            ):
                is_under_x_angle_threshold = True
                self.guide_coil_actors[0].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_x_angle_threshold = False
                self.guide_coil_actors[0].GetProperty().SetColor(1, 1, 1)

            if (
                angle_threshold * const.ARROW_SCALE
                > coordrz_arrow
                > -angle_threshold * const.ARROW_SCALE
            ):
                is_under_z_angle_threshold = True
                self.guide_coil_actors[1].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_z_angle_threshold = False
                self.guide_coil_actors[1].GetProperty().SetColor(1, 1, 1)

            if (
                angle_threshold * const.ARROW_SCALE
                > coordry_arrow
                > -angle_threshold * const.ARROW_SCALE
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

            guide_signature = (
                int(round(coordrx_arrow / self.target_guide_deadband)),
                int(round(coordry_arrow / self.target_guide_deadband)),
                int(round(coordrz_arrow / self.target_guide_deadband)),
            )
            should_update_guide = (
                guide_signature != self.target_guide_last_signature
                and now - self.target_guide_last_update >= self.target_guide_update_interval
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

                self.target_guide_last_signature = guide_signature
                self.target_guide_last_update = now

            return coil_at_target, displacement_to_target_robot

    @staticmethod
    def create_robot_warnings_text():
        robot_warnings_text = vtku.Text()

        robot_warnings_text.actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        robot_warnings_text.SetSize(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION)
        robot_warnings_text.SetPosition((const.X, 1.02 - const.YZ))
        robot_warnings_text.SetVerticalJustificationToBottom()
        robot_warnings_text.SetColour((1, 1, 0))
        robot_warnings_text.BoldOn()

        return robot_warnings_text

    @staticmethod
    def create_distance_text():
        distance_text = vtku.Text()

        distance_text.actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        distance_text.SetSize(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION)
        distance_text.SetPosition((const.X, 1.0 - const.Y))
        distance_text.SetVerticalJustificationToBottom()
        distance_text.BoldOn()

        return distance_text

    @staticmethod
    def create_coil_name_text(coil_name):
        coil_name_text = vtku.Text()

        coil_name_text.actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        coil_name_text.SetSize(const.TEXT_SIZE_SMALL)
        coil_name_text.SetPosition(const.TEXT_POS_RIGHT_DOWN)
        coil_name_text.SetJustificationToRight()
        coil_name_text.SetVerticalJustificationToBottom()
        coil_name_text.SetColour((0.75, 0.75, 0.75))
        coil_name_text.SetValue(coil_name or "")

        return coil_name_text

    def set_camera_target(self):
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

    def track_object(self, enabled):
        if enabled and self.obj_projection_arrow_actor is not None:
            return
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

    def OnRobotForceVisibility(self, visible, coil_associated):
        if coil_associated is not None and coil_associated == self.coil_name:
            self.set_robot_force_visibility(visible)

    def OnUpdateRobotWarning(self, robot_warning, coil_associated):
        if coil_associated is not None and coil_associated == self.coil_name:
            self.update_robot_warning(robot_warning)

    def OnUpdateRobotForceData(self, force_data, coil_associated):
        if coil_associated is not None and coil_associated == self.coil_name:
            self.update_robot_force(force_data)
