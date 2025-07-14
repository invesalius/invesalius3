import os
from pathlib import Path
from typing import Any, Tuple

import numpy as np
import pytest
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkFiltersCore import vtkContourFilter
from vtkmodules.vtkIOGeometry import vtkSTLReader, vtkSTLWriter

import invesalius.constants as const
import invesalius.project as prj
from invesalius.data.converters import to_vtk
from invesalius.data.surface import Surface, SurfaceManager


def make_test_polydata(shape: Tuple[int, int, int], region: Any, value: int = 255) -> vtkPolyData:
    """Method to create a test polydata mesh with a filled region."""
    mask_array = np.zeros(shape, dtype=np.uint8)
    mask_array[region] = value
    vtk_mask = to_vtk(mask_array, spacing=(1.0, 1.0, 1.0))
    mc = vtkContourFilter()
    mc.SetInputData(vtk_mask)
    mc.SetValue(0, 128)
    mc.Update()
    return mc.GetOutput()


@pytest.fixture
def raw_contour_mesh() -> vtkPolyData:
    shape = (20, 20, 20)
    region = (slice(5, 15), slice(5, 15), slice(5, 15))
    return make_test_polydata(shape, region, value=255)


@pytest.fixture
def clean_project() -> prj.Project:
    """Creating a clean project for testing."""
    # Create a new project and clear any existing surfaces
    project = prj.Project()
    project.surface_dict.clear()
    return project


@pytest.fixture
def surface_manager_with_surfaces(clean_project: prj.Project) -> Tuple[SurfaceManager, prj.Project]:
    project = clean_project
    shape = (10, 10, 10)
    region = (slice(3, 7), slice(3, 7), slice(3, 7))
    polydata = make_test_polydata(shape, region, value=255)
    surface_manager = SurfaceManager()
    surface1 = Surface(name="Test Surface 1")
    surface1.polydata = polydata
    surface1.is_shown = True
    surface1.colour = (1.0, 0.0, 0.0)
    surface2 = Surface(name="Test Surface 2")
    surface2.polydata = polydata
    surface2.is_shown = False
    surface2.colour = (0.0, 1.0, 0.0)
    index1 = project.AddSurface(surface1)
    index2 = project.AddSurface(surface2)
    surface1.index = index1
    surface2.index = index2
    surface_manager.actors_dict[index1] = None
    surface_manager.actors_dict[index2] = None
    surface_manager.last_surface_index = index1
    return surface_manager, project


@pytest.mark.parametrize("filetype", ["binary", "ascii"])
def test_stl_export_and_import_consistency(
    raw_contour_mesh: vtkPolyData, filetype: str, tmp_path: Path
) -> None:
    """Test exporting a mesh to STL (binary/ascii) and reading it back, checking geometry and consistency."""
    filename = tmp_path / "test.stl"
    writer = vtkSTLWriter()
    writer.SetFileName(str(filename))
    writer.SetInputData(raw_contour_mesh)
    if filetype == "binary":
        writer.SetFileTypeToBinary()
    else:
        writer.SetFileTypeToASCII()
    writer.Write()

    assert os.path.exists(filename) and os.path.getsize(filename) > 0

    reader = vtkSTLReader()
    reader.SetFileName(str(filename))
    reader.Update()
    mesh = reader.GetOutput()

    # Check mesh is valid
    assert mesh.GetNumberOfPoints() > 0
    assert mesh.GetNumberOfCells() > 0

    # Check that the number of points/cells and geometry are preserved after export/import
    n_points_before = raw_contour_mesh.GetNumberOfPoints()
    n_cells_before = raw_contour_mesh.GetNumberOfCells()
    assert mesh.GetNumberOfPoints() == n_points_before
    assert mesh.GetNumberOfCells() == n_cells_before

    orig_points = numpy_support.vtk_to_numpy(raw_contour_mesh.GetPoints().GetData())
    new_points = numpy_support.vtk_to_numpy(mesh.GetPoints().GetData())
    assert orig_points.shape == new_points.shape
    # Defined a method to check if the points are the same
    assert points_match_setwise(orig_points, new_points, tol=1e-2)


def test_stl_export_empty_mesh(tmp_path: Path) -> None:
    """Test exporting an empty mesh to STL and reading it back"""
    # Suppress VTK error popups by redirecting output to a file or null device as it will show a popup otherwise
    fow = vtkFileOutputWindow()
    fow.SetFileName(str(tmp_path / "vtkoutput.txt"))
    ow = vtkOutputWindow()
    ow.SetInstance(fow)

    empty_mesh = vtkPolyData()
    filename = tmp_path / "empty.stl"

    # Attempt to write the empty mesh
    writer = vtkSTLWriter()
    writer.SetFileName(str(filename))
    writer.SetInputData(empty_mesh)
    writer.SetFileTypeToBinary()
    writer.Write()

    # If file is not created or is empty, that's ok for an empty mesh
    assert not os.path.exists(filename)


