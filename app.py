#!/usr/bin/env python3
# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# -------------------------------------------------------------------------

import argparse
import multiprocessing
import os
import re
import shutil
import sys
import traceback

if sys.platform == "darwin":
    try:
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass

if sys.platform == "win32":
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

# Forcing to use X11, OpenGL in wxPython doesn't work with Wayland.
if sys.platform not in ("win32", "darwin"):
    os.environ["GDK_BACKEND"] = "x11"

import wx
from wx.adv import SPLASH_CENTRE_ON_SCREEN, SPLASH_TIMEOUT, SplashScreen

# import wx.lib.agw.advancedsplash as agw
# if sys.platform.startswith('linux'):
#    _SplashScreen = agw.AdvancedSplash
# else:
#    if sys.platform != 'darwin':
#        _SplashScreen = wx.SplashScreen
import invesalius.gui.language_dialog as lang_dlg
import invesalius.gui.log as log
import invesalius.i18n as i18n
import invesalius.session as ses
import invesalius.utils as utils
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher

FS_ENCODE = sys.getfilesystemencoding()
LANG = None

# ------------------------------------------------------------------

if sys.platform in ("linux2", "linux", "win32"):
    if not hasattr(wx, "GetXDisplay"):
        setattr(wx, "GetXDisplay", lambda: None)


session = ses.Session()
if session.ReadConfig():
    lang = session.GetConfig("language")
    if lang:
        try:
            LANG = lang
        except FileNotFoundError:
            pass


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
        wx.CallLater(1000, self.Startup2)

        return True

    def MacOpenFile(self, filename):
        """
        Open drag & drop files under darwin
        """
        path = os.path.abspath(filename)
        Publisher.sendMessage("Open project", filepath=path)

    def Startup2(self):
        self.control = self.splash.control
        self.frame = self.splash.main
        self.SetTopWindow(self.frame)
        self.frame.Show()
        self.frame.Raise()
        # logger = log.MyLogger()
        log.invLogger.configureLogging()


# ------------------------------------------------------------------


class Inv3SplashScreen(SplashScreen):
    """
    Splash screen to be shown in InVesalius initialization.
    """

    def __init__(self):
        # Splash screen image will depend on the current language
        lang = LANG
        self.locale = wx.Locale(wx.LANGUAGE_ENGLISH)

        # Language information is available in session configuration
        # file. First we need to check if this file exist, if now, it
        # should be created
        create_session = LANG is None

        install_lang = False
        if lang:
            install_lang = True

        # If no language is set into session file, show dialog so
        # user can select language
        if not install_lang:
            dialog = lang_dlg.LanguageDialog()

            # FIXME: This works ok in linux2, darwin and win32,
            # except on win64, due to wxWidgets bug
            try:
                ok = dialog.ShowModal() == wx.ID_OK
            except wx.PyAssertionError:
                ok = True
            finally:
                if ok:
                    lang = dialog.GetSelectedLanguage()
                    session.SetConfig("language", lang)
                    i18n.tr.reset()
                else:
                    homedir = os.path.expanduser("~")
                    config_dir = os.path.join(homedir, ".invesalius")
                    shutil.rmtree(config_dir)

                    sys.exit()

            dialog.Destroy()

        # Session file should be created... So we set the recently chosen language.
        if create_session:
            session.CreateConfig()
            session.SetConfig("language", lang)

        # Only after language was defined, splash screen will be shown.
        if lang:
            # import locale
            # try:
            #    locale.setlocale(locale.LC_ALL, '')
            # except locale.Error:
            #    pass

            # For pt_BR, splash_pt.png should be used
            if lang.startswith("pt"):
                icon_file = "splash_pt.png"
            else:
                icon_file = "splash_" + lang + ".png"

            if hasattr(sys, "frozen") and (
                getattr(sys, "frozen") == "windows_exe" or getattr(sys, "frozen") == "console_exe"
            ):
                abs_file_path = os.path.abspath(".." + os.sep)
                path = abs_file_path
                path = os.path.join(path, "icons", icon_file)
            else:
                path = os.path.join(inv_paths.ICON_DIR, icon_file)
                if not os.path.exists(path):
                    path = os.path.join(inv_paths.ICON_DIR, "splash_en.png")

            bmp = wx.Image(path).ConvertToBitmap()

            style = SPLASH_TIMEOUT | SPLASH_CENTRE_ON_SCREEN

            SplashScreen.__init__(
                self, bitmap=bmp, splashStyle=style, milliseconds=1500, id=-1, parent=None
            )
            self.Bind(wx.EVT_CLOSE, self.OnClose)
            wx.GetApp().Yield()
            wx.CallLater(200, self.Startup)

    def Startup(self):
        # Importing takes sometime, therefore it will be done
        # while splash is being shown
        from invesalius.control import Controller
        from invesalius.gui.frame import Frame

        self.main = Frame(None)
        self.control = Controller(self.main)

        self.fc = wx.CallLater(200, self.ShowMain)
        args = parse_command_line()
        wx.CallLater(1, use_cmd_optargs, args)

        # Check for updates
        from threading import Thread

        p = Thread(target=utils.UpdateCheck, args=())
        p.start()

        if not session.ExitedSuccessfullyLastTime():
            # Reopen project
            project_path = session.GetState("project_path")
            if project_path is not None:
                filepath = os.path.join(project_path[0], project_path[1])
                if os.path.exists(filepath):
                    Publisher.sendMessage("Open project", filepath=filepath)
                else:
                    utils.debug(f"File doesn't exist: {filepath}")
                    session.CloseProject()
        else:
            session.CreateState()

    def OnClose(self, evt):
        # Make sure the default handler runs too so this window gets
        # destroyed
        evt.Skip()
        self.Hide()
        evt.GetEventObject().Destroy()

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


