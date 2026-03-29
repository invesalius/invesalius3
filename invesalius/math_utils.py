import math
from typing import Iterable, List, Sequence, Tuple

import numpy as np


def calculate_distance(p1: Iterable[float], p2: Iterable[float]) -> float:
    """
    Calculates the euclidian distance between p1 and p2 points.

    >>> calculate_distance((0, 0), (1, 0))
    1.0

    >>> calculate_distance((0, 0), (0, 1))
    1.0
    """
    return math.sqrt(sum([(j - i) ** 2 for i, j in zip(p1, p2)]))


def calculate_angle(v1: Tuple[float, ...], v2: Tuple[float, ...]) -> float:
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


def calc_ellipse_area(a: float, b: float) -> float:
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


def calc_polygon_area(points: Sequence[Tuple[float, float]]) -> float:
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


# ---------------------------------------------------------------------------
# OBB (Oriented Bounding Box) + GJK distance algorithm
# ---------------------------------------------------------------------------


def obb_vertices_from_center_axes(center, axes):
    """Build the 8 vertices of an OBB from its center and 3 half-axis vectors.

    Args:
        center: (3,) array — centre of the box.
        axes:   (3, 3) array — rows are half_u, half_v, half_n.

    Returns:
        (8, 3) ndarray of vertices.
    """
    verts = np.empty((8, 3))
    idx = 0
    for s0 in (-1.0, 1.0):
        for s1 in (-1.0, 1.0):
            for s2 in (-1.0, 1.0):
                verts[idx] = center + s0 * axes[0] + s1 * axes[1] + s2 * axes[2]
                idx += 1
    return verts


def _gjk_support(vertices, direction):
    """Return the vertex of *vertices* farthest along *direction*."""
    dots = vertices @ direction
    return vertices[np.argmax(dots)].copy()


def _closest_point_on_segment(a, b):
    """Closest point to the origin on segment AB. Returns (point, barycentric t)."""
    ab = b - a
    t = -a.dot(ab) / (ab.dot(ab) + 1e-30)
    t = max(0.0, min(1.0, t))
    return a + t * ab, t


def _closest_point_on_triangle(a, b, c):
    """Closest point to the origin on triangle ABC using Voronoi-region tests."""
    ab = b - a
    ac = c - a
    ao = -a

    d1 = ab.dot(ao)
    d2 = ac.dot(ao)
    if d1 <= 0.0 and d2 <= 0.0:
        return a.copy()

    bo = -b
    d3 = ab.dot(bo)
    d4 = ac.dot(bo)
    if d3 >= 0.0 and d4 <= d3:
        return b.copy()

    co = -c
    d5 = ab.dot(co)
    d6 = ac.dot(co)
    if d6 >= 0.0 and d5 <= d6:
        return c.copy()

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3 + 1e-30)
        return a + v * ab

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6 + 1e-30)
        return a + w * ac

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6) + 1e-30)
        return b + w * (c - b)

    denom = 1.0 / (va + vb + vc + 1e-30)
    v = vb * denom
    w = vc * denom
    return a + v * ab + w * ac


def _prune_simplex_triangle(simplex, a, b, c, closest):
    """Remove vertices from a 3-point simplex that don't contribute to *closest*."""
    eps = 1e-10
    if np.linalg.norm(closest - a) < eps:
        simplex[:] = [simplex[0]]
    elif np.linalg.norm(closest - b) < eps:
        simplex[:] = [simplex[1]]
    elif np.linalg.norm(closest - c) < eps:
        simplex[:] = [simplex[2]]
    else:
        ab_closest, _ = _closest_point_on_segment(a, b)
        if np.linalg.norm(closest - ab_closest) < eps:
            simplex[:] = [simplex[0], simplex[1]]
            return
        ac_closest, _ = _closest_point_on_segment(a, c)
        if np.linalg.norm(closest - ac_closest) < eps:
            simplex[:] = [simplex[0], simplex[2]]
            return
        bc_closest, _ = _closest_point_on_segment(b, c)
        if np.linalg.norm(closest - bc_closest) < eps:
            simplex[:] = [simplex[1], simplex[2]]
            return


def _point_in_tetrahedron(p, verts):
    """Check if point p is inside tetrahedron defined by 4 vertices."""
    a, b, c, d = verts[0], verts[1], verts[2], verts[3]

    def _same_side(v1, v2, v3, v4, p_test):
        normal = np.cross(v2 - v1, v3 - v1)
        dot_v4 = normal.dot(v4 - v1)
        dot_p = normal.dot(p_test - v1)
        return dot_v4 * dot_p >= 0

    return (
        _same_side(a, b, c, d, p)
        and _same_side(b, c, d, a, p)
        and _same_side(c, d, a, b, p)
        and _same_side(d, a, b, c, p)
    )


