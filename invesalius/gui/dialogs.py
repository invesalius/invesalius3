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
from functools import partial

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
from invesalius.pubsub import pub as Publisher

try:
    from wx.adv import AboutDialogInfo, AboutBox
except ImportError:
    from wx import AboutDialogInfo, AboutBox

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.gui.widgets.gradient as grad
import invesalius.session as ses
import invesalius.utils as utils
import invesalius.data.vtk_utils as vtku
import invesalius.data.coregistration as dcr
from invesalius.gui.widgets.inv_spinctrl import InvSpinCtrl, InvFloatSpinCtrl
from invesalius.gui.widgets import clut_imagedata
from invesalius.gui.widgets.clut_imagedata import CLUTImageDataWidget, EVT_CLUT_NODE_CHANGED
import numpy as np
from numpy.core.umath_tests import inner1d

from invesalius import inv_paths

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

        num_ctrl_percent = InvSpinCtrl(self, -1, value=100, min_value=20, max_value=100)
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
    def __init__(self, parent, maximum, abort=False):
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
                                     parent = parent,
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

WILDCARD_NIFTI = "NIfTI 1 (*.nii;*.nii.gz;*.hdr)|*.nii;*.nii.gz;*.hdr|" \
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


def ShowImportOtherFilesDialog(id_type, msg='Import NIFTi 1 file'):
    # Default system path
    session = ses.Session()
    last_directory = session.get('paths', 'last_directory_%d' % id_type, '')
    dlg = wx.FileDialog(None, message=msg, defaultDir=last_directory,
                        defaultFile="", wildcard=WILDCARD_NIFTI,
                        style=wx.FD_OPEN | wx.FD_CHANGE_DIR)

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


def ShowLoadSaveDialog(message=_(u"Load File"), current_dir=os.path.abspath("."), style=wx.FD_OPEN | wx.FD_CHANGE_DIR,
                       wildcard=_("Registration files (*.obr)|*.obr"), default_filename="", save_ext=None):

    dlg = wx.FileDialog(None, message=message, defaultDir="", defaultFile=default_filename,
                        wildcard=wildcard, style=style)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    try:
        if dlg.ShowModal() == wx.ID_OK:
            # This returns a Python list of files that were selected.
            filepath = dlg.GetPath()
            ok_press = 1
        else:
            ok_press = 0
    except(wx._core.PyAssertionError):  # FIX: win64
        filepath = dlg.GetPath()
        ok_press = 1

    # fix the extension if set different than expected
    if save_ext and ok_press:
        extension = save_ext
        if sys.platform != 'win32':
            if filepath.split(".")[-1] != extension:
                filepath = filepath + "." + extension

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)

    return filepath


class MessageDialog(wx.Dialog):
    def __init__(self, message):
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


class MessageBox(wx.Dialog):
    def __init__(self, parent, title, message, caption="InVesalius3 Error"):
        wx.Dialog.__init__(self, parent, title=caption, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)

        title_label = wx.StaticText(self, -1, title)

        text = wx.TextCtrl(self, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.BORDER_NONE)
        text.SetValue(message)
        text.SetBackgroundColour(wx.SystemSettings.GetColour(4))

        width, height = text.GetTextExtent("O"*30)
        text.SetMinSize((width, -1))

        btn_ok = wx.Button(self, wx.ID_OK)
        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(btn_ok)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_label, 0, wx.ALL | wx.EXPAND, 5)
        sizer.Add(text, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.ALL, 5)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Center()
        self.ShowModal()


class ErrorMessageBox(wx.Dialog):
    def __init__(self, parent, title, message, caption="InVesalius3 Error"):
        wx.Dialog.__init__(self, parent, title=caption, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)

        title_label = wx.StaticText(self, -1, title)
        title_width, title_height = title_label.GetSize()

        icon = wx.ArtProvider.GetBitmap(wx.ART_ERROR, wx.ART_MESSAGE_BOX, (title_height * 2, title_height * 2))
        bmp = wx.StaticBitmap(self, -1, icon)

        text = wx.TextCtrl(self, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.BORDER_NONE)
        text.SetValue(message)
        text.SetBackgroundColour(wx.SystemSettings.GetColour(4))

        width, height = text.GetTextExtent("M"*60)
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
# ----------------------------------

def ShowNavigationTrackerWarning(trck_id, lib_mode):
    """
    Spatial Tracker connection error
    """
    trck = {const.SELECT: 'Tracker',
            const.MTC: 'Claron MicronTracker',
            const.FASTRAK: 'Polhemus FASTRAK',
            const.ISOTRAKII: 'Polhemus ISOTRAK',
            const.PATRIOT: 'Polhemus PATRIOT',
            const.CAMERA: 'CAMERA',
            const.POLARIS: 'NDI Polaris',
            const.POLARISP4: 'NDI Polaris P4',
            const.OPTITRACK: 'Optitrack',
            const.DEBUGTRACKRANDOM: 'Debug tracker device (random)',
            const.DEBUGTRACKAPPROACH: 'Debug tracker device (approach)'}

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

def ICPcorregistration(fre):
    msg = _("The fiducial registration error is: ") + str(round(fre, 2)) + '\n\n' + \
          _("Would you like to improve accuracy?")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.YES_NO)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                               wx.YES_NO)

    if dlg.ShowModal() == wx.ID_YES:
        flag = True
    else:
        flag = False

    dlg.Destroy()
    return flag

def ReportICPerror(prev_error, final_error):
    msg = _("Error after refine: ") + str(round(final_error, 2)) + ' mm' + '\n\n' + \
          _("Previous error: ") + str(round(prev_error, 2)) + ' mm'
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                               wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def ShowEnterMarkerID(default):
    msg = _("Edit marker ID")
    if sys.platform == 'darwin':
        dlg = wx.TextEntryDialog(None, "", msg, defaultValue=default)
    else:
        dlg = wx.TextEntryDialog(None, msg, "InVesalius 3", value=default)
    dlg.ShowModal()
    result = dlg.GetValue()
    dlg.Destroy()
    return result


def ShowConfirmationDialog(msg=_('Proceed?')):
    # msg = _("Do you want to delete all markers?")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.OK | wx.CANCEL | wx.ICON_QUESTION)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                               wx.OK | wx.CANCEL | wx.ICON_QUESTION)
    result = dlg.ShowModal()
    dlg.Destroy()
    return result


