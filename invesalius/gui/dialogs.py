#!/usr/bin/env python
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
import os
import random
import sys

import vtk
import wx
import wx.combo

from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
from wx.lib import masked
from wx.lib.agw import floatspin
from wx.lib.wordwrap import wordwrap
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.bases as bases
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
        pre = wx.PreDialog()
        pre.Create(None, -1, "InVesalius 3", size=wx.DefaultSize,
                   pos=wx.DefaultPosition,
                   style=wx.DEFAULT_DIALOG_STYLE)
        self.PostCreate(pre)

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
        pre = self.pre = wx.PreDialog()
        pre.Create(None, -1, "InVesalius 3", size=wx.DefaultSize,
                   pos=wx.DefaultPosition,
                   style=wx.DEFAULT_DIALOG_STYLE)
        self.PostCreate(pre)

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
        sizer_itens.AddSizer(sizer_percent, 0, wx.EXPAND|wx.ALL, 5)
        sizer_itens.Add(btn_sizer, 0, wx.EXPAND|wx.ALL, 5)

        sizer_general = wx.BoxSizer(wx.HORIZONTAL)
        sizer_general.Add(bmp, 0, wx.ALIGN_CENTRE|wx.ALL, 10)
        sizer_general.AddSizer(sizer_itens, 0, wx.ALL , 5)

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
        self.pre.Destroy()

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
WILDCARD_OPEN = "InVesalius 3 project (*.inv3)|*.inv3|" \
                "All files (*.*)|*.*"

WILDCARD_ANALYZE = "Analyze 7.5 (*.hdr)|*.hdr|" \
                   "All files (*.*)|*.*"

WILDCARD_NIFTI = "NIfTI 1 (*.nii)|*.nii|" \
                 "Compressed NIfTI (*.nii.gz)|*.nii.gz|" \
                 "All files (*.*)|*.*"

WILDCARD_PARREC = "PAR/REC (*.par)|*.par|" \
                  "All files (*.*)|*.*"


def ShowOpenProjectDialog():
    # Default system path
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None, message=_("Open InVesalius 3 project..."),
                        defaultDir="",
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

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filepath


def ShowImportDirDialog():
    current_dir = os.path.abspath(".")

    if (sys.platform == 'win32') or (sys.platform == 'linux2'):
        session = ses.Session()

        if (session.GetLastDicomFolder()):
            folder = session.GetLastDicomFolder()
        else:
            folder = ''
    else:
        folder = ''

    dlg = wx.DirDialog(None, _("Choose a DICOM folder:"), folder,
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

def ShowImportBitmapDirDialog():
    current_dir = os.path.abspath(".")

    if (sys.platform == 'win32') or (sys.platform == 'linux2'):
        session = ses.Session()

        if (session.GetLastDicomFolder()):
            folder = session.GetLastDicomFolder()
        else:
            folder = ''
    else:
        folder = ''

    dlg = wx.DirDialog(None, _("Choose a folder with TIFF, BMP, JPG or PNG:"), folder,
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


def ShowImportOtherFilesDialog(id_type):
    # Default system path
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None, message=_("Import Analyze 7.5 file"),
                        defaultDir="",
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

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filename


def ShowSaveAsProjectDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None,
                        _("Save project as..."), # title
                        "", # last used directory
                        default_filename,
                        _("InVesalius project (*.inv3)|*.inv3"),
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

    os.chdir(current_dir)
    return filename


# Dialog for neuronavigation markers
def ShowSaveMarkersDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None,
                        _("Save markers as..."),  # title
                        "",  # last used directory
                        default_filename,
                        _("Markers (*.txt)|*.txt"),
                        wx.SAVE | wx.OVERWRITE_PROMPT)
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
        extension = "txt"
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
                        style=wx.OPEN|wx.CHANGE_DIR)

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
        pre = wx.PreDialog()
        pre.Create(None, -1, "InVesalius 3",  size=(360, 370), pos=wx.DefaultPosition,
                    style=wx.DEFAULT_DIALOG_STYLE|wx.ICON_INFORMATION)
        self.PostCreate(pre)

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

        pre = wx.PreDialog()
        pre.Create(None, -1, title,  size=(360, 370), pos=wx.DefaultPosition,
                    style=wx.DEFAULT_DIALOG_STYLE|wx.ICON_INFORMATION)
        self.PostCreate(pre)

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

    def _OnCloseInV(self, pubsub_evt):
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

def ImportInvalidFiles(ftype="DICOM"):
    if ftype == "Bitmap":
        msg =  _("There are no Bitmap, JPEG, PNG or TIFF files in the selected folder.")
    else:
        msg = _("There are no DICOM files in the selected folder.")

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


# Navigation dialogs
def InvalidReferences():
    msg = _("The references are not set.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def TrackerNotConnected(trck_id):
    """Spatial Tracker connection error

    """
    trck = {0 : 'Claron MicronTracker',
            1 : 'Polhemus FASTRAK',
            2 : 'Polhemus ISOTRAK II',
            3 : 'Polhemus PATRIOT',
            4 : 'Zebris CMS20'}

    if trck_id < 5:
        msg = trck[trck_id] + ' is not connected.'
    elif trck_id == 5:
        msg = 'The library for specified tracker is not installed.'
    elif trck_id == 6:
        msg = 'The tracker connection is already set.'

    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)

    dlg.ShowModal()
    dlg.Destroy()


def TrackerAlreadyConnected():
    msg = _("This tracker is already connected")

    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

	
