"""
MedSAM inference for InVesalius — Cropped-Region + Seed-Guided Consistency.

KEY INSIGHTS from testing:
  1. Cropped-region inference gives PERFECT results on slices where the
     organ IS present (confirmed visually).
  2. On slices where the organ is ABSENT, MedSAM segments whatever is in
     the crop (spine, ribs) → noise in 3D.

SOLUTION: Seed-guided consistency filtering.
  - Run seed slice first (middle of Z range) → get reference mask
  - For each other slice: run inference, then CHECK the result against the seed
  - Reject masks that are too different in area or centroid position
  - This eliminates spine segmentation on slices where the kidney doesn't exist

PIPELINE per slice:
  1. Crop region = box center ± 0.5× box size (tight − excludes spine)
  2. HU → uint8 → 3ch → skimage resize 1024 → normalize
  3. Box in crop's 1024-space → MedSAM inference
  4. Iterative refinement (tight box → re-run)
  5. Consistency check vs seed: area + centroid
  6. Map back, crop to ROI, morphological cleanup, largest 3D CC

CRITICAL: model.preprocess() is NEVER called.
"""

import numpy as np
import torch
from torch.nn import functional as F
from scipy.ndimage import label as ndlabel
from scipy.ndimage import binary_opening, binary_closing, gaussian_filter
from skimage import transform

from .model import sam_model_registry

# Configuration 
CROP_PAD_FACTOR = 0.4         # reduced from 0.5 to make the crop window tighter (less noise)
REFINE_PAD_PX = 10
N_REFINE_ITERS = 1
MORPH_KERNEL_SIZE = 5         # increased from 3 for stronger denoising
MEDSAM_THRESHOLD = 0.6        # increased from 0.5 for more conservative masks
MIN_COMPONENT_PX = 150        # increased from 100 — remove isolated CCs smaller than this
SMOOTH_SIGMA = 1.0            # 3D Gaussian sigma for inter-slice smoothing

# Seed-guided consistency thresholds
MAX_AREA_RATIO = 2.5      
MIN_AREA_RATIO = 0.1      
MAX_CENTROID_DRIFT = 0.5  


#  Core MedSAM functions
@torch.no_grad()
def _medsam_inference(medsam_model, img_embed, box_1024, height, width):
    box_torch = torch.as_tensor(
        box_1024, dtype=torch.float, device=img_embed.device
    )
    if len(box_torch.shape) == 2:
        box_torch = box_torch[:, None, :]

    sparse_embeddings, dense_embeddings = medsam_model.prompt_encoder(
        points=None, boxes=box_torch, masks=None,
    )
    low_res_logits, _ = medsam_model.mask_decoder(
        image_embeddings=img_embed,
        image_pe=medsam_model.prompt_encoder.get_dense_pe(),
        sparse_prompt_embeddings=sparse_embeddings,
        dense_prompt_embeddings=dense_embeddings,
        multimask_output=False,
    )
    low_res_pred = torch.sigmoid(low_res_logits)
    high_res_pred = F.interpolate(
        low_res_pred, size=(height, width),
        mode="bilinear", align_corners=False,
    )
    medsam_seg = (high_res_pred.squeeze().cpu().numpy() > MEDSAM_THRESHOLD).astype(np.uint8)
    return medsam_seg


@torch.no_grad()
def _get_embedding(medsam_model, img_3c, device):
    img_1024 = transform.resize(
        img_3c, (1024, 1024), order=3,
        preserve_range=True, anti_aliasing=True,
    ).astype(np.uint8)
    img_1024 = (img_1024 - img_1024.min()) / np.clip(
        img_1024.max() - img_1024.min(), a_min=1e-8, a_max=None
    )
    img_1024_tensor = (
        torch.tensor(img_1024).float().permute(2, 0, 1).unsqueeze(0).to(device)
    )
    return medsam_model.image_encoder(img_1024_tensor)


def _preprocess_ct_slice(slice_2d, hu_low=-160.0, hu_high=240.0):
    img = np.clip(slice_2d, hu_low, hu_high)
    img = (img - img.min()) / (img.max() - img.min()) * 255.0
    return np.uint8(img)


