import numpy as np
import pytest
from scipy.ndimage import shift
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData

from invesalius.data.nonrigid_registration import (
    demons_registration,
    warp_image,
    warp_points,
    warp_polydata,
)


def _make_sphere_volume(shape=(30, 30, 30), radius=8, center=None):
    center = center if center is not None else np.array(shape) / 2
    zz, yy, xx = np.mgrid[0 : shape[0], 0 : shape[1], 0 : shape[2]]
    r = np.sqrt((zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2)
    return (r < radius).astype(np.float64) * 255


def test_warp_image_zero_displacement_is_identity():
    image = _make_sphere_volume()
    displacement_field = np.zeros(image.shape + (3,))
    warped = warp_image(image, displacement_field)
    assert np.allclose(warped, image)


def test_warp_image_shape_mismatch_raises():
    image = _make_sphere_volume(shape=(10, 10, 10))
    bad_field = np.zeros((5, 5, 5, 3))
    with pytest.raises(ValueError):
        warp_image(image, bad_field)


def test_demons_registration_shape_mismatch_raises():
    fixed = _make_sphere_volume(shape=(10, 10, 10))
    moving = _make_sphere_volume(shape=(12, 12, 12))
    with pytest.raises(ValueError):
        demons_registration(fixed, moving)


def test_demons_registration_requires_3d_volumes():
    fixed = np.zeros((10, 10))
    moving = np.zeros((10, 10))
    with pytest.raises(ValueError):
        demons_registration(fixed, moving)


def test_demons_registration_identical_images_no_op():
    fixed = _make_sphere_volume()
    displacement_field, warped = demons_registration(fixed, fixed.copy())

    assert np.abs(displacement_field).max() == 0.0
    assert np.array_equal(warped, fixed)


def test_demons_registration_recovers_rigid_translation():
    fixed = _make_sphere_volume()
    moving = shift(fixed, shift=(1.5, -1.0, 2.0), order=1)

    mse_before = np.mean((moving - fixed) ** 2)
    _, warped = demons_registration(fixed, moving)
    mse_after = np.mean((warped - fixed) ** 2)

    assert mse_after < mse_before * 0.5


def test_demons_registration_recovers_smooth_nonrigid_deformation():
    fixed = _make_sphere_volume()

    zz, yy, xx = np.mgrid[0:30, 0:30, 0:30]
    synthetic_field = np.zeros(fixed.shape + (3,))
    synthetic_field[..., 0] = 1.5 * np.sin(yy / 6.0)
    synthetic_field[..., 1] = 1.0 * np.cos(xx / 6.0)
    synthetic_field[..., 2] = 0.8 * np.sin(zz / 5.0)
    moving = warp_image(fixed, synthetic_field)

    mse_before = np.mean((moving - fixed) ** 2)
    _, warped = demons_registration(fixed, moving)
    mse_after = np.mean((warped - fixed) ** 2)

    assert mse_after < mse_before * 0.5


def test_demons_registration_returns_field_shaped_for_moving():
    fixed = _make_sphere_volume(shape=(16, 16, 16))
    moving = shift(fixed, shift=(1.0, 0.5, -0.5), order=1)

    displacement_field, warped = demons_registration(fixed, moving, num_iterations=10)

    assert displacement_field.shape == fixed.shape + (3,)
    assert warped.shape == fixed.shape


def _make_polydata(points):
    polydata = vtkPolyData()
    vtk_points = vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.asarray(points, dtype=np.float64), deep=True))
    polydata.SetPoints(vtk_points)
    return polydata


def test_warp_points_zero_displacement_is_identity_in_world_space():
    affine = np.eye(4)
    affine[:3, 3] = (10.0, -5.0, 2.0)  # world origin offset only
    displacement_field = np.zeros((10, 10, 10, 3))
    points = np.array([[10.0, -5.0, 2.0], [12.0, -3.0, 5.0]])

    warped = warp_points(points, displacement_field, affine)

    assert np.allclose(warped, points)


def test_warp_points_applies_spacing_scaled_displacement():
    spacing = (2.0, 1.0, 0.5)
    affine = np.diag((*spacing, 1.0))
    displacement_field = np.zeros((10, 10, 10, 3))
    displacement_field[..., 0] = 1.0  # 1 voxel along axis 0

    point = np.array([[4.0, 4.0, 4.0]])  # voxel index (2, 4, 8)
    warped = warp_points(point, displacement_field, affine)

    # a 1-voxel displacement along axis 0 is `spacing[0]` mm in world space
    assert np.allclose(warped, point + np.array([[spacing[0], 0.0, 0.0]]))


def test_warp_points_rejects_wrong_shapes():
    displacement_field = np.zeros((5, 5, 5, 3))
    affine = np.eye(4)

    with pytest.raises(ValueError):
        warp_points(np.zeros((4,)), displacement_field, affine)
    with pytest.raises(ValueError):
        warp_points(np.zeros((3, 3)), np.zeros((5, 5, 5)), affine)
    with pytest.raises(ValueError):
        warp_points(np.zeros((3, 3)), displacement_field, np.eye(3))


def test_warp_polydata_preserves_topology_and_warps_points():
    affine = np.eye(4)
    displacement_field = np.zeros((10, 10, 10, 3))
    displacement_field[..., 2] = 3.0
    points = np.array([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [3.0, 1.0, 1.0]])
    polydata = _make_polydata(points)

    warped_polydata = warp_polydata(polydata, displacement_field, affine)

    assert warped_polydata.GetNumberOfPoints() == polydata.GetNumberOfPoints()
    for i in range(3):
        warped_point = np.array(warped_polydata.GetPoint(i))
        assert np.allclose(warped_point, points[i] + np.array([0.0, 0.0, 3.0]))
    # original polydata is untouched
    for i in range(3):
        assert np.allclose(np.array(polydata.GetPoint(i)), points[i])
