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
import time
import traceback
from typing import Iterable
from invesalius.data.slice_ import Slice
import invesalius.data.surface_process as surface_process
import vtk
import invesalius.constants as const



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

import invesalius.enhanced_logging
import invesalius.error_handling
import invesalius.gui.language_dialog as lang_dlg
import invesalius.gui.log as log
import invesalius.i18n as i18n
import invesalius.session as ses
import invesalius.utils as utils
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher


from scripts import dicom_crop

import_folder_path = os.path.abspath("G:\\My Drive\\Lawson\\FOURDIX\\FOURDIX\\RATIB1\\Cardiac 1CTA_CORONARY_ARTERIES_lowHR_TESTBOLUS (Adult)\\CorCTALow  0.6  B10f 65%")
output_folder_path = os.path.abspath("G:\\My Drive\\Lawson\\crop")

def set_import_folder_path(import_folder_path_p: str, output_folder_path_p: str):

    """
    Set the import folder path and optionally the output folder path.
    """
    import_folder_path = import_folder_path_p
    output_folder_path = output_folder_path_p
    print(f"Import folder set to: {import_folder_path}")
    if output_folder_path:
        print(f"Output folder set to: {output_folder_path}")
    else:
        print("No output folder specified.")
Publisher.subscribe(set_import_folder_path, "Set import folder path into gui")

def update_crop_limits(limits: Iterable[float]):
    # Wait until both paths are set
    wait_count = 0
    while (import_folder_path is None or output_folder_path is None) and wait_count < 20:
        print("Waiting for import_folder_path and output_folder_path to be set...")
        time.sleep(0.1)
        wait_count += 1
    if import_folder_path is not None and output_folder_path is not None:
        if len(limits) != 6:
            raise ValueError("Crop limits must contain exactly 6 values: xi, xf, yi, yf, zi, zf")
        xi, xf, yi, yf, zi, zf = limits
        xi = float(xi)
        xf = float(xf)
        yi = float(yi)
        yf = float(yf)
        zi = float(zi)
        zf = float(zf)

        # Remove previous planes if needed (depends on your implementation)
        # Example: volume.planes.clear()

        # Create 6 planes at the crop boundaries
        # Each plane is defined by a point and a normal vector

        # Plane at xi (YZ plane)
        Publisher.sendMessage(
            "Create cut plane",
            origin=(50.689785105501976, -123.21592241920409, 68.5),
            normal=(1, 0, 0),
            label="Crop X min"
        )
        # # Plane at xf (YZ plane)
        Publisher.sendMessage(
            "Create cut plane",
            origin=(174.5108179722372, -122.48449494233766, 65.5),
            normal=(-1, 0, 0),
            label="Crop X max"
        )
        # # Plane at yi (XZ plane)
        Publisher.sendMessage(
            "Create cut plane",
            origin=(107.32721972890238, -173.2818497116884, 65.5),
            normal=(0, 1, 0),
            label="Crop Y min"
        )
        # # Plane at yf (XZ plane)
        Publisher.sendMessage(
            "Create cut plane",
            origin=(104.04997103410557, -64.3133306096941, 65.5),
            normal=(0, -1, 0),
            label="Crop Y max"
        )
        # # Optionally, add Z planes for full 3D cropping:
        # Publisher.sendMessage(
        #     "Create cut plane",
        #     origin=(0, 0, zi),
        #     normal=(0, 0, 1),
        #     label="Crop Z min"
        # )
        # Publisher.sendMessage(
        #     "Create cut plane",
        #     origin=(0, 0, zf),
        #     normal=(0, 0, -1),
        #     label="Crop Z max"
        # )

        print("Created 6 cut planes at crop boundaries.")
    else:
        raise ValueError("No import folder specified. Please set the import folder path before updating crop limits.")
Publisher.subscribe(update_crop_limits, "Update crop limits into gui")

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

        # Initialize the enhanced logging system
        invesalius.enhanced_logging.register_menu_handler()

        # Initialize the legacy logging system for backward compatibility
        log.invLogger.configureLogging()

        # <-- Add this line to ensure tag_start runs after the GUI is visible
        import wx
        args = parse_command_line()
        wx.CallAfter(tag_start, args.dicom_dir, args.tag, args.raycast_mode)


