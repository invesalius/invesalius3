import os
import sys
from distutils.core import setup
from distutils.extension import Extension

import numpy
from Cython.Build import cythonize
from Cython.Distutils import build_ext

if sys.platform == 'darwin':
    unix_copt = ['-Xpreprocessor', '-fopenmp', '-lomp']
    unix_lopt = ['-Xpreprocessor', '-fopenmp', '-lomp']
else:
    unix_copt = ['-fopenmp',]
    unix_lopt = ['-fopenmp',]


copt = {"msvc": ["/openmp"], "mingw32": ["-fopenmp"], "unix": unix_copt}

lopt = {"mingw32": ["-fopenmp"], "unix": unix_lopt}


class build_ext_subclass(build_ext):
    def build_extensions(self):
        c = self.compiler.compiler_type
        print("Compiler", c)
        if c in copt:
            for e in self.extensions:
                e.extra_compile_args = copt[c]
        if c in lopt:
            for e in self.extensions:
                e.extra_link_args = lopt[c]
        for e in self.extensions:
            e.include_dirs = [numpy.get_include()]
        build_ext.build_extensions(self)


setup(
    cmdclass={"build_ext": build_ext_subclass},
    packages=['invesalius_pubsub'],
    ext_modules=cythonize(
        [
            Extension(
                "invesalius_cy.mips",
                ["invesalius_cy/mips.pyx"],
            ),
            Extension(
                "invesalius_cy.interpolation",
                ["invesalius_cy/interpolation.pyx"],
            ),
            Extension(
                "invesalius_cy.transforms",
                ["invesalius_cy/transforms.pyx"],
            ),
            Extension(
                "invesalius_cy.floodfill",
                ["invesalius_cy/floodfill.pyx"],
                language="c++",
            ),
            Extension(
                "invesalius_cy.cy_mesh",
                ["invesalius_cy/cy_mesh.pyx"],
                language="c++",
            ),
        ]
    ),
)
