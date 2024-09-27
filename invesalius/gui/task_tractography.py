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

import nibabel as nb
import numpy as np

try:
    import Trekker

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

import multiprocessing
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import wx
import wx.lib.agw.genericmessagedialog as GMD
import wx.lib.masked.numctrl

import invesalius.constants as const
import invesalius.data.brainmesh_handler as brain
import invesalius.data.slice_ as sl
import invesalius.data.tractography as dti
import invesalius.data.vtk_utils as vtk_utils
import invesalius.gui.dialogs as dlg
import invesalius.project as prj
import invesalius.utils as utils
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)

        self.SetBackgroundColour(default_colour)

        self.affine = np.identity(4)
        self.affine_vtk = None
        self.trekker = None
        self.n_tracts = const.N_TRACTS
        self.peel_depth = const.PEEL_DEPTH
        self.view_tracts = False
        self.seed_offset = const.SEED_OFFSET
        self.seed_radius = const.SEED_RADIUS
        self.brain_opacity = const.BRAIN_OPACITY
        self.brain_peel = None
        self.brain_actor = None
        self.n_peels = const.MAX_PEEL_DEPTH
        self.p_old = np.array([[0.0, 0.0, 0.0]])
        self.tracts_run = None
        self.trekker_cfg = const.TREKKER_CONFIG
        self.nav_status = False
        self.peel_loaded = False
        self.SetAutoLayout(1)
        self.__bind_events()

        # Button for loading Trekker FOD
        tooltip = _("Load FOD")
        btn_load = wx.Button(self, -1, _("FOD"), size=wx.Size(50, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(True)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLinkFOD)

        # Button for loading Trekker configuration
        tooltip = _("Load Trekker configuration parameters")
        btn_load_cfg = wx.Button(self, -1, _("Configure"), size=wx.Size(65, 23))
        btn_load_cfg.SetToolTip(tooltip)
        btn_load_cfg.Enable(True)
        btn_load_cfg.Bind(wx.EVT_BUTTON, self.OnLoadParameters)

        # Button for creating peel
        tooltip = _("Create peel")
        btn_mask = wx.Button(self, -1, _("Peel"), size=wx.Size(50, 23))
        btn_mask.SetToolTip(tooltip)
        btn_mask.Enable(True)
        btn_mask.Bind(wx.EVT_BUTTON, self.OnCreatePeel)

        # Button for creating new coil
        tooltip = _("Load anatomical labels")
        btn_act = wx.Button(self, -1, _("ACT"), size=wx.Size(50, 23))
        btn_act.SetToolTip(tooltip)
        btn_act.Enable(True)
        btn_act.Bind(wx.EVT_BUTTON, self.OnLoadACT)

        # Create a horizontal sizer to represent button save
        line_btns = wx.BoxSizer(wx.HORIZONTAL)
        line_btns.Add(btn_load, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns.Add(btn_load_cfg, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns.Add(btn_mask, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)
        line_btns.Add(btn_act, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        # Change peeling depth
        text_peel_depth = wx.StaticText(self, -1, _("Peeling depth (mm):"))
        spin_peel_depth = wx.SpinCtrl(self, -1, "", size=wx.Size(50, 23))
        spin_peel_depth.Enable(True)
        spin_peel_depth.SetRange(0, const.MAX_PEEL_DEPTH)
        spin_peel_depth.SetValue(const.PEEL_DEPTH)
        spin_peel_depth.Bind(wx.EVT_TEXT, partial(self.OnSelectPeelingDepth, ctrl=spin_peel_depth))
        spin_peel_depth.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectPeelingDepth, ctrl=spin_peel_depth)
        )

        # Change number of tracts
        text_ntracts = wx.StaticText(self, -1, _("Number tracts:"))
        spin_ntracts = wx.SpinCtrl(self, -1, "", size=wx.Size(50, 23))
        spin_ntracts.Enable(True)
        spin_ntracts.SetRange(1, 2000)
        spin_ntracts.SetValue(const.N_TRACTS)
        spin_ntracts.Bind(wx.EVT_TEXT, partial(self.OnSelectNumTracts, ctrl=spin_ntracts))
        spin_ntracts.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectNumTracts, ctrl=spin_ntracts))

        # Change seed offset for computing tracts
        text_offset = wx.StaticText(self, -1, _("Seed offset (mm):"))
        spin_offset = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_offset.Enable(True)
        spin_offset.SetRange(0, 100.0)
        spin_offset.SetValue(self.seed_offset)
        spin_offset.Bind(wx.EVT_TEXT, partial(self.OnSelectOffset, ctrl=spin_offset))
        spin_offset.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectOffset, ctrl=spin_offset))
        # self.spin_offset = spin_offset

        # Change seed radius for computing tracts
        text_radius = wx.StaticText(self, -1, _("Seed radius (mm):"))
        spin_radius = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_radius.Enable(True)
        spin_radius.SetRange(0, 100.0)
        spin_radius.SetValue(self.seed_radius)
        spin_radius.Bind(wx.EVT_TEXT, partial(self.OnSelectRadius, ctrl=spin_radius))
        spin_radius.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectRadius, ctrl=spin_radius))
        # self.spin_radius = spin_radius

        # Change sleep pause between navigation loops
        # text_sleep = wx.StaticText(self, -1, _("Sleep (s):"))
        # spin_sleep = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        # spin_sleep.Enable(1)
        # spin_sleep.SetRange(0.01, 10.0)
        # spin_sleep.SetValue(self.sleep_nav)
        # spin_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectSleep, ctrl=spin_sleep))
        # spin_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectSleep, ctrl=spin_sleep))

        # Change opacity of brain mask visualization
        text_opacity = wx.StaticText(self, -1, _("Brain opacity:"))
        spin_opacity = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_opacity.Enable(False)
        spin_opacity.SetRange(0, 1.0)
        spin_opacity.SetValue(self.brain_opacity)
        spin_opacity.Bind(wx.EVT_TEXT, partial(self.OnSelectOpacity, ctrl=spin_opacity))
        spin_opacity.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectOpacity, ctrl=spin_opacity))
        self.spin_opacity = spin_opacity

        # Create a horizontal sizer to threshold configs
        border = 1
        line_peel_depth = wx.BoxSizer(wx.HORIZONTAL)
        line_peel_depth.AddMany(
            [
                (text_peel_depth, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (spin_peel_depth, 0, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        line_ntracts = wx.BoxSizer(wx.HORIZONTAL)
        line_ntracts.AddMany(
            [
                (text_ntracts, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (spin_ntracts, 0, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        line_offset = wx.BoxSizer(wx.HORIZONTAL)
        line_offset.AddMany(
            [
                (text_offset, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (spin_offset, 0, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        line_radius = wx.BoxSizer(wx.HORIZONTAL)
        line_radius.AddMany(
            [
                (text_radius, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (spin_radius, 0, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        # line_sleep = wx.BoxSizer(wx.HORIZONTAL)
        # line_sleep.AddMany([(text_sleep, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
        #                     (spin_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, border)])

        line_opacity = wx.BoxSizer(wx.HORIZONTAL)
        line_opacity.AddMany(
            [
                (text_opacity, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, border),
                (spin_opacity, 0, wx.ALL | wx.EXPAND | wx.GROW, border),
            ]
        )

        # Check box to enable tract visualization
        checktracts = wx.CheckBox(self, -1, _("Enable tracts"))
        checktracts.SetValue(False)
        checktracts.Enable(False)
        checktracts.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableTracts, ctrl=checktracts))
        self.checktracts = checktracts

        # Check box to enable surface peeling
        checkpeeling = wx.CheckBox(self, -1, _("Peel surface"))
        checkpeeling.SetValue(False)
        checkpeeling.Enable(False)
        checkpeeling.Bind(wx.EVT_CHECKBOX, partial(self.OnShowPeeling, ctrl=checkpeeling))
        self.checkpeeling = checkpeeling

        # Check box to enable tract visualization
        checkACT = wx.CheckBox(self, -1, _("ACT"))
        checkACT.SetValue(False)
        checkACT.Enable(False)
        checkACT.Bind(wx.EVT_CHECKBOX, partial(self.OnEnableACT, ctrl=checkACT))
        self.checkACT = checkACT

        border_last = 1
        line_checks = wx.BoxSizer(wx.HORIZONTAL)
        line_checks.Add(checktracts, 0, wx.ALIGN_LEFT | wx.RIGHT | wx.LEFT, border_last)
        line_checks.Add(checkpeeling, 0, wx.ALIGN_CENTER | wx.RIGHT | wx.LEFT, border_last)
        line_checks.Add(checkACT, 0, wx.RIGHT | wx.LEFT, border_last)

        # Add line sizers into main sizer
        border = 1
        border_last = 10
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(line_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, border_last)
        main_sizer.Add(
            line_peel_depth, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border
        )
        main_sizer.Add(line_ntracts, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_offset, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_radius, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        # main_sizer.Add(line_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(line_opacity, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border)
        main_sizer.Add(
            line_checks,
            0,
            wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM,
            border_last,
        )
        main_sizer.Fit(self)

        self.SetSizer(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnUpdateTracts, "Set cross focal point")
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")

    def OnSelectPeelingDepth(self, evt, ctrl):
        self.peel_depth = ctrl.GetValue()
        if self.checkpeeling.GetValue():
            actor = self.brain_peel.get_actor(self.peel_depth)
            Publisher.sendMessage("Update peel", flag=True, actor=actor)
            Publisher.sendMessage(
                "Get peel centers and normals",
                centers=self.brain_peel.peel_centers,
                normals=self.brain_peel.peel_normals,
            )
            Publisher.sendMessage("Get init locator", locator=self.brain_peel.locator)
            self.peel_loaded = True

    def OnSelectNumTracts(self, evt, ctrl):
        self.n_tracts = ctrl.GetValue()
        # self.tract.n_tracts = ctrl.GetValue()
        Publisher.sendMessage("Update number of tracts", data=self.n_tracts)

    def OnSelectOffset(self, evt, ctrl):
        self.seed_offset = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage("Update seed offset", data=self.seed_offset)

    def OnSelectRadius(self, evt, ctrl):
        self.seed_radius = ctrl.GetValue()
        # self.tract.seed_offset = ctrl.GetValue()
        Publisher.sendMessage("Update seed radius", data=self.seed_radius)

    # def OnSelectSleep(self, evt, ctrl):
    #     self.sleep_nav = ctrl.GetValue()
    #     # self.tract.seed_offset = ctrl.GetValue()
    #     Publisher.sendMessage('Update sleep', data=self.sleep_nav)

    def OnSelectOpacity(self, evt, ctrl):
        self.brain_actor.GetProperty().SetOpacity(ctrl.GetValue())
        Publisher.sendMessage("Update peel", flag=True, actor=self.brain_actor)

    def OnShowPeeling(self, evt, ctrl):
        # self.view_peeling = ctrl.GetValue()
        if ctrl.GetValue():
            actor = self.brain_peel.get_actor(self.peel_depth)
            self.peel_loaded = True
            Publisher.sendMessage("Update peel visualization", data=self.peel_loaded)
        else:
            actor = None
            self.peel_loaded = False
            Publisher.sendMessage("Update peel visualization", data=self.peel_loaded)

        Publisher.sendMessage("Update peel", flag=ctrl.GetValue(), actor=actor)

    def OnEnableTracts(self, evt, ctrl):
        self.view_tracts = ctrl.GetValue()
        Publisher.sendMessage("Update tracts visualization", data=self.view_tracts)
        if not self.view_tracts:
            Publisher.sendMessage("Remove tracts")
            Publisher.sendMessage("Update marker offset state", create=False)

    def OnEnableACT(self, evt, ctrl):
        # self.view_peeling = ctrl.GetValue()
        # if ctrl.GetValue():
        #     act_data = self.brain_peel.get_actor(self.peel_depth)
        # else:
        #     actor = None
        Publisher.sendMessage("Enable ACT", data=ctrl.GetValue())

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status

    def UpdateDialog(self, msg):
        while self.tp.running:
            self.tp.dlg.Pulse(msg)
            if not self.tp.running:
                break
            wx.Yield()

    def OnCreatePeel(self, event=None):
        Publisher.sendMessage("Begin busy cursor")
        inv_proj = prj.Project()
        peels_dlg = dlg.PeelsCreationDlg(wx.GetApp().GetTopWindow())
        ret = peels_dlg.ShowModal()
        method = peels_dlg.method
        if ret == wx.ID_OK:
            t_init = time.time()
            msg = "Creating peeled surface..."
            self.tp = dlg.TractographyProgressWindow(msg)

            slic = sl.Slice()
            ww = slic.window_width
            wl = slic.window_level
            affine = np.eye(4)
            if method == peels_dlg.FROM_FILES:
                try:
                    affine = slic.affine.copy()
                except AttributeError:
                    pass

            self.brain_peel = brain.Brain(self.n_peels, ww, wl, affine, inv_proj)
            if method == peels_dlg.FROM_MASK:
                choices = [i for i in inv_proj.mask_dict.values()]
                mask_index = peels_dlg.cb_masks.GetSelection()
                mask = choices[mask_index]
                option = 1
            else:
                mask = peels_dlg.mask_path
                option = 2
            with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as exec:
                futures = [
                    exec.submit(self.UpdateDialog, msg),
                    exec.submit(self.BrainLoading, option, mask),
                ]
                done, not_done = wait(futures, return_when=FIRST_COMPLETED)
                self.tp.running = False

            t_end = time.time()
            print(f"Elapsed time - {t_end - t_init}")
            self.tp.Close()
            if self.tp.error:
                dlgg = GMD.GenericMessageDialog(
                    None, self.tp.error, "Exception!", wx.OK | wx.ICON_ERROR
                )
                dlgg.ShowModal()

            self.brain_actor = self.brain_peel.get_actor(self.peel_depth)
            self.brain_actor.GetProperty().SetOpacity(self.brain_opacity)
            Publisher.sendMessage("Update peel", flag=True, actor=self.brain_actor)
            Publisher.sendMessage(
                "Get peel centers and normals",
                centers=self.brain_peel.peel_centers,
                normals=self.brain_peel.peel_normals,
            )
            Publisher.sendMessage("Get init locator", locator=self.brain_peel.locator)
            self.checkpeeling.Enable(1)
            self.checkpeeling.SetValue(True)
            self.spin_opacity.Enable(1)
            Publisher.sendMessage("Update status text in GUI", label=_("Brain model loaded"))
            self.peel_loaded = True
            Publisher.sendMessage("Update peel visualization", data=self.peel_loaded)
            del self.tp
            wx.MessageBox(_("Peeled surface created"), _("InVesalius 3"))
        peels_dlg.Destroy()
        Publisher.sendMessage("End busy cursor")

    def BrainLoading(self, option, mask):
        if option == 1:
            self.brain_peel.from_mask(mask)
        else:
            self.brain_peel.from_mask_file(mask)

    def OnLinkFOD(self, event=None):
        Publisher.sendMessage("Begin busy cursor")
        filename = dlg.ShowImportOtherFilesDialog(
            const.ID_NIFTI_IMPORT, msg=_("Import Trekker FOD")
        )
        filename = utils.decode(filename, const.FS_ENCODE)

        if not self.affine_vtk:
            slic = sl.Slice()
            prj_data = prj.Project()
            matrix_shape = tuple(prj_data.matrix_shape)
            spacing = tuple(prj_data.spacing)
            img_shift = spacing[1] * (matrix_shape[1] - 1)
            self.affine = slic.affine.copy()
            self.affine[1, -1] -= img_shift
            self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

        if filename:
            Publisher.sendMessage("Update status text in GUI", label=_("Busy"))
            t_init = time.time()
            try:
                msg = "Setting up FOD ... "
                self.tp = dlg.TractographyProgressWindow(msg)

                self.trekker = None
                file = filename.encode("utf-8")
                with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as exec:
                    futures = [
                        exec.submit(self.UpdateDialog, msg),
                        exec.submit(Trekker.initialize, file),
                    ]
                    done, not_done = wait(futures, return_when=FIRST_COMPLETED)
                    completed_future = done.pop()
                    self.TrekkerCallback(completed_future)

                t_end = time.time()
                print(f"Elapsed time - {t_end - t_init}")
                self.tp.Close()
                if self.tp.error:
                    dlgg = GMD.GenericMessageDialog(
                        None, self.tp.error, "Exception!", wx.OK | wx.ICON_ERROR
                    )
                    dlgg.ShowModal()
                del self.tp
                wx.MessageBox(_("FOD Import successful"), _("InVesalius 3"))
            except Exception:
                Publisher.sendMessage(
                    "Update status text in GUI", label=_("Trekker initialization failed.")
                )
                wx.MessageBox(_("Unable to load FOD."), _("InVesalius 3"))

        Publisher.sendMessage("End busy cursor")

    def TrekkerCallback(self, trekker):
        self.tp.running = False
        print("Import Complete")
        if trekker is not None:
            self.trekker = trekker.result()
            self.trekker, n_threads = dti.set_trekker_parameters(self.trekker, self.trekker_cfg)

            self.checktracts.Enable(True)
            self.checktracts.SetValue(True)
            self.view_tracts = True

            Publisher.sendMessage("Update Trekker object", data=self.trekker)
            Publisher.sendMessage("Update number of threads", data=n_threads)
            Publisher.sendMessage("Update tracts visualization", data=1)
            Publisher.sendMessage("Update status text in GUI", label=_("Trekker initialized"))
            self.tp.running = False

    def OnLoadACT(self, event=None):
        if self.trekker:
            Publisher.sendMessage("Begin busy cursor")
            filename = dlg.ShowImportOtherFilesDialog(
                const.ID_NIFTI_IMPORT, msg=_("Import anatomical labels")
            )
            filename = utils.decode(filename, const.FS_ENCODE)

            if not self.affine_vtk:
                slic = sl.Slice()
                prj_data = prj.Project()
                matrix_shape = tuple(prj_data.matrix_shape)
                spacing = tuple(prj_data.spacing)
                img_shift = spacing[1] * (matrix_shape[1] - 1)
                self.affine = slic.affine.copy()
                self.affine[1, -1] -= img_shift
                self.affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(self.affine)

            try:
                t_init = time.time()
                msg = "Setting up ACT..."
                self.tp = dlg.TractographyProgressWindow(msg)

                Publisher.sendMessage("Update status text in GUI", label=_("Busy"))
                if filename:
                    with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as exec:
                        futures = [
                            exec.submit(self.UpdateDialog, msg),
                            exec.submit(self.ACTLoading, filename),
                        ]
                        done, not_done = wait(futures, return_when=FIRST_COMPLETED)
                        self.tp.running = False

                    t_end = time.time()
                    print(f"Elapsed time - {t_end - t_init}")
                    self.tp.Close()
                    if self.tp.error:
                        dlgg = GMD.GenericMessageDialog(
                            None, self.tp.error, "Exception!", wx.OK | wx.ICON_ERROR
                        )
                        dlgg.ShowModal()
                    del self.tp
                    self.checkACT.Enable(True)
                    self.checkACT.SetValue(True)
                    Publisher.sendMessage("Update ACT data", data=self.act_data_arr)
                    Publisher.sendMessage("Enable ACT", data=True)
                    Publisher.sendMessage(
                        "Update status text in GUI", label=_("Trekker ACT loaded")
                    )
                    wx.MessageBox(_("ACT Import successful"), _("InVesalius 3"))
            except Exception:
                Publisher.sendMessage(
                    "Update status text in GUI", label=_("ACT initialization failed.")
                )
                wx.MessageBox(_("Unable to load ACT."), _("InVesalius 3"))

            Publisher.sendMessage("End busy cursor")
        else:
            wx.MessageBox(_("Load FOD image before the ACT."), _("InVesalius 3"))

    def ACTLoading(self, filename):
        act_data = nb.squeeze_image(nb.load(filename))
        act_data = nb.as_closest_canonical(act_data)
        act_data.update_header()
        self.act_data_arr = act_data.get_fdata()
        # ACT rules should be as follows:
        self.trekker.pathway_stop_at_entry(filename.encode("utf-8"), -1)  # outside
        self.trekker.pathway_discard_if_ends_inside(filename.encode("utf-8"), 1)  # wm
        self.trekker.pathway_discard_if_enters(filename.encode("utf-8"), 0)  # csf

    def OnLoadParameters(self, event=None):
        import json

        filename = dlg.ShowLoadSaveDialog(
            message=_("Load Trekker configuration"), wildcard=_("JSON file (*.json)|*.json")
        )
        try:
            # Check if filename exists, read the JSON file and check if all parameters match
            # with the required list defined in the constants module
            # if a parameter is missing, raise an error
            if filename:
                with open(filename) as json_file:
                    self.trekker_cfg = json.load(json_file)
                assert all(name in self.trekker_cfg for name in const.TREKKER_CONFIG)
                if self.trekker:
                    self.trekker, n_threads = dti.set_trekker_parameters(
                        self.trekker, self.trekker_cfg
                    )
                    Publisher.sendMessage("Update Trekker object", data=self.trekker)
                    Publisher.sendMessage("Update number of threads", data=n_threads)

                Publisher.sendMessage("Update status text in GUI", label=_("Trekker config loaded"))

        except (AssertionError, json.decoder.JSONDecodeError):
            # Inform user that file is not compatible
            self.trekker_cfg = const.TREKKER_CONFIG
            wx.MessageBox(_("File incompatible, using default configuration."), _("InVesalius 3"))
            Publisher.sendMessage("Update status text in GUI", label="")

    def OnUpdateTracts(self, position):
        """
        Minimal working version of tract computation. Updates when cross sends Pubsub message to update.
        Position refers to the coordinates in InVesalius 2D space. To represent the same coordinates in the 3D space,
        flip_x the coordinates and multiply the z coordinate by -1. This is all done in the flix_x function.

        :param arg: event for pubsub
        :param position: list or array with the x, y, and z coordinates in InVesalius space
        """
        # Minimal working version of tract computation
        # It updates when cross updates
        # pass
        if self.view_tracts and not self.nav_status:
            # print("Running during navigation")
            coord_flip = list(position[:3])
            coord_flip[1] = -coord_flip[1]
            dti.compute_and_visualize_tracts(
                self.trekker, coord_flip, self.affine, self.affine_vtk, self.n_tracts
            )

    def OnCloseProject(self):
        self.trekker = None
        self.trekker_cfg = const.TREKKER_CONFIG

        self.checktracts.SetValue(False)
        self.checktracts.Enable(False)
        self.checkpeeling.SetValue(False)
        self.checkpeeling.Enable(False)
        self.checkACT.SetValue(False)
        self.checkACT.Enable(False)

        self.spin_opacity.SetValue(const.BRAIN_OPACITY)
        self.spin_opacity.Enable(False)
        Publisher.sendMessage("Update peel", flag=False, actor=self.brain_actor)

        self.peel_depth = const.PEEL_DEPTH
        self.n_tracts = const.N_TRACTS

        Publisher.sendMessage("Remove tracts")
