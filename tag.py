from invesalius.data import measures
from invesalius.pubsub import pub as Publisher
import invesalius.constants as const

class Tag:
    def __init__(self, x, y, z, label, colour=(0, 255, 0)):
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR  # Use LINEAR for a single point
        self.measurement.location = const.SURFACE
        self.measurement.slice_number = 0
        self.measurement.points = [(x, y, z)]
        self.measurement.name = label
        self.measurement.colour = colour
        self.measurement.value = 0.0

        # Representation: just a point, no line
        self.representation = measures.CirclePointRepresentation(colour)
        self.point_actor = self.representation.GetRepresentation(x, y, z)

        # Add to measurements
        mm = measures.MeasurementManager()
        mm.measures.append((self.measurement, self))
        self.index = self.measurement.index

        # Add actor to 3D view
        Publisher.sendMessage("Add actors " + str(self.measurement.location), actors=(self.point_actor,))

        # Update GUI with label
        Publisher.sendMessage(
            "Update measurement info in GUI",
            index=self.index,
            name=label,
            colour=colour,
            location=measures.LOCATION[self.measurement.location],
            type_="Tag",
            value="",
        )

    def GetActors(self):
        return [self.point_actor]

    def SetVisibility(self, visible):
        self.point_actor.SetVisibility(visible)