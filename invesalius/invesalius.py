#!/usr/bin/env python2.6
# NOTE: #!/usr/local/bin/python simply will *not* work if python is not
# installed  in that exact location and, therefore, we're using the code
# above
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

if sys.platform == 'win32':
    import _winreg
else:
    import wxversion
    wxversion.ensureMinimal('2.8-unicode', optionsRequired=True)
    wxversion.select('2.8-unicode', optionsRequired=True)

import wx
import wx.lib.pubsub as ps
import wx.lib.agw.advancedsplash as agw
if sys.platform == 'linux2':
    _SplashScreen = agw.AdvancedSplash
else:
    _SplashScreen = wx.SplashScreen

import gui.language_dialog as lang_dlg
import i18n
import session as ses
import utils

# ------------------------------------------------------------------

class InVesalius(wx.App):
    """
    InVesalius wxPython application class.
    """
    def OnInit(self):
        """
        Initialize splash screen and main frame.
        """
        self.SetAppName("InVesalius 3")
        splash = SplashScreen()
        self.control = splash.control
        self.frame = splash.main
        splash.Show()
        return True

    def MacOpenFile(self, filename):
        """
        Open drag & drop files under darwin
        """
        path = os.path.abspath(filename)
        ps.Publisher().sendMessage('Open project', path)

# ------------------------------------------------------------------

class SplashScreen(_SplashScreen):
    """
    Splash screen to be shown in InVesalius initialization.
    """
    def __init__(self):
        # Splash screen image will depend on currently language
        lang = False

        # Language information is available in session configuration
        # file. First we need to check if this file exist, if now, it
        # should be created
        create_session = False
        session = ses.Session()
        if not (session.ReadSession()):
            create_session = True

        # Check if there is a language set (if session file exists
        language_exist = session.ReadLanguage()

        if language_exist:
            lang = session.GetLanguage()
            install = i18n.InstallLanguage(lang)
            if install:
                _ = install
            else:
    		    language_exist = False

        # If no language is set into session file, show dialog so
        # user can select language
        if not language_exist:
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

        # Session file should be created... So we set the recent
        # choosen language
        if (create_session):
            session.CreateItens()
            session.SetLanguage(lang)
            session.CreateSessionFile()

        session.SaveConfigFileBackup()

        # Only after language was defined, splash screen will be
        # shown
        if lang:
            # For pt_BR, splash_pt.png should be used
            if (lang.startswith('pt')):
                icon_file = "splash_pt.png"
            else:
                icon_file = "splash_" + lang + ".png"

            path = os.path.join("..","icons", icon_file)

            bmp = wx.Image(path).ConvertToBitmap()

            style = wx.SPLASH_TIMEOUT | wx.SPLASH_CENTRE_ON_SCREEN |\
                    wx.FRAME_SHAPED
            if sys.platform == 'linux2':
                _SplashScreen.__init__(self,
                                     bitmap=bmp,
                                     style=style,
                                     timeout=5000,
                                     id=-1,
                                     parent=None)
            else:
                _SplashScreen.__init__(self,
                                     bitmap=bmp,
                                     splashStyle=style,
                                     milliseconds=5000,
                                     id=-1,
                                     parent=None)


            self.Bind(wx.EVT_CLOSE, self.OnClose)

            # Importing takes sometime, therefore it will be done
            # while splash is being shown
            from gui.frame import Frame
            from control import Controller
            from project import Project

            self.main = Frame(None)
            self.control = Controller(self.main)

            self.fc = wx.FutureCall(2000, self.ShowMain)

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
        try:
            ps.Publisher().subscribe(print_events, ps.ALL_TOPICS)
        except AttributeError:
            ps.Publisher().subscribe(print_events, ps.pub.getStrAllTopics())
        session.debug = 1

    # If import DICOM argument...
    if options.dicom_dir:
        import_dir = options.dicom_dir
        ps.Publisher().sendMessage('Import directory', import_dir)
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
                ps.Publisher().sendMessage('Open project', path)
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
    parse_comand_line()
    application.MainLoop()

if __name__ == '__main__':
    # Needed in win 32 exe
    if hasattr(sys,"frozen") and sys.frozen == "windows_exe":
        multiprocessing.freeze_support()

        #Click in the .inv3 file support
        root = _winreg.HKEY_CLASSES_ROOT
        key = "InVesalius 3.0\InstallationDir"
        hKey = _winreg.OpenKey (root, key, 0, _winreg.KEY_READ)
        value, type_ = _winreg.QueryValueEx (hKey, "")
        path = os.path.join(value,'dist')

        os.chdir(path)

    # Create raycasting presets' folder, if it doens't exist
    dirpath = os.path.join(os.path.expanduser('~'),
                           ".invesalius",
                           "presets")
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath)

    # Create logs' folder, if it doesn't exist
    dirpath = os.path.join(os.path.expanduser('~'),
                           ".invesalius",
                           "logs")
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath)

    if hasattr(sys,"frozen") and sys.frozen == "windows_exe":
        # Set system standard error output to file
        path = os.path.join(dirpath, "stderr.log")
        sys.stderr = open(path, "w")

    # Add current directory to PYTHONPATH, so other classes can
    # import modules as they were on root invesalius folder
    sys.path.append(".")

    # Init application
    main()

