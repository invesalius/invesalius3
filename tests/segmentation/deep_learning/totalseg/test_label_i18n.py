from invesalius.segmentation.deep_learning.totalseg import label_i18n


def test_display_from_key_title_cases_and_replaces_underscores():
    assert label_i18n._display_from_key("kidney_right") == "Kidney Right"
    assert label_i18n._display_from_key("vertebrae_L1") == "Vertebrae L1"
    assert label_i18n._display_from_key("lung_upper_lobe_left") == "Lung Upper Lobe Left"


def test_display_from_key_single_word():
    assert label_i18n._display_from_key("liver") == "Liver"


def test_translate_structure_returns_string_for_known_key():
    # Result depends on the current locale's .mo file; we only assert it stays
    # a non-empty string. gettext falls back to the msgid (the display name)
    # when no translation exists, so the result is always renderable.
    out = label_i18n.translate_structure("liver")
    assert isinstance(out, str)
    assert out.strip()


def test_translate_structure_unknown_key_falls_back_to_display():
    # Unknown key never appears in .po -> gettext returns the msgid, which is
    # the auto-formatted display name.
    assert label_i18n.translate_structure("invented_structure_xyz") == "Invented Structure Xyz"


def test_anatomical_string_list_covers_expected_entries():
    # Sanity check: pygettext needs literal _() calls to extract every
    # anatomical name. If someone removes the extraction tuple, this fails.
    assert len(label_i18n._ANATOMICAL_STRINGS) >= 100