def ShowColorDialog(color_current):
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

        wx.Dialog.__init__(self, parent, ID, title, pos, style=style)
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
        gradient = grad.GradientCtrl(self, -1, int(bound_min),
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
        sizer.Add(gradient, 0, wx.BOTTOM|wx.RIGHT|wx.LEFT|wx.EXPAND|wx.GROW, 20)
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT|wx.BOTTOM, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

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
    info.Version = const.INVESALIUS_VERSION
    info.Copyright = _("(c) 2007-2019 Center for Information Technology Renato Archer - CTI")
    info.Description = wordwrap(_("InVesalius is a medical imaging program for 3D reconstruction. It uses a sequence of 2D DICOM image files acquired with CT or MRI scanners. InVesalius allows exporting 3D volumes or surfaces as mesh files for creating physical models of a patient's anatomy using additive manufacturing (3D printing) technologies. The software is developed by Center for Information Technology Renato Archer (CTI), National Council for Scientific and Technological Development (CNPq) and the Brazilian Ministry of Health.\n\n InVesalius must be used only for research. The Center for Information Technology Renato Archer is not responsible for damages caused by the use of this software.\n\n Contact: invesalius@cti.gov.br"), 350, wx.ClientDC(parent))

#       _("InVesalius is a software for medical imaging 3D reconstruction. ")+\
#       _("Its input is a sequency of DICOM 2D image files acquired with CT or MR.\n\n")+\
#       _("The software also allows generating correspondent STL files,")+\
#       _("so the user can print 3D physical models of the patient's anatomy ")+\
#       _("using Rapid Prototyping."), 350, wx.ClientDC(parent))

    icon = wx.Icon(os.path.join(inv_paths.ICON_DIR, "invesalius_64x64.ico"),\
            wx.BITMAP_TYPE_ICO)

    info.SetWebSite("https://www.cti.gov.br/invesalius")
    info.SetIcon(icon)

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

        active_mask = 0
        for idx in project.mask_dict:
            if project.mask_dict[idx] is slc.Slice().current_mask:
                active_mask = idx
                break

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
        self.angle = InvFloatSpinCtrl(self, -1, value=0.7, min_value=0.0,
                                      max_value=1.0, increment=0.1,
                                      digits=1)

        self.max_distance = InvFloatSpinCtrl(self, -1, value=3.0, min_value=0.0,
                                         max_value=100.0, increment=0.1,
                                         digits=2)

        self.min_weight = InvFloatSpinCtrl(self, -1, value=0.5, min_value=0.0,
                                         max_value=1.0, increment=0.1,
                                         digits=1)

        self.steps = InvSpinCtrl(self, -1, value=10, min_value=1, max_value=100)

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
        w, h = self.cb_types.GetSize()

        icon = wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_MESSAGE_BOX,
                                        (h * 0.8, h * 0.8))
        self.bmp = wx.StaticBitmap(self, -1, icon)
        self.bmp.SetToolTip(_("It is not possible to use the Default method because the mask was edited."))

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

        self.gaussian_size = InvSpinCtrl(self, -1, value=self.config.mg_size,
                                         min_value=1, max_value=10)

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

    def apply_options(self):
        self.config.algorithm = self.algorithms[self.choice_algorithm.GetSelection()]
        self.config.con_2d = self.con2d_choices[self.choice_2dcon.GetSelection()]
        self.config.con_3d = self.con3d_choices[self.choice_3dcon.GetSelection()]
        self.config.mg_size = self.gaussian_size.GetValue()


