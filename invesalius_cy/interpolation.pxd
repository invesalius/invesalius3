#cython: language_level=3

from .cy_my_types cimport image_t

cdef double interpolate(image_t[:, :, :], double, double, double) nogil
cdef double tricub_interpolate(image_t[:, :, :], double, double, double) nogil
cdef double tricubicInterpolate (image_t[:, :, :], double, double, double) nogil
cdef double lanczos3 (image_t[:, :, :], double, double, double) nogil

cdef double nearest_neighbour_interp(image_t[:, :, :], double, double, double) nogil
