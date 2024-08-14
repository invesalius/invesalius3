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

import sys

import matplotlib.pyplot as plt
import nibabel as nb
import numpy as np
import wx
import wx.lib.colourselect as csel
import wx.lib.masked.numctrl
import wx.lib.scrolledpanel as scrolled

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
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
        self.Fit()
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        # White background looks better
        background_colour = wx.Colour(255, 255, 255)
        self.SetBackgroundColour(background_colour)

        self.__bind_events()

        self.session = ses.Session()
        self.slc = Slice()
        self.colormaps = [str(cmap) for cmap in const.MEP_COLORMAP_DEFINITIONS]

        self.current_colormap = self.colormaps[0]
        self.number_colors = 10
        self.cluster_volume = None
        self.zero_value = 0

        line0 = wx.StaticText(self, -1, _("Motor Mapping Configuration"))

        # Button for import config coil file
        # tooltip = _("Select the brain surface to be mapped on.")
        # btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        # btn_load.SetToolTip(tooltip)
        # btn_load.Enable(1)
        # btn_load.Bind(wx.EVT_BUTTON, self.OnLoadFmri)
        # self.btn_load = btn_load

        # Create a horizontal sizer to represent button save
        line1 = wx.BoxSizer(wx.VERTICAL)

        # add surface panel window
        self.surface_panel = SurfaceProperties(self)
        line1.Add(self.surface_panel, 5, wx.LEFT | wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT, 2)
        line1.AddSpacer(5)
        # line1.Add(btn_load, 5, wx.LEFT | wx.TOP | wx.RIGHT, 1)

        line3 = wx.StaticText(self, -1, _("Markers Import/Export:"))

        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(7)
        sizer.Add(line0, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)
        # sizer.Add(line1, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.Add(line1, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 3)
        sizer.AddSpacer(5)
        sizer.Add(line3, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(5)

        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

    def __bind_events(self):
        pass

    def OnSelectColormap(self, event=None):
        self.current_colormap = self.colormaps[self.combo_thresh.GetSelection()]
        colors = self.GenerateColormapColors(self.current_colormap, self.number_colors)

        self.UpdateGradient(self.gradient, colors)

        if isinstance(self.cluster_volume, np.ndarray):
            self.apply_colormap(self.current_colormap, self.cluster_volume, self.zero_value)

    def GenerateColormapColors(self, colormap_name, number_colors=10):
        cmap = plt.get_cmap(colormap_name)
        colors_gradient = [
            (
                int(255 * cmap(i)[0]),
                int(255 * cmap(i)[1]),
                int(255 * cmap(i)[2]),
                int(255 * cmap(i)[3]),
            )
            for i in np.linspace(0, 1, number_colors)
        ]

        return colors_gradient

    def UpdateGradient(self, gradient, colors):
        gradient.SetGradientColours(colors)
        gradient.Refresh()
        gradient.Update()

        self.Refresh()
        self.Update()
        self.Show(True)

    def OnLoadFmri(self, event=None):
        filename = dlg.ShowImportOtherFilesDialog(id_type=const.ID_NIFTI_IMPORT)
        filename = utils.decode(filename, const.FS_ENCODE)

        fmri_data = nb.squeeze_image(nb.load(filename))
        fmri_data = nb.as_closest_canonical(fmri_data)
        fmri_data.update_header()

        cluster_volume_original = fmri_data.get_fdata().T[:, ::-1].copy()
        # Normalize the data to 0-1 range
        cluster_volume_normalized = (cluster_volume_original - np.min(cluster_volume_original)) / (
            np.max(cluster_volume_original) - np.min(cluster_volume_original)
        )
        # Convert data to 8-bit integer
        self.cluster_volume = (cluster_volume_normalized * 255).astype(np.uint8)

        self.zero_value = int(
            (0.0 - np.min(cluster_volume_original))
            / (np.max(cluster_volume_original) - np.min(cluster_volume_original))
            * 255
        )

        if self.slc.matrix.shape != self.cluster_volume.shape:
            wx.MessageBox(
                ("The overlay volume does not match the underlying structural volume"),
                ("InVesalius 3"),
            )

        else:
            self.slc.aux_matrices["color_overlay"] = self.cluster_volume
            # 3. Show colors
            self.slc.to_show_aux = "color_overlay"
            self.apply_colormap(self.current_colormap, self.cluster_volume, self.zero_value)

    def apply_colormap(self, colormap, cluster_volume, zero_value):
        # 2. Attribute different hue accordingly
        cmap = plt.get_cmap(colormap)

        # new way
        # Flatten the data to 1D
        cluster_volume_unique = np.unique(cluster_volume)
        # Map the scaled data to colors
        colors = cmap(cluster_volume_unique / 255)
        # Create a dictionary where keys are scaled data and values are colors
        color_dict = {val: color for val, color in zip(cluster_volume_unique, map(tuple, colors))}

        self.slc.aux_matrices_colours["color_overlay"] = color_dict
        # add transparent color for nans and non GM voxels
        if zero_value in self.slc.aux_matrices_colours["color_overlay"]:
            self.slc.aux_matrices_colours["color_overlay"][zero_value] = (0.0, 0.0, 0.0, 0.0)
        else:
            print("Zero value not found in color_overlay. No data is set as transparent.")

        Publisher.sendMessage("Reload actual slice")


class SurfaceProperties(scrolled.ScrolledPanel):
    def __init__(self, parent):
        scrolled.ScrolledPanel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.surface_list = []

        # LINE 1

        # Combo related to mask name
        combo_surface_name = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        # combo_surface_name.SetSelection(0)
        if sys.platform != "win32":
            combo_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        combo_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)
        self.combo_surface_name = combo_surface_name

        # Mask colour
        button_colour = csel.ColourSelect(self, -1, colour=(0, 0, 255), size=(22, -1))
        button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_colour = button_colour

        # Sizer which represents the first line
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(combo_surface_name, 1, wx.LEFT | wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT, 7)
        line1.Add(button_colour, 0, wx.TOP | wx.RIGHT, 7)

        # LINE 2
        text_transparency = wx.StaticText(self, -1, _("Brain Surface:"))

        # MIX LINE 2 AND 3
        # flag_link = wx.EXPAND | wx.GROW | wx.RIGHT
        fixed_sizer = wx.BoxSizer(wx.HORIZONTAL)

        fixed_sizer.Add(text_transparency, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        # fixed_sizer.AddSpacer(7)
        fixed_sizer.Add(line1, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT, 5)

        # LINE 4
        # # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fixed_sizer, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)
        # sizer.Add(line1, 1, wx.GROW | wx.EXPAND | wx.TOP, 10)

        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.SetupScrolling()

        self.Bind(wx.EVT_SIZE, self.OnResize)

        self.__bind_events()

    def OnResize(self, evt):
        self.SetupScrolling()

    def __bind_events(self):
        Publisher.subscribe(self.InsertNewSurface, "Update surface info in GUI")
        Publisher.subscribe(self.ChangeSurfaceName, "Change surface name")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnRemoveSurfaces, "Remove surfaces")

    def OnRemoveSurfaces(self, surface_indexes):
        s = self.combo_surface_name.GetSelection()
        ns = 0

        old_dict = self.surface_list
        new_dict = []
        i = 0
        for n, (name, index) in enumerate(old_dict):
            if n not in surface_indexes:
                new_dict.append([name, i])
                if s == n:
                    ns = i
                i += 1
        self.surface_list = new_dict

        self.combo_surface_name.SetItems([n[0] for n in self.surface_list])

        if self.surface_list:
            self.combo_surface_name.SetSelection(ns)

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        n = self.combo_surface_name.GetCount()
        for i in range(n - 1, -1, -1):
            self.combo_surface_name.Delete(i)
        self.surface_list = []

    def ChangeSurfaceName(self, index, name):
        self.surface_list[index][0] = name
        self.combo_surface_name.SetString(index, name)

    def InsertNewSurface(self, surface):
        index = surface.index
        name = surface.name
        colour = [int(value * 255) for value in surface.colour]
        i = 0
        try:
            i = self.surface_list.index([name, index])
            overwrite = True
        except ValueError:
            overwrite = False

        if overwrite:
            self.surface_list[i] = [name, index]
        else:
            self.surface_list.append([name, index])
            i = len(self.surface_list) - 1

        self.combo_surface_name.SetItems([n[0] for n in self.surface_list])
        self.combo_surface_name.SetSelection(i)
        # transparency = 100*surface.transparency
        # print("Button color: ", colour)
        self.button_colour.SetColour(colour)
        # self.slider_transparency.SetValue(int(transparency))
        #  Publisher.sendMessage('Update surface data', (index))

    def OnComboName(self, evt):
        surface_name = evt.GetString()
        surface_index = evt.GetSelection()
        self.button_colour.SetColour(
            [int(value * 255) for value in self.surface_list[surface_index][2]]
        )
        Publisher.sendMessage(
            "Change surface selected", surface_index=self.surface_list[surface_index][1]
        )

    def OnSelectColour(self, evt):
        colour = [value / 255.0 for value in evt.GetValue()]
        Publisher.sendMessage(
            "Set surface colour",
            surface_index=self.combo_surface_name.GetSelection(),
            colour=colour,
        )
