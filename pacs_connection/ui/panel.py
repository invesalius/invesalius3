import wx
import sys
import webbrowser
from pacs_connection.ui.search_download import Browse
from pacs_connection.ui.upload import UploadFiles
from pacs_connection.ui.pacs_config import Configuration

class NetPanel(wx.Frame):

    def __init__(self):
        super().__init__(parent=None, size= (-1,300), title='Network Panel')
        self.panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.create_ui()
        self.panel.SetSizer(self.main_sizer)

    def create_ui(self):
        #self.dummy_menu()
        self.create_menu()

    def create_menu(self):
        sizer = wx.GridBagSizer(1, 1)
        self.browse_button = wx.Button(self.panel, label='Browse')
        self.upload_button = wx.Button(self.panel, label='Upload')
        self.config_button = wx.Button(self.panel, label='Configuration')
        self.help_button = wx.Button(self.panel, label='Help')
        sizer.Add(self.browse_button, pos=(3,4), flag=wx.ALL, border=5)
        sizer.Add(self.upload_button, pos=(3,8), flag=wx.ALL, border=5)
        sizer.Add(self.config_button, pos=(5,4), flag=wx.ALL, border=5)
        sizer.Add(self.help_button, pos=(5,8), flag=wx.ALL, border=5)
        #add this sizer in the middle of the main sizer
        self.main_sizer.Add(sizer, 0, wx.ALL|wx.EXPAND | wx.CentreX | wx.CentreY, 5)

        #mapping to action
        self.browse_button.Bind(wx.EVT_BUTTON, self.on_browse)
        self.upload_button.Bind(wx.EVT_BUTTON, self.on_upload)
        self.config_button.Bind(wx.EVT_BUTTON, self.on_config)
        self.help_button.Bind(wx.EVT_BUTTON, self.on_help)

    def on_browse(self, event):
        pop = Browse()
        #close current panel
        self.Close()
        pop.Show()
        pop.Bind(wx.EVT_CLOSE, lambda event : pop.Destroy())

    def on_upload(self, event):
        pop = UploadFiles()
        self.Close()
        pop.Show()
        pop.Bind(wx.EVT_CLOSE, lambda event : pop.Destroy())

    def on_config(self, event):
        pop = Configuration()
        self.Close()
        pop.Show()
        pop.Bind(wx.EVT_CLOSE, lambda event : pop.Destroy())
    
    def on_help(self, event):
        # TODO: add help page
        webbrowser.open('https://github.com/invesalius/invesalius3')
        self.Close()



if __name__ == '__main__':
    app = wx.App()
    frame = NetPanel()
    frame.Show()
    app.MainLoop()
    
