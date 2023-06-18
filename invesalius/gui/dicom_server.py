import sys

import invesalius.constants as const
import invesalius.session as ses
import wx
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher

class DicomServer(wx.Dialog):
    """ Dicom Server Dialog. """

    def __init__(
        self,
        parent,
        id_=-1,
        title=_("Dicom Server"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    ):
        super().__init__(parent, id_, title, style=style)

        # Create the input fields
        self.__ae_input = wx.TextCtrl(self)
        self.__port_input = wx.TextCtrl(self)

        self.__buttons_sizer = self._create_buttons_box_sizer()

        # Load values from config file
        self._load_values()

        # Create the controls static box sizer
        static_box_sizer = self._create_static_box_sizer()

        # Adds controls static sizer to main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(static_box_sizer, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        
        # Set the main sizer
        self.SetSizer(sizer)
        
        # Set the size of the dialog and center it
        self.SetSize(300, 250)
        self.Center()

    @property
    def ae_title(self):
        return self.__ae_input.GetValue()

    @property
    def port(self):
        return self.__port_input.GetValue()

    def _load_values(self):
        """ Load the values from the config file. """

        session = ses.Session()

        ae_title = session.GetConfig('server_aetitle') \
            if session.GetConfig('server_aetitle') \
            else 'INVESALIUS'

        port = session.GetConfig('server_port') \
            if session.GetConfig('server_port') \
            else '5000'

        self.__ae_input.SetValue(ae_title)
        self.__port_input.SetValue(port)

    def _create_buttons_box_sizer(self):
        """ Create the buttons. """

        # Create the sizer
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Save and cancel buttons
        save_button = wx.Button(self, wx.ID_OK)
        save_button.SetDefault()
        cancel_button = wx.Button(self, wx.ID_CANCEL)

        # Add buttons to sizer
        button_sizer.Add(cancel_button, 0, wx.ALL, 5)
        button_sizer.Add(save_button, 0, wx.ALL, 5)

        return button_sizer

    def _create_static_box_sizer(self):
        """ Creates a static box sizer with the controls. """

        static_box = wx.StaticBox(self, label="Form")

        static_box_sizer = wx.StaticBoxSizer(static_box, wx.VERTICAL)

        static_box_sizer.Add(wx.StaticText(self, label="AE Title"), flag=wx.ALL, border=5)
        static_box_sizer.Add(self.__ae_input, flag=wx.EXPAND|wx.ALL, border=5)
        static_box_sizer.Add(wx.StaticText(self, label="PORT"), flag=wx.ALL, border=5)
        static_box_sizer.Add(self.__port_input, flag=wx.EXPAND|wx.ALL, border=5)
        static_box_sizer.Add(self.__buttons_sizer, flag=wx.ALIGN_RIGHT|wx.ALL, border=5)

        return static_box_sizer