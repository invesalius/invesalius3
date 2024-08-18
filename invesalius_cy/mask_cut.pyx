import numpy as np
cimport numpy as np
cimport cython

from libc.math cimport floor, ceil, sqrt, fabs, round
from cython.parallel import prange

ctypedef np.float64_t DTYPEF64_t

from .cy_my_types cimport image_t, mask_t

@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
def mask_cut(np.ndarray[image_t, ndim=3] mask_data,
                float sx, float sy, float sz,
                np.ndarray[mask_t, ndim=2] filter,
                np.ndarray[DTYPEF64_t, ndim=2] M,
                np.ndarray[image_t, ndim=3] out):

    cdef int dz = mask_data.shape[0]
    cdef int dy = mask_data.shape[1]
    cdef int dx = mask_data.shape[2]

    cdef int x
    cdef int y
    cdef int z

    cdef int h = filter.shape[0]
    cdef int w = filter.shape[1]

    cdef DTYPEF64_t px
    cdef DTYPEF64_t py

    cdef DTYPEF64_t p0, p1, p2, p3
    cdef DTYPEF64_t _q0, _q1, _q2, _q3
    cdef DTYPEF64_t q0, q1, q2

    for z in prange(dz, nogil=True):
        for y in range(dy):
            for x in range(dx):
                p0 = <float>(x*sx)
                p1 = <float>(y*sy)
                p2 = <float>(z*sz)
                p3 = 1.0

                _q0 = p0 * M[0, 0] + p1 * M[0, 1] + p2 * M[0, 2] + p3 * M[0, 3]
                _q1 = p0 * M[1, 0] + p1 * M[1, 1] + p2 * M[1, 2] + p3 * M[1, 3]
                _q2 = p0 * M[2, 0] + p1 * M[2, 1] + p2 * M[2, 2] + p3 * M[2, 3]
                _q3 = p0 * M[3, 0] + p1 * M[3, 1] + p2 * M[3, 2] + p3 * M[3, 3]

                if _q3 > 0:
                    q0 = _q0/_q3
                    q1 = _q1/_q3
                    q2 = _q2/_q3

                    px = (q0/2.0 + 0.5) * (w - 1)
                    py = (q1/2.0 + 0.5) * (h - 1)

                    if 0 <= px <= w and 0 <= py <= h:
                        if filter[<int>(py), <int>(px)]:
                            out[z, y, x] = 0
