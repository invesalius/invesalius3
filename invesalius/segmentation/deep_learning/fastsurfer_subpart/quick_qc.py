# Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# IMPORTS
import logging
from typing import cast

import nibabel as nib
import numpy as np
from skimage.morphology import binary_dilation

LOGGER = logging.getLogger(__name__)

VENT_LABELS = {
    "Left-Lateral-Ventricle": 4,
    "Right-Lateral-Ventricle": 43,
    "Left-choroid-plexus": 31,
    "Right-choroid-plexus": 63,
}
BG_LABEL = 0


def check_volume(asegdkt_segfile: np.ndarray, voxvol: float, thres: float = 0.70) -> bool:
    """
    Check if total volume is bigger or smaller than threshold.

    Parameters
    ----------
    asegdkt_segfile : np.ndarray
        The segmentation file.
    voxvol : float
        The volume of a voxel.
    thres : float, default=0.7
        The threshold for the total volume (Default value = 0.70).

    Returns
    -------
    bool
        Whether or not total volume is bigger or smaller than threshold.
    """
    LOGGER.info("Checking total volume ...")
    mask = asegdkt_segfile > 0
    total_vol = np.sum(mask) * voxvol / 1000000
    LOGGER.info(f"Voxel size in mm3: {voxvol}")
    LOGGER.info(f"Total segmentation volume in liter: {np.round(total_vol, 2)}")
    if total_vol < thres:
        return False

    return True


def get_region_bg_intersection_mask(
    seg_array: np.ndarray, region_labels: dict = VENT_LABELS, bg_label: int = BG_LABEL
) -> np.ndarray:
    """
    Return a mask of the intersection between the voxels of a given region and background voxels.

    This is obtained by dilating the region by 1 voxel and computing the intersection with the
    background mask.

    The region can be defined by passing in the region_labels dict.

    Parameters
    ----------
    seg_array : numpy.ndarray
        Segmentation array.
    region_labels : dict, default=VENT_LABELS
        Dictionary whose values correspond to the desired region's labels (see Note).
    bg_label : int, default=BG_LABEL
        Label id of the background.

    Returns
    -------
    bg_intersect : numpy.ndarray
        Region and background intersection mask array.

    Notes
    -----
    VENT_LABELS is a dictionary containing labels for four regions related to the ventricles:
    "Left-Lateral-Ventricle", "Right-Lateral-Ventricle", "Left-choroid-plexus",
    "Right-choroid-plexus" along with their corresponding integer label values
    (see also FreeSurferColorLUT.txt).
    """
    region_array = seg_array.copy()
    conditions = np.all(
        np.array([(region_array != value) for value in region_labels.values()]), axis=0
    )
    region_array[conditions] = 0
    region_array[region_array != 0] = 1

    bg_array = seg_array.copy()
    bg_array[bg_array != bg_label] = -1.0
    bg_array[bg_array == bg_label] = 1
    bg_array[bg_array != 1] = 0

    region_array_dilated = binary_dilation(region_array)

    bg_intersect = np.bitwise_and(region_array_dilated.astype(int), bg_array.astype(int))

    return bg_intersect


def get_ventricle_bg_intersection_volume(seg_array: np.ndarray, voxvol: float) -> float:
    """
    Return a volume estimate for the intersection of ventricle voxels with background voxels.

    Parameters
    ----------
    seg_array : numpy.ndarray
        Segmentation array.
    voxvol : float
        Voxel volume.

    Returns
    -------
    intersection_volume : float
        Estimated volume of voxels in ventricle and background intersection.
    """
    bg_intersect_mask = get_region_bg_intersection_mask(seg_array)
    intersection_volume = bg_intersect_mask.sum() * voxvol

    return intersection_volume


def run_quick_qc(
    segmentation_data: np.ndarray, voxel_volume: float, volume_threshold: float = 0.70
) -> dict:
    """
    Run all quick quality checks on the segmentation data.

    This function orchestrates all QC checks and returns a comprehensive report.

    Parameters
    ----------
    segmentation_data : np.ndarray
        The segmentation array to check
    voxel_volume : float
        The volume of a single voxel in mm³
    volume_threshold : float, default=0.70
        The threshold for total volume check in liters

    Returns
    -------
    dict
        Dictionary containing QC results with the following keys:
        - 'volume_check_passed': bool - Whether volume check passed
        - 'total_volume_liters': float - Total segmentation volume in liters
        - 'ventricle_bg_intersection_volume_mm3': float - Ventricle-background intersection volume
        - 'overall_passed': bool - Whether all checks passed
    """
    LOGGER.info("Starting quick quality checks...")

    # Run volume check
    volume_check_passed = check_volume(segmentation_data, voxel_volume, volume_threshold)

    # Calculate total volume for reporting
    mask = segmentation_data > 0
    total_volume_liters = np.sum(mask) * voxel_volume / 1000000

    # Run ventricle-background intersection check
    LOGGER.info("Estimating ventricle-background intersection volume...")
    ventricle_bg_intersection_volume = get_ventricle_bg_intersection_volume(
        segmentation_data, voxel_volume
    )
    LOGGER.info(
        f"Ventricle-background intersection volume in mm³: {ventricle_bg_intersection_volume:.2f}"
    )

    # Determine overall QC status
    overall_passed = volume_check_passed

    # Log warnings if checks failed
    if not volume_check_passed:
        LOGGER.warning(
            "Total segmentation volume is very small. Segmentation may be corrupted! Please check."
        )

    results = {
        "volume_check_passed": volume_check_passed,
        "total_volume_liters": total_volume_liters,
        "ventricle_bg_intersection_volume_mm3": ventricle_bg_intersection_volume,
        "overall_passed": overall_passed,
    }

    LOGGER.info(f"Quick QC completed. Overall status: {'PASSED' if overall_passed else 'FAILED'}")
    return results


def run_quick_qc_from_file(segmentation_file: str, volume_threshold: float = 0.70) -> dict:
    """
    Run quick quality checks on a segmentation file.

    Parameters
    ----------
    segmentation_file : str
        Path to the segmentation file (nii.gz, mgz, etc.)
    volume_threshold : float, default=0.70
        The threshold for total volume check in liters

    Returns
    -------
    dict
        QC results dictionary (see run_quick_qc for details)
    """
    LOGGER.info(f"Reading segmentation file: {segmentation_file}")

    # Load the segmentation file
    seg_image = cast(nib.analyze.SpatialImage, nib.load(segmentation_file))
    seg_data = np.asanyarray(seg_image.dataobj)
    seg_header = seg_image.header
    voxel_volume = np.prod(seg_header.get_zooms())

    # Run QC checks
    return run_quick_qc(seg_data, voxel_volume, volume_threshold)
