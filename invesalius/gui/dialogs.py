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

import wx
import wx.combo
from wx.lib import masked
from wx.lib.agw import floatspin
from wx.lib.wordwrap import wordwrap
from wx.lib.pubsub import pub as Publisher

import constants as const
import gui.widgets.gradient as grad
import project as proj
import session as ses
import utils

from gui.widgets.clut_imagedata import CLUTImageDataWidget, EVT_CLUT_NODE_CHANGED

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



#---------
WILDCARD_OPEN = "InVesalius 3 project (*.inv3)|*.inv3|"\
                "All files (*.*)|*.*"

WILDCARD_ANALYZE = "Analyze (*.hdr)|*.hdr|"\
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
    except(wx._core.PyAssertionError): #FIX: win64
        filepath = dlg.GetPath()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    os.chdir(current_dir)
    return filepath


def ShowOpenAnalyzeDialog():
    # Default system path
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None, message=_("Open Analyze file"),
                        defaultDir="",
                        defaultFile="", wildcard=WILDCARD_ANALYZE,
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
    except(wx._core.PyAssertionError): #FIX: win64
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

class NewMask(wx.Dialog):
    def __init__(self,
                 parent=None,
                 ID=-1,
                 title="InVesalius 3",
                 size=wx.DefaultSize,
                 pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE,
                 useMetal=False):
        import constants as const
        import data.mask as mask
        import project as prj

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
        import project as prj
        proj = prj.Project()
        (thresh_min, thresh_max) = proj.threshold_modes[evt.GetString()]
        self.gradient.SetMinimun(thresh_min)
        self.gradient.SetMaximun(thresh_max)

    def OnSlideChanged(self, evt):
        import project as prj
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
        import constants as const
        import data.surface as surface
        import project as prj

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
    import constants as const
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
        mask = proj.Project().mask_dict[evt.mask_index]
        self.ca.mask_edited = mask.was_edited
        self.ca.ReloadMethodsOptions()

    def GetValue(self):
        return {"method": self.ca.GetValue(),
                "options": self.nsd.GetValue()}

class SurfaceCreationOptionsPanel(wx.Panel):
    def __init__(self, parent, ID=-1):
        import constants as const
        import data.surface as surface
        import project as prj

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

        self.min_weight = floatspin.FloatSpin(self, -1, value=0.2, min_val=0.0,
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

        icon_folder = '../icons/'
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

        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u"Create project from bitmap"),size=wx.Size(380,220),\
                                style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT|wx.STAY_ON_TOP)

        self.interval = 0
        
        self.PostCreate(pre)

        self._init_gui()

        self.bind_evts()
        self.CenterOnScreen()


    def _init_gui(self):
        
        import project as prj
        
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


class FFillOptionsDialog(wx.Dialog):
    def __init__(self, config):
        pre = wx.PreDialog()
        pre.Create(wx.GetApp().GetTopWindow(), -1, _(u'Floodfill'), style=wx.DEFAULT_DIALOG_STYLE|wx.FRAME_FLOAT_ON_PARENT)
        self.PostCreate(pre)

        self.config = config

        self._init_gui()

    def _init_gui(self):
        sizer = wx.GridBagSizer(3, 1)

        flag_labels = wx.ALIGN_RIGHT  | wx.ALIGN_CENTER_VERTICAL

        self.target = wx.RadioBox(self, -1, _(u"Target"),
                                 choices=[_(u"Slice"), _(u"Volume")],
                                 style=wx.NO_BORDER | wx.HORIZONTAL)

        if self.config.target == "2D":
            self.target.SetSelection(0)
        else:
            self.target.SetSelection(1)

        sizer.Add(self.target, (0, 0))

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.Layout()

        self.target.Bind(wx.EVT_RADIOBOX, self.OnSetTarget)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnSetTarget(self, evt):
        if self.target.GetSelection() == 0:
            self.config.target = "2D"
        else:
            self.config.target = "3D"

    def OnClose(self, evt):
        self.config.dlg_visible = False
        evt.Skip()
