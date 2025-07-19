import numpy as np
import pytest
from scipy import ndimage

from invesalius.data.mask import Mask
from invesalius.data.slice_ import Slice
from invesalius_cy import floodfill


def test_region_growing_threshold():
    # Dummy Image
    image = np.array(
        [
            [1, 1, 1, 5, 5],
            [1, 2, 2, 5, 5],
            [1, 2, 3, 5, 5],
            [1, 2, 2, 5, 5],
            [1, 1, 1, 5, 5],
        ],
        dtype=np.int16,
    )

    # single starting point for the region growing.
    seed = [[2, 2, 0]]
    t0 = 2
    t1 = 3
    bstruct = np.ones((1, 3, 3), dtype=np.uint8)
    out_mask = np.zeros((1, 5, 5), dtype=np.uint8)
    image_3d = image[np.newaxis, ...]  # Simulating a 3D array with one slice.
    floodfill.floodfill_threshold(image_3d, seed, t0, t1, 1, bstruct, out_mask)
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
            [2, 2, 0],
            [0, 2, 0],
            [0, 0, 2],
        ],
        dtype=np.int16,
    )

    seed = [[0, 0, 0]]
    t0 = 2
    t1 = 2

    # All are connected including the diagonal
    bstruct8 = np.ones((1, 3, 3), dtype=np.uint8)
    out_mask8 = np.zeros((1, 3, 3), dtype=np.uint8)
    image_3d = image[np.newaxis, ...]
    floodfill.floodfill_threshold(image_3d, seed, t0, t1, 1, bstruct8, out_mask8)
    expected8 = np.array(
        [
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
        ],
        dtype=np.uint8,
    )[np.newaxis, ...]
    assert np.array_equal(
        out_mask8, expected8
    ), f" Both diagonals filled.\nExpected:\n{expected8}\nGot:\n{out_mask8}"

    # diagonals are NOT connected(only neighbours connected), so only the starting 2 and its neighbours is filled as the rest 2 are not connected
    bstruct4 = np.zeros((1, 3, 3), dtype=np.uint8)
    bstruct4[0, 1, 0] = 1
    bstruct4[0, 0, 1] = 1
    bstruct4[0, 1, 2] = 1
    bstruct4[0, 2, 1] = 1
    bstruct4[0, 1, 1] = 1
    out_mask4 = np.zeros((1, 3, 3), dtype=np.uint8)
    floodfill.floodfill_threshold(image_3d, seed, t0, t1, 1, bstruct4, out_mask4)
    expected4 = np.array(
        [
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 0],
        ],
        dtype=np.uint8,
    )[np.newaxis, ...]
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
