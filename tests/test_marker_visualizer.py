from unittest.mock import Mock

import pytest
import vtk

from invesalius.data.actor_factory import ActorFactory
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.data.visualization.marker_visualizer import MarkerVisualizer
from invesalius.navigation.markers import MarkersControl
from invesalius.pubsub import pub as Publisher


@pytest.fixture
def visualizer():
    vector_field_visualizer = Mock()
    vector_field_visualizer.CreateVectorFieldAssembly.return_value = vtk.vtkAssembly()
    visualizer = MarkerVisualizer(
        renderer=vtk.vtkRenderer(),
        interactor=Mock(),
        actor_factory=ActorFactory(),
        vector_field_visualizer=vector_field_visualizer,
    )
    yield visualizer
    visualizer.dispose()


@pytest.fixture
def markers_control(visualizer):
    # Bypass the singleton so each test has independent markers and navigation state.
    control = object.__new__(MarkersControl)
    control.navigation = Mock()
    control.SaveState = Mock()
    control.list = []
    for marker_id in range(2):
        marker = Marker(
            marker_id=marker_id,
            alpha=0,
            beta=0,
            gamma=0,
            marker_type=MarkerType.COIL_TARGET,
        )
        visualizer.AddMarker(marker, render=False, focus=False)
        control.list.append(marker)

    # NavigationScene forwards these events to the visualizer in the application.
    Publisher.subscribe(visualizer.SetTarget, "Set target")
    Publisher.subscribe(visualizer.UnsetTarget, "Unset target")
    return control


@pytest.mark.parametrize("is_navigating", [False, True])
@pytest.mark.parametrize("transparent, expected_opacity", [(True, 0.4), (False, 1.0)])
def test_target_transparency_updates_actor_and_idle_view(
    visualizer, is_navigating, transparent, expected_opacity
):
    marker = Marker(visualization={"actor": vtk.vtkActor()})
    actor = marker.visualization["actor"]
    actor.GetProperty().SetOpacity(1.0 if transparent else 0.4)
    visualizer.is_navigating = is_navigating
    rendered_opacities = []
    visualizer.interactor.Render.side_effect = lambda: rendered_opacities.append(
        actor.GetProperty().GetOpacity()
    )

    visualizer.SetTargetTransparency(marker, transparent)

    assert marker.visualization["actor"] is actor
    assert actor.GetProperty().GetOpacity() == pytest.approx(expected_opacity)
    assert rendered_opacities == ([] if is_navigating else [expected_opacity])


def test_target_transparency_can_be_toggled_repeatedly(visualizer):
    marker = Marker(visualization={"actor": vtk.vtkActor()})

    for transparent, expected_opacity in [(True, 0.4), (False, 1.0), (True, 0.4)]:
        visualizer.SetTargetTransparency(marker, transparent)
        assert marker.visualization["actor"].GetProperty().GetOpacity() == pytest.approx(
            expected_opacity
        )


def test_setting_target_makes_replacement_aim_transparent(visualizer, markers_control):
    marker = markers_control.list[0]
    arrow = marker.visualization["actor"]
    rendered_opacities = []
    visualizer.interactor.Render.side_effect = lambda: rendered_opacities.append(
        marker.visualization["actor"].GetProperty().GetOpacity()
    )

    markers_control.SetTarget(marker.marker_id)

    assert marker.is_target
    assert marker.visualization["actor"] is not arrow
    assert marker.visualization["actor"].GetProperty().GetOpacity() == pytest.approx(0.4)
    assert rendered_opacities[-1] == pytest.approx(0.4)
    markers_control.navigation.SetTarget.assert_called_once_with(marker)


def test_unsetting_target_restores_aim_opacity_before_replacing_it(visualizer, markers_control):
    marker = markers_control.list[0]
    markers_control.SetTarget(marker.marker_id)
    aim = marker.visualization["actor"]

    markers_control.UnsetTarget(marker.marker_id)

    assert not marker.is_target
    assert aim.GetProperty().GetOpacity() == pytest.approx(1.0)
    assert marker.visualization["actor"] is not aim
    assert visualizer.target_marker is None
    markers_control.navigation.UnsetTarget.assert_called_once_with()


def test_switching_targets_restores_previous_aim_opacity(visualizer, markers_control):
    previous_marker, next_marker = markers_control.list
    markers_control.SetTarget(previous_marker.marker_id)
    previous_aim = previous_marker.visualization["actor"]

    markers_control.SetTarget(next_marker.marker_id)

    assert not previous_marker.is_target
    assert previous_aim.GetProperty().GetOpacity() == pytest.approx(1.0)
    assert next_marker.is_target
    assert next_marker.visualization["actor"].GetProperty().GetOpacity() == pytest.approx(0.4)
    assert visualizer.target_marker is next_marker


def test_unsetting_point_of_interest_restores_opacity(visualizer, markers_control):
    marker = markers_control.list[0]
    marker.is_point_of_interest = True
    visualizer.SetTargetTransparency(marker, transparent=True)

    markers_control.UnsetPointOfInterest(marker.marker_id)

    assert not marker.is_point_of_interest
    assert marker.visualization["actor"].GetProperty().GetOpacity() == pytest.approx(1.0)