class WatershedOptionsDialog(wx.Dialog):
    def __init__(self, config, ID=-1, title=_(u'Watershed'), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP):
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
        sizer.Add(btnsizer, 0, wx.ALIGN_RIGHT | wx.BOTTOM, 5)

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

        icon_folder = inv_paths.ICON_DIR
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

        gsizer.Add(wx.StaticText(self, -1, _(u"Mask 1")), 0, wx.ALIGN_CENTER_VERTICAL)
        gsizer.Add(self.mask1, 1, wx.EXPAND)
        gsizer.Add(wx.StaticText(self, -1, _(u"Operation")), 0, wx.ALIGN_CENTER_VERTICAL)
        gsizer.Add(self.op_boolean, 1, wx.EXPAND)
        gsizer.Add(wx.StaticText(self, -1, _(u"Mask 2")), 0, wx.ALIGN_CENTER_VERTICAL)
        gsizer.Add(self.mask2, 1, wx.EXPAND)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gsizer, 0, wx.EXPAND | wx.ALL, border=5)
        sizer.Add(btnsizer, 0, wx.EXPAND | wx.ALL, border=5)

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
        fsp_spacing_x = self.fsp_spacing_x = InvFloatSpinCtrl(p, -1, min_value=0, max_value=1000000000,
                                            increment=0.25, value=1.0, digits=8)


        stx_spacing_y = stx_spacing_y = wx.StaticText(p, -1, _(u"Y:"))
        fsp_spacing_y = self.fsp_spacing_y = InvFloatSpinCtrl(p, -1, min_value=0, max_value=1000000000,
                                            increment=0.25, value=1.0, digits=8)

        stx_spacing_z = stx_spacing_z = wx.StaticText(p, -1, _(u"Z:"))
        fsp_spacing_z = self.fsp_spacing_z = InvFloatSpinCtrl(p, -1, min_value=0, max_value=1000000000,
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

        self.deviation_min = InvSpinCtrl(self, -1, value=self.config.dev_min, min_value=0, max_value=10000)
        self.deviation_min.CalcSizeFromTextSize()

        self.deviation_max = InvSpinCtrl(self, -1, value=self.config.dev_max, min_value=0, max_value=10000)
        self.deviation_max.CalcSizeFromTextSize()

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

        self.spin_mult = InvFloatSpinCtrl(self, -1,
                                          value=self.config.confid_mult,
                                          min_value=1.0, max_value=10.0,
                                          increment=0.1, digits=1)
                                          #  style=wx.TE_PROCESS_TAB|wx.TE_PROCESS_ENTER,
                                          #  agwStyle=floatspin.FS_RIGHT)
        self.spin_mult.CalcSizeFromTextSize()

        self.spin_iters = InvSpinCtrl(self, -1, value=self.config.confid_iters, min_value=0, max_value=100)
        self.spin_iters.CalcSizeFromTextSize()

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


class PanelFFillProgress(wx.Panel):
    def __init__(self, parent, ID=-1, style=wx.TAB_TRAVERSAL|wx.NO_BORDER):
        wx.Panel.__init__(self, parent, ID, style=style)
        self._init_gui()

    def _init_gui(self):
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

    def StartTimer(self):
        self.t0 = time.time()

    def StopTimer(self):
        fmt = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        self.progress.SetValue(0)

    def Pulse(self):
        fmt = "%H:%M:%S"
        self.lbl_time.SetLabel(time.strftime(fmt, time.gmtime(time.time() - self.t0)))
        self.progress.Pulse()


class FFillOptionsDialog(wx.Dialog):
    def __init__(self, title, config):
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
        btn_sizer.Add(self.btn_ok, 0)# flag=wx.ALIGN_RIGHT, border=5)
        btn_sizer.Add(self.btn_cancel, 0, flag=wx.LEFT, border=5)

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
    def __init__(self, config, ID=-1, title=_(u"Region growing"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT):
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

        self.panel_ffill_progress = PanelFFillProgress(self, -1, style=wx.TAB_TRAVERSAL)
        self.panel_ffill_progress.SetMinSize((250, -1))
        # self.panel_ffill_progress.Hide()

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
        sizer.Add(self.panel_ffill_progress, (13, 0), (1, 6), flag=wx.ALIGN_RIGHT|wx.RIGHT, border=5)
        try:
            sizer.Add(0, 0, (14, 0))
        except TypeError:
            sizer.AddStretchSpacer((14, 0))
        sizer.Add(self.close_btn, (15, 0), (1, 6), flag=wx.ALIGN_RIGHT|wx.RIGHT, border=5)
        try:
            sizer.Add(0, 0, (16, 0))
        except TypeError:
            sizer.AddStretchSpacer((16, 0))

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
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
        self._init_gui()

    def _init_gui(self):
        if sys.platform == "win32":
            border_style = wx.SIMPLE_BORDER
        else:
            border_style = wx.SUNKEN_BORDER

        self.spin_size = InvSpinCtrl(self, -1, value=1000, min_value=1, max_value=1000000000)
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
        btn_sizer.Add(self.apply_btn, 0)# flag=wx.ALIGN_RIGHT, border=5)
        btn_sizer.Add(self.close_btn, 0, flag=wx.LEFT, border=5)

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

    def __init__(self, tracker, pedal_connection):
        self.tracker = tracker
        self.pedal_connection = pedal_connection

        self.trk_init, self.tracker_id = tracker.GetTrackerInfo()

        self.obj_ref_id = 2
        self.obj_name = None
        self.polydata = None
        self.use_default_object = False
        self.object_fiducial_being_set = None

        self.obj_fiducials = np.full([5, 3], np.nan)
        self.obj_orients = np.full([5, 3], np.nan)

        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, _(u"Object calibration"), size=(450, 440),
                           style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self._init_gui()
        self.LoadObject()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetObjectFiducial, 'Set object fiducial')

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
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(wx.EVT_COMBOBOX, self.OnChooseReferenceMode)
        choice_ref.SetSelection(1)
        choice_ref.Enable(1)
        if self.tracker_id == const.PATRIOT or self.tracker_id == const.ISOTRAKII:
            self.obj_ref_id = 0
            choice_ref.SetSelection(0)
            choice_ref.Enable(0)

        # ComboBox for sensor selection for FASTRAK
        tooltip = wx.ToolTip(_(u"Choose the FASTRAK sensor port"))
        choice_sensor = wx.ComboBox(self, -1, "", size=wx.Size(90, 23),
                                 choices=const.FT_SENSOR_MODE, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        choice_sensor.SetSelection(0)
        choice_sensor.SetToolTip(tooltip)
        choice_sensor.Bind(wx.EVT_COMBOBOX, self.OnChoiceFTSensor)
        if self.tracker_id in [const.FASTRAK, const.DEBUGTRACKRANDOM, const.DEBUGTRACKAPPROACH]:
            choice_sensor.Show(True)
        else:
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
        for object_fiducial in const.OBJECT_FIDUCIALS:
            index = object_fiducial['fiducial_index']
            label = object_fiducial['label']
            button_id = object_fiducial['button_id']
            tip = object_fiducial['tip']

            ctrl = wx.ToggleButton(self, button_id, label=label, size=wx.Size(60, 23))
            ctrl.SetToolTip(wx.ToolTip(tip))
            ctrl.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnObjectFiducialButton, index, ctrl=ctrl))

            self.btns_coord[index] = ctrl

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
                       wx.EXPAND|wx.GROW|wx.LEFT|wx.TOP|wx.RIGHT|wx.BOTTOM, 10)

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
        self.use_default_object = self.ObjectImportDialog()

        if not self.use_default_object:
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
                    wx.MessageBox(_("File format not recognized by InVesalius"), _("Import surface error"))
                    return
            else:
                filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")
                reader = vtk.vtkSTLReader()

                # XXX: If the user cancels the dialog for importing the coil mesh file, the current behavior is to
                #      use the default object after all. A more logical behavior in that case would be to cancel the
                #      whole object calibration, but implementing that would need larger refactoring.
                #
                self.use_default_object = True
        else:
            filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")
            reader = vtk.vtkSTLReader()

        if _has_win32api:
            self.obj_name = win32api.GetShortPathName(filename).encode(const.FS_ENCODE)
        else:
            self.obj_name = filename.encode(const.FS_ENCODE)

        reader.SetFileName(self.obj_name)
        reader.Update()
        polydata = reader.GetOutput()
        self.polydata = polydata

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
        #mapper.ImmediateModeRenderingOn()

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

    def OnObjectFiducialButton(self, index, evt, ctrl):
        if not self.tracker.IsTrackerInitialized():
            ShowNavigationTrackerWarning(0, 'choose')
            return

        # TODO: The code below until the end of the function is essentially copy-paste from
        #       OnTrackerFiducials function in NeuronavigationPanel class. Probably the easiest
        #       way to deduplicate this would be to create a Fiducial class, which would contain
        #       this code just once.
        #

        # Do not allow several object fiducials to be set at the same time.
        if self.object_fiducial_being_set is not None and self.object_fiducial_being_set != index:
            ctrl.SetValue(False)
            return

        # Called when the button for setting the object fiducial is enabled and either pedal is pressed
        # or the button is pressed again.
        #
        def set_fiducial_callback(state):
            if state:
                Publisher.sendMessage('Set object fiducial', fiducial_index=index)

                ctrl.SetValue(False)
                self.object_fiducial_being_set = None

        if ctrl.GetValue():
            self.object_fiducial_being_set = index

            if self.pedal_connection is not None:
                self.pedal_connection.add_callback(
                    name='fiducial',
                    callback=set_fiducial_callback,
                    remove_when_released=True,
                )
        else:
            set_fiducial_callback(True)

            if self.pedal_connection is not None:
                self.pedal_connection.remove_callback(name='fiducial')

    def SetObjectFiducial(self, fiducial_index):
        coord, coord_raw = self.tracker.GetTrackerCoordinates(
            # XXX: Always use static reference mode when getting the coordinates. This is what the
            #      code did previously, as well. At some point, it should probably be thought through
            #      if this is actually what we want or if it should be changed somehow.
            #
            ref_mode_id=const.STATIC_REF,
            n_samples=const.CALIBRATION_TRACKER_SAMPLES,
        )

        # XXX: The condition below happens when setting the "fixed" coordinate in the object calibration.
        #      The case is not handled by GetTrackerCoordinates function, therefore redo some computation
        #      that is already done once by GetTrackerCoordinates, namely, invert the y-coordinate.
        #
        #      (What is done here does not seem to be completely consistent with "always use static reference
        #      mode" principle above, but it's hard to come up with a simple change to increase the consistency
        #      and not change the function to the point of potentially breaking it.)
        #
        if self.obj_ref_id and fiducial_index == 4:
            coord = coord_raw[self.obj_ref_id, :]
            coord[2] = -coord[2]

        if fiducial_index == 3:
            coord = np.zeros([6,])

        # Update text controls with tracker coordinates
        if coord is not None or np.sum(coord) != 0.0:
            self.obj_fiducials[fiducial_index, :] = coord[:3]
            self.obj_orients[fiducial_index, :] = coord[3:]
            for i in [0, 1, 2]:
                self.txt_coord[fiducial_index][i].SetLabel(str(round(coord[i], 1)))
                if self.text_actors[fiducial_index]:
                    self.text_actors[fiducial_index].GetProperty().SetColor(0.0, 1.0, 0.0)
                    self.ball_actors[fiducial_index].GetProperty().SetColor(0.0, 1.0, 0.0)
            self.Refresh()
        else:
            ShowNavigationTrackerWarning(0, 'choose')

    def OnChooseReferenceMode(self, evt):
        # When ref mode is changed the tracker coordinates are set to nan
        # This is for Polhemus FASTRAK wrapper, where the sensor attached to the object can be the stylus (Static
        # reference - Selection 0 - index 0 for coordinates) or can be a 3rd sensor (Dynamic reference - Selection 1 -
        # index 2 for coordinates)
        # I use the index 2 directly here to send to the coregistration module where it is possible to access without
        # any conditional statement the correct index of coordinates.

        if evt.GetSelection() == 1:
            self.obj_ref_id = 2
            if self.tracker_id in [const.FASTRAK, const.DEBUGTRACKRANDOM, const.DEBUGTRACKAPPROACH]:
                self.choice_sensor.Show(self.obj_ref_id)
        else:
            self.obj_ref_id = 0
            self.choice_sensor.Show(self.obj_ref_id)

        for m in range(0, 5):
            self.obj_fiducials[m, :] = np.full([1, 3], np.nan)
            self.obj_orients[m, :] = np.full([1, 3], np.nan)
            for n in range(0, 3):
                self.txt_coord[m][n].SetLabel('-')

        # Used to update choice sensor controls
        self.Layout()

    def OnChoiceFTSensor(self, evt):
        if evt.GetSelection():
            self.obj_ref_id = 3
        else:
            self.obj_ref_id = 0

    def GetValue(self):
        return self.obj_fiducials, self.obj_orients, self.obj_ref_id, self.obj_name, self.polydata, self.use_default_object

