import logging
from typing import Dict

import nibabel as nib
import numpy as np

from .utils import Conformer, PreparePlaneView, Validator

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates the entire segmentation process, combining the individual components (validation, conforming,
    preparation, inference, and post-processing) into a single, executable pipeline.
    """

    def __init__(self, num_channels: int = 7, base_resolution: float = 0.7):
        """
        Initializes the pipeline with its core components.
        """
        self.validator = Validator()
        self.conformer = Conformer()
        self.preparer = PreparePlaneView(num_channels=num_channels)
        self.base_resolution = base_resolution
        self.planes = ["axial", "coronal", "sagittal"]

    def prepare_input(self, input_img_path: str) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Runs the full data preparation pipeline on an input image.

        This method performs validation, conforming, and plane-wise data
        preparation, returning a dictionary of data ready for inference.
        """
        # load and validate image
        logger.info(f"Loading image from: {input_img_path}")
        img = nib.load(input_img_path)

        is_valid, issues = self.validator.validate(img)
        if not is_valid:
            raise ValueError(f"Input image failed validation: {', '.join(issues)}")
        # logger.info("Input image passed validation.")

        # conform image
        logger.info("Conforming image...")
        conformed_img = self.conformer.conform(img)
        conformed_data = np.asarray(conformed_img.dataobj)
        original_zoom = img.header.get_zooms()

        # prepare data for each plane
        all_plane_data = {}

        for plane in self.planes:
            logger.info(f"Processing {plane} plane...")

            plane_view_data = self.preparer.get_plane_view_data(conformed_data, plane)

            thick_slices = self.preparer.get_thick_slices(plane_view_data)

            scale_factor = self.preparer.get_scale_factor(
                original_zoom, plane, self.base_resolution
            )

            all_plane_data[plane] = {
                "thick_slices": thick_slices,
                "scale_factor": scale_factor,
            }
            logger.info(
                f"-> {plane.capitalize()} data shape: {thick_slices.shape}, "
                f"Scale Factor: {np.round(scale_factor, 3)}"
            )

        logger.info("All planes prepared for inference")
        return all_plane_data

    def run_pipeline(self, input_img_path: str) -> np.ndarray:
        """
        Executes the full pipeline from input image to final segmentation.
        """
        prepared_data = self.prepare_input(input_img_path)
        final_segmentation = self.run_inference(prepared_data)
        return final_segmentation
