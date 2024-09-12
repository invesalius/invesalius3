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

# from dicionario import musicdata
# from dicionario import musicdata
import wx.lib.splitter as spl

import invesalius.constants as const
import invesalius.gui.dialogs as dlg

# import invesalius.gui.dicom_preview_panel as dpp
import invesalius.reader.dicom_grouper as dcm
from invesalius.gui.network.host_find_panel import HostFindPanel
from invesalius.gui.network.text_panel import TextPanel
from invesalius.i18n import tr as _

myEVT_SELECT_SERIE = wx.NewEventType()
EVT_SELECT_SERIE = wx.PyEventBinder(myEVT_SELECT_SERIE, 1)

myEVT_SELECT_SLICE = wx.NewEventType()
EVT_SELECT_SLICE = wx.PyEventBinder(myEVT_SELECT_SLICE, 1)

myEVT_SELECT_PATIENT = wx.NewEventType()
EVT_SELECT_PATIENT = wx.PyEventBinder(myEVT_SELECT_PATIENT, 1)

myEVT_SELECT_SERIE_TEXT = wx.NewEventType()
EVT_SELECT_SERIE_TEXT = wx.PyEventBinder(myEVT_SELECT_SERIE_TEXT, 1)


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
        if (self.first_image_selection != None) and (
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