class ICPCorregistrationDialog(wx.Dialog):

    def __init__(self, nav_prop):
        import invesalius.project as prj

        self.m_change = nav_prop[0]
        self.tracker = nav_prop[1]
        self.obj_ref_id = 2
        self.obj_name = None
        self.obj_actor = None
        self.polydata = None
        self.m_icp = None
        self.initial_focus = None
        self.prev_error = None
        self.final_error = None
        self.icp_mode = 0
        self.staticballs = []
        self.point_coord = []
        self.transformed_points = []

        self.obj_fiducials = np.full([5, 3], np.nan)
        self.obj_orients = np.full([5, 3], np.nan)

        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, _(u"Refine Corregistration"), size=(380, 440),
                           style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.proj = prj.Project()

        self._init_gui()

    def _init_gui(self):
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        self.interactor.Enable(1)
        self.ren = vtk.vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnUpdate, self.timer)

        txt_surface = wx.StaticText(self, -1, _('Select the surface:'))
        txt_mode = wx.StaticText(self, -1, _('Registration mode:'))

        combo_surface_name = wx.ComboBox(self, -1, size=(210, 23),
                                         style=wx.CB_DROPDOWN | wx.CB_READONLY)
        # combo_surface_name.SetSelection(0)
        if sys.platform != 'win32':
            combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        for n in range(len(self.proj.surface_dict)):
            combo_surface_name.Insert(str(self.proj.surface_dict[n].name), n)

        self.combo_surface_name = combo_surface_name

        init_surface = 0
        combo_surface_name.SetSelection(init_surface)
        self.surface = self.proj.surface_dict[init_surface].polydata
        self.LoadActor()

        tooltip = wx.ToolTip(_("Choose the registration mode:"))
        choice_icp_method = wx.ComboBox(self, -1, "", size=(100, 23),
                                        choices=([_("Affine"), _("Similarity"), _("RigidBody")]),
                                        style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_icp_method.SetSelection(0)
        choice_icp_method.SetToolTip(tooltip)
        choice_icp_method.Bind(wx.EVT_COMBOBOX, self.OnChoiceICPMethod)

        # Buttons to acquire and remove points
        create_point = wx.Button(self, -1, label=_('Create point'))
        create_point.Bind(wx.EVT_BUTTON, self.OnCreatePoint)

        cont_point = wx.ToggleButton(self, -1, label=_('Continuous acquisition'))
        cont_point.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnContinuousAcquisition, btn=cont_point))
        self.cont_point = cont_point

        btn_reset = wx.Button(self, -1, label=_('Remove points'))
        btn_reset.Bind(wx.EVT_BUTTON, self.OnReset)

        btn_apply_icp = wx.Button(self, -1, label=_('Apply registration'))
        btn_apply_icp.Bind(wx.EVT_BUTTON, self.OnICP)
        btn_apply_icp.Enable(False)
        self.btn_apply_icp = btn_apply_icp

        tooltip = wx.ToolTip(_(u"Refine done"))
        btn_ok = wx.Button(self, wx.ID_OK, _(u"Done"))
        btn_ok.SetToolTip(tooltip)
        btn_ok.Enable(False)
        self.btn_ok = btn_ok

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("")

        top_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=50, vgap=5)
        top_sizer.AddMany([txt_surface, txt_mode,
                           combo_surface_name, choice_icp_method])

        btn_acqui_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=15, vgap=15)
        btn_acqui_sizer.AddMany([create_point, cont_point, btn_reset])

        btn_ok_sizer = wx.FlexGridSizer(rows=1, cols=3, hgap=20, vgap=20)
        btn_ok_sizer.AddMany([btn_apply_icp, btn_ok, btn_cancel])

        btn_sizer = wx.FlexGridSizer(rows=2, cols=1, hgap=50, vgap=20)
        btn_sizer.AddMany([(btn_acqui_sizer, 1, wx.ALIGN_CENTER_HORIZONTAL),
                            (btn_ok_sizer, 1, wx.ALIGN_RIGHT)])

        self.progress = wx.Gauge(self, -1)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(top_sizer, 0, wx.LEFT|wx.TOP|wx.BOTTOM, 10)
        main_sizer.Add(self.interactor, 0, wx.EXPAND)
        main_sizer.Add(btn_sizer, 0,
                       wx.EXPAND|wx.GROW|wx.LEFT|wx.TOP|wx.BOTTOM, 10)
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

    def LoadActor(self):
        '''
        Load the selected actor from the project (self.surface) into the scene
        :return:
        '''
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self.surface)
        mapper.ScalarVisibilityOff()
        #mapper.ImmediateModeRenderingOn()

        obj_actor = vtk.vtkActor()
        obj_actor.SetMapper(mapper)
        self.obj_actor = obj_actor

        poses_recorded = vtku.Text()
        poses_recorded.SetSize(const.TEXT_SIZE_LARGE)
        poses_recorded.SetPosition((const.X, const.Y))
        poses_recorded.ShadowOff()
        poses_recorded.SetValue("Poses recorded: ")

        collect_points = vtku.Text()
        collect_points.SetSize(const.TEXT_SIZE_LARGE)
        collect_points.SetPosition((const.X+0.35, const.Y))
        collect_points.ShadowOff()
        collect_points.SetValue("0")
        self.collect_points = collect_points

        self.ren.AddActor(obj_actor)
        self.ren.AddActor(poses_recorded.actor)
        self.ren.AddActor(collect_points.actor)
        self.ren.ResetCamera()
        self.interactor.Render()

    def RemoveActor(self):
        self.ren.RemoveAllViewProps()
        self.point_coord = []
        self.transformed_points = []
        self.m_icp = None
        self.SetProgress(0)
        self.btn_apply_icp.Enable(False)
        self.btn_ok.Enable(False)
        self.ren.ResetCamera()
        self.interactor.Render()

    def GetCurrentCoord(self):
        coord_raw, markers_flag = self.tracker.TrackerCoordinates.GetCoordinates()
        coord, _ = dcr.corregistrate_dynamic((self.m_change, 0), coord_raw, const.DEFAULT_REF_MODE, [None, None])
        return coord[:3]

    def AddMarker(self, size, colour, coord):
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

        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(size)
        ball_ref.SetCenter(x, y, z)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtk.vtkProperty()
        prop.SetColor(colour[0:3])

        #adding a new actor for the present ball
        sphere_actor = vtk.vtkActor()

        sphere_actor.SetMapper(mapper)
        sphere_actor.SetProperty(prop)

        self.ren.AddActor(sphere_actor)
        self.point_coord.append([x, y, z])

        self.collect_points.SetValue(str(int(self.collect_points.GetValue()) + 1))

        self.interactor.Render()

        if len(self.point_coord) >= 5 and self.btn_apply_icp.IsEnabled() is False:
            self.btn_apply_icp.Enable(True)

        if self.progress.GetValue() != 0:
            self.SetProgress(0)

    def SetProgress(self, progress):
        self.progress.SetValue(progress * 100)
        self.interactor.Render()

    def vtkmatrix_to_numpy(self, matrix):
        """
        Copies the elements of a vtkMatrix4x4 into a numpy array.

        :param matrix: The matrix to be copied into an array.
        :type matrix: vtk.vtkMatrix4x4
        :rtype: numpy.ndarray
        """
        m = np.ones((4, 4))
        for i in range(4):
            for j in range(4):
                m[i, j] = matrix.GetElement(i, j)
        return m

    def SetCameraVolume(self, position):
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

        v1 = (cam_focus - self.initial_focus)

        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1/v1n)*v0n + cam_focus

        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)

        self.interactor.Render()

    def ErrorEstimation(self, surface, points):
        """
        Estimation of the average squared distance between the cloud of points to the closest mesh
        :param surface: Surface polydata of the scene
        :type surface: vtk.polydata
        :param points: Cloud of points
        :type points: np.ndarray
        :return: mean distance
        """
        cell_locator = vtk.vtkCellLocator()
        cell_locator.SetDataSet(surface)
        cell_locator.BuildLocator()

        cellId = vtk.mutable(0)
        c = [0.0, 0.0, 0.0]
        subId = vtk.mutable(0)
        d = vtk.mutable(0.0)
        error = []
        for i in range(len(points)):
            cell_locator.FindClosestPoint(points[i], c, cellId, subId, d)
            error.append(np.sqrt(float(d)))

        return np.mean(error)

    def OnComboName(self, evt):
        surface_name = evt.GetString()
        surface_index = evt.GetSelection()
        self.surface = self.proj.surface_dict[surface_index].polydata
        if self.obj_actor:
            self.RemoveActor()
        self.LoadActor()

    def OnChoiceICPMethod(self, evt):
        self.icp_mode = evt.GetSelection()

    def OnContinuousAcquisition(self, evt=None, btn=None):
        value = btn.GetValue()
        if value:
            self.timer.Start(500)
        else:
            self.timer.Stop()

    def OnUpdate(self, evt):
        current_coord = self.GetCurrentCoord()
        self.AddMarker(3, (1, 0, 0), current_coord)
        self.SetCameraVolume(current_coord)

    def OnCreatePoint(self, evt):
        current_coord = self.GetCurrentCoord()
        self.AddMarker(3, (1, 0, 0), current_coord)
        self.SetCameraVolume(current_coord)

    def OnReset(self, evt):
        if self.cont_point:
            self.cont_point.SetValue(False)
            self.OnContinuousAcquisition(evt=None, btn=self.cont_point)

        self.RemoveActor()
        self.LoadActor()

    def OnICP(self, evt):
        if self.cont_point:
            self.cont_point.SetValue(False)
            self.OnContinuousAcquisition(evt=None, btn=self.cont_point)

        self.SetProgress(0.3)
        time.sleep(1)

        sourcePoints = np.array(self.point_coord)
        sourcePoints_vtk = vtk.vtkPoints()

        for i in range(len(sourcePoints)):
            id0 = sourcePoints_vtk.InsertNextPoint(sourcePoints[i])

        source = vtk.vtkPolyData()
        source.SetPoints(sourcePoints_vtk)

        icp = vtk.vtkIterativeClosestPointTransform()
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

        #icp.DebugOn()
        icp.SetMaximumNumberOfIterations(1000)

        icp.Modified()

        icp.Update()

        self.m_icp = self.vtkmatrix_to_numpy(icp.GetMatrix())

        icpTransformFilter = vtk.vtkTransformPolyDataFilter()
        icpTransformFilter.SetInputData(source)

        icpTransformFilter.SetTransform(icp)
        icpTransformFilter.Update()

        transformedSource = icpTransformFilter.GetOutput()


        for i in range(transformedSource.GetNumberOfPoints()):
            p = [0, 0, 0]
            transformedSource.GetPoint(i, p)
            self.transformed_points.append(p)
            point = vtk.vtkSphereSource()
            point.SetCenter(p)
            point.SetRadius(3)
            point.SetPhiResolution(3)
            point.SetThetaResolution(3)

            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(point.GetOutputPort())

            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor((0,1,0))

            self.ren.AddActor(actor)

        self.prev_error = self.ErrorEstimation(self.surface, sourcePoints)
        self.final_error = self.ErrorEstimation(self.surface, self.transformed_points)

        self.interactor.Render()

        self.SetProgress(1)

        self.btn_ok.Enable(True)

    def GetValue(self):
        return self.m_icp, self.point_coord, self.transformed_points, self.prev_error, self.final_error

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

        self.orientation = None

        self.__bind_events()

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def __bind_events(self):
        Publisher.subscribe(self.SetNewFocalPoint,'Cross focal point')

    def OnOk(self, evt):
        try:
            slice_number = int(self.goto_slice.GetValue())
            orientation = self.orientation = self.goto_orientation.GetClientData(self.goto_orientation.GetSelection())

            Publisher.sendMessage(("Set scroll position", orientation), index=slice_number)
            Publisher.sendMessage('Set Update cross pos')

        except ValueError:
            pass
        self.Close()

    def SetNewFocalPoint(self, coord, spacing):
        newCoord = list(coord)
        if self.orientation=='AXIAL':
            newCoord[2] = int(self.goto_slice.GetValue())*spacing[2]
        if self.orientation == 'CORONAL':
            newCoord[1] = int(self.goto_slice.GetValue())*spacing[1]
        if self.orientation == 'SAGITAL':
            newCoord[0] = int(self.goto_slice.GetValue())*spacing[0]

        Publisher.sendMessage('Update cross pos', coord = newCoord)

    def Close(self):
        wx.Dialog.Close(self)
        self.Destroy()


