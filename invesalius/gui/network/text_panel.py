import os
import pathlib

import wx
import wx.gizmos as gizmos

import invesalius.net.dicom as dcm_net
import invesalius.session as ses
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher

myEVT_SELECT_PATIENT = wx.NewEventType()
EVT_SELECT_PATIENT = wx.PyEventBinder(myEVT_SELECT_PATIENT, 1)


class TextPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.__idserie_treeitem = {}
        self.__idpatient_treeitem = {}
        self.__idstudy_treeitem = {}
        self.__selected = None
        self.__server_ip = None
        self.__server_aetitle = None
        self.__server_port = None
        self.__download_method = ""
        self.__store_path = None
        self.__patients_data = None

        self.__session = ses.Session()

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
        tree.AddColumn(_("Status"))

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

    def _load_values(self):
        self.__selected = (
            self.__session.GetConfig("selected_node")
            if self.__session.GetConfig("selected_node")
            else None
        )

        self.__server_ip = (
            self.__session.GetConfig("server_ip")
            if self.__session.GetConfig("server_ip")
            else "0.0.0.0"
        )

        self.__server_aetitle = (
            self.__session.GetConfig("server_aetitle")
            if self.__session.GetConfig("server_aetitle")
            else "INVESALIUS"
        )

        self.__server_port = (
            self.__session.GetConfig("server_port")
            if self.__session.GetConfig("server_port")
            else 11120
        )

        self.__download_method = (
            self.__session.GetConfig("download_method")
            if self.__session.GetConfig("download_method")
            else "CMOVE"
        )

        self.__store_path = (
            pathlib.Path(self.__session.GetConfig("store_path"))
            if self.__session.GetConfig("store_path")
            else inv_paths.USER_DICOM_DIR
        )

    def Populate(self, patients):
        """Populate tree."""

        self.__tree.DeleteChildren(self.__root)

        self.__idpatient_treeitem.clear()
        self.__idstudy_treeitem.clear()
        self.__idserie_treeitem.clear()

        self.__patients_data = patients

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

            self.__tree.SetItemPyData(
                parent, {"type": "patient", "patient": patient, "n_images": n_amount_images}
            )

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
                    study_node,
                    {"type": "study", "study": study, "patient": patient, "n_images": study_images},
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
                        {
                            "type": "series",
                            "patient": patient,
                            "study": study,
                            "series": series,
                            "n_images": n_images,
                        },
                    )
                    self.__tree.SetItemText(child, serie_description, 0)
                    # tree.SetItemText(child, dicom.acquisition.protocol_name, 4)
                    self.__tree.SetItemText(child, modality, 5)
                    self.__tree.SetItemText(child, date + " " + time, 6)
                    self.__tree.SetItemText(child, str(n_images), 7)

                    self.__tree.SetItemText(child, "", 12)
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
        if not evt:
            item = self.__tree.GetSelection()
        else:
            item = evt.GetItem()

        self._load_values()

        data = self.__tree.GetItemPyData(item)

        patient_id = data.get("patient")
        if not patient_id:
            wx.MessageBox(_("Missing patient information"), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        patient_data = self.__patients_data.get(patient_id)
        if not patient_data:
            wx.MessageBox(_("Patient data not found"), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        series_list = []

        if data.get("type") == "patient":
            for study_id, study_data in patient_data.items():
                for series_id, series_data in study_data.items():
                    series_data["patient"] = patient_id
                    series_data["study"] = study_id
                    series_data["series"] = series_id
                    series_data["type"] = "series"
                    series_list.append((study_id, series_id, series_data))

        elif data.get("type") == "study":
            study_id = data.get("study")
            study_data = patient_data.get(study_id, {})
            for series_id, series_data in study_data.items():
                series_data["patient"] = patient_id
                series_data["study"] = study_id
                series_data["series"] = series_id
                series_data["type"] = "series"
                series_list.append((study_id, series_id, series_data))

        elif data.get("type") == "series":
            study_id = data.get("study")
            series_id = data.get("series")
            series_data = patient_data.get(study_id, {}).get(series_id, {})
            series_data["patient"] = patient_id
            series_data["study"] = study_id
            series_data["series"] = series_id
            series_data["type"] = "series"
            series_list.append((study_id, series_id, series_data))

        if not series_list:
            wx.MessageBox(_("No series found to download"), _("Info"), wx.OK | wx.ICON_INFORMATION)
            return

        for study_id, series_id, series_data in series_list:
            dest = self.__store_path / patient_id / study_id / series_id
            self._download_series(series_data, dest)

    def _download_series(self, data, dest):
        n_images = data.get("n_images", 0)
        dest.mkdir(parents=True, exist_ok=True)
        found = len([f for f in dest.rglob("*.dcm") if f.is_file()])
        if found >= n_images:
            wx.MessageBox("Images already downloaded!", "Info", wx.OK)
            Publisher.sendMessage("Hide import network panel")
            Publisher.sendMessage("Import directory", directory=str(dest), use_gui=False)
            return

        dn = dcm_net.DicomNet(
            self.__selected["ipaddress"],
            int(self.__selected["port"]),
            self.__selected["aetitle"],
        )
        dn.ServerAETitle(self.__server_aetitle)
        dn.SetPortCall(int(self.__server_port))
        dn.SetIPCall(self.__server_ip)

        try:
            dn.RunDownloader(
                data,
                str(dest),
                self.__download_method,
                self._on_download_done,
            )

        except Exception as e:
            wx.MessageBox(str(e), _("Error"), wx.OK | wx.ICON_ERROR)
            return

    def ImportSelected(self):
        """Import the currently selected tree item."""

        selection = self.GetSelection()

        if selection:
            self.OnActivate(None)
        else:
            wx.MessageBox(
                _("Please select a series to import."), _("Info"), wx.OK | wx.ICON_INFORMATION
            )

    def _on_download_done(self, dest, result=None, error=None):
        if error == "CANCELLED":
            wx.MessageBox(
                _("Download cancelled. Partial files have been removed."),
                _("Cancelled"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        if error:
            wx.MessageBox(str(error), _("Error"), wx.OK | wx.ICON_ERROR)
            return

        dcm_files = [f for f in os.listdir(dest) if f.endswith(".dcm")]

        if not dcm_files:
            wx.MessageBox("No DICOM files found!", "Error", wx.OK | wx.ICON_ERROR)
            return

        # Pass the first DICOM file to import
        # first_dcm = os.path.join(dest, dcm_files[0])

        wx.MessageBox("Download complete!", "Success", wx.OK)
        Publisher.sendMessage("Hide import network panel")
        Publisher.sendMessage("Import directory", directory=str(dest), use_gui=False)

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
