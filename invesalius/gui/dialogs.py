# -*- coding: UTF-8 -*-
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
# --------------------------------------------------------------------------

import datetime
import itertools
import os
import random
import sys
import time
from concurrent import futures
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    MutableSequence,
    Optional,
    Sequence,
    Tuple,
    Union,
)

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

import csv

import numpy as np
import wx
import wx.lib.filebrowsebutton as filebrowse
from vtkmodules.vtkCommonColor import vtkNamedColors
from vtkmodules.vtkCommonComputationalGeometry import vtkParametricTorus
from vtkmodules.vtkCommonCore import mutable, vtkPoints
from vtkmodules.vtkCommonDataModel import (
    vtkCellLocator,
    vtkIterativeClosestPointTransform,
    vtkPolyData,
)
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkAppendPolyData, vtkCleanPolyData, vtkPolyDataNormals
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkFiltersSources import (
    vtkArrowSource,
    vtkCylinderSource,
    vtkParametricFunctionSource,
    vtkRegularPolygonSource,
    vtkSphereSource,
)
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleTrackballActor,
    vtkInteractorStyleTrackballCamera,
)
from vtkmodules.vtkIOGeometry import vtkSTLReader
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkCellPicker,
    vtkFollower,
    vtkPolyDataMapper,
    vtkProperty,
    vtkRenderer,
)
from vtkmodules.vtkRenderingFreeType import vtkVectorText
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from wx.adv import AboutBox, AboutDialogInfo, BitmapComboBox
from wx.lib import masked
from wx.lib.wordwrap import wordwrap

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.polydata_utils as pu
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.gui.widgets.gradient as grad
import invesalius.session as ses
import invesalius.utils as utils
from invesalius import inv_paths
from invesalius.gui.widgets.clut_imagedata import EVT_CLUT_NODE_CHANGED, CLUTImageDataWidget
from invesalius.gui.widgets.fiducial_buttons import OrderedFiducialButtons
from invesalius.gui.widgets.inv_spinctrl import InvFloatSpinCtrl, InvSpinCtrl
from invesalius.i18n import tr as _
from invesalius.math_utils import inner1d
from invesalius.pubsub import pub as Publisher

if TYPE_CHECKING:
    from invesalius.data.mask import Mask
    from invesalius.data.styles import (
        CropMaskConfig,
        FFillConfig,
        FFillSegmentationConfig,
        SelectPartConfig,
        WatershedConfig,
    )
    from invesalius.gui.widgets.clut_imagedata import CLUTEvent, Node
    from invesalius.navigation.mtms import mTMS
    from invesalius.navigation.navigation import Navigation
    from invesalius.navigation.robot import Robot
    from invesalius.navigation.tracker import Tracker
    from invesalius.net.pedal_connection import PedalConnector
    from typings.wx.type_defs import ColourType  # type: ignore


class MaskEvent(wx.PyCommandEvent):
    def __init__(self, evtType: int, id: int, mask_index: int):
        wx.PyCommandEvent.__init__(
            self,
            evtType,
            id,
        )
        self.mask_index = mask_index


myEVT_MASK_SET = wx.NewEventType()
EVT_MASK_SET = wx.PyEventBinder(myEVT_MASK_SET, 1)


class NumberDialog(wx.Dialog):
    def __init__(self, message: str, value: int = 0):
        wx.Dialog.__init__(
            self,
            None,
            -1,
            "InVesalius 3",
            size=wx.DefaultSize,
            pos=wx.DefaultPosition,
            style=wx.DEFAULT_DIALOG_STYLE,
        )

        # Static text which contains message to user
        label = wx.StaticText(self, -1, message)

        # Numeric value to be changed by user
        num_ctrl = masked.NumCtrl(
            self,
            value=value,
            integerWidth=3,
            fractionWidth=2,
            allowNegative=True,
            signedForegroundColour="Black",
        )
        self.num_ctrl = num_ctrl

        # Buttons
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText(_("Value will be applied."))
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText(_("Value will not be applied."))

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        sizer.Add(num_ctrl, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Centre()

    def SetValue(self, value: int) -> None:
        self.num_ctrl.SetValue(value)

    def GetValue(self) -> Union[int, float, None]:
        return self.num_ctrl.GetValue()


class ResizeImageDialog(wx.Dialog):
    def __init__(self):  # , message, value=0):
        wx.Dialog.__init__(
            self,
            None,
            -1,
            "InVesalius 3",
            size=wx.DefaultSize,
            pos=wx.DefaultPosition,
            style=wx.DEFAULT_DIALOG_STYLE,
        )

        lbl_message = wx.StaticText(
            self,
            -1,
            _(
                "InVesalius is running on a 32-bit operating system or has insufficient memory. \nIf you want to work with 3D surfaces or volume rendering, \nit is recommended to reduce the medical images resolution."
            ),
        )
        icon = wx.ArtProvider.GetBitmap(wx.ART_WARNING, wx.ART_MESSAGE_BOX, (32, 32))
        bmp = wx.StaticBitmap(self, -1, icon)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()

        lbl_message_percent = wx.StaticText(self, -1, _("Percentage of original resolution"))

        num_ctrl_percent = InvSpinCtrl(self, -1, value=100, min_value=20, max_value=100)
        self.num_ctrl_porcent = num_ctrl_percent

        sizer_percent = wx.BoxSizer(wx.HORIZONTAL)
        sizer_percent.Add(lbl_message_percent, 0, wx.EXPAND | wx.ALL, 5)
        sizer_percent.Add(num_ctrl_percent, 0, wx.ALL, 5)

        sizer_itens = wx.BoxSizer(wx.VERTICAL)
        sizer_itens.Add(lbl_message, 0, wx.EXPAND | wx.ALL, 5)
        sizer_itens.Add(sizer_percent, 0, wx.EXPAND | wx.ALL, 5)
        sizer_itens.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        sizer_general = wx.BoxSizer(wx.HORIZONTAL)
        sizer_general.Add(bmp, 0, wx.ALIGN_CENTRE | wx.ALL, 10)
        sizer_general.Add(sizer_itens, 0, wx.ALL, 5)

        # self.SetAutoLayout(True)
        self.SetSizer(sizer_general)
        sizer_general.Fit(self)
        self.Layout()
        self.Centre()

    def SetValue(self, value: Union[float, str]) -> None:
        self.num_ctrl_porcent.SetValue(value)

    def GetValue(self) -> int:
        return self.num_ctrl_porcent.GetValue()

    def Close(self) -> None:
        self.Destroy()


def ShowNumberDialog(message: str, value: int = 0) -> Union[int, float, None]:
    dlg = NumberDialog(message, value)
    dlg.SetValue(value)

    if dlg.ShowModal() == wx.ID_OK:
        return dlg.GetValue()
    dlg.Destroy()

    return 0


# ---------

INV_NON_COMPRESSED = 0
INV_COMPRESSED = 1

WILDCARD_INV_SAVE = (
    _("InVesalius project (*.inv3)|*.inv3")
    + "|"
    + _("InVesalius project compressed (*.inv3)|*.inv3")
)

WILDCARD_OPEN = "InVesalius 3 project (*.inv3)|*.inv3|" "All files (*.*)|*.*"

WILDCARD_ANALYZE = "Analyze 7.5 (*.hdr)|*.hdr|" "All files (*.*)|*.*"

WILDCARD_NIFTI = "NIfTI 1 (*.nii;*.nii.gz;*.hdr)|*.nii;*.nii.gz;*.hdr|" "All files (*.*)|*.*"
# ".[jJ][pP][gG]"
WILDCARD_PARREC = "PAR/REC (*.par)|*.par|" "All files (*.*)|*.*"

WILDCARD_MESH_FILES = (
    "STL File format (*.stl)|*.stl|"
    "Standard Polygon File Format (*.ply)|*.ply|"
    "Alias Wavefront Object (*.obj)|*.obj|"
    "VTK Polydata File Format (*.vtp)|*.vtp|"
    "All files (*.*)|*.*"
)
WILDCARD_JSON_FILES = "JSON File format (*.json|*.json|" "All files (*.*)|*.*"


def ShowOpenProjectDialog() -> Union[str, None]:
    # Default system path
    current_dir = os.path.abspath(".")
    session = ses.Session()
    last_directory = session.GetConfig("last_directory_inv3", "")
    dlg = wx.FileDialog(
        None,
        message=_("Open InVesalius 3 project..."),
        defaultDir=last_directory,
        defaultFile="",
        wildcard=WILDCARD_OPEN,
        style=wx.FD_OPEN | wx.FD_CHANGE_DIR,
    )

    # inv3 filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            filepath = dlg.GetPath()
    except wx.PyAssertionError:  # FIX: win64
        filepath = dlg.GetPath()

    if filepath:
        last_directory = os.path.split(filepath)[0]
        session.SetConfig("last_directory_inv3", last_directory)

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filepath


def ShowImportDirDialog(self) -> Union[str, bytes, None]:
    current_dir = os.path.abspath(".")

    if sys.platform == "win32" or sys.platform.startswith("linux"):
        session = ses.Session()
        folder = session.GetConfig("last_dicom_folder", "")
    else:
        folder = ""

    dlg = wx.DirDialog(
        self,
        _("Choose a DICOM folder:"),
        folder,
        style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR,
    )

    path = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # GetPath returns in unicode, if a path has non-ascii characters a
            # UnicodeEncodeError is raised. To avoid this, path is encoded in utf-8
            if sys.platform == "win32":
                path = dlg.GetPath()
            else:
                path = dlg.GetPath().encode("utf-8")

    except wx.PyAssertionError:  # TODO: error win64
        if dlg.GetPath():
            path = dlg.GetPath()

    if sys.platform != "darwin":
        if path:
            path_decoded = utils.decode(path, const.FS_ENCODE)
            session.SetConfig("last_dicom_folder", path_decoded)

    # Only destroy a dialog after you're done with it.
    dlg.Destroy()
    os.chdir(current_dir)
    return path


def ShowImportBitmapDirDialog(self) -> Optional[str]:
    current_dir = os.path.abspath(".")

    session = ses.Session()
    last_directory = session.GetConfig("last_directory_bitmap", "")

    dlg = wx.DirDialog(
        self,
        _("Choose a folder with TIFF, BMP, JPG or PNG:"),
        last_directory,
        style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_CHANGE_DIR,
    )

    path = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # GetPath returns in unicode, if a path has non-ascii characters a
            # UnicodeEncodeError is raised. To avoid this, path is encoded in utf-8
            path = dlg.GetPath()

    except wx.PyAssertionError:  # TODO: error win64
        if dlg.GetPath():
            path = dlg.GetPath()

    if path:
        session.SetConfig("last_directory_bitmap", path)

    # Only destroy a dialog after you're done with it.
    dlg.Destroy()
    os.chdir(current_dir)
    return path


def ShowImportOtherFilesDialog(
    id_type: wx.WindowIDRef, msg: str = "Import NIFTi 1 file"
) -> Union[str, bytes, None]:
    # Default system path
    session = ses.Session()
    last_directory = session.GetConfig("last_directory_%d" % id_type, "")
    dlg = wx.FileDialog(
        None,
        message=msg,
        defaultDir=last_directory,
        defaultFile="",
        wildcard=WILDCARD_NIFTI,
        style=wx.FD_OPEN | wx.FD_CHANGE_DIR,
    )

    # if id_type == const.ID_NIFTI_IMPORT:
    #     dlg.SetMessage(_("Import NIFTi 1 file"))
    #     dlg.SetWildcard(WILDCARD_NIFTI)
    # elif id_type == const.ID_TREKKER_MASK:
    #     dlg.SetMessage(_("Import Trekker mask"))
    #     dlg.SetWildcard(WILDCARD_NIFTI)
    # elif id_type == const.ID_TREKKER_IMG:
    #     dlg.SetMessage(_("Import Trekker anatomical image"))
    #     dlg.SetWildcard(WILDCARD_NIFTI)
    # elif id_type == const.ID_TREKKER_FOD:
    #     dlg.SetMessage(_("Import Trekker FOD"))
    #     dlg.SetWildcard(WILDCARD_NIFTI)
    # elif id_type == const.ID_TREKKER_ACT:
    #     dlg.SetMessage(_("Import acantomical labels"))
    #     dlg.SetWildcard(WILDCARD_NIFTI)
    if id_type == const.ID_PARREC_IMPORT:
        dlg.SetMessage(_("Import PAR/REC file"))
        dlg.SetWildcard(WILDCARD_PARREC)
    elif id_type == const.ID_ANALYZE_IMPORT:
        dlg.SetMessage(_("Import Analyze 7.5 file"))
        dlg.SetWildcard(WILDCARD_ANALYZE)

    # inv3 filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # GetPath returns in unicode, if a path has non-ascii characters a
            # UnicodeEncodeError is raised. To avoid this, path is encoded in utf-8
            if sys.platform == "win32":
                filename = dlg.GetPath()
            else:
                filename = dlg.GetPath().encode("utf-8")

    except wx.PyAssertionError:  # TODO: error win64
        if dlg.GetPath():
            filename = dlg.GetPath()

    if filename:
        last_directory = os.path.split(dlg.GetPath())[0]
        session.SetConfig("last_directory_%d" % id_type, last_directory)

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    return filename


def ShowImportMeshFilesDialog() -> Optional[str]:
    from invesalius.data.slice_ import Slice

    # Default system path
    current_dir = os.path.abspath(".")

    session = ses.Session()
    last_directory = session.GetConfig("last_directory_surface_import", "")

    dlg_message = _("Import surface file")
    dlg_style = wx.FD_OPEN | wx.FD_CHANGE_DIR

    if Slice().has_affine():
        dlg = FileSelectionDialog(
            title=dlg_message, default_dir=last_directory, wildcard=WILDCARD_MESH_FILES
        )
        conversion_radio_box = wx.RadioBox(
            dlg,
            -1,
            _("File coordinate space"),
            choices=const.SURFACE_SPACE_CHOICES,
            style=wx.RA_SPECIFY_ROWS,
        )
        dlg.sizer.Add(conversion_radio_box, 0, wx.LEFT)
        dlg.FitSizers()
    else:
        dlg = wx.FileDialog(
            None,
            message=dlg_message,
            defaultDir=last_directory,
            wildcard=WILDCARD_MESH_FILES,
            style=dlg_style,
        )
        # stl filter is default
        dlg.SetFilterIndex(0)
        conversion_radio_box = None

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            if conversion_radio_box is not None:
                convert_to_inv = conversion_radio_box.GetSelection() == const.SURFACE_SPACE_WORLD
                Publisher.sendMessage("Update convert_to_inv flag", convert_to_inv=convert_to_inv)

    except wx.PyAssertionError:  # TODO: error win64
        if dlg.GetPath():
            filename = dlg.GetPath()

    if filename:
        session.SetConfig("last_directory_surface_import", os.path.split(filename)[0])

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filename


def ImportMeshCoordSystem() -> bool:
    msg = _("Was the imported mesh created by InVesalius?")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.YES_NO)

    if dlg.ShowModal() == wx.ID_YES:
        flag = False
    else:
        flag = True

    dlg.Destroy()
    return flag


def ShowSaveAsProjectDialog(default_filename: str) -> Tuple[Optional[str], bool]:
    current_dir = os.path.abspath(".")

    session = ses.Session()
    last_directory = session.GetConfig("last_directory_inv3", "")

    dlg = wx.FileDialog(
        None,
        _("Save project as..."),  # title
        last_directory,  # last used directory
        default_filename,
        WILDCARD_INV_SAVE,
        wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
    )
    # dlg.SetFilterIndex(0) # default is VTI

    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
    except wx.PyAssertionError:  # TODO: fix win64
        filename = dlg.GetPath()

    if filename is not None:
        extension = "inv3"
        if sys.platform != "win32":
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension

    if filename:
        last_directory = os.path.split(filename)[0]
        session.SetConfig("last_directory_inv3", last_directory)

    wildcard = dlg.GetFilterIndex()
    os.chdir(current_dir)
    return filename, wildcard == INV_COMPRESSED


def ShowLoadCSVDebugEfield(
    message: str = _("Load debug CSV Enorm file"),
    current_dir: "str | bytes | os.PathLike[str]" = os.path.abspath("."),
    style: int = wx.FD_OPEN | wx.FD_CHANGE_DIR,
    wildcard: str = _("(*.csv)|*.csv"),
    default_filename: str = "",
) -> Optional[np.ndarray]:
    dlg = wx.FileDialog(
        None,
        message=message,
        defaultDir="",
        defaultFile=default_filename,
        wildcard=wildcard,
        style=style,
    )

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # GetPath returns in unicode, if a path has non-ascii characters a
            # UnicodeEncodeError is raised. To avoid this, path is encoded in utf-8
            if sys.platform == "win32":
                filepath = dlg.GetPath()
            else:
                filepath = dlg.GetPath().encode("utf-8")

    except wx.PyAssertionError:  # TODO: error win64
        if dlg.GetPath():
            filepath = dlg.GetPath()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    if filepath:
        with open(filepath) as file:
            my_reader = csv.reader(file, delimiter=",")
            rows = []
            for row in my_reader:
                rows.append(row)
        e_field = rows
        e_field_norms = np.array(e_field).astype(float)

        return e_field_norms
    else:
        return None


def ShowLoadSaveDialog(
    message: str = _("Load File"),
    current_dir: "str | bytes | os.PathLike[str]" = os.path.abspath("."),
    style: int = wx.FD_OPEN | wx.FD_CHANGE_DIR,
    wildcard: str = _("Registration files (*.obr)|*.obr"),
    default_filename: str = "",
    save_ext: Optional[str] = None,
) -> Optional[str]:
    dlg = wx.FileDialog(
        None,
        message=message,
        defaultDir="",
        defaultFile=default_filename,
        wildcard=wildcard,
        style=style,
    )

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None

    try:
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            filepath = dlg.GetPath()
    except wx.PyAssertionError:  # FIX: win64
        filepath = dlg.GetPath()

    # Change the extension if it was set to a value different than expected.
    if save_ext and filepath is not None:
        extension = save_ext
        if sys.platform != "win32":
            if filepath.split(".")[-1] != extension:
                filepath = filepath + "." + extension

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)

    return filepath


def LoadConfigEfield() -> Optional[str]:
    # Default system path
    current_dir = os.path.abspath(".")

    session = ses.Session()
    last_directory = session.GetConfig("last_directory_surface_import", "")

    dlg = wx.FileDialog(
        None,
        message=_("Import json file"),
        defaultDir=last_directory,
        wildcard=WILDCARD_JSON_FILES,
        style=wx.FD_OPEN | wx.FD_CHANGE_DIR,
    )

    # stl filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()

    except wx.PyAssertionError:  # TODO: error win64
        if dlg.GetPath():
            filename = dlg.GetPath()

    if filename:
        session.SetConfig("last_directory_surface_import", os.path.split(filename)[0])

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filename


class MessageDialog(wx.Dialog):
    def __init__(self, message: str):
        wx.Dialog.__init__(
            self,
            None,
            -1,
            "InVesalius 3",
            size=(360, 370),
            pos=wx.DefaultPosition,
            style=wx.DEFAULT_DIALOG_STYLE | wx.ICON_INFORMATION,
        )

        # Static text which contains message to user
        label = wx.StaticText(self, -1, message)

        # Buttons
        btn_yes = wx.Button(self, wx.ID_YES)
        btn_yes.SetHelpText("")
        btn_yes.SetDefault()

        btn_no = wx.Button(self, wx.ID_NO)
        btn_no.SetHelpText("")

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_yes)
        btnsizer.AddButton(btn_cancel)
        btnsizer.AddButton(btn_no)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Centre()


class UpdateMessageDialog(wx.Dialog):
    def __init__(self, url: str):
        msg = _(
            "A new version of InVesalius is available. Do you want to open the download website now?"
        )
        title = _("Invesalius Update")
        self.url = url

        wx.Dialog.__init__(
            self,
            None,
            -1,
            title,
            size=(360, 370),
            pos=wx.DefaultPosition,
            style=wx.DEFAULT_DIALOG_STYLE | wx.ICON_INFORMATION,
        )

        # Static text which contains message to user
        label = wx.StaticText(self, -1, msg)

        # Buttons
        btn_yes = wx.Button(self, wx.ID_YES)
        btn_yes.SetHelpText("")
        btn_yes.SetDefault()

        btn_no = wx.Button(self, wx.ID_NO)
        btn_no.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_yes)
        btnsizer.AddButton(btn_no)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Centre()

        btn_yes.Bind(wx.EVT_BUTTON, self._OnYes)
        btn_no.Bind(wx.EVT_BUTTON, self._OnNo)

        # Subscribing to the pubsub event which happens when InVesalius is closed.
        Publisher.subscribe(self._Exit, "Exit")

    def _OnYes(self, evt: wx.CommandEvent) -> None:
        # Launches the default browser with the url to download the new
        # InVesalius version.
        wx.LaunchDefaultBrowser(self.url)
        self.Close()
        self.Destroy()

    def _OnNo(self, evt: wx.CommandEvent) -> None:
        # Closes and destroy this dialog.
        self.Close()
        self.Destroy()

    def _Exit(self) -> None:
        # Closes and destroy this dialog.
        self.Close()
        self.Destroy()


