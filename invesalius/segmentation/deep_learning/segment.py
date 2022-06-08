import itertools
import multiprocessing
import os
import pathlib
import sys
import tempfile
import traceback

import numpy as np
from skimage.transform import resize

import invesalius.data.slice_ as slc
from invesalius import inv_paths
from invesalius.data import imagedata_utils
from invesalius.utils import new_name_by_pattern
from invesalius.net.utils import download_url_to_file
from invesalius import inv_paths

from . import utils

SIZE = 48


def gen_patches(image, patch_size, overlap):
    overlap = int(patch_size * overlap / 100)
    print(f"{overlap=}")
    sz, sy, sx = image.shape
    i_cuts = list(
        itertools.product(
            range(0, sz, patch_size - overlap),
            range(0, sy, patch_size - overlap),
            range(0, sx, patch_size - overlap),
        )
    )
    sub_image = np.empty(shape=(patch_size, patch_size, patch_size), dtype="float32")
    for idx, (iz, iy, ix) in enumerate(i_cuts):
        sub_image[:] = 0
        _sub_image = image[
            iz : iz + patch_size, iy : iy + patch_size, ix : ix + patch_size
        ]
        sz, sy, sx = _sub_image.shape
        sub_image[0:sz, 0:sy, 0:sx] = _sub_image
        ez = iz + sz
        ey = iy + sy
        ex = ix + sx

        yield (idx + 1.0) / len(i_cuts), sub_image, ((iz, ez), (iy, ey), (ix, ex))


def predict_patch(sub_image, patch, nn_model, patch_size=SIZE):
    (iz, ez), (iy, ey), (ix, ex) = patch
    sub_mask = nn_model.predict(
        sub_image.reshape(1, patch_size, patch_size, patch_size, 1)
    )
    return sub_mask.reshape(patch_size, patch_size, patch_size)[
        0 : ez - iz, 0 : ey - iy, 0 : ex - ix
    ]

def predict_patch_torch(sub_image, patch, nn_model, device, patch_size=SIZE):
    import torch
    with torch.no_grad():
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = nn_model(
            torch.from_numpy(sub_image.reshape(1, 1, patch_size, patch_size, patch_size)).to(device)
        ).cpu().numpy()
        return sub_mask.reshape(patch_size, patch_size, patch_size)[
            0 : ez - iz, 0 : ey - iy, 0 : ex - ix
        ]


def brain_segment(image, overlap, probability_array, comm_array):
    import keras

    # Loading model
    folder = inv_paths.MODELS_DIR.joinpath("brain_mri_t1")
    with open(folder.joinpath("model.json"), "r") as json_file:
        model = keras.models.model_from_json(json_file.read())
    model.load_weights(str(folder.joinpath("model.h5")))
    model.compile("Adam", "binary_crossentropy")

    image = imagedata_utils.image_normalize(image, 0.0, 1.0, output_dtype=np.float32)
    sums = np.zeros_like(image)
    # segmenting by patches
    for completion, sub_image, patch in gen_patches(image, SIZE, overlap):
        comm_array[0] = completion
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = predict_patch(sub_image, patch, model, SIZE)
        probability_array[iz:ez, iy:ey, ix:ex] += sub_mask
        sums[iz:ez, iy:ey, ix:ex] += 1

    probability_array /= sums
    comm_array[0] = np.Inf


def download_callback(comm_array):
    def _download_callback(value):
        comm_array[0] = value
    return _download_callback

def brain_segment_torch(image, overlap, device_id, probability_array, comm_array):
    import torch
    from .model import Unet3D
    device = torch.device(device_id)
    folder = inv_paths.MODELS_DIR.joinpath("brain_mri_t1")
    system_state_dict_file = folder.joinpath("brain_mri_t1.pt")
    user_state_dict_file = inv_paths.USER_DL_WEIGHTS.joinpath("brain_mri_t1.pt")
    if not system_state_dict_file.exists() and not user_state_dict_file.exists():
        download_url_to_file(
                "https://github.com/tfmoraes/deepbrain_torch/releases/download/v1.1.0/weights.pt",
                user_state_dict_file,
                "194b0305947c9326eeee9da34ada728435a13c7b24015cbd95971097fc178f22",
                download_callback(comm_array)
                )
    if user_state_dict_file.exists():
        state_dict = torch.load(str(user_state_dict_file))
    elif system_state_dict_file.exists():
        state_dict = torch.load(str(system_state_dict_file))
    else:
         raise FileNotFoundError("Weights file not found")
    model = Unet3D()
    model.load_state_dict(state_dict["model_state_dict"])
    model.to(device)
    model.eval()

    image = imagedata_utils.image_normalize(image, 0.0, 1.0, output_dtype=np.float32)
    sums = np.zeros_like(image)
    # segmenting by patches
    for completion, sub_image, patch in gen_patches(image, SIZE, overlap):
        comm_array[0] = completion
        (iz, ez), (iy, ey), (ix, ex) = patch
        sub_mask = predict_patch_torch(sub_image, patch, model, device, SIZE)
        probability_array[iz:ez, iy:ey, ix:ex] += sub_mask
        sums[iz:ez, iy:ey, ix:ex] += 1

    probability_array /= sums
    comm_array[0] = np.Inf

ctx = multiprocessing.get_context('spawn')
class SegmentProcess(ctx.Process):
    def __init__(self, image, create_new_mask, backend, device_id, use_gpu, overlap=50, apply_wwwl=False, window_width=255, window_level=127):
        multiprocessing.Process.__init__(self)

        self._image_filename = image.filename
        self._image_dtype = image.dtype
        self._image_shape = image.shape

        self._probability_array = np.memmap(
            tempfile.mktemp(), shape=image.shape, dtype=np.float32, mode="w+"
        )
        self._prob_array_filename = self._probability_array.filename

        self._comm_array = np.memmap(
            tempfile.mktemp(), shape=(1,), dtype=np.float32, mode="w+"
        )
        self._comm_array_filename = self._comm_array.filename

        self.create_new_mask = create_new_mask
        self.backend = backend
        self.device_id = device_id
        self.use_gpu = use_gpu

        self.overlap = overlap

        self.apply_wwwl = apply_wwwl
        self.window_width = window_width
        self.window_level = window_level

        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

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
        comm_array = np.memmap(
            self._comm_array_filename, dtype=np.float32, shape=(1,), mode="r+"
        )

        if self.backend.lower() == "pytorch":
            brain_segment_torch(image, self.overlap, self.device_id, probability_array, comm_array)
        else:
            utils.prepare_ambient(self.backend, self.device_id, self.use_gpu)
            brain_segment(image, self.overlap, probability_array, comm_array)

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
        os.remove(self._comm_array_filename)

        del self._probability_array
        os.remove(self._prob_array_filename)
