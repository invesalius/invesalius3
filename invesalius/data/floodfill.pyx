import numpy as np
cimport numpy as np
cimport cython

from collections import deque

from libc.math cimport floor, ceil
from libcpp.deque cimport deque as cdeque

from cy_my_types cimport image_t, mask_t

@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.wraparound(False)
@cython.nonecheck(False)
@cython.cdivision(True)
cdef inline void append_queue(cdeque[int]& stack, int x, int y, int z, int d, int h, int w) nogil:
    stack.push_back(z*h*w + y*w + x)


@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.wraparound(False)
@cython.nonecheck(False)
@cython.cdivision(True)
cdef inline void pop_queue(cdeque[int]& stack, int* x, int* y, int* z, int d, int h, int w) nogil:
    cdef int i = stack.front()
    stack.pop_front()
    x[0] = i % w
    y[0] = (i / w) % h
    z[0] = i / (h * w)


@cython.boundscheck(False) # turn of bounds-checking for entire function
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


@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.wraparound(False)
@cython.nonecheck(False)
def floodfill_threshold(np.ndarray[image_t, ndim=3] data, list seeds, int t0, int t1, int fill, tuple neighbor_iter, np.ndarray[mask_t, ndim=3] out):

    cdef int to_return = 0
    if out is None:
        out = np.zeros_like(data)
        to_return = 1

    cdef int x, y, z
    cdef int xd, yd, zd
    cdef int w, h, d
    cdef int xo, yo, zo

    d = data.shape[0]
    h = data.shape[1]
    w = data.shape[2]

    stack = deque()

    for i, j, k in seeds:
        if data[k, j, i] >= t0 and data[k, j, i] <= t1:
            stack.append((i, j, k))
            out[k, j, i] = fill

    while stack:
        x, y, z = stack.pop()


        for xd, yd, zd in neighbor_iter:
            xo = x + xd
            yo = y + yd
            zo = z + zd
            if 0 <= (x + xd) < w and 0 <= (y + yd) < h and 0 <= (z + zd) < d and out[zo, yo, xo] != fill and t0 <= data[zo, yo, xo] <= t1:
                out[zo, yo, xo] = fill
                stack.append((xo, yo, zo))

        #  if z + 1 < d and data[z + 1, y, x] >= t0 and data[z + 1, y, x] <= t1 and out[zo + 1, yo, xo] != fill:
            #  out[zo + 1, yo, xo] =  fill
            #  stack.append((x, y, z + 1))

        #  if z - 1 >= 0 and data[z - 1, y, x] >= t0 and data[z - 1, y, x] <= t1 and out[zo - 1, yo, xo] != fill:
            #  out[zo - 1, yo, xo] = fill
            #  stack.append((x, y, z - 1))

        #  if y + 1 < h and data[z, y + 1, x] >= t0 and data[z, y + 1, x] <= t1 and out[zo, yo + 1, xo] != fill:
            #  out[zo, yo + 1, xo] = fill
            #  stack.append((x, y + 1, z))

        #  if y - 1 >= 0 and data[z, y - 1, x] >= t0 and data[z, y - 1, x] <= t1 and out[zo, yo - 1, xo] != fill:
            #  out[zo, yo - 1, xo] = fill
            #  stack.append((x, y - 1, z))

        #  if x + 1 < w and data[z, y, x + 1] >= t0 and data[z, y, x + 1] <= t1 and out[zo, yo, xo + 1] != fill:
            #  out[zo, yo, xo + 1] = fill
            #  stack.append((x + 1, y, z))

        #  if x - 1 >= 0 and data[z, y, x - 1] >= t0 and data[z, y, x - 1] <= t1 and out[zo, yo, xo - 1] != fill:
            #  out[zo, yo, xo - 1] = fill
            #  stack.append((x - 1, y, z))

    if to_return:
        return out


@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.wraparound(False)
@cython.nonecheck(False)
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
        print i, j, k, d, h, w

    with nogil:
        while stack.size():
            pop_queue(stack, &x, &y, &z, d, h, w)

            #  print x, y, z, d, h, w

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
