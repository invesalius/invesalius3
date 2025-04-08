import itertools
import multiprocessing
import os
import pathlib
import sys
import tempfile
import traceback
from typing import Generator, Tuple

import numpy as np
from skimage.transform import resize
from vtkmodules.vtkIOXML import vtkXMLImageDataWriter

import invesalius.data.slice_ as slc
from invesalius import inv_paths
from invesalius.data import imagedata_utils
from invesalius.data.converters import to_vtk
from invesalius.net.utils import download_url_to_file
from invesalius.pubsub import pub as Publisher
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
    resize_by_spacing = True
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


def segment_keras(image, weights_file, overlap, probability_array, comm_array, patch_size):
    import keras

    # Loading model
    with open(weights_file) as json_file:
        model = keras.models.model_from_json(json_file.read())
    model.load_weights(str(weights_file.parent.joinpath("model.h5")))
    model.compile("Adam", "binary_crossentropy")

    image = imagedata_utils.image_normalize(image, 0.0, 1.0, output_dtype=np.float32)
    sums = np.zeros_like(image)
    # segmenting by patches
    for completion, sub_image, patch in gen_patches(image, patch_size, overlap):
        comm_array[0] = completion
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = predict_patch(sub_image, patch, model, patch_size)
        probability_array[iz:ez, iy:ey, ix:ex] += sub_mask
        sums[iz:ez, iy:ey, ix:ex] += 1

    probability_array /= sums
    comm_array[0] = 100.0


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
    comm_array[0] = 100.0


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

    comm_array[0] = 100.0


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
            filename=fname, shape=image.shape, dtype=np.float32, mode="w+"
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

        self.keras_weight_file = ""

        self.mask = None

    def run(self):
        try:
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
        else:
            utils.prepare_ambient(self.backend, self.device_id, self.use_gpu)
            segment_keras(
                image,
                self.keras_weight_file,
                self.overlap,
                probability_array,
                comm_array,
                self.patch_size,
            )

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

        self.keras_weight_file = inv_paths.MODELS_DIR.joinpath("brain_mri_t1/model.json")


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
            utils.prepare_ambient(self.backend, self.device_id, self.use_gpu)
            segment_keras(
                image,
                self.keras_weight_file,
                self.overlap,
                probability_array,
                comm_array,
                self.patch_size,
            )


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
            utils.prepare_ambient(self.backend, self.device_id, self.use_gpu)
            segment_keras(
                image,
                self.keras_weight_file,
                self.overlap,
                probability_array,
                comm_array,
                self.patch_size,
            )


