import pytest
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkFiltersSources import vtkSphereSource

from invesalius.data.polydata_utils import ApplyDecimationFilter, ApplySmoothFilter


@pytest.fixture
def sphere_polydata() -> vtkPolyData:
    sphere = vtkSphereSource()
    sphere.SetThetaResolution(20)
    sphere.SetPhiResolution(20)
    sphere.Update()
    return sphere.GetOutput()


def test_apply_decimation_filter(sphere_polydata: vtkPolyData) -> None:
    original_cells = sphere_polydata.GetNumberOfCells()
    assert original_cells > 0

    # Apply 50% decimation
    decimated = ApplyDecimationFilter(sphere_polydata, 0.5)

    assert isinstance(decimated, vtkPolyData)
    assert decimated.GetNumberOfPoints() > 0
    assert decimated.GetNumberOfCells() < original_cells


def test_apply_smooth_filter(sphere_polydata: vtkPolyData) -> None:
    original_points = sphere_polydata.GetNumberOfPoints()
    assert original_points > 0

    smoothed = ApplySmoothFilter(sphere_polydata, iterations=10, relaxation_factor=0.2)

    assert isinstance(smoothed, vtkPolyData)
    assert smoothed.GetNumberOfPoints() > 0
    assert smoothed.GetNumberOfCells() > 0
