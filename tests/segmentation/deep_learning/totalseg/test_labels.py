from invesalius.segmentation.deep_learning.totalseg import labels as lbl


def test_categorize_labels_groups_by_anatomy():
    grouped = lbl.categorize_labels(
        {
            1: "liver",
            2: "kidney_right",
            3: "vertebrae_L1",
            4: "rib_left_1",
            5: "heart",
            6: "aorta",
            7: "gluteus_maximus_left",
            8: "lung_upper_lobe_right",
        }
    )
    assert 1 in grouped["Organs"]
    assert 2 in grouped["Organs"]
    assert 8 in grouped["Organs"]
    assert 3 in grouped["Bones"]
    assert 4 in grouped["Bones"]
    assert 5 in grouped["Cardiac"]
    assert 6 in grouped["Vessels"]
    assert 7 in grouped["Muscles"]


def test_categorize_labels_empty_categories_are_dropped():
    grouped = lbl.categorize_labels({1: "liver"})
    assert "Organs" in grouped
    assert "Bones" not in grouped
    assert "Cardiac" not in grouped


def test_categorize_labels_unknown_goes_to_other():
    grouped = lbl.categorize_labels({1: "invented_structure_xyz"})
    assert grouped == {"Other": [1]}


def test_categorize_labels_sorts_ids_within_category():
    grouped = lbl.categorize_labels({5: "liver", 1: "spleen", 3: "kidney_left"})
    assert grouped["Organs"] == [1, 3, 5]


def test_categorize_labels_preserves_category_order():
    grouped = lbl.categorize_labels({1: "aorta", 2: "vertebrae_L1", 3: "liver"})
    # CATEGORY_ORDER dictates iteration order in the returned dict.
    assert list(grouped.keys()) == ["Organs", "Bones", "Vessels"]
