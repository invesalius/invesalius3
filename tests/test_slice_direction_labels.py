from types import SimpleNamespace

import pytest
import wx
from vtkmodules.vtkRenderingCore import vtkCamera

import invesalius.constants as const
import invesalius.data.slice_  # noqa: F401
import invesalius.project as project
from invesalius.data.viewer_slice import Viewer

if not wx.GetApp():
    app = wx.App(False)

ORIGINAL_ORIENTATIONS = [const.AXIAL, const.SAGITAL, const.CORONAL]
SLICE_ORIENTATIONS = ["AXIAL", "CORONAL", "SAGITAL"]


class FakeViewer(SimpleNamespace):
    GetDefaultViewUp = Viewer.GetDefaultViewUp
    GetDirectionLabels = Viewer.GetDirectionLabels
    UpdateTextDirection = Viewer.UpdateTextDirection

    def RenderTextDirection(self, directions):
        self.directions = list(directions)


def make_camera(original_orientation, slice_orientation, roll=0):
    cam = vtkCamera()
    cam.SetFocalPoint(0, 0, 0)
    cam.SetViewUp(const.SLICE_POSITION[original_orientation][0][slice_orientation])
    cam.SetPosition(const.SLICE_POSITION[original_orientation][1][slice_orientation])
    cam.ParallelProjectionOn()
    cam.Roll(roll)
    return cam


def get_directions(original_orientation, slice_orientation, roll):
    """Return the direction texts as [top, left, bottom, right]."""
    project.Project().original_orientation = original_orientation
    viewer = FakeViewer(orientation=slice_orientation, nav_status=True)
    viewer.UpdateTextDirection(make_camera(original_orientation, slice_orientation, roll))
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
def test_default_camera_keeps_default_labels(original_orientation, slice_orientation, expected):
    assert get_directions(original_orientation, slice_orientation, 0) == expected


@pytest.mark.parametrize("original_orientation", ORIGINAL_ORIENTATIONS)
@pytest.mark.parametrize(
    "roll, expected",
    [
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
def test_axial_labels_follow_the_roll(original_orientation, roll, expected):
    assert get_directions(original_orientation, "AXIAL", roll) == expected


@pytest.mark.parametrize("original_orientation", ORIGINAL_ORIENTATIONS)
@pytest.mark.parametrize("slice_orientation", SLICE_ORIENTATIONS)
def test_labels_do_not_depend_on_original_orientation(original_orientation, slice_orientation):
    for roll in range(-170, 181, 20):
        assert get_directions(original_orientation, slice_orientation, roll) == get_directions(
            const.AXIAL, slice_orientation, roll
        )


@pytest.mark.parametrize("slice_orientation", SLICE_ORIENTATIONS)
def test_every_roll_gives_four_labels(slice_orientation):
    # The previous lookup had gaps, e.g. between 88 and 89 degrees.
    for tenth in range(-1800, 1801, 5):
        directions = get_directions(const.AXIAL, slice_orientation, tenth / 10)
        assert len(directions) == 4
        assert all(1 <= len(d) <= 2 for d in directions)


def test_small_roll_shows_single_letters():
    assert get_directions(const.CORONAL, "AXIAL", 1) == ["A", "R", "P", "L"]
    assert get_directions(const.CORONAL, "AXIAL", -1) == ["A", "R", "P", "L"]
