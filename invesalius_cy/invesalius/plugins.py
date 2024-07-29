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

from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher


def import_source(module_name, module_file_path):
    module_spec = importlib.util.spec_from_file_location(module_name, module_file_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.__bind_pubsub_evt()

    def __bind_pubsub_evt(self):
        Publisher.subscribe(self.load_plugin, "Load plugin")

    def find_plugins(self):
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
                print("It was not possible to load plugin. Error: {}".format(err))

        Publisher.sendMessage("Add plugins menu items", items=self.plugins)

    def load_plugin(self, plugin_name):
        if plugin_name in self.plugins:
            plugin_module = import_source(
                plugin_name, self.plugins[plugin_name]["folder"].joinpath("__init__.py")
            )
            sys.modules[plugin_name] = plugin_module
            main = importlib.import_module(plugin_name + ".main")
            main.load()
