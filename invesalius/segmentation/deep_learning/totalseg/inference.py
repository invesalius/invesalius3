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

import logging
import os
from collections.abc import Callable

import numpy as np
from scipy.ndimage import gaussian_filter

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False


from .preprocess import (
    output_to_input_layout,
    postprocess,
    preprocess,
)

logger = logging.getLogger(__name__)


def load_model(
    model_path: str, backend: str, use_gpu: bool = False, device_id: str = "cpu"
) -> dict:
    if backend == "onnx":
        if not ONNX_AVAILABLE:
            raise ImportError(
                "ONNX Runtime is not installed. Please install onnxruntime to use the onnx backend."
            )

        try:
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)

            providers = (
                [("CUDAExecutionProvider", {}), "CPUExecutionProvider"]
                if use_gpu
                else ["CPUExecutionProvider"]
            )
            session = ort.InferenceSession(model_path, sess_options, providers=providers)

            return {
                "type": "onnx",
                "session": session,
                "input_name": session.get_inputs()[0].name,
                "output_name": session.get_outputs()[0].name,
            }
        except Exception as e:
            logger.error(f"Failed to load ONNX model from {model_path}: {e}")
            raise

    elif backend == "jit":
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is not installed. Please install torch to use the jit backend."
            )

        try:
            device = torch.device(device_id if use_gpu and torch.cuda.is_available() else "cpu")
            model = torch.jit.load(model_path, map_location=device)
            model.eval()
            model = model.to(device)
            logger.info(f"Loaded JIT model from {model_path} on {device}")

            return {
                "type": "jit",
                "model": model,
                "device": device,
            }
        except Exception as e:
            logger.error(f"Failed to load JIT model from {model_path}: {e}")
            raise

    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'jit' or 'onnx'.")


def infer_num_classes(handle: dict, patch_size: tuple[int, ...]) -> int:
    dummy = np.zeros((1, 1, *patch_size), dtype=np.float32)
    if handle["type"] == "jit":
        with torch.no_grad():
            out = handle["model"](torch.from_numpy(dummy))
            if isinstance(out, list | tuple):
                out = out[0]
            return int(out.shape[1])
    out = handle["session"].run(None, {handle["input_name"]: dummy})[0]
    return int(out.shape[1])


def compute_steps(
    image_size: tuple[int, ...],
    patch_size: tuple[int, ...],
    step_size: float = 0.5,
) -> list[list[int]]:
    # Port of nnUNetv2's _compute_steps_for_sliding_window. Patch starts are
    # evenly distributed across [0, image - patch] so the final patch always
    # lands at image - patch and covers the far edge cleanly.
    target = [p * step_size for p in patch_size]
    num_steps = [int(np.ceil((i - p) / t)) + 1 for i, p, t in zip(image_size, patch_size, target)]

    steps: list[list[int]] = []
    for d in range(len(patch_size)):
        max_value = image_size[d] - patch_size[d]
        if num_steps[d] > 1:
            actual = max_value / (num_steps[d] - 1)
        else:
            actual = 1e12
        steps.append([int(np.round(actual * i)) for i in range(num_steps[d])])
    return steps


