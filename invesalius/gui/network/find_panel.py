from invesalius.pubsub import pub as Publisher
import invesalius.net.dicom as dcm_net
import invesalius.session as ses
import wx

class FindPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        session = ses.Session()
        self.__selected_node = session.GetConfig('selected_node') \
            if session.GetConfig('selected_node') \
            else None

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_word_label = wx.BoxSizer(wx.HORIZONTAL)
        sizer_word_label.Add((5, 0), 0, wx.EXPAND|wx.HORIZONTAL)
        find_label = wx.StaticText(self, -1, _("Word"))
        sizer_word_label.Add(find_label)
        
        sizer_txt_find = wx.BoxSizer(wx.HORIZONTAL) 
        sizer_txt_find.Add((5, 0), 0, wx.EXPAND|wx.HORIZONTAL)
        self.find_txt = wx.TextCtrl(self, -1,size=(225, -1))

        self.btn_find = wx.Button(self, -1, _("Search"))
        
        sizer_txt_find.Add(self.find_txt) 
        sizer_txt_find.Add(self.btn_find)

        self.sizer.Add((0, 5), 0, wx.EXPAND|wx.HORIZONTAL)
        self.sizer.Add(sizer_word_label)
        self.sizer.Add(sizer_txt_find)

        #self.sizer.Add(self.serie_preview, 1, wx.EXPAND | wx.ALL, 5)
        #self.sizer.Add(self.dicom_preview, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Fit(self)

        self.SetSizer(self.sizer)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self._bind_gui_evt()

    def _bind_gui_evt(self):

        #self.serie_preview.Bind(dpp.EVT_CLICK_SERIE, self.OnSelectSerie)
        #self.dicom_preview.Bind(dpp.EVT_CLICK_SLICE, self.OnSelectSlice)
        self.Bind(wx.EVT_BUTTON, self._on_button_find, self.btn_find)

    def _on_button_find(self, evt):
        """ Find button event. """

        if self.__selected_node is None:
            
            wx.MessageBox(_("Please, select a node."), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        dn = dcm_net.DicomNet()
        dn.SetHost(self.__selected_node['ipaddress'])
        dn.SetPort(self.__selected_node['port'])
        dn.SetAETitle(self.__selected_node['aetitle'])
        dn.SetSearchWord(self.find_txt.GetValue())
        Publisher.sendMessage('Populate tree', patients=dn.RunCFind())