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

import time
from functools import partial

import numpy as np

try:
    import Trekker  # noqa: F401

    has_trekker = True
except ImportError:
    has_trekker = False

try:
    # TODO: the try-except could be done inside the mTMS() method call
    from invesalius.navigation.mtms import mTMS

    mTMS()
    has_mTMS = True
except Exception:
    has_mTMS = False

import wx
import wx.lib.masked.numctrl

import invesalius.constants as const
import invesalius.data.brainmesh_handler as brain
import invesalius.gui.dialogs as dlg
import invesalius.session as ses
from invesalius.i18n import tr as _
from invesalius.navigation.navigation import Navigation
from invesalius.net.neuronavigation_api import NeuronavigationApi
from invesalius.net.pedal_connection import PedalConnector
from invesalius.pubsub import pub as Publisher


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        neuronavigation_api = NeuronavigationApi()
        pedal_connector = PedalConnector(neuronavigation_api, self)
        navigation = Navigation(
            pedal_connector=pedal_connector,
            neuronavigation_api=neuronavigation_api,
        )

        inner_panel = InnerTaskPanel(self, navigation)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent, navigation):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        self.__bind_events()

        self.SetBackgroundColour(default_colour)
        self.e_field_loaded = False
        self.e_field_brain = None
        self.e_field_mesh = None
        self.cortex_file = None
        self.meshes_file = None
        self.multilocus_coil = None
        self.coil = None
        self.ci = None
        self.co = None
        self.sleep_nav = const.SLEEP_NAVIGATION
        self.navigation = navigation
        self.session = ses.Session()
        #  Check box to enable e-field visualization
        enable_efield = wx.CheckBox(self, -1, _("Enable E-field"))
        enable_efield.SetValue(False)
        enable_efield.Enable(True)
        enable_efield.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableEfield, ctrl=enable_efield))
        self.enable_efield = enable_efield

        # plot_vectors = wx.CheckBox(self, -1, _('Plot Efield vectors'))
        # plot_vectors.SetValue(False)
        # plot_vectors.Enable(1)
        # plot_vectors.Bind(wx.EVT_CHECKBOX, partial(self.OnEnablePlotVectors, ctrl=plot_vectors))

        show_area = wx.CheckBox(self, -1, _("Show area above threshold"))
        show_area.SetValue(False)
        show_area.Enable(True)
        show_area.Bind(
            wx.EVT_CHECKBOX, partial(self.OnEnableShowAreaAboveThreshold, ctrl=show_area)
        )

        efield_tools = wx.CheckBox(self, -1, _("Enable Efield targeting tools"))
        efield_tools.SetValue(False)
        efield_tools.Enable(True)
        efield_tools.Bind(
            wx.EVT_CHECKBOX, partial(self.OnEnableEfieldTargetingTools, ctrl=efield_tools)
        )

        efield_cortex_markers = wx.CheckBox(self, -1, _("View cortex Markers"))
        efield_cortex_markers.SetValue(True)
        efield_cortex_markers.Enable(True)
        efield_cortex_markers.Bind(
            wx.EVT_CHECKBOX, partial(self.OnViewCortexMarkers, ctrl=efield_cortex_markers)
        )

        efield_save_automatically = wx.CheckBox(self, -1, _("Save Automatically"))
        efield_save_automatically.SetValue(False)
        efield_save_automatically.Enable(True)
        efield_save_automatically.Bind(
            wx.EVT_CHECKBOX, partial(self.OnSaveEfieldAutomatically, ctrl=efield_save_automatically)
        )

        tooltip2 = _("Load Brain Json config")
        btn_act2 = wx.Button(self, -1, _("Load Config"), size=wx.Size(100, 23))
        btn_act2.SetToolTip(tooltip2)
        btn_act2.Enable(True)
        btn_act2.Bind(wx.EVT_BUTTON, self.OnAddConfig)

        tooltip = _("Save Efield")
        self.btn_save = wx.Button(self, -1, _("Save Efield"), size=wx.Size(80, -1))
        self.btn_save.SetToolTip(tooltip)
        self.btn_save.Bind(wx.EVT_BUTTON, self.OnSaveEfield)
        self.btn_save.Enable(False)

        tooltip3 = _("Save All Efield")
        self.btn_all_save = wx.Button(self, -1, _("Save All Efield"), size=wx.Size(80, -1))
        self.btn_all_save.SetToolTip(tooltip3)
        self.btn_all_save.Bind(wx.EVT_BUTTON, self.OnSaveAllDataEfield)
        self.btn_all_save.Enable(False)

        text_sleep = wx.StaticText(self, -1, _("Sleep (s):"))
        spin_sleep = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        spin_sleep.Enable(True)
        spin_sleep.SetRange(0.05, 10.0)
        spin_sleep.SetValue(self.sleep_nav)
        spin_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectSleep, ctrl=spin_sleep))
        spin_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectSleep, ctrl=spin_sleep))

        text_threshold = wx.StaticText(self, -1, _("Threshold:"))
        spin_threshold = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        spin_threshold.Enable(True)
        spin_threshold.SetRange(0.1, 1)
        spin_threshold.SetValue(const.EFIELD_MAX_RANGE_SCALE)
        spin_threshold.Bind(wx.EVT_TEXT, partial(self.OnSelectThreshold, ctrl=spin_threshold))
        spin_threshold.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectThreshold, ctrl=spin_threshold))

        text_ROI_size = wx.StaticText(self, -1, _("ROI size:"))
        spin_ROI_size = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        spin_ROI_size.Enable(True)
        spin_ROI_size.SetValue(const.EFIELD_ROI_SIZE)
        spin_ROI_size.Bind(wx.EVT_TEXT, partial(self.OnSelectROISize, ctrl=spin_ROI_size))
        spin_ROI_size.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectROISize, ctrl=spin_ROI_size))

        combo_surface_name_title = wx.StaticText(self, -1, _("Change coil:"))
        self.combo_change_coil = wx.ComboBox(
            self, -1, size=(100, 23), pos=(25, 20), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        # combo_surface_name.SetSelection(0)
        self.combo_change_coil.Bind(wx.EVT_COMBOBOX_DROPDOWN, self.OnComboCoilNameClic)
        self.combo_change_coil.Bind(wx.EVT_COMBOBOX, self.OnComboCoil)
        self.combo_change_coil.Insert("Select coil:", 0)
        self.combo_change_coil.Enable(False)

        value = str(0)
        tooltip = _("dt(\u03bc s)")
        self.input_dt = wx.TextCtrl(self, value=str(60), size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_dt.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_dt.SetBackgroundColour("WHITE")
        self.input_dt.SetEditable(1)
        self.input_dt.SetToolTip(tooltip)

        tooltip = _("dI")
        self.input_coil1 = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_coil1.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_coil1.SetBackgroundColour("WHITE")
        self.input_coil1.SetEditable(1)
        self.input_coil1.SetToolTip(tooltip)

        self.input_coil2 = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_coil2.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_coil2.SetBackgroundColour("WHITE")
        self.input_coil2.SetEditable(1)
        self.input_coil2.SetToolTip(tooltip)

        self.input_coil3 = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_coil3.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_coil3.SetBackgroundColour("WHITE")
        self.input_coil3.SetEditable(1)
        self.input_coil3.SetToolTip(tooltip)

        self.input_coil4 = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_coil4.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_coil4.SetBackgroundColour("WHITE")
        self.input_coil4.SetEditable(1)
        self.input_coil4.SetToolTip(tooltip)

        self.input_coil5 = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_coil5.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_coil5.SetBackgroundColour("WHITE")
        self.input_coil5.SetEditable(1)
        self.input_coil5.SetToolTip(tooltip)

        tooltip = _("mtms coords")
        text_input_coord = wx.StaticText(self, -1, _("mtms coords:"))
        self.input_coord = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        self.input_coord.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.input_coord.SetBackgroundColour("WHITE")
        self.input_coord.SetEditable(1)
        self.input_coord.SetToolTip(tooltip)

        tooltip = _("Enter mtms coord")
        btn_enter_mtms_coord = wx.Button(self, -1, _("Enter mtms coord"), size=wx.Size(80, -1))
        btn_enter_mtms_coord.SetToolTip(tooltip)
        btn_enter_mtms_coord.Bind(wx.EVT_BUTTON, self.OnEnterMtmsCoords)
        btn_enter_mtms_coord.Enable(True)

        tooltip = _("Enter Values")
        btn_enter = wx.Button(self, -1, _("Enter"), size=wx.Size(80, -1))
        btn_enter.SetToolTip(tooltip)
        btn_enter.Bind(wx.EVT_BUTTON, self.OnEnterdIPerdt)
        btn_enter.Enable(True)

        tooltip = _("Reset Values")
        btn_reset = wx.Button(self, -1, _("Reset"), size=wx.Size(80, -1))
        btn_reset.SetToolTip(tooltip)
        btn_reset.Bind(wx.EVT_BUTTON, self.OnReset)
        btn_reset.Enable(True)

        line_checkboxes = wx.BoxSizer(wx.HORIZONTAL)
        line_checkboxes.AddMany(
            [
                (enable_efield, 1, wx.LEFT | wx.RIGHT, 2),
                (show_area, 1, wx.LEFT | wx.RIGHT, 2),
                (efield_tools, 1, wx.LEFT | wx.RIGHT, 2),
            ]
        )

        line_change_coil_input_coord_text = wx.BoxSizer(wx.HORIZONTAL)
        line_change_coil_input_coord_text.AddMany(
            [(combo_surface_name_title, 0, wx.RIGHT), (text_input_coord, 0, wx.CENTER)]
        )

        line_change_coil_input_coord = wx.BoxSizer(wx.HORIZONTAL)
        line_change_coil_input_coord.AddMany(
            [
                (self.combo_change_coil, 1, wx.RIGHT, 2),
                (self.input_coord, 1, wx.LEFT, 2),
                (btn_enter_mtms_coord, 1, wx.LEFT, 2),
            ]
        )

        line_sleep = wx.BoxSizer(wx.HORIZONTAL)
        line_sleep.AddMany(
            [
                (text_sleep, 1, wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT),
                (spin_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW),
                (text_threshold, 1, wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT),
                (spin_threshold, 0, wx.ALL | wx.EXPAND | wx.GROW),
                (text_ROI_size, 1, wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT),
                (spin_ROI_size, 0, wx.ALL | wx.EXPAND | wx.GROW),
            ]
        )

        line_btns = wx.BoxSizer(wx.HORIZONTAL)
        line_btns.Add(btn_act2, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        line_btns_save = wx.BoxSizer(wx.HORIZONTAL)
        line_btns_save.Add(self.input_dt, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns_save.Add(self.btn_save, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns_save.Add(self.btn_all_save, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        line_mtms = wx.BoxSizer(wx.HORIZONTAL)
        text_mtms = wx.StaticText(self, -1, _("dI"))
        line_mtms.Add(
            self.input_coil1,
            0,
            wx.LEFT | wx.BOTTOM | wx.RIGHT,
        )
        line_mtms.Add(
            self.input_coil2,
            0,
            wx.LEFT | wx.BOTTOM | wx.RIGHT,
        )
        line_mtms.Add(
            self.input_coil3,
            0,
            wx.LEFT | wx.BOTTOM | wx.RIGHT,
        )
        line_mtms.Add(
            self.input_coil4,
            0,
            wx.LEFT | wx.BOTTOM | wx.RIGHT,
        )
        line_mtms.Add(
            self.input_coil5,
            0,
            wx.LEFT | wx.BOTTOM | wx.RIGHT,
        )

        line_mtms_buttoms = wx.BoxSizer(wx.HORIZONTAL)
        line_mtms_buttoms.AddMany(
            [
                (btn_enter, 0, wx.LEFT | wx.BOTTOM | wx.RIGHT),
                (btn_reset, 0, wx.LEFT | wx.BOTTOM | wx.RIGHT),
            ]
        )

        line_cortex_markers = wx.BoxSizer(wx.HORIZONTAL)
        line_cortex_markers.Add(efield_cortex_markers, 1, wx.LEFT | wx.RIGHT, 2)
        line_cortex_markers.Add(efield_save_automatically, 1, wx.LEFT | wx.RIGHT, 2)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL)
        main_sizer.Add(line_checkboxes, 1, wx.LEFT | wx.RIGHT, 2)
        main_sizer.Add(line_change_coil_input_coord_text, 0, wx.RIGHT)
        main_sizer.Add(line_change_coil_input_coord, 0, wx.RIGHT)
        main_sizer.Add(line_sleep, 0, wx.LEFT | wx.RIGHT | wx.TOP)
        main_sizer.Add(line_btns_save, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL)
        main_sizer.Add(text_mtms, 0, wx.BOTTOM | wx.ALIGN_LEFT)
        main_sizer.Add(line_mtms, 0, wx.BOTTOM | wx.ALIGN_LEFT)
        main_sizer.Add(line_mtms_buttoms, 0, wx.LEFT | wx.BOTTOM | wx.RIGHT)
        main_sizer.Add(line_cortex_markers, wx.BOTTOM | wx.ALIGN_CENTER)
        main_sizer.SetSizeHints(self)
        self.SetSizer(main_sizer)

    def __bind_events(self):
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")
        Publisher.subscribe(self.OnGetEfieldActor, "Get Efield actor from json")
        Publisher.subscribe(self.OnGetEfieldPaths, "Get Efield paths")
        Publisher.subscribe(self.OnGetMultilocusCoils, "Get multilocus paths from json")
        Publisher.subscribe(self.SendNeuronavigationApi, "Send Neuronavigation Api")
        Publisher.subscribe(self.GetEfieldDataStatus, "Get status of Efield saved data")
        Publisher.subscribe(self.GetIds, "Get dI for mtms")

    def OnAddConfig(self, evt):
        filename = dlg.LoadConfigEfield()
        if filename:
            convert_to_inv = dlg.ImportMeshCoordSystem()
            Publisher.sendMessage("Update status in GUI", value=50, label="Loading E-field...")
            Publisher.sendMessage("Update convert_to_inv flag", convert_to_inv=convert_to_inv)
            Publisher.sendMessage(
                "Read json config file for efield", filename=filename, convert_to_inv=convert_to_inv
            )
            self.e_field_brain = brain.E_field_brain(self.e_field_mesh)
            self.Init_efield()

    def Init_efield(self):
        self.navigation.neuronavigation_api.initialize_efield(
            cortex_model_path=self.cortex_file,
            mesh_models_paths=self.meshes_file,
            coil_model_path=self.coil,
            coil_set=False,
            conductivities_inside=self.ci,
            conductivities_outside=self.co,
            dI_per_dt=self.dIperdt_list,
        )
        Publisher.sendMessage("Update status in GUI", value=0, label="Ready")

    def OnEnableEfield(self, evt, ctrl):
        efield_enabled = ctrl.GetValue()
        self.plot_efield_vectors = ctrl.GetValue()
        self.navigation.plot_efield_vectors = self.plot_efield_vectors
        if efield_enabled:
            if self.session.GetConfig("debug_efield"):
                debug_efield_enorm = dlg.ShowLoadCSVDebugEfield()
                if isinstance(debug_efield_enorm, np.ndarray):
                    self.navigation.debug_efield_enorm = debug_efield_enorm
                else:
                    dlg.Efield_debug_Enorm_warning()
                    self.enable_efield.SetValue(False)
                    self.e_field_loaded = False
                    self.navigation.e_field_loaded = self.e_field_loaded
                    return
            else:
                if not self.navigation.neuronavigation_api.connection:
                    dlg.Efield_connection_warning()
                    # self.combo_surface_name.Enable(False)
                    self.enable_efield.Enable(False)
                    self.e_field_loaded = False
                    return
            Publisher.sendMessage("Initialize E-field brain", e_field_brain=self.e_field_brain)

            Publisher.sendMessage("Initialize color array")
            self.e_field_loaded = True
            self.combo_change_coil.Enable(True)
            self.btn_all_save.Enable(True)

        else:
            Publisher.sendMessage("Recolor again")
            self.e_field_loaded = False
            # self.combo_surface_name.Enable(True)
        self.navigation.e_field_loaded = self.e_field_loaded

    def OnEnablePlotVectors(self, evt, ctrl):
        self.plot_efield_vectors = ctrl.GetValue()
        self.navigation.plot_efield_vectors = self.plot_efield_vectors

    def OnEnableShowAreaAboveThreshold(self, evt, ctrl):
        enable = ctrl.GetValue()
        Publisher.sendMessage("Show area above threshold", enable=enable)

    def OnEnableEfieldTargetingTools(self, evt, ctrl):
        enable = ctrl.GetValue()
        Publisher.sendMessage("Enable Efield tools", enable=enable)

    def OnViewCortexMarkers(self, evt, ctrl):
        enable = ctrl.GetValue()
        Publisher.sendMessage("Display efield markers at cortex", display_flag=enable)

    def OnComboNameClic(self, evt):
        import invesalius.project as prj

        proj = prj.Project()
        self.combo_change_coil.Clear()
        for n in range(len(proj.surface_dict)):
            self.combo_change_coil.Insert(str(proj.surface_dict[n].name), n)

    def OnComboCoilNameClic(self, evt):
        self.combo_change_coil.Clear()
        if self.multilocus_coil is not None:
            for elements in range(len(self.multilocus_coil)):
                coil_name = self.multilocus_coil[elements].split("/")[-1].split(".bin")[0]
                self.combo_change_coil.Insert(coil_name, elements)

    def OnComboCoil(self, evt):
        # coil_name = evt.GetString()
        coil_index = evt.GetSelection()
        if coil_index == 6:
            coil_set = True
        else:
            coil_set = False
        self.OnChangeCoil(self.multilocus_coil[coil_index], coil_set)
        # self.e_field_mesh = self.proj.surface_dict[self.surface_index].polydata
        # Publisher.sendMessage('Get Actor', surface_index = self.surface_index)

    def OnChangeCoil(self, coil_model_path, coil_set):
        self.navigation.neuronavigation_api.efield_coil(
            coil_model_path=coil_model_path, coil_set=coil_set
        )

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if nav_status:
            self.enable_efield.Enable(False)
            self.btn_save.Enable(True)
        else:
            self.enable_efield.Enable(True)
            self.btn_save.Enable(False)

    def OnSelectSleep(self, evt, ctrl):
        self.sleep_nav = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage("Update sleep", data=self.sleep_nav)

    def OnSelectThreshold(self, evt, ctrl):
        threshold = ctrl.GetValue()
        Publisher.sendMessage("Update Efield Threshold", data=threshold)

    def OnSelectROISize(self, evt, ctrl):
        ROI_size = ctrl.GetValue()
        Publisher.sendMessage("Update Efield ROI size", data=ROI_size)

    def OnGetEfieldActor(self, efield_actor, surface_index_cortex):
        self.e_field_mesh = efield_actor
        self.surface_index = surface_index_cortex
        Publisher.sendMessage("Get Actor", surface_index=self.surface_index)

    def OnGetEfieldPaths(self, path_meshes, cortex_file, meshes_file, coil, ci, co, dIperdt_list):
        self.path_meshes = path_meshes
        self.cortex_file = cortex_file
        self.meshes_file = meshes_file
        self.ci = ci
        self.co = co
        self.coil = coil
        self.dIperdt_list = dIperdt_list

    def OnGetMultilocusCoils(self, multilocus_coil_list):
        self.multilocus_coil = multilocus_coil_list

    def OnSaveEfieldAutomatically(self, evt, ctrl):
        enable = ctrl.GetValue()
        Publisher.sendMessage(
            "Save automatically efield data",
            enable=enable,
            path_meshes=self.path_meshes,
            plot_efield_vectors=self.navigation.plot_efield_vectors,
        )

    def OnSaveEfield(self, evt):
        import invesalius.project as prj

        proj = prj.Project()
        timestamp = time.localtime(time.time())
        stamp_date = f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
        stamp_time = f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
        sep = "-"
        if self.path_meshes is None:
            import os

            current_folder_path = os.getcwd()
        else:
            current_folder_path = self.path_meshes
        parts = [current_folder_path, "/", stamp_date, stamp_time, proj.name, "Efield"]
        default_filename = sep.join(parts) + ".csv"

        filename = dlg.ShowLoadSaveDialog(
            message=_("Save markers as..."),
            wildcard="(*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            default_filename=default_filename,
        )

        if not filename:
            return
        plot_efield_vectors = self.navigation.plot_efield_vectors
        Publisher.sendMessage(
            "Save Efield data",
            filename=filename,
            plot_efield_vectors=plot_efield_vectors,
            marker_id=None,
        )

    def OnSaveAllDataEfield(self, evt):
        Publisher.sendMessage("Check efield data")
        if self.efield_data_saved:
            import invesalius.project as prj

            proj = prj.Project()
            timestamp = time.localtime(time.time())
            stamp_date = f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
            stamp_time = f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
            sep = "-"
            if self.path_meshes is None:
                import os

                current_folder_path = os.getcwd()
            else:
                current_folder_path = self.path_meshes
            parts = [current_folder_path, "/", stamp_date, stamp_time, proj.name, "Efield"]
            default_filename = sep.join(parts) + ".csv"

            filename = dlg.ShowLoadSaveDialog(
                message=_("Save markers as..."),
                wildcard="(*.csv)|*.csv",
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                default_filename=default_filename,
            )

            if not filename:
                return

            Publisher.sendMessage("Save all Efield data", filename=filename)
        else:
            dlg.Efield_no_data_to_save_warning()

    def SendNeuronavigationApi(self):
        Publisher.sendMessage(
            "Get Neuronavigation Api", neuronavigation_api=self.navigation.neuronavigation_api
        )

    def GetEfieldDataStatus(self, efield_data_loaded, indexes_saved_list):
        self.efield_data_saved = efield_data_loaded

    def OnEnterdIPerdt(self, evt):
        input_dt = 1 / (float(self.input_dt.GetValue()) * 1e-6)
        self.input_coils = [
            float(self.input_coil1.GetValue()),
            float(self.input_coil2.GetValue()),
            float(self.input_coil3.GetValue()),
            float(self.input_coil4.GetValue()),
            float(self.input_coil5.GetValue()),
        ]
        self.input_coils = np.array(self.input_coils) * input_dt
        self.input_coils = self.input_coils.tolist()
        self.navigation.neuronavigation_api.set_dIperdt(
            dIperdt=self.input_coils,
        )

    def OnEnterMtmsCoords(self, evt):
        input_coord_str = self.input_coord.GetValue()
        input_coord = [int(i) for i in input_coord_str.split(",") if i]
        Publisher.sendMessage("Send mtms coords", mtms_coord=input_coord)

    def SenddI(self, dIs):
        self.OnChangeCoil(self.multilocus_coil[6], True)
        input_dt = 1 / (float(self.input_dt.GetValue()) * 1e-6)
        dIs[1] = -dIs[1]
        dIs[2] = -dIs[2]
        self.input_coils = dIs
        self.input_coils = np.array(self.input_coils) * input_dt
        self.input_coil1.SetValue(str(dIs[0]))
        self.input_coil2.SetValue(str(dIs[1]))
        self.input_coil3.SetValue(str(dIs[2]))
        self.input_coil4.SetValue(str(dIs[3]))
        self.input_coil5.SetValue(str(dIs[4]))

        self.navigation.neuronavigation_api.set_dIperdt(
            dIperdt=self.input_coils,
        )

    def GetIds(self, dIs):
        self.SenddI(dIs)

    def OnReset(self, evt):
        Publisher.sendMessage("Get targets Ids for mtms", target1_origin=[0, 0], target2=[0, 0])
