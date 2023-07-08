#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------
import wx
import sys
import wx.gizmos as gizmos
from invesalius.pubsub import pub as Publisher
import wx.lib.splitter as spl

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
#import invesalius.gui.dicom_preview_panel as dpp
import invesalius.reader.dicom_grouper as dcm
import invesalius.net.dicom as dcm_net


from wx.lib.mixins.listctrl import CheckListCtrlMixin
#from dicionario import musicdata
import wx.lib.mixins.listctrl as listmix
from invesalius.gui.network.host_find_panel import HostFindPanel

myEVT_SELECT_PATIENT = wx.NewEventType()
EVT_SELECT_PATIENT = wx.PyEventBinder(myEVT_SELECT_PATIENT, 1)

class SelectEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id):
        super(SelectEvent, self).__init__(evtType, id)

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
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5))#,
                          #size=wx.Size(280, 656))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(InnerPanel(self), 1, wx.EXPAND|wx.GROW|wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)


# Inner fold panel
class InnerPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5))#,
                          #size=wx.Size(680, 656))

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

        self.combo_interval = wx.ComboBox(panel, -1, "", choices=const.IMPORT_INTERVAL,
                                     style=wx.CB_DROPDOWN|wx.CB_READONLY)
        self.combo_interval.SetSelection(0)

        inner_sizer = wx.BoxSizer(wx.HORIZONTAL)
        inner_sizer.Add(btnsizer, 0, wx.LEFT|wx.TOP, 5)
        inner_sizer.Add(self.combo_interval, 0, wx.LEFT|wx.RIGHT|wx.TOP, 5)
        panel.SetSizer(inner_sizer)
        inner_sizer.Fit(panel)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(splitter, 20, wx.EXPAND)
        sizer.Add(panel, 1, wx.EXPAND|wx.LEFT, 90)

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
        #Publisher.subscribe(self.ShowDicomPreview, "Load import panel")
        #Publisher.subscribe(self.GetSelectedImages ,"Selected Import Images")     
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
        #Publisher.sendMessage("Cancel DICOM load")
        pass

    def LoadDicom(self, group):
        interval = self.combo_interval.GetSelection()

        if not isinstance(group, dcm.DicomGroup):
            group = max(group.GetGroups(), key=lambda g: g.nslices)
        
        slice_amont = group.nslices
        if (self.first_image_selection != None) and (self.first_image_selection != self.last_image_selection):
            slice_amont = (self.last_image_selection) - self.first_image_selection
            slice_amont += 1
            if slice_amont == 0:
                slice_amont = group.nslices

        nslices_result = slice_amont / (interval + 1)
        if (nslices_result > 1):
            #Publisher.sendMessage('Open DICOM group', (group, interval, 
            #                        [self.first_image_selection, self.last_image_selection]))
            pass
        else:
            dlg.MissingFilesForReconstruction()

class TextPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self._selected_by_user = True
        self.__idserie_treeitem = {}
        self.__idpatient_treeitem = {}

        self.__init_gui()
        self.__bind_events_wx()
        self.__bind_pubsub_evt()

    def __bind_pubsub_evt(self):
        #Publisher.subscribe(self.SelectSeries, 'Select series in import panel')
        Publisher.subscribe(self.Populate, 'Populate tree')
        Publisher.subscribe(self.SetHostsList, 'Set FindPanel hosts list')

    def __bind_events_wx(self):
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def __init_gui(self):
        tree = gizmos.TreeListCtrl(self, -1, style =
                                   wx.TR_DEFAULT_STYLE
                                   | wx.TR_HIDE_ROOT
                                   | wx.TR_ROW_LINES
                                   #  | wx.TR_COLUMN_LINES
                                   | wx.TR_FULL_ROW_HIGHLIGHT
                                   | wx.TR_SINGLE
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
        tree.SetColumnWidth(10, 140) # Accession Number
        tree.SetColumnWidth(11, 160) # Referring physician

        self.root = tree.AddRoot(_("InVesalius Database"))
        self.tree = tree

    def SelectSeries(self, group_index):
        pass

    def Populate(self, patients):

        tree = self.tree

        first = 0

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

            n_amount_images = [patients[patient][se]['n_images'] for se in patients[patient]]
            n_amount_images = sum(n_amount_images)

            parent = self.__idpatient_treeitem[patient] \
                if patient in self.__idpatient_treeitem \
                else tree.AppendItem(self.root, str(title))

            tree.SetItemPyData(parent, patient)

            tree.SetItemText(parent, p_id, 1)
            tree.SetItemText(parent, age, 2)
            tree.SetItemText(parent, gender, 3)
            tree.SetItemText(parent, study_description, 4)
            tree.SetItemText(parent, "", 5)
            tree.SetItemText(parent, date + " " + time, 6)
            tree.SetItemText(parent, institution, 8)
            tree.SetItemText(parent, birthdate, 9)
            tree.SetItemText(parent, acession_number, 10)
            tree.SetItemText(parent, str(physician), 11)

            self.__idpatient_treeitem[patient] = parent

            for series in patients[patient].keys():
                                
                serie_description = patients[patient][series]['serie_description']
                n_images =  patients[patient][series]['n_images']
                date =  patients[patient][series]['acquisition_date']
                time =  patients[patient][series]['acquisition_time']
                modality = patients[patient][series]['modality']

                child = self.__idserie_treeitem[(patient, series)] \
                    if (patient, series) in self.__idserie_treeitem \
                    else tree.AppendItem(parent, series)

                tree.SetItemPyData(child, series)

                tree.SetItemText(child, serie_description, 0)
                tree.SetItemText(child, modality, 5)
                tree.SetItemText(child, date + " " + time, 6)
                tree.SetItemText(child, str(n_images) , 7)
                tree.SetItemText(parent, str(n_amount_images), 7)

                self.__idserie_treeitem[(patient, series)] = child

        tree.Expand(self.root)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)

    def SetHostsList(self, evt_pub):
        self.hosts = evt_pub.data

    def GetHostList(self):
        Publisher.sendMessage('Get NodesPanel host list')
        return self.hosts 

    def OnSelChanged(self, evt):
        item = self.tree.GetSelection()
        if self._selected_by_user:
            group = self.tree.GetItemPyData(item)
            if isinstance(group, dcm.DicomGroup):
                #Publisher.sendMessage('Load group into import panel',
                #                            group)
                pass

            elif isinstance(group, dcm.PatientGroup):
                id = group.GetDicomSample().patient.id
                my_evt = SelectEvent(myEVT_SELECT_PATIENT, self.GetId())
                my_evt.SetSelectedID(id)
                self.GetEventHandler().ProcessEvent(my_evt)

                #Publisher.sendMessage('Load patient into import panel',
                #                            group)
        else:
            parent_id = self.tree.GetItemParent(item)
            self.tree.Expand(parent_id)
        evt.Skip()

    def OnActivate(self, evt):
        

        item = evt.GetItem()
        item_parent = self.tree.GetItemParent(item)
        
        patient_id = self.tree.GetItemPyData(item_parent)
        serie_id  = self.tree.GetItemPyData(item)

        hosts = self.GetHostList()

        for key in hosts.keys():
            if key != 0:
                dn = dcm_net.DicomNet()
                dn.SetHost(self.hosts[key][1])
                dn.SetPort(self.hosts[key][2])
                dn.SetAETitleCall(self.hosts[key][3])
                dn.SetAETitle(self.hosts[0][3])
                dn.RunCMove((patient_id, serie_id))
                #dn.SetSearchWord(self.find_txt.GetValue())

                #Publisher.sendMessage('Populate tree', dn.RunCFind())



        #my_evt = SelectEvent(myEVT_SELECT_SERIE_TEXT, self.GetId())
        #my_evt.SetItemData(group)
        #self.GetEventHandler().ProcessEvent(my_evt)


    def OnSize(self, evt):
        self.tree.SetSize(self.GetSize())

    def SelectSerie(self, serie):
        self._selected_by_user = False
        item = self.__idserie_treeitem[serie]
        self.tree.SelectItem(item)
        self._selected_by_user = True

    def GetSelection(self):
        """Get selected item"""
        item = self.tree.GetSelection()
        group = self.tree.GetItemPyData(item)
        return group
