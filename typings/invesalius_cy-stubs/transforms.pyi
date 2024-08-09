import numpy as np

def convolve_non_zero(volume: np.ndarray, kernel: np.ndarray, cval: float) -> np.ndarray: ...
def apply_view_matrix_transform(
    volume: np.ndarray,
    spacing,
    M: np.ndarray,
    n: int,
    orientation: str,
    minterpol: int,
    cval: float,
    out: np.ndarray,
) -> None: ...
