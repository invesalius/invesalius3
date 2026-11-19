from unittest.mock import patch

import pytest

from invesalius.data.markers.marker import Marker, MarkerType


def test_marker_defaults():
    marker = Marker()
    assert marker.version == 3
    assert marker.marker_id == 0
    assert marker.position == [0, 0, 0]
    assert marker.orientation == [None, None, None]
    assert marker.colour == [0, 1, 0]
    assert marker.size == 2
    assert marker.label == ""
    assert marker.is_target is False
    assert marker.is_point_of_interest is False
    assert marker.session_id == 1
    assert marker.marker_type == MarkerType.LANDMARK
    assert marker.marker_uuid == ""


#### Tests for confirming that the `@property` mechanism works as expected.
def test_marker_position():
    marker = Marker()
    marker.position = [1, 2, 3]
    assert marker.position == [1, 2, 3]
    assert marker.x == 1
    assert marker.y == 2
    assert marker.z == 3


def test_marker_orientation():
    marker = Marker()
    marker.orientation = [0.1, 0.2, 0.3]
    assert marker.orientation == [0.1, 0.2, 0.3]
    assert marker.alpha == 0.1
    assert marker.beta == 0.2
    assert marker.gamma == 0.3


def test_marker_colour():
    marker = Marker()
    marker.colour = [0.5, 0.6, 0.7]
    assert marker.colour == [0.5, 0.6, 0.7]
    assert marker.r == 0.5
    assert marker.g == 0.6
    assert marker.b == 0.7


def test_marker_colour8bit():
    marker = Marker()
    marker.colour8bit = [128, 255, 64]
    assert marker.colour8bit == [128, 255, 64]
    assert marker.colour == [128 / 255, 1.0, 64 / 255]


def test_marker_seed():
    marker = Marker()
    marker.seed = [4, 5, 6]
    assert marker.seed == [4, 5, 6]
    assert marker.x_seed == 4
    assert marker.y_seed == 5
    assert marker.z_seed == 6


def test_marker_to_dict():
    marker = Marker(label="TestLabel", is_target=True)
    data = marker.to_dict()
    assert data["label"] == "TestLabel"
    assert data["is_target"] is True


data_cases = [
    (
        {
            "position": [1.0, 2.0, 3.0],
            "orientation": [0.1, 0.2, 0.3],
            "colour": [0.5, 0.5, 0.5],
            "size": 5.0,
            "label": "Test",
            "is_target": True,
            "session_id": 42,
            "marker_type": MarkerType.LANDMARK.value,
            "seed": [4.0, 5.0, 6.0],
            "cortex_position_orientation": [1, 2, 3, 4, 5, 6],
            "z_rotation": 1.0,
            "z_offset": 2.0,
            "mep_value": None,
            "brain_target_list": [],
            "marker_uuid": "test-uuid",
        },
        Marker(
            x=1.0,
            y=2.0,
            z=3.0,
            alpha=0.1,
            beta=0.2,
            gamma=0.3,
            r=0.5,
            g=0.5,
            b=0.5,
            size=5.0,
            label="Test",
            is_target=True,
            session_id=42,
            marker_type=MarkerType.LANDMARK,
            x_seed=4.0,
            y_seed=5.0,
            z_seed=6.0,
            x_cortex=1,
            y_cortex=2,
            z_cortex=3,
            alpha_cortex=4,
            beta_cortex=5,
            gamma_cortex=6,
            z_rotation=1.0,
            z_offset=2.0,
            mep_value=None,
            brain_target_list=[],
            marker_uuid="test-uuid",
        ),
    ),
    # Empty field test cases with default values
    (
        {
            "label": "LEI",
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
            "r": 1.0,
            "g": 1.0,
            "b": 1.0,
            "size": 1.0,
            "is_target": False,
            "session_id": 0,
            "marker_type": MarkerType.FIDUCIAL.value,
            "x_seed": 0.0,
            "y_seed": 0.0,
            "z_seed": 0.0,
            "x_cortex": 0,
            "y_cortex": 0,
            "z_cortex": 0,
            "alpha_cortex": 0,
            "beta_cortex": 0,
            "gamma_cortex": 0,
            "z_rotation": 0.0,
            "z_offset": 0.0,
        },
        Marker(
            x=0.0,
            y=0.0,
            z=0.0,
            alpha=0.0,
            beta=0.0,
            gamma=0.0,
            r=1.0,
            g=1.0,
            b=1.0,
            size=1.0,
            label="LEI",
            is_target=False,
            session_id=0,
            marker_type=MarkerType(MarkerType.FIDUCIAL.value),
            x_seed=0.0,
            y_seed=0.0,
            z_seed=0.0,
            x_cortex=0,
            y_cortex=0,
            z_cortex=0,
            alpha_cortex=0,
            beta_cortex=0,
            gamma_cortex=0,
            z_rotation=0.0,
            z_offset=0.0,
            mep_value=None,
            brain_target_list=[],
            marker_uuid="",
        ),
    ),
]


@pytest.mark.parametrize("input_dict, expected_marker", data_cases)
def test_from_dict(input_dict, expected_marker):
    marker = Marker().from_dict(input_dict)

    assert marker.position == expected_marker.position
    assert marker.orientation == expected_marker.orientation
    assert marker.colour == expected_marker.colour
    assert marker.size == expected_marker.size
    assert marker.label == expected_marker.label
    assert marker.is_target == expected_marker.is_target
    assert marker.session_id == expected_marker.session_id
    assert marker.marker_type == expected_marker.marker_type
    assert marker.seed == expected_marker.seed
    assert marker.cortex_position_orientation == expected_marker.cortex_position_orientation
    assert marker.z_rotation == expected_marker.z_rotation
    assert marker.z_offset == expected_marker.z_offset
    assert marker.mep_value == expected_marker.mep_value
    assert marker.brain_target_list == expected_marker.brain_target_list
    assert marker.marker_uuid == expected_marker.marker_uuid


@patch("uuid.uuid4", return_value="mocked-uuid")
@patch("copy.deepcopy", side_effect=lambda x: x)  # Mock deepcopy to return the same object
def test_duplicate(mock_deepcopy, mock_uuid):
    """
    Test that duplicate creates a deep copy with a new UUID and resets necessary fields.
    """
    marker = Marker()
    marker.position = [1, 2, 3]
    marker.visualization = {"some_key": "some_value"}
    marker.is_target = True
    marker.marker_uuid = "uuid-1"

    duplicate_marker = marker.duplicate()

    # Ensure deep copy was made
    mock_deepcopy.assert_called()

    # Check copied fields
    assert duplicate_marker.position == [1, 2, 3]
    assert duplicate_marker.marker_uuid == "mocked-uuid"
    assert duplicate_marker.visualization == {}  # Visualization should be reset
    assert duplicate_marker.is_target is False
