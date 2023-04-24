#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------

try:
    import configparser as ConfigParser
except ImportError:
    import ConfigParser

import os
import shutil
import sys
import time
import codecs
import collections
import json
from random import randint
from threading import Thread
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional, Tuple, Union

import wx

from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton, debug, decode, deep_merge_dict

CONFIG_PATH: str = os.path.join(inv_paths.USER_INV_DIR, 'config.json')
OLD_CONFIG_PATH: str = os.path.join(inv_paths.USER_INV_DIR, 'config.cfg')

STATE_PATH: str = os.path.join(inv_paths.USER_INV_DIR, 'state.json')

SESSION_ENCODING: str = 'utf8'


# Only one session will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Session(metaclass=Singleton):

    def __init__(self) -> None:
        self.temp_item: bool = False
        self.mask_3d_preview: bool = False

        self._config: dict = {
            'project_status': 3,
            'language': '',
            'auto_reload_preview': False,
        }
        self._exited_successfully_last_time: bool = not self._ReadState()

        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self._Exit, 'Exit')

    def CreateConfig(self) -> None:
        import invesalius.constants as const
        self._config: dict = {
            'mode': const.MODE_RP,
            'project_status': const.PROJECT_STATUS_CLOSED,
            'debug': False,
            'debug_efield': False,
            'language': "",
            'random_id': randint(0, pow(10, 16)),
            'surface_interpolation': 1,
            'rendering': 0,
            'slice_interpolation': 0,
            'auto_reload_preview': False,
            'recent_projects': [(str(inv_paths.SAMPLE_DIR), u"Cranium.inv3"), ],
            'last_dicom_folder': '',
        }
        self.WriteConfigFile()

    def CreateState(self) -> None:
        self._state: dict = {}
        self.WriteStateFile()

    def DeleteStateFile(self) -> None:
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
            print("Successfully deleted state file.")
        else:
            print("State file does not exist.")

    def ExitedSuccessfullyLastTime(self) -> bool:
        return self._exited_successfully_last_time

    def SetConfig(self, key: str, value: any) -> None:
        self._config[key] = value
        self.WriteConfigFile()

    def GetConfig(self, key: str, default_value: any = None) -> any:
        if key in self._config:
            return self._config[key]
        else:
            return default_value

    def SetState(self, key: str, value: any) -> None:
        self._state[key] = value
        self.WriteStateFile()

    def GetState(self, key: str, default_value: any = None) -> any:
        if key in self._state:
            return self._state[key]
        else:
            return default_value

    def IsOpen(self) -> bool:
        import invesalius.constants as const
        return self.GetConfig('project_status') != const.PROJECT_STATUS_CLOSED

    def CloseProject(self) -> None:
        import invesalius.constants as const
        debug("Session.CloseProject")
        self.SetState('project_path', None)
        self.SetConfig('project_status', const.PROJECT_STATUS_CLOSED)
        #self.mode = const.MODE_RP
        self.temp_item = False

    def SaveProject(self, path: str = ()) -> None:
        import invesalius.constants as const
        debug("Session.SaveProject")
        if path:
            self.SetState('project_path', path)
            self._add_to_recent_projects(path)
        if self.temp_item:
            self.temp_item = False

        self.SetConfig('project_status', const.PROJECT_STATUS_OPENED)



    def ChangeProject(self) -> None:
        debug("Session.ChangeProject")
        self.SetConfig('project_status', const.PROJECT_STATUS_CHANGED)

    def CreateProject(self, filename: str) -> None:
        Publisher.sendMessage('Begin busy cursor')

        # Set session info
        tempdir = str(inv_paths.TEMP_DIR)

        project_path: Tuple[str, str] = (tempdir, filename)
        self.SetState('project_path', project_path)

        self.temp_item = True

        self.SetConfig('project_status', const.PROJECT_STATUS_NEW)

    def OpenProject(self, filepath: str) -> None:
        # Add item to recent projects list
        project_path: Tuple[str, str] = os.path.split(filepath)
        self._add_to_recent_projects(project_path)

        # Set session info
        self.SetState('project_path', project_path)
        self.SetConfig('project_status', const.PROJECT_STATUS_OPENED)

    def WriteConfigFile(self) -> None:
        self._write_to_json(self._config, CONFIG_PATH)

    def WriteStateFile(self) -> None:
        self._write_to_json(self._state, STATE_PATH)

    def _write_to_json(self, config_dict: Dict[str, Any], config_filename: str) -> None:
        with open(config_filename, 'w') as config_file:
            json.dump(config_dict, config_file, sort_keys=True, indent=4)

    def _add_to_recent_projects(self, item: Tuple[str, str]) -> None:
        # Recent projects list
        recent_projects: List[List[str]] = self.GetConfig('recent_projects')
        item = list(item)

        # If item exists, remove it from list
        if recent_projects.count(item):
            recent_projects.remove(item)

        # Add new item
        recent_projects.insert(0, item)
        self.SetConfig('recent_projects', recent_projects[:const.RECENT_PROJECTS_MAXIMUM])

    def _read_config_from_json(self, json_filename: str) -> None:
        with open(json_filename, 'r') as config_file:
            config_dict: Dict[str, Any] = json.load(config_file)
            self._config = deep_merge_dict(self._config.copy(), config_dict)

        # Do not reading project status from the config file, since there
        # isn't a recover session tool in InVesalius yet.
        self.project_status = 3

    def _read_config_from_ini(self, config_filename: str) -> None:
        file = codecs.open(config_filename, 'rb', SESSION_ENCODING)
        config = ConfigParser.ConfigParser()
        config.readfp(file)
        file.close()

        mode: int = config.getint('session', 'mode')
        debug: bool = config.getboolean('session', 'debug')
        debug_efield: bool = config.getboolean('session','debug_efield')
        language: str = config.get('session','language')
        last_dicom_folder: str = config.get('paths','last_dicom_folder') 
        project_status: int = config.getint('session', 'status')
        surface_interpolation: int = config.getint('session', 'surface_interpolation')
        slice_interpolation: int = config.getint('session', 'slice_interpolation')
        rendering: int = config.getint('session', 'rendering')
        random_id: int = config.getint('session','random_id')

        recent_projects = eval(config.get('project','recent_projects'))
        recent_projects: list[list[Any]] = [list(rp) for rp in recent_projects]

        self.SetConfig('mode', mode)
        self.SetConfig('debug', debug)
        self.SetConfig('debug_efield', debug_efield)
        self.SetConfig('language', language)
        self.SetConfig('last_dicom_folder', last_dicom_folder)
        self.SetConfig('surface_interpolation', surface_interpolation)
        self.SetConfig('slice_interpolation', slice_interpolation)
        self.SetConfig('rendering', rendering)
        self.SetConfig('random_id', random_id)
        self.SetConfig('recent_projects', recent_projects)

        # Do not update project status from the config file, since there
        # isn't a recover session tool in InVesalius
        #self.SetConfig('project_status', project_status)

        #  if not(sys.platform == 'win32'):
            #  self.SetConfig('last_dicom_folder', last_dicom_folder.decode('utf-8'))

    # TODO: Make also this function private so that it is run when the class constructor is run.
    #   (Compare to _ReadState below.)
    def ReadConfig(self) -> bool:
        try:
            self._read_config_from_json(CONFIG_PATH)
        except Exception as e1:
            debug(e1)
            try:
                self._read_config_from_ini(OLD_CONFIG_PATH)
            except Exception as e2:
                debug(e2)
                return False
        self.WriteConfigFile()
        return True

    def _ReadState(self) -> bool:
        success = False
        if os.path.exists(STATE_PATH):
            print("Restoring a previous state...")

            state_file = open(STATE_PATH, 'r')
            try:
                self._state = json.load(state_file)
                success = True

            except JSONDecodeError as e:
                print("State file is corrupted. Deleting...")

                state_file.close()
                self.DeleteStateFile()

        if not success:
            self._state = {}

        return success

    # Exit-related functions

    def StoreSessionDialog(self) -> bool:
        msg = _("Would you like to store the session?")
        if sys.platform == 'darwin':
            dialog = wx.MessageDialog(None, "", msg,
                                        wx.ICON_QUESTION | wx.YES_NO)
        else:
            dialog = wx.MessageDialog(None, msg, "InVesalius 3",
                                        wx.ICON_QUESTION | wx.YES_NO)

        answer = dialog.ShowModal()
        dialog.Destroy()

        return answer == wx.ID_YES

    def _Exit(self) -> None:
        if not self.StoreSessionDialog():
            self.CloseProject()
            self.DeleteStateFile()
