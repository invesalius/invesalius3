import vtk

import invesalius.data.coordinates as dco
from invesalius.data.markers.marker import Marker, MarkerType


class MarkerViewer:
    """
    A class for managing the highlighting of markers in the 3D viewer. Later, this class could be extended to handle other
    marker-related functionality, such as adding and removing markers, etc.
    """
    def __init__(self, renderer, actor_factory):
        self.renderer = renderer
        
        # The actor factory is used to create actor for the projection line of the coil target to the brain surface.
        self.actor_factory = actor_factory

        # The currently highlighted marker object.
        self.highlighted_marker = None

        # The actor representing the projection line of the coil target to the brain surface.
        self.projection_line_actor = None

    def HighlightMarker(self, marker):
        # Unpack relevant fields from the marker.
        actor = marker["actor"]
        marker_type = marker["marker_type"]
        position = marker["position"]
        orientation = marker["orientation"]

        # Use color red for highlighting.
        vtk_colors = vtk.vtkNamedColors()
        colour = vtk_colors.GetColor3d('Red')

        # Change the color of the marker.
        actor.GetProperty().SetColor(colour)

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
        marker["highlighted"] = True

    def UnhighlightMarker(self):
        # Return early in case there is no highlighted marker. This shouldn't happen, though.
        if self.highlighted_marker is None:
            return

        marker = self.highlighted_marker

        actor = marker["actor"]
        colour = marker["colour"]

        # Change the color of the marker back to its original color.
        actor.GetProperty().SetColor(colour)

        # Remove the projection actor if it exists.
        if self.projection_line_actor:
            self.renderer.RemoveActor(self.projection_line_actor)
            self.projection_line_actor = None

        # Reset the highlighted marker.
        self.highlighted_marker = None
        marker["highlighted"] = False