class GoToDialogScannerCoord(wx.Dialog):
    def __init__(self, title=_("Go to scanner coord...")):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
        self._init_gui()

    def _init_gui(self):
        self.goto_sagital = wx.TextCtrl(self, size=(50,-1))
        self.goto_coronal = wx.TextCtrl(self, size=(50,-1))
        self.goto_axial = wx.TextCtrl(self, size=(50,-1))

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
        sizer_create.AddMany([(wx.StaticText(self, 1, _("Sagital coordinate:")), 1, wx.LEFT, 10), (self.goto_sagital, 1, wx.RIGHT, 10),
                              (wx.StaticText(self, 1, _("Coronal coordinate:")), 1, wx.LEFT, 10), (self.goto_coronal, 1, wx.RIGHT, 10),
                              (wx.StaticText(self, 1, _("Axial coordinate:")), 1, wx.LEFT, 10), (self.goto_axial, 1, wx.RIGHT, 10)])

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add((5, 5))
        main_sizer.Add(sizer_create, proportion=3, flag=wx.CENTER, border=20)
        main_sizer.Add(btnsizer, proportion=1, flag=wx.CENTER|wx.TOP, border=5)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.orientation = None
        self.affine = None

        self.__bind_events()

        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)

    def __bind_events(self):
        Publisher.subscribe(self.SetNewFocalPoint, 'Cross focal point')

    def SetNewFocalPoint(self, coord, spacing):
        Publisher.sendMessage('Update cross pos', coord=self.result*spacing)

    def OnOk(self, evt):
        import invesalius.data.slice_ as slc
        try:
            point = [float(self.goto_sagital.GetValue()),
                     float(self.goto_coronal.GetValue()),
                     float(self.goto_axial.GetValue())]

            # transformation from scanner coordinates to inv coord system
            affine_inverse = np.linalg.inv(slc.Slice().affine)
            self.result = np.dot(affine_inverse[:3, :3], np.transpose(point[0:3])) + affine_inverse[:3, 3]
            self.result[1] = slc.Slice().GetMaxSliceNumber(const.CORONAL_STR) - self.result[1]

            Publisher.sendMessage('Update status text in GUI', label=_("Calculating the transformation ..."))

            Publisher.sendMessage('Set Update cross pos')
            Publisher.sendMessage("Toggle Cross", id=const.SLICE_STATE_CROSS)

            Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
        except ValueError:
            pass
        self.Close()

    def Close(self):
        wx.Dialog.Close(self)
        self.Destroy()

