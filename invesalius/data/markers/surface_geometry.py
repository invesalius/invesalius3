import vtk
import numpy as np

from invesalius.utils import Singleton

from invesalius.pubsub import pub as Publisher
import invesalius.data.coordinates as dco


class SurfaceGeometry(metaclass=Singleton):
    def __init__(self):
        self.__bind_events()

        self.surfaces = {}

    def LoadActor(self, actor):
        # XXX: Assuming that the first actor is the scalp and the second actor is the brain. This should be made more explicit by the
        #   publisher of 'Load surface actor into viewer' message. See similar assumption in volume_viewer.py.
        if 'scalp' not in self.surfaces:
            surface_name = 'scalp'
        else:
            surface_name = 'brain'

        # Get the polydata from the actor.
        polydata = actor.GetMapper().GetInput()

        # Compute normals for the surface.
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(polydata)
        normals.ComputePointNormalsOn()
        normals.Update()

        self.surfaces[surface_name] = {
            'actor': actor,
            'polydata': polydata,
            'normals': normals.GetOutput()
        }

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor, 'Load surface actor into viewer')

    def GetClosestPointOnSurface(self, surface_name, point):
        surface = self.surfaces[surface_name]

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
