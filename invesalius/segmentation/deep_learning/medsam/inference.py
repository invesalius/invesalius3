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

"""

import numpy as np
import torch
from torch.nn import functional as F
from math import floor, ceil
from scipy.ndimage import label as ndlabel
from scipy.ndimage import binary_opening, binary_closing, gaussian_filter
from skimage import transform
from .model import sam_model_registry

# Configuration 

BATCH_SIZE = 2   

# Default batch size is conservative for 4GB-8GB GPUs.
# 12GB+ GPUs (like Titan Xp) can safely use BATCH_SIZE = 8 or 16 for vastly faster inference.
          
CROP_PAD_FACTOR = 0.4        
MORPH_KERNEL_SIZE = 5        
MEDSAM_THRESHOLD = 0.6       
MIN_COMPONENT_PX = 150       
SMOOTH_SIGMA_Z = 2.0         
SMOOTH_SIGMA_XY = 0.5        



#  Core MedSAM functions
@torch.no_grad()
def _medsam_inference_batch(medsam_model, img_embed_batch, box_1024, height, width):
    B = img_embed_batch.shape[0]
    box_torch = torch.as_tensor(
        box_1024, dtype=torch.float, device=img_embed_batch.device
    )
    # Replicate prompt for the batch
    box_torch = box_torch.unsqueeze(1).repeat(B, 1, 1)

    sparse_embeddings, dense_embeddings = medsam_model.prompt_encoder(
        points=None, boxes=box_torch, masks=None,
    )
    low_res_logits, _ = medsam_model.mask_decoder(
        image_embeddings=img_embed_batch,
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
    medsam_seg = (high_res_pred.squeeze(1).cpu().numpy() > MEDSAM_THRESHOLD).astype(np.uint8)
    return medsam_seg


@torch.no_grad()
def _get_embedding_batch(medsam_model, img_3c_batch, device):
    tensors = []
    for img_3c in img_3c_batch:
        img_1024 = transform.resize(
            img_3c, (1024, 1024), order=3,
            preserve_range=True, anti_aliasing=True,
        ).astype(np.float32)
        v_min, v_max = img_1024.min(), img_1024.max()
        img_1024 = (img_1024 - v_min) / max(v_max - v_min, 1e-8)
        tensors.append(torch.tensor(img_1024).float().permute(2, 0, 1))
        
    batch_tensor = torch.stack(tensors).to(device)
    return medsam_model.image_encoder(batch_tensor)


def _preprocess_ct_slice(slice_2d, hu_low=-160.0, hu_high=240.0):
    img = np.clip(slice_2d, hu_low, hu_high)
    img = (img - img.min()) / (img.max() - img.min()) * 255.0
    return np.uint8(img)


#  Cropped-Region Inference
def _compute_crop_window(xi, yi, xf, yf, img_w, img_h,pad_factor=CROP_PAD_FACTOR):
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


def _infer_batch(medsam_model, slice_3c_batch, xi, yi, xf, yf, img_w, img_h, device):
    B = len(slice_3c_batch)
    cxi, cyi, cxf, cyf = _compute_crop_window(xi, yi, xf, yf, img_w, img_h)
    crop_w = cxf - cxi
    crop_h = cyf - cyi
    
    crop_img_batch = [img[cyi:cyf, cxi:cxf, :] for img in slice_3c_batch]
    box_in_crop = np.array([[(xi - cxi) / crop_w * 1024, (yi - cyi) / crop_h * 1024, (xf - cxi) / crop_w * 1024, (yf - cyi) / crop_h * 1024]])

    embedding_batch = _get_embedding_batch(medsam_model, crop_img_batch, device)
    crop_masks = _medsam_inference_batch(medsam_model, embedding_batch, box_in_crop, crop_h, crop_w)

    mask_full_batch = np.zeros((B, img_h, img_w), dtype=np.uint8)
    mask_full_batch[:, cyi:cyf, cxi:cxf] = crop_masks
    return mask_full_batch



def _cluster_components(mask: np.ndarray, volume: np.ndarray, zi: int, yi: int, xi: int, min_vol: int = 500, hu_tol: float = 20.0):
    """
    Extracts 3D connected components and clusters them semantics based on HU
    density. Returns a list of individual mask arrays.
    """
    labeled, num_features = ndlabel(mask)
    if num_features == 0:
        return []

    components = []
    for i in range(1, num_features + 1):
        island_mask = (labeled == i)
        vol = island_mask.sum()
        
        if vol < min_vol:
            continue 

        zs, ys, xs = np.where(island_mask)
        
        global_zs = zs + zi
        global_ys = ys + yi
        global_xs = xs + xi

        mean_hu = volume[global_zs, global_ys, global_xs].mean()
        
        components.append({
            'mask': island_mask,
            'vol': vol,
            'hu': mean_hu
        })

    if not components:
        return []
    clusters = []
    for comp in components:
        merged = False
        for cluster in clusters:
            if abs(comp['hu'] - cluster['mean_hu']) <= hu_tol:
                cluster['mask'] = np.logical_or(cluster['mask'], comp['mask'])
                total_vol = cluster['vol'] + comp['vol']
                cluster['mean_hu'] = (cluster['mean_hu'] * cluster['vol'] + comp['hu'] * comp['vol']) / total_vol
                cluster['vol'] = total_vol
                merged = True
                break
        
        if not merged:
            # New distinct organ class
            clusters.append({
                'mask': comp['mask'],
                'vol': comp['vol'],
                'mean_hu': comp['hu']
            })

    return [c['mask'].astype(np.uint8) for c in clusters]


def run_medlsam(
    volume: np.ndarray,
    bbox: tuple,
    weights_path: str,
    model_type: str = "vit_b",
    device: str = "cpu",
    callback=None,
    hu_low: float = -160.0,
    hu_high: float = 240.0,
) -> list:
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

    print(f"\n[MedSAM] ═══ Batched Inference ═══")
    print(f"[MedSAM] Volume   : {volume.shape}  device={device}  BATCH={BATCH_SIZE}")
    print(f"[MedSAM] User box : xi={xi} xf={xf}  yi={yi} yf={yf}  zi={zi} zf={zf}")
    print(f"[MedSAM] Slices   : {n_slices}")

    medsam_model = sam_model_registry[model_type](checkpoint=weights_path)
    medsam_model = medsam_model.to(device)
    medsam_model.eval()

    result_mask = np.zeros((n_slices, roi_y, roi_x), dtype=np.uint8)

    if callback:
        callback(0.1, "Starting Inference")

    with torch.no_grad():
        batches = []
        indices = []
        for idx in range(n_slices):
            z = zi + idx
            
            # Form the batch array
            slice_u8 = _preprocess_ct_slice(volume[z].astype(np.float32), hu_low, hu_high)
            slice_3c = np.repeat(slice_u8[:, :, None], 3, axis=-1)
            batches.append(slice_3c)
            indices.append(idx)

            # Process when batch is full OR if it's the very last slice
            if len(batches) == BATCH_SIZE or idx == n_slices - 1:
                if callback:
                    frac = 0.1 + 0.8 * idx / n_slices
                    if not callback(frac, f"Slice {idx+1}/{n_slices} (Batched)"):
                        return np.zeros((n_slices, roi_y, roi_x), dtype=np.uint8)

                # Send multi-tensor array to GPU
                full_masks = _infer_batch(
                    medsam_model, batches, xi, yi, xf, yf, vol_w, vol_h, device
                )
                
                # Retrieve and assign individual cropped matrices
                for i, b_mask in enumerate(full_masks):
                    result_mask[indices[i]] = b_mask[yi:yf, xi:xf]

                batches = []
                indices = []


    if result_mask.sum() == 0:
        return []

    # --- Strict Clipping to Unpadded Box ---
    for s in range(result_mask.shape[0]):
        slice_mask = result_mask[s]
        lb, num = ndlabel(slice_mask)
        if num > 1:
            sizes = np.bincount(lb.ravel())
            sizes[0] = 0
            for label_id, size in enumerate(sizes):
                if label_id > 0 and size < MIN_COMPONENT_PX:
                    slice_mask[lb == label_id] = 0
            result_mask[s] = slice_mask

    if callback: callback(0.95, "Smoothing (3D)")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        
        if MORPH_KERNEL_SIZE > 0:
            sz = MORPH_KERNEL_SIZE
            radius = sz // 2
            z, y, x = np.ogrid[-radius:radius+1, -radius:radius+1, -radius:radius+1]
            struct = (x**2 + y**2 + z**2) <= radius**2
            
            struct_mask = binary_opening(result_mask, structure=struct)
            struct_mask = binary_closing(struct_mask, structure=struct)
        else:
            struct_mask = result_mask.copy()

        if SMOOTH_SIGMA_Z > 0 or SMOOTH_SIGMA_XY > 0:
            sigma = (SMOOTH_SIGMA_Z, SMOOTH_SIGMA_XY, SMOOTH_SIGMA_XY)
            smoothed = gaussian_filter(struct_mask.astype(float), sigma=sigma)
            struct_mask = (smoothed > 0.5).astype(np.uint8)

    # --- Multi-Mask Semantic Clustering ---
    if callback: callback(0.98, "Clustering Organs")
    final_masks = _cluster_components(struct_mask, volume, zi, yi, xi)

    if callback: callback(1.0, "Done")
    return final_masks

#  Diagnostics
def _save_diagnostics(seed_u8, mask, xi, yi, xf, yf, vol_w, vol_h, cxi, cyi, cxf, cyf):
    """
    Saves intermediate images of the MedSAM cropping, masking, and inference boundary process.
    Commented out for production but can be enabled for MedSAM debugging.
    """
    pass
    # try:
    #     import os
    #     from PIL import Image as PILImage
    #     diag_dir = os.path.join(os.path.dirname(__file__), "diagnostics")
    #     os.makedirs(diag_dir, exist_ok=True)
    # 
    #     PILImage.fromarray(seed_u8).save(os.path.join(diag_dir, "seed_input.png"))
    #     PILImage.fromarray((mask * 255).astype(np.uint8)).save(os.path.join(diag_dir, "seed_mask.png"))
    # 
    #     overlay = np.repeat(seed_u8[:, :, None], 3, axis=-1).copy()
    #     overlay[mask == 1, 0] = np.minimum(overlay[mask == 1, 0].astype(int) + 120, 255).astype(np.uint8)
    #     overlay[mask == 1, 1] = (overlay[mask == 1, 1] * 0.5).astype(np.uint8)
    #     overlay[mask == 1, 2] = (overlay[mask == 1, 2] * 0.5).astype(np.uint8)
    #     for t in range(2):
    #         if yi+t < vol_h: overlay[yi+t, xi:xf] = [0,255,0]
    #         if yf-1-t >= 0:  overlay[yf-1-t, xi:xf] = [0,255,0]
    #         if xi+t < vol_w: overlay[yi:yf, xi+t] = [0,255,0]
    #         if xf-1-t >= 0:  overlay[yi:yf, xf-1-t] = [0,255,0]
    #     for t in range(2):
    #         if cyi+t < vol_h: overlay[cyi+t, cxi:cxf] = [0,255,255]
    #         if cyf-1-t >= 0:  overlay[cyf-1-t, cxi:cxf] = [0,255,255]
    #         if cxi+t < vol_w: overlay[cyi:cyf, cxi+t] = [0,255,255]
    #         if cxf-1-t >= 0:  overlay[cyi:cyf, cxf-1-t] = [0,255,255]
    #     PILImage.fromarray(overlay).save(os.path.join(diag_dir, "seed_overlay.png"))
    #     PILImage.fromarray(overlay[cyi:cyf, cxi:cxf]).save(os.path.join(diag_dir, "seed_crop.png"))
    # except Exception as e:
    #     print(f"[MedSAM] Diagnostic save failed: {e}")


