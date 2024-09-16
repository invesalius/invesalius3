import vtk

from invesalius.pubsub import pub as Publisher


class VectorFieldVisualizer:
    """
    A class for visualizing vector fields relative to, e.g., the coil or markers in the volume viewer.
    """

    def __init__(self, actor_factory):
        # The actor factory is used to create the actors for representing the vectors (= arrows).
        self.actor_factory = actor_factory

        # An empty vector field to begin with.
        self.vector_field = ()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetVectorField, "Set vector field")

    def SetVectorField(self, vector_field):
        """
        Store the vector field to be visualized.
        """
        self.vector_field = vector_field
        Publisher.sendMessage("Update vector field")

    def CreateVectorFieldAssembly(self):
        """
        Create an assembly for the current vector field.
        """
        assembly = vtk.vtkAssembly()

        actors = [
            self.actor_factory.CreateArrowUsingDirection(
                position=vector["position"],
                orientation=vector["orientation"],
                colour=vector["color"],
                length_multiplier=vector["length"],
            )
            for vector in self.vector_field
        ]

        for actor in actors:
            assembly.AddPart(actor)

        return assembly
