import vtk
import numpy as np

from invesalius.utils import Singleton

from invesalius.pubsub import pub as Publisher
import invesalius.data.coordinates as dco


class SurfaceGeometry(metaclass=Singleton):
    def __init__(self):
        self.__bind_events()

        self.surfaces = []

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor, 'Load surface actor into viewer')

    def LoadActor(self, actor):
        normals = self.GetSurfaceNormals(actor)
        highest_z = self.CalculateHighestZ(actor)

        # Get the polydata from the actor.
        polydata = actor.GetMapper().GetInput()

        self.surfaces.append({
            'actor': actor,
            'polydata': polydata,
            'normals': normals,
            'highest_z': highest_z,
        })

    def HideAllSurfaces(self):
        """
        Forcibly hide all surfaces in the viewer, overriding the user-set visibility state of each surface.
        This is useful, e.g., when we want to pick a marker without any of the surfaces getting in the way.
        """
        for surface in self.surfaces:
            surface['visible'] = surface['actor'].GetVisibility() 
            surface['actor'].VisibilityOff()

    def ShowAllSurfaces(self):
        """
        Show all surfaces in the viewer, restoring the visibility state of each surface to what it was before
        HideAllSurfaces was called.
        """
        for surface in self.surfaces:
            visible = surface['visible'] if 'visible' in surface else True
            surface['actor'].SetVisibility(visible)

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

    def GetScalpSurface(self):
        # Retrieve the surface with the highest z-coordinate.
        if not self.surfaces:
            return None

        return max(self.surfaces, key=lambda surface: surface['highest_z'])

    def GetClosestPointOnSurface(self, surface_name, point):
        surface = self.GetScalpSurface()

        polydata = surface['polydata']
        normals = surface['normals']

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
