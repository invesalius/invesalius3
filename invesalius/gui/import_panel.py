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
import wx.gizmos as gizmos
import wx.lib.pubsub as ps
import wx.lib.splitter as spl

import dicom_preview_panel as dpp
import reader.dicom_grouper as dcm

myEVT_SELECT_SERIE = wx.NewEventType()
EVT_SELECT_SERIE = wx.PyEventBinder(myEVT_SELECT_SERIE, 1)

myEVT_SELECT_SLICE = wx.NewEventType()
EVT_SELECT_SLICE = wx.PyEventBinder(myEVT_SELECT_SLICE, 1)

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

        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.VERTICAL)
        self.splitter = splitter
        
        panel = wx.Panel(self)
        button = wx.Button(panel, -1, _("Import medical images"), (20, 20))

        inner_sizer = wx.BoxSizer()
        inner_sizer.Add(button, 0, wx.ALIGN_CENTER_HORIZONTAL, 40)
        panel.SetSizer(inner_sizer)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(splitter, 20, wx.EXPAND)
        sizer.Add(panel, 1, wx.EXPAND)
       
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)
 
        self.text_panel = TextPanel(splitter)
        splitter.AppendWindow(self.text_panel, 250)
        
        self.image_panel = ImagePanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)
        
        self._bind_events()
        self._bind_pubsubevt()
        
    def _bind_pubsubevt(self):
        ps.Publisher().subscribe(self.ShowDicomPreview, "Load import panel")

    def _bind_events(self):
        self.Bind(EVT_SELECT_SERIE, self.OnSelectSerie)
        self.Bind(EVT_SELECT_SLICE, self.OnSelectSlice)
        self.Bind(EVT_SELECT_PATIENT, self.OnSelectPatient)
    
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
        print "You've selected the slice", evt.GetSelectID()

    def OnSelectPatient(self, evt):
        print "You've selected the patient", evt.GetSelectID()
        
        
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
        ps.Publisher().subscribe(self.SelectSeries, 'Select series in import panel')

    def __bind_events_wx(self):
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def __init_gui(self):
        tree = gizmos.TreeListCtrl(self, -1, style =
                                   wx.TR_DEFAULT_STYLE
                                   | wx.TR_HIDE_ROOT
                                   | wx.TR_ROW_LINES
                                   | wx.TR_COLUMN_LINES
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

    def SelectSeries(self, pubsub_evt):
        group_index = pubsub_evt.data

    def Populate(self, patient_list):
        tree = self.tree
        
        first = 0
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
        print "parent select", parent_select
        
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)
        tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged)

    def OnSelChanged(self, evt):
        item = self.tree.GetSelection()
        if self._selected_by_user:
            print "Yes, I'm here"
            group = self.tree.GetItemPyData(item)
            if isinstance(group, dcm.DicomGroup):
                ps.Publisher().sendMessage('Load group into import panel',
                                            group)

            elif isinstance(group, dcm.PatientGroup):
                id = group.GetDicomSample().patient.id
                my_evt = SelectEvent(myEVT_SELECT_PATIENT, self.GetId())
                my_evt.SetSelectedID(id)
                self.GetEventHandler().ProcessEvent(my_evt)

                ps.Publisher().sendMessage('Load patient into import panel',
                                            group)
        else:
            parent_id = self.tree.GetItemParent(item)
            self.tree.Expand(parent_id)
        evt.Skip()

    def OnActivate(self, evt):
        item = evt.GetItem()
        group = self.tree.GetItemPyData(item)
        if isinstance(group, dcm.DicomGroup):
            ps.Publisher().sendMessage('Open DICOM group',
                                        group)
        else:
            if self.tree.IsExpanded(item):
                self.tree.Collapse(item)
            else:
                self.tree.Expand(item)

    def OnSize(self, evt):
        self.tree.SetSize(self.GetSize())

    def SelectSerie(self, serie):
        self._selected_by_user = False
        item = self.idserie_treeitem[serie]
        self.tree.SelectItem(item)
        self._selected_by_user = True


class ImagePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self._init_ui()
        self._bind_events()

    def _init_ui(self):
        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.HORIZONTAL)
        self.splitter = splitter

        splitter.ContainingSizer = wx.BoxSizer(wx.HORIZONTAL)
        
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
        self.text_panel.Bind(EVT_SELECT_SERIE, self.OnSelectSerie)
        self.text_panel.Bind(EVT_SELECT_SLICE, self.OnSelectSlice)

    def OnSelectSerie(self, evt):
        print "Hi, You selected Serie"
        evt.Skip()

    def OnSelectSlice(self, evt):
        print "Hi, You selected slice"
        print "Selected ID", evt.GetSelectID()
        self.image_panel.dicom_preview.ShowSlice(evt.GetSelectID())
        evt.Skip()

    def SetSerie(self, serie):
        self.image_panel.dicom_preview.SetDicomGroup(serie)

        
class SeriesPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        #self.SetBackgroundColour((0,0,0)) 

        self.serie_preview = dpp.DicomPreviewSeries(self)
        self.dicom_preview = dpp.DicomPreviewSlice(self)
        self.dicom_preview.Show(0)
       
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer.Add(self.serie_preview, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Add(self.dicom_preview, 1, wx.EXPAND | wx.ALL, 5)
        self.sizer.Fit(self)

        self.SetSizer(self.sizer)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.__bind_evt()
        self._bind_gui_evt()

    def __bind_evt(self):
        ps.Publisher().subscribe(self.ShowDicomSeries, 'Load dicom preview')
        ps.Publisher().subscribe(self.SetDicomSeries, 'Load group into import panel')
        ps.Publisher().subscribe(self.SetPatientSeries, 'Load patient into import panel')

    def _bind_gui_evt(self):
        self.serie_preview.Bind(dpp.EVT_CLICK_SERIE, self.OnSelectSerie)
        self.dicom_preview.Bind(dpp.EVT_CLICK_SLICE, self.OnSelectSlice)

    def SetDicomSeries(self, pubsub_evt):
        group = pubsub_evt.data
        self.dicom_preview.SetDicomGroup(group)
        self.dicom_preview.Show(1)
        self.serie_preview.Show(0)
        self.sizer.Layout()
        self.Update()

    def SetPatientSeries(self, pubsub_evt):
        patient = pubsub_evt.data
        
        self.dicom_preview.Show(0)
        self.serie_preview.Show(1)
            
        self.serie_preview.SetPatientGroups(patient)
        self.dicom_preview.SetPatientGroups(patient)  
         
        self.Update()

    def OnSelectSerie(self, evt):
        print "Hey, You selected a serie"
        serie = evt.GetItemData()
        data = evt.GetItemData()
        
        my_evt = SelectEvent(myEVT_SELECT_SERIE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())
        self.GetEventHandler().ProcessEvent(my_evt)

        #self.dicom_preview.SetDicomGroup(serie)
        #self.dicom_preview.Show(1)
        #self.serie_preview.Show(0)
        self.sizer.Layout()
        #self.Show()
        self.Update()

    def OnSelectSlice(self, evt):
        print "Hey, Ho, Let's go", evt.GetSelectID()

        my_evt = SelectEvent(myEVT_SELECT_SLICE, self.GetId())
        my_evt.SetSelectedID(evt.GetSelectID())
        my_evt.SetItemData(evt.GetItemData())
        self.GetEventHandler().ProcessEvent(my_evt)

    def ShowDicomSeries(self, pubsub_evt):
        patient = pubsub_evt.data
        if isinstance(patient, dcm.PatientGroup):        
            self.serie_preview.SetPatientGroups(patient)
            self.dicom_preview.SetPatientGroups(patient)


class SlicePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.__init_gui()
        self.__bind_evt()

    def __bind_evt(self):
        ps.Publisher().subscribe(self.ShowDicomSeries, 'Load dicom preview')
        ps.Publisher().subscribe(self.SetDicomSeries, 'Load group into import panel')
        ps.Publisher().subscribe(self.SetPatientSeries, 'Load patient into import panel')

    def __init_gui(self):
        self.SetBackgroundColour((255,255,255))
        print "----------------------------"
        self.dicom_preview = dpp.SingleImagePreview(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.dicom_preview, 1, wx.GROW|wx.EXPAND)
        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)
        self.sizer = sizer

    def SetPatientSeries(self, pubsub_evt):
        patient = pubsub_evt.data
        group = patient.GetGroups()[0]
        self.dicom_preview.SetDicomGroup(group)
        self.sizer.Layout()
        self.Update()

    def SetDicomSeries(self, evt):
        group = evt.data
        self.dicom_preview.SetDicomGroup(group)
        self.sizer.Layout()
        self.Update()

    def ShowDicomSeries(self, pubsub_evt):
        patient = pubsub_evt.data
        group = patient.GetGroups()[0]
        self.dicom_preview.SetDicomGroup(group)
        self.sizer.Layout()
        self.Update() 


