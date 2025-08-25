from threading import Event
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from invesalius.navigation.navigation import Navigation, QueueCustom
from invesalius.pubsub import pub as Publisher


@pytest.fixture
def mock_session(mocker):
    """Fixture to mock session handling."""
    mock_session = mocker.patch("invesalius.session.Session")
    mock_instance = mock_session.return_value
    return mock_instance


@pytest.fixture
def mock_publisher(mocker):
    """Fixture to mock Publisher.sendMessage."""
    return mocker.patch.object(Publisher, "sendMessage")


@pytest.fixture
def mock_navigation(mock_session, mock_publisher):
    """Fixture to create a mock instance of Navigation."""
    pedal_connector = MagicMock()
    neuronavigation_api = MagicMock()
    nav = Navigation(pedal_connector=pedal_connector, neuronavigation_api=neuronavigation_api)
    return nav


def test_queue_custom_clear():
    """Test QueueCustom's clear method."""
    q = QueueCustom()
    q.all_tasks_done.notify_all = MagicMock()
    q.not_full.notify_all = MagicMock()

    q.put(1)
    q.put(2)
    assert q.qsize() == 2

    q.clear()

    assert q.qsize() == 0
    q.all_tasks_done.notify_all.assert_called_once()
    q.not_full.notify_all.assert_called_once()


def test_save_config(mock_navigation, mock_session):
    mock_session.GetConfig.return_value = {}
    nav = mock_navigation

    nav.n_coils = 2
    nav.main_coil = "coil_1"
    nav.r_stylus = np.array(["dummyVal"])
    nav.coil_registrations = {"coil_1": {"path": "/path/to/coil"}}
    nav.track_coil = False
    nav.SaveConfig()

    mock_session.SetConfig.assert_called_once_with(
        "navigation",
        {
            "selected_coils": ["coil_1"],
            "n_coils": 2,
            "track_coil": False,
            "main_coil": "coil_1",
            "r_stylus": ["dummyVal"],
        },
    )


def test_load_config(mock_navigation, mock_session):
    mock_session.GetConfig.side_effect = lambda key, default=None: {
        "navigation": {"n_coils": 2, "track_coil": True, "main_coil": "coil_2"},
        "coil_registrations": {"coil_2": {"fiducials": [], "orientations": []}},
    }.get(key, default)

    nav = mock_navigation
    nav.LoadConfig()

    assert nav.n_coils == 2
    assert nav.track_coil is True
    assert nav.main_coil == "coil_2"


def test_coil_selection(mock_navigation):
    nav = mock_navigation
    nav.SaveConfig = MagicMock()

    nav.main_coil = None
    nav.SelectCoil("coil_1", {"fiducials": [], "orientations": []})
    assert "coil_1" in nav.coil_registrations
    assert nav.main_coil == "coil_1"

    nav.SelectCoil("coil_1", None)
    assert "coil_1" not in nav.coil_registrations
    assert nav.main_coil is None
    assert nav.SaveConfig.call_count > 0


def test_set_no_of_coils(mock_navigation):
    nav = mock_navigation
    nav.SetNoOfCoils(3)

    assert nav.n_coils == 3
    assert nav.coil_registrations == {}
    assert nav.main_coil is None


def test_coil_at_target(mock_navigation):
    nav = mock_navigation
    nav.CoilAtTarget(True)
    assert nav.coil_at_target is True


@patch("invesalius.data.polydata_utils.LoadPolydata")
def test_set_main_coil(mock_load_polydata, mock_navigation):
    mock_polydata = MagicMock()
    mock_load_polydata.return_value = mock_polydata

    mock_navigation.SaveConfig = MagicMock()
    mock_navigation.neuronavigation_api = MagicMock()

    mock_navigation.coil_registrations = {"coil_1": {"path": "/fake/path/to/coil.stl"}}
    mock_navigation.SetMainCoil("coil_1")
    mock_load_polydata.assert_called_once_with("/fake/path/to/coil.stl")
    mock_navigation.neuronavigation_api.update_coil_mesh.assert_called_once_with(mock_polydata)
    mock_navigation.SaveConfig.assert_called_once_with("main_coil", "coil_1")