# ------------------------------------------------------------------


class Inv3SplashScreen(SplashScreen):
    """
    Splash screen to be shown in InVesalius initialization.
    """

    def __init__(self):
        # Splash screen image will depend on the current language
        lang = LANG
        self.locale = wx.Locale(wx.LANGUAGE_ENGLISH)

        # Initialize attributes to avoid errors
        self.control = None
        self.main = None
        self.fc = None

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
        # args = parse_command_line() #PREVENT IN
        # wx.CallLater(1, use_cmd_optargs, args)

        # Check for updates NOT USING
        from threading import Thread

        # p = Thread(target=utils.UpdateCheck, args=())
        # p.start()

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

        # If the timer is still running then go ahead and show the
        # main frame now
        if hasattr(self, "fc") and self.fc and self.fc.IsRunning():
            self.fc.Stop()
            self.ShowMain()

    def ShowMain(self):
        if not self.main.IsShown():
            self.main.Show()
            self.main.Raise()
        # Destroy the splash screen
        self.Destroy()


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
    
def tag_start(dicom_dir=None, tag_args=None, raycast_mode=None):
    """
    Import DICOM if specified, then import surface files and create tags (not associated with surfaces).
    Tags are created in order after all files are imported.
    Optionally set raycasting mode after surfaces are loaded.
    """
    from invesalius.data.tag import Tag3D, Tag2D

    if dicom_dir:
        Publisher.sendMessage("Import directory", directory=dicom_dir, use_gui=True)
        Publisher.sendMessage("Wait for import to finish")

    if tag_args:
        # First, collect all files (assume .stl or similar)
        files = []
        i = 0
        while i < len(tag_args) and tag_args[i].lower().endswith('.stl'):
            files.append(tag_args[i])
            i += 1

        # Import all surface files
        for idx, file in enumerate(files):
            Publisher.sendMessage("Import surface file", filename=file)
            if file.endswith("lvm.stl"):
                Publisher.sendMessage("Set surface colour", surface_index=idx, colour=(1.0, 1.0, 0.5019607843137255))
                Publisher.sendMessage("Set surface transparency", surface_index=idx, transparency=0.833)
            elif file.endswith("cornary.stl"):
                Publisher.sendMessage("Set surface colour", surface_index=idx, colour=(1.0, 0.0, 0.0))

        # If raycast_mode is specified, set raycasting preset and hide surface 0
        if raycast_mode:
            Publisher.sendMessage("Load raycasting preset", preset_name=raycast_mode)
            Publisher.sendMessage("Show surface", index=0, visibility=False)

        # Now, parse tags (each tag: 6 floats + optional label)
        tag_index = 0
        while i < len(tag_args):
            # Need at least 6 numbers for a tag
            if i + 5 >= len(tag_args):
                break
            try:
                coords = [float(tag_args[i + j]) for j in range(6)]
            except ValueError:
                break
            i += 6
            # Optional label
            label = None
            if i < len(tag_args) and not tag_args[i].lower().endswith('.stl'):
                label = tag_args[i]
                i += 1
            if not label:
                label = f"Tag {tag_index+1}"
            point1 = tuple(coords[:3])
            point2 = tuple(coords[3:])
            Tag3D(point1, point2, label=label, colour=(0, 255, 0))
            Tag2D(point1, point2, label=label, location=const.AXIAL)
            Tag2D(point1, point2, label=label, location=const.CORONAL)
            tag_index += 1
       

# ------------------------------------------------------------------


from selector_mask import SelectMaskParts
from invesalius.data.crop_mask import CropMask

