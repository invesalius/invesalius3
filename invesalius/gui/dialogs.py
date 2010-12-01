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
from wx.lib import masked
from wx.lib.wordwrap import wordwrap
import wx.lib.pubsub as ps

import constants as const
import gui.widgets.gradient as grad
import project as proj
import session as ses
import utils

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
        ps.Publisher().sendMessage("Cancel DICOM load")

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
    dlg = wx.FileDialog(None, message=_("Open Analyze File..."),
                        defaultDir="",
                        defaultFile="", wildcard=WILDCARD_ANALYZE,
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

def ShowSaveAsProjectDialog(default_filename=None):
    current_dir = os.path.abspath(".")
    dlg = wx.FileDialog(None,
                        _("Save project as..."), # title
                        "", # last used directory
                        default_filename,
                        _("InVesalius project (*.inv3)|*.inv3"),
                        wx.SAVE|wx.OVERWRITE_PROMPT)
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
    msg = _("%s is an empty directory.") % dirpath.decode("utf-8")
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

def ImportInvalidFiles():
    msg = _("There are no DICOM files in the selected directory.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def InexistentMask():
    msg = _("There is no mask of reference to create a surface.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def MaskSelectionRequiredForRemoval():
    msg = _("No masks were selected for removal.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def SurfaceSelectionRequiredForRemoval():
    msg = _("No surfaces were selected for removal.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()


def MeasureSelectionRequiredForRemoval():
    msg = _("No measures were selected for removal.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()

def MaskSelectionRequiredForDuplication():
    msg = _("No masks were selected for duplication.")
    if sys.platform == 'darwin':
        dlg = wx.MessageDialog(None, "", msg,
                                wx.ICON_INFORMATION | wx.OK)
    else:
        dlg = wx.MessageDialog(None, msg, "InVesalius 3",
                                wx.ICON_INFORMATION | wx.OK)
    dlg.ShowModal()
    dlg.Destroy()



def SurfaceSelectionRequiredForDuplication():
    msg = _("No surfaces were selected for duplication.")
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
    info.Version = "3.0 - Beta 3"
    info.Copyright = _("(c) 2007-2010 Renato Archer Information Technology Centre")
    info.Description = wordwrap(_("InVesalius is a medical imaging program for 3D reconstruction. It uses a sequence of 2D DICOM image files acquired with CT or MRI scanners. InVesalius allows for the export of 3D volumes or surfaces as STL files for creating physical models of a patient's anatomy using rapid prototyping technologies."), 350, wx.ClientDC(parent))

#       _("InVesalius is a software for medical imaging 3D reconstruction. ")+\
#       _("Its input is a sequency of DICOM 2D image files acquired with CT or MR.\n\n")+\
#       _("The software also allows generating correspondent STL files,")+\
#       _("so the user can print 3D physical models of the patient's anatomy ")+\
#       _("using Rapid Prototyping."), 350, wx.ClientDC(parent))
    info.WebSite = ("http://svn.softwarepublico.gov.br/trac/invesalius")
    info.License = _("GNU GPL (General Public License) version 2")

    info.Developers = ["Tatiana Al-Chueyr",
                       "Paulo Henrique Junqueira Amorim",
                       "Thiago Franco de Moraes"]

    info.Translators = ["Alex P. Natsios",
                        "Andreas Loupasakis",
                        "Cheng-Chia Tseng",
                        "Dimitris Glezos",
                        "Eugene Liscio",
                        u"Frédéric Lopez",
                        "Javier de Lima Moreno"
                        "Nikos Korkakakis",
                        "Massimo Crisantemo",
                        "Raul Bolliger Neto",
                        "Sebastian Hilbert",
                        "Semarang Pari"]

    info.DocWriters = ["Fabio Francisco da Silva (PT)"] 

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

INDEX_TO_EXTENSION = {0: "bmp", 1: "jpg", 2: "png", 3: "ps", 4:"povray", 5:"tiff"}
WILDCARD_SAVE_PICTURE = _("BMP image")+" (*.bmp)|*.bmp|"+\
                            _("JPG image")+" (*.jpg)|*.jpg|"+\
                            _("PNG image")+" (*.png)|*.png|"+\
                            _("PostScript document")+" (*.ps)|*.ps|"+\
                            _("POV-Ray file")+" (*.pov)|*.pov|"+\
                            _("TIFF image")+" (*.tif)|*.tif"


def ExportPicture(type_=""):
    import constants as const

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
                        wx.SAVE|wx.OVERWRITE_PROMPT)
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


