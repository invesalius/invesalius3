import numpy as np
import pytest

from invesalius.math_utils import solve_qef


def test_qef_orthogonal_planes():
    """
    Test QEF solver with 3 orthogonal planes (like the corner of a cube).
    The intersection of x=1, y=1, z=1 should exactly be [1, 1, 1].
    """
    normals = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    positions = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])

    result = solve_qef(normals, positions)
    np.testing.assert_allclose(result, [1.0, 1.0, 1.0], atol=1e-5)


def test_qef_parallel_planes_fallback():
    """
    Test QEF solver with parallel planes.
    Standard matrix inversion fails here (singular matrix Ax=b).
    The SVD pseudo-inverse should gracefully fall back to returning
    a stable point (derived from the mass point offset).
    """
    normals = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    positions = np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]])

    # Mass point of positions is [2.0, 0.0, 0.0]
    # The pseudo-inverse logic handles this gracefully due to SVD.
    result = solve_qef(normals, positions)

    # Depending on the exact SVD projection, it will return a point
    # that minimizes the error. Since all normals point along X,
    # the optimal X is the average, and Y, Z stay at mass point's Y, Z.
    np.testing.assert_allclose(result, [2.0, 0.0, 0.0], atol=1e-5)


def test_qef_collinear_normals():
    """
    Test QEF with collinear normals (like a sharp edge).
    This is an under-determined system in 3D (rank 2).
    """
    normals = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    positions = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 1.0]])

    result = solve_qef(normals, positions)

    # The optimal point should lie on the intersection of x=1 and y=1.
    # The z-coordinate is under-determined by the equations, so it
    # should pull toward the mass point's z-coord = 0.333333
    mass_z = (0.0 + 0.0 + 1.0) / 3.0
    np.testing.assert_allclose(result, [1.0, 1.0, mass_z], atol=1e-5)


def test_qef_invalid_shapes():
    """
    Test that appropriate ValueErrors are raised for invalid inputs.
    """
    bad_normals = np.array([[1, 0, 0], [0, 1, 0]])  # 2x3
    bad_positions = np.array([[1, 0, 0]])  # 1x3

    with pytest.raises(ValueError, match="same number of points"):
        solve_qef(bad_normals, bad_positions)

    flat_normals = np.array([1, 0, 0])
    with pytest.raises(ValueError, match="must be an N x 3 array"):
        solve_qef(flat_normals, bad_positions)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(["-v", __file__]))
