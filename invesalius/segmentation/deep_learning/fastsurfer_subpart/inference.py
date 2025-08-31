# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------

import logging
import os
import threading
import time
from typing import Optional

import numpy as np
from numpy import typing as npt
from pandas import DataFrame
from torch.utils.data import DataLoader

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


from .data_process import (
    ProcessDataThickSlices,
    ToTensorTest,
    apply_sagittal_mapping,
)
from .misc import Config


class Compose:
    def __init__(self, transforms_list):
        self.transforms = transforms_list

    def __call__(self, img):
        for transform in self.transforms:
            img = transform(img)
        return img


logger = logging.getLogger(__name__)


def load_model(model_path: str, backend: str, use_gpu: bool = False, device_id: str = "cpu"):
    """
    Load a model based on the specified backend
    """
    if backend == "tinygrad":
        if not ONNX_AVAILABLE:
            raise ImportError(
                "ONNX Runtime is not installed. Please install onnxruntime to use the tinygrad backend."
            )

        try:
            # Set up session options
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.enable_mem_pattern = True
            sess_options.enable_cpu_mem_arena = True
            sess_options.intra_op_num_threads = os.cpu_count() // 2
            sess_options.inter_op_num_threads = 2

            provider_options = {}
            if use_gpu:
                sess_options.enable_mem_reuse = True
                sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                provider_options["gpu_mem_limit"] = 3.2 * 1024 * 1024 * 1024  # ~3.2GB limit

            providers = (
                [("CUDAExecutionProvider", provider_options), "CPUExecutionProvider"]
                if use_gpu
                else ["CPUExecutionProvider"]
            )

            session = ort.InferenceSession(model_path, sess_options, providers=providers)

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
            logger.error(f"Failed to import required libraries for tinygrad backend: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load tinygrad model from {model_path}: {e}")
            raise

    elif backend == "pytorch":
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is not installed. Please install torch to use the pytorch backend."
            )

        try:
            logger.info(f"load_model: use_gpu={use_gpu}, device_id={device_id}")
            logger.info(f"load_model: torch.cuda.is_available()={torch.cuda.is_available()}")

            device = torch.device(device_id if use_gpu and torch.cuda.is_available() else "cpu")
            logger.info(f"load_model: determined device={device}")

            # Load TorchScript model (.pt file)
            model = torch.jit.load(model_path, map_location=device)
            is_torchscript = True

            # Ensure model is in evaluation mode
            if model is not None:
                model.eval()
                # Move model to specified device
                model = model.to(device)
                logger.info(f"Model loaded successfully from {model_path}")

            model_info = {
                "type": "pytorch",
                "model": model,
                "device": device,
                "is_torchscript": is_torchscript,
                "model_path": model_path,
            }
            return model_info

        except Exception as e:
            logger.error(f"Failed to load PyTorch model from {model_path}: {e}")
            raise
    else:
        raise ValueError(f"Unknown backend: {backend}")


