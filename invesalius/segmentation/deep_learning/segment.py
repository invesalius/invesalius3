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
    comm_array[0] = np.inf


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
