import itertools
import multiprocessing
import os
import pathlib
import tempfile
import traceback
from pathlib import Path
from typing import Generator, Tuple

import nibabel.processing
import numpy as np
from skimage.transform import resize

import invesalius.data.slice_ as slc
from invesalius import inv_paths
from invesalius.data import imagedata_utils
from invesalius.net.utils import download_url_to_file
from invesalius.pubsub import pub as Publisher
from invesalius.segmentation.deep_learning.fastsurfer_subpart.data_process import (
    read_classes_from_lut,
)
from invesalius.segmentation.deep_learning.fastsurfer_subpart.pipeline import run_pipeline
from invesalius.utils import new_name_by_pattern

from . import utils

SIZE = 48


def run_cranioplasty_implant():
    """
    This function was created to allow the creation of implants for
    cranioplasty to be called by command line.
    """
    image = slc.Slice().matrix
    backend = "pytorch"
    device_id = list(utils.get_torch_devices().values())[0]
    apply_wwwl = False
    create_new_mask = True
    use_gpu = True
    # resize_by_spacing = True
    window_width = slc.Slice().window_width
    window_level = slc.Slice().window_level
    overlap = 50
    patch_size = 480
    method = 0  # binary

    seg = ImplantCTSegmentProcess

    ps = seg(
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap,
        apply_wwwl,
        window_width,
        window_level,
        method=method,
        patch_size=patch_size,
        resize_by_spacing=True,
        image_spacing=slc.Slice().spacing,
    )
    ps._run_segmentation()
    ps.apply_segment_threshold(0.75)
    slc.Slice().discard_all_buffers()
    Publisher.sendMessage("Reload actual slice")


patch_type = Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]


def gen_patches(
    image: np.ndarray, patch_size: int, overlap: int
) -> Generator[Tuple[float, np.ndarray, patch_type], None, None]:
    overlap = int(patch_size * overlap / 100)
    sz, sy, sx = image.shape
    slices_x = [i for i in range(0, sx, patch_size - overlap) if i + patch_size <= sx]
    if not slices_x:
        slices_x.append(0)
    elif slices_x[-1] + patch_size < sx:
        slices_x.append(sx - patch_size)
    slices_y = [i for i in range(0, sy, patch_size - overlap) if i + patch_size <= sy]
    if not slices_y:
        slices_y.append(0)
    elif slices_y[-1] + patch_size < sy:
        slices_y.append(sy - patch_size)
    slices_z = [i for i in range(0, sz, patch_size - overlap) if i + patch_size <= sz]
    if not slices_z:
        slices_z.append(0)
    elif slices_z[-1] + patch_size < sz:
        slices_z.append(sz - patch_size)
    i_cuts = list(itertools.product(slices_z, slices_y, slices_x))

    sub_image = np.empty(shape=(patch_size, patch_size, patch_size), dtype="float32")
    for idx, (iz, iy, ix) in enumerate(i_cuts):
        sub_image[:] = 0
        _sub_image = image[iz : iz + patch_size, iy : iy + patch_size, ix : ix + patch_size]
        sz, sy, sx = _sub_image.shape
        sub_image[0:sz, 0:sy, 0:sx] = _sub_image
        ez = iz + sz
        ey = iy + sy
        ex = ix + sx

        yield (idx + 1.0) / len(i_cuts), sub_image, ((iz, ez), (iy, ey), (ix, ex))


def predict_patch(sub_image, patch, nn_model, patch_size):
    (iz, ez), (iy, ey), (ix, ex) = patch
    sub_mask = nn_model.predict(sub_image.reshape(1, patch_size, patch_size, patch_size, 1))
    return sub_mask.reshape(patch_size, patch_size, patch_size)[
        0 : ez - iz, 0 : ey - iy, 0 : ex - ix
    ]


def predict_patch_torch(sub_image, patch, nn_model, device, patch_size):
    import torch

    with torch.no_grad():
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = (
            nn_model(
                torch.from_numpy(sub_image.reshape(1, 1, patch_size, patch_size, patch_size)).to(
                    device
                )
            )
            .cpu()
            .numpy()
        )
    return sub_mask.reshape(patch_size, patch_size, patch_size)[
        0 : ez - iz, 0 : ey - iy, 0 : ex - ix
    ]


