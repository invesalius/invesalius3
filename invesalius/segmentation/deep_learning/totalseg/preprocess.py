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

import json
import logging

import nibabel as nib
import numpy as np
from scipy.ndimage import zoom

logger = logging.getLogger(__name__)


def load_nifti(path: str) -> tuple[np.ndarray, np.ndarray]:
    img = nib.load(str(path))
    img = nib.as_closest_canonical(img)
    # nnU-Net is trained on (Z, Y, X). Native nibabel order is (X, Y, Z).
    volume = img.get_fdata().astype(np.float32).transpose(2, 1, 0)
    spacing = np.array(img.header.get_zooms()[::-1], dtype=np.float32)
    return volume, spacing


def load_volume_from_array(volume: np.ndarray, spacing) -> tuple[np.ndarray, np.ndarray]:
    volume = np.asarray(volume, dtype=np.float32)
    if volume.ndim != 3:
        raise ValueError(f"Expected 3D volume, got shape {volume.shape}")
    volume = volume.transpose(2, 1, 0)
    spacing = np.array(spacing[::-1], dtype=np.float32)
    return volume, spacing


def read_plans(path: str, config: str = "3d_fullres") -> dict:
    with open(path) as f:
        plans = json.load(f)
    cfg = plans["configurations"][config]
    intensity = plans["foreground_intensity_properties_per_channel"]["0"]
    return {
        "patch_size": cfg["patch_size"],
        "target_spacing": cfg["spacing"],
        "normalization": cfg["normalization_schemes"][0],
        "mean": intensity["mean"],
        "std": intensity["std"],
        "clip_low": intensity["percentile_00_5"],
        "clip_high": intensity["percentile_99_5"],
    }


def read_sidecar(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def crop_to_body(volume: np.ndarray) -> tuple[np.ndarray, list[tuple[int, int]]]:
    mask = volume != 0
    if not mask.any():
        return volume, [(0, s) for s in volume.shape]

    nonzero = np.where(mask)
    bbox = [(int(axis.min()), int(axis.max()) + 1) for axis in nonzero]
    cropped = volume[
        bbox[0][0] : bbox[0][1],
        bbox[1][0] : bbox[1][1],
        bbox[2][0] : bbox[2][1],
    ]
    return cropped, bbox


def resample_volume(
    volume: np.ndarray,
    src_spacing: np.ndarray,
    dst_spacing: np.ndarray,
    order: int = 3,
) -> np.ndarray:
    factors = src_spacing / dst_spacing
    return zoom(volume, factors, order=order).astype(np.float32)


def resample_to_shape(volume: np.ndarray, target_shape, order: int = 0) -> np.ndarray:
    current = np.array(volume.shape)
    target = np.array(target_shape)
    factors = target / current
    result = zoom(volume, factors, order=order)

    if result.shape == tuple(target_shape):
        return result

    # zoom() can be off by one voxel due to rounding; crop or pad to recover.
    out = np.zeros(target_shape, dtype=result.dtype)
    src_sl, dst_sl = [], []
    for s, d in zip(result.shape, target_shape):
        if s >= d:
            start = (s - d) // 2
            src_sl.append(slice(start, start + d))
            dst_sl.append(slice(0, d))
        else:
            start = (d - s) // 2
            src_sl.append(slice(0, s))
            dst_sl.append(slice(start, start + s))
    out[tuple(dst_sl)] = result[tuple(src_sl)]
    return out


def normalize_ct(
    volume: np.ndarray,
    clip_low: float,
    clip_high: float,
    mean: float,
    std: float,
) -> np.ndarray:
    # Dataset-wide stats, NOT per-volume.
    v = np.clip(volume, clip_low, clip_high)
    v = (v - mean) / std
    return v.astype(np.float32)


def normalize_mri(volume: np.ndarray) -> np.ndarray:
    mask = volume > 0
    if not mask.any():
        return volume.astype(np.float32)
    mean = volume[mask].mean()
    std = volume[mask].std()
    return ((volume - mean) / (std + 1e-8)).astype(np.float32)


def preprocess(
    volume: np.ndarray,
    spacing: np.ndarray,
    plans: dict,
    modality: str = "ct",
) -> tuple[np.ndarray, dict]:
    cropped, bbox = crop_to_body(volume)
    target_spacing = np.array(plans["target_spacing"], dtype=np.float32)
    resampled = resample_volume(cropped, spacing, target_spacing, order=3)

    if modality == "ct":
        normalized = normalize_ct(
            resampled,
            clip_low=plans["clip_low"],
            clip_high=plans["clip_high"],
            mean=plans["mean"],
            std=plans["std"],
        )
    elif modality == "mri":
        normalized = normalize_mri(resampled)
    else:
        raise ValueError(f"Unknown modality: {modality}")

    meta = {
        "original_shape": tuple(volume.shape),
        "original_spacing": spacing.tolist(),
        "bbox": bbox,
        "cropped_shape": tuple(cropped.shape),
        "resampled_shape": tuple(resampled.shape),
        "target_spacing": target_spacing.tolist(),
    }
    return normalized, meta


def postprocess(label_map: np.ndarray, meta: dict) -> np.ndarray:
    label_in_cropped = resample_to_shape(label_map, meta["cropped_shape"], order=0)
    output = np.zeros(meta["original_shape"], dtype=np.uint8)
    bbox = meta["bbox"]
    output[
        bbox[0][0] : bbox[0][1],
        bbox[1][0] : bbox[1][1],
        bbox[2][0] : bbox[2][1],
    ] = label_in_cropped
    return output


def output_to_input_layout(label_map: np.ndarray) -> np.ndarray:
    return label_map.transpose(2, 1, 0)
