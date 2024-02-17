import vtk
import numpy as np

from invesalius.pubsub import pub as Publisher
import invesalius.data.transformations as tr
import invesalius.data.coordinates as dco

class MarkerTransformator:
    def __init__(self):
        self.__bind_events()
        
        self.surfaces = {}

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor, 'Load surface actor into viewer')

    def LoadActor(self, actor):
        # XXX: Assuming that the first actor is the scalp and the second actor is the brain. This should be made more explicit.
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

    def ProjectToScalp(self, marker):
        # XXX: The markers have y-coordinate inverted, compared to the 3d view. Hence, invert the y-coordinate here.
        marker_position = list(marker.position)
        marker_position[1] = -marker_position[1]

        surface = self.surfaces['scalp']

        polydata = surface['polydata']
        normals = surface['normals']

        # Create a cell locator using VTK. This will allow us to find the closest point on the surface to the marker.
        point_locator = vtk.vtkPointLocator()
        point_locator.SetDataSet(polydata)
        point_locator.BuildLocator()
        closest_point_id = point_locator.FindClosestPoint(marker_position)

        # Retrieve the coordinates of the closest point using the point ID
        closest_point = polydata.GetPoint(closest_point_id)

        # Extract the normal at the closest point
        normal_data = normals.GetPointData().GetNormals()
        closest_normal = normal_data.GetTuple(closest_point_id)

        # The reference direction vector that we want to align the normal to.
        #
        ref_vector = np.array([0, 0, 1])

        # Normal at the closest point
        normal_vector = np.array(closest_normal)

        # Calculate the rotation axis (cross product) and angle (dot product)
        rotation_axis = np.cross(ref_vector, normal_vector)
        rotation_angle = np.arccos(np.dot(ref_vector, normal_vector) / (np.linalg.norm(ref_vector) * np.linalg.norm(normal_vector)))

        # Normalize the rotation axis
        rotation_axis_normalized = rotation_axis / np.linalg.norm(rotation_axis)

        # Create a rotation matrix from the axis and angle
        rotation_matrix = tr.rotation_matrix(rotation_angle, rotation_axis_normalized)

        # Convert the rotation matrix to Euler angles
        euler_angles = tr.euler_from_matrix(rotation_matrix, 'sxyz')
        
        euler_angles = np.degrees(euler_angles)

        A = dco.coordinates_to_transformation_matrix([0,0,0], euler_angles, axes='sxyz')
        print("simot:")
        print(A)
        print(A @ [0,0,1,1])
        print(normal_vector)

        # XXX: Invert back to the get to 'marker space'.
        closest_point = list(closest_point)
        closest_point[1] = -closest_point[1]

        marker.position = closest_point
        marker.orientation = euler_angles

        print(marker.orientation)
        # This has been figured out by testing; from the vectors (1, 0, 0), (0, 1, 0), and (0, 0, 1), the one was selected that
        # made the coil point towards the brain.