def predict_patch_tinygrad(sub_image, patch, nn_model, device, patch_size):
    from tinygrad import Tensor, dtypes

    with Tensor.test():
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = nn_model(
            Tensor(
                sub_image.reshape(-1, 1, SIZE, SIZE, SIZE),
                dtype=dtypes.float32,
                device=device,
                requires_grad=False,
            )
        ).numpy()

    return sub_mask.reshape(patch_size, patch_size, patch_size)[
        0 : ez - iz, 0 : ey - iy, 0 : ex - ix
    ]


def download_callback(comm_array):
    def _download_callback(value):
        comm_array[0] = value

    return _download_callback


def segment_torch(
    image, weights_file, overlap, device_id, probability_array, comm_array, patch_size
):
    import torch

    from .model import Unet3D

    device = torch.device(device_id)
    if weights_file.exists():
        state_dict = torch.load(str(weights_file), map_location=torch.device("cpu"))
    else:
        raise FileNotFoundError("Weights file not found")
    model = Unet3D()
    model.load_state_dict(state_dict["model_state_dict"])
    model.to(device)
    model.eval()

    image = imagedata_utils.image_normalize(image, 0.0, 1.0, output_dtype=np.float32)
    sums = np.zeros_like(image)
    # segmenting by patches
    with torch.no_grad():
        for completion, sub_image, patch in gen_patches(image, patch_size, overlap):
            comm_array[0] = completion
            (iz, ez), (iy, ey), (ix, ex) = patch
            sub_mask = predict_patch_torch(sub_image, patch, model, device, patch_size)
            probability_array[iz:ez, iy:ey, ix:ex] += sub_mask
            sums[iz:ez, iy:ey, ix:ex] += 1

    probability_array /= sums
    comm_array[0] = np.inf


def segment_tinygrad(
    image: np.ndarray, weights_file, overlap, device_id, probability_array, comm_array, patch_size
):
    import onnx
    from tinygrad import Tensor
    from tinygrad.engine.jit import TinyJit

    from invesalius.segmentation.tinygrad_extra.onnx import OnnxRunner

    device = device_id

    if not weights_file.exists():
        raise FileNotFoundError("Weights file not found")

    onnx_model = onnx.load(weights_file)
    model = OnnxRunner(onnx_model)
    model_jit = TinyJit(lambda x: model({"input": x})["output"])
    image = imagedata_utils.image_normalize(image, 0.0, 1.0, output_dtype=np.float32)
    sums = np.zeros_like(image)

    # segmenting
    with Tensor.test():
        for completion, sub_image, patch in gen_patches(image, patch_size, overlap):
            comm_array[0] = completion
            (iz, ez), (iy, ey), (ix, ex) = patch
            sub_mask = predict_patch_tinygrad(sub_image, patch, model_jit, device, patch_size)
            probability_array[iz:ez, iy:ey, ix:ex] += sub_mask
            sums[iz:ez, iy:ey, ix:ex] += 1

    probability_array /= sums
    comm_array[0] = np.inf


def segment_torch_jit(
    image,
    weights_file,
    overlap,
    device_id,
    probability_array,
    comm_array,
    patch_size,
    resize_by_spacing=True,
    image_spacing=(1.0, 1.0, 1.0),
    needed_spacing=(0.5, 0.5, 0.5),
    flipped=False,
):
    import torch

    from .model import WrapModel

    print(f"\n\n\n{image_spacing}\n\n\n")
    print("Patch size:", patch_size)

    if resize_by_spacing:
        old_shape = image.shape
        new_shape = [
            round(i * j / k)
            for (i, j, k) in zip(old_shape, image_spacing[::-1], needed_spacing[::-1])
        ]

        image = resize(image, output_shape=new_shape, order=0, preserve_range=True)
        original_probability_array = probability_array
        probability_array = np.zeros_like(image)

    device = torch.device(device_id)
    if weights_file.exists():
        jit_model = torch.jit.load(weights_file, map_location=torch.device("cpu"))
    else:
        raise FileNotFoundError("Weights file not found")
    model = WrapModel(jit_model)
    model.to(device)
    model.eval()

    sums = np.zeros_like(image)
    # segmenting by patches
    for completion, sub_image, patch in gen_patches(image, patch_size, overlap):
        comm_array[0] = completion
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = predict_patch_torch(sub_image, patch, model, device, patch_size)
        probability_array[iz:ez, iy:ey, ix:ex] += sub_mask.squeeze()
        sums[iz:ez, iy:ey, ix:ex] += 1

    probability_array /= sums

    # FIX: to remove
    if flipped:
        probability_array = np.flip(probability_array, 2)

    if resize_by_spacing:
        original_probability_array[:] = resize(
            probability_array, output_shape=old_shape, preserve_range=True
        )

    comm_array[0] = np.inf


