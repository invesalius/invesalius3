import ConfigParser
import os
from threading import Thread
import time
import wx.lib.pubsub as ps

import constants as const
from utils import Singleton

import wx.lib.pubsub as ps

class Session(object):
    # Only one session will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton

    def __init__(self):
        # ?
        self.temp_item = False
        
        ws = self.ws = WriteSession(self)
        ws.start()
        
        ps.Publisher().subscribe(self.StopRecording, "Stop Config Recording")
    
    def CreateItens(self):
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
        invdir = os.path.join(homedir, ".invesalius", "temp")
        if not os.path.isdir(invdir):
            os.makedirs(invdir)
        self.invdir = invdir
        
        # GUI language
        self.language = "" # "pt_BR", "es"
        
        # Recent projects list
        self.recent_projects = []
    
    def StopRecording(self, pubsub_evt):
        self.ws.Stop()


    def CloseProject(self):
        print "-- CloseProject"
        self.project_path = ()
        self.project_status = const.PROJ_CLOSE
        self.mode = const.MODE_RP
        self.temp_item = False

    def SaveProject(self, path=()):
        print "-- SaveProject"
        self.project_status = const.PROJ_OPEN
        if path:
            self.project_path = path
            self.__add_to_list(path)
        if self.temp_item:
            self.temp_item = False

    def ChangeProject(self):
        print "-- ChangeProject"
        self.project_status = const.PROJ_CHANGE

    def CreateProject(self, filename):
        print "-- CreateProject"
        # Set session info
        self.project_path = (self.invdir, filename)
        self.project_status = const.PROJ_NEW
        self.temp_item = True
        return self.invdir

    def OpenProject(self, filepath):
        print "-- OpenProject"
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


    def __add_to_list(self, item):
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
        filepath = os.join(self.invdir, filename)
        plistlib.writePlist(self.__dict__, filepath)

    def OpenPlist(self):
        filename = 'session.conf'
        filepath = os.join(self.invdir, filename)
        # TODO: try/except
        dict = plistlib.readPlist(main_plist)
        for key in dict:
            setattr(self, key, dict[key])
    
    def GetLanguage(self):
        return self.language
    
    def SetLanguage(self, language):
        self.language = language
    
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
            self.invdir = config.get('paths','invdir')
            return True
        except(ConfigParser.NoSectionError):
            return False
        
class WriteSession(Thread):
    
    def __init__ (self, session):
      Thread.__init__(self)
      self.session = session
      self.runing = 1
      
    def run(self):
      while self.runing:
        time.sleep(10)
        self.Write()
      
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
        config.set('paths','invdir',self.session.invdir)
        path = os.path.join(self.session.homedir ,
                            '.invesalius', 'config.cfg')
        configfile = open(path, 'wb')
        config.write(configfile)
        configfile.close()
       


    