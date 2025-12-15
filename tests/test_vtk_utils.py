import numpy as np
from vtkmodules.vtkCommonMath import vtkMatrix4x4

from invesalius.data import coordinates as dco
from invesalius.data.vtk_utils import coordinates_to_vtk_object_matrix, numpy_to_vtkMatrix4x4


def vtk_to_numpy(m: vtkMatrix4x4) -> np.ndarray:
    return np.array([[m.GetElement(r, c) for c in range(4)] for r in range(4)], dtype=float)


def test_coordinates_to_vtk_object_matrix_matches_reference():
    position = [10.0, -5.0, 3.0]
    orientation = [15.0, 30.0, -45.0]

    ref_affine = dco.coordinates_to_transformation_matrix(
        position=position,
        orientation=orientation,
        axes="sxyz",
    )
    ref_affine = np.asarray(ref_affine, dtype=float).reshape(4, 4)
    ref_vtk = numpy_to_vtkMatrix4x4(ref_affine)

    mat = coordinates_to_vtk_object_matrix(position, orientation)

    np.testing.assert_allclose(
        vtk_to_numpy(mat),
        vtk_to_numpy(ref_vtk),
        rtol=1e-6,
        atol=1e-8,
    )