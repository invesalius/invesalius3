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
USER_INV_CFG_PATH = os.path.join(USER_INV_DIR, 'config.cfg')

SESSION_ENCODING = 'utf8'


# Only one session will be initialized per time. Therefore, we use
# Singleton design pattern for implementing it
class Session(with_metaclass(Singleton, object)):

    def __init__(self):
        self.temp_item = False
        # Initializing as project status closed.
        # TODO: A better way to initialize project_status as closed (3)
        self.project_status = 3

    def CreateItens(self):
        import invesalius.constants as const
        self.project_path = ()
        self.debug = False
        self.project_status = const.PROJ_CLOSE
        # const.PROJ_NEW*, const.PROJ_OPEN, const.PROJ_CHANGE*,
        # const.PROJ_CLOSE

        self.mode = const.MODE_RP
        # const.MODE_RP, const.MODE_NAVIGATOR, const.MODE_RADIOLOGY,
        # const.MODE_ODONTOLOGY

        # InVesalius default projects' directory
        homedir = self.homedir = USER_DIR
        tempdir = os.path.join(homedir, u".invesalius", u"temp")
        if not os.path.isdir(tempdir):
            os.makedirs(tempdir)
        self.tempdir = tempdir

        # GUI language
        self.language = "" # "pt_BR", "es"

        self.random_id = randint(0,pow(10,16))

        # Recent projects list
        self.recent_projects = [(const.SAMPLE_DIR, u"Cranium.inv3")]
        self.last_dicom_folder = ''
        self.surface_interpolation = 1
        self.slice_interpolation = 0
        self.rendering = 0
        self.WriteSessionFile()

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
        config = ConfigParser.RawConfigParser()

        config.add_section('session')
        config.set('session', 'mode', self.mode)
        config.set('session', 'status', self.project_status)
        config.set('session','debug', self.debug)
        config.set('session', 'language', self.language)
        config.set('session', 'random_id', self.random_id)
        config.set('session', 'surface_interpolation', self.surface_interpolation)
        config.set('session', 'rendering', self.rendering)
        config.set('session', 'slice_interpolation', self.slice_interpolation)

        config.add_section('project')
        config.set('project', 'recent_projects', self.recent_projects)

        config.add_section('paths')
        config.set('paths','homedir',self.homedir)
        config.set('paths','tempdir',self.tempdir)
        config.set('paths','last_dicom_folder',self.last_dicom_folder)

        path = os.path.join(self.homedir ,
                            '.invesalius', 'config.cfg')

        configfile = codecs.open(path, 'wb', SESSION_ENCODING)
        try:
            config.write(configfile)
        except UnicodeDecodeError:
            pass
        configfile.close()

    def __add_to_list(self, item):
        import invesalius.constants as const
        # Last projects list
        l = self.recent_projects

        # If item exists, remove it from list
        if l.count(item):
            l.remove(item)

        # Add new item
        l.insert(0, item)

        # Remove oldest projects from list
        if len(l)>const.PROJ_MAX:
            for i in xrange(len(l)-const.PROJ_MAX):
                l.pop()

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

    def ReadLanguage(self):
        config = ConfigParser.ConfigParser()
        path = os.path.join(USER_INV_DIR, 'config.cfg')
        try:
            f = codecs.open(path, 'rb', SESSION_ENCODING)
            config.readfp(f)
            f.close()
            self.language = config.get('session','language')
            return self.language
        except IOError:
            return False
        except (ConfigParser.NoSectionError,
                  ConfigParser.NoOptionError,
                  ConfigParser.MissingSectionHeaderError):
            return False

    def ReadRandomId(self):
        config = ConfigParser.ConfigParser()
        path = os.path.join(USER_INV_DIR, 'config.cfg')
        try:
            f = codecs.open(path, 'rb', SESSION_ENCODING)
            config.readfp(f)
            f.close()
            self.random_id = config.get('session','random_id')
            return self.random_id
        except IOError:
            return False
        except (ConfigParser.NoSectionError,
                  ConfigParser.NoOptionError,
                  ConfigParser.MissingSectionHeaderError):
            return False

    def ReadSession(self):
        config = ConfigParser.ConfigParser()
        path = USER_INV_CFG_PATH
        try:
            f = codecs.open(path, 'rb', SESSION_ENCODING)
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

            #if not(sys.platform == 'win32'):
            #    self.last_dicom_folder = self.last_dicom_folder.decode('utf-8')

            self.surface_interpolation = config.get('session', 'surface_interpolation')
            self.slice_interpolation = config.get('session', 'slice_interpolation')

            self.rendering = config.get('session', 'rendering')
            self.random_id = config.get('session','random_id')
            return True

        except IOError:
            return False

        except(ConfigParser.NoSectionError, ConfigParser.MissingSectionHeaderError, 
                                                        ConfigParser.ParsingError):

            if (self.RecoveryConfigFile()):
                self.ReadSession()
                return True
            else:
                return False

        except(ConfigParser.NoOptionError):
            #Added to fix new version compatibility
            self.surface_interpolation = 0
            self.slice_interpolation = 0
            self.rendering = 0
            self.random_id = randint(0,pow(10,16))  
            try:
                self.WriteSessionFile()
            except AttributeError:
                return False
            return True
