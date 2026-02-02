# distutils: define_macros=NPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True
# cython: nonecheck=False
# cython: language_level=3

import numpy as np
cimport numpy as np
cimport cython

from collections import deque

from cython.parallel cimport prange
from libc.math cimport floor, ceil
from libcpp cimport bool
from libcpp.deque cimport deque as cdeque
from libcpp.vector cimport vector

from .cy_my_types cimport image_t, mask_t

cdef struct s_coord:
    int x
    int y
    int z

ctypedef s_coord coord


cdef inline void append_queue(cdeque[int]& stack, int x, int y, int z, int d, int h, int w) noexcept nogil:
    stack.push_back(z*h*w + y*w + x)


cdef inline void pop_queue(cdeque[int]& stack, int* x, int* y, int* z, int d, int h, int w) noexcept nogil:
    cdef int i = stack.front()
    stack.pop_front()
    x[0] = i % w
    y[0] = (i / w) % h
    z[0] = i / (h * w)


def floodfill(np.ndarray[image_t, ndim=3] data, int i, int j, int k, int v, int fill, np.ndarray[mask_t, ndim=3] out):

    cdef int to_return = 0
    if out is None:
        out = np.zeros_like(data)
        to_return = 1

    cdef int x, y, z
    cdef int w, h, d

    d = data.shape[0]
    h = data.shape[1]
    w = data.shape[2]

    stack = [(i, j, k), ]
    out[k, j, i] = fill

    while stack:
        x, y, z = stack.pop()

        if z + 1 < d and data[z + 1, y, x] == v and out[z + 1, y, x] != fill:
            out[z + 1, y, x] =  fill
            stack.append((x, y, z + 1))

        if z - 1 >= 0 and data[z - 1, y, x] == v and out[z - 1, y, x] != fill:
            out[z - 1, y, x] = fill
            stack.append((x, y, z - 1))

        if y + 1 < h and data[z, y + 1, x] == v and out[z, y + 1, x] != fill:
            out[z, y + 1, x] = fill
            stack.append((x, y + 1, z))

        if y - 1 >= 0 and data[z, y - 1, x] == v and out[z, y - 1, x] != fill:
            out[z, y - 1, x] = fill
            stack.append((x, y - 1, z))

        if x + 1 < w and data[z, y, x + 1] == v and out[z, y, x + 1] != fill:
            out[z, y, x + 1] = fill
            stack.append((x + 1, y, z))

        if x - 1 >= 0 and data[z, y, x - 1] == v and out[z, y, x - 1] != fill:
            out[z, y, x - 1] = fill
            stack.append((x - 1, y, z))

    if to_return:
        return out


def floodfill_threshold(np.ndarray[image_t, ndim=3] data, list seeds, int t0, int t1, int fill, np.ndarray[mask_t, ndim=3] strct, np.ndarray[mask_t, ndim=3] out):

    cdef int to_return = 0
    if out is None:
        out = np.zeros_like(data)
        to_return = 1

    cdef int x, y, z
    cdef int dx, dy, dz
    cdef int odx, ody, odz
    cdef int xo, yo, zo
    cdef int i, j, k
    cdef int offset_x, offset_y, offset_z

    dz = data.shape[0]
    dy = data.shape[1]
    dx = data.shape[2]

    odz = strct.shape[0]
    ody = strct.shape[1]
    odx = strct.shape[2]

    cdef cdeque[coord] stack
    cdef coord c

    offset_z = odz // 2
    offset_y = ody // 2
    offset_x = odx // 2

    for i, j, k in seeds:
        if data[k, j, i] >= t0 and data[k, j, i] <= t1:
            c.x = i
            c.y = j
            c.z = k
            stack.push_back(c)
            out[k, j, i] = fill

    with nogil:
        while stack.size():
            c = stack.back()
            stack.pop_back()

            x = c.x
            y = c.y
            z = c.z

            out[z, y, x] = fill

            for k in range(odz):
                zo = z + k - offset_z
                for j in range(ody):
                    yo = y + j - offset_y
                    for i in range(odx):
                        if strct[k, j, i]:
                            xo = x + i - offset_x
                            if 0 <= xo < dx and 0 <= yo < dy and 0 <= zo < dz and out[zo, yo, xo] != fill and t0 <= data[zo, yo, xo] <= t1:
                                out[zo, yo, xo] = fill
                                c.x = xo
                                c.y = yo
                                c.z = zo
                                stack.push_back(c)

    if to_return:
        return out


