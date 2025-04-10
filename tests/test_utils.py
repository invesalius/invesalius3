from invesalius.utils import *
import pytest
import time
import sys
import platform
import psutil
from unittest.mock import patch


@pytest.mark.parametrize("input_time,expected", [
    ("12:30:45", "12:30:45"),                  
    ("12.30.45", "12:30:45"),                  
    ("12:30:45.123", "12:30:45"),              
    ("123045", "12:30:45"),                    
    ("3600.0", time.strftime("%H:%M:%S", time.gmtime(3600.0))),   
    ("bad_time", "bad_time"),                  
])
def test_format_time(input_time, expected):
    assert format_time(input_time) == expected


@pytest.mark.parametrize("input_date,expected", [
    ("20230409", "09/04/2023"),
    ("09.04.2023", "09/04/2023"),
    ("2023.04.09", "09/04/2023"),
    ("09/04/2023", "09/04/2023"),
    ("invalid", ""),
])
def test_format_date(input_date, expected):
    assert format_date(input_date) == expected


def test_next_copy_name():
    assert next_copy_name("Test", ["Test", "Test copy", "Test copy#1", "Test copy#2"]) == "Test copy#3"
    assert next_copy_name("Another", ["Another"]) == "Another copy"
    assert next_copy_name("Thing copy", ["Thing copy"]) == "Thing copy#1"
    assert next_copy_name("Something copy#notanumber", []) == "Something copy"
    assert next_copy_name("Fresh", []) == "Fresh copy"
    assert next_copy_name("Z", ["Z", "Z copy#1"]) == "Z copy"
    assert next_copy_name("Alpha copy#99", ["Alpha copy", "Alpha copy#99"]) == "Alpha copy#100"



def test_verify_invalid_plist_character():
    assert VerifyInvalidPListCharacter("valid_string") is False
    assert VerifyInvalidPListCharacter("invalid\x0cstring") is True


@patch("invesalius.session.Session")
def test_two_ways_dictionary(mock_session, capsys):
    mock_session.return_value.GetConfig.return_value = True

    d = TwoWaysDictionary([("a", 1), ("b", 2)])
    assert d.get_value("a") == 1
    assert d.get_key(1) == "a"
    assert sorted(d.get_keys(2)) == ["b"]

    d.remove("b")
    assert d.get("b") is None

    d.remove("non_existent_key")  
    captured = capsys.readouterr()

    assert "TwoWaysDictionary: key not found" in captured.out


@pytest.mark.parametrize("args, expected", [
    ((0.5, 2.0, 0.5), [0.5, 1.0, 1.5]),      
    ((2.0, 0.5, -0.5), [2.0, 1.5, 1.0]),     
    ((3,), [0.0, 1.0, 2.0]),                
    ((0, 2, 0), [0.0, 1.0]),                
])
def test_frange_various_cases(args, expected):
    assert frange(*args) == expected


def test_touch(tmp_path):
    file_path = tmp_path / "testfile.txt"
    touch(str(file_path))
    
    assert file_path.exists()


def test_encode_decode_utf8():
    original = "hello"
    encoded = encode(original, "utf-8")
    decoded = decode(encoded, "utf-8")
    
    assert decoded == original

    
def test_decode_attribute_error():
    input_val = "hello"  
    result = decode(input_val, "utf-8")
    
    assert result == input_val


def test_encode_attribute_error():
    input_val = 123  
    result = encode(input_val, "utf-8")
    
    assert result == input_val


def test_deep_merge_dict():
    d1 = {"a": {"b": 1}, "c": 3}
    d2 = {"a": {"d": 2}, "e": 5}
    result = deep_merge_dict(d1, d2)
    
    assert result == {"a": {"b": 1, "d": 2}, "c": 3, "e": 5}


def test_timing_decorator(capsys):
    @timing
    def slow_add(a, b):
        time.sleep(0.1)
        return a + b

    result = slow_add(2, 3)
    
    assert result == 5

    captured = capsys.readouterr()
    
    assert "slow_add elapsed time:" in captured.out
    

def test_log_traceback_with_traceback():
    try:
        1 / 0  
    except ZeroDivisionError as ex:
        tb = log_traceback(ex)
        
        assert "ZeroDivisionError" in tb
        assert "1 / 0" in tb


def test_log_traceback_without_traceback():
    class FakeException(Exception):
        __traceback__ = None

    ex = FakeException("simulated")
    tb = log_traceback(ex)
    
    assert "FakeException" in tb
    assert "simulated" in tb
    