#  Cropped-Region Inference
def _compute_crop_window(xi, yi, xf, yf, img_w, img_h,
                          pad_factor=CROP_PAD_FACTOR):
    box_w = xf - xi
    box_h = yf - yi
    cx = (xi + xf) / 2.0
    cy = (yi + yf) / 2.0
    half_w = box_w * (0.5 + pad_factor)
    half_h = box_h * (0.5 + pad_factor)
    crop_xi = int(max(0, cx - half_w))
    crop_yi = int(max(0, cy - half_h))
    crop_xf = int(min(img_w, cx + half_w))
    crop_yf = int(min(img_h, cy + half_h))
    return crop_xi, crop_yi, crop_xf, crop_yf


def _infer_on_crop(medsam_model, slice_3c, xi, yi, xf, yf,
                    img_w, img_h, device):
    """Run MedSAM on a cropped region around the box."""
    cxi, cyi, cxf, cyf = _compute_crop_window(xi, yi, xf, yf, img_w, img_h)
    crop_w = cxf - cxi
    crop_h = cyf - cyi
    crop_img = slice_3c[cyi:cyf, cxi:cxf, :]

    # Box in crop's 1024 coordinate space
    box_in_crop = np.array([[
        (xi - cxi) / crop_w * 1024,
        (yi - cyi) / crop_h * 1024,
        (xf - cxi) / crop_w * 1024,
        (yf - cyi) / crop_h * 1024,
    ]])

    embedding = _get_embedding(medsam_model, crop_img, device)
    crop_mask = _medsam_inference(medsam_model, embedding, box_in_crop,
                                  crop_h, crop_w)

    # Map back to full-image coordinates
    mask_full = np.zeros((img_h, img_w), dtype=np.uint8)
    mask_full[cyi:cyf, cxi:cxf] = crop_mask
    return mask_full


def _iterative_refine(medsam_model, slice_3c, xi, yi, xf, yf,
                       img_w, img_h, device, n_iters=N_REFINE_ITERS):
    """Initial inference + refinement passes with tighter boxes."""
    cur_xi, cur_yi, cur_xf, cur_yf = xi, yi, xf, yf
    mask_full = None

    for it in range(1 + n_iters):
        mask_full = _infer_on_crop(
            medsam_model, slice_3c, cur_xi, cur_yi, cur_xf, cur_yf,
            img_w, img_h, device
        )
        if it < n_iters:
            ys, xs = np.where(mask_full > 0)
            if len(ys) == 0:
                break
            cur_xi = max(0, int(xs.min()) - REFINE_PAD_PX)
            cur_xf = min(img_w, int(xs.max()) + 1 + REFINE_PAD_PX)
            cur_yi = max(0, int(ys.min()) - REFINE_PAD_PX)
            cur_yf = min(img_h, int(ys.max()) + 1 + REFINE_PAD_PX)

    return mask_full


def _mask_stats(mask_roi):
    """Compute area and centroid of a 2D mask (ROI-space)."""
    area = int(mask_roi.sum())
    if area == 0:
        return 0, 0.0, 0.0
    ys, xs = np.where(mask_roi > 0)
    cy = float(ys.mean())
    cx = float(xs.mean())
    return area, cy, cx


def _is_consistent(mask_roi, seed_area, seed_cy, seed_cx,
                     roi_h, roi_w):
    """
    Check if a slice's mask is consistent with the seed mask.
    Rejects masks that are spine/ribs on slices without the organ.
    """
    area, cy, cx = _mask_stats(mask_roi)

    if area == 0:
        return True  # empty is fine

    # Area check: reject if too large or too small vs seed
    if seed_area > 0:
        ratio = area / seed_area
        if ratio > MAX_AREA_RATIO or ratio < MIN_AREA_RATIO:
            return False

    # Centroid drift check: reject if centroid moved too far
    max_drift_y = roi_h * MAX_CENTROID_DRIFT
    max_drift_x = roi_w * MAX_CENTROID_DRIFT

    if abs(cy - seed_cy) > max_drift_y or abs(cx - seed_cx) > max_drift_x:
        return False

    return True


