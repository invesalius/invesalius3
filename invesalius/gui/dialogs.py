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
import sys

import wx
from wx.lib import masked
import wx.lib.pubsub as ps

import project

class NumberDialog(wx.Dialog):
    def __init__(self, message, value=0):
        pre = wx.PreDialog()
        pre.Create(None, -1, "InVesalius 3", size=wx.DefaultSize, pos=wx.DefaultPosition, 
                    style=wx.DEFAULT_DIALOG_STYLE)
        self.PostCreate(pre)

        # Static text which contains message to user
        print "message: ", message
        label = wx.StaticText(self, -1, message)

        # Numeric value to be changed by user
        num_ctrl = masked.NumCtrl(self, value=value, integerWidth=3,
                                    fractionWidth=2, allowNegative=True)
        self.num_ctrl = num_ctrl

        # Buttons       
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetHelpText("Above value will be applied.")
        btn_ok.SetDefault()

        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_cancel.SetHelpText("Value will not be applied.)")

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
    def __init__(self, maximum):
        self.title = "InVesalius 3"
        self.msg = "Loading DICOM files"
        self.maximum = maximum
        self.current = 0
        self.style = wx.PD_CAN_ABORT | wx.PD_APP_MODAL
        self.dlg = wx.ProgressDialog(self.title,
                                     self.msg,
                                     maximum = self.maximum,
                                     parent = None,
                                     style = wx.PD_CAN_ABORT
                                      | wx.PD_APP_MODAL,
                                     #| wx.PD_ELAPSED_TIME
                                     #| wx.PD_ESTIMATED_TIME
                                     #| wx.PD_REMAINING_TIME
                                     )
        
        self.dlg.Bind(wx.EVT_BUTTON, self.Cancel)
        self.dlg.SetSize(wx.Size(250,150))
        
    def Cancel(self, evt):
        ps.Publisher().sendMessage("Cancel DICOM load")
                
    def Update(self, value, message):
        if(int(value) != self.maximum):  
            try:
                self.dlg.Update(value,message)
            #TODO:
            #Exception in the Windows XP 64 Bits with wxPython 2.8.10
            except(wx._core.PyAssertionError):
                pass
            return True
        else:
            return False
                     
    def Close(self):
        self.dlg.Destroy()






#---------
WILDCARD_OPEN = "InVesalius 3 project (*.inv3)|*.inv3|"\
                "All files (*.*)|*.*"

def ShowOpenProjectDialog():
    # Default system path
    if sys.platform == 'win32':
        default_path = ""
    else:
        default_path = os.getcwd()

    dlg = wx.FileDialog(None, message="Open InVesalius 3 project...",
                        defaultDir=default_path,
                        defaultFile="", wildcard=WILDCARD_OPEN,
                        style=wx.OPEN|wx.CHANGE_DIR)

    # In OSX this filter is not working - wxPython 2.8.10 problem
    if sys.platform != 'darwin':
        dlg.SetFilterIndex(0)
    else:
        dlg.SetFilterIndex(1)

    # Show the dialog and retrieve the user response. If it is the OK response,
    # process the data.
    filepath = None
    if dlg.ShowModal() == wx.ID_OK:
        # This returns a Python list of files that were selected.
        filepath = dlg.GetPath()

    # Destroy the dialog. Don't do this until you are done with it!
    # BAD things can happen otherwise!
    dlg.Destroy()
    return filepath

def ShowImportDirDialog():
    dlg = wx.DirDialog(None, "Choose a DICOM folder:", "",
                        style=wx.DD_DEFAULT_STYLE
                        | wx.DD_DIR_MUST_EXIST
                        | wx.DD_CHANGE_DIR)

    path = None
    if dlg.ShowModal() == wx.ID_OK:
        path = dlg.GetPath()
        
    # Only destroy a dialog after you're done with it.
    dlg.Destroy()
    return path

def ShowSaveAsProjectDialog(default_filename=None):
    dlg = wx.FileDialog(None,
                        "Save project as...", # title
                        "", # last used directory
                        default_filename,
                        "InVesalius project (*.inv3)|*.inv3",
                        wx.SAVE|wx.OVERWRITE_PROMPT)
    #dlg.SetFilterIndex(0) # default is VTI

    filename = None                 
    if dlg.ShowModal() == wx.ID_OK:
        filename = dlg.GetPath()
        extension = "inv3"
        if sys.platform != 'win32':
            if filename.split(".")[-1] != extension:
                filename = filename + "." + extension
    return filename

def SaveChangesDialog(filename):
    dlg = wx.MessageDialog(None,
                           "InVesalius 3",
                           "Save changes to "+filename+"?",
                            wx.YES | wx.NO | wx.CANCEL | wx.ICON_INFORMATION)

    if dlg.ShowModal() == wx.ID_YES:
        return 1
    elif dlg.ShowModal() == wx.ID_NO:
        return 0
    else:
        return -1

