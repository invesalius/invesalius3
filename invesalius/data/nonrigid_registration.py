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
"""
Non-rigid (deformable) registration between two 3D image volumes.

Implements Thirion's Demons algorithm, an intensity-based, iterative
registration method that estimates a dense per-voxel displacement field
warping a moving image onto a fixed image. Unlike the point-based rigid
ICP registration in invesalius.navigation.iterativeclosestpoint (used to
align tracker fiducials to patient space), this operates directly on two
image volumes and can recover local, non-linear deformation such as brain
shift or soft tissue motion between two scans of the same subject.

Only numpy/scipy are used, both already project dependencies, so this
does not introduce a new dependency (see discussion on issue #1433 about
SimpleITK/Elastix). This module implements the registration backend only;
it is not yet wired into any UI panel or navigation workflow.

The demons iteration itself is run in voxel-index space, since that is
what the intensity gradients and the update rule are defined on. But a
displacement field expressed in voxel indices cannot, by itself, be
applied to anything that lives in physical/world space, most notably a
vtkPolyData surface, without also knowing the image's spacing, origin
and axis orientation. This module represents that mapping the same way
the rest of InVesalius does, as a 4x4 voxel-to-world affine (see
invesalius.data.imagedata_utils.convert_world_to_voxel), and provides
warp_points/warp_polydata to correctly resample the field at arbitrary
world-space points and turn the interpolated voxel-space displacement
into a world-space one.
"""

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData


def warp_image(image: np.ndarray, displacement_field: np.ndarray, order: int = 1) -> np.ndarray:
    """
    Resamples `image` through a dense displacement field.

    Parameters
    ----------
    image : ndarray
        3D array to be warped.
    displacement_field : ndarray
        Array of shape ``image.shape + (image.ndim,)`` giving, for each
        voxel, the offset to sample `image` at along each axis.
    order : int
        Spline interpolation order passed to
        ``scipy.ndimage.map_coordinates`` (1 = trilinear).

    Returns
    -------
    ndarray
        `image` resampled at ``coordinate + displacement_field[coordinate]``
        for every voxel, same shape and dtype as `image`.
    """
    if displacement_field.shape[:-1] != image.shape:
        raise ValueError(
            "displacement_field's leading shape must match image.shape, "
            f"got {displacement_field.shape[:-1]} for image shape {image.shape}"
        )

    grid = np.indices(image.shape, dtype=np.float64)
    sample_coords = grid + np.moveaxis(displacement_field, -1, 0)

    warped = map_coordinates(
        image.astype(np.float64, copy=False),
        sample_coords,
        order=order,
        mode="nearest",
    )
    return warped.astype(image.dtype, copy=False)


