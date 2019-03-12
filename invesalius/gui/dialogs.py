# -*- coding: UTF-8 -*-
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

import itertools
import os
import random
import sys
import time

from concurrent import futures

if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

import vtk
import wx
try:
    from wx.adv import BitmapComboBox
except ImportError:
    from wx.combo import BitmapComboBox

from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from wx.lib import masked
from wx.lib.agw import floatspin
from wx.lib.wordwrap import wordwrap
from wx.lib.pubsub import pub as Publisher

try:
    from wx.adv import AboutDialogInfo, AboutBox
except ImportError:
    from wx import AboutDialogInfo, AboutBox

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.gui.widgets.gradient as grad
import invesalius.session as ses
import invesalius.utils as utils
from invesalius.gui.widgets import clut_imagedata
from invesalius.gui.widgets.clut_imagedata import CLUTImageDataWidget, EVT_CLUT_NODE_CHANGED
import numpy as np

try:
    from agw import floatspin as FS
except ImportError: # if it's not there locally, try the wxPython lib.
    import wx.lib.agw.floatspin as FS


class MaskEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id, mask_index):
        wx.PyCommandEvent.__init__(self, evtType, id,)
        self.mask_index = mask_index

myEVT_MASK_SET = wx.NewEventType()
EVT_MASK_SET = wx.PyEventBinder(myEVT_MASK_SET, 1)

class NumberDialog(wx.Dialog):
    def __init__(self, message, value=0):
        try:
            pre = wx.PreDialog()
            pre.Create(None, -1, "InVesalius 3", size=wx.DefaultSize,
                       pos=wx.DefaultPosition,
                       style=wx.DEFAULT_DIALOG_STYLE)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, None, -1, "InVesalius 3", size=wx.DefaultSize,
                               pos=wx.DefaultPosition,
                               style=wx.DEFAULT_DIALOG_STYLE)

        # Static text which contains message to user
        label = wx.StaticText(self, -1, message)

        # Numeric value to be changed by user
        num_ctrl = masked.NumCtrl(self, value=value, integerWidth=3,
                                    fractionWidth=2,
                                    allowNegative=True,
                                    signedForegroundColour = "Black")
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
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
        sizer.Add(num_ctrl, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Centre()

    def SetValue(self, value):
        self.num_ctrl.SetValue(value)

    def GetValue(self):
        return self.num_ctrl.GetValue()


class ResizeImageDialog(wx.Dialog):

    def __init__(self):#, message, value=0):
        try:
            pre = self.pre = wx.PreDialog()
            pre.Create(None, -1, "InVesalius 3", size=wx.DefaultSize,
                       pos=wx.DefaultPosition,
                       style=wx.DEFAULT_DIALOG_STYLE)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, None, -1, "InVesalius 3", size=wx.DefaultSize,
                              pos=wx.DefaultPosition,
                              style=wx.DEFAULT_DIALOG_STYLE)

        lbl_message = wx.StaticText(self, -1, _("InVesalius is running on a 32-bit operating system or has insufficient memory. \nIf you want to work with 3D surfaces or volume rendering, \nit is recommended to reduce the medical images resolution."))
        icon = wx.ArtProvider.GetBitmap(wx.ART_WARNING, wx.ART_MESSAGE_BOX, (32,32))
        bmp = wx.StaticBitmap(self, -1, icon)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()

        lbl_message_percent = wx.StaticText(self, -1,_("Percentage of original resolution"))

        num_ctrl_percent = wx.SpinCtrl(self, -1)
        num_ctrl_percent.SetRange(20,100)
        self.num_ctrl_porcent = num_ctrl_percent

        sizer_percent = wx.BoxSizer(wx.HORIZONTAL)
        sizer_percent.Add(lbl_message_percent, 0, wx.EXPAND|wx.ALL, 5)
        sizer_percent.Add(num_ctrl_percent, 0, wx.ALL, 5)

        sizer_itens = wx.BoxSizer(wx.VERTICAL)
        sizer_itens.Add(lbl_message, 0, wx.EXPAND|wx.ALL, 5)
        sizer_itens.Add(sizer_percent, 0, wx.EXPAND|wx.ALL, 5)
        sizer_itens.Add(btn_sizer, 0, wx.EXPAND|wx.ALL, 5)

        sizer_general = wx.BoxSizer(wx.HORIZONTAL)
        sizer_general.Add(bmp, 0, wx.ALIGN_CENTRE|wx.ALL, 10)
        sizer_general.Add(sizer_itens, 0, wx.ALL , 5)

        #self.SetAutoLayout(True)
        self.SetSizer(sizer_general)
        sizer_general.Fit(self)
        self.Layout()
        self.Centre()

    def SetValue(self, value):
        self.num_ctrl_porcent.SetValue(value)

    def GetValue(self):
        return self.num_ctrl_porcent.GetValue()

    def Close(self):
        self.Destroy()

def ShowNumberDialog(message, value=0):
    dlg = NumberDialog(message, value)
    dlg.SetValue(value)

    if dlg.ShowModal() == wx.ID_OK:
        return dlg.GetValue()
    dlg.Destroy()

    return 0


class ProgressDialog(object):
    def __init__(self, maximum, abort=False):
        self.title = "InVesalius 3"
        self.msg = _("Loading DICOM files")
        self.maximum = maximum
        self.current = 0
        self.style = wx.PD_APP_MODAL
        if abort:
            self.style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT

        self.dlg = wx.ProgressDialog(self.title,
                                     self.msg,
                                     maximum = self.maximum,
                                     parent = None,
                                     style  = self.style)

        self.dlg.Bind(wx.EVT_BUTTON, self.Cancel)
        self.dlg.SetSize(wx.Size(250,150))

    def Cancel(self, evt):
        Publisher.sendMessage("Cancel DICOM load")

    def Update(self, value, message):
        if(int(value) != self.maximum):
            try:
                return self.dlg.Update(value,message)
            #TODO:
            #Exception in the Windows XP 64 Bits with wxPython 2.8.10
            except(wx._core.PyAssertionError):
                return True
        else:
            return False

    def Close(self):
        self.dlg.Destroy()


# ---------

INV_NON_COMPRESSED = 0
INV_COMPRESSED = 1

WILDCARD_INV_SAVE = _("InVesalius project (*.inv3)|*.inv3") + "|" + \
                    _("InVesalius project compressed (*.inv3)|*.inv3")

WILDCARD_OPEN = "InVesalius 3 project (*.inv3)|*.inv3|" \
                "All files (*.*)|*.*"

WILDCARD_ANALYZE = "Analyze 7.5 (*.hdr)|*.hdr|" \
                   "All files (*.*)|*.*"

WILDCARD_NIFTI = "NIfTI 1 (*.nii)|*.nii|" \
                 "Compressed NIfTI (*.nii.gz)|*.nii.gz|" \
                 "HDR NIfTI (*.hdr)|*.hdr|" \
                 "All files (*.*)|*.*"
#".[jJ][pP][gG]"
WILDCARD_PARREC = "PAR/REC (*.par)|*.par|" \
                  "All files (*.*)|*.*"

WILDCARD_MESH_FILES = "STL File format (*.stl)|*.stl|" \
                      "Standard Polygon File Format (*.ply)|*.ply|" \
                      "Alias Wavefront Object (*.obj)|*.obj|" \
                      "VTK Polydata File Format (*.vtp)|*.vtp|" \
                      "All files (*.*)|*.*"


def ShowOpenProjectDialog():
    # Default system path
    current_dir = os.path.abspath(".")
    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_inv3', '')
    dlg = wx.FileDialog(None, message=_("Open InVesalius 3 project..."),
                        defaultDir=last_directory,
                        defaultFile="", wildcard=WILDCARD_OPEN,
                        style=wx.FD_OPEN|wx.FD_CHANGE_DIR)

    # inv3 filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            filepath = dlg.GetPath()
    except(wx._core.PyAssertionError):  # FIX: win64
        filepath = dlg.GetPath()

    if filepath:
        session['paths']['last_directory_inv3'] = os.path.split(filepath)[0]
        session.WriteSessionFile()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filepath


def ShowImportDirDialog(self):
    current_dir = os.path.abspath(".")

    if sys.platform == 'win32' or sys.platform.startswith('linux'):
        session = ses.Session()

        if (session.GetLastDicomFolder()):
            folder = session.GetLastDicomFolder()
        else:
            folder = ''
    else:
        folder = ''

    dlg = wx.DirDialog(self, _("Choose a DICOM folder:"), folder,
                        style=wx.DD_DEFAULT_STYLE
                        | wx.DD_DIR_MUST_EXIST
                        | wx.DD_CHANGE_DIR)

    path = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # GetPath returns in unicode, if a path has non-ascii characters a
            # UnicodeEncodeError is raised. To avoid this, path is encoded in utf-8
            if sys.platform == "win32":
                path = dlg.GetPath()
            else:
                path = dlg.GetPath().encode('utf-8')

    except(wx._core.PyAssertionError): #TODO: error win64
         if (dlg.GetPath()):
             path = dlg.GetPath()

    if (sys.platform != 'darwin'):
        if (path):
            session.SetLastDicomFolder(path)

    # Only destroy a dialog after you're done with it.
    dlg.Destroy()
    os.chdir(current_dir)
    return path

def ShowImportBitmapDirDialog(self):
    current_dir = os.path.abspath(".")

    #  if sys.platform == 'win32' or sys.platform.startswith('linux'):
        #  session = ses.Session()

        #  if (session.GetLastDicomFolder()):
            #  folder = session.GetLastDicomFolder()
        #  else:
            #  folder = ''
    #  else:
        #  folder = ''
    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_bitmap', '')

    dlg = wx.DirDialog(self, _("Choose a folder with TIFF, BMP, JPG or PNG:"), last_directory,
                        style=wx.DD_DEFAULT_STYLE
                        | wx.DD_DIR_MUST_EXIST
                        | wx.DD_CHANGE_DIR)

    path = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # GetPath returns in unicode, if a path has non-ascii characters a
            # UnicodeEncodeError is raised. To avoid this, path is encoded in utf-8
            path = dlg.GetPath()

    except(wx._core.PyAssertionError): #TODO: error win64
         if (dlg.GetPath()):
             path = dlg.GetPath()

    #  if (sys.platform != 'darwin'):
        #  if (path):
            #  session.SetLastDicomFolder(path)

    if path:
        session['paths']['last_directory_bitmap'] = path
        session.WriteSessionFile()

    # Only destroy a dialog after you're done with it.
    dlg.Destroy()
    os.chdir(current_dir)
    return path


def ShowImportOtherFilesDialog(id_type):
    # Default system path
    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_%d' % id_type, '')
    dlg = wx.FileDialog(None, message=_("Import Analyze 7.5 file"),
                        defaultDir=last_directory,
                        defaultFile="", wildcard=WILDCARD_ANALYZE,
                        style=wx.FD_OPEN | wx.FD_CHANGE_DIR)

    if id_type == const.ID_NIFTI_IMPORT:
        dlg.SetMessage(_("Import NIFTi 1 file"))
        dlg.SetWildcard(WILDCARD_NIFTI)
    elif id_type == const.ID_PARREC_IMPORT:
        dlg.SetMessage(_("Import PAR/REC file"))
        dlg.SetWildcard(WILDCARD_PARREC)

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
                filename = dlg.GetPath().encode('utf-8')

    except(wx._core.PyAssertionError):  # TODO: error win64
        if (dlg.GetPath()):
            filename = dlg.GetPath()

    if filename:
        session['paths']['last_directory_%d' % id_type] = os.path.split(dlg.GetPath())[0]
        session.WriteSessionFile()
    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    return filename


def ShowImportMeshFilesDialog():
    # Default system path
    current_dir = os.path.abspath(".")
    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_surface_import', '')
    dlg = wx.FileDialog(None, message=_("Import surface file"),
                        defaultDir=last_directory,
                        wildcard=WILDCARD_MESH_FILES,
                        style=wx.FD_OPEN | wx.FD_CHANGE_DIR)

    # stl filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()

    except(wx._core.PyAssertionError):  # TODO: error win64
        if (dlg.GetPath()):
            filename = dlg.GetPath()

    if filename:
        session['paths']['last_directory_surface_import'] = os.path.split(filename)[0]
        session.WriteSessionFile()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filename

def ImportMeshCoordSystem():
    msg = _("Was the imported mesh created by InVesalius?")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                               wx.YES_NO)

    if dlg.ShowModal() == wx.ID_YES:
        flag = False
    else:
        flag = True

    dlg.Destroy()
    return flag

def ShowSaveAsProjectDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_inv3', '')
    dlg = wx.FileDialog(None,
                        _("Save project as..."), # title
                        last_directory, # last used directory
                        default_filename,
                        WILDCARD_INV_SAVE,
                        wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
    #dlg.SetFilterIndex(0) # default is VTI

    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            ok = 1
        else:
            ok = 0
    except(wx._core.PyAssertionError): #TODO: fix win64
        filename = dlg.GetPath()
        ok = 1

    if (ok):
        extension = "inv3"
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension

    if filename:
        session['paths']['last_directory_inv3'] = os.path.split(filename)[0]
        session.WriteSessionFile()

    wildcard = dlg.GetFilterIndex()
    os.chdir(current_dir)
    return filename, wildcard == INV_COMPRESSED


# Dialog for neuronavigation markers
def ShowSaveMarkersDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None,
                        _("Save markers as..."),  # title
                        "",  # last used directory
                        default_filename,
                        _("Markers files (*.mks)|*.mks"),
                        wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    # dlg.SetFilterIndex(0) # default is VTI

    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            ok = 1
        else:
            ok = 0
    except(wx._core.PyAssertionError):  # TODO: fix win64
        filename = dlg.GetPath()
        ok = 1

    if (ok):
        extension = "mks"
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension

    os.chdir(current_dir)
    return filename

def ShowSaveCoordsDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None,
                        _("Save coords as..."),  # title
                        "",  # last used directory
                        default_filename,
                        _("Coordinates files (*.csv)|*.csv"),
                        wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    # dlg.SetFilterIndex(0) # default is VTI

    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            ok = 1
        else:
            ok = 0
    except(wx._core.PyAssertionError):  # TODO: fix win64
        filename = dlg.GetPath()
        ok = 1

    if (ok):
        extension = "csv"
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension

    os.chdir(current_dir)
    return filename


def ShowLoadMarkersDialog():
    current_dir = os.path.abspath(".")

    dlg = wx.FileDialog(None, message=_("Load markers"),
                        defaultDir="",
                        defaultFile="",
                        wildcard=_("Markers files (*.mks)|*.mks"),
                        style=wx.FD_OPEN|wx.FD_CHANGE_DIR)

    # inv3 filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            filepath = dlg.GetPath()
    except(wx._core.PyAssertionError):  # FIX: win64
        filepath = dlg.GetPath()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filepath


def ShowSaveRegistrationDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None,
                        _("Save object registration as..."),  # title
                        "",  # last used directory
                        default_filename,
                        _("Registration files (*.obr)|*.obr"),
                        wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    # dlg.SetFilterIndex(0) # default is VTI

    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            ok = 1
        else:
            ok = 0
    except(wx._core.PyAssertionError):  # TODO: fix win64
        filename = dlg.GetPath()
        ok = 1

    if (ok):
        extension = "obr"
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension

    os.chdir(current_dir)
    return filename


def ShowLoadRegistrationDialog():
    current_dir = os.path.abspath(".")

    dlg = wx.FileDialog(None, message=_("Load object registration"),
                        defaultDir="",
                        defaultFile="",
                        wildcard=_("Registration files (*.obr)|*.obr"),
                        style=wx.FD_OPEN|wx.FD_CHANGE_DIR)

    # inv3 filter is default
    dlg.SetFilterIndex(0)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            filepath = dlg.GetPath()
    except(wx._core.PyAssertionError):  # FIX: win64
        filepath = dlg.GetPath()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filepath


class MessageDialog(wx.Dialog):
    def __init__(self, message):
        try:
            pre = wx.PreDialog()
            pre.Create(None, -1, "InVesalius 3",  size=(360, 370), pos=wx.DefaultPosition,
                        style=wx.DEFAULT_DIALOG_STYLE|wx.ICON_INFORMATION)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, None, -1, "InVesalius 3",  size=(360, 370), pos=wx.DefaultPosition,
                        style=wx.DEFAULT_DIALOG_STYLE|wx.ICON_INFORMATION)

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
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|
                  wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Centre()


class UpdateMessageDialog(wx.Dialog):
    def __init__(self, url):
        msg=_("A new version of InVesalius is available. Do you want to open the download website now?")
        title=_("Invesalius Update")
        self.url = url

        try:
            pre = wx.PreDialog()
            pre.Create(None, -1, title,  size=(360, 370), pos=wx.DefaultPosition,
                        style=wx.DEFAULT_DIALOG_STYLE|wx.ICON_INFORMATION)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, None, -1, title,  size=(360, 370), pos=wx.DefaultPosition,
                        style=wx.DEFAULT_DIALOG_STYLE|wx.ICON_INFORMATION)

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
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|
                  wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Centre()

        btn_yes.Bind(wx.EVT_BUTTON, self._OnYes)
        btn_no.Bind(wx.EVT_BUTTON, self._OnNo)

        # Subscribing to the pubsub event which happens when InVesalius is
        # closed.
        Publisher.subscribe(self._OnCloseInV, 'Exit')

    def _OnYes(self, evt):
        # Launches the default browser with the url to download the new
        # InVesalius version.
        wx.LaunchDefaultBrowser(self.url)
        self.Close()
        self.Destroy()

    def _OnNo(self, evt):
        # Closes and destroy this dialog.
        self.Close()
        self.Destroy()

    def _OnCloseInV(self):
        # Closes and destroy this dialog.
        self.Close()
        self.Destroy()


def SaveChangesDialog__Old(filename):
    message = _("The project %s has been modified.\nSave changes?")%filename
    dlg = MessageDialog(message)

    answer = dlg.ShowModal()
    dlg.Destroy()
    if answer == wx.ID_YES:
        return 1
    elif answer == wx.ID_NO:
        return 0
    else:
        return -1


