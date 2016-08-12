import numpy as np
cimport numpy as np
cimport cython

#  ctypedef np.uint16_t image_t

ctypedef fused image_t:
    np.float64_t
    np.int16_t
    np.uint8_t

ctypedef np.uint8_t mask_t
