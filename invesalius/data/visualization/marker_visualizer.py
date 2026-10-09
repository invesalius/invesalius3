import numpy as np
import vtk

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.slice_ as sl
import invesalius.session as ses
from invesalius.data.markers.marker import MarkerType
from invesalius.gui.widgets.canvas_renderer import CanvasHandlerBase
from invesalius.pubsub import pub as Publisher


class MarkerHighlightX(CanvasHandlerBase):
    """A red 'X' mark drawn at a 3-D world position on the slice canvas.

    The X mark is only visible on the slice where the marker was created,
    ensuring precise spatial awareness of the marker's location.
    """

    _COLOUR = (255, 0, 0, 255)  # bright red for maximum visibility
    _SIZE = 7  # half-width of X mark (14px total span)
    _LINE_WIDTH = 2  # line thickness

    def __init__(self, position=(0, 0, 0)):
        super().__init__(parent=None)
        self.position = position
        self.layer = 99  # draw on top of everything
        self.visible = True
        self.sagittal_slice = None  # slice index for sagittal view
        self.coronal_slice = None  # slice index for coronal view
        self.axial_slice = None  # slice index for axial view

    def draw_to_canvas(self, gc, canvas):
        """Draw the X mark only on the slice where the marker was created."""
        if not self.visible:
            return

        viewer = canvas.viewer

        # Check if we're on the correct slice for this orientation
        if viewer.slice_data is not None:
            current_slice = viewer.slice_data.number

            # Only draw if we're on the exact slice where the marker was created
            if viewer.orientation == "AXIAL":
                if self.axial_slice is None or current_slice != self.axial_slice:
                    return
            elif viewer.orientation == "CORONAL":
                if self.coronal_slice is None or current_slice != self.coronal_slice:
                    return
            elif viewer.orientation == "SAGITAL":
                if self.sagittal_slice is None or current_slice != self.sagittal_slice:
                    return

        # Project 3D marker position to 2D screen coordinates
        px, py = self._3d_to_2d(canvas.evt_renderer, self.position)
        scale = viewer.GetContentScaleFactor()
        size = self._SIZE * scale

        # Draw an X mark using canvas.draw_line() method
        # Line from top-left to bottom-right
        canvas.draw_line(
            (px - size, py - size),
            (px + size, py + size),
            colour=self._COLOUR,
            width=self._LINE_WIDTH,
        )

        # Line from top-right to bottom-left
        canvas.draw_line(
            (px + size, py - size),
            (px - size, py + size),
            colour=self._COLOUR,
            width=self._LINE_WIDTH,
        )


