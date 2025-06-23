import numpy as np
import pytest
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkFloatArray, vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData, vtkTriangle
from vtkmodules.vtkFiltersCore import vtkContourFilter

import invesalius.data.slice_ as sl
from invesalius.data.brainmesh_handler import (
    Brain,
    cleanMesh,
    downsample,
    fixMesh,
    smooth,
    upsample,
)
from invesalius.data.mask import Mask


@pytest.fixture
def raw_contour_mesh():
    """Create a raw, unsmoothed mesh from a contour filter."""
    mask_array = np.zeros((20, 20, 20), dtype=np.uint8)
    mask_array[5:15, 5:15, 5:15] = 255  # A simple cube

    from invesalius.data.converters import to_vtk

    vtk_mask = to_vtk(mask_array, spacing=(1.0, 1.0, 1.0))

    mc = vtkContourFilter()
    mc.SetInputData(vtk_mask)
    mc.SetValue(0, 128)
    mc.Update()
    return mc.GetOutput()


def test_do_surface_creation_generates_mesh():
    # Real Mask object with the correct shape
    mask = Mask()
    shape = (10, 10, 10)
    mask.create_mask(shape)
    mask.matrix[4:7, 4:7, 4:7] = 1  # [1:, 1:, 1:] is the active region

    slic = sl.Slice()
    image = np.ones(shape, dtype=np.uint8)
    image.flat[0] = 2
    slic.matrix = image  # dummy image matrix
    slic.spacing = (1.0, 1.0, 1.0)

    # Dummy values for required Brain parameters
    n_peels = 1
    window_width = 100
    window_level = 50
    affine = np.eye(4)
    inv_proj = np.eye(4)

    brain = Brain(n_peels, window_width, window_level, affine, inv_proj)
    brain.from_mask(mask)

    # Check that a mesh was generated
    assert len(brain.peel) > 0
    mesh = brain.peel[0]
    assert isinstance(mesh, vtkPolyData)
    assert mesh.GetNumberOfPoints() > 0
    assert mesh.GetNumberOfCells() > 0

    # Testing that the mesh is roughly in the expected region
    bounds = mesh.GetBounds()
    xmin, xmax, ymin, ymax, zmin, zmax = bounds

    # The filled region in the active 10x10x10 array is at indices [3:6].
    # So coordinates should be roughly [3, 6].
    # With smoothing, allow a margin, e.g., [2, 7].

    # Check X and Z bounds (not flipped)
    assert 2.0 < xmin < xmax < 8.0
    assert 2.0 < zmin < zmax < 8.0

    # Check Y bounds (flipped about origin)
    # The Y coordinates [3, 6] become roughly [-6, -3].
    # With smoothing, allow a margin, e.g., [-8, -2].
    assert -8.0 < ymin < ymax < -2.0


def test_clean_mesh(raw_contour_mesh):
    """Test mesh cleaning returns a valid mesh."""
    result = cleanMesh(raw_contour_mesh)
    assert isinstance(result, vtkPolyData)
    assert result.GetNumberOfPoints() > 0
    assert result.GetNumberOfCells() > 0


def test_fix_mesh(raw_contour_mesh):
    """Test mesh fixing returns a valid mesh."""
    result = fixMesh(raw_contour_mesh)
    assert isinstance(result, vtkPolyData)
    assert result.GetNumberOfPoints() > 0
    assert result.GetNumberOfCells() > 0


def test_upsample_mesh(raw_contour_mesh):
    """Test that upsampling increases the number of points and cells."""
    original_points = raw_contour_mesh.GetNumberOfPoints()
    original_cells = raw_contour_mesh.GetNumberOfCells()
    result = upsample(raw_contour_mesh)
    assert isinstance(result, vtkPolyData)
    assert result.GetNumberOfPoints() > original_points
    assert result.GetNumberOfCells() > original_cells


def test_smooth_mesh(raw_contour_mesh):
    """Test that smoothing changes the point coordinates."""
    original_points_arr = numpy_support.vtk_to_numpy(raw_contour_mesh.GetPoints().GetData())
    result = smooth(raw_contour_mesh)
    smoothed_points_arr = numpy_support.vtk_to_numpy(result.GetPoints().GetData())
    assert isinstance(result, vtkPolyData)
    assert not np.array_equal(original_points_arr, smoothed_points_arr)


def test_downsample_mesh(raw_contour_mesh):
    """Test that downsampling reduces the number of points and cells."""
    # First, upsample to ensure there's something to downsample
    upsampled_mesh = upsample(raw_contour_mesh)
    original_points = upsampled_mesh.GetNumberOfPoints()
    original_cells = upsampled_mesh.GetNumberOfCells()

    result = downsample(upsampled_mesh)
    assert isinstance(result, vtkPolyData)
    assert result.GetNumberOfPoints() < original_points
    assert result.GetNumberOfCells() < original_cells