def run_medlsam(
    volume: np.ndarray,
    bbox: tuple,
    weights_path: str,
    model_type: str = "vit_b",
    device: str = "cpu",
    callback=None,
    hu_low: float = -160.0,
    hu_high: float = 240.0,
) -> np.ndarray:
    """
    MedSAM 3D segmentation with cropped-region inference + seed consistency.

    Strategy:
      1. Seed from middle slice → reference area + centroid
      2. Process all slices with cropped-region inference
      3. Reject slices inconsistent with seed (wrong structure)
      4. Morphological cleanup + largest 3D CC
    """
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    xi, xf, yi, yf, zi, zf = map(int, bbox[:6])
    vol_z, vol_h, vol_w = volume.shape

    xi = max(0, min(xi, vol_w - 1))
    xf = max(xi + 1, min(xf, vol_w))
    yi = max(0, min(yi, vol_h - 1))
    yf = max(yi + 1, min(yf, vol_h))
    zi = max(0, min(zi, vol_z - 1))
    zf = max(zi, min(zf, vol_z - 1))
    n_slices = zf - zi + 1
    roi_y = yf - yi
    roi_x = xf - xi

    cxi, cyi, cxf, cyf = _compute_crop_window(xi, yi, xf, yf, vol_w, vol_h)
    box_area_pct = roi_x * roi_y / ((cxf-cxi) * (cyf-cyi)) * 100

    print(f"\n[MedSAM] ═══ Cropped-Region + Seed Consistency ═══")
    print(f"[MedSAM] Volume   : {volume.shape}  device={device}")
    print(f"[MedSAM] User box : xi={xi} xf={xf}  yi={yi} yf={yf}  zi={zi} zf={zf}")
    print(f"[MedSAM] Crop     : ({cxi},{cyi})-({cxf},{cyf})  "
          f"= {cxf-cxi}×{cyf-cyi}  box={box_area_pct:.0f}% of crop")
    print(f"[MedSAM] Slices   : {n_slices}")

    medsam_model = sam_model_registry[model_type](checkpoint=weights_path)
    medsam_model = medsam_model.to(device)
    medsam_model.eval()

    result_mask = np.zeros((n_slices, roi_y, roi_x), dtype=np.uint8)

    # ═══ PHASE 1: SEED from middle slice ═══
    mid_idx = n_slices // 2
    mid_z = zi + mid_idx
    print(f"\n[MedSAM] SEED z={mid_z}")

    with torch.no_grad():
        seed_u8 = _preprocess_ct_slice(volume[mid_z].astype(np.float32),
                                        hu_low, hu_high)
        seed_3c = np.repeat(seed_u8[:, :, None], 3, axis=-1)
        seed_full = _iterative_refine(
            medsam_model, seed_3c, xi, yi, xf, yf, vol_w, vol_h, device
        )

    seed_roi = seed_full[yi:yf, xi:xf]
    result_mask[mid_idx] = seed_roi
    seed_area, seed_cy, seed_cx = _mask_stats(seed_roi)
    print(f"[MedSAM] Seed: area={seed_area}  centroid=({seed_cx:.1f},{seed_cy:.1f})")

    _save_diagnostics(seed_u8, seed_full, xi, yi, xf, yf, vol_w, vol_h,
                      cxi, cyi, cxf, cyf)

    if callback:
        callback(0.1, "Seed done")

    # ═══ PHASE 2: Process all other slices ═══
    rejected = 0
    with torch.no_grad():
        for idx in range(n_slices):
            if idx == mid_idx:
                continue  # already done

            z = zi + idx
            if callback:
                frac = 0.1 + 0.8 * idx / n_slices
                if not callback(frac, f"Slice {idx+1}/{n_slices}"):
                    return np.zeros((n_slices, roi_y, roi_x), dtype=np.uint8)

            slice_u8 = _preprocess_ct_slice(volume[z].astype(np.float32),
                                             hu_low, hu_high)
            slice_3c = np.repeat(slice_u8[:, :, None], 3, axis=-1)

            full_mask = _iterative_refine(
                medsam_model, slice_3c, xi, yi, xf, yf,
                vol_w, vol_h, device
            )
            mask_roi = full_mask[yi:yf, xi:xf]

            # Consistency check against seed
            if _is_consistent(mask_roi, seed_area, seed_cy, seed_cx,
                               roi_y, roi_x):
                result_mask[idx] = mask_roi
            else:
                # Reject this slice — wrong structure
                result_mask[idx] = 0
                rejected += 1

            if idx % 5 == 0:
                area = int(mask_roi.sum())
                status = "✓" if result_mask[idx].sum() > 0 else "✗"
                print(f"  z={z:3d}  area={area:>5}  {status}")

    print(f"\n[MedSAM] Processed: {n_slices} slices, rejected {rejected}")

    if callback:
        callback(0.92, "Post-processing")

    total = int(result_mask.sum())
    print(f"[MedSAM] Raw: {total} voxels")

    # --- Per-slice small-component removal ---
    if total > 0:
        for s in range(result_mask.shape[0]):
            sl = result_mask[s]
            if sl.sum() == 0:
                continue
            labeled_2d, n_2d = ndlabel(sl)
            for lbl in range(1, n_2d + 1):
                if (labeled_2d == lbl).sum() < MIN_COMPONENT_PX:
                    sl[labeled_2d == lbl] = 0
            result_mask[s] = sl
        print(f"[MedSAM] After per-slice CC filter: {result_mask.sum()} voxels")

    # --- Morphological cleanup (2D per-slice) ---
    if result_mask.sum() > 0:
        struct = np.ones((1, MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), dtype=bool)
        result_mask = binary_opening(result_mask, structure=struct).astype(np.uint8)
        result_mask = binary_closing(result_mask, structure=struct).astype(np.uint8)
        print(f"[MedSAM] After morphology: {result_mask.sum()} voxels")

    # --- 3D Gaussian smoothing → re-threshold ---
    # Smooths jagged inter-slice transitions (the "shelf" noise)
    if result_mask.sum() > 0:
        smoothed = gaussian_filter(result_mask.astype(np.float32), sigma=SMOOTH_SIGMA)
        result_mask = (smoothed > 0.5).astype(np.uint8)
        print(f"[MedSAM] After 3D smoothing: {result_mask.sum()} voxels")

    # --- Largest 3D connected component ---
    if result_mask.sum() > 0:
        result_mask = _keep_largest_component(result_mask)

    return result_mask


