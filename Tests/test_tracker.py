import pytest
import numpy as np
from unittest.mock import MagicMock
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from invesalius.navigation.tracker import Tracker
import invesalius.data.tracker_connection as tc
import invesalius.constants as const
import invesalius.session as ses
import invesalius.data.coordinates as dco
import wx

if not wx.GetApp():
    app = wx.App(False)

@pytest.fixture
def tracker():
    return Tracker()

def test_tracker_initialization(mocker):
    mock_load_state = mocker.patch.object(Tracker, "LoadState")
    mock_delete_state = mocker.patch.object(ses.Session, "DeleteStateFile")
    tracker = Tracker()
    assert tracker.tracker_connection is None
    assert tracker.tracker_id == const.DEFAULT_TRACKER
    assert tracker.tracker_connected is False
    assert tracker.tracker_fiducials.shape == (3, 3)
    assert tracker.tracker_fiducials_raw.shape == (6, 6)
    assert tracker.m_tracker_fiducials_raw.shape == (6, 4, 4)

    mock_load_state.assert_called_once()

def test_save_state(mocker, tracker):
    mock_set_state = mocker.patch.object(ses.Session, "SetState")
    tracker.SaveState()
    expected_state = {
        "tracker_id": tracker.tracker_id,
        "tracker_fiducials": tracker.tracker_fiducials.tolist(),
        "tracker_fiducials_raw": tracker.tracker_fiducials_raw.tolist(),
        "marker_tracker_fiducials_raw": tracker.m_tracker_fiducials_raw.tolist(),
        "configuration": tracker.tracker_connection.GetConfiguration() if tracker.tracker_connection else None,
    }
    actual_call = mock_set_state.call_args[0][1]
    def replace_nan_with_none(lst):
        return [[None if np.isnan(x) else x for x in row] for row in lst]

    expected_state["tracker_fiducials"] = replace_nan_with_none(expected_state["tracker_fiducials"])
    actual_call["tracker_fiducials"] = replace_nan_with_none(actual_call["tracker_fiducials"])
    assert expected_state == actual_call
    mock_set_state.assert_called_once()

def test_load_state(mocker, tracker):
    mock_get_state = mocker.patch.object(ses.Session, "GetState", return_value={
        "tracker_id": 1,
        "tracker_fiducials": [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
        "tracker_fiducials_raw": np.zeros((6, 6)).tolist(),
        "marker_tracker_fiducials_raw": np.zeros((6, 4, 4)).tolist(),
        "configuration": None,
    })
    mock_set_tracker = mocker.patch.object(tracker, "SetTracker")

    tracker.LoadState()

    assert tracker.tracker_id == 1
    assert (tracker.tracker_fiducials == np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]])).all()
    mock_set_tracker.assert_called_once_with(tracker_id=1, configuration=None)

def test_set_tracker(mocker, tracker):
    mock_tracker_conn = mocker.MagicMock()
    mock_tracker_conn.GetConfiguration.return_value = {"param1": 10, "param2": "value"}
    mocker.patch("invesalius.data.tracker_connection.CreateTrackerConnection", return_value=mock_tracker_conn)
    tracker.SetTracker(tracker_id=1)
    assert tracker.tracker_connection is not None
    assert isinstance(tracker.tracker_connection.GetConfiguration(), dict)

def test_get_tracker_coordinates(mocker, tracker):
    mock_get_coords = mocker.patch.object(tracker.TrackerCoordinates, "GetCoordinates", side_effect=[
        (np.array([[1, 2, 3], [4, 5, 6]]), (True, True, True)),
        (np.array([[2, 3, 4], [5, 6, 7]]), (True, True, True))
    ])

    visibilities, coord_avg, coord_raw_avg = tracker.GetTrackerCoordinates(ref_mode_id=0, n_samples=2)

    assert visibilities == (True, True, True)
    assert np.allclose(coord_avg, np.array([1.5, 2.5, -3.5]), atol=1e-6)
    assert np.allclose(coord_raw_avg, np.array([[1.5, 2.5, -3.5], [4.5, 5.5, 6.5]]), atol=1e-6)

def test_get_tracker_id(tracker):
    tracker.tracker_id = 10
    assert tracker.GetTrackerId() == 10
