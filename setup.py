from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext
from Cython.Build import cythonize

import os
import sys

import numpy

if sys.platform == 'linux2':
    setup(
        cmdclass = {'build_ext': build_ext},
        ext_modules = cythonize([ Extension("invesalius.data.mips", ["invesalius/data/mips.pyx"],
                                  include_dirs =  [numpy.get_include()],
                                  extra_compile_args=['-fopenmp'],
                                  extra_link_args=['-fopenmp']),

                       Extension("invesalius.data.interpolation", ["invesalius/data/interpolation.pyx"],
                                 include_dirs=[numpy.get_include()],
                                 extra_compile_args=['-fopenmp',],
                                 extra_link_args=['-fopenmp',]),

                       Extension("invesalius.data.transforms", ["invesalius/data/transforms.pyx"],
                                 include_dirs=[numpy.get_include()],
                                 extra_compile_args=['-fopenmp',],
                                 extra_link_args=['-fopenmp',]),
                       ])
         )

elif sys.platform == 'win32':
    setup(
        cmdclass = {'build_ext': build_ext},
        ext_modules = [ Extension("invesalius.data.mips", ["invesalius/data/mips.pyx"],
                                  include_dirs =  [numpy.get_include()],
                                  extra_compile_args=['/openmp'],
                                 )]
         )

else:
    setup(
        packages=["invesalius", ],
        cmdclass = {'build_ext': build_ext},
        ext_modules = cythonize([Extension("invesalius.data.mips", ["invesalius/data/mips.pyx"],
                                           include_dirs =  [numpy.get_include()],
                                           extra_compile_args=['-fopenmp',],
                                           extra_link_args=['-fopenmp',]),

                                 Extension("invesalius.data.interpolation", ["invesalius/data/interpolation.pyx"],
                                           include_dirs=[numpy.get_include()],
                                           extra_compile_args=['-fopenmp',],
                                           extra_link_args=['-fopenmp',]),

                                 Extension("invesalius.data.transforms", ["invesalius/data/transforms.pyx"],
                                           include_dirs=[numpy.get_include()],
                                           extra_compile_args=['-fopenmp',],
                                           extra_link_args=['-fopenmp',]),
                                 ])
    )