def InvalidTxt():
    msg = _("The TXT file is invalid.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3 - Neuronavigator",
                               wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

	
def error_correg_fine():
    msg = _("There aren't any created surface.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                               wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

# ===============================================================================

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
        thresh_list = project.threshold_modes.keys()
        thresh_list.sort()
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
    msg = _("The project %s has been modified.\nSave changes?")%filename
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

    info = wx.AboutDialogInfo()
    info.Name = "InVesalius"
    info.Version = "3.0"
    info.Copyright = _("(c) 2007-2015 Center for Information Technology Renato Archer - CTI")
    info.Description = wordwrap(_("InVesalius is a medical imaging program for 3D reconstruction. It uses a sequence of 2D DICOM image files acquired with CT or MRI scanners. InVesalius allows exporting 3D volumes or surfaces as mesh files for creating physical models of a patient's anatomy using additive manufacturing (3D printing) technologies. The software is developed by Center for Information Technology Renato Archer (CTI), National Council for Scientific and Technological Development (CNPq) and the Brazilian Ministry of Health.\n\n InVesalius must be used only for research. The Center for Information Technology Renato Archer is not responsible for damages caused by the use of this software.\n\n Contact: invesalius@cti.gov.br"), 350, wx.ClientDC(parent))

#       _("InVesalius is a software for medical imaging 3D reconstruction. ")+\
#       _("Its input is a sequency of DICOM 2D image files acquired with CT or MR.\n\n")+\
#       _("The software also allows generating correspondent STL files,")+\
#       _("so the user can print 3D physical models of the patient's anatomy ")+\
#       _("using Rapid Prototyping."), 350, wx.ClientDC(parent))
    info.WebSite = ("http://www.cti.gov.br/invesalius")
    info.License = _("GNU GPL (General Public License) version 2")

    info.Developers = ["Paulo Henrique Junqueira Amorim",
                       "Thiago Franco de Moraes",
                       "Jorge Vicente Lopes da Silva",
                       "Tatiana Al-Chueyr (former)",
                       "Guilherme Cesar Soares Ruppert (former)",
                       "Fabio de Souza Azevedo (former)",
                       "Bruno Lara Bottazzini (contributor)",
                       "Olly Betts (patches to support wxPython3)"]

    info.Translators = ["Alex P. Natsios",
                        "Anderson Antonio Mamede da Silva",
                        "Andreas Loupasakis",
                        "Annalisa Manenti",
                        "Cheng-Chia Tseng",
                        "Dimitris Glezos",
                        "Eugene Liscio",
                        u"Frédéric Lopez",
                        "fri",
                        "Javier de Lima Moreno",
                        "Mario Regino Moreno Guerra",
                        "Massimo Crisantemo",
                        "Nikos Korkakakis",
                        "Raul Bolliger Neto",
                        "Sebastian Hilbert",
                        "Semarang Pari"]

    #info.DocWriters = ["Fabio Francisco da Silva (PT)"]

    info.Artists = ["Otavio Henrique Junqueira Amorim"]

    # Then we call wx.AboutBox providing its info object
    wx.AboutBox(info)


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
        index_list = project.mask_dict.keys()
        index_list.sort()
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

    project_name = "%s_%s" % (project.name, type_)
    if not sys.platform in ('win32', 'linux2'):
        project_name += ".jpg"

    dlg = wx.FileDialog(None,
                        "Save %s picture as..." %type_,
                        "", # last used directory
                        project_name, # filename
                        WILDCARD_SAVE_PICTURE,
                        wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
    dlg.SetFilterIndex(1) # default is VTI

    if dlg.ShowModal() == wx.ID_OK:
        filetype_index = dlg.GetFilterIndex()
        filetype = INDEX_TO_TYPE[filetype_index]
        extension = INDEX_TO_EXTENSION[filetype_index]
        filename = dlg.GetPath()
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "."+ extension
        return filename, filetype
    else:
        return ()


# Navigation dialogs
class FineCalibration(wx.Window):
    def __init__(self, parent=None, ID=-1, title="Fine Calibration", size=wx.DefaultSize,
                 pos=wx.DefaultPosition,
                 useMetal=False):

        self.correg = None
        self.staticballs = []
        self.ball_id = 0
        self.ball_centers = []
        self.to_translate = 0
        self.flagpoint1 = 0
        self.init_angle_plh = None
        ####ICP##########
        # initial parameters
        self.actor_head_init = None
        self.actor_cloud = None

        # actors parameters
        self.color_head_init = 1.0, 0.0, 0.0
        self.color_cloud = 0.0, 1.0, 0.0
        self.color_head_icp = 224.0 / 255.0, 201.0 / 255.0, 190.0 / 255.0
        self.opacity_head_init = 1.0
        self.opacity_cloud = 0.7
        self.opacity_head_icp = 1.0
        ################

        # Instead of calling wx.Dialog.__init__ we precreate the dialog
        # so we can set an extra style that must be set before
        # creation, and then we create the GUI object using the Create
        # method.
        self.pre = wx.Frame(parent, -1, title)
        self.pre.SetPosition(pos)
        self.pre.SetSize(wx.Size(200, 200))
        self.pre.SetBackgroundColour('LIGHT GRAY')
        self.pre.CenterOnScreen()
        self.pre.Show()

        #self.pre.Create(parent, ID, title, pos, (500,300))

        # This next step is the most important, it turns this Python
        # object into the real wrapper of the dialog (instead of pre)
        # as far as the wxPython extension is concerned.
        self.PostCreate(self.pre)

        # This extra style can be set after the UI object has been created.
        if 'wxMac' in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.Center()
        self.__bind_events()
        self.draw_gui()

#         try:
        Publisher.sendMessage('Load surface into DLG')
#         except:
#             try:
#                 Publisher.sendMessage('Load volume DLG')
#             except:
#                 error_correg_fine()

        #self.LoadData()

    def ShowLoadSurfaceDialog(self):
        current_dir = os.path.abspath(".")

        dlg = wx.FileDialog(None, message=_("Load surface"),
                            defaultDir="",
                            defaultFile="",
                            style=wx.OPEN|wx.CHANGE_DIR)

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

    def __bind_events(self):
        Publisher.subscribe(self.LoadVolumeDLG,
                            'Load Raycasting into DLG')
        Publisher.subscribe(self.LoadActorDLG,
                            'Load surface actor into DLG')
        # LINE 1: Janela

    def draw_gui(self):
        #style = vtk.vtkInteractorStyleTrackballActor()
        self.panel=wx.Panel(self)
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        # self.interactor.SetInteractorStyle(style)
        self.interactor.Enable(1)
        self.ren = vtk.vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)

        # LINE 2: Botoes

        marker = wx.Button(self.panel, -1, "Create Marker",size = wx.Size(85,23))
        marker.Bind(wx.EVT_BUTTON, self.OnCalibrationMarkers)

        marker_load = wx.Button(self.panel, -1, "Load Marker",size = wx.Size(85,23))
        marker_load.Bind(wx.EVT_BUTTON, self.OnLoadMarkers)

        apply_ICP = wx.Button(self.panel, -1, "Apply ICP",size = wx.Size(85,23))
        apply_ICP.Bind(wx.EVT_BUTTON, self.OnApplyICP)

        self.showObjICP = wx.CheckBox(self.panel, -1, 'Show ICP Surface', (100, 10))
        self.showObjICP.SetValue(False)
        wx.EVT_CHECKBOX(self, self.showObjICP.GetId(), self.ShowObjectICP)

        self.showObjCloud = wx.CheckBox(self.panel, -1, 'Show Cloud of Points', (100, 10))
        self.showObjCloud.SetValue(True)
        wx.EVT_CHECKBOX(self, self.showObjCloud.GetId(), self.ShowObjectCloud)

        self.showObjHead = wx.CheckBox(self.panel, -1, 'Show Head Surface', (100, 10))
        self.showObjHead.SetValue(True)
        wx.EVT_CHECKBOX(self, self.showObjHead.GetId(), self.ShowObjectHead)

        text_X = wx.StaticText(self.panel, -1, _("X:"))
        spin_X = wx.SpinCtrl(self.panel, -1, "X", size = wx.Size(67,23))
        spin_X .SetValue(0)
        spin_X.Bind(wx.EVT_SPINCTRL, self.translate_rotate)
        spin_X.Bind(wx.EVT_TEXT, self.translate_rotate)
        spin_X .SetRange(-500,500)

        self.spin_X = spin_X

        text_Y = wx.StaticText(self.panel, -1, _("Y:"))
        spin_Y = wx.SpinCtrl(self.panel, -1, "Y", size=wx.Size(67, 23))
        spin_Y.SetValue(0)
        spin_Y.Bind(wx.EVT_SPINCTRL, self.translate_rotate)
        spin_Y.Bind(wx.EVT_TEXT, self.translate_rotate)
        spin_Y.SetRange(-500, 500)

        self.spin_Y = spin_Y

        text_Z = wx.StaticText(self.panel, -1, _("Z:"))
        spin_Z = wx.SpinCtrl(self.panel, -1, "Z", size = wx.Size(67,23))
        spin_Z .SetValue(0)
        spin_Z.Bind(wx.EVT_SPINCTRL, self.translate_rotate)
        spin_Z.Bind(wx.EVT_TEXT, self.translate_rotate)
        spin_Z .SetRange(-500,500)

        self.spin_Z = spin_Z

        text_A = wx.StaticText(self.panel,-1, _("Alfa:"))
        spin_A = wx.SpinCtrl(self.panel, -1, "Alfa", size = wx.Size(67,23))
        spin_A .SetValue(0)
        spin_A .SetRange(-500,500)
        spin_A.Bind(wx.EVT_SPINCTRL, self.translate_rotate)
        spin_A.Bind(wx.EVT_TEXT, self.translate_rotate)

        self.spin_A = spin_A

        text_B = wx.StaticText(self.panel, -1, _("Beta:"))
        spin_B = wx.SpinCtrl(self.panel, -1, "Beta", size = wx.Size(67,23))
        spin_B .SetValue(0)
        spin_B .SetRange(-500,500)
        spin_B.Bind(wx.EVT_SPINCTRL, self.translate_rotate)
        spin_B.Bind(wx.EVT_TEXT, self.translate_rotate)

        self.spin_B = spin_B

        text_G = wx.StaticText(self.panel, -1, _("Gama:"))
        spin_G = wx.SpinCtrl(self.panel, -1, "Gama", size = wx.Size(67,23))
        spin_G .SetValue(0)
        spin_G .SetRange(-500,500)
        spin_G.Bind(wx.EVT_SPINCTRL, self.translate_rotate)
        spin_G.Bind(wx.EVT_TEXT, self.translate_rotate)

        self.spin_G = spin_G

        text_inter = wx.StaticText(self.panel, -1, _("Number of Iterations:"))
        spin_inter = wx.SpinCtrl(self.panel, -1, "Numb Inter", size = wx.Size(95,23))
        spin_inter.SetValue(1000)
        spin_inter.SetRange(0, 5000)
        #        spin_X .SetValue()
        self.spin_inter = spin_inter

        text_land = wx.StaticText(self.panel, -1, _("Number of Landmarks:"))
        spin_land = wx.SpinCtrl(self.panel, -1, "Landmarks", size = wx.Size(95,23))
        spin_land.SetValue(1000)
        spin_land .SetRange(0,5000)

#        spin_Y .SetValue()
        self.spin_land = spin_land

        text_mean = wx.StaticText(self.panel, -1, _("Max Mean Distance:"))
        #spin_mean= wx.SpinCtrl(self.panel, 1, "mean", size = wx.Size(107,23))
        spin_mean = floatspin.FloatSpin(self.panel,-1,value=0.01, min_val=0.0,max_val=10.0, increment=0.01, digits=2)

        #spin_mean.SetValue(0.01)                                  
        #spin_mean .SetRange(0,10)
#       spin_Z .SetValue()
        self.spin_mean = spin_mean

        spinicp = wx.FlexGridSizer(rows=3, cols=2, hgap=1, vgap=1)
        spinicp.AddMany([(text_inter,0,wx.ALIGN_TOP|wx.EXPAND | wx.TOP|wx.BOTTOM,5),(spin_inter, 1),
                      (text_land,0,wx.ALIGN_CENTER_VERTICAL|wx.EXPAND | wx.TOP|wx.BOTTOM,5),(spin_land, 1),
                      (text_mean,0, wx.ALIGN_BOTTOM|wx.EXPAND | wx.TOP|wx.BOTTOM,5),(spin_mean, 1)])

        spin = wx.FlexGridSizer(rows=3, cols=4, hgap=1, vgap=1)
        spin.AddMany([(text_X, 0,wx.ALIGN_TOP|wx.EXPAND | wx.TOP|wx.BOTTOM,5),(spin_X, 1),(text_A, 0,wx.ALIGN_TOP|wx.EXPAND|wx.LEFT| wx.TOP|wx.BOTTOM,5),(spin_A, 1),
                      (text_Y,  0,wx.ALIGN_CENTER_VERTICAL|wx.EXPAND | wx.TOP|wx.BOTTOM,5),(spin_Y, 1),(text_B, 0,wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.LEFT| wx.TOP|wx.BOTTOM,5),(spin_B, 1),
                      (text_Z,  0,wx.ALIGN_BOTTOM|wx.EXPAND | wx.TOP|wx.BOTTOM,5),(spin_Z, 1),(text_G, 0,wx.ALIGN_BOTTOM|wx.EXPAND|wx.LEFT| wx.TOP|wx.BOTTOM,5),(spin_G, 1)])

        ok = wx.Button(self.panel, wx.ID_OK)
        ok.Bind(wx.EVT_BUTTON, self.OK)
        cancel = wx.Button(self.panel, wx.ID_CANCEL)
        cancel.Bind(wx.EVT_BUTTON, self.CANCEL)

        checkb = wx.FlexGridSizer(rows=3, cols=1, hgap=1, vgap=1)
        checkb.AddMany([(self.showObjICP , 0,wx.ALIGN_TOP|wx.EXPAND | wx.TOP|wx.BOTTOM,5),
                      (self.showObjHead , 0,wx.ALIGN_CENTER_VERTICAL|wx.EXPAND | wx.TOP|wx.BOTTOM,5),
                      (self.showObjCloud , 0,wx.ALIGN_BOTTOM|wx.EXPAND | wx.TOP|wx.BOTTOM,5)])

        col1 = wx.FlexGridSizer(rows=3, cols=1, hgap=1, vgap=1)
        col1.AddMany([(marker, 1),
                      (marker_load, 1),
                      (apply_ICP, 1)])

#         col2 = wx.FlexGridSizer(rows=1, cols=1, hgap=1, vgap=1)
#         col2.AddMany([(param_ICP, 1)])
#
        col4 = wx.FlexGridSizer(rows=2, cols=1, hgap=1, vgap=1)
        col4.AddMany([(ok, 1),
                      (cancel, 1)])

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(col1, 0, wx.EXPAND | wx.ALL, 10)
        button_sizer.Add(checkb, 0, wx.EXPAND | wx.ALL, 10)
        button_sizer.Add(spinicp, 0, wx.EXPAND | wx.ALL, 10)
        button_sizer.Add(spin, 0, wx.EXPAND | wx.ALL, 10)
        button_sizer.Add(col4, 0, wx.EXPAND | wx.ALL, 10)
        self.panel.SetSizer(button_sizer)
        # OVERVIEW
        # Merge all sizers and checkboxes
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.interactor, 5, wx.EXPAND,10)
        sizer.Add(self.panel, 1,wx.ALIGN_CENTER,1)

        self.SetSizerAndFit(sizer)
        self.Show()
        sizer.Fit(self)

    def GetValue(self):
        return self.actor_icp,self.icp_matrix
    def OK(self,evt):
        self.Close()
    def CANCEL(self,evt):
        self.Destroy()
    def ShowObjectICP(self, evt):
        objectbin = self.showObjICP.GetValue()
        if objectbin == True:
            self.actor_icp.SetVisibility(1)
            self.interactor.Render()
        if objectbin == False:
            self.actor_icp.SetVisibility(0)
            self.interactor.Render()

    def ShowObjectCloud(self, evt):
        objectbin = self.showObjCloud.GetValue()
        if objectbin == True:
            self.actor_cloud.SetVisibility(1)
            self.interactor.Render()
        if objectbin == False:
            self.actor_cloud.SetVisibility(0)
            self.interactor.Render()

    def ShowObjectHead(self, evt):
        objectbin = self.showObjHead.GetValue()
        if objectbin == True:
            self.actor.SetVisibility(1)
            self.interactor.Render()
        if objectbin == False:
            self.actor.SetVisibility(0)
            self.interactor.Render()

    def translate_rotate(self,evt):
             self.transform = vtk.vtkTransform()
             self.transform.Identity()
             self.transform.PostMultiply()

#             try2=vtk.vtkImageChangeInformation.SetInput(self.cloud)
#             self.cloud.vtk.vtkImageData.SetOrigin(self.actor_cloud.GetCenter())
#              try1=vtk.vtkImageData(self.reader_cloud)
#              try1.SetOrigin(self.actor_cloud.GetCenter())

             self.transform.Translate(self.spin_X.GetValue(), 0, 0)
             self.transform.Translate(0,self.spin_Y.GetValue(), 0)
             self.transform.Translate(0, 0, self.spin_Z.GetValue())

             #self.actor_cloud.SetOrientation(self.spin_A.GetValue(),xyz[1],xyz[2])
             #transform.RotateWXYZ(self.spin_A.GetValue(),1,0,0)

#              transform.RotateX(self.spin_A.GetValue())
#              transform.RotateY(self.spin_B.GetValue())
#              transform.RotateZ(self.spin_G.GetValue())
#             transform.RotateWXYZ(self.spin_B.GetValue(),xyz[0],1,xyz[2])
#             transform.RotateWXYZ(self.spin_G.GetValue(),xyz[0],xyz[1],1)
             self.actor_cloud.SetOrigin(self.actor_cloud.GetCenter())
             self.actor_cloud.SetOrientation(0,0,0)
             #self.transform.SetInput(self.actor_cloud)
             self.transform.RotateX(self.spin_A.GetValue())
             self.transform.RotateY(self.spin_B.GetValue())
             self.transform.RotateZ(self.spin_G.GetValue())

#              self.transform.RotateX(self.spin_A.GetValue())
#              self.transform.RotateY(self.spin_B.GetValue())
#              self.transform.RotateZ(self.spin_G.GetValue())
             self.transform.Update()

             self.transf = vtk.vtkTransformPolyDataFilter()

             self.transf.SetInput(self.cloud)
             self.transf.SetTransform(self.transform)
             self.transf.Update()
             self.ren.RemoveActor(self.actor_cloud)
             self.mapper_cloud = vtk.vtkPolyDataMapper()
             self.mapper_cloud.SetInput(self.transf.GetOutput())
             self.mapper_cloud.ScalarVisibilityOff()
             self.mapper_cloud.ImmediateModeRenderingOn()
             self.actor_cloud = vtk.vtkActor()
             self.actor_cloud.SetMapper(self.mapper_cloud)
             self.actor_cloud.GetProperty().SetColor(self.color_cloud)
             self.actor_cloud.GetProperty().SetOpacity(self.opacity_cloud)
             self.ren.AddActor(self.actor_cloud)

             #self.actor_cloud.SetOrigin(self.actor_cloud.GetCenter())
             #self.actor_cloud.SetOrientation(0,0,0)
             #self.actor_cloud.RotateX(self.spin_A.GetValue())
             #self.actor_cloud.RotateY(self.spin_B.GetValue())
             #self.actor_cloud.RotateZ(self.spin_G.GetValue())
             self.interactor.Render()

    def OnLoadMarkers(self, evt):
        print "Reading the points!"

        filepath = ShowLoadMarkersDialog()
        text_file = open(filepath, "r")
        # reading all lines and splitting into a float vector
        while 1:
            line = text_file.readline()
            if not line:
                break
            try:
                line1 = [float(s) for s in line.split()]
                coord = float(line1[1] - 1.0), float(line1[0] - 1.0), float(line1[2] - 1.0)
                colour = line1[3], line1[4], line1[5]
                size = line1[6]

                CreateSphereMarkers(self,size,colour,coord)

                    #sum 1 for each coordinate to matlab comprehension
                    #coord = coord[0] + 1.0, coord[1] + 1.0, coord[2] + 1.0
                    #line with coordinates and properties of a marker
                line = coord[0] , coord[1] , coord[2] , colour[0], colour[1], colour[2], size
                if self.flagpoint1 == 0:
                    self.list_coord = [line]
                    self.flagpoint1 = 1
                else:
                    # adding actual line to a list of all markers already created
                    self.list_coord.append(line)
            except:
                InvalidTxt()
                raise ValueError('Invalid Txt')

    def OnCalibrationMarkers(self, evt):
        None

    def OnParamICP(self, evt):
        None

    def OnApplyICP(self, evt):
        self.showObjICP.SetValue(True)
        self.icp_number_iterations= self.spin_inter.GetValue()
        self.icp_number_landmarks= self.spin_land.GetValue()
        self.icp_max_mean_distance = self.spin_mean.GetValue()
        self.Transformation()
        self.interactor.Render()
        self.Show()

    def CreateCloudPointsSurface(self, filename_cloud):
            # Reconstruct the surface from the cloud of points
            self.reader_cloud = vtk.vtkPLYReader()

            self.reader_cloud.SetFileName(filename_cloud)
            self.reader_cloud.Update()

            print "Creating cloud surface..."

            self.mapper_cloud = vtk.vtkPolyDataMapper()
            self.mapper_cloud.SetInput(self.reader_cloud.GetOutput())
            self.mapper_cloud.ScalarVisibilityOff()
            self.mapper_cloud.ImmediateModeRenderingOn()

            self.actor_cloud = vtk.vtkActor()
            self.actor_cloud.SetMapper(self.mapper_cloud)
            self.actor_cloud.GetProperty().SetColor(self.color_cloud)
            self.actor_cloud.GetProperty().SetOpacity(self.opacity_cloud)

            return self.reader_cloud.GetOutput()

    def Transformation(self):
                # Apply IterativeClosestPoint Method

                #self.filename_cloud=self.ShowLoadSurfaceDialog()
                try:
                    self.ren.RemoveActor(self.actor_icp)
                    self.interactor.Render()
                except:
                    None
                filename_head = self.head
                #filename_cloud = sys.argv[2]
                #head_init = self.CreateHeadSurface(filename_head)
                #cloud = self.CreateCloudPointsSurface(self.filename_cloud)

                print "Applying ICP method..."
                icp = vtk.vtkIterativeClosestPointTransform()
                icp.SetSource(filename_head)
                try:
                    icp.SetTarget(self.transf.GetOutput())
                except:
                    icp.SetTarget(self.cloud)

                icp.StartByMatchingCentroidsOn()
                icp.SetMaximumNumberOfIterations(self.icp_number_iterations)
                icp.SetMaximumNumberOfLandmarks(self.icp_number_landmarks)
                icp.SetMaximumMeanDistance(self.icp_max_mean_distance)
                icp.GetLandmarkTransform().SetModeToRigidBody()
                icp.SetMeanDistanceModeToRMS()
                icp.Update()

                icp_transf = vtk.vtkTransformPolyDataFilter()
                icp_transf.SetInput(filename_head)
                icp_transf.SetTransform(icp)
                icp_transf.Update()

                mapper_head_icp = vtk.vtkPolyDataMapper()
                mapper_head_icp.SetInput(icp_transf.GetOutput())
                mapper_head_icp.ScalarVisibilityOff()
                mapper_head_icp.ImmediateModeRenderingOn()

                self.actor_icp = vtk.vtkActor()
                self.actor_icp.SetMapper(mapper_head_icp)
                self.actor_icp.GetProperty().SetColor(self.color_head_icp)
                self.actor_icp.GetProperty().SetOpacity(self.opacity_head_icp)

                self.icp_matrix = vtk.vtkMatrix4x4()
                self.icp_matrix = icp.GetMatrix()
                print self.icp_matrix

                #Eixos para facilitar visualizacao -----------------
#                 axes = vtk.vtkAxesActor()
#                 axes.SetShaftTypeToCylinder()
#                 axes.SetXAxisLabelText("x")
#                 axes.SetYAxisLabelText("y")
#                 axes.SetZAxisLabelText("z")
#                 axes.SetTotalLength(25, 25, 25)
                #---------------------------------------------------


                #renderer.AddActor(axes)

                self.ren.AddActor(self.actor_icp)
                #self.outlineF(icp_transf.GetOutput())
                #self.ren.AddActor(self.outline)
                self.ren.SetBackground(0, 0, 0)
                self.ren.ResetCamera()

    def LoadData(self):
        coil_reference = vtk.vtkOBJReader()
        # coil_reference.SetFileName(os.path.realpath(os.path.join('..',
        #                                                         'models',
        #                                                         'coil_cti_2_scale10.obj')))

        coil_reference.SetFileName('C:\Users\Administrator\Dropbox\Biomag\Renan\coil\coil_cti_2_scale10.obj')
        coilMapper = vtk.vtkPolyDataMapper()
        coilMapper.SetInputConnection(coil_reference.GetOutputPort())
        self.coilActor = vtk.vtkActor()
        # self.coilActor.Scale(10.0, 10.0, 10.0)
        self.coilActor.SetMapper(coilMapper)

        axes = vtk.vtkAxesActor()
        axes.SetShaftTypeToCylinder()
        axes.SetXAxisLabelText("x")
        axes.SetYAxisLabelText("y")
        axes.SetZAxisLabelText("z")
        axes.SetTotalLength(50.0, 50.0, 50.0)

        self.ren.AddActor(self.coilActor)
        self.ren.AddActor(axes)

    def LoadActorDLG(self, pubsub_evt):
        self.actor = pubsub_evt.data[0]
        #self.head=actor
        self.head=pubsub_evt.data[1]

        self.outlineF(self.head)
        self.ren.AddActor(self.outline)

        self.filename_cloud=self.ShowLoadSurfaceDialog()
        self.cloud = self.CreateCloudPointsSurface(self.filename_cloud)
        print self.cloud

        self.outlineF(self.cloud)
        self.ren.AddActor(self.outline)

        self.ren.AddActor(self.actor)
        self.ren.AddActor(self.actor_cloud)

        axes = vtk.vtkAxesActor()
        axes.SetShaftTypeToCylinder()
        axes.SetXAxisLabelText("x")
        axes.SetYAxisLabelText("y")
        axes.SetZAxisLabelText("z")
        axes.SetTotalLength(25, 25, 25)
        self.ren.AddActor(axes)

        self.ren.ResetCamera()
        #self.ren.ResetCameraClippingRange()

        #self.ShowOrientationCube()
        self.interactor.Render()

    def LoadVolumeDLG(self, pubsub_evt):
        self.raycasting_volume = True

        #self._to_show_ball += 1
        #print "to show ball", self._to_show_ball

        volume = pubsub_evt.data[0]
        colour = pubsub_evt.data[1]
        self.light = self.ren.GetLights().GetNextItem()

        self.ren.AddVolume(volume)

        self.ren.SetBackground(colour)

        self.interactor.Render()

    def outlineF(self,Actor):
        #filtro outline
        self.outline = vtk.vtkActor()
        outlineData = vtk.vtkOutlineFilter()
        outlineData.SetInput(Actor)
        outlineData.Update()

        mapoutline = vtk.vtkPolyDataMapper()
        mapoutline.SetInputConnection(outlineData.GetOutputPort())

        self.outline.SetMapper(mapoutline)
        self.outline.GetProperty().SetColor(0.0, 0.0, 1.0)

def CreateSphereMarkers(self,ballsize,ballcolour,coord):

        x, y, z = bases.flip_x(coord)

        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(ballsize)
        ball_ref.SetCenter(x, y, z)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(ball_ref.GetOutput())

        prop = vtk.vtkProperty()
        prop.SetColor(ballcolour)

        #adding a new actor for the present ball
        self.staticballs.append(vtk.vtkActor())

        self.staticballs[self.ball_id].SetMapper(mapper)
        self.staticballs[self.ball_id].SetProperty(prop)

        self.ren.AddActor(self.staticballs[self.ball_id])
        self.ball_id = self.ball_id + 1
        self.interactor.Render()



        self.PostCreate(self.pre)
# # # class ObjectCalibration(wx.Window):
# # #     def __init__(self, parent=None, ID=-1, title="Object Calibration", size=wx.DefaultSize,
# # #             pos=wx.DefaultPosition,style=wx.DEFAULT_DIALOG_STYLE,
# # #             useMetal=False,nav_prop=None):
# # #         self.correg = None
# # #         self.nav_prop = nav_prop
# # #         self.staticballs = []
# # #         self.ball_id = 0
# # #         self.ball_centers = []
# # #         self.to_translate = 0
# # #         self.flagpoint1 = 0
# # #         self.init_angle_plh = None
# # #
# # #         # Instead of calling wx.Dialog.__init__ we precreate the dialog
# # #         # so we can set an extra style that must be set before
# # #         # creation, and then we create the GUI object using the Create
# # #         # method.
# # #
# # #
# # #         self.pre = wx.Frame(parent, -1, title)
# # #         self.pre.SetPosition(pos)
# # #         self.pre.SetSize(wx.Size(200,200))
# # #         self.pre.SetBackgroundColour('LIGHT GRAY')
# # #         self.pre.CenterOnScreen()
# # #         self.pre.Show()
# # #         # This next step is the most important, it turns this Python
# # #         # object into the real wrapper of the dialog (instead of pre)
# # #         # as far as the wxPython extension is concerned.
# # #         self.PostCreate(self.pre)
# # #
# # #
# # #         # This extra style can be set after the UI object has been created.
# # #         if 'wxMac' in wx.PlatformInfo and useMetal:
# # #             self.SetExtraStyle(wx.DIALOG_EX_METAL)
# # #
# # #         self.draw_gui()
# # #         self.LoadData()
# # #
# # #         # LINE 1: Janela
# # #
# # #     def draw_gui(self):
# # #         #style = vtk.vtkInteractorStyleTrackballActor()
# # #         self.panel=wx.Panel(self)
# # #         self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
# # #         #self.interactor.SetInteractorStyle(style)
# # #         self.interactor.Enable(1)
# # #         self.ren = vtk.vtkRenderer()
# # #         self.interactor.GetRenderWindow().AddRenderer(self.ren)
# # #
# # #         # LINE 2: Botoes
# # #
# # #         marker = wx.Button(self.panel, -1, "Create Marker",size = wx.Size(85,23))
# # #         marker.Bind(wx.EVT_BUTTON, self.OnCalibrationMarkers)
# # #
# # #         marker_load = wx.Button(self.panel, -1, "Load Marker",size = wx.Size(85,23))
# # #         marker_load.Bind(wx.EVT_BUTTON, self.OnLoadMarkers)
# # #
# # #
# # #         #Change X,Y,Z and Alfa,Beta,Gama
# # #         text_X = wx.StaticText(self.panel, -1, _("X:"))
# # #         spin_X = wx.SpinCtrl(self.panel, -1, "X", size = wx.Size(47,23))
# # #         spin_X .SetRange(1,100)
# # #         spin_X .SetValue(0)
# # #         self.spin_X = spin_X
# # #
# # #         text_Y = wx.StaticText(self.panel, -1, _("Y:"))
# # #         spin_Y = wx.SpinCtrl(self.panel, -1, "Y", size = wx.Size(47,23))
# # #         spin_Y .SetRange(1,100)
# # #         spin_Y .SetValue(0)
# # #         self.spin_Y = spin_Y
# # #
# # #         text_Z = wx.StaticText(self.panel, -1, _("Z:"))
# # #         spin_Z = wx.SpinCtrl(self.panel, -1, "Z", size = wx.Size(47,23))
# # #         spin_Z .SetRange(1,100)
# # #         spin_Z .SetValue(0)
# # #         self.spin_Z = spin_Z
# # #
# # #         text_A = wx.StaticText(self.panel, -1, _("Alfa:"))
# # #         spin_A = wx.SpinCtrl(self.panel, -1, "Alfa", size = wx.Size(47,23))
# # #         spin_A .SetRange(1,100)
# # #         spin_A .SetValue(0)
# # #         self.spin_A = spin_A
# # #
# # #         text_B = wx.StaticText(self.panel, -1, _("Beta:"))
# # #         spin_B = wx.SpinCtrl(self.panel, -1, "Beta", size = wx.Size(47,23))
# # #         spin_B .SetRange(1,100)
# # #         spin_B .SetValue(0)
# # #         self.spin_B = spin_B
# # #
# # #         text_G = wx.StaticText(self.panel, -1, _("Gama:"))
# # #         spin_G = wx.SpinCtrl(self.panel, -1, "Gama", size = wx.Size(47,23))
# # #         spin_G .SetRange(1,100)
# # #         spin_G .SetValue(0)
# # #         self.spin_G = spin_G
# # #
# # #         spin = wx.FlexGridSizer(rows=3, cols=4, hgap=5, vgap=5)
# # #         spin.AddMany([(text_X, 1,wx.LEFT|wx.ALIGN_CENTER_VERTICAL),(spin_X, 1, wx.RIGHT|wx.LEFT),(text_A, 1,wx.LEFT|wx.ALIGN_CENTER_VERTICAL),(spin_A, 1, wx.RIGHT),
# # #                       (text_Y, 1,wx.LEFT|wx.ALIGN_CENTER_VERTICAL),(spin_Y, 1, wx.RIGHT|wx.LEFT),(text_B, 1,wx.LEFT|wx.ALIGN_CENTER_VERTICAL),(spin_B, 1, wx.RIGHT),
# # #                       (text_Z, 1,wx.LEFT|wx.ALIGN_CENTER_VERTICAL),(spin_Z, 1, wx.RIGHT|wx.LEFT),(text_G, 1,wx.LEFT|wx.ALIGN_CENTER_VERTICAL),(spin_G, 1, wx.RIGHT)])
# # #
# # #         ok = wx.Button(self.panel, wx.ID_OK)
# # #         ok.Bind(wx.EVT_BUTTON, self.OK)
# # #         cancel = wx.Button(self.panel, wx.ID_CANCEL)
# # #
# # #         col1 = wx.FlexGridSizer(rows=3, cols=1, hgap=5, vgap=5)
# # #         col1.AddMany([(marker, 0, wx.RIGHT|wx.LEFT),
# # #                       (marker_load, 0, wx.RIGHT|wx.LEFT)])
# # #
# # #         col4 = wx.FlexGridSizer(rows=2, cols=1, hgap=5, vgap=5)
# # #         col4.AddMany([(ok, 0, wx.RIGHT|wx.LEFT),
# # #                       (cancel, 0, wx.RIGHT|wx.LEFT|wx.BOTTOM)])
# # #
# # #         button_sizer = wx.BoxSizer(wx.HORIZONTAL)
# # #         button_sizer.Add(col1,0,wx.RIGHT|wx.ALIGN_CENTER_VERTICAL,10)
# # #         button_sizer.Add(spin,0,wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL,10)
# # #         button_sizer.Add(col4,0,wx.LEFT|wx.ALIGN_CENTER_VERTICAL,10)
# # #         self.panel.SetSizer(button_sizer)
# # #         # OVERVIEW
# # #         # Merge all sizers and checkboxes
# # #         sizer = wx.BoxSizer(wx.VERTICAL)
# # #         sizer.Add(self.interactor, 3, wx.EXPAND)
# # #         sizer.Add(self.panel, 1,wx.ALIGN_CENTER_HORIZONTAL|wx.TOP|wx.BOTTOM|wx.RIGHT|wx.LEFT, 20)
# # #
# # #         self.SetSizer(sizer)
# # #         sizer.Fit(self)
# # #
# # #     def OK(self,evt):
# # #         Publisher.sendMessage('Load Param Obj')
# # #         self.Close()
# # #
# # #     def OnLoadMarkers(self, evt):
# # #         print "Reading the points!"
# # #
# # #         filepath = ShowLoadMarkersDialog()
# # #         text_file = open(filepath, "r")
# # #         #reading all lines and splitting into a float vector
# # #         while 1:
# # #             line = text_file.readline()
# # #             if not line:
# # #                 break
# # #             try:
# # #                 line1 = [float(s) for s in line.split()]
# # #                 coord = float(line1[1] - 1.0), float(line1[0] - 1.0), float(line1[2] - 1.0)
# # #                 colour = line1[3], line1[4], line1[5]
# # #                 size = line1[6]
# # #
# # #                 CreateSphereMarkers(self,size,colour,coord)
# # #
# # #                     #sum 1 for each coordinate to matlab comprehension
# # #                     #coord = coord[0] + 1.0, coord[1] + 1.0, coord[2] + 1.0
# # #                     #line with coordinates and properties of a marker
# # #                 line = coord[0] , coord[1] , coord[2] , colour[0], colour[1], colour[2], size
# # #                 if self.flagpoint1 == 0:
# # #                     self.list_coord = [line]
# # #                     self.flagpoint1 = 1
# # #                 else:
# # #                         #adding actual line to a list of all markers already created
# # #                     self.list_coord.append(line)
# # #             except:
# # #                 InvalidTxt()
# # #                 raise ValueError('Invalid Txt')
# # #     def OnCalibrationMarkers(self, evt):
# # #         import data.coordinates as co
# # #         from numpy import matrix
# # #         Minv = self.nav_prop[0][0]
# # #         N = self.nav_prop[0][1]
# # #         q1 = self.nav_prop[0][2]
# # #         q2 = self.nav_prop[0][3]
# # #         nav_id = self.nav_prop[1]
# # #         tracker_init = self.nav_prop[1][0]
# # #         tracker = self.nav_prop[1][1]
# # #         tracker_mode = self.nav_prop[1][2]
# # #
# # #         trck = co.Coordinates(tracker_init, tracker, tracker_mode).Returns()
# # #         tracker = matrix([[trck[0]], [trck[1]], [trck[2]]])
# # #         self.init_angle_plh = trck[3], trck[4], trck[5]
# # #         img = q1 + (Minv*N)*(tracker - q2)
# # #         coord = float(img[0]), float(img[1]), float(img[2])
# # #         x, y, z = bases.FlipX(coord)
# # #
# # #         if not self.ball_centers:
# # #             self.to_translate = -x, -y, -z
# # #
# # #         x = x + self.to_translate[0]
# # #         y = y + self.to_translate[1]
# # #         z = z + self.to_translate[2]
# # #
# # #         ball_ref = vtk.vtkSphereSource()
# # #         ball_ref.SetRadius(4)
# # #         ball_ref.SetCenter(x, y, z)
# # #
# # #         self.ball_centers.append((x, y, z))
# # #
# # #         mapper = vtk.vtkPolyDataMapper()
# # #         mapper.SetInput(ball_ref.GetOutput())
# # #
# # #         prop = vtk.vtkProperty()
# # #         prop.SetColor(0,1, 1)
# # #
# # #         #adding a new actor for the present ball
# # #         self.staticballs.append(vtk.vtkActor())
# # #
# # #         self.staticballs[self.ball_id].SetMapper(mapper)
# # #         self.staticballs[self.ball_id].SetProperty(prop)
# # #
# # #         self.ren.AddActor(self.staticballs[self.ball_id])
# # #         self.ball_id += 1
# # #
# # #         self.interactor.Render()
# # #
# # #
# # #     def LoadData(self):
# # #         coil_reference = vtk.vtkOBJReader()
# # #         #coil_reference.SetFileName(os.path.realpath(os.path.join('..',
# # #         #                                                         'models',
# # #         #                                                         'coil_cti_2_scale10.obj')))
# # #         coil_reference.SetFileName('C:\Users\Administrator\Dropbox\Biomag\Renan\coil\coil_cti_2_scale10.obj')
# # #        # coil_reference.SetFileName('C:\Users\Renan\Dropbox\Biomag\Renan\coil\coil_cti_2_scale10.obj')
# # #         coilMapper = vtk.vtkPolyDataMapper()
# # #         coilMapper.SetInputConnection(coil_reference.GetOutputPort())
# # #         self.coilActor = vtk.vtkActor()
# # #         #self.coilActor.Scale(10.0, 10.0, 10.0)
# # #         self.coilActor.SetMapper(coilMapper)
# # #
# # #         axes = vtk.vtkAxesActor()
# # #         axes.SetShaftTypeToCylinder()
# # #         axes.SetXAxisLabelText("x")
# # #         axes.SetYAxisLabelText("y")
# # #         axes.SetZAxisLabelText("z")
# # #         axes.SetTotalLength(50.0, 50.0, 50.0)
# # #
# # #         self.ren.AddActor(self.coilActor)
# # #         self.ren.AddActor(axes)
class ObjectCalibration(wx.Dialog):
    def __init__(self, parent=None, ID=-1, title="Calibration Dialog", size=wx.DefaultSize,
            pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE,
            useMetal=False, nav_prop=None):

        self.nav_prop = nav_prop
        self.correg = None
        self.staticballs = []
        self.ball_id = 0
        self.ball_centers = []
        self.to_translate = 0
        self.init_angle_plh = None

        # Instead of calling wx.Dialog.__init__ we precreate the dialog
        # so we can set an extra style that must be set before
        # creation, and then we create the GUI object using the Create
        # method.
        pre = wx.PreDialog()
        pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        pre.Create(parent, ID, title, pos, (700, 500), style)

        # This next step is the most important, it turns this Python
        # object into the real wrapper of the dialog (instead of pre)
        # as far as the wxPython extension is concerned.
        self.PostCreate(pre)

        self.CenterOnScreen()

        # This extra style can be set after the UI object has been created.
        if 'wxMac' in wx.PlatformInfo and useMetal:
            self.SetExtraStyle(wx.DIALOG_EX_METAL)

        self.CenterOnScreen()
        self.draw_gui()
        self.LoadData()

        # LINE 1: Janela

    def draw_gui(self):
        #style = vtk.vtkInteractorStyleTrackballActor()

        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        # self.interactor.SetInteractorStyle(style)
        self.interactor.Enable(1)
        self.ren = vtk.vtkRenderer()
        self.interactor.GetRenderWindow().AddRenderer(self.ren)

        # LINE 2: Botoes

        marker = wx.Button(self, -1, "Create Marker")
        marker.Bind(wx.EVT_BUTTON, self.OnCalibrationMarkers)

        dc_vtkMatrix = wx.Button(self, -1, "Matrix")
        dc_vtkMatrix.Bind(wx.EVT_BUTTON, self.DirectionCosinesTest_vtkmatrix)

        dc_eulerangles = wx.Button(self, -1, "Euler")
        dc_eulerangles.Bind(wx.EVT_BUTTON, self.DirectionCosinesTest_eulerangles)

        rotate_button = wx.Button(self, -1, "Rotate")
        rotate_button.Bind(wx.EVT_BUTTON, self.rotate)

        reset = wx.Button(self, -1, "Reset")
        reset.Bind(wx.EVT_BUTTON, self.Reset)

        button_neuronavigate = wx.Button(self, -1, "Neuronavigate")
        button_neuronavigate.Bind(wx.EVT_BUTTON, self.Neuronavigate_ToggleButton)

        ok = wx.Button(self, wx.ID_OK)

        cancel = wx.Button(self, wx.ID_CANCEL)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(marker)
        button_sizer.Add(dc_vtkMatrix)
        button_sizer.Add(dc_eulerangles)
        button_sizer.Add(reset)
        button_sizer.Add(button_neuronavigate)
        button_sizer.Add(rotate_button)
        button_sizer.Add(ok)
        button_sizer.Add(cancel)

        # OVERVIEW
        # Merge all sizers and checkboxes
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.interactor, 0, wx.EXPAND)
        sizer.Add(button_sizer, 0, wx.TOP | wx.RIGHT | wx.LEFT | wx.GROW | wx.EXPAND, 20)

        self.SetSizer(sizer)
        sizer.Fit(self)

    def LoadData(self):
        coil_reference = vtk.vtkOBJReader()
        # coil_reference.SetFileName(os.path.realpath(os.path.join('..',
        #                                                         'models',
        #                                                         'coil_cti_2_scale10.obj')))

        coil_reference.SetFileName('C:\Users\Administrator\Dropbox\Biomag\Renan\coil\coil_cti_2_scale10.obj')
        coilMapper = vtk.vtkPolyDataMapper()
        coilMapper.SetInputConnection(coil_reference.GetOutputPort())
        self.coilActor = vtk.vtkActor()
        # self.coilActor.Scale(10.0, 10.0, 10.0)
        self.coilActor.SetMapper(coilMapper)

        axes = vtk.vtkAxesActor()
        axes.SetShaftTypeToCylinder()
        axes.SetXAxisLabelText("x")
        axes.SetYAxisLabelText("y")
        axes.SetZAxisLabelText("z")
        axes.SetTotalLength(50.0, 50.0, 50.0)

        self.ren.AddActor(self.coilActor)
        self.ren.AddActor(axes)

    def rotate(self, evt):
        self.coilActor.RotateX(90)
        self.interactor.Render()
        print 'Coil orientation', self.coilActor.GetOrientation()

    def OnCalibrationMarkers(self, evt):
        import data.coordinates as co
        from numpy import matrix
        Minv = self.nav_prop[0][0]
        N = self.nav_prop[0][1]
        q1 = self.nav_prop[0][2]
        q2 = self.nav_prop[0][3]
        nav_id = self.nav_prop[1]
        tracker_init = self.nav_prop[1][0]
        tracker = self.nav_prop[1][1]
        tracker_mode = self.nav_prop[1][2]

        trck = co.Coordinates(tracker_init, tracker, tracker_mode).Returns()
        tracker = matrix([[trck[0]], [trck[1]], [trck[2]]])
        self.init_angle_plh = trck[3], trck[4], trck[5]
        img = q1 + (Minv*N)*(tracker - q2)
        coord = float(img[0]), float(img[1]), float(img[2])
        x, y, z = bases.flip_x(coord)

        if not self.ball_centers:
            self.to_translate = -x, -y, -z

        x = x + self.to_translate[0]
        y = y + self.to_translate[1]
        z = z + self.to_translate[2]

        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(4)
        ball_ref.SetCenter(x, y, z)

        self.ball_centers.append((x, y, z))

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInput(ball_ref.GetOutput())

        prop = vtk.vtkProperty()
        prop.SetColor(0,1, 1)

        #adding a new actor for the present ball
        self.staticballs.append(vtk.vtkActor())

        self.staticballs[self.ball_id].SetMapper(mapper)
        self.staticballs[self.ball_id].SetProperty(prop)

        self.ren.AddActor(self.staticballs[self.ball_id])
        self.ball_id += 1

        self.interactor.Render()

    def DirectionCosinesTest_vtkmatrix(self, evt):
        p1, p2, p3 = self.ball_centers[:3]
        dcm = self.base_creation(p1, p2, p3)

        mat4x4 = vtk.vtkMatrix4x4()
        mat4x4.DeepCopy(dcm[0][0], dcm[0][1], dcm[0][2], 0.0,
                        dcm[1][0], dcm[1][1], dcm[1][2], 0.0,
                        dcm[2][0], dcm[2][1], dcm[2][2], 0.0,
                              0.0,       0.0,       0.0, 1.0)

        self.coilActor.SetUserMatrix(mat4x4)
        print "\n===================================="
        print "orientation: ", self.coilActor.GetOrientation()
        print "====================================\n"


    def DirectionCosinesTest_eulerangles(self, evt):
        # p1, p2, p3 = self.ball_centers[:3]
        # dcm = self.base_creation(p1, p2, p3)

        dcm = self.nav_prop[0][1]

        # site http://met.fzu.edu.cn/cai/Matlab6.5/help/toolbox/aeroblks/directioncosinematrixtoeulerangles.html
        theta = np.rad2deg(-np.arcsin(dcm[0][2]))
        phi = np.rad2deg(np.arctan(dcm[1][2] / dcm[2][2]))
        psi = np.rad2deg(np.arctan(dcm[0][1] / dcm[0][0]))

        self.coilActor.RotateWXYZ(psi, 0, 0, 1)
        self.coilActor.RotateWXYZ(phi, 1, 0, 0)
        self.coilActor.RotateWXYZ(theta, 0, 1, 0)
        self.interactor.Render()

        print "\n===================================="
        print "orientation: ", self.coilActor.GetOrientation()
        print "====================================\n"


    def Reset(self, evt):
        self.ball_centers = []
        self.ball_id = 0
        self.to_translate = 0, 0, 0
        self.coilActor.SetOrientation(0, 0, 0)
        self.coilActor.SetOrigin(0, 0, 0)
        for i in range(0, len(self.staticballs)):
            self.ren.RemoveActor(self.staticballs[i])
        self.staticballs = []

    def Neuronavigate_ToggleButton(self, evt):
        p0, p1, p2 = self.ball_centers[:3]
        m = self.base_creation(p0, p1, p2)

        print "\n===================================="
        print "Pontos bobina", p0, p1, p2
        print "====================================\n"

        #vm = vtk.vtkMatrix4x4()
        #vm.SetElement(0, 0, m[0, 0])
        #vm.SetElement(0, 1, m[0, 1])
        #vm.SetElement(0, 2, m[0, 2])
        #vm.SetElement(0, 3, 0      )

        #vm.SetElement(1, 0, m[1, 0])
        #vm.SetElement(1, 1, m[1, 1])
        #vm.SetElement(1, 2, m[1, 2])
        #vm.SetElement(1, 3, 0      )

        #vm.SetElement(2, 0, m[2, 0])
        #vm.SetElement(2, 1, m[2, 1])
        #vm.SetElement(2, 2, m[2, 2])
        #vm.SetElement(2, 3, 0      )

        #vm.SetElement(3, 0, 0      )
        #vm.SetElement(3, 1, 0      )
        #vm.SetElement(3, 2, 0      )
        #vm.SetElement(3, 3, 1      )

        #self.coilActor.SetUserMatrix(vm)
        # theta == beta
        # psi == alpha
        # phi == gama
        gama = np.rad2deg(np.arctan(m[1, 2] / m[2, 2]))
        beta = np.rad2deg(np.arcsin(-m[0, 2]))
        alpha = np.rad2deg(np.arctan(m[0, 1] / m[0, 0]))

        print "Angulos", gama, beta, alpha

        self.coilActor.RotateWXYZ(alpha, 0, 1, 0)
        self.coilActor.RotateWXYZ(beta, 1, 0, 0)
        self.coilActor.RotateWXYZ(gama, 0, 0, 1)
        self.interactor.Render()

    def GetValue(self):
        size = len(self.ball_centers) - 2  # ultima casa eh pra pegar o
        # angulo inicial do plh
        presize = len(self.ball_centers) - 5
        p1, p2, p3 = self.ball_centers[presize:size]
        M, q1, Minv = db.base_creation(p1, p2, p3)
        inits_angles = self.coilActor.GetOrientation(), self.init_angle_plh, M

        coil_top = self.ball_centers[len(self.ball_centers)-1]
        coil_bottom = self.ball_centers[len(self.ball_centers)-2]
        coil_axis = np.matrix(coil_bottom[0:3]).reshape(3, 1),np.matrix(coil_top[0:3]).reshape(3, 1)

        return inits_angles, coil_axis
