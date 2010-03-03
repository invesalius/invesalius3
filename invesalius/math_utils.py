#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import numpy

def calculate_distance(p1, p2):
    """
    Calculates the euclidian distance between p1 and p2 points.

    >>> calculate_distance((0, 0), (1, 0))
    1.0

    >>> calculate_distance((0, 0), (0, 1))
    1.0
    """
    return math.sqrt(sum([(j-i)**2 for i,j in zip(p1, p2)]))

def calculate_angle(v1, v2):
    """
    Calculates the angle formed between vector v1 and v2.

    >>> calculate_angle((0, 1), (1, 0))
    90.0
    
    >>> calculate_angle((1, 0), (0, 1))
    90.0
    """
    cos_ = numpy.dot(v1, v2)/(numpy.linalg.norm(v1)*numpy.linalg.norm(v2))
    angle = math.degrees(math.acos(cos_))
    return angle

if __name__ == '__main__':
    import doctest
    doctest.testmod()
