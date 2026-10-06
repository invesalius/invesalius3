import numpy as np

import invesalius.constants as const
from invesalius.data.coordinates import GetCoordinatesForThread


def test_get_coordinates_for_thread_no_tracker():
    """When no tracker is selected (tracker_id == SELECT), the function
    should return (None, None) instead of raising an UnboundLocalError."""
    coord, marker_visibilities = GetCoordinatesForThread(None, const.SELECT, 0)
    assert coord is None
    assert marker_visibilities is None


def test_get_coordinates_for_thread_dispatches_tracker(mocker):
    expected_coord = np.array([[1, 2, 3]])
    expected_vis = [True, True, True]
    mock_coord = mocker.patch(
        "invesalius.data.coordinates.PolhemusCoord",
        return_value=(expected_coord, expected_vis),
    )
    coord, marker_visibilities = GetCoordinatesForThread(None, const.FASTRAK, 1)
    mock_coord.assert_called_once_with(None, const.FASTRAK, 1)
    assert coord is expected_coord
    assert marker_visibilities is expected_vis
