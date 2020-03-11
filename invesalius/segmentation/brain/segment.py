import itertools
import os
import pathlib
import sys

from . import utils

os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
os.environ["RUNFILES_DIR"] = str(pathlib.Path("~/.local/share/plaidml/").expanduser().absolute())
os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("~/.local/lib/libplaidml.so").expanduser().absolute())

device = utils.get_plaidml_devices(True)

os.environ["PLAIDML_DEVICE_IDS"] = device.id.decode("utf8")
os.environ["PLAIDML_STRIPE_JIT"] = "1"
os.environ["PLAIDML_USE_STRIPE"] = "1"

import keras
import numpy as np
from skimage.transform import resize

from invesalius.data import imagedata_utils
from invesalius.utils import timing

SIZE = 48
OVERLAP = SIZE // 2 + 1


def gen_patches(image, patch_size, overlap):
    sz, sy, sx = image.shape
    i_cuts = list(itertools.product(
        range(0, sz, patch_size - OVERLAP),
        range(0, sy, patch_size - OVERLAP),
        range(0, sx, patch_size - OVERLAP),
    ))
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

        yield (idx + 1.0)/len(i_cuts), sub_image, ((iz, ez), (iy, ey), (ix, ex))


def predict_patch(sub_image, patch, nn_model, patch_size=SIZE):
    (iz, ez), (iy, ey), (ix, ex) = patch
    sub_mask = nn_model.predict(sub_image.reshape(1, patch_size, patch_size, patch_size, 1))
    return sub_mask.reshape(patch_size, patch_size, patch_size)[0:ez-iz, 0:ey-iy, 0:ex-ix]


class BrainSegmenter:
    def __init__(self):
        self.mask = None
        self.propability_array = None

    def segment(self, image, prob_threshold, backend, use_gpu, progress_callback=None):
        if backend.lower() == 'plaidml':
            os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
            os.environ["RUNFILES_DIR"] = str(pathlib.Path("~/.local/share/plaidml/").expanduser().absolute())
            os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("~/.local/lib/libplaidml.so").expanduser().absolute())
            device = utils.get_plaidml_devices(use_gpu)
            os.environ["PLAIDML_DEVICE_IDS"] = device.id.decode("utf8")
            os.environ["PLAIDML_STRIPE_JIT"] = "1"
            os.environ["PLAIDML_USE_STRIPE"] = "1"
        elif backend.lower() == 'theano':
            os.environ["KERAS_BACKEND"] = "theano"
        else:
            raise TypeError("Wrong backend")

        import keras
        import invesalius.data.slice_ as slc

        image = imagedata_utils.image_normalize(image, 0.0, 1.0)

        # Loading model
        folder = pathlib.Path(__file__).parent.resolve()
        with open(folder.joinpath("model.json"), "r") as json_file:
            model = keras.models.model_from_json(json_file.read())
        model.load_weights(str(folder.joinpath("model.h5")))
        model.compile("Adam", "binary_crossentropy")

        # segmenting by patches
        msk = np.zeros_like(image, dtype="float32")
        sums = np.zeros_like(image)
        for completion, sub_image, patch in gen_patches(image, SIZE, OVERLAP):
            if progress_callback is not None:
                progress_callback(completion)
            print("completion", completion)
            (iz, ez), (iy, ey), (ix, ex) = patch
            sub_mask = predict_patch(sub_image, patch, model, SIZE)
            msk[iz:ez, iy:ey, ix:ex] += sub_mask
            sums[iz:ez, iy:ey, ix:ex] += 1

        propability_array = msk / sums

        mask = slc.Slice().create_new_mask()
        mask.was_edited = True
        mask.matrix[:] = 1
        mask.matrix[1:, 1:, 1:] = ((msk / sums) > prob_threshold) * 255

        self.mask = mask
        self.propability_array = propability_array