def non_gui_startup(args):
    if LANG:
        lang = LANG
    else:
        lang = "en"
    _ = i18n.InstallLanguage(lang)

    from invesalius.control import Controller

    session = ses.Session()
    if not session.ReadConfig():
        session.CreateConfig()
        session.SetConfig("language", lang)

    _ = Controller(None)

    use_cmd_optargs(args)


# ------------------------------------------------------------------


def parse_command_line():
    """
    Handle command line arguments.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser()

    # -d or --debug: print all pubsub messages sent
    parser.add_argument("-d", "--debug", action="store_true", dest="debug")
    parser.add_argument("project_file", nargs="?", default="", help="InVesalius 3 project file")

    parser.add_argument("--no-gui", action="store_true", dest="no_gui")

    # -i or --import: import DICOM directory
    # chooses largest series
    parser.add_argument("-i", "--import", action="store", dest="dicom_dir")

    parser.add_argument("--import-all", action="store")

    parser.add_argument("--import-folder", action="store", dest="import_folder")

    parser.add_argument(
        "-o", "--import-other", dest="other_file", help="Import Nifti, Analyze, PAR/REC file"
    )

    parser.add_argument("--remote-host", action="store", dest="remote_host")

    parser.add_argument("-s", "--save", help="Save the project after an import.")

    parser.add_argument(
        "-t", "--threshold", help="Define the threshold for the export (e.g. 100-780)."
    )

    parser.add_argument("-e", "--export", help="Export to STL.")

    parser.add_argument("-a", "--export-to-all", help="Export to STL for all mask presets.")

    parser.add_argument("--export-project", help="Export slices and mask to HDF5 or Nifti file.")

    parser.add_argument(
        "--no-masks",
        action="store_false",
        dest="save_masks",
        default=True,
        help="Make InVesalius not export mask when exporting project.",
    )

    parser.add_argument(
        "--use-pedal", action="store_true", dest="use_pedal", help="Use an external trigger pedal"
    )

    parser.add_argument(
        "--debug-efield",
        action="store_true",
        dest="debug_efield",
        help="Debug navigated TMS E-field computation",
    )

    parser.add_argument("--cranioplasty", help="Creates an AI-based cranioplasty implant.")

    args = parser.parse_args()
    return args


def use_cmd_optargs(args):
    # If import DICOM argument...
    if args.dicom_dir:
        import_dir = args.dicom_dir
        Publisher.sendMessage("Import directory", directory=import_dir, use_gui=not args.no_gui)

        if args.save:
            Publisher.sendMessage("Save project", filepath=os.path.abspath(args.save))
            exit(0)
        if args.cranioplasty:
            check_for_cranioplasty(args)
        else:
            check_for_export(args)
        return True

    elif args.import_folder:
        Publisher.sendMessage("Import folder", folder=args.import_folder)
        if args.save:
            Publisher.sendMessage("Save project", filepath=os.path.abspath(args.save))
            exit(0)
        if args.cranioplasty:
            check_for_cranioplasty(args)
        else:
            check_for_export(args)

    elif args.other_file:
        Publisher.sendMessage("Open other files", filepath=args.other_file)
        if args.save:
            Publisher.sendMessage("Save project", filepath=os.path.abspath(args.save))
            exit(0)
        if args.cranioplasty:
            check_for_cranioplasty(args)
        else:
            check_for_export(args)

    elif args.import_all:
        import invesalius.reader.dicom_reader as dcm

        for patient in dcm.GetDicomGroups(args.import_all):
            for group in patient.GetGroups():
                Publisher.sendMessage("Import group", group=group, use_gui=not args.no_gui)
                check_for_export(args, suffix=group.title, remove_surfaces=False)
                Publisher.sendMessage("Remove masks", mask_indexes=(0,))
        return True

    # Check if there is a file path somewhere in what the user wrote
    # In case there is, try opening as it was a inv3
    else:
        if args.project_file:
            file = utils.decode(args.project_file, FS_ENCODE)
            if os.path.isfile(file):
                path = os.path.abspath(file)
                Publisher.sendMessage("Open project", filepath=path)
                check_for_export(args)
                return True

            file = utils.decode(args.project_file, sys.stdin.encoding)
            if os.path.isfile(file):
                path = os.path.abspath(file)
                Publisher.sendMessage("Open project", filepath=path)
                check_for_export(args)
                return True

    return False


def check_for_cranioplasty(args):
    import invesalius.constants as const
    from invesalius.i18n import tr as _

    if args.cranioplasty:
        from invesalius.data import slice_
        from invesalius.project import Project

        # create cranium mask
        Publisher.sendMessage("Update threshold limits", threshold_range=(226, 3071))
        Publisher.sendMessage("Appy threshold all slices")

        # create implant mask
        Publisher.sendMessage("Create implant for cranioplasty")

        path_ = args.export

        # convert masks to surfaces and exports them.
        Publisher.sendMessage(
            "Export all surfaces separately", folder=path_, filetype=const.FILETYPE_STL
        )


def sanitize(text):
    text = str(text).strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", text)


def check_for_export(args, suffix="", remove_surfaces=False):
    suffix = sanitize(suffix)

    if args.export:
        if not args.threshold:
            print("Need option --threshold when using --export.")
            exit(1)
        threshold_range = tuple([int(n) for n in args.threshold.split(",")])

        if suffix:
            if args.export.endswith(".stl"):
                path_ = f"{args.export[:-4]}-{suffix}.stl"
            else:
                path_ = f"{args.export}-{suffix}.stl"
        else:
            path_ = args.export

        export(path_, threshold_range, remove_surface=remove_surfaces)
    elif args.export_to_all:
        # noinspection PyBroadException
        try:
            from invesalius.project import Project

            for threshold_name, threshold_range in Project().presets.thresh_ct.items():
                if isinstance(threshold_range[0], int):
                    path_ = f"{args.export_to_all}-{suffix}-{threshold_name}.stl"
                    export(path_, threshold_range, remove_surface=True)
        except Exception:
            traceback.print_exc()
        finally:
            exit(0)

    if args.export_project:
        from invesalius.project import Project

        prj = Project()
        export_filename = args.export_project
        if suffix:
            export_filename, ext = os.path.splitext(export_filename)
            export_filename = f"{export_filename}-{suffix}{ext}"

        prj.export_project(export_filename, save_masks=args.save_masks)
        print(f"Saved {export_filename}")


def export(path_, threshold_range, remove_surface=False):
    import invesalius.constants as const
    from invesalius.i18n import tr as _

    Publisher.sendMessage("Set threshold values", threshold_range=threshold_range)

    surface_options = {
        "method": {
            "algorithm": "Default",
            "options": {},
        },
        "options": {
            "index": 0,
            "name": "",
            "quality": _("Optimal *"),
            "fill": False,
            "keep_largest": False,
            "overwrite": False,
        },
    }
    Publisher.sendMessage("Create surface from index", surface_parameters=surface_options)
    Publisher.sendMessage("Export surface to file", filename=path_, filetype=const.FILETYPE_STL)
    if remove_surface:
        Publisher.sendMessage("Remove surfaces", surface_indexes=(0,))


def print_events(topic=Publisher.AUTO_TOPIC, **msg_data):
    """
    Print pubsub messages
    """
    utils.debug(f"{topic}\n\tParameters: {msg_data}")


def init():
    """
    Initialize InVesalius.

    Mostly file-system related initializations.
    """
    # Is needed because of pyinstaller
    multiprocessing.freeze_support()

    # Needed in win 32 exe
    if hasattr(sys, "frozen") and sys.platform == "win32":
        # Click in the .inv3 file support
        root = winreg.HKEY_CLASSES_ROOT
        key = "InVesalius 3.1\InstallationDir"
        hKey = winreg.OpenKey(root, key, 0, winreg.KEY_READ)
        value, type_ = winreg.QueryValueEx(hKey, "")
        path = os.path.join(value, "dist")

        os.chdir(path)

    if not inv_paths.USER_INV_DIR.exists():
        inv_paths.create_conf_folders()
        if inv_paths.OLD_USER_INV_DIR.exists():
            inv_paths.copy_old_files()

    if hasattr(sys, "frozen") and getattr(sys, "frozen") == "windows_exe":
        # Set system standard error output to file
        path = inv_paths.USER_LOG_DIR.joinpath("stderr.log")
        sys.stderr = open(path, "w")


def main(connection=None, remote_host=None):
    """
    Start InVesalius.

    Parameters:
        connection: An object to communicate with the outside world.
          In theory, can be any object supports certain function calls.
          See invesalius.net.neuronavigation_api for a comprehensive
          description of how the object is used.

          Note that if InVesalius is started in the usual way by running
          app.py, the connection object defaults to None. To enable this
          functionality, InVesalius needs to be started by calling the main
          function directly with a proper connection object.

        remote_host: Specifies the address and the port of the remote host with
          which InVesalius should communicate. If provided, overrides any value
          passed through the command line using the --remote-host argument.
    """
    init()

    args = parse_command_line()

    session = ses.Session()
    session.SetConfig("debug", args.debug)
    session.SetConfig("debug_efield", args.debug_efield)

    if args.debug:
        Publisher.subscribe(print_events, Publisher.ALL_TOPICS)

    if remote_host is not None or args.remote_host is not None:
        from invesalius.net.remote_control import RemoteControl

        remote_control = RemoteControl(remote_host or args.remote_host)
        remote_control.connect()

    if args.use_pedal:
        from invesalius.net.pedal_connection import MidiPedal

        MidiPedal().start()

    from invesalius.net.neuronavigation_api import NeuronavigationApi

    NeuronavigationApi(connection)

    if args.no_gui:
        non_gui_startup(args)
    else:
        application = InVesalius(False)
        application.MainLoop()


if __name__ == "__main__":
    main()
