import time

import pytest

from invesalius.utils import (
    TwoWaysDictionary,
    VerifyInvalidPListCharacter,
    debug,
    decode,
    deep_merge_dict,
    encode,
    format_date,
    format_time,
    frange,
    next_copy_name,
    timing,
)


def test_format_time():
    assert format_time("12:34:56.789") == "12:34:56"
    assert format_time("12:34:56") == "12:34:56"
    assert format_time("123456") == "12:34:56"
    assert format_time("12.34.56") == "12:34:56"
    assert format_time("invalid") == "invalid"


def test_format_date():
    assert format_date("2025.12.31") == "31/12/2025"
    assert format_date("31.12.2025") == "31/12/2025"
    assert format_date("20251231") == "31/12/2025"

    assert format_date("2025/12/31") == ""
    assert format_date("12.31.2025") == ""
    assert format_date("2025.31.12") == ""
    assert format_date("31-12-2025") == ""
    assert format_date("31//12//2025") == ""
    assert format_date("invalid") == ""


def test_next_copy_name():
    names_list = ["file", "file copy", "file copy#1"]
    assert next_copy_name("file", names_list) == "file copy#2"
    assert next_copy_name("file copy", names_list) == "file copy#2"
    assert next_copy_name("file copy#1", names_list) == "file copy#2"
    names_list2 = ["image", "image copy", "image copy#1", "image copy#2"]
    assert next_copy_name("image", names_list2) == "image copy#3"
    names_list4 = []
    assert next_copy_name("newfile", names_list4) == "newfile copy"


def test_VerifyInvalidPListCharacter():
    assert VerifyInvalidPListCharacter("valid") == False
    assert VerifyInvalidPListCharacter("\x00invalid") == True
    assert VerifyInvalidPListCharacter("normal text") == False
    assert VerifyInvalidPListCharacter("test\x1ftest") == True
    assert VerifyInvalidPListCharacter(" ") == False


def test_TwoWaysDictionary():
    twd = TwoWaysDictionary({"a": 1, "b": 2})

    assert twd.get_key(1) == "a"
    assert twd.get_keys(2) == ["b"]

    assert twd.get_value("a") == 1
    assert twd.get_value("b") == 2

    twd.remove("a")
    assert "a" not in twd
    assert twd.get_keys(1) == []

    # Test removing a non-existing key (should not raise an error)
    twd.remove("x")

    # Test adding multiple keys with the same value
    twd["c"] = 2
    twd["d"] = 2
    assert set(twd.get_keys(2)) == {"b", "c", "d"}

    empty_twd = TwoWaysDictionary()
    assert empty_twd.get_keys(1) == []
    assert empty_twd.get_value("x") is None
    assert empty_twd.get_key(1) is None

    twd["e"] = 3
    assert twd.get_value("e") == 3
    assert twd.get_key(3) == "e"


def test_frange():
    # Standard increasing and decreasing range
    assert frange(1.0, 5.0, 1.0) == [1.0, 2.0, 3.0, 4.0]
    assert frange(5.0, 1.0, -1.0) == [5.0, 4.0, 3.0, 2.0]

    # Default increment (should behave like range with step=1)
    assert frange(3.0) == [0.0, 1.0, 2.0]

    # Edge case: start == end (should return an empty list)
    assert frange(2.0, 2.0, 0.5) == []

    # Edge case: increment of 0
    assert frange(1.0, 5.0, 0.0) == [1.0, 2.0, 3.0, 4.0]


def test_decode():
    assert decode(b"test", "utf-8") == "test"
    assert decode("test", "utf-8") == "test"


def test_encode():
    assert encode("test", "utf-8") == b"test"
    assert encode(b"test", "utf-8") == b"test"


def test_timing(capsys):
    @timing
    def test_func():
        time.sleep(1)

    assert test_func() is None

    captured = capsys.readouterr()
    assert "test_func elapsed time:" in captured.out


def test_debug(monkeypatch, capsys):
    class MockSession:
        def GetConfig(self, key):
            return True

    monkeypatch.setattr("invesalius.session.Session", MockSession)
    debug("Test debug message")
    captured = capsys.readouterr()
    assert "Test debug message" in captured.out


def test_deep_merge_dict():
    assert deep_merge_dict({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}  # Merging distinct keys
    assert deep_merge_dict({"a": {"x": 1}}, {"a": {"y": 2}}) == {
        "a": {"x": 1, "y": 2}
    }  # Merging nested dicts
    assert deep_merge_dict({"a": {"x": 1}}, {"a": 2}) == {"a": 2}  # Overwriting dict with value
    assert deep_merge_dict({}, {"a": 1}) == {"a": 1}  # Merging into empty dict
    assert deep_merge_dict({"a": 1}, {}) == {"a": 1}  # Merging empty dict