class TinyGradInference:
    """
    ONNX inference class
    """

    def __init__(
        self,
        cfg: Config,
        device: torch.device | str | None = None,
        ckpt: str = "",
        lut: str | np.ndarray | DataFrame | None = None,
        parallel_batches: int = 2,
        use_gpu: bool = False,
    ):
        self.cfg = cfg
        self.device = device
        self.lut = lut

        # Set random seed from configs
        np.random.seed(cfg.RNG_SEED)

        self.parallel_batches = max(1, parallel_batches)

        # GPU detection for ONNX - don't rely on PyTorch
        if use_gpu or (
            device is not None
            and (
                (hasattr(device, "type") and device.type == "cuda")
                or (isinstance(device, str) and "cuda" in device.lower())
            )
        ):
            print("*" * 100)
            # Check if CUDA is available for ONNX Runtime
            available_providers = ort.get_available_providers() if ONNX_AVAILABLE else []
            self.use_gpu = "CUDAExecutionProvider" in available_providers
            if not self.use_gpu:
                logger.warning(
                    "CUDA requested but CUDAExecutionProvider not available in ONNX Runtime"
                )
            self.device_id = "cuda:0" if self.use_gpu else "cpu"
        else:
            self.use_gpu = False
            self.device_id = "cpu"

        logger.info(f"TinyGradInference: use_gpu={self.use_gpu}, device_id={self.device_id}")
        logger.info(
            f"Available ONNX providers: {ort.get_available_providers() if ONNX_AVAILABLE else 'ONNX not available'}"
        )

        self.permute_order = {
            "axial": (3, 0, 2, 1),
            "coronal": (2, 3, 0, 1),
            "sagittal": (0, 3, 2, 1),
        }

        self.alpha = {"sagittal": 0.2}
        self.model_info = None
        self._thread_local = threading.local()

        # Load checkpoint if provided
        if ckpt:
            self.load_checkpoint(ckpt)

    def load_checkpoint(self, ckpt: str):
        """Load ONNX model"""
        logger.info(f"Loading ONNX model {ckpt}")

        try:
            self.model_info = load_model(ckpt, "tinygrad", self.use_gpu, self.device_id)
            logger.info("ONNX model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load ONNX model: {e}")
            raise

    def predict_batch(self, batch_data: np.ndarray) -> np.ndarray:
        """Predict a batch using ONNX"""
        session = self.model_info["session"]
        input_name = self.model_info["input_name"]
        output_name = self.model_info["output_name"]

        batch_input = batch_data.astype(np.float32)
        thread_id = threading.current_thread().ident
        logger.debug(
            f"Running ONNX inference for batch shape: {batch_input.shape} [Thread: {thread_id}]"
        )

        try:
            outputs = session.run([output_name], {input_name: batch_input})
            logger.debug(
                f"ONNX inference completed, output shape: {outputs[0].shape} [Thread: {thread_id}]"
            )
            return outputs[0]
        except Exception as e:
            if "OUT_OF_MEMORY" in str(e) or "CUDNN_STATUS_INTERNAL_ERROR" in str(e):
                logger.warning(f"GPU memory error, trying with smaller batch size: {e}")
                if batch_data.shape[0] > 1:
                    results = []
                    for i in range(batch_data.shape[0]):
                        single_batch = batch_data[i : i + 1]
                        single_input = single_batch.astype(np.float32)
                        single_output = session.run([output_name], {input_name: single_input})
                        results.append(single_output[0])
                    return np.concatenate(results, axis=0)
                else:
                    raise e
            else:
                raise e

    def eval(self, init_pred, val_loader, *, out_scale: Optional = None, out: Optional = None):
        """
        Perform prediction using ONNX backend with streaming sagittal processing.
        """
        if self.model_info is None:
            raise RuntimeError("Model not loaded. Call load_checkpoint() first.")

        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for sagittal mapping, even in the ONNX backend.")

        start_index = 0
        plane = self.cfg.DATA.PLANE
        index_of_current_plane = self.permute_order[plane].index(0)
        target_shape = init_pred.shape
        ii = [slice(None) for _ in range(4)]
        pred_ii = tuple(slice(i) for i in target_shape[:3])

        if out is None:
            out = init_pred.detach().clone()

        try:
            for batch_idx, batch in enumerate(val_loader):
                images = batch["image"]
                if hasattr(images, "numpy"):
                    images = images.numpy()

                # predict the current batch, outputs numpy array
                pred = self.predict_batch(images)
                batch_size = pred.shape[0]
                end_index = start_index + batch_size

                # convert to tensor for mapping and aggregation
                pred = torch.from_numpy(pred)

                # check if we need a special mapping (e.g. as for sagittal)
                if plane == "sagittal":
                    pred = apply_sagittal_mapping(
                        pred, num_classes=self.cfg.MODEL.NUM_CLASSES, lut=self.lut
                    )

                # permute the prediction into the out slice order
                pred = pred.permute(*self.permute_order[plane]).to(out.device)

                # cut prediction to the image size
                pred = pred[pred_ii]

                # add prediction logits into the output
                ii[index_of_current_plane] = slice(start_index, end_index)
                out[tuple(ii)].add_(pred, alpha=self.alpha.get(plane, 0.4))
                start_index = end_index
        except Exception:
            raise

        return out

    def run(
        self,
        init_pred,
        img_filename: str,
        orig_data: npt.NDArray,
        orig_zoom: npt.NDArray,
        out: Optional = None,
        out_res: int | None = None,
        batch_size: int | None = None,
    ):
        """
        Run ONNX inference on the data
        """
        # Set up DataLoader
        test_dataset = ProcessDataThickSlices(
            orig_data,
            orig_zoom,
            self.cfg,
            transforms=Compose([ToTensorTest()]),
        )

        test_data_loader = DataLoader(
            dataset=test_dataset,
            shuffle=False,
            batch_size=self.cfg.TEST.BATCH_SIZE if batch_size is None else batch_size,
        )

        # Run evaluation
        start = time.time()
        out = self.eval(init_pred, test_data_loader, out=out, out_scale=out_res)
        time_delta = time.time() - start
        logger.info(
            f"{self.cfg.DATA.PLANE.capitalize()} ONNX inference on {img_filename} finished in "
            f"{time_delta:0.4f} seconds"
        )

        return out


