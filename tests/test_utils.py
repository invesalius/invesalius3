from invesalius.utils import next_copy_name


def test_next_copy_name_basic():
    result = next_copy_name("Mask", ["Mask"])
    assert result == "Mask copy"


def test_next_copy_name_already_has_copy():
    result = next_copy_name("Mask copy", ["Mask copy"])
    assert result == "Mask copy#1"


def test_next_copy_name_numbered():
    result = next_copy_name("Mask copy#3", ["Mask copy#3", "Mask copy#1", "Mask copy#2"])
    assert result == "Mask copy#4"


def test_next_copy_name_skip_existing():
    result = next_copy_name("Mask copy#1", ["Mask copy#1", "Mask copy#2"])
    assert result == "Mask copy#3"


def test_next_copy_name_non_numeric_suffix():
    result = next_copy_name("Mask copy#abc", ["Mask copy#abc"])
    assert result == "Mask copy#abc copy"


def test_next_copy_name_non_numeric_suffix_existing():
    result = next_copy_name("Mask copy#abc", ["Mask copy#abc", "Mask copy#abc copy"])
    assert result == "Mask copy#abc copy#1"


def test_next_copy_name_float_suffix():
    result = next_copy_name("Mask copy#3.5", ["Mask copy#3.5"])
    assert result == "Mask copy#3.5 copy"
