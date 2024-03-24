import wx
import time
import wx.adv as wxadv
import wx.grid as gridlib
import wx.lib.agw.pybusyinfo as PBI


class CustomDialog(wx.Dialog):
    def __init__(self, parent, message):
        super().__init__(parent, title="Confirmation", size=(250, 150))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        message_label = wx.StaticText(panel, label=message)
        sizer.Add(message_label, 0, wx.ALL | wx.CENTER, 5)
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        yes_button = wx.Button(panel, label="Yes")
        no_button = wx.Button(panel, label="No")
        button_sizer.Add(yes_button, 0, wx.ALL | wx.CENTER, 5)
        button_sizer.Add(no_button, 0, wx.ALL | wx.CENTER, 5)
        sizer.Add(button_sizer, 0, wx.CENTER)
        panel.SetSizer(sizer)
        yes_button.Bind(wx.EVT_BUTTON, self.on_yes)
        no_button.Bind(wx.EVT_BUTTON, self.on_no)

    def on_yes(self, event):
        self.EndModal(wx.ID_YES)

    def on_no(self, event):
        self.EndModal(wx.ID_NO)

class BasicCompo:

    @staticmethod
    def create_label_textbox(panel, label: str = '', text_box_value: str = '', enable: bool = True, textbox_needed: int = 1, horizontal: int = 0, **kwargs) -> list:

        if horizontal:
            sizer = wx.BoxSizer(wx.HORIZONTAL)
        else:
            sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(panel, label=label)
        if kwargs.get('label_size'):
            label.SetSize(kwargs.get('label_size'))

        if horizontal:
            sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL |
                      wx.LEFT | wx.TOP | wx.BOTTOM, border=5)
        else:
            sizer.Add(label, 0, wx.LEFT | wx.EXPAND |
                      wx.ALL | wx.TOP | wx.BOTTOM, border=1)

        textbox = wx.TextCtrl(panel, value=text_box_value,
                              style=wx.TE_LEFT | wx.TE_PROCESS_ENTER)
        textbox.Enable(enable)
        if kwargs.get('textbox_size'):
            textbox.SetSize(kwargs.get('textbox_size'))
        sizer.AddSpacer(10)  # Add spacer between label and text control
        sizer.Add(textbox, 1, wx.EXPAND | wx.RIGHT |
                  wx.TOP | wx.BOTTOM, border=1)

        # preparing response
        res = [sizer]
        if textbox_needed:
            res.append(textbox)
        return res

    @staticmethod
    def create_button(panel, label='', enable=True):
        button = wx.Button(panel, label=label)
        button.Enable(enable)
        return button
    
    @staticmethod
    def showmsg(t: int, msgs: str = 'PACS Details are Deleted') -> PBI.PyBusyInfo:
        app = wx.App(redirect=False)
        msg = msgs
        title = 'Message!'
        d = PBI.PyBusyInfo(msg, title=title)
        time.sleep(t)
        return d
    
    @staticmethod
    def create_slider(panel, label, value=100, min_value=0, max_value=100):
        slider_comp = wx.Slider(panel, value=value, minValue=min_value, maxValue=max_value, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        slider_comp.SetTickFreq(100)
        slider_comp.SetPageSize(100)
        slider_comp.SetLineSize(100)
        slider_comp.SetTick(100)
        slider_comp.SetLabel(label)
        slider_comp.SetThumbLength(25)
        slider_comp.SetValue(50)
        return slider_comp
    
