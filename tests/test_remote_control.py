import pytest

from invesalius.net.remote_control import RemoteControl
from invesalius.pubsub import pub as Publisher


@pytest.fixture
def remote_control():
    return RemoteControl(remote_host="http://example.invalid")


@pytest.fixture
def recorder():
    calls = []

    def handler(objective, robot_id=None):
        calls.append({"objective": objective, "robot_id": robot_id})

    topic = "Robot to Neuronavigation: Set objective"
    Publisher.subscribe(handler, topic)
    yield calls
    Publisher.unsubscribe(handler, topic)


def test_default_allow_list_forwards_robot_topic(remote_control, recorder):
    remote_control._to_neuronavigation(
        {
            "topic": "Robot to Neuronavigation: Set objective",
            "data": {"objective": 1, "robot_id": 0},
        }
    )

    assert recorder == [{"objective": 1, "robot_id": 0}]


def test_default_allow_list_forwards_neurosimo_topic():
    calls = []

    def handler(value):
        calls.append(value)

    topic = "NeuroSimo to Neuronavigation: Test topic"
    Publisher.subscribe(handler, topic)
    try:
        rc = RemoteControl(remote_host="http://example.invalid")
        rc._to_neuronavigation({"topic": topic, "data": {"value": 42}})
    finally:
        Publisher.unsubscribe(handler, topic)

    assert calls == [42]


def test_default_allow_list_rejects_arbitrary_internal_topic(remote_control):
    calls = []

    def handler(**kwargs):
        calls.append(kwargs)

    # "Stop navigation" is a real internal topic with no "<sender> to
    # Neuronavigation:" prefix, so a remote peer should not be able to
    # trigger it.
    Publisher.subscribe(handler, "Stop navigation")
    try:
        remote_control._to_neuronavigation({"topic": "Stop navigation", "data": {}})
    finally:
        Publisher.unsubscribe(handler, "Stop navigation")

    assert calls == []


def test_default_allow_list_rejects_prefix_lookalike(remote_control):
    calls = []

    def handler(**kwargs):
        calls.append(kwargs)

    # Doesn't match "<sender> to Neuronavigation: " since there's no
    # trailing colon-space after "Neuronavigation".
    topic = "Robot to Neuronavigationally confuse this"
    Publisher.subscribe(handler, topic)
    try:
        remote_control._to_neuronavigation({"topic": topic, "data": {}})
    finally:
        Publisher.unsubscribe(handler, topic)

    assert calls == []


def test_non_string_topic_is_rejected_without_raising(remote_control):
    # Should not raise, just be ignored.
    remote_control._to_neuronavigation({"topic": None, "data": {}})
    remote_control._to_neuronavigation({"topic": 123, "data": {}})


def test_none_data_is_treated_as_no_arguments():
    calls = []

    def handler():
        calls.append(True)

    topic = "Robot to Neuronavigation: Ping"
    Publisher.subscribe(handler, topic)
    try:
        rc = RemoteControl(remote_host="http://example.invalid")
        rc._to_neuronavigation({"topic": topic, "data": None})
    finally:
        Publisher.unsubscribe(handler, topic)

    assert calls == [True]


def test_explicit_allowed_topics_overrides_default_pattern():
    calls = []

    def allowed_handler(enabled):
        calls.append({"enabled": enabled})

    def disallowed_handler(objective, robot_id=None):
        calls.append({"objective": objective, "robot_id": robot_id})

    allowed_topic = "Set target mode"
    disallowed_topic = "Robot to Neuronavigation: Set objective"

    Publisher.subscribe(allowed_handler, allowed_topic)
    Publisher.subscribe(disallowed_handler, disallowed_topic)
    try:
        rc = RemoteControl(remote_host="http://example.invalid", allowed_topics={allowed_topic})

        rc._to_neuronavigation({"topic": allowed_topic, "data": {"enabled": True}})
        rc._to_neuronavigation({"topic": disallowed_topic, "data": {"objective": 1}})
    finally:
        Publisher.unsubscribe(allowed_handler, allowed_topic)
        Publisher.unsubscribe(disallowed_handler, disallowed_topic)

    # Only the explicitly allowed topic should have gone through, even
    # though the other one matches the default pattern.
    assert calls == [{"enabled": True}]