def ImportEmptyDirectory(dirpath):
    msg = _("%s is an empty folder.") % dirpath.decode("utf-8")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "",
                                msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg,
                               "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ImportOldFormatInvFile():
    msg = _("File was created in a newer InVesalius version. Some functionalities may not work correctly.")
    dlg = wx.MessageDialog(None, msg,
                           "InVesalius 3",
                           wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ImportInvalidFiles(ftype="DICOM"):
    if ftype == "Bitmap":
        msg =  _("There are no Bitmap, JPEG, PNG or TIFF files in the selected folder.")
    elif ftype == "DICOM":
        msg = _("There are no DICOM files in the selected folder.")
    else:
        msg = _("Invalid file.")

    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def ImportAnalyzeWarning():
    msg1 = _("Warning! InVesalius has limited support to Analyze format.\n")
    msg2 = _("Slices may be wrongly oriented and functions may not work properly.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg1 + msg2,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg1 + msg2, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def InexistentMask():
    msg = _("A mask is needed to create a surface.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def MaskSelectionRequiredForRemoval():
    msg = _("No mask was selected for removal.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def SurfaceSelectionRequiredForRemoval():
    msg = _("No surface was selected for removal.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def MeasureSelectionRequiredForRemoval():
    msg = _("No measure was selected for removal.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def MaskSelectionRequiredForDuplication():
    msg = _("No mask was selected for duplication.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()



def SurfaceSelectionRequiredForDuplication():
    msg = _("No surface was selected for duplication.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


# Dialogs for neuronavigation mode
def InvalidFiducials():
    msg = _("Fiducials are invalid. Select all coordinates.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def InvalidObjectRegistration():
    msg = _("Perform coil registration before navigation.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def NavigationTrackerWarning(trck_id, lib_mode):
    """
    Spatial Tracker connection error
    """
    trck = {1: 'Claron MicronTracker',
            2: 'Polhemus FASTRAK',
            3: 'Polhemus ISOTRAK',
            4: 'Polhemus PATRIOT',
            5: 'Debug tracker device'}

    if lib_mode == 'choose':
        msg = _('No tracking device selected')
    elif lib_mode == 'error':
        msg = trck[trck_id] + _(' is not installed.')
    elif lib_mode == 'disconnect':
        msg = trck[trck_id] + _(' disconnected.')
    else:
        msg = trck[trck_id] + _(' is not connected.')

    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)

    dlg.ShowModal()
    dlg.Destroy()


def InvalidMarkersFile():
    msg = _("The TXT file is invalid.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def NoMarkerSelected():
    msg = _("No data selected")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def DeleteAllMarkers():
    msg = _("Do you really want to delete all markers?")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.OK | wx.CANCEL | wx.ICON_QUESTION)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.OK | wx.CANCEL | wx.ICON_QUESTION)
    result = dlg.ShowModal()
    dlg.Destroy()
    return result

def DeleteTarget():
    msg = _("Target deleted")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def NewTarget():
    msg = _("New target selected")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def InvalidTargetID():
    msg = _("Sorry, you cannot use 'TARGET' ID")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def EnterMarkerID(default):
    msg = _("Edit marker ID")
    if sys.platform == 'darwin':
        dlg = wx.TextEntryDialog(None, "", msg, defaultValue=default)
    else:
        dlg = wx.TextEntryDialog(None, msg, "InVesalius 3", value=default)
    dlg.ShowModal()
    result = dlg.GetValue()
    dlg.Destroy()
    return result


class NewMask(wx.Dialog):
    def __init__(self,
                 parent=None,
                 ID=-1,
                 title="InVesalius 3",
                 size=wx.DefaultSize,
                 pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE,
                 useMetal=False):
        import invesalius.constants as const
        import invesalius.data.mask as mask
        import invesalius.project as prj

        try:
            # Instead of calling wx.Dialog.__init__ we precreate the dialog
            # so we can set an extra style that must be set before
            # creation, and then we create the GUI object using the Create
            # method.
            pre = wx.PreDialog()
            pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
            pre.Create(parent, ID, title, pos, (500,300), style)
            # This next step is the most important, it turns this Python
            # object into the real wrapper of the dialog (instead of pre)
            # as far as the wxPython extension is concerned.
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, parent, ID, title, pos, (500,300), style)
            self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)


        self.CenterOnScreen()

        # This extra style can be set after the UI object has been created.
        if 'wxMac' in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # LINE 1: Surface name

        label_mask = wx.StaticText(self, -1, _("New mask name:"))

        default_name =  const.MASK_NAME_PATTERN %(mask.Mask.general_index+2)
        text = wx.TextCtrl(self, -1, "", size=(80,-1))
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
        combo_thresh = wx.ComboBox(self, -1, "", choices= self.thresh_list,
                                 style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_thresh.SetSelection(default_index)
        if sys.platform != 'win32':
            combo_thresh.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_thresh = combo_thresh

        # LINE 3: Gradient
        bound_min, bound_max = project.threshold_range
        thresh_min, thresh_max = project.threshold_modes[_("Bone")]
        original_colour = random.choice(const.MASK_COLOUR)
        self.colour = original_colour
        colour = [255*i for i in original_colour]
        colour.append(100)
        gradient = grad.GradientSlider(self, -1, int(bound_min),
                                        int(bound_max),
                                        int(thresh_min), int(thresh_max),
                                        colour)
        self.gradient = gradient

        # OVERVIEW
        # Sizer that joins content above
        flag_link = wx.EXPAND|wx.GROW|wx.ALL
        flag_button = wx.ALL | wx.EXPAND| wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=10, vgap=10)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany([ (label_mask, 1, flag_link, 5),
                              (text, 1, flag_button, 2),
                              (label_thresh, 1, flag_link, 5),
                              (combo_thresh, 0, flag_button, 1)])#,
                              #(label_quality, 1, flag_link, 5),
                              #(combo_quality, 0, flag_button, 1)])

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
        sizer.Add(fixed_sizer, 0, wx.ALL|wx.GROW|wx.EXPAND, 15)
        sizer.Add(gradient, 1, wx.BOTTOM|wx.RIGHT|wx.LEFT|wx.EXPAND|wx.GROW, 20)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT|wx.BOTTOM, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Bind(grad.EVT_THRESHOLD_CHANGED, self.OnSlideChanged, self.gradient)
        self.combo_thresh.Bind(wx.EVT_COMBOBOX, self.OnComboThresh)


    def OnComboThresh(self, evt):
        import invesalius.project as prj
        proj = prj.Project()
        (thresh_min, thresh_max) = proj.threshold_modes[evt.GetString()]
        self.gradient.SetMinimun(thresh_min)
        self.gradient.SetMaximun(thresh_max)

    def OnSlideChanged(self, evt):
        import invesalius.project as prj
        thresh_min = self.gradient.GetMinValue()
        thresh_max = self.gradient.GetMaxValue()
        thresh = (thresh_min, thresh_max)
        proj = prj.Project()
        if thresh  in proj.threshold_modes.values():
            preset_name = proj.threshold_modes.get_key(thresh)[0]
            index = self.thresh_list.index(preset_name)
            self.combo_thresh.SetSelection(index)
        else:
            index = self.thresh_list.index(_("Custom"))
            self.combo_thresh.SetSelection(index)

    def GetValue(self):
        #mask_index = self.combo_mask.GetSelection()
        mask_name = self.text.GetValue()
        thresh_value = [self.gradient.GetMinValue(), self.gradient.GetMaxValue()]
        #quality = const.SURFACE_QUALITY_LIST[self.combo_quality.GetSelection()]
        #fill_holes = self.check_box_holes.GetValue()
        #keep_largest = self.check_box_largest.GetValue()
        #return (mask_index, surface_name, quality, fill_holes, keep_largest)
        return mask_name, thresh_value, self.colour


def InexistentPath(path):
    msg = _("%s does not exist.")%(path)
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def MissingFilesForReconstruction():
    msg = _("Please, provide more than one DICOM file for 3D reconstruction")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def SaveChangesDialog(filename, parent):
    current_dir = os.path.abspath(".")
    msg = _(u"The project %s has been modified.\nSave changes?")%filename
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_QUESTION | wx.YES_NO | wx.CANCEL)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                         wx.ICON_QUESTION | wx.YES_NO | wx.CANCEL)

    try:
        answer = dlg.ShowModal()
    except(wx._core.PyAssertionError): #TODO: FIX win64
        answer =  wx.ID_YES

    dlg.Destroy()
    os.chdir(current_dir)

    if answer == wx.ID_YES:
        return 1
    elif answer == wx.ID_NO:
        return 0
    else:
        return -1

def SaveChangesDialog2(filename):
    current_dir = os.path.abspath(".")
    msg = _("The project %s has been modified.\nSave changes?")%filename
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_QUESTION | wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg,
                               "InVesalius 3",
                               wx.ICON_QUESTION | wx.YES_NO)

    answer = dlg.ShowModal()
    dlg.Destroy()
    os.chdir(current_dir)
    if answer == wx.ID_YES:
        return 1
    else:# answer == wx.ID_NO:
        return 0



def ShowAboutDialog(parent):

    info = AboutDialogInfo()
    info.Name = "InVesalius"
    info.Version = "3.1.1"
    info.Copyright = _("(c) 2007-2019 Center for Information Technology Renato Archer - CTI")
    info.Description = wordwrap(_("InVesalius is a medical imaging program for 3D reconstruction. It uses a sequence of 2D DICOM image files acquired with CT or MRI scanners. InVesalius allows exporting 3D volumes or surfaces as mesh files for creating physical models of a patient's anatomy using additive manufacturing (3D printing) technologies. The software is developed by Center for Information Technology Renato Archer (CTI), National Council for Scientific and Technological Development (CNPq) and the Brazilian Ministry of Health.\n\n InVesalius must be used only for research. The Center for Information Technology Renato Archer is not responsible for damages caused by the use of this software.\n\n Contact: invesalius@cti.gov.br"), 350, wx.ClientDC(parent))

#       _("InVesalius is a software for medical imaging 3D reconstruction. ")+\
#       _("Its input is a sequency of DICOM 2D image files acquired with CT or MR.\n\n")+\
#       _("The software also allows generating correspondent STL files,")+\
#       _("so the user can print 3D physical models of the patient's anatomy ")+\
#       _("using Rapid Prototyping."), 350, wx.ClientDC(parent))
    info.WebSite = ("https://www.cti.gov.br/invesalius")
    info.License = _("GNU GPL (General Public License) version 2")

    info.Developers = [u"Paulo Henrique Junqueira Amorim",
                       u"Thiago Franco de Moraes",
                       u"Hélio Pedrini",
                       u"Jorge Vicente Lopes da Silva",
                       u"Victor Hugo de Oliveira e Souza (navigator)",
                       u"Renan Hiroshi Matsuda (navigator)",
                       u"André Salles Cunha Peres (navigator)",
                       u"Oswaldo Baffa Filho (navigator)",
                       u"Tatiana Al-Chueyr (former)",
                       u"Guilherme Cesar Soares Ruppert (former)",
                       u"Fabio de Souza Azevedo (former)",
                       u"Bruno Lara Bottazzini (contributor)",
                       u"Olly Betts (patches to support wxPython3)"]

    info.Translators = [u"Alex P. Natsios",
                        u"Alicia Perez",
                        u"Anderson Antonio Mamede da Silva",
                        u"Andreas Loupasakis",
                        u"Angelo Pucillo",
                        u"Annalisa Manenti",
                        u"Cheng-Chia Tseng",
                        u"Dan",
                        u"DCamer",
                        u"Dimitris Glezos",
                        u"Eugene Liscio",
                        u"Frédéric Lopez",
                        u"Florin Putura",
                        u"Fri",
                        u"Jangblue",
                        u"Javier de Lima Moreno",
                        u"Kensey Okinawa",
                        u"Maki Sugimoto",
                        u"Mario Regino Moreno Guerra",
                        u"Massimo Crisantemo",
                        u"Nikolai Guschinsky",
                        u"Nikos Korkakakis",
                        u"Raul Bolliger Neto",
                        u"Sebastian Hilbert",
                        u"Semarang Pari",
                        u"Silvério Santos",
                        u"Vasily Shishkin",
                        u"Yohei Sotsuka",
                        u"Yoshihiro Sato"]

    #info.DocWriters = ["Fabio Francisco da Silva (PT)"]

    info.Artists = [u"Otavio Henrique Junqueira Amorim"]

    # Then we call AboutBox providing its info object
    AboutBox(info)


def ShowSavePresetDialog(default_filename="raycasting"):
    dlg = wx.TextEntryDialog(None,
                             _("Save raycasting preset as:"),
                             "InVesalius 3")
    #dlg.SetFilterIndex(0) # default is VTI
    filename = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetValue()
    except(wx._core.PyAssertionError):
        filename = dlg.GetValue()

    return filename

class NewSurfaceDialog(wx.Dialog):
    def __init__(self, parent=None, ID=-1, title="InVesalius 3", size=wx.DefaultSize,
            pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE,
            useMetal=False):
        import invesalius.constants as const
        import invesalius.data.surface as surface
        import invesalius.project as prj

        try:
            # Instead of calling wx.Dialog.__init__ we precreate the dialog
            # so we can set an extra style that must be set before
            # creation, and then we create the GUI object using the Create
            # method.
            pre = wx.PreDialog()
            pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
            pre.Create(parent, ID, title, pos, (500,300), style)

            # This next step is the most important, it turns this Python
            # object into the real wrapper of the dialog (instead of pre)
            # as far as the wxPython extension is concerned.
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, parent, ID, title, pos, (500,300), style)
            self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)

        self.CenterOnScreen()

        # This extra style can be set after the UI object has been created.
        if 'wxMac' in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # LINE 1: Surface name

        label_surface = wx.StaticText(self, -1, _("New surface name:"))

        default_name =  const.SURFACE_NAME_PATTERN %(surface.Surface.general_index+2)
        text = wx.TextCtrl(self, -1, "", size=(80,-1))
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
        combo_mask = wx.ComboBox(self, -1, "", choices= self.mask_list,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_mask.SetSelection(len(self.mask_list)-1)
        if sys.platform != 'win32':
            combo_mask.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_mask = combo_mask

        # LINE 3: Surface quality
        label_quality = wx.StaticText(self, -1, _("Surface quality:"))

        choices =  const.SURFACE_QUALITY_LIST
        style = wx.CB_DROPDOWN|wx.CB_READONLY
        combo_quality = wx.ComboBox(self, -1, "",
                                    choices= choices,
                                    style=style)
        combo_quality.SetSelection(3)
        if sys.platform != 'win32':
            combo_quality.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_quality = combo_quality


        # OVERVIEW
        # Sizer that joins content above
        flag_link = wx.EXPAND|wx.GROW|wx.ALL
        flag_button = wx.ALL | wx.EXPAND| wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=10, vgap=0)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany([ (label_surface, 1, flag_link, 5),
                              (text, 1, flag_button, 2),
                              (label_mask, 1, flag_link, 5),
                              (combo_mask, 0, flag_button, 1),
                              (label_quality, 1, flag_link, 5),
                              (combo_quality, 0, flag_button, 1)])


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
        sizer.Add(fixed_sizer, 0, wx.TOP|wx.RIGHT|wx.LEFT|wx.GROW|wx.EXPAND, 20)
        sizer.Add(check_box_holes, 0, wx.RIGHT|wx.LEFT, 30)
        sizer.Add(check_box_largest, 0, wx.RIGHT|wx.LEFT, 30)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT|wx.ALL, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def GetValue(self):
        mask_index = self.combo_mask.GetSelection()
        surface_name = self.text.GetValue()
        quality = const.SURFACE_QUALITY_LIST[self.combo_quality.GetSelection()]
        fill_holes = self.check_box_holes.GetValue()
        keep_largest = self.check_box_largest.GetValue()
        return (mask_index, surface_name, quality, fill_holes, keep_largest)



def ExportPicture(type_=""):
    import invesalius.constants as const
    import invesalius.project as proj
    
    INDEX_TO_EXTENSION = {0: "bmp", 1: "jpg", 2: "png", 3: "ps", 4:"povray", 5:"tiff"}
    WILDCARD_SAVE_PICTURE = _("BMP image")+" (*.bmp)|*.bmp|"+\
                                _("JPG image")+" (*.jpg)|*.jpg|"+\
                                _("PNG image")+" (*.png)|*.png|"+\
                                _("PostScript document")+" (*.ps)|*.ps|"+\
                                _("POV-Ray file")+" (*.pov)|*.pov|"+\
                                _("TIFF image")+" (*.tif)|*.tif"

    INDEX_TO_TYPE = {0: const.FILETYPE_BMP,
                1: const.FILETYPE_JPG,
                2: const.FILETYPE_PNG,
                3: const.FILETYPE_PS,
                4: const.FILETYPE_POV,
                5: const.FILETYPE_TIF}

    utils.debug("ExportPicture")
    project = proj.Project()

    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_screenshot', '')

    project_name = "%s_%s" % (project.name, type_)
    if not sys.platform in ('win32', 'linux2', 'linux'):
        project_name += ".jpg"

    dlg = wx.FileDialog(None,
                        "Save %s picture as..." %type_,
                        last_directory, # last used directory
                        project_name, # filename
                        WILDCARD_SAVE_PICTURE,
                        wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
    dlg.SetFilterIndex(1) # default is VTI

    if dlg.ShowModal() == wx.ID_OK:
        filetype_index = dlg.GetFilterIndex()
        filetype = INDEX_TO_TYPE[filetype_index]
        extension = INDEX_TO_EXTENSION[filetype_index]
        filename = dlg.GetPath()
        session['paths']['last_directory_screenshot'] = os.path.split(filename)[0]
        session.WriteSessionFile()
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "."+ extension
        return filename, filetype
    else:
        return ()


class SurfaceDialog(wx.Dialog):
    '''
    This dialog is only shown when the mask whose surface will be generate was
    edited. So far, the only options available are the choice of method to
    generate the surface, Binary or `Context aware smoothing', and options from
    `Context aware smoothing'
    '''
    def __init__(self):
        wx.Dialog.__init__(self, None, -1, _('Surface generation options'))
        self._build_widgets()
        self.CenterOnScreen()

    def _build_widgets(self):
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()

        self.ca = SurfaceMethodPanel(self, -1, True)

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_sizer.Add(self.ca, 0, wx.EXPAND|wx.ALL, 5)
        self.main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(self.main_sizer)
        self.Fit()

    def GetOptions(self):
        return self.ca.GetOptions()

    def GetAlgorithmSelected(self):
        return self.ca.GetAlgorithmSelected()


####################### New surface creation dialog ###########################
class SurfaceCreationDialog(wx.Dialog):
    def __init__(self, parent=None, ID=-1, title=_(u"Surface creation"),
                 size=wx.DefaultSize, pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE, useMetal=False,
                 mask_edited=False):

        # Instead of calling wx.Dialog.__init__ we precreate the dialog
        # so we can set an extra style that must be set before
        # creation, and then we create the GUI object using the Create
        # method.
        try:
            pre = wx.PreDialog()
            pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
            pre.Create(parent, ID, title, pos, (500,300), style)

            # This extra style can be set after the UI object has been created.
            if 'wxMac' in wx.PlatformInfo and useMetal:
                self.SetExtraStyle(wx.DIALOG_EX_METAL)

            # This next step is the most important, it turns this Python
            # object into the real wrapper of the dialog (instead of pre)
            # as far as the wxPython extension is concerned.
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, parent, ID, title, pos, size, style)
            self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
            if 'wxMac' in wx.PlatformInfo and useMetal:
                self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()

        # It's necessary to create a staticbox before is children widgets
        # because otherwise in MacOSX it'll not be possible to use the mouse in
        # static's children widgets.
        sb_nsd = wx.StaticBox(self, -1, _('Surface creation options'))
        self.nsd = SurfaceCreationOptionsPanel(self, -1)
        self.nsd.Bind(EVT_MASK_SET, self.OnSetMask)
        surface_options_sizer = wx.StaticBoxSizer(sb_nsd, wx.VERTICAL)
        surface_options_sizer.Add(self.nsd, 1, wx.EXPAND|wx.ALL, 5)

        sb_ca = wx.StaticBox(self, -1, _('Surface creation method'))
        self.ca = SurfaceMethodPanel(self, -1, mask_edited)
        surface_method_sizer = wx.StaticBoxSizer(sb_ca, wx.VERTICAL)
        surface_method_sizer.Add(self.ca, 1, wx.EXPAND|wx.ALL, 5)

        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL)

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.AddButton(btn_cancel)
        btnsizer.Realize()

        sizer_panels = wx.BoxSizer(wx.HORIZONTAL)
        sizer_panels.Add(surface_options_sizer, 0, wx.EXPAND|wx.ALL, 5)
        sizer_panels.Add(surface_method_sizer, 0, wx.EXPAND|wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(sizer_panels, 0, wx.ALIGN_RIGHT|wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT|wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def OnSetMask(self, evt):
        import invesalius.project as proj
        mask = proj.Project().mask_dict[evt.mask_index]
        self.ca.mask_edited = mask.was_edited
        self.ca.ReloadMethodsOptions()

    def GetValue(self):
        return {"method": self.ca.GetValue(),
                "options": self.nsd.GetValue()}

class SurfaceCreationOptionsPanel(wx.Panel):
    def __init__(self, parent, ID=-1):
        import invesalius.constants as const
        import invesalius.data.surface as surface
        import invesalius.project as prj
        import invesalius.data.slice_ as slc

        wx.Panel.__init__(self, parent, ID)

        # LINE 1: Surface name
        label_surface = wx.StaticText(self, -1, _("New surface name:"))

        default_name =  const.SURFACE_NAME_PATTERN %(surface.Surface.general_index+2)
        text = wx.TextCtrl(self, -1, "", size=(80,-1))
        text.SetHelpText(_("Name the surface to be created"))
        text.SetValue(default_name)
        self.text = text

        # LINE 2: Mask of reference

        # Informative label
        label_mask = wx.StaticText(self, -1, _("Mask of reference:"))

        #Retrieve existing masks
        project = prj.Project()
        index_list = project.mask_dict.keys()
        self.mask_list = [project.mask_dict[index].name for index in sorted(index_list)]
        
        active_mask = slc.Slice().current_mask.index
        #active_mask = len(self.mask_list)-1

        # Mask selection combo
        combo_mask = wx.ComboBox(self, -1, "", choices= self.mask_list,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_mask.SetSelection(active_mask)
        combo_mask.Bind(wx.EVT_COMBOBOX, self.OnSetMask)
        if sys.platform != 'win32':
            combo_mask.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_mask = combo_mask

        # LINE 3: Surface quality
        label_quality = wx.StaticText(self, -1, _("Surface quality:"))

        choices =  const.SURFACE_QUALITY_LIST
        style = wx.CB_DROPDOWN|wx.CB_READONLY
        combo_quality = wx.ComboBox(self, -1, "",
                                    choices= choices,
                                    style=style)
        combo_quality.SetSelection(3)
        if sys.platform != 'win32':
            combo_quality.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.combo_quality = combo_quality

        # OVERVIEW
        # Sizer that joins content above
        flag_link = wx.EXPAND|wx.GROW|wx.ALL
        flag_button = wx.ALL | wx.EXPAND| wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=10, vgap=5)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany([ (label_surface, 1, flag_link, 0),
                              (text, 1, flag_button, 0),
                              (label_mask, 1, flag_link, 0),
                              (combo_mask, 0, flag_button, 0),
                              (label_quality, 1, flag_link, 0),
                              (combo_quality, 0, flag_button, 0)])


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
        sizer.Add(fixed_sizer, 0, wx.TOP|wx.RIGHT|wx.LEFT|wx.GROW|wx.EXPAND, 5)
        sizer.Add(check_box_border_holes, 0, wx.RIGHT|wx.LEFT, 5)
        sizer.Add(check_box_holes, 0, wx.RIGHT|wx.LEFT, 5)
        sizer.Add(check_box_largest, 0, wx.RIGHT|wx.LEFT, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def OnSetMask(self, evt):
        new_evt = MaskEvent(myEVT_MASK_SET, -1, self.combo_mask.GetSelection())
        self.GetEventHandler().ProcessEvent(new_evt)

    def GetValue(self):
        mask_index = self.combo_mask.GetSelection()
        surface_name = self.text.GetValue()
        quality = const.SURFACE_QUALITY_LIST[self.combo_quality.GetSelection()]
        fill_border_holes = self.check_box_border_holes.GetValue()
        fill_holes = self.check_box_holes.GetValue()
        keep_largest = self.check_box_largest.GetValue()
        return {"index": mask_index,
                "name": surface_name,
                "quality": quality,
                "fill_border_holes": fill_border_holes,
                "fill": fill_holes,
                "keep_largest": keep_largest,
                "overwrite": False}


class CAOptions(wx.Panel):
    '''
    Options related to Context aware algorithm:
    Angle: The min angle to a vertex to be considered a staircase vertex;
    Max distance: The max distance a normal vertex must be to calculate its
        weighting;
    Min Weighting: The min weight a vertex must have;
    Steps: The number of iterations the smoothing algorithm have to do.
    '''
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self._build_widgets()

    def _build_widgets(self):
        sb = wx.StaticBox(self, -1, _('Options'))
        self.angle = floatspin.FloatSpin(self, -1, value=0.7, min_val=0.0,
                                         max_val=1.0, increment=0.1,
                                         digits=1)

        self.max_distance = floatspin.FloatSpin(self, -1, value=3.0, min_val=0.0,
                                         max_val=100.0, increment=0.1,
                                         digits=2)

        self.min_weight = floatspin.FloatSpin(self, -1, value=0.5, min_val=0.0,
                                         max_val=1.0, increment=0.1,
                                         digits=1)

        self.steps = wx.SpinCtrl(self, -1, value='10', min=1, max=100)

        layout_sizer = wx.FlexGridSizer(rows=4, cols=2, hgap=5, vgap=5)
        layout_sizer.Add(wx.StaticText(self, -1, _(u'Angle:')),  0, wx.EXPAND)
        layout_sizer.Add(self.angle, 0, wx.EXPAND)
        layout_sizer.Add(wx.StaticText(self, -1, _(u'Max. distance:')),  0, wx.EXPAND)
        layout_sizer.Add(self.max_distance, 0, wx.EXPAND)
        layout_sizer.Add(wx.StaticText(self, -1, _(u'Min. weight:')), 0, wx.EXPAND)
        layout_sizer.Add(self.min_weight, 0, wx.EXPAND)
        layout_sizer.Add(wx.StaticText(self, -1, _(u'N. steps:')),  0, wx.EXPAND)
        layout_sizer.Add(self.steps, 0, wx.EXPAND)

        self.main_sizer = wx.StaticBoxSizer(sb, wx.VERTICAL)
        self.main_sizer.Add(layout_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(self.main_sizer)

class SurfaceMethodPanel(wx.Panel):
    '''
    This dialog is only shown when the mask whose surface will be generate was
    edited. So far, the only options available are the choice of method to
    generate the surface, Binary or `Context aware smoothing', and options from
    `Context aware smoothing'
    '''
    def __init__(self, parent, id, mask_edited=False):
        wx.Panel.__init__(self, parent, id)

        self.mask_edited = mask_edited
        self.alg_types = {_(u'Default'): 'Default',
                          _(u'Context aware smoothing'): 'ca_smoothing',
                          _(u'Binary'): 'Binary'}
        self.edited_imp = [_(u'Default'), ]

        self._build_widgets()
        self._bind_wx()

    def _build_widgets(self):
        self.ca_options = CAOptions(self)

        self.cb_types = wx.ComboBox(self, -1, _(u'Default'),
                                    choices=[i for i in sorted(self.alg_types)
                                            if not (self.mask_edited and i in self.edited_imp)],
                                    style=wx.CB_READONLY)
        w, h = self.cb_types.GetSizeTuple()

        icon = wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_MESSAGE_BOX,
                                        (h * 0.8, h * 0.8))
        self.bmp = wx.StaticBitmap(self, -1, icon)
        self.bmp.SetToolTipString(_("It is not possible to use the Default method because the mask was edited."))

        self.method_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.method_sizer.Add(wx.StaticText(self, -1, _(u'Method:')), 0,
                              wx.EXPAND | wx.ALL, 5)
        self.method_sizer.Add(self.cb_types, 1, wx.EXPAND)
        self.method_sizer.Add(self.bmp, 0, wx.EXPAND|wx.ALL, 5)

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_sizer.Add(self.method_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.main_sizer.Add(self.ca_options, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(self.main_sizer)
        self.Layout()
        self.Fit()

        if self.mask_edited:
            self.cb_types.SetValue(_(u'Context aware smoothing'))
            self.ca_options.Enable()
            self.method_sizer.Show(self.bmp)
        else:
            self.ca_options.Disable()
            self.method_sizer.Hide(self.bmp)

    def _bind_wx(self):
        self.cb_types.Bind(wx.EVT_COMBOBOX, self._set_cb_types)

    def _set_cb_types(self, evt):
        if self.alg_types[evt.GetString()] == 'ca_smoothing':
            self.ca_options.Enable()
        else:
            self.ca_options.Disable()
        evt.Skip()

    def GetAlgorithmSelected(self):
        try:
            return self.alg_types[self.cb_types.GetValue()]
        except KeyError:
            return self.alg_types[0]

    def GetOptions(self):
        if self.GetAlgorithmSelected() == 'ca_smoothing':
            options = {'angle': self.ca_options.angle.GetValue(),
                       'max distance': self.ca_options.max_distance.GetValue(),
                       'min weight': self.ca_options.min_weight.GetValue(),
                       'steps': self.ca_options.steps.GetValue()}
        else:
            options = {}
        return options

    def GetValue(self):
        algorithm = self.GetAlgorithmSelected()
        options = self.GetOptions()

        return {"algorithm": algorithm,
                "options": options}

    def ReloadMethodsOptions(self):
        self.cb_types.Clear()
        self.cb_types.AppendItems([i for i in sorted(self.alg_types)
                                   if not (self.mask_edited and i in self.edited_imp)])
        if self.mask_edited:
            self.cb_types.SetValue(_(u'Context aware smoothing'))
            self.ca_options.Enable()
            self.method_sizer.Show(self.bmp)
        else:
            self.cb_types.SetValue(_(u'Default'))
            self.ca_options.Disable()
            self.method_sizer.Hide(self.bmp)

        self.method_sizer.Layout()


class ClutImagedataDialog(wx.Dialog):
    def __init__(self, histogram, init, end, nodes=None):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.histogram = histogram
        self.init = init
        self.end = end
        self.nodes = nodes

        self._init_gui()
        self.bind_events()
        self.bind_events_wx()

    def _init_gui(self):
        self.clut_widget = CLUTImageDataWidget(self, -1, self.histogram,
                                               self.init, self.end, self.nodes)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.clut_widget, 1, wx.EXPAND)

        self.SetSizer(sizer)
        self.Fit()

    def bind_events_wx(self):
        self.clut_widget.Bind(EVT_CLUT_NODE_CHANGED, self.OnClutChange)

    def bind_events(self):
        Publisher.subscribe(self._refresh_widget, 'Update clut imagedata widget')

    def OnClutChange(self, evt):
        Publisher.sendMessage('Change colour table from background image from widget',
                              nodes=evt.GetNodes())
        Publisher.sendMessage('Update window level text',
                              window=self.clut_widget.window_width,
                              level=self.clut_widget.window_level)

    def _refresh_widget(self):
        self.clut_widget.Refresh()

    def Show(self, gen_evt=True, show=True):
        super(wx.Dialog, self).Show(show)
        if gen_evt:
            self.clut_widget._generate_event()


class WatershedOptionsPanel(wx.Panel):
    def __init__(self, parent, config):
        wx.Panel.__init__(self, parent)

        self.algorithms = ("Watershed", "Watershed IFT")
        self.con2d_choices = (4, 8)
        self.con3d_choices = (6, 18, 26)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        self.choice_algorithm = wx.RadioBox(self, -1, _(u"Method"),
                                           choices=self.algorithms,
                                           style=wx.NO_BORDER | wx.HORIZONTAL)
        self.choice_algorithm.SetSelection(self.algorithms.index(self.config.algorithm))

        self.choice_2dcon = wx.RadioBox(self, -1, "2D",
                                        choices=[str(i) for i in self.con2d_choices],
                                        style=wx.NO_BORDER | wx.HORIZONTAL)
        self.choice_2dcon.SetSelection(self.con2d_choices.index(self.config.con_2d))

        self.choice_3dcon = wx.RadioBox(self, -1, "3D",
                                        choices=[str(i) for i in self.con3d_choices],
                                        style=wx.NO_BORDER | wx.HORIZONTAL)
        self.choice_3dcon.SetSelection(self.con3d_choices.index(self.config.con_3d))

        self.gaussian_size = wx.SpinCtrl(self, -1, "", min=1, max=10)
        self.gaussian_size.SetValue(self.config.mg_size)

        box_sizer = wx.StaticBoxSizer(wx.StaticBox(self, -1, "Conectivity"), wx.VERTICAL)
        box_sizer.Add(self.choice_2dcon, 0, wx.ALIGN_CENTER_VERTICAL,2)
        box_sizer.Add(self.choice_3dcon, 0, wx.ALIGN_CENTER_VERTICAL,2)

        g_sizer = wx.BoxSizer(wx.HORIZONTAL)
        g_sizer.Add(wx.StaticText(self, -1, _("Gaussian sigma")), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        g_sizer.Add(self.gaussian_size, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.choice_algorithm, 0, wx.ALIGN_CENTER_VERTICAL,2)
        sizer.Add(box_sizer, 1, wx.EXPAND,2)
        sizer.Add(g_sizer, 0, wx.ALIGN_LEFT, 2)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def apply_options(self):
        self.config.algorithm = self.algorithms[self.choice_algorithm.GetSelection()]
        self.config.con_2d = self.con2d_choices[self.choice_2dcon.GetSelection()]
        self.config.con_3d = self.con3d_choices[self.choice_3dcon.GetSelection()]
        self.config.mg_size = self.gaussian_size.GetValue()


class WatershedOptionsDialog(wx.Dialog):
    def __init__(self, config, ID=-1, title=_(u'Watershed'), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), ID, title=title, style=style)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self):
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
        sizer.Add(btnsizer, 0, wx.EXPAND)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.CenterOnScreen()

    def OnOk(self, evt):
        self.wop.apply_options()
        evt.Skip()

class MaskBooleanDialog(wx.Dialog):
    def __init__(self, masks, ID=-1, title=_(u"Boolean operations"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), ID, title=title, style=style)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self._init_gui(masks)
        self.CenterOnScreen()

    def _init_gui(self, masks):
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

        icon_folder = const.ICON_DIR
        op_choices = ((_(u"Union"), const.BOOLEAN_UNION, 'bool_union.png'),
                      (_(u"Difference"), const.BOOLEAN_DIFF, 'bool_difference.png'),
                      (_(u"Intersection"), const.BOOLEAN_AND, 'bool_intersection.png'),
                      (_(u"Exclusive disjunction"), const.BOOLEAN_XOR, 'bool_disjunction.png'))
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

        gsizer.Add(wx.StaticText(self, -1, _(u"Mask 1")))
        gsizer.Add(self.mask1, 1, wx.EXPAND)
        gsizer.Add(wx.StaticText(self, -1, _(u"Operation")))
        gsizer.Add(self.op_boolean, 1, wx.EXPAND)
        gsizer.Add(wx.StaticText(self, -1, _(u"Mask 2")))
        gsizer.Add(self.mask2, 1, wx.EXPAND)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gsizer, 0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=5)
        sizer.Add(btnsizer, 0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=5)

        self.SetSizer(sizer)
        sizer.Fit(self)


        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def OnOk(self, evt):
        op = self.op_boolean.GetClientData(self.op_boolean.GetSelection())
        m1 = self.mask1.GetClientData(self.mask1.GetSelection())
        m2 = self.mask2.GetClientData(self.mask2.GetSelection())

        Publisher.sendMessage('Do boolean operation',
                              operation=op, mask1=m1, mask2=m2)
        Publisher.sendMessage('Reload actual slice')
        Publisher.sendMessage('Refresh viewer')

        self.Close()
        self.Destroy()


class ReorientImageDialog(wx.Dialog):
    def __init__(self, ID=-1, title=_(u'Image reorientation'), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), ID, title=title, style=style)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self._closed = False

        self._last_ax = "0.0"
        self._last_ay = "0.0"
        self._last_az = "0.0"

        self._init_gui()
        self._bind_events()
        self._bind_events_wx()

    def _init_gui(self):
        interp_methods_choices = ((_(u"Nearest Neighbour"), 0),
                                  (_(u"Trilinear"), 1),
                                  (_(u"Tricubic"), 2),
                                  (_(u"Lanczos (experimental)"), 3))
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
        angles_sizer.AddMany([
            (wx.StaticText(self, -1, _("Angle X")), 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5),
            (self.anglex, 0, wx.EXPAND | wx.ALL, 5),

            (wx.StaticText(self, -1, _("Angle Y")), 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5),
            (self.angley, 0, wx.EXPAND | wx.ALL, 5),

            (wx.StaticText(self, -1, _("Angle Z")), 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5),
            (self.anglez, 0, wx.EXPAND | wx.ALL, 5),
        ])

        sizer.Add(wx.StaticText(self, -1, _("Interpolation method:")), 0, wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT, 5)
        sizer.Add(self.interp_method, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(angles_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.btnapply, 0, wx.EXPAND | wx.ALL, 5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        self.Fit()

    def _bind_events(self):
        Publisher.subscribe(self._update_angles, 'Update reorient angles')
        Publisher.subscribe(self._close_dialog, 'Close reorient dialog')

    def _bind_events_wx(self):
        self.interp_method.Bind(wx.EVT_COMBOBOX, self.OnSelect)

        self.anglex.Bind(wx.EVT_KILL_FOCUS, self.OnLostFocus)
        self.angley.Bind(wx.EVT_KILL_FOCUS, self.OnLostFocus)
        self.anglez.Bind(wx.EVT_KILL_FOCUS, self.OnLostFocus)

        self.anglex.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.angley.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.anglez.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)

        self.btnapply.Bind(wx.EVT_BUTTON, self.apply_reorientation)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def _update_angles(self, angles):
        anglex, angley, anglez = angles
        self.anglex.SetValue("%.3f" % np.rad2deg(anglex))
        self.angley.SetValue("%.3f" % np.rad2deg(angley))
        self.anglez.SetValue("%.3f" % np.rad2deg(anglez))

    def _close_dialog(self):
        self.Destroy()

    def apply_reorientation(self, evt):
        Publisher.sendMessage('Apply reorientation')
        self.Close()

    def OnClose(self, evt):
        self._closed = True
        Publisher.sendMessage('Disable style', style=const.SLICE_STATE_REORIENT)
        Publisher.sendMessage('Enable style', style=const.STATE_DEFAULT)
        self.Destroy()

    def OnSelect(self, evt):
        im_code = self.interp_method.GetClientData(self.interp_method.GetSelection())
        Publisher.sendMessage('Set interpolation method', interp_method=im_code)

    def OnSetFocus(self, evt):
        self._last_ax = self.anglex.GetValue()
        self._last_ay = self.angley.GetValue()
        self._last_az = self.anglez.GetValue()

    def OnLostFocus(self, evt):
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
            Publisher.sendMessage('Set reorientation angles', angles=(ax, ay, az))


class ImportBitmapParameters(wx.Dialog):
    from os import sys

    def __init__(self):
        if sys.platform == 'win32':
            size=wx.Size(380,180)
        else:
            size=wx.Size(380,210)

        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Create project from bitmap"),size=size,
                                    style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1,
                               _(u"Create project from bitmap"),
                               size=size,
                               style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.interval = 0

        self._init_gui()
        self.bind_evts()
        self.CenterOnScreen()


    def _init_gui(self):
        
        import invesalius.project as prj
        
        p = wx.Panel(self, -1, style = wx.TAB_TRAVERSAL
                     | wx.CLIP_CHILDREN
                     | wx.FULL_REPAINT_ON_RESIZE)
       
        gbs_principal = self.gbs = wx.GridBagSizer(4,1)

        gbs = self.gbs = wx.GridBagSizer(5, 2)
       
        flag_labels = wx.ALIGN_RIGHT  | wx.ALIGN_CENTER_VERTICAL

        stx_name = wx.StaticText(p, -1, _(u"Project name:"))
        tx_name = self.tx_name = wx.TextCtrl(p, -1, "InVesalius Bitmap", size=wx.Size(220,-1))

        stx_orientation = wx.StaticText(p, -1, _(u"Slices orientation:"),)
        cb_orientation_options = [_(u'Axial'), _(u'Coronal'), _(u'Sagital')]
        cb_orientation = self.cb_orientation = wx.ComboBox(p, value="Axial", choices=cb_orientation_options,\
                                                size=wx.Size(160,-1), style=wx.CB_DROPDOWN|wx.CB_READONLY)

        stx_spacing = wx.StaticText(p, -1, _(u"Spacing (mm):"))

        gbs.Add(stx_name, (0,0), flag=flag_labels)
        gbs.Add(tx_name, (0,1))
        try:
            gbs.Add(0, 0, (1,0))
        except TypeError:
            gbs.AddStretchSpacer((1,0))

        gbs.Add(stx_orientation, (2,0), flag=flag_labels)
        gbs.Add(cb_orientation, (2,1))

        gbs.Add(stx_spacing, (3,0))
        try:
            gbs.Add(0, 0, (4,0))
        except TypeError:
            gbs.AddStretchSpacer((4,0))

        #--- spacing --------------
        gbs_spacing = wx.GridBagSizer(2, 6)
        
        stx_spacing_x = stx_spacing_x = wx.StaticText(p, -1, _(u"X:"))
        fsp_spacing_x = self.fsp_spacing_x = FS.FloatSpin(p, -1, min_val=0,\
                                            increment=0.25, value=1.0, digits=8)


        stx_spacing_y = stx_spacing_y = wx.StaticText(p, -1, _(u"Y:"))
        fsp_spacing_y = self.fsp_spacing_y = FS.FloatSpin(p, -1, min_val=0,\
                                            increment=0.25, value=1.0, digits=8)

        stx_spacing_z = stx_spacing_z = wx.StaticText(p, -1, _(u"Z:"))
        fsp_spacing_z = self.fsp_spacing_z = FS.FloatSpin(p, -1, min_val=0,\
                                            increment=0.25, value=1.0, digits=8)


        try:
            proj = prj.Project()
            
            sx = proj.spacing[0]
            sy = proj.spacing[1]
            sz = proj.spacing[2]

            fsp_spacing_x.SetValue(sx)
            fsp_spacing_y.SetValue(sy)
            fsp_spacing_z.SetValue(sz)

        except(AttributeError):
            pass

        gbs_spacing.Add(stx_spacing_x, (0,0), flag=flag_labels)
        gbs_spacing.Add(fsp_spacing_x, (0,1))

        gbs_spacing.Add(stx_spacing_y, (0,2), flag=flag_labels)
        gbs_spacing.Add(fsp_spacing_y, (0,3))

        gbs_spacing.Add(stx_spacing_z, (0,4), flag=flag_labels)
        gbs_spacing.Add(fsp_spacing_z, (0,5))

        #----- buttons ------------------------
        gbs_button = wx.GridBagSizer(2, 4)
 
        btn_ok = self.btn_ok= wx.Button(p, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(p, wx.ID_CANCEL)

        try:
            gbs_button.Add(0, 0, (0,2))
        except TypeError:
            gbs_button.AddStretchSpacer((0,2))
        gbs_button.Add(btn_cancel, (1,2))
        gbs_button.Add(btn_ok, (1,3))

        gbs_principal.Add(gbs, (0,0), flag = wx.ALL|wx.EXPAND)
        gbs_principal.Add(gbs_spacing, (1,0),  flag=wx.ALL|wx.EXPAND)
        try:
            gbs_principal.Add(0, 0, (2,0))
        except TypeError:
            gbs_principal.AddStretchSpacer((2,0))
        gbs_principal.Add(gbs_button, (3,0), flag = wx.ALIGN_RIGHT)

        box = wx.BoxSizer()
        box.Add(gbs_principal, 1, wx.ALL|wx.EXPAND, 10)
        
        p.SetSizer(box)
        box.Fit(self)
        self.Layout()

    def bind_evts(self):
        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
   
    def SetInterval(self, v):
        self.interval = v

    def OnOk(self, evt):
        orient_selection = self.cb_orientation.GetSelection()

        if(orient_selection == 1):
            orientation = u"CORONAL"
        elif(orient_selection == 2):
            orientation = u"SAGITTAL"
        else:
            orientation = u"AXIAL"

        values = [self.tx_name.GetValue(), orientation,\
                  self.fsp_spacing_x.GetValue(), self.fsp_spacing_y.GetValue(),\
                  self.fsp_spacing_z.GetValue(), self.interval]
        Publisher.sendMessage('Open bitmap files', rec_data=values)

        self.Close()
        self.Destroy()


def BitmapNotSameSize():
    
    dlg = wx.MessageDialog(None,_("All bitmaps files must be the same \n width and height size."), 'Error',\
                                wx.OK | wx.ICON_ERROR)
 
    dlg.ShowModal()
    dlg.Destroy()


class PanelTargeFFill(wx.Panel):
    def __init__(self, parent, ID=-1, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui()

    def _init_gui(self):
        self.target_2d = wx.RadioButton(self, -1, _(u"2D - Actual slice"), style=wx.RB_GROUP)
        self.target_3d = wx.RadioButton(self, -1, _(u"3D - All slices"))

        sizer = wx.GridBagSizer(5, 5)

        try:
            sizer.Add(0, 0, (0, 0))
        except TypeError:
            sizer.AddStretchSpacer((0, 0))
        sizer.Add(self.target_2d, (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.target_3d, (2, 0), (1, 6), flag=wx.LEFT, border=5)
        try:
            sizer.Add(0, 0, (3, 0))
        except TypeError:
            sizer.AddStretchSpacer((3, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

class Panel2DConnectivity(wx.Panel):
    def __init__(self, parent, ID=-1, show_orientation=False, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui(show_orientation)

    def _init_gui(self, show_orientation):
        self.conect2D_4 = wx.RadioButton(self, -1, "4", style=wx.RB_GROUP)
        self.conect2D_8 = wx.RadioButton(self, -1, "8")

        sizer = wx.GridBagSizer(5, 5)

        try:
            sizer.Add(0, 0, (0, 0))
        except TypeError:
            sizer.AddStretchSpacer((0, 0))
        sizer.Add(wx.StaticText(self, -1, _(u"2D Connectivity")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.conect2D_4, (2, 0), flag=wx.LEFT, border=7)
        sizer.Add(self.conect2D_8, (2, 1), flag=wx.LEFT, border=7)
        try:
            sizer.Add(0, 0, (3, 0))
        except TypeError:
            sizer.AddStretchSpacer((3, 0))

        if show_orientation:
            self.cmb_orientation = wx.ComboBox(self, -1, choices=(_(u"Axial"), _(u"Coronal"), _(u"Sagital")), style=wx.CB_READONLY)
            self.cmb_orientation.SetSelection(0)

            sizer.Add(wx.StaticText(self, -1, _(u"Orientation")), (4, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=5)
            sizer.Add(self.cmb_orientation, (5, 0), (1, 10), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
            try:
                sizer.Add(0, 0, (6, 0))
            except TypeError:
                sizer.AddStretchSpacer((6, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def GetConnSelected(self):
        if self.conect2D_4.GetValue():
            return 4
        else:
            return 8

    def GetOrientation(self):
        dic_ori = {
            _(u"Axial"): 'AXIAL',
            _(u"Coronal"): 'CORONAL',
            _(u"Sagital"): 'SAGITAL'
        }

        return dic_ori[self.cmb_orientation.GetStringSelection()]


class Panel3DConnectivity(wx.Panel):
    def __init__(self, parent, ID=-1, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui()

    def _init_gui(self):
        self.conect3D_6 = wx.RadioButton(self, -1, "6", style=wx.RB_GROUP)
        self.conect3D_18 = wx.RadioButton(self, -1, "18")
        self.conect3D_26 = wx.RadioButton(self, -1, "26")

        sizer = wx.GridBagSizer(5, 5)

        try:
            sizer.Add(0, 0, (0, 0))
        except TypeError:
            sizer.AddStretchSpacer((0, 0))
        sizer.Add(wx.StaticText(self, -1, _(u"3D Connectivity")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.conect3D_6, (2, 0), flag=wx.LEFT, border=9)
        sizer.Add(self.conect3D_18, (2, 1), flag=wx.LEFT, border=9)
        sizer.Add(self.conect3D_26, (2, 2), flag=wx.LEFT, border=9)
        try:
            sizer.Add(0, 0, (3, 0))
        except TypeError:
            sizer.AddStretchSpacer((3, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

    def GetConnSelected(self):
        if self.conect3D_6.GetValue():
            return 6
        elif self.conect3D_18.GetValue():
            return 18
        else:
            return 26


class PanelFFillThreshold(wx.Panel):
    def __init__(self, parent, config, ID=-1, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        import invesalius.project as prj

        project = prj.Project()
        bound_min, bound_max = project.threshold_range
        colour = [i*255 for i in const.MASK_COLOUR[0]]
        colour.append(100)

        self.threshold = grad.GradientCtrl(self, -1, int(bound_min),
                                             int(bound_max), self.config.t0,
                                             self.config.t1, colour)

        # sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(5)
        sizer.Add(self.threshold, 0, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.Bind(grad.EVT_THRESHOLD_CHANGING, self.OnSlideChanged, self.threshold)
        self.Bind(grad.EVT_THRESHOLD_CHANGED, self.OnSlideChanged, self.threshold)

    def OnSlideChanged(self, evt):
        self.config.t0 = int(self.threshold.GetMinValue())
        self.config.t1 = int(self.threshold.GetMaxValue())
        print(self.config.t0, self.config.t1)


class PanelFFillDynamic(wx.Panel):
    def __init__(self, parent, config, ID=-1, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        self.use_ww_wl = wx.CheckBox(self, -1,  _(u"Use WW&WL"))
        self.use_ww_wl.SetValue(self.config.use_ww_wl)

        self.deviation_min = wx.SpinCtrl(self, -1, value='%d' % self.config.dev_min, min=0, max=10000)
        w, h = self.deviation_min.GetTextExtent('M')
        self.deviation_min.SetMinSize((w*5, -1))

        self.deviation_max = wx.SpinCtrl(self, -1, value='%d' % self.config.dev_max, min=0, max=10000)
        self.deviation_max.SetMinSize((w*5, -1))

        sizer = wx.GridBagSizer(5, 5)

        try:
            sizer.Add(0, 0, (0, 0))
        except TypeError:
            sizer.AddStretchSpacer((0, 0))

        sizer.Add(self.use_ww_wl, (1, 0), (1, 6), flag=wx.LEFT, border=5)

        try:
            sizer.Add(0, 0, (2, 0))
        except TypeError:
            sizer.AddStretchSpacer((2, 0))

        sizer.Add(wx.StaticText(self, -1, _(u"Deviation")), (3, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.Add(wx.StaticText(self, -1, _(u"Min:")), (4, 0), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=9)
        sizer.Add(self.deviation_min, (4, 1))

        sizer.Add(wx.StaticText(self, -1, _(u"Max:")), (4, 2), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=9)
        sizer.Add(self.deviation_max, (4, 3))

        try:
            sizer.Add(0, 0, (5, 0))
        except TypeError:
            sizer.AddStretchSpacer((5, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.use_ww_wl.Bind(wx.EVT_CHECKBOX, self.OnSetUseWWWL)
        self.deviation_min.Bind(wx.EVT_SPINCTRL, self.OnSetDeviation)
        self.deviation_max.Bind(wx.EVT_SPINCTRL, self.OnSetDeviation)

    def OnSetUseWWWL(self, evt):
        self.config.use_ww_wl = self.use_ww_wl.GetValue()

    def OnSetDeviation(self, evt):
        self.config.dev_max = self.deviation_max.GetValue()
        self.config.dev_min = self.deviation_min.GetValue()


class PanelFFillConfidence(wx.Panel):
    def __init__(self, parent, config, ID=-1, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        self.use_ww_wl = wx.CheckBox(self, -1,  _(u"Use WW&WL"))
        self.use_ww_wl.SetValue(self.config.use_ww_wl)

        self.spin_mult = floatspin.FloatSpin(self, -1,
                                             value=self.config.confid_mult,
                                             min_val=1.0, max_val=10.0,
                                             increment=0.1, digits=1,
                                             style=wx.TE_PROCESS_TAB|wx.TE_PROCESS_ENTER,
                                             agwStyle=floatspin.FS_RIGHT)
        w, h = self.spin_mult.GetTextExtent('M')
        self.spin_mult.SetMinSize((w*7, -1))

        self.spin_iters = wx.SpinCtrl(self, -1, value='%d' % self.config.confid_iters, min=0, max=100)
        self.spin_iters.SetMinSize((w*7, -1))

        sizer = wx.GridBagSizer(5, 5)

        try:
            sizer.Add(0, 0, (0, 0))
        except TypeError:
            sizer.AddStretchSpacer((0, 0))

        sizer.Add(self.use_ww_wl, (1, 0), (1, 6), flag=wx.LEFT, border=5)

        try:
            sizer.Add(0, 0, (2, 0))
        except TypeError:
            sizer.AddStretchSpacer((2, 0))

        sizer.Add(wx.StaticText(self, -1, _(u"Multiplier")), (3, 0), (1, 3), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=5)
        sizer.Add(self.spin_mult, (3, 3), (1, 3))

        sizer.Add(wx.StaticText(self, -1, _(u"Iterations")), (4, 0), (1, 3), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=5)
        sizer.Add(self.spin_iters, (4, 3), (1, 2))

        try:
            sizer.Add(0, 0, (5, 0))
        except TypeError:
            sizer.AddStretchSpacer((5, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.use_ww_wl.Bind(wx.EVT_CHECKBOX, self.OnSetUseWWWL)
        self.spin_mult.Bind(wx.EVT_SPINCTRL, self.OnSetMult)
        self.spin_iters.Bind(wx.EVT_SPINCTRL, self.OnSetIters)

    def OnSetUseWWWL(self, evt):
        self.config.use_ww_wl = self.use_ww_wl.GetValue()

    def OnSetMult(self, evt):
        self.config.confid_mult = self.spin_mult.GetValue()

    def OnSetIters(self, evt):
        self.config.confid_iters = self.spin_iters.GetValue()


class FFillOptionsDialog(wx.Dialog):
    def __init__(self, title, config):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        """
        Create the widgets.
        """

        # Target
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.panel_target = PanelTargeFFill(self, style=border_style|wx.TAB_TRAVERSAL)
        self.panel2dcon = Panel2DConnectivity(self, style=border_style|wx.TAB_TRAVERSAL)
        self.panel3dcon = Panel3DConnectivity(self, style=border_style|wx.TAB_TRAVERSAL)

        if self.config.target == "2D":
            self.panel_target.target_2d.SetValue(1)
            self.panel2dcon.Enable(1)
            self.panel3dcon.Enable(0)
        else:
            self.panel_target.target_3d.SetValue(1)
            self.panel3dcon.Enable(1)
            self.panel2dcon.Enable(0)

        # Connectivity 2D
        if self.config.con_2d == 8:
            self.panel2dcon.conect2D_8.SetValue(1)
        else:
            self.panel2dcon.conect2D_4.SetValue(1)
            self.config.con_2d = 4

        # Connectivity 3D
        if self.config.con_3d == 18:
            self.panel3dcon.conect3D_18.SetValue(1)
        elif self.config.con_3d == 26:
            self.panel3dcon.conect3D_26.SetValue(1)
        else:
            self.panel3dcon.conect3D_6.SetValue(1)

        self.close_btn = wx.Button(self, wx.ID_CLOSE)

        # Sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(5)
        sizer.Add(wx.StaticText(self, -1, _(u"Parameters")), flag=wx.LEFT, border=5)
        sizer.AddSpacer(5)
        sizer.Add(self.panel_target, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel2dcon, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel3dcon, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.close_btn, 0, flag=wx.ALIGN_RIGHT|wx.RIGHT, border=7)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.close_btn.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnBtnClose(self, evt):
        self.Close()

    def OnSetRadio(self, evt):
        # Target
        if self.panel_target.target_2d.GetValue():
            self.config.target = "2D"
            self.panel2dcon.Enable(1)
            self.panel3dcon.Enable(0)
        else:
            self.config.target = "3D"
            self.panel3dcon.Enable(1)
            self.panel2dcon.Enable(0)

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

    def OnClose(self, evt):
        print("ONCLOSE")
        if self.config.dlg_visible:
            Publisher.sendMessage('Disable style', style=const.SLICE_STATE_MASK_FFILL)
        evt.Skip()
        self.Destroy()


class SelectPartsOptionsDialog(wx.Dialog):
    def __init__(self, config):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Select mask parts"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, _(u"Select mask parts"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.config = config

        self.SetReturnCode(wx.CANCEL)

        self._init_gui()

    def _init_gui(self):
        self.target_name = wx.TextCtrl(self, -1)
        self.target_name.SetValue(self.config.mask_name)

        # Connectivity 3D
        self.panel3dcon = Panel3DConnectivity(self)
        if self.config.con_3d == 18:
            self.panel3dcon.conect3D_18.SetValue(1)
        elif self.config.con_3d == 26:
            self.panel3dcon.conect3D_26.SetValue(1)
        else:
            self.panel3dcon.conect3D_6.SetValue(1)

        self.btn_ok = wx.Button(self, wx.ID_OK)
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL)

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(5)
        sizer.Add(wx.StaticText(self, -1, _(u"Target mask name")), flag=wx.LEFT, border=5)
        sizer.AddSpacer(5)
        sizer.Add(self.target_name, flag=wx.LEFT|wx.EXPAND|wx.RIGHT, border=9)
        sizer.AddSpacer(5)
        sizer.Add(self.panel3dcon, flag=wx.LEFT|wx.RIGHT|wx.EXPAND)
        sizer.AddSpacer(5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self.btn_ok, 0, flag=wx.ALIGN_RIGHT, border=5)
        btn_sizer.Add(self.btn_cancel, 0, flag=wx.LEFT|wx.ALIGN_RIGHT, border=5)

        sizer.Add(btn_sizer, 0, flag=wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT, border=5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

        self.target_name.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnOk(self, evt):
        self.SetReturnCode(wx.OK)
        self.Close()

    def OnCancel(self, evt):
        self.SetReturnCode(wx.CANCEL)
        self.Close()

    def OnChar(self, evt):
        evt.Skip()
        self.config.mask_name = self.target_name.GetValue()

    def OnSetRadio(self, evt):
        if self.panel3dcon.conect3D_6.GetValue():
            self.config.con_3d = 6
        elif self.panel3dcon.conect3D_18.GetValue():
            self.config.con_3d = 18
        elif self.panel3dcon.conect3D_26.GetValue():
            self.config.con_3d = 26

    def OnClose(self, evt):
        if self.config.dlg_visible:
            Publisher.sendMessage('Disable style', style=const.SLICE_STATE_SELECT_MASK_PARTS)
        evt.Skip()
        self.Destroy()

class FFillSegmentationOptionsDialog(wx.Dialog):
    def __init__(self, config, ID=-1, title=_(u"Region growing"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), ID, title=title, style=style)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        """
        Create the widgets.
        """
        import invesalius.project as prj

        # Target
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.panel_target = PanelTargeFFill(self, style=border_style|wx.TAB_TRAVERSAL)
        self.panel2dcon = Panel2DConnectivity(self, style=border_style|wx.TAB_TRAVERSAL)
        self.panel3dcon = Panel3DConnectivity(self, style=border_style|wx.TAB_TRAVERSAL)

        if self.config.target == "2D":
            self.panel_target.target_2d.SetValue(1)
            self.panel2dcon.Enable(1)
            self.panel3dcon.Enable(0)
        else:
            self.panel_target.target_3d.SetValue(1)
            self.panel3dcon.Enable(1)
            self.panel2dcon.Enable(0)

        # Connectivity 2D
        if self.config.con_2d == 8:
            self.panel2dcon.conect2D_8.SetValue(1)
        else:
            self.panel2dcon.conect2D_4.SetValue(1)
            self.config.con_2d = 4

        # Connectivity 3D
        if self.config.con_3d == 18:
            self.panel3dcon.conect3D_18.SetValue(1)
        elif self.config.con_3d == 26:
            self.panel3dcon.conect3D_26.SetValue(1)
        else:
            self.panel3dcon.conect3D_6.SetValue(1)

        self.cmb_method = wx.ComboBox(self, -1, choices=(_(u"Dynamic"), _(u"Threshold"), _(u"Confidence")), style=wx.CB_READONLY)

        if self.config.method == 'dynamic':
            self.cmb_method.SetSelection(0)
        elif self.config.method == 'threshold':
            self.cmb_method.SetSelection(1)
        elif self.config.method == 'confidence':
            self.cmb_method.SetSelection(2)

        self.panel_ffill_threshold = PanelFFillThreshold(self, self.config, -1, style=border_style|wx.TAB_TRAVERSAL)
        self.panel_ffill_threshold.SetMinSize((250, -1))
        self.panel_ffill_threshold.Hide()

        self.panel_ffill_dynamic = PanelFFillDynamic(self, self.config, -1, style=border_style|wx.TAB_TRAVERSAL)
        self.panel_ffill_dynamic.SetMinSize((250, -1))
        self.panel_ffill_dynamic.Hide()

        self.panel_ffill_confidence = PanelFFillConfidence(self, self.config, -1, style=border_style|wx.TAB_TRAVERSAL)
        self.panel_ffill_confidence.SetMinSize((250, -1))
        self.panel_ffill_confidence.Hide()

        self.close_btn = wx.Button(self, wx.ID_CLOSE)

        # Sizer
        sizer = wx.GridBagSizer(2, 2)

        try:
            sizer.Add(0, 0, (0, 0))
        except TypeError:
            sizer.AddStretchSpacer((0, 0))
        sizer.Add(wx.StaticText(self, -1, _(u"Parameters")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        try:
            sizer.Add(0, 0, (2, 0))
        except TypeError:
            sizer.AddStretchSpacer((2, 0))
        sizer.Add(self.panel_target, (3, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        try:
            sizer.Add(0, 0, (4, 0))
        except TypeError:
            sizer.AddStretchSpacer((4, 0))
        sizer.Add(self.panel2dcon, (5, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        try:
            sizer.Add(0, 0, (6, 0))
        except TypeError:
            sizer.AddStretchSpacer((6, 0))
        sizer.Add(self.panel3dcon, (7, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        try:
            sizer.Add(0, 0, (8, 0))
        except TypeError:
            sizer.AddStretchSpacer((8, 0))

        sizer.Add(wx.StaticText(self, -1, _(u"Method")), (9, 0), (1, 1), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=7)
        sizer.Add(self.cmb_method, (9, 1), (1, 5), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)

        try:
            sizer.Add(0, 0, (10, 0))
        except TypeError:
            sizer.AddStretchSpacer((10, 0))

        if self.config.method == 'dynamic':
            self.cmb_method.SetSelection(0)
            self.panel_ffill_dynamic.Show()
            sizer.Add(self.panel_ffill_dynamic, (11, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        elif self.config.method == 'confidence':
            self.cmb_method.SetSelection(2)
            self.panel_ffill_confidence.Show()
            sizer.Add(self.panel_ffill_confidence, (11, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        else:
            self.cmb_method.SetSelection(1)
            self.panel_ffill_threshold.Show()
            sizer.Add(self.panel_ffill_threshold, (11, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
            self.config.method = 'threshold'

        try:
            sizer.Add(0, 0, (12, 0))
        except TypeError:
            sizer.AddStretchSpacer((12, 0))
        sizer.Add(self.close_btn, (13, 0), (1, 6), flag=wx.ALIGN_RIGHT|wx.RIGHT, border=5)
        try:
            sizer.Add(0, 0, (14, 0))
        except TypeError:
            sizer.AddStretchSpacer((14, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)
        self.cmb_method.Bind(wx.EVT_COMBOBOX, self.OnSetMethod)
        self.close_btn.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnSetRadio(self, evt):
        # Target
        if self.panel_target.target_2d.GetValue():
            self.config.target = "2D"
            self.panel2dcon.Enable(1)
            self.panel3dcon.Enable(0)
        else:
            self.config.target = "3D"
            self.panel3dcon.Enable(1)
            self.panel2dcon.Enable(0)

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

    def OnSetMethod(self, evt):
        item_panel = self.GetSizer().FindItemAtPosition((11, 0)).GetWindow()

        if self.cmb_method.GetSelection() == 0:
            self.config.method = 'dynamic'
            item_panel.Hide()
            self.panel_ffill_dynamic.Show()
            self.GetSizer().Replace(item_panel, self.panel_ffill_dynamic)

        elif self.cmb_method.GetSelection() == 2:
            self.config.method = 'confidence'
            item_panel.Hide()
            self.panel_ffill_confidence.Show()
            self.GetSizer().Replace(item_panel, self.panel_ffill_confidence)

        else:
            self.config.method = 'threshold'
            item_panel.Hide()
            self.panel_ffill_threshold.Show()
            self.GetSizer().Replace(item_panel, self.panel_ffill_threshold)

        self.GetSizer().Fit(self)
        self.Layout()

    def OnBtnClose(self, evt):
        self.Close()

    def OnClose(self, evt):
        if self.config.dlg_visible:
            Publisher.sendMessage('Disable style', style=const.SLICE_STATE_MASK_FFILL)
        evt.Skip()
        self.Destroy()


class CropOptionsDialog(wx.Dialog):
    
    def __init__(self, config, ID=-1, title=_(u"Crop mask"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP):
        self.config = config
        try:
            pre = wx.PreDialog()

            pre.Create(wx.GetApp().GetTopWindow(), ID, title=title, style=style)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), ID, title=title, style=style)


        self._init_gui()

    def UpdateValues(self, limits):
        xi, xf, yi, yf, zi, zf = limits

        self.tx_axial_i.SetValue(str(zi))
        self.tx_axial_f.SetValue(str(zf))

        self.tx_sagital_i.SetValue(str(xi))
        self.tx_sagital_f.SetValue(str(xf))

        self.tx_coronal_i.SetValue(str(yi))
        self.tx_coronal_f.SetValue(str(yf))

    def _init_gui(self):
        p = wx.Panel(self, -1, style = wx.TAB_TRAVERSAL
                     | wx.CLIP_CHILDREN
                     | wx.FULL_REPAINT_ON_RESIZE)

        gbs_principal = self.gbs = wx.GridBagSizer(4,1)

        gbs = self.gbs = wx.GridBagSizer(3, 4)

        flag_labels = wx.ALIGN_RIGHT  | wx.ALIGN_CENTER_VERTICAL

        txt_style = wx.TE_READONLY

        stx_axial = wx.StaticText(p, -1, _(u"Axial:"))
        self.tx_axial_i = tx_axial_i = wx.TextCtrl(p, -1, "", size=wx.Size(50,-1), style=txt_style)
        stx_axial_t = wx.StaticText(p, -1, _(u" - "))
        self.tx_axial_f = tx_axial_f = wx.TextCtrl(p, -1, "", size=wx.Size(50,-1), style=txt_style)

        gbs.Add(stx_axial, (0,0), flag=flag_labels)
        gbs.Add(tx_axial_i, (0,1))
        gbs.Add(stx_axial_t, (0,2), flag=flag_labels)
        gbs.Add(tx_axial_f, (0,3))

        stx_sagital = wx.StaticText(p, -1, _(u"Sagital:"))
        self.tx_sagital_i = tx_sagital_i = wx.TextCtrl(p, -1, "", size=wx.Size(50,-1), style=txt_style)
        stx_sagital_t = wx.StaticText(p, -1, _(u" - "))
        self.tx_sagital_f = tx_sagital_f = wx.TextCtrl(p, -1, "", size=wx.Size(50,-1), style=txt_style)

        gbs.Add(stx_sagital, (1,0), flag=flag_labels)
        gbs.Add(tx_sagital_i, (1,1))
        gbs.Add(stx_sagital_t, (1,2), flag=flag_labels)
        gbs.Add(tx_sagital_f, (1,3))

        stx_coronal = wx.StaticText(p, -1, _(u"Coronal:"))
        self.tx_coronal_i = tx_coronal_i = wx.TextCtrl(p, -1, "", size=wx.Size(50,-1), style=txt_style)
        stx_coronal_t = wx.StaticText(p, -1, _(u" - "))
        self.tx_coronal_f = tx_coronal_f = wx.TextCtrl(p, -1, "", size=wx.Size(50,-1), style=txt_style)

        gbs.Add(stx_coronal, (2,0), flag=flag_labels)
        gbs.Add(tx_coronal_i, (2,1))
        gbs.Add(stx_coronal_t, (2,2), flag=flag_labels)
        gbs.Add(tx_coronal_f, (2,3))

        gbs_button = wx.GridBagSizer(2, 4)

        btn_ok = self.btn_ok= wx.Button(p, wx.ID_OK)
        btn_ok.SetDefault()

        btn_cancel = wx.Button(p, wx.ID_CANCEL)

        gbs_button.Add(btn_cancel, (0,0))
        gbs_button.Add(btn_ok, (0,1))

        gbs_principal.Add(gbs, (0,0), flag = wx.ALL|wx.EXPAND)
        try:
            gbs_principal.Add(0, 0, (1, 0))
            gbs_principal.Add(0, 0, (2, 0))
        except TypeError:
            gbs_principal.AddStretchSpacer((1, 0))
            gbs_principal.AddStretchSpacer((2, 0))
        gbs_principal.Add(gbs_button, (3,0), flag = wx.ALIGN_RIGHT)

        box = wx.BoxSizer()
        box.Add(gbs_principal, 1, wx.ALL|wx.EXPAND, 10)

        p.SetSizer(box)
        box.Fit(p)
        p.Layout()

        sizer = wx.BoxSizer()
        sizer.Add(p, 1, wx.EXPAND)
        sizer.Fit(self)
        self.Layout()

        Publisher.subscribe(self.UpdateValues, 'Update crop limits into gui')

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        btn_cancel.Bind(wx.EVT_BUTTON, self.OnClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)


    def OnOk(self, evt):
        self.config.dlg_visible = False
        Publisher.sendMessage('Crop mask')
        Publisher.sendMessage('Disable style', style=const.SLICE_STATE_CROP_MASK)
        evt.Skip()

    def OnClose(self, evt):
        self.config.dlg_visible = False
        Publisher.sendMessage('Disable style', style=const.SLICE_STATE_CROP_MASK)
        evt.Skip()
        self.Destroy()


class FillHolesAutoDialog(wx.Dialog):
    def __init__(self, title):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self._init_gui()

    def _init_gui(self):
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.spin_size = wx.SpinCtrl(self, -1, value='1000', min=1, max=1000000000)
        self.panel_target = PanelTargeFFill(self, style=border_style|wx.TAB_TRAVERSAL)
        self.panel2dcon = Panel2DConnectivity(self, show_orientation=True, style=border_style|wx.TAB_TRAVERSAL)
        self.panel3dcon = Panel3DConnectivity(self, style=border_style|wx.TAB_TRAVERSAL)

        self.panel2dcon.Enable(1)
        self.panel3dcon.Enable(0)

        self.panel_target.target_2d.SetValue(1)
        self.panel2dcon.conect2D_4.SetValue(1)
        self.panel3dcon.conect3D_6.SetValue(1)

        self.apply_btn = wx.Button(self, wx.ID_APPLY)
        self.close_btn = wx.Button(self, wx.ID_CLOSE)

        # Sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(5)
        sizer.Add(wx.StaticText(self, -1, _(u"Parameters")), flag=wx.LEFT, border=5)
        sizer.AddSpacer(5)

        sizer.Add(self.panel_target, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel2dcon, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)
        sizer.Add(self.panel3dcon, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)

        spin_sizer = wx.BoxSizer(wx.HORIZONTAL)
        spin_sizer.Add(wx.StaticText(self, -1, _(u"Max hole size")), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=5)
        spin_sizer.Add(self.spin_size, 0, flag=wx.LEFT|wx.RIGHT, border=5)
        spin_sizer.Add(wx.StaticText(self, -1, _(u"voxels")), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=5)

        sizer.Add(spin_sizer, 0, flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddSpacer(5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self.apply_btn, 0, flag=wx.ALIGN_RIGHT, border=5)
        btn_sizer.Add(self.close_btn, 0, flag=wx.LEFT|wx.ALIGN_RIGHT, border=5)

        sizer.Add(btn_sizer, 0, flag=wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT, border=5)

        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.apply_btn.Bind(wx.EVT_BUTTON, self.OnApply)
        self.close_btn.Bind(wx.EVT_BUTTON, self.OnBtnClose)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnSetRadio)

    def OnApply(self, evt):
        if self.panel_target.target_2d.GetValue():
            target = "2D"
            conn = self.panel2dcon.GetConnSelected()
            orientation = self.panel2dcon.GetOrientation()
        else:
            target = "3D"
            conn = self.panel3dcon.GetConnSelected()
            orientation = 'VOLUME'

        parameters = {
            'target': target,
            'conn': conn,
            'orientation': orientation,
            'size': self.spin_size.GetValue(),
        }

        Publisher.sendMessage("Fill holes automatically", parameters=parameters)


    def OnBtnClose(self, evt):
        self.Close()
        self.Destroy()

    def OnSetRadio(self, evt):
        # Target
        if self.panel_target.target_2d.GetValue():
            self.panel2dcon.Enable(1)
            self.panel3dcon.Enable(0)
        else:
            self.panel3dcon.Enable(1)
            self.panel2dcon.Enable(0)


class MaskDensityDialog(wx.Dialog):
    def __init__(self, title):
        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Mask density"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, _(u"Mask density"),
                               style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT)

        self._init_gui()
        self._bind_events()

    def _init_gui(self):
        import invesalius.project as prj
        project = prj.Project()

        self.cmb_mask = wx.ComboBox(self, -1, choices=[], style=wx.CB_READONLY)
        if project.mask_dict.values():
            for mask in project.mask_dict.values():
                self.cmb_mask.Append(mask.name, mask)
            self.cmb_mask.SetValue(list(project.mask_dict.values())[0].name)

        self.calc_button = wx.Button(self, -1, _(u'Calculate'))

        self.mean_density = self._create_selectable_label_text('')
        self.min_density = self._create_selectable_label_text('')
        self.max_density = self._create_selectable_label_text('')
        self.std_density = self._create_selectable_label_text('')


        slt_mask_sizer = wx.FlexGridSizer(rows=1, cols=3, vgap=5, hgap=5)
        slt_mask_sizer.AddMany([
            (wx.StaticText(self, -1, _(u'Mask:'), style=wx.ALIGN_CENTER_VERTICAL),  0, wx.ALIGN_CENTRE),
            (self.cmb_mask, 1, wx.EXPAND),
            (self.calc_button, 0, wx.EXPAND),
        ])

        values_sizer = wx.FlexGridSizer(rows=4, cols=2, vgap=5, hgap=5)
        values_sizer.AddMany([
            (wx.StaticText(self, -1, _(u'Mean:')),  0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT),
            (self.mean_density, 1, wx.EXPAND),

            (wx.StaticText(self, -1, _(u'Minimun:')),  0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT),
            (self.min_density, 1, wx.EXPAND),

            (wx.StaticText(self, -1, _(u'Maximun:')),  0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT),
            (self.max_density, 1, wx.EXPAND),

            (wx.StaticText(self, -1, _(u'Standard deviation:')),  0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT),
            (self.std_density, 1, wx.EXPAND),
        ])

        sizer = wx.FlexGridSizer(rows=4, cols=1, vgap=5, hgap=5)
        sizer.AddSpacer(5)
        sizer.AddMany([
            (slt_mask_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5) ,
            (values_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5),
        ])
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.CenterOnScreen()

    def _create_selectable_label_text(self, text):
        label = wx.TextCtrl(self, -1, style=wx.TE_READONLY)
        label.SetValue(text)
        #  label.SetBackgroundColour(self.GetBackgroundColour())
        return label

    def _bind_events(self):
        self.calc_button.Bind(wx.EVT_BUTTON, self.OnCalcButton)

    def OnCalcButton(self, evt):
        from invesalius.data.slice_ import Slice
        mask = self.cmb_mask.GetClientData(self.cmb_mask.GetSelection())

        slc = Slice()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(slc.calc_image_density, mask)
            for c in itertools.cycle(['', '.', '..', '...']):
                s = _(u'Calculating ') + c
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

    def __init__(self, nav_prop):

        self.tracker_id = nav_prop[0]
        self.trk_init = nav_prop[1]
        self.obj_ref_id = 0
        self.obj_name = None

        self.obj_fiducials = np.full([5, 3], np.nan)
        self.obj_orients = np.full([5, 3], np.nan)

        try:
            pre = wx.PreDialog()
            pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Object calibration"), size=(450, 440),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
            self.PostCreate(pre)
        except AttributeError:
            wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, _(u"Object calibration"), size=(450, 440),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self._init_gui()
        self.LoadObject()

    def _init_gui(self):
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        self.interactor.Enable(1)
        self.ren = vtk.vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)

        # Initialize list of buttons and txtctrls for wx objects
        self.btns_coord = [None] * 5
        self.text_actors = [None] * 5
        self.ball_actors = [None] * 5
        self.txt_coord = [list(), list(), list(), list(), list()]

        # ComboBox for tracker reference mode
        tooltip = wx.ToolTip(_(u"Choose the object reference mode"))
        choice_ref = wx.ComboBox(self, -1, "", size=wx.Size(90, 23),
                                 choices=const.REF_MODE, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        choice_ref.SetSelection(self.obj_ref_id)
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(wx.EVT_COMBOBOX, self.OnChoiceRefMode)
        choice_ref.Enable(0)
        if self.tracker_id == const.MTC or self.tracker_id == const.FASTRAK or self.tracker_id == const.DEBUGTRACK:
            choice_ref.Enable(1)

        # ComboBox for sensor selection for FASTRAK
        tooltip = wx.ToolTip(_(u"Choose the FASTRAK sensor port"))
        choice_sensor = wx.ComboBox(self, -1, "", size=wx.Size(90, 23),
                                 choices=const.FT_SENSOR_MODE, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        choice_sensor.SetSelection(0)
        choice_sensor.SetToolTip(tooltip)
        choice_sensor.Bind(wx.EVT_COMBOBOX, self.OnChoiceFTSensor)
        choice_sensor.Show(False)
        self.choice_sensor = choice_sensor

        # Buttons to finish or cancel object registration
        tooltip = wx.ToolTip(_(u"Registration done"))
        # btn_ok = wx.Button(self, -1, _(u"Done"), size=wx.Size(90, 30))
        btn_ok = wx.Button(self, wx.ID_OK, _(u"Done"), size=wx.Size(90, 30))
        btn_ok.SetToolTip(tooltip)

        extra_sizer = wx.FlexGridSizer(rows=3, cols=1, hgap=5, vgap=30)
        extra_sizer.AddMany([choice_ref,
                             btn_ok,
                             choice_sensor])

        # Push buttons for object fiducials
        btns_obj = const.BTNS_OBJ
        tips_obj = const.TIPS_OBJ

        for k in btns_obj:
            n = list(btns_obj[k].keys())[0]
            lab = list(btns_obj[k].values())[0]
            self.btns_coord[n] = wx.Button(self, k, label=lab, size=wx.Size(60, 23))
            self.btns_coord[n].SetToolTip(wx.ToolTip(tips_obj[n]))
            self.btns_coord[n].Bind(wx.EVT_BUTTON, self.OnGetObjectFiducials)

        for m in range(0, 5):
            for n in range(0, 3):
                self.txt_coord[m].append(wx.StaticText(self, -1, label='-',
                                                       style=wx.ALIGN_RIGHT, size=wx.Size(40, 23)))

        coord_sizer = wx.GridBagSizer(hgap=20, vgap=5)

        for m in range(0, 5):
            coord_sizer.Add(self.btns_coord[m], pos=wx.GBPosition(m, 0))
            for n in range(0, 3):
                coord_sizer.Add(self.txt_coord[m][n], pos=wx.GBPosition(m, n + 1), flag=wx.TOP, border=5)

        group_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=50, vgap=5)
        group_sizer.AddMany([(coord_sizer, 0, wx.LEFT, 20),
                             (extra_sizer, 0, wx.LEFT, 10)])

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.interactor, 0, wx.EXPAND)
        main_sizer.Add(group_sizer, 0,
                       wx.EXPAND|wx.GROW|wx.LEFT|wx.TOP|wx.RIGHT|wx.BOTTOM|wx.ALIGN_CENTER_HORIZONTAL, 10)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

    def ObjectImportDialog(self):
        msg = _("Would like to use InVesalius default object?")
        if sys.platform == 'darwin':
            dlg = wx.MessageDialog(None, "", msg,
                                   wx.ICON_QUESTION | wx.YES_NO)
        else:
            dlg = wx.MessageDialog(None, msg,
                                   "InVesalius 3",
                                   wx.ICON_QUESTION | wx.YES_NO)
        answer = dlg.ShowModal()
        dlg.Destroy()

        if answer == wx.ID_YES:
            return 1
        else:  # answer == wx.ID_NO:
            return 0

    def LoadObject(self):
        default = self.ObjectImportDialog()
        if not default:
            filename = ShowImportMeshFilesDialog()

            if filename:
                if filename.lower().endswith('.stl'):
                    reader = vtk.vtkSTLReader()
                elif filename.lower().endswith('.ply'):
                    reader = vtk.vtkPLYReader()
                elif filename.lower().endswith('.obj'):
                    reader = vtk.vtkOBJReader()
                elif filename.lower().endswith('.vtp'):
                    reader = vtk.vtkXMLPolyDataReader()
                else:
                    wx.MessageBox(_("File format not reconized by InVesalius"), _("Import surface error"))
                    return
            else:
                filename = os.path.join(const.OBJ_DIR, "magstim_fig8_coil.stl")
                reader = vtk.vtkSTLReader()
        else:
            filename = os.path.join(const.OBJ_DIR, "magstim_fig8_coil.stl")
            reader = vtk.vtkSTLReader()

        if _has_win32api:
            self.obj_name = win32api.GetShortPathName(filename).encode(const.FS_ENCODE)
        else:
            self.obj_name = filename.encode(const.FS_ENCODE)

        reader.SetFileName(self.obj_name)
        reader.Update()
        polydata = reader.GetOutput()

        if polydata.GetNumberOfPoints() == 0:
            wx.MessageBox(_("InVesalius was not able to import this surface"), _("Import surface error"))

        transform = vtk.vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtk.vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(polydata)
        transform_filt.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        mapper.ScalarVisibilityOff()
        mapper.ImmediateModeRenderingOn()

        obj_actor = vtk.vtkActor()
        obj_actor.SetMapper(mapper)

        self.ball_actors[0], self.text_actors[0] = self.OnCreateObjectText('Left', (0,55,0))
        self.ball_actors[1], self.text_actors[1] = self.OnCreateObjectText('Right', (0,-55,0))
        self.ball_actors[2], self.text_actors[2] = self.OnCreateObjectText('Anterior', (23,0,0))

        self.ren.AddActor(obj_actor)
        self.ren.ResetCamera()

        self.interactor.Render()

    def OnCreateObjectText(self, name, coord):
        ball_source = vtk.vtkSphereSource()
        ball_source.SetRadius(3)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_source.GetOutputPort())
        ball_actor = vtk.vtkActor()
        ball_actor.SetMapper(mapper)
        ball_actor.SetPosition(coord)
        ball_actor.GetProperty().SetColor(1, 0, 0)

        textSource = vtk.vtkVectorText()
        textSource.SetText(name)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(textSource.GetOutputPort())
        tactor = vtk.vtkFollower()
        tactor.SetMapper(mapper)
        tactor.GetProperty().SetColor(1.0, 0.0, 0.0)
        tactor.SetScale(5)
        ball_position = ball_actor.GetPosition()
        tactor.SetPosition(ball_position[0]+5, ball_position[1]+5, ball_position[2]+10)
        self.ren.AddActor(tactor)
        tactor.SetCamera(self.ren.GetActiveCamera())
        self.ren.AddActor(ball_actor)
        return ball_actor, tactor

    def OnGetObjectFiducials(self, evt):
        btn_id = list(const.BTNS_OBJ[evt.GetId()].keys())[0]

        if self.trk_init and self.tracker_id:
            coord_raw = dco.GetCoordinates(self.trk_init, self.tracker_id, self.obj_ref_id)
            if self.obj_ref_id and btn_id == 4:
                coord = coord_raw[self.obj_ref_id, :]
            else:
                coord = coord_raw[0, :]
        else:
            NavigationTrackerWarning(0, 'choose')

        # Update text controls with tracker coordinates
        if coord is not None or np.sum(coord) != 0.0:
            self.obj_fiducials[btn_id, :] = coord[:3]
            self.obj_orients[btn_id, :] = coord[3:]
            for n in [0, 1, 2]:
                self.txt_coord[btn_id][n].SetLabel(str(round(coord[n], 1)))
                if self.text_actors[btn_id]:
                    self.text_actors[btn_id].GetProperty().SetColor(0.0, 1.0, 0.0)
                    self.ball_actors[btn_id].GetProperty().SetColor(0.0, 1.0, 0.0)
            self.Refresh()
        else:
            NavigationTrackerWarning(0, 'choose')

    def OnChoiceRefMode(self, evt):
        # When ref mode is changed the tracker coordinates are set to nan
        # This is for Polhemus FASTRAK wrapper, where the sensor attached to the object can be the stylus (Static
        # reference - Selection 0 - index 0 for coordinates) or can be a 3rd sensor (Dynamic reference - Selection 1 -
        # index 2 for coordinates)
        # I use the index 2 directly here to send to the coregistration module where it is possible to access without
        # any conditional statement the correct index of coordinates.

        if evt.GetSelection():
            self.obj_ref_id = 2
            if self.tracker_id == const.FASTRAK or self.tracker_id == const.DEBUGTRACK:
                self.choice_sensor.Show(True)
                self.Layout()
        else:
            self.obj_ref_id = 0
        for m in range(0, 5):
            self.obj_fiducials[m, :] = np.full([1, 3], np.nan)
            self.obj_orients[m, :] = np.full([1, 3], np.nan)
            for n in range(0, 3):
                self.txt_coord[m][n].SetLabel('-')

    def OnChoiceFTSensor(self, evt):
        if evt.GetSelection():
            self.obj_ref_id = 3
        else:
            self.obj_ref_id = 0

    def GetValue(self):
        return self.obj_fiducials, self.obj_orients, self.obj_ref_id, self.obj_name


class SurfaceProgressWindow(object):
    def __init__(self):
        self.title = "InVesalius 3"
        self.msg = _("Creating 3D surface ...")
        self.style = wx.PD_APP_MODAL | wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME
        self.dlg = wx.ProgressDialog(self.title,
                                     self.msg,
                                     parent=None,
                                     style=self.style)
        self.running = True
        self.error = None
        self.dlg.Show()

    def WasCancelled(self):
        #  print("Cancelled?", self.dlg.WasCancelled())
        return self.dlg.WasCancelled()

    def Update(self, msg=None, value=None):
        if msg is None:
            self.dlg.Pulse()
        else:
            self.dlg.Pulse(msg)

    def Close(self):
        self.dlg.Destroy()


class GoToDialog(wx.Dialog):
    def __init__(self, title=_("Go to slice ..."), init_orientation=const.AXIAL_STR):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
        self._init_gui(init_orientation)

    def _init_gui(self, init_orientation):
        orientations = (
            (_("Axial"), const.AXIAL_STR),
            (_("Coronal"), const.CORONAL_STR),
            (_("Sagital"), const.SAGITAL_STR),
        )
        self.goto_slice = wx.TextCtrl(self, -1, "")
        self.goto_orientation = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN|wx.CB_READONLY)
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
        slice_sizer.Add(wx.StaticText(self, -1, _("Slice number"), style=wx.ALIGN_CENTER), 0, wx.ALIGN_CENTER|wx.RIGHT, 5)
        slice_sizer.Add(self.goto_slice, 1, wx.EXPAND)

        main_sizer.Add((5, 5))
        main_sizer.Add(slice_sizer, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(self.goto_orientation, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def OnOk(self, evt):
        try:
            slice_number = int(self.goto_slice.GetValue())
            orientation = self.goto_orientation.GetClientData(self.goto_orientation.GetSelection())
            Publisher.sendMessage(("Set scroll position", orientation), index=slice_number)
        except ValueError:
            pass
        self.Close()

    def Close(self):
        wx.Dialog.Close(self)
        self.Destroy()
