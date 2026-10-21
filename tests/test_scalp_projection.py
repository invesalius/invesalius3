import numpy as np
import pytest
import vtk

from invesalius.data import coordinates as dco
from invesalius.data.markers.surface_geometry import SurfaceGeometry
from invesalius.pubsub import pub as Publisher


@pytest.fixture
def geometry(monkeypatch):
    monkeypatch.setattr(SurfaceGeometry, "instance", None)
    geometry = SurfaceGeometry()
    yield geometry
    Publisher.unsubscribe_owner(geometry)


def test_projection_hits_cell_interior_and_reuses_locators(geometry, monkeypatch):
    plane = vtk.vtkPlaneSource()
    plane.SetOrigin(-10, -10, 0)
    plane.SetPoint1(10, -10, 0)
    plane.SetPoint2(-10, 10, 0)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(plane.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    surface = geometry.PrecalculateSurfaceData(actor)
    monkeypatch.setattr(geometry, "GetSmoothedScalpSurface", lambda: surface)
    locator = surface["cell_locator"]
    for point in [(1, 2, 4), (-3, -2, 6)]:
        projected, normal = geometry.GetClosestPointOnSurface("scalp", point, smooth_radius=15)
        assert projected == pytest.approx([*point[:2], 0])
        assert normal == pytest.approx([0, 0, 1])
        assert surface["cell_locator"] is locator


@pytest.mark.parametrize("normal", [(0, 0, 1), (0, 0, -1), (1, 2, 3)])
def test_orientation_aligns_z_with_scalp_normal(geometry, normal):
    orientation = geometry.OrientationFromNormal(normal)
    matrix = dco.coordinates_to_transformation_matrix([0, 0, 0], orientation, axes="sxyz")
    assert matrix[:3, 2] == pytest.approx(np.array(normal) / np.linalg.norm(normal))


def test_projection_rejects_missing_geometry_and_nonfinite_coordinates(geometry, monkeypatch):
    monkeypatch.setattr(geometry, "GetSmoothedScalpSurface", lambda: None)
    with pytest.raises(RuntimeError, match="scalp surface"):
        geometry.GetClosestPointOnSurface("scalp", [0, 0, 0])
    monkeypatch.setattr(
        geometry,
        "GetSmoothedScalpSurface",
        lambda: {
            "polydata": None,
            "normals": None,
            "point_locator": None,
        },
    )
    with pytest.raises(RuntimeError, match="finite"):
        geometry.GetClosestPointOnSurface("scalp", [float("nan"), 0, 0])
