import os

import numpy as np

from invesalius.data.mask import DeltaHistoryNode, EditionHistory


def test_delta_history_node_sparse():
    # Create mock 3D matrix (e.g. 50x50x50)
    p_matrix = np.zeros((50, 50, 50), dtype=np.uint8)
    p_matrix[10:20, 10:20, 10:20] = 255

    # New matrix with a stroke applied (modifying 5x5x5 voxels)
    new_matrix = p_matrix.copy()
    new_matrix[12:17, 12:17, 12:17] = 0

    # Instantiate DeltaHistoryNode
    node = DeltaHistoryNode(0, "VOLUME", p_matrix, new_matrix)

    # Verify only modified voxels are stored
    num_changed = 5 * 5 * 5
    assert len(node.indices[0]) == num_changed
    assert len(node.old_values) == num_changed
    assert len(node.new_values) == num_changed

    # Test undo application on new_matrix
    test_matrix = new_matrix.copy()
    node.apply_undo(test_matrix)
    assert np.array_equal(test_matrix, p_matrix)

    # Test redo application on p_matrix
    node.apply_redo(test_matrix)
    assert np.array_equal(test_matrix, new_matrix)


def test_delta_history_node_serialization():
    p_matrix = np.zeros((30, 30, 30), dtype=np.uint8)
    new_matrix = p_matrix.copy()
    new_matrix[5:10, 5:10, 5:10] = 255

    node = DeltaHistoryNode(0, "VOLUME", p_matrix, new_matrix)

    # Serialize to disk
    node.serialize_to_disk()
    assert node.filename is not None
    assert os.path.exists(node.filename)
    assert node.indices is None  # Arrays cleared from RAM

    # Test in-memory restoration and undo/redo
    test_matrix = p_matrix.copy()
    node.apply_redo(test_matrix)
    assert np.array_equal(test_matrix, new_matrix)


def test_edition_history_volume_deltas():
    history = EditionHistory(size=10)
    matrix = np.zeros((40, 40, 40), dtype=np.uint8)

    # State 0 -> State 1
    orig_1 = matrix.copy()
    matrix[10:15, 10:15, 10:15] = 255
    history.new_node(0, "VOLUME", matrix.copy(), orig_1, clean=False)

    # State 1 -> State 2
    orig_2 = matrix.copy()
    matrix[12:18, 12:18, 12:18] = 0
    history.new_node(0, "VOLUME", matrix.copy(), orig_2, clean=False)

    assert len(history.history) == 2
    assert history.index == 1

    # Undo Stroke 2 -> should return to State 1
    history.undo(matrix)
    assert np.array_equal(matrix, orig_2)
    assert history.index == 0

    # Undo Stroke 1 -> should return to State 0
    history.undo(matrix)
    assert np.array_equal(matrix, orig_1)
    assert history.index == -1

    # Redo Stroke 1 -> should return to State 1
    history.redo(matrix)
    assert np.array_equal(matrix, orig_2)
    assert history.index == 0


def test_edition_history_jump_to():
    history = EditionHistory(size=10)
    matrix = np.zeros((30, 30, 30), dtype=np.uint8)

    # Initial state (State -1)
    state_init = matrix.copy()

    # Stroke 1: State -1 -> State 0
    matrix[5:10, 5:10, 5:10] = 255
    state_0 = matrix.copy()
    history.new_node(0, "VOLUME", state_0, state_init, clean=False, tool_id="BRUSH")

    # Stroke 2: State 0 -> State 1
    matrix[15:20, 15:20, 15:20] = 255
    state_1 = matrix.copy()
    history.new_node(0, "VOLUME", state_1, state_0, clean=False, tool_id="POLYGON")

    assert history.index == 1

    # Jump directly back to Initial State (index -1)
    history.jump_to(-1, matrix)
    assert history.index == -1
    assert np.array_equal(matrix, state_init)

    # Jump forward directly to State 1 (index 1)
    history.jump_to(1, matrix)
    assert history.index == 1
    assert np.array_equal(matrix, state_1)


