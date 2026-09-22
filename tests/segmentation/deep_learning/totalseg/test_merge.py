import numpy as np
import pytest

from invesalius.segmentation.deep_learning.totalseg import merge

FAKE_TARGET_LABELS = {0: "background", 1: "liver", 2: "spleen", 3: "kidney_left"}
FAKE_PART_A_LABELS = {0: "background", 1: "liver", 2: "spleen"}
FAKE_PART_B_LABELS = {0: "background", 1: "kidney_left"}


@pytest.fixture(autouse=True)
def _fake_multipart(monkeypatch):
    monkeypatch.setitem(
        merge.MULTIPART_TASKS,
        "fake_composite",
        {"parts": ["part_a", "part_b"], "target": "fake_target"},
    )

    def fake_get_labels(task, cache_only=False):
        return {
            "fake_target": FAKE_TARGET_LABELS,
            "part_a": FAKE_PART_A_LABELS,
            "part_b": FAKE_PART_B_LABELS,
        }[task]

    monkeypatch.setattr(merge._labels, "get_labels", fake_get_labels)
    merge._build_remaps.cache_clear()
    merge.get_unified_labels.cache_clear()
    yield
    merge._build_remaps.cache_clear()
    merge.get_unified_labels.cache_clear()


def test_is_multipart():
    assert merge.is_multipart("fake_composite") is True
    assert merge.is_multipart("ct_organs") is False
    assert merge.is_multipart("does_not_exist") is False


def test_parts_for_selection_none_returns_all_parts():
    assert merge.parts_for_selection("fake_composite", None) == ["part_a", "part_b"]
    assert merge.parts_for_selection("fake_composite", set()) == ["part_a", "part_b"]


def test_parts_for_selection_filters_by_selected_ids():
    # liver + spleen are only in part_a; kidney_left is only in part_b.
    assert merge.parts_for_selection("fake_composite", {1, 2}) == ["part_a"]
    assert merge.parts_for_selection("fake_composite", {3}) == ["part_b"]
    assert merge.parts_for_selection("fake_composite", {1, 3}) == ["part_a", "part_b"]


def test_parts_for_selection_unknown_selection_returns_all():
    assert merge.parts_for_selection("fake_composite", {999}) == ["part_a", "part_b"]


def test_parts_for_selection_unknown_task():
    with pytest.raises(ValueError):
        merge.parts_for_selection("not_a_task", None)


def test_get_unified_labels_from_target():
    unified = merge.get_unified_labels("fake_composite")
    assert unified == FAKE_TARGET_LABELS


def test_merge_label_maps_full_dict():
    shape = (4, 4, 4)
    part_a = np.zeros(shape, dtype=np.uint8)
    part_a[0, 0, 0] = 1  # liver (local 1 → unified 1)
    part_a[1, 0, 0] = 2  # spleen (local 2 → unified 2)
    part_b = np.zeros(shape, dtype=np.uint8)
    part_b[2, 0, 0] = 1  # kidney_left (local 1 → unified 3)

    unified = merge.merge_label_maps({"part_a": part_a, "part_b": part_b}, "fake_composite")

    assert unified.shape == shape
    assert unified[0, 0, 0] == 1
    assert unified[1, 0, 0] == 2
    assert unified[2, 0, 0] == 3
    assert unified[3, 3, 3] == 0


def test_merge_label_maps_partial_dict_still_works():
    shape = (3, 3, 3)
    part_a = np.zeros(shape, dtype=np.uint8)
    part_a[0, 0, 0] = 1
    unified = merge.merge_label_maps({"part_a": part_a}, "fake_composite")
    assert unified[0, 0, 0] == 1
    assert unified.sum() == 1


def test_merge_label_maps_later_part_overwrites_earlier():
    shape = (2, 2, 2)
    part_a = np.zeros(shape, dtype=np.uint8)
    part_a[0, 0, 0] = 1  # liver (unified 1)
    part_b = np.zeros(shape, dtype=np.uint8)
    part_b[0, 0, 0] = 1  # kidney_left (unified 3), same voxel as part_a's liver

    unified = merge.merge_label_maps({"part_a": part_a, "part_b": part_b}, "fake_composite")
    assert unified[0, 0, 0] == 3


def test_merge_label_maps_rejects_unknown_part():
    shape = (2, 2, 2)
    with pytest.raises(ValueError):
        merge.merge_label_maps(
            {"part_a": np.zeros(shape, dtype=np.uint8), "junk": np.zeros(shape, dtype=np.uint8)},
            "fake_composite",
        )


def test_merge_label_maps_rejects_empty_dict():
    with pytest.raises(ValueError):
        merge.merge_label_maps({}, "fake_composite")


def test_merge_label_maps_rejects_shape_mismatch():
    part_a = np.zeros((3, 3, 3), dtype=np.uint8)
    part_b = np.zeros((4, 4, 4), dtype=np.uint8)
    with pytest.raises(ValueError):
        merge.merge_label_maps({"part_a": part_a, "part_b": part_b}, "fake_composite")
