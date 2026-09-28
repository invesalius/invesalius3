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
Core computational and data management engine for fMRI support and functional
connectivity modalities in InVesalius.

Supported modalities:
1. Parcellations showing functional networks (Yeo 7 / Yeo 17 atlases)
2. Task Beta values and 4D BOLD timeframe inspection
3. Resting-state / Task continuous Functional Gradients
4. Seed-based Functional Connectivity (real-time voxel-wise Pearson correlation)
"""

from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt
import nibabel as nb
import numpy as np
from scipy.ndimage import zoom
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkUnsignedCharArray
from vtkmodules.vtkCommonDataModel import vtkPolyData

# --- Modality Identifiers ---
MODALITY_PARCELLATION = "Parcellations (Yeo7 / Yeo17)"
MODALITY_BETA_BOLD = "Beta values / BOLD timeframes"
MODALITY_GRADIENT = "Rest / Task Functional Gradients"
MODALITY_SEED_FC = "Seed-based Functional Connectivity"

MODALITY_CHOICES = [
    MODALITY_PARCELLATION,
    MODALITY_BETA_BOLD,
    MODALITY_GRADIENT,
    MODALITY_SEED_FC,
]

# --- Yeo 7 Cortical Networks Definition (Yeo et al. 2011) ---
YEO_7_NETWORKS: dict[int, dict[str, Any]] = {
    1: {"name": "Visual", "color": (120, 18, 134), "hex": "#781286"},
    2: {"name": "Somatomotor", "color": (70, 130, 180), "hex": "#4682B4"},
    3: {"name": "Dorsal Attention", "color": (0, 118, 14), "hex": "#00760E"},
    4: {"name": "Ventral Attention / Salience", "color": (196, 58, 250), "hex": "#C43AFA"},
    5: {"name": "Limbic", "color": (220, 248, 164), "hex": "#DCF8A4"},
    6: {"name": "Frontoparietal / Control", "color": (230, 148, 34), "hex": "#E69422"},
    7: {"name": "Default Mode Network", "color": (205, 62, 78), "hex": "#CD3E4E"},
}

# --- Yeo 17 Cortical Networks Definition ---
YEO_17_NETWORKS: dict[int, dict[str, Any]] = {
    1: {"name": "Visual Central", "color": (120, 18, 134), "hex": "#781286"},
    2: {"name": "Visual Peripheral", "color": (255, 0, 0), "hex": "#FF0000"},
    3: {"name": "Somatomotor A", "color": (70, 130, 180), "hex": "#4682B4"},
    4: {"name": "Somatomotor B", "color": (42, 204, 164), "hex": "#2ACCA4"},
    5: {"name": "Dorsal Attention A", "color": (74, 155, 60), "hex": "#4A9B3C"},
    6: {"name": "Dorsal Attention B", "color": (0, 118, 14), "hex": "#00760E"},
    7: {"name": "Ventral Attention A", "color": (196, 58, 250), "hex": "#C43AFA"},
    8: {"name": "Ventral Attention B", "color": (255, 152, 213), "hex": "#FF98D5"},
    9: {"name": "Limbic A", "color": (220, 248, 164), "hex": "#DCF8A4"},
    10: {"name": "Limbic B", "color": (119, 140, 43), "hex": "#778C2B"},
    11: {"name": "Control / FP A", "color": (230, 148, 34), "hex": "#E69422"},
    12: {"name": "Control / FP B", "color": (135, 50, 74), "hex": "#87324A"},
    13: {"name": "Control / FP C", "color": (12, 48, 255), "hex": "#0C30FF"},
    14: {"name": "Default Mode A", "color": (205, 62, 78), "hex": "#CD3E4E"},
    15: {"name": "Default Mode B", "color": (255, 215, 0), "hex": "#FFD700"},
    16: {"name": "Default Mode C", "color": (0, 0, 139), "hex": "#00008B"},
    17: {"name": "Temporoparietal", "color": (32, 178, 170), "hex": "#20B2AA"},
}

COLORMAP_PRESETS = {
    MODALITY_PARCELLATION: ["Yeo Standard", "tab10", "Set3", "Paired", "Dark2"],
    MODALITY_BETA_BOLD: ["autumn", "hot", "plasma", "inferno", "bwr", "coolwarm", "RdBu_r"],
    MODALITY_GRADIENT: ["viridis", "plasma", "coolwarm", "twilight", "spectral", "cividis"],
    MODALITY_SEED_FC: ["hot", "autumn", "plasma", "bwr", "coolwarm", "inferno"],
}


def resample_volume(data: np.ndarray, target_shape: tuple[int, int, int], is_categorical: bool = False) -> np.ndarray:
    """
    Resample a 3D or 4D volume to match target 3D shape (Z, Y, X).
    For 4D volumes (Z, Y, X, T), each 3D time frame is resampled to target_shape.
    """
    if data.ndim == 3:
        if data.shape == target_shape:
            return data.copy()
        zoom_factors = [t / s for t, s in zip(target_shape, data.shape)]
        order = 0 if is_categorical else 1
        return zoom(data, zoom_factors, order=order)
    elif data.ndim == 4:
        spatial_shape = data.shape[:3]
        if spatial_shape == target_shape:
            return data.copy()
        zoom_factors = [t / s for t, s in zip(target_shape, spatial_shape)] + [1.0]
        order = 0 if is_categorical else 1
        return zoom(data, zoom_factors, order=order)
    else:
        raise ValueError(f"Expected 3D or 4D array, got ndim={data.ndim}")


def generate_synthetic_yeo_parcellation(shape: tuple[int, int, int]) -> np.ndarray:
    """
    Generate a synthetic cortical resting-state 7-network parcellation volume
    adapted to the target shape (Z, Y, X). 0 = background, 1..7 = Yeo networks.
    """
    dz, dy, dx = shape
    zz, yy, xx = np.ogrid[:dz, :dy, :dx]
    cz, cy, cx = dz / 2.0, dy / 2.0, dx / 2.0
    rz, ry, rx = dz * 0.42, dy * 0.45, dx * 0.40

    # Ellipsoid brain mask
    dist_sq = ((zz - cz) / rz) ** 2 + ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    brain_mask = dist_sq <= 1.0
    cortex_mask = brain_mask & (dist_sq >= 0.45)

    parcellation = np.zeros(shape, dtype=np.uint8)

    # Angular and spatial sectors mapped to canonical networks:
    angle = np.arctan2(yy - cy, xx - cx)  # -pi to pi
    norm_z = (zz - cz) / rz  # -1 to 1
    norm_y = (yy - cy) / ry  # -1 to 1

    # 1: Visual (Posterior / Occipital)
    parcellation[cortex_mask & (norm_y < -0.35) & (norm_z < 0.2)] = 1
    # 2: Somatomotor (Central Strip / Dorsal Parietal-Frontal)
    parcellation[cortex_mask & (norm_y >= -0.2) & (norm_y <= 0.15) & (norm_z >= 0.1)] = 2
    # 3: Dorsal Attention (Superior Parietal & FEF)
    parcellation[cortex_mask & (norm_y >= -0.35) & (norm_y < -0.15) & (norm_z >= 0.3)] = 3
    # 4: Ventral Attention / Salience (Insula / Temporoparietal junction)
    parcellation[cortex_mask & (abs(angle) > 1.2) & (abs(angle) < 2.2) & (norm_z < 0.1)] = 4
    # 5: Limbic (Orbitofrontal / Temporal pole)
    parcellation[cortex_mask & (norm_z < -0.3) & (norm_y > 0.0)] = 5
    # 6: Frontoparietal / Control (Lateral Prefrontal)
    parcellation[cortex_mask & (norm_y > 0.2) & (norm_y < 0.6) & (norm_z > 0.0)] = 6
    # 7: Default Mode Network (Medial Prefrontal & PCC)
    parcellation[cortex_mask & (norm_y >= 0.55)] = 7
    parcellation[cortex_mask & (norm_y < -0.2) & (abs(norm_z) < 0.2) & (abs(xx - cx) < rx * 0.35)] = 7

    return parcellation


def generate_synthetic_4d_bold(
    shape: tuple[int, int, int], num_frames: int = 30, random_seed: int = 42
) -> np.ndarray:
    """
    Generate a synthetic 4D resting-state fMRI dataset (Z, Y, X, T) with
    synchronized networks and realistic temporal dynamics for seed connectivity testing.
    """
    dz, dy, dx = shape
    rng = np.random.RandomState(random_seed)

    # Base noise
    bold_4d = rng.randn(dz, dy, dx, num_frames).astype(np.float32) * 0.8

    # Create brain mask
    zz, yy, xx = np.ogrid[:dz, :dy, :dx]
    cz, cy, cx = dz / 2.0, dy / 2.0, dx / 2.0
    rz, ry, rx = dz * 0.42, dy * 0.45, dx * 0.40
    dist_sq = ((zz - cz) / rz) ** 2 + ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    brain_mask = dist_sq <= 1.0

    t = np.linspace(0, 4 * math.pi, num_frames)

    # Network 1: Bilateral Motor (sinusoidal modulation)
    sig1 = np.sin(t) * 3.5
    left_motor = brain_mask & (abs(zz - cz) < 4) & (abs(yy - cy) < 4) & (xx < cx - 4)
    right_motor = brain_mask & (abs(zz - cz) < 4) & (abs(yy - cy) < 4) & (xx > cx + 4)
    bold_4d[left_motor] += sig1
    bold_4d[right_motor] += sig1

    # Network 2: Default Mode Network (mPFC + PCC)
    sig2 = np.cos(t * 0.7) * 3.2
    mpfc = brain_mask & (zz > cz - 3) & (yy > cy + dy * 0.25) & (abs(xx - cx) < 6)
    pcc = brain_mask & (zz > cz - 3) & (yy < cy - dy * 0.2) & (abs(xx - cx) < 6)
    bold_4d[mpfc] += sig2
    bold_4d[pcc] += sig2

    # Network 3: Visual Cortex
    sig3 = np.sin(t * 1.5) * 2.8
    visual = brain_mask & (yy < cy - dy * 0.3) & (abs(zz - cz) < 6) & (abs(xx - cx) < 8)
    bold_4d[visual] += sig3

    # Baseline intensity for brain voxels
    bold_4d[brain_mask] += 100.0
    bold_4d[~brain_mask] = 0.0

    return bold_4d


def generate_synthetic_gradient(shape: tuple[int, int, int]) -> np.ndarray:
    """
    Generate a synthetic macroscale functional gradient (Gradient 1: Sensorimotor to Transmodal).
    Values range continuously from -1.0 to +1.0.
    """
    dz, dy, dx = shape
    zz, yy, xx = np.ogrid[:dz, :dy, :dx]
    cz, cy, cx = dz / 2.0, dy / 2.0, dx / 2.0
    rz, ry, rx = dz * 0.42, dy * 0.45, dx * 0.40
    dist_sq = ((zz - cz) / rz) ** 2 + ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
    brain_mask = dist_sq <= 1.0

    # Sensorimotor (posterior/dorsal) to DMN/PFC (anterior/polar)
    grad_slice = (yy - cy) / ry * 0.7 + (zz - cz) / rz * 0.3
    grad = np.broadcast_to(grad_slice, shape).copy()
    grad = np.clip(grad, -1.0, 1.0)
    grad[~brain_mask] = 0.0
    return grad.astype(np.float32)


def compute_seed_correlation(
    bold_4d: np.ndarray, seed_coord: tuple[int, int, int], threshold: float = 0.3
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute Pearson correlation between seed voxel time-series and all other voxels.

    :param bold_4d: 4D numpy array (Z, Y, X, T)
    :param seed_coord: Tuple (z, y, x)
    :param threshold: float minimum correlation value [0, 1]
    :return: (r_map, thresholded_r_map)
    """
    sz, sy, sx = seed_coord
    dz, dy, dx, num_frames = bold_4d.shape

    # Clamp seed coordinates
    sz = max(0, min(dz - 1, sz))
    sy = max(0, min(dy - 1, sy))
    sx = max(0, min(dx - 1, sx))

    seed_ts = bold_4d[sz, sy, sx, :].astype(np.float64)
    seed_std = np.std(seed_ts)

    if seed_std < 1e-6:
        # If seed is in background / flat, return zero map
        return np.zeros((dz, dy, dx), dtype=np.float32), np.zeros((dz, dy, dx), dtype=np.float32)

    seed_norm = (seed_ts - np.mean(seed_ts)) / seed_std

    # Flatten spatial dims for high-speed dot product
    flat_data = bold_4d.reshape(-1, num_frames).astype(np.float64)
    means = np.mean(flat_data, axis=1, keepdims=True)
    stds = np.std(flat_data, axis=1, keepdims=True)
    stds[stds < 1e-6] = 1.0

    flat_norm = (flat_data - means) / stds
    r_flat = np.dot(flat_norm, seed_norm) / float(num_frames)
    r_map = r_flat.reshape(dz, dy, dx).astype(np.float32)

    # Thresholded map
    thresh_map = np.where(r_map >= threshold, r_map, 0.0).astype(np.float32)
    return r_map, thresh_map


