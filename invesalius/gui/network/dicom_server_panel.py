from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher
import invesalius.constants as const
import invesalius.session as ses
import sys
import wx

class DicomServerPanel(wx.Panel):
    """ Dicom Server Panel. """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        # Create the input fields
        self.__path = wx.DirPickerCtrl(self,
            wx.ID_ANY,
            path="",
            message="Select a folder",
            style=wx.DIRP_USE_TEXTCTRL)
        self.__ae_input = wx.TextCtrl(self)
        self.__port_input = wx.TextCtrl(self)

        # Load values from config file
        self._load_values()

        # Create the controls static box sizer
        server_sizer = self._create_server_sizer()
        picker_sizer = self._create_picker_sizer()

        # Adds controls static sizer to main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(server_sizer, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(picker_sizer, flag=wx.EXPAND|wx.ALL, border=10)
        
        # Set the main sizer
        self.SetSizer(sizer)
        
        # Set the size of the dialog and center it
        self.SetSize(300, 250)
        self.Center()

    def as_dict(self):
        """ Returns the values as a dictionary. """

        return {
            const.SERVER_AETITLE: self.__ae_input.GetValue(),
            const.SERVER_PORT: self.__port_input.GetValue(),
            const.STORE_PATH: self.__path.GetPath()
        }

    def _load_values(self):
        """ Load the values from the config file. """

        session = ses.Session()

        ae_title = session.GetConfig('server_aetitle') \
            if session.GetConfig('server_aetitle') \
            else 'INVESALIUS'

        port = session.GetConfig('server_port') \
            if session.GetConfig('server_port') \
            else '5000'

        path = session.GetConfig('store_path') \
            if session.GetConfig('store_path') \
            else ''

        self.__ae_input.SetValue(ae_title)
        self.__port_input.SetValue(port)
        self.__path.SetPath(path)

    def _create_picker_sizer(self):

        static_box = wx.StaticBox(self, label="Path")

        static_box_sizer = wx.StaticBoxSizer(static_box, wx.VERTICAL)

        static_box_sizer.Add(self.__path, flag=wx.EXPAND|wx.ALL, border=5)

        return static_box_sizer

    def _create_server_sizer(self):
        """ Creates a static box sizer with the controls. """

        static_box = wx.StaticBox(self, label="Server")

        static_box_sizer = wx.StaticBoxSizer(static_box, wx.VERTICAL)

        static_box_sizer.Add(wx.StaticText(self, label="AE Title"), flag=wx.ALL, border=5)
        static_box_sizer.Add(self.__ae_input, flag=wx.EXPAND|wx.ALL, border=5)
        static_box_sizer.Add(wx.StaticText(self, label="PORT"), flag=wx.ALL, border=5)
        static_box_sizer.Add(self.__port_input, flag=wx.EXPAND|wx.ALL, border=5)

        return static_box_sizer