class PytorchInference:
    """
    PyTorch inference class
    """

    def __init__(
        self,
        cfg: Config,
        device: torch.device,
        ckpt: str = "",
        lut: str | np.ndarray | DataFrame | None = None,
    ):
        self.cfg = cfg
        self.device = device
        self.lut = lut

        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is not installed. Please install torch to use the pytorch backend."
            )

        # Set random seed from configs
        np.random.seed(cfg.RNG_SEED)
        torch.manual_seed(cfg.RNG_SEED)

        # switched on denormal flushing for faster cpu processing
        torch.set_flush_denormal(True)

        self.default_device = device

        self.model_parallel = (
            torch.cuda.device_count() > 1
            and self.default_device.type == "cuda"
            and self.default_device.index is None
        )

        self.model = None
        self._model_not_init = None
        self.setup_model(cfg, device=self.default_device)
        self.model_name = self.cfg.MODEL.MODEL_NAME

        self.alpha = {"sagittal": 0.2}
        self.permute_order = {
            "axial": (3, 0, 2, 1),
            "coronal": (2, 3, 0, 1),
            "sagittal": (0, 3, 2, 1),
        }
        self.is_jit_model = False

        if ckpt:
            self.load_checkpoint(ckpt)

    def setup_model(self, cfg=None, device: torch.device = None):
        """Set up the PyTorch model"""
        if cfg is not None:
            self.cfg = cfg
        if device is None:
            device = self.default_device
        self._model_not_init = None
        self.device = None

    def to(self, device: torch.device | None = None):
        """Move and/or cast the parameters and buffers"""
        if self.model_parallel:
            raise RuntimeError(
                "Moving the model to other devices is not supported for multi-device models."
            )
        _device = self.default_device if device is None else device
        self.device = _device
        self.model.to(device=_device)

    def load_checkpoint(self, ckpt: str):
        """Load the PyTorch checkpoint and set device and model"""
        logger.info(f"Loading checkpoint {ckpt}")

        # If device is None, the model has never been loaded
        if self.device is None:
            self.device = self.default_device

        # workaround for mps - set device for loading
        device = self.device
        if self.device.type == "mps":
            device = "cpu"

        # Load TorchScript model (.pt file)
        logger.info("Loading TorchScript model (.pt file)")
        self.model = torch.jit.load(ckpt, map_location=device)
        self.is_jit_model = True

        # Move model to target device after loading
        self.model.to(self.device)

        if self.model_parallel:
            self.model = torch.nn.DataParallel(self.model)

    def get_modelname(self) -> str:
        """Return the model name"""
        return self.model_name

    @torch.no_grad()
    def eval(
        self,
        init_pred: torch.Tensor,
        val_loader: DataLoader,
        *,
        out_scale: Optional = None,
        out: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Perform prediction and inplace-aggregate views into pred_prob"""
        self.model.eval()

        if not isinstance(val_loader.sampler, torch.utils.data.SequentialSampler):
            logger.warning(
                "The Validation loader seems to not use the SequentialSampler. This might interfere with "
                "the assumed sorting of batches."
            )

        start_index = 0
        plane = self.cfg.DATA.PLANE
        index_of_current_plane = self.permute_order[plane].index(0)
        target_shape = init_pred.shape
        ii = [slice(None) for _ in range(4)]
        pred_ii = tuple(slice(i) for i in target_shape[:3])

        if out is None:
            out = init_pred.detach().clone()

        try:
            for batch_idx, batch in enumerate(val_loader):
                # move data to the model device
                images, scale_factors = (
                    batch["image"].to(self.device),
                    batch["scale_factor"].to(self.device),
                )

                # predict the current batch, outputs logits
                if self.is_jit_model:
                    pred = self.model(images, scale_factors)
                else:
                    pred = self.model(images, scale_factors, out_scale)
                batch_size = pred.shape[0]
                end_index = start_index + batch_size

                # check if we need a special mapping (e.g. as for sagittal)
                if plane == "sagittal":
                    pred = apply_sagittal_mapping(
                        pred, num_classes=self.cfg.MODEL.NUM_CLASSES, lut=self.lut
                    )

                # permute the prediction into the out slice order
                pred = pred.permute(*self.permute_order[plane]).to(out.device)

                # cut prediction to the image size
                pred = pred[pred_ii]

                # add prediction logits into the output
                ii[index_of_current_plane] = slice(start_index, end_index)
                out[tuple(ii)].add_(pred, alpha=self.alpha.get(plane, 0.4))
                start_index = end_index
        except Exception:
            raise

        return out

    @torch.no_grad()
    def run(
        self,
        init_pred: torch.Tensor,
        img_filename: str,
        orig_data: npt.NDArray,
        orig_zoom: npt.NDArray,
        out: torch.Tensor | None = None,
        out_res: int | None = None,
        batch_size: int | None = None,
    ) -> torch.Tensor:
        """Run the loaded model on the data"""
        # Set up DataLoader
        test_dataset = ProcessDataThickSlices(
            orig_data,
            orig_zoom,
            self.cfg,
            transforms=Compose([ToTensorTest()]),
        )

        test_data_loader = DataLoader(
            dataset=test_dataset,
            shuffle=False,
            batch_size=self.cfg.TEST.BATCH_SIZE if batch_size is None else batch_size,
        )

        # Run evaluation
        start = time.time()
        out = self.eval(init_pred, test_data_loader, out=out, out_scale=out_res)
        time_delta = time.time() - start
        logger.info(
            f"{self.cfg.DATA.PLANE.capitalize()} PyTorch inference on {img_filename} finished in "
            f"{time_delta:0.4f} seconds"
        )

        return out


def CreateInference(
    backend: str,
    cfg: Config,
    device: torch.device | str | None = None,
    ckpt: str = "",
    lut: str | np.ndarray | DataFrame | None = None,
    use_gpu: bool = False,
    **kwargs,
) -> PytorchInference | TinyGradInference:
    """
    Creates inference instances based on backend
    """

    if backend == "pytorch":
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is not installed. Please install torch to use the pytorch backend."
            )
        if device is None:
            device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
        elif isinstance(device, str):
            device = torch.device(device)
        return PytorchInference(cfg, device, ckpt, lut)
    elif backend == "tinygrad":
        # Note: "tinygrad" backend actually uses ONNX Runtime for inference
        if not ONNX_AVAILABLE:
            raise ImportError(
                "ONNX Runtime is not installed. Please install onnxruntime to use the tinygrad backend."
            )
        parallel_batches = kwargs.get("parallel_batches", 2)
        logger.info(
            f"Using TinyGrad backend (ONNX Runtime) with device: {device}, use_gpu: {use_gpu}"
        )
        return TinyGradInference(cfg, device, ckpt, lut, parallel_batches, use_gpu)
    else:
        raise ValueError(f"Unknown backend: {backend}. Supported backends: 'pytorch', 'tinygrad'")