def test_export_surface_to_stl(
    surface_manager_with_surfaces: Tuple[SurfaceManager, prj.Project], tmp_path: Path
) -> None:
    """Test the core functionality of OnExportSurface without relying on temp file mechanism."""
    surface_manager, project = surface_manager_with_surfaces

    # Test file path
    filename = tmp_path / "exported_surface.stl"

    # Test the _export_surface method
    surface_manager._export_surface(str(filename), const.FILETYPE_STL, convert_to_world=False)

    # Check that file was created
    assert os.path.exists(filename), f"STL file was not created: {filename}"
    assert os.path.getsize(filename) > 0, f"STL file is empty: {filename}"

    # Verify the exported file can be read back
    reader = vtkSTLReader()
    reader.SetFileName(str(filename))
    reader.Update()
    mesh = reader.GetOutput()

    # Check that the mesh is valid
    assert mesh.GetNumberOfPoints() > 0, "Exported mesh has no points"
    assert mesh.GetNumberOfCells() > 0, "Exported mesh has no cells"


def test_on_export_surface_empty_project(clean_project: prj.Project, tmp_path: Path) -> None:
    """Test OnExportSurface when no surfaces are visible."""
    surface_manager = SurfaceManager()

    filename = tmp_path / "empty_export.stl"

    # This should not create a file since no surfaces are visible
    surface_manager._export_surface(str(filename), const.FILETYPE_STL, convert_to_world=False)

    # File should not exist since no surfaces were exported
    assert not os.path.exists(filename), "File should not be created when no surfaces are visible"


def test_export_surface_multiple_visible(
    surface_manager_with_surfaces: Tuple[SurfaceManager, prj.Project], tmp_path: Path
) -> None:
    """Test OnExportSurface with multiple visible surfaces."""
    surface_manager, project = surface_manager_with_surfaces

    # Make both surfaces visible
    for index in project.surface_dict:
        project.surface_dict[index].is_shown = True

    filename = tmp_path / "multiple_surfaces.stl"

    surface_manager._export_surface(str(filename), const.FILETYPE_STL, convert_to_world=False)

    # Check that file was created
    assert os.path.exists(filename), f"STL file was not created: {filename}"
    assert os.path.getsize(filename) > 0, f"STL file is empty: {filename}"

    # Verify the exported file can be read back
    reader = vtkSTLReader()
    reader.SetFileName(str(filename))
    reader.Update()
    mesh = reader.GetOutput()

    # Check that the mesh is valid
    assert mesh.GetNumberOfPoints() > 0, "Exported mesh has no points"
    assert mesh.GetNumberOfCells() > 0, "Exported mesh has no cells"


def test_on_export_surface_ascii_format(
    surface_manager_with_surfaces: Tuple[SurfaceManager, prj.Project], tmp_path: Path
) -> None:
    """Test OnExportSurface with ASCII STL format."""
    surface_manager, project = surface_manager_with_surfaces

    filename = tmp_path / "ascii_surface.stl"

    # Test the core functionality directly
    surface_manager._export_surface(str(filename), const.FILETYPE_STL_ASCII, convert_to_world=False)

    # Check that file was created
    assert os.path.exists(filename), f"ASCII STL file was not created: {filename}"
    assert os.path.getsize(filename) > 0, f"ASCII STL file is empty: {filename}"

    # Verify the exported file can be read back
    reader = vtkSTLReader()
    reader.SetFileName(str(filename))
    reader.Update()
    mesh = reader.GetOutput()

    # Check that the mesh is valid
    assert mesh.GetNumberOfPoints() > 0, "Exported ASCII mesh has no points"
    assert mesh.GetNumberOfCells() > 0, "Exported ASCII mesh has no cells"


def test_on_export_surface_file_formats(
    surface_manager_with_surfaces: Tuple[SurfaceManager, prj.Project], tmp_path: Path
) -> None:
    """Test different file formats supported by OnExportSurface."""
    surface_manager, project = surface_manager_with_surfaces

    # Test STL binary
    stl_binary_file = tmp_path / "test_binary.stl"
    surface_manager._export_surface(
        str(stl_binary_file), const.FILETYPE_STL, convert_to_world=False
    )
    assert os.path.exists(stl_binary_file), "STL binary file was not created"

    # Test STL ASCII
    stl_ascii_file = tmp_path / "test_ascii.stl"
    surface_manager._export_surface(
        str(stl_ascii_file), const.FILETYPE_STL_ASCII, convert_to_world=False
    )
    assert os.path.exists(stl_ascii_file), "STL ASCII file was not created"

    # Test VTP
    vtp_file = tmp_path / "test.vtp"
    surface_manager._export_surface(str(vtp_file), const.FILETYPE_VTP, convert_to_world=False)
    assert os.path.exists(vtp_file), "VTP file was not created"

    # Test PLY
    ply_file = tmp_path / "test.ply"
    surface_manager._export_surface(str(ply_file), const.FILETYPE_PLY, convert_to_world=False)
    assert os.path.exists(ply_file), "PLY file was not created"


def points_match_setwise(points1: np.ndarray, points2: np.ndarray, tol: float = 1e-3) -> bool:
    points1_sorted = np.array(sorted(points1.tolist()))
    points2_sorted = np.array(sorted(points2.tolist()))
    return np.allclose(points1_sorted, points2_sorted, atol=tol)
