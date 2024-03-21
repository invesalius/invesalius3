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

import nibabel as nb
import numpy as np
import matplotlib.pyplot as plt
import wx
import wx.lib.masked.numctrl

import invesalius.constants as const
from invesalius.data.slice_ import Slice
import invesalius.gui.dialogs as dlg
import invesalius.gui.widgets.gradient as grad
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
import invesalius.session as ses
import invesalius.utils as utils


class TaskPanel(wx.Panel):
    def __init__(self, parent):

        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)

        self.__bind_events()

        self.SetBackgroundColour(default_colour)
        self.session = ses.Session()
        self.slc = Slice()
        self.colormaps = ["autumn", "hot", "plasma", "cividis",  # sequential
                          "bwr", "RdBu",  # diverging
                          "Set3", "tab10",  # categorical
                          "twilight", "hsv"]   # cyclic
        self.current_colormap = "autumn"
        self.number_colors = 10
        self.cluster_volume = None
        self.zero_value = 0

        line0 = wx.StaticText(self, -1,
                              _("Select Modalities / File"))
        
        # Button for import config coil file
        tooltip = wx.ToolTip(_("Load Nifti image"))
        btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadFmri)
        self.btn_load = btn_load

        # Create a horizontal sizer to represent button save
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(btn_load, 1, wx.LEFT | wx.TOP | wx.RIGHT, 2)

        ### LINE 2
        text_thresh = wx.StaticText(self, -1,
                                    _("Select Colormap"))

        ### LINE 3
        combo_thresh = wx.ComboBox(self, -1, "", #size=(15,-1),
                                   choices=self.colormaps,
                                   style=wx.CB_DROPDOWN|wx.CB_READONLY)
        combo_thresh.Bind(wx.EVT_COMBOBOX, self.OnSelectColormap)
        # by default use the initial value set in self.current_colormap
        combo_thresh.SetSelection(self.colormaps.index(self.current_colormap))

        self.combo_thresh = combo_thresh

        ## LINE 4
        cmap = plt.get_cmap(self.current_colormap)
        colors_gradient = self.GenerateColormapColors(cmap)

        self.gradient = grad.GradientDisp(self, -1, -5000, 5000, -5000, 5000,
                                          colors_gradient)

        # Add all lines into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(7)
        sizer.Add(line0, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.AddSpacer(5)
        # sizer.Add(line1, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.Add(line1, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 3)
 
        sizer.AddSpacer(5)
        sizer.Add(text_thresh, 0, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.AddSpacer(2)
        sizer.Add(combo_thresh, 0, wx.EXPAND|wx.GROW|wx.LEFT|wx.RIGHT, 5)

        sizer.AddSpacer(5)
        sizer.Add(self.gradient, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.AddSpacer(7)

        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)
        self.UpdateGradient(self.gradient, colors_gradient)

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
        colors_gradient = [(int(255*cmap(i)[0]),
                            int(255*cmap(i)[1]),
                            int(255*cmap(i)[2]),
                            int(255*cmap(i)[3])) for i in np.linspace(0, 1, number_colors)]

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
                    np.max(cluster_volume_original) - np.min(cluster_volume_original))
        # Convert data to 8-bit integer
        self.cluster_volume = (cluster_volume_normalized * 255).astype(np.uint8)

        self.zero_value = int((0. - np.min(cluster_volume_original)) / (np.max(cluster_volume_original) - np.min(cluster_volume_original)) * 255)

        if self.slc.matrix.shape != self.cluster_volume.shape:
            wx.MessageBox(("The overlay volume does not match the underlying structural volume"), ("InVesalius 3"))

        else:
            self.slc.aux_matrices['color_overlay'] = self.cluster_volume
            # 3. Show colors
            self.slc.to_show_aux = 'color_overlay'
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

        self.slc.aux_matrices_colours['color_overlay'] = color_dict
        # add transparent color for nans and non GM voxels
        if zero_value in self.slc.aux_matrices_colours['color_overlay']:
            self.slc.aux_matrices_colours['color_overlay'][zero_value] = (0.0, 0.0, 0.0, 0.0)
        else:
            print("Zero value not found in color_overlay. No data is set as transparent.")

        Publisher.sendMessage('Reload actual slice')
