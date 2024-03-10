import vtk

import invesalius.data.coordinates as dco
import invesalius.constants as const
import invesalius.data.vtk_utils as vtku
import invesalius.data.polydata_utils as pu

from invesalius.pubsub import pub as Publisher
import invesalius.session as ses


class VectorFieldVisualizer:
    """
    A class for visualizing vector fields relative to, e.g., the coil or markers in the volume viewer.
    """
    def __init__(self, actor_factory):
        # The actor factory is used to create the actors for representing the vectors (= arrows).
        self.actor_factory = actor_factory

        # An example vector field.
        self.current_vector_field = (
            {'position': (0, 0, 0), 'orientation': (90, 0, 0)},
            {'position': (0, 0, -10), 'orientation': (0, 90, 0)},
            {'position': (0, 0, -20), 'orientation': (0, 0, 90)},
        )

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetVectorField, 'Set vector field')

    def SetVectorField(self, vector_field):
        """
        Store the vector field to be visualized.
        """
        self.current_vector_field = vector_field

    def CreateVectorFieldAssembly(self):
        """
        Create an assembly for the current vector field.
        """
        assembly = vtk.vtkAssembly()

        actors = [self.actor_factory.CreateArrowUsingDirection(
            position=vector['position'],
            orientation=vector['orientation'],
        ) for vector in self.current_vector_field]

        for actor in actors:
            assembly.AddPart(actor)

        return assembly
