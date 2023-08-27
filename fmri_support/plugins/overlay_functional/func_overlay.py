import wx
import vtk
import numpy as np
from pubsub import pub as Publisher
from six import with_metaclass

from invesalius.data import styles

import nibabel as nib
from copy import deepcopy
from matplotlib.pyplot import cm
from sklearn.cluster import KMeans

import os
from . import gui

class FunctionalOverlayStyle(styles.DefaultInteractorStyle):
    gui = None
    def __init__(self, viewer):
        super().__init__(viewer)

        self.picker = vtk.vtkWorldPointPicker()
        # NOTE: BIDS folder pathing
        self.datapath = '../resources/' # In the same subject folder as where one loads the T1 volumes
        resource_files = os.listdir(self.datapath)

        for filename in resource_files:
            if filename.startswith('funcslice_display'):
                self.funcslice_file = filename
            elif filename.startswith('G1_display'):
                self.G1 = filename
            elif filename.startswith('yeo7_display'):
                self.y7 = filename
            elif filename.startswith('yeo17_display'):
                self.y17 = filename

        self.func_frame = nib.load(self.datapath + self.funcslice_file).get_fdata()
        self.func_conn = nib.load(self.datapath + self.G1).get_fdata()
        self.yeo7 = nib.load(self.datapath + self.y7).get_fdata()
        self.yeo17 = nib.load(self.datapath + self.y17).get_fdata()

        self.cluster_smoothness = 10
        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButtonOverlay)


    def SetUp(self):
        print("SetUP")
        if self.gui is None:
            self.create_gui()

    def CleanUp(self):
        print("CleanUp")
        if self.gui is not None:
            self.destroy_gui()

    def OnPressLeftButtonOverlay(self, obj, evt):
        mask = self.viewer.slice_.current_mask


        mouse_x, mouse_y = self.GetMousePosition()
        x, y, z = self.viewer.get_voxel_coord_by_screen_pos(mouse_x, mouse_y, self.picker)
        image = self.viewer.slice_.matrix
        dz, dy, dx = image.shape

        # Set the overlay
        # we transpose and flip since the functional frames are not rotated in the same way structurals are
        if self.gui.choice_morph == "TimeFrame":
            clust_vol = deepcopy(self.func_frame).T[:,::-1]

            # 1. Create layer of shape first
            self.viewer.slice_.aux_matrices['color_overlay'] = clust_vol
            self.viewer.slice_.aux_matrices['color_overlay'] = self.viewer.slice_.aux_matrices['color_overlay'].astype(int)

            # 2. Attribute different hue accordingly
            self.viewer.slice_.aux_matrices_colours['color_overlay'] = {k+1: (1.0,1.0,0.0, 1/(k+1)) for k in range(self.cluster_smoothness)}
            self.viewer.slice_.aux_matrices_colours['color_overlay'][0] = (0.0, 0.0, 0.0, 0.0) # add transparent color for nans and non GM voxels

            # 3. Show colors
            self.viewer.slice_.to_show_aux = 'color_overlay'
            self.viewer.discard_mask_cache(all_orientations=True, vtk_cache=True)

            Publisher.sendMessage('Reload actual slice')
        elif self.gui.choice_morph == "Yeo-7":
            self.cluster_smoothness = 7
            tmp = deepcopy(self.yeo7)
            clust_vol = tmp.astype(int).T[:,::-1]
        elif self.gui.choice_morph == "Yeo-17":
            self.cluster_smoothness = 17
            tmp = deepcopy(self.yeo17)
            clust_vol = tmp.astype(int).T[:,::-1]
        else:
            tmp = deepcopy(self.func_conn)
            clust_vol = tmp.astype(int).T[:,::-1]

        # 1. Create layer of shape first
        self.viewer.slice_.aux_matrices['color_overlay'] = clust_vol
        self.viewer.slice_.aux_matrices['color_overlay'] = self.viewer.slice_.aux_matrices['color_overlay'].astype(int)

        # 2. Attribute different hue accordingly
        color = cm.rainbow(np.linspace(0, 1, self.cluster_smoothness), alpha=0.4)
        self.viewer.slice_.aux_matrices_colours['color_overlay'] = {k+1:color[k] for k in range(self.cluster_smoothness)}
        self.viewer.slice_.aux_matrices_colours['color_overlay'][0] = (0.0, 0.0, 0.0, 0.0) # add transparent color for nans and non GM voxels

        # 3. Show colors
        self.viewer.slice_.to_show_aux = 'color_overlay'
        self.viewer.discard_mask_cache(all_orientations=True, vtk_cache=True)


        Publisher.sendMessage('Reload actual slice')

    @classmethod
    def create_gui(cls):
        if cls.gui is None:
            top_window = wx.GetApp().GetTopWindow()
            cls.gui = gui.FunctionalOverlayGUI(top_window)
            cls.gui.Show()

    @classmethod
    def destroy_gui(cls):
        if cls.gui is not None:
            cls.gui.Destroy()
            cls.gui = None
