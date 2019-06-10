#--------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------
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
#--------------------------------------------------------------------

import json
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as consts
from invesalius import inv_paths


class PluginManager:
    def __init__(self):
        self.plugins = {}

    def __bind_pubsub_evt(self):
        Publisher.subscribe(self.load_plugin, 'Load plugin')

    def find_plugins(self):
        self.plugins = {}
        for p in sorted(inv_paths.USER_PLUGINS_DIRECTORY.glob("*")):
            if p.is_dir():
                try:
                    with p.joinpath('plugin.json').open() as f:
                        jdict = json.load(f)
                        plugin_name = jdict["name"]
                        plugin_description = jdict["description"]

                        self.plugins[plugin_name] = {
                            "description": plugin_description,
                            "folder": p
                        }
                except Exception as err:
                    print("It was not possible to load plugin. Error: {}".format(err))

        Publisher.sendMessage("Add plugins menu items", items=self.plugins)

    def load_plugin(self, name):
        if name in self.plugins:
            print("NAME")