ctx = multiprocessing.get_context("spawn")


class SegmentProcess(ctx.Process):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap=50,
        apply_wwwl=False,
        window_width=255,
        window_level=127,
        patch_size=SIZE,
    ):
        multiprocessing.Process.__init__(self)

        self._image_filename = image.filename
        self._image_dtype = image.dtype
        self._image_shape = image.shape

        fd, fname = tempfile.mkstemp()
        self._probability_array = np.memmap(
            filename=fname, shape=self._image_shape, dtype=np.float32, mode="w+"
        )
        self._prob_array_filename = self._probability_array.filename
        self._prob_array_fd = fd

        fd, fname = tempfile.mkstemp()
        self._comm_array = np.memmap(filename=fname, shape=(1,), dtype=np.float32, mode="w+")
        self._comm_array_filename = self._comm_array.filename
        self._comm_array_fd = fd

        self.create_new_mask = create_new_mask
        self.backend = backend
        self.device_id = device_id
        self.use_gpu = use_gpu

        self.overlap = overlap

        self.patch_size = patch_size

        self.apply_wwwl = apply_wwwl
        self.window_width = window_width
        self.window_level = window_level

        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

        self.torch_weights_file_name = ""
        self.torch_weights_url = ""
        self.torch_weights_hash = ""

        self.onnx_weights_file_name = ""
        self.onnx_weights_url = ""
        self.onnx_weights_hash = ""

        self.mask = None

    def run(self):
        try:
            multiprocessing.current_process().name = "MainProcess"
            os.environ[self.device_id] = "1"
            self._run_segmentation()
            self._cconn.send(None)
        except Exception as e:
            tb = traceback.format_exc()
            self._cconn.send((e, tb))

    def _run_segmentation(self):
        image = np.memmap(
            self._image_filename,
            dtype=self._image_dtype,
            shape=self._image_shape,
            mode="r",
        )

        if self.apply_wwwl:
            image = imagedata_utils.get_LUT_value(image, self.window_width, self.window_level)

        probability_array = np.memmap(
            self._prob_array_filename,
            dtype=np.float32,
            shape=self._image_shape,
            mode="r+",
        )
        comm_array = np.memmap(self._comm_array_filename, dtype=np.float32, shape=(1,), mode="r+")

        if self.backend.lower() == "pytorch":
            if not self.torch_weights_file_name:
                raise FileNotFoundError("Weights file not specified.")
            folder = inv_paths.MODELS_DIR.joinpath(self.torch_weights_file_name.split(".")[0])
            system_state_dict_file = folder.joinpath(self.torch_weights_file_name)
            user_state_dict_file = inv_paths.USER_DL_WEIGHTS.joinpath(self.torch_weights_file_name)
            if system_state_dict_file.exists():
                weights_file = system_state_dict_file
            elif user_state_dict_file.exists():
                weights_file = user_state_dict_file
            else:
                download_url_to_file(
                    self.torch_weights_url,
                    user_state_dict_file,
                    self.torch_weights_hash,
                    download_callback(comm_array),
                )
                weights_file = user_state_dict_file
            segment_torch(
                image,
                weights_file,
                self.overlap,
                self.device_id,
                probability_array,
                comm_array,
                self.patch_size,
            )
        elif self.backend.lower() == "tinygrad":
            if not self.onnx_weights_file_name:
                raise FileNotFoundError("Weights file not specified.")
            folder = inv_paths.MODELS_DIR.joinpath(self.onnx_weights_file_name.split(".")[0])
            system_state_dict_file = folder.joinpath(self.onnx_weights_file_name)
            user_state_dict_file = inv_paths.USER_DL_WEIGHTS.joinpath(self.onnx_weights_file_name)
            if system_state_dict_file.exists():
                weights_file = system_state_dict_file
            elif user_state_dict_file.exists():
                weights_file = user_state_dict_file

            else:
                download_url_to_file(
                    self.onnx_weights_url,
                    user_state_dict_file,
                    self.onnx_weights_hash,
                    download_callback(comm_array),
                )
                weights_file = user_state_dict_file
            segment_tinygrad(
                image,
                weights_file,
                self.overlap,
                self.device_id,
                probability_array,
                comm_array,
                self.patch_size,
            )
        else:
            raise TypeError("Wrong backend")

    @property
    def exception(self):
        # Based on https://stackoverflow.com/a/33599967
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception

    def apply_segment_threshold(self, threshold):
        if self.create_new_mask:
            if self.mask is None:
                name = new_name_by_pattern("brainseg_mri_t1")
                self.mask = slc.Slice().create_new_mask(name=name)
        else:
            self.mask = slc.Slice().current_mask
            if self.mask is None:
                name = new_name_by_pattern("brainseg_mri_t1")
                self.mask = slc.Slice().create_new_mask(name=name)

        self.mask.was_edited = True
        self.mask.matrix[1:, 1:, 1:] = (self._probability_array >= threshold) * 255
        self.mask.modified(True)

    def get_completion(self):
        return self._comm_array[0]

    def __del__(self):
        del self._comm_array
        os.close(self._comm_array_fd)
        os.remove(self._comm_array_filename)

        del self._probability_array
        os.close(self._prob_array_fd)
        os.remove(self._prob_array_filename)


