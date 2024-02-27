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
        self.colormaps = ["twilight","hsv","Set1","Set2","winter","hot","autumn"]
        self.current_colormap = "twilight"
        self.cluster_volume = None

        line0 = wx.StaticText(self, -1,
                                    _("Select Modalities / File"))
        
        # Button for import config coil file
        tooltip = wx.ToolTip(_("Load Modalities"))
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
        combo_thresh.SetSelection(0) # By Default use Twilight

        self.combo_thresh = combo_thresh

        ## LINE 4
        cmap = plt.get_cmap(self.current_colormap)
        colororder = [(int(255*cmap(i)[0]),
                       int(255*cmap(i)[1]),
                       int(255*cmap(i)[2]),
                       int(100*cmap(i)[3])) for i in np.linspace(0, 1, 100)]
        
        gradient = grad.GradientDisp(self, -1, -5000, 5000, -5000, 5000,
                                     colororder, colortype=self.current_colormap in ['Set1', 'Set2'])
        self.gradient = gradient

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
        sizer.Add(gradient, 1, wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
        sizer.AddSpacer(7)

        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)

    def __bind_events(self):
        pass

    def OnSelectColormap(self, event=None):
        self.current_colormap = self.colormaps[self.combo_thresh.GetSelection()]
        cmap = plt.get_cmap(self.current_colormap)
        colororder = [(int(255*cmap(i)[0]),
                       int(255*cmap(i)[1]),
                       int(255*cmap(i)[2]),
                       int(100*cmap(i)[3])) for i in np.linspace(0, 1, 20)]
        
        self.gradient.SetGradientColours(colororder)
        self.gradient.colortype = self.current_colormap in ['Set1', 'Set2']
        self.gradient.gradient_slider.colortype = self.current_colormap in ['Set1', 'Set2']
        
        self.gradient.gradient_slider.Refresh()
        self.gradient.gradient_slider.Update()
        self.gradient.Refresh()
        self.gradient.Update()
        
        self.Refresh()
        self.Update()
        self.Show(False)
        self.Show(True)

        if isinstance(self.cluster_volume, np.ndarray):
            self.apply_colormap(self.current_colormap, self.cluster_volume)

    def OnLoadFmri(self, event=None):
        filename = dlg.ShowImportOtherFilesDialog(id_type=const.ID_NIFTI_IMPORT)
        filename = utils.decode(filename, const.FS_ENCODE)

        fmri_data = nb.squeeze_image(nb.load(filename))
        fmri_data = nb.as_closest_canonical(fmri_data)
        fmri_data.update_header()

        self.cluster_volume = fmri_data.get_fdata().T[:, ::-1]

        # 1. Create layer of shape first
        if self.slc.matrix.shape != self.cluster_volume.shape:
            wx.MessageBox(("The overlay volume does not match the underlying structural volume"), ("InVesalius 3"))

        else:
            self.slc.aux_matrices['color_overlay'] = self.cluster_volume
            self.slc.aux_matrices['color_overlay'] = self.slc.aux_matrices['color_overlay'].astype(int)
            # 3. Show colors
            self.slc.to_show_aux = 'color_overlay'
            self.apply_colormap(self.current_colormap, self.cluster_volume)

    def apply_colormap(self, colormap, cluster_volume):
        # 2. Attribute different hue accordingly
        cluster_smoothness = int(np.max(list(set(cluster_volume.flatten()))))
        cmap = plt.get_cmap(colormap)
        colororder = [cmap(i) for i in np.linspace(0, 1, cluster_smoothness)]

        self.slc.aux_matrices_colours['color_overlay'] = {k + 1: colororder[k] for k in range(cluster_smoothness)}
        # add transparent color for nans and non GM voxels
        self.slc.aux_matrices_colours['color_overlay'][0] = (0.0, 0.0, 0.0, 0.0)

        Publisher.sendMessage('Reload actual slice')
