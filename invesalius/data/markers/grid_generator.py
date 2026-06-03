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

import uuid
from typing import List

import numpy as np

import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.data.markers.surface_geometry import SurfaceGeometry


# Maximum grid dimension to prevent accidental creation of excessive markers.
MAX_GRID_DIMENSION = 100


class GridGenerator:
    """Generates a grid of coil targets around a reference target on the scalp surface.

    The grid points are computed in the local coordinate system of the reference marker,
    projected onto the smoothed scalp surface, and oriented tangentially to the surface
    while preserving the z_rotation from the original target.
    """

    def __init__(self, surface_geometry: SurfaceGeometry):
        self.surface_geometry = surface_geometry

    def generate_rectangular_grid(
        self,
        reference_marker: Marker,
        rows: int,
        cols: int,
        spacing: float,
    ) -> List[Marker]:
        """Generate a rectangular grid of coil targets centered on the reference marker.

        The grid is laid out in the local coordinate system of the reference marker:
        - Local X axis (anterior/posterior direction) corresponds to rows.
        - Local Y axis (lateral direction) corresponds to columns.

        Each grid point is displaced from the reference, projected onto the smoothed
        scalp surface, and given an orientation tangential to the local surface normal.

        :param reference_marker: The coil target marker serving as the center of the grid.
        :param rows: Number of rows in the grid.
        :param cols: Number of columns in the grid.
        :param spacing: Distance between adjacent grid points in mm.
        :return: A list of newly created Marker objects (type COIL_TARGET).
        """
        if rows > MAX_GRID_DIMENSION or cols > MAX_GRID_DIMENSION:
            raise ValueError(
                f"Grid dimensions ({rows}x{cols}) exceed the maximum allowed "
                f"({MAX_GRID_DIMENSION}x{MAX_GRID_DIMENSION})."
            )

        markers = []

        # Compute offsets so the grid is centered on the reference marker.
        row_offset = (rows - 1) / 2.0
        col_offset = (cols - 1) / 2.0

        for r in range(rows):
            for c in range(cols):
                # Skip the center point (the reference marker itself).
                if r == row_offset and c == col_offset:
                    continue

                dx = (r - row_offset) * spacing
                dy = (c - col_offset) * spacing

                # Label follows the pattern: <ref_label><row>_<col>
                label = f"{reference_marker.label}{r + 1}_{c + 1}"

                new_marker = self._create_grid_point(
                    reference_marker=reference_marker,
                    dx=dx,
                    dy=dy,
                    label=label,
                )
                markers.append(new_marker)

        return markers

    def generate_circular_grid(
        self,
        reference_marker: Marker,
        rings: int,
        points_per_ring: int,
        spacing: float,
    ) -> List[Marker]:
        """Generate a circular grid of coil targets around the reference marker.

        The grid consists of concentric rings centered on the reference marker.
        Each ring has a fixed number of points distributed evenly around the circle.

        :param reference_marker: The coil target marker serving as the center of the grid.
        :param rings: Number of concentric rings.
        :param points_per_ring: Number of points on each ring.
        :param spacing: Radial distance between consecutive rings in mm.
        :return: A list of newly created Marker objects (type COIL_TARGET).
        """
        total_points = rings * points_per_ring
        if total_points > MAX_GRID_DIMENSION * MAX_GRID_DIMENSION:
            raise ValueError(
                f"Total grid points ({total_points}) exceed the maximum allowed "
                f"({MAX_GRID_DIMENSION * MAX_GRID_DIMENSION})."
            )

        markers = []

        for ring_idx in range(1, rings + 1):
            radius = ring_idx * spacing

            for point_idx in range(points_per_ring):
                angle = 2 * np.pi * point_idx / points_per_ring

                dx = radius * np.cos(angle)
                dy = radius * np.sin(angle)

                # Label follows the pattern: <ref_label><ring>_<point>
                label = f"{reference_marker.label}{ring_idx}_{point_idx + 1}"

                new_marker = self._create_grid_point(
                    reference_marker=reference_marker,
                    dx=dx,
                    dy=dy,
                    label=label,
                )
                markers.append(new_marker)

        return markers

    def _create_grid_point(
        self,
        reference_marker: Marker,
        dx: float,
        dy: float,
        label: str,
    ) -> Marker:
        """Create a single grid point by displacing from the reference marker and
        projecting onto the scalp surface.

        Steps:
        1. Duplicate the reference marker.
        2. Move the duplicate in the local coordinate system by (dx, dy, 0).
        3. Project onto the smoothed scalp surface (find closest point + normal).
        4. Compute the orientation from the local surface normal.
        5. Apply the original z_rotation.
        6. Apply the original z_offset (distance from scalp).
        7. Set marker type and label.

        :param reference_marker: The original coil target to base the grid point on.
        :param dx: Displacement along the local X axis (anterior/posterior) in mm.
        :param dy: Displacement along the local Y axis (lateral) in mm.
        :param label: Label for the new marker.
        :return: A new Marker object positioned on the scalp.
        """
        new_marker = reference_marker.duplicate()

        # Step 1: Move the marker in its local coordinate system by the grid offset.
        displacement = [dx, dy, 0, 0, 0, 0]
        self._move_marker(new_marker, displacement)

        # Step 2: Project the displaced marker onto the smoothed scalp surface.
        self._project_to_scalp(new_marker, reference_marker.z_rotation)

        # Step 3: Apply the z_offset from the reference marker (distance above scalp).
        if reference_marker.z_offset != 0:
            z_offset_displacement = [0, 0, reference_marker.z_offset, 0, 0, 0]
            self._move_marker(new_marker, z_offset_displacement)

        # Step 4: Set marker properties.
        new_marker.marker_type = MarkerType.COIL_TARGET
        new_marker.label = label
        new_marker.z_rotation = reference_marker.z_rotation
        new_marker.z_offset = reference_marker.z_offset
        new_marker.marker_uuid = str(uuid.uuid4())
        new_marker.is_target = False

        # Reset cortex position since it is no longer valid for the new position.
        new_marker.cortex_position_orientation = 6 * [None]
        new_marker.mep_value = None

        return new_marker

    def _move_marker(self, marker, displacement):
        """Move a marker in its local coordinate system by the given displacement.

        This replicates the logic from MarkerTransformator.MoveMarker, handling the
        y-coordinate inversion between marker space and 3D view space.

        :param marker: The marker to move.
        :param displacement: A list of 6 values [dx, dy, dz, dalpha, dbeta, dgamma].
        """
        # The markers have y-coordinate inverted compared to the 3D view.
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

        # Invert back to marker space.
        new_position = list(new_position)
        new_position[1] = -new_position[1]

        marker.position = new_position
        marker.orientation = new_orientation

    def _project_to_scalp(self, marker, z_rotation):
        """Project a marker onto the smoothed scalp surface and orient it tangentially.

        This replicates the logic from MarkerTransformator.ProjectToScalp, using the
        smoothed scalp surface from SurfaceGeometry.

        :param marker: The marker to project onto the scalp.
        :param z_rotation: The z_rotation value to apply after projection.
        """
        # The markers have y-coordinate inverted compared to the 3D view.
        marker_position = list(marker.position)
        marker_position[1] = -marker_position[1]

        closest_point, closest_normal = self.surface_geometry.GetClosestPointOnSurface(
            "scalp", marker_position
        )

        # The reference direction vector that we want to align the normal to.
        # This was figured out by testing; (0, 0, 1) makes the coil point towards the brain.
        ref_vector = np.array([0, 0, 1])

        # Normal at the closest point.
        normal_vector = np.array(closest_normal)

        # Calculate the rotation axis (cross product) and angle (dot product).
        rotation_axis = np.cross(ref_vector, normal_vector)
        rotation_axis_norm = np.linalg.norm(rotation_axis)

        # Handle the degenerate case where the normal is parallel to the reference vector.
        if rotation_axis_norm < 1e-10:
            euler_angles_deg = [0.0, 0.0, 0.0]
        else:
            rotation_angle = np.arccos(
                np.clip(
                    np.dot(ref_vector, normal_vector)
                    / (np.linalg.norm(ref_vector) * np.linalg.norm(normal_vector)),
                    -1.0,
                    1.0,
                )
            )

            # Normalize the rotation axis.
            rotation_axis_normalized = rotation_axis / rotation_axis_norm

            # Create a rotation matrix from the axis and angle.
            rotation_matrix = tr.rotation_matrix(rotation_angle, rotation_axis_normalized)

            # Convert the rotation matrix to Euler angles.
            euler_angles = tr.euler_from_matrix(rotation_matrix, "sxyz")

            # Convert the Euler angles to degrees.
            euler_angles_deg = np.degrees(euler_angles)

        # Invert back to marker space.
        closest_point = list(closest_point)
        closest_point[1] = -closest_point[1]

        marker.position = closest_point
        marker.orientation = euler_angles_deg

        # Apply the z_rotation offset (90 degrees base + custom z_rotation).
        # This accounts for the difference between coil and world coordinate systems.
        displacement = [0, 0, 0, 0, 0, 90 + z_rotation]
        self._move_marker(marker, displacement)
