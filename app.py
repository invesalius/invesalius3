#!/usr/bin/env python3
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
#-------------------------------------------------------------------------

from __future__ import print_function

import multiprocessing
import optparse as op
import os
import sys
import shutil
import traceback

import re

if sys.platform == 'win32':
    try:
        import winreg
    except ImportError:
        import _winreg as winreg
#  else:
    #  if sys.platform != 'darwin':
        #  import wxversion
        #  #wxversion.ensureMinimal('2.8-unicode', optionsRequired=True)
        #  #wxversion.select('2.8-unicode', optionsRequired=True)
        #  #  wxversion.ensureMinimal('4.0')
        
import wx
try:
    from wx.adv import SplashScreen
except ImportError:
    from wx import SplashScreen
#from wx.lib.pubsub import setupv1 #new wx
#  from wx.lib.pubsub import setuparg1# as psv1
#from wx.lib.pubsub import Publisher 
#import wx.lib.pubsub as ps
from wx.lib.pubsub import pub as Publisher

#import wx.lib.agw.advancedsplash as agw
#if sys.platform.startswith('linux'):
#    _SplashScreen = agw.AdvancedSplash
#else:
#    if sys.platform != 'darwin':
#        _SplashScreen = wx.SplashScreen


import invesalius.gui.language_dialog as lang_dlg
import invesalius.i18n as i18n
import invesalius.session as ses
import invesalius.utils as utils

FS_ENCODE = sys.getfilesystemencoding()

if sys.platform == 'win32':
    from invesalius.expanduser import expand_user
    try:
        USER_DIR = expand_user()
    except:
        USER_DIR = utils.decode(os.path.expanduser('~'), FS_ENCODE)
else:
    USER_DIR = utils.decode(os.path.expanduser('~'),FS_ENCODE)

USER_INV_DIR = os.path.join(USER_DIR, u'.invesalius')
USER_PRESET_DIR = os.path.join(USER_INV_DIR, u'presets')
USER_RAYCASTING_PRESETS_DIRECTORY = os.path.join(USER_PRESET_DIR, u'raycasting')
USER_LOG_DIR = os.path.join(USER_INV_DIR, u'logs')

# ------------------------------------------------------------------

if sys.platform in ('linux2', 'linux', 'win32'):
    try:
        tmp_var = wx.GetXDisplay
    except AttributeError:
        # A workaround to make InVesalius run with wxPython4 from Ubuntu 18.04
        wx.GetXDisplay = lambda: None
    else:
        del tmp_var


class InVesalius(wx.App):
    """
    InVesalius wxPython application class.
    """
    def OnInit(self):
        """
        Initialize splash screen and main frame.
        """
        
        from multiprocessing import freeze_support
        freeze_support()

        self.SetAppName("InVesalius 3")
        self.splash = Inv3SplashScreen()
        self.splash.Show()
        wx.CallLater(1000,self.Startup2)

        return True

    def MacOpenFile(self, filename):
        """
        Open drag & drop files under darwin
        """
        path = os.path.abspath(filename)
        Publisher.sendMessage('Open project', filepath=path)

    def Startup2(self):
        self.control = self.splash.control
        self.frame = self.splash.main
        self.SetTopWindow(self.frame)
        self.frame.Show()
        self.frame.Raise()

# ------------------------------------------------------------------