def build_categorical_colormap(
    unique_labels: np.ndarray,
    network_dict: dict[int, dict[str, Any]],
    active_labels: set[int] | None = None,
) -> dict[int, tuple[float, float, float, float]]:
    """
    Build color dictionary for integer parcellation labels.
    """
    color_dict: dict[int, tuple[float, float, float, float]] = {0: (0.0, 0.0, 0.0, 0.0)}

    for label in unique_labels:
        label = int(label)
        if label == 0:
            continue
        if active_labels is not None and label not in active_labels:
            color_dict[label] = (0.0, 0.0, 0.0, 0.0)
            continue

        if label in network_dict:
            r, g, b = (c / 255.0 for c in network_dict[label]["color"][:3])
            color_dict[label] = (r, g, b, 1.0)
        else:
            # Fallback to matplotlib tab20
            cmap = plt.get_cmap("tab20")
            c = cmap((label % 20) / 20.0)
            color_dict[label] = (c[0], c[1], c[2], 1.0)

    return color_dict


def build_continuous_colormap(
    data_3d: np.ndarray,
    colormap_name: str = "autumn",
    min_thresh: float = 0.0,
    max_thresh: float | None = None,
    two_sided: bool = False,
    num_bins: int = 255,
) -> tuple[np.ndarray, dict[int, tuple[float, float, float, float]], int]:
    """
    Normalize 3D scalar data to uint8 (0..255) and build an RGBA color lookup table.

    :return: (uint8_volume, color_dict, zero_val)
    """
    finite_mask = np.isfinite(data_3d)
    if not np.any(finite_mask):
        uint8_vol = np.zeros(data_3d.shape, dtype=np.uint8)
        return uint8_vol, {0: (0.0, 0.0, 0.0, 0.0)}, 0

    valid_vals = data_3d[finite_mask]
    d_min = float(np.min(valid_vals))
    d_max = float(np.max(valid_vals))

    if math.isclose(d_min, d_max):
        uint8_vol = np.zeros(data_3d.shape, dtype=np.uint8)
        return uint8_vol, {0: (0.0, 0.0, 0.0, 0.0)}, 0

    if max_thresh is None:
        max_thresh = d_max

    # Zero value mapping
    zero_val = int(round(np.clip((0.0 - d_min) / (d_max - d_min) * 255, 0, 255)))

    # Normalize data to 0..255
    norm_data = (data_3d - d_min) / (d_max - d_min)
    norm_data = np.nan_to_num(norm_data, nan=0.0)
    uint8_vol = (np.clip(norm_data, 0.0, 1.0) * 255).astype(np.uint8)

    # Thresholding
    cmap = plt.get_cmap(colormap_name)
    color_dict: dict[int, tuple[float, float, float, float]] = {}

    for val in np.unique(uint8_vol):
        val_int = int(val)
        orig_val = d_min + (val_int / 255.0) * (d_max - d_min)

        is_subthreshold = False
        if two_sided:
            if abs(orig_val) < min_thresh:
                is_subthreshold = True
        else:
            if orig_val < min_thresh or orig_val > max_thresh:
                is_subthreshold = True

        if is_subthreshold or val_int == zero_val or abs(orig_val) < 1e-6:
            color_dict[val_int] = (0.0, 0.0, 0.0, 0.0)
        else:
            rgba = cmap(val_int / 255.0)
            color_dict[val_int] = (float(rgba[0]), float(rgba[1]), float(rgba[2]), 1.0)

    # Ensure zero_val is explicitly transparent
    color_dict[zero_val] = (0.0, 0.0, 0.0, 0.0)
    return uint8_vol, color_dict, zero_val


