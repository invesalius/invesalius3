import multiprocessing
import os
import tempfile

import numpy as np
import pytest
from scipy import ndimage
from scipy.ndimage import generate_binary_structure

from invesalius.data import watershed_process
from invesalius.data.mask import Mask
from invesalius.data.slice_ import Slice
from invesalius.data.styles import WaterShedInteractorStyle
from invesalius_cy import floodfill


def test_region_growing_threshold():
    # Dummy Image
    image = np.array(
        [
            [
                [1, 1, 1, 5, 5],
                [1, 2, 2, 5, 5],
                [1, 2, 3, 5, 5],
                [1, 2, 2, 5, 5],
                [1, 1, 1, 5, 5],
            ]
        ],
        dtype=np.int16,
    )
    # single starting point for the region growing.
    seed = [[2, 2, 0]]
    t0 = 2
    t1 = 3
    bstruct = generate_binary_structure(3, 1)
    out_mask = np.zeros((1, 5, 5), dtype=np.uint8)
    floodfill.floodfill_threshold(image, seed, t0, t1, 1, bstruct, out_mask)
    # The 2s and 3s are made 1
    expected = np.array(
        [
            [0, 0, 0, 0, 0],
            [0, 1, 1, 0, 0],
            [0, 1, 1, 0, 0],
            [0, 1, 1, 0, 0],
            [0, 0, 0, 0, 0],
        ],
        dtype=np.uint8,
    )
    assert np.array_equal(
        out_mask[0], expected
    ), f"Region growing incorrect.\nExpected:\n{expected}\nGot:\n{out_mask[0]}"


def test_region_growing_strct_disconnected():
    # Dummy image
    image = np.array(
        [
            [
                [2, 2, 0],
                [0, 2, 0],
                [0, 0, 2],
            ]
        ],
        dtype=np.int16,
    )
    seed = [[0, 0, 0]]
    t0 = 2
    t1 = 2
    # All are connected including the diagonal
    bstruct8 = generate_binary_structure(3, 2)
    out_mask8 = np.zeros((1, 3, 3), dtype=np.uint8)
    floodfill.floodfill_threshold(image, seed, t0, t1, 1, bstruct8, out_mask8)
    expected8 = np.array(
        [
            [
                [1, 1, 0],
                [0, 1, 0],
                [0, 0, 1],
            ]
        ],
        dtype=np.uint8,
    )
    assert np.array_equal(
        out_mask8, expected8
    ), f" Both diagonals filled.\nExpected:\n{expected8}\nGot:\n{out_mask8}"
    # diagonals are NOT connected (only neighbours connected), so only the starting 2 and its neighbours is filled as the rest 2 are not connected
    bstruct4 = generate_binary_structure(3, 1)
    out_mask4 = np.zeros((1, 3, 3), dtype=np.uint8)
    floodfill.floodfill_threshold(image, seed, t0, t1, 1, bstruct4, out_mask4)
    expected4 = np.array(
        [
            [
                [1, 1, 0],
                [0, 1, 0],
                [0, 0, 0],
            ]
        ],
        dtype=np.uint8,
    )
    assert np.array_equal(
        out_mask4, expected4
    ), f"only neighbour regions are filled\nExpected:\n{expected4}\nGot:\n{out_mask4}"


def test_fill_holes_automatically():
    mask_2d = np.ones((7, 7), dtype=np.uint8)
    mask_2d[3, 3] = 0  # single-pixel hole
    mask = mask_2d[np.newaxis, ...]

    structure = np.ones((3, 3), dtype=np.uint8)
    labels_2d, nlabels = ndimage.label(mask_2d == 0, structure=structure, output=np.uint16)
    border_labels = set()
    for i in range(labels_2d.shape[0]):
        border_labels.add(labels_2d[i, 0])
        border_labels.add(labels_2d[i, -1])
    for j in range(labels_2d.shape[1]):
        border_labels.add(labels_2d[0, j])
        border_labels.add(labels_2d[-1, j])
    for bl in border_labels:
        labels_2d[labels_2d == bl] = 0
    labels = labels_2d[np.newaxis, ...]
    nlabels = int(labels.max())

    max_size = 1

    ret = floodfill.fill_holes_automatically(mask, labels, nlabels, max_size)

    expected = np.ones((1, 7, 7), dtype=np.uint8)
    expected[0, 3, 3] = 254  # Only the hole is filled

    assert ret, "fill_holes_automatically function failed"
    assert np.array_equal(
        mask, expected
    ), f"Fill holes failed.\nExpected:\n{expected}\nGot:\n{mask}"


def test_threshold_and_density_measure():
    # Create a dummy image
    image = np.zeros((5, 5, 5), dtype=np.int16)
    image[2, 2, 2] = 100
    image[3, 3, 3] = 200

    mask = Mask()
    mask.create_mask((5, 5, 5))
    mask.threshold_range = (100, 200)

    slc = Slice()
    slc.matrix = image
    slc.current_mask = mask

    slc.do_threshold_to_all_slices(mask)

    # The mask should have 255 at [3,3,3] and [4,4,4] (corresponding to image[2,2,2] and [3,3,3])
    mask_data = mask.matrix[1:, 1:, 1:]
    expected = np.zeros((5, 5, 5), dtype=np.uint8)
    expected[2, 2, 2] = 255
    expected[3, 3, 3] = 255
    assert np.array_equal(
        mask_data, expected
    ), f"Mask thresholding failed.\nExpected:\n{expected}\nGot:\n{mask_data}"

    # calc_image_density will use the mask as set by thresholding
    _min, _max, _mean, _std = slc.calc_image_density(mask)
    assert _min == 100
    assert _max == 200
    assert _mean == 150
    assert _std == 50


