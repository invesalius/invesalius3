import vtk

import invesalius.data.coordinates as dco
import invesalius.constants as const
import invesalius.data.vtk_utils as vtku
import invesalius.data.polydata_utils as pu

from invesalius.pubsub import pub as Publisher
import invesalius.session as ses


class CoilVisualizer:
    """
    A class for visualizing coil in the volume viewer.
    """
    # Color for highlighting a marker.
    HIGHLIGHT_COLOR = vtk.vtkNamedColors().GetColor3d('Red')

    # Color for the marker for target when the coil at the target.
    COIL_AT_TARGET_COLOR = vtk.vtkNamedColors().GetColor3d('Green')

    def __init__(self, renderer, interactor, actor_factory, vector_field_visualizer):
        self.renderer = renderer
        self.interactor = interactor
        
        # The actor factory is used to create actors for the coil and coil center.
        self.actor_factory = actor_factory

        # The vector field visualizer is used to show a vector field relative to the coil.
        self.vector_field_visualizer = vector_field_visualizer

        # The actor for showing the actual coil in the volume viewer.
        self.coil_actor = None

        # The actor for showing the center of the actual coil in the volume viewer.
        self.coil_center_actor = None

        # The actor for showing the target coil in the volume viewer.
        self.target_coil_actor = None

        # The assembly for showing the vector field relative to the coil in the volume viewer.
        self.vector_field_assembly = self.vector_field_visualizer.CreateVectorFieldAssembly()

        # Add the vector field assembly to the renderer, but make it invisible until the coil is shown.
        self.renderer.AddActor(self.vector_field_assembly)
        self.vector_field_assembly.SetVisibility(0)

        self.x_axis_actor = None
        self.y_axis_actor = None
        self.z_axis_actor = None

        self.coil_at_target = False

        self.coil_path = None
        self.coil_polydata = None

        self.show_coil = False
        self.is_navigating = False

        self.LoadConfig()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetCoilAtTarget, 'Coil at target')
        Publisher.subscribe(self.OnNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.TrackObject, 'Track object')
        Publisher.subscribe(self.ShowCoil, 'Show coil in viewer volume')
        Publisher.subscribe(self.ConfigureCoil, 'Configure coil')
        Publisher.subscribe(self.UpdateCoilPose, 'Update coil pose')
        Publisher.subscribe(self.UpdateVectorField, 'Update vector field')

    def SaveConfig(self):
        coil_path = self.coil_path.decode(const.FS_ENCODE) if self.coil_path is not None else None

        session = ses.Session()
        session.SetConfig('coil_path', coil_path)

    def LoadConfig(self):
        session = ses.Session()
        coil_path_unencoded = session.GetConfig('coil_path')

        if coil_path_unencoded is None:
            return

        self.coil_path = coil_path_unencoded.encode(const.FS_ENCODE)
        self.coil_polydata = pu.LoadPolydata(path=coil_path_unencoded)

    def UpdateVectorField(self):
        """
        Update the vector field assembly to reflect the current vector field.
        """
        # Create a new vector field assembly.
        new_vector_field_assembly = self.vector_field_visualizer.CreateVectorFieldAssembly()

        # Replace the old vector field assembly with the new one.
        self.actor_factory.ReplaceActor(self.renderer, self.vector_field_assembly, new_vector_field_assembly)

        # Store the new vector field assembly.
        self.vector_field_assembly = new_vector_field_assembly

        # If not navigating, render the scene.
        if not self.is_navigating:
            self.interactor.Render()

    def SetCoilAtTarget(self, state):
        self.coil_at_target = state

        vtk_colors = vtk.vtkNamedColors()

        # Set the color of the target coil based on whether the coil is at the target or not.
        target_coil_color = vtk_colors.GetColor3d('Green') if state else vtk_colors.GetColor3d('DarkOrange')

        # Set the color of both target coil (representing the target) and the coil center (representing the actual coil).
        self.target_coil_actor.GetProperty().SetDiffuseColor(target_coil_color)
        self.coil_center_actor.GetProperty().SetDiffuseColor(target_coil_color)

    def RemoveCoilActor(self):
        self.renderer.RemoveActor(self.coil_actor)
        self.renderer.RemoveActor(self.coil_center_actor)
        # TODO: Vector field assembly follows a different pattern for removal, should unify.
        self.vector_field_assembly.SetVisibility(0)
        self.renderer.RemoveActor(self.x_axis_actor)
        self.renderer.RemoveActor(self.y_axis_actor)
        self.renderer.RemoveActor(self.z_axis_actor)

        self.coil_actor = None
        self.coil_center_actor = None
        self.x_axis_actor = None
        self.y_axis_actor = None
        self.z_axis_actor = None

    def ConfigureCoil(self, coil_path=None, polydata=None):
        self.coil_path = coil_path
        self.coil_polydata = polydata

        self.SaveConfig()

    def OnNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = nav_status
        if self.is_navigating and self.coil_actor is not None:
            self.coil_actor.SetVisibility(self.show_coil)

    # Called when 'track object' button is pressed in the user interface.
    def TrackObject(self, enabled):
        if self.coil_path is None:
            return

        # Remove the previous coil actor if it exists.
        if self.coil_actor is not None:
            self.RemoveCoilActor()

        # If enabled, add a new coil actor.
        if enabled:
            self.AddCoilActor(self.coil_path)

    # Called when 'show coil' button is pressed in the user interface.
    def ShowCoil(self, state):
        self.show_coil = state

        if self.target_coil_actor is not None:
            self.target_coil_actor.SetVisibility(state)

        if self.coil_actor:
            self.coil_actor.SetVisibility(state)
            self.x_axis_actor.SetVisibility(state)
            self.y_axis_actor.SetVisibility(state)
            self.z_axis_actor.SetVisibility(state)

        if not self.is_navigating:
            self.interactor.Render()

    def AddTargetCoil(self, m_target):
        self.RemoveTargetCoil()

        vtk_colors = vtk.vtkNamedColors()
            
        transform = vtk.vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtk.vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(self.coil_polydata)
        transform_filt.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        obj_mapper = vtk.vtkPolyDataMapper()
        obj_mapper.SetInputData(normals.GetOutput())
        obj_mapper.ScalarVisibilityOff()
        #obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.target_coil_actor = vtk.vtkActor()
        self.target_coil_actor.SetMapper(obj_mapper)
        self.target_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkOrange'))
        self.target_coil_actor.GetProperty().SetSpecular(0.5)
        self.target_coil_actor.GetProperty().SetSpecularPower(10)
        self.target_coil_actor.GetProperty().SetOpacity(.3)
        self.target_coil_actor.SetVisibility(self.show_coil)
        self.target_coil_actor.SetUserMatrix(m_target)

        self.renderer.AddActor(self.target_coil_actor)

        if not self.is_navigating:
            self.interactor.Render()

    def RemoveTargetCoil(self):
        if self.target_coil_actor is None:
            return

        self.renderer.RemoveActor(self.target_coil_actor)
        self.target_coil_actor = None

    def AddCoilActor(self, coil_path):
        """
        Add actors for actual coil, coil center, and x, y, and z-axes to the renderer.
        """
        vtk_colors = vtk.vtkNamedColors()
        obj_polydata = vtku.CreateObjectPolyData(coil_path)

        transform = vtk.vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtk.vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        obj_mapper = vtk.vtkPolyDataMapper()
        obj_mapper.SetInputData(normals.GetOutput())
        obj_mapper.ScalarVisibilityOff()
        #obj_mapper.ImmediateModeRenderingOn()  # improve performance

        coil_actor = vtk.vtkActor()
        coil_actor.SetMapper(obj_mapper)
        coil_actor.GetProperty().SetAmbientColor(vtk_colors.GetColor3d('GhostWhite'))
        coil_actor.GetProperty().SetSpecular(30)
        coil_actor.GetProperty().SetSpecularPower(80)
        coil_actor.GetProperty().SetOpacity(.4)
        coil_actor.SetVisibility(0)

        self.coil_actor = coil_actor

        # Create an actor for the coil center.
        coil_center_actor = self.actor_factory.CreateTorus(
            position=[0., 0., 0.],
            orientation=[0., 0., 0.],
            colour=vtk_colors.GetColor3d('Red'),
            scale=0.5,
        )
        self.coil_center_actor = coil_center_actor

        # Create actors for the x, y, and z-axes.
        self.x_axis_actor = self.actor_factory.CreateLine([0., 0., 0.], [1., 0., 0.], colour=[.0, .0, 1.0])
        self.y_axis_actor = self.actor_factory.CreateLine([0., 0., 0.], [0., 1., 0.], colour=[.0, 1.0, .0])
        self.z_axis_actor = self.actor_factory.CreateLine([0., 0., 0.], [0., 0., 1.], colour=[1.0, .0, .0])

        self.renderer.AddActor(self.coil_actor)
        self.renderer.AddActor(self.coil_center_actor)
        # TODO: Vector field assembly follows a different pattern for addition, should unify.
        self.vector_field_assembly.SetVisibility(1)
        self.renderer.AddActor(self.x_axis_actor)
        self.renderer.AddActor(self.y_axis_actor)
        self.renderer.AddActor(self.z_axis_actor)

        self.x_axis_actor.SetVisibility(0)
        self.y_axis_actor.SetVisibility(0)
        self.z_axis_actor.SetVisibility(0)

    def UpdateCoilPose(self, m_img, coord):
        """
        During navigation, use updated coil pose to perform the following tasks:

        - Update actor positions for coil, coil center, and coil orientation axes.
        """
        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]

        m_img_vtk = vtku.numpy_to_vtkMatrix4x4(m_img_flip)

        # Update actor positions for coil, coil center, and coil orientation axes.
        self.coil_actor.SetUserMatrix(m_img_vtk)
        self.coil_center_actor.SetUserMatrix(m_img_vtk)
        self.vector_field_assembly.SetUserMatrix(m_img_vtk)
        self.x_axis_actor.SetUserMatrix(m_img_vtk)
        self.y_axis_actor.SetUserMatrix(m_img_vtk)
        self.z_axis_actor.SetUserMatrix(m_img_vtk)
