import wx
from wx.lib import masked

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
                                      | wx.PD_APP_MODAL
                                     #| wx.PD_ELAPSED_TIME
                                     #| wx.PD_ESTIMATED_TIME
                                     #| wx.PD_REMAINING_TIME
                                     )

    def Update(self, value):
        if (value == self.maximum):
            self.dlg.Destroy()
            return False
        else:
            self.dlg.Update(value)
            return True
    
