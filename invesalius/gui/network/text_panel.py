import wx
import wx.gizmos as gizmos
import invesalius.net.dicom as dcm_net
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher
import os

myEVT_SELECT_PATIENT = wx.NewEventType()
EVT_SELECT_PATIENT = wx.PyEventBinder(myEVT_SELECT_PATIENT, 1)


class TextPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self._selected_by_user = True
        self.__idserie_treeitem = {}
        self.__idpatient_treeitem = {}
        self.__idstudy_treeitem = {}

        session = ses.Session()
        self.__selected = (
            session.GetConfig("selected_node") if session.GetConfig("selected_node") else None
        )

        self.__server_ip = session.GetConfig('server_ip') \
            if session.GetConfig('server_ip') \
            else None

        self.__server_aetitle = (
            session.GetConfig("server_aetitle") if session.GetConfig("server_aetitle") else ""
        )

        self.__server_port = (
            session.GetConfig("server_port") if session.GetConfig("server_port") else ""
        )

        self.__store_path = (
            session.GetConfig("store_path") if session.GetConfig("store_path") else ""
        )

        self.__tree = self.__init_gui()
        self.__root = self.__tree.AddRoot(_("InVesalius Database"))

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

        return tree

    def SelectSeries(self, group_index):
        pass

    def Populate(self, patients):
        """Populate tree."""

        for patient in patients.keys():
            first_study = list(patients[patient].keys())[0]
            first_serie = list(patients[patient][first_study].keys())[0]
            title = patients[patient][first_study][first_serie]["name"]
            p = patients[patient][first_study][first_serie]

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

            n_amount_images = 0
            for study in patients[patient]:
                for serie in patients[patient][study]:
                    n_amount_images = n_amount_images + patients[patient][study][serie]["n_images"]

            parent = (
                self.__idpatient_treeitem[patient]
                if patient in self.__idpatient_treeitem
                else self.__tree.AppendItem(self.__root, str(title))
            )

            self.__tree.SetItemPyData(parent, {"type": "patient", "patient": patient})

            self.__tree.SetItemText(parent, p_id, 1)
            self.__tree.SetItemText(parent, age, 2)
            self.__tree.SetItemText(parent, gender, 3)
            self.__tree.SetItemText(parent, study_description, 4)
            self.__tree.SetItemText(parent, "", 5)
            self.__tree.SetItemText(parent, date + " " + time, 6)
            self.__tree.SetItemText(parent, str(n_amount_images), 7)
            self.__tree.SetItemText(parent, institution, 8)
            self.__tree.SetItemText(parent, birthdate, 9)
            self.__tree.SetItemText(parent, acession_number, 10)
            self.__tree.SetItemText(parent, str(physician), 11)

            self.__idpatient_treeitem[patient] = parent

            for study in patients[patient].keys():
                study_images = sum(
                    patients[patient][study][serie]["n_images"]
                    for serie in patients[patient][study]
                )

                study_node = self.__tree.AppendItem(parent, f"Study: {study[:8]}...")
                study_key = (patient, study)

                self.__tree.SetItemPyData(
                    study_node, {"type": "study", "study": study, "patient": patient}
                )

                self.__idstudy_treeitem[study_key] = study_node

                for series in patients[patient][study].keys():
                    serie_description = patients[patient][study][series]["serie_description"]
                    n_images = patients[patient][study][series]["n_images"]
                    date = patients[patient][study][series]["acquisition_date"]
                    time = patients[patient][study][series]["acquisition_time"]
                    modality = patients[patient][study][series]["modality"]

                    child_key = (patient, study, series)
                    child = (
                        self.__idserie_treeitem.get(child_key)
                        if child_key in self.__idserie_treeitem
                        else self.__tree.AppendItem(study_node, series)
                    )

                    self.__tree.SetItemPyData(
                        child,
                        {"type": "series", "patient": patient, "study": study, "series": series},
                    )
                    self.__tree.SetItemText(child, serie_description, 0)
                    # tree.SetItemText(child, dicom.acquisition.protocol_name, 4)
                    self.__tree.SetItemText(child, modality, 5)
                    self.__tree.SetItemText(child, date + " " + time, 6)
                    self.__tree.SetItemText(child, str(n_images), 7)

                    self.__idserie_treeitem[child_key] = child

        self.__tree.Expand(self.__root)
        self.__tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)

    def SetHostsList(self, evt_pub):
        self.hosts = evt_pub.data

    def GetHostList(self):
        Publisher.sendMessage("Get NodesPanel host list")
        return self.hosts

    def OnSelChanged(self, evt):
        item = self.__tree.GetSelection()
        if self._selected_by_user:
            group = self.__tree.GetItemPyData(item)
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
            parent_id = self.__tree.GetItemParent(item)
            self.__tree.Expand(parent_id)
        evt.Skip()

    def OnActivate(self, evt):
        item = evt.GetItem()

        data = self.__tree.GetItemPyData(item)

        dest = ""

        if data['type'] == 'patient':
            dest = f"{self.__store_path}/{data['patient']}"
        elif data['type'] == 'study':
            dest = f"{self.__store_path}/{data['patient']}/{data['study']}"
        elif data['type'] == 'series':
            dest = f"{self.__store_path}/{data['patient']}/{data['study']}/{data['series']}"
        else:
            wx.MessageBox(_("Unknown item type"), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        if data:
            if self.__selected is None:
                wx.MessageBox(_("Please select a node"), _("Error"), wx.OK | wx.ICON_ERROR)
                return

            if self.__server_aetitle is None or \
                self.__server_port is None or \
                self.__server_ip is None:

                wx.MessageBox(_("Please configure the server"), _("Error"), wx.OK | wx.ICON_ERROR)
                return

            dn = dcm_net.DicomNet(
                self.__selected["ipaddress"],
                int(self.__selected["port"]),
                self.__selected["aetitle"],
            )
            dn.ServerAETitle(self.__server_aetitle)
            dn.SetPortCall(int(self.__server_port))
            dn.SetStorePath(self.__store_path)
            dn.SetIPCall(self.__server_ip)

            try:

                dn.RunCMove(data, dest, self.OnDone(dest))
            
            except Exception as e:
                    
                wx.MessageBox(str(e), _("Error"), wx.OK | wx.ICON_ERROR)
                return

    def OnDone(self, dest):
        Publisher.sendMessage("Hide import network panel")
        Publisher.sendMessage('Import directory', directory=dest, use_gui=False)

    def OnSize(self, evt):
        self.__tree.SetSize(self.GetSize())

    def SelectSerie(self, serie):
        self._selected_by_user = False
        item = self.__idserie_treeitem[serie]
        self.__tree.SelectItem(item)
        self._selected_by_user = True

    def GetSelection(self):
        """Get selected item"""
        item = self.__tree.GetSelection()
        group = self.__tree.GetItemPyData(item)
        return group
