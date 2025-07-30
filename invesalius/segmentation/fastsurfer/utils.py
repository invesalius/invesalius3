import logging
from typing import Literal, Optional, Tuple, Union

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class Validator:
    """Validates images against FastSurfer's basic input requirements"""

    @staticmethod
    def validate(img: nib.analyze.SpatialImage) -> Tuple[bool, list[str]]:
        issues = []
        img_shape = img.shape

        if img.ndim != 3:
            issues.append(f"Image must be 3D, but has {img.ndim} dimensions.")

        if not np.issubdtype(img.get_data_dtype(), np.number):
            issues.append(f"Non-numeric data type found: {img.get_data_dtype()}.")

        return len(issues) == 0, issues


class Conformer:
    """Handles image conforming to models' standard format"""

    def __init__(
        self,
        vox_size: Union[float, Literal["min"]] = 1.0,
        img_size: Union[int, Literal["auto"]] = 256,
        orientation: str = "LIA",
        dtype: type = np.uint8,
        rescale: bool = True,
        order: int = 1,
    ):
        self.vox_size = vox_size
        self.img_size = img_size
        self.orientation = orientation
        self.dtype = dtype
        self.rescale = rescale
        self.order = order
        # self.vox_eps = 1e-4  #voxel size tolerance
        # self.rot_eps = 1e-6  #rotation tolerance

    def conform(self, img: nib.analyze.SpatialImage) -> nib.analyze.SpatialImage:
        logger.info("Conforming image to FastSurfer standard format...")

        # reorient image to target orientation first
        target_ornt = nib.orientations.axcodes2ornt(self.orientation)
        reoriented_img = img.as_reoriented(target_ornt)

        target_vox_size, target_shape = self._get_target_dimensions(reoriented_img)

        target_affine = self._get_target_affine(target_vox_size, target_shape)

        resampled_data = self._resample_image(reoriented_img, target_affine, target_shape)

        if self.rescale:
            resampled_data = self._rescale_intensities(img, resampled_data)

        # cast to final data type
        if np.issubdtype(self.dtype, np.integer):
            resampled_data = np.rint(resampled_data)
        final_data = resampled_data.astype(self.dtype)

        conformed_img = nib.MGHImage(final_data, target_affine)
        logger.info(
            f"Conforming finished. New shape: {conformed_img.shape}, "
            f"New dtype: {conformed_img.get_data_dtype()}"
        )
        return conformed_img

    def _get_target_dimensions(
        self, img: nib.analyze.SpatialImage
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Calculates the target voxel size and image shape"""
        source_voxels = np.array(img.header.get_zooms()[:3])
        source_shape = np.array(img.shape[:3])

        if self.vox_size == "min":
            target_vox_size = np.full(3, source_voxels.min())
        else:
            target_vox_size = np.full(3, float(self.vox_size))

        if self.img_size == "auto":
            fov = source_shape * source_voxels  # fov: field of view
            target_dim = max(256, int(np.ceil(fov.max() / target_vox_size[0])))
            target_shape = np.full(3, target_dim)
        else:
            target_shape = np.full(3, int(self.img_size))

        return target_vox_size, target_shape

    def _get_target_affine(
        self,
        target_vox_size: np.ndarray,
        target_shape: np.ndarray,
    ) -> np.ndarray:
        """Creates a canonical LIA affine matrix"""
        # target_affine = np.array(
        #     [
        #         [-1 * target_vox_size[0], 0, 0, 0],  # L
        #         [0, 0, 1 * target_vox_size[2], 0],  # I
        #         [0, -1 * target_vox_size[1], 0, 0], # A
        #         [0, 0, 0, 1],
        #     ]
        # )
        dir_x = np.array([-target_vox_size[0], 0, 0])  # voxel x-axis -> Left (negative x)
        dir_y = np.array([0, 0, -target_vox_size[1]])  # voxel y-axis -> Inferior (negative z)
        dir_z = np.array([0, target_vox_size[2], 0])  # voxel z-axis -> Anterior (positive y)

        scale_matrix = np.column_stack((dir_x, dir_y, dir_z))
        target_affine = np.eye(4)
        target_affine[:3, :3] = scale_matrix

        # center the image
        translation = (target_shape * target_vox_size) / 2.0
        target_affine[:3, 3] = translation
        return target_affine

    def _resample_image(
        self,
        img: nib.analyze.SpatialImage,
        target_affine: np.ndarray,
        target_shape: np.ndarray,
    ) -> np.ndarray:
        """Resamples image data into the target space using the calculated affines"""
        from scipy.ndimage import affine_transform

        vox_to_vox_transform = (
            np.linalg.inv(img.affine) @ target_affine
        )  # matrix multiplication for mapping target voxels to source voxels
        inv_transform = np.linalg.inv(vox_to_vox_transform)

        source_data = np.asarray(img.dataobj, dtype=np.float32)

        resampled_data = affine_transform(
            source_data,
            inv_transform,
            output_shape=target_shape,
            order=self.order,
            mode="constant",
            cval=0.0,
        )
        return resampled_data

    def _rescale_intensities(
        self, img: nib.analyze.SpatialImage, resampled_data: np.ndarray
    ) -> np.ndarray:
        """Applies intensity clipping (0-255)"""
        source_data = np.asarray(img.dataobj)
        dst_min, dst_max = 0, 255

        # Finding the max and min intensity between 0.1% and 99.9%
        hist, bin_edges = np.histogram(source_data.flatten(), bins=1000)
        cumulative_histogram = np.cumsum(hist)
        total_voxels = source_data.size

        min_idx = np.searchsorted(cumulative_histogram, total_voxels * 0.001)
        src_min = bin_edges[min_idx]

        max_idx = np.searchsorted(cumulative_histogram, total_voxels * 0.999)
        src_max = bin_edges[max_idx]

        if src_min >= src_max:
            logger.warning("Image intensity range is zero or invalid. Scaling may fail.")
            scale = 1.0
        else:
            scale = (dst_max - dst_min) / (src_max - src_min)

        logger.info(
            f"Intensity scaling: "
            f"input range=[{src_min:.2f}, {src_max:.2f}], "
            f"output scale={scale:.4f}"
        )

        # apply the scaling and clipping
        background_mask = np.isclose(resampled_data, 0)
        scaled_data = dst_min + scale * (resampled_data - src_min)
        scaled_data = np.clip(scaled_data, dst_min, dst_max)
        scaled_data[background_mask] = 0

        return scaled_data


class PreparePlaneView:
    """Prepares image data for planewise inference"""

    def __init__(self, num_channels: int = 7):
        if num_channels % 2 == 0:
            raise ValueError("Number of channels must be odd.")
        self.num_channels = num_channels
        self.slice_thickness = num_channels // 2

    def transform_planewise(self, conformed_data: np.ndarray, plane: str) -> np.ndarray:
        """Transposes the data array to match the model's expected plane view"""
        if plane == "sagittal":
            return np.transpose(conformed_data, (2, 0, 1))  # (X, Y, Z) -> (Z, Y, X)
        elif plane == "axial":
            return np.transpose(conformed_data, (1, 2, 0))  # (X, Y, Z) -> (Y, Z, X)
        # since coronal is the default, no transpose needed
        return conformed_data

    def get_thick_slices(self, plane_view_data: np.ndarray) -> np.ndarray:
        """Creates thick slices of 7 from the plane-specific view data"""
        num_slices = plane_view_data.shape[2]
        # pad the array to ensure enough slices are available at the edge cases
        padded_data = np.pad(
            plane_view_data,
            ((0, 0), (0, 0), (self.slice_thickness, self.slice_thickness)),
            mode="edge",
        )

        thick_slices = np.stack(
            [padded_data[:, :, i : i + self.num_channels] for i in range(num_slices)],
            axis=0,
        )
        return np.transpose(thick_slices, (0, 2, 1, 3))

    def get_scale_factor(
        self,
        original_zoom: Tuple[float, float, float],
        plane: str,
        base_resolution: float = 0.7,
    ) -> np.ndarray:
        """Gets the scaling factor for a specific plane-view"""
        zoom_array = np.asarray(original_zoom)
        x_zoom, y_zoom, z_zoom = zoom_array[0], zoom_array[1], zoom_array[2]

        if plane == "axial":
            plane_zoom = np.array([x_zoom, y_zoom])
        elif plane == "coronal":
            plane_zoom = np.array([x_zoom, z_zoom])
        else:  # "sagittal"
            plane_zoom = np.array([y_zoom, z_zoom])

        return base_resolution / plane_zoom


def apply_sagittal_mapping(self, prediction: np.ndarray) -> np.ndarray:
    """Apply sagittal mapping"""
    sagittal_num_classes = prediction.shape[1]

    r = range
    _idx = []

    if sagittal_num_classes == 96:
        _idx = [[0], r(5, 14), r(1, 4), [14, 15, 4], r(16, 19), r(5, 51), r(20, 51)]
    elif sagittal_num_classes == 51:
        _idx = [[0], r(5, 14), r(1, 4), [14, 15, 4], r(16, 19), r(5, 51)]
        _idx.extend([[20, 22, 27], r(29, 32), [33, 34], r(38, 43), [45]])
    elif sagittal_num_classes == 21:
        _idx = [[0], r(5, 15), r(1, 4), [15, 16, 4], r(17, 20), r(5, 21)]
    else:
        self.logger.warning(f"No predefined sagittal mapping for {sagittal_num_classes} classes")
        if sagittal_num_classes <= self.num_classes:
            idx_list = list(range(sagittal_num_classes))
            mapped_prediction = prediction[:, idx_list, :, :]
            return mapped_prediction
        else:
            idx_list = list(range(self.num_classes))
            mapped_prediction = prediction[:, idx_list, :, :]
            return mapped_prediction
