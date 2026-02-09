import numpy as np
import torch
from torch.nn import functional as F
from copy import deepcopy
from typing import Tuple


class ResizeLongestSide:
    """
    Resizes images to the longest side 'target_length', as well as provides
    methods for resizing coordinates and boxes. Provides methods for
    transforming both numpy array and batched torch tensors.
    """

    def __init__(self, target_length: int) -> None:
        self.target_length = target_length

    def apply_image(self, image: np.ndarray) -> np.ndarray:
        h, w, c = image.shape
        img_tensor = torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0).float()

        target_size = self.get_preprocess_shape(h, w, self.target_length)

        resized_tensor = F.interpolate(
            img_tensor,
            size=target_size,
            mode="bilinear",
            align_corners=False,
            antialias=False,
        )

        resized_img = (
            resized_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy().astype(np.uint8)
        )

        return resized_img

    def apply_coords(
        self, coords: np.ndarray, original_size: Tuple[int, ...]
    ) -> np.ndarray:
        old_h, old_w = original_size
        new_h, new_w = self.get_preprocess_shape(old_h, old_w, self.target_length)
        new_coords = np.empty_like(coords)
        new_coords[..., 0] = coords[..., 0] * (new_w / old_w)
        new_coords[..., 1] = coords[..., 1] * (new_h / old_h)
        return new_coords

    def apply_boxes(
        self, boxes: np.ndarray, original_size: Tuple[int, ...]
    ) -> np.ndarray:
        boxes = self.apply_coords(boxes.reshape(-1, 2, 2), original_size)
        return boxes.reshape(-1, 4)

    def apply_image_torch(self, image: torch.Tensor) -> torch.Tensor:
        target_size = self.get_preprocess_shape(
            image.shape[2], image.shape[3], self.target_length
        )
        return F.interpolate(
            image, target_size, mode="bilinear", align_corners=False, antialias=True
        )

    def apply_coords_torch(
        self, coords: torch.Tensor, original_size: Tuple[int, ...]
    ) -> torch.Tensor:
        old_h, old_w = original_size
        new_h, new_w = self.get_preprocess_shape(
            original_size[0], original_size[1], self.target_length
        )
        coords = deepcopy(coords).to(torch.float)
        coords[..., 0] = coords[..., 0] * (new_w / old_w)
        coords[..., 1] = coords[..., 1] * (new_h / old_h)
        return coords

    def apply_boxes_torch(
        self, boxes: torch.Tensor, original_size: Tuple[int, ...]
    ) -> torch.Tensor:
        boxes = self.apply_coords_torch(boxes.reshape(-1, 2, 2), original_size)
        return boxes.reshape(-1, 4)

    @staticmethod
    def get_preprocess_shape(
        oldh: int, oldw: int, long_side_length: int
    ) -> Tuple[int, int]:
        scale = long_side_length * 1.0 / max(oldh, oldw)
        newh, neww = oldh * scale, oldw * scale
        neww = int(neww + 0.5)
        newh = int(newh + 0.5)
        return (newh, neww)