def _reduce_tetrahedron(simplex):
    """For a 4-point simplex, find the closest feature to the origin."""
    faces = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]

    best_dist = float("inf")
    best_closest = simplex[0][0].copy()
    best_face = (0,)

    for i, j, k in faces:
        a, b, c = simplex[i][0], simplex[j][0], simplex[k][0]
        cp = _closest_point_on_triangle(a, b, c)
        d = np.linalg.norm(cp)
        if d < best_dist:
            best_dist = d
            best_closest = cp
            best_face = (i, j, k)

    pts = np.array([s[0] for s in simplex])
    if _point_in_tetrahedron(np.zeros(3), pts):
        return np.zeros(3), simplex

    new_simplex = [simplex[idx] for idx in best_face]
    _prune_simplex_triangle(
        new_simplex, new_simplex[0][0], new_simplex[1][0], new_simplex[2][0], best_closest
    )
    return best_closest, new_simplex


def _barycentric_triangle(a, b, c, p):
    """Compute barycentric coordinates of point p w.r.t. triangle ABC."""
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00 = v0.dot(v0)
    d01 = v0.dot(v1)
    d11 = v1.dot(v1)
    d20 = v2.dot(v0)
    d21 = v2.dot(v1)
    denom = d00 * d11 - d01 * d01 + 1e-30
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return np.array([u, v, w])


def gjk_distance(vertices_a, vertices_b, max_iterations=64, tolerance=1e-8):
    """Compute the minimum distance between two convex polyhedra using GJK.

    Args:
        vertices_a: (N, 3) ndarray — vertices of shape A.
        vertices_b: (M, 3) ndarray — vertices of shape B.
        max_iterations: maximum GJK iterations.
        tolerance: convergence threshold.

    Returns:
        (distance, closest_point_a, closest_point_b)
        distance:        minimum Euclidean distance (0 if penetrating).
        closest_point_a: (3,) point on A closest to B.
        closest_point_b: (3,) point on B closest to A.
    """
    vertices_a = np.asarray(vertices_a, dtype=float)
    vertices_b = np.asarray(vertices_b, dtype=float)

    direction = vertices_a.mean(axis=0) - vertices_b.mean(axis=0)
    if np.linalg.norm(direction) < 1e-12:
        direction = np.array([1.0, 0.0, 0.0])

    sup_a = _gjk_support(vertices_a, direction)
    sup_b = _gjk_support(vertices_b, -direction)
    w = sup_a - sup_b

    simplex = [(w, sup_a, sup_b)]
    closest = w.copy()

    for _ in range(max_iterations):
        direction = -closest
        dir_norm = np.linalg.norm(direction)
        if dir_norm < tolerance:
            break
        direction /= dir_norm

        sup_a = _gjk_support(vertices_a, direction)
        sup_b = _gjk_support(vertices_b, -direction)
        w = sup_a - sup_b

        if w.dot(direction) - closest.dot(direction) < tolerance:
            break

        simplex.append((w, sup_a, sup_b))

        n = len(simplex)
        if n == 2:
            a_pt, b_pt = simplex[0][0], simplex[1][0]
            closest, t = _closest_point_on_segment(a_pt, b_pt)
            if t <= 0.0:
                simplex = [simplex[0]]
            elif t >= 1.0:
                simplex = [simplex[1]]
        elif n == 3:
            a_pt, b_pt, c_pt = simplex[0][0], simplex[1][0], simplex[2][0]
            closest = _closest_point_on_triangle(a_pt, b_pt, c_pt)
            _prune_simplex_triangle(simplex, a_pt, b_pt, c_pt, closest)
        elif n == 4:
            closest, simplex = _reduce_tetrahedron(simplex)

    dist = np.linalg.norm(closest)

    if len(simplex) == 1:
        pt_a = simplex[0][1]
        pt_b = simplex[0][2]
    elif len(simplex) == 2:
        _, t = _closest_point_on_segment(simplex[0][0], simplex[1][0])
        pt_a = (1.0 - t) * simplex[0][1] + t * simplex[1][1]
        pt_b = (1.0 - t) * simplex[0][2] + t * simplex[1][2]
    elif len(simplex) == 3:
        bary = _barycentric_triangle(simplex[0][0], simplex[1][0], simplex[2][0], closest)
        pt_a = bary[0] * simplex[0][1] + bary[1] * simplex[1][1] + bary[2] * simplex[2][1]
        pt_b = bary[0] * simplex[0][2] + bary[1] * simplex[1][2] + bary[2] * simplex[2][2]
    else:
        pt_a = vertices_a.mean(axis=0)
        pt_b = vertices_b.mean(axis=0)
        dist = 0.0

    return dist, pt_a, pt_b


if __name__ == "__main__":
    import doctest

    doctest.testmod()
