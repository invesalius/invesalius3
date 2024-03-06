import vtk

import invesalius.data.coordinates as dco
from invesalius.data.markers.marker import Marker, MarkerType

from invesalius.pubsub import pub as Publisher


class MarkerViewer:
    """
    A class for managing the highlighting of markers in the 3D viewer. Later, this class could be extended to handle other
    marker-related functionality, such as adding and removing markers, etc.
    """
    def __init__(self, renderer, interactor, actor_factory):
        self.renderer = renderer
        self.interactor = interactor
        
        # The actor factory is used to create actor for the projection line of the coil target to the brain surface.
        self.actor_factory = actor_factory

        # The currently highlighted marker object.
        self.highlighted_marker = None

        # The actor representing the projection line of the coil target to the brain surface.
        self.projection_line_actor = None
 
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.AddMarker, 'Add marker')
        Publisher.subscribe(self.UpdateMarker, 'Update marker')
        Publisher.subscribe(self.HideMarkers, 'Hide markers')
        Publisher.subscribe(self.ShowMarkers, 'Show markers')
        Publisher.subscribe(self.DeleteMarkers, 'Delete markers')
        Publisher.subscribe(self.DeleteMarker, 'Delete marker')
        Publisher.subscribe(self.HighlightMarker, 'Highlight marker')
        Publisher.subscribe(self.UnhighlightMarker, 'Unhighlight marker')
        Publisher.subscribe(self.SetNewColor, 'Set new color')
        Publisher.subscribe(self.SetTargetTransparency, 'Set target transparency')

    def AddMarker(self, marker):
        """
        Visualize marker and add the visualization to the marker object.
        """
        position = marker.position
        orientation = marker.orientation

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        position = marker.position
        orientation = marker.orientation
        marker_id = marker.marker_id
        marker_type = marker.marker_type
        colour = marker.colour
        size = marker.size
        cortex_marker = marker.cortex_position_orientation

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        # For 'fiducial' type markers, create a ball. TODO: This could be changed to something more distinctive.
        if marker_type == MarkerType.FIDUCIAL:
            actor = self.actor_factory.CreateBall(position_flipped, colour, size)

        # For 'landmark' type markers, create a ball.
        elif marker_type == MarkerType.LANDMARK:
            actor = self.actor_factory.CreateBall(position_flipped, colour, size)

        # For 'brain target' type markers, create an arrow.
        elif marker_type == MarkerType.BRAIN_TARGET:
            actor = self.actor_factory.CreateArrowUsingDirection(position_flipped, orientation, colour, const.ARROW_MARKER_SIZE)

        # For 'coil target' type markers, create a crosshair.
        elif marker_type == MarkerType.COIL_TARGET:
            actor = self.actor_factory.CreateAim(position_flipped, orientation, colour)

        # For 'coil pose' type markers, create a smaller crosshair; they are generated when pulses are
        # given; hence, they easily clutter the volume viewer if they are too big.
        elif marker_type == MarkerType.COIL_POSE:
            actor = self.actor_factory.CreateAim(position_flipped, orientation, colour, scale=0.3)

        else:
            assert False, "Invalid marker type."

        if cortex_marker[0] is not None:
            Publisher.sendMessage('Add cortex marker actor', position_orientation=cortex_marker, marker_id=marker_id)

        marker.visualization = {
            'actor': actor,
            'position': position_flipped,
            'orientation': orientation,
            'highlighted': False,
            'hidden': False,
        }
        self.renderer.AddActor(actor)

        self.interactor.Render()

    def UpdateMarker(self, marker, new_position, new_orientation):
        """
        Update the position and orientation of a marker.
        """
        actor = marker.visualization['actor']
        highlighted = marker.visualization['highlighted']
        colour = marker.colour

        new_position_flipped = list(new_position)
        new_position_flipped[1] = -new_position_flipped[1]

        # XXX: Workaround because modifying the original actor does not seem to work using
        #   method UpdatePositionAndOrientation in ActorFactory; instead, create a new actor
        #   and remove the old one. This only works for coil target markers, as the new actor
        #   created is of a fixed type (aim).
        new_actor = self.actor_factory.CreateAim(new_position_flipped, new_orientation, colour)

        if highlighted:
            self.UnhighlightMarker()

        marker.visualization = {
            'actor': new_actor,
            'position': new_position_flipped,
            'orientation': new_orientation,
            'highlighted': False,
            'hidden': False,
        }

        self.renderer.RemoveActor(actor)
        self.renderer.AddActor(new_actor)

        if highlighted:
            self.HighlightMarker(marker)

        self.interactor.Render()

    def HideMarkers(self, markers):
        for marker in markers:
            visualization = marker.visualization
            is_target = marker.is_target

            highlighted = visualization['highlighted']
            actor = visualization['actor']

            # Mark the marker as 'hidden' regardless of if it's the target or highlighted.
            #
            # This is to ensure that the marker will be properly hidden if it stops being the target or is unhighlighted.
            visualization['hidden'] = True

            # If marker is the target or it is already highlighted, do not actually hide the actor.
            if is_target or highlighted:
                continue

            # Hide the actor.
            actor.SetVisibility(0)

        self.interactor.Render()

    def ShowMarkers(self, markers):
        for marker in markers:
            visualization = marker.visualization

            visualization['actor'].SetVisibility(1)

            # Mark the marker as not hidden.
            visualization['hidden'] = False

        self.interactor.Render()

    def DeleteMarkers(self, markers):
        for marker in markers:
            actor = marker.visualization["actor"]
            self.renderer.RemoveActor(actor)

        self.interactor.Render()

    def DeleteMarker(self, marker):
        actor = marker.visualization["actor"]
        self.renderer.RemoveActor(actor)
        self.interactor.Render()

    def SetNewColor(self, marker, new_color):
        actor = marker.visualization["actor"]
        actor.GetProperty().SetColor([round(s / 255.0, 3) for s in new_color])

        self.interactor.Render()

    def SetTargetTransparency(self, marker, transparent):
        actor = marker.visualization["actor"]
        if transparent:
            actor.GetProperty().SetOpacity(1)
            # actor.GetProperty().SetOpacity(0.4)
        else:
            actor.GetProperty().SetOpacity(1)

    def HighlightMarker(self, marker):
        # Unpack relevant fields from the marker.
        actor = marker.visualization['actor']

        marker_type = marker.marker_type
        position = marker.visualization['position']
        orientation = marker.visualization['orientation']

        # Use color red for highlighting.
        vtk_colors = vtk.vtkNamedColors()
        colour = vtk_colors.GetColor3d('Red')

        # Change the color of the marker.
        actor.GetProperty().SetColor(colour)

        # Set the marker visible when highlighted even if it's hidden.
        if marker.visualization['hidden']:
            actor.SetVisibility(1)

        # If the marker is a coil target, create a perpendicular line from the coil to the brain surface.
        if marker_type == MarkerType.COIL_TARGET:
            startpoint = position[:]

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
                axes='sxyz',
            )
            m_marker = dco.coordinates_to_transformation_matrix(
                position=position,
                orientation=orientation,
                axes='sxyz',
            )
            m_endpoint = m_marker @ m_delta

            endpoint, _ = dco.transformation_matrix_to_coordinates(m_endpoint, 'sxyz')

            actor = self.actor_factory.CreateTube(startpoint, endpoint, colour=colour)

            self.renderer.AddActor(actor)

            # Store the projection line actor so that it can be removed later.
            self.projection_line_actor = actor

        # Store the highlighted marker.
        self.highlighted_marker = marker

        # Store the 'highlighted' status in the marker.
        marker.visualization['highlighted'] = True

        self.interactor.Render()

    def UnhighlightMarker(self):
        # Return early in case there is no highlighted marker. This shouldn't happen, though.
        if self.highlighted_marker is None:
            return

        marker = self.highlighted_marker

        actor = marker.visualization['actor']
        colour = marker.colour

        # Change the color of the marker back to its original color.
        actor.GetProperty().SetColor(colour)

        # Set the marker invisible if it should be hidden.
        if marker.visualization['hidden']:
            actor.SetVisibility(0)

        # However, if it is the target, it should remain visible.
        if marker.is_target:
            actor.SetVisibility(1)

        # Remove the projection actor if it exists.
        if self.projection_line_actor:
            self.renderer.RemoveActor(self.projection_line_actor)
            self.projection_line_actor = None

        # Reset the highlighted marker.
        self.highlighted_marker = None
        marker.visualization['highlighted'] = False

        self.interactor.Render()
