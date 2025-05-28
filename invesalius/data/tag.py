import wx
from invesalius.data import measures
from invesalius.pubsub import pub as Publisher
import invesalius.constants as const
import invesalius.data.measures as measures

class Tag:
    """
    Represents a single-point tag (marker) in the 3D scene.

    This class creates a measurement at a given (x, y, z) position, 
    with a label and color. It manages the VTK actors for visualization,
    registers the measurement with the MeasurementManager, and sends 
    pubsub messages to update the GUI and scene.

    Args:
        x (float): X coordinate of the tag.
        y (float): Y coordinate of the tag.
        z (float): Z coordinate of the tag.
        label (str): The label to display for the tag.
        colour (tuple): RGB tuple for the tag color (default: (0, 255, 0)).
    """
    def __init__(self, x, y, z, label, colour=(0, 255, 0)):
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR  
        self.measurement.location = const.SURFACE
        self.measurement.slice_number = 0
        
        self.measurement.points = [(x, y, z), (x, y, z)]
        self.measurement.name = label
        self.measurement.colour = colour
        self.measurement.value = 0.0

        
        self.representation = measures.CirclePointRepresentation(colour)
        self.point_actor1 = self.representation.GetRepresentation(x, y, z)
        self.point_actor2 = self.representation.GetRepresentation(x, y, z)
        self.point_actors = [self.point_actor1, self.point_actor2]

        
        mm = measures.MeasurementManager()
        mm.measures.append((self.measurement, self))
        self.index = self.measurement.index

        
        Publisher.sendMessage(
            "Add measurement point",
            position=(x, y, z),
            type=const.LINEAR,
            location=const.SURFACE,
            radius=const.PROP_MEASURE if hasattr(const, "PROP_MEASURE") else 0.34375,
            label=label
        )
        # Publisher.sendMessage(
        #     "Add actors " + str(self.measurement.location),
        #     actors=(self.point_actor1,)
        # )
        Publisher.sendMessage(
            "Add measurement point",
            position=(x, y, z),
            type=const.LINEAR,
            location=const.SURFACE,
            radius=const.PROP_MEASURE if hasattr(const, "PROP_MEASURE") else 0.34375,
            label=label
        )
        # Publisher.sendMessage(
        #     "Add actors " + str(self.measurement.location),
        #     actors=(self.point_actor2,)
        # )

        
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

class Tag2:
    """
    Represents a two-point tag (e.g., for stenosis or distance) in the 3D scene.

    This class creates a measurement between two points, with a label and color.
    It manages the VTK actors for both points, registers the measurement with 
    the MeasurementManager, and sends pubsub messages to update the GUI and scene.

    Args:
        point1 (tuple): First point as (x, y, z).
        point2 (tuple): Second point as (x, y, z).
        label (str): The label to display for the tag.
        colour (tuple): RGB tuple for the tag color (default: (0, 255, 0)).
    """
    def __init__(self, point1, point2, label, colour=(0, 255, 0)):
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR
        self.measurement.location = const.SURFACE
        self.measurement.slice_number = 0
        self.measurement.points = [point1, point2]
        self.measurement.name = label
        self.measurement.colour = colour
        self.measurement.value = 0.0

        
        self.representation = measures.CirclePointRepresentation(colour)
        self.point_actor1 = self.representation.GetRepresentation(*point1)
        self.point_actor2 = self.representation.GetRepresentation(*point2)
        self.point_actors = [self.point_actor1, self.point_actor2]

        
        mm = measures.MeasurementManager()
        mm.measures.append((self.measurement, self))
        self.index = self.measurement.index

        
        Publisher.sendMessage(
            "Add measurement point",
            position=point1,
            type=const.LINEAR,
            location=const.SURFACE,
            radius=getattr(const, "PROP_MEASURE", 0.34375),
            label=label
        )
        # Publisher.sendMessage(
        #     "Add actors " + str(self.measurement.location),
        #     actors=(self.point_actor1,)
        # )
        Publisher.sendMessage(
            "Add measurement point",
            position=point2,
            type=const.LINEAR,
            location=const.SURFACE,
            radius=getattr(const, "PROP_MEASURE", 0.34375),
            label=label
        )
        # Publisher.sendMessage(
        #     "Add actors " + str(self.measurement.location),
        #     actors=(self.point_actor2,)
        # )

        
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

class Tag2D(measures.LinearMeasure):
    """
    A 2D linear measurement/tag for the Axial slice, compatible with MeasurementManager.
    """

    def __init__(
        self,
        point1=(94.21822494971511, 104.45962712095515, 65.5),
        point2=(94.21822494971511, 104.45962712095515, 65.5),
        slice_number=131,
        radius=0.34375,
        colour=[1, 0, 0],
        label=None
    ):
        # Call LinearMeasure constructor
        representation = measures.CirclePointRepresentation(colour, radius)
        super().__init__(colour=colour, representation=representation)

        self.layer = 0
        self.visible = True
        self.children = []

        # Add points using LinearMeasure logic
        self.AddPoint(*point1, label=label)
        self.AddPoint(*point2, label=label)

        # Set up measurement object for manager
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR
        self.measurement.location = const.AXIAL
        self.measurement.slice_number = slice_number
        self.measurement.points = [point1, point2]
        self.measurement.name = label
        self.measurement.colour = colour
        self.measurement.value = self.GetValue()
        self.measurement.visible = True

        # Add to MeasurementManager
        mm = measures.MeasurementManager()
        mm.measures.append((self.measurement, self))
        self.index = self.measurement.index

        # PubSub messages (optional, as before)
        Publisher.sendMessage(
            "Add measurement point",
            position=point1,
            type=const.LINEAR,
            location=const.AXIAL,
            slice_number=slice_number,
            radius=radius,
            label=label
        )
        Publisher.sendMessage(
            "Add measurement point",
            position=point2,
            type=const.LINEAR,
            location=const.AXIAL,
            slice_number=slice_number,
            radius=radius,
            label=label
        )
        Publisher.sendMessage(
            ("Update measurement info in GUI",),
            index=self.index,
            name=label,
            colour=colour,
            location="Axial",
            type_="Linear",
            value=f"{self.GetValue():.3f} mm"
        )

    # Optionally override SetVisibility to keep self.visible in sync
    def SetVisibility(self, visible):
        self.visible = visible
        super().SetVisibility(visible)




