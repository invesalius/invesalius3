import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import onnxruntime as ort
import torch

from .utils import apply_sagittal_mapping

logger = logging.getLogger(__name__)


def load_model(model_path: str, backend: str, use_gpu: bool = False, device_id: str = "cpu"):
    """
    Load a model based on the specified backend"""

    if backend == "tinygrad":
        try:
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if use_gpu
                else ["CPUExecutionProvider"]
            )
            session = ort.InferenceSession(model_path, providers=providers)

            model_info = {
                "type": "onnx",
                "session": session,
                "input_name": session.get_inputs()[0].name,
                "output_name": session.get_outputs()[0].name,
                "input_shape": session.get_inputs()[0].shape,
                "output_shape": session.get_outputs()[0].shape,
            }
            return model_info

        except ImportError as e:
            print(f"Failed to import required libraries for tinygrad backend: {e}")
            raise
        except Exception as e:
            print(f"Failed to load tinygrad model from {model_path}: {e}")
            raise
    elif backend == "pytorch":
        try:
            device = torch.device(device_id if use_gpu and torch.cuda.is_available() else "cpu")
            model = torch.load(model_path, map_location=device)

            model_info = {"type": "pytorch", "model": model, "device": device}
            return model_info

        except ImportError as e:
            print(f"Failed to import PyTorch: {e}")
            raise
        except Exception as e:
            print(f"Failed to load PyTorch model from {model_path}: {e}")
            raise
    else:
        raise ValueError(f"Unknown backend: {backend}")


class TinyGradInference:
    """
    ONNX inference class containing multi-view inference and view aggregation logic.
    """

    def __init__(
        self,
        model_paths: Dict[str, str],
        use_gpu: bool = False,
        device_id: str = "cpu",
        logger=None,
    ):
        self.model_paths = model_paths
        self.use_gpu = use_gpu
        self.device_id = device_id
        self.logger = logger or logging.getLogger(__name__)

        self.permute_order = {
            "axial": (3, 0, 2, 1),
            "coronal": (2, 3, 0, 1),
            "sagittal": (0, 3, 2, 1),
        }

        self.alpha = {"axial": 0.4, "coronal": 0.4, "sagittal": 0.2}

        self.models = {}
        self.num_classes = None

        self.get_num_classes()

    def get_num_classes(self):
        """Load model and get num_classes"""
        for plane, model_path in self.model_paths.items():
            print(f"Loading {plane} model")

            try:
                model_info = load_model(model_path, "tinygrad", self.use_gpu, self.device_id)
                self.models[plane] = model_info

                if self.num_classes is None:
                    output_shape = model_info["output_shape"]  # [batch, classes, height, width]
                    self.num_classes = output_shape[1] if len(output_shape) > 1 else 95

            except Exception as e:
                self.logger.error(f"Failed to load {plane} model: {e}")
                raise

    def _view_agg(
        self, batch_pred: np.ndarray, alpha: float, target_slices: tuple, out: np.ndarray
    ) -> np.ndarray:
        try:
            out[target_slices] = out[target_slices] + (alpha * batch_pred)
        except ValueError as e:
            self.logger.warning(f"out[{target_slices}].shape = {out[target_slices].shape}")
            self.logger.warning(f"batch_pred.shape = {batch_pred.shape}")
            out_slice = out[target_slices]
            min_shape = tuple(
                min(out_slice.shape[i], batch_pred.shape[i]) for i in range(len(batch_pred.shape))
            )
            compatible_slice = tuple(slice(0, s) for s in min_shape)
            out[target_slices][compatible_slice] = out[target_slices][compatible_slice] + (
                alpha * batch_pred[compatible_slice]
            )

        return out

    def _predict_batch(self, plane: str, batch_data: np.ndarray, scale_factor: float) -> np.ndarray:
        """
        Predict a single batch for a plane"""
        model_info = self.models[plane]

        session = model_info["session"]
        input_name = model_info["input_name"]
        output_name = model_info["output_name"]

        batch_input = batch_data.astype(np.float32)
        outputs = session.run([output_name], {input_name: batch_input})
        return outputs[0]

    def _predict_single_plane(
        self,
        init_pred: np.ndarray,
        plane: str,
        thick_slices: np.ndarray,
        scale_factor: float,
        out: np.ndarray,
    ) -> np.ndarray:
        """
        Run prediction for a single plane.

        Returns Prediction logits for the plane
        """
        start_idx = 0
        index_of_current_plane = self.permute_order[plane].index(0)
        target_shape = init_pred.shape
        ii = [slice(None) for _ in range(4)]
        pred_ii = tuple(slice(i) for i in target_shape[:3])

        alpha = self.alpha.get(plane, 0.4)

        batch_size = 8
        num_slices = thick_slices.shape[0]

        for start_idx in range(0, num_slices, batch_size):
            end_idx = min(start_idx + batch_size, num_slices)
            batch_data = thick_slices[start_idx:end_idx]
            actual_batch_size = batch_data.shape[0]

            batch_pred = self._predict_batch(plane, batch_data, scale_factor)

            if plane == "sagittal":
                batch_pred = apply_sagittal_mapping(batch_pred)

            batch_pred = np.transpose(batch_pred, self.permute_order[plane])

            batch_pred = batch_pred.astype(np.float16)

            batch_pred = batch_pred[pred_ii]

            end_idx = start_idx + actual_batch_size

            ii[index_of_current_plane] = slice(start_idx, end_idx)
            target_slices = tuple(ii)

            out = self._view_agg(batch_pred, alpha, target_slices, out)

            start_idx = end_idx

        print(f"Completed aggregation for {plane} plane with alpha={alpha}")
        return out

    def run_multi_view_inference(self, prepared_data: Dict[str, Dict[str, Any]]) -> np.ndarray:
        """
        Run the complete multi-view inference pipeline.

        Returns final segmentation as numpy array
        """

        first_plane_data = next(iter(prepared_data.values()))
        thick_slices = first_plane_data["thick_slices"]

        # shape --> [height, width, depth, num_classes] - same as orig_in_lia.shape + (num_classes,)
        h, w, d = thick_slices.shape[2], thick_slices.shape[3], thick_slices.shape[0]
        output_shape = (h, w, d, self.num_classes)

        print(f"thick_slices.shape = {thick_slices.shape}")
        print(f"Final output_shape = {output_shape}")

        pred_prob = np.zeros(
            output_shape, dtype=np.float16
        )  # float16 for memory efficiency and exact compatibility

        print(f"initialized prediction tensor with shape: {output_shape}, dtype: {pred_prob.dtype}")

        for plane, data in prepared_data.items():
            if plane not in self.models:
                self.logger.warning(f"No model found for plane {plane}, skipping")
                continue

            print(f"Running {plane} prediction")
            thick_slices = data["thick_slices"]
            scale_factor = data.get("scale_factor", 1.0)

            pred_prob = self._predict_single_plane(
                init_pred=pred_prob,
                plane=plane,
                thick_slices=thick_slices,
                scale_factor=scale_factor,
                out=pred_prob,
            )

        pred_classes = np.argmax(pred_prob, axis=3)

        return pred_classes


