import vtk
import numpy as np

from invesalius.utils import Singleton

from invesalius.pubsub import pub as Publisher
import invesalius.data.coordinates as dco


class SurfaceGeometry(metaclass=Singleton):
    def __init__(self):
        self.__bind_events()

        self.surfaces = []

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

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor, 'Load surface actor into viewer')

    def GetSurfaceNormals(self, actor):
        # Get the polydata from the actor.
        polydata = actor.GetMapper().GetInput()

        # Compute normals for the surface.
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(polydata)
        normals.ComputePointNormalsOn()
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

    def GetClosestPointOnScalp(self, point):
        print("pointti:")
        print(point)
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

        print("closest_point")
        print(closest_point)
        return closest_point, closest_normal