class BrainSegmentProcess(SegmentProcess):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap=50,
        apply_wwwl=False,
        window_width=255,
        window_level=127,
        patch_size=SIZE,
    ):
        super().__init__(
            image,
            create_new_mask,
            backend,
            device_id,
            use_gpu,
            overlap=overlap,
            apply_wwwl=apply_wwwl,
            window_width=window_width,
            window_level=window_level,
            patch_size=patch_size,
        )
        self.torch_weights_file_name = "brain_mri_t1.pt"
        self.torch_weights_url = (
            "https://github.com/tfmoraes/deepbrain_torch/releases/download/v1.1.0/weights.pt"
        )
        self.torch_weights_hash = "194b0305947c9326eeee9da34ada728435a13c7b24015cbd95971097fc178f22"

        self.onnx_weights_file_name = "brain_mri_t1.onnx"
        self.onnx_weights_url = (
            "https://github.com/tfmoraes/deepbrain_torch/releases/download/v1.1.0/weights.onnx"
        )
        self.onnx_weights_hash = "3e506ae448150ca2c7eb9a8a6b31075ffff38e8db0fc6e25cb58c320aea79d21"


class SubpartSegmentProcess(SegmentProcess):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap=50,
        apply_wwwl=False,
        window_width=255,
        window_level=127,
        patch_size=SIZE,
        selected_mask_types=None,
    ):
        super().__init__(
            image,
            create_new_mask,
            backend,
            device_id,
            use_gpu,
            overlap=overlap,
            apply_wwwl=apply_wwwl,
            window_width=window_width,
            window_level=window_level,
            patch_size=patch_size,
        )
        self.selected_mask_types = selected_mask_types or []
        fastsurfer_dir = Path(__file__).parent / "fastsurfer_subpart"
        self.lut_file = fastsurfer_dir / "LUT.tsv"

    model_info = {
        "axial": {
            "pytorch": {
                "filename": "model_axial.pt",
                "url": "https://raw.githubusercontent.com/invesalius/weights/main/fastsurf/fastsurf_axial.pt",
                "hash": "3387b311aa985dc200941277013760ba67ca8f9fb43612e86c065b922619c1bf",
            },
            "tinygrad": {
                "filename": "model_axial.onnx",
                "url": "https://raw.githubusercontent.com/invesalius/weights/main/fastsurf/fastsurf_axial.onnx",
                "hash": "fcf8bd9af831f9eb3e836c868fee6434d41cdbeb76d38337f54bd4f6acc32624",
            },
        },
        "coronal": {
            "pytorch": {
                "filename": "model_coronal.pt",
                "url": "https://raw.githubusercontent.com/invesalius/weights/main/fastsurf/fastsurf_coronal.pt",
                "hash": "da64d4735053b72fb8c76713ab0273d1543a9fd8887453b141e8fe5813dd0faa",
            },
            "tinygrad": {
                "filename": "model_coronal.onnx",
                "url": "https://raw.githubusercontent.com/invesalius/weights/main/fastsurf/fastsurf_coronal.onnx",
                "hash": "45fb8b495d77de7787a0cb6759c2a8b18cc7972495275e19a3c0a7f7e1f8ba4c",
            },
        },
        "sagittal": {
            "pytorch": {
                "filename": "model_sagittal.pt",
                "url": "https://raw.githubusercontent.com/invesalius/weights/main/fastsurf/fastsurf_sagittal.pt",
                "hash": "91e523b9ba6cd463187654118a800eca55c76b3b0c9b3cc1a69310152a912731",
            },
            "tinygrad": {
                "filename": "model_sagittal.onnx",
                "url": "https://raw.githubusercontent.com/invesalius/weights/main/fastsurf/fastsurf_sagittal.onnx",
                "hash": "7781066a49de688e127945f17209d6136dbee44fb163ea3b16387058b77856ce",
            },
        },
    }

    def get_model_path(self, plane):
        backend = self.backend.lower()
        info = self.model_info[plane][backend]
        sys_path = inv_paths.MODELS_DIR / "fastsurfer" / plane / info["filename"]
        user_path = inv_paths.USER_DL_WEIGHTS / info["filename"]
        if sys_path.exists():
            return str(sys_path)
        elif user_path.exists():
            return str(user_path)
        else:
            download_url_to_file(
                info["url"], user_path, info["hash"], download_callback(self._comm_array)
            )
            return str(user_path)

    def _run_segmentation(self):
        import nibabel as nib

        image = np.memmap(
            self._image_filename,
            dtype=self._image_dtype,
            shape=self._image_shape,
            mode="r",
        )

        if self.apply_wwwl:
            image = imagedata_utils.get_LUT_value(image, self.window_width, self.window_level)

        temp_dir = tempfile.gettempdir()
        temp_img_file = pathlib.Path(temp_dir) / "input_image.nii.gz"

        img = nib.load(f"{temp_dir}/proj_image.nii.gz")
        nib.save(img, str(temp_img_file))

        # get backend specific model paths
        model_paths = {
            plane: self.get_model_path(plane) for plane in ["axial", "coronal", "sagittal"]
        }

        # create temporary directory for output
        with tempfile.TemporaryDirectory() as temp_output_dir:
            try:
                print("Starting subpart prediction pipeline...")

                comm_array = np.memmap(
                    self._comm_array_filename, dtype=np.float32, shape=(1,), mode="r+"
                )

                def progress_callback(current_step, total_steps):
                    progress = current_step / total_steps
                    comm_array[0] = progress * 0.9

                sid = "subject"
                pred_name = "mri/aparc.DKTatlas+aseg.deep.mgz"

                args = {
                    "orig_name": temp_img_file,
                    "out_dir": Path(temp_output_dir),
                    "sid": sid,
                    "pred_name": pred_name,
                    "ckpt_ax": model_paths["axial"],
                    "ckpt_cor": model_paths["coronal"],
                    "ckpt_sag": model_paths["sagittal"],
                    "lut": self.lut_file,
                    "device": self.device_id if self.use_gpu else "cpu",
                    "viewagg_device": self.device_id if self.use_gpu else "cpu",
                    "batch_size": 6,
                    "threads": 4,
                    "backend": self.backend.lower(),
                    "progress_callback": progress_callback,
                }
                return_code = run_pipeline(**args)

                if return_code != 0:
                    raise RuntimeError(
                        f"FastSurfer's pipeline.py failed with exit code {return_code}"
                    )

                segmentation_file = Path(temp_output_dir) / sid / pred_name
                if not segmentation_file.exists():
                    raise FileNotFoundError(
                        f"Final segmentation file not found at {segmentation_file}"
                    )

                comm_array[0] = 0.92
                original_nifti_img = nib.load(str(temp_img_file))
                conformed_segmentation_img = nib.load(str(segmentation_file))

                comm_array[0] = 0.95
                resampled_segmentation_img = nibabel.processing.resample_from_to(
                    conformed_segmentation_img, original_nifti_img, order=0
                )

                comm_array[0] = 0.98
                final_segmentation = np.asarray(resampled_segmentation_img.dataobj)
                final_segmentation = np.fliplr(np.swapaxes(final_segmentation, 0, 2))

                print(
                    f"Segmentation data range: [{final_segmentation.min()}, {final_segmentation.max()}]"
                )
                print(f"Segmentation unique values: {len(np.unique(final_segmentation))}")
                print(f"Non-zero segmentation pixels: {np.count_nonzero(final_segmentation)}")

                probability_array = np.memmap(
                    self._prob_array_filename,
                    dtype=np.float32,
                    shape=self._image_shape,
                    mode="r+",
                )

                probability_array[:] = final_segmentation.astype(np.float32)

                comm_array[0] = 1.0

            finally:
                import shutil

                if os.path.exists(temp_output_dir):
                    shutil.rmtree(temp_output_dir)

    def apply_segment_threshold(self, threshold):
        seg = getattr(self, "_probability_array", None)
        if seg is None:
            raise RuntimeError("_probability_array not initialized.")

        # Whole brain fallback
        if not self.selected_mask_types:
            mask = slc.Slice().create_new_mask(
                name=new_name_by_pattern("whole_brain"), add_to_project=True
            )
            mask.was_edited = True
            mask.matrix[1:, 1:, 1:] = (seg > 0).astype(np.uint8) * 255
            mask.modified(True)
            return

        lut = read_classes_from_lut(self.lut_file).to_dict("records")
        all_names = {str(rec["LabelName"]) for rec in lut}

        # Prefix constants (correct lengths)
        P_CTX_LH = "ctx-lh-"
        P_CTX_RH = "ctx-rh-"
        P_CTX = "ctx-"
        P_LEFT = "Left-"
        P_RIGHT = "Right-"

        # Helpers
        def color(rec):
            r = rec.get("R", rec.get("Red", 0))
            g = rec.get("G", rec.get("Green", 0))
            b = rec.get("B", rec.get("Blue", 0))
            return (float(r) / 255.0, float(g) / 255.0, float(b) / 255.0)

        is_ctx = lambda n: n.startswith((P_CTX_LH, P_CTX_RH, P_CTX))

        # Expand WM category to include ventricles, cerebellum (WM and cortex), and choroid plexus
        def is_wm_like(name: str) -> bool:
            return (
                name.startswith(("Left-Cerebral-White-Matter", "Right-Cerebral-White-Matter"))
                or name.startswith(
                    ("Left-Cerebellum-White-Matter", "Right-Cerebellum-White-Matter")
                )
                or name.startswith(("Left-Cerebellum-Cortex", "Right-Cerebellum-Cortex"))
                or name in ("3rd-Ventricle", "4th-Ventricle")
                or name.startswith(("Left-Lateral-Ventricle", "Right-Lateral-Ventricle"))
                or name.startswith(("Left-Inf-Lat-Vent", "Right-Inf-Lat-Vent"))
                or name.startswith(("Left-choroid-plexus", "Right-choroid-plexus"))
                or name == "WM-hypointensities"
            )

        def pick_regions(cat):
            """
            Categories:
              - cortical: any ctx-* labels
              - subcortical: everything that's not cortical and not background (ID 0)
              - wm: cerebral + cerebellar WM, cerebellar cortex, ventricles (lat/inf-lat/3rd/4th), choroid plexus, WM-hypointensities
            """
            c = str(cat).lower()
            if c == "cortical":
                return [r for r in lut if is_ctx(str(r["LabelName"]))]
            if c == "subcortical":
                return [r for r in lut if not is_ctx(str(r["LabelName"])) and int(r["ID"]) != 0]
            if c in ("wm", "white_matter", "white-matter"):
                return [r for r in lut if is_wm_like(str(r["LabelName"]))]
            # Fallback: exact match by label name
            return [r for r in lut if str(r["LabelName"]).lower() == c]

        def std_name(label_name: str) -> str:
            """
            Standardize names (flip side in text only, lowercase 'left'/'right'):
              - cortical: 'ctx-lh-foo' -> 'right_foo', 'ctx-rh-bar' -> 'left_bar'
                if no RH counterpart for LH, drop side: 'ctx-lh-foo' -> 'foo'
              - sub/wm: 'Left-foo' -> 'right_foo', 'Right-bar' -> 'left_bar'
              - midline/unpaired: just sanitize with underscores
            """
            n = str(label_name)

            # Cortical
            if n.startswith(P_CTX_LH):
                base = n[len(P_CTX_LH) :]
                if (P_CTX_RH + base) in all_names:
                    return "right_" + base.replace("-", "_").replace(" ", "_")
                return base.replace("-", "_").replace(" ", "_")  # no RH counterpart -> drop side
            if n.startswith(P_CTX_RH):
                base = n[len(P_CTX_RH) :]
                return "left_" + base.replace("-", "_").replace(" ", "_")
            if n.startswith(P_CTX):
                base = n[len(P_CTX) :]
                return base.replace("-", "_").replace(" ", "_")

            # Subcortical / WM (flip side in text only)
            if n.startswith(P_LEFT):
                base = n[len(P_LEFT) :]
                return "right_" + base.replace("-", "_").replace(" ", "_")
            if n.startswith(P_RIGHT):
                base = n[len(P_RIGHT) :]
                return "left_" + base.replace("-", "_").replace(" ", "_")

            # Midline/unpaired (e.g., 3rd/4th ventricle, brain-stem, CSF)
            return n.replace("-", "_").replace(" ", "_")

        for category in self.selected_mask_types:
            regions = pick_regions(category)
            if not regions:
                print(f"No regions found for category '{category}'. Skipping.")
                continue

            for rec in regions:
                lid = int(rec["ID"])  # do NOT flip ID
                name = std_name(rec["LabelName"])
                binmask = (seg == lid).astype(np.uint8) * 255
                if not np.any(binmask):
                    print(f"No voxels found for label ID {lid} ('{name}'). Skipping mask creation.")
                    continue

                m = slc.Slice().create_new_mask(
                    name=new_name_by_pattern(f"{category}_{name}"), add_to_project=True
                )
                m.color = color(rec)
                m.was_edited = True
                m.matrix[1:, 1:, 1:] = binmask
                m.modified(True)


