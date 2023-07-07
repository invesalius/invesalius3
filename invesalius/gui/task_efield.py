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
import os

import dataclasses
from functools import partial
import itertools
import time

import nibabel as nb
import numpy as np
try:
    import Trekker
    has_trekker = True
except ImportError:
    has_trekker = False

try:
    #TODO: the try-except could be done inside the mTMS() method call
    from invesalius.navigation.mtms import mTMS
    mTMS()
    has_mTMS = True
except:
    has_mTMS = False

import wx

try:
    import wx.lib.agw.foldpanelbar as fpb
except ImportError:
    import wx.lib.foldpanelbar as fpb

import wx.lib.colourselect as csel
import wx.lib.masked.numctrl
from invesalius.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.brainmesh_handler as brain

import invesalius.data.imagedata_utils as imagedata_utils
import invesalius.data.slice_ as sl
import invesalius.data.tractography as dti
import invesalius.data.record_coords as rec
import invesalius.data.vtk_utils as vtk_utils
import invesalius.data.bases as db
import invesalius.data.coregistration as dcr
import invesalius.gui.dialogs as dlg
import invesalius.project as prj
import invesalius.session as ses

from invesalius import utils
from invesalius.gui import utils as gui_utils
from invesalius.navigation.iterativeclosestpoint import IterativeClosestPoint
from invesalius.navigation.navigation import Navigation
from invesalius.navigation.image import Image
from invesalius.navigation.tracker import Tracker

from invesalius.navigation.robot import Robot
from invesalius.data.converters import to_vtk, convert_custom_bin_to_vtk

from invesalius.net.neuronavigation_api import NeuronavigationApi

HAS_PEDAL_CONNECTION = True
try:
    from invesalius.net.pedal_connection import PedalConnection
except ImportError:
    HAS_PEDAL_CONNECTION = False

from invesalius import inv_paths

