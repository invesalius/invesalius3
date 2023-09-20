#cython: language_level=3

#http://en.wikipedia.org/wiki/Local_maximum_intensity_projection
import numpy as np
cimport numpy as np
cimport cython

from libc.math cimport floor, ceil, sqrt, fabs
from cython.parallel cimport prange

DTYPE = np.uint8
ctypedef np.uint8_t DTYPE_t

DTYPE16 = np.int16
ctypedef np.int16_t DTYPE16_t

DTYPEF32 = np.float32
ctypedef np.float32_t DTYPEF32_t

@cython.boundscheck(False) # turn of bounds-checking for entire function
def lmip(np.ndarray[DTYPE16_t, ndim=3] image, int axis, DTYPE16_t tmin,
         DTYPE16_t tmax, np.ndarray[DTYPE16_t, ndim=2] out):
    cdef DTYPE16_t max
    cdef int start
    cdef int sz = image.shape[0]
    cdef int sy = image.shape[1]
    cdef int sx = image.shape[2]

    # AXIAL
    if axis == 0:
        for x in range(sx):
            for y in range(sy):
                max = image[0, y, x]
                if max >= tmin and max <= tmax:
                    start = 1
                else:
                    start = 0
                for z in range(sz):
                    if image[z, y, x] > max:
                        max = image[z, y, x]

                    elif image[z, y, x] < max and start:
                        break
                    
                    if image[z, y, x] >= tmin and image[z, y, x] <= tmax:
                        start = 1

                out[y, x] = max

    #CORONAL
    elif axis == 1:
        for z in range(sz):
            for x in range(sx):
                max = image[z, 0, x]
                if max >= tmin and max <= tmax:
                    start = 1
                else:
                    start = 0
                for y in range(sy):
                    if image[z, y, x] > max:
                        max = image[z, y, x]

                    elif image[z, y, x] < max and start:
                        break
                    
                    if image[z, y, x] >= tmin and image[z, y, x] <= tmax:
                        start = 1

                out[z, x] = max

    #CORONAL
    elif axis == 2:
        for z in range(sz):
            for y in range(sy):
                max = image[z, y, 0]
                if max >= tmin and max <= tmax:
                    start = 1
                else:
                    start = 0
                for x in range(sx):
                    if image[z, y, x] > max:
                        max = image[z, y, x]

                    elif image[z, y, x] < max and start:
                        break
                    
                    if image[z, y, x] >= tmin and image[z, y, x] <= tmax:
                        start = 1

                out[z, y] = max


