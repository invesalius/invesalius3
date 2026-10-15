import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkColorTransferFunction,
    vtkPolyDataMapper,
)


def CreateColorTransferFunction(color_points, nan_color=None):
    """Create a VTK color transfer function from scalar and RGB pairs."""
    color_function = vtkColorTransferFunction()
    for value, color in color_points:
        color_function.AddRGBPoint(value, *color[:3])

    if nan_color is not None:
        color_function.SetNanColor(*nan_color)

    return color_function


class SurfaceScalarLayer:
    """Represent scalar point data as a colored surface and scalar bar."""

    def __init__(self):
        self.poly_data = None
        self.lookup_table = None

        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor()
        self.actor.SetMapper(self.mapper)

        self.scalar_bar = vtkScalarBarActor()

    def SetInputData(self, poly_data):
        self.poly_data = poly_data
        self.mapper.SetInputData(poly_data)

    def SetPointScalars(self, name, values, point_ids=None, default_value=np.nan):
        """Set point scalars for the whole surface or for selected point IDs."""
        if self.poly_data is None:
            raise RuntimeError("Surface scalar input data has not been set")

        values = np.asarray(values, dtype=float)
        number_of_points = self.poly_data.GetNumberOfPoints()

        if point_ids is None:
            if len(values) != number_of_points:
                raise ValueError(
                    "The number of scalar values must match the number of surface points"
                )
            scalar_values = values
        else:
            point_ids = np.asarray(point_ids, dtype=int)
            if len(values) != len(point_ids):
                raise ValueError("A scalar value is required for each point ID")
            if len(point_ids) and (point_ids.min() < 0 or point_ids.max() >= number_of_points):
                raise ValueError("Point ID is outside the surface point range")

            scalar_values = np.full(number_of_points, default_value, dtype=float)
            scalar_values[point_ids] = values

        scalars = numpy_to_vtk(scalar_values, deep=True)
        scalars.SetName(name)
        self.poly_data.GetPointData().AddArray(scalars)
        self.poly_data.GetPointData().SetActiveScalars(name)
        self.mapper.SetScalarModeToUsePointData()
        self.mapper.ScalarVisibilityOn()
        self.poly_data.Modified()

    def SetLookupTable(self, lookup_table):
        self.lookup_table = lookup_table
        self.mapper.SetLookupTable(lookup_table)
        self.scalar_bar.SetLookupTable(lookup_table)

    def SetScalarRange(self, scalar_range):
        self.mapper.SetScalarRange(*scalar_range)

    def ConfigureScalarBar(
        self,
        title,
        number_of_labels=4,
        label_format="%g",
        position=(0.06, 0.06),
        width=0.1,
        height=0.3,
    ):
        self.scalar_bar.SetTitle(title)
        self.scalar_bar.SetNumberOfLabels(number_of_labels)
        self.scalar_bar.SetLabelFormat(label_format)
        self.scalar_bar.SetWidth(width)
        self.scalar_bar.SetHeight(height)
        self.scalar_bar.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        self.scalar_bar.GetPositionCoordinate().SetValue(*position)

    def GetActor(self):
        return self.actor

    def GetScalarBar(self):
        return self.scalar_bar
