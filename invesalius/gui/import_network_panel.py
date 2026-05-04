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
import sys

import wx
import wx.gizmos as gizmos

# from dicionario import musicdata
import wx.lib.mixins.listctrl as listmix
import wx.lib.splitter as spl
from wx.lib.mixins.listctrl import CheckListCtrlMixin

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
import invesalius.net.dicom as dcm_net

# import invesalius.gui.dicom_preview_panel as dpp
import invesalius.reader.dicom_grouper as dcm
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
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5))  # ,
        # size=wx.Size(280, 656))

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
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5))  # ,
        # size=wx.Size(680, 656))

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
        sizer.Add(panel, 1, wx.EXPAND | wx.LEFT, 90)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.image_panel = HostFindPanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)

        self.text_panel = TextPanel(splitter)
        splitter.AppendWindow(self.text_panel, 250)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def _bind_pubsubevt(self):
        # Publisher.subscribe(self.ShowDicomPreview, "Load import panel")
        # Publisher.subscribe(self.GetSelectedImages ,"Selected Import Images")
        pass

    def GetSelectedImages(self, pubsub_evt):
        self.first_image_selection = pubsub_evt.data[0]
        self.last_image_selection = pubsub_evt.data[1]

    def _bind_events(self):
        self.Bind(EVT_SELECT_SERIE, self.OnSelectSerie)
        self.Bind(EVT_SELECT_SLICE, self.OnSelectSlice)
        self.Bind(EVT_SELECT_PATIENT, self.OnSelectPatient)
        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnClickOk)
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.OnClickCancel)
        self.text_panel.Bind(EVT_SELECT_SERIE_TEXT, self.OnDblClickTextPanel)

    def ShowDicomPreview(self, pubsub_evt):
        dicom_groups = pubsub_evt.data
        self.patients.extend(dicom_groups)
        self.text_panel.Populate(dicom_groups)

    def OnSelectSerie(self, evt):
        patient_id, serie_number = evt.GetSelectID()
        self.text_panel.SelectSerie(evt.GetSelectID())
        for patient in self.patients:
            if patient_id == patient.GetDicomSample().patient.id:
                for group in patient.GetGroups():
                    if serie_number == group.GetDicomSample().acquisition.serie_number:
                        self.image_panel.SetSerie(group)

    def OnSelectSlice(self, evt):
        pass

    def OnSelectPatient(self, evt):
        pass

    def OnDblClickTextPanel(self, evt):
        group = evt.GetItemData()
        self.LoadDicom(group)

    def OnClickOk(self, evt):
        group = self.text_panel.GetSelection()

        if group:
            self.LoadDicom(group)

    def OnClickCancel(self, evt):
        # Publisher.sendMessage("Cancel DICOM load")
        pass

    def LoadDicom(self, group):
        interval = self.combo_interval.GetSelection()

        if not isinstance(group, dcm.DicomGroup):
            group = max(group.GetGroups(), key=lambda g: g.nslices)

        slice_amont = group.nslices
        if (self.first_image_selection is not None) and (
            self.first_image_selection != self.last_image_selection
        ):
            slice_amont = (self.last_image_selection) - self.first_image_selection
            slice_amont += 1
            if slice_amont == 0:
                slice_amont = group.nslices

        nslices_result = slice_amont / (interval + 1)
        if nslices_result > 1:
            # Publisher.sendMessage('Open DICOM group', (group, interval,
            #                        [self.first_image_selection, self.last_image_selection]))
            pass
        else:
            dlg.MissingFilesForReconstruction()


class TextPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self._selected_by_user = True
        self.idserie_treeitem = {}
        self.treeitem_idpatient = {}

        self.__init_gui()
        self.__bind_events_wx()
        self.__bind_pubsub_evt()

    def __bind_pubsub_evt(self):
        # Publisher.subscribe(self.SelectSeries, 'Select series in import panel')
        Publisher.subscribe(self.Populate, "Populate tree")
        Publisher.subscribe(self.SetHostsList, "Set FindPanel hosts list")

    def __bind_events_wx(self):
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def __init_gui(self):
        tree = gizmos.TreeListCtrl(
            self,
            -1,
            style=wx.TR_DEFAULT_STYLE
            | wx.TR_HIDE_ROOT
            | wx.TR_ROW_LINES
            #  | wx.TR_COLUMN_LINES
            | wx.TR_FULL_ROW_HIGHLIGHT
            | wx.TR_SINGLE,
        )

        tree.AddColumn(_("Patient name"))
        tree.AddColumn(_("Patient ID"))
        tree.AddColumn(_("Age"))
        tree.AddColumn(_("Gender"))
        tree.AddColumn(_("Study description"))
        tree.AddColumn(_("Modality"))
        tree.AddColumn(_("Date acquired"))
        tree.AddColumn(_("# Images"))
        tree.AddColumn(_("Institution"))
        tree.AddColumn(_("Date of birth"))
        tree.AddColumn(_("Accession Number"))
        tree.AddColumn(_("Referring physician"))

        tree.SetMainColumn(0)  # the one with the tree in it...
        tree.SetColumnWidth(0, 280)  # Patient name
        tree.SetColumnWidth(1, 110)  # Patient ID
        tree.SetColumnWidth(2, 40)  # Age
        tree.SetColumnWidth(3, 60)  # Gender
        tree.SetColumnWidth(4, 160)  # Study description
        tree.SetColumnWidth(5, 70)  # Modality
        tree.SetColumnWidth(6, 200)  # Date acquired
        tree.SetColumnWidth(7, 70)  # Number Images
        tree.SetColumnWidth(8, 130)  # Institution
        tree.SetColumnWidth(9, 100)  # Date of birth
        tree.SetColumnWidth(10, 140)  # Accession Number
        tree.SetColumnWidth(11, 160)  # Referring physician

        self.root = tree.AddRoot(_("InVesalius Database"))
        self.tree = tree

    def SelectSeries(self, group_index):
        pass

    def Populate(self, pubsub_evt):
        tree = self.tree
        # print ">>>>>>>>>>>>>>>>>>>>>>>>>>", dir(tree.GetRootItem())
        # print ">>>>>>>>>>>>",dir(self.tree)
        patients = pubsub_evt.data

        # first = 0
        self.idserie_treeitem = {}

        for patient in patients.keys():
            # ngroups = patient.ngroups
            # dicom = patient.GetDicomSample()
            # title = dicom.patient.name + " (%d series)"%(ngroups)
            # date_time = "%s %s"%(dicom.acquisition.date,
            #                     dicom.acquisition.time)

            first_serie = patients[patient].keys()[0]
            title = patients[patient][first_serie]["name"]
            p = patients[patient][first_serie]

            p_id = patient
            age = p["age"]
            gender = p["gender"]
            study_description = p["study_description"]
            modality = p["modality"]
            date = p["acquisition_date"]
            time = p["acquisition_time"]
            institution = p["institution"]
            birthdate = p["date_of_birth"]
            acession_number = p["acession_number"]
            physician = p["ref_physician"]

            parent = tree.AppendItem(self.root, title)

            n_amount_images = 0
            for se in patients[patient]:
                n_amount_images = n_amount_images + patients[patient][se]["n_images"]

            tree.SetItemPyData(parent, patient)
            tree.SetItemText(parent, f"{p_id}", 1)
            tree.SetItemText(parent, f"{age}", 2)
            tree.SetItemText(parent, f"{gender}", 3)
            tree.SetItemText(parent, f"{study_description}", 4)
            tree.SetItemText(parent, "{}".format(""), 5)
            tree.SetItemText(parent, f"{date}" + " " + time, 6)
            tree.SetItemText(parent, f"{str(n_amount_images)}", 7)
            tree.SetItemText(parent, f"{institution}", 8)
            tree.SetItemText(parent, f"{birthdate}", 9)
            tree.SetItemText(parent, f"{acession_number}", 10)
            tree.SetItemText(parent, f"{physician}", 11)

            for series in patients[patient].keys():
                serie_description = patients[patient][series]["serie_description"]
                n_images = patients[patient][series]["n_images"]
                date = patients[patient][series]["acquisition_date"]
                time = patients[patient][series]["acquisition_time"]
                modality = patients[patient][series]["modality"]

                child = tree.AppendItem(parent, series)
                tree.SetItemPyData(child, series)

                tree.SetItemText(child, f"{serie_description}", 0)
                # tree.SetItemText(child, "%s" % dicom.acquisition.protocol_name, 4)
                tree.SetItemText(child, f"{modality}", 5)
                tree.SetItemText(child, f"{date}" + " " + time, 6)
                tree.SetItemText(child, f"{n_images}", 7)

                self.idserie_treeitem[(patient, series)] = child

        tree.Expand(self.root)
        # tree.SelectItem(parent_select)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)
        # tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged)

        """

        for patient in patient_list:
            if not isinstance(patient, dcm.PatientGroup):
                return None
            ngroups = patient.ngroups
            dicom = patient.GetDicomSample()
            title = dicom.patient.name + " (%d series)"%(ngroups)
            date_time = "%s %s"%(dicom.acquisition.date,
                                 dicom.acquisition.time)

            parent = tree.AppendItem(self.root, title)

            if not first:
                parent_select = parent
                first += 1

            tree.SetItemPyData(parent, patient)
            tree.SetItemText(parent, "%s" % dicom.patient.id, 1)
            tree.SetItemText(parent, "%s" % dicom.patient.age, 2)
            tree.SetItemText(parent, "%s" % dicom.patient.gender, 3)
            tree.SetItemText(parent, "%s" % dicom.acquisition.study_description, 4)
            tree.SetItemText(parent, "%s" % dicom.acquisition.modality, 5)
            tree.SetItemText(parent, "%s" % date_time, 6)
            tree.SetItemText(parent, "%s" % patient.nslices, 7)
            tree.SetItemText(parent, "%s" % dicom.acquisition.institution, 8)
            tree.SetItemText(parent, "%s" % dicom.patient.birthdate, 9)
            tree.SetItemText(parent, "%s" % dicom.acquisition.accession_number, 10)
            tree.SetItemText(parent, "%s" % dicom.patient.physician, 11)

            group_list = patient.GetGroups()
            for n, group in enumerate(group_list):
                dicom = group.GetDicomSample()

                child = tree.AppendItem(parent, group.title)
                tree.SetItemPyData(child, group)

                tree.SetItemText(child, "%s" % group.title, 0)
                tree.SetItemText(child, "%s" % dicom.acquisition.protocol_name, 4)
                tree.SetItemText(child, "%s" % dicom.acquisition.modality, 5)
                tree.SetItemText(child, "%s" % date_time, 6)
                tree.SetItemText(child, "%s" % group.nslices, 7)

                self.idserie_treeitem[(dicom.patient.id,
                                       dicom.acquisition.serie_number)] = child

        tree.Expand(self.root)
        tree.SelectItem(parent_select)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)
        tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged)"""

    def SetHostsList(self, evt_pub):
        self.hosts = evt_pub.data

    def GetHostList(self):
        Publisher.sendMessage("Get NodesPanel host list")
        return self.hosts

    def OnSelChanged(self, evt):
        item = self.tree.GetSelection()
        if self._selected_by_user:
            group = self.tree.GetItemPyData(item)
            if isinstance(group, dcm.DicomGroup):
                # Publisher.sendMessage('Load group into import panel',
                #                            group)
                pass

            elif isinstance(group, dcm.PatientGroup):
                id = group.GetDicomSample().patient.id
                my_evt = SelectEvent(myEVT_SELECT_PATIENT, self.GetId())
                my_evt.SetSelectedID(id)
                self.GetEventHandler().ProcessEvent(my_evt)

                # Publisher.sendMessage('Load patient into import panel',
                #                            group)
        else:
            parent_id = self.tree.GetItemParent(item)
            self.tree.Expand(parent_id)
        evt.Skip()

    def OnActivate(self, evt):
        item = evt.GetItem()
        item_parent = self.tree.GetItemParent(item)

        patient_id = self.tree.GetItemPyData(item_parent)
        serie_id = self.tree.GetItemPyData(item)

        hosts = self.GetHostList()

        for key in hosts.keys():
            if key != 0:
                dn = dcm_net.DicomNet()
                dn.SetHost(self.hosts[key][1])
                dn.SetPort(self.hosts[key][2])
                dn.SetAETitleCall(self.hosts[key][3])
                dn.SetAETitle(self.hosts[0][3])
                dn.RunCMove((patient_id, serie_id))
                # dn.SetSearchWord(self.find_txt.GetValue())

                # Publisher.sendMessage('Populate tree', dn.RunCFind())

        # my_evt = SelectEvent(myEVT_SELECT_SERIE_TEXT, self.GetId())
        # my_evt.SetItemData(group)
        # self.GetEventHandler().ProcessEvent(my_evt)

    def OnSize(self, evt):
        self.tree.SetSize(self.GetSize())

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


class FindPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        sizer_word_label = wx.BoxSizer(wx.HORIZONTAL)
        sizer_word_label.Add((5, 0), 0, wx.EXPAND | wx.HORIZONTAL)
        find_label = wx.StaticText(self, -1, _("Word"))
        sizer_word_label.Add(find_label)

        sizer_txt_find = wx.BoxSizer(wx.HORIZONTAL)
        sizer_txt_find.Add((5, 0), 0, wx.EXPAND | wx.HORIZONTAL)
        self.find_txt = wx.TextCtrl(self, -1, size=(225, -1))

        self.btn_find = wx.Button(self, -1, _("Search"))

        sizer_txt_find.Add(self.find_txt)
        sizer_txt_find.Add(self.btn_find)

        self.sizer.Add((0, 5), 0, wx.EXPAND | wx.HORIZONTAL)
        self.sizer.Add(sizer_word_label)
        self.sizer.Add(sizer_txt_find)

        # self.sizer.Add(self.serie_preview, 1, wx.EXPAND | wx.ALL, 5)
        # self.sizer.Add(self.dicom_preview, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Fit(self)

        self.SetSizer(self.sizer)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_evt()
        self._bind_gui_evt()

    def __bind_evt(self):
        Publisher.subscribe(self.SetHostsList, "Set FindPanel hosts list")
        # Publisher.subscribe(self.ShowDicomSeries, 'Load dicom preview')
        # Publisher.subscribe(self.SetDicomSeries, 'Load group into import panel')
        # Publisher.subscribe(self.SetPatientSeries, 'Load patient into import panel')
        pass

    def _bind_gui_evt(self):
        # self.serie_preview.Bind(dpp.EVT_CLICK_SERIE, self.OnSelectSerie)
        # self.dicom_preview.Bind(dpp.EVT_CLICK_SLICE, self.OnSelectSlice)
        self.Bind(wx.EVT_BUTTON, self.OnButtonFind, self.btn_find)

    def OnButtonFind(self, evt):
        hosts = self.GetHostList()

        for key in hosts.keys():
            if key != 0:
                dn = dcm_net.DicomNet()
                dn.SetHost(self.hosts[key][1])
                dn.SetPort(self.hosts[key][2])
                dn.SetAETitleCall(self.hosts[key][3])
                dn.SetAETitle(self.hosts[0][3])
                dn.SetSearchWord(self.find_txt.GetValue())

                Publisher.sendMessage("Populate tree", dn.RunCFind())

    def SetHostsList(self, evt_pub):
        self.hosts = evt_pub.data

    def GetHostList(self):
        Publisher.sendMessage("Get NodesPanel host list")
        return self.hosts


