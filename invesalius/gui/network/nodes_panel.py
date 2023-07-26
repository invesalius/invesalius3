from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher
import invesalius.net.dicom as dcm_net
import invesalius.constants as const
import invesalius.session as ses
import wx.grid as gridlib
import sys
import wx

class NodesPanel(wx.Panel):
    """ Dicom Nodes Dialog. """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        
        self.__nodes = []
        self.__selected_index = None
        self.__selected_node = None

        self.__session = ses.Session()

        # Create the main vertical box sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.__find_input = wx.TextCtrl(self, size=(225, -1))
        self.__find_input.SetHint(_("Enter patient name"))
        
        find_sizer = self._create_find_box_sizer()

        buttons_sizer = self._create_buttons_box_sizer()

        hor = wx.BoxSizer(wx.HORIZONTAL)

        hor.Add(find_sizer, 0, wx.EXPAND | wx.ALL, 5)
        hor.AddStretchSpacer()
        hor.Add(buttons_sizer, 0, wx.EXPAND | wx.ALL, 5)

        main_sizer.Add(hor, 0, wx.EXPAND)

        self.__list_ctrl = self._create_list_ctrl()

        # Load values from config file
        self._load_values()
        
        # Add the grid table to the main sizer
        main_sizer.Add(self.__list_ctrl, 1, wx.GROW | wx.EXPAND)
        
        # Create the input fields
        self.__ipaddress_input = wx.TextCtrl(self, size=(225, -1))
        self.__ipaddress_input.SetHint(_("127.0.0.1"))
        self.__port_input = wx.TextCtrl(self, size=(225, -1))
        self.__port_input.SetHint(_("4242"))
        self.__aetitle_input = wx.TextCtrl(self, size=(225, -1))
        self.__aetitle_input.SetHint(_("ORTHANC"))
        self.__description_input = wx.TextCtrl(self, size=(225, -1))
        self.__description_input.SetHint(_("My local server"))

        form_sizer = self._create_form_sizer()
        
        # Add the form sizer to the main sizer
        main_sizer.Add(form_sizer, 0, wx.ALIGN_CENTER)
        
        # Set the main sizer as the sizer for the frame
        self.SetSizer(main_sizer)

        self._bind_evt()

    def _on_button_find(self, evt):
        """ Find button event. """

        if self.__selected_node is None:
            
            wx.MessageBox(_("Please, select a node."), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        dn = dcm_net.DicomNet()
        dn.SetHost(self.__selected_node['ipaddress'])
        dn.SetPort(self.__selected_node['port'])
        dn.SetSearchWord(self.__find_input.GetValue())
        Publisher.sendMessage('Populate tree', patients=dn.RunCFind())

    def _add_node(self, node):
        """ Add a node to the nodes list. """
        
        self.__nodes.append(node)

    def _remove_node(self, idx):
        """ Remove a node from the nodes list. """

        del self.__nodes[idx]

    def _load_values(self):
        """ Load the values from the config file. """

        nodes = self.__session.GetConfig('nodes') \
            if self.__session.GetConfig('nodes') \
            else []

        for node in nodes:
            
            # Add node row to the grid
            self._add_node_to_list(node)

            # Add node row to the nodes list
            self._add_node(node)

        self.__selected_node = self.__session.GetConfig('selected_node') \
            if self.__session.GetConfig('selected_node') \
            else None

        self.__selected_index = self.__nodes.index(self.__selected_node) \
            if self.__selected_node \
            else None

        if self.__selected_index is not None:
            self.__list_ctrl.CheckItem(self.__selected_index, True)

    def _create_find_box_sizer(self):
        """ Create the find box sizer. """

        find_sizer = wx.BoxSizer(wx.HORIZONTAL) 

        btn_find = wx.Button(self, label="Search")
        btn_find.Bind(wx.EVT_BUTTON, self._on_button_find)
        
        find_sizer.Add(self.__find_input, 0, wx.ALL, 5) 
        find_sizer.Add(btn_find, 0, wx.ALL, 5)

        return find_sizer

    def _create_buttons_box_sizer(self):
        """ Create the buttons. """

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        check_button = wx.Button(self, label="Check status")
        check_button.Bind(wx.EVT_BUTTON, self._on_button_check)

        add_button = wx.Button(self, label="New")
        add_button.Bind(wx.EVT_BUTTON, self._on_add_button)

        remove_button = wx.Button(self, label="Remove")
        remove_button.Bind(wx.EVT_BUTTON, self._on_remove_button)

        # Add buttons to sizer
        button_sizer.Add(check_button, 0, wx.ALL, 5)
        button_sizer.Add(add_button, 0, wx.ALL, 5)
        button_sizer.Add(remove_button, 0, wx.ALL, 5)

        return button_sizer

    def _create_list_ctrl(self):

        list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        
        list_ctrl.InsertColumn(0, _("Active"))
        list_ctrl.InsertColumn(1, _("IP Address"))
        list_ctrl.InsertColumn(2, _("Port"))
        list_ctrl.InsertColumn(3, _("AE Title"))
        list_ctrl.InsertColumn(4, _("Description"))
        list_ctrl.InsertColumn(5, _("Status"))
        list_ctrl.EnableCheckBoxes()

        return list_ctrl

    def _bind_evt(self):
        """ Bind events. """

        self.Bind(wx.EVT_LIST_ITEM_CHECKED, self._on_item_selected, self.__list_ctrl)
        self.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self._on_item_deselected, self.__list_ctrl)

    def _add_node_to_list(self, node):
        """ add node to list. """

        try:

            index = self.__list_ctrl.InsertItem(sys.maxsize, "")
        
        except (OverflowError, AssertionError):
            
            index = self.__list_ctrl.InsertItem(sys.maxsize, "")

        self.__list_ctrl.SetItem(index, 0, "", 0)
        self.__list_ctrl.SetItem(index, 1, node["ipaddress"])
        self.__list_ctrl.SetItem(index, 2, node["port"])
        self.__list_ctrl.SetItem(index, 3, node["aetitle"])
        self.__list_ctrl.SetItem(index, 4, node["description"])
        self.__list_ctrl.SetItem(index, 5, "-")

    def _on_button_check(self, evt):
        """ check status button handler """

        if self.__selected_node is None:

            wx.MessageBox(_("Please select a node"), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        dn = dcm_net.DicomNet()
        dn.SetHost(self.__selected_node['ipaddress'])
        dn.SetPort(self.__selected_node['port'])

        ok = dn.RunCEcho()
        self.__list_ctrl.SetItem(self.__selected_index, 5, _("ok")) if ok\
            else self.__list_ctrl.SetItem(self.__selected_index, 5, _("error"))

    def _on_item_deselected(self, evt):
        """ unchecked item handler """

        self.__session.SetConfig('selected_node', {})

        self.__selected_index = None
        self.__selected_node = None

    def _on_item_selected(self, evt):
        """ checked item handler """

        idx = evt.GetIndex()
        count_items = self.__list_ctrl.GetItemCount()
        for index in range(count_items):
            is_checked = self.__list_ctrl.IsItemChecked(index)
            if index != idx and is_checked:
                self.__list_ctrl.CheckItem(index, False)

        self.__session.SetConfig('selected_node', self.__nodes[idx])

        self.__selected_index = idx
        self.__selected_node = self.__nodes[idx]

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

        return form_sizer

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
        self._add_node_to_list(node)

        # Add node row to the nodes list
        self._add_node(node)

        # Save the nodes list to the config file
        self.__session.SetConfig('nodes', self.__nodes)

        # Clear the input fields
        self.__ipaddress_input.Clear()
        self.__port_input.Clear()
        self.__aetitle_input.Clear()
        self.__description_input.Clear()

    def _on_remove_button(self, event):
        """ Handler for the "Remove" button. """

        if self.__selected_index is None:

            wx.MessageBox(_("Please select a node"), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        # Remove node from the grid
        self.__list_ctrl.DeleteItem(self.__selected_index)

        # Remove node from the nodes list
        self._remove_node(self.__selected_index)

        self.__selected_index = None
        self.__selected_node = None

        # Updates nodes list and selected node in the config file
        self.__session.SetConfig('selected_node', {})
        self.__session.SetConfig('nodes', self.__nodes)