class Inv3SplashScreen(SplashScreen):
    """
    Splash screen to be shown in InVesalius initialization.
    """
    def __init__(self):
        # Splash screen image will depend on currently language
        lang = False

        self.locale = wx.Locale(wx.LANGUAGE_DEFAULT)

        # Language information is available in session configuration
        # file. First we need to check if this file exist, if now, it
        # should be created
        create_session = False
        session = ses.Session()
        if not (session.ReadSession()):
            create_session = True

        install_lang = 0
        # Check if there is a language set (if session file exists
        if session.ReadLanguage():
            lang = session.GetLanguage()
            if (lang != "False"):
                _ = i18n.InstallLanguage(lang)
                install_lang = 1
            else:
                install_lang = 0
        else:
            install_lang = 0

        # If no language is set into session file, show dialog so
        # user can select language
        if install_lang == 0:
            dialog = lang_dlg.LanguageDialog()

            # FIXME: This works ok in linux2, darwin and win32,
            # except on win64, due to wxWidgets bug
            try:
                ok = (dialog.ShowModal() == wx.ID_OK)
            except wx._core.PyAssertionError:
                ok = True
            finally:
                if ok:
                    lang = dialog.GetSelectedLanguage()
                    session.SetLanguage(lang)
                    _ = i18n.InstallLanguage(lang)
                else:
                    homedir = self.homedir = os.path.expanduser('~')
                    invdir = os.path.join(homedir, ".invesalius")
                    shutil.rmtree(invdir)
                    sys.exit()
                    
        # Session file should be created... So we set the recent
        # choosen language
        if (create_session):
            session.CreateItens()
            session.SetLanguage(lang)
            session.WriteSessionFile()

        session.SaveConfigFileBackup()

           
        # Only after language was defined, splash screen will be
        # shown
        if lang:
            #  print "LANG", lang, _, wx.Locale(), wx.GetLocale()
            import locale
            try:
                locale.setlocale(locale.LC_ALL, '')
            except locale.Error:
                pass
            # For pt_BR, splash_pt.png should be used
            if (lang.startswith('pt')):
                icon_file = "splash_pt.png"
            else:
                icon_file = "splash_" + lang + ".png"

            if hasattr(sys,"frozen") and (sys.frozen == "windows_exe"\
                                        or sys.frozen == "console_exe"):
                abs_file_path = os.path.abspath(".." + os.sep)
                path = abs_file_path
                path = os.path.join(path, 'icons', icon_file)
            
            else:

                path = os.path.join(".","icons", icon_file)
                if not os.path.exists(path):
                    path = os.path.join(".", "icons", "splash_en.png")
				
            bmp = wx.Image(path).ConvertToBitmap()

            try:
                style = wx.adv.SPLASH_TIMEOUT | wx.adv.SPLASH_CENTRE_ON_SCREEN
            except AttributeError:
                style = wx.SPLASH_TIMEOUT | wx.SPLASH_CENTRE_ON_SCREEN

            SplashScreen.__init__(self,
                                  bitmap=bmp,
                                  splashStyle=style,
                                  milliseconds=1500,
                                  id=-1,
                                  parent=None)
            self.Bind(wx.EVT_CLOSE, self.OnClose)
            wx.Yield()
            wx.CallLater(200, self.Startup)

    def Startup(self):
        # Importing takes sometime, therefore it will be done
        # while splash is being shown
        from invesalius.gui.frame import Frame
        from invesalius.control import Controller
        from invesalius.project import Project
        
        self.main = Frame(None)
        self.control = Controller(self.main)
        
        self.fc = wx.FutureCall(1, self.ShowMain)
        options, args = parse_comand_line()
        wx.FutureCall(1, use_cmd_optargs, options, args)

        # Check for updates
        from threading import Thread
        p = Thread(target=utils.UpdateCheck, args=())
        p.start()

    def OnClose(self, evt):
        # Make sure the default handler runs too so this window gets
        # destroyed
        evt.Skip()
        self.Hide()

        # If the timer is still running then go ahead and show the
        # main frame now
        if self.fc.IsRunning():
            self.fc.Stop()
            self.ShowMain()

    def ShowMain(self):
        # Show main frame
        self.main.Show()

        if self.fc.IsRunning():
            self.Raise()


def non_gui_startup(options, args):
    lang = 'en'
    _ = i18n.InstallLanguage(lang)

    from invesalius.control import Controller
    from invesalius.project import Project

    session = ses.Session()
    if not session.ReadSession():
        session.CreateItens()
        session.SetLanguage(lang)
        session.WriteSessionFile()

    control = Controller(None)

    use_cmd_optargs(options, args)

# ------------------------------------------------------------------


def parse_comand_line():
    """
    Handle command line arguments.
    """
    session = ses.Session()


    # Parse command line arguments
    parser = op.OptionParser()

    # -d or --debug: print all pubsub messagessent
    parser.add_option("-d", "--debug",
                      action="store_true",
                      dest="debug")

    parser.add_option('--no-gui',
                      action='store_true',
                      dest='no_gui')

    # -i or --import: import DICOM directory
    # chooses largest series
    parser.add_option("-i", "--import",
                      action="store",
                      dest="dicom_dir")

    parser.add_option("--import-all",
                      action="store")

    parser.add_option("-s", "--save",
                      help="Save the project after an import.")

    parser.add_option("-t", "--threshold",
                      help="Define the threshold for the export (e.g. 100-780).")

    parser.add_option("-e", "--export",
                      help="Export to STL.")

    parser.add_option("-a", "--export-to-all",
                      help="Export to STL for all mask presets.")

    options, args = parser.parse_args()
    return options, args