class HostFindPanel(wx.Panel):
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

        self.image_panel = NodesPanel(splitter)
        splitter.AppendWindow(self.image_panel, 500)

        self.text_panel = FindPanel(splitter)
        splitter.AppendWindow(self.text_panel, 750)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def _bind_events(self):
        self.text_panel.Bind(EVT_SELECT_SERIE, self.OnSelectSerie)
        self.text_panel.Bind(EVT_SELECT_SLICE, self.OnSelectSlice)

    def OnSelectSerie(self, evt):
        evt.Skip()

    def OnSelectSlice(self, evt):
        self.image_panel.dicom_preview.ShowSlice(evt.GetSelectID())
        evt.Skip()

    def SetSerie(self, serie):
        self.image_panel.dicom_preview.SetDicomGroup(serie)


class NodesTree(
    wx.ListCtrl, CheckListCtrlMixin, listmix.ListCtrlAutoWidthMixin, listmix.TextEditMixin
):
    def __init__(self, parent):
        self.item = 0
        self.col_locs = [0]
        self.editorBgColour = wx.Colour(255, 255, 255, 255)
        wx.ListCtrl.__init__(self, parent, -1, style=wx.LC_REPORT | wx.LC_HRULES)
        listmix.CheckListCtrlMixin.__init__(self)
        listmix.TextEditMixin.__init__(self)

    def OnCheckItem(self, index, flag):
        Publisher.sendMessage("Check item dict", [index, flag])

    def OpenEditor(self, col, row):
        if col >= 1 and col < 4:
            listmix.TextEditMixin.OpenEditor(self, col, row)
        else:
            listmix.CheckListCtrlMixin.ToggleItem(self, self.item)

    def SetSelected(self, item):
        self.item = item

    def SetDeselected(self, item):
        self.item = item


