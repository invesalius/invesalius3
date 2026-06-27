import sys

import invesalius.constants as const
import invesalius.session as ses
import wx
import wx.grid as gridlib
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher

class DicomNodes(wx.Dialog):
    def __init__(
        self,
        parent,
        id_=-1,
        title=_("Dicom Nodes"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    ):
        super().__init__(parent, id_, title, style=style)

        panel = wx.Panel(self)

        # Create the main vertical box sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create the grid table
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(0, 4)  # 5 rows, 2 columns

        # hide numbers row
        self.grid.HideRowLabels()

        # set header labels
        self.grid.SetColLabelValue(0, "IP ADDRESS")
        self.grid.SetColLabelValue(1, "PORT")
        self.grid.SetColLabelValue(2, "AE TITLE")
        self.grid.SetColLabelValue(3, "DESCRIPTION")

        # make column fill the entire grid wite space
        self.grid.AutoSizeColumns()
        
        # Add the grid table to the main sizer
        main_sizer.Add(self.grid, 1, wx.EXPAND | wx.ALL, 5)
        
        # Create the horizontal form sizer
        form_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Create the input fields
        self.__ipaddress_label = wx.StaticText(self, label="IP Address")
        self.__ipaddress_input = wx.TextCtrl(self)

        sizer1 = wx.BoxSizer(wx.VERTICAL)
        sizer1.Add(self.__ipaddress_label, 0, wx.ALL, 5)
        sizer1.Add(self.__ipaddress_input, 0, wx.ALL, 5)
        
        self.__port_label = wx.StaticText(self, label="Port")
        self.__port_input = wx.TextCtrl(self)

        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer2.Add(self.__port_label, 0, wx.ALL, 5)
        sizer2.Add(self.__port_input, 0, wx.ALL, 5)

        self.__aetitle_label = wx.StaticText(self, label="AE Title:")
        self.__aetitle_input = wx.TextCtrl(self)

        sizer3 = wx.BoxSizer(wx.VERTICAL)
        sizer3.Add(self.__aetitle_label, 0, wx.ALL, 5)
        sizer3.Add(self.__aetitle_input, 0, wx.ALL, 5)

        self.__description_label = wx.StaticText(self, label="Description")
        self.__description_input = wx.TextCtrl(self)

        sizer4 = wx.BoxSizer(wx.VERTICAL)
        sizer4.Add(self.__description_label, 0, wx.ALL, 5)
        sizer4.Add(self.__description_input, 0, wx.ALL, 5)
        
        form_sizer.Add(sizer1, 0, wx.ALL, 5)
        form_sizer.Add(sizer2, 0, wx.ALL, 5)
        form_sizer.Add(sizer3, 0, wx.ALL, 5)
        form_sizer.Add(sizer4, 0, wx.ALL, 5)
        
        # Create the "Add" button
        add_button = wx.Button(self, label="Add")
        add_button.Bind(wx.EVT_BUTTON, self.on_add_button)
        
        # Add the button to the form sizer
        form_sizer.Add(add_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        
        # Add the form sizer to the main sizer
        main_sizer.Add(form_sizer, 0, wx.ALIGN_CENTER)
        
        # Set the main sizer as the sizer for the frame
        self.SetSizer(main_sizer)
        
        # Automatically adjust the layout of the frame
        main_sizer.Fit(self)

        self.SetSize(600, 350)
        self.Center()
    
    def on_add_button(self, event):
        # Get the values from the input fields
        ipaddress = self.__ipaddress_input.GetValue()
        port = self.__port_input.GetValue()
        aetitle = self.__aetitle_input.GetValue()
        description = self.__description_input.GetValue()

        # Add the values to the grid
        self.grid.AppendRows(1)
        self.grid.SetCellValue(self.grid.GetNumberRows() - 1, 0, ipaddress)
        self.grid.SetCellValue(self.grid.GetNumberRows() - 1, 1, port)
        self.grid.SetCellValue(self.grid.GetNumberRows() - 1, 2, aetitle)
        self.grid.SetCellValue(self.grid.GetNumberRows() - 1, 3, description)

        # Clear the input fields
        self.__ipaddress_input.Clear()
        self.__port_input.Clear()
        self.__aetitle_input.Clear()
        self.__description_input.Clear()