import ConfigParser
import os
from threading import Thread
import time

import wx.lib.pubsub as ps

from utils import Singleton, debug

class Session(object):
    # Only one session will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton

    def __init__(self):
        self.temp_item = False

        ws = self.ws = WriteSession(self)
        ws.start()
        ps.Publisher().subscribe(self.StopRecording, "Stop Config Recording")

    def CreateItens(self):
        import constants as const
        self.project_path = ()
        self.debug = False

        self.project_status = const.PROJ_CLOSE
        # const.PROJ_NEW*, const.PROJ_OPEN, const.PROJ_CHANGE*,
        # const.PROJ_CLOSE

        self.mode = const.MODE_RP
        # const.MODE_RP, const.MODE_NAVIGATOR, const.MODE_RADIOLOGY,
        # const.MODE_ODONTOLOGY

        # InVesalius default projects' directory
        homedir = self.homedir = os.path.expanduser('~')
        tempdir = os.path.join(homedir, ".invesalius", "temp")
        if not os.path.isdir(tempdir):
            os.makedirs(tempdir)
        self.tempdir = tempdir

        # GUI language
        self.language = "" # "pt_BR", "es"

        # Recent projects list
        self.recent_projects = [(const.SAMPLE_DIR, "Cranium.inv3")]
        self.last_dicom_folder = ''

        self.CreateSessionFile()

    def StopRecording(self, pubsub_evt):
        self.ws.Stop()


    def CloseProject(self):
        import constants as const
        debug("Session.CloseProject")
        self.project_path = ()
        self.project_status = const.PROJ_CLOSE
        self.mode = const.MODE_RP
        self.temp_item = False

    def SaveProject(self, path=()):
        import constants as const
        debug("Session.SaveProject")
        self.project_status = const.PROJ_OPEN
        if path:
            self.project_path = path
            self.__add_to_list(path)
        if self.temp_item:
            self.temp_item = False

    def ChangeProject(self):
        import constants as const
        debug("Session.ChangeProject")
        self.project_status = const.PROJ_CHANGE

    def CreateProject(self, filename):
        import constants as const
        debug("Session.CreateProject")
        ps.Publisher().sendMessage('Begin busy cursor')
        # Set session info
        self.project_path = (self.tempdir, filename)
        self.project_status = const.PROJ_NEW
        self.temp_item = True
        return self.tempdir

    def OpenProject(self, filepath):
        import constants as const
        debug("Session.OpenProject")
        # Add item to recent projects list
        item = (path, file) = os.path.split(filepath)
        self.__add_to_list(item)

        # Set session info
        self.project_path = item
        self.project_status = const.PROJ_OPEN

    def RemoveTemp(self):
        if self.temp_item:
            (dirpath, file) = self.project_path
            path = os.path.join(dirpath, file)
            os.remove(path)
            self.temp_item = False

    def CreateSessionFile(self):

        config = ConfigParser.RawConfigParser()

        config.add_section('session')
        config.set('session', 'mode', self.mode)
        config.set('session', 'status', self.project_status)
        config.set('session','debug', self.debug)
        config.set('session', 'language', self.language)

        config.add_section('project')
        config.set('project', 'recent_projects', self.recent_projects)

        config.add_section('paths')
        config.set('paths','homedir',self.homedir)
        config.set('paths','tempdir',self.tempdir)
        config.set('paths','last_dicom_folder',self.last_dicom_folder)
        path = os.path.join(self.homedir ,
                            '.invesalius', 'config.cfg')
        configfile = open(path, 'wb')
        config.write(configfile)
        configfile.close()


    def __add_to_list(self, item):
        import constants as const
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

    def SavePlist(self):
        filename = 'session.conf'
        filepath = os.join(self.tempdir, filename)
        plistlib.writePlist(self.__dict__, filepath)

    def OpenPlist(self):
        filename = 'session.conf'
        filepath = os.join(self.tempdir, filename)
        # TODO: try/except
        dict = plistlib.readPlist(main_plist)
        for key in dict:
            setattr(self, key, dict[key])

    def GetLanguage(self):
        return self.language

    def SetLanguage(self, language):
        self.language = language

    def GetLastDicomFolder(self):
        return self.last_dicom_folder

    def SetLastDicomFolder(self, folder):
        self.last_dicom_folder = folder
        self.CreateSessionFile()

    def ReadLanguage(self):
        config = ConfigParser.ConfigParser()
        home_path = os.path.expanduser('~')
        path = os.path.join(home_path ,'.invesalius', 'config.cfg')
        try:
            config.read(path)
            self.language = config.get('session','language')
            return self.language
        except(ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return False

    def ReadSession(self):

        config = ConfigParser.ConfigParser()
        home_path = os.path.expanduser('~')
        path = os.path.join(home_path ,'.invesalius', 'config.cfg')
        try:
            config.read(path)
            self.mode = config.get('session', 'mode')
            self.project_status = config.get('session', 'status')
            self.debug = config.get('session','debug')
            self.language = config.get('session','language')
            self.recent_projects = eval(config.get('project','recent_projects'))
            self.homedir = config.get('paths','homedir')
            self.tempdir = config.get('paths','tempdir')
            self.last_dicom_folder = config.get('paths','last_dicom_folder')
            return True
        except(ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return False


class WriteSession(Thread):

    def __init__ (self, session):
      Thread.__init__(self)
      self.session = session
      self.runing = 1

    def run(self):
      while self.runing:
        time.sleep(10)
        try:
            self.Write()
        except AttributeError:
            pass

    def Stop(self):
        self.runing = 0

    def Write(self):

        config = ConfigParser.RawConfigParser()

        config.add_section('session')
        config.set('session', 'mode', self.session.mode)
        config.set('session', 'status', self.session.project_status)
        config.set('session','debug', self.session.debug)
        config.set('session', 'language', self.session.language)

        config.add_section('project')
        config.set('project', 'recent_projects', self.session.recent_projects)

        config.add_section('paths')
        config.set('paths','homedir',self.session.homedir)
        config.set('paths','tempdir',self.session.tempdir)
        config.set('paths','last_dicom_folder', self.session.last_dicom_folder)

        path = os.path.join(self.session.homedir ,
                            '.invesalius', 'config.cfg')
        configfile = open(path, 'wb')
        config.write(configfile)
        configfile.close()