class FastSurferCNNProcess(SegmentProcess):
    """
    Process class for FastSurferCNN brain segmentation.
    Extends the standard SegmentProcess to handle multiple view models
    and DKT atlas labels.
    """

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
        patch_size=192,
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

        # Default to ONNX runtime for FastSurferCNN
        self.backend = "onnx"

        # Mask types to generate
        self.selected_mask_types = selected_mask_types or [
            "cortical_dkt",
            "subcortical_gm",
            "white_matter",
            "csf",
        ]

        # Store multiple masks
        self.masks = {}

        # Path for ONNX models and LUT
        self.onnx_dir = inv_paths.USER_DL_WEIGHTS.joinpath("fastsurfer_onnx")
        self.onnx_dir.mkdir(parents=True, exist_ok=True)

        # Path to model files
        self.onnx_paths = {
            "axial": self.onnx_dir.joinpath("fastsurfer_axial.onnx"),
            "coronal": self.onnx_dir.joinpath("fastsurfer_coronal.onnx"),
            "sagittal": self.onnx_dir.joinpath("fastsurfer_sagittal.onnx"),
        }

    def _run_segmentation(self):
        """
        Execute the FastSurferCNN segmentation using ONNX models.
        """
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

        # Check if ONNX models exist
        for view, path in self.onnx_paths.items():
            if not path.exists():
                raise FileNotFoundError(f"ONNX model for {view} view not found at {path}")

        # Run segmentation with ONNX models
        self._segment_onnx(
            image,
            probability_array,
            comm_array,
        )

    def _conform_image(self, image, spacing=(1.0, 1.0, 1.0)):
        """
        Conform image to 1mm isotropic resolution (or other specified spacing).
        This replicates the crucial FastSurferCNN preprocessing step.

        Parameters
        ----------
        image : np.ndarray
            The input 3D image
        spacing : tuple, optional
            Target spacing (default is 1mm isotropic)

        Returns
        -------
        np.ndarray
            Conformed image
        """
        # Calculate target shape based on current shape and spacing ratio
        orig_shape = image.shape
        orig_spacing = slc.Slice().spacing

        target_shape = [int(orig_shape[i] * orig_spacing[i] / spacing[i]) for i in range(3)]

        # Resample to target shape
        conformed_image = resize(
            image,
            output_shape=target_shape,
            order=3,  # Cubic interpolation
            mode="constant",
            anti_aliasing=True,
            preserve_range=True,
        )

        return conformed_image.astype(np.float32)

    def _intensity_normalization(self, image):
        """
        Apply the same intensity normalization as used in FastSurferCNN.

        Parameters
        ----------
        image : np.ndarray
            The input image

        Returns
        -------
        np.ndarray
            Normalized image
        """
        # Clip outliers
        p1 = np.percentile(image, 1)
        p99 = np.percentile(image, 99)
        image_clipped = np.clip(image, p1, p99)

        # Normalize to [0, 1]
        image_norm = (image_clipped - p1) / (p99 - p1)

        return image_norm

    def _gen_patches(self, image, patch_size, overlap):
        """
        Generate patches from 3D image with specified overlap.

        Parameters
        ----------
        image : np.ndarray
            Input 3D image
        patch_size : int
            Size of patch (cube)
        overlap : int
            Overlap between patches (percentage)

        Returns
        -------
        Generator
            Yields tuples of (patch, patch_info)
        """
        # Calculate effective stride based on overlap
        stride = int(patch_size * (1 - overlap / 100))
        shape = image.shape

        # Generate patch indices for each dimension
        indices = []
        for i in range(3):
            indices.append([])
            for start in range(0, shape[i], stride):
                end = start + patch_size

                # Handle edge cases
                if end > shape[i]:
                    end = shape[i]
                    start = max(0, end - patch_size)

                indices[i].append((start, end))

        # Generate all patch combinations
        for z_idx, y_idx, x_idx in itertools.product(
            range(len(indices[0])), range(len(indices[1])), range(len(indices[2]))
        ):
            z_start, z_end = indices[0][z_idx]
            y_start, y_end = indices[1][y_idx]
            x_start, x_end = indices[2][x_idx]

            # Extract patch
            patch = image[z_start:z_end, y_start:y_end, x_start:x_end]

            # For edges, pad if necessary
            if patch.shape != (patch_size, patch_size, patch_size):
                tmp_patch = np.zeros((patch_size, patch_size, patch_size), dtype=patch.dtype)
                tmp_patch[: patch.shape[0], : patch.shape[1], : patch.shape[2]] = patch
                patch = tmp_patch

            patch_info = {
                "z_start": z_start,
                "z_end": z_end,
                "y_start": y_start,
                "y_end": y_end,
                "x_start": x_start,
                "x_end": x_end,
            }

            yield (patch, patch_info)

    def _segment_onnx(self, image, probability_array, comm_array):
        """
        Run segmentation using ONNX models for axial, coronal, and sagittal views.

        Parameters
        ----------
        image : np.ndarray
            Input 3D image
        probability_array : np.ndarray
            Output array for probability values
        comm_array : np.ndarray
            Communication array for progress
        """
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError("onnxruntime is required for FastSurferCNN segmentation")

        # Prepare the image
        conformed_image = self._conform_image(image)
        norm_image = self._intensity_normalization(conformed_image)

        # Initialize aggregated prediction array
        num_classes = 95  # Fixed number of classes in FastSurferCNN
        agg_pred = np.zeros(
            (
                probability_array.shape[0],
                probability_array.shape[1],
                probability_array.shape[2],
                num_classes,
            ),
            dtype=np.float32,
        )

        # Run each view model
        views = ["axial", "coronal", "sagittal"]

        # Setup ONNX Runtime options
        session_options = ort.SessionOptions()

        # Create ONNX Runtime execution providers based on device
        if self.device_id.startswith("cuda") and self.use_gpu:
            ep_list = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            ep_list = ["CPUExecutionProvider"]

        # Batch size for inference
        batch_size = 1

        # Total patches count for progress tracking
        total_patches = 0
        for view in views:
            shape = norm_image.shape
            stride = int(self.patch_size * (1 - self.overlap / 100))
            patches_per_dim = [(s + stride - 1) // stride for s in shape]
            view_patches = patches_per_dim[0] * patches_per_dim[1] * patches_per_dim[2]
            total_patches += view_patches

        processed_patches = 0

        # Load and run each view model
        for view_idx, view in enumerate(views):
            if view not in self.onnx_paths or not os.path.exists(self.onnx_paths[view]):
                continue

            # Load ONNX model
            session = ort.InferenceSession(
                str(self.onnx_paths[view]), providers=ep_list, sess_options=session_options
            )

            input_name = session.get_inputs()[0].name

            view_pred = np.zeros_like(agg_pred)

            # Generate and process patches
            for patch, patch_info in self._gen_patches(norm_image, self.patch_size, self.overlap):
                # Prepare input for the specific view
                if view == "axial":
                    input_patch = patch.transpose(2, 0, 1)  # [D, H, W] -> [W, D, H]
                elif view == "coronal":
                    input_patch = patch.transpose(1, 0, 2)  # [D, H, W] -> [H, D, W]
                else:  # sagittal
                    input_patch = patch  # [D, H, W]

                # Add batch and channel dimensions [B, C, D, H, W]
                input_patch = np.expand_dims(np.expand_dims(input_patch, 0), 0).astype(np.float32)

                # Run inference
                outputs = session.run(None, {input_name: input_patch})

                # Get softmax output
                patch_pred = outputs[0][0]  # Remove batch dimension

                # Convert back to original orientation
                if view == "axial":
                    patch_pred = patch_pred.transpose(1, 2, 0, 3)  # [C, W, D, H] -> [C, D, H, W]
                elif view == "coronal":
                    patch_pred = patch_pred.transpose(1, 0, 2, 3)  # [C, H, D, W] -> [C, D, H, W]

                # Get spatial dimensions back
                z_start, z_end = patch_info["z_start"], patch_info["z_end"]
                y_start, y_end = patch_info["y_start"], patch_info["y_end"]
                x_start, x_end = patch_info["x_start"], patch_info["x_end"]

                # Store valid part back to the volume
                z_size = z_end - z_start
                y_size = y_end - y_start
                x_size = x_end - x_start

                # Transpose to [D, H, W, C] format for storage
                patch_pred = patch_pred.transpose(1, 2, 3, 0)

                # Store patch prediction
                view_pred[z_start:z_end, y_start:y_end, x_start:x_end, :] = patch_pred[
                    :z_size, :y_size, :x_size, :
                ]

                # Update progress
                processed_patches += 1
                progress = processed_patches / total_patches * 100
                comm_array[0] = progress

            # Aggregate predictions
            agg_pred += view_pred

        # Average predictions and get the most likely class for each voxel
        agg_pred /= len(views)
        seg_result = np.argmax(agg_pred, axis=-1)

        # Resize back to original size if needed
        if probability_array.shape != seg_result.shape:
            seg_result = resize(
                seg_result,
                output_shape=probability_array.shape,
                order=0,  # Nearest-neighbor interpolation for labels
                preserve_range=True,
            )

        # Store result in the output array
        probability_array[:] = seg_result

        # Signal completion
        comm_array[0] = 100.0

    def apply_segment_threshold(self, threshold=0.5):
        """
        Apply threshold to segmentation results and create masks.
        Overrides the base class method to handle multiple mask types.

        Parameters
        ----------
        threshold : float, optional
            Threshold value (not used for label-based segmentation)
        """
        # Create output processor to handle mask creation
        output_processor = FastSurferOutputProcessor(
            self._probability_array, self.onnx_dir, selected_mask_types=self.selected_mask_types
        )

        # Apply masks to InVesalius
        self.masks = output_processor.apply_masks_to_invesalius(
            create_new_mask=self.create_new_mask
        )

    def _create_default_masks(self):
        """
        Create default masks if the LUT file is not available.
        Uses simple thresholding to create a single mask.
        """
        # Use output processor to create a default mask
        output_processor = FastSurferOutputProcessor(self._probability_array, self.onnx_dir)

        # Apply a simple mask
        self.masks = output_processor.apply_masks_to_invesalius(
            create_new_mask=self.create_new_mask
        )


class FastSurferOutputProcessor:
    """
    Process the output from FastSurferCNN segmentation and create
    appropriate masks in InVesalius.

    This class handles loading the LUT, determining label types,
    creating binary masks for selected anatomical structures,
    and integrating with InVesalius mask system.
    """

    def __init__(self, label_volume, onnx_dir, selected_mask_types=None):
        """
        Initialize the output processor.

        Parameters
        ----------
        label_volume : np.ndarray
            3D volume of integer labels from FastSurferCNN
        onnx_dir : pathlib.Path
            Directory containing ONNX models and LUT
        selected_mask_types : list, optional
            List of selected mask types to generate
        """
        self.label_volume = label_volume
        self.onnx_dir = onnx_dir

        # Mask types mapping
        self.mask_types = {
            "cortical_dkt": "cortical",
            "subcortical_gm": "subcortical",
            "white_matter": "white_matter",
            "csf": "csf",
        }

        # Selected mask types
        self.selected_mask_types = selected_mask_types or list(self.mask_types.keys())

        # Path to FreeSurfer Color LUT
        self.lut_path = self.onnx_dir.joinpath("FastSurfer_ColorLUT.tsv")
        self.lut_data = None

        # Store created masks
        self.masks = {}

    def load_lut(self):
        """
        Load the FreeSurfer Color LUT file.

        Returns
        -------
        dict
            Dictionary mapping label IDs to label information
        """
        if not self.lut_path.exists():
            raise FileNotFoundError(f"FastSurfer Color LUT file not found at {self.lut_path}")

        lut_data = {}
        with open(self.lut_path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.strip().split()
                if len(parts) >= 5:  # Make sure we have enough parts
                    label_id = int(parts[0])
                    label_name = parts[1]
                    r, g, b = int(parts[2]), int(parts[3]), int(parts[4])
                    lut_data[label_id] = {
                        "name": label_name,
                        "color": (r, g, b),
                        "type": self._determine_label_type(label_name, label_id),
                    }

        self.lut_data = lut_data
        return lut_data

    def _determine_label_type(self, label_name, label_id):
        """
        Determine the type of the label (cortical, subcortical, etc.).

        Parameters
        ----------
        label_name : str
            Name of the label
        label_id : int
            ID of the label

        Returns
        -------
        str
            Type of the label
        """
        # Commonly used classification logic
        if any(term in label_name.lower() for term in ["ctx", "cortex"]):
            return "cortical"
        elif any(term in label_name.lower() for term in ["wm", "white"]):
            return "white_matter"
        elif "csf" in label_name.lower():
            return "csf"
        elif (
            label_id > 0 and label_id < 100
        ):  # Subcortical structures typically have IDs in this range
            return "subcortical"
        else:
            return "other"

    def _create_binary_mask(self, label_ids=None):
        """
        Create a binary mask from the given label IDs.
        If no label IDs are provided, creates a mask for all non-zero labels.

        Parameters
        ----------
        label_ids : list, optional
            List of label IDs to include in the mask

        Returns
        -------
        np.ndarray
            Binary mask as a uint8 array with values 0 and 255
        """
        # Create binary mask
        binary_mask = np.zeros(self.label_volume.shape, dtype=np.uint8)

        if label_ids is None:
            # Include all non-zero labels
            binary_mask[self.label_volume > 0] = 1
        else:
            # Include only specified labels
            for label in label_ids:
                binary_mask[self.label_volume == label] = 1

        # Convert to 0-255 scale
        return binary_mask * 255

    def create_whole_brain_mask(self):
        """
        Create a binary mask for the whole brain (all non-zero labels).

        Returns
        -------
        np.ndarray
            Binary mask as a uint8 array with values 0 and 255
        """
        # Create mask from all non-zero labels
        return self._create_binary_mask()

    def create_subpart_masks(self):
        """
        Create binary masks for each selected anatomical type.

        Returns
        -------
        dict
            Dictionary of binary masks by type
        """
        if self.lut_data is None:
            try:
                self.load_lut()
            except FileNotFoundError:
                # Create default mask if LUT not available
                return {}

        # Create masks for each selected type
        binary_masks = {}
        for mask_type in self.selected_mask_types:
            # Get all labels of this type
            type_key = self.mask_types.get(mask_type, "other")
            type_labels = [
                label_id for label_id, info in self.lut_data.items() if info["type"] == type_key
            ]

            # Create binary mask for this type
            binary_mask = self._create_binary_mask(type_labels)

            # Only include mask if it has any foreground voxels
            if np.any(binary_mask):
                binary_masks[mask_type] = binary_mask

        return binary_masks

    def _create_default_binary_mask(self):
        """
        Create a default binary mask if the LUT file is not available.
        Simply treats any non-zero label as foreground.

        Returns
        -------
        dict
            Dictionary with a single binary mask
        """
        binary_mask = self.create_whole_brain_mask()
        return {"combined": binary_mask}

    def apply_masks_to_invesalius(self, create_new_mask=True):
        """
        Apply the binary masks to InVesalius.
        Always creates a whole brain mask, plus any selected subpart masks.

        Parameters
        ----------
        create_new_mask : bool, optional
            Whether to create new masks or use existing ones

        Returns
        -------
        dict
            Dictionary of created masks
        """
        # Create whole brain mask
        whole_brain_mask = self.create_whole_brain_mask()

        # Create subpart masks
        subpart_masks = self.create_subpart_masks()

        # Combine all masks
        all_masks = {"whole_brain": whole_brain_mask}
        all_masks.update(subpart_masks)

        # Apply each mask to InVesalius
        created_masks = {}
        for mask_type, binary_mask in all_masks.items():
            # Create a new mask or use current
            if create_new_mask:
                name = new_name_by_pattern(f"fastsurfer_{mask_type}")
                mask = slc.Slice().create_new_mask(name=name)
            else:
                mask = slc.Slice().current_mask
                if mask is None:
                    name = new_name_by_pattern(f"fastsurfer_{mask_type}")
                    mask = slc.Slice().create_new_mask(name=name)

            # Apply the binary mask
            mask.was_edited = True
            mask.matrix[1:, 1:, 1:] = binary_mask
            mask.modified(True)

            # Store mask reference
            created_masks[mask_type] = mask

        self.masks = created_masks
        return created_masks