def test_serial_port_update(mock_navigation):
    nav = mock_navigation
    nav.UpdateSerialPort(serial_port_in_use=True, com_port="COM3", baud_rate=9600)

    assert nav.serial_port_in_use is True
    assert nav.com_port == "COM3"
    assert nav.baud_rate == 9600


def test_pedal_state_changed(mock_navigation, mock_publisher):
    nav = mock_navigation
    nav.serial_port_in_use = True
    nav.lock_to_target = True
    nav.coil_at_target = True
    nav.serial_port_connection = MagicMock()
    nav.PedalStateChanged(True)
    nav.serial_port_connection.SendPulse.assert_called_once()


@patch("invesalius.data.transformations.affine_matrix_from_points")
def test_estimate_tracker_to_inv_transformation_matrix(mock_affine, mock_navigation):
    nav = mock_navigation

    tracker_fiducials = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    tracker_fiducials_raw = np.array([[10, 11, 12], [13, 14, 15], [16, 17, 18]])
    image_fiducials = np.array([[21, 22, 23], [24, 25, 26], [27, 28, 29]])

    mock_tracker = MagicMock()
    mock_tracker.GetTrackerFiducials.return_value = (tracker_fiducials, tracker_fiducials_raw)
    mock_image = MagicMock()
    mock_image.GetImageFiducials.return_value = image_fiducials
    mock_transformation_matrix = np.eye(4)
    mock_affine.return_value = mock_transformation_matrix

    nav.EstimateTrackerToInVTransformationMatrix(mock_tracker, mock_image)
    expected_fiducials = np.vstack([image_fiducials, tracker_fiducials])

    np.testing.assert_array_equal(nav.all_fiducials, expected_fiducials)
    actual_args, actual_kwargs = mock_affine.call_args
    np.testing.assert_array_equal(actual_args[0], expected_fiducials[3:, :].T)
    np.testing.assert_array_equal(actual_args[1], expected_fiducials[:3, :].T)

    assert actual_kwargs == {"shear": False, "scale": False}
    np.testing.assert_array_equal(nav.m_change, mock_transformation_matrix)


@patch("invesalius.data.coregistration.compute_marker_transformation")
@patch("invesalius.data.coregistration.object_to_reference")
@patch("invesalius.data.transformations.euler_matrix")
def test_on_record_stylus_orientation(
    mock_euler_matrix, mock_object_to_reference, mock_compute_marker_transformation, mock_navigation
):
    nav = mock_navigation
    nav.SaveConfig = MagicMock()

    nav.m_change = np.eye(4)
    nav.ref_mode_id = True

    mock_probe_matrix = np.eye(4)
    mock_reference_matrix = np.eye(4)

    mock_compute_marker_transformation.return_value = mock_probe_matrix
    mock_object_to_reference.return_value = mock_reference_matrix

    mock_up_vtk = np.eye(3)
    mock_rot_z = np.eye(3)

    def euler_side_effect(*args, **kwargs):
        if len(args) == 1 and np.array_equal(args[0], np.radians([90.0, 0.0, 0.0])):
            return np.vstack([mock_up_vtk, [0, 0, 0, 1]])
        elif len(args) == 1 and np.array_equal(args[0], np.radians([0, 0, -90])):
            return np.vstack([mock_rot_z, [0, 0, 0, 1]])
        return np.eye(4)

    mock_euler_matrix.side_effect = euler_side_effect

    coord_raw = np.array([1, 2, 3])
    result = nav.OnRecordStylusOrientation(coord_raw)

    assert result is True
    mock_compute_marker_transformation.assert_called_once_with(coord_raw, 0)
    mock_object_to_reference.assert_called_once_with(coord_raw, mock_probe_matrix)
    nav.SaveConfig.assert_called_once_with("r_stylus", nav.r_stylus.tolist())

    expected_x_flip = np.eye(3)
    expected_x_flip[0] *= -1
    expected_r_stylus = (
        expected_x_flip
        @ mock_up_vtk
        @ np.linalg.inv(mock_rot_z @ mock_reference_matrix[:3, :3] @ np.linalg.inv(mock_rot_z))
    )
    np.testing.assert_array_equal(nav.r_stylus, expected_r_stylus)