class MarkerVisualizer:
    """
    A class for visualizing markers. Handles, e.g., creating 3d-actors for the markers
    and highlighting a marker in the 3D viewer when it is selected as a target.
    """

    # The scale of the coil target marker when it is the target.
    TARGET_SCALE = 1.0

    # Color for highlighting a marker.
    HIGHLIGHT_COLOR = vtk.vtkNamedColors().GetColor3d("Red")
    EEG_HIGHLIGHT_COLOR = (0.0, 0.5, 1.0)

    # Scaling factor for the marker when it is highlighted.
    #
    # This is done to make the highlighted marker visible if there are other markers with
    # identical positions, which happens, e.g., when duplicating a marker.
    HIGHLIGHTED_MARKER_SCALING_FACTOR = 1.01

    # Color for the marker for target when the coil at the target.
    COIL_AT_TARGET_COLOR = vtk.vtkNamedColors().GetColor3d("Green")

    def __init__(self, renderer, interactor, actor_factory, vector_field_visualizer):
        self.renderer = renderer
        self.interactor = interactor

        # The actor factory is used to create actor for the projection line of the coil target to the brain surface.
        self.actor_factory = actor_factory

        # The vector field visualizer is used to represent a vector field relative to target.
        self.vector_field_visualizer = vector_field_visualizer

        # The currently highlighted marker object.
        self.highlighted_marker = None

        # The actor representing the projection line of the coil target to the brain surface.
        self.projection_line_actor = None

        # The currently set target marker object.
        self.target_marker = None

        # The status of the coil at the target.
        self.is_coil_at_target = False

        self.is_navigating = False
        self.is_target_mode = False
        self.eeg_labels_visible = True

        # The assembly for the current vector field, shown relative to the highlighted marker.
        self.vector_field_assembly = self.vector_field_visualizer.CreateVectorFieldAssembly()

        # Add the vector field assembly to the renderer, but make it invisible until a marker is highlighted.
        self.renderer.AddActor(self.vector_field_assembly)
        self.vector_field_assembly.SetVisibility(0)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.AddMarker, "Add marker")
        Publisher.subscribe(self.UpdateMarker, "Update marker")
        Publisher.subscribe(self.UpdateMarkerLabel, "Update marker label")
        Publisher.subscribe(self.HideMarkers, "Hide markers")
        Publisher.subscribe(self.ShowMarkers, "Show markers")
        Publisher.subscribe(self.SetMarkerVisibility, "Set marker visibility")
        Publisher.subscribe(self.SetMarkersVisibility, "Set markers visibility")
        Publisher.subscribe(
            self.SetEEGLabelsVisibility,
            "Set EEG electrode labels visibility",
        )
        Publisher.subscribe(self.DeleteMarkers, "Delete markers")
        Publisher.subscribe(self.DeleteMarker, "Delete marker")
        Publisher.subscribe(self.SetCameraToFocusOnMarker, "Set camera to focus on marker")
        Publisher.subscribe(self.HighlightMarker, "Highlight marker")
        Publisher.subscribe(self.UnhighlightMarker, "Unhighlight marker")
        Publisher.subscribe(self.SetNewColor, "Set new color")
        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")
        Publisher.subscribe(self.SetTargetTransparency, "Set target transparency")
        Publisher.subscribe(self.SetCoilAtTarget, "Coil at target")
        Publisher.subscribe(self.UpdateBrainTargets, "Update brain targets")
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")
        Publisher.subscribe(self.UpdateTargetMode, "Set target mode")
        Publisher.subscribe(
            self.UpdateVectorFieldAssemblyVisibility, "Set vector field assembly visibility"
        )

    def dispose(self):
        Publisher.unsubscribe_owner(self)

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = nav_status

    def UpdateTargetMode(self, enabled=False):
        self.is_target_mode = enabled

    def UpdateVectorFieldAssemblyVisibility(self, enabled=False):
        self.vector_field_assembly.SetVisibility(enabled)
        # If not navigating, render the scene.
        if not self.is_navigating:
            self.interactor.Render()

    def UpdateBrainTargets(self, brain_targets):
        """
        Update the vector field assembly to reflect the current vector field.
        """
        # Create a new vector field assembly.
        new_vector_field_assembly = self.vector_field_visualizer.CreateVectorFieldAssembly(
            brain_targets
        )
        # Replace the old vector field assembly with the new one.
        self.actor_factory.ReplaceActor(
            self.renderer, self.vector_field_assembly, new_vector_field_assembly
        )

        # Store the new vector field assembly.
        self.vector_field_assembly = new_vector_field_assembly

        # If not navigating, render the scene.
        if not self.is_navigating:
            self.interactor.Render()

    def AddMarker(self, marker, render, focus):
        """
        Visualize marker and add the visualization to the marker object.

        If 'render' is True, the interactor will be rendered after adding the marker.
        """
        position = marker.position
        orientation = marker.orientation
        marker_id = marker.marker_id
        marker_type = marker.marker_type
        colour = marker.colour
        size = marker.size
        cortex_marker = marker.cortex_position_orientation
        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        # Get marker shape preferences from session
        session = ses.Session()

        # For 'fiducial' type markers, use user preference (ball or cross).
        if marker_type == MarkerType.FIDUCIAL:
            fiducial_shape = session.GetConfig("fiducial_marker_shape", const.MARKER_SHAPE_CROSS)
            if fiducial_shape == const.MARKER_SHAPE_CROSS:
                actor = self.actor_factory.CreateCross(position_flipped, colour, size)
            else:
                actor = self.actor_factory.CreateBall(position_flipped, colour, size)

        # For 'landmark' type markers, use user preference (ball or cross).
        elif marker_type == MarkerType.LANDMARK:
            landmark_shape = session.GetConfig("landmark_marker_shape", const.MARKER_SHAPE_BALL)
            if landmark_shape == const.MARKER_SHAPE_CROSS:
                actor = self.actor_factory.CreateCross(position_flipped, colour, size)
            else:
                actor = self.actor_factory.CreateBall(position_flipped, colour, size)

        # For 'brain target' type markers, create an arrow.
        elif marker_type == MarkerType.BRAIN_TARGET:
            actor = self.actor_factory.CreateArrowUsingDirection(
                position_flipped, orientation, colour
            )

        # For 'coil target' type markers, create an arrow.
        elif marker_type == MarkerType.COIL_TARGET:
            actor = self.actor_factory.CreateArrowUsingDirection(
                position_flipped, orientation, colour
            )

        # For 'coil pose' type markers, create an arrow.
        elif marker_type == MarkerType.COIL_POSE:
            actor = self.actor_factory.CreateArrowUsingDirection(
                position_flipped, orientation, colour
            )

        # For 'EEG electrode' type markers, create a torus and a camera-facing label.
        elif marker_type == MarkerType.EEG_ELECTRODE:
            actor, label_actor = self._CreateEEGElectrodeActors(marker, position_flipped)

        else:
            assert False, "Invalid marker type."

        if cortex_marker[0] is not None:
            Publisher.sendMessage(
                "Add cortex marker actor", position_orientation=cortex_marker, marker_id=marker_id
            )

        marker.visualization = {
            "actor": actor,
            "label_actor": label_actor if marker_type == MarkerType.EEG_ELECTRODE else None,
            "highlighted": False,
            "hidden": not marker.visible,
        }
        actor.SetVisibility(marker.visible)
        self.renderer.AddActor(actor)
        if marker_type == MarkerType.EEG_ELECTRODE:
            label_actor.SetVisibility(marker.visible and self.eeg_labels_visible)
            self.renderer.AddActor(label_actor)

        if render:
            self.interactor.Render()

    def UpdateMarker(self, marker, new_position, new_orientation):
        """
        Update the position and orientation of a marker.
        """
        old_visualization = marker.visualization
        highlighted = old_visualization["highlighted"]
        colour = marker.colour

        new_position_flipped = list(new_position)
        new_position_flipped[1] = -new_position_flipped[1]

        if marker.marker_type == MarkerType.EEG_ELECTRODE:
            new_actor, new_label_actor = self._CreateEEGElectrodeActors(
                marker, new_position_flipped, orientation=new_orientation
            )
        else:
            # XXX: Workaround because modifying the original actor does not seem to work using
            #   method UpdatePositionAndOrientation in ActorFactory; instead, create a new actor
            #   and remove the old one. This only works for coil target markers, as the new actor
            #   created is of a fixed type (arrow).
            new_actor = self.actor_factory.CreateArrowUsingDirection(
                new_position_flipped, new_orientation, colour
            )
            new_label_actor = None

        if highlighted:
            # Unhighlight the marker, but do not render the interactor yet to avoid flickering.
            self.UnhighlightMarker(render=False)

        marker.visualization = {
            "actor": new_actor,
            "label_actor": new_label_actor,
            "highlighted": False,
            "hidden": old_visualization["hidden"],
        }
        if marker.marker_type == MarkerType.EEG_ELECTRODE:
            new_actor.SetVisibility(not old_visualization["hidden"])
            new_label_actor.SetVisibility(
                not old_visualization["hidden"] and self.eeg_labels_visible
            )

        for old_actor in self._GetVisualizationActors(marker, visualization=old_visualization):
            self.renderer.RemoveActor(old_actor)
        self.renderer.AddActor(new_actor)
        if new_label_actor is not None:
            self.renderer.AddActor(new_label_actor)

        if highlighted:
            self.HighlightMarker(marker)

        if not self.is_navigating:
            self.interactor.Render()

    def HideMarkers(self, markers):
        for marker in markers:
            visualization = marker.visualization
            is_target = marker.is_target

            highlighted = visualization["highlighted"]

            # Mark the marker as 'hidden' regardless of if it's the target or highlighted.
            #
            # This is to ensure that the marker will be properly hidden if it stops being the target or is unhighlighted.
            visualization["hidden"] = True

            # If marker is the target or it is already highlighted, do not actually hide the actor.
            if (is_target or highlighted) and marker.marker_type != MarkerType.EEG_ELECTRODE:
                continue

            # Hide the actor.
            for actor in self._GetVisualizationActors(marker):
                actor.SetVisibility(0)

        if not self.is_navigating:
            self.interactor.Render()

    def ShowMarkers(self, markers):
        for marker in markers:
            visualization = marker.visualization

            actor = visualization.get("actor")
            if actor is not None:
                actor.SetVisibility(1)
            label_actor = visualization.get("label_actor")
            if label_actor is not None:
                label_actor.SetVisibility(self.eeg_labels_visible)

            # Mark the marker as not hidden.
            visualization["hidden"] = False

        if not self.is_navigating:
            self.interactor.Render()

    def SetEEGLabelsVisibility(self, markers, visible):
        self.eeg_labels_visible = bool(visible)
        for marker in markers:
            label_actor = marker.visualization.get("label_actor")
            if label_actor is not None:
                label_actor.SetVisibility(
                    self.eeg_labels_visible and not marker.visualization["hidden"]
                )

        if not self.is_navigating:
            self.interactor.Render()

    def SetMarkerVisibility(self, marker, visible):
        self.SetMarkersVisibility([marker], visible)

    def SetMarkersVisibility(self, markers, visible):
        markers_with_actors = [
            marker for marker in markers if marker.visualization.get("actor") is not None
        ]
        if visible:
            self.ShowMarkers(markers_with_actors)
        else:
            self.HideMarkers(markers_with_actors)

    def DeleteMarkers(self, markers):
        for marker in markers:
            for actor in self._GetVisualizationActors(marker):
                self.renderer.RemoveActor(actor)

        if not self.is_navigating:
            self.interactor.Render()

    def DeleteMarker(self, marker):
        for actor in self._GetVisualizationActors(marker):
            self.renderer.RemoveActor(actor)
        if not self.is_navigating:
            self.interactor.Render()

    def SetNewColor(self, marker, new_color):
        actor = marker.visualization.get("actor")
        colour = [round(s / 255.0, 3) for s in new_color]
        actor.GetProperty().SetColor(colour)
        label_actor = marker.visualization.get("label_actor")
        if label_actor is not None:
            label_actor.GetTextProperty().SetColor(colour)

        if not self.is_navigating:
            self.interactor.Render()

    def UpdateMarkerLabel(self, marker):
        if marker.marker_type != MarkerType.EEG_ELECTRODE:
            return

        label_actor = marker.visualization.get("label_actor")
        if label_actor is not None:
            label_actor.SetInput(self._GetEEGElectrodeLabel(marker))
            if not self.is_navigating:
                self.interactor.Render()

    def _CreateEEGElectrodeActors(self, marker, position, orientation=None):
        orientation = orientation if orientation is not None else marker.orientation
        orientation = [value if value is not None else 0.0 for value in orientation]
        torus_actor = self.actor_factory.CreateTorus(
            position,
            orientation,
            marker.colour,
            ring_radius=3.0,
            cross_section_radius=0.8,
        )
        torus_actor.GetProperty().SetOpacity(0.8)

        label_actor = vtk.vtkBillboardTextActor3D()
        label_actor.SetInput(self._GetEEGElectrodeLabel(marker))
        label_actor.SetPosition(position[0], position[1], position[2] + 6.0)
        label_actor.PickableOff()

        text_property = label_actor.GetTextProperty()
        text_property.SetFontSize(28)
        text_property.SetColor(marker.colour)
        text_property.SetBold(True)
        text_property.SetShadow(True)
        text_property.SetShadowOffset(2, -2)
        text_property.SetFrame(True)
        text_property.SetFrameColor(0.2, 0.2, 0.2)
        text_property.SetFrameWidth(2)
        text_property.SetBackgroundColor(0.3, 0.3, 0.3)
        text_property.SetBackgroundOpacity(0.85)

        return torus_actor, label_actor

    @staticmethod
    def _GetEEGElectrodeLabel(marker):
        return marker.eeg_matched_name or marker.label

    @staticmethod
    def _GetVisualizationActors(marker, visualization=None):
        visualization = visualization if visualization is not None else marker.visualization
        return [
            actor
            for actor in (visualization.get("actor"), visualization.get("label_actor"))
            if actor is not None
        ]

    def SetTarget(self, marker):
        """
        When setting a marker as the target, change the arrow to an aim highlight
        that it is the target.
        """
        # Store the target marker so that it can be modified, e.g., when the coil is at target.
        self.target_marker = marker

        position = marker.position
        orientation = marker.orientation
        colour = marker.colour

        actor = marker.visualization.get("actor")
        highlighted = marker.visualization["highlighted"]

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        # Replace the arrow with an aim.
        new_actor = self.actor_factory.CreateAim(
            position_flipped, orientation, colour, scale=self.TARGET_SCALE
        )

        if highlighted:
            self.UnhighlightMarker(render=False)

        marker.visualization["actor"] = new_actor

        if highlighted:
            self.HighlightMarker(marker, render=False)

        self.renderer.RemoveActor(actor)
        self.renderer.AddActor(new_actor)

        if not self.is_navigating:
            self.interactor.Render()

    def UnsetTarget(self, marker):
        """
        When unsetting a marker as the target, change the aim back to an arrow.
        """
        self.target_marker = None

        position = marker.position
        orientation = marker.orientation
        colour = marker.colour

        actor = marker.visualization["actor"]
        highlighted = marker.visualization["highlighted"]

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        # Replace the aim with an arrow.
        new_actor = self.actor_factory.CreateArrowUsingDirection(
            position_flipped, orientation, colour
        )

        if highlighted:
            self.UnhighlightMarker(render=False)

        marker.visualization["actor"] = new_actor

        if highlighted:
            self.HighlightMarker(marker, render=False)

        self.renderer.RemoveActor(actor)
        self.renderer.AddActor(new_actor)

        if not self.is_navigating:
            self.interactor.Render()

    def SetCoilAtTarget(self, state):
        """
        Set the coil at target, which is a special case of setting a marker as the target.
        """
        self.is_coil_at_target = state

        marker = self.target_marker

        if marker is None:
            return

        actor = marker.visualization["actor"]
        highlighted = marker.visualization["highlighted"]

        # vtk_colors = vtk.vtkNamedColors()
        if state:
            # Change the color of the marker.
            actor.GetProperty().SetColor(self.COIL_AT_TARGET_COLOR)
        else:
            # Change the color of the marker back to its original color, unless it's highlighted,
            # in which case it should be red.
            colour = marker.colour if not highlighted else self.HIGHLIGHT_COLOR

            actor.GetProperty().SetColor(colour)

        if not self.is_navigating:
            self.interactor.Render()

    def SetTargetTransparency(self, marker, transparent):
        actor = marker.visualization["actor"]
        if transparent:
            actor.GetProperty().SetOpacity(1)
            # actor.GetProperty().SetOpacity(0.4)
        else:
            actor.GetProperty().SetOpacity(1)

    def _CreateProjectionLine(self, startpoint_position, startpoint_orientation):
        """
        Create a projection line from the coil to the brain surface.
        """
        # Move the endpoint 30 mm in the direction of the orientation. This should be enough to reach the brain surface.
        dx = 0
        dy = 0
        dz = -30
        delta_translation = [dx, dy, dz]
        delta_orientation = [0, 0, 0]

        # Create transformation matrices for the marker and the movement delta.
        m_delta = dco.coordinates_to_transformation_matrix(
            position=delta_translation,
            orientation=delta_orientation,
            axes="sxyz",
        )
        m_marker = dco.coordinates_to_transformation_matrix(
            position=startpoint_position,
            orientation=startpoint_orientation,
            axes="sxyz",
        )
        m_endpoint = m_marker @ m_delta

        endpoint, _ = dco.transformation_matrix_to_coordinates(m_endpoint, "sxyz")

        actor = self.actor_factory.CreateTube(
            startpoint_position, endpoint, colour=self.HIGHLIGHT_COLOR, radius=0.5
        )
        actor.GetProperty().SetOpacity(0.1)

        # If there is already a projection line actor, remove it.
        if self.projection_line_actor is not None:
            self.renderer.RemoveActor(self.projection_line_actor)

        self.renderer.AddActor(actor)

        # Store the projection line actor so that it can be removed later.
        self.projection_line_actor = actor

    def SetCameraToFocusOnMarker(self, marker):
        """
        Set the camera focal point to the marker, making the marker the center of the view.
        """
        if marker.marker_type == MarkerType.EEG_ELECTRODE:
            if self.is_navigating:
                return
            self._FocusCameraOnEEGElectrode(marker)
            return

        # If not navigating, render the scene.
        if not self.is_target_mode or not self.is_navigating:
            position = marker.position

            position_flipped = list(position)
            position_flipped[1] = -position_flipped[1]

            camera = self.renderer.GetActiveCamera()
            camera.SetFocalPoint(position_flipped)

            # If not navigating, render the scene.
            if not self.is_navigating:
                self.renderer.ResetCameraClippingRange()
                self.renderer.Render()
                self.interactor.GetRenderWindow().Render()

    def _FocusCameraOnEEGElectrode(self, marker):
        target = np.asarray(marker.position, dtype=float)
        target[1] *= -1

        orientation = [value if value is not None else 0.0 for value in marker.orientation]
        rotation = dco.coordinates_to_transformation_matrix(
            position=(0.0, 0.0, 0.0),
            orientation=orientation,
            axes="sxyz",
        )
        normal = rotation[:3, 2]
        normal_length = np.linalg.norm(normal)
        normal = normal / normal_length if normal_length > 1e-6 else np.array([0.0, 0.0, 1.0])

        camera = self.renderer.GetActiveCamera()
        camera_position = np.asarray(camera.GetPosition(), dtype=float)
        camera_focal_point = np.asarray(camera.GetFocalPoint(), dtype=float)
        camera_distance = np.linalg.norm(camera_position - camera_focal_point)
        if camera_distance < 50.0:
            camera_distance = 250.0

        new_position = target + normal * camera_distance
        camera.SetFocalPoint(*target)
        camera.SetPosition(*new_position)
        camera.SetViewUp(0, 1, 0) if abs(normal[2]) > 0.99 else camera.SetViewUp(0, 0, 1)

        self.renderer.ResetCameraClippingRange()
        self.interactor.Render()

    def HighlightMarker(self, marker, render=True):
        # Unpack relevant fields from the marker.
        actor = marker.visualization["actor"]

        marker_type = marker.marker_type
        position = marker.position
        orientation = marker.orientation

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        # If the marker is a coil target, show the vector field assembly and update its position and orientation,
        # otherwise, hide the vector field assembly.
        # if marker_type == MarkerType.COIL_TARGET:
        #     self.vector_field_assembly.SetVisibility(1)
        #
        #     self.vector_field_assembly.SetPosition(position_flipped)
        #     self.vector_field_assembly.SetOrientation(orientation)
        # else:
        #     self.vector_field_assembly.SetVisibility(0)

        # Return early if the marker is a target and the coil is at the target.
        #
        # In that case, the marker should not be highlighted, as being at the target overrides the highlighting.
        if marker.is_target and self.is_coil_at_target:
            return

        # Change the color of the marker.
        highlight_colour = (
            self.EEG_HIGHLIGHT_COLOR
            if marker_type == MarkerType.EEG_ELECTRODE
            else self.HIGHLIGHT_COLOR
        )
        actor.GetProperty().SetColor(highlight_colour)

        # Increase the scale of the marker.
        self.actor_factory.ScaleActor(actor, self.HIGHLIGHTED_MARKER_SCALING_FACTOR)

        # Set the marker visible when highlighted even if it's hidden.
        # if marker.visualization["hidden"]:
        #    actor.SetVisibility(1)

        # If the marker is a coil target, create a perpendicular line from the coil to the brain surface.
        if marker_type == MarkerType.COIL_TARGET:
            self._CreateProjectionLine(
                startpoint_position=position_flipped,
                startpoint_orientation=orientation,
            )

        # Store the highlighted marker.
        self.highlighted_marker = marker

        # Store the 'highlighted' status in the marker.
        marker.visualization["highlighted"] = True

        if render:
            self.interactor.Render()

    def UnhighlightMarker(self, render=True):
        marker = self.highlighted_marker

        # Return early in case there is no highlighted marker. This shouldn't happen, though.
        if marker is None:
            return

        # Return early if the marker is a target and the coil is at the target.
        #
        # In that case, the marker should not be unhighlighted, as being at the target overrides the
        # highlighting.
        if marker.is_target and self.is_coil_at_target:
            return

        actor = marker.visualization["actor"]
        colour = marker.colour

        # Change the color of the marker back to its original color.
        actor.GetProperty().SetColor(colour)

        # Decrease back the scale of the marker.
        self.actor_factory.ScaleActor(actor, 1 / self.HIGHLIGHTED_MARKER_SCALING_FACTOR)

        # Set the marker invisible if it should be hidden.
        if marker.visualization["hidden"]:
            actor.SetVisibility(0)

        # However, if it is the target, it should remain visible.
        if marker.is_target:
            actor.SetVisibility(1)

        label_actor = marker.visualization.get("label_actor")
        if label_actor is not None:
            label_actor.SetVisibility(
                self.eeg_labels_visible and not marker.visualization["hidden"]
            )

        # Remove the projection actor if it exists.
        if self.projection_line_actor is not None:
            self.renderer.RemoveActor(self.projection_line_actor)
            self.projection_line_actor = None

        # Reset the highlighted marker.
        self.highlighted_marker = None
        marker.visualization["highlighted"] = False

        if render:
            self.interactor.Render()
