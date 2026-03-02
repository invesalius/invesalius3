import vtk
import wx

from invesalius.gui import dialogs
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class SurfaceGeometry(metaclass=Singleton):
    def __init__(self):
        self.__bind_events()

        self.surfaces = []

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor, "Load surface actor into viewer")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.RemoveSurface, "Remove surface actor from viewer")

    def OnCloseProject(self):
        self.surfaces = []

    def PrecalculateSurfaceData(self, actor):
        normals = self.GetSurfaceNormals(actor)
        highest_z = self.CalculateHighestZ(actor)
        polydata = actor.GetMapper().GetInput()
        return {
            "actor": actor,
            "polydata": polydata,
            "normals": normals,
            "highest_z": highest_z,
        }

    def LoadActor(self, actor):
        # Maintain a list of surfaces and their smoothed versions. However,
        # do not compute the smoothed surface until it is needed.
        #
        # The original versions are used for visualization, while the smoothed
        # versions are used for calculations.
        self.surfaces.append(
            {
                "original": self.PrecalculateSurfaceData(actor),
                "smoothed": None,
            }
        )

    def RemoveSurface(self, actor):
        """
        Removes a surface by its actor from internal storage.
        """
        for index, surface in enumerate(self.surfaces):
            if surface["original"]["actor"] == actor:
                self.surfaces.pop(index)

    def SmoothSurface(
        self,
        polydata,
        actor,
        progress_window,
        smooth_iterations=100,
        relaxation_factor=0.4,
        hole_size=1000,
        inflate_scale=0.1,
        inflate_iterations=20,
    ):
        # Preprocessing: Clean and triangulate input data
        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(polydata)
        cleaner.Update()

        triangles = vtk.vtkTriangleFilter()
        triangles.SetInputConnection(cleaner.GetOutputPort())
        triangles.Update()

        # Compute consistent normals
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(triangles.GetOutputPort())
        normals.ConsistencyOn()
        normals.SplittingOff()
        normals.Update()

        progress_window.Update()
        # This step involves explicitly copying points and connectivity information to a new vtkPolyData.
        # It ensures that all connectivity information is accurate and explicitly defined.
        new_points = vtk.vtkPoints()
        new_polys = vtk.vtkCellArray()
        num_points = normals.GetOutput().GetNumberOfPoints()
        for i in range(num_points):
            p = normals.GetOutput().GetPoint(i)
            new_points.InsertNextPoint(p)
            progress_window.Update()

        # Copy cells
        polys = normals.GetOutput().GetPolys()
        polys.InitTraversal()
        id_list = vtk.vtkIdList()
        while polys.GetNextCell(id_list):
            new_polys.InsertNextCell(id_list)
            progress_window.Update()

        new_polydata = vtk.vtkPolyData()
        new_polydata.SetPoints(new_points)
        new_polydata.SetPolys(new_polys)

        def apply_smoothing_and_filling(input_pd):
            """Helper function to apply smoothing and hole filling."""
            smoother = vtk.vtkSmoothPolyDataFilter()
            smoother.SetInputData(input_pd)
            smoother.SetNumberOfIterations(smooth_iterations)
            smoother.SetRelaxationFactor(relaxation_factor)
            smoother.FeatureEdgeSmoothingOff()
            smoother.BoundarySmoothingOff()
            smoother.Update()
            progress_window.Update()

            filler = vtk.vtkFillHolesFilter()
            filler.SetInputConnection(smoother.GetOutputPort())
            filler.SetHoleSize(hole_size)
            filler.Update()
            progress_window.Update()
            return filler.GetOutput()

        # Process through two rounds of smoothing and filling
        processed_data = apply_smoothing_and_filling(new_polydata)

        # Mesh inflation with iterative normal displacement
        def inflate_mesh(input_pd):
            """Inflate mesh by displacing points along their normals."""
            normal_generator = vtk.vtkPolyDataNormals()
            normal_generator.SetInputData(input_pd)
            normal_generator.ComputePointNormalsOn()
            normal_generator.Update()

            inflated = vtk.vtkPolyData()
            inflated.DeepCopy(input_pd)
            points = inflated.GetPoints()

            for _ in range(inflate_iterations):
                normals_data = normal_generator.GetOutput().GetPointData().GetNormals()
                new_points = vtk.vtkPoints()
                new_points.DeepCopy(points)

                for i in range(new_points.GetNumberOfPoints()):
                    p = new_points.GetPoint(i)
                    n = normals_data.GetTuple(i)
                    new_point = [p[j] + inflate_scale * n[j] for j in range(3)]
                    new_points.SetPoint(i, new_point)

                inflated.SetPoints(new_points)
                # Update normals for next iteration
                normal_generator.SetInputData(inflated)
                normal_generator.Update()
                points = inflated.GetPoints()
                progress_window.Update()

            return inflated

        inflated_mesh = inflate_mesh(processed_data)
        processed_data = apply_smoothing_and_filling(inflated_mesh)
        progress_window.Update()

        # Create and configure visualization components
        smoothed_mapper = vtk.vtkPolyDataMapper()
        smoothed_mapper.SetInputData(processed_data)

        # Create a new actor using the smoothed mapper.
        smoothed_actor = vtk.vtkActor()
        smoothed_actor.SetMapper(smoothed_mapper)

        # Copy visual properties from the original actor to the new one.
        smoothed_actor.GetProperty().DeepCopy(actor.GetProperty())

        return smoothed_actor

    def HideAllSurfaces(self):
        """
        Forcibly hide all surfaces in the viewer, overriding the user-set visibility state of each surface.
        This is useful, e.g., when we want to pick a marker without any of the surfaces getting in the way.
        """
        for surface in self.surfaces:
            # Only the original actor is used for visualization, so we only need to hide that one.
            actor = surface["original"]["actor"]
            surface["visible"] = actor.GetVisibility()
            actor.VisibilityOff()

    def ShowAllSurfaces(self):
        """
        Show all surfaces in the viewer, restoring the visibility state of each surface to what it was before
        HideAllSurfaces was called.
        """
        for surface in self.surfaces:
            # Only the original actor is used for visualization, so we only need to show that one.
            actor = surface["original"]["actor"]
            visible = surface["visible"] if "visible" in surface else True
            actor.SetVisibility(visible)

    def GetSurfaceCenter(self, actor):
        # Get the bounding box of the actor.
        bounds = actor.GetBounds()

        # Calculate center for each dimension.
        center_x = (bounds[0] + bounds[1]) / 2
        center_y = (bounds[2] + bounds[3]) / 2
        center_z = (bounds[4] + bounds[5]) / 2

        return (center_x, center_y, center_z)

    def GetSurfaceNormals(self, actor):
        # Get the polydata from the actor.
        polydata = actor.GetMapper().GetInput()

        # Compute normals for the surface.
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(polydata)

        # Enable point normals to average normals at vertices.
        normals.ComputePointNormalsOn()

        # Enable smoothing.
        normals.SetFeatureAngle(60.0)
        normals.SplittingOff()

        # Enable consistency check.
        normals.ConsistencyOn()

        # Update the vtkPolyDataNormals object to process the input.
        normals.Update()

        return normals.GetOutput()

    def CalculateHighestZ(self, actor):
        # Get the polydata from the actor.
        polydata = actor.GetMapper().GetInput()

        # Extract the z-coordinates of all points and return the highest one.
        points = polydata.GetPoints()
        if not points or points.GetNumberOfPoints() == 0:
            return float("-inf")

        highest_z = max([points.GetPoint(i)[2] for i in range(points.GetNumberOfPoints())])
        return highest_z

    def GetSmoothedScalpSurface(self):
        # Retrieve the surface with the highest z-coordinate.
        if not self.surfaces:
            return None

        # Find the surface with the highest z-coordinate
        highest_surface = max(self.surfaces, key=lambda surface: surface["original"]["highest_z"])

        # Track if a new highest surface was detected
        current_id = id(highest_surface)
        previous_id = getattr(self, "_last_highest_surface_id", None)
        self._last_highest_surface_id = current_id
        has_changed = current_id != previous_id

        # If the highest surface has changed, ask the user if they want to update
        if has_changed and highest_surface["smoothed"] is not None:
            result = dialogs.ShowConfirmationDialog(
                _(
                    "A new highest scalp surface was identified. Do you want to update the smoothed surface?"
                )
            )
            if result != wx.ID_OK:
                return highest_surface["smoothed"]

        # Reprocess if user agreed OR if no smoothed version exists yet
        if has_changed or highest_surface["smoothed"] is None:
            progress_window = dialogs.SurfaceSmoothingProgressWindow()
            progress_window.Update()
            polydata = highest_surface["original"]["polydata"]
            actor = highest_surface["original"]["actor"]

            # Create a smoothed version of the actor.
            if polydata.GetNumberOfCells() > 10000:
                smoothed_actor = self.SmoothSurface(polydata, actor, progress_window)
            else:
                smoothed_actor = actor
            progress_window.Update()
            highest_surface["smoothed"] = self.PrecalculateSurfaceData(smoothed_actor)

            progress_window.Close()

        return highest_surface["smoothed"]

    def GetClosestPointOnSurface(self, surface_name, point):
        surface = self.GetSmoothedScalpSurface()

        polydata = surface["polydata"]
        normals = surface["normals"]

        # Create a cell locator using VTK. This will allow us to find the closest point on the surface to the given point.
        point_locator = vtk.vtkPointLocator()
        point_locator.SetDataSet(polydata)
        point_locator.BuildLocator()
        closest_point_id = point_locator.FindClosestPoint(point)

        # Retrieve the coordinates of the closest point using the point ID.
        closest_point = polydata.GetPoint(closest_point_id)

        # Extract the normal at the closest point
        normal_data = normals.GetPointData().GetNormals()
        closest_normal = normal_data.GetTuple(closest_point_id)

        return closest_point, closest_normal