class TracheaSegmentProcess(SegmentProcess):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap=50,
        apply_wwwl=False,
        window_width=255,
        window_level=127,
        patch_size=48,
    ):
        super().__init__(
            image,
            create_new_mask,
            backend,
            device_id,
            use_gpu,
            overlap=overlap,
            apply_wwwl=apply_wwwl,
            window_width=window_width,
            window_level=window_level,
            patch_size=patch_size,
        )
        self.torch_weights_file_name = "trachea_ct.pt"
        self.torch_weights_url = (
            "https://github.com/tfmoraes/deep_trachea_torch/releases/download/v1.0/weights.pt"
        )
        self.torch_weights_hash = "6102d16e3c8c07a1c7b0632bc76db4d869c7467724ff7906f87d04f6dc72022e"

        self.onnx_weights_file_name = "trachea_ct.onnx"
        self.onnx_weights_url = "https://github.com/tfmoraes/deep_trachea_torch/releases/download/v1.0/weights_trachea_ct.onnx"
        self.onnx_weights_hash = "b43ab3b6ec3788a179def66af18715f57450e33ef557fafb34c49ee5e3ab8a48"


class MandibleCTSegmentProcess(SegmentProcess):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap=50,
        apply_wwwl=False,
        window_width=255,
        window_level=127,
        patch_size=96,
        threshold=150,
        resize_by_spacing=True,
        image_spacing=(1.0, 1.0, 1.0),
    ):
        super().__init__(
            image,
            create_new_mask,
            backend,
            device_id,
            use_gpu,
            overlap=overlap,
            apply_wwwl=apply_wwwl,
            window_width=window_width,
            window_level=window_level,
            patch_size=patch_size,
        )

        self.threshold = threshold
        self.resize_by_spacing = resize_by_spacing
        self.image_spacing = image_spacing
        self.needed_spacing = (0.5, 0.5, 0.5)

        self.torch_weights_file_name = "mandible_jit_ct.pt"
        self.torch_weights_url = "https://raw.githubusercontent.com/invesalius/weights/main/mandible_ct/mandible_jit_ct.pt"
        self.torch_weights_hash = "a9988c64b5f04dfbb6d058b95b737ed801f1a89d1cc828cd3e5d76d81979a724"

    def _run_segmentation(self):
        image = np.memmap(
            self._image_filename,
            dtype=self._image_dtype,
            shape=self._image_shape,
            mode="r",
        )

        if self.apply_wwwl:
            image = imagedata_utils.get_LUT_value(image, self.window_width, self.window_level)

        image = (image >= self.threshold).astype(np.float32)

        probability_array = np.memmap(
            self._prob_array_filename,
            dtype=np.float32,
            shape=self._image_shape,
            mode="r+",
        )
        comm_array = np.memmap(self._comm_array_filename, dtype=np.float32, shape=(1,), mode="r+")

        if self.backend.lower() == "pytorch":
            if not self.torch_weights_file_name:
                raise FileNotFoundError("Weights file not specified.")
            folder = inv_paths.MODELS_DIR.joinpath(self.torch_weights_file_name.split(".")[0])
            system_state_dict_file = folder.joinpath(self.torch_weights_file_name)
            user_state_dict_file = inv_paths.USER_DL_WEIGHTS.joinpath(self.torch_weights_file_name)
            if system_state_dict_file.exists():
                weights_file = system_state_dict_file
            elif user_state_dict_file.exists():
                weights_file = user_state_dict_file
            else:
                download_url_to_file(
                    self.torch_weights_url,
                    user_state_dict_file,
                    self.torch_weights_hash,
                    download_callback(comm_array),
                )
                weights_file = user_state_dict_file
            segment_torch_jit(
                image,
                weights_file,
                self.overlap,
                self.device_id,
                probability_array,
                comm_array,
                self.patch_size,
                resize_by_spacing=self.resize_by_spacing,
                image_spacing=self.image_spacing,
                needed_spacing=self.needed_spacing,
            )
        else:
            raise TypeError("Wrong backend")


