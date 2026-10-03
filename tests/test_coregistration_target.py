from types import SimpleNamespace

import numpy as np

from invesalius.data.coregistration import CoordinateCorregistrate


def make_thread(target):
    thread = object.__new__(CoordinateCorregistrate)
    thread.navigation = SimpleNamespace(target=target)
    return thread


def test_no_target_returns_none():
    assert make_thread(None)._get_current_target() is None


def test_target_has_y_flipped():
    thread = make_thread(np.array([10.0, 20.0, 30.0, 1.0, 2.0, 3.0]))
    np.testing.assert_array_equal(
        thread._get_current_target(), [10.0, -20.0, 30.0, 1.0, 2.0, 3.0]
    )


def test_navigation_target_is_not_modified():
    original = np.array([10.0, 20.0, 30.0, 1.0, 2.0, 3.0])
    thread = make_thread(original)
    thread._get_current_target()
    np.testing.assert_array_equal(original, [10.0, 20.0, 30.0, 1.0, 2.0, 3.0])


def test_new_target_is_picked_up_while_running():
    thread = make_thread(np.array([1.0, 2.0, 3.0, 0.0, 0.0, 0.0]))
    first = thread._get_current_target()

    thread.navigation.target = np.array([4.0, 5.0, 6.0, 0.0, 0.0, 0.0])
    second = thread._get_current_target()

    np.testing.assert_array_equal(first[:3], [1.0, -2.0, 3.0])
    np.testing.assert_array_equal(second[:3], [4.0, -5.0, 6.0])


def test_unset_target_returns_none():
    thread = make_thread(np.array([1.0, 2.0, 3.0, 0.0, 0.0, 0.0]))
    thread.navigation.target = None
    assert thread._get_current_target() is None
