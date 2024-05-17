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

from .cy_my_types cimport image_t
from .interpolation cimport interpolate, tricub_interpolate, tricubicInterpolate, lanczos3, nearest_neighbour_interp

from libc.math cimport floor, ceil, sqrt, fabs, round
from cython.parallel cimport prange

ctypedef double (*interp_function)(image_t[:, :, :], double, double, double) noexcept nogil

cdef void mul_mat4_vec4(double[:, :] M,
                            double* coord,
                            double* out) noexcept nogil:
    out[0] = coord[0] * M[0, 0] + coord[1] * M[0, 1] + coord[2] * M[0, 2] + coord[3] * M[0, 3]
    out[1] = coord[0] * M[1, 0] + coord[1] * M[1, 1] + coord[2] * M[1, 2] + coord[3] * M[1, 3]
    out[2] = coord[0] * M[2, 0] + coord[1] * M[2, 1] + coord[2] * M[2, 2] + coord[3] * M[2, 3]
    out[3] = coord[0] * M[3, 0] + coord[1] * M[3, 1] + coord[2] * M[3, 2] + coord[3] * M[3, 3]


cdef image_t coord_transform(image_t[:, :, :] volume, double[:, :] M, int x, int y, int z, double sx, double sy, double sz, int minterpol, image_t cval) noexcept nogil:

    cdef double coord[4]
    coord[0] = z*sz
    coord[1] = y*sy
    coord[2] = x*sx
    coord[3] = 1.0

    cdef double _ncoord[4]
    _ncoord[3] = 1
    # _ncoord[:] = [0.0, 0.0, 0.0, 1.0]

    cdef unsigned int dz, dy, dx
    dz = volume.shape[0]
    dy = volume.shape[1]
    dx = volume.shape[2]


    mul_mat4_vec4(M, coord, _ncoord)

    cdef double nz, ny, nx
    nz = (_ncoord[0]/_ncoord[3])/sz
    ny = (_ncoord[1]/_ncoord[3])/sy
    nx = (_ncoord[2]/_ncoord[3])/sx

    cdef double v

    if 0 <= nz <= (dz-1) and 0 <= ny <= (dy-1) and 0 <= nx <= (dx-1):
        if minterpol == 0:
            return <image_t>nearest_neighbour_interp(volume, nx, ny, nz)
        elif minterpol == 1:
            return <image_t>interpolate(volume, nx, ny, nz)
        elif minterpol == 2:
            v = tricubicInterpolate(volume, nx, ny, nz)
            if (v < cval):
                v = cval
            return <image_t>v
        else:
            v = lanczos3(volume, nx, ny, nz)
            if (v < cval):
                v = cval
            return <image_t>v
    else:
        return cval


def apply_view_matrix_transform(image_t[:, :, :] volume,
                                spacing,
                                double[:, :] M,
                                unsigned int n, str orientation,
                                int minterpol,
                                image_t cval,
                                image_t[:, :, :] out):

    cdef int dz, dy, dx
    cdef int z, y, x
    dz = volume.shape[0]
    dy = volume.shape[1]
    dx = volume.shape[2]

    cdef unsigned int odz, ody, odx
    odz = out.shape[0]
    ody = out.shape[1]
    odx = out.shape[2]

    cdef unsigned int count = 0

    cdef double sx, sy, sz
    sx = spacing[0]
    sy = spacing[1]
    sz = spacing[2]

    cdef double kkkkk = sx * sy * sz

    cdef interp_function f_interp

    if minterpol == 0:
        f_interp = nearest_neighbour_interp
    elif minterpol == 1:
        f_interp = interpolate
    elif minterpol == 2:
        f_interp = tricubicInterpolate
    else:
        f_interp = lanczos3

    if orientation == 'AXIAL':
        for z in range(n, n+odz):
            for y in prange(dy, nogil=True):
                for x in range(dx):
                    out[count, y, x] = coord_transform(volume, M, x, y, z, sx, sy, sz, minterpol, cval)
            count += 1

    elif orientation == 'CORONAL':
        for y in range(n, n+ody):
            for z in prange(dz, nogil=True):
                for x in range(dx):
                    out[z, count, x] = coord_transform(volume, M, x, y, z, sx, sy, sz, minterpol, cval)
            count += 1

    elif orientation == 'SAGITAL':
        for x in range(n, n+odx):
            for z in prange(dz, nogil=True):
                for y in range(dy):
                    out[z, y, count] = coord_transform(volume, M, x, y, z, sx, sy, sz, minterpol, cval)
            count += 1


def convolve_non_zero(image_t[:, :, :] volume,
                      image_t[:, :, :] kernel,
                      image_t cval):
    cdef Py_ssize_t x, y, z, sx, sy, sz, kx, ky, kz, skx, sky, skz, i, j, k
    cdef image_t v

    cdef image_t[:, :, :] out = np.zeros_like(volume)

    sz = volume.shape[0]
    sy = volume.shape[1]
    sx = volume.shape[2]

    skz = kernel.shape[0]
    sky = kernel.shape[1]
    skx = kernel.shape[2]

    for z in prange(sz, nogil=True):
        for y in range(sy):
            for x in range(sx):
                if volume[z, y, x] != 0:
                    for k in range(skz):
                        kz = z - skz // 2 + k
                        for j in range(sky):
                            ky = y - sky // 2 + j
                            for i in range(skx):
                                kx = x - skx // 2 + i

                                if 0 <= kz < sz and 0 <= ky < sy and 0 <= kx < sx:
                                    v = volume[kz, ky, kx]
                                else:
                                    v = cval

                                out[z, y, x] += (v * kernel[k, j, i])
    return np.asarray(out)