def map_overlay_to_surface(
    polydata: vtkPolyData,
    overlay_3d: np.ndarray,
    color_dict: dict[int, tuple[float, float, float, float]],
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
    base_color: tuple[int, int, int] = (180, 180, 180),
) -> vtkUnsignedCharArray:
    """
    Project 3D functional overlay onto a surface polydata's vertices.
    Assigns RGBA point scalar colors.
    """
    num_points = polydata.GetNumberOfPoints()
    dz, dy, dx = overlay_3d.shape
    sx, sy, sz = spacing

    rgba_array = np.zeros((num_points, 4), dtype=np.uint8)
    rgba_array[:, :3] = base_color
    rgba_array[:, 3] = 255

    for i in range(num_points):
        x, y, z = polydata.GetPoint(i)
        # Convert physical coordinates to voxel indices
        vx = int(round(x / sx))
        vy = int(round(y / sy))
        vz = int(round(z / sz))

        if 0 <= vz < dz and 0 <= vy < dy and 0 <= vx < dx:
            val = int(overlay_3d[vz, vy, vx])
            if val in color_dict:
                r, g, b, a = color_dict[val]
                if a > 0.05:
                    rgba_array[i, 0] = int(round(r * 255))
                    rgba_array[i, 1] = int(round(g * 255))
                    rgba_array[i, 2] = int(round(b * 255))
                    rgba_array[i, 3] = 255

    vtk_colors = numpy_support.numpy_to_vtk(rgba_array, deep=True, array_type=vtkUnsignedCharArray().GetDataType())
    vtk_colors.SetName("FunctionalOverlayColors")
    vtk_colors.SetNumberOfComponents(4)
    return vtk_colors


