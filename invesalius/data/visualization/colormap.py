import numpy as np
from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction


def CreateColorTransferFunction(color_points, nan_color=None):
    """Create a VTK color transfer function from scalar and RGB pairs."""
    color_function = vtkColorTransferFunction()
    for value, color in color_points:
        color_function.AddRGBPoint(value, *color[:3])

    if nan_color is not None:
        color_function.SetNanColor(*nan_color)

    return color_function


def CreateLookupTable(scalar_range, colors, nan_color=None):
    """Create a VTK lookup table from normalized RGB or RGBA colors."""
    lookup_table = vtkLookupTable()
    lookup_table.SetTableRange(*scalar_range)
    lookup_table.SetNumberOfTableValues(len(colors))
    lookup_table.Build()

    for index, color in enumerate(colors):
        rgba = tuple(color) if len(color) == 4 else (*color, 1.0)
        lookup_table.SetTableValue(index, *rgba)

    if nan_color is not None:
        lookup_table.SetNanColor(*nan_color)

    return lookup_table


def SampleColorFunction(color_function, number_of_colors=10):
    """Return evenly spaced RGBA samples from a normalized color function."""
    return [tuple(color_function(value)) for value in np.linspace(0.0, 1.0, number_of_colors)]


def CreateColorTable(values, color_function, scalar_range):
    """Map scalar values to RGBA colors using a normalized color function."""
    values = np.asarray(values)
    minimum, maximum = scalar_range
    if maximum <= minimum:
        raise ValueError("The colormap scalar range must have a positive width")

    normalized_values = (values - minimum) / (maximum - minimum)
    colors = color_function(normalized_values)
    return {value: tuple(color) for value, color in zip(values, colors)}
