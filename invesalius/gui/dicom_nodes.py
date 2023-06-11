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

        self.__nodes = []

        # Create the main vertical box sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.__grid = self._create_grid_table()

        # grid column size event handler
        self.Bind(wx.EVT_SIZE, self.on_size)
        
        # Add the grid table to the main sizer
        main_sizer.Add(self.__grid, 1, wx.EXPAND | wx.ALL, 5)
        
        # Create the input fields
        self.__ipaddress_input = wx.TextCtrl(self)
        self.__port_input = wx.TextCtrl(self)
        self.__aetitle_input = wx.TextCtrl(self)
        self.__description_input = wx.TextCtrl(self)

        form_sizer = self._create_form_sizer()
        
        # Add the form sizer to the main sizer
        main_sizer.Add(form_sizer, 0, wx.ALIGN_CENTER)
        
        # Set the main sizer as the sizer for the frame
        self.SetSizer(main_sizer)

        self.SetSize(600, 350)
        self.Center()

    def _add_node(self, node):
        """ Add a node to the nodes list. """
        
        self.__nodes.append(node)

    @property
    def nodes(self):
        """ Return the nodes list. """

        return self.__nodes

    def _load_values(self):
        """ Load the values from the config file. """

        session = ses.Session()

        nodes = session.GetConfig('nodes') \
            if session.GetConfig('nodes') \
            else []

        for node in nodes: self._add_row_to_grid(node)

    def _create_form_sizer(self):
        """ Create the form sizer. """

        form_sizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer1 = wx.BoxSizer(wx.VERTICAL)
        sizer1.Add(wx.StaticText(self, label="IP Address"), 0, wx.ALL, 5)
        sizer1.Add(self.__ipaddress_input, 0, wx.ALL, 5)
        
        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer2.Add(wx.StaticText(self, label="Port"), 0, wx.ALL, 5)
        sizer2.Add(self.__port_input, 0, wx.ALL, 5)

        sizer3 = wx.BoxSizer(wx.VERTICAL)
        sizer3.Add(wx.StaticText(self, label="AE Title"), 0, wx.ALL, 5)
        sizer3.Add(self.__aetitle_input, 0, wx.ALL, 5)

        sizer4 = wx.BoxSizer(wx.VERTICAL)
        sizer4.Add(wx.StaticText(self, label="Description"), 0, wx.ALL, 5)
        sizer4.Add(self.__description_input, 0, wx.ALL, 5)
        
        form_sizer.Add(sizer1, 0, wx.ALL, 5)
        form_sizer.Add(sizer2, 0, wx.ALL, 5)
        form_sizer.Add(sizer3, 0, wx.ALL, 5)
        form_sizer.Add(sizer4, 0, wx.ALL, 5)
        
        # Create the "Add" button
        add_button = wx.Button(self, label="Add")
        add_button.Bind(wx.EVT_BUTTON, self._on_add_button)
        
        # Add the button to the form sizer
        form_sizer.Add(add_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        return form_sizer

    def _create_grid_table(self):
        """ Create the grid table. """

        grid = gridlib.Grid(self)
        grid.CreateGrid(0, 4)  # 0 rows, 4 columns

        # hide numbers row
        grid.HideRowLabels()

        # set header labels
        grid.SetColLabelValue(0, "IP ADDRESS")
        grid.SetColLabelValue(1, "PORT")
        grid.SetColLabelValue(2, "AE TITLE")
        grid.SetColLabelValue(3, "DESCRIPTION")

        return grid

    def set_grid_column_sizes(self):
        """ Set the column sizes based on the grid width. """

        width = self.__grid.GetClientSize()[0]  # Get grid width
        col_count = self.__grid.GetNumberCols()
        col_width = (width) / col_count
        
        for col in range(col_count):
            self.__grid.SetColSize(col, col_width)
    
    def on_size(self, event):
        """ Handler for the wx.EVT_SIZE event. """

        self.set_grid_column_sizes()
        event.Skip()

    def _on_add_button(self, event):
        """ Handler for the "Add" button. """

        ipaddress = self.__ipaddress_input.GetValue()
        port = self.__port_input.GetValue()
        aetitle = self.__aetitle_input.GetValue()
        description = self.__description_input.GetValue()

        node = {
            "ipaddress": ipaddress,
            "port": port,
            "aetitle": aetitle,
            "description": description,
        }

        # Add node row to the grid
        self._add_row_to_grid(node)

        # Add node row to the nodes list
        self._add_node(node)

        # Clear the input fields
        self.__ipaddress_input.Clear()
        self.__port_input.Clear()
        self.__aetitle_input.Clear()
        self.__description_input.Clear()

    def _add_row_to_grid(self, node):
        """ Add a row to the grid. """

        self.__grid.AppendRows(1)
        self.__grid.SetCellValue(self.__grid.GetNumberRows() - 1, 0, node["ipaddress"])
        self.__grid.SetCellValue(self.__grid.GetNumberRows() - 1, 1, node["port"])
        self.__grid.SetCellValue(self.__grid.GetNumberRows() - 1, 2, node["aetitle"])
        self.__grid.SetCellValue(self.__grid.GetNumberRows() - 1, 3, node["description"])