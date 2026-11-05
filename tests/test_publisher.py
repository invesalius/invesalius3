import os
import sys
from unittest.mock import call

import pytest

from invesalius.pubsub.pub import (
    add_sendMessage_hook,
    sendMessage,
    sendMessage_no_hook,
    subscribe,
    unsubscribe,
    unsubscribe_owner,
)


@pytest.fixture
def mock_publisher(mocker):
    return mocker.patch("invesalius.pubsub.pub.Publisher")


def test_subscribe(mock_publisher, mocker):
    mock_publisher.subscribe.return_value = ("mocked_listener", True)
    mock_listener = mocker.Mock()
    listener, success = subscribe(mock_listener, "dummy_topic")
    mock_publisher.subscribe.assert_called_once_with(mock_listener, "dummy_topic")
    assert listener == "mocked_listener"
    assert success is True


def test_unsubscribe(mocker):
    mock_publisher = mocker.patch("invesalius.pubsub.pub.Publisher.unsubscribe")
    mock_listener = mocker.Mock()
    unsubscribe(mock_listener, "test_topic", arg1="value")
    mock_publisher.assert_called_once_with(mock_listener, "test_topic", arg1="value")
    assert unsubscribe(mock_listener, "test_topic") is None


def test_send_message(mock_publisher):
    """Test that sendMessage() calls Publisher.sendMessage() correctly."""
    sendMessage("test_topic", key="value")
    mock_publisher.sendMessage.assert_called_once_with("test_topic", key="value")


def test_send_message_no_hook(mock_publisher):
    """Test that sendMessage_no_hook() calls Publisher.sendMessage() and does not trigger hooks."""
    sendMessage_no_hook("test_topic", key="value")
    mock_publisher.sendMessage.assert_called_once_with("test_topic", key="value")


def test_send_message_with_hook(mock_publisher, mocker):
    """Test that sendMessage() triggers the added hook function."""
    mock_hook = mocker.Mock()
    add_sendMessage_hook(mock_hook)
    sendMessage("test_topic", key="value")
    mock_publisher.sendMessage.assert_called_once_with("test_topic", key="value")
    mock_hook.assert_called_once_with("test_topic", {"key": "value"})


def test_send_message_no_hook_does_not_trigger_hook(mock_publisher, mocker):
    """Test that sendMessage_no_hook() does not call the hook function."""
    mock_hook = mocker.Mock()
    add_sendMessage_hook(mock_hook)
    sendMessage_no_hook("test_topic", key="value")
    mock_publisher.sendMessage.assert_called_once_with("test_topic", key="value")
    mock_hook.assert_not_called()


def test_send_message_hook_is_called(mocker):
    mock_publisher = mocker.patch("invesalius.pubsub.pub.Publisher.sendMessage")
    mock_hook1 = mocker.Mock()
    mock_hook2 = mocker.Mock()
    add_sendMessage_hook(mock_hook1)
    add_sendMessage_hook(mock_hook2)  # This overwrites mock_hook1
    sendMessage("test_topic", key="value")
    mock_publisher.assert_called_once_with("test_topic", key="value")
    # Since hook1 was overwritten, it should NOT be called
    mock_hook1.assert_not_called()
    mock_hook2.assert_called_once_with("test_topic", {"key": "value"})


def test_unsubscribe_owner_filters_bound_methods_by_owner(mock_publisher, mocker):
    class Subscriber:
        def callback(self):
            pass

    owner = Subscriber()
    other = Subscriber()
    mock_publisher.unsubAll.return_value = ["unsubscribed_listener"]

    result = unsubscribe_owner(owner)

    listener_filter = mock_publisher.unsubAll.call_args.kwargs["listenerFilter"]
    owned_listener = mocker.Mock()
    owned_listener.getCallable.return_value = owner.callback
    other_listener = mocker.Mock()
    other_listener.getCallable.return_value = other.callback
    dead_listener = mocker.Mock()
    dead_listener.getCallable.return_value = None

    assert listener_filter(owned_listener) is True
    assert listener_filter(other_listener) is False
    assert listener_filter(dead_listener) is False
    assert result == ["unsubscribed_listener"]


def test_unsubscribe_owner_keeps_other_instances_subscribed():
    class Subscriber:
        def __init__(self):
            self.values = []

        def callback(self, value):
            self.values.append(value)

    owner = Subscriber()
    other = Subscriber()
    subscribe(owner.callback, "unsubscribe_owner_test")
    subscribe(other.callback, "unsubscribe_owner_test")

    try:
        unsubscribe_owner(owner)
        sendMessage_no_hook("unsubscribe_owner_test", value=42)

        assert owner.values == []
        assert other.values == [42]
    finally:
        unsubscribe_owner(owner)
        unsubscribe_owner(other)