def parse_command_line():
    """
    Handle command line arguments.
    """
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

    # New argument for center selection
    parser.add_argument(
        "-center_select",
        nargs=4,  # Now expects X, Y, Z, OUTPUT_PATH
        metavar=("X", "Y", "Z", "OUTPUT_PATH"),
        help="Create a new mask from the specified 3D coordinate (x, y, z) in the mask array and export to OUTPUT_PATH.",
        type=str,
    )

    parser.add_argument(
        "--crop-mask",
        nargs=7,  # xi xf yi yf zi zf OUTPUT_PATH
        metavar=("XI", "XF", "YI", "YF", "ZI", "ZF", "OUTPUT_PATH"),
        help="Crop the current mask with voxel limits and export to OUTPUT_PATH.",
        type=str,
    )
  
    parser.add_argument(
        "--threshold-crop-mask",
        nargs=9,  # lower upper xi xf yi yf zi zf OUTPUT_PATH
        metavar=("LOWER", "UPPER", "XI", "XF", "YI", "YF", "ZI", "ZF", "OUTPUT_PATH"),
        help="Create a new mask with threshold [LOWER,UPPER], crop it with voxel limits, and export to OUTPUT_PATH.",
        type=str,
    )

    parser.add_argument(
        "--tag",
        nargs="+",
        metavar="FILE [FILE ...] [X1 Y1 Z1 X2 Y2 Z2 [LABEL]] ...",
        help=(
            "Import one or more surface files (e.g. .stl), then create N tags in order after all files are imported. "
            "Usage: --tag file1.stl file2.stl ... [x1 y1 z1 x2 y2 z2 [label]] [x1 y1 z1 x2 y2 z2 [label]] ...\n"
            "First, specify all files to import. After the last file, provide 6 numbers (coordinates for a tag) and an optional label for each tag. "
            "Tags are not associated with specific files, but are created in order after all files are imported."
        ),
        type=str,
    )
    # Add the new argument for raycast mode
    parser.add_argument(
        "--raycast-mode",
        type=str,
        help="Specify a raycasting preset to load after surfaces are loaded (e.g. 'Mid contrast')."
    )
    parser.add_argument(
        "--print-crop-limits",
        action="store_true",
        help="Print crop limits to stdout and exit when available.",
    )
    parser.add_argument(
        "--output-folder",
        type=str,
        help="Output folder for cropped DICOM series when using --print-crop-limits.",
    )
    args = parser.parse_args()
    return args