class MessageBox(wx.Dialog):
    def __init__(
        self, parent: wx.Window, title: str, message: str, caption: str = "InVesalius3 Error"
    ):
        wx.Dialog.__init__(
            self, parent, title=caption, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        title_label = wx.StaticText(self, -1, title)

        text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        text.SetValue(message)
        text.SetBackgroundColour(wx.SystemSettings.GetColour(4))

        width, height = text.GetTextExtent("O" * 30)
        text.SetMinSize((width, -1))

        btn_ok = wx.Button(self, wx.ID_OK)
        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_label, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(text, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Center()
        self.ShowModal()


class ErrorMessageBox(wx.Dialog):
    def __init__(
        self,
        parent: Optional[wx.Window],
        title: str,
        message: str,
        caption: str = "InVesalius3 Error",
    ):
        wx.Dialog.__init__(
            self, parent, title=caption, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        title_label = wx.StaticText(self, -1, title)
        title_width, title_height = title_label.GetSize()

        icon = wx.ArtProvider.GetBitmap(
            wx.ART_ERROR, wx.ART_MESSAGE_BOX, (title_height * 2, title_height * 2)
        )
        bmp = wx.StaticBitmap(self, -1, icon)

        text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        text.SetValue(message)
        text.SetBackgroundColour(wx.SystemSettings.GetColour(4))

        width, height = text.GetTextExtent("M" * 60)
        text.SetMinSize((width, -1))

        btn_ok = wx.Button(self, wx.ID_OK)
        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.Realize()

        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        title_sizer.Add(bmp, 0, wx.ALL | wx.EXPAND, 5)
        title_sizer.Add(title_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(text, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(btnsizer, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Center()


def SaveChangesDialog__Old(filename: str) -> Literal[-1, 0, 1]:
    message = _("The project %s has been modified.\nSave changes?") % filename
    dlg = MessageDialog(message)

    answer = dlg.ShowModal()
    dlg.Destroy()
    if answer == wx.ID_YES:
        return 1
    elif answer == wx.ID_NO:
        return 0
    else:
        return -1


def ImportEmptyDirectory(dirpath: bytes) -> None:
    msg = _("%s is an empty folder.") % dirpath.decode("utf-8")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ImportOldFormatInvFile() -> None:
    msg = _(
        "File was created in a newer InVesalius version. Some functionalities may not work correctly."
    )
    dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ImportInvalidFiles(ftype: str = "DICOM") -> None:
    if ftype == "Bitmap":
        msg = _("There are no Bitmap, JPEG, PNG or TIFF files in the selected folder.")
    elif ftype == "DICOM":
        msg = _("There are no DICOM files in the selected folder.")
    else:
        msg = _("Invalid file.")

    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def WarningRescalePixelValues() -> None:
    msg1 = _("Warning! Pixel values are smaller than 8 (possible float values).\n")
    msg2 = _("Pixel values have been rescaled from 0-255 for compatibility.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg1 + msg2, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg1 + msg2, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ImagePixelRescaling() -> None:
    msg1 = _("Warning! InVesalius has limited support to Analyze format.\n")
    msg2 = _("Slices may be wrongly oriented and functions may not work properly.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg1 + msg2, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg1 + msg2, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def InexistentMask() -> None:
    msg = _("A mask is needed to create a surface.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def MaskSelectionRequiredForRemoval() -> None:
    msg = _("No mask was selected for removal.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def SurfaceSelectionRequiredForRemoval() -> None:
    msg = _("No surface was selected for removal.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def MeasureSelectionRequiredForRemoval() -> None:
    msg = _("No measure was selected for removal.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def MaskSelectionRequiredForDuplication() -> None:
    msg = _("No mask was selected for duplication.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def SurfaceSelectionRequiredForDuplication() -> None:
    msg = _("No surface was selected for duplication.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


# Dialogs for neuronavigation mode
# ----------------------------------


def ShowNavigationTrackerWarning(trck_id: int, lib_mode: str) -> None:
    """
    Spatial Tracker connection error
    """
    trck = {
        const.SELECT: "Tracker",
        const.MTC: "Claron MicronTracker",
        const.FASTRAK: "Polhemus FASTRAK",
        const.ISOTRAKII: "Polhemus ISOTRAK",
        const.PATRIOT: "Polhemus PATRIOT",
        const.CAMERA: "CAMERA",
        const.POLARIS: "NDI Polaris",
        const.POLARISP4: "NDI Polaris P4",
        const.OPTITRACK: "Optitrack",
        const.DEBUGTRACKRANDOM: "Debug tracker device (random)",
        const.DEBUGTRACKAPPROACH: "Debug tracker device (approach)",
    }

    if lib_mode == "choose":
        msg = _("No tracking device selected")
    elif lib_mode == "probe marker not visible":
        msg = _("Probe marker is not visible.")
    elif lib_mode == "coil marker not visible":
        msg = _("Coil marker is not visible.")
    elif lib_mode == "head marker not visible":
        msg = _("Head marker is not visible.")
    elif lib_mode == "error":
        msg = trck[trck_id] + _(" is not installed.")
    elif lib_mode == "disconnect":
        msg = trck[trck_id] + _(" disconnected.")
    else:
        msg = trck[trck_id] + _(" is not connected.")

    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(
            None, msg, "InVesalius 3 - Neuronavigator", wx.ICON_INFORMATION | wx.OK
        )

    dlg.ShowModal()
    dlg.Destroy()


def Efield_connection_warning() -> None:
    msg = _("No connection to E-field library")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(
            None, msg, "InVesalius 3 - Neuronavigator", wx.ICON_INFORMATION | wx.OK
        )
    dlg.ShowModal()
    dlg.Destroy()


def Efield_no_data_to_save_warning() -> None:
    msg = _("No Efield data to save")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(
            None, msg, "InVesalius 3 - Neuronavigator", wx.ICON_INFORMATION | wx.OK
        )
    dlg.ShowModal()
    dlg.Destroy()


def Efield_debug_Enorm_warning() -> None:
    msg = _("The CSV Enorm file is not loaded.")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(
            None, msg, "InVesalius 3 - Neuronavigator", wx.ICON_INFORMATION | wx.OK
        )
    dlg.ShowModal()
    dlg.Destroy()


def ICPcorregistration(fre: float) -> bool:
    msg = (
        _("The fiducial registration error is: ")
        + str(round(fre, 2))
        + "\n\n"
        + _("Would you like to improve accuracy?")
    )
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.YES_NO)

    if dlg.ShowModal() == wx.ID_YES:
        flag = True
    else:
        flag = False

    dlg.Destroy()
    return flag


def ReportICPerror(prev_error: float, final_error: float) -> None:
    msg = (
        _("Points to scalp distance: ")
        + str(round(final_error, 2))
        + " mm"
        + "\n\n"
        + _("Distance before refine: ")
        + str(round(prev_error, 2))
        + " mm"
    )
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ReportICPPointError() -> None:
    msg = (
        _("The last point is more than 20 mm away from the surface")
        + "\n\n"
        + _("Please, create a new point.")
    )
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ReportICPDistributionError() -> None:
    msg = (
        _("The distribution of the transformed points looks wrong.")
        + "\n\n"
        + _("It is recommended to remove the points and redone the acquisition")
    )
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ShowEnterMarkerID(default: str) -> str:
    msg = _("Change label")
    dlg = wx.TextEntryDialog(None, msg, "InVesalius 3", value=default)
    dlg.ShowModal()
    result = dlg.GetValue()
    dlg.Destroy()

    return result


def ShowEnterMEPValue(default):
    msg = _("Enter the MEP value (uV)")
    if sys.platform == "darwin":
        dlg = wx.TextEntryDialog(None, "", msg, defaultValue=default)
    else:
        dlg = wx.TextEntryDialog(None, msg, "InVesalius 3", value=default)
    dlg.ShowModal()
    result = dlg.GetValue()
    # check if the value is a number
    try:
        result = float(result)
    except ValueError:
        result = None
    # if the value is not a number, raise error message
    if result is None:
        msg = _("The value entered is not a number.")
        if sys.platform == "darwin":
            dlg_warn = wx.MessageDialog(None, "", msg, wx.OK)
        else:
            dlg_warn = wx.MessageDialog(None, msg, "InVesalius 3", wx.OK)
        dlg_warn.ShowModal()
        dlg_warn.Destroy()

    dlg.Destroy()

    return result


def ShowConfirmationDialog(msg: str = _("Proceed?")) -> int:
    # msg = _("Do you want to delete all markers?")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.OK | wx.CANCEL | wx.ICON_QUESTION)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
    result = dlg.ShowModal()
    dlg.Destroy()
    return result


def ShowColorDialog(
    color_current: "ColourType",
) -> Optional[Tuple[int, int, int]]:
    cdata = wx.ColourData()
    cdata.SetColour(wx.Colour(color_current))
    dlg = wx.ColourDialog(None, data=cdata)
    dlg.GetColourData().SetChooseFull(True)

    if dlg.ShowModal() == wx.ID_OK:
        color_new = dlg.GetColourData().GetColour().Get(includeAlpha=False)
    else:
        color_new = None

    dlg.Destroy()
    return color_new


# ----------------------------------


class NewMask(wx.Dialog):
    def __init__(
        self,
        parent: Optional[wx.Window] = None,
        ID: int = -1,
        title: str = "InVesalius 3",
        size: wx.Size = wx.DefaultSize,
        pos: wx.Point = wx.DefaultPosition,
        style: int = wx.DEFAULT_DIALOG_STYLE,
        useMetal: bool = False,
    ):
        import invesalius.constants as const
        import invesalius.data.mask as mask
        import invesalius.project as prj

        wx.Dialog.__init__(self, parent, ID, title, pos, style=style)
        self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)

        self.CenterOnScreen()

        # This extra style can be set after the UI object has been created.
        if "wxMac" in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # LINE 1: Surface name

        label_mask = wx.StaticText(self, -1, _("New mask name:"))

        default_name = const.MASK_NAME_PATTERN % (mask.Mask.general_index + 2)
        text = wx.TextCtrl(self, -1, "", size=(80, -1))
        text.SetHelpText(_("Name the mask to be created"))
        text.SetValue(default_name)
        self.text = text

        # LINE 2: Threshold of reference

        # Informative label
        label_thresh = wx.StaticText(self, -1, _("Threshold preset:"))

        # Retrieve existing masks
        project = prj.Project()
        thresh_list = sorted(project.threshold_modes.keys())
        default_index = thresh_list.index(_("Bone"))
        self.thresh_list = thresh_list

        # Mask selection combo
        combo_thresh = wx.ComboBox(
            self, -1, "", choices=self.thresh_list, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        combo_thresh.SetSelection(default_index)
        if sys.platform != "win32":
            combo_thresh.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_thresh = combo_thresh

        # LINE 3: Gradient
        bound_min, bound_max = project.threshold_range
        thresh_min, thresh_max = project.threshold_modes[_("Bone")]
        original_colour = random.choice(const.MASK_COLOUR)
        self.colour = original_colour
        colour = [255 * i for i in original_colour]
        colour.append(100)
        gradient = grad.GradientCtrl(
            self, -1, int(bound_min), int(bound_max), int(thresh_min), int(thresh_max), colour
        )
        self.gradient = gradient

        # OVERVIEW
        # Sizer that joins content above
        flag_link = wx.EXPAND | wx.GROW | wx.ALL
        flag_button = wx.ALL | wx.EXPAND | wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=10, vgap=10)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany(
            [
                (label_mask, 1, flag_link, 5),
                (text, 1, flag_button, 2),
                (label_thresh, 1, flag_link, 5),
                (combo_thresh, 0, flag_button, 1),
            ]
        )  # ,
        # (label_quality, 1, flag_link, 5),
        # (combo_quality, 0, flag_button, 1)])

        # LINE 6: Buttons

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        # OVERVIEW
        # Merge all sizers and checkboxes
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fixed_sizer, 0, wx.ALL | wx.GROW | wx.EXPAND, 15)
        sizer.Add(gradient, 0, wx.BOTTOM | wx.RIGHT | wx.LEFT | wx.EXPAND | wx.GROW, 20)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.BOTTOM, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.Bind(grad.EVT_THRESHOLD_CHANGED, self.OnSlideChanged, self.gradient)
        self.combo_thresh.Bind(wx.EVT_COMBOBOX, self.OnComboThresh)

    def OnComboThresh(self, evt: wx.CommandEvent) -> None:
        import invesalius.project as prj

        proj = prj.Project()
        (thresh_min, thresh_max) = proj.threshold_modes[evt.GetString()]
        self.gradient.SetMinValue(thresh_min)
        self.gradient.SetMaxValue(thresh_max)

    def OnSlideChanged(self, evt: wx.Event) -> None:
        import invesalius.project as prj

        thresh_min = self.gradient.GetMinValue()
        thresh_max = self.gradient.GetMaxValue()
        thresh = (thresh_min, thresh_max)
        proj = prj.Project()
        if thresh in proj.threshold_modes.values():
            preset_name = proj.threshold_modes.get_key(thresh)[0]
            index = self.thresh_list.index(preset_name)
            self.combo_thresh.SetSelection(index)
        else:
            index = self.thresh_list.index(_("Custom"))
            self.combo_thresh.SetSelection(index)

    def GetValue(self) -> Tuple[str, List[int], List[float]]:
        # mask_index = self.combo_mask.GetSelection()
        mask_name = self.text.GetValue()
        thresh_value = [self.gradient.GetMinValue(), self.gradient.GetMaxValue()]
        # quality = const.SURFACE_QUALITY_LIST[self.combo_quality.GetSelection()]
        # fill_holes = self.check_box_holes.GetValue()
        # keep_largest = self.check_box_largest.GetValue()
        # return (mask_index, surface_name, quality, fill_holes, keep_largest)
        return mask_name, thresh_value, self.colour


def InexistentPath(path: "str | bytes | os.PathLike[str]") -> None:
    msg = _("%s does not exist.") % (path)
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def MissingFilesForReconstruction() -> None:
    msg = _("Please, provide more than one DICOM file for 3D reconstruction")
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def SaveChangesDialog(filename: "str | bytes | os.PathLike[str]", parent) -> Literal[-1, 0, 1]:
    current_dir = os.path.abspath(".")
    msg = _("The project %s has been modified.\nSave changes?") % filename
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_QUESTION | wx.YES_NO | wx.CANCEL)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_QUESTION | wx.YES_NO | wx.CANCEL)

    try:
        answer = dlg.ShowModal()
    except wx.PyAssertionError:  # TODO: FIX win64
        answer = wx.ID_YES

    dlg.Destroy()
    os.chdir(current_dir)

    if answer == wx.ID_YES:
        return 1
    elif answer == wx.ID_NO:
        return 0
    else:
        return -1


def SaveChangesDialog2(filename: "str | bytes | os.PathLike[str]") -> Literal[0, 1]:
    current_dir = os.path.abspath(".")
    msg = _("The project %s has been modified.\nSave changes?") % filename
    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.ICON_QUESTION | wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_QUESTION | wx.YES_NO)

    answer = dlg.ShowModal()
    dlg.Destroy()
    os.chdir(current_dir)
    if answer == wx.ID_YES:
        return 1
    else:  # answer == wx.ID_NO:
        return 0


def ShowAboutDialog(parent: wx.Window) -> None:
    info = AboutDialogInfo()
    info.Name = "InVesalius"
    info.Version = const.INVESALIUS_VERSION

    year = datetime.date.today().year

    info.Copyright = _(
        "(c) 2007-" + str(year) + " Center for Information Technology Renato Archer - CTI"
    )
    info.Description = wordwrap(
        _(
            "InVesalius is a medical imaging program for 3D reconstruction. It uses a sequence of 2D DICOM image files acquired with CT or MRI scanners. InVesalius allows exporting 3D volumes or surfaces as mesh files for creating physical models of a patient's anatomy using additive manufacturing (3D printing) technologies. The software is developed by Center for Information Technology Renato Archer (CTI), National Council for Scientific and Technological Development (CNPq) and the Brazilian Ministry of Health.\n\n InVesalius must be used only for research. The Center for Information Technology Renato Archer is not responsible for damages caused by the use of this software.\n\n Contact: invesalius@cti.gov.br"
        ),
        350,
        wx.ClientDC(parent),
    )

    #       _("InVesalius is a software for medical imaging 3D reconstruction. ")+\
    #       _("Its input is a sequency of DICOM 2D image files acquired with CT or MR.\n\n")+\
    #       _("The software also allows generating correspondent STL files,")+\
    #       _("so the user can print 3D physical models of the patient's anatomy ")+\
    #       _("using Rapid Prototyping."), 350, wx.ClientDC(parent))

    icon = wx.Icon(os.path.join(inv_paths.ICON_DIR, "invesalius_64x64.ico"), wx.BITMAP_TYPE_ICO)

    info.SetWebSite("https://www.cti.gov.br/invesalius")
    info.SetIcon(icon)

    info.License = _("GNU GPL (General Public License) version 2")

    info.Developers = [
        "Paulo Henrique Junqueira Amorim",
        "Thiago Franco de Moraes",
        "Hélio Pedrini",
        "Jorge Vicente Lopes da Silva",
        "Victor Hugo de Oliveira e Souza (navigator)",
        "Renan Hiroshi Matsuda (navigator)",
        "André Salles Cunha Peres (navigator)",
        "Oswaldo Baffa Filho (navigator)",
        "Tatiana Al-Chueyr (former)",
        "Guilherme Cesar Soares Ruppert (former)",
        "Fabio de Souza Azevedo (former)",
        "Bruno Lara Bottazzini (contributor)",
        "Olly Betts (patches to support wxPython3)",
    ]

    info.Translators = [
        "Alex P. Natsios",
        "Alicia Perez",
        "Anderson Antonio Mamede da Silva",
        "Andreas Loupasakis",
        "Angelo Pucillo",
        "Annalisa Manenti",
        "Baymuratova Irina",
        "Cheng-Chia Tseng",
        "Dan",
        "DCamer",
        "Dimitris Glezos",
        "Eugene Liscio",
        "Frédéric Lopez",
        "Florin Putura",
        "Fri",
        "Jangblue",
        "Javier de Lima Moreno",
        "Kensey Okinawa",
        "Maki Sugimoto",
        "Mario Regino Moreno Guerra",
        "Massimo Crisantemo",
        "Nikolai Guschinsky",
        "Nikos Korkakakis",
        "Raul Bolliger Neto",
        "Sebastian Hilbert",
        "Semarang Pari",
        "Silvério Santos",
        "Vasily Shishkin",
        "Yohei Sotsuka",
        "Yoshihiro Sato",
    ]

    # info.DocWriters = ["Fabio Francisco da Silva (PT)"]

    info.Artists = ["Otavio Henrique Junqueira Amorim"]

    # Then we call AboutBox providing its info object
    AboutBox(info)


def ShowSavePresetDialog(default_filename: str = "raycasting") -> Optional[str]:
    dlg = wx.TextEntryDialog(None, _("Save raycasting preset as:"), "InVesalius 3")
    # dlg.SetFilterIndex(0) # default is VTI
    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetValue()
    except wx.PyAssertionError:
        filename = dlg.GetValue()

    return filename


class NewSurfaceDialog(wx.Dialog):
    def __init__(
        self,
        parent: Optional[wx.Window] = None,
        ID: int = -1,
        title: str = "InVesalius 3",
        size: wx.Size = wx.DefaultSize,
        pos: wx.Point = wx.DefaultPosition,
        style: int = wx.DEFAULT_DIALOG_STYLE,
        useMetal: bool = False,
    ):
        import invesalius.constants as const
        import invesalius.data.surface as surface
        import invesalius.project as prj

        wx.Dialog.__init__(self, parent, ID, title, pos, (500, 300), style)
        self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)

        self.CenterOnScreen()

        # This extra style can be set after the UI object has been created.
        if "wxMac" in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # LINE 1: Surface name

        label_surface = wx.StaticText(self, -1, _("New surface name:"))

        default_name = const.SURFACE_NAME_PATTERN % (surface.Surface.general_index + 2)
        text = wx.TextCtrl(self, -1, "", size=(80, -1))
        text.SetHelpText(_("Name the surface to be created"))
        text.SetValue(default_name)
        self.text = text

        # LINE 2: Mask of reference

        # Informative label
        label_mask = wx.StaticText(self, -1, _("Mask of reference:"))

        # Retrieve existing masks
        project = prj.Project()
        index_list = sorted(project.mask_dict.keys())
        self.mask_list = [project.mask_dict[index].name for index in index_list]

        # Mask selection combo
        combo_mask = wx.ComboBox(
            self, -1, "", choices=self.mask_list, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        combo_mask.SetSelection(len(self.mask_list) - 1)
        if sys.platform != "win32":
            combo_mask.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_mask = combo_mask

        # LINE 3: Surface quality
        label_quality = wx.StaticText(self, -1, _("Surface quality:"))

        choices = const.SURFACE_QUALITY_LIST
        style = wx.CB_DROPDOWN | wx.CB_READONLY
        combo_quality = wx.ComboBox(self, -1, "", choices=choices, style=style)
        combo_quality.SetSelection(3)
        if sys.platform != "win32":
            combo_quality.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_quality = combo_quality

        # OVERVIEW
        # Sizer that joins content above
        flag_link = wx.EXPAND | wx.GROW | wx.ALL
        flag_button = wx.ALL | wx.EXPAND | wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=10, vgap=0)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany(
            [
                (label_surface, 1, flag_link, 5),
                (text, 1, flag_button, 2),
                (label_mask, 1, flag_link, 5),
                (combo_mask, 0, flag_button, 1),
                (label_quality, 1, flag_link, 5),
                (combo_quality, 0, flag_button, 1),
            ]
        )

        # LINES 4 and 5: Checkboxes
        check_box_holes = wx.CheckBox(self, -1, _("Fill holes"))
        check_box_holes.SetValue(True)
        self.check_box_holes = check_box_holes
        check_box_largest = wx.CheckBox(self, -1, _("Keep largest region"))
        self.check_box_largest = check_box_largest

        # LINE 6: Buttons

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        # OVERVIEW
        # Merge all sizers and checkboxes
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fixed_sizer, 0, wx.TOP | wx.RIGHT | wx.LEFT | wx.GROW | wx.EXPAND, 20)
        sizer.Add(check_box_holes, 0, wx.RIGHT | wx.LEFT, 30)
        sizer.Add(check_box_largest, 0, wx.RIGHT | wx.LEFT, 30)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def GetValue(self) -> Tuple[int, str, str, bool, bool]:
        mask_index = self.combo_mask.GetSelection()
        surface_name = self.text.GetValue()
        quality = const.SURFACE_QUALITY_LIST[self.combo_quality.GetSelection()]
        fill_holes = self.check_box_holes.GetValue()
        keep_largest = self.check_box_largest.GetValue()
        return (mask_index, surface_name, quality, fill_holes, keep_largest)


def ExportPicture(type_: str = "") -> Union[Tuple[str, wx.WindowIDRef], Tuple[()]]:
    import invesalius.constants as const
    import invesalius.project as proj

    INDEX_TO_EXTENSION = {0: "bmp", 1: "jpg", 2: "png", 3: "ps", 4: "povray", 5: "tiff"}
    WILDCARD_SAVE_PICTURE = (
        _("BMP image")
        + " (*.bmp)|*.bmp|"
        + _("JPG image")
        + " (*.jpg)|*.jpg|"
        + _("PNG image")
        + " (*.png)|*.png|"
        + _("PostScript document")
        + " (*.ps)|*.ps|"
        + _("POV-Ray file")
        + " (*.pov)|*.pov|"
        + _("TIFF image")
        + " (*.tif)|*.tif"
    )

    INDEX_TO_TYPE = {
        0: const.FILETYPE_BMP,
        1: const.FILETYPE_JPG,
        2: const.FILETYPE_PNG,
        3: const.FILETYPE_PS,
        4: const.FILETYPE_POV,
        5: const.FILETYPE_TIF,
    }

    utils.debug("ExportPicture")
    project = proj.Project()

    session = ses.Session()
    last_directory = session.GetConfig("last_directory_screenshot", "")

    project_name = f"{project.name}_{type_}"
    if sys.platform not in ("win32", "linux2", "linux"):
        project_name += ".jpg"

    dlg = wx.FileDialog(
        None,
        f"Save {type_} picture as...",
        last_directory,  # last used directory
        project_name,  # filename
        WILDCARD_SAVE_PICTURE,
        wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
    )
    dlg.SetFilterIndex(1)  # default is VTI

    if dlg.ShowModal() == wx.ID_OK:
        filetype_index = dlg.GetFilterIndex()
        filetype = INDEX_TO_TYPE[filetype_index]
        extension = INDEX_TO_EXTENSION[filetype_index]
        filename = dlg.GetPath()

        last_directory = os.path.split(filename)[0]
        session.SetConfig("last_directory_screenshot", last_directory)

        if sys.platform != "win32":
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension
        return filename, filetype
    else:
        return ()


class SurfaceDialog(wx.Dialog):
    """
    This dialog is only shown when the mask whose surface will be generate was
    edited. So far, the only options available are the choice of method to
    generate the surface, Binary or `Context aware smoothing', and options from
    `Context aware smoothing'
    """

    def __init__(self):
        wx.Dialog.__init__(self, None, -1, _("Surface generation options"))
        self._build_widgets()
        self.CenterOnScreen()

    def _build_widgets(self) -> None:
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()

        self.ca = SurfaceMethodPanel(self, -1, True)

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_sizer.Add(self.ca, 0, wx.EXPAND | wx.ALL, 5)
        self.main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(self.main_sizer)
        self.Fit()

    def GetOptions(self) -> Dict[str, float]:
        return self.ca.GetOptions()

    def GetAlgorithmSelected(self) -> str:
        return self.ca.GetAlgorithmSelected()


####################### New surface creation dialog ###########################
class SurfaceCreationDialog(wx.Dialog):
    def __init__(
        self,
        parent: Optional[wx.Window] = None,
        ID: int = -1,
        title: str = _("Surface creation"),
        size: wx.Size = wx.DefaultSize,
        pos: wx.Point = wx.DefaultPosition,
        style: int = wx.DEFAULT_DIALOG_STYLE,
        useMetal: bool = False,
        mask_edited: bool = False,
    ):
        wx.Dialog.__init__(self, parent, ID, title, pos, size, style)
        self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        if "wxMac" in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # It's necessary to create a staticbox before is children widgets
        # because otherwise in MacOSX it'll not be possible to use the mouse in
        # static's children widgets.
        sb_nsd = wx.StaticBox(self, -1, _("Surface creation options"))
        self.nsd = SurfaceCreationOptionsPanel(self, -1)
        self.nsd.Bind(EVT_MASK_SET, self.OnSetMask)
        surface_options_sizer = wx.StaticBoxSizer(sb_nsd, wx.VERTICAL)
        surface_options_sizer.Add(self.nsd, 1, wx.EXPAND | wx.ALL, 5)

        sb_ca = wx.StaticBox(self, -1, _("Surface creation method"))
        self.ca = SurfaceMethodPanel(self, -1, mask_edited)
        surface_method_sizer = wx.StaticBoxSizer(sb_ca, wx.VERTICAL)
        surface_method_sizer.Add(self.ca, 1, wx.EXPAND | wx.ALL, 5)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        sizer_panels = wx.BoxSizer(wx.HORIZONTAL)
        sizer_panels.Add(surface_options_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer_panels.Add(surface_method_sizer, 0, wx.EXPAND | wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(sizer_panels, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def OnSetMask(self, evt: MaskEvent) -> None:
        import invesalius.project as proj

        mask = proj.Project().mask_dict[evt.mask_index]
        self.ca.mask_edited = mask.was_edited
        self.ca.ReloadMethodsOptions()

    def GetValue(
        self,
    ) -> "Dict[str, Dict[str, str | Dict[str, float]] | Dict[str, str | int | bool]]":
        return {"method": self.ca.GetValue(), "options": self.nsd.GetValue()}


class SurfaceCreationOptionsPanel(wx.Panel):
    def __init__(self, parent: wx.Window, ID: int = -1):
        import invesalius.constants as const
        import invesalius.data.slice_ as slc
        import invesalius.data.surface as surface
        import invesalius.project as prj

        wx.Panel.__init__(self, parent, ID)

        # LINE 1: Surface name
        label_surface = wx.StaticText(self, -1, _("New surface name:"))

        default_name = const.SURFACE_NAME_PATTERN % (surface.Surface.general_index + 2)
        text = wx.TextCtrl(self, -1, "", size=(80, -1))
        text.SetHelpText(_("Name the surface to be created"))
        text.SetValue(default_name)
        self.text = text

        # LINE 2: Mask of reference

        # Informative label
        label_mask = wx.StaticText(self, -1, _("Mask of reference:"))

        # Retrieve existing masks
        project = prj.Project()
        index_list = project.mask_dict.keys()
        self.mask_list = [project.mask_dict[index].name for index in sorted(index_list)]

        active_mask = 0
        for idx in project.mask_dict:
            if project.mask_dict[idx] is slc.Slice().current_mask:
                active_mask = idx
                break

        # Mask selection combo
        combo_mask = wx.ComboBox(
            self, -1, "", choices=self.mask_list, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        combo_mask.SetSelection(active_mask)
        combo_mask.Bind(wx.EVT_COMBOBOX, self.OnSetMask)
        if sys.platform != "win32":
            combo_mask.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_mask = combo_mask

        # LINE 3: Surface quality
        label_quality = wx.StaticText(self, -1, _("Surface quality:"))

        choices = const.SURFACE_QUALITY_LIST
        style = wx.CB_DROPDOWN | wx.CB_READONLY
        combo_quality = wx.ComboBox(self, -1, "", choices=choices, style=style)
        combo_quality.SetSelection(3)
        if sys.platform != "win32":
            combo_quality.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_quality = combo_quality

        # OVERVIEW
        # Sizer that joins content above
        flag_link = wx.EXPAND | wx.GROW | wx.ALL
        flag_button = wx.ALL | wx.EXPAND | wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=10, vgap=5)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany(
            [
                (label_surface, 1, flag_link, 0),
                (text, 1, flag_button, 0),
                (label_mask, 1, flag_link, 0),
                (combo_mask, 0, flag_button, 0),
                (label_quality, 1, flag_link, 0),
                (combo_quality, 0, flag_button, 0),
            ]
        )

        # LINES 4, 5 and 6: Checkboxes
        check_box_border_holes = wx.CheckBox(self, -1, _("Fill border holes"))
        check_box_border_holes.SetValue(False)
        self.check_box_border_holes = check_box_border_holes
        check_box_holes = wx.CheckBox(self, -1, _("Fill holes"))
        check_box_holes.SetValue(False)
        self.check_box_holes = check_box_holes
        check_box_largest = wx.CheckBox(self, -1, _("Keep largest region"))
        self.check_box_largest = check_box_largest

        # OVERVIEW
        # Merge all sizers and checkboxes
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fixed_sizer, 0, wx.TOP | wx.RIGHT | wx.LEFT | wx.GROW | wx.EXPAND, 5)
        sizer.Add(check_box_border_holes, 0, wx.RIGHT | wx.LEFT, 5)
        sizer.Add(check_box_holes, 0, wx.RIGHT | wx.LEFT, 5)
        sizer.Add(check_box_largest, 0, wx.RIGHT | wx.LEFT, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def OnSetMask(self, evt: wx.CommandEvent) -> None:
        new_evt = MaskEvent(myEVT_MASK_SET, -1, self.combo_mask.GetSelection())
        self.GetEventHandler().ProcessEvent(new_evt)

    def GetValue(self) -> Dict[str, Union[str, int, bool]]:
        mask_index = self.combo_mask.GetSelection()
        surface_name = self.text.GetValue()
        quality = const.SURFACE_QUALITY_LIST[self.combo_quality.GetSelection()]
        fill_border_holes = self.check_box_border_holes.GetValue()
        fill_holes = self.check_box_holes.GetValue()
        keep_largest = self.check_box_largest.GetValue()
        return {
            "index": mask_index,
            "name": surface_name,
            "quality": quality,
            "fill_border_holes": fill_border_holes,
            "fill": fill_holes,
            "keep_largest": keep_largest,
            "overwrite": False,
        }


class SurfaceTransparencyDialog(wx.Dialog):
    def __init__(
        self, parent: Optional[wx.Window], surface_index: int = 0, transparency: int = 0
    ) -> None:
        super().__init__(parent)

        self.surface_index = surface_index

        self.SetTitle("InVesalius 3")
        self.SetSize((300, 180))

        self.slider = wx.Slider(
            self, value=transparency, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL
        )

        self.slider.Bind(wx.EVT_SLIDER, self.on_slider)

        # Current value
        self.value_text = wx.StaticText(
            self, label=f"Surface transparency: {self.slider.GetValue()}%"
        )

        # Buttons
        ok_button = wx.Button(self, wx.ID_OK, label="OK")
        ok_button.Bind(wx.EVT_BUTTON, self.on_ok)

        cancel_button = wx.Button(self, wx.ID_CANCEL, label="Cancel")

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.value_text, 0, wx.ALL | wx.CENTER, 10)
        sizer.Add(self.slider, 0, wx.ALL | wx.EXPAND, 10)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(ok_button, 0, wx.ALL, 5)
        button_sizer.Add(cancel_button, 0, wx.ALL, 5)

        sizer.Add(button_sizer, 0, wx.ALL | wx.CENTER, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()
        self.CenterOnScreen()

    def on_slider(self, event: wx.CommandEvent) -> None:
        value = self.slider.GetValue()
        self.value_text.SetLabel(f"Surface transparency: {value}%")

        Publisher.sendMessage(
            "Set surface transparency", surface_index=self.surface_index, transparency=value / 100.0
        )

    def on_ok(self, event: wx.CommandEvent) -> None:
        self.EndModal(wx.ID_OK)

    def get_value(self) -> int:
        return self.slider.GetValue()


class CAOptions(wx.Panel):
    """
    Options related to Context aware algorithm:
    Angle: The min angle to a vertex to be considered a staircase vertex;
    Max distance: The max distance a normal vertex must be to calculate its
        weighting;
    Min Weighting: The min weight a vertex must have;
    Steps: The number of iterations the smoothing algorithm have to do.
    """

    def __init__(self, parent: wx.Window):
        wx.Panel.__init__(self, parent, -1)
        self._build_widgets()

    def _build_widgets(self) -> None:
        sb = wx.StaticBox(self, -1, _("Options"))
        self.angle = InvFloatSpinCtrl(
            self, -1, value=0.7, min_value=0.0, max_value=1.0, increment=0.1, digits=1
        )

        self.max_distance = InvFloatSpinCtrl(
            self, -1, value=3.0, min_value=0.0, max_value=100.0, increment=0.1, digits=2
        )

        self.min_weight = InvFloatSpinCtrl(
            self, -1, value=0.5, min_value=0.0, max_value=1.0, increment=0.1, digits=1
        )

        self.steps = InvSpinCtrl(self, -1, value=10, min_value=1, max_value=100)

        layout_sizer = wx.FlexGridSizer(rows=4, cols=2, hgap=5, vgap=5)
        layout_sizer.Add(wx.StaticText(self, -1, _("Angle:")), 0, wx.EXPAND)
        layout_sizer.Add(self.angle, 0, wx.EXPAND)
        layout_sizer.Add(wx.StaticText(self, -1, _("Max. distance:")), 0, wx.EXPAND)
        layout_sizer.Add(self.max_distance, 0, wx.EXPAND)
        layout_sizer.Add(wx.StaticText(self, -1, _("Min. weight:")), 0, wx.EXPAND)
        layout_sizer.Add(self.min_weight, 0, wx.EXPAND)
        layout_sizer.Add(wx.StaticText(self, -1, _("N. steps:")), 0, wx.EXPAND)
        layout_sizer.Add(self.steps, 0, wx.EXPAND)

        self.main_sizer = wx.StaticBoxSizer(sb, wx.VERTICAL)
        self.main_sizer.Add(layout_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(self.main_sizer)


class SurfaceMethodPanel(wx.Panel):
    """
    This dialog is only shown when the mask whose surface will be generate was
    edited. So far, the only options available are the choice of method to
    generate the surface, Binary or `Context aware smoothing', and options from
    `Context aware smoothing'
    """

    def __init__(self, parent: wx.Window, id: int, mask_edited: bool = False):
        wx.Panel.__init__(self, parent, id)

        self.mask_edited = mask_edited
        self.alg_types = {
            _("Default"): "Default",
            _("Context aware smoothing"): "ca_smoothing",
            _("Binary"): "Binary",
        }
        self.edited_imp = [
            _("Default"),
        ]

        self._build_widgets()
        self._bind_wx()

    def _build_widgets(self) -> None:
        self.ca_options = CAOptions(self)

        self.cb_types = wx.ComboBox(
            self,
            -1,
            _("Default"),
            choices=[
                i for i in sorted(self.alg_types) if not (self.mask_edited and i in self.edited_imp)
            ],
            style=wx.CB_READONLY,
        )
        w, h = self.cb_types.GetSize()

        icon = wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_MESSAGE_BOX, (h * 0.8, h * 0.8))
        self.bmp = wx.StaticBitmap(self, -1, icon)
        self.bmp.SetToolTip(
            _("It is not possible to use the Default method because the mask was edited.")
        )

        self.method_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.method_sizer.Add(wx.StaticText(self, -1, _("Method:")), 0, wx.EXPAND | wx.ALL, 5)
        self.method_sizer.Add(self.cb_types, 1, wx.EXPAND)
        self.method_sizer.Add(self.bmp, 0, wx.EXPAND | wx.ALL, 5)

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_sizer.Add(self.method_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.main_sizer.Add(self.ca_options, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(self.main_sizer)
        self.Layout()
        self.Fit()

        if self.mask_edited:
            self.cb_types.SetValue(_("Context aware smoothing"))
            self.ca_options.Enable()
            self.method_sizer.Show(self.bmp)
        else:
            self.ca_options.Disable()
            self.method_sizer.Hide(self.bmp)

    def _bind_wx(self) -> None:
        self.cb_types.Bind(wx.EVT_COMBOBOX, self._set_cb_types)

    def _set_cb_types(self, evt: wx.CommandEvent) -> None:
        if self.alg_types[evt.GetString()] == "ca_smoothing":
            self.ca_options.Enable()
        else:
            self.ca_options.Disable()
        evt.Skip()

    def GetAlgorithmSelected(self) -> str:
        return self.alg_types.get(self.cb_types.GetValue(), "Default")

    def GetOptions(self) -> Dict[str, float]:
        if self.GetAlgorithmSelected() == "ca_smoothing":
            options = {
                "angle": self.ca_options.angle.GetValue(),
                "max distance": self.ca_options.max_distance.GetValue(),
                "min weight": self.ca_options.min_weight.GetValue(),
                "steps": self.ca_options.steps.GetValue(),
            }
        else:
            options = {}
        return options

    def GetValue(self) -> Dict[str, Union[str, Dict[str, float]]]:
        algorithm = self.GetAlgorithmSelected()
        options = self.GetOptions()

        return {"algorithm": algorithm, "options": options}

    def ReloadMethodsOptions(self) -> None:
        self.cb_types.Clear()
        self.cb_types.AppendItems(
            [i for i in sorted(self.alg_types) if not (self.mask_edited and i in self.edited_imp)]
        )
        if self.mask_edited:
            self.cb_types.SetValue(_("Context aware smoothing"))
            self.ca_options.Enable()
            self.method_sizer.Show(self.bmp)
        else:
            self.cb_types.SetValue(_("Default"))
            self.ca_options.Disable()
            self.method_sizer.Hide(self.bmp)

        self.method_sizer.Layout()


class ClutImagedataDialog(wx.Dialog):
    def __init__(
        self, histogram: np.ndarray, init: float, end: float, nodes: Optional[List["Node"]] = None
    ):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        self.histogram = histogram
        self.init = init
        self.end = end
        self.nodes = nodes

        self._init_gui()
        self.bind_events()
        self.bind_events_wx()

    def _init_gui(self) -> None:
        self.clut_widget = CLUTImageDataWidget(
            self, -1, self.histogram, self.init, self.end, self.nodes
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.clut_widget, 1, wx.EXPAND)

        self.SetSizer(sizer)
        self.Fit()

    def bind_events_wx(self) -> None:
        self.clut_widget.Bind(EVT_CLUT_NODE_CHANGED, self.OnClutChange)

    def bind_events(self) -> None:
        Publisher.subscribe(self._refresh_widget, "Update clut imagedata widget")

    def OnClutChange(self, evt: "CLUTEvent") -> None:
        Publisher.sendMessage(
            "Change colour table from background image from widget", nodes=evt.GetNodes()
        )
        Publisher.sendMessage(
            "Update window level text",
            window=self.clut_widget.window_width,
            level=self.clut_widget.window_level,
        )

    def _refresh_widget(self) -> None:
        self.clut_widget.Refresh()

    def Show(self, gen_evt: bool = True, show: bool = True) -> None:
        super(wx.Dialog, self).Show(show)
        if gen_evt:
            self.clut_widget._generate_event()


class WatershedOptionsPanel(wx.Panel):
    def __init__(self, parent: wx.Window, config: "WatershedConfig"):
        wx.Panel.__init__(self, parent)

        self.algorithms = ("Watershed", "Watershed IFT")
        self.con2d_choices = (4, 8)
        self.con3d_choices = (6, 18, 26)

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        self.choice_algorithm = wx.RadioBox(
            self, -1, _("Method"), choices=self.algorithms, style=wx.NO_BORDER | wx.HORIZONTAL
        )
        self.choice_algorithm.SetSelection(self.algorithms.index(self.config.algorithm))

        self.choice_2dcon = wx.RadioBox(
            self,
            -1,
            "2D",
            choices=[str(i) for i in self.con2d_choices],
            style=wx.NO_BORDER | wx.HORIZONTAL,
        )
        self.choice_2dcon.SetSelection(self.con2d_choices.index(self.config.con_2d))

        self.choice_3dcon = wx.RadioBox(
            self,
            -1,
            "3D",
            choices=[str(i) for i in self.con3d_choices],
            style=wx.NO_BORDER | wx.HORIZONTAL,
        )
        self.choice_3dcon.SetSelection(self.con3d_choices.index(self.config.con_3d))

        self.gaussian_size = InvSpinCtrl(
            self, -1, value=self.config.mg_size, min_value=1, max_value=10
        )

        box_sizer = wx.StaticBoxSizer(wx.StaticBox(self, -1, "Conectivity"), wx.VERTICAL)
        box_sizer.Add(self.choice_2dcon, 0, wx.ALL, 5)
        box_sizer.Add(self.choice_3dcon, 0, wx.ALL, 5)

        g_sizer = wx.BoxSizer(wx.HORIZONTAL)
        g_sizer.Add(wx.StaticText(self, -1, _("Gaussian sigma")), 0, wx.ALIGN_CENTER | wx.ALL, 5)
        g_sizer.Add(self.gaussian_size, 0, wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.choice_algorithm, 0, wx.ALL, 5)
        sizer.Add(box_sizer, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(g_sizer, 0, wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def apply_options(self) -> None:
        self.config.algorithm = self.algorithms[self.choice_algorithm.GetSelection()]
        self.config.con_2d = self.con2d_choices[self.choice_2dcon.GetSelection()]
        self.config.con_3d = self.con3d_choices[self.choice_3dcon.GetSelection()]
        self.config.mg_size = self.gaussian_size.GetValue()


class WatershedOptionsDialog(wx.Dialog):
    def __init__(
        self,
        config: "WatershedConfig",
        ID: int = -1,
        title: str = _("Watershed"),
        style: int = wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
    ):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        wop = WatershedOptionsPanel(self, self.config)
        self.wop = wop

        sizer = wx.BoxSizer(wx.VERTICAL)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        sizer.Add(wop, 0, wx.EXPAND)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.BOTTOM, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.CenterOnScreen()

    def OnOk(self, evt: wx.CommandEvent) -> None:
        self.wop.apply_options()
        evt.Skip()


class MaskBooleanDialog(wx.Dialog):
    def __init__(
        self,
        masks: Dict[int, "Mask"],
        ID: int = -1,
        title: str = _("Boolean operations"),
        style: int = wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
    ):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self._init_gui(masks)
        self.CenterOnScreen()

    def _init_gui(self, masks: Dict[int, "Mask"]) -> None:
        mask_choices = [(masks[i].name, masks[i]) for i in sorted(masks)]
        self.mask1 = wx.ComboBox(self, -1, mask_choices[0][0], choices=[])
        self.mask2 = wx.ComboBox(self, -1, mask_choices[0][0], choices=[])

        for n, m in mask_choices:
            self.mask1.Append(n, m)
            self.mask2.Append(n, m)

        self.mask1.SetSelection(0)

        if len(mask_choices) > 1:
            self.mask2.SetSelection(1)
        else:
            self.mask2.SetSelection(0)

        icon_folder = inv_paths.ICON_DIR
        op_choices = (
            (_("Union"), const.BOOLEAN_UNION, "bool_union.png"),
            (_("Difference"), const.BOOLEAN_DIFF, "bool_difference.png"),
            (_("Intersection"), const.BOOLEAN_AND, "bool_intersection.png"),
            (_("Exclusive disjunction"), const.BOOLEAN_XOR, "bool_disjunction.png"),
        )
        self.op_boolean = BitmapComboBox(self, -1, op_choices[0][0], choices=[])

        for n, i, f in op_choices:
            bmp = wx.Bitmap(os.path.join(icon_folder, f), wx.BITMAP_TYPE_PNG)
            self.op_boolean.Append(n, bmp, i)

        self.op_boolean.SetSelection(0)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        gsizer = wx.FlexGridSizer(rows=3, cols=2, hgap=5, vgap=5)

        gsizer.Add(wx.StaticText(self, -1, _("Mask 1")), 0, wx.ALIGN_CENTER_VERTICAL)
        gsizer.Add(self.mask1, 1, wx.EXPAND)
        gsizer.Add(wx.StaticText(self, -1, _("Operation")), 0, wx.ALIGN_CENTER_VERTICAL)
        gsizer.Add(self.op_boolean, 1, wx.EXPAND)
        gsizer.Add(wx.StaticText(self, -1, _("Mask 2")), 0, wx.ALIGN_CENTER_VERTICAL)
        gsizer.Add(self.mask2, 1, wx.EXPAND)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gsizer, 0, wx.EXPAND | wx.ALL, border=5)
        sizer.Add(btnsizer, 0, wx.EXPAND | wx.ALL, border=5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def OnOk(self, evt: wx.CommandEvent) -> None:
        op = self.op_boolean.GetClientData(self.op_boolean.GetSelection())
        m1 = self.mask1.GetClientData(self.mask1.GetSelection())
        m2 = self.mask2.GetClientData(self.mask2.GetSelection())

        Publisher.sendMessage("Do boolean operation", operation=op, mask1=m1, mask2=m2)
        Publisher.sendMessage("Reload actual slice")
        Publisher.sendMessage("Refresh viewer")

        self.Close()
        self.Destroy()


class ReorientImageDialog(wx.Dialog):
    def __init__(
        self,
        ID: int = -1,
        title: str = _("Image reorientation"),
        style: int = wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
    ):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self._closed = False

        self._last_ax = "0.0"
        self._last_ay = "0.0"
        self._last_az = "0.0"

        self._init_gui()
        self._bind_events()
        self._bind_events_wx()

    def _init_gui(self) -> None:
        interp_methods_choices = (
            (_("Nearest Neighbour"), 0),
            (_("Trilinear"), 1),
            (_("Tricubic"), 2),
            (_("Lanczos (experimental)"), 3),
        )
        self.interp_method = wx.ComboBox(self, -1, choices=[], style=wx.CB_READONLY)
        for txt, im_code in interp_methods_choices:
            self.interp_method.Append(txt, im_code)
        self.interp_method.SetValue(interp_methods_choices[2][0])

        self.anglex = wx.TextCtrl(self, -1, "0.0")
        self.angley = wx.TextCtrl(self, -1, "0.0")
        self.anglez = wx.TextCtrl(self, -1, "0.0")

        self.btnapply = wx.Button(self, -1, _("Apply"))

        sizer = wx.BoxSizer(wx.VERTICAL)

        angles_sizer = wx.FlexGridSizer(3, 2, 5, 5)
        angles_sizer.AddMany(
            [
                (wx.StaticText(self, -1, _("Angle X")), 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5),
                (self.anglex, 0, wx.EXPAND | wx.ALL, 5),
                (wx.StaticText(self, -1, _("Angle Y")), 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5),
                (self.angley, 0, wx.EXPAND | wx.ALL, 5),
                (wx.StaticText(self, -1, _("Angle Z")), 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5),
                (self.anglez, 0, wx.EXPAND | wx.ALL, 5),
            ]
        )

        sizer.Add(
            wx.StaticText(self, -1, _("Interpolation method:")),
            0,
            wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT,
            5,
        )
        sizer.Add(self.interp_method, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(angles_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.btnapply, 0, wx.EXPAND | wx.ALL, 5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        self.Fit()

    def _bind_events(self) -> None:
        Publisher.subscribe(self._update_angles, "Update reorient angles")
        Publisher.subscribe(self._close_dialog, "Close reorient dialog")

    def _bind_events_wx(self) -> None:
        self.interp_method.Bind(wx.EVT_COMBOBOX, self.OnSelect)

        self.anglex.Bind(wx.EVT_KILL_FOCUS, self.OnLostFocus)
        self.angley.Bind(wx.EVT_KILL_FOCUS, self.OnLostFocus)
        self.anglez.Bind(wx.EVT_KILL_FOCUS, self.OnLostFocus)

        self.anglex.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.angley.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.anglez.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)

        self.btnapply.Bind(wx.EVT_BUTTON, self.apply_reorientation)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def _update_angles(self, angles: Tuple[float, float, float]) -> None:
        anglex, angley, anglez = angles
        self.anglex.SetValue(f"{np.rad2deg(anglex):.3f}")
        self.angley.SetValue(f"{np.rad2deg(angley):.3f}")
        self.anglez.SetValue(f"{np.rad2deg(anglez):.3f}")

    def _close_dialog(self) -> None:
        self.Destroy()

    def apply_reorientation(self, evt: wx.CommandEvent) -> None:
        Publisher.sendMessage("Apply reorientation")
        self.Close()

    def OnClose(self, evt: wx.CloseEvent) -> None:
        self._closed = True
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_REORIENT)
        Publisher.sendMessage("Enable style", style=const.STATE_DEFAULT)
        self.Destroy()

    def OnSelect(self, evt: wx.CommandEvent) -> None:
        im_code = self.interp_method.GetClientData(self.interp_method.GetSelection())
        Publisher.sendMessage("Set interpolation method", interp_method=im_code)

    def OnSetFocus(self, evt: wx.FocusEvent) -> None:
        self._last_ax = self.anglex.GetValue()
        self._last_ay = self.angley.GetValue()
        self._last_az = self.anglez.GetValue()

    def OnLostFocus(self, evt: wx.FocusEvent) -> None:
        if not self._closed:
            try:
                ax = np.deg2rad(float(self.anglex.GetValue()))
                ay = np.deg2rad(float(self.angley.GetValue()))
                az = np.deg2rad(float(self.anglez.GetValue()))
            except ValueError:
                self.anglex.SetValue(self._last_ax)
                self.angley.SetValue(self._last_ay)
                self.anglez.SetValue(self._last_az)
                return
            Publisher.sendMessage("Set reorientation angles", angles=(ax, ay, az))


class ImportBitmapParameters(wx.Dialog):
    def __init__(self):
        if sys.platform == "win32":
            size = wx.Size(380, 180)
        else:
            size = wx.Size(380, 210)

        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Create project from bitmap"),
            size=size,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        self.interval: int = 0

        self._init_gui()
        self.bind_evts()
        self.CenterOnScreen()

    def _init_gui(self) -> None:
        import invesalius.project as prj

        p = wx.Panel(
            self, -1, style=wx.TAB_TRAVERSAL | wx.CLIP_CHILDREN | wx.FULL_REPAINT_ON_RESIZE
        )

        gbs_principal = self.gbs = wx.GridBagSizer(4, 1)

        gbs = self.gbs = wx.GridBagSizer(5, 2)

        flag_labels = wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL

        stx_name = wx.StaticText(p, -1, _("Project name:"))
        tx_name = self.tx_name = wx.TextCtrl(p, -1, "InVesalius Bitmap", size=wx.Size(220, -1))

        stx_orientation = wx.StaticText(
            p,
            -1,
            _("Slices orientation:"),
        )
        cb_orientation_options = [_("Axial"), _("Coronal"), _("Sagital")]
        cb_orientation = self.cb_orientation = wx.ComboBox(
            p,
            value="Axial",
            choices=cb_orientation_options,
            size=wx.Size(160, -1),
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )

        stx_spacing = wx.StaticText(p, -1, _("Spacing (mm):"))

        gbs.Add(stx_name, (0, 0), flag=flag_labels)
        gbs.Add(tx_name, (0, 1))
        gbs.Add(0, 0, (1, 0))

        gbs.Add(stx_orientation, (2, 0), flag=flag_labels)
        gbs.Add(cb_orientation, (2, 1))

        gbs.Add(stx_spacing, (3, 0))
        gbs.Add(0, 0, (4, 0))

        # --- spacing --------------
        gbs_spacing = wx.GridBagSizer(2, 6)

        stx_spacing_x = stx_spacing_x = wx.StaticText(p, -1, _("X:"))
        fsp_spacing_x = self.fsp_spacing_x = InvFloatSpinCtrl(
            p, -1, min_value=0, max_value=1000000000, increment=0.25, value=1.0, digits=8
        )

        stx_spacing_y = stx_spacing_y = wx.StaticText(p, -1, _("Y:"))
        fsp_spacing_y = self.fsp_spacing_y = InvFloatSpinCtrl(
            p, -1, min_value=0, max_value=1000000000, increment=0.25, value=1.0, digits=8
        )

        stx_spacing_z = stx_spacing_z = wx.StaticText(p, -1, _("Z:"))
        fsp_spacing_z = self.fsp_spacing_z = InvFloatSpinCtrl(
            p, -1, min_value=0, max_value=1000000000, increment=0.25, value=1.0, digits=8
        )

        try:
            proj = prj.Project()

            sx = proj.spacing[0]
            sy = proj.spacing[1]
            sz = proj.spacing[2]

            fsp_spacing_x.SetValue(sx)
            fsp_spacing_y.SetValue(sy)
            fsp_spacing_z.SetValue(sz)

        except AttributeError:
            pass

        gbs_spacing.Add(stx_spacing_x, (0, 0), flag=flag_labels)
        gbs_spacing.Add(fsp_spacing_x, (0, 1))

        gbs_spacing.Add(stx_spacing_y, (0, 2), flag=flag_labels)
        gbs_spacing.Add(fsp_spacing_y, (0, 3))

        gbs_spacing.Add(stx_spacing_z, (0, 4), flag=flag_labels)
        gbs_spacing.Add(fsp_spacing_z, (0, 5))

        # ----- buttons ------------------------
        gbs_button = wx.GridBagSizer(2, 4)

        btn_ok = self.btn_ok = wx.Button(p, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(p, wx.ID_CANCEL)

        gbs_button.Add(0, 0, (0, 2))

        gbs_button.Add(btn_cancel, (1, 2))
        gbs_button.Add(btn_ok, (1, 3))

        gbs_principal.Add(gbs, (0, 0), flag=wx.ALL | wx.EXPAND)
        gbs_principal.Add(gbs_spacing, (1, 0), flag=wx.ALL | wx.EXPAND)
        gbs_principal.Add(0, 0, (2, 0))
        gbs_principal.Add(gbs_button, (3, 0), flag=wx.ALIGN_RIGHT)

        box = wx.BoxSizer()
        box.Add(gbs_principal, 1, wx.ALL | wx.EXPAND, 10)

        p.SetSizer(box)
        box.Fit(self)
        self.Layout()

    def bind_evts(self) -> None:
        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def SetInterval(self, v: int) -> None:
        self.interval = v

    def OnOk(self, evt: wx.CommandEvent) -> None:
        orient_selection = self.cb_orientation.GetSelection()

        if orient_selection == 1:
            orientation = "CORONAL"
        elif orient_selection == 2:
            orientation = "SAGITTAL"
        else:
            orientation = "AXIAL"

        values = [
            self.tx_name.GetValue(),
            orientation,
            self.fsp_spacing_x.GetValue(),
            self.fsp_spacing_y.GetValue(),
            self.fsp_spacing_z.GetValue(),
            self.interval,
        ]
        Publisher.sendMessage("Open bitmap files", rec_data=values)

        self.Close()
        self.Destroy()


def BitmapNotSameSize() -> None:
    dlg = wx.MessageDialog(
        None,
        _("All bitmaps files must be the same \n width and height size."),
        "Error",
        wx.OK | wx.ICON_ERROR,
    )

    dlg.ShowModal()
    dlg.Destroy()


class PanelTargeFFill(wx.Panel):
    def __init__(
        self, parent: wx.Window, ID: int = -1, style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER
    ):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui()

    def _init_gui(self) -> None:
        self.target_2d = wx.RadioButton(self, -1, _("2D - Actual slice"), style=wx.RB_GROUP)
        self.target_3d = wx.RadioButton(self, -1, _("3D - All slices"))

        sizer = wx.GridBagSizer(5, 5)

        sizer.Add(0, 0, (0, 0))
        sizer.Add(self.target_2d, (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.target_3d, (2, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(0, 0, (3, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()


class Panel2DConnectivity(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        ID: int = -1,
        show_orientation: bool = False,
        style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER,
    ):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui(show_orientation)

    def _init_gui(self, show_orientation: bool) -> None:
        self.conect2D_4 = wx.RadioButton(self, -1, "4", style=wx.RB_GROUP)
        self.conect2D_8 = wx.RadioButton(self, -1, "8")

        sizer = wx.GridBagSizer(5, 5)

        sizer.Add(0, 0, (0, 0))
        sizer.Add(
            wx.StaticText(self, -1, _("2D Connectivity")), (1, 0), (1, 6), flag=wx.LEFT, border=5
        )
        sizer.Add(self.conect2D_4, (2, 0), flag=wx.LEFT, border=7)
        sizer.Add(self.conect2D_8, (2, 1), flag=wx.LEFT, border=7)
        sizer.Add(0, 0, (3, 0))

        if show_orientation:
            self.cmb_orientation = wx.ComboBox(
                self, -1, choices=(_("Axial"), _("Coronal"), _("Sagital")), style=wx.CB_READONLY
            )
            self.cmb_orientation.SetSelection(0)

            sizer.Add(
                wx.StaticText(self, -1, _("Orientation")),
                (4, 0),
                (1, 6),
                flag=wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
                border=5,
            )
            sizer.Add(
                self.cmb_orientation, (5, 0), (1, 10), flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7
            )
            sizer.Add(0, 0, (6, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def GetConnSelected(self) -> Literal[4, 8]:
        if self.conect2D_4.GetValue():
            return 4
        else:
            return 8

    def GetOrientation(self) -> str:
        dic_ori = {_("Axial"): "AXIAL", _("Coronal"): "CORONAL", _("Sagital"): "SAGITAL"}

        return dic_ori[self.cmb_orientation.GetStringSelection()]


class Panel3DConnectivity(wx.Panel):
    def __init__(
        self, parent: wx.Window, ID: int = -1, style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER
    ):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui()

    def _init_gui(self) -> None:
        self.conect3D_6 = wx.RadioButton(self, -1, "6", style=wx.RB_GROUP)
        self.conect3D_18 = wx.RadioButton(self, -1, "18")
        self.conect3D_26 = wx.RadioButton(self, -1, "26")

        sizer = wx.GridBagSizer(5, 5)

        sizer.Add(0, 0, (0, 0))
        sizer.Add(
            wx.StaticText(self, -1, _("3D Connectivity")), (1, 0), (1, 6), flag=wx.LEFT, border=5
        )
        sizer.Add(self.conect3D_6, (2, 0), flag=wx.LEFT, border=9)
        sizer.Add(self.conect3D_18, (2, 1), flag=wx.LEFT, border=9)
        sizer.Add(self.conect3D_26, (2, 2), flag=wx.LEFT, border=9)
        sizer.Add(0, 0, (3, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def GetConnSelected(self) -> Literal[6, 18, 26]:
        if self.conect3D_6.GetValue():
            return 6
        elif self.conect3D_18.GetValue():
            return 18
        else:
            return 26


class PanelFFillThreshold(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        config: "FFillSegmentationConfig",
        ID: int = -1,
        style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER,
    ) -> None:
        wx.Panel.__init__(self, parent, ID, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        import invesalius.project as prj

        project = prj.Project()
        bound_min, bound_max = project.threshold_range
        colour = [i * 255 for i in const.MASK_COLOUR[0]]
        colour.append(100)

        self.threshold = grad.GradientCtrl(
            self, -1, int(bound_min), int(bound_max), self.config.t0, self.config.t1, colour
        )

        # sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(5)
        sizer.Add(self.threshold, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.Bind(grad.EVT_THRESHOLD_CHANGING, self.OnSlideChanged, self.threshold)
        self.Bind(grad.EVT_THRESHOLD_CHANGED, self.OnSlideChanged, self.threshold)

    def OnSlideChanged(self, evt: wx.Event) -> None:
        self.config.t0 = int(self.threshold.GetMinValue())
        self.config.t1 = int(self.threshold.GetMaxValue())
        print(self.config.t0, self.config.t1)


class PanelFFillDynamic(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        config: "FFillSegmentationConfig",
        ID: int = -1,
        style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER,
    ):
        wx.Panel.__init__(self, parent, ID, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        self.use_ww_wl = wx.CheckBox(self, -1, _("Use WW&WL"))
        self.use_ww_wl.SetValue(self.config.use_ww_wl)

        self.deviation_min = InvSpinCtrl(
            self, -1, value=self.config.dev_min, min_value=0, max_value=10000
        )
        self.deviation_min.CalcSizeFromTextSize()

        self.deviation_max = InvSpinCtrl(
            self, -1, value=self.config.dev_max, min_value=0, max_value=10000
        )
        self.deviation_max.CalcSizeFromTextSize()

        sizer = wx.GridBagSizer(5, 5)

        sizer.Add(0, 0, (0, 0))

        sizer.Add(self.use_ww_wl, (1, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.Add(0, 0, (2, 0))

        sizer.Add(wx.StaticText(self, -1, _("Deviation")), (3, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.Add(
            wx.StaticText(self, -1, _("Min:")),
            (4, 0),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT,
            border=9,
        )
        sizer.Add(self.deviation_min, (4, 1))

        sizer.Add(
            wx.StaticText(self, -1, _("Max:")),
            (4, 2),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT,
            border=9,
        )
        sizer.Add(self.deviation_max, (4, 3))

        sizer.Add(0, 0, (5, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.use_ww_wl.Bind(wx.EVT_CHECKBOX, self.OnSetUseWWWL)
        self.deviation_min.Bind(wx.EVT_SPINCTRL, self.OnSetDeviation)
        self.deviation_max.Bind(wx.EVT_SPINCTRL, self.OnSetDeviation)

    def OnSetUseWWWL(self, evt: wx.CommandEvent) -> None:
        self.config.use_ww_wl = self.use_ww_wl.GetValue()

    def OnSetDeviation(self, evt: wx.SpinEvent) -> None:
        self.config.dev_max = self.deviation_max.GetValue()
        self.config.dev_min = self.deviation_min.GetValue()


class PanelFFillConfidence(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        config: "FFillSegmentationConfig",
        ID: int = -1,
        style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER,
    ):
        wx.Panel.__init__(self, parent, ID, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        self.use_ww_wl = wx.CheckBox(self, -1, _("Use WW&WL"))
        self.use_ww_wl.SetValue(self.config.use_ww_wl)

        self.spin_mult = InvFloatSpinCtrl(
            self,
            -1,
            value=self.config.confid_mult,
            min_value=1.0,
            max_value=10.0,
            increment=0.1,
            digits=1,
        )
        #  style=wx.TE_PROCESS_TAB|wx.TE_PROCESS_ENTER,
        #  agwStyle=floatspin.FS_RIGHT)
        self.spin_mult.CalcSizeFromTextSize()

        self.spin_iters = InvSpinCtrl(
            self, -1, value=self.config.confid_iters, min_value=0, max_value=100
        )
        self.spin_iters.CalcSizeFromTextSize()

        sizer = wx.GridBagSizer(5, 5)

        sizer.Add(0, 0, (0, 0))

        sizer.Add(self.use_ww_wl, (1, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.Add(0, 0, (2, 0))

        sizer.Add(
            wx.StaticText(self, -1, _("Multiplier")),
            (3, 0),
            (1, 3),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT,
            border=5,
        )
        sizer.Add(self.spin_mult, (3, 3), (1, 3))

        sizer.Add(
            wx.StaticText(self, -1, _("Iterations")),
            (4, 0),
            (1, 3),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT,
            border=5,
        )
        sizer.Add(self.spin_iters, (4, 3), (1, 2))

        sizer.Add(0, 0, (5, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.use_ww_wl.Bind(wx.EVT_CHECKBOX, self.OnSetUseWWWL)
        self.spin_mult.Bind(wx.EVT_SPINCTRL, self.OnSetMult)
        self.spin_iters.Bind(wx.EVT_SPINCTRL, self.OnSetIters)

    def OnSetUseWWWL(self, evt: wx.CommandEvent) -> None:
        self.config.use_ww_wl = self.use_ww_wl.GetValue()

    def OnSetMult(self, evt: wx.SpinEvent) -> None:
        self.config.confid_mult = self.spin_mult.GetValue()

    def OnSetIters(self, evt: wx.SpinEvent) -> None:
        self.config.confid_iters = self.spin_iters.GetValue()


class PanelFFillProgress(wx.Panel):
    def __init__(
        self, parent: wx.Window, ID: int = -1, style: int = wx.TAB_TRAVERSAL | wx.NO_BORDER
    ) -> None:
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui()

    def _init_gui(self) -> None:
        self.progress = wx.Gauge(self, -1)
        self.lbl_progress_caption = wx.StaticText(self, -1, _("Elapsed time:"))
        self.lbl_time = wx.StaticText(self, -1, _("00:00:00"))

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)
        time_sizer = wx.BoxSizer(wx.HORIZONTAL)
        time_sizer.Add(self.lbl_progress_caption, 0, wx.EXPAND, 0)
        time_sizer.Add(self.lbl_time, 1, wx.EXPAND | wx.LEFT, 5)
        main_sizer.Add(time_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        main_sizer.SetSizeHints(self)

    def StartTimer(self) -> None:
        self.t0 = time.time()

    def StopTimer(self) -> None:
        fmt = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        self.progress.SetValue(0)

    def Pulse(self) -> None:
        fmt = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        self.progress.Pulse()


class FFillOptionsDialog(wx.Dialog):
    def __init__(self, title: str, config: "FFillConfig"):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        """
        Create the widgets.
        """

        # Target
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.panel_target = PanelTargeFFill(self, style=border_style | wx.TAB_TRAVERSAL)
        self.panel2dcon = Panel2DConnectivity(self, style=border_style | wx.TAB_TRAVERSAL)
        self.panel3dcon = Panel3DConnectivity(self, style=border_style | wx.TAB_TRAVERSAL)

        if self.config.target == "2D":
            self.panel_target.target_2d.SetValue(True)
            self.panel2dcon.Enable(True)
            self.panel3dcon.Enable(False)
        else:
            self.panel_target.target_3d.SetValue(True)
            self.panel3dcon.Enable(True)
            self.panel2dcon.Enable(False)

        # Connectivity 2D
        if self.config.con_2d == 8:
            self.panel2dcon.conect2D_8.SetValue(True)
        else:
            self.panel2dcon.conect2D_4.SetValue(True)
            self.config.con_2d = 4

        # Connectivity 3D
        if self.config.con_3d == 18:
            self.panel3dcon.conect3D_18.SetValue(True)
        elif self.config.con_3d == 26:
            self.panel3dcon.conect3D_26.SetValue(True)
        else:
            self.panel3dcon.conect3D_6.SetValue(True)

        self.close_btn = wx.Button(self, wx.ID_CLOSE)

        # Sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(5)
        sizer.Add(wx.StaticText(self, -1, _("Parameters")), flag=wx.LEFT, border=5)
        sizer.AddSpacer(5)
        sizer.Add(self.panel_target, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel2dcon, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel3dcon, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.close_btn, 0, flag=wx.ALIGN_RIGHT | wx.RIGHT, border=7)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.close_btn.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnBtnClose(self, evt: wx.CommandEvent) -> None:
        self.Close()

    def OnSetRadio(self, evt: wx.CommandEvent) -> None:
        # Target
        if self.panel_target.target_2d.GetValue():
            self.config.target = "2D"
            self.panel2dcon.Enable(True)
            self.panel3dcon.Enable(False)
        else:
            self.config.target = "3D"
            self.panel3dcon.Enable(True)
            self.panel2dcon.Enable(False)

        # 2D
        if self.panel2dcon.conect2D_4.GetValue():
            self.config.con_2d = 4
        elif self.panel2dcon.conect2D_8.GetValue():
            self.config.con_2d = 8

        # 3D
        if self.panel3dcon.conect3D_6.GetValue():
            self.config.con_3d = 6
        elif self.panel3dcon.conect3D_18.GetValue():
            self.config.con_3d = 18
        elif self.panel3dcon.conect3D_26.GetValue():
            self.config.con_3d = 26

    def OnClose(self, evt: wx.CloseEvent) -> None:
        print("ONCLOSE")
        if self.config.dlg_visible:
            Publisher.sendMessage("Disable style", style=const.SLICE_STATE_MASK_FFILL)
        evt.Skip()
        self.Destroy()


class SelectPartsOptionsDialog(wx.Dialog):
    def __init__(self, config: "SelectPartConfig"):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Select mask parts"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        self.config = config

        self.SetReturnCode(wx.CANCEL)

        self._init_gui()

    def _init_gui(self) -> None:
        self.target_name = wx.TextCtrl(self, -1)
        self.target_name.SetValue(self.config.mask_name)

        # Connectivity 3D
        self.panel3dcon = Panel3DConnectivity(self)
        if self.config.con_3d == 18:
            self.panel3dcon.conect3D_18.SetValue(True)
        elif self.config.con_3d == 26:
            self.panel3dcon.conect3D_26.SetValue(True)
        else:
            self.panel3dcon.conect3D_6.SetValue(True)

        self.btn_ok = wx.Button(self, wx.ID_OK)
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL)

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(5)
        sizer.Add(wx.StaticText(self, -1, _("Target mask name")), flag=wx.LEFT, border=5)
        sizer.AddSpacer(5)
        sizer.Add(self.target_name, flag=wx.LEFT | wx.EXPAND | wx.RIGHT, border=9)
        sizer.AddSpacer(5)
        sizer.Add(self.panel3dcon, flag=wx.LEFT | wx.RIGHT | wx.EXPAND)
        sizer.AddSpacer(5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self.btn_ok, 0)  # flag=wx.ALIGN_RIGHT, border=5)
        btn_sizer.Add(self.btn_cancel, 0, flag=wx.LEFT, border=5)

        sizer.Add(btn_sizer, 0, flag=wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT, border=5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

        self.target_name.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnOk(self, evt: wx.CommandEvent) -> None:
        self.SetReturnCode(wx.OK)
        self.Close()

    def OnCancel(self, evt: wx.CommandEvent) -> None:
        self.SetReturnCode(wx.CANCEL)
        self.Close()

    def OnChar(self, evt: wx.KeyEvent) -> None:
        evt.Skip()
        self.config.mask_name = self.target_name.GetValue()

    def OnSetRadio(self, evt: wx.CommandEvent) -> None:
        if self.panel3dcon.conect3D_6.GetValue():
            self.config.con_3d = 6
        elif self.panel3dcon.conect3D_18.GetValue():
            self.config.con_3d = 18
        elif self.panel3dcon.conect3D_26.GetValue():
            self.config.con_3d = 26

    def OnClose(self, evt: wx.CloseEvent) -> None:
        if self.config.dlg_visible:
            Publisher.sendMessage("Disable style", style=const.SLICE_STATE_SELECT_MASK_PARTS)
        evt.Skip()
        self.Destroy()


class FFillSegmentationOptionsDialog(wx.Dialog):
    def __init__(
        self,
        config: "FFillSegmentationConfig",
        ID: int = -1,
        title: str = _("Region growing"),
        style: int = wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
    ):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self) -> None:
        """
        Create the widgets.
        """

        # Target
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.panel_target = PanelTargeFFill(self, style=border_style | wx.TAB_TRAVERSAL)
        self.panel2dcon = Panel2DConnectivity(self, style=border_style | wx.TAB_TRAVERSAL)
        self.panel3dcon = Panel3DConnectivity(self, style=border_style | wx.TAB_TRAVERSAL)

        if self.config.target == "2D":
            self.panel_target.target_2d.SetValue(True)
            self.panel2dcon.Enable(True)
            self.panel3dcon.Enable(False)
        else:
            self.panel_target.target_3d.SetValue(True)
            self.panel3dcon.Enable(True)
            self.panel2dcon.Enable(False)

        # Connectivity 2D
        if self.config.con_2d == 8:
            self.panel2dcon.conect2D_8.SetValue(True)
        else:
            self.panel2dcon.conect2D_4.SetValue(True)
            self.config.con_2d = 4

        # Connectivity 3D
        if self.config.con_3d == 18:
            self.panel3dcon.conect3D_18.SetValue(True)
        elif self.config.con_3d == 26:
            self.panel3dcon.conect3D_26.SetValue(True)
        else:
            self.panel3dcon.conect3D_6.SetValue(True)

        self.cmb_method = wx.ComboBox(
            self, -1, choices=(_("Dynamic"), _("Threshold"), _("Confidence")), style=wx.CB_READONLY
        )

        if self.config.method == "dynamic":
            self.cmb_method.SetSelection(0)
        elif self.config.method == "threshold":
            self.cmb_method.SetSelection(1)
        elif self.config.method == "confidence":
            self.cmb_method.SetSelection(2)

        self.panel_ffill_threshold = PanelFFillThreshold(
            self, self.config, -1, style=border_style | wx.TAB_TRAVERSAL
        )
        self.panel_ffill_threshold.SetMinSize((250, -1))
        self.panel_ffill_threshold.Hide()

        self.panel_ffill_dynamic = PanelFFillDynamic(
            self, self.config, -1, style=border_style | wx.TAB_TRAVERSAL
        )
        self.panel_ffill_dynamic.SetMinSize((250, -1))
        self.panel_ffill_dynamic.Hide()

        self.panel_ffill_confidence = PanelFFillConfidence(
            self, self.config, -1, style=border_style | wx.TAB_TRAVERSAL
        )
        self.panel_ffill_confidence.SetMinSize((250, -1))
        self.panel_ffill_confidence.Hide()

        self.panel_ffill_progress = PanelFFillProgress(self, -1, style=wx.TAB_TRAVERSAL)
        self.panel_ffill_progress.SetMinSize((250, -1))
        # self.panel_ffill_progress.Hide()

        self.close_btn = wx.Button(self, wx.ID_CLOSE)

        # Sizer
        sizer = wx.GridBagSizer(2, 2)

        sizer.Add(0, 0, (0, 0))
        sizer.Add(wx.StaticText(self, -1, _("Parameters")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(0, 0, (2, 0))
        sizer.Add(self.panel_target, (3, 0), (1, 6), flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.Add(0, 0, (4, 0))
        sizer.Add(self.panel2dcon, (5, 0), (1, 6), flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.Add(0, 0, (6, 0))
        sizer.Add(self.panel3dcon, (7, 0), (1, 6), flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.Add(0, 0, (8, 0))

        sizer.Add(
            wx.StaticText(self, -1, _("Method")),
            (9, 0),
            (1, 1),
            flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL,
            border=7,
        )
        sizer.Add(self.cmb_method, (9, 1), (1, 5), flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)

        sizer.Add(0, 0, (10, 0))

        if self.config.method == "dynamic":
            self.cmb_method.SetSelection(0)
            self.panel_ffill_dynamic.Show()
            sizer.Add(
                self.panel_ffill_dynamic,
                (11, 0),
                (1, 6),
                flag=wx.LEFT | wx.RIGHT | wx.EXPAND,
                border=7,
            )
        elif self.config.method == "confidence":
            self.cmb_method.SetSelection(2)
            self.panel_ffill_confidence.Show()
            sizer.Add(
                self.panel_ffill_confidence,
                (11, 0),
                (1, 6),
                flag=wx.LEFT | wx.RIGHT | wx.EXPAND,
                border=7,
            )
        else:
            self.cmb_method.SetSelection(1)
            self.panel_ffill_threshold.Show()
            sizer.Add(
                self.panel_ffill_threshold,
                (11, 0),
                (1, 6),
                flag=wx.LEFT | wx.RIGHT | wx.EXPAND,
                border=7,
            )
            self.config.method = "threshold"

        sizer.Add(0, 0, (12, 0))
        sizer.Add(
            self.panel_ffill_progress, (13, 0), (1, 6), flag=wx.ALIGN_RIGHT | wx.RIGHT, border=5
        )
        sizer.Add(0, 0, (14, 0))
        sizer.Add(self.close_btn, (15, 0), (1, 6), flag=wx.ALIGN_RIGHT | wx.RIGHT, border=5)
        sizer.Add(0, 0, (16, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)
        self.cmb_method.Bind(wx.EVT_COMBOBOX, self.OnSetMethod)
        self.close_btn.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnSetRadio(self, evt: wx.CommandEvent) -> None:
        # Target
        if self.panel_target.target_2d.GetValue():
            self.config.target = "2D"
            self.panel2dcon.Enable(True)
            self.panel3dcon.Enable(False)
        else:
            self.config.target = "3D"
            self.panel3dcon.Enable(True)
            self.panel2dcon.Enable(False)

        # 2D
        if self.panel2dcon.conect2D_4.GetValue():
            self.config.con_2d = 4
        elif self.panel2dcon.conect2D_8.GetValue():
            self.config.con_2d = 8

        # 3D
        if self.panel3dcon.conect3D_6.GetValue():
            self.config.con_3d = 6
        elif self.panel3dcon.conect3D_18.GetValue():
            self.config.con_3d = 18
        elif self.panel3dcon.conect3D_26.GetValue():
            self.config.con_3d = 26

    def OnSetMethod(self, evt: wx.CommandEvent) -> None:
        sizer = self.GetSizer()
        assert isinstance(sizer, wx.GridBagSizer), "assigned sizer must be a wx.GridBagSizer"
        item_panel = sizer.FindItemAtPosition((11, 0)).GetWindow()

        if self.cmb_method.GetSelection() == 0:
            self.config.method = "dynamic"
            item_panel.Hide()
            self.panel_ffill_dynamic.Show()
            self.GetSizer().Replace(item_panel, self.panel_ffill_dynamic)

        elif self.cmb_method.GetSelection() == 2:
            self.config.method = "confidence"
            item_panel.Hide()
            self.panel_ffill_confidence.Show()
            self.GetSizer().Replace(item_panel, self.panel_ffill_confidence)

        else:
            self.config.method = "threshold"
            item_panel.Hide()
            self.panel_ffill_threshold.Show()
            self.GetSizer().Replace(item_panel, self.panel_ffill_threshold)

        self.GetSizer().Fit(self)
        self.Layout()

    def OnBtnClose(self, evt: wx.CommandEvent) -> None:
        self.Close()

    def OnClose(self, evt: wx.CloseEvent) -> None:
        if self.config.dlg_visible:
            Publisher.sendMessage("Disable style", style=const.SLICE_STATE_MASK_FFILL)
        evt.Skip()
        self.Destroy()


class CropOptionsDialog(wx.Dialog):
    def __init__(
        self,
        config: "CropMaskConfig",
        ID: int = -1,
        title: str = _("Crop mask"),
        style: int = wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
    ):
        self.config = config
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)
        self._init_gui()

    def UpdateValues(self, limits: Iterable[float]) -> None:
        xi, xf, yi, yf, zi, zf = limits

        self.tx_axial_i.SetValue(str(zi))
        self.tx_axial_f.SetValue(str(zf))

        self.tx_sagital_i.SetValue(str(xi))
        self.tx_sagital_f.SetValue(str(xf))

        self.tx_coronal_i.SetValue(str(yi))
        self.tx_coronal_f.SetValue(str(yf))

    def _init_gui(self) -> None:
        p = wx.Panel(
            self, -1, style=wx.TAB_TRAVERSAL | wx.CLIP_CHILDREN | wx.FULL_REPAINT_ON_RESIZE
        )

        gbs_principal = self.gbs = wx.GridBagSizer(4, 1)

        gbs = self.gbs = wx.GridBagSizer(3, 4)

        flag_labels = wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL

        txt_style = wx.TE_READONLY

        stx_axial = wx.StaticText(p, -1, _("Axial:"))
        self.tx_axial_i = tx_axial_i = wx.TextCtrl(p, -1, "", size=wx.Size(50, -1), style=txt_style)
        stx_axial_t = wx.StaticText(p, -1, _(" - "))
        self.tx_axial_f = tx_axial_f = wx.TextCtrl(p, -1, "", size=wx.Size(50, -1), style=txt_style)

        gbs.Add(stx_axial, (0, 0), flag=flag_labels)
        gbs.Add(tx_axial_i, (0, 1))
        gbs.Add(stx_axial_t, (0, 2), flag=flag_labels)
        gbs.Add(tx_axial_f, (0, 3))

        stx_sagital = wx.StaticText(p, -1, _("Sagital:"))
        self.tx_sagital_i = tx_sagital_i = wx.TextCtrl(
            p, -1, "", size=wx.Size(50, -1), style=txt_style
        )
        stx_sagital_t = wx.StaticText(p, -1, _(" - "))
        self.tx_sagital_f = tx_sagital_f = wx.TextCtrl(
            p, -1, "", size=wx.Size(50, -1), style=txt_style
        )

        gbs.Add(stx_sagital, (1, 0), flag=flag_labels)
        gbs.Add(tx_sagital_i, (1, 1))
        gbs.Add(stx_sagital_t, (1, 2), flag=flag_labels)
        gbs.Add(tx_sagital_f, (1, 3))

        stx_coronal = wx.StaticText(p, -1, _("Coronal:"))
        self.tx_coronal_i = tx_coronal_i = wx.TextCtrl(
            p, -1, "", size=wx.Size(50, -1), style=txt_style
        )
        stx_coronal_t = wx.StaticText(p, -1, _(" - "))
        self.tx_coronal_f = tx_coronal_f = wx.TextCtrl(
            p, -1, "", size=wx.Size(50, -1), style=txt_style
        )

        gbs.Add(stx_coronal, (2, 0), flag=flag_labels)
        gbs.Add(tx_coronal_i, (2, 1))
        gbs.Add(stx_coronal_t, (2, 2), flag=flag_labels)
        gbs.Add(tx_coronal_f, (2, 3))

        gbs_button = wx.GridBagSizer(2, 4)

        btn_ok = self.btn_ok = wx.Button(p, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(p, wx.ID_CANCEL)

        gbs_button.Add(btn_cancel, (0, 0))
        gbs_button.Add(btn_ok, (0, 1))

        gbs_principal.Add(gbs, (0, 0), flag=wx.ALL | wx.EXPAND)
        gbs_principal.Add(0, 0, (1, 0))
        gbs_principal.Add(0, 0, (2, 0))

        gbs_principal.Add(gbs_button, (3, 0), flag=wx.ALIGN_RIGHT)

        box = wx.BoxSizer()
        box.Add(gbs_principal, 1, wx.ALL | wx.EXPAND, 10)

        p.SetSizer(box)
        box.Fit(p)
        p.Layout()

        sizer = wx.BoxSizer()
        sizer.Add(p, 1, wx.EXPAND)
        sizer.Fit(self)
        self.Layout()

        Publisher.subscribe(self.UpdateValues, "Update crop limits into gui")

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        btn_cancel.Bind(wx.EVT_BUTTON, self.OnClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnOk(self, evt: wx.CommandEvent) -> None:
        self.config.dlg_visible = False
        Publisher.sendMessage("Crop mask")
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_CROP_MASK)
        evt.Skip()

    def OnClose(self, evt: Union[wx.CommandEvent, wx.CloseEvent]) -> None:
        self.config.dlg_visible = False
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_CROP_MASK)
        evt.Skip()
        self.Destroy()


class FillHolesAutoDialog(wx.Dialog):
    def __init__(self, title: str):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )
        self._init_gui()

    def _init_gui(self) -> None:
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.spin_size = InvSpinCtrl(self, -1, value=1000, min_value=1, max_value=1000000000)
        self.panel_target = PanelTargeFFill(self, style=border_style | wx.TAB_TRAVERSAL)
        self.panel2dcon = Panel2DConnectivity(
            self, show_orientation=True, style=border_style | wx.TAB_TRAVERSAL
        )
        self.panel3dcon = Panel3DConnectivity(self, style=border_style | wx.TAB_TRAVERSAL)

        self.panel2dcon.Enable(True)
        self.panel3dcon.Enable(False)

        self.panel_target.target_2d.SetValue(True)
        self.panel2dcon.conect2D_4.SetValue(True)
        self.panel3dcon.conect3D_6.SetValue(True)

        self.apply_btn = wx.Button(self, wx.ID_APPLY)
        self.close_btn = wx.Button(self, wx.ID_CLOSE)

        # Sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(5)
        sizer.Add(wx.StaticText(self, -1, _("Parameters")), flag=wx.LEFT, border=5)
        sizer.AddSpacer(5)

        sizer.Add(self.panel_target, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel2dcon, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel3dcon, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)

        spin_sizer = wx.BoxSizer(wx.HORIZONTAL)
        spin_sizer.Add(
            wx.StaticText(self, -1, _("Max hole size")),
            flag=wx.LEFT | wx.ALIGN_CENTER_VERTICAL,
            border=5,
        )
        spin_sizer.Add(self.spin_size, 0, flag=wx.LEFT | wx.RIGHT, border=5)
        spin_sizer.Add(
            wx.StaticText(self, -1, _("voxels")), flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5
        )

        sizer.Add(spin_sizer, 0, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=7)
        sizer.AddSpacer(5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self.apply_btn, 0)  # flag=wx.ALIGN_RIGHT, border=5)
        btn_sizer.Add(self.close_btn, 0, flag=wx.LEFT, border=5)

        sizer.Add(btn_sizer, 0, flag=wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT, border=5)

        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.apply_btn.Bind(wx.EVT_BUTTON, self.OnApply)
        self.close_btn.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)

    def OnApply(self, evt: wx.CommandEvent) -> None:
        if self.panel_target.target_2d.GetValue():
            target = "2D"
            conn = self.panel2dcon.GetConnSelected()
            orientation = self.panel2dcon.GetOrientation()
        else:
            target = "3D"
            conn = self.panel3dcon.GetConnSelected()
            orientation = "VOLUME"

        parameters = {
            "target": target,
            "conn": conn,
            "orientation": orientation,
            "size": self.spin_size.GetValue(),
        }

        Publisher.sendMessage("Fill holes automatically", parameters=parameters)

    def OnBtnClose(self, evt: wx.CommandEvent) -> None:
        self.Close()
        self.Destroy()

    def OnSetRadio(self, evt: wx.CommandEvent) -> None:
        # Target
        if self.panel_target.target_2d.GetValue():
            self.panel2dcon.Enable(True)
            self.panel3dcon.Enable(False)
        else:
            self.panel3dcon.Enable(True)
            self.panel2dcon.Enable(False)


class MaskDensityDialog(wx.Dialog):
    def __init__(self, title: str) -> None:
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Mask density"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )
        self._init_gui()
        self._bind_events()

    def _init_gui(self) -> None:
        import invesalius.project as prj

        project = prj.Project()

        self.cmb_mask = wx.ComboBox(self, -1, choices=[], style=wx.CB_READONLY)
        if project.mask_dict.values():
            for mask in project.mask_dict.values():
                self.cmb_mask.Append(mask.name, mask)
            self.cmb_mask.SetValue(list(project.mask_dict.values())[0].name)

        self.calc_button = wx.Button(self, -1, _("Calculate"))

        self.mean_density = self._create_selectable_label_text("")
        self.min_density = self._create_selectable_label_text("")
        self.max_density = self._create_selectable_label_text("")
        self.std_density = self._create_selectable_label_text("")

        slt_mask_sizer = wx.FlexGridSizer(rows=1, cols=3, vgap=5, hgap=5)
        slt_mask_sizer.AddMany(
            [
                (
                    wx.StaticText(self, -1, _("Mask:"), style=wx.ALIGN_CENTER_VERTICAL),
                    0,
                    wx.ALIGN_CENTRE,
                ),
                (self.cmb_mask, 1, wx.EXPAND),
                (self.calc_button, 0, wx.EXPAND),
            ]
        )

        values_sizer = wx.FlexGridSizer(rows=4, cols=2, vgap=5, hgap=5)
        values_sizer.AddMany(
            [
                (wx.StaticText(self, -1, _("Mean:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT),
                (self.mean_density, 1, wx.EXPAND),
                (
                    wx.StaticText(self, -1, _("Minimun:")),
                    0,
                    wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT,
                ),
                (self.min_density, 1, wx.EXPAND),
                (
                    wx.StaticText(self, -1, _("Maximun:")),
                    0,
                    wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT,
                ),
                (self.max_density, 1, wx.EXPAND),
                (
                    wx.StaticText(self, -1, _("Standard deviation:")),
                    0,
                    wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT,
                ),
                (self.std_density, 1, wx.EXPAND),
            ]
        )

        sizer = wx.FlexGridSizer(rows=4, cols=1, vgap=5, hgap=5)
        sizer.AddSpacer(5)
        sizer.AddMany(
            [
                (slt_mask_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5),
                (values_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5),
            ]
        )
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.CenterOnScreen()

    def _create_selectable_label_text(self, text: str) -> wx.TextCtrl:
        label = wx.TextCtrl(self, -1, style=wx.TE_READONLY)
        label.SetValue(text)
        #  label.SetBackgroundColour(self.GetBackgroundColour())
        return label

    def _bind_events(self) -> None:
        self.calc_button.Bind(wx.EVT_BUTTON, self.OnCalcButton)

    def OnCalcButton(self, evt: wx.CommandEvent) -> None:
        from invesalius.data.slice_ import Slice

        mask = self.cmb_mask.GetClientData(self.cmb_mask.GetSelection())

        slc = Slice()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(slc.calc_image_density, mask)
            for c in itertools.cycle(["", ".", "..", "..."]):
                s = _("Calculating ") + c
                self.mean_density.SetValue(s)
                self.min_density.SetValue(s)
                self.max_density.SetValue(s)
                self.std_density.SetValue(s)
                self.Update()
                self.Refresh()
                if future.done():
                    break
                time.sleep(0.1)

            _min, _max, _mean, _std = future.result()

        self.mean_density.SetValue(str(_mean))
        self.min_density.SetValue(str(_min))
        self.max_density.SetValue(str(_max))
        self.std_density.SetValue(str(_std))

        print(">>>> Area of mask", slc.calc_mask_area(mask))


class ObjectCalibrationDialog(wx.Dialog):
    def __init__(
        self,
        tracker: "Tracker",
        n_coils: "int",
        pedal_connector: "PedalConnector",
    ):
        self.tracker = tracker
        self.n_coils = n_coils
        self.pedal_connector = pedal_connector

        self.tracker_id = tracker.GetTrackerId()
        self.obj_id = 2  # the index of the object in coord_raw
        self.show_sensor_options: bool = self.tracker_id in const.TRACKERS_WITH_SENSOR_OPTIONS
        self.coil_path = None
        self.polydata = None

        self.obj_fiducials = np.full([4, 3], np.nan)
        self.obj_orients = np.full([4, 3], np.nan)

        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Object calibration"),
            size=(450, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
        )

        self._init_gui()
        self._init_pedal()
        self.InitializeObject()

    def _init_gui(self) -> None:
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        self.interactor.Enable(1)
        self.ren = vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)

        # Initialize list of buttons and txtctrls for wx objects
        self.btns_coord = [None] * 4
        self.text_actors: List[Optional[vtkFollower]] = [None] * 4
        self.ball_actors: List[Optional[vtkActor]] = [None] * 4
        self.txt_coord = [list(), list(), list(), list()]

        # ComboBox for object index in coord_raw (0 for static, 2 for dynamic, 3, 4, ... for multiple coils)
        # Check how many coords the tracker gives, ie. coord_raw.shape[0]
        max_obj_id = self.tracker.GetTrackerCoordinates(ref_mode_id=0)[2].shape[0]
        tooltip = _(
            "Choose the coil index in coord_raw. Choose 0 for static mode, 2 for dynamic mode and 3 onwards for multiple coils."
        )

        # Static mode obj_id=0 (case where stylus is attached to coil) is only feasible for single coil-mode, so hide it in multicoil mode
        choices = ["0"] if self.n_coils == 1 else []
        choices += [str(i) for i in range(2, max_obj_id)]

        choice_obj_id = wx.ComboBox(
            self,
            -1,
            "",
            size=wx.Size(90, 23),
            choices=choices,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        choice_obj_id.SetToolTip(tooltip)
        choice_obj_id.Bind(wx.EVT_COMBOBOX, self.OnChooseObjID)
        choice_obj_id.SetStringSelection(str(self.obj_id))
        choice_obj_id.Enable(True)

        if self.tracker_id == const.PATRIOT or self.tracker_id == const.ISOTRAKII:
            self.obj_id = 0
            choice_obj_id.SetSelection(0)
            choice_obj_id.Enable(False)

        # ComboBox for sensor selection for FASTRAK
        tooltip = _("Choose the FASTRAK sensor port")
        choice_sensor = wx.ComboBox(
            self,
            -1,
            "",
            size=wx.Size(90, 23),
            choices=const.FT_SENSOR_MODE,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        choice_sensor.SetSelection(0)
        choice_sensor.SetToolTip(tooltip)
        choice_sensor.Bind(wx.EVT_COMBOBOX, self.OnChoiceFTSensor)
        self.choice_sensor = choice_sensor

        # Show sensor selection for certain trackers only
        if self.show_sensor_options:
            choice_sensor.Show(True)
        else:
            choice_sensor.Show(False)

        tooltip = _("Reset all fiducials")
        btn_reset = wx.Button(self, -1, _("Reset"), size=wx.Size(90, 30))
        btn_reset.SetToolTip(tooltip)
        btn_reset.Bind(wx.EVT_BUTTON, self.OnReset)

        # Buttons to finish or cancel object registration
        tooltip = _("Registration done")
        btn_ok = wx.Button(self, wx.ID_OK, _("Done"), size=wx.Size(90, 30))
        btn_ok.SetToolTip(tooltip)

        extra_sizer = wx.FlexGridSizer(cols=1, hgap=5, vgap=10)
        extra_sizer.AddMany([choice_obj_id, btn_reset, btn_ok, choice_sensor])

        # Buttons for object fiducials
        self.buttons = OrderedFiducialButtons(
            self, const.OBJECT_FIDUCIALS, self.IsObjectFiducialSet
        )

        for index, btn in enumerate(self.buttons):
            btn.Bind(wx.EVT_BUTTON, partial(self.OnObjectFiducialButton, index))

        self.buttons.FocusNext()

        # Display fiducial coordinates
        for m in range(0, 4):
            for n in range(0, 3):
                self.txt_coord[m].append(
                    wx.StaticText(self, -1, label="-", style=wx.ALIGN_RIGHT, size=wx.Size(40, 23))
                )

        coord_sizer = wx.GridBagSizer(hgap=20, vgap=5)

        for m, button in enumerate(self.buttons):
            coord_sizer.Add(button, pos=wx.GBPosition(m, 0))
            for n in range(0, 3):
                coord_sizer.Add(
                    self.txt_coord[m][n], pos=wx.GBPosition(m, n + 1), flag=wx.TOP, border=5
                )

        # Hide "Fixed fiducial" for trackers other than Polhemus
        if not self.show_sensor_options:
            self.buttons[const.OBJECT_FIDUCIAL_FIXED].Hide()
            for coord in self.txt_coord[const.OBJECT_FIDUCIAL_FIXED]:
                coord.Hide()

        group_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=50, vgap=5)
        group_sizer.AddMany([(coord_sizer, 0, wx.LEFT, 20), (extra_sizer, 0, wx.LEFT, 10)])

        name_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        lbl_name = wx.StaticText(self, -1, _("Name the coil:"))
        self.name_box = name_box = wx.TextCtrl(self, -1, _("coil1"))
        name_sizer.AddMany(
            [(lbl_name, 1, wx.ALIGN_CENTER_VERTICAL), (name_box, 1, wx.ALIGN_CENTER_VERTICAL)]
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.interactor, 0, wx.EXPAND)
        main_sizer.Add(
            group_sizer, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.TOP | wx.RIGHT | wx.BOTTOM, 10
        )
        if self.n_coils > 1:  # Multicoil
            main_sizer.Add(name_sizer, 0, wx.EXPAND)
        else:  # Single coil mode
            # Hide obj_id combobox
            choice_obj_id.Enable(False)
            choice_obj_id.Show(False)
            name_sizer.Show(False)
            name_sizer.ShowItems(False)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

    def _init_pedal(self) -> None:
        def set_fiducial_callback(state):
            index = self.buttons.focused_index
            if state and index is not None:
                self.SetObjectFiducial(index)

        self.pedal_connector.add_callback(
            "fiducial", set_fiducial_callback, remove_when_released=False, panel=self
        )
        self.Bind(wx.EVT_BUTTON, self.OnOk)

    def ObjectImportDialog(self) -> Literal[0, 1]:
        msg = _("Would like to use InVesalius default object?")
        if sys.platform == "darwin":
            dlg = wx.MessageDialog(None, "", msg, wx.ICON_QUESTION | wx.YES_NO)
        else:
            dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.ICON_QUESTION | wx.YES_NO)
        answer = dlg.ShowModal()
        dlg.Destroy()

        if answer == wx.ID_YES:
            return 1
        else:  # answer == wx.ID_NO:
            return 0

    def ShowObject(self, polydata: vtkPolyData) -> None:
        if polydata.GetNumberOfPoints() == 0:
            wx.MessageBox(
                _("InVesalius was not able to import this surface"), _("Import surface error")
            )

        transform = vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(polydata)
        transform_filt.Update()

        normals = vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        mapper.ScalarVisibilityOff()
        # mapper.ImmediateModeRenderingOn()

        obj_actor = vtkActor()
        obj_actor.SetMapper(mapper)

        self.ball_actors[0], self.text_actors[0] = self.OnCreateObjectText("Left", (0, 55, 0))
        self.ball_actors[1], self.text_actors[1] = self.OnCreateObjectText("Right", (0, -55, 0))
        self.ball_actors[2], self.text_actors[2] = self.OnCreateObjectText("Anterior", (23, 0, 0))

        # Match actor colors with fiducial buttons
        def set_actor_colors(n: int, color_float: Sequence[float]) -> None:
            if n != const.OBJECT_FIDUCIAL_FIXED:
                self.ball_actors[n].GetProperty().SetColor(color_float)
                self.text_actors[n].GetProperty().SetColor(color_float)
                self.Refresh()

        self.buttons.set_actor_colors = set_actor_colors
        self.buttons.Update()

        self.ren.AddActor(obj_actor)
        self.ren.ResetCamera()

        self.interactor.Render()

    def ConfigureObject(self) -> bool:
        use_default_coil = self.ObjectImportDialog()

        if use_default_coil:
            path = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

        else:
            path = ShowImportMeshFilesDialog()

            # Return if the open file dialog was canceled.
            if path is None:
                return False

            # Validate the file extension.
            valid_extensions = (".stl", "ply", ".obj", ".vtp")
            if not path.lower().endswith(valid_extensions):
                wx.MessageBox(
                    _("File format not recognized by InVesalius"), _("Import surface error")
                )
                return False

        if _has_win32api:
            path = win32api.GetShortPathName(path)

        self.coil_path = path.encode(const.FS_ENCODE)

        return True

    def InitializeObject(self) -> None:
        success = self.ConfigureObject()
        if success:
            # XXX: Is this back and forth encoding and decoding needed? Maybe path could be encoded
            #   only where it is needed, and mostly remain as a string in self.coil_path and elsewhere.
            #
            object_path = self.coil_path.decode(const.FS_ENCODE)
            self.polydata = pu.LoadPolydata(path=object_path)
            self.ShowObject(polydata=self.polydata)

    def OnCreateObjectText(self, name: str, coord: Sequence[float]) -> Tuple[vtkActor, vtkFollower]:
        ball_source = vtkSphereSource()
        ball_source.SetRadius(3)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(ball_source.GetOutputPort())
        ball_actor = vtkActor()
        ball_actor.SetMapper(mapper)
        ball_actor.SetPosition(coord)
        ball_actor.GetProperty().SetColor(const.RED_COLOR_FLOAT)

        textSource = vtkVectorText()
        textSource.SetText(name)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(textSource.GetOutputPort())
        tactor = vtkFollower()
        tactor.SetMapper(mapper)
        tactor.GetProperty().SetColor(const.RED_COLOR_FLOAT)
        tactor.SetScale(5)
        ball_position = ball_actor.GetPosition()
        tactor.SetPosition(ball_position[0] + 5, ball_position[1] + 5, ball_position[2] + 10)
        self.ren.AddActor(tactor)
        tactor.SetCamera(self.ren.GetActiveCamera())
        self.ren.AddActor(ball_actor)
        return ball_actor, tactor

    def IsObjectFiducialSet(self, fiducial_index: int) -> bool:
        fiducial = self.obj_fiducials[fiducial_index]
        return not np.isnan(fiducial).any()

    def OnObjectFiducialButton(self, index: int, evt: wx.CommandEvent) -> None:
        button = self.buttons[index]

        if button is self.buttons.focused:
            self.SetObjectFiducial(index)
        elif self.IsObjectFiducialSet(index):
            self.ResetObjectFiducial(index)
        else:
            self.buttons.Focus(index)

    def SetObjectFiducial(self, fiducial_index: int) -> None:
        if not self.tracker.IsTrackerInitialized():
            ShowNavigationTrackerWarning(0, "choose")
            return

        marker_visibilities, coord, coord_raw = self.tracker.GetTrackerCoordinates(
            # XXX: Always use static reference mode when getting the coordinates. This is what the
            #      code did previously, as well. At some point, it should probably be thought through
            #      if this is actually what we want or if it should be changed somehow.
            #
            ref_mode_id=const.STATIC_REF,
            n_samples=const.CALIBRATION_TRACKER_SAMPLES,
        )

        # If coil or probe markers are not visible, show a warning and return early.
        probe_visible, head_visible, *coils_visible = marker_visibilities

        if not self.show_sensor_options:
            if not probe_visible:
                ShowNavigationTrackerWarning(0, "probe marker not visible")
                return

            if not coils_visible[self.obj_id - 2]:
                ShowNavigationTrackerWarning(0, "coil marker not visible")
                return

        # XXX: The condition below happens when setting the "fixed" coordinate in the object calibration.
        #      The case is not handled by GetTrackerCoordinates function, therefore redo some computation
        #      that is already done once by GetTrackerCoordinates, namely, invert the y-coordinate.
        #
        #      (What is done here does not seem to be completely consistent with "always use static reference
        #      mode" principle above, but it's hard to come up with a simple change to increase the consistency
        #      and not change the function to the point of potentially breaking it.)
        #
        if self.obj_id and fiducial_index == const.OBJECT_FIDUCIAL_FIXED:
            coord = coord_raw[self.obj_id, :]
        else:
            coord = coord_raw[0, :]

        Publisher.sendMessage("Set object fiducial", fiducial_index=fiducial_index)

        # Update buttons and text controls with tracker coordinates
        if coord is not None or np.sum(coord) != 0.0:
            self.obj_fiducials[fiducial_index, :] = coord[:3]
            self.obj_orients[fiducial_index, :] = coord[3:]
            self.buttons.SetFocused()
            for i in [0, 1, 2]:
                self.txt_coord[fiducial_index][i].SetLabel(str(round(coord[i], 1)))
            self.Refresh()
        else:
            ShowNavigationTrackerWarning(0, "choose")

        # Collect the "fixed fiducial" at the same time as anterior for trackers other than Polhemus
        if fiducial_index == const.OBJECT_FIDUCIAL_ANTERIOR and not self.show_sensor_options:
            self.SetObjectFiducial(const.OBJECT_FIDUCIAL_FIXED)

    def ResetObjectFiducials(self) -> None:
        for m in range(0, 4):
            self.ResetObjectFiducial(m)
        self.buttons.Update()

    def ResetObjectFiducial(self, index: int) -> None:
        self.obj_fiducials[index, :] = np.full([1, 3], np.nan)
        self.obj_orients[index, :] = np.full([1, 3], np.nan)
        for coord_index in range(0, 3):
            self.txt_coord[index][coord_index].SetLabel("-")
        self.buttons.Unset(index)

    def OnReset(self, evt: wx.CommandEvent) -> None:
        self.ResetObjectFiducials()

    def OnChooseObjID(self, evt: wx.CommandEvent) -> None:
        self.obj_id = int(evt.GetEventObject().GetStringSelection())

        # choice_sensor is only shown for relevant trackers like Polhemus FASTRAK
        # If obj_id=0, (ie. the stylus is attached to the coil), the sensor is not used, so hide this
        self.choice_sensor.Show(
            self.obj_id == 0 and self.tracker_id in const.TRACKERS_WITH_SENSOR_OPTIONS
        )

        # When obj_id is changed the object fiducials are reset
        self.ResetObjectFiducials()
        self.Layout()

    def OnChoiceFTSensor(self, evt: wx.CommandEvent) -> None:
        if evt.GetSelection():
            self.obj_id = 3
        else:
            self.obj_id = 0

    def GetValue(
        self,
    ) -> Tuple[np.ndarray, np.ndarray, int, Optional[bytes], Optional[vtkPolyData]]:
        if self.n_coils > 1:
            coil_name = self.name_box.GetValue().strip()
        else:
            coil_name = "default_coil"

        return (
            coil_name,
            self.coil_path,
            self.obj_fiducials,
            self.obj_orients,
            self.obj_id,
            self.tracker_id,
        )

    def OnOk(self, evt: wx.CommandEvent) -> None:
        if evt.GetId() == wx.ID_OK:
            # This should always be called when the dialog is closed. Seems to be working correctly.
            self.pedal_connector.remove_callback("fiducial", panel=self)

        evt.Skip()


class ICPCorregistrationDialog(wx.Dialog):
    def __init__(self, navigation: "Navigation", tracker: "Tracker"):
        import invesalius.project as prj

        self.tracker = tracker
        self.m_change = navigation.m_change
        self.obj_ref_id = 2
        self.obj_name = None
        self.obj_actor = None
        self.polydata = None
        self.m_icp = None
        self.initial_focus = None
        self.prev_error = None
        self.final_error = None
        self.icp_mode = 0
        self.actors_static_points = []
        self.point_coord = []
        self.actors_transformed_points = []

        self.obj_fiducials = np.full([5, 3], np.nan)
        self.obj_orients = np.full([5, 3], np.nan)

        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Refine Corregistration"),
            size=(380, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
        )

        self.proj = prj.Project()

        self._init_gui()

    def _init_gui(self) -> None:
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        self.interactor.Enable(1)
        self.ren = vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.HandleContinuousAcquisition, self.timer)

        txt_surface = wx.StaticText(self, -1, _("Select the surface:"))
        txt_mode = wx.StaticText(self, -1, _("Registration mode:"))

        combo_surface_name = wx.ComboBox(
            self, -1, size=(210, 23), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        for n in range(len(self.proj.surface_dict)):
            combo_surface_name.Insert(str(self.proj.surface_dict[n].name), n)

        self.combo_surface_name = combo_surface_name

        init_surface = 0
        combo_surface_name.SetSelection(init_surface)
        self.surface = self.proj.surface_dict[init_surface].polydata
        self.LoadActor()

        tooltip = _("Choose the registration mode:")
        choice_icp_method = wx.ComboBox(
            self,
            -1,
            "",
            size=(100, 23),
            choices=([_("Affine"), _("Similarity"), _("RigidBody")]),
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        choice_icp_method.SetSelection(0)
        choice_icp_method.SetToolTip(tooltip)
        choice_icp_method.Bind(wx.EVT_COMBOBOX, self.OnChoiceICPMethod)

        # Buttons to acquire and remove points
        create_point = wx.Button(self, -1, label=_("Create point"))
        create_point.Bind(wx.EVT_BUTTON, self.CreatePoint)

        cont_point = wx.ToggleButton(self, -1, label=_("Continuous acquisition"))
        cont_point.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnContinuousAcquisitionButton, btn=cont_point)
        )
        self.cont_point = cont_point

        btn_reset = wx.Button(self, -1, label=_("Reset points"))
        btn_reset.Bind(wx.EVT_BUTTON, self.OnResetPoints)

        btn_apply_icp = wx.Button(self, -1, label=_("Apply registration"))
        btn_apply_icp.Bind(wx.EVT_BUTTON, self.OnICP)
        btn_apply_icp.Enable(False)
        self.btn_apply_icp = btn_apply_icp

        tooltip = _("Refine done")
        btn_ok = wx.Button(self, wx.ID_OK, _("Done"))
        btn_ok.SetToolTip(tooltip)
        btn_ok.Enable(False)
        self.btn_ok = btn_ok

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        top_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=50, vgap=5)
        top_sizer.AddMany([txt_surface, txt_mode, combo_surface_name, choice_icp_method])

        btn_acqui_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=15, vgap=15)
        btn_acqui_sizer.AddMany([create_point, cont_point, btn_reset])

        btn_ok_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=20, vgap=20)
        btn_ok_sizer.AddMany([btn_apply_icp, btn_ok, btn_cancel])

        btn_sizer = wx.FlexGridSizer(rows=2, cols=1, hgap=50, vgap=20)
        btn_sizer.AddMany(
            [(btn_acqui_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL), (btn_ok_sizer, 1, wx.ALIGN_RIGHT)]
        )

        self.progress = wx.Gauge(self, -1)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(top_sizer, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)
        main_sizer.Add(self.interactor, 0, wx.EXPAND)
        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.TOP | wx.BOTTOM, 10)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

    def LoadActor(self) -> None:
        """
        Load the selected actor from the project (self.surface) into the scene
        :return:
        """
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(self.surface)
        mapper.ScalarVisibilityOff()
        # mapper.ImmediateModeRenderingOn()

        obj_actor = vtkActor()
        obj_actor.SetMapper(mapper)
        self.obj_actor = obj_actor

        poses_recorded = vtku.Text()
        poses_recorded.SetSize(const.TEXT_SIZE_LARGE)
        poses_recorded.SetPosition((const.X, const.Y))
        poses_recorded.ShadowOff()
        poses_recorded.SetValue("Poses recorded: ")

        collect_points = vtku.Text()
        collect_points.SetSize(const.TEXT_SIZE_LARGE)
        collect_points.SetPosition((const.X + 0.35, const.Y))
        collect_points.ShadowOff()
        collect_points.SetValue("0")
        self.collect_points = collect_points

        txt_markers_not_detected = vtku.Text()
        txt_markers_not_detected.SetSize(const.TEXT_SIZE_LARGE)
        txt_markers_not_detected.SetPosition((const.X + 0.50, const.Y))
        txt_markers_not_detected.ShadowOff()
        txt_markers_not_detected.SetColour((1, 0, 0))
        txt_markers_not_detected.SetValue("Markers not detected")
        txt_markers_not_detected.actor.VisibilityOff()
        self.txt_markers_not_detected = txt_markers_not_detected.actor

        self.ren.AddActor(obj_actor)
        self.ren.AddActor(poses_recorded.actor)
        self.ren.AddActor(collect_points.actor)
        self.ren.AddActor(txt_markers_not_detected.actor)
        self.ren.ResetCamera()
        self.interactor.Render()

    def RemoveAllActors(self) -> None:
        self.ren.RemoveAllViewProps()
        self.actors_static_points = []
        self.point_coord = []
        self.actors_transformed_points = []
        self.m_icp = None
        self.SetProgress(0)
        self.btn_apply_icp.Enable(False)
        self.btn_ok.Enable(False)
        self.ren.ResetCamera()
        self.interactor.Render()

    def RemoveSinglePointActor(self) -> None:
        self.ren.RemoveActor(self.actors_static_points[-1])
        self.actors_static_points.pop()
        self.point_coord.pop()
        self.collect_points.SetValue(str(int(self.collect_points.GetValue()) - 1))
        self.interactor.Render()

    def GetCurrentCoord(self) -> Tuple[Tuple, List[bool]]:
        coord_raw, marker_visibilities = self.tracker.TrackerCoordinates.GetCoordinates()
        coord, _ = dcr.corregistrate_probe(self.m_change, None, coord_raw, const.DEFAULT_REF_MODE)
        return coord[:3], marker_visibilities

    def AddMarker(self, size: int, colour: Tuple[int, int, int], coord: np.ndarray) -> None:
        """
        Points are rendered into the scene. These points give visual information about the registration.
        :param size: value of the marker size
        :type size: int
        :param colour: RGB Color Code for the marker
        :type colour: tuple (int(R),int(G),int(B))
        :param coord: x, y, z of the marker
        :type coord: np.ndarray
        """

        x, y, z = coord[0], -coord[1], coord[2]

        ball_ref = vtkSphereSource()
        ball_ref.SetRadius(size)
        ball_ref.SetCenter(x, y, z)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtkProperty()
        prop.SetColor(colour[0:3])

        # adding a new actor for the present ball
        sphere_actor = vtkActor()

        sphere_actor.SetMapper(mapper)
        sphere_actor.SetProperty(prop)

        self.ren.AddActor(sphere_actor)
        self.actors_static_points.append(sphere_actor)
        self.point_coord.append([x, y, z])

        self.collect_points.SetValue(str(int(self.collect_points.GetValue()) + 1))

        self.interactor.Render()

        if len(self.point_coord) >= 5 and self.btn_apply_icp.IsEnabled() is False:
            self.btn_apply_icp.Enable(True)

        if self.progress.GetValue() != 0:
            self.SetProgress(0)

    def SetProgress(self, progress: float) -> None:
        self.progress.SetValue(int(progress * 100))
        self.interactor.Render()

    def vtkmatrix_to_numpy(self, matrix: vtkMatrix4x4) -> np.ndarray:
        """
        Copies the elements of a vtkMatrix4x4 into a numpy array.

        :param matrix: The matrix to be copied into an array.
        :type matrix: vtkMatrix4x4
        :rtype: numpy.ndarray
        """
        m = np.ones((4, 4))
        for i in range(4):
            for j in range(4):
                m[i, j] = matrix.GetElement(i, j)
        return m

    def SetCameraVolume(self, position: Sequence[float]) -> None:
        """
        Positioning of the camera based on the acquired point
        :param position: x, y, z of the last acquired point
        :return:
        """
        cam_focus = np.array([position[0], -position[1], position[2]])
        cam = self.ren.GetActiveCamera()

        if self.initial_focus is None:
            self.initial_focus = np.array(cam.GetFocalPoint())

        cam_pos0 = np.array(cam.GetPosition())
        cam_focus0 = np.array(cam.GetFocalPoint())
        v0 = cam_pos0 - cam_focus0
        v0n = np.sqrt(inner1d(v0, v0))

        v1 = cam_focus - self.initial_focus

        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1 / v1n) * v0n + cam_focus

        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)

        self.interactor.Render()

    def CheckTransformedPointsDistribution(
        self, points: Union[Sequence[float], np.ndarray]
    ) -> np.floating:
        from scipy.spatial.distance import pdist

        return np.mean(pdist(points))

    def ErrorEstimation(self, surface, points: np.ndarray) -> np.floating:
        """
        Estimation of the average squared distance between the cloud of points to the closest mesh
        :param surface: Surface polydata of the scene
        :type surface: polydata
        :param points: Cloud of points
        :type points: np.ndarray
        :return: mean distance
        """
        cell_locator = vtkCellLocator()
        cell_locator.SetDataSet(surface)
        cell_locator.BuildLocator()

        cellId = mutable(0)
        c = [0.0, 0.0, 0.0]
        subId = mutable(0)
        d = mutable(0.0)
        error = []
        for i in range(len(points)):
            cell_locator.FindClosestPoint(points[i], c, cellId, subId, d)
            error.append(np.sqrt(float(d)))

        return np.mean(error)

    def DistanceBetweenPointAndSurface(self, surface, points: np.ndarray) -> np.floating:
        """
        Estimation of the squared distance between the point to the closest mesh
        :param surface: Surface polydata of the scene
        :type surface: polydata
        :param points: single points
        :type points: np.ndarray
        :return: mean distance
        """
        cell_locator = vtkCellLocator()
        cell_locator.SetDataSet(surface)
        cell_locator.BuildLocator()

        cellId = mutable(0)
        c = [0.0, 0.0, 0.0]
        subId = mutable(0)
        d = mutable(0.0)
        cell_locator.FindClosestPoint(points, c, cellId, subId, d)

        return np.sqrt(float(d))

    def OnComboName(self, evt: wx.CommandEvent) -> None:
        # surface_name = evt.GetString()
        surface_index = evt.GetSelection()
        self.surface = self.proj.surface_dict[surface_index].polydata
        if self.obj_actor:
            self.RemoveAllActors()
        self.LoadActor()

    def OnChoiceICPMethod(self, evt: wx.CommandEvent) -> None:
        self.icp_mode = evt.GetSelection()

    def OnContinuousAcquisitionButton(
        self, evt: Optional[wx.CommandEvent] = None, btn: Optional[wx.ToggleButton] = None
    ) -> None:
        assert btn is not None, "btn must be provided"
        value = btn.GetValue()
        if value:
            self.timer.Start(500)
        else:
            self.timer.Stop()

    def HandleContinuousAcquisition(self, evt: wx.TimerEvent) -> None:
        self.CreatePoint()

    def CreatePoint(self, evt: Optional[wx.CommandEvent] = None) -> None:
        current_coord, marker_visibilities = self.GetCurrentCoord()

        probe_visible, head_visible, *coils_visible = marker_visibilities

        if probe_visible and head_visible:
            self.AddMarker(3, (1, 0, 0), current_coord)
            self.txt_markers_not_detected.VisibilityOff()
            if self.DistanceBetweenPointAndSurface(self.surface, self.point_coord[-1]) >= 20:
                self.OnDeleteLastPoint()
                ReportICPPointError()
            else:
                self.SetCameraVolume(current_coord)
        else:
            self.txt_markers_not_detected.VisibilityOn()
            self.interactor.Render()

    def OnDeleteLastPoint(self) -> None:
        # Stop continuous acquisition if it is running.
        if self.cont_point:
            self.cont_point.SetValue(False)
            self.OnContinuousAcquisitionButton(btn=self.cont_point)

        self.RemoveSinglePointActor()

    def OnResetPoints(self, evt: wx.CommandEvent) -> None:
        # Stop continuous acquisition if it is running.
        if self.cont_point:
            self.cont_point.SetValue(False)
            self.OnContinuousAcquisitionButton(evt=None, btn=self.cont_point)

        self.RemoveAllActors()
        self.LoadActor()

    def OnICP(self, evt: wx.CommandEvent) -> None:
        if self.cont_point:
            self.cont_point.SetValue(False)
            self.OnContinuousAcquisitionButton(evt=None, btn=self.cont_point)

        self.SetProgress(0.3)
        time.sleep(1)

        sourcePoints = np.array(self.point_coord)
        sourcePoints_vtk = vtkPoints()

        for i in range(len(sourcePoints)):
            sourcePoints_vtk.InsertNextPoint(sourcePoints[i])

        source = vtkPolyData()
        source.SetPoints(sourcePoints_vtk)

        icp = vtkIterativeClosestPointTransform()
        icp.SetSource(source)
        icp.SetTarget(self.surface)

        self.SetProgress(0.5)

        if self.icp_mode == 0:
            print("Affine mode")
            icp.GetLandmarkTransform().SetModeToAffine()
        elif self.icp_mode == 1:
            print("Similarity mode")
            icp.GetLandmarkTransform().SetModeToSimilarity()
        elif self.icp_mode == 2:
            print("Rigid mode")
            icp.GetLandmarkTransform().SetModeToRigidBody()

        # icp.DebugOn()
        icp.SetMaximumNumberOfIterations(1000)

        icp.Modified()

        icp.Update()

        self.m_icp = self.vtkmatrix_to_numpy(icp.GetMatrix())

        icpTransformFilter = vtkTransformPolyDataFilter()
        icpTransformFilter.SetInputData(source)

        icpTransformFilter.SetTransform(icp)
        icpTransformFilter.Update()

        transformedSource: vtkPolyData = icpTransformFilter.GetOutput()

        transformed_points = []

        # removes previously transformed points
        if self.actors_transformed_points:
            for i in self.actors_transformed_points:
                self.ren.RemoveActor(i)
            self.actors_transformed_points = []

        for i in range(transformedSource.GetNumberOfPoints()):
            p = [0, 0, 0]
            transformedSource.GetPoint(i, p)
            transformed_points.append(p)

            point = vtkSphereSource()
            point.SetCenter(p)
            point.SetRadius(3)
            point.SetPhiResolution(3)
            point.SetThetaResolution(3)

            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(point.GetOutputPort())

            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor((0, 1, 0))
            self.actors_transformed_points.append(actor)

            self.ren.AddActor(actor)

        if self.CheckTransformedPointsDistribution(transformed_points) <= 25:
            ReportICPDistributionError()

        self.prev_error = self.ErrorEstimation(self.surface, sourcePoints)
        self.final_error = self.ErrorEstimation(self.surface, transformed_points)

        self.interactor.Render()

        self.SetProgress(1)

        self.btn_ok.Enable(True)

    def GetValue(self):
        return (
            self.m_icp,
            self.point_coord,
            self.actors_transformed_points,
            self.prev_error,
            self.final_error,
        )


class EfieldConfiguration(wx.Dialog):
    def __init__(self):
        import invesalius.project as prj

        self.polydata = None

        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Set Efield Configuration"),
            size=(380, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
        )

        self.proj = prj.Project()
        self._init_gui()
        self.brain_surface = None
        self.scalp_surface = None

    def _init_gui(self) -> None:
        tooltip = _("Load Brain Meshes")
        btn_act = wx.Button(self, -1, _("Load"), size=wx.Size(100, 23))
        btn_act.SetToolTip(tooltip)
        btn_act.Enable(True)
        btn_act.Bind(wx.EVT_BUTTON, self.OnAddMeshes)

        txt_brain_surface = wx.StaticText(self, -1, _("Select the brain surface:"))

        combo_brain_surface_name = wx.ComboBox(
            self, -1, size=(210, 23), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_brain_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_brain_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboNameBrainSurface)
        for n in range(len(self.proj.surface_dict)):
            combo_brain_surface_name.Insert(str(self.proj.surface_dict[n].name), n)

        txt_scalp_surface = wx.StaticText(self, -1, _("Select the scalp surface:"))
        combo_brain_scalp_name = wx.ComboBox(
            self, -1, size=(210, 23), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_brain_scalp_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_brain_scalp_name.Bind(wx.EVT_COMBOBOX, self.OnComboNameBrainSurface)
        for n in range(len(self.proj.surface_dict)):
            combo_brain_scalp_name.Insert(str(self.proj.surface_dict[n].name), n)

        tooltip1 = _("Target orientation done")
        btn_ok = wx.Button(self, wx.ID_OK, _("Done"))
        btn_ok.SetToolTip(tooltip1)
        self.btn_ok = btn_ok

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")
        btn_ok_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=20, vgap=20)
        btn_ok_sizer.AddMany([btn_ok, btn_cancel])

        btn_sizer = wx.FlexGridSizer(rows=2, cols=1, hgap=50, vgap=20)
        btn_sizer.AddMany([(btn_ok_sizer, 1, wx.ALIGN_RIGHT)])

        line_btns = wx.BoxSizer(wx.HORIZONTAL)
        line_btns.Add(btn_act, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        top_sizer = wx.FlexGridSizer(rows=3, cols=3, hgap=50, vgap=5)
        top_sizer.AddMany(
            [
                txt_brain_surface,
                txt_scalp_surface,
                (wx.StaticText(self, -1, ""), 0, wx.EXPAND),
                combo_brain_surface_name,
                combo_brain_scalp_name,
                (wx.StaticText(self, -1, ""), 0, wx.EXPAND),
            ]
        )
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_btns, 0, wx.TOP | wx.ALIGN_LEFT)
        main_sizer.Add(top_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

    def OnComboNameBrainSurface(self, evt: wx.CommandEvent) -> Union[str, vtkPolyData]:
        surface_index = evt.GetSelection()
        self.brain_surface = self.proj.surface_dict[surface_index].polydata
        return self.brain_surface

    def OnComboNameScalpSurface(self, evt: wx.CommandEvent) -> Union[str, vtkPolyData]:
        surface_index = evt.GetSelection()
        self.scalp_surface = self.proj.surface_dict[surface_index].polydata
        return self.scalp_surface

    def OnAddMeshes(self, evt: wx.CommandEvent) -> None:
        filename = ShowImportMeshFilesDialog()
        if filename:
            convert_to_inv = ImportMeshCoordSystem()
            Publisher.sendMessage("Update convert_to_inv flag", convert_to_inv=convert_to_inv)
        Publisher.sendMessage("Import bin file", filename=filename)


class CreateBrainTargetDialog(wx.Dialog):
    def __init__(
        self,
        marker,
        mTMS: Optional["mTMS"] = None,
        brain_target: bool = False,
        brain_actor: Optional[vtkActor] = None,
    ):
        import invesalius.project as prj

        self.obj_actor = None
        self.polydata = None
        self.initial_focus = None

        self.mTMS = mTMS
        self.marker = marker
        self.brain_target = brain_target
        self.peel_brain_actor = brain_actor
        self.brain_target_actor_list = []
        self.coil_target_actor_list = []
        self.center_brain_target_actor = None
        self.marker_actor = None
        self.dummy_coil_actor = None
        self.m_target = None

        self.spinning = False
        self.rotationX = 0
        self.rotationY = 0
        self.rotationZ = 0

        self.obj_fiducials = np.full([5, 3], np.nan)
        self.obj_orients = np.full([5, 3], np.nan)

        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            _("Set target Orientation"),
            size=(380, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
        )

        self.proj = prj.Project()

        self._init_gui()

    def _init_gui(self) -> None:
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        self.interactor.Enable(1)
        self.ren = vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)
        self.actor_style = vtkInteractorStyleTrackballActor()
        self.camera_style = vtkInteractorStyleTrackballCamera()

        self.picker = vtkCellPicker()
        self.picker.SetTolerance(1e-3)
        # self.picker.SetUseCells(True)
        self.interactor.SetPicker(self.picker)
        self.actor_style.AddObserver("RightButtonPressEvent", self.OnCrossMouseClick)
        self.actor_style.AddObserver("MiddleButtonPressEvent", self.OnWheelMouseClick)

        self.interactor.SetInteractorStyle(self.actor_style)
        self.actor_style.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.actor_style.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)
        self.actor_style.AddObserver("MouseMoveEvent", self.OnSpinMove)
        self.actor_style.AddObserver("MouseWheelForwardEvent", self.OnZoomMove)
        self.actor_style.AddObserver("MouseWheelBackwardEvent", self.OnZoomMove)

        self.camera_style.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.camera_style.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)
        self.camera_style.AddObserver("MouseMoveEvent", self.OnSpinMove)
        self.camera_style.AddObserver("MouseWheelForwardEvent", self.OnZoomMove)
        self.camera_style.AddObserver("MouseWheelBackwardEvent", self.OnZoomMove)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnDepth)

        txt_surface = wx.StaticText(self, -1, _("Select the surface:"))

        combo_surface_name = wx.ComboBox(
            self, -1, size=(210, 23), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboNameScalpSurface)
        for n in range(len(self.proj.surface_dict)):
            combo_surface_name.Insert(str(self.proj.surface_dict[n].name), n)

        txt_brain_surface = wx.StaticText(self, -1, _("Select the brain surface:"))

        combo_brain_surface_name = wx.ComboBox(
            self, -1, size=(210, 23), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_brain_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_brain_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboNameBrainSurface)
        for n in range(len(self.proj.surface_dict)):
            combo_brain_surface_name.Insert(str(self.proj.surface_dict[n].name), n)

        init_surface = 0
        combo_surface_name.SetSelection(init_surface)
        combo_brain_surface_name.SetSelection(init_surface)
        self.surface = self.proj.surface_dict[init_surface].polydata
        self.brain_surface = self.proj.surface_dict[init_surface].polydata
        if self.peel_brain_actor:
            self.peel_brain_actor.PickableOff()
            self.ren.AddActor(self.peel_brain_actor)
        self.obj_actor = self.LoadActor(self.surface)
        if self.brain_target:
            self.brain_surface = self.surface
        else:
            self.brain_actor = self.LoadActor(self.brain_surface)
        self.coil_pose_actor = self.LoadTarget()

        self.chk_show_surface = wx.CheckBox(self, wx.ID_ANY, _("Show scalp surface"))
        self.chk_show_surface.Bind(wx.EVT_CHECKBOX, self.OnCheckBoxScalp)
        self.chk_show_surface.SetValue(True)
        self.chk_show_brain_surface = wx.CheckBox(self, wx.ID_ANY, _("Show brain surface"))
        self.chk_show_brain_surface.Bind(wx.EVT_CHECKBOX, self.OnCheckBoxBrain)
        self.chk_show_brain_surface.SetValue(True)

        reset_orientation = wx.Button(self, -1, label=_("Reset arrow orientation"))
        reset_orientation.Bind(wx.EVT_BUTTON, self.OnResetOrientation)

        change_view = wx.Button(self, -1, label=_("Change view"))
        change_view.Bind(wx.EVT_BUTTON, self.OnChangeView)

        create_random_target_grid = wx.Button(self, -1, label=_("Create random coil target grid"))
        create_random_target_grid.Bind(wx.EVT_BUTTON, self.OnCreateRandomTargetGrid)

        create_target_grid = wx.Button(self, -1, label=_("Create coil target grid"))
        create_target_grid.Bind(wx.EVT_BUTTON, self.OnCreateTargetGrid)

        create_brain_grid = wx.Button(self, -1, label=_("Create brain target grid"))
        create_brain_grid.Bind(wx.EVT_BUTTON, self.OnCreateBrainGrid)

        send_to_mtms = wx.Button(self, -1, label=_("Send to mTMS"))
        send_to_mtms.Bind(wx.EVT_BUTTON, self.OnSendMtms)
        send_to_mtms.Hide()

        text_rotation_x = wx.StaticText(self, -1, _("Rotation X:"))

        slider_rotation_x = wx.Slider(
            self, -1, 0, -180, 180, style=wx.SL_HORIZONTAL
        )  # |wx.SL_AUTOTICKS)
        slider_rotation_x.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider_rotation_x.Bind(wx.EVT_SLIDER, self.OnRotationX)
        self.slider_rotation_x = slider_rotation_x

        text_rotation_y = wx.StaticText(self, -1, _("Rotation Y:"))

        slider_rotation_y = wx.Slider(
            self, -1, 0, -180, 180, style=wx.SL_HORIZONTAL
        )  # |wx.SL_AUTOTICKS)
        slider_rotation_y.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider_rotation_y.Bind(wx.EVT_SLIDER, self.OnRotationY)
        self.slider_rotation_y = slider_rotation_y

        text_rotation_z = wx.StaticText(self, -1, _("Rotation Z:"))

        slider_rotation_z = wx.Slider(
            self, -1, 0, -180, 180, style=wx.SL_HORIZONTAL
        )  # |wx.SL_AUTOTICKS)
        slider_rotation_z.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        slider_rotation_z.Bind(wx.EVT_SLIDER, self.OnRotationZ)
        self.slider_rotation_z = slider_rotation_z

        tooltip = _("Target orientation done")
        btn_ok = wx.Button(self, wx.ID_OK, _("Done"))
        btn_ok.SetToolTip(tooltip)
        self.btn_ok = btn_ok

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        if self.brain_target:
            self.chk_show_brain_surface.Hide()
            txt_brain_surface.Hide()
            combo_brain_surface_name.Hide()
            create_random_target_grid.Hide()
            create_target_grid.Hide()
            create_brain_grid.Hide()
            send_to_mtms.Show()

        top_sizer = wx.FlexGridSizer(rows=3, cols=3, hgap=50, vgap=5)
        top_sizer.AddMany(
            [
                txt_surface,
                txt_brain_surface,
                (wx.StaticText(self, -1, ""), 0, wx.EXPAND),
                combo_surface_name,
                combo_brain_surface_name,
                change_view,
                self.chk_show_surface,
                self.chk_show_brain_surface,
                (wx.StaticText(self, -1, ""), 0, wx.EXPAND),
            ]
        )
        btn_changes_sizer = wx.FlexGridSizer(rows=1, cols=5, hgap=20, vgap=20)
        btn_changes_sizer.AddMany([create_random_target_grid])
        btn_changes_sizer.AddMany([create_target_grid])
        btn_changes_sizer.AddMany([create_brain_grid])
        btn_changes_sizer.AddMany([send_to_mtms])
        btn_changes_sizer.AddMany([reset_orientation])
        btn_ok_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=20, vgap=20)
        btn_ok_sizer.AddMany([btn_ok, btn_cancel])

        flag_link = wx.EXPAND | wx.GROW | wx.RIGHT | wx.TOP
        flag_slider = wx.EXPAND | wx.GROW | wx.LEFT
        rotationx_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rotationy_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rotationz_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rotationx_sizer.AddMany(
            [
                (text_rotation_x, 0, flag_link, 0),
                (slider_rotation_x, 1, flag_slider, 4),
            ]
        )
        rotationy_sizer.AddMany(
            [(text_rotation_y, 0, flag_link, 0), (slider_rotation_y, 1, flag_slider, 4)]
        )
        rotationz_sizer.AddMany(
            [(text_rotation_z, 0, flag_link, 0), (slider_rotation_z, 1, flag_slider, 4)]
        )

        btn_sizer = wx.FlexGridSizer(rows=2, cols=1, hgap=50, vgap=20)
        btn_sizer.AddMany([(btn_ok_sizer, 1, wx.ALIGN_RIGHT)])

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(top_sizer, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)
        main_sizer.Add(self.interactor, 0, wx.EXPAND)
        main_sizer.Add(btn_changes_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        main_sizer.Add(rotationx_sizer, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(rotationy_sizer, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(rotationz_sizer, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

    def get_vtk_mouse_position(self) -> Tuple[int, int]:
        """
        Get Mouse position inside a wxVTKRenderWindowInteractorself. Return a
        tuple with X and Y position.
        Please use this instead of using iren.GetEventPosition because it's
        not returning the correct values on Mac with HighDPI display, maybe
        the same is happing with Windows and Linux, we need to test.
        """
        mposx, mposy = wx.GetMousePosition()
        cposx, cposy = self.interactor.ScreenToClient((mposx, mposy))
        mx, my = cposx, self.interactor.GetSize()[1] - cposy
        if sys.platform == "darwin":
            # It's needed to mutiple by scale factor in HighDPI because of
            # https://docs.wxpython.org/wx.glcanvas.GLCanvas.html
            # For now we are doing this only on Mac but it may be needed on
            # Windows and Linux too.
            scale = self.interactor.GetContentScaleFactor()
            mx *= scale
            my *= scale
        return int(mx), int(my)

    def OnCreateDummyCoil(self, target_actor: vtkActor) -> None:
        if self.dummy_coil_actor:
            self.RemoveActor(self.dummy_coil_actor)

        filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil_no_handle.stl")
        filename = utils.decode(filename, const.FS_ENCODE)
        reader = vtkSTLReader()
        if _has_win32api:
            obj_name = win32api.GetShortPathName(filename).encode(const.FS_ENCODE)
        else:
            obj_name = filename.encode(const.FS_ENCODE)

        reader.SetFileName(obj_name)
        reader.Update()
        obj_polydata = reader.GetOutput()

        transform = vtkTransform()
        transform.RotateZ(90)
        transform_filt = vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()
        obj_mapper = vtkPolyDataMapper()
        obj_mapper.SetInputData(transform_filt.GetOutput())
        self.dummy_coil_actor = vtkActor()
        self.dummy_coil_actor.SetMapper(obj_mapper)
        vtk_colors = vtkNamedColors()
        self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d("cornsilk4"))
        self.dummy_coil_actor.GetProperty().SetSpecular(0.5)
        self.dummy_coil_actor.GetProperty().SetSpecularPower(10)
        self.dummy_coil_actor.GetProperty().SetOpacity(0.3)
        self.dummy_coil_actor.SetVisibility(1)
        self.dummy_coil_actor.SetUserMatrix(target_actor.GetMatrix())
        self.dummy_coil_actor.SetScale(0.1)
        self.dummy_coil_actor.PickableOff()
        self.ren.AddActor(self.dummy_coil_actor)

    def OnWheelMouseClick(self, obj, evt) -> None:
        x, y = self.get_vtk_mouse_position()
        self.picker.Pick(x, y, 0, self.ren)
        if self.picker.GetActor():
            if self.brain_target:
                colour = [1, 0, 0]
            else:
                colour = [0, 0, 1]
            self.marker_actor.GetProperty().SetColor(colour)
            self.marker_actor = self.picker.GetActor()
            self.marker_actor.GetProperty().SetColor([0, 1, 0])
            self.rotationX = self.rotationY = self.rotationZ = 0
            self.slider_rotation_x.SetValue(0)
            self.slider_rotation_y.SetValue(0)
            self.slider_rotation_z.SetValue(0)
            if not self.brain_target:
                self.OnCreateDummyCoil(self.marker_actor)
            self.interactor.Render()

    def OnCrossMouseClick(self, obj, evt) -> None:
        if self.brain_target:
            self.obj_actor.PickableOn()
            if self.peel_brain_actor:
                self.peel_brain_actor.PickableOn()
            x, y = self.get_vtk_mouse_position()
            self.picker.Pick(x, y, 0, self.ren)
            x, y, z = self.picker.GetPickPosition()
            coord_flip = list(self.marker)
            coord_flip[1] = -coord_flip[1]
            if self.picker.GetActor():
                if self.marker_actor != self.coil_pose_actor:
                    self.marker_actor.GetProperty().SetColor([1, 0, 0])
                coord = [x, y, z, coord_flip[3], coord_flip[4], coord_flip[5]]
                brain_target_actor, _ = self.AddTarget(coord, colour=[1.0, 0.0, 0.0], scale=2)
                self.marker_actor.GetProperty().SetColor([0, 1, 0])
                self.brain_target_actor_list.append(brain_target_actor)
                self.OnResetOrientation()
            self.obj_actor.PickableOff()
            if self.peel_brain_actor:
                self.peel_brain_actor.PickableOff()
            self.interactor.Render()

    def OnCheckBoxScalp(self, evt: Optional[wx.CommandEvent] = None) -> None:
        status = self.chk_show_surface.GetValue()
        self.obj_actor.SetVisibility(status)
        self.interactor.Render()

    def OnCheckBoxBrain(self, evt: Optional[wx.CommandEvent] = None) -> None:
        status = self.chk_show_brain_surface.GetValue()
        self.brain_actor.SetVisibility(status)
        self.interactor.Render()

    def OnResetOrientation(self, evt: Optional[wx.CommandEvent] = None) -> None:
        self.rotationX = self.rotationY = self.rotationZ = 0
        self.slider_rotation_x.SetValue(0)
        self.slider_rotation_y.SetValue(0)
        self.slider_rotation_z.SetValue(0)
        self.marker_actor.SetOrientation(self.rotationX, self.rotationY, self.rotationZ)
        self.interactor.Render()

    def OnRotationX(self, evt: wx.CommandEvent) -> None:
        self.rotationX = evt.GetInt()
        self.marker_actor.SetOrientation(self.rotationX, self.rotationY, self.rotationZ)
        self.interactor.Render()

    def OnRotationY(self, evt: wx.CommandEvent) -> None:
        self.rotationY = evt.GetInt()
        self.marker_actor.SetOrientation(self.rotationX, self.rotationY, self.rotationZ)
        self.interactor.Render()

    def OnRotationZ(self, evt: wx.CommandEvent) -> None:
        self.rotationZ = evt.GetInt()
        self.marker_actor.SetOrientation(self.rotationX, self.rotationY, self.rotationZ)
        self.interactor.Render()

    def OnDepth(self, evt: wx.KeyEvent) -> None:
        if evt.GetKeyCode() == wx.WXK_UP:
            depth = 1
        elif evt.GetKeyCode() == wx.WXK_DOWN:
            depth = -1
        else:
            depth = 0
        self.marker_actor.AddPosition(0, 0, depth)
        self.interactor.Render()

    def OnPressLeftButton(self, evt, obj) -> None:
        self.spinning = True

    def OnReleaseLeftButton(self, evt, obj) -> None:
        self.spinning = False

    def OnSpinMove(self, evt, obj) -> None:
        self.interactor.SetInteractorStyle(self.actor_style)
        if self.spinning:
            evt.Spin()
            evt.OnRightButtonDown()

    def OnZoomMove(self, evt, obj) -> None:
        self.interactor.SetInteractorStyle(self.camera_style)
        if obj == "MouseWheelForwardEvent":
            self.camera_style.OnMouseWheelForward()
        else:
            self.camera_style.OnMouseWheelBackward()

    def OnChangeView(self, evt: wx.CommandEvent) -> None:
        self.ren.GetActiveCamera().Roll(90)
        self.interactor.Render()

    def OnComboNameBrainSurface(self, evt: wx.CommandEvent) -> None:
        surface_index = evt.GetSelection()
        self.brain_surface = self.proj.surface_dict[surface_index].polydata
        if self.brain_actor:
            self.RemoveActor(self.brain_actor)
        self.brain_actor = self.LoadActor(self.brain_surface)
        self.chk_show_brain_surface.SetValue(True)

    def OnComboNameScalpSurface(self, evt: wx.CommandEvent) -> None:
        surface_index = evt.GetSelection()
        self.surface = self.proj.surface_dict[surface_index].polydata
        if self.obj_actor:
            self.RemoveAllActor()
            if self.peel_brain_actor:
                self.peel_brain_actor.PickableOff()
                self.ren.AddActor(self.peel_brain_actor)
        self.brain_target_actor_list = []
        self.coil_target_actor_list = []
        self.center_brain_target_actor = None
        self.obj_actor = self.LoadActor(self.surface)
        if not self.brain_target:
            self.brain_actor = self.LoadActor(self.brain_surface)
        self.coil_pose_actor = self.LoadTarget()
        self.chk_show_surface.SetValue(True)

    def LoadCenterBrainTarget(
        self,
        coil_target_position: Union[Sequence, np.ndarray],
        coil_target_orientation: Union[Sequence, np.ndarray],
    ) -> None:
        m_coil = dco.coordinates_to_transformation_matrix(
            position=coil_target_position,
            orientation=coil_target_orientation,
            axes="sxyz",
        )
        m_offset_brain = dco.coordinates_to_transformation_matrix(
            position=[0, 0, -20],
            orientation=coil_target_orientation,
            axes="sxyz",
        )
        m_brain = m_coil @ m_offset_brain
        coord = (
            m_brain[0][-1],
            m_brain[1][-1],
            m_brain[2][-1],
            coil_target_orientation[0],
            coil_target_orientation[1],
            coil_target_orientation[2],
        )

        brain_target_actor, _ = self.AddTarget(coord, scale=2)
        brain_target_actor.PickableOff()
        brain_target_actor.GetProperty().SetColor([1, 1, 0])
        self.brain_target_actor_list.append(brain_target_actor)

        print("Adding brain markers")

    def LoadTarget(self) -> vtkActor:
        coord_flip = list(self.marker)
        coord_flip[1] = -coord_flip[1]
        if self.brain_target:
            marker_actor, _ = self.AddTarget(coord_flip, scale=5)
            self.ren.GetActiveCamera().Zoom(2)
            colors = vtkNamedColors()
            # Create a circle
            polygonSource = vtkRegularPolygonSource()
            # Comment this line to generate a disk instead of a circle.
            polygonSource.GeneratePolygonOff()
            polygonSource.SetNumberOfSides(50)
            polygonSource.SetRadius(const.MTMS_RADIUS)
            polygonSource.SetCenter(0, 0, 0)
            #  Visualize
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(polygonSource.GetOutputPort())
            circle_actor = vtkActor()
            circle_actor.SetMapper(mapper)
            circle_actor.PickableOff()
            circle_actor.GetProperty().SetColor(colors.GetColor3d("Red"))
            circle_actor.SetUserMatrix(self.m_target)
            self.ren.AddActor(circle_actor)
            self.marker_actor.PickableOff()
        else:
            marker_actor, coordinates = self.AddTarget(coord_flip, scale=10)
            self.marker[3], self.marker[4], self.marker[5] = (
                coordinates[3],
                coordinates[4],
                coordinates[5],
            )
        self.interactor.Render()

        return marker_actor

    def LoadActor(self, surface: vtkPolyData) -> vtkActor:
        """
        Load the selected actor from the project (self.surface) into the scene
        :return:
        """
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(surface)
        mapper.ScalarVisibilityOff()

        obj_actor = vtkActor()
        obj_actor.SetMapper(mapper)
        # obj_actor.GetProperty().SetOpacity(0.1)
        obj_actor.PickableOff()

        self.ren.AddActor(obj_actor)
        coord_flip = list(self.marker)
        coord_flip[1] = -coord_flip[1]
        self.ren.ResetCamera()
        self.interactor.Render()

        return obj_actor

    def RemoveActor(self, actor: vtkActor) -> None:
        self.ren.RemoveActor(actor)
        self.interactor.Render()

    def RemoveAllActor(self) -> None:
        self.ren.RemoveAllViewProps()
        self.ren.ResetCamera()
        self.interactor.Render()

    def AddTarget(
        self,
        coord_flip: Sequence[float],
        colour: MutableSequence[float] = [0.0, 0.0, 1.0],
        scale: float = 10,
    ) -> Tuple[vtkActor, Tuple[float, float, float, float, float, float]]:
        rx, ry, rz = coord_flip[3:]
        if rx is None:
            coord = self.Versor(self.CenterOfMass(self.brain_surface), coord_flip[:3])
            rx, ry, rz = self.GetEulerAnglesFromVectors([1, 0, 0], coord)
            ry += 90
            m_img_vtk, rx, ry, rz = self.CreateVTKObjectMatrix(
                coord_flip[:3], [rx, ry, rz], new_target=True
            )
            self.m_target = m_img_vtk
        else:
            m_img_vtk, rx, ry, rz = self.CreateVTKObjectMatrix(
                coord_flip[:3], [rx, ry, rz], new_target=False
            )
            if not self.m_target:
                self.m_target = m_img_vtk

        coordinate = coord_flip[0], coord_flip[1], coord_flip[2], rx, ry, rz
        marker_actor = self.CreateActorArrow(m_img_vtk, colour=colour)
        marker_actor.SetScale(scale)
        self.marker_actor = marker_actor

        self.ren.AddActor(marker_actor)

        return marker_actor, coordinate

    def CreateActorArrow(self, m_img_vtk, colour, size=const.ARROW_MARKER_SIZE):
        input1 = vtkPolyData()
        input2 = vtkPolyData()
        input3 = vtkPolyData()
        input4 = vtkPolyData()

        cylinderSourceWing = vtkCylinderSource()
        cylinderSourceWing.SetRadius(0.02)
        cylinderSourceWing.Update()
        input1.ShallowCopy(cylinderSourceWing.GetOutput())

        arrow = vtkArrowSource()
        arrow.SetArrowOriginToCenter()
        arrow.SetTipResolution(40)
        arrow.SetShaftResolution(40)
        arrow.SetShaftRadius(0.025)
        arrow.SetTipRadius(0.10)
        arrow.SetTipLength(0.30)
        arrow.Update()
        input2.ShallowCopy(arrow.GetOutput())

        arrowDown = vtkArrowSource()
        arrowDown.SetArrowOriginToCenter()
        arrowDown.SetTipResolution(4)
        arrowDown.SetShaftResolution(40)
        arrowDown.SetShaftRadius(0.05)
        arrowDown.SetTipRadius(0.15)
        arrowDown.SetTipLength(0.35)
        arrowDown.Update()

        ArrowDownTransformFilter = vtkTransformPolyDataFilter()
        RotateTransform = vtkTransform()
        RotateTransform.RotateZ(45)
        RotateTransform.RotateY(90)
        ArrowDownTransformFilter.SetTransform(RotateTransform)
        ArrowDownTransformFilter.SetInputConnection(arrowDown.GetOutputPort())
        ArrowDownTransformFilter.Update()
        input3.ShallowCopy(ArrowDownTransformFilter.GetOutput())

        torus = vtkParametricTorus()
        torus.SetRingRadius(0.15)
        torus.SetCrossSectionRadius(0.02)
        torusSource = vtkParametricFunctionSource()
        torusSource.SetParametricFunction(torus)
        torusSource.Update()
        input4.ShallowCopy(torusSource.GetOutput())

        # Append the two meshes
        appendFilter = vtkAppendPolyData()
        appendFilter.AddInputData(input1)
        appendFilter.AddInputData(input2)
        appendFilter.AddInputData(input3)
        appendFilter.AddInputData(input4)
        appendFilter.Update()

        #  Remove any duplicate points.
        cleanFilter = vtkCleanPolyData()
        cleanFilter.SetInputConnection(appendFilter.GetOutputPort())
        cleanFilter.Update()

        # Create a mapper and actor
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(cleanFilter.GetOutputPort())

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetScale(size)
        actor.GetProperty().SetColor(colour)
        actor.SetUserMatrix(m_img_vtk)

        return actor

    def vtkmatrix2numpy(self, matrix: vtkMatrix4x4) -> np.ndarray:
        """
        Copies the elements of a vtkMatrix4x4 into a numpy array.
        param matrix: The matrix to be copied into an array.
        Args:
            matrix: vtk type matrix
        """
        m = np.ones((4, 4))
        for i in range(4):
            for j in range(4):
                m[i, j] = matrix.GetElement(i, j)
        return m

    def ICP(
        self, coord: Sequence[float], center: Sequence, surface: vtkPolyData
    ) -> Tuple[int, int, int, None, None, None]:
        """
        Apply ICP transforms to fit the spiral points to the surface
        Args:
            coord: raw coordinates to apply ICP
        """
        sourcePoints = np.array(coord[:3])
        sourcePoints_vtk = vtkPoints()
        for i in range(len(sourcePoints)):
            sourcePoints_vtk.InsertNextPoint(sourcePoints)
        source = vtkPolyData()
        source.SetPoints(sourcePoints_vtk)

        if float(center[0]) > 100.0:
            transform = vtkTransform()
            transform.Translate(float(center[0]), -float(center[1]), float(center[2]))
            transform.RotateY(35)
            transform.Translate(-float(center[0]), float(center[1]), -float(center[2]))

        if float(center[0]) <= 100.00:
            transform = vtkTransform()
            transform.Translate(float(center[0]), -float(center[1]), float(center[2]))
            transform.RotateY(-35)
            transform.Translate(-float(center[0]), float(center[1]), -float(center[2]))

        transform_filt = vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(source)
        transform_filt.Update()

        source_points = transform_filt.GetOutput()

        icp = vtkIterativeClosestPointTransform()
        icp.SetSource(source_points)
        icp.SetTarget(surface)

        icp.GetLandmarkTransform().SetModeToRigidBody()
        # icp.GetLandmarkTransform().SetModeToAffine()
        icp.DebugOn()
        icp.SetMaximumNumberOfIterations(100)
        icp.Modified()
        icp.Update()

        self.m_icp = self.vtkmatrix2numpy(icp.GetMatrix())

        icpTransformFilter = vtkTransformPolyDataFilter()
        icpTransformFilter.SetInputData(source_points)
        icpTransformFilter.SetTransform(icp)
        icpTransformFilter.Update()

        transformedSource = icpTransformFilter.GetOutput()
        p = [0, 0, 0]
        transformedSource.GetPoint(0, p)
        # source_points.GetPoint(0, p)
        point = vtkSphereSource()
        point.SetCenter(p)
        point.SetRadius(1.5)
        point.SetPhiResolution(10)
        point.SetThetaResolution(10)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(point.GetOutputPort())

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor((0, 0, 1))

        # self.ren.AddActor(actor)
        # self.ActorCollection.AddItem(actor)
        # self.interactor.Render()
        # coord = p[0], p[1], p[2], center[3], center[4], center[5]
        ret = p[0], p[1], p[2], None, None, None

        return ret

        # p[1] = -p[1]
        # self.icp_points.append(p)

    def CreateSphere(self, center: Sequence[float], radius: float) -> vtkPolyData:
        point = vtkSphereSource()
        point.SetCenter(center)
        point.SetRadius(radius)
        point.SetPhiResolution(100)
        point.SetThetaResolution(100)
        point.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(point.GetOutputPort())

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor((0, 1, 0))

        self.ren.AddActor(actor)

        return point.GetOutput()

    def CreateGrid(self, resolution: int, space_x: float, space_y: float) -> List[np.ndarray]:
        minX, maxX, minY, maxY = -space_x, space_x, -space_y, space_y
        # create one-dimensional arrays for x and y
        x = np.linspace(minX, maxX, resolution)
        y = np.linspace(minY, maxY, resolution)

        return np.meshgrid(x, y)

    def OnCreateRandomTargetGrid(self, evt: wx.CommandEvent) -> None:
        vtkmat = self.coil_pose_actor.GetMatrix()
        narray = np.eye(4)
        vtkmat.DeepCopy(narray.ravel(), vtkmat)
        position = [narray[0][-1], narray[1][-1], narray[2][-1]]
        m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
        coil_target_position = position
        coil_target_orientation = np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))
        if self.center_brain_target_actor is None:
            self.center_brain_target_actor = self.LoadCenterBrainTarget(
                coil_target_position, coil_target_orientation
            )

        self.coil_pose_actor.GetProperty().SetColor([1, 0, 0])
        self.coil_pose_actor.GetProperty().SetOpacity(1)
        self.coil_pose_actor.PickableOff()
        if self.dummy_coil_actor:
            self.RemoveActor(self.dummy_coil_actor)

        number_of_targets = 10
        # radius of the circle
        circle_r = 15

        for i in range(number_of_targets):
            alpha = 2 * np.pi * random.random()
            r = circle_r * np.sqrt(random.random())
            X = r * np.cos(alpha)
            Y = r * np.sin(alpha)
            rZ = random.randrange(-30, 30, 1)

            m_offset_target = dco.coordinates_to_transformation_matrix(
                position=[X, Y, 0],
                orientation=[0, 0, rZ],
                axes="sxyz",
            )
            m_origin_coil = dco.coordinates_to_transformation_matrix(
                position=coil_target_position,
                orientation=coil_target_orientation,
                axes="sxyz",
            )
            m_target = m_origin_coil @ m_offset_target
            position, orientation = dco.transformation_matrix_to_coordinates(m_target, axes="sxyz")
            coord = [
                position[0],
                position[1],
                position[2],
                orientation[0],
                orientation[1],
                orientation[2],
            ]
            coil_target_actor, coordinate = self.AddTarget(coord)
            self.coil_target_actor_list.append(coil_target_actor)

        self.interactor.Render()

    def OnCreateTargetGrid(self, evt: wx.CommandEvent) -> None:
        vtkmat = self.coil_pose_actor.GetMatrix()
        narray = np.eye(4)
        vtkmat.DeepCopy(narray.ravel(), vtkmat)
        position = [narray[0][-1], narray[1][-1], narray[2][-1]]
        m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
        coil_target_position = position
        coil_target_orientation = np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))

        # coord_flip = list(self.marker)
        # coord_flip[1] = -coord_flip[1]
        self.coil_pose_actor.GetProperty().SetColor([1, 0, 0])
        self.coil_pose_actor.GetProperty().SetOpacity(0)
        self.coil_pose_actor.PickableOff()
        if self.dummy_coil_actor:
            self.RemoveActor(self.dummy_coil_actor)

        grid_resolution = 3
        X, Y = self.CreateGrid(grid_resolution, 5, 5)
        self.coil_target_actor_list = []
        for i in range(grid_resolution):
            for j in range(grid_resolution):
                m_offset_target = dco.coordinates_to_transformation_matrix(
                    position=[X[i][j], Y[i][j], 0],
                    orientation=coil_target_orientation[:3],
                    axes="sxyz",
                )
                m_origin_coil = dco.coordinates_to_transformation_matrix(
                    position=[
                        coil_target_position[0],
                        coil_target_position[1],
                        coil_target_position[2],
                    ],
                    orientation=[0, 0, 0],
                    axes="sxyz",
                )
                m_target = m_origin_coil @ m_offset_target
                position = [m_target[0][-1], m_target[1][-1], m_target[2][-1]]
                coord_scalp = self.ICP(position, coil_target_position, self.surface)
                coord = (
                    coord_scalp[0],
                    coord_scalp[1],
                    coord_scalp[2],
                    coil_target_orientation[0],
                    coil_target_orientation[1],
                    coil_target_orientation[2],
                )
                coil_target_actor, coordinate = self.AddTarget(coord)
                # self.marker_actor.AddPosition(0, 0, 5)
                self.coil_target_actor_list.append(coil_target_actor)

        self.interactor.Render()

    def OnCreateBrainGrid(self, evt: wx.CommandEvent) -> None:
        if self.coil_target_actor_list:
            for coil_target_actor in self.coil_target_actor_list:
                vtkmat = coil_target_actor.GetMatrix()
                narray = np.eye(4)
                vtkmat.DeepCopy(narray.ravel(), vtkmat)
                position = [narray[0][-1], narray[1][-1], narray[2][-1]]
                m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
                orientation = np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))

                m_coil = dco.coordinates_to_transformation_matrix(
                    position=position,
                    orientation=orientation,
                    axes="sxyz",
                )
                m_offset_brain = dco.coordinates_to_transformation_matrix(
                    position=[0, 0, -20],
                    orientation=orientation,
                    axes="sxyz",
                )
                m_brain = m_coil @ m_offset_brain
                coord = (
                    m_brain[0][-1],
                    m_brain[1][-1],
                    m_brain[2][-1],
                    orientation[0],
                    orientation[1],
                    orientation[2],
                )

                brain_target_actor, _ = self.AddTarget(coord, scale=1.5)
                brain_target_actor.PickableOff()
                brain_target_actor.GetProperty().SetColor([1, 1, 0])
                self.brain_target_actor_list.append(brain_target_actor)
                print("Adding brain markers")

    def OnSendMtms(self, evt: Optional[wx.CommandEvent] = None) -> None:
        vtkmat = self.marker_actor.GetMatrix()
        narray = np.eye(4)
        vtkmat.DeepCopy(narray.ravel(), vtkmat)
        position = [narray[0][-1], -narray[1][-1], narray[2][-1]]
        m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
        orientation = list(np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz")))
        if self.mTMS:
            self.mTMS.UpdateTarget(coil_pose=self.marker, brain_target=position + orientation)

    def CreateVTKObjectMatrix(
        self,
        direction: "Sequence[float] | np.ndarray",
        orientation: "Sequence[float] | np.ndarray",
        new_target: bool,
    ) -> Tuple[vtkMatrix4x4, float, float, float]:
        m_img = dco.coordinates_to_transformation_matrix(
            position=direction,
            orientation=orientation,
            axes="sxyz",
        )
        m_img = np.asmatrix(m_img)
        m_img_vtk = vtkMatrix4x4()
        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        RotateTransform = vtkTransform()
        RotateTransform.SetMatrix(m_img_vtk)
        if new_target:
            RotateTransform.RotateZ(-135)
        m_img_vtk_rotate = RotateTransform.GetMatrix()
        rx, ry, rz = RotateTransform.GetOrientation()

        return m_img_vtk_rotate, rx, ry, rz

    def GetRotationMatrix(
        self,
        v1_start: np.ndarray,
        v2_start: np.ndarray,
        v1_target: np.ndarray,
        v2_target: np.ndarray,
    ) -> np.ndarray:
        """
        based on https://stackoverflow.com/questions/15101103/euler-angles-between-two-3d-vectors
        calculating M the rotation matrix from base U to base V
        M @ U = V
        M = V @ U^-1
        """
        u1_start = self.Normalize(v1_start)
        u2_start = self.Normalize(v2_start)
        u3_start = self.Normalize(np.cross(u1_start, u2_start))

        u1_target = self.Normalize(v1_target)
        u2_target = self.Normalize(v2_target)
        u3_target = self.Normalize(np.cross(u1_target, u2_target))

        U = np.hstack([u1_start.reshape(3, 1), u2_start.reshape(3, 1), u3_start.reshape(3, 1)])
        V = np.hstack([u1_target.reshape(3, 1), u2_target.reshape(3, 1), u3_target.reshape(3, 1)])

        if not np.isclose(np.dot(v1_target, v2_target), 0, atol=1e-03):
            raise ValueError("v1_target and v2_target must be vertical")

        return np.dot(V, np.linalg.inv(U))

    def GetEulerAnglesFromVectors(
        self, init_arrow_vector: np.ndarray, target_arrow_vector
    ) -> np.ndarray:
        import invesalius.data.transformations as tr

        init_up_vector = self.GetPerpendicularVector(init_arrow_vector)
        target_up_vector = self.GetPerpendicularVector(target_arrow_vector)
        rot_mat = self.GetRotationMatrix(
            init_arrow_vector, init_up_vector, target_arrow_vector, target_up_vector
        )

        return np.rad2deg(tr.euler_from_matrix(rot_mat, axes="sxyz"))

    def CenterOfMass(self, surface: vtkPolyData) -> List[float]:
        barycenter = [0.0, 0.0, 0.0]
        n = surface.GetNumberOfPoints()
        for i in range(n):
            point = surface.GetPoint(i)
            barycenter[0] += point[0]
            barycenter[1] += point[1]
            barycenter[2] += point[2]
        barycenter[0] /= n
        barycenter[1] /= n
        barycenter[2] /= n

        return barycenter

    def Normalize(self, v: np.ndarray) -> np.ndarray:
        return v / np.linalg.norm(v)

    def Versor(
        self,
        init_point: Union[Sequence[float], np.ndarray],
        final_point: Union[Sequence[float], np.ndarray],
    ) -> List[float]:
        init_point = np.array(init_point)
        final_point = np.array(final_point)
        norm = (sum((final_point - init_point) ** 2)) ** 0.5
        versor_factor = (((final_point - init_point) / norm) * 1).tolist()

        return versor_factor

    def GetPerpendicularVector(self, vector: np.ndarray) -> np.ndarray:
        ez = np.array([0, 0, 1])
        look_at_vector = self.Normalize(vector)
        up_vector = self.Normalize(ez - np.dot(look_at_vector, ez) * look_at_vector)
        return up_vector

    def GetValue(
        self,
    ) -> Tuple[List[List[np.float64]], List[np.ndarray], List[List[np.float64]], List[np.ndarray]]:
        self.ren.RemoveActor(self.peel_brain_actor)
        vtkmat = self.coil_pose_actor.GetMatrix()
        narray = np.eye(4)
        vtkmat.DeepCopy(narray.ravel(), vtkmat)
        position: List[np.float64] = [narray[0][-1], -narray[1][-1], narray[2][-1]]
        m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
        coil_target_position = [position]
        coil_target_orientation = [np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))]

        brain_target_position: List[List[np.float64]] = []
        brain_target_orientation = []
        for coil_target_actor in self.coil_target_actor_list:
            vtkmat = coil_target_actor.GetMatrix()
            narray = np.eye(4)
            vtkmat.DeepCopy(narray.ravel(), vtkmat)
            position = [narray[0][-1], -narray[1][-1], narray[2][-1]]
            m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
            orientation = np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))
            coil_target_position.append(position)
            coil_target_orientation.append(orientation)

        for brain_target_actor in self.brain_target_actor_list:
            vtkmat = brain_target_actor.GetMatrix()
            narray = np.eye(4)
            vtkmat.DeepCopy(narray.ravel(), vtkmat)
            position = [narray[0][-1], -narray[1][-1], narray[2][-1]]
            m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
            orientation = np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))
            brain_target_position.append(position)
            brain_target_orientation.append(orientation)

        return (
            coil_target_position,
            coil_target_orientation,
            brain_target_position,
            brain_target_orientation,
        )

    def GetValueBrainTarget(self) -> Tuple[List[List[np.float64]], List[np.ndarray]]:
        import invesalius.data.transformations as tr

        brain_target_position = []
        brain_target_orientation = []
        for brain_target_actor in self.brain_target_actor_list:
            vtkmat = brain_target_actor.GetMatrix()
            narray = np.eye(4)
            vtkmat.DeepCopy(narray.ravel(), vtkmat)
            position: List[np.float64] = [narray[0][-1], -narray[1][-1], narray[2][-1]]
            m_rotation = [narray[0][:3], narray[1][:3], narray[2][:3]]
            orientation = np.rad2deg(tr.euler_from_matrix(m_rotation, axes="sxyz"))
            brain_target_position.append(position)
            brain_target_orientation.append(orientation)
        return brain_target_position, brain_target_orientation


class TractographyProgressWindow:
    def __init__(self, msg: str):
        self.title = "InVesalius 3"
        self.msg = msg
        self.style = wx.PD_APP_MODAL | wx.PD_APP_MODAL | wx.PD_CAN_ABORT
        self.dlg = wx.ProgressDialog(self.title, self.msg, parent=None, style=self.style)
        self.running = True
        self.error = None
        self.dlg.Show()

    def WasCancelled(self) -> bool:
        return self.dlg.WasCancelled()

    def Update(self, msg: Optional[str] = None, value=None) -> None:
        if msg is None:
            self.dlg.Pulse()
        else:
            self.dlg.Pulse(msg)

    def Close(self) -> None:
        self.dlg.Destroy()


class BrainSurfaceLoadingProgressWindow:
    def __init__(self):
        title = "InVesalius 3"
        message = _("Loading brain surface...")
        style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT
        parent = wx.GetApp().GetTopWindow()

        self.dlg = wx.ProgressDialog(title, message, parent=parent, style=style)
        self.dlg.Show()

    def Update(self, msg: Optional[str] = None, value=None) -> None:
        if value:
            self.dlg.Update(int(value), msg)
        elif msg:
            self.dlg.Pulse(msg)
        else:
            self.dlg.Pulse()

    def Close(self) -> None:
        self.dlg.Destroy()


class SurfaceSmoothingProgressWindow:
    def __init__(self):
        title = "InVesalius 3"
        message = _("Smoothing the surface...")
        style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT
        parent = wx.GetApp().GetTopWindow()

        self.dlg = wx.ProgressDialog(title, message, parent=parent, style=style)
        self.dlg.Show()

    def Close(self) -> None:
        self.dlg.Destroy()


class SurfaceProgressWindow:
    def __init__(self):
        self.title = "InVesalius 3"
        self.msg = _("Creating 3D surface ...")
        self.style = wx.PD_APP_MODAL | wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME
        self.dlg = wx.ProgressDialog(self.title, self.msg, parent=None, style=self.style)
        self.running = True
        self.error = None
        self.dlg.Show()

    def WasCancelled(self) -> bool:
        #  print("Cancelled?", self.dlg.WasCancelled())
        return self.dlg.WasCancelled()

    def Update(self, msg: Optional[str] = None, value=None) -> None:
        if msg is None:
            self.dlg.Pulse()
        else:
            self.dlg.Pulse(msg)

    def Close(self) -> None:
        self.dlg.Destroy()


class GoToDialog(wx.Dialog):
    def __init__(self, title: str = _("Go to slice ..."), init_orientation: str = const.AXIAL_STR):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )
        self._init_gui(init_orientation)

    def _init_gui(self, init_orientation: str) -> None:
        orientations = (
            (_("Axial"), const.AXIAL_STR),
            (_("Coronal"), const.CORONAL_STR),
            (_("Sagital"), const.SAGITAL_STR),
        )
        self.goto_slice = wx.TextCtrl(self, -1, "")
        self.goto_orientation = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        cb_init = 0
        for n, orientation in enumerate(orientations):
            self.goto_orientation.Append(*orientation)
            if orientation[1] == init_orientation:
                cb_init = n
        self.goto_orientation.SetSelection(cb_init)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        slice_sizer = wx.BoxSizer(wx.HORIZONTAL)
        slice_sizer.Add(
            wx.StaticText(self, -1, _("Slice number"), style=wx.ALIGN_CENTER),
            0,
            wx.ALIGN_CENTER | wx.RIGHT,
            5,
        )
        slice_sizer.Add(self.goto_slice, 1, wx.EXPAND)

        main_sizer.Add((5, 5))
        main_sizer.Add(slice_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(self.goto_orientation, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.orientation = None

        self.__bind_events()

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def __bind_events(self) -> None:
        Publisher.subscribe(self.SetNewFocalPoint, "Cross focal point")

    def OnOk(self, evt: wx.CommandEvent) -> None:
        try:
            slice_number = int(self.goto_slice.GetValue())
            orientation = self.orientation = self.goto_orientation.GetClientData(
                self.goto_orientation.GetSelection()
            )

            Publisher.sendMessage(("Set scroll position", orientation), index=slice_number)
            Publisher.sendMessage("Set Update cross pos")

        except ValueError:
            pass
        self.Close()

    def SetNewFocalPoint(self, coord: Iterable[int], spacing: Sequence[int]) -> None:
        newCoord = list(coord)
        if self.orientation == "AXIAL":
            newCoord[2] = int(self.goto_slice.GetValue()) * spacing[2]
        if self.orientation == "CORONAL":
            newCoord[1] = int(self.goto_slice.GetValue()) * spacing[1]
        if self.orientation == "SAGITAL":
            newCoord[0] = int(self.goto_slice.GetValue()) * spacing[0]

        Publisher.sendMessage("Update cross pos", coord=newCoord)

    def Close(self) -> None:
        wx.Dialog.Close(self)
        self.Destroy()


class GoToDialogScannerCoord(wx.Dialog):
    def __init__(self, title: str = _("Go to scanner coord...")):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
        )
        self._init_gui()

    def _init_gui(self) -> None:
        self.goto_sagital = wx.TextCtrl(self, size=(50, -1))
        self.goto_coronal = wx.TextCtrl(self, size=(50, -1))
        self.goto_axial = wx.TextCtrl(self, size=(50, -1))

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        sizer_create = wx.FlexGridSizer(3, 2, 10, 10)
        sizer_create.AddMany(
            [
                (wx.StaticText(self, 1, _("Sagital coordinate:")), 1, wx.LEFT, 10),
                (self.goto_sagital, 1, wx.RIGHT, 10),
                (wx.StaticText(self, 1, _("Coronal coordinate:")), 1, wx.LEFT, 10),
                (self.goto_coronal, 1, wx.RIGHT, 10),
                (wx.StaticText(self, 1, _("Axial coordinate:")), 1, wx.LEFT, 10),
                (self.goto_axial, 1, wx.RIGHT, 10),
            ]
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(sizer_create, proportion=3, flag=wx.CENTER, border=20)
        main_sizer.Add(btnsizer, proportion=1, flag=wx.CENTER | wx.TOP, border=5)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.orientation = None
        self.affine = np.identity(4)

        self.__bind_events()

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def __bind_events(self) -> None:
        Publisher.subscribe(self.SetNewFocalPoint, "Cross focal point")

    def SetNewFocalPoint(self, coord, spacing):
        Publisher.sendMessage("Update cross pos", coord=self.result * spacing)

    def OnOk(self, evt: wx.CommandEvent) -> None:
        import invesalius.data.slice_ as slc

        try:
            point = [
                float(self.goto_sagital.GetValue()),
                float(self.goto_coronal.GetValue()),
                float(self.goto_axial.GetValue()),
            ]

            # transformation from scanner coordinates to inv coord system
            affine_inverse = np.linalg.inv(slc.Slice().affine)
            self.result = (
                np.dot(affine_inverse[:3, :3], np.transpose(point[0:3])) + affine_inverse[:3, 3]
            )
            self.result[1] = slc.Slice().GetMaxSliceNumber(const.CORONAL_STR) - self.result[1]

            Publisher.sendMessage(
                "Update status text in GUI", label=_("Calculating the transformation ...")
            )

            Publisher.sendMessage("Set Update cross pos")
            Publisher.sendMessage("Toggle toolbar button", id=const.SLICE_STATE_CROSS)

            Publisher.sendMessage("Update status text in GUI", label=_("Ready"))
        except ValueError:
            pass
        self.Close()

    def Close(self) -> None:
        wx.Dialog.Close(self)
        self.Destroy()


class SelectNiftiVolumeDialog(wx.Dialog):
    def __init__(self, volumes: Sequence[str], title: str = _("Select NIfTI volume")):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        self._init_gui(volumes)

    def _init_gui(self, volumes: Sequence[str]) -> None:
        self.cmb_volume = wx.ComboBox(
            self, -1, choices=volumes, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )

        button_ok = wx.Button(self, wx.ID_OK)
        button_ok.SetHelpText("")
        button_ok.SetDefault()

        button_cancel = wx.Button(self, wx.ID_CANCEL)
        button_cancel.SetHelpText("")

        button_sizer = wx.StdDialogButtonSizer()
        button_sizer.AddButton(button_ok)
        button_sizer.AddButton(button_cancel)
        button_sizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # main_sizer.Add((5, 5))
        # main_sizer.Add(
        # wx.StaticText(self, -1, _("Select NIfTI volume:")), 0, wx.EXPAND, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(self.cmb_volume, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        # main_sizer.Fit(self)
        # self.Layout()
        self.CenterOnParent()

    def GetVolumeChoice(self) -> int:
        volume_choice = int(self.cmb_volume.GetString(self.cmb_volume.GetSelection())) - 1

        return volume_choice


def DialogRescalePixelIntensity(max_intensity: float, unique_values: Any) -> bool:
    msg = (
        _("Maximum pixel intensity is: ")
        + str(round(max_intensity, 1))
        + "\n\n"
        + _("Number of unique pixel intensities: ")
        + str(unique_values)
        + "\n\n"
        + _("Would you like to rescale pixel values to 0-255?")
    )

    if sys.platform == "darwin":
        dlg = wx.MessageDialog(None, "", msg, wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3", wx.YES_NO)

    if dlg.ShowModal() == wx.ID_YES:
        status = True
    else:
        status = False

    dlg.Destroy()
    return status


class ConfigureOptitrackDialog(wx.Dialog):
    def __init__(self, title: str = _("Configure Optitrack")):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            size=wx.Size(1000, 200),
            style=wx.DEFAULT_DIALOG_STYLE
            | wx.FRAME_FLOAT_ON_PARENT
            | wx.STAY_ON_TOP
            | wx.RESIZE_BORDER,
        )
        self._init_gui()

    def _init_gui(self) -> None:
        session = ses.Session()
        last_optitrack_cal_dir = session.GetConfig("last_optitrack_cal_dir", "")
        last_optitrack_User_Profile_dir = session.GetConfig("last_optitrack_User_Profile_dir", "")

        if not last_optitrack_cal_dir:
            last_optitrack_cal_dir = inv_paths.OPTITRACK_CAL_DIR
        if not last_optitrack_User_Profile_dir:
            last_optitrack_User_Profile_dir = inv_paths.OPTITRACK_USERPROFILE_DIR

        self.dir_cal = wx.FilePickerCtrl(
            self,
            path=last_optitrack_cal_dir,
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
            wildcard="Cal files (*.cal)|*.cal",
            message="Select the calibration file",
            size=(700, -1),
        )
        row_cal = wx.BoxSizer(wx.VERTICAL)
        row_cal.Add(wx.StaticText(self, wx.ID_ANY, "Calibration:"), 0, wx.TOP | wx.RIGHT, 5)
        row_cal.Add(self.dir_cal, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        self.dir_UserProfile = wx.FilePickerCtrl(
            self,
            path=last_optitrack_User_Profile_dir,
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
            wildcard="User Profile files (*.motive)|*.motive",
            message="Select the user profile file",
            size=(700, -1),
        )

        row_userprofile = wx.BoxSizer(wx.VERTICAL)
        row_userprofile.Add(
            wx.StaticText(self, wx.ID_ANY, "User profile:"), 0, wx.TOP | wx.RIGHT, 5
        )
        row_userprofile.Add(self.dir_UserProfile, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(row_cal, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(row_userprofile, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((15, 15))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.CenterOnParent()

    def GetValue(self) -> Tuple[str, str]:
        fn_cal = self.dir_cal.GetPath()
        fn_userprofile = self.dir_UserProfile.GetPath()

        if fn_cal and fn_userprofile:
            session = ses.Session()
            session.SetConfig("last_optitrack_cal_dir", self.dir_cal.GetPath())
            session.SetConfig("last_optitrack_User_Profile_dir", self.dir_UserProfile.GetPath())

        return fn_cal, fn_userprofile


class SetTrackerDeviceToRobot(wx.Dialog):
    """
    Robot navigation requires a tracker device to tracker the head position and the object (coil) position.
    A dialog pops up showing a combobox with all trackers but debugs and the robot itself (const.TRACKERS[:-3])
    """

    def __init__(self, title: str = _("Set tracker device")):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            size=wx.Size(1000, 200),
            style=wx.DEFAULT_DIALOG_STYLE
            | wx.FRAME_FLOAT_ON_PARENT
            | wx.STAY_ON_TOP
            | wx.RESIZE_BORDER,
        )
        self.tracker_id = const.DEFAULT_TRACKER
        self._init_gui()

    def _init_gui(self) -> None:
        # ComboBox for spatial tracker device selection
        tooltip = _("Choose the tracking device")
        trackers = const.TRACKERS.copy()

        session = ses.Session()
        if not session.GetConfig("debug"):
            del trackers[-3:]

        tracker_options = [_("Select tracker:")] + trackers
        choice_trck = wx.ComboBox(
            self, -1, "", choices=tracker_options, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        choice_trck.SetToolTip(tooltip)
        choice_trck.SetSelection(const.DEFAULT_TRACKER)
        choice_trck.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceTracker, ctrl=choice_trck))

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(choice_trck, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((15, 15))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.CenterOnParent()

    def OnChoiceTracker(self, evt: wx.CommandEvent, ctrl: wx.ComboBox) -> None:
        choice = evt.GetSelection()
        self.tracker_id = choice

    def GetValue(self) -> int:
        return self.tracker_id


class SetRobotIP(wx.Dialog):
    def __init__(self, title: str = _("Set Robot IP")):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            size=wx.Size(1000, 200),
            style=wx.DEFAULT_DIALOG_STYLE
            | wx.FRAME_FLOAT_ON_PARENT
            | wx.STAY_ON_TOP
            | wx.RESIZE_BORDER,
        )
        self.robot_ip = None
        self._init_gui()

    def _init_gui(self) -> None:
        # ComboBox for spatial tracker device selection
        tooltip = _("Choose or type the robot IP")
        robot_ip_options = [_("Select robot IP:")] + const.ROBOT_ElFIN_IP
        choice_IP = wx.ComboBox(
            self, -1, "", choices=robot_ip_options, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER
        )
        choice_IP.SetToolTip(tooltip)
        choice_IP.SetSelection(const.DEFAULT_TRACKER)
        choice_IP.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceIP, ctrl=choice_IP))
        choice_IP.Bind(wx.EVT_TEXT, partial(self.OnTxt_Ent, ctrl=choice_IP))

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(choice_IP, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((15, 15))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.CenterOnParent()

    def OnTxt_Ent(self, evt: wx.CommandEvent, ctrl: wx.TextEntry) -> None:
        self.robot_ip = str(ctrl.GetValue())

    def OnChoiceIP(self, evt: wx.CommandEvent, ctrl: wx.ComboBox) -> None:
        self.robot_ip = ctrl.GetStringSelection()

    def GetValue(self) -> Optional[str]:
        return self.robot_ip


class RobotCoregistrationDialog(wx.Dialog):
    def __init__(
        self,
        robot: "Robot",
        tracker: "Tracker",
        title: str = _("Create transformation matrix to robot space"),
    ):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,  # size=wx.Size(1000, 200),
            style=wx.DEFAULT_DIALOG_STYLE
            | wx.FRAME_FLOAT_ON_PARENT
            | wx.STAY_ON_TOP
            | wx.RESIZE_BORDER,
        )
        """
        M_robot_2_tracker is created by an affine transformation. Robot TCP should be calibrated to the center of the tracker marker
        """
        # TODO: make aboutbox
        self.matrix_tracker_to_robot = []

        self.robot = robot
        self.tracker = tracker
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.HandleContinuousAcquisition, self.timer)

        self._init_gui()

    def _init_gui(self) -> None:
        # Buttons to acquire and remove points
        txt_acquisition = wx.StaticText(self, -1, _("Poses acquisition for robot registration:"))

        btn_create_point = wx.Button(self, -1, label=_("Single"))
        btn_create_point.Bind(wx.EVT_BUTTON, self.CreatePoint)

        btn_cont_point = wx.ToggleButton(self, -1, label=_("Continuous"))
        btn_cont_point.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnContinuousAcquisitionButton, btn=btn_cont_point)
        )
        self.btn_cont_point = btn_cont_point

        txt_number = wx.StaticText(self, -1, _("0"))
        txt_recorded = wx.StaticText(self, -1, _("Poses recorded"))
        self.txt_number = txt_number

        btn_reset = wx.Button(self, -1, label=_("Reset points"))
        btn_reset.Bind(wx.EVT_BUTTON, self.ResetPoints)

        btn_apply_reg = wx.Button(self, -1, label=_("Apply"))
        btn_apply_reg.Bind(wx.EVT_BUTTON, self.ApplyRegistration)
        btn_apply_reg.Enable(False)
        self.btn_apply_reg = btn_apply_reg

        # Buttons to save and load
        txt_file = wx.StaticText(self, -1, _("Registration file"))

        btn_save = wx.Button(self, -1, label=_("Save"), size=wx.Size(65, 23))
        btn_save.Bind(wx.EVT_BUTTON, self.SaveRegistration)
        btn_save.Enable(False)
        self.btn_save = btn_save

        btn_load = wx.Button(self, -1, label=_("Load"), size=wx.Size(65, 23))
        btn_load.Bind(wx.EVT_BUTTON, self.LoadRegistration)

        if not self.robot.IsConnected():
            btn_load.Enable(False)
        else:
            btn_load.Enable(True)
        self.btn_load = btn_load

        # Create a horizontal sizers
        border = 1
        acquisition = wx.BoxSizer(wx.HORIZONTAL)
        acquisition.AddMany(
            [
                (btn_create_point, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (btn_cont_point, 1, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        txt_pose = wx.BoxSizer(wx.HORIZONTAL)
        txt_pose.AddMany([(txt_number, 1, wx.LEFT, 50), (txt_recorded, 1, wx.LEFT, border)])

        apply_reset = wx.BoxSizer(wx.HORIZONTAL)
        apply_reset.AddMany(
            [
                (btn_reset, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (btn_apply_reg, 1, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        save_load = wx.BoxSizer(wx.HORIZONTAL)
        save_load.AddMany(
            [
                (btn_save, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (btn_load, 1, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()
        btn_ok.Enable(False)
        self.btn_ok = btn_ok

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        # Add line sizers into main sizer
        border = 10
        border_last = 10
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, border)
        main_sizer.Add(
            txt_acquisition, 0, wx.BOTTOM | wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_HORIZONTAL, border
        )
        main_sizer.Add(acquisition, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border)
        main_sizer.Add(txt_pose, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM, border)
        main_sizer.Add(apply_reset, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, border_last)
        main_sizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, border)
        main_sizer.Add(
            txt_file, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, int(border / 2)
        )
        main_sizer.Add(save_load, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border)
        main_sizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, border)
        main_sizer.Add(btnsizer, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border)
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()
        main_sizer.Fit(self)

        self.CenterOnParent()
        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(
            self.UpdateRobotTransformationMatrix,
            "Robot to Neuronavigation: Update robot transformation matrix",
        )
        Publisher.subscribe(
            self.PointRegisteredByRobot,
            "Robot to Neuronavigation: Coordinates for the robot transformation matrix collected",
        )

    def OnContinuousAcquisitionButton(
        self, evt: Optional[wx.CommandEvent] = None, btn: Optional[wx.ToggleButton] = None
    ) -> None:
        assert btn is not None, "btn must be provided"
        value = btn.GetValue()
        if value:
            self.timer.Start(100)
        else:
            self.timer.Stop()

    def StopContinuousAcquisition(self) -> None:
        if self.btn_cont_point:
            self.btn_cont_point.SetValue(False)
            self.OnContinuousAcquisitionButton(btn=self.btn_cont_point)

    def HandleContinuousAcquisition(self, evt: wx.TimerEvent) -> None:
        self.CreatePoint()

    def CreatePoint(self, evt: Optional[wx.CommandEvent] = None) -> None:
        Publisher.sendMessage(
            "Neuronavigation to Robot: Collect coordinates for the robot transformation matrix",
            data=None,
        )

    def GetAcquiredPoints(self) -> int:
        return int(self.txt_number.GetLabel())

    def SetAcquiredPoints(self, num_points: int) -> None:
        self.txt_number.SetLabel(str(num_points))

    def PointRegisteredByRobot(self) -> None:
        # Increment the number of acquired points.
        num_points = self.GetAcquiredPoints()
        num_points += 1
        self.SetAcquiredPoints(num_points)

        # Enable 'Apply registration' button only when the robot connection is ok and there are enough acquired points.
        if self.robot.IsConnected() and num_points >= 3:
            self.btn_apply_reg.Enable(True)

    def ResetPoints(self, evt: wx.CommandEvent) -> None:
        Publisher.sendMessage(
            "Neuronavigation to Robot: Reset coordinates collection for the robot transformation matrix",
            data=None,
        )

        self.StopContinuousAcquisition()
        self.SetAcquiredPoints(0)

        self.btn_apply_reg.Enable(False)
        self.btn_save.Enable(False)
        self.btn_ok.Enable(False)

        self.matrix_tracker_to_robot = []

    def ApplyRegistration(self, evt: wx.CommandEvent) -> None:
        self.StopContinuousAcquisition()

        Publisher.sendMessage(
            "Neuronavigation to Robot: Estimate robot transformation matrix", data=None
        )

        self.btn_save.Enable(True)
        self.btn_ok.Enable(True)

        # TODO: make a colored circle to sinalize that the transformation was made (green) (red if not)

    def UpdateRobotTransformationMatrix(self, data: Any) -> None:
        self.matrix_tracker_to_robot = np.array(data)

    def SaveRegistration(self, evt: wx.CommandEvent) -> None:
        if self.matrix_tracker_to_robot is None:
            return

        # Open dialog to choose filename.
        filename = ShowLoadSaveDialog(
            message=_("Save robot transformation file as..."),
            wildcard=_("Robot transformation files (*.rbtf)|*.rbtf"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            default_filename="robottransform.rbtf",
            save_ext="rbtf",
        )
        if not filename:
            return

        # Write registration to file.
        with open(filename, "w", newline="") as file:
            writer = csv.writer(file, delimiter="\t")
            writer.writerows(np.vstack(self.matrix_tracker_to_robot).tolist())

    def LoadRegistration(self, evt: wx.CommandEvent) -> None:
        # Open dialog to choose filename.
        filename = ShowLoadSaveDialog(
            message=_("Load robot transformation"),
            wildcard=_("Robot transformation files (*.rbtf)|*.rbtf"),
        )
        if not filename:
            return

        # Load registration from file.
        with open(filename) as file:
            reader = csv.reader(file, delimiter="\t")
            content = [row for row in reader]

        self.matrix_tracker_to_robot = np.vstack(list(np.float64(content)))

        # Send registration to robot.
        Publisher.sendMessage(
            "Neuronavigation to Robot: Set robot transformation matrix",
            data=self.matrix_tracker_to_robot.tolist(),
        )

        # Enable 'Ok' button if connection to robot is ok.
        if self.robot.IsConnected():
            self.btn_ok.Enable(True)

    def GetValue(self) -> Optional[Union[np.ndarray, List]]:
        return self.matrix_tracker_to_robot


class ConfigurePolarisDialog(wx.Dialog):
    def __init__(self, n_coils, title: str = _("Configure NDI Polaris")):
        self.n_coils = n_coils
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            size=wx.Size(1000, 200 + (n_coils - 1) * 50),
            style=wx.DEFAULT_DIALOG_STYLE
            | wx.FRAME_FLOAT_ON_PARENT
            | wx.STAY_ON_TOP
            | wx.RESIZE_BORDER,
        )
        self._init_gui()

    def serial_ports(self) -> Tuple[List[str], List[int]]:
        """
        Lists serial port names and pre-select the description containing NDI
        """
        import serial.tools.list_ports

        port_list: List[str] = []
        desc_list: List[str] = []
        ports = serial.tools.list_ports.comports()
        if sys.platform.startswith("win"):
            for port, desc, hwid in sorted(ports):
                port_list.append(port)
                desc_list.append(desc)
            port_selec = [i for i, e in enumerate(desc_list) if "NDI" in e]
        else:
            for p in ports:
                port_list.append(p.device)
                desc_list.append(p.description)
            port_selec = [i for i, e in enumerate(desc_list) if "NDI" in e]

        # print("Here is the chosen port: {} with id {}".format(port_selec[0], port_selec[1]))

        return port_list, port_selec

    def _init_gui(self) -> None:
        com_ports = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN)
        com_ports.Bind(wx.EVT_COMBOBOX, partial(self.OnChoicePort, ctrl=com_ports))
        row_com = wx.BoxSizer(wx.VERTICAL)
        row_com.Add(wx.StaticText(self, wx.ID_ANY, "COM port or IP:"), 0, wx.TOP | wx.RIGHT, 5)
        row_com.Add(com_ports, 0, wx.EXPAND)

        port_list, port_selec = self.serial_ports()

        com_ports.Append(port_list)
        com_ports.Append(const.NDI_IP)
        if port_selec:
            com_ports.SetSelection(port_selec[0])
        else:
            com_ports.SetSelection(0)
        self.com_ports = com_ports

        session = ses.Session()
        last_ndi_probe_marker = session.GetConfig("last_ndi_probe_marker", "")
        last_ndi_ref_marker = session.GetConfig("last_ndi_ref_marker", "")
        last_ndi_obj_markers = session.GetConfig("last_ndi_obj_markers", [])
        if not last_ndi_probe_marker:
            last_ndi_probe_marker = inv_paths.NDI_MAR_DIR_PROBE
        if not last_ndi_ref_marker:
            last_ndi_ref_marker = inv_paths.NDI_MAR_DIR_REF
        while len(last_ndi_obj_markers) < self.n_coils:
            last_ndi_obj_markers.append(inv_paths.NDI_MAR_DIR_OBJ)

        self.dir_probe = wx.FilePickerCtrl(
            self,
            path=last_ndi_probe_marker,
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
            wildcard="Rom files (*.rom)|*.rom",
            message="Select the ROM file of the probe",
            size=(700, -1),
        )
        row_probe = wx.BoxSizer(wx.VERTICAL)
        row_probe.Add(wx.StaticText(self, wx.ID_ANY, "Probe ROM file:"), 0, wx.TOP | wx.RIGHT, 5)
        row_probe.Add(self.dir_probe, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        self.dir_ref = wx.FilePickerCtrl(
            self,
            path=last_ndi_ref_marker,
            style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
            wildcard="Rom files (*.rom)|*.rom",
            message="Select the ROM file of the reference",
            size=(700, -1),
        )
        row_ref = wx.BoxSizer(wx.VERTICAL)
        row_ref.Add(wx.StaticText(self, wx.ID_ANY, "Reference ROM file:"), 0, wx.TOP | wx.RIGHT, 5)
        row_ref.Add(self.dir_ref, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        self.dir_objs = []
        row_objs = []
        for i in range(self.n_coils):
            dir_obj = wx.FilePickerCtrl(
                self,
                path=last_ndi_obj_markers[i],
                style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
                wildcard="Rom files (*.rom)|*.rom",
                message=f"Select the ROM file of coil {i+1}",
                size=(700, -1),
            )
            self.dir_objs.append(dir_obj)

            row_obj = wx.BoxSizer(wx.VERTICAL)
            row_obj.Add(
                wx.StaticText(self, wx.ID_ANY, f"Coil {i+1} ROM file:"), 0, wx.TOP | wx.RIGHT, 5
            )
            row_obj.Add(dir_obj, 0, wx.ALL | wx.CENTER | wx.EXPAND)
            row_objs.append(row_obj)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()
        self.btn_ok = btn_ok

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(row_com, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(row_probe, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(row_ref, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        for row_obj in row_objs:
            main_sizer.Add((5, 5))
            main_sizer.Add(row_obj, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add((15, 15))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.CenterOnParent()

    def OnChoicePort(self, evt: wx.CommandEvent, ctrl: wx.ComboBox) -> None:
        self.btn_ok.Enable(True)

    def GetValue(self) -> Tuple[str, str, str, str]:
        fn_probe = self.dir_probe.GetPath()
        fn_ref = self.dir_ref.GetPath()
        fn_objs = [dir_obj.GetPath() for dir_obj in self.dir_objs]

        if fn_probe and fn_ref and fn_objs:
            session = ses.Session()
            session.SetConfig("last_ndi_probe_marker", fn_probe)
            session.SetConfig("last_ndi_ref_marker", fn_ref)
            session.SetConfig("last_ndi_obj_markers", fn_objs)

        com_port = self.com_ports.GetValue()

        return com_port, fn_probe, fn_ref, fn_objs


class SetCOMPort(wx.Dialog):
    def __init__(self, select_baud_rate: bool, title: str = _("Select COM port")):
        wx.Dialog.__init__(
            self,
            wx.GetApp().GetTopWindow(),
            -1,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
        )

        self.select_baud_rate = select_baud_rate
        self._init_gui()

    def serial_ports(self) -> List[str]:
        """
        Lists serial port names
        """
        import serial.tools.list_ports

        if sys.platform.startswith("win"):
            ports = [comport.device for comport in serial.tools.list_ports.comports()]
        else:
            raise OSError("Unsupported platform")
        return ports

    def _init_gui(self) -> None:
        # COM port selection
        ports = self.serial_ports()
        self.com_port_dropdown = wx.ComboBox(
            self, -1, choices=ports, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        self.com_port_dropdown.SetSelection(0)

        com_port_text_and_dropdown = wx.BoxSizer(wx.VERTICAL)
        com_port_text_and_dropdown.Add(
            wx.StaticText(self, wx.ID_ANY, "COM port"), 0, wx.TOP | wx.RIGHT, 5
        )
        com_port_text_and_dropdown.Add(self.com_port_dropdown, 0, wx.EXPAND)

        # Baud rate selection
        if self.select_baud_rate:
            baud_rates_as_strings = [str(baud_rate) for baud_rate in const.BAUD_RATES]
            self.baud_rate_dropdown = wx.ComboBox(
                self, -1, choices=baud_rates_as_strings, style=wx.CB_DROPDOWN | wx.CB_READONLY
            )
            self.baud_rate_dropdown.SetSelection(const.BAUD_RATE_DEFAULT_SELECTION)

            baud_rate_text_and_dropdown = wx.BoxSizer(wx.VERTICAL)
            baud_rate_text_and_dropdown.Add(
                wx.StaticText(self, wx.ID_ANY, "Baud rate"), 0, wx.TOP | wx.RIGHT, 5
            )
            baud_rate_text_and_dropdown.Add(self.baud_rate_dropdown, 0, wx.EXPAND)

        # OK and Cancel buttons
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        # Set up the main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(com_port_text_and_dropdown, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        if self.select_baud_rate:
            main_sizer.Add((5, 5))
            main_sizer.Add(baud_rate_text_and_dropdown, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        main_sizer.Add((5, 5))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.CenterOnParent()

    def GetCOMPort(self) -> str:
        com_port = self.com_port_dropdown.GetString(self.com_port_dropdown.GetSelection())
        return com_port

    def GetBaudRate(self) -> Optional[str]:
        if not self.select_baud_rate:
            return None

        baud_rate = self.baud_rate_dropdown.GetString(self.baud_rate_dropdown.GetSelection())
        return baud_rate


class ManualWWWLDialog(wx.Dialog):
    def __init__(self, parent: wx.Window):
        wx.Dialog.__init__(self, parent, -1, _("Set WW&WL manually"))
        self._init_gui()

    def _init_gui(self) -> None:
        import invesalius.data.slice_ as slc

        ww = slc.Slice().window_width
        wl = slc.Slice().window_level

        self.txt_wl = wx.TextCtrl(self, -1, str(int(wl)))
        wl_sizer = wx.BoxSizer(wx.HORIZONTAL)
        wl_sizer.Add(wx.StaticText(self, -1, _("Window Level")), 0, wx.ALIGN_CENTER_VERTICAL)
        wl_sizer.Add(self.txt_wl, 1, wx.ALL | wx.EXPAND, 5)
        wl_sizer.Add(wx.StaticText(self, -1, _("WL")), 0, wx.ALIGN_CENTER_VERTICAL)

        self.txt_ww = wx.TextCtrl(self, -1, str(int(ww)))
        ww_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ww_sizer.Add(wx.StaticText(self, -1, _("Window Width")), 0, wx.ALIGN_CENTER_VERTICAL)
        ww_sizer.Add(self.txt_ww, 1, wx.ALL | wx.EXPAND, 5)
        ww_sizer.Add(wx.StaticText(self, -1, _("WW")), 0, wx.ALIGN_CENTER_VERTICAL)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(wl_sizer, 1, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(ww_sizer, 1, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(btnsizer, 1, wx.ALL | wx.EXPAND, 5)

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOK)
        btn_cancel.Bind(wx.EVT_BUTTON, self.OnCancel)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        main_sizer.SetSizeHints(self)

        self.Layout()
        self.Center()

    def OnOK(self, evt: wx.CommandEvent) -> None:
        try:
            ww = int(self.txt_ww.GetValue())
            wl = int(self.txt_wl.GetValue())
        except ValueError:
            self.Close()
            return

        Publisher.sendMessage("Bright and contrast adjustment image", window=ww, level=wl)
        const.WINDOW_LEVEL["Manual"] = (ww, wl)
        Publisher.sendMessage("Check window and level other")
        Publisher.sendMessage("Update window level value", window=ww, level=wl)
        # Necessary update the slice plane in the volume case exists
        Publisher.sendMessage("Update slice viewer")
        Publisher.sendMessage("Render volume viewer")

        self.Close()

    def OnCancel(self, evt: wx.CommandEvent) -> None:
        self.Close()

    def OnClose(self, evt: wx.CloseEvent) -> None:
        self.Destroy()


class SetSpacingDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        sx: float,
        sy: float,
        sz: float,
        title: str = _("Set spacing"),
        style: int = wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT,
    ):
        wx.Dialog.__init__(self, parent, -1, title=title, style=style)
        self.spacing_original_x = sx
        self.spacing_original_y = sy
        self.spacing_original_z = sz

        self._init_gui()
        self._bind_events()

    def _init_gui(self) -> None:
        self.txt_spacing_new_x = wx.TextCtrl(self, -1, value=str(self.spacing_original_x))
        self.txt_spacing_new_y = wx.TextCtrl(self, -1, value=str(self.spacing_original_y))
        self.txt_spacing_new_z = wx.TextCtrl(self, -1, value=str(self.spacing_original_z))

        sizer_new = wx.FlexGridSizer(3, 2, 5, 5)
        sizer_new.AddMany(
            (
                (wx.StaticText(self, -1, "Spacing X"), 0, wx.ALIGN_CENTER_VERTICAL),
                (self.txt_spacing_new_x, 1, wx.EXPAND),
                (wx.StaticText(self, -1, "Spacing Y"), 0, wx.ALIGN_CENTER_VERTICAL),
                (self.txt_spacing_new_y, 1, wx.EXPAND),
                (wx.StaticText(self, -1, "Spacing Z"), 0, wx.ALIGN_CENTER_VERTICAL),
                (self.txt_spacing_new_z, 1, wx.EXPAND),
            )
        )

        self.button_ok = wx.Button(self, wx.ID_OK)
        self.button_cancel = wx.Button(self, wx.ID_CANCEL)

        button_sizer = wx.StdDialogButtonSizer()
        button_sizer.AddButton(self.button_ok)
        button_sizer.AddButton(self.button_cancel)
        button_sizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(
            wx.StaticText(
                self,
                -1,
                _("It was not possible to obtain the image spacings.\nPlease set it correctly:"),
            ),
            0,
            wx.EXPAND,
        )
        main_sizer.Add(sizer_new, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.Layout()

    def _bind_events(self) -> None:
        self.txt_spacing_new_x.Bind(wx.EVT_KILL_FOCUS, self.OnSetNewSpacing)
        self.txt_spacing_new_y.Bind(wx.EVT_KILL_FOCUS, self.OnSetNewSpacing)
        self.txt_spacing_new_z.Bind(wx.EVT_KILL_FOCUS, self.OnSetNewSpacing)

        self.button_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.button_cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

    def OnSetNewSpacing(self, evt: wx.FocusEvent) -> None:
        try:
            new_spacing_x = float(self.txt_spacing_new_x.GetValue())
        except ValueError:
            new_spacing_x = self.spacing_new_x

        try:
            new_spacing_y = float(self.txt_spacing_new_y.GetValue())
        except ValueError:
            new_spacing_y = self.spacing_new_y

        try:
            new_spacing_z = float(self.txt_spacing_new_z.GetValue())
        except ValueError:
            new_spacing_z = self.spacing_new_z

        self.set_new_spacing(new_spacing_x, new_spacing_y, new_spacing_z)

    def set_new_spacing(self, sx: float, sy: float, sz: float) -> None:
        self.spacing_new_x = sx
        self.spacing_new_y = sy
        self.spacing_new_z = sz

        self.txt_spacing_new_x.ChangeValue(str(sx))
        self.txt_spacing_new_y.ChangeValue(str(sy))
        self.txt_spacing_new_z.ChangeValue(str(sz))

    def OnOk(self, evt: wx.CommandEvent) -> None:
        if self.spacing_new_x == 0.0:
            self.txt_spacing_new_x.SetFocus()
        elif self.spacing_new_y == 0.0:
            self.txt_spacing_new_y.SetFocus()
        elif self.spacing_new_z == 0.0:
            self.txt_spacing_new_z.SetFocus()
        else:
            self.EndModal(wx.ID_OK)

    def OnCancel(self, evt: wx.CommandEvent) -> None:
        self.EndModal(wx.ID_CANCEL)


class PeelsCreationDlg(wx.Dialog):
    FROM_MASK = 1
    FROM_FILES = 2

    def __init__(self, parent: wx.Window, *args, **kwds):
        wx.Dialog.__init__(self, parent, *args, **kwds)

        self.mask_path = ""
        self.method = self.FROM_MASK

        self._init_gui()
        self._bind_events_wx()
        self.get_all_masks()

    def _init_gui(self) -> None:
        self.SetTitle(_("Create peel"))

        from_mask_stbox = self._from_mask_gui()
        from_files_stbox = self._from_files_gui()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(from_mask_stbox, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(from_files_stbox, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.StdDialogButtonSizer()
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.btn_ok = wx.Button(self, wx.ID_OK, "")
        self.btn_ok.SetDefault()
        btn_sizer.AddButton(self.btn_ok)

        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, "")
        btn_sizer.AddButton(self.btn_cancel)

        btn_sizer.Realize()

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.SetAffirmativeId(self.btn_ok.GetId())
        self.SetEscapeId(self.btn_cancel.GetId())

        self.Layout()

    def _from_mask_gui(self) -> wx.StaticBoxSizer:
        mask_box = wx.StaticBox(self, -1, _("From mask"))
        from_mask_stbox = wx.StaticBoxSizer(mask_box, wx.VERTICAL)

        self.cb_masks = wx.ComboBox(self, wx.ID_ANY, choices=[])
        self.from_mask_rb = wx.RadioButton(self, -1, "", style=wx.RB_GROUP)

        internal_sizer = wx.BoxSizer(wx.HORIZONTAL)
        internal_sizer.Add(self.from_mask_rb, 0, wx.ALL | wx.EXPAND, 5)
        internal_sizer.Add(self.cb_masks, 1, wx.ALL | wx.EXPAND, 5)

        from_mask_stbox.Add(internal_sizer, 0, wx.EXPAND)

        return from_mask_stbox

    def _from_files_gui(self) -> wx.StaticBoxSizer:
        session = ses.Session()
        last_directory = session.GetConfig("last_directory_%d" % const.ID_NIFTI_IMPORT, "")

        files_box = wx.StaticBox(self, -1, _("From files"))
        from_files_stbox = wx.StaticBoxSizer(files_box, wx.VERTICAL)

        self.mask_file_browse = filebrowse.FileBrowseButton(
            self,
            -1,
            labelText=_("Mask file"),
            fileMask=WILDCARD_NIFTI,
            dialogTitle=_("Choose mask file"),
            startDirectory=last_directory,
            changeCallback=lambda evt: self._set_files_callback(mask_path=evt.GetString()),
        )
        self.from_files_rb = wx.RadioButton(self, -1, "")

        ctrl_sizer = wx.BoxSizer(wx.VERTICAL)
        ctrl_sizer.Add(self.mask_file_browse, 0, wx.ALL | wx.EXPAND, 5)

        internal_sizer = wx.BoxSizer(wx.HORIZONTAL)
        internal_sizer.Add(self.from_files_rb, 0, wx.ALL | wx.EXPAND, 5)
        internal_sizer.Add(ctrl_sizer, 0, wx.ALL | wx.EXPAND, 5)

        from_files_stbox.Add(internal_sizer, 0, wx.EXPAND)

        return from_files_stbox

    def _bind_events_wx(self) -> None:
        self.from_mask_rb.Bind(wx.EVT_RADIOBUTTON, self.on_select_method)
        self.from_files_rb.Bind(wx.EVT_RADIOBUTTON, self.on_select_method)

    def get_all_masks(self) -> None:
        import invesalius.project as prj

        inv_proj = prj.Project()
        choices = [i.name for i in inv_proj.mask_dict.values()]
        try:
            initial_value = choices[0]
            enable = True
        except IndexError:
            initial_value = ""
            enable = False

        self.cb_masks.SetItems(choices)
        self.cb_masks.SetValue(initial_value)
        self.btn_ok.Enable(enable)

    def on_select_method(self, evt: wx.CommandEvent) -> None:
        radio_selected = evt.GetEventObject()
        if radio_selected is self.from_mask_rb:
            self.method = self.FROM_MASK
            if self.cb_masks.GetItems():
                self.btn_ok.Enable(True)
            else:
                self.btn_ok.Enable(False)
        else:
            self.method = self.FROM_FILES
            if self._check_if_files_exists():
                self.btn_ok.Enable(True)
            else:
                self.btn_ok.Enable(False)

    def _set_files_callback(self, mask_path: str = "") -> None:
        if mask_path:
            self.mask_path = mask_path
        if self.method == self.FROM_FILES:
            if self._check_if_files_exists():
                self.btn_ok.Enable(True)
            else:
                self.btn_ok.Enable(False)

    def _check_if_files_exists(self) -> bool:
        return bool(self.mask_path and os.path.exists(self.mask_path))


class FileSelectionDialog(wx.Dialog):
    def __init__(self, title: str, default_dir: str, wildcard: str):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow())
        self.SetTitle(title)

        self.default_dir = default_dir
        self.wildcard = wildcard
        self.path = ""

        # Init GUI
        outer_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        outer_sizer.Add(sizer, 0, wx.EXPAND | wx.ALL)

        from_files_static_box = self._from_files_gui()
        sizer.Add(from_files_static_box, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.StdDialogButtonSizer()

        self.btn_ok = wx.Button(self, wx.ID_OK, "")
        self.btn_ok.SetDefault()
        btn_sizer.AddButton(self.btn_ok)

        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, "")
        btn_sizer.AddButton(self.btn_cancel)

        btn_sizer.Realize()
        outer_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizer(outer_sizer)
        outer_sizer.Fit(self)
        self.sizer = sizer
        self._outer_sizer = outer_sizer

        self.SetAffirmativeId(self.btn_ok.GetId())
        self.SetEscapeId(self.btn_cancel.GetId())

        self.Layout()

    def _from_files_gui(self) -> wx.StaticBoxSizer:
        files_box = wx.StaticBox(self, -1)
        from_files_static_box = wx.StaticBoxSizer(files_box, wx.VERTICAL)

        def callback(evt) -> None:
            self._set_path(path=evt.GetString())

        file_browse = filebrowse.FileBrowseButton(
            self,
            -1,
            labelText="",
            fileMask=self.wildcard,
            dialogTitle=_("Choose file"),
            startDirectory=self.default_dir,
            changeCallback=callback,
        )

        file_browse.SetMinSize(wx.Size(500, -1))

        internal_sizer = wx.BoxSizer(wx.HORIZONTAL)
        internal_sizer.Add(file_browse, 0, wx.ALL | wx.EXPAND, 5)

        from_files_static_box.Add(internal_sizer, 0, wx.EXPAND)

        return from_files_static_box

    def _set_path(self, path: str = "") -> None:
        self.path = path

    def FitSizers(self) -> None:
        self._outer_sizer.Fit(self)

    def GetPath(self) -> str:
        return self.path


class ProgressBarHandler(wx.ProgressDialog):
    def __init__(
        self,
        parent: wx.Window,
        title: str = "Progress Dialog",
        msg: str = "Initializing...",
        max_value: Optional[float] = None,
    ):
        super().__init__(title, msg, parent=parent, style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)

        self.max_value = max_value

        self.Bind(wx.EVT_CLOSE, self.close)

        # self.Show()
        self.__bind_events()

    def __bind_events(self) -> None:
        # Subscribe to pubsub messages
        Publisher.subscribe(self.update, "Update Progress bar")
        Publisher.subscribe(self.close, "Close Progress bar")

    def was_cancelled(self) -> bool:
        return super().WasCancelled()

    def update(self, value: float, msg: Optional[str] = None) -> None:
        if self.was_cancelled():
            return

        if self.max_value is None:
            self.pulse(msg)
        else:
            # value must be less than or equal max_value
            if value > self.max_value:
                value = self.max_value
            super().Update(int(value), msg)

    def close(self) -> None:
        if self.IsShown():
            self.Destroy()

    def pulse(self, msg: Optional[str] = None) -> None:
        # if self.IsShown():
        if msg is None:
            super().Pulse()
        else:
            super().Pulse(msg)
