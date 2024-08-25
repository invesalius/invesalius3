import vtk

from invesalius.gui import dialogs
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class SurfaceGeometry(metaclass=Singleton):
    def __init__(self):
        self.__bind_events()

        self.surfaces = []

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor, "Load surface actor into viewer")

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

    def SmoothSurface(self, actor):
        mapper = actor.GetMapper()
        polydata = mapper.GetInput()

        # Create the smoothing filter.
        smoother = vtk.vtkSmoothPolyDataFilter()
        smoother.SetInputData(polydata)
        # TODO: Having many iterations is slow and should be probably computed
        #   only once and then stored on the disk - not re-computed every time InVesalius
        #   is started. Setting the number of iterations, e.g., to a relatively small value such
        #   as 100 does not seem to provide that good results.
        #
        # TODO: The smoothing filter is effectively disabled for now by setting the number of iterations
        #   to 0, as it does not seem to work consistently with all surfaces. Investigate more on how
        #   this should be used. An initial value that seemed to work with some, but not all surfaces
        #   was 400.
        smoother.SetNumberOfIterations(0)
        smoother.SetRelaxationFactor(0.9)
        smoother.FeatureEdgeSmoothingOff()
        smoother.BoundarySmoothingOn()
        smoother.Update()

        # Create a new mapper for the smoothed data.
        smoothed_mapper = vtk.vtkPolyDataMapper()
        smoothed_mapper.SetInputData(smoother.GetOutput())

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
        highest_z = max([points.GetPoint(i)[2] for i in range(points.GetNumberOfPoints())])

        return highest_z

    def GetSmoothedScalpSurface(self):
        # Retrieve the surface with the highest z-coordinate.
        if not self.surfaces:
            return None

        # Find the (non-smoothed) surface with the highest z-coordinate, corresponding to the scalp.
        highest_surface = max(self.surfaces, key=lambda surface: surface["original"]["highest_z"])

        # Compute smoothed surface if it has not been computed yet.
        if highest_surface["smoothed"] is None:
            progress_window = dialogs.SurfaceSmoothingProgressWindow()

            actor = highest_surface["original"]["actor"]

            # Create a smoothed version of the actor.
            smoothed_actor = self.SmoothSurface(actor)

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
