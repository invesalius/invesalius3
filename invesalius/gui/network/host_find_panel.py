from invesalius.gui.network.nodes_panel import NodesPanel
import wx.lib.splitter as spl
import wx

myEVT_SELECT_SERIE = wx.NewEventType()
EVT_SELECT_SERIE = wx.PyEventBinder(myEVT_SELECT_SERIE, 1)

myEVT_SELECT_SLICE = wx.NewEventType()
EVT_SELECT_SLICE = wx.PyEventBinder(myEVT_SELECT_SLICE, 1)

class HostFindPanel(wx.Panel):
    """ Host find panel. """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self._init_ui()
        self._bind_events()

    def _init_ui(self):

        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.HORIZONTAL)

        # TODO: Rever isso
        #  splitter.ContainingSizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(sizer)

        self.__image_panel = NodesPanel(splitter)
        splitter.AppendWindow(self.__image_panel)

        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def _bind_events(self):

        self.__image_panel.Bind(EVT_SELECT_SERIE, self._on_select_serie)
        #self.__image_panel.Bind(EVT_SELECT_SLICE, self._on_select_slice)

    def _on_select_serie(self, evt):

        evt.Skip()

    def _on_select_slice(self, evt):

        self.__image_panel.dicom_preview.ShowSlice(evt.GetSelectID())
        evt.Skip()