def compute_gaussian(
    patch_size: tuple[int, ...],
    sigma_scale: float = 1.0 / 8,
) -> np.ndarray:
    # Zeros are floored to the smallest non-zero to prevent divide-by-zero
    # in the weighted accumulator at the very corners of the patch.
    tmp = np.zeros(patch_size, dtype=np.float32)
    center = tuple(s // 2 for s in patch_size)
    sigmas = [s * sigma_scale for s in patch_size]
    tmp[center] = 1
    g = gaussian_filter(tmp, sigmas, 0, mode="constant", cval=0)
    g = g / g.max()
    zero_mask = g == 0
    if zero_mask.any():
        g[zero_mask] = g[~zero_mask].min()
    return g.astype(np.float32)


def pad_to_min_patch(
    volume: np.ndarray,
    patch_size: tuple[int, ...],
    pad_value: float = 0.0,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    # pad_value=0 is the post-z-score neutral (= dataset mean). Matches what
    # nnU-Net does internally.
    target = [max(s, p) for s, p in zip(volume.shape, patch_size)]
    pad_widths = []
    for src, dst in zip(volume.shape, target):
        diff = dst - src
        before = diff // 2
        pad_widths.append((before, diff - before))
    padded = np.pad(volume, pad_widths, mode="constant", constant_values=pad_value)
    return padded, pad_widths


def _run_patch(handle: dict, patch: np.ndarray) -> np.ndarray:
    x = patch[np.newaxis, np.newaxis].astype(np.float32)
    if handle["type"] == "jit":
        with torch.no_grad():
            out = handle["model"](torch.from_numpy(x).to(handle["device"]))
            if isinstance(out, list | tuple):
                out = out[0]
            return out.cpu().numpy()[0]
    out = handle["session"].run(None, {handle["input_name"]: x})[0]
    return out[0]


def sliding_window_inference(
    volume: np.ndarray,
    handle: dict,
    patch_size: tuple[int, ...],
    num_classes: int,
    step_size: float = 0.5,
    progress_callback: Callable[[float], None] | None = None,
) -> np.ndarray:
    padded, pad_widths = pad_to_min_patch(volume, patch_size, pad_value=0.0)
    steps = compute_steps(padded.shape, patch_size, step_size)
    gaussian = compute_gaussian(patch_size)

    accum = np.zeros((num_classes, *padded.shape), dtype=np.float32)
    weight = np.zeros(padded.shape, dtype=np.float32)

    n_total = len(steps[0]) * len(steps[1]) * len(steps[2])
    logger.info(
        f"Sliding window: padded={padded.shape}, patches={n_total}, "
        f"per-axis steps={[len(s) for s in steps]}"
    )

    idx = 0
    for z0 in steps[0]:
        for y0 in steps[1]:
            for x0 in steps[2]:
                z1 = z0 + patch_size[0]
                y1 = y0 + patch_size[1]
                x1 = x0 + patch_size[2]
                patch = padded[z0:z1, y0:y1, x0:x1]

                logits = _run_patch(handle, patch)
                accum[:, z0:z1, y0:y1, x0:x1] += logits * gaussian
                weight[z0:z1, y0:y1, x0:x1] += gaussian

                idx += 1
                if progress_callback is not None:
                    progress_callback(idx / n_total)

    weight = np.maximum(weight, 1e-8)
    accum /= weight[np.newaxis]
    labels = accum.argmax(axis=0).astype(np.uint8)

    (z_b, _), (y_b, _), (x_b, _) = pad_widths
    z_e = z_b + volume.shape[0]
    y_e = y_b + volume.shape[1]
    x_e = x_b + volume.shape[2]
    return labels[z_b:z_e, y_b:y_e, x_b:x_e]


def run(
    volume: np.ndarray,
    spacing,
    sidecar: dict,
    handle: dict,
    modality: str | None = None,
    step_size: float = 0.5,
    progress_callback: Callable[[float], None] | None = None,
    output_layout: str = "input",
) -> np.ndarray:
    if modality is None:
        modality = sidecar.get("modality", "CT").lower()

    plans = {
        "patch_size": sidecar["patch_size"],
        "target_spacing": sidecar["target_spacing"],
        "normalization": sidecar["normalization"]["scheme"],
    }
    if modality == "ct":
        plans["clip_low"] = sidecar["normalization"]["clip_low"]
        plans["clip_high"] = sidecar["normalization"]["clip_high"]
        plans["mean"] = sidecar["normalization"]["mean"]
        plans["std"] = sidecar["normalization"]["std"]

    spacing = np.asarray(spacing, dtype=np.float32)
    preprocessed, meta = preprocess(volume, spacing, plans, modality=modality)

    patch_size = tuple(plans["patch_size"])
    num_classes = infer_num_classes(handle, patch_size)
    pred = sliding_window_inference(
        preprocessed,
        handle,
        patch_size,
        num_classes,
        step_size=step_size,
        progress_callback=progress_callback,
    )

    # postprocess returns ZYX (the layout the network ran in). "input" assumes
    # the caller fed XYZ via load_nifti/load_volume_from_array, so transpose
    # back. Callers already in ZYX (InVesalius wrapper) pass "zyx" to skip.
    pred_zyx = postprocess(pred, meta)
    if output_layout == "zyx":
        return pred_zyx
    return output_to_input_layout(pred_zyx)
