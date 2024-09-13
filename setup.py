import logging
import os
import pathlib
import subprocess
import sys

import numpy
import setuptools
from Cython.Build import build_ext, cythonize

if sys.platform == "darwin":
    unix_copt = ["-Xpreprocessor", "-fopenmp", "-lomp"]
    unix_lopt = ["-Xpreprocessor", "-fopenmp", "-lomp"]
else:
    unix_copt = [
        "-fopenmp",
    ]
    unix_lopt = [
        "-fopenmp",
    ]


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


class BuildPluginsCommand(setuptools.Command):
    """
    A custom command to build all plugins with cython code.
    """

    description = "Build all plugins with cython code"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        compilable_plugins = ["porous_creation", "remove_tiny_objects"]
        inv_folder = pathlib.Path(__file__).parent.resolve()
        plugins_folder = inv_folder.joinpath("plugins")
        for p in compilable_plugins:
            plugin_folder = plugins_folder.joinpath(p)
            self.announce("Compiling plugin: {}".format(p))
            os.chdir(plugin_folder)
            subprocess.check_call([sys.executable, "setup.py", "build_ext", "--inplace"])
            os.chdir(inv_folder)


setuptools.setup(
    cmdclass={
        "build_ext": build_ext_subclass,
        "build_plugins": BuildPluginsCommand,
    },
    ext_modules=cythonize(
        [
            setuptools.Extension(
                "invesalius_cy.mips",
                ["invesalius_cy/mips.pyx"],
            ),
            setuptools.Extension(
                "invesalius_cy.interpolation",
                ["invesalius_cy/interpolation.pyx"],
            ),
            setuptools.Extension(
                "invesalius_cy.transforms",
                ["invesalius_cy/transforms.pyx"],
            ),
            setuptools.Extension(
                "invesalius_cy.floodfill",
                ["invesalius_cy/floodfill.pyx"],
                language="c++",
            ),
            setuptools.Extension(
                "invesalius_cy.cy_mesh",
                ["invesalius_cy/cy_mesh.pyx"],
                language="c++",
            ),
        ]
    ),
)