def use_cmd_optargs(options, args):
    # If debug argument...
    if options.debug:
        Publisher.subscribe(print_events, Publisher.ALL_TOPICS)
        session = ses.Session()
        session.debug = 1

    # If import DICOM argument...
    if options.dicom_dir:
        import_dir = options.dicom_dir
        Publisher.sendMessage('Import directory', directory=import_dir, use_gui=not options.no_gui)

        if options.save:
            Publisher.sendMessage('Save project', filepath=os.path.abspath(options.save))
            exit(0)

        check_for_export(options)

        return True
    elif options.import_all:
        import invesalius.reader.dicom_reader as dcm
        for patient in dcm.GetDicomGroups(options.import_all):
            for group in patient.GetGroups():
                Publisher.sendMessage('Import group',
                                      group=group,
                                      use_gui=not options.no_gui)
                check_for_export(options, suffix=group.title, remove_surfaces=False)
                Publisher.sendMessage('Remove masks', mask_indexes=(0,))
        return True

    # Check if there is a file path somewhere in what the user wrote
    # In case there is, try opening as it was a inv3
    else:
        for arg in reversed(args):

            file = utils.decode(arg, FS_ENCODE)
            if os.path.isfile(file):
                path = os.path.abspath(file)
                Publisher.sendMessage('Open project', filepath=path)
                check_for_export(options)
                return True

            file = utils.decode(arg, sys.stdin.encoding)
            if os.path.isfile(file):
                path = os.path.abspath(file)
                Publisher.sendMessage('Open project', filepath=path)
                check_for_export(options)
                return True

    return False


def sanitize(text):
    text = str(text).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', text)


def check_for_export(options, suffix='', remove_surfaces=False):
    suffix = sanitize(suffix)

    if options.export:
        if not options.threshold:
            print("Need option --threshold when using --export.")
            exit(1)
        threshold_range = tuple([int(n) for n in options.threshold.split(',')])

        if suffix:
            if options.export.endswith('.stl'):
                path_ = '{}-{}.stl'.format(options.export[:-4], suffix)
            else:
                path_ = '{}-{}.stl'.format(options.export, suffix)
        else:
            path_ = options.export

        export(path_, threshold_range, remove_surface=remove_surfaces)
    elif options.export_to_all:
        # noinspection PyBroadException
        try:
            from invesalius.project import Project

            for threshold_name, threshold_range in Project().presets.thresh_ct.iteritems():
                if isinstance(threshold_range[0], int):
                    path_ = u'{}-{}-{}.stl'.format(options.export_to_all, suffix, threshold_name)
                    export(path_, threshold_range, remove_surface=True)
        except:
            traceback.print_exc()
        finally:
            exit(0)


def export(path_, threshold_range, remove_surface=False):
    import invesalius.constants as const

    Publisher.sendMessage('Set threshold values',
                          threshold_range=threshold_range)

    surface_options = {
        'method': {
            'algorithm': 'Default',
            'options': {},
        }, 'options': {
            'index': 0,
            'name': '',
            'quality': _('Optimal *'),
            'fill': False,
            'keep_largest': False,
            'overwrite': False,
        }
    }
    Publisher.sendMessage('Create surface from index',
                          surface_parameters=surface_options)
    Publisher.sendMessage('Export surface to file',
                          filename=path_, filetype=const.FILETYPE_STL)
    if remove_surface:
        Publisher.sendMessage('Remove surfaces',
                              surface_indexes=(0,))


def print_events(topic=Publisher.AUTO_TOPIC, **msg_data):
    """
    Print pubsub messages
    """
    utils.debug("%s\n\tParameters: %s" % (topic, msg_data))

def main():
    """
    Initialize InVesalius GUI
    """
    options, args = parse_comand_line()

    if options.no_gui:
        non_gui_startup(options, args)
    else:
        application = InVesalius(0)
        application.MainLoop()

if __name__ == '__main__':
    #Is needed because of pyinstaller
    multiprocessing.freeze_support()
    
    #Needed in win 32 exe
    if hasattr(sys,"frozen") and sys.platform.startswith('win'):

        #Click in the .inv3 file support
        root = winreg.HKEY_CLASSES_ROOT
        key = "InVesalius 3.1\InstallationDir"
        hKey = winreg.OpenKey (root, key, 0, winreg.KEY_READ)
        value, type_ = winreg.QueryValueEx (hKey, "")
        path = os.path.join(value,'dist')

        os.chdir(path)

    # Create raycasting presets' folder, if it doens't exist
    if not os.path.isdir(USER_RAYCASTING_PRESETS_DIRECTORY):
        os.makedirs(USER_RAYCASTING_PRESETS_DIRECTORY)

    # Create logs' folder, if it doesn't exist
    if not os.path.isdir(USER_LOG_DIR):
        os.makedirs(USER_LOG_DIR)

    if hasattr(sys,"frozen") and sys.frozen == "windows_exe":
        # Set system standard error output to file
        path = os.path.join(USER_LOG_DIR, u"stderr.log")
        sys.stderr = open(path, "w")

    # Add current directory to PYTHONPATH, so other classes can
    # import modules as they were on root invesalius folder
    sys.path.insert(0, '.')
    sys.path.append(".")


    # Init application
    main()

