# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------
import wx
import wx.gizmos as gizmos
import wx.lib.splitter as spl

import invesalius.constants as const
import invesalius.gui.bitmap_preview_panel as bpp
import invesalius.gui.dialogs as dlg
import invesalius.reader.bitmap_reader as bpr
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

myEVT_SELECT_SERIE = wx.NewEventType()
EVT_SELECT_SERIE = wx.PyEventBinder(myEVT_SELECT_SERIE, 1)

myEVT_SELECT_SLICE = wx.NewEventType()
EVT_SELECT_SLICE = wx.PyEventBinder(myEVT_SELECT_SLICE, 1)

myEVT_SELECT_PATIENT = wx.NewEventType()
EVT_SELECT_PATIENT = wx.PyEventBinder(myEVT_SELECT_PATIENT, 1)

myEVT_SELECT_SERIE_TEXT = wx.NewEventType()
EVT_SELECT_SERIE_TEXT = wx.PyEventBinder(myEVT_SELECT_SERIE_TEXT, 1)


class SelectEvent(wx.PyCommandEvent):
    def __init__(self, evtType, id):
        super().__init__(evtType, id)

    def GetSelectID(self):
        return self.SelectedID

    def SetSelectedID(self, id):
        self.SelectedID = id

    def GetItemData(self):
        return self.data

    def SetItemData(self, data):
        self.data = data


class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(InnerPanel(self), 1, wx.EXPAND | wx.GROW | wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)


# Inner fold panel
class InnerPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5))

        self.patients = []
        self.first_image_selection = None
        self.last_image_selection = None
        self._init_ui()
        self._bind_events()
        self._bind_pubsubevt()

    def _init_ui(self):
        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.VERTICAL)
        self.splitter = splitter

        panel = wx.Panel(self)
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL)
        self.btn_ok = wx.Button(panel, wx.ID_OK, _("Import"))

        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(self.btn_ok)
        btnsizer.AddButton(self.btn_cancel)
        btnsizer.Realize()

        self.combo_interval = wx.ComboBox(
            panel, -1, "", choices=const.IMPORT_INTERVAL, style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        self.combo_interval.SetSelection(0)

        inner_sizer = wx.BoxSizer(wx.HORIZONTAL)
        inner_sizer.Add(btnsizer, 0, wx.LEFT | wx.TOP, 5)
        inner_sizer.Add(self.combo_interval, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
        panel.SetSizer(inner_sizer)
        inner_sizer.Fit(panel)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(splitter, 20, wx.EXPAND)
        sizer.Add(panel, 0, wx.EXPAND | wx.LEFT, 90)

        self.text_panel = TextPanel(splitter)
        splitter.AppendWindow(self.text_panel, 250)

        self.image_panel = ImagePanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def _bind_pubsubevt(self):
        Publisher.subscribe(self.ShowBitmapPreview, "Load import bitmap panel")
        Publisher.subscribe(self.GetSelectedImages, "Selected Import Images")

    def ShowBitmapPreview(self, data):
        # self.patients.extend(dicom_groups)
        self.text_panel.Populate(data)

    def GetSelectedImages(self, selection):
        self.first_image_selection = selection[0]
        self.last_image_selection = selection[1]

    def _bind_events(self):
        self.Bind(EVT_SELECT_SLICE, self.OnSelectSlice)
        self.Bind(EVT_SELECT_PATIENT, self.OnSelectPatient)
        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnClickOk)
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.OnClickCancel)
        self.text_panel.Bind(EVT_SELECT_SERIE_TEXT, self.OnDblClickTextPanel)

    def OnSelectSlice(self, evt):
        pass

    def OnSelectPatient(self, evt):
        pass

    def OnDblClickTextPanel(self, evt):
        pass

    def OnClickOk(self, evt):
        parm = dlg.ImportBitmapParameters()
        parm.SetInterval(self.combo_interval.GetSelection())
        parm.ShowModal()

    def OnClickCancel(self, evt):
        Publisher.sendMessage("Cancel DICOM load")


class TextPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.parent = parent

        self._selected_by_user = True
        self.idserie_treeitem = {}
        self.treeitem_idpatient = {}

        self.selected_items = None
        self.shift_pressed = False

        self.__init_gui()
        self.__bind_events_wx()
        self.__bind_pubsub_evt()

    def __bind_pubsub_evt(self):
        Publisher.subscribe(self.SelectSeries, "Select series in import panel")

    def __bind_events_wx(self):
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyPress)

    def __init_gui(self):
        tree = gizmos.TreeListCtrl(
            self,
            -1,
            style=wx.TR_DEFAULT_STYLE
            | wx.TR_HIDE_ROOT
            | wx.TR_ROW_LINES
            #  | wx.TR_COLUMN_LINES
            | wx.TR_FULL_ROW_HIGHLIGHT
            # | wx.TR_MULTIPLE
            | wx.TR_HIDE_ROOT,
            agwStyle=gizmos.TR_MULTIPLE,
        )

        tree.AddColumn(_("Path"))
        tree.AddColumn(_("Type"))
        tree.AddColumn(_("Width x Height"))

        tree.SetMainColumn(0)
        tree.SetColumnWidth(0, 880)
        tree.SetColumnWidth(1, 60)
        tree.SetColumnWidth(2, 130)

        self.root = tree.AddRoot(_("InVesalius Database"))
        self.tree = tree

    def OnKeyPress(self, evt):
        key_code = evt.GetKeyCode()

        if key_code == wx.WXK_DELETE or key_code == wx.WXK_NUMPAD_DELETE:
            for selected_item in self.selected_items:
                if selected_item != self.tree.GetRootItem():
                    text_item = self.tree.GetItemText(selected_item)

                    index = bpr.BitmapData().GetIndexByPath(text_item)

                    bpr.BitmapData().RemoveFileByPath(text_item)

                    data_size = len(bpr.BitmapData().GetData())

                    if index >= 0 and index < data_size:
                        Publisher.sendMessage("Set bitmap in preview panel", pos=index)
                    elif index == data_size and data_size > 0:
                        Publisher.sendMessage("Set bitmap in preview panel", pos=index - 1)
                    elif data_size == 1:
                        Publisher.sendMessage("Set bitmap in preview panel", pos=0)
                    else:
                        Publisher.sendMessage("Show black slice in single preview image")

                    self.tree.Delete(selected_item)
                    self.tree.Update()
                    self.tree.Refresh()
                    Publisher.sendMessage("Remove preview panel", data=text_item)

        evt.Skip()

    def SelectSeries(self, group_index):
        pass

    def Populate(self, data):
        tree = self.tree
        for value in data:
            parent = tree.AppendItem(self.root, value[0])
            self.tree.SetItemText(parent, value[2], 1)
            self.tree.SetItemText(parent, value[5], 2)

        tree.Expand(self.root)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)
        tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged)

        Publisher.sendMessage("Load bitmap into import panel", data=data)

    def OnSelChanged(self, evt):
        self.selected_items = self.tree.GetSelections()
        item = self.selected_items[-1]

        if self._selected_by_user:
            text_item = self.tree.GetItemText(item)
            index = bpr.BitmapData().GetIndexByPath(text_item)
            Publisher.sendMessage("Set bitmap in preview panel", pos=index)

        evt.Skip()

    def OnActivate(self, evt):
        item = evt.GetItem()
        group = self.tree.GetItemPyData(item)
        my_evt = SelectEvent(myEVT_SELECT_SERIE_TEXT, self.GetId())
        my_evt.SetItemData(group)
        self.GetEventHandler().ProcessEvent(my_evt)

    def OnSize(self, evt):
        self.tree.SetSize(self.GetSize())
        evt.Skip()

    def SelectSerie(self, serie):
        self._selected_by_user = False
        item = self.idserie_treeitem[serie]
        self.tree.SelectItem(item)
        self._selected_by_user = True

    def GetSelection(self):
        """Get selected item"""
        item = self.tree.GetSelection()
        group = self.tree.GetItemPyData(item)
        return group


class ImagePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self._init_ui()
        self._bind_events()

    def _init_ui(self):
        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.HORIZONTAL)
        self.splitter = splitter

        # TODO: Rever isso
        #  splitter.ContainingSizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.text_panel = SeriesPanel(splitter)
        splitter.AppendWindow(self.text_panel, 600)

        self.image_panel = SlicePanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def _bind_events(self):
        self.text_panel.Bind(EVT_SELECT_SLICE, self.OnSelectSlice)

    def OnSelectSlice(self, evt):
        self.image_panel.bitmap_preview.ShowSlice(evt.GetSelectID())
        evt.Skip()

    def SetSerie(self, serie):
        self.image_panel.bitmap_preview.SetDicomGroup(serie)


class SeriesPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.thumbnail_preview = bpp.BitmapPreviewSeries(self)

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer.Add(self.thumbnail_preview, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Fit(self)

        self.SetSizer(self.sizer)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_evt()
        self._bind_gui_evt()

    def __bind_evt(self):
        Publisher.subscribe(self.SetBitmapFiles, "Load bitmap into import panel")

    def _bind_gui_evt(self):
        self.thumbnail_preview.Bind(bpp.EVT_CLICK_SERIE, self.OnSelectSerie)

    def GetSelectedImagesRange(self):
        return [self.bitmap_preview.first_selected, self.dicom_preview_last_selection]

    def SetBitmapFiles(self, data):
        bitmap = data
        self.thumbnail_preview.Show(1)
        self.thumbnail_preview.SetBitmapFiles(bitmap)
        self.Update()

    def OnSelectSerie(self, evt):
        # data = evt.GetItemData()
        my_evt = SelectEvent(myEVT_SELECT_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())
        self.GetEventHandler().ProcessEvent(my_evt)

        self.sizer.Layout()
        self.Show()
        self.Update()

    def OnSelectSlice(self, evt):
        my_evt = SelectEvent(myEVT_SELECT_SLICE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())
        self.GetEventHandler().ProcessEvent(my_evt)


class SlicePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.__init_gui()
        self.__bind_evt()

    def __bind_evt(self):
        Publisher.subscribe(self.SetBitmapFiles, "Load bitmap into import panel")

    def __init_gui(self):
        self.SetBackgroundColour((255, 255, 255))
        self.bitmap_preview = bpp.SingleImagePreview(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.bitmap_preview, 1, wx.GROW | wx.EXPAND)
        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)
        self.sizer = sizer

    def SetBitmapFiles(self, data):
        self.bitmap_preview.SetBitmapFiles(data)
        self.sizer.Layout()
        self.Update()
