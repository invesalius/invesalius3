from invesalius.pubsub import pub as Publisher
import invesalius.net.dicom as dcm_net
import invesalius.session as ses
from invesalius import inv_paths
import wx.gizmos as gizmos
import pathlib
import wx
import os

myEVT_SELECT_PATIENT = wx.NewEventType()
EVT_SELECT_PATIENT = wx.PyEventBinder(myEVT_SELECT_PATIENT, 1)


class TextPanel(wx.Panel):
    """ Text panel. """

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.__idserie_treeitem = {}
        self.__idpatient_treeitem = {}
        self.__selected = None
        self.__server_ip = None
        self.__server_aetitle = None
        self.__server_port = None
        self.__store_path = None
        self.__progress_dialog = None

        self.__session = ses.Session()

        self.__tree = self._init_gui()
        self.__root = self.__tree.AddRoot(_("InVesalius Database"))

        self._bind_events_wx()
        self._bind_pubsub_evt()

    def _bind_pubsub_evt(self):

        Publisher.subscribe(self._populate, 'Populate tree')

    def _bind_events_wx(self):

        self.Bind(wx.EVT_SIZE, self._on_size)

    def _init_gui(self):

        tree = gizmos.TreeListCtrl(self, -1, style=wx.TR_DEFAULT_STYLE |
                                   wx.TR_HIDE_ROOT |
                                   wx.TR_ROW_LINES |
                                   wx.TR_FULL_ROW_HIGHLIGHT |
                                   wx.TR_SINGLE
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

        tree.SetMainColumn(0)        # the one with the tree in it...
        tree.SetColumnWidth(0, 280)  # Patient name
        tree.SetColumnWidth(1, 110)  # Patient ID
        tree.SetColumnWidth(2, 40)   # Age
        tree.SetColumnWidth(3, 60)   # Gender
        tree.SetColumnWidth(4, 160)  # Study description
        tree.SetColumnWidth(5, 70)   # Modality
        tree.SetColumnWidth(6, 200)  # Date acquired
        tree.SetColumnWidth(7, 70)   # Number Images
        tree.SetColumnWidth(8, 130)  # Institution
        tree.SetColumnWidth(9, 100)  # Date of birth
        tree.SetColumnWidth(10, 140)  # Accession Number
        tree.SetColumnWidth(11, 160)  # Referring physician

        return tree

    def _load_values(self):

        self.__selected = self.__session.GetConfig('selected_node') \
            if self.__session.GetConfig('selected_node') \
            else None

        self.__server_ip = self.__session.GetConfig('server_ip') \
            if self.__session.GetConfig('server_ip') \
            else '0.0.0.0'

        self.__server_aetitle = self.__session.GetConfig('server_aetitle') \
            if self.__session.GetConfig('server_aetitle') \
            else 'PYNETDICOM'

        self.__server_port = self.__session.GetConfig('server_port') \
            if self.__session.GetConfig('server_port') \
            else 11120

        self.__store_path = pathlib.Path(self.__session.GetConfig('store_path')) \
            if self.__session.GetConfig('store_path') \
            else inv_paths.USER_DICOM_DIR

    def _populate(self, patients):
        """ Populate tree. """

        for patient in patients.keys():

            first_serie = list(patients[patient].keys())[0]
            title = patients[patient][first_serie]['name']
            p = patients[patient][first_serie]

            p_id = patient
            age = p['age']
            gender = p['gender']
            study_description = p['study_description']
            modality = p['modality']
            date = p['acquisition_date']
            time = p['acquisition_time']
            institution = p['institution']
            birthdate = p['date_of_birth']
            acession_number = p['acession_number']
            physician = p['ref_physician']

            n_amount_images = [patients[patient][se]['n_images']
                               for se in patients[patient]]
            n_amount_images = sum(n_amount_images)

            parent = self.__idpatient_treeitem[patient] \
                if patient in self.__idpatient_treeitem \
                else self.__tree.AppendItem(self.__root, str(title))

            self.__tree.SetItemText(parent, p_id, 1)
            self.__tree.SetItemText(parent, age, 2)
            self.__tree.SetItemText(parent, gender, 3)
            self.__tree.SetItemText(parent, study_description, 4)
            self.__tree.SetItemText(parent, "", 5)
            self.__tree.SetItemText(parent, date + " " + time, 6)
            self.__tree.SetItemText(parent, institution, 8)
            self.__tree.SetItemText(parent, birthdate, 9)
            self.__tree.SetItemText(parent, acession_number, 10)
            self.__tree.SetItemText(parent, str(physician), 11)

            self.__idpatient_treeitem[patient] = parent

            for series in patients[patient].keys():

                serie_description = patients[patient][series]['serie_description']
                n_images = patients[patient][series]['n_images']
                date = patients[patient][series]['acquisition_date']
                time = patients[patient][series]['acquisition_time']
                modality = patients[patient][series]['modality']

                child = self.__idserie_treeitem[(patient, series)] \
                    if (patient, series) in self.__idserie_treeitem \
                    else self.__tree.AppendItem(parent, series)

                self.__tree.SetItemPyData(child, (patient, series, n_images))

                self.__tree.SetItemText(child, serie_description, 0)
                self.__tree.SetItemText(child, modality, 5)
                self.__tree.SetItemText(child, date + " " + time, 6)
                self.__tree.SetItemText(child, str(n_images), 7)
                self.__tree.SetItemText(parent, str(n_amount_images), 7)

                self.__idserie_treeitem[(patient, series)] = child

        self.__tree.Expand(self.__root)
        self.__tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_activate)

    def _update_progress(self, completed, total):

        percentage = int((completed / total) * 100)
        keep_going, skip = self.__progress_dialog.Update(
            percentage, f"Progress: {completed}/{total}")

        if not keep_going:

            raise RuntimeError("Operation canceled by user")

    def _destroy_progress(self):

        if self.__progress_dialog:
            self.__progress_dialog.Destroy()

    def _on_activate(self, evt):

        item = evt.GetItem()

        self._load_values()

        series_data = self.__tree.GetItemPyData(item)
        if series_data:

            patient_id, series_id, n_images = series_data

            if self.__selected is None:

                wx.MessageBox(_("Please select a node"), _(
                    "Error"), wx.OK | wx.ICON_ERROR)
                return

            dest = self.__store_path.joinpath(patient_id, series_id)
            dest.mkdir(parents=True, exist_ok=True)
            found = len(os.listdir(dest))
            if found < n_images:

                dn = dcm_net.DicomNet()
                dn.SetHost(self.__selected['ipaddress'])
                dn.SetPort(self.__selected['port'])
                dn.SetAETitle(self.__selected['aetitle'])
                dn.SetAETitleCall(self.__server_aetitle)
                dn.SetPortCall(self.__server_port)
                dn.SetIPCall(self.__server_ip)

                try:

                    self.__progress_dialog = wx.ProgressDialog(
                        "C-MOVE Progress", "Starting...", maximum=100, parent=self, style=wx.PD_CAN_ABORT | wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME
                    )

                    dn.RunCMove({'patient_id': patient_id,
                                'serie_id': series_id, 'n_images': n_images, 'destination': dest}, self._update_progress)

                except Exception as e:

                    self._destroy_progress()
                    wx.MessageBox(str(e), _("Error"), wx.OK | wx.ICON_ERROR)
                    return

            self._destroy_progress()
            Publisher.sendMessage("Hide import network panel")
            Publisher.sendMessage('Import directory',
                                  directory=str(dest), use_gui=False)

    def _on_size(self, evt):

        self.__tree.SetSize(self.GetSize())