class FMRIOverlayManager:
    """
    Central state manager for fMRI data, modalities, timeframe selection,
    and functional connectivity calculation.
    """

    def __init__(self):
        self.raw_data: np.ndarray | None = None
        self.is_4d: bool = False
        self.num_timeframes: int = 1
        self.current_timeframe: int = 0
        self.modality: str = MODALITY_PARCELLATION
        self.colormap: str = "Yeo Standard"
        self.min_threshold: float = 0.0
        self.max_threshold: float | None = None
        self.two_sided: bool = False
        self.seed_coord: tuple[int, int, int] = (0, 0, 0)
        self.active_networks: set[int] = set(range(1, 8))
        self.cluster_volume: np.ndarray | None = None
        self.color_dict: dict[int, tuple[float, float, float, float]] = {}
        self.zero_val: int = 0
        self.is_visible: bool = True
        self.opacity: float = 0.85
        self.filename: str = ""

    def load_file(self, filepath: str, target_shape: tuple[int, int, int] | None = None) -> bool:
        """
        Load a NIfTI file (3D or 4D).
        """
        img = nb.squeeze_image(nb.load(filepath))
        img = nb.as_closest_canonical(img)
        img.update_header()
        data = img.get_fdata().copy()

        # Handle NIfTI orientation to InVesalius (Z, Y, X)
        if data.ndim == 3:
            data = data.T[:, ::-1].copy()
            self.is_4d = False
            self.num_timeframes = 1
        elif data.ndim == 4:
            # 4D: (X, Y, Z, T) -> (Z, Y, X, T)
            data = np.transpose(data, (2, 1, 0, 3))[:, ::-1, :, :].copy()
            self.is_4d = True
            self.num_timeframes = data.shape[-1]
            self.current_timeframe = 0
        else:
            raise ValueError(f"Unsupported NIfTI dimension: {data.ndim}")

        if target_shape is not None:
            is_cat = self.modality == MODALITY_PARCELLATION
            data = resample_volume(data, target_shape, is_categorical=is_cat)

        self.raw_data = data
        self.filename = filepath

        # Auto-detect modality if possible
        if self.is_4d:
            self.modality = MODALITY_BETA_BOLD
        else:
            u_vals = np.unique(data)
            if len(u_vals) <= 20 and np.all(np.equal(np.mod(u_vals, 1), 0)):
                self.modality = MODALITY_PARCELLATION
            else:
                self.modality = MODALITY_GRADIENT

        self.update_overlay(target_shape)
        return True

    def set_modality(self, modality: str, target_shape: tuple[int, int, int] | None = None) -> None:
        self.modality = modality
        if modality == MODALITY_PARCELLATION:
            self.colormap = "Yeo Standard"
        elif modality == MODALITY_BETA_BOLD:
            self.colormap = "hot" if not self.two_sided else "coolwarm"
        elif modality == MODALITY_GRADIENT:
            self.colormap = "viridis"
        elif modality == MODALITY_SEED_FC:
            self.colormap = "hot"

        self.update_overlay(target_shape)

    def set_timeframe(self, t: int, target_shape: tuple[int, int, int] | None = None) -> None:
        if self.is_4d and self.raw_data is not None:
            self.current_timeframe = max(0, min(self.num_timeframes - 1, t))
            self.update_overlay(target_shape)

    def set_threshold(self, min_thresh: float, max_thresh: float | None = None) -> None:
        self.min_threshold = min_thresh
        self.max_threshold = max_thresh
        self.update_overlay()

    def set_seed_coord(self, z: int, y: int, x: int, target_shape: tuple[int, int, int] | None = None) -> None:
        self.seed_coord = (z, y, x)
        if self.modality == MODALITY_SEED_FC:
            self.update_overlay(target_shape)

    def set_colormap(self, cmap_name: str) -> None:
        self.colormap = cmap_name
        self.update_overlay()

    def toggle_network(self, network_id: int, enabled: bool) -> None:
        if enabled:
            self.active_networks.add(network_id)
        else:
            self.active_networks.discard(network_id)
        self.update_overlay()

    def generate_demo_data(self, modality: str, target_shape: tuple[int, int, int]) -> None:
        """
        Generate built-in synthetic modality datasets for testing or demo without external files.
        """
        self.modality = modality
        if modality == MODALITY_PARCELLATION:
            self.raw_data = generate_synthetic_yeo_parcellation(target_shape)
            self.is_4d = False
            self.num_timeframes = 1
            self.colormap = "Yeo Standard"
            self.active_networks = set(range(1, 8))
        elif modality == MODALITY_BETA_BOLD:
            self.raw_data = generate_synthetic_4d_bold(target_shape, num_frames=30)
            self.is_4d = True
            self.num_timeframes = 30
            self.current_timeframe = 0
            self.colormap = "hot"
        elif modality == MODALITY_GRADIENT:
            self.raw_data = generate_synthetic_gradient(target_shape)
            self.is_4d = False
            self.num_timeframes = 1
            self.colormap = "viridis"
        elif modality == MODALITY_SEED_FC:
            self.raw_data = generate_synthetic_4d_bold(target_shape, num_frames=30)
            self.is_4d = True
            self.num_timeframes = 30
            self.seed_coord = (target_shape[0] // 2, target_shape[1] // 2, target_shape[2] // 4)
            self.colormap = "hot"

        self.update_overlay(target_shape)

    def update_overlay(self, target_shape: tuple[int, int, int] | None = None) -> None:
        """
        Recalculate cluster_volume, color_dict, and zero_val according to the current modality and state.
        """
        if self.raw_data is None:
            return

        data = self.raw_data
        if target_shape is not None and data.shape[:3] != target_shape:
            is_cat = self.modality == MODALITY_PARCELLATION
            data = resample_volume(data, target_shape, is_categorical=is_cat)
            self.raw_data = data

        if self.modality == MODALITY_PARCELLATION:
            # Categorical network labels
            if data.ndim == 4:
                curr_3d = data[..., self.current_timeframe]
            else:
                curr_3d = data

            self.cluster_volume = curr_3d.astype(np.uint8)
            u_labels = np.unique(self.cluster_volume)

            if self.colormap == "Yeo Standard":
                net_dict = YEO_17_NETWORKS if len(u_labels) > 8 else YEO_7_NETWORKS
                self.color_dict = build_categorical_colormap(u_labels, net_dict, self.active_networks)
            else:
                # Matplotlib categorical colormap
                cmap = plt.get_cmap(self.colormap)
                self.color_dict = {0: (0.0, 0.0, 0.0, 0.0)}
                max_u = max(1, int(np.max(u_labels)))
                for lbl in u_labels:
                    lbl = int(lbl)
                    if lbl == 0 or lbl not in self.active_networks:
                        self.color_dict[lbl] = (0.0, 0.0, 0.0, 0.0)
                    else:
                        c = cmap((lbl % max_u) / float(max_u))
                        self.color_dict[lbl] = (float(c[0]), float(c[1]), float(c[2]), 1.0)
            self.zero_val = 0

        elif self.modality == MODALITY_BETA_BOLD:
            if self.is_4d and data.ndim == 4:
                curr_3d = data[..., self.current_timeframe]
            else:
                curr_3d = data

            vol, c_dict, z_val = build_continuous_colormap(
                curr_3d,
                colormap_name=self.colormap,
                min_thresh=self.min_threshold,
                max_thresh=self.max_threshold,
                two_sided=self.two_sided,
            )
            self.cluster_volume = vol
            self.color_dict = c_dict
            self.zero_val = z_val

        elif self.modality == MODALITY_GRADIENT:
            if data.ndim == 4:
                curr_3d = data[..., 0]
            else:
                curr_3d = data

            vol, c_dict, z_val = build_continuous_colormap(
                curr_3d,
                colormap_name=self.colormap,
                min_thresh=self.min_threshold,
                max_thresh=self.max_threshold,
                two_sided=True,
            )
            self.cluster_volume = vol
            self.color_dict = c_dict
            self.zero_val = z_val

        elif self.modality == MODALITY_SEED_FC:
            if not self.is_4d or data.ndim != 4:
                # If only 3D data was loaded, convert to 4D synthetic or show warning
                vol, c_dict, z_val = build_continuous_colormap(
                    data,
                    colormap_name=self.colormap,
                    min_thresh=self.min_threshold,
                )
                self.cluster_volume = vol
                self.color_dict = c_dict
                self.zero_val = z_val
                return

            r_map, thresh_r = compute_seed_correlation(
                data, self.seed_coord, threshold=self.min_threshold
            )
            vol, c_dict, z_val = build_continuous_colormap(
                r_map,
                colormap_name=self.colormap,
                min_thresh=self.min_threshold,
                max_thresh=1.0,
                two_sided=self.two_sided,
            )
            self.cluster_volume = vol
            self.color_dict = c_dict
            self.zero_val = z_val