class ImplantCTSegmentProcess(SegmentProcess):
    def __init__(
        self,
        image,
        create_new_mask,
        backend,
        device_id,
        use_gpu,
        overlap=50,
        apply_wwwl=False,
        window_width=4000,
        window_level=700,
        method=0,
        patch_size=192,
        threshold=150,
        resize_by_spacing=True,
        image_spacing=(1.0, 1.0, 1.0),
    ):
        super().__init__(
            image,
            create_new_mask,
            backend,
            device_id,
            use_gpu,
            overlap=overlap,
            apply_wwwl=apply_wwwl,
            window_width=window_width,
            window_level=window_level,
            patch_size=patch_size,
        )

        self.threshold = threshold
        self.resize_by_spacing = resize_by_spacing
        self.image_spacing = image_spacing
        self.needed_spacing = (1.0, 1.0, 1.0)
        self.method = method

        if self.method == 1:
            self.torch_weights_file_name = "cranioplasty_jit_ct_gray.pt"
            self.torch_weights_url = "https://raw.githubusercontent.com/invesalius/weights/main/cranioplasty_jit_ct_gray/cranioplasty_jit_ct_gray.pt"
            self.torch_weights_hash = (
                "eeb046514cec7b6655745bebcd8403da04009bf1760aabd0f72967a23b5b5f19"
            )
        else:
            self.torch_weights_file_name = "cranioplasty_jit_ct_binary.pt"
            self.torch_weights_url = "https://raw.githubusercontent.com/invesalius/weights/main/cranioplasty_jit_ct_binary/cranioplasty_jit_ct_binary.pt"
            self.torch_weights_hash = (
                "cfd9af5c53c5354959b8f5fd091a6208f6b1fa8a22ae8b4bf2e83cba5e735b41"
            )

    def _run_segmentation(self):
        image = np.memmap(
            self._image_filename,
            dtype=self._image_dtype,
            shape=self._image_shape,
            mode="r",
        )

        # FIX: to remove
        image = np.flip(image, 2)

        if self.method == 1:
            # To use gray scale AI weight
            image = imagedata_utils.get_LUT_value_normalized(image, 700, 4000)
        else:
            # To binary to use binary AI weight
            image = image.copy()
            image[image < 300] = 0
            image[image >= 300] = 1

            # Select only largest connected component
            image = imagedata_utils.get_largest_connected_component(image)

            image = image.astype("float")

        probability_array = np.memmap(
            self._prob_array_filename,
            dtype=np.float32,
            shape=self._image_shape,
            mode="r+",
        )
        comm_array = np.memmap(self._comm_array_filename, dtype=np.float32, shape=(1,), mode="r+")

        if self.backend.lower() == "pytorch":
            if not self.torch_weights_file_name:
                raise FileNotFoundError("Weights file not specified.")
            folder = inv_paths.MODELS_DIR.joinpath(self.torch_weights_file_name.split(".")[0])
            system_state_dict_file = folder.joinpath(self.torch_weights_file_name)
            user_state_dict_file = inv_paths.USER_DL_WEIGHTS.joinpath(self.torch_weights_file_name)
            if system_state_dict_file.exists():
                weights_file = system_state_dict_file
            elif user_state_dict_file.exists():
                weights_file = user_state_dict_file
            else:
                download_url_to_file(
                    self.torch_weights_url,
                    user_state_dict_file,
                    self.torch_weights_hash,
                    download_callback(comm_array),
                )
                weights_file = user_state_dict_file
            segment_torch_jit(
                image,
                weights_file,
                self.overlap,
                self.device_id,
                probability_array,
                comm_array,
                self.patch_size,
                resize_by_spacing=self.resize_by_spacing,
                image_spacing=self.image_spacing,
                needed_spacing=self.needed_spacing,
                flipped=True,
            )
        else:
            raise TypeError("Wrong backend")
