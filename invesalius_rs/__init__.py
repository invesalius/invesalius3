# InVesalius Rust Extension Module
# This module provides high-performance implementations of critical algorithms
# Originally implemented in Cython, now ported to Rust using PyO3

import numpy as np
import warnings

# --------------------------------------------------
# Safe import of Rust native backend
# --------------------------------------------------
try:
    from invesalius_rs import _native
except Exception as exc:
    _native = None
    warnings.warn(
        "Rust native backend not available. "
        "Some features will be disabled.\n"
        f"Reason: {exc}",
        RuntimeWarning,
    )


def _require_native(name: str):
    if _native is None:
        raise RuntimeError(f"Rust backend required for {name}")


# --------------------------------------------------
# Re-exported / wrapped native functions (SAFE)
# --------------------------------------------------
def floodfill(*args, **kwargs):
    _require_native("floodfill")
    return _native.floodfill(*args, **kwargs)


def fill_holes_automatically(*args, **kwargs):
    _require_native("fill_holes_automatically")
    return _native.fill_holes_automatically(*args, **kwargs)


def apply_view_matrix_transform(*args, **kwargs):
    _require_native("apply_view_matrix_transform")
    return _native.apply_view_matrix_transform(*args, **kwargs)


def convolve_non_zero(*args, **kwargs):
    _require_native("convolve_non_zero")
    return _native.convolve_non_zero(*args, **kwargs)


def _context_aware_smoothing(*args, **kwargs):
    _require_native("context_aware_smoothing")
    return _native.context_aware_smoothing(*args, **kwargs)


# --------------------------------------------------
# Floodfill wrappers (ORIGINAL LOGIC PRESERVED)
# --------------------------------------------------
def floodfill_threshold(data, seeds, t0, t1, fill, strct, out):
    tuple_seeds = [tuple(s) for s in seeds]
    strct_u8 = np.ascontiguousarray(strct, dtype=np.uint8)

    if data.dtype in [
        np.int16, np.uint16, np.int32, np.uint32, np.int64, np.uint64
    ]:
        t0 = int(t0)
        t1 = int(t1)
        fill = int(fill)
    elif data.dtype in [np.float32, np.float64]:
        t0 = float(t0)
        t1 = float(t1)
        fill = float(fill)

    _require_native("floodfill_threshold")
    return _native.floodfill_threshold(
        data, tuple_seeds, t0, t1, fill, strct_u8, out
    )


def floodfill_threshold_inplace(data, seeds, t0, t1, fill, strct):
    tuple_seeds = [tuple(s) for s in seeds]
    strct_u8 = np.ascontiguousarray(strct, dtype=np.uint8)

    _require_native("floodfill_threshold_inplace")
    return _native.floodfill_threshold_inplace(
        data, tuple_seeds, t0, t1, fill, strct_u8
    )


def floodfill_auto_threshold(data, seeds, p, fill, out):
    tuple_seeds = [tuple(s) for s in seeds]

    _require_native("floodfill_auto_threshold")
    return _native.floodfill_auto_threshold(
        data, tuple_seeds, p, fill, out
    )


# --------------------------------------------------
# Mask / 3D operations
# --------------------------------------------------
def mask_cut(*args, **kwargs):
    _require_native("mask_cut")
    return _native.mask_cut(*args, **kwargs)


# --------------------------------------------------
# MIPS / Image processing
# --------------------------------------------------
def mida(image: np.ndarray, axis: int, wl: int, ww: int, out: np.ndarray):
    _require_native("mida")
    return _native.mida(image, axis, int(wl), int(ww), out)


def fast_countour_mip(
    image: np.ndarray, n: float, axis: int, wl: int, ww: int, tmip: int, out: np.ndarray
):
    _require_native("fast_countour_mip")
    return _native.fast_countour_mip(
        image, n, axis, int(wl), int(ww), tmip, out
    )


# --------------------------------------------------
# Mesh class (UNCHANGED API)
# --------------------------------------------------
class Mesh:
    """
    Mesh wrapper class compatible with the original cy_mesh.Mesh interface.
    Accepts either a vtkPolyData object or numpy arrays.
    """

    def __init__(self, pd=None, other=None, vertices=None, faces=None, normals=None):
        _require_native("Mesh")

        if pd is not None:
            from vtkmodules.util import numpy_support

            self._vertices = numpy_support.vtk_to_numpy(
                pd.GetPoints().GetData()
            ).reshape(-1, 3)

            self._faces = numpy_support.vtk_to_numpy(
                pd.GetPolys().GetData()
            ).reshape(-1, 4)

            self._normals = numpy_support.vtk_to_numpy(
                pd.GetCellData().GetArray("Normals")
            ).reshape(-1, 3)

        elif other is not None:
            if isinstance(other, Mesh):
                self._vertices = np.ascontiguousarray(other.vertices.copy())
                self._faces = np.ascontiguousarray(other.faces.copy())
                self._normals = np.ascontiguousarray(other.normals.copy())
            else:
                raise TypeError("other must be a Mesh instance")

        elif vertices is not None and faces is not None and normals is not None:
            self._vertices = np.ascontiguousarray(vertices)
            self._faces = np.ascontiguousarray(faces)
            self._normals = np.ascontiguousarray(normals)
        else:
            raise ValueError("Must provide either pd, other, or (vertices, faces, normals)")

    @property
    def vertices(self):
        return self._vertices

    @property
    def faces(self):
        return self._faces

    @property
    def normals(self):
        return self._normals

    def to_vtk(self):
        from vtkmodules.util import numpy_support
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

        points = vtkPoints()
        points.SetData(numpy_support.numpy_to_vtk(self.vertices))

        triangles = vtkCellArray()
        triangles.SetCells(
            self.faces.shape[0],
            numpy_support.numpy_to_vtkIdTypeArray(self.faces.flatten()),
        )

        pd = vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(triangles)
        return pd

    def ca_smoothing(self, T, tmax, bmin, n_iters):
        _context_aware_smoothing(
            self._vertices, self._faces, self._normals,
            T, tmax, bmin, n_iters
        )


def ca_smoothing(mesh, T, tmax, bmin, n_iters):
    mesh.ca_smoothing(T, tmax, bmin, n_iters)


__all__ = [
    "floodfill",
    "floodfill_threshold",
    "floodfill_auto_threshold",
    "fill_holes_automatically",
    "mida",
    "fast_countour_mip",
    "apply_view_matrix_transform",
    "convolve_non_zero",
    "mask_cut",
    "Mesh",
    "ca_smoothing",
]

