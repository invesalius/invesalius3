from typing import TYPE_CHECKING, Tuple

import numpy as np
from scipy import ndimage
from scipy.ndimage import watershed_ift

from invesalius.data.imagedata_utils import get_LUT_value

try:
    from skimage.segmentation import watershed
except ImportError:
    from skimage.morphology import watershed

if TYPE_CHECKING:
    import os
    from multiprocessing import Queue


def do_watershed(
    image: np.ndarray,
    markers: np.ndarray,
    tfile: "str | bytes | os.PathLike[str]",
    shape: "int | tuple[int, ...] | None",
    bstruct: "int | np.ndarray | None",
    algorithm: str,
    mg_size: Tuple[int, ...],
    use_ww_wl: bool,
    wl: int,
    ww: int,
    q: "Queue[int]",
) -> None:
    mask = np.memmap(tfile, shape=shape, dtype="uint8", mode="r+")

    if use_ww_wl:
        if algorithm == "Watershed":
            tmp_image = ndimage.morphological_gradient(
                get_LUT_value(image, ww, wl).astype("uint16"), mg_size
            )
            tmp_mask = watershed(tmp_image, markers.astype("int16"), bstruct)
        else:
            tmp_image = get_LUT_value(image, ww, wl).astype("uint16")
            # tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
            # tmp_image = ndimage.morphological_gradient(
            # get_LUT_value(image, ww, wl).astype('uint16'),
            # self.config.mg_size)
            tmp_mask = watershed_ift(tmp_image, markers.astype("int16"), bstruct)
    else:
        if algorithm == "Watershed":
            tmp_image = ndimage.morphological_gradient(
                (image - image.min()).astype("uint16"), mg_size
            )
            tmp_mask = watershed(tmp_image, markers.astype("int16"), bstruct)
        else:
            tmp_image = (image - image.min()).astype("uint16")
            # tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
            # tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
            tmp_mask = watershed_ift(tmp_image, markers.astype("int8"), bstruct)
    mask[:] = tmp_mask
    mask.flush()
    q.put(1)
