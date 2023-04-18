import numpy as np
from typing import Tuple
from scipy import ndimage
from scipy.ndimage import watershed_ift, generate_binary_structure
try:
    from skimage.segmentation import watershed
except ImportError:
    from skimage.morphology import watershed

def get_LUT_value(data: np.ndarray, window: int, level: int) -> np.ndarray:
    shape: Tuple[int, ...] = data.shape
    data_ = data.ravel()
    data = np.piecewise(data_,
                        [data_ <= (level - 0.5 - (window-1)/2),
                         data_ > (level - 0.5 + (window-1)/2)],
                        [0, window, lambda data_: ((data_ - (level - 0.5))/(window-1) + 0.5)*(window)])
    data.shape = shape
    return data


def do_watershed(image: np.ndarray, markers: np.ndarray,  tfile: str, shape: tuple, bstruct: np.ndarray, algorithm: str, mg_size: int, use_ww_wl: bool, wl: int, ww: int, q: queue.Queue) -> None:
    mask = np.memmap(tfile, shape=shape, dtype='uint8', mode='r+')
                
    if use_ww_wl:
        if algorithm == 'Watershed':
            tmp_image = ndimage.morphological_gradient(
                           get_LUT_value(image, ww, wl).astype('uint16'),
                           mg_size)
            tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
        else:
            tmp_image = get_LUT_value(image, ww, wl).astype('uint16')
            #tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
            #tmp_image = ndimage.morphological_gradient(
                           #get_LUT_value(image, ww, wl).astype('uint16'),
                           #self.config.mg_size)
            tmp_mask = watershed_ift(tmp_image, markers.astype('int16'), bstruct)
    else:
        if algorithm == 'Watershed':
            tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), mg_size)
            tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
        else:
            tmp_image = (image - image.min()).astype('uint16')
            #tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
            #tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
            tmp_mask = watershed_ift(tmp_image, markers.astype('int8'), bstruct)
    mask[:] = tmp_mask
    mask.flush()
    q.put(1)
    