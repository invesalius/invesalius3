# InVesalius Rust Extension Module
# This module provides high-performance implementations of critical algorithms
# Originally implemented in Cython, now ported to Rust using PyO3

import numpy as np

# Import the compiled Rust extension module
from invesalius_rs import _native

# Re-export all symbols from the native module
trilin_interpolate_py = _native.trilin_interpolate_py
nearest_neighbour_interp = _native.nearest_neighbour_interp
tricub_interpolate_py = _native.tricub_interpolate_py
tricub_interpolate2_py = _native.tricub_interpolate2_py
lanczos_interpolate_py = _native.lanczos_interpolate_py
floodfill = _native.floodfill
_native_floodfill_threshold = _native.floodfill_threshold
_native_floodfill_threshold_inplace = _native.floodfill_threshold_inplace
_native_floodfill_auto_threshold = _native.floodfill_auto_threshold
fill_holes_automatically = _native.fill_holes_automatically


def floodfill_threshold(data, seeds, t0, t1, fill, strct, out):
    """
    Floodfill with threshold constraints.

    This wrapper converts seed lists to tuples for Rust compatibility
    and ensures array types are correct.
    """
    # Convert seeds to list of tuples if necessary
    tuple_seeds = [tuple(s) for s in seeds]
    # Ensure strct is uint8 (scipy's generate_binary_structure returns bool)
    strct_u8 = np.ascontiguousarray(strct, dtype=np.uint8)
    return _native_floodfill_threshold(data, tuple_seeds, t0, t1, fill, strct_u8, out)

def floodfill_threshold_inplace(data, seeds, t0, t1, fill, strct):
    """
    Floodfill with threshold constraints.

    This wrapper converts seed lists to tuples for Rust compatibility
    and ensures array types are correct.
    """
    # Convert seeds to list of tuples if necessary
    tuple_seeds = [tuple(s) for s in seeds]
    # Ensure strct is uint8 (scipy's generate_binary_structure returns bool)
    strct_u8 = np.ascontiguousarray(strct, dtype=np.uint8)
    return _native_floodfill_threshold_inplace(data, tuple_seeds, t0, t1, fill, strct_u8)


def floodfill_auto_threshold(data, seeds, p, fill, out):
    """
    Floodfill with automatic threshold based on seed values.

    This wrapper converts seed lists to tuples for Rust compatibility.
    """
    # Convert seeds to list of tuples if necessary
    tuple_seeds = [tuple(s) for s in seeds]
    return _native_floodfill_auto_threshold(data, tuple_seeds, p, fill, out)


lmip = _native.lmip
apply_view_matrix_transform = _native.apply_view_matrix_transform
convolve_non_zero = _native.convolve_non_zero
mask_cut = _native.mask_cut


def mida(image: np.ndarray, axis: int, wl: int, ww: int, out: np.ndarray):
    """
    Apply MIDA (Maximum Intensity Diffusion Algorithm) to the image.
    """
    return _native.mida(image, axis, int(wl), int(ww), out)


def fast_countour_mip(
    image: np.ndarray, n: float, axis: int, wl: int, ww: int, tmip: int, out: np.ndarray
):
    return _native.fast_countour_mip(image, n, axis, int(wl), int(ww), tmip, out)


# Rust Mesh class (low-level, takes numpy arrays)
_RustMesh = _native.Mesh


