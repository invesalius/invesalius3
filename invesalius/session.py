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

from six import with_metaclass

try:
    import configparser as ConfigParser
except(ImportError):
    import ConfigParser

import os
import shutil
import sys
from threading import Thread
import time
import codecs
import collections
import json

#import wx.lib.pubsub as ps
from wx.lib.pubsub import pub as Publisher
import wx

from invesalius.utils import Singleton, debug, decode
from random import randint

FS_ENCODE = sys.getfilesystemencoding()

if sys.platform == 'win32':
    from invesalius.expanduser import expand_user
    try:
        USER_DIR = expand_user()
    except:
        USER_DIR = decode(os.path.expanduser('~'), FS_ENCODE)
else:
    USER_DIR = decode(os.path.expanduser('~'), FS_ENCODE)

USER_INV_DIR = os.path.join(USER_DIR, u'.invesalius')
USER_PRESET_DIR = os.path.join(USER_INV_DIR, u'presets')
USER_LOG_DIR = os.path.join(USER_INV_DIR, u'logs')
USER_INV_CFG_PATH = os.path.join(USER_INV_DIR, 'config.json')
OLD_USER_INV_CFG_PATH = os.path.join(USER_INV_DIR, 'config.cfg')

SESSION_ENCODING = 'utf8'


