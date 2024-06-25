# -*- coding: utf-8 -*-

import math
from typing import List, Tuple

import numpy as np


def calculate_distance(p1, p2):
    """
    Calculates the euclidian distance between p1 and p2 points.

    >>> calculate_distance((0, 0), (1, 0))
    1.0

    >>> calculate_distance((0, 0), (0, 1))
    1.0
    """
    return math.sqrt(sum([(j - i) ** 2 for i, j in zip(p1, p2)]))


def calculate_angle(v1, v2):
    """
    Calculates the angle formed between vector v1 and v2.

    >>> calculate_angle((0, 1), (1, 0))
    90.0

    >>> calculate_angle((1, 0), (0, 1))
    90.0
    """
    cos_ = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    angle = math.degrees(math.acos(cos_))
    return angle


def calc_ellipse_area(a, b):
    """
    Calculates the area of the ellipse with the given a and b radius.

    >>> area = calc_ellipse_area(3, 5)
    >>> np.allclose(area, 47.1238)
    True

    >>> area = calc_polygon_area(10, 10)
    >>> np.allclose(area, 314.1592)
    True
    """
    return np.pi * a * b


def calc_ellipse_circumference(a: float, b: float) -> float:
    """
    Calculates the area of the ellipse circumference with the given a and b radius using Ramanujan formula
    """
    semi_axis_a = a / 2
    semi_axis_b = b / 2
    circumference = np.pi * (
        3.0 * (semi_axis_a + semi_axis_b)
        - np.sqrt((3.0 * semi_axis_a + semi_axis_b) * (semi_axis_a + 3.0 * semi_axis_b))
    )
    return circumference


def calc_polygon_area(points):
    """
    Calculates the area from the polygon formed by given the points.

    >>> # Square
    >>> calc_polygon_area([(0,0), (0,2), (2, 2), (2, 0)])
    4.0

    >>> # Triangle
    >>> calc_polygon_area([(0, 0), (0, 9), (6, 0)])
    27.0

    >>> points = [(1.2*np.cos(i), 1.2*np.sin(i)) for i in np.linspace(0, 2.0*np.pi, 9)]
    >>> area = calc_polygon_area(points)
    >>> np.allclose(area, 4.0729)
    True

    >>> points = [(108.73990145506055, 117.34406876547659), (71.04545419038097, 109.14962370793754), (71.04545419038097, 68.17739842024233), (83.33712177668953, 43.5940632476252), (139.05934816795505, 38.67739621310179), (152.9899047657714, 50.969063799410335), (143.9760152024784, 62.441286879965), (117.75379101835351, 62.441286879965), (127.58712508740032, 89.48295556984385), (154.62879377727918, 98.49684513313679)]
    >>> area = calc_polygon_area(points)
    >>> np.allclose(area, 4477.4906)
    True
    """
    area = 0.0
    j = len(points) - 1
    for i in range(len(points)):
        area += (points[j][0] + points[i][0]) * (points[j][1] - points[i][1])
        j = i
    area = abs(area / 2.0)
    return area


def calc_polygon_perimeter(points: List[Tuple[float, float]]) -> float:
    """
    Calculates the perimeter from the polygon formed by given the points.
    """
    perimeter = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        perimeter += np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    return perimeter


def inner1d(v0: np.ndarray, v1: np.ndarray) -> np.ndarray:
    """
    inner on the last dimension and broadcast on the rest

    imports from numpy.core.umath_tests is being deprecated

    This implementation is based on
    https://github.com/numpy/numpy/issues/10815#issuecomment-376847774

    >>> a = np.array((1, 2, 3))
    >>> b = np.array((4, 5, 6))
    >>> inner1d(a, b)
    32

    >>> a = np.arange(9).reshape(3,3)
    >>> b = np.arange(9).reshape(3,3)
    >>> inner1d(a, b)
    array([  5,  50, 149])
    """
    return (v0 * v1).sum(axis=-1)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
