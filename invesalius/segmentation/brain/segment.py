import sys
import pathlib

from skimage.transform import resize
from invesalius.data import imagedata_utils

import keras

SIZE = 64


def load_model():
    folder = pathlib.Path(__file__).parent.resolve()
    with open(folder.joinpath("model.json"), "r") as json_file:
        model = keras.models.model_from_json(json_file.read())
    model.load_weights(str(folder.joinpath("model.h5")))
    model.compile("Adam", "mean_squared_error")
    return model


def segment(image, mask):
    img = resize(image, (SIZE, SIZE, SIZE), mode="constant", anti_aliasing=True)
    img = imagedata_utils.image_normalize(img)
    img = img.astype("float32").reshape(1, SIZE, SIZE, SIZE, 1)

    nn_model = load_model()
    msk = nn_model.predict(img)
    msk = resize(
        msk.reshape(SIZE, SIZE, SIZE), image.shape, mode="constant", anti_aliasing=True
    )
    print(img.min(), img.max(), msk.min(), msk.max())
    msk = (msk >= 0.5) * 255
    mask.matrix[:] = 1
    mask.matrix[1:, 1:, 1:] = msk

