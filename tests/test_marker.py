from unittest.mock import patch

import pytest

from invesalius.data.markers.marker import Marker, MarkerType


@pytest.fixture
def mock_world_conversion():
    """Isolates Marker.to_brain_targets_dict() from invesalius.data.slice_.Slice(),
    a process-wide singleton whose state depends on whether a project is loaded."""
    with patch(
        "invesalius.data.markers.marker.imagedata_utils.convert_invesalius_to_world"
    ) as mock_convert:
        mock_convert.return_value = ((None, None, None), (None, None, None))
        yield mock_convert


def test_marker_has_mtms_fields_by_default():
    marker = Marker()
    assert marker.x_mtms is None
    assert marker.y_mtms is None
    assert marker.r_mtms is None
    assert marker.intensity_mtms is None


def test_to_brain_targets_dict_without_mtms_data(mock_world_conversion):
    """Regression test for #1468: creating a brain target through the plain,
    non-mTMS flow (as in TaskPanel.OnSetBrainTarget) must not raise AttributeError."""
    marker = Marker(marker_type=MarkerType.BRAIN_TARGET, x=1.0, y=2.0, z=3.0)

    result = marker.to_brain_targets_dict()

    assert result["x_mtms"] is None
    assert result["y_mtms"] is None
    assert result["r_mtms"] is None
    assert result["intensity_mtms"] is None


def test_to_brain_targets_dict_with_mtms_data(mock_world_conversion):
    """Markers created through the mTMS flow still carry their mTMS coordinates through."""
    marker = Marker(marker_type=MarkerType.BRAIN_TARGET, x=1.0, y=2.0, z=3.0)
    marker.x_mtms = 10.5
    marker.y_mtms = -3.2
    marker.r_mtms = 45.0
    marker.intensity_mtms = 10

    result = marker.to_brain_targets_dict()

    assert result["x_mtms"] == 10.5
    assert result["y_mtms"] == -3.2
    assert result["r_mtms"] == 45.0
    assert result["intensity_mtms"] == 10


def test_to_brain_targets_dict_with_orientation(mock_world_conversion):
    """Same regression as above, but through the branch taken when alpha/beta/gamma
    are set (e.g. coil targets promoted to brain targets)."""
    marker = Marker(
        marker_type=MarkerType.BRAIN_TARGET,
        x=1.0,
        y=2.0,
        z=3.0,
        alpha=10.0,
        beta=20.0,
        gamma=30.0,
    )

    result = marker.to_brain_targets_dict()

    assert result["x_mtms"] is None
    assert result["y_mtms"] is None
    assert result["r_mtms"] is None
    assert result["intensity_mtms"] is None


def test_duplicate_preserves_mtms_fields():
    marker = Marker(marker_type=MarkerType.BRAIN_TARGET)
    marker.x_mtms = 1.0
    marker.y_mtms = 2.0
    marker.r_mtms = 3.0
    marker.intensity_mtms = 4.0

    duplicate = marker.duplicate()

    assert duplicate.x_mtms == 1.0
    assert duplicate.y_mtms == 2.0
    assert duplicate.r_mtms == 3.0
    assert duplicate.intensity_mtms == 4.0
