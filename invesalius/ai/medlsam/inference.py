import numpy as np
import torch
import torch.nn.functional as F
from .model import sam_model_registry
from .utils import ResizeLongestSide


def run_medlsam(
    roi_volume: np.ndarray,
    weights_path: str,
    model_type: str = "vit_b",
    device: str = "cpu",
    callback=None,
) -> np.ndarray:
    """
    Runs MedLSAM segmentation on a 3D ROI volume.

    Args:
        roi_volume (np.ndarray): 3D volume (Z, Y, X)
        weights_path (str): Path to model checkpoint
        model_type (str): 'vit_b', 'vit_l', or 'vit_h'
        device (str): 'cuda' or 'cpu'
        callback (callable, optional): Function to call with progress (0.0 to 1.0)

    Returns:
        np.ndarray: 3D binary mask (Z, Y, X) of type uint8 (0 or 1)
    """

    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    print(f"Loading MedLSAM model ({model_type}) from {weights_path} to {device}...")
    try:
        sam_model = sam_model_registry[model_type](checkpoint=weights_path)
        sam_model.to(device)
        sam_model.eval()
    except Exception as e:
        raise RuntimeError(f"Failed to load MedLSAM model: {e}")

    # Prepare transform
    sam_trans = ResizeLongestSide(sam_model.image_encoder.img_size)

    # Initialize output mask
    z_dim, y_dim, x_dim = roi_volume.shape
    segmentation_mask = np.zeros_like(roi_volume, dtype=np.uint8)

    print("Running inference on slices...")
    print(f"MedLSAM Inference Device: {device.upper()}")

    # Process each slice
    # TODO: Batch processing could optimize this for GPU
    with torch.no_grad():
        for z in range(z_dim):
            # Report progress
            if callback:
                if not callback(z / z_dim, f"Slice {z+1}/{z_dim}"):
                    print("Inference cancelled by user.")
                    return np.zeros_like(roi_volume, dtype=np.uint8)

            # Get 2D slice
            img_slice = roi_volume[z, :, :]

            # MedSAM expects 3-channel RGB 0-255 uint8 images
            # Normalize to 0-255 range and stack to 3 channels
            img_min = img_slice.min()
            img_max = img_slice.max()
            if img_max > img_min:
                img_normalized = (
                    (img_slice - img_min) / (img_max - img_min) * 255.0
                ).astype(np.uint8)
            else:
                img_normalized = np.zeros_like(img_slice, dtype=np.uint8)

            # Stack to 3 channels
            img_rgb = np.stack((img_normalized,) * 3, axis=-1)
            box_np = np.array([0, 0, x_dim, y_dim])

            # Run prediction
            mask_2d = _predict_slice(img_rgb, box_np, sam_trans, sam_model, device)

            segmentation_mask[z, :, :] = mask_2d

    return segmentation_mask


def _predict_slice(
    img_np: np.ndarray,
    box_np: np.ndarray,
    sam_trans: ResizeLongestSide,
    sam_model: torch.nn.Module,
    device: str,
) -> np.ndarray:
    """
    Internal function to predict a single random slice.
    """
    H, W = img_np.shape[:2]

    # Resize image
    resize_img = sam_trans.apply_image(img_np)
    resize_img_tensor = (
        torch.as_tensor(resize_img.transpose(2, 0, 1)).float().to(device)
    )

    # Preprocess (normalize/pad)
    input_image = sam_model.preprocess(
        resize_img_tensor[None, :, :, :]
    )  # (1, 3, 1024, 1024)
    image_embedding = sam_model.image_encoder(input_image)

    # Box Prompt Processing
    box = sam_trans.apply_boxes(box_np, (H, W))
    box_torch = torch.as_tensor(box, dtype=torch.float, device=device)
    if len(box_torch.shape) == 1:
        box_torch = box_torch[None, :]  # (1, 4)
    if len(box_torch.shape) == 2:
        box_torch = box_torch[:, None, :]  # (B, 1, 4)

    # Prompt Encoder
    sparse_embeddings, dense_embeddings = sam_model.prompt_encoder(
        points=None,
        boxes=box_torch,
        masks=None,
    )

    # Mask Decoder
    low_res_masks, iou_predictions = sam_model.mask_decoder(
        image_embeddings=image_embedding,
        image_pe=sam_model.prompt_encoder.get_dense_pe(),
        sparse_prompt_embeddings=sparse_embeddings,
        dense_prompt_embeddings=dense_embeddings,
        multimask_output=False,
    )

    # Upscale mask to original size
    # Using torch interpolate to resize back to original HxW
    masks = F.interpolate(
        low_res_masks,
        (sam_model.image_encoder.img_size, sam_model.image_encoder.img_size),
        mode="bilinear",
        align_corners=False,
    )

    input_h, input_w = resize_img.shape[:2]
    masks = masks[..., :input_h, :input_w]

    masks = F.interpolate(masks, (H, W), mode="bilinear", align_corners=False)
    masks = torch.sigmoid(masks)
    mask_np = (masks > 0.5).cpu().numpy().squeeze().astype(np.uint8)

    return mask_np
