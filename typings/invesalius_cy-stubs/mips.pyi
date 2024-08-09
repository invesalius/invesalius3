import numpy as np

DTYPE = np.uint8
DTYPE16 = np.uint16
DTYPEF32 = np.float32
DTYPE16_t = int

def lmip(
    image: np.ndarray, axis: int, tmin: DTYPE16_t, tmax: DTYPE16_t, out: np.ndarray
) -> None: ...
def mida(image: np.ndarray, axis: int, wl: DTYPE16_t, ww: DTYPE16_t, out: np.ndarray) -> None: ...
def fast_countour_mip(
    image: np.ndarray, n: float, axis: int, wl: DTYPE16_t, ww: DTYPE16_t, tmip: int, out: np.ndarray
) -> None: ...
