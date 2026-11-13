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


def test_serialize_to_disk_is_reentrant_after_reload():
    # Regression test for the bug where serialize_to_disk() silently did
    # nothing on a node that had already been spilled once and then brought
    # back into memory by _ensure_in_memory(), because its guard required
    # self.filename to still be None. That left the reloaded arrays
    # permanently resident instead of being spillable again.
    p_matrix = np.zeros((30, 30, 30), dtype=np.uint8)
    new_matrix = p_matrix.copy()
    new_matrix[5:10, 5:10, 5:10] = 255

    node = DeltaHistoryNode(0, "VOLUME", p_matrix, new_matrix)
    node.serialize_to_disk()
    first_filename = node.filename
    assert first_filename is not None
    assert node.indices is None

    # Bring it back into memory, as undo()/redo() do via _ensure_in_memory().
    test_matrix = p_matrix.copy()
    node.apply_redo(test_matrix)
    assert np.array_equal(test_matrix, new_matrix)
    assert node.indices is not None

    # Spilling it again must actually clear the in-memory arrays a second
    # time, reusing the existing temp file rather than being skipped.
    node.serialize_to_disk()
    assert node.indices is None
    assert node.filename == first_filename
    assert os.path.exists(node.filename)

    # Data must still round-trip correctly after the second spill/reload.
    test_matrix = new_matrix.copy()
    node.apply_undo(test_matrix)
    assert np.array_equal(test_matrix, p_matrix)


def test_volume_delta_nodes_spill_to_disk_when_inactive():
    # Regression test for #1470: serialize_to_disk() was never invoked from
    # the real EditionHistory flow, so every DeltaHistoryNode stayed fully
    # resident in memory for as long as it lived in the undo stack.
    history = EditionHistory(size=10)
    matrix = np.zeros((40, 40, 40), dtype=np.uint8)

    orig_1 = matrix.copy()
    matrix[10:15, 10:15, 10:15] = 255
    history.new_node(0, "VOLUME", matrix.copy(), orig_1, clean=False)
    first_node = history.history[0]
    assert first_node.indices is not None

    orig_2 = matrix.copy()
    matrix[12:18, 12:18, 12:18] = 0
    history.new_node(0, "VOLUME", matrix.copy(), orig_2, clean=False)
    second_node = history.history[1]
    state_after_stroke_2 = matrix.copy()

    # Only the node matching the current index may still be fully in RAM;
    # every other delta node must have been spilled to disk automatically.
    assert history.index == 1
    assert first_node.indices is None
    assert first_node.filename is not None
    assert os.path.exists(first_node.filename)
    assert second_node.indices is not None

    # Undo applies second_node (still in RAM, being the active node) and
    # then spills it, since it is no longer the active state; first_node
    # is untouched and stays spilled.
    history.undo(matrix)
    assert np.array_equal(matrix, orig_2)
    assert history.index == 0
    assert second_node.indices is None
    assert first_node.indices is None

    # Redo reloads second_node from disk to reapply it, and it becomes the
    # active node again, so it is not immediately re-spilled.
    history.redo(matrix)
    assert np.array_equal(matrix, state_after_stroke_2)
    assert history.index == 1
    assert second_node.indices is not None
    assert first_node.indices is None


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