def demons_registration(
    fixed: np.ndarray,
    moving: np.ndarray,
    num_iterations: int = 100,
    smoothing_sigma: float = 1.0,
    step_length: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Registers `moving` onto `fixed` using Thirion's Demons algorithm.

    At each iteration, a per-voxel displacement update is computed from
    the local intensity difference between `fixed` and the
    currently-warped `moving`, using Thirion's diffeomorphic demons force
    (normalized by the local gradient magnitude and intensity difference
    to keep the update numerically stable in flat, low-gradient regions).
    The accumulated displacement field is Gaussian-smoothed after every
    iteration, which regularizes the deformation and is what keeps the
    algorithm from just overfitting to noise.

    Parameters
    ----------
    fixed : ndarray
        3D reference image that `moving` is registered onto.
    moving : ndarray
        3D image to be warped into alignment with `fixed`. Must have the
        same shape as `fixed`.
    num_iterations : int
        Number of demons update iterations to run.
    smoothing_sigma : float
        Gaussian smoothing sigma (in voxels) applied to the displacement
        field after every iteration, for regularization.
    step_length : float
        Scale factor applied to each iteration's displacement update.

    Returns
    -------
    (displacement_field, warped_moving) : (ndarray, ndarray)
        `displacement_field` has shape ``fixed.shape + (fixed.ndim,)`` and
        gives the total per-voxel offset applied to `moving`.
        `warped_moving` is `moving` resampled through that field, i.e.
        ``warp_image(moving, displacement_field)``.

    Raises
    ------
    ValueError
        If `fixed` and `moving` don't have the same shape, or aren't 3D.
    """
    if fixed.shape != moving.shape:
        raise ValueError(
            f"fixed and moving must have the same shape, got {fixed.shape} and {moving.shape}"
        )
    if fixed.ndim != 3:
        raise ValueError(f"demons_registration expects 3D volumes, got {fixed.ndim}D")

    fixed = fixed.astype(np.float64, copy=False)
    moving = moving.astype(np.float64, copy=False)

    displacement_field = np.zeros(fixed.shape + (3,), dtype=np.float64)
    fixed_gradient = np.stack(np.gradient(fixed), axis=-1)
    fixed_gradient_sq_norm = np.sum(fixed_gradient**2, axis=-1)

    warped_moving = moving.copy()

    for _ in range(num_iterations):
        intensity_diff = warped_moving - fixed

        # Thirion's demons force: intensity_diff * grad / (|grad|^2 + diff^2),
        # with a small epsilon to avoid dividing by zero in flat regions.
        denominator = fixed_gradient_sq_norm + intensity_diff**2
        denominator = np.where(denominator < 1e-8, 1e-8, denominator)
        force = -(intensity_diff[..., np.newaxis] * fixed_gradient) / denominator[..., np.newaxis]

        displacement_field += step_length * force
        for axis in range(3):
            displacement_field[..., axis] = gaussian_filter(
                displacement_field[..., axis], sigma=smoothing_sigma
            )

        warped_moving = warp_image(moving, displacement_field)

    return displacement_field, warped_moving


def warp_points(
    points: np.ndarray, displacement_field: np.ndarray, affine: np.ndarray
) -> np.ndarray:
    """
    Applies a voxel-space displacement field to points given in world
    (physical, mm) coordinates.

    `displacement_field` is defined on the voxel grid, one displacement
    vector per voxel index, in voxel-index units (as returned by
    `demons_registration`). `points`, however, are not guaranteed to land
    on that grid, for instance the vertices of a vtkPolyData surface, so
    the field is resampled at each point's voxel-space location by
    trilinear interpolation rather than looked up directly.

    The affine's linear part (its top-left 3x3) is what maps a voxel
    displacement vector to a world displacement vector, since spacing and
    axis orientation can make a step of, say, 1 along a voxel axis
    correspond to a different length and/or direction in world space.
    This mirrors invesalius.data.imagedata_utils.convert_world_to_voxel,
    which uses the same affine to map points the other way.

    Parameters
    ----------
    points : ndarray
        Array of shape (N, 3) with world-space (x, y, z) coordinates.
    displacement_field : ndarray
        Array of shape ``fixed.shape + (3,)``, as returned by
        `demons_registration`, giving the voxel-space displacement at
        every voxel index (k, j, i) of the fixed volume.
    affine : ndarray
        4x4 voxel-to-world affine transform of the fixed volume (maps
        (i, j, k) voxel indices to (x, y, z) world coordinates).

    Returns
    -------
    ndarray
        Array of shape (N, 3), the input points warped into world space.
    """
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"points must have shape (N, 3), got {points.shape}")
    if displacement_field.ndim != 4 or displacement_field.shape[-1] != 3:
        raise ValueError(
            f"displacement_field must have shape (Z, Y, X, 3), got {displacement_field.shape}"
        )
    if affine.shape != (4, 4):
        raise ValueError(f"affine must be a 4x4 matrix, got {affine.shape}")

    inverse_affine = np.linalg.inv(affine)
    points_homogeneous = np.hstack([points, np.ones((points.shape[0], 1))])
    # voxel_coords[:, n] indexes displacement_field's axis n, matching the
    # affine convention used throughout invesalius.data.imagedata_utils,
    # where the affine maps voxel indices (i, j, k) to world (x, y, z)
    # axis-for-axis, with no reversal between the two.
    voxel_coords = (inverse_affine @ points_homogeneous.T).T[:, :3]

    sample_coords = voxel_coords.T
    voxel_displacement = np.stack(
        [
            map_coordinates(displacement_field[..., axis], sample_coords, order=1, mode="nearest")
            for axis in range(3)
        ],
        axis=-1,
    )

    world_displacement = (affine[:3, :3] @ voxel_displacement.T).T

    return points + world_displacement


def warp_polydata(
    polydata: vtkPolyData, displacement_field: np.ndarray, affine: np.ndarray
) -> vtkPolyData:
    """
    Applies a voxel-space displacement field to a vtkPolyData surface.

    Points are read out of `polydata`, warped in world space with
    `warp_points`, and written into a new vtkPolyData that otherwise
    shares `polydata`'s topology (points, polys/lines/verts, and point
    data are deep-copied so the input is left untouched).

    Parameters
    ----------
    polydata : vtkPolyData
        Surface whose points are in the same world/physical space as the
        volumes passed to `demons_registration`.
    displacement_field : ndarray
        Array of shape ``fixed.shape + (3,)``, as returned by
        `demons_registration`.
    affine : ndarray
        4x4 voxel-to-world affine transform of the fixed volume.

    Returns
    -------
    vtkPolyData
        A new vtkPolyData with the same topology as `polydata` and its
        points warped by the displacement field.
    """
    points = vtk_to_numpy(polydata.GetPoints().GetData())
    warped_points = warp_points(points, displacement_field, affine)

    warped_polydata = vtkPolyData()
    warped_polydata.DeepCopy(polydata)

    vtk_points = vtkPoints()
    vtk_points.SetData(numpy_to_vtk(warped_points, deep=True))
    warped_polydata.SetPoints(vtk_points)

    return warped_polydata
