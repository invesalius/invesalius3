from invesalius.data import measures
from invesalius.pubsub import pub as Publisher
import invesalius.constants as const

class Tag:
    def __init__(self, x, y, z, label, colour=(0, 255, 0)):
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR  # Use LINEAR for a single point
        self.measurement.location = const.SURFACE
        self.measurement.slice_number = 0
        # Add two identical points, so it behaves like a measure
        self.measurement.points = [(x, y, z), (x, y, z)]
        self.measurement.name = label
        self.measurement.colour = colour
        self.measurement.value = 0.0

        # Representation: two points for measure-like behavior
        self.representation = measures.CirclePointRepresentation(colour)
        self.point_actor1 = self.representation.GetRepresentation(x, y, z)
        self.point_actor2 = self.representation.GetRepresentation(x, y, z)
        self.point_actors = [self.point_actor1, self.point_actor2]

        # Add to measurements
        mm = measures.MeasurementManager()
        mm.measures.append((self.measurement, self))
        self.index = self.measurement.index

        # Add measurement points (mimic measure tool sequence)
        Publisher.sendMessage(
            "Add measurement point",
            position=(x, y, z),
            type=const.LINEAR,
            location=const.SURFACE,
            radius=const.PROP_MEASURE if hasattr(const, "PROP_MEASURE") else 0.34375,
            label=label
        )
        Publisher.sendMessage(
            "Add actors " + str(self.measurement.location),
            actors=(self.point_actor1,)
        )
        Publisher.sendMessage(
            "Add measurement point",
            position=(x, y, z),
            type=const.LINEAR,
            location=const.SURFACE,
            radius=const.PROP_MEASURE if hasattr(const, "PROP_MEASURE") else 0.34375,
            label=label
        )
        Publisher.sendMessage(
            "Add actors " + str(self.measurement.location),
            actors=(self.point_actor2,)
        )

        # Update GUI with label as the "distance" field (value)
        Publisher.sendMessage(
            "Update measurement info in GUI",
            index=self.index,
            name=label,
            colour=colour,
            location='3D',
            type_="Linear",
            value=label,  # Tag name shown in the value/distance field
        )

    def GetActors(self):
        return self.point_actors

    def SetVisibility(self, visible):
        for actor in self.point_actors:
            actor.SetVisibility(visible)

class Tag2:
    def __init__(self, point1, point2, label, colour=(0, 255, 0)):
        """
        point1, point2: tuples (x, y, z)
        label: string
        colour: RGB tuple
        """
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR
        self.measurement.location = const.SURFACE
        self.measurement.slice_number = 0
        self.measurement.points = [point1, point2]
        self.measurement.name = label
        self.measurement.colour = colour
        self.measurement.value = 0.0

        # Representation for each point
        self.representation = measures.CirclePointRepresentation(colour)
        self.point_actor1 = self.representation.GetRepresentation(*point1)
        self.point_actor2 = self.representation.GetRepresentation(*point2)
        self.point_actors = [self.point_actor1, self.point_actor2]

        # Add to measurements
        mm = measures.MeasurementManager()
        mm.measures.append((self.measurement, self))
        self.index = self.measurement.index

        # Add measurement points (mimic measure tool sequence)
        Publisher.sendMessage(
            "Add measurement point",
            position=point1,
            type=const.LINEAR,
            location=const.SURFACE,
            radius=getattr(const, "PROP_MEASURE", 0.34375),
            label=label
        )
        Publisher.sendMessage(
            "Add actors " + str(self.measurement.location),
            actors=(self.point_actor1,)
        )
        Publisher.sendMessage(
            "Add measurement point",
            position=point2,
            type=const.LINEAR,
            location=const.SURFACE,
            radius=getattr(const, "PROP_MEASURE", 0.34375),
            label=label
        )
        Publisher.sendMessage(
            "Add actors " + str(self.measurement.location),
            actors=(self.point_actor2,)
        )

        # Update GUI with label as the "distance" field (value)
        Publisher.sendMessage(
            "Update measurement info in GUI",
            index=self.index,
            name=label,
            colour=colour,
            location='3D',
            type_="Linear",
            value=label,
        )

    def GetActors(self):
        return self.point_actors

    def SetVisibility(self, visible):
        for actor in self.point_actors:
            actor.SetVisibility(visible)