def test_edition_history_2d_undo_reaches_initial_state():
    # Regression test: a single 2D slice edit (AXIAL/CORONAL/SAGITAL, as
    # opposed to a VOLUME/DeltaHistoryNode edit) used to leave undo()
    # permanently stuck at index 0 -- every branch that decremented
    # self.index required self.index > 0, so -1 (the "no edits" sentinel)
    # was unreachable.
    matrix = np.zeros((10, 10, 10), dtype=np.uint8)
    history = EditionHistory(size=10)

    p_array = matrix[1, 1:, 1:].copy()
    array = p_array.copy()
    array[0, 0] = 255
    history.new_node(0, "AXIAL", array, p_array, clean=False)
    matrix[1, 1:, 1:] = array
    assert history.index == 1

    actual_slices = {"AXIAL": 0, "CORONAL": 0, "SAGITAL": 0, "VOLUME": 0}

    # First undo: back to the pre-edit snapshot.
    history.undo(matrix, actual_slices)
    assert history.index == 0
    assert np.array_equal(matrix[1, 1:, 1:], p_array)

    # Second undo: must reach the "no edits" sentinel, not stay stuck at 0.
    history.undo(matrix, actual_slices)
    assert history.index == -1

    # A further undo() call should be a safe no-op.
    history.undo(matrix, actual_slices)
    assert history.index == -1


def test_edition_history_jump_to_2d_initial_state_terminates():
    # Regression test: EditionHistory.jump_to() drives undo()/redo() in an
    # unbounded loop and used to spin forever once undo() got stuck (see
    # test_edition_history_2d_undo_reaches_initial_state). Jumping to
    # "Initial State" (-1) after a single 2D edit reproduced this directly.
    matrix = np.zeros((10, 10, 10), dtype=np.uint8)
    history = EditionHistory(size=10)

    p_array = matrix[1, 1:, 1:].copy()
    array = p_array.copy()
    array[0, 0] = 255
    history.new_node(0, "AXIAL", array, p_array, clean=False)
    matrix[1, 1:, 1:] = array

    actual_slices = {"AXIAL": 0, "CORONAL": 0, "SAGITAL": 0, "VOLUME": 0}
    history.jump_to(-1, matrix, actual_slices)

    assert history.index == -1
    assert np.array_equal(matrix[1, 1:, 1:], p_array)


def test_edition_history_jump_to_2d_mismatched_viewer_slice_terminates():
    # Regression test: undo()/redo() also make no progress when the slice
    # currently shown in the 2D viewer doesn't match the history entry
    # being crossed (they only reposition the viewer, by design, so a
    # single manual click can apply the edit on the next press). jump_to()
    # walks several steps in one call and used to spin forever if this
    # branch was hit anywhere along the way, regardless of index 0.
    matrix = np.zeros((10, 10, 10), dtype=np.uint8)
    history = EditionHistory(size=10)

    p1 = matrix[1, 1:, 1:].copy()
    a1 = p1.copy()
    a1[0, 0] = 255
    history.new_node(0, "AXIAL", a1, p1, clean=False)  # slice 0
    matrix[1, 1:, 1:] = a1

    p2 = matrix[3, 1:, 1:].copy()
    a2 = p2.copy()
    a2[0, 0] = 255
    history.new_node(2, "AXIAL", a2, p2, clean=False)  # slice 2
    matrix[3, 1:, 1:] = a2

    assert history.index == 3

    # Viewer is on a slice that matches neither recorded edit.
    actual_slices = {"AXIAL": 7, "CORONAL": 0, "SAGITAL": 0, "VOLUME": 0}
    history.jump_to(-1, matrix, actual_slices)

    assert history.index == -1
    assert np.array_equal(matrix[1, 1:, 1:], p1)
    assert np.array_equal(matrix[3, 1:, 1:], p2)


def test_edition_history_jump_to_mixed_2d_and_volume():
    # A history mixing 2D slice edits and VOLUME/delta edits should still
    # jump to -1 and back without getting stuck partway through.
    matrix = np.zeros((10, 10, 10), dtype=np.uint8)
    history = EditionHistory(size=10)

    p1 = matrix[1, 1:, 1:].copy()
    a1 = p1.copy()
    a1[0, 0] = 255
    history.new_node(0, "AXIAL", a1, p1, clean=False)
    matrix[1, 1:, 1:] = a1

    p_vol = matrix.copy()
    matrix[5, 5, 5] = 255
    history.new_node(0, "VOLUME", matrix.copy(), p_vol, clean=False)

    actual_slices = {"AXIAL": 0, "CORONAL": 0, "SAGITAL": 0, "VOLUME": 0}

    history.jump_to(-1, matrix, actual_slices)
    assert history.index == -1
    assert np.array_equal(matrix, np.zeros((10, 10, 10), dtype=np.uint8))

    # index 0 = pre-edit snapshot, index 1 = post-edit snapshot (2D edits
    # always add both), index 2 = the VOLUME/delta edit.
    assert history.index == -1
    history.jump_to(2, matrix, actual_slices)
    assert history.index == 2
    assert matrix[5, 5, 5] == 255
