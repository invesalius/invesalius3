import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from invesalius.utils import (
    Singleton,
    TwoWaysDictionary,
    VerifyInvalidPListCharacter,
    debug,
    decode,
    deep_merge_dict,
    encode,
    format_date,
    format_time,
    get_system_encoding,
    log_traceback,
    new_name_by_pattern,
    next_copy_name,
    timing,
    touch,
    vtkarray_to_numpy,
)


class TestSingleton(unittest.TestCase):
    def test_singleton_pattern(self):
        class SingletonTest(metaclass=Singleton):
            pass

        instance1 = SingletonTest()
        instance2 = SingletonTest()
        self.assertIs(instance1, instance2)

    def test_singleton_with_args(self):
        class SingletonWithArgs(metaclass=Singleton):
            def __init__(self, value=None):
                self.value = value

        instance1 = SingletonWithArgs("test")
        instance2 = SingletonWithArgs("different")
        self.assertIs(instance1, instance2)
        self.assertEqual(instance1.value, "test")
        self.assertEqual(instance2.value, "test")


class TestTwoWaysDictionary(unittest.TestCase):
    def setUp(self):
        self.twd = TwoWaysDictionary([("key1", "value1"), ("key2", "value2"), ("key3", "value1")])

    def test_get_key(self):
        self.assertEqual(self.twd.get_key("value1"), "key1")
        self.assertEqual(self.twd.get_key("value2"), "key2")
        self.assertIsNone(self.twd.get_key("no exist"))

    def test_get_keys(self):
        self.assertEqual(self.twd.get_keys("value1"), ["key1", "key3"])
        self.assertEqual(self.twd.get_keys("value2"), ["key2"])
        self.assertEqual(self.twd.get_keys("no exist"), [])

    def test_get_value(self):
        self.assertEqual(self.twd.get_value("key1"), "value1")
        self.assertEqual(self.twd.get_value("key2"), "value2")
        self.assertIsNone(self.twd.get_value("no exist"))

    def test_remove(self):
        self.twd.remove("key1")
        self.assertIsNone(self.twd.get_value("key1"))
        self.assertEqual(self.twd.get_key("value1"), "key3")
        self.twd.remove("no exist")


class TestTimeFormatting(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(format_time("11.29.56"), "11:29:56")
        self.assertEqual(format_time("11:29:56"), "11:29:56")
        self.assertEqual(format_time("112956"), "11:29:56")
        self.assertEqual(format_time("11.29"), time.strftime("%H:%M:%S", time.gmtime(11.29)))


class TestStringFormatting(unittest.TestCase):
    def test_format_date(self):
        self.assertEqual(format_date("21.04.2025"), "21/04/2025")
        self.assertEqual(format_date("2025.04.21"), "21/04/2025")
        self.assertEqual(format_date("21/04/2025"), "")
        self.assertEqual(format_date("21//04//2025"), "")
        self.assertEqual(format_date("20250421"), "21/04/2025")
        self.assertEqual(format_date("invalid"), "")


class TestNamingUtilities(unittest.TestCase):
    def test_next_copy_name(self):
        names_list = ["original", "original copy", "original copy#1", "another"]
        self.assertEqual(next_copy_name("original", names_list), "original copy#2")
        self.assertEqual(next_copy_name("original copy", names_list), "original copy#2")
        self.assertEqual(next_copy_name("another", names_list), "another copy")
        self.assertEqual(next_copy_name("new", names_list), "new copy")

    @patch("invesalius.project.Project")
    def test_new_name_by_pattern(self, mock_project):
        class MockMask:
            def __init__(self, name):
                self.name = name

        mock_project_instance = mock_project.return_value
        mock_project_instance.mask_dict = {1: MockMask("mask_1"), 2: MockMask("mask_2")}

        self.assertEqual(new_name_by_pattern("mask"), "mask_3")

        mock_project_instance.mask_dict = {
            1: MockMask("surface_1"),
            2: MockMask("surface_2"),
            3: MockMask("surface_3"),
        }
        self.assertEqual(new_name_by_pattern("surface"), "surface_4")

        mock_project_instance.mask_dict = {
            1: MockMask("other_1"),
        }
        self.assertEqual(new_name_by_pattern("new"), "new_1")


class TestValidationUtils(unittest.TestCase):
    def test_verify_invalid_plist_character(self):
        self.assertTrue(VerifyInvalidPListCharacter("bad\x0bchar"))
        self.assertFalse(VerifyInvalidPListCharacter("good string"))


class TestFileAndSystemUtilities(unittest.TestCase):
    def test_touch(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp_path = temp.name
            os.unlink(temp_path)
            touch(temp_path)
            self.assertTrue(os.path.exists(temp_path))
            os.unlink(temp_path)

    def test_get_system_encoding(self):
        encoding = get_system_encoding()
        if sys.platform == "win32":
            self.assertIsNotNone(encoding)
        else:
            self.assertEqual(encoding, "utf-8")


class TestEncodingFunctions(unittest.TestCase):
    def test_decode(self):
        self.assertEqual(decode(b"test", "utf-8"), "test")
        self.assertEqual(decode("test", "utf-8"), "test")

    def test_encode(self):
        self.assertEqual(encode("test", "utf-8"), b"test")
        self.assertEqual(encode(b"test", "utf-8"), b"test")


class TestDictionaryOperations(unittest.TestCase):
    def test_deep_merge_dict(self):
        d1 = {"a": 1, "b": {"c": 2, "d": 3}}
        d2 = {"b": {"d": 4, "e": 5}, "f": 6}
        expected = {"a": 1, "b": {"c": 2, "d": 4, "e": 5}, "f": 6}
        self.assertEqual(deep_merge_dict(d1, d2), expected)