#===============================================================================
#===============================================================================

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
        index_list.sort()
        self.mask_list = [project.mask_dict[index].name for index in index_list]

        # Mask selection combo
        combo_mask = wx.ComboBox(self, -1, "", choices= self.mask_list,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_mask.SetSelection(len(self.mask_list)-1)
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


        # LINES 4 and 5: Checkboxes
        check_box_holes = wx.CheckBox(self, -1, _("Fill holes"))
        check_box_holes.SetValue(True)
        self.check_box_holes = check_box_holes
        check_box_largest = wx.CheckBox(self, -1, _("Keep largest region"))
        self.check_box_largest = check_box_largest

        # OVERVIEW
        # Merge all sizers and checkboxes
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fixed_sizer, 0, wx.TOP|wx.RIGHT|wx.LEFT|wx.GROW|wx.EXPAND, 5)
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
        fill_holes = self.check_box_holes.GetValue()
        keep_largest = self.check_box_largest.GetValue()
        return {"index": mask_index,
                "name": surface_name,
                "quality": quality,
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
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

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
                              evt.GetNodes())
        Publisher.sendMessage('Update window level text',
                              (self.clut_widget.window_width,
                               self.clut_widget.window_level))

    def _refresh_widget(self, pubsub_evt):
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
    def __init__(self, config):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u'Watershed'), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

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
    def __init__(self, masks):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Boolean operations"),  style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)
        self.PostCreate(pre)

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
        self.op_boolean = wx.combo.BitmapComboBox(self, -1, op_choices[0][0], choices=[])

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

        Publisher.sendMessage('Do boolean operation', (op, m1, m2))
        Publisher.sendMessage('Reload actual slice')
        Publisher.sendMessage('Refresh viewer')

        self.Close()
        self.Destroy()


