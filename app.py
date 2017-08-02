#!/usr/bin/python
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


import multiprocessing
import optparse as op
import os
import sys
import shutil

if sys.platform == 'win32':
    import _winreg
else:
    if sys.platform != 'darwin':
        import wxversion
        #wxversion.ensureMinimal('2.8-unicode', optionsRequired=True)
        #wxversion.select('2.8-unicode', optionsRequired=True)
        wxversion.ensureMinimal('3.0')
        
import wx
#from wx.lib.pubsub import setupv1 #new wx
from wx.lib.pubsub import setuparg1# as psv1
#from wx.lib.pubsub import Publisher 
#import wx.lib.pubsub as ps
from wx.lib.pubsub import pub as Publisher

#import wx.lib.agw.advancedsplash as agw
#if sys.platform == 'linux2':
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
        USER_DIR = os.path.expanduser('~').decode(FS_ENCODE)
else:
    USER_DIR = os.path.expanduser('~').decode(FS_ENCODE)

USER_INV_DIR = os.path.join(USER_DIR, u'.invesalius')
USER_PRESET_DIR = os.path.join(USER_INV_DIR, u'presets')
USER_RAYCASTING_PRESETS_DIRECTORY = os.path.join(USER_PRESET_DIR, u'raycasting')
USER_LOG_DIR = os.path.join(USER_INV_DIR, u'logs')

# ------------------------------------------------------------------


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
        self.splash = SplashScreen()
        self.splash.Show()
        wx.CallLater(1000,self.Startup2)

        return True

    def MacOpenFile(self, filename):
        """
        Open drag & drop files under darwin
        """
        path = os.path.abspath(filename)
        Publisher.sendMessage('Open project', path)

    def Startup2(self):
        self.control = self.splash.control
        self.frame = self.splash.main
        self.SetTopWindow(self.frame)
        self.frame.Show()
        self.frame.Raise()

# ------------------------------------------------------------------

class SplashScreen(wx.SplashScreen):
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
            print "LANG", lang, _, wx.Locale(), wx.GetLocale()
            import locale
            locale.setlocale(locale.LC_ALL, '')
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

            style = wx.SPLASH_TIMEOUT | wx.SPLASH_CENTRE_ON_SCREEN
            wx.SplashScreen.__init__(self,
                                     bitmap=bmp,
                                     splashStyle=style,
                                     milliseconds=1500,
                                     id=-1,
                                     parent=None)
            self.Bind(wx.EVT_CLOSE, self.OnClose)
            wx.Yield()
            wx.CallLater(200,self.Startup)

    def Startup(self):
        # Importing takes sometime, therefore it will be done
        # while splash is being shown
        from invesalius.gui.frame import Frame
        from invesalius.control import Controller
        from invesalius.project import Project
        
        self.main = Frame(None)
        self.control = Controller(self.main)
        
        self.fc = wx.FutureCall(1, self.ShowMain)
        wx.FutureCall(1, parse_comand_line)

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

    # -i or --import: import DICOM directory
    # chooses largest series
    parser.add_option("-i", "--import",
                      action="store",
                      dest="dicom_dir")
    options, args = parser.parse_args()

    # If debug argument...
    if options.debug:
        Publisher.subscribe(print_events, Publisher.ALL_TOPICS)
        session.debug = 1

    # If import DICOM argument...
    if options.dicom_dir:
        import_dir = options.dicom_dir
        Publisher.sendMessage('Import directory', import_dir)
        return True

    # Check if there is a file path somewhere in what the user wrote
    # In case there is, try opening as it was a inv3
    else:
        i = len(args)
        while i:
            i -= 1
            file = args[i]
            if os.path.isfile(file):
                path = os.path.abspath(file)
                Publisher.sendMessage('Open project', path)
                i = 0
                return True
    return False


def print_events(data):
    """
    Print pubsub messages
    """
    utils.debug(data.topic)

def main():
    """
    Initialize InVesalius GUI
    """
    application = InVesalius(0)
    application.MainLoop()

if __name__ == '__main__':
    #Is needed because of pyinstaller
    multiprocessing.freeze_support()
    
    #Needed in win 32 exe
    if hasattr(sys,"frozen") and sys.platform.startswith('win'):

        #Click in the .inv3 file support
        root = _winreg.HKEY_CLASSES_ROOT
        key = "InVesalius 3.1\InstallationDir"
        hKey = _winreg.OpenKey (root, key, 0, _winreg.KEY_READ)
        value, type_ = _winreg.QueryValueEx (hKey, "")
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

