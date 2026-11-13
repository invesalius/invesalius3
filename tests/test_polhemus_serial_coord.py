import numpy as np

import invesalius.constants as const
from invesalius.data.coordinates import PolhemusSerialCoord


def _mock_serial_connection(mocker, lines):
    trck = mocker.MagicMock()
    trck.readlines.return_value = lines
    connector = mocker.MagicMock()
    connector.GetConnection.return_value = trck
    return connector


def test_polhemus_serial_coord_device_not_connected(mocker):
    """When the serial device is not connected, readlines() returns None and
    PolhemusSerialCoord should return None instead of raising UnboundLocalError."""
    connector = _mock_serial_connection(mocker, None)

    coord = PolhemusSerialCoord(connector, const.ISOTRAKII, 0)

    assert coord is None


def test_polhemus_serial_coord_probe_only(mocker):
    line = b"0 1.0 2.0 3.0 4.0 5.0 6.0"
    connector = _mock_serial_connection(mocker, [line])

    coord = PolhemusSerialCoord(connector, const.ISOTRAKII, 0)

    expected = np.vstack([np.array([10.0, 20.0, 30.0, 4.0, 5.0, 6.0]), np.zeros(6)])
    np.testing.assert_allclose(coord, expected)


def test_polhemus_serial_coord_dynamic_reference(mocker):
    lines = [
        b"0 1.0 2.0 3.0 4.0 5.0 6.0",
        b"1 7.0 8.0 9.0 10.0 11.0 12.0",
    ]
    connector = _mock_serial_connection(mocker, lines)

    coord = PolhemusSerialCoord(connector, const.ISOTRAKII, 1)

    expected = np.vstack(
        [
            np.array([10.0, 20.0, 30.0, 4.0, 5.0, 6.0]),
            np.array([70.0, 80.0, 90.0, 10.0, 11.0, 12.0]),
        ]
    )
    np.testing.assert_allclose(coord, expected)