def test_do_watershed():
    image = np.zeros((5, 5, 5), dtype=np.int16)
    image[1:4, 1:4, 1:4] = 100

    markers = np.zeros((5, 5, 5), dtype=np.int16)
    markers[2, 2, 2] = 1
    markers[0, 0, 0] = 2

    bstruct = generate_binary_structure(3, 1)

    # queue to check if communication is working
    q = multiprocessing.Queue()

    with tempfile.TemporaryDirectory() as temp_dir:
        tfile = os.path.join(temp_dir, "watershed_mask.tmp")

        tmp_mask = np.memmap(tfile, shape=(5, 5, 5), dtype="uint8", mode="w+")

        watershed_process.do_watershed(
            image=image,
            markers=markers,
            tfile=tfile,
            shape=(5, 5, 5),
            bstruct=bstruct,
            algorithm="Watershed",
            mg_size=(3, 3, 3),
            use_ww_wl=False,
            wl=0,
            ww=0,
            q=q,
        )

        result = tmp_mask.copy()
        tmp_mask._mmap.close()
        del tmp_mask

        assert np.any(result > 0), "Watershed should produce segmentation"

        # Check that the queue received a completion signal
        assert not q.empty(), "Queue should contain completion signal"
        completion_signal = q.get()
        assert completion_signal == 1, "Completion signal should be 1"


class MockSliceData:
    def __init__(self):
        self.number = 0
        self.cursor = None

    def SetCursor(self, cursor):
        self.cursor = cursor


class MockViewer:
    def __init__(self):
        self.slice_ = MockSlice()
        self.orientation = "AXIAL"
        self.slice_data = MockSliceData()
        self._brush_cursor_colour = (1.0, 1.0, 1.0)


class MockSlice:
    def __init__(self):
        self.spacing = [1.0, 1.0, 1.0]


class TestStyle(WaterShedInteractorStyle):
    def __init__(self):
        super().__init__(MockViewer())
        self.matrix = np.zeros((5, 5, 5), dtype=np.uint8)


@pytest.mark.parametrize(
    "orientation,slice_idx,position,brush_shape,expected_positions",
    [
        ("AXIAL", 2, (2, 2), (2, 2), [(2, 2), (2, 3), (3, 2), (3, 3)]),
        ("CORONAL", 2, (2, 2), (2, 2), [(2, 2), (2, 3), (3, 2), (3, 3)]),
        ("SAGITAL", 2, (2, 2), (2, 2), [(2, 2), (2, 3), (3, 2), (3, 3)]),
    ],
)
def test_edit_mask_pixel_orientations(
    orientation, slice_idx, position, brush_shape, expected_positions
):
    style = TestStyle()
    brush = np.ones(brush_shape, dtype=bool)

    style.edit_mask_pixel(255, slice_idx, brush, position, 1, orientation)

    if orientation == "AXIAL":
        mask = style.matrix[slice_idx, :, :]
    elif orientation == "CORONAL":
        mask = style.matrix[:, slice_idx, :]
    else:  # SAGITAL
        mask = style.matrix[:, :, slice_idx]

    # Verify brush was applied at expected positions
    for y, x in expected_positions:
        assert mask[y, x] == 255, f"Brush should be applied at position ({y}, {x})"

    # Verify if the expected number of pixels were changed
    total_modified = np.sum(mask == 255)
    expected_count = len(expected_positions)
    assert (
        total_modified == expected_count
    ), f"Expected {expected_count} modified pixels, got {total_modified}"


@pytest.mark.parametrize("operation_value", [0, 128, 255])
def test_edit_mask_pixel_operation_values(operation_value):
    style = TestStyle()
    brush = np.ones((2, 2), dtype=bool)

    style.edit_mask_pixel(operation_value, 2, brush, (2, 2), 1, "AXIAL")

    if operation_value > 0:
        assert (
            style.matrix[2, 2, 2] == operation_value
        ), f"Operation value should be {operation_value}, got {style.matrix[2, 2, 2]}"
    else:
        assert not np.any(style.matrix > 0), "Operation value 0 should not modify matrix"


@pytest.mark.parametrize(
    "position,should_modify",
    [
        ((2, 2), True),
        ((0, 0), True),
        ((10, 10), False),
        ((-5, -5), False),
    ],
)
def test_edit_mask_pixel_boundaries(position, should_modify):
    style = TestStyle()
    brush = np.ones((3, 3), dtype=bool)

    style.edit_mask_pixel(255, 2, brush, position, 1, "AXIAL")

    if should_modify:
        assert np.any(style.matrix > 0), f"Brush at {position} should modify matrix"
    else:
        assert not np.any(style.matrix > 0), f"Brush at {position} should not modify matrix"
