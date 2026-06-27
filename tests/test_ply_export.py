import os
from pathlib import Path
from typing import Tuple

import pytest
import wx
from vtkmodules.vtkIOPLY import vtkPLYReader

import invesalius.constants as const
from invesalius.data.surface import SurfaceManager
from tests.test_stl_export import surface_manager_with_surfaces, clean_project


@pytest.fixture(scope="module", autouse=True)
def wx_app():
    app = wx.GetApp() or wx.App(False)
    yield app


def test_export_surface_to_ply(surface_manager_with_surfaces, tmp_path: Path) -> None:
    surface_manager, _ = surface_manager_with_surfaces

    filename = tmp_path / "exported_surface.ply"

    surface_manager._export_surface(str(filename), const.FILETYPE_PLY, convert_to_world=False)

    assert os.path.exists(filename), f"PLY file not created: {filename}"
    assert os.path.getsize(filename) > 0, f"PLY file is empty: {filename}"

    reader = vtkPLYReader()
    reader.SetFileName(str(filename))
    reader.Update()
    mesh = reader.GetOutput()

    assert mesh.GetNumberOfPoints() > 0, "Exported mesh has no points"
    assert mesh.GetNumberOfCells() > 0, "Exported mesh has no cells"


def test_export_surface_empty_project(clean_project, tmp_path: Path) -> None:
    surface_manager = SurfaceManager()

    filename = tmp_path / "empty_export.ply"

    surface_manager._export_surface(str(filename), const.FILETYPE_PLY, convert_to_world=False)

    assert not os.path.exists(filename), "File should not be created when no surfaces are visible"


def test_export_surface_multiple_visible(surface_manager_with_surfaces, tmp_path: Path) -> None:
    surface_manager, project = surface_manager_with_surfaces

    for index in project.surface_dict:
        project.surface_dict[index].is_shown = True

    filename = tmp_path / "multiple_surfaces.ply"

    surface_manager._export_surface(str(filename), const.FILETYPE_PLY, convert_to_world=False)

    assert os.path.exists(filename), f"PLY file not created: {filename}"
    assert os.path.getsize(filename) > 0, f"PLY file is empty: {filename}"

    reader = vtkPLYReader()
    reader.SetFileName(str(filename))
    reader.Update()
    mesh = reader.GetOutput()

    assert mesh.GetNumberOfPoints() > 0, "Exported mesh has no points"
    assert mesh.GetNumberOfCells() > 0, "Exported mesh has no cells"