class NodesPanel(wx.Panel):
    def __init__(self, parent):
        self.selected_item = None
        self.hosts = {}

        wx.Panel.__init__(self, parent, -1)
        self.__init_gui()
        self.__bind_evt()

    def __bind_evt(self):
        self.Bind(wx.EVT_COMMAND_RIGHT_CLICK, self.RightButton, self.tree_node)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self.tree_node)
        self.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected, self.tree_node)
        self.Bind(wx.EVT_BUTTON, self.OnButtonAdd, self.btn_add)
        self.Bind(wx.EVT_BUTTON, self.OnButtonRemove, self.btn_remove)
        self.Bind(wx.EVT_BUTTON, self.OnButtonCheck, self.btn_check)

        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.EndEdition, self.tree_node)

        Publisher.subscribe(self.CheckItemDict, "Check item dict")
        Publisher.subscribe(self.GetHostsList, "Get NodesPanel host list")
        # Publisher.subscribe(self.UnCheckItemDict, "Uncheck item dict")

    def __init_gui(self):
        self.tree_node = NodesTree(self)

        self.tree_node.InsertColumn(0, _("Active"))
        self.tree_node.InsertColumn(1, _("Host"))
        self.tree_node.InsertColumn(2, _("Port"))
        self.tree_node.InsertColumn(3, _("AETitle"))
        self.tree_node.InsertColumn(4, _("Status"))

        self.tree_node.SetColumnWidth(0, 50)
        self.tree_node.SetColumnWidth(1, 150)
        self.tree_node.SetColumnWidth(2, 50)
        self.tree_node.SetColumnWidth(3, 150)
        self.tree_node.SetColumnWidth(4, 80)

        self.hosts[0] = [True, "localhost", "", "invesalius"]
        try:
            index = self.tree_node.InsertItem(sys.maxsize, "")
        except (OverflowError, AssertionError):
            index = self.tree_node.InsertItem(sys.maxint, "")
        self.tree_node.SetItem(index, 1, "localhost")
        self.tree_node.SetItem(index, 2, "")
        self.tree_node.SetItem(index, 3, "invesalius")
        self.tree_node.SetItem(index, 4, "ok")
        self.tree_node.CheckItem(index)
        self.tree_node.SetItemBackgroundColour(index, wx.Colour(245, 245, 245))
        # print ">>>>>>>>>>>>>>>>>>>>>", sys.maxint
        # index = self.tree_node.InsertItem(sys.maxint, "")#adiciona vazio a coluna de check
        # self.tree_node.SetItem(index, 1, "200.144.114.19")
        # self.tree_node.SetItem(index, 2, "80")
        # self.tree_node.SetItemData(index, 0)

        # index2 = self.tree_node.InsertItem(sys.maxint, "")#adiciona vazio a coluna de check
        # self.tree_node.SetItem(index2, 1, "200.144.114.19")
        # self.tree_node.SetItem(index2, 2, "80")
        # self.tree_node.SetItemData(index2, 0)

        self.btn_add = wx.Button(self, -1, _("Add"))
        self.btn_remove = wx.Button(self, -1, _("Remove"))
        self.btn_check = wx.Button(self, -1, _("Check status"))

        sizer_btn = wx.BoxSizer(wx.HORIZONTAL)
        sizer_btn.Add((90, 0), 0, wx.EXPAND | wx.HORIZONTAL)
        sizer_btn.Add(self.btn_add, 10)
        sizer_btn.Add(self.btn_remove, 10)
        sizer_btn.Add(self.btn_check, 0, wx.ALIGN_CENTER_HORIZONTAL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tree_node, 85, wx.GROW | wx.EXPAND)
        sizer.Add(sizer_btn, 15)
        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)
        self.sizer = sizer

    def GetHostsList(self, pub_evt):
        Publisher.sendMessage("Set FindPanel hosts list", self.hosts)

    def EndEdition(self, evt):
        index = evt.m_itemIndex
        item = evt.m_item
        col = item.GetColumn()
        txt = item.GetText()

        values = self.hosts[index]
        values[col] = str(txt)
        self.hosts[index] = values

    def OnButtonAdd(self, evt):
        # adiciona vazio a coluna de check
        index = self.tree_node.InsertItem(sys.maxsize, "")

        self.hosts[index] = [True, "localhost", "80", ""]
        self.tree_node.SetItem(index, 1, "localhost")
        self.tree_node.SetItem(index, 2, "80")
        self.tree_node.SetItem(index, 3, "")
        self.tree_node.CheckItem(index)

    def OnLeftDown(self, evt):
        evt.Skip()

    def OnButtonRemove(self, evt):
        if self.selected_item is not None and self.selected_item != 0:
            self.tree_node.DeleteItem(self.selected_item)
            self.hosts.pop(self.selected_item)
            self.selected_item = None

            k = self.hosts.keys()
            tmp_cont = 0

            tmp_host = {}
            for x in k:
                tmp_host[tmp_cont] = self.hosts[x]
                tmp_cont += 1
            self.hosts = tmp_host

    def OnButtonCheck(self, evt):
        for key in self.hosts.keys():
            if key != 0:
                dn = dcm_net.DicomNet()
                dn.SetHost(self.hosts[key][1])
                dn.SetPort(self.hosts[key][2])
                dn.SetAETitleCall(self.hosts[key][3])
                dn.SetAETitle(self.hosts[0][3])

                if dn.RunCEcho():
                    self.tree_node.SetItem(key, 4, _("ok"))
                else:
                    self.tree_node.SetItem(key, 4, _("error"))

    def RightButton(self, evt):
        evt.Skip()

    def OnItemSelected(self, evt):
        self.selected_item = evt.m_itemIndex
        self.tree_node.SetSelected(evt.m_itemIndex)

    def OnItemDeselected(self, evt):
        if evt.m_itemIndex != 0:
            self.tree_node.SetDeselected(evt.m_itemIndex)

    def CheckItemDict(self, evt_pub):
        index, flag = evt_pub.data
        if index != 0:
            self.hosts[index][0] = flag
        else:
            self.tree_node.CheckItem(0)
