# -*- coding: utf-8 -*-
# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------

import numpy as np

def extract_roi(volume, bbox):
    """
    Extract a voxel-aligned ROI from the full volume.

    Args:
        volume (np.ndarray): Full image volume (Z, Y, X).
        bbox (tuple): (xmin, xmax, ymin, ymax, zmin, zmax).

    Returns:
        np.ndarray: Extracted sub-volume.
    """
    if volume is None or not isinstance(volume, np.ndarray):
        raise ValueError("Invalid volume input.")

    if len(bbox) != 6:
        raise ValueError("Bounding box must have 6 elements.")

    xi, xf, yi, yf, zi, zf = map(int, bbox)

    if xi > xf or yi > yf or zi > zf:
        raise ValueError(f"Invalid bounding box: {bbox}")

    if volume.ndim != 3:
        raise ValueError(f"Volume must be 3D. Shape: {volume.shape}")

    d, h, w = volume.shape

    # Clip values to volume boundaries
    zi_clip, zf_clip = max(0, min(zi, d - 1)), max(0, min(zf, d - 1))
    yi_clip, yf_clip = max(0, min(yi, h - 1)), max(0, min(yf, h - 1))
    xi_clip, xf_clip = max(0, min(xi, w - 1)), max(0, min(xf, w - 1))

    # Check for clipping
    # if (xi, xf, yi, yf, zi, zf) != (xi_clip, xf_clip, yi_clip, yf_clip, zi_clip, zf_clip):
    #     pass

    roi = volume[zi_clip : zf_clip + 1, yi_clip : yf_clip + 1, xi_clip : xf_clip + 1]

    if roi.size == 0:
        raise ValueError(f"Empty ROI extracted. Bbox: {bbox}")

    return roi


def extract_roi_padded(volume, bbox, pad_fraction=0.15, min_pad=5):
    """
    Extract a padded ROI from the volume.

    Expands the user's bounding box by pad_fraction (default 15%) on each axis,
    with a hard minimum of min_pad voxels, clamped to volume boundaries.
    Returns the padded sub-volume AND the effective padded bbox so the caller
    can place the resulting mask at the correct position in the full volume.

    Args:
        volume       (np.ndarray): Full 3D volume (Z, Y, X).
        bbox         (tuple)     : (xmin, xmax, ymin, ymax, zmin, zmax).
        pad_fraction (float)     : Fraction of each axis extent added per side.
        min_pad      (int)       : Minimum padding in voxels per side.

    Returns:
        roi         (np.ndarray): Padded sub-volume.
        padded_bbox (tuple)     : (xi_p, xf_p, yi_p, yf_p, zi_p, zf_p).
    """
    if volume is None or not isinstance(volume, np.ndarray):
        raise ValueError("Invalid volume input.")
    if len(bbox) != 6:
        raise ValueError("Bounding box must have 6 elements.")
    if volume.ndim != 3:
        raise ValueError(f"Volume must be 3D. Shape: {volume.shape}")

    xi, xf, yi, yf, zi, zf = map(int, bbox)
    d, h, w = volume.shape

    pad_x = max(min_pad, round(pad_fraction * max(1, xf - xi)))
    pad_y = max(min_pad, round(pad_fraction * max(1, yf - yi)))
    pad_z = max(min_pad, round(pad_fraction * max(1, zf - zi)))

    xi_p = max(0, xi - pad_x)
    xf_p = min(w - 1, xf + pad_x)
    yi_p = max(0, yi - pad_y)
    yf_p = min(h - 1, yf + pad_y)
    zi_p = max(0, zi - pad_z)
    zf_p = min(d - 1, zf + pad_z)

    roi = volume[zi_p : zf_p + 1, yi_p : yf_p + 1, xi_p : xf_p + 1]

    if roi.size == 0:
        raise ValueError(
            f"Empty padded ROI. Original: {bbox}, padded: "
            f"({xi_p},{xf_p},{yi_p},{yf_p},{zi_p},{zf_p})"
        )

    padded_bbox = (xi_p, xf_p, yi_p, yf_p, zi_p, zf_p)
    print(
        f"[ROI] original=({xi},{xf},{yi},{yf},{zi},{zf})  "
        f"padded=({xi_p},{xf_p},{yi_p},{yf_p},{zi_p},{zf_p})  "
        f"shape={roi.shape}"
    )
    return roi, padded_bbox
