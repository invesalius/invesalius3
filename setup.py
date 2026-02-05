import os
import pathlib
import subprocess
import sys

import setuptools


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
            self.announce(f"Compiling plugin: {p}")
            os.chdir(plugin_folder)
            subprocess.check_call([sys.executable, "setup.py", "build_ext", "--inplace"])
            os.chdir(inv_folder)


setuptools.setup(
    cmdclass={
        "build_plugins": BuildPluginsCommand,
    },
)
