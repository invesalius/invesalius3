from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from invesalius.data.eeg_electrode import EEGElectrode
from invesalius.navigation import eeg_electrodes as eeg
from invesalius.pubsub import pub as Publisher


@pytest.fixture
def manager(monkeypatch):
    state = {"markers": [{"marker_type": 1, "label": "Target"}]}
    session = SimpleNamespace(
        GetState=lambda key, default=None: deepcopy(state.get(key, default)),
        SetState=Mock(side_effect=lambda key, value: state.update({key: deepcopy(value)})),
    )
    monkeypatch.setattr(eeg.ses, "Session", lambda: session)
    monkeypatch.setattr(eeg, "SurfaceGeometry", Mock())
    monkeypatch.setattr(eeg.EEGElectrodeManager, "instance", None)
    instance = eeg.EEGElectrodeManager()
    yield instance, state, session
    Publisher.unsubscribe_owner(instance)


def test_electrodes_persist_and_delete_without_changing_markers(manager):
    electrodes, state, session = manager
    original_markers = deepcopy(state["markers"])
    first = electrodes.create([1.0, 2.0, 3.0])
    second = electrodes.create([4.0, 5.0, 6.0])
    assert (first.label, second.label) == ("E1", "E2")
    assert not hasattr(first, "marker_type")
    electrodes.set_visible(first.electrode_uuid, False)
    electrodes.LoadState()
    assert not electrodes.get(first.electrode_uuid).visible
    assert electrodes.get(second.electrode_uuid).position == [4.0, 5.0, 6.0]
    session.SetState.reset_mock()
    assert electrodes.remove_many([first.electrode_uuid, first.electrode_uuid, "missing"]) == 1
    session.SetState.assert_called_once()
    assert electrodes.next_label() == "E1"
    assert electrodes.get(second.electrode_uuid) is not None
    assert state["markers"] == original_markers


def test_migrate_legacy_eeg_state_once_and_preserve_newer_electrodes(manager):
    electrodes, state, session = manager
    current = electrodes.create([1.0, 2.0, 3.0], label="Cz")
    state["markers"].append(
        {
            "marker_type": 5,
            "label": "E1",
            "eeg_matched_name": "OldCz",
            "position": [0.0, 0.0, 0.0],
            "marker_uuid": current.electrode_uuid,
        }
    )
    state["markers"].append(
        {
            "marker_type": 5,
            "label": "E2",
            "eeg_matched_name": "Pz",
            "position": [4.0, 5.0, 6.0],
            "marker_uuid": "legacy-pz",
            "visible": False,
        }
    )
    electrodes.LoadState()
    assert electrodes.get(current.electrode_uuid).label == "Cz"
    assert electrodes.get("legacy-pz").label == "Pz"
    assert not electrodes.get("legacy-pz").visible
    assert state["markers"] == [{"marker_type": 1, "label": "Target"}]
    session.SetState.reset_mock()
    electrodes.LoadState()
    assert len(electrodes.electrodes) == 2
    session.SetState.assert_not_called()


def test_invalid_migration_leaves_saved_state_untouched(manager):
    electrodes, state, session = manager
    state["markers"].append({"marker_type": 5, "label": "Cz", "position": [float("nan"), 0, 0]})
    original_state = deepcopy(state)
    with pytest.raises(ValueError):
        electrodes.LoadState()
    session.SetState.assert_not_called()
    assert state["markers"][1]["label"] == original_state["markers"][1]["label"]
    assert "eeg_electrodes" not in state


def test_capture_requires_recent_visible_probe_and_head(manager, monkeypatch):
    electrodes, _, _ = manager
    now = [10.0]
    monkeypatch.setattr(eeg, "monotonic", lambda: now[0])
    with pytest.raises(RuntimeError, match="Start navigation"):
        electrodes.get_capture_position()
    electrodes.on_navigation_status(True, [])
    for probe_visible, head_visible in [(False, True), (True, False), (False, False)]:
        electrodes.update_probe_pose(None, [1, 2, 3], probe_visible, head_visible)
        with pytest.raises(RuntimeError, match="tracked"):
            electrodes.get_capture_position()
    electrodes.update_probe_pose(None, [1, 2, 3], True, True)
    captured = electrodes.get_capture_position()
    captured[0] = 99
    assert electrodes.get_capture_position() == [1, 2, 3]
    now[0] += 1.01
    with pytest.raises(RuntimeError, match="tracked"):
        electrodes.get_capture_position()


def test_projection_uses_display_coordinates_and_preserves_confirmed_capture(manager):
    electrodes, _, _ = manager
    geometry = electrodes.surface_geometry
    geometry.GetClosestPointOnSurface.return_value = ([1.0, -2.0, 3.0], (0.0, 0.0, 1.0))
    geometry.OrientationFromNormal.return_value = [0.0, 0.0, 0.0]
    capture = electrodes.project_to_scalp([1.0, 2.0, 7.0])
    assert capture.position == [1.0, 2.0, 3.0]
    assert capture.distance_mm == 4.0
    assert capture.needs_confirmation
    geometry.GetClosestPointOnSurface.assert_called_once_with(
        "scalp", [1.0, -2.0, 7.0], smooth_radius=15.0
    )
    electrode = electrodes.create_from_capture(capture)
    assert electrode.position == capture.position
    geometry.GetClosestPointOnSurface.assert_called_once()


def test_reset_clears_only_eeg_and_invalidates_capture(manager):
    electrodes, state, _ = manager
    electrodes.create([1.0, 2.0, 3.0])
    electrodes.set_registration_active(True)
    electrodes.on_navigation_status(True, [])
    electrodes.on_navigation_mode(False)
    assert electrodes.electrodes == []
    assert not electrodes.registration_active
    assert not electrodes.navigation_on
    assert state["markers"] == [{"marker_type": 1, "label": "Target"}]


@pytest.mark.parametrize(
    "options",
    [
        {"position": [1, 2]},
        {"position": [float("inf"), 2, 3]},
        {"orientation": [float("nan"), 0, 0]},
        {"colour": [0, 2, 0]},
        {"size": 0},
        {"label": ""},
        {"electrode_uuid": ""},
    ],
)
def test_electrode_rejects_invalid_data(options):
    with pytest.raises(ValueError):
        EEGElectrode(**({"position": [1, 2, 3], "label": "Cz"} | options))