def use_cmd_optargs(args):
    

    # If the new center_select argument is provided
    if args.center_select:
        try:
            x, y, z, output_path = args.center_select  # Now expecting X, Y, Z, OUTPUT_PATH
            x = int(x)
            y = int(y)
            z = int(z)
            coord_3d = (x, y, z)

            if args.dicom_dir:
                import_dir = args.dicom_dir
                Publisher.sendMessage("Import directory", directory=import_dir, use_gui=not args.no_gui)
                Publisher.sendMessage("Wait for import to finish")

            # Create the new mask from the selection
            new_mask_selection = SelectMaskParts(Slice())
            new_mask_selection.OnSelect(None, None, x, y, z)
            new_mask_selection.CleanUp()
            
            

            export_mask(new_mask_selection.config.mask, output_path, index=1)
            print(f"Surface exported to {output_path}")
            # -------------------------------------------

            print(f"New mask '{new_mask_selection.config.mask.name}' created and used for surface generation.")
        except Exception as e:
            print(f"Error while creating the new mask or generating the surface: {e}")
        finally:
            print("done")
            exit(0)

    # Handle --crop-mask
    if args.crop_mask:
        try:
            xi, xf, yi, yf, zi, zf, output_path = args.crop_mask
            xi = int(xi)
            xf = int(xf)
            yi = int(yi)
            yf = int(yf)
            zi = int(zi)
            zf = int(zf)

            # Optionally import DICOM if specified
            if args.dicom_dir:
                import_dir = args.dicom_dir
                Publisher.sendMessage("Import directory", directory=import_dir, use_gui=not args.no_gui)
                Publisher.sendMessage("Wait for import to finish")

            # Create and crop the mask
            cropper = CropMask(Slice())
            cropper.set_limits(xi, xf, yi, yf, zi, zf)
            cropper.crop()

            # Export the cropped mask
            export_mask(cropper.slice.current_mask, output_path, index=1)
            print(f"Cropped mask exported to {output_path}")
        except Exception as e:
            print(f"Error while cropping and exporting the mask: {e}")
        finally:
            print("done")
            exit(0)

    # Handle --threshold-crop-mask
    if args.threshold_crop_mask:
        try:
            lower, upper, xi, xf, yi, yf, zi, zf, output_path = args.threshold_crop_mask
            lower = int(lower)
            upper = int(upper)
            xi = int(xi)
            xf = int(xf)
            yi = int(yi)
            yf = int(yf)
            zi = int(zi)
            zf = int(zf)

            # Optionally import DICOM if specified
            if args.dicom_dir:
                import_dir = args.dicom_dir
                Publisher.sendMessage("Import directory", directory=import_dir, use_gui=not args.no_gui)
                Publisher.sendMessage("Wait for import to finish")

            slice_ = Slice()
            mask = slice_.current_mask
            if mask is None:
                raise RuntimeError("No mask available to apply threshold.")

            # Set the new threshold range on the existing mask
            mask.threshold_range = (lower, upper)
            print(f"Set threshold range to {lower}-{upper} on mask '{mask.name}'.")

            # Apply the threshold to the current mask
            # slice_.do_threshold_to_all_slices(mask)
            # print("Applied threshold to all slices.")

            # Crop the mask
            cropper = CropMask(slice_)
            cropper.set_limits(xi, xf, yi, yf, zi, zf)
            cropper.crop()
            print(f"Mask cropped to limits: {xi}, {xf}, {yi}, {yf}, {zi}, {zf}.")

            # Export the cropped mask
            export_mask(mask, output_path, index=mask.index)
            print(f"Thresholded and cropped mask exported to {output_path}")
        except Exception as e:
            print(f"Error while thresholding, cropping, and exporting the mask: {e}")
        finally:
            print("done")
            exit(0)

    # Handle --print-crop-limits
    if getattr(args, "print_crop_limits", False):
        # Set globals for use in update_crop_limits
        import_folder_path_p = args.import_folder
        # Allow user to specify output folder, else use default
        output_folder_path_p = getattr(args, "output_folder", None) or "cropped_output"
        Publisher.sendMessage("Set import folder path into gui", import_folder_path_p, output_folder_path_p)

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
    from invesalius.data.slice_ import Slice

    # Print the name of the currently selected mask
    current_mask = Slice().current_mask
    if current_mask is not None:
        print(f"Exporting mask: {current_mask.name}")
    else:
        print("No mask selected for export.")
    # input("Press Enter to continue...")

    #Publisher.sendMessage("Set threshold values", threshold_range=threshold_range)

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
        key = r"InVesalius 3.1\InstallationDir"
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
    # Set a global flag for no-gui mode
    global NO_GUI
    NO_GUI = args.no_gui

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

def export_mask(mask, file_name, index=1):
    """
    Export a surface using a specific mask object and custom surface parameters,
    and export the surface to a file.
    """
    import invesalius.constants as const
    from invesalius.data.slice_ import Slice

    surface_parameters = {
        "method": {
            "algorithm": "ca_smoothing",
            "options": {
                "angle": 0.7,
                "max distance": 3.0,
                "min weight": 0.5,
                "steps": 10,
            },
        },
        "options": {
            "index": index,
            "name": "",
            "quality": "Optimal *",
            "fill": False,
            "keep_largest": False,
            "overwrite": False,
        },
    }

    
    

    slice_ = Slice()
    Publisher.sendMessage("Create surface", slice_=slice_, mask=mask, surface_parameters=surface_parameters)

    print(surface_parameters)

    # Export the surface to file
    print(f"Sending message in topic Export surface to file with data {{'filename': '{file_name}', 'filetype': {const.FILETYPE_STL}, 'convert_to_world': False}}")
    Publisher.sendMessage(
        "Export surface to file",
        filename=file_name,
        filetype=const.FILETYPE_STL
    )



if __name__ == "__main__":
    main()