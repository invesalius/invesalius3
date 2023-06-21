import invesalius.net.dicom as dcm_net
import invesalius.session as ses
import sys
import wx

class NodesPanel(wx.Panel):
    """ Nodes panel. """

    def __init__(self, parent):
        super().__init__(parent, -1)

        self.__session = ses.Session()

        self.__selected_index = None

        self.__list_ctrl = self._create_list_ctrl()

        session = ses.Session()
        nodes = session.GetConfig('nodes') \
            if session.GetConfig('nodes') \
            else []

        for node in nodes: self._add_node_to_list(node)

        self.__nodes = nodes

        self._load_values()

        self.__btn_check = wx.Button(self, label="Check status")

        sizer_btn = wx.BoxSizer(wx.HORIZONTAL)
        sizer_btn.Add(self.__btn_check, 0, wx.ALIGN_CENTER)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.__list_ctrl, 85, wx.GROW|wx.EXPAND)
        sizer.Add(sizer_btn, 15)
        sizer.Fit(self)

        self.SetSizer(sizer)

        self._bind_evt()
    
    def _load_values(self):
        """ Load the values from the config file. """

        selected_node = self.__session.GetConfig('selected_node') \
            if self.__session.GetConfig('selected_node') \
            else None

        self.__selected_index = self.__nodes.index(selected_node) \
            if selected_node \
            else None

        if self.__selected_index is not None:
            self.__list_ctrl.CheckItem(self.__selected_index, True)

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
        self.Bind(wx.EVT_BUTTON, self._on_button_check, self.__btn_check)

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

        if self.__selected_index is None:

            wx.MessageBox(_("Please select a node"), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        selected = self.__nodes[self.__selected_index]

        dn = dcm_net.DicomNet()
        dn.SetHost(selected['ipaddress'])
        dn.SetPort(selected['port'])

        ok = dn.RunCEcho()
        self.__list_ctrl.SetItem(self.__selected_index, 5, _("ok")) if ok else self.__list_ctrl.SetItem(self.__selected_index, 5, _("error"))

    def _on_item_deselected(self, evt):
        """ unchecked item handler """

        self.__session.SetConfig('selected_node', {})

        self.__selected_index = None

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