class PytorchInference:
    """
    Contains Pytorch inference logic - plane by plane inference and view aggregation"""

    def __init__(
        self,
        model_paths: Dict[str, str],
        use_gpu: bool = False,
        device_id: str = "cpu",
        logger=None,
    ):
        self.model_paths = model_paths
        self.use_gpu = use_gpu
        self.device_id = device_id
        self.logger = logger or logging.getLogger(__name__)

        self.permute_order = {
            "axial": (3, 0, 2, 1),
            "coronal": (2, 3, 0, 1),
            "sagittal": (0, 3, 2, 1),
        }

        self.alpha = {"axial": 0.4, "coronal": 0.4, "sagittal": 0.2}

        self.models = {}
        self.num_classes = None

        self.get_num_classes()

    def get_num_classes(self):
        """Load model and get num_classes"""
        for plane, model_path in self.model_paths.items():
            print(f"Loading {plane} model")

            try:
                model_info = load_model(model_path, "pytorch", self.use_gpu, self.device_id)
                self.models[plane] = model_info

                if self.num_classes is None:
                    ...
                    # self.num_classes = 79

            except Exception as e:
                self.logger.error(f"Failed to load {plane} model: {e}")
                raise

    def _predict_batch(self, plane: str, batch_data: np.ndarray, scale_factor: float) -> np.ndarray:
        model_info = self.models[plane]
        model = model_info["model"]
        device = model_info["device"]

        # with torch.no_grad():
        #     batch_input = torch.from_numpy(batch_data).float().to(device)
        #     # scale_tensor = torch.tensor([scale_factor] * batch_data.shape[0], device=device)
        #     # batch_pred = model(batch_input, scale_tensor)
        #     batch_pred = model(batch_input)
        #     return batch_pred.cpu().numpy()

    def _predict_Single_plane(): ...

    def run_multi_view_inference():
        print("WIP")
