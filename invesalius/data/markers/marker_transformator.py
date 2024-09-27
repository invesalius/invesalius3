import numpy as np

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr
from invesalius.data.markers.marker import MarkerType
from invesalius.data.markers.surface_geometry import SurfaceGeometry
from invesalius.pubsub import pub as Publisher


class MarkerTransformator:
    def __init__(self):
        self.surface_geometry = SurfaceGeometry()

        # Keep track of the marker selected in the marker menu; this is the marker
        # that will be moved when the user presses a key.
        self.selected_marker = None

        # Keep track of the navigation status to prevent moving the marker when the
        # navigation is on.
        self.is_navigating = False

        # Keep track of the current target and whether the target mode is on.
        self.target = None
        self.is_target_mode = False

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")
        Publisher.subscribe(self.MoveMarkerByKeyboard, "Move marker by keyboard")
        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")
        Publisher.subscribe(self.SetTargetMode, "Set target mode")

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = nav_status

    def UpdateSelectedMarker(self, marker):
        self.selected_marker = marker

    def SetTarget(self, marker):
        self.target = marker

    def UnsetTarget(self, marker):
        self.target = None

    def SetTargetMode(self, enabled=False):
        self.is_target_mode = enabled

    def MoveMarker(self, marker, displacement):
        """
        Move marker in its local coordinate system by the given displacement.
        """
        # XXX: The markers have y-coordinate inverted, compared to the 3d view. Hence, invert the y-coordinate here.
        position = list(marker.position[:])
        position[1] = -position[1]

        orientation = marker.orientation[:]

        # Create transformation matrices for the marker and the displacement.
        m_displacement = dco.coordinates_to_transformation_matrix(
            position=displacement[:3],
            orientation=displacement[3:],
            axes="sxyz",
        )
        m_marker = dco.coordinates_to_transformation_matrix(
            position=position,
            orientation=orientation,
            axes="sxyz",
        )
        m_marker_new = m_marker @ m_displacement

        new_position, new_orientation = dco.transformation_matrix_to_coordinates(
            m_marker_new, "sxyz"
        )

        # XXX: Invert back to the get to 'marker space'.
        new_position = list(new_position)
        new_position[1] = -new_position[1]

        marker.position = new_position
        marker.orientation = new_orientation

    def MoveMarkerOnScalp(self, marker, displacement_along_scalp_tangent):
        """
        Move marker along scalp tangent by the given displacement and project it to the scalp,
        to make it stay on the scalp surface.

        Maintain the distance to the scalp after the movement.
        """
        # XXX: This should be orthogonal distance to the scalp - currently its the distance to the closest point on the scalp.
        distance_to_scalp = self.DistanceToScalp(marker)

        # Move the marker towards the scalp.
        displacement = [0, 0, -distance_to_scalp, 0, 0, 0]
        self.MoveMarker(
            marker=marker,
            displacement=displacement,
        )

        # Move the marker along the scalp tangent by the desired displacement.
        desired_distance_along_scalp_tangent = np.linalg.norm(displacement_along_scalp_tangent)

        distance = None
        scale = 1
        while distance is None or distance < desired_distance_along_scalp_tangent:
            old_position = marker.position

            scaled_displacement = scale * np.array(displacement_along_scalp_tangent)
            self.MoveMarker(
                marker=marker,
                displacement=scaled_displacement,
            )
            self.ProjectToScalp(
                marker=marker,
                # We are projecting a marker that is already over the scalp; hence, do not project to the opposite side
                # to keep the marker on top of the scalp.
                opposite_side=False,
            )

            distance = np.linalg.norm(np.array(marker.position) - np.array(old_position))
            scale += 1

            # XXX: Avoid infinite loop.
            if scale >= 100:
                break

        self.ProjectToScalp(
            marker=marker,
            # We are projecting a marker that is already over the scalp; hence, do not project to the opposite side
            # to keep the marker on top of the scalp.
            opposite_side=False,
        )
        # Move the marker back from the scalp by the same distance it was before the movement.
        #
        # XXX: This should be orthogonal distance to the scalp - currently its the distance to the closest point on the scalp.
        #   Hence, the marker does not end up the same orthogonal distance to the scalp as it was before the movement, but instead,
        #   usually ends up closer to the scalp. (For instance, repeated movements back and forth will eventually make the marker
        #   end up touching the scalp). It's better that it tries to maintain the distance to the scalp that the marker had than
        #   not doing that, so this better than nothing - but it should be fixed.
        displacement = [0, 0, distance_to_scalp, 0, 0, 0]
        self.MoveMarker(
            marker=marker,
            displacement=displacement,
        )

    def DistanceToScalp(self, marker):
        """
        Return the distance from the marker to the closest point on the scalp.

        TODO: This would be more useful if it returned the orthogonal distance to the scalp, instead of the distance to the closest point.
        """
        # XXX: The markers have y-coordinate inverted, compared to the 3d view. Hence, invert the y-coordinate here.
        marker_position = list(marker.position)
        marker_position[1] = -marker_position[1]

        closest_point, _ = self.surface_geometry.GetClosestPointOnSurface("scalp", marker_position)

        distance = np.linalg.norm(np.array(marker_position) - np.array(closest_point))

        return distance

    def ProjectToScalp(self, marker, opposite_side=False):
        """
        Project a marker to the scalp.

        If opposite_side is True, the marker is projected to the other side of the scalp, compared to the original position.
        If projecting from the brain to the scalp, this is done to avoid the marker being inside the scalp, where the normal vectors are not reliable.
        """
        # XXX: The markers have y-coordinate inverted, compared to the 3d view. Hence, invert the y-coordinate here.
        marker_position = list(marker.position)
        marker_position[1] = -marker_position[1]

        closest_point, closest_normal = self.surface_geometry.GetClosestPointOnSurface(
            "scalp", marker_position
        )

        if opposite_side:
            # Move to the other side of the scalp by going towards the closest point and then a bit further.
            direction_vector = np.array(closest_point) - np.array(marker_position)
            new_position = np.array(closest_point) + 1.1 * direction_vector

            # Re-compute the closest point and normal, but now for the new position.
            closest_point, closest_normal = self.surface_geometry.GetClosestPointOnSurface(
                "scalp", new_position
            )

        # The reference direction vector that we want to align the normal to.
        #
        # This was figured out by testing; from the vectors (1, 0, 0), (0, 1, 0), and (0, 0, 1), the one was selected that
        # made the coil point towards the brain.
        ref_vector = np.array([0, 0, 1])

        # Normal at the closest point.
        normal_vector = np.array(closest_normal)

        # Calculate the rotation axis (cross product) and angle (dot product).
        rotation_axis = np.cross(ref_vector, normal_vector)
        rotation_angle = np.arccos(
            np.dot(ref_vector, normal_vector)
            / (np.linalg.norm(ref_vector) * np.linalg.norm(normal_vector))
        )

        # Normalize the rotation axis.
        rotation_axis_normalized = rotation_axis / np.linalg.norm(rotation_axis)

        # Create a rotation matrix from the axis and angle.
        rotation_matrix = tr.rotation_matrix(rotation_angle, rotation_axis_normalized)

        # Convert the rotation matrix to Euler angles.
        euler_angles = tr.euler_from_matrix(rotation_matrix, "sxyz")

        # Convert the Euler angles to degrees.
        euler_angles_deg = np.degrees(euler_angles)

        # XXX: Invert back to the get to 'marker space'.
        closest_point = list(closest_point)
        closest_point[1] = -closest_point[1]

        marker.position = closest_point
        marker.orientation = euler_angles_deg

        # XXX: This rotation is done apparently to account for the fact that in coil coordinate
        #   system, y-axis is along the left-right axis of the coil, but in the world coordinates,
        #   (the ones that volume viewer shows) left-right axis is the x-axis. The right solution
        #   here would be to fix the coil coordinate system to match the world coordinates.
        displacement = [0, 0, 0, 0, 0, 90 + marker.z_rotation]
        self.MoveMarker(marker, displacement)

    def MoveMarkerByKeyboard(self, keycode):
        """
        When a key is pressed, move the target marker or the selected marker in the direction specified
        by the key.

        If in target mode, move the target marker, otherwise move the marker selected in the marker list.

        The marker can be moved in the X- or Y-direction or rotated along the Z-axis using the keys
        'W', 'A', 'S', 'D', 'PageUp', and 'PageDown'.

        The marker can also be moved in the Z-direction using the '+' and '-' keys;
        '+' moves it closer to the scalp, and '-' moves it away from the scalp.

        The marker can only be moved if the navigation is off, except for the '+' and '-' keys.
        """
        marker = (
            self.target if self.is_target_mode and self.target is not None else self.selected_marker
        )

        # Return early if no marker is selected.
        if marker is None:
            return

        # Return early if keycode is not a movement key.
        if keycode not in const.MOVEMENT_KEYCODES:
            return

        # Return early if the marker is not of type 'coil target'.
        if marker.marker_type != MarkerType.COIL_TARGET:
            return

        direction = None
        stay_on_scalp = True

        # Allow moving the marker in X- or Y-direction or rotating along Z-axis only if navigation is off.
        if keycode == const.MOVE_MARKER_POSTERIOR_KEYCODE and not self.is_navigating:
            direction = [-0.1, 0, 0, 0, 0, 0]

        elif keycode == const.MOVE_MARKER_ANTERIOR_KEYCODE and not self.is_navigating:
            direction = [0.1, 0, 0, 0, 0, 0]

        elif keycode == const.MOVE_MARKER_LEFT_KEYCODE and not self.is_navigating:
            direction = [0, 0.1, 0, 0, 0, 0]

        elif keycode == const.MOVE_MARKER_RIGHT_KEYCODE and not self.is_navigating:
            direction = [0, -0.1, 0, 0, 0, 0]

        elif keycode == const.ROTATE_MARKER_CLOCKWISE_15 and not self.is_navigating:
            stay_on_scalp = False
            direction = [0, 0, 0, 0, 0, -15]
            marker.z_rotation -= 15

        elif keycode == const.ROTATE_MARKER_COUNTERCLOCKWISE_15 and not self.is_navigating:
            stay_on_scalp = False
            direction = [0, 0, 0, 0, 0, 15]
            marker.z_rotation += 15

        elif keycode == const.ROTATE_MARKER_CLOCKWISE:
            stay_on_scalp = False
            direction = [0, 0, 0, 0, 0, -5]
            marker.z_rotation -= 5

        elif keycode == const.ROTATE_MARKER_COUNTERCLOCKWISE:
            stay_on_scalp = False
            direction = [0, 0, 0, 0, 0, 5]
            marker.z_rotation += 5

        elif keycode in [
            const.MOVE_MARKER_CLOSER_KEYCODE,
            const.MOVE_MARKER_CLOSER_ALTERNATIVE_KEYCODE,
        ]:
            stay_on_scalp = False
            direction = [0, 0, -1, 0, 0, 0]
            marker.z_offset += 1

        elif keycode in [
            const.MOVE_MARKER_AWAY_KEYCODE,
            const.MOVE_MARKER_AWAY_ALTERNATIVE_KEYCODE,
        ]:
            stay_on_scalp = False
            direction = [0, 0, 1, 0, 0, 0]
            marker.z_offset -= 1

        if direction is None:
            return

        # Move the marker in the direction specified by the key.
        displacement = np.array(direction)
        if stay_on_scalp:
            self.MoveMarkerOnScalp(
                marker=marker,
                displacement_along_scalp_tangent=displacement,
            )
        else:
            self.MoveMarker(
                marker=marker,
                displacement=displacement,
            )

        # Update the marker in the volume viewer.
        Publisher.sendMessage(
            "Update marker",
            marker=marker,
            new_position=marker.position,
            new_orientation=marker.orientation,
        )

        # Update the camera to focus on the marker.
        Publisher.sendMessage("Set camera to focus on marker", marker=marker)

        # Update the target if the marker is the active target.
        if marker.is_target:
            Publisher.sendMessage("Set target", marker=marker)