def floodfill_auto_threshold(np.ndarray[image_t, ndim=3] data, list seeds, float p, int fill, np.ndarray[mask_t, ndim=3] out):

    cdef int to_return = 0
    if out is None:
        out = np.zeros_like(data)
        to_return = 1

    cdef cdeque[int] stack
    cdef int x, y, z
    cdef int w, h, d
    cdef int xo, yo, zo
    cdef int t0, t1

    cdef int i, j, k

    d = data.shape[0]
    h = data.shape[1]
    w = data.shape[2]


    #  stack = deque()

    x = 0
    y = 0
    z = 0


    for i, j, k in seeds:
        append_queue(stack, i, j, k, d, h, w)
        out[k, j, i] = fill
        print(i, j, k, d, h, w)

    with nogil:
        while stack.size():
            pop_queue(stack, &x, &y, &z, d, h, w)

            #  print(x, y, z, d, h, w)

            xo = x
            yo = y
            zo = z

            t0 = <int>ceil(data[z, y, x] * (1 - p))
            t1 = <int>floor(data[z, y, x] * (1 + p))

            if z + 1 < d and data[z + 1, y, x] >= t0 and data[z + 1, y, x] <= t1 and out[zo + 1, yo, xo] != fill:
                out[zo + 1, yo, xo] =  fill
                append_queue(stack, x, y, z+1, d, h, w)

            if z - 1 >= 0 and data[z - 1, y, x] >= t0 and data[z - 1, y, x] <= t1 and out[zo - 1, yo, xo] != fill:
                out[zo - 1, yo, xo] = fill
                append_queue(stack, x, y, z-1, d, h, w)

            if y + 1 < h and data[z, y + 1, x] >= t0 and data[z, y + 1, x] <= t1 and out[zo, yo + 1, xo] != fill:
                out[zo, yo + 1, xo] = fill
                append_queue(stack, x, y+1, z, d, h, w)

            if y - 1 >= 0 and data[z, y - 1, x] >= t0 and data[z, y - 1, x] <= t1 and out[zo, yo - 1, xo] != fill:
                out[zo, yo - 1, xo] = fill
                append_queue(stack, x, y-1, z, d, h, w)

            if x + 1 < w and data[z, y, x + 1] >= t0 and data[z, y, x + 1] <= t1 and out[zo, yo, xo + 1] != fill:
                out[zo, yo, xo + 1] = fill
                append_queue(stack, x+1, y, z, d, h, w)

            if x - 1 >= 0 and data[z, y, x - 1] >= t0 and data[z, y, x - 1] <= t1 and out[zo, yo, xo - 1] != fill:
                out[zo, yo, xo - 1] = fill
                append_queue(stack, x-1, y, z, d, h, w)

    if to_return:
        return out


def fill_holes_automatically(np.ndarray[mask_t, ndim=3] mask, np.ndarray[np.uint32_t, ndim=3] labels, unsigned int nlabels, unsigned int max_size):
    """
    Fill mask holes automatically. The hole must <= max_size. Return True if any hole were filled.
    """
    cdef np.ndarray[np.uint32_t, ndim=1] sizes = np.zeros(shape=(nlabels + 1), dtype=np.uint32)
    cdef int x, y, z
    cdef int dx, dy, dz
    cdef int i

    cdef bool modified = False

    dz = mask.shape[0]
    dy = mask.shape[1]
    dx = mask.shape[2]

    for z in range(dz):
        for y in range(dy):
            for x in range(dx):
                sizes[labels[z, y, x]] += 1

    #Checking if any hole will be filled
    for i in range(nlabels + 1):
        if sizes[i] <= max_size:
            modified = True

    if not modified:
        return 0

    for z in prange(dz, nogil=True):
        for y in range(dy):
            for x in range(dx):
                if sizes[labels[z, y, x]] <= max_size:
                    mask[z, y, x] = 254

    return modified