class SetOptitrackconfigs(wx.Dialog):
    def __init__(self, title=_("Setting Optitrack configs:")):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, size=wx.Size(1000, 200),
                           style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP|wx.RESIZE_BORDER)
        self._init_gui()

    def _init_gui(self):
        session = ses.Session()
        last_optitrack_cal_dir = session.get('paths', 'last_optitrack_cal_dir', '')
        last_optitrack_User_Profile_dir = session.get('paths', 'last_optitrack_User_Profile_dir', '')

        if not last_optitrack_cal_dir:
            last_optitrack_cal_dir = inv_paths.OPTITRACK_CAL_DIR
        if not last_optitrack_User_Profile_dir:
            last_optitrack_User_Profile_dir = inv_paths.OPTITRACK_USERPROFILE_DIR

        self.dir_cal = wx.FilePickerCtrl(self, path=last_optitrack_cal_dir, style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
                                         wildcard="Cal files (*.cal)|*.cal", message="Select Calibration file")
        row_cal = wx.BoxSizer(wx.VERTICAL)
        row_cal.Add(wx.StaticText(self, wx.ID_ANY, "Select Calibration file"), 0, wx.TOP | wx.RIGHT, 5)
        row_cal.Add(self.dir_cal, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        self.dir_UserProfile = wx.FilePickerCtrl(self, path=last_optitrack_User_Profile_dir, style=wx.FLP_USE_TEXTCTRL | wx.FLP_SMALL,
                                         wildcard="User Profile files (*.motive)|*.motive", message="Select User Profile file")

        row_userprofile = wx.BoxSizer(wx.VERTICAL)
        row_userprofile.Add(wx.StaticText(self, wx.ID_ANY, "Select User Profile file"), 0, wx.TOP | wx.RIGHT, 5)
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

    def GetValue(self):
        fn_cal = self.dir_cal.GetPath()
        fn_userprofile = self.dir_UserProfile.GetPath()

        if fn_cal and fn_userprofile:
            session = ses.Session()
            session['paths']['last_optitrack_cal_dir'] = self.dir_cal.GetPath()
            session['paths']['last_optitrack_User_Profile_dir'] = self.dir_UserProfile.GetPath()
            session.WriteSessionFile()

        return fn_cal, fn_userprofile

class SetNDIconfigs(wx.Dialog):
    def __init__(self, title=_("Setting NDI polaris configs:")):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, size=wx.Size(1000, 200),
                           style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP|wx.RESIZE_BORDER)
        self._init_gui()

    def serial_ports(self):
        """
        Lists serial port names and pre-select the description containing NDI
        """
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()
        if sys.platform.startswith('win'):
            port_list = []
            desc_list = []
            for port, desc, hwid in sorted(ports):
                port_list.append(port)
                desc_list.append(desc)
            port_selec = [i for i, e in enumerate(desc_list) if 'NDI' in e]
        else:
            raise EnvironmentError('Unsupported platform')

        #print("Here is the chosen port: {} with id {}".format(port_selec[0], port_selec[1]))

        return port_list, port_selec

    def _init_gui(self):
        self.com_ports = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        row_com = wx.BoxSizer(wx.VERTICAL)
        row_com.Add(wx.StaticText(self, wx.ID_ANY, "Select the COM port"), 0, wx.TOP|wx.RIGHT,5)
        row_com.Add(self.com_ports, 0, wx.EXPAND)

        port_list, port_selec = self.serial_ports()

        self.com_ports.Append(port_list)
        if port_selec:
            self.com_ports.SetSelection(port_selec[0])

        session = ses.Session()
        last_ndi_probe_marker = session.get('paths', 'last_ndi_probe_marker', '')
        last_ndi_ref_marker = session.get('paths', 'last_ndi_ref_marker', '')
        last_ndi_obj_marker = session.get('paths', 'last_ndi_obj_marker', '')

        if not last_ndi_probe_marker:
            last_ndi_probe_marker = inv_paths.NDI_MAR_DIR_PROBE
        if not last_ndi_ref_marker:
            last_ndi_ref_marker = inv_paths.NDI_MAR_DIR_REF
        if not last_ndi_obj_marker:
            last_ndi_obj_marker = inv_paths.NDI_MAR_DIR_OBJ

        self.dir_probe = wx.FilePickerCtrl(self, path=last_ndi_probe_marker, style=wx.FLP_USE_TEXTCTRL|wx.FLP_SMALL,
                                           wildcard="Rom files (*.rom)|*.rom", message="Select probe's rom file")
        row_probe = wx.BoxSizer(wx.VERTICAL)
        row_probe.Add(wx.StaticText(self, wx.ID_ANY, "Set probe's rom file"), 0, wx.TOP|wx.RIGHT, 5)
        row_probe.Add(self.dir_probe, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        self.dir_ref = wx.FilePickerCtrl(self, path=last_ndi_ref_marker, style=wx.FLP_USE_TEXTCTRL|wx.FLP_SMALL,
                                         wildcard="Rom files (*.rom)|*.rom", message="Select reference's rom file")
        row_ref = wx.BoxSizer(wx.VERTICAL)
        row_ref.Add(wx.StaticText(self, wx.ID_ANY, "Set reference's rom file"), 0, wx.TOP | wx.RIGHT, 5)
        row_ref.Add(self.dir_ref, 0, wx.ALL | wx.CENTER | wx.EXPAND)

        self.dir_obj = wx.FilePickerCtrl(self, path=last_ndi_obj_marker, style=wx.FLP_USE_TEXTCTRL|wx.FLP_SMALL,
                                         wildcard="Rom files (*.rom)|*.rom", message="Select object's rom file")
        #self.dir_probe.Bind(wx.EVT_FILEPICKER_CHANGED, self.Selected)
        row_obj = wx.BoxSizer(wx.VERTICAL)
        row_obj.Add(wx.StaticText(self, wx.ID_ANY, "Set object's rom file"), 0, wx.TOP|wx.RIGHT, 5)
        row_obj.Add(self.dir_obj, 0, wx.ALL | wx.CENTER | wx.EXPAND)

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
        main_sizer.Add(row_com, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(row_probe, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(row_ref, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add((5, 5))
        main_sizer.Add(row_obj, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        main_sizer.Add((15, 15))
        main_sizer.Add(btnsizer, 0, wx.EXPAND)
        main_sizer.Add((5, 5))

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self.CenterOnParent()

    def GetValue(self):
        fn_probe = self.dir_probe.GetPath().encode(const.FS_ENCODE)
        fn_ref = self.dir_ref.GetPath().encode(const.FS_ENCODE)
        fn_obj = self.dir_obj.GetPath().encode(const.FS_ENCODE)

        if fn_probe and fn_ref and fn_obj:
            session = ses.Session()
            session['paths']['last_ndi_probe_marker'] = self.dir_probe.GetPath()
            session['paths']['last_ndi_ref_marker'] = self.dir_ref.GetPath()
            session['paths']['last_ndi_obj_marker'] = self.dir_obj.GetPath()
            session.WriteSessionFile()

        return self.com_ports.GetString(self.com_ports.GetSelection()).encode(const.FS_ENCODE), fn_probe, fn_ref, fn_obj


class SetCOMPort(wx.Dialog):
    def __init__(self, select_baud_rate, title=_("Select COM port")):
        wx.Dialog.__init__(self, wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP)

        self.select_baud_rate = select_baud_rate
        self._init_gui()

    def serial_ports(self):
        """
        Lists serial port names
        """
        import serial.tools.list_ports
        if sys.platform.startswith('win'):
            ports = ([comport.device for comport in serial.tools.list_ports.comports()])
        else:
            raise EnvironmentError('Unsupported platform')
        return ports

    def _init_gui(self):
        # COM port selection
        ports = self.serial_ports()
        self.com_port_dropdown = wx.ComboBox(self, -1, choices=ports, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.com_port_dropdown.SetSelection(0)

        com_port_text_and_dropdown = wx.BoxSizer(wx.VERTICAL)
        com_port_text_and_dropdown.Add(wx.StaticText(self, wx.ID_ANY, "COM port"), 0, wx.TOP | wx.RIGHT,5)
        com_port_text_and_dropdown.Add(self.com_port_dropdown, 0, wx.EXPAND)

        # Baud rate selection
        if self.select_baud_rate:
            baud_rates_as_strings = [str(baud_rate) for baud_rate in const.BAUD_RATES]
            self.baud_rate_dropdown = wx.ComboBox(self, -1, choices=baud_rates_as_strings, style=wx.CB_DROPDOWN | wx.CB_READONLY)
            self.baud_rate_dropdown.SetSelection(const.BAUD_RATE_DEFAULT_SELECTION)

            baud_rate_text_and_dropdown = wx.BoxSizer(wx.VERTICAL)
            baud_rate_text_and_dropdown.Add(wx.StaticText(self, wx.ID_ANY, "Baud rate"), 0, wx.TOP | wx.RIGHT,5)
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

    def GetValue(self):
        com_port = self.com_port_dropdown.GetString(self.com_port_dropdown.GetSelection())

        if self.select_baud_rate:
            baud_rate = self.baud_rate_dropdown.GetString(self.baud_rate_dropdown.GetSelection())
        else:
            baud_rate = None

        return com_port, baud_rate


class ManualWWWLDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, _("Set WW&WL manually"))
        self._init_gui()

    def _init_gui(self):
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

    def OnOK(self, evt):
        try:
            ww = int(self.txt_ww.GetValue())
            wl = int(self.txt_wl.GetValue())
        except ValueError:
            self.Close()
            return

        Publisher.sendMessage('Bright and contrast adjustment image', window=ww, level=wl)
        const.WINDOW_LEVEL['Manual'] = (ww, wl)
        Publisher.sendMessage('Check window and level other')
        Publisher.sendMessage('Update window level value', window=ww, level=wl)
        #Necessary update the slice plane in the volume case exists
        Publisher.sendMessage('Update slice viewer')
        Publisher.sendMessage('Render volume viewer')

        self.Close()

    def OnCancel(self, evt):
        self.Close()

    def OnClose(self, evt):
        self.Destroy()



class SetSpacingDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        sx,
        sy,
        sz,
        title=_("Set spacing"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP,
    ):
        wx.Dialog.__init__(self, parent, -1, title=title, style=style)
        self.spacing_original_x = sx
        self.spacing_original_y = sy
        self.spacing_original_z = sz

        self._init_gui()
        self._bind_events()

    def _init_gui(self):
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
        main_sizer.Add(wx.StaticText(self, -1, _("It was not possible to obtain the image spacings.\nPlease set it correctly:")), 0, wx.EXPAND)
        main_sizer.Add(sizer_new, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.Layout()

    def _bind_events(self):
        self.txt_spacing_new_x.Bind(wx.EVT_KILL_FOCUS, self.OnSetNewSpacing)
        self.txt_spacing_new_y.Bind(wx.EVT_KILL_FOCUS, self.OnSetNewSpacing)
        self.txt_spacing_new_z.Bind(wx.EVT_KILL_FOCUS, self.OnSetNewSpacing)

        self.button_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        self.button_cancel.Bind(wx.EVT_BUTTON, self.OnCancel)

    def OnSetNewSpacing(self, evt):
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

    def set_new_spacing(self, sx, sy, sz):
        self.spacing_new_x = sx
        self.spacing_new_y = sy
        self.spacing_new_z = sz

        self.txt_spacing_new_x.ChangeValue(str(sx))
        self.txt_spacing_new_y.ChangeValue(str(sy))
        self.txt_spacing_new_z.ChangeValue(str(sz))

    def OnOk(self, evt):
        if self.spacing_new_x == 0.0:
            self.txt_spacing_new_x.SetFocus()
        elif self.spacing_new_y == 0.0:
            self.txt_spacing_new_y.SetFocus()
        elif self.spacing_new_z == 0.0:
            self.txt_spacing_new_z.SetFocus()
        else:
            self.EndModal(wx.ID_OK)

    def OnCancel(self, evt):
        self.EndModal(wx.ID_CANCEL)
