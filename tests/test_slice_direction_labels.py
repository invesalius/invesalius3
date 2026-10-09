from types import SimpleNamespace

import pytest
import wx
from vtkmodules.vtkRenderingCore import vtkCamera

import invesalius.constants as const
import invesalius.data.slice_  # noqa: F401
import invesalius.data.viewer_slice as viewer_slice

if not wx.GetApp():
    app = wx.App(False)

ORIGINAL_ORIENTATIONS = [const.AXIAL, const.SAGITAL, const.CORONAL]


class FakeViewer(SimpleNamespace):
    GetDefaultTextDirection = viewer_slice.Viewer.GetDefaultTextDirection
    UpdateTextDirection = viewer_slice.Viewer.UpdateTextDirection

    def RenderTextDirection(self, directions):
        self.directions = directions


@pytest.fixture(autouse=True)
def english_labels(monkeypatch):
    monkeypatch.setattr(viewer_slice, "_", lambda text: text)


def get_directions(original_orientation, slice_orientation, roll):
    """Direction texts as [top, left, bottom, right] after rolling the default camera."""
    cam = vtkCamera()
    cam.SetFocalPoint(0, 0, 0)
    cam.SetViewUp(const.SLICE_POSITION[original_orientation][0][slice_orientation])
    cam.SetPosition(const.SLICE_POSITION[original_orientation][1][slice_orientation])
    viewer = FakeViewer(orientation=slice_orientation, default_roll=cam.GetRoll())
    cam.Roll(roll)
    viewer.UpdateTextDirection(cam)
    return viewer.directions


@pytest.mark.parametrize("original_orientation", ORIGINAL_ORIENTATIONS)
@pytest.mark.parametrize(
    "slice_orientation, expected",
    [
        ("AXIAL", ["A", "R", "P", "L"]),
        ("CORONAL", ["T", "R", "B", "L"]),
        ("SAGITAL", ["T", "P", "B", "A"]),
    ],
)
def test_default_camera_shows_default_directions(original_orientation, slice_orientation, expected):
    assert get_directions(original_orientation, slice_orientation, 0) == expected


@pytest.mark.parametrize("original_orientation", ORIGINAL_ORIENTATIONS)
@pytest.mark.parametrize(
    "roll, expected",
    [
        (1, ["A", "R", "P", "L"]),
        (30, ["AL", "RA", "PR", "LP"]),
        (60, ["LA", "AR", "RP", "PL"]),
        (90, ["L", "A", "R", "P"]),
        (120, ["LP", "AL", "RA", "PR"]),
        (180, ["P", "L", "A", "R"]),
        (-30, ["AR", "RP", "PL", "LA"]),
        (-90, ["R", "P", "L", "A"]),
        (-150, ["PR", "LP", "AL", "RA"]),
    ],
)
def test_axial_directions_follow_the_roll(original_orientation, roll, expected):
    assert get_directions(original_orientation, "AXIAL", roll) == expected


@pytest.mark.parametrize("slice_orientation", ["AXIAL", "CORONAL", "SAGITAL"])
def test_every_roll_has_a_direction(slice_orientation):
    # 88.5 and 180 degrees, for example, used to fall between two ranges.
    for half_degree in range(-360, 361):
        directions = get_directions(const.AXIAL, slice_orientation, half_degree / 2)
        assert all(len(direction) in (1, 2) for direction in directions)
