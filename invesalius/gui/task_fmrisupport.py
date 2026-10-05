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

import os

import matplotlib.pyplot as plt
import numpy as np
import wx
import wx.lib.scrolledpanel as scrolled

import invesalius.constants as const
import invesalius.data.fmri as fmri
import invesalius.gui.widgets.gradient as grad
import invesalius.session as ses
import invesalius.utils as utils
from invesalius.data.slice_ import Slice
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


class InnerTaskPanel(scrolled.ScrolledPanel):
    def __init__(self, parent):
        super().__init__(parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)

        self.SetBackgroundColour(default_colour)
        self.session = ses.Session()
        self.slc = Slice()
        self.manager = fmri.FMRIOverlayManager()

        self._init_gui()
        self.__bind_events()
        self.SetupScrolling(scroll_x=False, scroll_y=True)

    def _init_gui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ----------------------------------------------------
        # 1. Modality Selection
        # ----------------------------------------------------
        lbl_modality = wx.StaticText(self, -1, _("Functional Modality:"))
        lbl_modality.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        self.combo_modality = wx.ComboBox(
            self,
            -1,
            choices=fmri.MODALITY_CHOICES,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        self.combo_modality.SetSelection(0)
        self.combo_modality.Bind(wx.EVT_COMBOBOX, self.OnSelectModality)

        # ----------------------------------------------------
        # 2. File Loading & Demo Presets
        # ----------------------------------------------------
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_load = wx.Button(self, -1, _("Load NIfTI..."))
        self.btn_load.SetToolTip(_("Load 3D or 4D fMRI NIfTI file (.nii / .nii.gz)"))
        self.btn_load.Bind(wx.EVT_BUTTON, self.OnLoadFmri)

        self.btn_demo = wx.Button(self, -1, _("Load Demo"))
        self.btn_demo.SetToolTip(_("Load built-in canonical demo dataset for current modality"))
        self.btn_demo.Bind(wx.EVT_BUTTON, self.OnLoadDemo)

        btn_sizer.Add(self.btn_load, 1, wx.RIGHT, 4)
        btn_sizer.Add(self.btn_demo, 1, wx.LEFT, 4)

        self.lbl_file_info = wx.StaticText(self, -1, _("No dataset loaded"))
        self.lbl_file_info.SetForegroundColour(wx.Colour(100, 100, 100))

        # ----------------------------------------------------
        # 3. Modality-Specific Subpanels
        # ----------------------------------------------------
        # A. Parcellations (Yeo7 / Yeo17) Panel
        self.panel_parcellation = wx.Panel(self)
        parc_sizer = wx.BoxSizer(wx.VERTICAL)

        lbl_parc = wx.StaticText(self.panel_parcellation, -1, _("Cortical Networks (Yeo):"))
        self.check_networks = wx.CheckListBox(
            self.panel_parcellation,
            -1,
            size=(-1, 140),
            choices=[f"{k}. {v['name']}" for k, v in fmri.YEO_7_NETWORKS.items()],
        )
        for i in range(self.check_networks.GetCount()):
            self.check_networks.Check(i, True)
        self.check_networks.Bind(wx.EVT_CHECKLISTBOX, self.OnToggleNetwork)

        parc_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_all = wx.Button(self.panel_parcellation, -1, _("All"), size=(-1, 22))
        btn_all.Bind(wx.EVT_BUTTON, self.OnSelectAllNetworks)
        btn_none = wx.Button(self.panel_parcellation, -1, _("None"), size=(-1, 22))
        btn_none.Bind(wx.EVT_BUTTON, self.OnClearAllNetworks)
        parc_btn_sizer.Add(btn_all, 1, wx.RIGHT, 2)
        parc_btn_sizer.Add(btn_none, 1, wx.LEFT, 2)

        parc_sizer.Add(lbl_parc, 0, wx.BOTTOM, 2)
        parc_sizer.Add(self.check_networks, 0, wx.EXPAND | wx.BOTTOM, 4)
        parc_sizer.Add(parc_btn_sizer, 0, wx.EXPAND)
        self.panel_parcellation.SetSizer(parc_sizer)

        # B. Beta Values & BOLD Timeframe Panel
        self.panel_beta_bold = wx.Panel(self)
        beta_sizer = wx.BoxSizer(wx.VERTICAL)

        self.lbl_timeframe = wx.StaticText(self.panel_beta_bold, -1, _("Timeframe (TR): 0 / 0"))
        self.slider_timeframe = wx.Slider(self.panel_beta_bold, -1, 0, 0, 100, style=wx.SL_HORIZONTAL)
        self.slider_timeframe.Bind(wx.EVT_SLIDER, self.OnTimeframeChange)

        tf_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_prev = wx.Button(self.panel_beta_bold, -1, _("◀ Prev"), size=(-1, 22))
        btn_prev.Bind(wx.EVT_BUTTON, self.OnPrevTimeframe)
        btn_next = wx.Button(self.panel_beta_bold, -1, _("Next ▶"), size=(-1, 22))
        btn_next.Bind(wx.EVT_BUTTON, self.OnNextTimeframe)
        tf_btn_sizer.Add(btn_prev, 1, wx.RIGHT, 2)
        tf_btn_sizer.Add(btn_next, 1, wx.LEFT, 2)

        self.lbl_threshold = wx.StaticText(self.panel_beta_bold, -1, _("Activation Threshold: 0%"))
        self.slider_threshold = wx.Slider(self.panel_beta_bold, -1, 0, 0, 95, style=wx.SL_HORIZONTAL)
        self.slider_threshold.Bind(wx.EVT_SLIDER, self.OnThresholdChange)

        self.chk_twosided = wx.CheckBox(self.panel_beta_bold, -1, _("Two-sided (pos & neg)"))
        self.chk_twosided.Bind(wx.EVT_CHECKBOX, self.OnToggleTwoSided)

        beta_sizer.Add(self.lbl_timeframe, 0, wx.BOTTOM, 2)
        beta_sizer.Add(self.slider_timeframe, 0, wx.EXPAND | wx.BOTTOM, 2)
        beta_sizer.Add(tf_btn_sizer, 0, wx.EXPAND | wx.BOTTOM, 4)
        beta_sizer.Add(self.lbl_threshold, 0, wx.BOTTOM, 2)
        beta_sizer.Add(self.slider_threshold, 0, wx.EXPAND | wx.BOTTOM, 2)
        beta_sizer.Add(self.chk_twosided, 0, wx.BOTTOM, 2)
        self.panel_beta_bold.SetSizer(beta_sizer)

        # C. Functional Gradient Panel
        self.panel_gradient = wx.Panel(self)
        grad_sizer = wx.BoxSizer(wx.VERTICAL)

        self.lbl_grad_thresh = wx.StaticText(self.panel_gradient, -1, _("Gradient Range Clipping: 0%"))
        self.slider_grad_thresh = wx.Slider(self.panel_gradient, -1, 0, 0, 90, style=wx.SL_HORIZONTAL)
        self.slider_grad_thresh.Bind(wx.EVT_SLIDER, self.OnGradThreshChange)

        grad_sizer.Add(self.lbl_grad_thresh, 0, wx.BOTTOM, 2)
        grad_sizer.Add(self.slider_grad_thresh, 0, wx.EXPAND)
        self.panel_gradient.SetSizer(grad_sizer)

        # D. Seed-based Functional Connectivity Panel
        self.panel_seed_fc = wx.Panel(self)
        seed_sizer = wx.BoxSizer(wx.VERTICAL)

        self.btn_seed = wx.Button(self.panel_seed_fc, -1, _("Set Seed from Crosshair"))
        self.btn_seed.SetToolTip(_("Pick current 2D slice crosshair coordinates as seed voxel"))
        self.btn_seed.Bind(wx.EVT_BUTTON, self.OnSetSeedFromCrosshair)

        self.lbl_seed = wx.StaticText(self.panel_seed_fc, -1, _("Seed (Z, Y, X): (0, 0, 0)"))
        self.lbl_fc_thresh = wx.StaticText(self.panel_seed_fc, -1, _("Correlation Threshold: r ≥ 0.35"))
        self.slider_fc_thresh = wx.Slider(self.panel_seed_fc, -1, 35, 10, 95, style=wx.SL_HORIZONTAL)
        self.slider_fc_thresh.Bind(wx.EVT_SLIDER, self.OnFCThreshChange)

        seed_sizer.Add(self.btn_seed, 0, wx.EXPAND | wx.BOTTOM, 4)
        seed_sizer.Add(self.lbl_seed, 0, wx.BOTTOM, 4)
        seed_sizer.Add(self.lbl_fc_thresh, 0, wx.BOTTOM, 2)
        seed_sizer.Add(self.slider_fc_thresh, 0, wx.EXPAND)
        self.panel_seed_fc.SetSizer(seed_sizer)

        # ----------------------------------------------------
        # 4. Colormap & Appearance Controls
        # ----------------------------------------------------
        lbl_colormap = wx.StaticText(self, -1, _("Colormap:"))
        self.combo_cmap = wx.ComboBox(
            self,
            -1,
            choices=fmri.COLORMAP_PRESETS[fmri.MODALITY_PARCELLATION],
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        self.combo_cmap.SetSelection(0)
        self.combo_cmap.Bind(wx.EVT_COMBOBOX, self.OnSelectColormap)

        # Gradient Preview Bar
        cmap_colors = self.GenerateColormapColors("autumn")
        self.gradient = grad.GradientDisp(self, -1, -5000, 5000, -5000, 5000, cmap_colors)

        # Opacity slider
        self.lbl_opacity = wx.StaticText(self, -1, _("Overlay Opacity: 85%"))
        self.slider_opacity = wx.Slider(self, -1, 85, 10, 100, style=wx.SL_HORIZONTAL)
        self.slider_opacity.Bind(wx.EVT_SLIDER, self.OnOpacityChange)

        # Visibility Checkbox
        self.chk_show = wx.CheckBox(self, -1, _("Show Overlay"))
        self.chk_show.SetValue(True)
        self.chk_show.Bind(wx.EVT_CHECKBOX, self.OnToggleVisibility)

        # ----------------------------------------------------
        # 5. 3D Surface Mapping & Action Buttons
        # ----------------------------------------------------
        self.btn_map_3d = wx.Button(self, -1, _("Map to 3D Brain Surface"))
        self.btn_map_3d.SetToolTip(_("Project functional overlay onto active 3D brain surface mesh"))
        self.btn_map_3d.Bind(wx.EVT_BUTTON, self.OnMapTo3DSurface)

        self.btn_clear = wx.Button(self, -1, _("Clear Overlay"))
        self.btn_clear.SetToolTip(_("Remove functional overlay from slices and 3D surface"))
        self.btn_clear.Bind(wx.EVT_BUTTON, self.OnClearOverlay)

        # ----------------------------------------------------
        # Assemble Main Sizer
        # ----------------------------------------------------
        main_sizer.AddSpacer(6)
        main_sizer.Add(lbl_modality, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(2)
        main_sizer.Add(self.combo_modality, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(8)

        main_sizer.Add(btn_sizer, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(3)
        main_sizer.Add(self.lbl_file_info, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(8)

        # Modality panels
        main_sizer.Add(self.panel_parcellation, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add(self.panel_beta_bold, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add(self.panel_gradient, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add(self.panel_seed_fc, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(8)

        # Colormap & Gradient
        main_sizer.Add(lbl_colormap, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(2)
        main_sizer.Add(self.combo_cmap, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(6)
        main_sizer.Add(self.gradient, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(6)

        main_sizer.Add(self.lbl_opacity, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add(self.slider_opacity, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(4)
        main_sizer.Add(self.chk_show, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(8)

        main_sizer.Add(self.btn_map_3d, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(4)
        main_sizer.Add(self.btn_clear, 0, wx.GROW | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(8)

        self.SetSizer(main_sizer)
        self._update_panel_visibility()
        self.Layout()

    def __bind_events(self):
        pass

    def _get_target_shape(self) -> tuple | None:
        if hasattr(self.slc, "matrix") and self.slc.matrix is not None:
            return self.slc.matrix.shape
        return None

    def _update_panel_visibility(self):
        mod = self.combo_modality.GetStringSelection()
        self.panel_parcellation.Show(mod == fmri.MODALITY_PARCELLATION)
        self.panel_beta_bold.Show(mod == fmri.MODALITY_BETA_BOLD)
        self.panel_gradient.Show(mod == fmri.MODALITY_GRADIENT)
        self.panel_seed_fc.Show(mod == fmri.MODALITY_SEED_FC)

        # Update colormaps list
        cmaps = fmri.COLORMAP_PRESETS.get(mod, ["autumn", "hot", "plasma", "viridis"])
        curr_cmap = self.combo_cmap.GetStringSelection()
        self.combo_cmap.SetItems(cmaps)
        if curr_cmap in cmaps:
            self.combo_cmap.SetStringSelection(curr_cmap)
        else:
            self.combo_cmap.SetSelection(0)
            self.manager.set_colormap(cmaps[0])

        self._update_gradient_display()
        self.Layout()
        self.SetupScrolling(scroll_x=False, scroll_y=True)

    def _update_gradient_display(self):
        cmap_name = self.combo_cmap.GetStringSelection()
        if cmap_name == "Yeo Standard":
            colors = [(c[0], c[1], c[2], 255) for k, v in fmri.YEO_7_NETWORKS.items() for c in [v["color"]]]
        else:
            colors = self.GenerateColormapColors(cmap_name)
        self.gradient.SetGradientColours(colors)
        self.gradient.Refresh()

    def GenerateColormapColors(self, colormap_name, number_colors=10):
        try:
            cmap = plt.get_cmap(colormap_name)
            return [
                (
                    int(255 * cmap(i)[0]),
                    int(255 * cmap(i)[1]),
                    int(255 * cmap(i)[2]),
                    int(255 * cmap(i)[3]),
                )
                for i in np.linspace(0, 1, number_colors)
            ]
        except Exception:
            return [(255, 0, 0, 255), (255, 255, 0, 255)]

    def ApplyOverlay(self):
        target_shape = self._get_target_shape()
        self.manager.update_overlay(target_shape)

        if self.chk_show.GetValue() and self.manager.cluster_volume is not None:
            self.slc.aux_matrices["color_overlay"] = self.manager.cluster_volume
            self.slc.aux_matrices_colours["color_overlay"] = self.manager.color_dict
            self.slc.to_show_aux = "color_overlay"
        else:
            self.slc.to_show_aux = ""

        Publisher.sendMessage("Reload actual slice")

    # ----------------------------------------------------
    # Event Handlers
    # ----------------------------------------------------
    def OnSelectModality(self, event):
        mod = self.combo_modality.GetStringSelection()
        target_shape = self._get_target_shape()
        self.manager.set_modality(mod, target_shape=target_shape)
        self._update_panel_visibility()
        self.ApplyOverlay()

    def OnSelectColormap(self, event):
        cmap_name = self.combo_cmap.GetStringSelection()
        self.manager.set_colormap(cmap_name)
        self._update_gradient_display()
        self.ApplyOverlay()

    def OnLoadFmri(self, event):
        import invesalius.gui.dialogs as dlg
        filename = dlg.ShowImportOtherFilesDialog(id_type=const.ID_NIFTI_IMPORT)
        if not filename:
            return
        filename = utils.decode(filename, const.FS_ENCODE)
        if not os.path.exists(filename):
            return

        target_shape = self._get_target_shape()
        try:
            self.manager.load_file(filename, target_shape=target_shape)
            basename = os.path.basename(filename)
            if self.manager.is_4d:
                info = f"{basename} (4D: {self.manager.num_timeframes} frames)"
                self.slider_timeframe.SetMax(self.manager.num_timeframes - 1)
                self.slider_timeframe.SetValue(0)
                self.lbl_timeframe.SetLabel(f"Timeframe (TR): 0 / {self.manager.num_timeframes - 1}")
            else:
                info = f"{basename} (3D volume)"

            self.lbl_file_info.SetLabel(info)
            self.combo_modality.SetStringSelection(self.manager.modality)
            self._update_panel_visibility()
            self.ApplyOverlay()
        except Exception as e:
            wx.MessageBox(
                _("Error loading fMRI dataset: {}").format(str(e)),
                _("InVesalius 3"),
                wx.OK | wx.ICON_ERROR,
            )

    def OnLoadDemo(self, event):
        target_shape = self._get_target_shape()
        if target_shape is None:
            # Fallback shape if no project scan is loaded
            target_shape = (60, 80, 80)

        mod = self.combo_modality.GetStringSelection()
        self.manager.generate_demo_data(mod, target_shape=target_shape)

        if self.manager.is_4d:
            self.lbl_file_info.SetLabel(f"Built-in 4D BOLD Demo ({self.manager.num_timeframes} TRs)")
            self.slider_timeframe.SetMax(self.manager.num_timeframes - 1)
            self.slider_timeframe.SetValue(0)
            self.lbl_timeframe.SetLabel(f"Timeframe (TR): 0 / {self.manager.num_timeframes - 1}")
        elif mod == fmri.MODALITY_PARCELLATION:
            self.lbl_file_info.SetLabel(_("Yeo 7 Networks Cortical Atlas"))
        elif mod == fmri.MODALITY_GRADIENT:
            self.lbl_file_info.SetLabel(_("Principal Macroscale Functional Gradient"))

        self._update_panel_visibility()
        self.ApplyOverlay()

    def OnToggleNetwork(self, event):
        idx = event.GetInt()
        label_id = idx + 1
        is_checked = self.check_networks.IsChecked(idx)
        self.manager.toggle_network(label_id, is_checked)
        self.ApplyOverlay()

    def OnSelectAllNetworks(self, event):
        for i in range(self.check_networks.GetCount()):
            self.check_networks.Check(i, True)
            self.manager.toggle_network(i + 1, True)
        self.ApplyOverlay()

    def OnClearAllNetworks(self, event):
        for i in range(self.check_networks.GetCount()):
            self.check_networks.Check(i, False)
            self.manager.toggle_network(i + 1, False)
        self.ApplyOverlay()

    def OnTimeframeChange(self, event):
        t = self.slider_timeframe.GetValue()
        self.lbl_timeframe.SetLabel(f"Timeframe (TR): {t} / {self.manager.num_timeframes - 1}")
        self.manager.set_timeframe(t, target_shape=self._get_target_shape())
        self.ApplyOverlay()

    def OnPrevTimeframe(self, event):
        curr = self.slider_timeframe.GetValue()
        if curr > 0:
            self.slider_timeframe.SetValue(curr - 1)
            self.OnTimeframeChange(None)

    def OnNextTimeframe(self, event):
        curr = self.slider_timeframe.GetValue()
        if curr < self.manager.num_timeframes - 1:
            self.slider_timeframe.SetValue(curr + 1)
            self.OnTimeframeChange(None)

    def OnThresholdChange(self, event):
        val = self.slider_threshold.GetValue()
        self.lbl_threshold.SetLabel(f"Activation Threshold: {val}%")
        self.manager.set_threshold(min_thresh=val / 100.0)
        self.ApplyOverlay()

    def OnToggleTwoSided(self, event):
        self.manager.two_sided = self.chk_twosided.GetValue()
        self.ApplyOverlay()

    def OnGradThreshChange(self, event):
        val = self.slider_grad_thresh.GetValue()
        self.lbl_grad_thresh.SetLabel(f"Gradient Range Clipping: {val}%")
        self.manager.set_threshold(min_thresh=val / 100.0)
        self.ApplyOverlay()

    def OnSetSeedFromCrosshair(self, event):
        if hasattr(self.slc, "buffer_slices") and self.slc.buffer_slices:
            z = self.slc.buffer_slices["AXIAL"].index
            y = self.slc.buffer_slices["CORONAL"].index
            x = self.slc.buffer_slices["SAGITAL"].index
        else:
            z, y, x = 0, 0, 0

        self.manager.set_seed_coord(z, y, x, target_shape=self._get_target_shape())
        self.lbl_seed.SetLabel(f"Seed (Z, Y, X): ({z}, {y}, {x})")
        self.ApplyOverlay()

    def OnFCThreshChange(self, event):
        r_thresh = self.slider_fc_thresh.GetValue() / 100.0
        self.lbl_fc_thresh.SetLabel(f"Correlation Threshold: r ≥ {r_thresh:.2f}")
        self.manager.set_threshold(min_thresh=r_thresh)
        self.ApplyOverlay()

    def OnOpacityChange(self, event):
        val = self.slider_opacity.GetValue()
        self.lbl_opacity.SetLabel(f"Overlay Opacity: {val}%")
        self.manager.opacity = val / 100.0
        # Re-scale alpha in color dictionary
        if self.manager.color_dict:
            new_dict = {}
            for k, (r, g, b, a) in self.manager.color_dict.items():
                if a > 0.05:
                    new_dict[k] = (r, g, b, self.manager.opacity)
                else:
                    new_dict[k] = (0.0, 0.0, 0.0, 0.0)
            self.slc.aux_matrices_colours["color_overlay"] = new_dict
            Publisher.sendMessage("Reload actual slice")

    def OnToggleVisibility(self, event):
        self.ApplyOverlay()

    def OnMapTo3DSurface(self, event):
        import invesalius.project as prj
        proj = prj.Project()
        if not hasattr(proj, "surface_dict") or not proj.surface_dict:
            wx.MessageBox(
                _("No 3D brain surface is currently created or loaded.\nPlease create or import a 3D surface first."),
                _("InVesalius 3"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        if self.manager.cluster_volume is None:
            wx.MessageBox(
                _("No functional overlay data to map onto surface."),
                _("InVesalius 3"),
                wx.OK | wx.ICON_WARNING,
            )
            return

        # Take first or active surface
        surface_index = list(proj.surface_dict.keys())[0]
        surface = proj.surface_dict[surface_index]

        spacing = getattr(self.slc, "spacing", (1.0, 1.0, 1.0))
        vtk_colors = fmri.map_overlay_to_surface(
            surface.polydata,
            self.manager.cluster_volume,
            self.manager.color_dict,
            spacing=spacing,
        )

        Publisher.sendMessage("Apply surface point colors", surface_index=surface_index, colors=vtk_colors)

    def OnClearOverlay(self, event):
        self.slc.to_show_aux = ""
        self.slc.aux_matrices.pop("color_overlay", None)
        self.slc.aux_matrices_colours.pop("color_overlay", None)

        # Clear 3D surface scalar colors
        import invesalius.project as prj
        proj = prj.Project()
        if hasattr(proj, "surface_dict"):
            for s_idx in proj.surface_dict:
                Publisher.sendMessage("Apply surface point colors", surface_index=s_idx, colors=None)

        Publisher.sendMessage("Reload actual slice")
        Publisher.sendMessage("Render volume viewer")
