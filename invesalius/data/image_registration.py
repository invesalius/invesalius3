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

from dataclasses import dataclass

import nibabel as nib
import numpy as np
from scipy.ndimage import affine_transform, gaussian_filter, map_coordinates
from scipy.optimize import minimize

from invesalius.data.transformations import euler_matrix
from invesalius.reader.others_reader import read_image


@dataclass
class ImageRegistrationResult:
    moving_to_fixed_ras: np.ndarray
    fixed: np.ndarray
    aligned: np.ndarray
    spacing: tuple[float, float, float]


def _sample_volume(data, voxel_to_ras):
    if len(data.shape) != 3 or min(data.shape) < 16:
        raise ValueError("Registration requires a 3D volume with at least 16 voxels per axis.")
    steps = np.maximum(1, np.ceil(np.asarray(data.shape) / 256).astype(int))
    sampled = np.asarray(
        data[tuple(slice(None, None, int(step)) for step in steps)], dtype=np.float32
    )
    if not np.isfinite(sampled).all() or sampled.min() == sampled.max():
        raise ValueError("Registration requires finite, nonconstant image intensities.")
    affine = np.asarray(voxel_to_ras, dtype=float)
    if (
        affine.shape != (4, 4)
        or not np.isfinite(affine).all()
        or not np.allclose(affine[3], [0, 0, 0, 1])
        or np.linalg.matrix_rank(affine[:3, :3]) != 3
    ):
        raise ValueError("Registration requires a finite positional voxel-to-RAS affine.")
    return sampled, affine @ np.diag([*steps, 1])


def _normalize(image):
    low, high = np.percentile(image, [1, 99])
    if low == high:
        low, high = float(image.min()), float(image.max())
    return np.clip((image - low) / (high - low), 0, 1)


def _rigid_matrix(parameters, moving_center, fixed_center):
    # Scale radians by a 100 mm head radius so all six optimizer steps are comparable.
    matrix = euler_matrix(*(parameters[:3] / 100.0))
    matrix[:3, 3] = fixed_center + parameters[3:] - matrix[:3, :3] @ moving_center
    return matrix


def _entropy(probabilities):
    positive = probabilities[probabilities > 0]
    return -np.sum(positive * np.log(positive))