class TaskPanel(wx.Panel):
    def __init__(self, parent):

        pedal_connection = PedalConnection() if HAS_PEDAL_CONNECTION else None
        neuronavigation_api = NeuronavigationApi()
        navigation = Navigation(
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )

        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self, navigation)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class InnerTaskPanel(wx.Panel):
    def __init__(self, parent, navigation):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
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
        enable_efield = wx.CheckBox(self, -1, _('Enable E-field'))
        enable_efield.SetValue(False)
        enable_efield.Enable(1)
        enable_efield.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableEfield, ctrl=enable_efield))
        self.enable_efield = enable_efield

        tooltip2 = wx.ToolTip(_("Load Brain Json config"))
        btn_act2 = wx.Button(self, -1, _("Load Config"), size=wx.Size(100, 23))
        btn_act2.SetToolTip(tooltip2)
        btn_act2.Enable(1)
        btn_act2.Bind(wx.EVT_BUTTON, self.OnAddConfig)

        tooltip = wx.ToolTip(_("Save Efield"))
        self.btn_save = wx.Button(self, -1, _("Save Efield"), size=wx.Size(80, -1))
        self.btn_save.SetToolTip(tooltip)
        self.btn_save.Bind(wx.EVT_BUTTON, self.OnSaveEfield)
        self.btn_save.Enable(False)

        text_sleep = wx.StaticText(self, -1, _("Sleep (s):"))
        spin_sleep = wx.SpinCtrlDouble(self, -1, "", size = wx.Size(50,23), inc = 0.01)
        spin_sleep.Enable(1)
        spin_sleep.SetRange(0.05,10.0)
        spin_sleep.SetValue(self.sleep_nav)
        spin_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectSleep, ctrl=spin_sleep))
        spin_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectSleep, ctrl=spin_sleep))

        border = 1
        line_sleep = wx.BoxSizer(wx.VERTICAL)
        line_sleep.AddMany([(text_sleep, 1, wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                            (spin_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])
        line_btns = wx.BoxSizer(wx.HORIZONTAL)
        line_btns.Add(btn_act2, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        line_btns_save = wx.BoxSizer(wx.HORIZONTAL)
        line_btns_save.Add(self.btn_save, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        # Add line sizers into main sizer
        border_last = 5
        txt_surface = wx.StaticText(self, -1, _('Change coil:'), pos=(0,100))
        self.combo_surface_name = wx.ComboBox(self, -1, size=(210, 23), pos=(25, 50),
                                              style=wx.CB_DROPDOWN | wx.CB_READONLY)
        # combo_surface_name.SetSelection(0)
        self.combo_surface_name.Bind(wx.EVT_COMBOBOX_DROPDOWN, self.OnComboCoilNameClic)
        self.combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboCoil)
        self.combo_surface_name.Insert('Select coil:',0)
        self.combo_surface_name.Enable(False)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, border_last)
        main_sizer.Add(enable_efield, 1, wx.LEFT | wx.RIGHT, 2)
        main_sizer.Add(line_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(self.combo_surface_name, 1, wx.BOTTOM | wx.ALIGN_RIGHT)
        main_sizer.Add(line_btns_save, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, border_last)

        main_sizer.SetSizeHints(self)
        self.SetSizer(main_sizer)

    def __bind_events(self):
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.OnGetEfieldActor, 'Get Efield actor from json')
        Publisher.subscribe(self.OnGetEfieldPaths, 'Get Efield paths')
        Publisher.subscribe(self.OnGetMultilocusCoils,'Get multilocus paths from json')

    def OnAddConfig(self, evt):
        filename = dlg.LoadConfigEfield()
        if filename:
            convert_to_inv = dlg.ImportMeshCoordSystem()
            Publisher.sendMessage('Update status in GUI', value=50, label="Loading E-field...")
            Publisher.sendMessage('Update convert_to_inv flag', convert_to_inv=convert_to_inv)
            Publisher.sendMessage('Read json config file for efield', filename=filename, convert_to_inv=convert_to_inv)
            self.Init_efield()

    def Init_efield(self):
        self.navigation.neuronavigation_api.initialize_efield(
            cortex_model_path=self.cortex_file,
            mesh_models_paths=self.meshes_file,
            coil_model_path=self.coil,
            conductivities_inside=self.ci,
            conductivities_outside=self.co,
        )
        Publisher.sendMessage('Update status in GUI', value=0, label="Ready")

    def OnEnableEfield(self, evt, ctrl):
        efield_enabled = ctrl.GetValue()
        if efield_enabled:
            if self.session.GetConfig('debug_efield'):
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
                    #self.combo_surface_name.Enable(False)
                    self.enable_efield.Enable(False)
                    self.e_field_loaded = False
                    return
            self.e_field_brain = brain.E_field_brain(self.e_field_mesh)
            Publisher.sendMessage('Initialize E-field brain', e_field_brain=self.e_field_brain)

            Publisher.sendMessage('Initialize color array')
            self.e_field_loaded = True
            self.combo_surface_name.Enable(True)
            self.btn_save.Enable(True)
        else:
            Publisher.sendMessage('Recolor again')
            self.e_field_loaded = False
            #self.combo_surface_name.Enable(True)
        self.navigation.e_field_loaded = self.e_field_loaded

    def OnComboNameClic(self, evt):
        import invesalius.project as prj
        proj = prj.Project()
        self.combo_surface_name.Clear()
        for n in range(len(proj.surface_dict)):
            self.combo_surface_name.Insert(str(proj.surface_dict[n].name), n)

    def OnComboCoilNameClic(self, evt):
        self.combo_surface_name.Clear()
        if self.multilocus_coil is not None:
            for elements in range(len(self.multilocus_coil)):
                self.combo_surface_name.Insert(self.multilocus_coil[elements], elements)

    def OnComboCoil(self, evt):
        coil_name = evt.GetString()
        coil_index = evt.GetSelection()
        self.OnChangeCoil(self.multilocus_coil[coil_index])
        #self.e_field_mesh = self.proj.surface_dict[self.surface_index].polydata
        #Publisher.sendMessage('Get Actor', surface_index = self.surface_index)

    def OnChangeCoil(self, coil_model_path):
        self.navigation.neuronavigation_api.efield_coil(
            coil_model_path=coil_model_path,
        )

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if nav_status:
            self.enable_efield.Enable(False)
        else:
            self.enable_efield.Enable(True)

    def OnSelectSleep(self, evt, ctrl):
        self.sleep_nav = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage('Update sleep', data=self.sleep_nav)

    def OnGetEfieldActor(self, efield_actor, surface_index_cortex):
        self.e_field_mesh = efield_actor
        self.surface_index= surface_index_cortex
        Publisher.sendMessage('Get Actor', surface_index = self.surface_index)

    def OnGetEfieldPaths(self, path_meshes, cortex_file, meshes_file, coil, ci, co):
        self.path_meshes = path_meshes
        self.cortex_file = cortex_file
        self.meshes_file = meshes_file
        self.ci = ci
        self.co = co
        self.coil = coil

    def OnGetMultilocusCoils(self, multilocus_coil_list):
        self.multilocus_coil = multilocus_coil_list

    def OnSaveEfield(self, evt):
        import invesalius.project as prj

        proj = prj.Project()
        timestamp = time.localtime(time.time())
        stamp_date = '{:0>4d}{:0>2d}{:0>2d}'.format(timestamp.tm_year, timestamp.tm_mon, timestamp.tm_mday)
        stamp_time = '{:0>2d}{:0>2d}{:0>2d}'.format(timestamp.tm_hour, timestamp.tm_min, timestamp.tm_sec)
        sep = '-'
        if self.path_meshes is None:
            import os
            current_folder_path = os.getcwd()
        else:
            current_folder_path = self.path_meshes
        parts = [current_folder_path,'/',stamp_date, stamp_time, proj.name, 'Efield']
        default_filename = sep.join(parts) + '.txt'

        filename = dlg.ShowLoadSaveDialog(message=_(u"Save markers as..."),
                                          wildcard='(*.txt)|*.txt',
                                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                          default_filename=default_filename)

        if not filename:
            return

        Publisher.sendMessage('Save Efield data', filename = filename)
