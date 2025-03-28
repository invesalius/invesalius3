from math import isclose

import numpy as np
import pytest

from invesalius.math_utils import (
    calc_ellipse_area,
    calc_ellipse_circumference,
    calc_polygon_area,
    calc_polygon_perimeter,
    calculate_angle,
    calculate_distance,
    inner1d,
)


# Checking cache on a new PR again
def test_calculate_distance():
    assert calculate_distance((0, 0), (1, 0)) == pytest.approx(1.0)
    assert calculate_distance((0, 0), (0, 1)) == pytest.approx(1.0)
    assert calculate_distance((0, 0), (3, 4)) == pytest.approx(5.0)


def test_calculate_angle():
    assert calculate_angle((0, 1), (1, 0)) == pytest.approx(90.0)
    assert calculate_angle((1, 0), (0, 1)) == pytest.approx(90.0)
    assert calculate_angle((1, 0), (1, 1)) == pytest.approx(45.0)


def test_calc_ellipse_area():
    assert isclose(calc_ellipse_area(3, 5), 47.1238, rel_tol=1e-4)
    assert isclose(calc_ellipse_area(10, 10), 314.1592, rel_tol=1e-4)


def test_calc_ellipse_circumference():
    assert isclose(calc_ellipse_circumference(4, 4), 12.5664, rel_tol=1e-4)
    assert isclose(calc_ellipse_circumference(10, 5), 24.221, rel_tol=1e-4)


def test_calc_polygon_area():
    assert calc_polygon_area([(0, 0), (0, 2), (2, 2), (2, 0)]) == pytest.approx(4.0)
    assert calc_polygon_area([(0, 0), (0, 9), (6, 0)]) == pytest.approx(27.0)


def test_calc_polygon_perimeter():
    assert calc_polygon_perimeter([(0, 0), (0, 2), (2, 2), (2, 0)]) == pytest.approx(8.0)
    assert calc_polygon_perimeter([(0, 0), (0, 4), (3, 0)]) == pytest.approx(12.0)


def test_inner1d():
    a = np.array((1, 2, 3))
    b = np.array((4, 5, 6))
    assert inner1d(a, b) == 32

    a = np.arange(9).reshape(3, 3)
    b = np.arange(9).reshape(3, 3)
    np.testing.assert_array_equal(inner1d(a, b), np.array([5, 50, 149]))
