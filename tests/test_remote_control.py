import pytest
from unittest.mock import patch, MagicMock
import socketio
from socketio import client
import wx
from invesalius.net.remote_control import RemoteControl

@pytest.fixture
def setup_remote_control():
    with patch("socketio.Client") as mock_socketio, patch("wx.CallAfter") as mock_callafter:
        mock_sio_instance = MagicMock()
        mock_socketio.return_value = mock_sio_instance

        remote_host = "http://localhost:5000"
        remote_control = RemoteControl(remote_host)
        yield remote_control, mock_socketio, mock_callafter


def test_initialization(setup_remote_control):
    remote_control, _, _ = setup_remote_control

    assert remote_control._remote_host == "http://localhost:5000"
    assert remote_control._connected is False
    assert remote_control._sio is None


def test_on_connect(setup_remote_control):
    remote_control, _, _ = setup_remote_control

    remote_control._on_connect()

    assert remote_control._connected is True


def test_on_disconnect(setup_remote_control):
    remote_control,_, _ = setup_remote_control

    remote_control._on_disconnect()

    assert remote_control._connected is False


def test_to_neuronavigation(setup_remote_control):
    remote_control, _, _ = setup_remote_control

    with patch("invesalius.pubsub.pub.sendMessage_no_hook") as mock_publisher:
        msg = {"topic": "test_topic", "data": {"key": "value"}}
        remote_control._to_neuronavigation(msg)
        mock_publisher.assert_called_once_with(topicName="test_topic", key="value")


def test_to_neuronavigation_wrapper(setup_remote_control):
    remote_control, _, mock_callafter = setup_remote_control

    msg = {"topic": "test_topic", "data": {"key": "value"}}

    remote_control._to_neuronavigation_wrapper(msg)

    mock_callafter.assert_called_once_with(remote_control._to_neuronavigation, msg)


def test_connect(setup_remote_control):
    remote_control, mock_socketio, mock_callafter = setup_remote_control

    mock_sio_instance = mock_socketio.return_value

    with patch("time.sleep", return_value=None):

        remote_control._connected = True
        remote_control.connect()
        mock_socketio.assert_called_once()

        mock_sio_instance.on.assert_any_call("connect", remote_control._on_connect)
        mock_sio_instance.on.assert_any_call("disconnect", remote_control._on_disconnect)
        mock_sio_instance.on.assert_any_call("to_neuronavigation", remote_control._to_neuronavigation_wrapper)

        mock_sio_instance.connect.assert_called_once_with(remote_control._remote_host)

        mock_sio_instance.emit.assert_called_once_with("restart_robot_main_loop")
