# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------

import glob
import importlib.util
import json
import pathlib
import sys
from itertools import chain
from types import ModuleType
from typing import TYPE_CHECKING

from invesalius import inv_paths, project
from invesalius.gui import dialogs
from invesalius.pubsub import pub as Publisher
from invesalius.utils import new_name_by_pattern

if TYPE_CHECKING:
    import os


def import_source(module_name: str, module_file_path: "str | bytes | os.PathLike") -> ModuleType:
    module_spec = importlib.util.spec_from_file_location(module_name, module_file_path)
    if module_spec is None:
        raise ImportError(f"No module named {module_name}")
    module = importlib.util.module_from_spec(module_spec)
    if module_spec.loader is None:
        raise ImportError(f"Loader is None for module {module_name}")
    module_spec.loader.exec_module(module)
    return module


class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.__bind_pubsub_evt()

    def __bind_pubsub_evt(self) -> None:
        Publisher.subscribe(self.load_plugin, "Load plugin")
        Publisher.subscribe(self.remove_non_visible_faces_no_gui, "Remove non-visible faces")

    def find_plugins(self) -> None:
        self.plugins = {}
        for p in chain(
            glob.glob(str(inv_paths.PLUGIN_DIRECTORY.joinpath("**/plugin.json")), recursive=True),
            glob.glob(
                str(inv_paths.USER_PLUGINS_DIRECTORY.joinpath("**/plugin.json")), recursive=True
            ),
        ):
            try:
                p = pathlib.Path(p)
                with p.open() as f:
                    jdict = json.load(f)
                    plugin_name = jdict["name"]
                    plugin_description = jdict["description"]
                    enable_startup = jdict.get("enable-startup", False)

                    self.plugins[plugin_name] = {
                        "name": plugin_name,
                        "description": plugin_description,
                        "folder": p.parent,
                        "enable_startup": enable_startup,
                    }
            except Exception as err:
                print(f"It was not possible to load plugin. Error: {err}")

        Publisher.sendMessage("Add plugins menu items", items=self.plugins)

    def load_plugin(self, plugin_name: str) -> None:
        if plugin_name in self.plugins:
            plugin_module = import_source(
                plugin_name, self.plugins[plugin_name]["folder"].joinpath("__init__.py")
            )
            sys.modules[plugin_name] = plugin_module
            main = importlib.import_module(plugin_name + ".main")
            main.load()

    # Remove non-visible faces from a surface without using the plugin GUI.
    # Defaults to the last surface in surface_dict which is generally the newest surface
    def remove_non_visible_faces_no_gui(self, surface_idx: int = -1) -> None:
        plugin_name = "Remove non-visible faces"
        if plugin_name in self.plugins:
            progress_dialog = dialogs.RemoveNonVisibleFacesProgressWindow()
            progress_dialog.Update()
            plugin_module = import_source(
                plugin_name, self.plugins[plugin_name]["folder"].joinpath("__init__.py")
            )
            sys.modules[plugin_name] = plugin_module
            remove_faces = importlib.import_module(plugin_name + ".remove_non_visible_faces")

            inv_proj = project.Project()
            try:
                surface = list(inv_proj.surface_dict.values())[surface_idx]
            except IndexError:
                print(f"Invalid surface_dict index {surface_idx}, did not remove non-visible faces")
                return

            overwrite = False
            new_polydata = remove_faces.remove_non_visible_faces(
                surface.polydata, remove_visible=False
            )

            name = new_name_by_pattern(f"{surface.name}_removed_nonvisible")
            colour = None

            Publisher.sendMessage(
                "Create surface from polydata",
                polydata=new_polydata,
                name=name,
                overwrite=overwrite,
                index=surface_idx,
                colour=colour,
            )
            Publisher.sendMessage("Fold surface task")
            progress_dialog.Close()