class Mesh:
    """
    Mesh wrapper class compatible with the original cy_mesh.Mesh interface.
    Accepts either a vtkPolyData object or numpy arrays.
    """

    def __init__(self, pd=None, other=None, vertices=None, faces=None, normals=None):
        """
        Initialize Mesh from vtkPolyData or numpy arrays.

        Parameters
        ----------
        pd : vtkPolyData, optional
            VTK polydata to create mesh from
        other : Mesh, optional
            Another Mesh to copy from
        vertices : ndarray, optional
            Vertex positions (Nx3 float32)
        faces : ndarray, optional
            Face indices (Mx4 int64, first column is vertex count)
        normals : ndarray, optional
            Face normals (Mx3 float32)
        """
        if pd is not None:
            # Import VTK utilities only when needed
            from vtkmodules.util import numpy_support

            # Extract vertices
            _vertices = numpy_support.vtk_to_numpy(pd.GetPoints().GetData())
            _vertices = np.ascontiguousarray(_vertices.reshape(-1, 3).astype(np.float32))

            # Extract faces
            _faces = numpy_support.vtk_to_numpy(pd.GetPolys().GetData())
            _faces = np.ascontiguousarray(_faces.reshape(-1, 4).astype(np.int64))

            # Extract normals
            normals_array = pd.GetCellData().GetArray("Normals")
            if normals_array is not None:
                _normals = numpy_support.vtk_to_numpy(normals_array)
                _normals = np.ascontiguousarray(_normals.reshape(-1, 3).astype(np.float32))
            else:
                # Compute normals if not present
                _normals = np.zeros((_faces.shape[0], 3), dtype=np.float32)

            self._mesh = _RustMesh(_vertices, _faces, _normals)

        elif other is not None:
            # Copy from another Mesh
            if isinstance(other, Mesh):
                v = np.ascontiguousarray(other.vertices.copy())
                f = np.ascontiguousarray(other.faces.copy())
                n = np.ascontiguousarray(other.normals.copy())
                self._mesh = _RustMesh(v, f, n)
            else:
                raise TypeError("other must be a Mesh instance")

        elif vertices is not None and faces is not None and normals is not None:
            # Direct numpy arrays
            _vertices = np.ascontiguousarray(vertices.astype(np.float32))
            _faces = np.ascontiguousarray(faces.astype(np.int64))
            _normals = np.ascontiguousarray(normals.astype(np.float32))
            self._mesh = _RustMesh(_vertices, _faces, _normals)
        else:
            raise ValueError("Must provide either pd, other, or (vertices, faces, normals)")

    @property
    def vertices(self):
        """Get vertex array."""
        return self._mesh.vertices

    @property
    def faces(self):
        """Get face array."""
        return self._mesh.faces

    @property
    def normals(self):
        """Get normal array."""
        return self._mesh.normals

    def to_vtk(self):
        """
        Convert Mesh to vtkPolyData.

        Returns
        -------
        vtkPolyData
            VTK polydata representation of the mesh
        """
        from vtkmodules.util import numpy_support
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

        vertices = np.asarray(self.vertices)
        faces = np.asarray(self.faces)

        points = vtkPoints()
        points.SetData(numpy_support.numpy_to_vtk(vertices))

        id_triangles = numpy_support.numpy_to_vtkIdTypeArray(faces.flatten())
        triangles = vtkCellArray()
        triangles.SetCells(faces.shape[0], id_triangles)

        pd = vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(triangles)

        return pd

    def ca_smoothing(self, T, tmax, bmin, n_iters):
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
        self._mesh.ca_smoothing(T, tmax, bmin, n_iters)


def ca_smoothing(mesh, T, tmax, bmin, n_iters):
    """
    Apply context-aware mesh smoothing (function interface for compatibility).

    This function provides backward compatibility with the cy_mesh interface.

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
    mesh.ca_smoothing(T, tmax, bmin, n_iters)


__all__ = [
    # Interpolation
    "trilin_interpolate_py",
    "nearest_neighbour_interp",
    "tricub_interpolate_py",
    "tricub_interpolate2_py",
    "lanczos_interpolate_py",
    # Floodfill
    "floodfill",
    "floodfill_threshold",
    "floodfill_auto_threshold",
    "fill_holes_automatically",
    # MIPS
    "lmip",
    "mida",
    "fast_countour_mip",
    # Transforms
    "apply_view_matrix_transform",
    "convolve_non_zero",
    # Mask cut
    "mask_cut",
    # Mesh
    "Mesh",
    "ca_smoothing",
]
