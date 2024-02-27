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
import matplotlib.pyplot as plt
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
import invesalius.gui.widgets.gradient as grad


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
        self.session = ses.Session()
        self.colormaps = ["twilight","hsv","Set1","Set2","winter","hot","autumn"]
        self.cur_colormap = "twilight"
        self.filename = None

        line0 = wx.StaticText(self, -1,
                                    _("Select Modalities / File"))
        
        # Button for import config coil file
        tooltip = wx.ToolTip(_("Load Modalities"))
        btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLinkLoad)
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
        combo_thresh.Bind(wx.EVT_COMBOBOX, self.SelectColormap)
        combo_thresh.SetSelection(0) # By Default use Twilight

        self.combo_thresh = combo_thresh

        ## LINE 4
        cmap = plt.get_cmap(self.cur_colormap)
        colororder = [(int(255*cmap(i)[0]),
                       int(255*cmap(i)[1]),
                       int(255*cmap(i)[2]),
                       int(100*cmap(i)[3])) for i in np.linspace(0, 1, 100)]
        
        gradient = grad.GradientDisp(self, -1, -5000, 5000, -5000, 5000,
                                           colororder, colortype=self.cur_colormap in ['Set1', 'Set2'])
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
        Publisher.subscribe(self.OnLinkLoad, 'Loading status')
        Publisher.subscribe(self.SelectColormap, 'Changing colormap')


    def SelectColormap(self, event=None):
        self.cur_colormap = self.colormaps[self.combo_thresh.GetSelection()]
        self.ReloadSlice()
        cmap = plt.get_cmap(self.cur_colormap)
        colororder = [(int(255*cmap(i)[0]),
                       int(255*cmap(i)[1]),
                       int(255*cmap(i)[2]),
                       int(100*cmap(i)[3])) for i in np.linspace(0, 1, 20)]
        
        self.gradient.SetGradientColours(colororder)
        self.gradient.colortype = self.cur_colormap in ['Set1', 'Set2']
        self.gradient.gradient_slider.colortype = self.cur_colormap in ['Set1', 'Set2']
        
        self.gradient.gradient_slider.Refresh()
        self.gradient.gradient_slider.Update()
        self.gradient.Refresh()
        self.gradient.Update()
        
        self.Refresh()
        self.Update()
        self.Show(False)
        self.Show(True)

    def ReloadSlice(self):
        if self.filename is None: return

        # Update Slice
        import nibabel as nib
        clust_vol = nib.load(self.filename).get_fdata().T[:,::-1]
        
        from invesalius.data.slice_ import Slice
        # 1. Create layer of shape first
        slc = Slice()
        slc.aux_matrices['color_overlay'] = clust_vol
        slc.aux_matrices['color_overlay'] = slc.aux_matrices['color_overlay'].astype(int)

        # 2. Attribute different hue accordingly
        cluster_smoothness = int(np.max(list(set(clust_vol.flatten()))))
        cmap = plt.get_cmap(self.cur_colormap)
        colororder = [cmap(i) for i in np.linspace(0, 1, cluster_smoothness)]

        slc.aux_matrices_colours['color_overlay'] = {k+1: colororder[k] for k in range(cluster_smoothness)}
        slc.aux_matrices_colours['color_overlay'][0] = (0.0, 0.0, 0.0, 0.0) # add transparent color for nans and non GM voxels

        # 3. Show colors
        slc.to_show_aux = 'color_overlay'

        Publisher.sendMessage('Reload actual slice')        

    def OnLinkLoad(self, event=None):
        filename = dlg.ShowLoadSaveDialog(message=_(u"Load volume to overlay"),
                                          wildcard=_("Registration files (*.nii.gz)|*.nii.gz"))
        self.filename = filename
        # Update Slice
        import nibabel as nib
        clust_vol = nib.load(filename).get_fdata().T[:,::-1]
        

        from invesalius.data.slice_ import Slice
        # 1. Create layer of shape first
        slc = Slice()
        if slc.matrix.shape != clust_vol.shape:
            wx.MessageBox(("The overlay volume does not match the underlying structural volume"), ("InVesalius 3"))
            return

        slc.aux_matrices['color_overlay'] = clust_vol
        slc.aux_matrices['color_overlay'] = slc.aux_matrices['color_overlay'].astype(int)

        # 2. Attribute different hue accordingly
        cluster_smoothness = int(np.max(list(set(clust_vol.flatten()))))
        cmap = plt.get_cmap(self.cur_colormap)
        colororder = [cmap(i) for i in np.linspace(0, 1, cluster_smoothness)]

        slc.aux_matrices_colours['color_overlay'] = {k+1: colororder[k] for k in range(cluster_smoothness)}
        slc.aux_matrices_colours['color_overlay'][0] = (0.0, 0.0, 0.0, 0.0) # add transparent color for nans and non GM voxels

        # 3. Show colors
        slc.to_show_aux = 'color_overlay'

        Publisher.sendMessage('Reload actual slice')