# Only one session will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Session(with_metaclass(Singleton, object)):

    def __init__(self):
        self.project_path = ()
        self.temp_item = False

        self._values = {
            'session': {
                'status': 3,
                'language': '',
            },
            'project': {
            },

            'paths': {
            }
        }

        self._map_attrs = {
            'mode': ('session', 'mode'),
            'project_status': ('session', 'status'),
            'debug': ('session', 'debug'),
            'language': ('session', 'language'),
            'random_id': ('session', 'random_id'),
            'surface_interpolation': ('session', 'surface_interpolation'),
            'rendering': ('session', 'rendering'),
            'slice_interpolation': ('session', 'slice_interpolation'),
            'recent_projects': ('project', 'recent_projects'),
            'homedir': ('paths', 'homedir'),
            'tempdir': ('paths', 'homedir'),
            'last_dicom_folder': ('paths', 'last_dicom_folder'),
        }


    def CreateItens(self):
        import invesalius.constants as const
        homedir = USER_DIR
        tempdir = os.path.join(USER_DIR, u".invesalius", u"temp")
        if not os.path.isdir(tempdir):
            os.makedirs(tempdir)

        self._values = {
            'session': {
                'mode': const.MODE_RP,
                'status': const.PROJ_CLOSE,
                'debug': False,
                'language': "",
                'random_id': randint(0, pow(10,16)),
                'surface_interpolation': 1,
                'rendering': 0,
                'slice_interpolation': 0,
            },

            'project': {
                'recent_projects': [(const.SAMPLE_DIR, u"Cranium.inv3"), ],
            },

            'paths': {
                'homedir': USER_DIR,
                'tempdir': os.path.join(homedir, u".invesalius", u"temp"),
                'last_dicom_folder': '',
            },
        }

    def __contains__(self, key):
        return key in self._values

    def __getitem__(self, key):
        return self._values[key]

    def __setitem__(self, key, value):
        self._values[key] = value

    def __getattr__(self, name):
        map_attrs = object.__getattribute__(self, '_map_attrs')
        if name not in map_attrs:
            raise AttributeError(name)
        session, key = map_attrs[name]
        return object.__getattribute__(self, '_values')[session][key]

    def __setattr__(self, name, value):
        if name in ("temp_item", "_map_attrs", "_values", "project_path"):
            return object.__setattr__(self, name, value)
        else:
            session, key = self._map_attrs[name]
            self._values[session][key] = value

    def __str__(self):
        return self._values.__str__()

    def IsOpen(self):
        import invesalius.constants as const
        return self.project_status != const.PROJ_CLOSE

    def SaveConfigFileBackup(self):
        path = os.path.join(self.homedir ,
                            u'.invesalius', u'config.cfg')
        path_dst = os.path.join(self.homedir ,
                            u'.invesalius', u'config.backup')
        shutil.copy(path, path_dst)

    def RecoveryConfigFile(self):
        homedir = self.homedir = os.path.expanduser('~')
        try:
            path = os.path.join(self.homedir ,
                            u'.invesalius', u'config.backup')
            path_dst = os.path.join(self.homedir ,
                        u'.invesalius', u'config.cfg')
            shutil.copy(path, path_dst)
            return True
        except(IOError):
           return False

    def CloseProject(self):
        import invesalius.constants as const
        debug("Session.CloseProject")
        self.project_path = ()
        self.project_status = const.PROJ_CLOSE
        #self.mode = const.MODE_RP
        self.temp_item = False
        self.WriteSessionFile()

    def SaveProject(self, path=()):
        import invesalius.constants as const
        debug("Session.SaveProject")
        self.project_status = const.PROJ_OPEN
        if path:
            self.project_path = path
            self.__add_to_list(path)
        if self.temp_item:
            self.temp_item = False
        self.WriteSessionFile()

    def ChangeProject(self):
        import invesalius.constants as const
        debug("Session.ChangeProject")
        self.project_status = const.PROJ_CHANGE

    def CreateProject(self, filename):
        import invesalius.constants as const
        debug("Session.CreateProject")
        Publisher.sendMessage('Begin busy cursor')
        # Set session info
        self.project_path = (self.tempdir, filename)
        self.project_status = const.PROJ_NEW
        self.temp_item = True
        self.WriteSessionFile()
        return self.tempdir

    def OpenProject(self, filepath):
        import invesalius.constants as const
        debug("Session.OpenProject")
        # Add item to recent projects list
        item = (path, file) = os.path.split(filepath)
        self.__add_to_list(item)

        # Set session info
        self.project_path = item
        self.project_status = const.PROJ_OPEN
        self.WriteSessionFile()

    def RemoveTemp(self):
        if self.temp_item:
            (dirpath, file) = self.project_path
            path = os.path.join(dirpath, file)
            os.remove(path)
            self.temp_item = False

    def WriteSessionFile(self):
        self._write_to_json(self._values, USER_INV_CFG_PATH)
        #  config = ConfigParser.RawConfigParser()

        #  #  config.add_section('session')
        #  #  config.set('session', 'mode', self.mode)
        #  #  config.set('session', 'status', self.project_status)
        #  #  config.set('session','debug', self.debug)
        #  #  config.set('session', 'language', self.language)
        #  #  config.set('session', 'random_id', self.random_id)
        #  #  config.set('session', 'surface_interpolation', self.surface_interpolation)
        #  #  config.set('session', 'rendering', self.rendering)
        #  #  config.set('session', 'slice_interpolation', self.slice_interpolation)

        #  #  config.add_section('project')
        #  #  config.set('project', 'recent_projects', self.recent_projects)

        #  #  config.add_section('paths')
        #  #  config.set('paths','homedir',self.homedir)
        #  #  config.set('paths','tempdir',self.tempdir)
        #  #  config.set('paths','last_dicom_folder',self.last_dicom_folder)

        #  #  for key in self._values:
            #  #  config.add_section(key)
            #  #  for sub_key in self._values[key]:
                #  #  config.set(key, sub_key, self._values[key][sub_key])

        #  print(self._values)
        #  print(dir(self))
        #  #  config.update(self._values)
        #  self._update_cfg_from_dict(config, self._values)
        #  path = os.path.join(self.homedir ,
                            #  '.invesalius', 'config.cfg')

        #  configfile = codecs.open(path, 'wb', SESSION_ENCODING)
        #  try:
            #  config.write(configfile)
        #  except UnicodeDecodeError:
            #  print("ERROR")
        #  configfile.close()

    def _write_to_json(self, cfg_dict, cfg_filename):
        with open(cfg_filename, 'w') as cfg_file:
            json.dump(cfg_dict, cfg_file, sort_keys=True, indent=4)

    def __add_to_list(self, item):
        import invesalius.constants as const
        # Last projects list
        l = self.recent_projects
        item = list(item)

        # If item exists, remove it from list
        if l.count(item):
            l.remove(item)

        # Add new item
        l.insert(0, item)

        self.recent_projects = l[:const.PROJ_MAX]
        # Remove oldest projects from list
        #  if len(l)>const.PROJ_MAX:
            #  for i in range(len(l)-const.PROJ_MAX):
                #  l.pop()

    def GetLanguage(self):
        return self.language

    def SetLanguage(self, language):
        self.language = language

    def GetRandomId(self):
        return self.random_id

    def SetRandomId(self, random_id):
        self.random_id = random_id

    def GetLastDicomFolder(self):
        return self.last_dicom_folder

    def SetLastDicomFolder(self, folder):
        self.last_dicom_folder = folder
        self.WriteSessionFile()

    def _update_from_cfg_file(self, config):
        tmp_dict = {}
        for session in config:
            if config[session]:
                tmp_dict[session] = {}
                for key in config[session]:
                    if key == 'recent_projects':
                        tmp_dict[session][key] = eval(config[session][key])
                    else:
                        tmp_dict[session][key] = config[session][key]
        self._values.update(tmp_dict)

    def _update_cfg_from_dict(self, config, cfg_dict):
        for session in cfg_dict:
            if cfg_dict[session] and isinstance(cfg_dict[session], dict):
                config.add_section(session)
                for key in cfg_dict[session]:
                    config.set(session, key, cfg_dict[session][key])

    def _read_cfg_from_json(self, json_filename):
        with open(json_filename, 'r') as cfg_file:
            cfg_dict = json.load(cfg_file)
            self._values.update(cfg_dict)

    def _read_cfg_from_ini(self, cfg_filename):
        f = codecs.open(cfg_filename, 'rb', SESSION_ENCODING)
        config = ConfigParser.ConfigParser()
        config.readfp(f)
        f.close()

        self.mode = config.get('session', 'mode')
        # Do not reading project status from the config file, since there
        # isn't a recover sessession tool in InVesalius
        #self.project_status = int(config.get('session', 'status'))
        self.debug = config.get('session','debug')
        self.language = config.get('session','language')
        self.recent_projects = eval(config.get('project','recent_projects'))
        self.homedir = config.get('paths','homedir')
        self.tempdir = config.get('paths','tempdir')
        self.last_dicom_folder = config.get('paths','last_dicom_folder') 

        #  if not(sys.platform == 'win32'):
          #  self.last_dicom_folder = self.last_dicom_folder.decode('utf-8')

        self.surface_interpolation = config.get('session', 'surface_interpolation')
        self.slice_interpolation = config.get('session', 'slice_interpolation')

        self.rendering = config.get('session', 'rendering')
        self.random_id = config.get('session','random_id')

    def ReadSession(self):
        try:
            self._read_cfg_from_json(USER_INV_CFG_PATH)
        except Exception:
            try:
                self._read_cfg_from_ini(OLD_USER_INV_CFG_PATH)
            except Exception:
                return False

        self.WriteSessionFile()
        return True
