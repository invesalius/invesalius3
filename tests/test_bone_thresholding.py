from typing import Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from invesalius.data.slice_ import Slice
from invesalius.presets import Presets
from invesalius.project import Project


@pytest.fixture
def mock_slice() -> Generator[Slice, None, None]:
    """Create a mock Slice instance with necessary attributes."""
    slice_: Slice = Slice()
    slice_.matrix = np.random.randint(1, 1000, (10, 10, 10), dtype=np.int16)
    slice_.spacing = (1.0, 1.0, 1.0)
    yield slice_
    slice_._matrix = None
    slice_.discard_all_buffers()


@pytest.fixture
def mock_presets() -> Presets:
    presets = Presets()
    return presets


@pytest.fixture
def mock_project() -> Project:
    project = Project()
    project.threshold_modes = {
        "Bone": (226, 3071),
        "Compact Bone (Adult)": (662, 1988),
        "Compact Bone (Child)": (586, 2198),
        "Spongial Bone (Adult)": (148, 661),
        "Spongial Bone (Child)": (156, 585),
    }
    return project


def test_bone_threshold_presets(mock_presets: Presets) -> None:
    # Test adult bone thresholds
    assert mock_presets.thresh_ct["Bone"] == (226, 3071)
    assert mock_presets.thresh_ct["Compact Bone (Adult)"] == (662, 1988)
    assert mock_presets.thresh_ct["Spongial Bone (Adult)"] == (148, 661)
    assert mock_presets.thresh_ct["Compact Bone (Child)"] == (586, 2198)
    assert mock_presets.thresh_ct["Spongial Bone (Child)"] == (156, 585)


def test_set_mask_threshold(mock_slice: Slice, mock_presets: Presets, mocker) -> None:
    """Test setting mask threshold for bone segmentation."""
    # Get bone threshold range from presets
    bone_min, bone_max = mock_presets.thresh_ct["Bone"]

    # Create test data
    test_image = np.random.randint(
        0, bone_min - 1, (10, 10), dtype=np.int16
    )  # Values below bone range
    test_image[5:8, 5:8] = (
        bone_min + bone_max
    ) // 2  # Set a specific region to middle of bone range

    mock_slice.buffer_slices["AXIAL"].image = test_image
    mock_slice.buffer_slices["AXIAL"].mask = np.random.randint(0, 256, (10, 10), dtype=np.uint8)

    # Mock the Publisher to prevent actual message sending
    send_message_mock = mocker.patch("invesalius.data.slice_.Publisher.sendMessage")

    # Create a mock mask and set it as current mask
    mock_mask = MagicMock()
    mock_mask.was_edited = False
    mock_mask.threshold_range = None
    mock_slice.current_mask = mock_mask

    # Add the mask to the project's mask dictionary
    mock_project = Project()
    mock_project.mask_dict = {1: mock_mask}

    # Set bone threshold
    bone_threshold = mock_presets.thresh_ct["Bone"]
    mock_slice.SetMaskThreshold(1, bone_threshold, slice_number=5, orientation="AXIAL")

    # Verify threshold was applied correctly
    expected_mask = np.zeros((10, 10), dtype=np.uint8)
    expected_mask[5:8, 5:8] = 255
    assert np.array_equal(mock_slice.buffer_slices["AXIAL"].mask, expected_mask)
    assert mock_mask.threshold_range == bone_threshold
    assert send_message_mock.called, "Publisher.sendMessage should have been called."


def test_do_threshold_to_a_slice(mock_slice: Slice, mock_presets: Presets) -> None:
    """Test thresholding a single slice."""
    bone_min, bone_max = mock_presets.thresh_ct["Bone"]

    slice_matrix = np.random.randint(
        0, bone_min - 1, (10, 10), dtype=np.int16
    )  # Values below bone range
    slice_matrix[5:8, 5:8] = (
        bone_min + bone_max
    ) // 2  # Set a specific region to middle of bone range

    initial_mask = np.zeros((10, 10), dtype=np.uint8)
    initial_mask[0:2, 0:2] = 1
    initial_mask[2:4, 2:4] = 2
    initial_mask[4:6, 4:6] = 253
    initial_mask[6:8, 6:8] = 254

    result = mock_slice.do_threshold_to_a_slice(slice_matrix, initial_mask, (bone_min, bone_max))

    expected = np.zeros((10, 10), dtype=np.uint8)
    expected[5:8, 5:8] = 255
    expected[0:2, 0:2] = 1
    expected[2:4, 2:4] = 2
    expected[4:6, 4:6] = 253
    expected[6:8, 6:8] = 254

    assert np.array_equal(result, expected)


def test_do_threshold_to_all_slices(mock_slice: Slice, mock_presets: Presets, mocker) -> None:
    """Test applying bone threshold to all slices."""
    # Get bone threshold range from presets
    bone_min, bone_max = mock_presets.thresh_ct["Bone"]

    test_volume = np.random.randint(
        0, bone_min - 1, (10, 10, 10), dtype=np.int16
    )  # Values below bone range
    test_volume[5:8, 5:8, 5:8] = (bone_min + bone_max) // 2

    mock_slice.matrix = test_volume

    from invesalius.data.mask import Mask

    mask = Mask()

    try:
        # passing the mask to the current mask so that the function uses the mask
        mask.create_mask(mock_slice.matrix.shape)
        mask.threshold_range = (bone_min, bone_max)
        mock_slice.current_mask = mask

        mocker.patch("invesalius.data.slice_.Publisher.sendMessage")

        mock_slice.do_threshold_to_all_slices()

        expected_mask = np.zeros((10, 10, 10), dtype=np.uint8)
        expected_mask[5:8, 5:8, 5:8] = 255  # Values in threshold range should be 255
        assert np.array_equal(mask.matrix[1:, 1:, 1:], expected_mask)
    finally:
        # cleaning up the memory-mapped array
        if hasattr(mask, "matrix"):
            del mask.matrix


def test_bone_threshold_edge_cases(mock_slice: Slice, mock_project: Project, mocker) -> None:
    test_image = np.zeros((10, 10), dtype=np.int16)
    test_image[0, 0] = 226  # Lower bone threshold
    test_image[0, 1] = 3071  # Upper bone threshold
    test_image[0, 2] = 225  # Below threshold
    test_image[0, 3] = 3072  # Above threshold

    # Initialize the buffer with image and mask
    mock_slice.buffer_slices["AXIAL"].image = test_image
    mock_slice.buffer_slices["AXIAL"].mask = np.zeros((10, 10), dtype=np.uint8)
    mocker.patch("invesalius.data.slice_.Publisher.sendMessage")

    from invesalius.data.mask import Mask

    mask = Mask()
    mask.create_mask((1, 10, 10))
    mock_slice.current_mask = mask
    mock_project.mask_dict = {1: mask}

    # Set bone threshold
    bone_threshold = mock_project.threshold_modes["Bone"]
    mock_slice.SetMaskThreshold(1, bone_threshold, slice_number=0, orientation="AXIAL")

    # Verify threshold was applied correctly
    expected_mask = np.zeros((10, 10), dtype=np.uint8)
    expected_mask[0, 0] = 255
    expected_mask[0, 1] = 255
    expected_mask[0, 2] = 0
    expected_mask[0, 3] = 0
    assert np.array_equal(mock_slice.buffer_slices["AXIAL"].mask, expected_mask)
