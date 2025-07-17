import logging
from typing import Dict, Optional

import nibabel as nib
import numpy as np

from .inference import PytorchInference, TinyGradInference
from .utils import Conformer, PreparePlaneView, Validator, apply_label_mapping

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates the entire segmentation process, combining the individual components (validation,
    input preparation, inference, and post-processing) into a single pipeline.
    """

    def __init__(self, num_channels: int = 7, base_resolution: float = 0.7):
        """
        Initializes the pipeline with its core components

        Args:
            num_channels: Number of channels for plane preparation
            base_resolution: Base resolution for scale factor calculation
            model_paths: Dictionary mapping plane names to model file paths
        """
        self.validator = Validator()
        self.conformer = Conformer()
        self.preparer = PreparePlaneView(num_channels=num_channels)
        self.base_resolution = base_resolution
        self.planes = ["axial", "coronal", "sagittal"]

    def run_pipeline(
        self,
        input_img_path: str,
        backend: str = "tinygrad",
        use_gpu: bool = False,
        device_id: str = "cpu",
        model_paths: Optional[Dict[str, str]] = None,
    ) -> np.ndarray:
        """
        Executes the full pipeline from input image to final segmentation

        Returns final segmentation as numpy array
        """
        if not model_paths:
            raise ValueError(
                "Model paths must be provided either in constructor or run_pipeline call"
            )

        prepared_data = self.prepare_input(input_img_path)
        final_segmentation = self.run_inference(
            prepared_data, backend, use_gpu, device_id, model_paths
        )
        final_segmentation = apply_label_mapping(final_segmentation)
        return final_segmentation

    def run_inference(
        self,
        prepared_data: Dict[str, Dict[str, np.ndarray]],
        backend: str,
        use_gpu: bool,
        device_id: str,
        model_paths: Dict[str, str],
    ) -> np.ndarray:
        """Runs inference for the required backend"""
        logger.info(f"Using GPU: {use_gpu}, Device: {device_id}")

        try:
            if backend == "tinygrad":
                engine = TinyGradInference(
                    model_paths=model_paths,
                    backend=backend,
                    use_gpu=use_gpu,
                    device_id=device_id,
                    logger=logger,
                )
            elif backend == "pytorch":
                engine = PytorchInference(
                    model_paths=model_paths,
                    backend=backend,
                    use_gpu=use_gpu,
                    device_id=device_id,
                    logger=logger,
                )
            else:
                raise ValueError("Invalid backend")

            print("Running multi-view inference...")
            final_segmentation = engine.run_multi_view_inference(prepared_data)

            print(f"output shape: {final_segmentation.shape}, dtype: {final_segmentation.dtype}")
            return final_segmentation

        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise

    def prepare_input(self, input_img_path: str) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Runs the full data preparation pipeline on an input image

        This method performs validation, conforming, and plane-wise data
        preparation, returning a dictionary of data ready for inference
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

            plane_view_data = self.preparer.transform_planewise(conformed_data, plane)

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
