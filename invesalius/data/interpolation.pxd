from .cy_my_types cimport image_t

cdef inline double interpolate(image_t[:, :, :], double, double, double) nogil
cdef inline double tricub_interpolate(image_t[:, :, :], double, double, double) nogil
cdef inline double tricubicInterpolate (image_t[:, :, :], double, double, double) nogil
