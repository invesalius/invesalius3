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