def register_image_to_volume(moving_filename, fixed_data_zyx, fixed_voxel_to_ras, cancelled):
    """Fit a rigid image registration and return moving-RAS to fixed-RAS plus a preview."""
    fixed_xyz, fixed_affine = _sample_volume(np.swapaxes(fixed_data_zyx, 0, 2), fixed_voxel_to_ras)
    moving_image = read_image(moving_filename)
    moving_xyz, moving_affine = _sample_volume(moving_image.dataobj, moving_image.affine)
    fixed_center = nib.affines.apply_affine(fixed_affine, (np.asarray(fixed_xyz.shape) - 1) / 2)
    moving_center = nib.affines.apply_affine(moving_affine, (np.asarray(moving_xyz.shape) - 1) / 2)
    fixed_normalized, moving_normalized = _normalize(fixed_xyz), _normalize(moving_xyz)
    # shortcut: local rigid search; add landmark initialization for large pose differences.
    parameters = np.zeros(6)
    rng = np.random.default_rng(42)

    for shrink in (4, 2, 1):
        if cancelled.is_set():
            raise InterruptedError("Registration cancelled.")
        levels = []
        for image, affine in ((fixed_normalized, fixed_affine), (moving_normalized, moving_affine)):
            sigma = (shrink / 2) if shrink > 1 else 0
            level = gaussian_filter(image, sigma)[::shrink, ::shrink, ::shrink]
            levels.append((level, affine @ np.diag([shrink, shrink, shrink, 1])))
        fixed, fixed_level_affine = levels[0]
        moving, moving_level_affine = levels[1]
        indices = np.flatnonzero(fixed > 0.01)
        if len(indices) < 128:
            raise ValueError("Too little anatomical image content for automatic alignment.")
        if len(indices) > 50_000:
            indices = rng.choice(indices, size=50_000, replace=False)
        points = np.asarray(np.unravel_index(indices, fixed.shape), dtype=float)
        fixed_values = fixed.ravel()[indices]
        moving_inverse = np.linalg.inv(moving_level_affine)
        moving_maximum = (np.asarray(moving.shape) - 1)[:, None]

        def metric(candidate):
            if cancelled.is_set():
                raise InterruptedError("Registration cancelled.")
            if not np.isfinite(candidate).all():
                return 3.0
            transform = _rigid_matrix(candidate, moving_center, fixed_center)
            voxel_map = moving_inverse @ np.linalg.solve(transform, fixed_level_affine)
            coordinates = voxel_map[:3, :3] @ points + voxel_map[:3, 3, None]
            valid = np.all((coordinates >= 0) & (coordinates <= moving_maximum), axis=0)
            overlap = valid.mean()
            if valid.sum() < max(128, len(indices) * 0.25):
                return 2.0 + (1.0 - overlap)
            values = map_coordinates(moving, coordinates[:, valid], order=1, prefilter=False)
            joint, _, _ = np.histogram2d(
                fixed_values[valid], values, bins=48, range=((0, 1), (0, 1))
            )
            joint = gaussian_filter(joint, 0.5)
            joint /= joint.sum()
            joint_entropy = _entropy(joint)
            if joint_entropy <= 0:
                return 3.0
            information = (
                _entropy(joint.sum(axis=0)) + _entropy(joint.sum(axis=1))
            ) / joint_entropy
            # Penalize lost overlap so a small matching patch cannot dominate the registration.
            return 2.0 - information + 0.25 * (1.0 - overlap)

        if shrink == 4:
            identity = np.zeros(6)
            identity[3:] = moving_center - fixed_center
            if metric(identity) < metric(parameters):
                parameters = identity
        initial_score = metric(parameters)
        result = minimize(
            metric,
            parameters,
            method="Powell",
            options={"xtol": 0.01, "ftol": 1e-5, "maxiter": 60, "maxfev": 2000},
        )
        if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            raise ValueError("Registration could not calculate a finite rigid transformation.")
        if result.fun < initial_score:
            parameters = result.x
        if shrink == 1 and not result.success:
            raise ValueError(
                "Alignment did not converge. Check the reference MRI and image coverage."
            )
    if metric(parameters) >= 1.0:
        raise ValueError("Registration could not find sufficient image similarity and overlap.")
    matrix_ras = _rigid_matrix(parameters, moving_center, fixed_center)
    if (
        not np.isfinite(matrix_ras).all()
        or not np.allclose(matrix_ras[:3, :3].T @ matrix_ras[:3, :3], np.eye(3), atol=1e-5)
        or not np.isclose(np.linalg.det(matrix_ras[:3, :3]), 1.0, atol=1e-5)
    ):
        raise ValueError("Registration did not produce a valid rigid transformation.")
    # Resampling pulls fixed voxels from moving voxels; the exported matrix maps the other way.
    voxel_map = np.linalg.solve(moving_affine, np.linalg.solve(matrix_ras, fixed_affine))
    aligned_data = affine_transform(
        moving_xyz, voxel_map, output_shape=fixed_xyz.shape, order=1, prefilter=False
    )
    if cancelled.is_set():
        raise InterruptedError("Registration cancelled.")
    if not np.isfinite(aligned_data).all() or aligned_data.min() == aligned_data.max():
        raise ValueError("The aligned image does not contain usable anatomical information.")
    return ImageRegistrationResult(
        matrix_ras,
        np.swapaxes(fixed_xyz, 0, 2),
        np.swapaxes(aligned_data, 0, 2),
        tuple(float(value) for value in np.linalg.norm(fixed_affine[:3, :3], axis=0)),
    )
