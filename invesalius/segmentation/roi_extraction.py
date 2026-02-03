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
    if (xi, xf, yi, yf, zi, zf) != (xi_clip, xf_clip, yi_clip, yf_clip, zi_clip, zf_clip):
        print(f"Debug: ROI clipped from {bbox} to {(xi_clip, xf_clip, yi_clip, yf_clip, zi_clip, zf_clip)}")

    roi = volume[zi_clip : zf_clip + 1, yi_clip : yf_clip + 1, xi_clip : xf_clip + 1]

    if roi.size == 0:
        raise ValueError(f"Empty ROI extracted. Bbox: {bbox}")

    return roi
