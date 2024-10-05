import os

import vtk

import invesalius.constants as const
import invesalius.data.polydata_utils as pu
import invesalius.data.vtk_utils as vtku
import invesalius.session as ses
from invesalius.navigation.navigation import Navigation
from invesalius.navigation.tracker import Tracker
from invesalius.pubsub import pub as Publisher


class CoilVisualizer:
    """
    A class for visualizing coil in the volume viewer.
    """

    # Color for highlighting a marker.
    HIGHLIGHT_COLOR = vtk.vtkNamedColors().GetColor3d("Red")

    # Color for the marker for target when the coil at the target.
    COIL_AT_TARGET_COLOR = vtk.vtkNamedColors().GetColor3d("Green")

    def __init__(self, renderer, actor_factory, vector_field_visualizer):
        self.renderer = renderer
        self.tracker = Tracker()

        # Keeps track of whether tracker fiducials have been set.
        self.tracker_fiducials_set = self.tracker.AreTrackerFiducialsSet()

        # The actor factory is used to create actors for the coil and coil center.
        self.actor_factory = actor_factory

        # The vector field visualizer is used to show a vector field relative to the coil.
        self.vector_field_visualizer = vector_field_visualizer

        # Keyed by coil name, each coil has a dict holding its coil actor, coil center actor, coil path.
        self.coils = {}

        # The actor for showing the target coil in the volume viewer.
        self.target_coil_actor = None

        # The assembly for showing the vector field relative to the coil in the volume viewer.
        self.vector_field_assembly = self.vector_field_visualizer.CreateVectorFieldAssembly()

        # Add the vector field assembly to the renderer, but make it invisible until the coil is shown.
        self.renderer.AddActor(self.vector_field_assembly)
        self.vector_field_assembly.SetVisibility(0)

        self.coil_at_target = False

        self.is_navigating = False

        self.LoadConfig()

        self.ShowCoil(False)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetCoilAtTarget, "Coil at target")
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")
        Publisher.subscribe(self.ShowCoil, "Show coil in viewer volume")
        Publisher.subscribe(self.ResetCoilVisualizer, "Reset coil selection")
        Publisher.subscribe(self.SelectCoil, "Select coil")
        Publisher.subscribe(self.UpdateCoilPoses, "Update coil poses")
        Publisher.subscribe(self.UpdateVectorField, "Update vector field")

    def LoadConfig(self):
        session = ses.Session()

        # Get the list of coil names of coils selected for navigation
        selected_coils = (session.GetConfig("navigation", {})).get("selected_coils", [])

        saved_registrations = session.GetConfig("coil_registrations", {})
        for coil_name in selected_coils:
            if (coil := saved_registrations.get(coil_name, None)) is not None:
                self.AddCoil(coil_name, coil["path"])

    def UpdateVectorField(self):
        """
        Update the vector field assembly to reflect the current vector field.
        """
        # Create a new vector field assembly.
        new_vector_field_assembly = self.vector_field_visualizer.CreateVectorFieldAssembly()

        # Replace the old vector field assembly with the new one.
        self.actor_factory.ReplaceActor(
            self.renderer, self.vector_field_assembly, new_vector_field_assembly
        )

        # Store the new vector field assembly.
        self.vector_field_assembly = new_vector_field_assembly

        # If not navigating, render the scene.
        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def SetCoilAtTarget(self, state):
        self.coil_at_target = state

        vtk_colors = vtk.vtkNamedColors()

        # Set the color of the target coil based on whether the coil is at the target or not.
        target_coil_color = (
            vtk_colors.GetColor3d("Green") if state else vtk_colors.GetColor3d("DarkOrange")
        )

        # Set the color of both target coil (representing the target) and the coil center (representing the actual coil).
        self.target_coil_actor.GetProperty().SetDiffuseColor(target_coil_color)

        # Multicoil mode will have a different GUI for targeting, so this is irrelevant for multicoil
        # In single coil mode, just get the single coil
        coil = next(iter(self.coils.values()), None)
        coil["center_actor"].GetProperty().SetDiffuseColor(target_coil_color)

    def OnNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = nav_status

    def ShowCoil(self, state, coil_name=None):
        if coil_name is None:  # Show/hide all coils
            for coil in self.coils.values():
                coil["actor"].SetVisibility(state)
                coil["center_actor"].SetVisibility(True)  # Always show the center donut actor

        elif (coil := self.coils.get(coil_name, None)) is not None:
            # Just toggle the visibility when dealing with specific coils
            new_state = not coil["actor"].GetVisibility()
            coil["actor"].SetVisibility(new_state)
            coil["center_actor"].SetVisibility(True)  # Always show the center donut actor

            # If all coils are hidden/shown, update the color of Show-coil button
            coils_visible = [coil["actor"].GetVisibility() for coil in self.coils.values()]
            if not any(coils_visible):  # all coils are hidden
                Publisher.sendMessage("Press show-coil button", pressed=False)
            elif all(coils_visible):  # all coils are shown
                Publisher.sendMessage("Press show-coil button", pressed=True)

        if self.target_coil_actor is not None:
            self.target_coil_actor.SetVisibility(state)
        # self.vector_field_assembly.SetVisibility(state) # LUKATODO: Keep this hidden for now

        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def AddTargetCoil(self, m_target):
        self.RemoveTargetCoil()

        vtk_colors = vtk.vtkNamedColors()

        # LUKATODO: this is an arbitrary coil... but works for single coil mode
        decoded_path = next(iter(self.coils.values()))["path"]

        coil_filename = os.path.basename(decoded_path)
        coil_dir = os.path.dirname(decoded_path)

        # A hack to load the coil without the handle for the Magstim figure-8 coil.
        coil_path = (
            os.path.join(coil_dir, coil_filename)
            if coil_filename != "magstim_fig8_coil.stl"
            else os.path.join(coil_dir, "magstim_fig8_coil_no_handle.stl")
        )

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
        # obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.target_coil_actor = vtk.vtkActor()
        self.target_coil_actor.SetMapper(obj_mapper)
        self.target_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d("DarkOrange"))
        self.target_coil_actor.GetProperty().SetSpecular(0.5)
        self.target_coil_actor.GetProperty().SetSpecularPower(10)
        self.target_coil_actor.GetProperty().SetOpacity(0.3)
        self.target_coil_actor.SetVisibility(True)
        self.target_coil_actor.SetUserMatrix(m_target)

        self.renderer.AddActor(self.target_coil_actor)

        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def RemoveTargetCoil(self):
        if self.target_coil_actor is None:
            return

        self.renderer.RemoveActor(self.target_coil_actor)
        self.target_coil_actor = None

    # Called when a coil is (un)selected for navigation
    def SelectCoil(self, coil_name, coil_registration):
        if coil_registration is not None:  # coil is selected
            self.AddCoil(coil_name, coil_registration["path"])
        else:  # coil is unselected
            self.RemoveCoil(coil_name)

    def AddCoil(self, coil_name, coil_path):
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
        # obj_mapper.ImmediateModeRenderingOn()  # improve performance

        coil_actor = vtk.vtkActor()
        coil_actor.SetMapper(obj_mapper)
        coil_actor.GetProperty().SetAmbientColor(vtk_colors.GetColor3d("GhostWhite"))
        coil_actor.GetProperty().SetSpecular(30)
        coil_actor.GetProperty().SetSpecularPower(80)
        coil_actor.GetProperty().SetOpacity(0.4)
        coil_actor.SetVisibility(1)

        # Create an actor for the coil center.
        coil_center_actor = self.actor_factory.CreateTorus(
            position=[0.0, 0.0, 0.0],
            orientation=[0.0, 0.0, 0.0],
            colour=vtk_colors.GetColor3d("Red"),
            scale=0.5,
        )

        self.renderer.AddActor(coil_actor)
        self.renderer.AddActor(coil_center_actor)

        self.coils[coil_name] = {}
        self.coils[coil_name]["actor"] = coil_actor
        self.coils[coil_name]["center_actor"] = coil_center_actor
        self.coils[coil_name]["path"] = coil_path

        # LUKATODO: Vector field assembly follows a different pattern for addition, should unify.
        # self.vector_field_assembly.SetVisibility(1)

    def RemoveCoil(self, coil_name=None):
        if coil_name is not None:
            coil = self.coils.pop(coil_name, None)
            if coil is not None:
                self.renderer.RemoveActor(coil["actor"])
                self.renderer.RemoveActor(coil["center_actor"])
        else:  # Remove all coils
            for coil in self.coils.values():
                self.renderer.RemoveActor(coil["actor"])
                self.renderer.RemoveActor(coil["center_actor"])
            self.coils = {}

        # self.vector_field_assembly.SetVisibility(0)
        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def ResetCoilVisualizer(self, n_coils):
        self.RemoveCoil()  # Remove all coils

    def UpdateCoilPoses(self, m_imgs, coords):
        """
        During navigation, use updated coil pose to perform the following tasks:

        - Update actor positions for coil, coil center, and coil orientation axes.
        """

        for name, m_img in m_imgs.items():
            m_img_flip = m_img.copy()
            m_img_flip[1, -1] = -m_img_flip[1, -1]

            m_img_vtk = vtku.numpy_to_vtkMatrix4x4(m_img_flip)

            # Update actor positions for coil, coil center, and coil orientation axes.
            self.coils[name]["actor"].SetUserMatrix(m_img_vtk)
            self.coils[name]["center_actor"].SetUserMatrix(m_img_vtk)

            # LUKATODO
            # self.vector_field_assembly.SetUserMatrix(m_img_vtk)