class ReorientImageDialog(wx.Dialog):
    def __init__(self):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u'Image reorientation'), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

        self._init_gui()
        self._bind_events()
        self._bind_events_wx()

    def _init_gui(self):
        self.anglex = wx.TextCtrl(self, -1, "0.0", style=wx.TE_READONLY)
        self.angley = wx.TextCtrl(self, -1, "0.0", style=wx.TE_READONLY)
        self.anglez = wx.TextCtrl(self, -1, "0.0", style=wx.TE_READONLY)

        self.btnapply = wx.Button(self, -1, _("Apply"))

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer.Add(wx.StaticText(self, -1, _("Angle X")), 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer.Add(self.anglex, 0, wx.EXPAND | wx.ALL, 5)
        sizer.AddSpacer(5)

        sizer.Add(wx.StaticText(self, -1, _("Angle Y")), 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer.Add(self.angley, 0, wx.EXPAND | wx.ALL, 5)
        sizer.AddSpacer(5)

        sizer.Add(wx.StaticText(self, -1, _("Angle Z")), 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer.Add(self.anglez, 0, wx.EXPAND | wx.ALL, 5)
        sizer.AddSpacer(5)

        sizer.Add(self.btnapply, 0, wx.EXPAND | wx.ALL, 5)
        sizer.AddSpacer(5)

        self.SetSizer(sizer)
        self.Fit()

    def _bind_events(self):
        Publisher.subscribe(self._update_angles, 'Update reorient angles')
        Publisher.subscribe(self._close_dialog, 'Close reorient dialog')

    def _bind_events_wx(self):
        self.btnapply.Bind(wx.EVT_BUTTON, self.apply_reorientation)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def _update_angles(self, pubsub_evt):
        anglex, angley, anglez = pubsub_evt.data
        self.anglex.SetValue("%.2f" % np.rad2deg(anglex))
        self.angley.SetValue("%.2f" % np.rad2deg(angley))
        self.anglez.SetValue("%.2f" % np.rad2deg(anglez))

    def _close_dialog(self, pubsub_evt):
        self.Destroy()

    def apply_reorientation(self, evt):
        Publisher.sendMessage('Apply reorientation')
        self.Close()

    def OnClose(self, evt):
        Publisher.sendMessage('Disable style', const.SLICE_STATE_REORIENT)
        Publisher.sendMessage('Enable style', const.STATE_DEFAULT)
        self.Destroy()



class ImportBitmapParameters(wx.Dialog):
    from os import sys

    def __init__(self):
        pre = wx.PreDialog()

        if sys.platform == 'win32':
            size=wx.Size(380,180)
        else:
            size=wx.Size(380,210)

        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Create project from bitmap"),size=size,\
                                style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.interval = 0
        
        self.PostCreate(pre)

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
        gbs.AddStretchSpacer((1,0))

        gbs.Add(stx_orientation, (2,0), flag=flag_labels)
        gbs.Add(cb_orientation, (2,1))

        gbs.Add(stx_spacing, (3,0))
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

        gbs_button.AddStretchSpacer((0,2))
        gbs_button.Add(btn_cancel, (1,2))
        gbs_button.Add(btn_ok, (1,3))

        gbs_principal.AddSizer(gbs, (0,0), flag = wx.ALL|wx.EXPAND)
        gbs_principal.AddSizer(gbs_spacing, (1,0),  flag=wx.ALL|wx.EXPAND)
        gbs_principal.AddStretchSpacer((2,0))
        gbs_principal.AddSizer(gbs_button, (3,0), flag = wx.ALIGN_RIGHT)

        box = wx.BoxSizer()
        box.AddSizer(gbs_principal, 1, wx.ALL|wx.EXPAND, 10)
        
        p.SetSizer(box)


    def bind_evts(self):
        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
   
    def SetInterval(self, v):
        self.interval = v

    def OnOk(self, evt):
        self.Close()
        self.Destroy()

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
        Publisher.sendMessage('Open bitmap files', values)


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

        sizer.AddStretchSpacer((0, 0))
        sizer.Add(self.target_2d, (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.target_3d, (2, 0), (1, 6), flag=wx.LEFT, border=5)
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

        sizer.AddStretchSpacer((0, 0))
        sizer.Add(wx.StaticText(self, -1, _(u"2D Connectivity")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.conect2D_4, (2, 0), flag=wx.LEFT, border=7)
        sizer.Add(self.conect2D_8, (2, 1), flag=wx.LEFT, border=7)
        sizer.AddStretchSpacer((3, 0))

        if show_orientation:
            self.cmb_orientation = wx.ComboBox(self, -1, choices=(_(u"Axial"), _(u"Coronal"), _(u"Sagital")), style=wx.CB_READONLY)
            self.cmb_orientation.SetSelection(0)

            sizer.Add(wx.StaticText(self, -1, _(u"Orientation")), (4, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=5)
            sizer.Add(self.cmb_orientation, (5, 0), (1, 10), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
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

        sizer.AddStretchSpacer((0, 0))
        sizer.Add(wx.StaticText(self, -1, _(u"3D Connectivity")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.Add(self.conect3D_6, (2, 0), flag=wx.LEFT, border=9)
        sizer.Add(self.conect3D_18, (2, 1), flag=wx.LEFT, border=9)
        sizer.Add(self.conect3D_26, (2, 2), flag=wx.LEFT, border=9)
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
        print self.config.t0, self.config.t1


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

        sizer.AddStretchSpacer((0, 0))

        sizer.Add(self.use_ww_wl, (1, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.AddStretchSpacer((2, 0))

        sizer.Add(wx.StaticText(self, -1, _(u"Deviation")), (3, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.Add(wx.StaticText(self, -1, _(u"Min:")), (4, 0), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=9)
        sizer.Add(self.deviation_min, (4, 1))

        sizer.Add(wx.StaticText(self, -1, _(u"Max:")), (4, 2), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=9)
        sizer.Add(self.deviation_max, (4, 3))

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

        sizer.AddStretchSpacer((0, 0))

        sizer.Add(self.use_ww_wl, (1, 0), (1, 6), flag=wx.LEFT, border=5)

        sizer.AddStretchSpacer((2, 0))

        sizer.Add(wx.StaticText(self, -1, _(u"Multiplier")), (3, 0), (1, 3), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=5)
        sizer.Add(self.spin_mult, (3, 3), (1, 2))

        sizer.Add(wx.StaticText(self, -1, _(u"Iterations")), (4, 0), (1, 3), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT, border=5)
        sizer.Add(self.spin_iters, (4, 3), (1, 2))

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
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

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
        print "ONCLOSE"
        if self.config.dlg_visible:
            Publisher.sendMessage('Disable style', const.SLICE_STATE_MASK_FFILL)
        evt.Skip()
        self.Destroy()


class SelectPartsOptionsDialog(wx.Dialog):
    def __init__(self, config):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Select mask parts"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

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

        sizer.AddSizer(btn_sizer, 0, flag=wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT, border=5)
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
            Publisher.sendMessage('Disable style', const.SLICE_STATE_SELECT_MASK_PARTS)
        evt.Skip()
        self.Destroy()

class FFillSegmentationOptionsDialog(wx.Dialog):
    def __init__(self, config):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Region growing"), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

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

        sizer.AddStretchSpacer((0, 0))
        sizer.Add(wx.StaticText(self, -1, _(u"Parameters")), (1, 0), (1, 6), flag=wx.LEFT, border=5)
        sizer.AddStretchSpacer((2, 0))
        sizer.Add(self.panel_target, (3, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddStretchSpacer((4, 0))
        sizer.Add(self.panel2dcon, (5, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddStretchSpacer((6, 0))
        sizer.Add(self.panel3dcon, (7, 0), (1, 6), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)
        sizer.AddStretchSpacer((8, 0))

        sizer.Add(wx.StaticText(self, -1, _(u"Method")), (9, 0), (1, 1), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=7)
        sizer.Add(self.cmb_method, (9, 1), (1, 5), flag=wx.LEFT|wx.RIGHT|wx.EXPAND, border=7)

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

        sizer.AddStretchSpacer((12, 0))
        sizer.Add(self.close_btn, (13, 0), (1, 6), flag=wx.ALIGN_RIGHT|wx.RIGHT, border=5)
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
            Publisher.sendMessage('Disable style', const.SLICE_STATE_MASK_FFILL)
        evt.Skip()
        self.Destroy()


class CropOptionsDialog(wx.Dialog):
    
    def __init__(self, config):

        self.config = config

        pre = wx.PreDialog()

        if sys.platform == 'win32':
            size=wx.Size(204,165)
        else:
            size=wx.Size(205,180)

        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Crop mask"),\
                    size=size, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
                
        self.PostCreate(pre)

        self._init_gui()
        #self.config = config

    def UpdateValues(self, pubsub_evt):

        if type(pubsub_evt) == list:
            data = pubsub_evt
        else:
            data = pubsub_evt.data

        xi, xf, yi, yf, zi, zf = data

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

        gbs_principal.AddSizer(gbs, (0,0), flag = wx.ALL|wx.EXPAND)
        gbs_principal.AddStretchSpacer((1,0))
        gbs_principal.AddStretchSpacer((2,0))
        gbs_principal.AddSizer(gbs_button, (3,0), flag = wx.ALIGN_RIGHT)

        box = wx.BoxSizer()
        box.AddSizer(gbs_principal, 1, wx.ALL|wx.EXPAND, 10)
        
        p.SetSizer(box)
        
        Publisher.subscribe(self.UpdateValues, 'Update crop limits into gui')
        
        btn_ok.Bind(wx.EVT_BUTTON, self.OnOk)
        btn_cancel.Bind(wx.EVT_BUTTON, self.OnClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)


    def OnOk(self, evt):
        self.config.dlg_visible = False
        Publisher.sendMessage('Crop mask')
        Publisher.sendMessage('Disable style', const.SLICE_STATE_CROP_MASK)
        evt.Skip()

    def OnClose(self, evt):
        self.config.dlg_visible = False
        Publisher.sendMessage('Disable style', const.SLICE_STATE_CROP_MASK)
        evt.Skip()
        self.Destroy()


class FillHolesAutoDialog(wx.Dialog):
    def __init__(self, title):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

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

        self.panel_target.target_2d.SetValue(1)
        self.panel2dcon.Enable(1)
        self.panel3dcon.Enable(0)

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

        sizer.AddSizer(btn_sizer, 0, flag=wx.ALIGN_RIGHT|wx.LEFT|wx.RIGHT, border=5)

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

        data = {
            'target': target,
            'conn': conn,
            'orientation': orientation,
            'size': self.spin_size.GetValue(),
        }

        Publisher.sendMessage("Fill holes automatically", data)


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
