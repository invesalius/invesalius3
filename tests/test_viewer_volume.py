"""Tests for invesalius/data/viewer_volume.py.

AddPointReference() built its mapper with the VTK 5 call `SetInput(data)`, which
was removed in VTK 6, so every call raised

    AttributeError: 'vtkOpenGLPolyDataMapper' object has no attribute 'SetInput'

The method only touches `self.ren` and `self.points_reference`, so the real
function is exercised here against a stub carrying those two attributes rather
than a full Viewer, which would need a wx frame and a live render window (#927).
"""

import pytest
import wx

# slice_ must be imported before viewer_volume: invesalius.project and
# invesalius.data.slice_ import each other, and viewer_volume pulls in the pair.
import invesalius.data.slice_  # noqa: F401
from vtkmodules.vtkRenderingCore import vtkRenderer

from invesalius.data.viewer_volume import Viewer

if not wx.GetApp():
    app = wx.App(False)


class _RendererStub:
    """The two attributes AddPointReference() reads off `self`."""

    def __init__(self) -> None:
        self.ren = vtkRenderer()
        self.points_reference: list = []


def test_add_point_reference_builds_an_actor() -> None:
    stub = _RendererStub()

    Viewer.AddPointReference(stub, [1.0, 2.0, 3.0], radius=2.0, colour=(0.0, 1.0, 0.0))

    assert len(stub.points_reference) == 1
    actor = stub.points_reference[0]
    assert stub.ren.GetActors().GetNumberOfItems() == 1
    assert actor.GetProperty().GetColor() == (0.0, 1.0, 0.0)
    # The reference points are decoration, never pick targets.
    assert actor.GetPickable() == 0


def test_add_point_reference_mapper_is_connected_to_the_sphere() -> None:
    """The mapper must actually receive the sphere, at the requested place.

    This is what distinguishes a real fix from one that merely stops raising:
    the bounds can only be right if the source reached the mapper.
    """
    stub = _RendererStub()
    centre = (10.0, -5.0, 2.0)
    radius = 3.0

    Viewer.AddPointReference(stub, list(centre), radius=radius)

    actor = stub.points_reference[0]
    actor.GetMapper().Update()
    x_min, x_max, y_min, y_max, z_min, z_max = actor.GetBounds()

    # A tessellated sphere is inscribed in its true bounds, so compare centres
    # and require the extent to be close to, and never larger than, the radius.
    assert (x_min + x_max) / 2 == pytest.approx(centre[0], abs=1e-6)
    assert (y_min + y_max) / 2 == pytest.approx(centre[1], abs=1e-6)
    assert (z_min + z_max) / 2 == pytest.approx(centre[2], abs=1e-6)
    assert 0 < (x_max - x_min) / 2 <= radius
    assert 0 < (z_max - z_min) / 2 <= radius


def test_remove_all_points_reference_clears_the_renderer() -> None:
    stub = _RendererStub()
    Viewer.AddPointReference(stub, [0.0, 0.0, 0.0])
    Viewer.AddPointReference(stub, [1.0, 1.0, 1.0])
    assert stub.ren.GetActors().GetNumberOfItems() == 2

    Viewer.RemoveAllPointsReference(stub)

    assert stub.points_reference == []
    assert stub.ren.GetActors().GetNumberOfItems() == 0
