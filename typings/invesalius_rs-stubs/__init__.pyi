"""Type stubs for invesalius_rs module."""

from typing import Iterable

import numpy as np
from numpy.typing import NDArray
from vtkmodules.vtkCommonDataModel import vtkPolyData

# Interpolation functions
def trilin_interpolate_py(v: NDArray[np.int16], x: float, y: float, z: float) -> float: ...
def nearest_neighbour_interp(v: NDArray[np.int16], x: float, y: float, z: float) -> float: ...
def tricub_interpolate_py(v: NDArray[np.int16], x: float, y: float, z: float) -> float: ...
def tricub_interpolate2_py(v: NDArray[np.int16], x: float, y: float, z: float) -> float: ...
def lanczos_interpolate_py(v: NDArray[np.int16], x: float, y: float, z: float) -> float: ...

# Floodfill functions
def floodfill(
    data: NDArray[np.int16],
    i: int,
    j: int,
    k: int,
    v: int,
    fill: int,
    out: NDArray[np.uint8],
) -> None: ...
def floodfill_threshold(
    data: NDArray[np.int16],
    seeds: list[tuple[int, int, int]],
    t0: int,
    t1: int,
    fill: int,
    strct: NDArray[np.uint8],
    out: NDArray[np.uint8],
) -> None: ...
def floodfill_auto_threshold(
    data: NDArray[np.int16],
    seeds: list[tuple[int, int, int]],
    p: float,
    fill: int,
    out: NDArray[np.uint8],
) -> None: ...
def fill_holes_automatically(
    mask: NDArray[np.uint8],
    labels: NDArray[np.uint16],
    nlabels: int,
    max_size: int,
) -> bool: ...

# MIPS functions
def lmip(
    image: NDArray[np.int16],
    axis: int,
    tmin: int,
    tmax: int,
    out: NDArray[np.int16],
) -> None: ...
def mida(
    image: NDArray[np.int16],
    axis: int,
    wl: int,
    ww: int,
    out: NDArray[np.int16],
) -> None: ...
def fast_countour_mip(
    image: NDArray[np.int16],
    n: float,
    axis: int,
    wl: int,
    ww: int,
    tmip: int,
    out: NDArray[np.int16],
) -> None: ...

# Transform functions
def apply_view_matrix_transform(
    volume: NDArray[np.int16],
    spacing: tuple[float, float, float],
    M: NDArray[np.float64],
    n: int,
    orientation: str,
    minterpol: int,
    cval: int,
    out: NDArray[np.int16],
) -> None: ...
def convolve_non_zero(
    volume: NDArray[np.int16],
    kernel: NDArray[np.int16],
    cval: int,
) -> NDArray[np.int16]: ...

# Mask cut function
def mask_cut(
    image: NDArray[np.int16],
    x_coords: NDArray[np.int32],
    y_coords: NDArray[np.int32],
    z_coords: NDArray[np.int32],
    sx: float,
    sy: float,
    sz: float,
    max_depth: float,
    mask: NDArray[np.uint8],
    M: NDArray[np.float64],
    MV: NDArray[np.float64],
    out: NDArray[np.int16],
) -> None: ...

# Mesh class
class Mesh:
    """Mesh class for 3D mesh manipulation and smoothing."""

    def __init__(
        self,
        pd: vtkPolyData | None = None,
        other: "Mesh | None" = None,
        vertices: NDArray[np.float32] | None = None,
        faces: NDArray[np.int64] | None = None,
        normals: NDArray[np.float32] | None = None,
    ) -> None: ...
    @property
    def vertices(self) -> NDArray[np.float32]: ...
    @property
    def faces(self) -> NDArray[np.int64]: ...
    @property
    def normals(self) -> NDArray[np.float32]: ...
    def to_vtk(self) -> vtkPolyData:
        """Convert Mesh to vtkPolyData."""
        ...

    def ca_smoothing(self, T: float, tmax: float, bmin: float, n_iters: int) -> None:
        """
        Apply context-aware mesh smoothing.

        Parameters
        ----------
        T : float
            Min angle threshold for staircase artifact detection
        tmax : float
            Max distance for weight calculation
        bmin : float
            Minimum weight
        n_iters : int
            Number of smoothing iterations
        """
        ...

def ca_smoothing(mesh: Mesh, T: float, tmax: float, bmin: float, n_iters: int) -> None:
    """
    Apply context-aware mesh smoothing (function interface for compatibility).

    Parameters
    ----------
    mesh : Mesh
        Mesh object to smooth (modified in place)
    T : float
        Min angle threshold for staircase artifact detection
    tmax : float
        Max distance for weight calculation
    bmin : float
        Minimum weight
    n_iters : int
        Number of smoothing iterations
    """
    ...