#  Diagnostics

def _save_diagnostics(seed_u8, mask, xi, yi, xf, yf, vol_w, vol_h,
                      cxi, cyi, cxf, cyf):
    try:
        import os
        from PIL import Image as PILImage
        diag_dir = os.path.join(os.path.dirname(__file__), "diagnostics")
        os.makedirs(diag_dir, exist_ok=True)

        PILImage.fromarray(seed_u8).save(os.path.join(diag_dir, "seed_input.png"))
        PILImage.fromarray((mask * 255).astype(np.uint8)).save(
            os.path.join(diag_dir, "seed_mask.png"))

        overlay = np.repeat(seed_u8[:, :, None], 3, axis=-1).copy()
        overlay[mask == 1, 0] = np.minimum(
            overlay[mask == 1, 0].astype(int) + 120, 255).astype(np.uint8)
        overlay[mask == 1, 1] = (overlay[mask == 1, 1] * 0.5).astype(np.uint8)
        overlay[mask == 1, 2] = (overlay[mask == 1, 2] * 0.5).astype(np.uint8)
        for t in range(2):
            if yi+t < vol_h: overlay[yi+t, xi:xf] = [0,255,0]
            if yf-1-t >= 0:  overlay[yf-1-t, xi:xf] = [0,255,0]
            if xi+t < vol_w: overlay[yi:yf, xi+t] = [0,255,0]
            if xf-1-t >= 0:  overlay[yi:yf, xf-1-t] = [0,255,0]
        # Cyan = crop window
        for t in range(2):
            if cyi+t < vol_h: overlay[cyi+t, cxi:cxf] = [0,255,255]
            if cyf-1-t >= 0:  overlay[cyf-1-t, cxi:cxf] = [0,255,255]
            if cxi+t < vol_w: overlay[cyi:cyf, cxi+t] = [0,255,255]
            if cxf-1-t >= 0:  overlay[cyi:cyf, cxf-1-t] = [0,255,255]
        PILImage.fromarray(overlay).save(os.path.join(diag_dir, "seed_overlay.png"))
        PILImage.fromarray(overlay[cyi:cyf, cxi:cxf]).save(
            os.path.join(diag_dir, "seed_crop.png"))
        print(f"[MedSAM] Diagnostics → {diag_dir}")
    except Exception as e:
        print(f"[MedSAM] Diagnostic save failed: {e}")


#  Post-processing
def _keep_largest_component(mask):
    labeled, n = ndlabel(mask)
    if n == 0:
        return mask
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0
    best = int(sizes.argmax())
    result = (labeled == best).astype(np.uint8)
    return result
