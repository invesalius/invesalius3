from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import vtk
import wx

from invesalius.data.visualization.marker_visualizer import MarkerVisualizer

if not wx.GetApp():
    app = wx.App(False)


@pytest.fixture
def visualizer():
    # Build the visualizer without running __init__, which needs a renderer, an
    # interactor and a live 3D viewer.
    visualizer = MarkerVisualizer.__new__(MarkerVisualizer)
    visualizer.interactor = MagicMock()
    visualizer.is_navigating = False
    return visualizer


@pytest.fixture
def marker():
    return SimpleNamespace(visualization={"actor": vtk.vtkActor()})


def test_set_target_transparency_makes_marker_transparent(visualizer, marker):
    visualizer.SetTargetTransparency(marker, transparent=True)

    opacity = marker.visualization["actor"].GetProperty().GetOpacity()

    assert opacity == pytest.approx(MarkerVisualizer.TARGET_OPACITY)
    assert opacity < 1.0


def test_set_target_transparency_restores_opacity(visualizer, marker):
    visualizer.SetTargetTransparency(marker, transparent=True)
    visualizer.SetTargetTransparency(marker, transparent=False)

    opacity = marker.visualization["actor"].GetProperty().GetOpacity()

    assert opacity == pytest.approx(1.0)


def test_set_target_transparency_renders_when_not_navigating(visualizer, marker):
    visualizer.SetTargetTransparency(marker, transparent=True)

    visualizer.interactor.Render.assert_called_once()


def test_set_target_transparency_does_not_render_when_navigating(visualizer, marker):
    visualizer.is_navigating = True

    visualizer.SetTargetTransparency(marker, transparent=True)

    visualizer.interactor.Render.assert_not_called()
