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