cdef DTYPE16_t get_colour(DTYPE16_t vl, DTYPE16_t wl, DTYPE16_t ww):
    cdef DTYPE16_t out_colour
    cdef DTYPE16_t min_value = wl - (ww // 2)
    cdef DTYPE16_t max_value = wl + (ww // 2)
    if vl < min_value:
        out_colour = min_value
    elif vl > max_value:
        out_colour = max_value
    else:
        out_colour = vl

    return out_colour

@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
cdef float get_opacity(DTYPE16_t vl, DTYPE16_t wl, DTYPE16_t ww) nogil:
    cdef float out_opacity
    cdef DTYPE16_t min_value = wl - (ww // 2)
    cdef DTYPE16_t max_value = wl + (ww // 2)
    if vl < min_value:
        out_opacity = 0.0
    elif vl > max_value:
        out_opacity = 1.0
    else:
        out_opacity = 1.0/(max_value - min_value) * (vl - min_value)

    return out_opacity

@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
cdef float get_opacity_f32(DTYPEF32_t vl, DTYPE16_t wl, DTYPE16_t ww) nogil:
    cdef float out_opacity
    cdef DTYPE16_t min_value = wl - (ww // 2)
    cdef DTYPE16_t max_value = wl + (ww // 2)
    if vl < min_value:
        out_opacity = 0.0
    elif vl > max_value:
        out_opacity = 1.0
    else:
        out_opacity = 1.0/(max_value - min_value) * (vl - min_value)

    return out_opacity


@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
def mida(np.ndarray[DTYPE16_t, ndim=3] image, int axis, DTYPE16_t wl,
         DTYPE16_t ww, np.ndarray[DTYPE16_t, ndim=2] out):
    cdef int sz = image.shape[0]
    cdef int sy = image.shape[1]
    cdef int sx = image.shape[2]

    cdef DTYPE16_t min = image.min()
    cdef DTYPE16_t max = image.max()
    cdef DTYPE16_t vl

    cdef DTYPE16_t min_value = wl - (ww // 2)
    cdef DTYPE16_t max_value = wl + (ww // 2)

    cdef float fmax=0.0
    cdef float fpi
    cdef float dl
    cdef float bt

    cdef float alpha
    cdef float alpha_p = 0.0
    cdef float colour
    cdef float colour_p = 0

    cdef int x, y, z

    # AXIAL
    if axis == 0:
        for x in prange(sx, nogil=True):
            for y in range(sy):
                fmax = 0.0
                alpha_p = 0.0
                colour_p = 0.0
                for z in range(sz):
                    vl = image[z, y, x]
                    fpi = 1.0/(max - min) * (vl - min)
                    if fpi > fmax:
                        dl = fpi - fmax
                        fmax = fpi
                    else:
                        dl = 0.0

                    bt = 1.0 - dl
                    
                    colour = fpi
                    alpha = get_opacity(vl, wl, ww)
                    colour = (bt * colour_p) + (1 - bt * alpha_p) * colour * alpha
                    alpha = (bt * alpha_p) + (1 - bt * alpha_p) * alpha

                    colour_p = colour
                    alpha_p = alpha

                    if alpha >= 1.0:
                        break


                #out[y, x] = <DTYPE16_t>((max_value - min_value) * colour + min_value)
                out[y, x] = <DTYPE16_t>((max - min) * colour + min)


    #CORONAL
    elif axis == 1:
        for z in prange(sz, nogil=True):
            for x in range(sx):
                fmax = 0.0
                alpha_p = 0.0
                colour_p = 0.0
                for y in range(sy):
                    vl = image[z, y, x]
                    fpi = 1.0/(max - min) * (vl - min)
                    if fpi > fmax:
                        dl = fpi - fmax
                        fmax = fpi
                    else:
                        dl = 0.0

                    bt = 1.0 - dl
                    
                    colour = fpi
                    alpha = get_opacity(vl, wl, ww)
                    colour = (bt * colour_p) + (1 - bt * alpha_p) * colour * alpha
                    alpha = (bt * alpha_p) + (1 - bt * alpha_p) * alpha

                    colour_p = colour
                    alpha_p = alpha

                    if alpha >= 1.0:
                        break

                out[z, x] = <DTYPE16_t>((max - min) * colour + min)

    #AXIAL
    elif axis == 2:
        for z in prange(sz, nogil=True):
            for y in range(sy):
                fmax = 0.0
                alpha_p = 0.0
                colour_p = 0.0
                for x in range(sx):
                    vl = image[z, y, x]
                    fpi = 1.0/(max - min) * (vl - min)
                    if fpi > fmax:
                        dl = fpi - fmax
                        fmax = fpi
                    else:
                        dl = 0.0

                    bt = 1.0 - dl
                    
                    colour = fpi
                    alpha = get_opacity(vl, wl, ww)
                    colour = (bt * colour_p) + (1 - bt * alpha_p) * colour * alpha
                    alpha = (bt * alpha_p) + (1 - bt * alpha_p) * alpha

                    colour_p = colour
                    alpha_p = alpha

                    if alpha >= 1.0:
                        break

                out[z, y] = <DTYPE16_t>((max - min) * colour + min)



@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
cdef inline void finite_difference(DTYPE16_t[:, :, :] image,
                              int x, int y, int z, float h, float *g) noexcept nogil:
    cdef int px, py, pz, fx, fy, fz

    cdef int sz = image.shape[0]
    cdef int sy = image.shape[1]
    cdef int sx = image.shape[2]

    cdef float gx, gy, gz

    if x == 0:
        px = 0
        fx = 1
    elif x == sx - 1:
        px = x - 1
        fx = x
    else:
        px = x - 1
        fx = x + 1

    if y == 0:
        py = 0
        fy = 1
    elif y == sy - 1:
        py = y - 1
        fy = y
    else:
        py = y - 1
        fy = y + 1

    if z == 0:
        pz = 0
        fz = 1
    elif z == sz - 1:
        pz = z - 1
        fz = z
    else:
        pz = z - 1
        fz = z + 1

    gx = (image[z, y, fx] - image[z, y, px]) / (2*h)
    gy = (image[z, fy, x] - image[z, py, x]) / (2*h)
    gz = (image[fz, y, x] - image[pz, y, x]) / (2*h)

    g[0] = gx
    g[1] = gy
    g[2] = gz



@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
cdef inline float calc_fcm_itensity(DTYPE16_t[:, :, :] image,
                      int x, int y, int z, float n, float* dir) noexcept nogil:
    cdef float g[3]
    finite_difference(image, x, y, z, 1.0, g)
    cdef float gm = sqrt(g[0]*g[0] + g[1]*g[1] + g[2]*g[2])
    cdef float d = g[0]*dir[0] + g[1]*dir[1] + g[2]*dir[2]
    cdef float sf = (1.0 - fabs(d/gm))**n
    #alpha = get_opacity_f32(gm, wl, ww)
    cdef float vl = gm * sf
    return vl

@cython.boundscheck(False) # turn of bounds-checking for entire function
@cython.cdivision(True)
def fast_countour_mip(np.ndarray[DTYPE16_t, ndim=3] image,
                      float n,
                      int axis,
                      DTYPE16_t wl, DTYPE16_t ww,
                      int tmip,
                      np.ndarray[DTYPE16_t, ndim=2] out):
    cdef int sz = image.shape[0]
    cdef int sy = image.shape[1]
    cdef int sx = image.shape[2]
    cdef float gm
    cdef float alpha
    cdef float sf
    cdef float d

    cdef float* g
    cdef float* dir = [ 0, 0, 0 ]

    cdef DTYPE16_t[:, :, :] vimage = image
    cdef np.ndarray[DTYPE16_t, ndim=3] tmp = np.empty_like(image)

    cdef DTYPE16_t min = image.min()
    cdef DTYPE16_t max = image.max()
    cdef float fmin = <float>min
    cdef float fmax = <float>max
    cdef float vl
    cdef DTYPE16_t V

    cdef int x, y, z

    if axis == 0:
        dir[2] = 1.0
    elif axis == 1:
        dir[1] = 1.0
    elif axis == 2:
        dir[0] = 1.0

    for z in prange(sz, nogil=True):
        for y in range(sy):
            for x in range(sx):
                vl = calc_fcm_itensity(vimage, x, y, z, n, dir)
                tmp[z, y, x] = <DTYPE16_t>vl

    cdef DTYPE16_t tmin = tmp.min()
    cdef DTYPE16_t tmax = tmp.max()

    #tmp = ((max - min)/<float>(tmax - tmin)) * (tmp - tmin) + min

    if tmip == 0:
        out[:] = tmp.max(axis)
    elif tmip == 1:
        lmip(tmp, axis, 700, 3033, out)
    elif tmip == 2:
        mida(tmp, axis, wl, ww, out)
