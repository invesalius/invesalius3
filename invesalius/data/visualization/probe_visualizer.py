import os

import vtk

import invesalius.data.vtk_utils as vtku
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher


class ProbeVisualizer:
    """
    A class for visualizing probe in the volume viewer.
    """

    def __init__(self, renderer):
        self.renderer = renderer

        self.probe_actor = None
        self.probe_path = os.path.join(inv_paths.OBJ_DIR, "stylus.stl")
        self.show_probe = False
        self.is_navigating = False

        self.AddProbeActor(self.probe_path)
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.ShowProbe, "Show probe in viewer volume")
        Publisher.subscribe(self.UpdateProbePose, "Update probe pose")
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")

    def OnNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = nav_status

    def ShowProbe(self, state):
        self.show_probe = state

        if self.probe_actor:
            self.probe_actor.SetVisibility(self.show_probe)
            if not self.is_navigating:
                Publisher.sendMessage("Render volume viewer")

    def AddProbeActor(self, probe_path):
        vtk_colors = vtk.vtkNamedColors()
        obj_polydata = vtku.CreateObjectPolyData(probe_path)

        # This rotation is done so that the probe visibility icon in viewer_volume doesn"t need to be rotated
        transform = vtk.vtkTransform()
        transform.RotateZ(-150)

        transform_filt = vtk.vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()

        obj_mapper = vtk.vtkPolyDataMapper()
        obj_mapper.SetInputData(transform_filt.GetOutput())
        obj_mapper.ScalarVisibilityOff()

        probe_actor = vtk.vtkActor()
        probe_actor.SetMapper(obj_mapper)
        probe_actor.GetProperty().SetAmbientColor(vtk_colors.GetColor3d("GhostWhite"))
        probe_actor.GetProperty().SetSpecular(30)
        probe_actor.GetProperty().SetSpecularPower(80)
        probe_actor.GetProperty().SetOpacity(1.0)
        probe_actor.SetVisibility(0)

        self.probe_actor = probe_actor
        self.renderer.AddActor(self.probe_actor)

    def RemoveProbeActor(self):
        if self.probe_actor is not None:
            self.renderer.RemoveActor(self.probe_actor)
            self.probe_actor = None

    def UpdateProbePose(self, m_img, coord):
        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]

        m_img_vtk = vtku.numpy_to_vtkMatrix4x4(m_img_flip)

        self.probe_actor.SetUserMatrix(m_img_vtk)


"""
Code used to shrink and align old stylus.stl file. 
May be useful for aligning other stl files into VTK in the future.
This computes the main axes of the object and position of the tip
then rotates and translates to align with vtk axes 

    import numpy as np

    import invesalius.data.coordinates as dco
    import invesalius.constants as const
    import invesalius.data.polydata_utils as pu

    obj_polydata = vtku.CreateObjectPolyData(probe_path) # STL file to be aligned
    #Shrink object
    scale_factor = 0.1
    shrink_transform = vtk.vtkTransform()
    shrink_transform.Scale(scale_factor, scale_factor, scale_factor)

    shrink_transform_filt = vtk.vtkTransformPolyDataFilter()
    shrink_transform_filt.SetTransform(shrink_transform)
    shrink_transform_filt.SetInputData(obj_polydata)
    shrink_transform_filt.Update()

    obj_polydata = shrink_transform_filt.GetOutput() #replace original with shrunk

    # Rotate to align obj_axes and translate tip to origin
    obj_axes, tip = self.__calculate_pca(obj_polydata)

    obj_to_vtk = np.linalg.inv(obj_axes) 
    rotation = vtk.vtkMatrix4x4() 
    rotation.SetElement(3, 3, 1) #affine transformation: last row is [0 0 0 1]
    for i in range(3): # copy obj_to_vtk to vtk_matrix
        for j in range(3):
            rotation.SetElement(i, j, obj_to_vtk[i, j])
            rotation.SetElement(3, j, 0) #last column
        rotation.SetElement(i, 3, 0) # last row

    transform = vtk.vtkTransform()
    transform.Translate(-obj_to_vtk@tip) #change to vtk basis before translating
    transform.Concatenate(rotation)

    transform_filt = vtk.vtkTransformPolyDataFilter()
    transform_filt.SetTransform(transform)
    transform_filt.SetInputData(obj_polydata)
    transform_filt.Update()

    # Write the aligned object into a new STL file
    output_path = os.path.join(inv_paths.OBJ_DIR, "stylus2.stl")
    stl_writer = vtk.vtkSTLWriter()
    stl_writer.SetFileTypeToBinary()
    stl_writer.SetFileName(output_path)
    stl_writer.SetInputData(transform_filt.GetOutput())
    stl_writer.Write()

    # Helper function
    def __calculate_pca(self, polydata): 
        #Calculate 3 principal axes of object from vtk polydata with principal component analysis.
        #Returns the object axes in the desired xyz-order in a 3x3 matrix:
        #    x-column: Secondary axis (lateral axis of object)
        #    y-column: Principal axis (longitudinal axis of object)
        #    z-column: Tertiary axis (normal to object)
        #Google aircraft axes for analogue

        points = np.array(polydata.GetPoints().GetData())

        # Center the points
        centroid = np.mean(points, axis=0)
        centered_points = points - centroid

        # Perform PCA
        covariance_matrix = np.cov(centered_points, rowvar=False)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance_matrix)
        #eigh returns vectors in ascending order (ie. principal axis is the last one)
        
        # Permute, so that y-column is the principal axis and x-column secondary axis
        eigenvectors[:, [0, 1, 2]] = eigenvectors[:, [1, 2, 0]]
        
        # the tip is the point furthest along principal axis 
        # for another STL object tip could be in opposite direction so would use argmin instead
        tip = points[np.argmax(np.dot(centered_points, eigenvectors[:,1]))]
        return eigenvectors, tip
"""
