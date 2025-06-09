import wx
from invesalius.data import measures
from invesalius.pubsub import pub as Publisher
import invesalius.constants as const
import invesalius.data.measures as measures


class Tag3D:
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

        Publisher.sendMessage(
            "Add measurement point",
            position=point2,
            type=const.LINEAR,
            location=const.SURFACE,
            radius=getattr(const, "PROP_MEASURE", 0.34375),
            label=label
        )
      
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
        point1=(0, 0, 0),
        point2=(0, 0, 0),
        slice_number=131,
        radius=0.34375,
        colour=[1, 0, 0],
        label="test tag 2D",
        location=const.AXIAL
    ):
        # Call LinearMeasure constructor
        representation = measures.CirclePointRepresentation(colour, radius)
        super().__init__(colour=colour, representation=representation)
        #Invert for 2d view
        x1, y1, z1 = point1
        y1=-y1
        x2, y2, z2 = point2
        y2 = -y2
        self.layer = 0
        self.visible = True
        self.children = []

        # Add points using LinearMeasure logic
        self.AddPoint(x1, y1, z1, label=label)
        self.AddPoint(x2,y2,z2, label=label)

        # Set up measurement object for manager
        self.measurement = measures.Measurement()
        self.measurement.type = const.LINEAR
        self.measurement.location = location
        self.measurement.slice_number = slice_number
        self.measurement.points = [(x1,y1,z1), (x2,y2,z2)]
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
            position=(x1, y1, z1),
            type=const.LINEAR,
            location=location,
            slice_number=slice_number,
            radius=radius,
            label=label
        )
        Publisher.sendMessage(
            "Add measurement point",
            position=(x2, y2, z2),
            type=const.LINEAR,
            location=location,
            slice_number=slice_number,
            radius=radius,
            label=label
        )
        if location == const.AXIAL:
            loc_str = "Axial"
        else:
            loc_str = "Coronal"
        
        Publisher.sendMessage(
            ("Update measurement info in GUI",),
            index=self.index,
            name=label,
            colour=colour,
            location=loc_str,
            type_="Linear",
            value=label
        )
        

    # Optionally override SetVisibility to keep self.visible in sync
    def SetVisibility(self, visible):
        self.visible = visible
        super().SetVisibility(visible)


class DensityTag:
    """
    Represents a density tag in the 3D or 2D scene.

    Args:
        x, y, z (float): Coordinates for the center of the density ellipse.
        label (str): The label to display for the tag.
        colour (tuple): RGB tuple for the tag color (default: (0, 255, 0)).
        location (str): The location type (default: const.AXIAL).
        slice_number (int): The slice number (default: 0).
    """
    def __init__(self, x, y, z, label, colour=(0, 255, 0), location=const.AXIAL, slice_number=0):
        self.label = label
        orientation = (
            "AXIAL" if location == const.AXIAL else
            "CORONAL" if location == const.CORONAL else
            "SAGITAL" if location == const.SAGITAL else
            "3D"
        )
        # Create a minimal ellipse (all points at the same location for now)
        density_measure = measures.CircleDensityMeasure(
            orientation=orientation,
            slice_number=slice_number,
            colour=colour,
            # interactive=False
        )
        center = (x, -y, z)
        density_measure.set_center(center)
        # Set p1 to be 10 units along +x, p2 to be 10 units along +y from center
        p1 = (x + 3, -y, z)
        p2 = (x, -y + 3, z)
        density_measure.set_point1(p1)
        density_measure.set_point2(p2)
        # defualt values for density measure
        _min = 0
        _max = 0
        _mean = 0
        _std = 0
        _area = 0
        _perimeter = 0

        # Call the method on your density measure instance
        density_measure.set_density_values(
            _min,
            _max,
            _mean,
            _std,
            _area,
            _perimeter
        )

        # Create and set the measurement object before adding to manager
        dm = measures.DensityMeasurement()
        dm.location = density_measure.location
        dm.slice_number = density_measure.slice_number
        dm.colour = density_measure.colour
        dm.value = density_measure._mean
        dm.area = density_measure._area
        dm.mean = density_measure._mean
        dm.min = density_measure._min
        dm.max = density_measure._max
        dm.std = density_measure._std
        dm.points = [density_measure.center, density_measure.point1, density_measure.point2]
        dm.type = const.DENSITY_ELLIPSE
        density_measure.index = dm.index
        density_measure.set_measurement(dm)

        # Register with MeasurementManager
        mm = measures.MeasurementManager()
        mm.measures.append((dm, density_measure))

        # Register with MeasurementManager via pubsub (optional, but kept for compatibility)
        Publisher.sendMessage(
            "Add density measurement",
            density_measure=density_measure
        )

        self.density_measure = density_measure
        self.index = getattr(density_measure, "index", None)

        Publisher.sendMessage(
            ("Update measurement info in GUI",),
            index=self.index,
            name=label,
            colour=colour,
            location=orientation,
            type_="Density",
            value='99'
        )
    
    def Update(self, raduis_delta):
        """
        Update the density tag's points based on deltas.
        
        Args:
            point1_delta (tuple): Change in coordinates for point1.
            point2_delta (tuple): Change in coordinates for point2.
        """
        p1 = self.density_measure.point1
        p2 = self.density_measure.point2
        new_p1 = (p1[0] + raduis_delta, p1[1], p1[2])
        new_p2 = (p2[0], p2[1] + raduis_delta, p2[2])
        self.density_measure.set_point1(new_p1)
        self.density_measure.set_point2(new_p2)

        self.density_measure._update_gui_info()
    def GetMinMax(self):
        """
        Get the minimum and maximum values of the density tag.
        
        Returns:
            tuple: (min_value, max_value)
        """
        self.density_measure.calc_density()
        return (self.density_measure._min, self.density_measure._max)
    def GetCenter(self):
        """
        Get the center coordinates of the density tag.
        Returns:
            tuple: (x, y, z) coordinates of the center.
        """
        return self.density_measure.center
    def GetPoint1(self):
        """
        Get the first point of the density tag.
        
        Returns:
            tuple: (x, y, z) coordinates of point1.
        """
        return self.density_measure.point1
    def GetPoint2(self):
        """
        Get the second point of the density tag.
        
        Returns:
            tuple: (x, y, z) coordinates of point2.
        """
        return self.density_measure.point2
    
    def UpdateCenter(self, point):
        """
        Update the center coordinates of the density tag.
        
        Args:
            x, y, z (float): New coordinates for the center.
        """
        x,y,z = point
        self.density_measure.set_center((x, y, z))
        self.density_measure._update_gui_info()
    
    def GetActors(self):
        if hasattr(self.density_measure, "ellipse"):
            return [self.density_measure.ellipse]
        return []
    def GetPerimeter(self):
        """
        Get the perimeter of the density tag.
        Returns:
            float: The perimeter of the density tag.
        """
        return self.density_measure.calc_perimeter()
    def GetMean(self):
        """
        Get the mean value of the density tag.
        
        Returns:
            float: The mean value of the density tag.
        """
        self.density_measure.calc_density()
        return self.density_measure._mean
    def SetPoint1(self, point):
        """
        Set the first point of the density tag.
        
        Args:
            point (tuple): New coordinates for point1 as (x, y, z).
        """
        self.density_measure.set_point1(point)
        self.density_measure._update_gui_info()
    def SetPoint2(self, point):
        """
        Set the second point of the density tag.
        Args:
            point (tuple): New coordinates for point2 as (x, y, z).
        """
        self.density_measure.set_point2(point)
        self.density_measure._update_gui_info()

    def SetVisibility(self, visible):
        self.density_measure.SetVisibility(visible)
        