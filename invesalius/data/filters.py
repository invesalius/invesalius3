import numpy as np
import scipy.ndimage as ndimage


def gaussian_blur_filter(matrix: np.ndarray, sigma: float) -> np.ndarray:
    return ndimage.gaussian_filter(matrix, sigma=sigma)


def median_blur_filter(matrix: np.ndarray, value: float) -> np.ndarray:
    # Median Filter (3D, capped at size 5)
    size = max(3, min(int(2 * value + 1), 5))
    return ndimage.median_filter(matrix, size=size)


def mean_blur_filter(matrix: np.ndarray, value: float) -> np.ndarray:
    # Mean Filter (fast separable 3D)
    size = int(2 * value + 1)
    return ndimage.uniform_filter(matrix, size=size).astype(matrix.dtype)


def sharpening_filter(matrix: np.ndarray, value: float) -> np.ndarray:
    # Sharpen via Unsharp Masking
    dtype = matrix.dtype
    min_val, max_val = matrix.min(), matrix.max()
    float_matrix = matrix.astype(float)
    blurred = ndimage.gaussian_filter(float_matrix, sigma=1.0)
    detail = float_matrix - blurred
    sharpened = float_matrix + value * 0.5 * detail
    return np.clip(sharpened, min_val, max_val).astype(dtype)


def despeckle_filter(matrix: np.ndarray, value: float) -> np.ndarray:
    """Gaussian-based speckle reduction.
    Uses 'value' as the sigma for Gaussian smoothing to remove high-frequency noise.
    """
    return ndimage.gaussian_filter(matrix, sigma=value)


def border_detection_filter(matrix: np.ndarray, value: float = 1.0) -> np.ndarray:
    """Sobel gradient magnitude with Gaussian pre-smoothing.
    Uses 'value' as the sigma for the pre-smoothing step to control noise sensitivity.
    """
    dtype = matrix.dtype
    # Pre-smooth to reduce noise in edges (using the 'kernel size' parameter)
    float_matrix = ndimage.gaussian_filter(matrix.astype(float), sigma=value)

    sx = ndimage.sobel(float_matrix, axis=0)
    sy = ndimage.sobel(float_matrix, axis=1)
    sz = ndimage.sobel(float_matrix, axis=2)
    magnitude = np.sqrt(sx**2 + sy**2 + sz**2)

    min_val, max_val = float(matrix.min()), float(matrix.max())
    mag_min = magnitude.min()
    mag_range = magnitude.max() - mag_min

    if mag_range > 0:
        magnitude = (magnitude - mag_min) / mag_range * (max_val - min_val) + min_val
    return magnitude.astype(dtype)
