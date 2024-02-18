import math

import vtk
import numpy as np

from invesalius.data.markers.marker import MarkerType
from invesalius.data.markers.surface_geometry import SurfaceGeometry
import invesalius.data.transformations as tr


class MarkerTransformator:
    def __init__(self):
        self.surface_geometry = SurfaceGeometry()

    def ProjectToScalp(self, marker):
        # XXX: The markers have y-coordinate inverted, compared to the 3d view. Hence, invert the y-coordinate here.
        marker_position = list(marker.position)
        marker_position[1] = -marker_position[1]

        closest_point, closest_normal = self.surface_geometry.get_closest_point_on_surface('scalp', marker_position)

        # The reference direction vector that we want to align the normal to.
        #
        # This was figured out by testing; from the vectors (1, 0, 0), (0, 1, 0), and (0, 0, 1), the one was selected that
        # made the coil point towards the brain.
        ref_vector = np.array([0, 0, 1])

        # Normal at the closest point.
        normal_vector = np.array(closest_normal)

        # Calculate the rotation axis (cross product) and angle (dot product).
        rotation_axis = np.cross(ref_vector, normal_vector)
        rotation_angle = np.arccos(np.dot(ref_vector, normal_vector) / (np.linalg.norm(ref_vector) * np.linalg.norm(normal_vector)))

        # Normalize the rotation axis.
        rotation_axis_normalized = rotation_axis / np.linalg.norm(rotation_axis)

        # Create a rotation matrix from the axis and angle.
        rotation_matrix = tr.rotation_matrix(rotation_angle, rotation_axis_normalized)

        # Rotate around coil's z-axis an additional 90 degrees to make coil's front-back axis align with anterior-posterior axis of the brain.
        #
        # This was figured out by looking at the discrepancy between the coil and the brain in the 3D view.
        rotation_matrix_align_coil = tr.rotation_matrix(math.pi / 2, [0, 0, 1])

        # Convert the rotation matrix to Euler angles.
        euler_angles = tr.euler_from_matrix(rotation_matrix @ rotation_matrix_align_coil, 'sxyz')

        # Convert the Euler angles to degrees.
        euler_angles_deg = np.degrees(euler_angles)

        # XXX: Invert back to the get to 'marker space'.
        closest_point = list(closest_point)
        closest_point[1] = -closest_point[1]

        marker.position = closest_point
        marker.orientation = euler_angles_deg
