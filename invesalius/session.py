import os

import constants as const
from utils import Singleton

class Session(object):
    # Only one session will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton

    def __init__(self):
        self.project_path = ()
        self.debug = False

        self.project_status = const.PROJ_CLOSE
        # const.PROJ_NEW*, const.PROJ_OPEN, const.PROJ_CHANGE*,
        # const.PROJ_CLOSE

        self.mode = const.MODE_RP
        # const.MODE_RP, const.MODE_NAVIGATOR, const.MODE_RADIOLOGY,
        # const.MODE_ODONTOLOGY

        # InVesalius default projects' directory
        homedir = os.path.expanduser('~')
        invdir = os.path.join(homedir, ".invesalius", "temp")
        if not os.path.isdir(invdir):
            os.makedirs(invdir)
        self.invdir = invdir

        self.temp_item = False

        # Recent projects list
        self.recent_projects = []

        # GUI language
        self.language = "en_GB" # "pt_BR", "es"

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
