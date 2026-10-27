"""Display a map without changing the actor used for anatomical calculations."""

from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper


class SurfaceMapVisualizer:
    def __init__(self):
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor()
        self.actor.SetMapper(self.mapper)
        self.scalar_bar = vtkScalarBarActor()
        self.scalar_bar.SetNumberOfLabels(4)
        self.scalar_bar.SetLabelFormat("%4.0f")
        self.scalar_bar.SetTitleRatio(0.1)
        self.scalar_bar.SetMaximumWidthInPixels(70)
        self.scalar_bar.GetTitleTextProperty().SetFontSize(1)
        self.scalar_bar.GetLabelTextProperty().SetFontSize(9)
        self.scalar_bar.SetWidth(0.1)
        self.scalar_bar.SetHeight(0.3)
        self.scalar_bar.SetVisibility(1)
        self.scalar_bar.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        self.scalar_bar.GetPositionCoordinate().SetValue(0.06, 0.06)
        self.actors = (self.actor, self.scalar_bar)

    def set_map(self, surface_map):
        self.mapper.SetInputData(surface_map.polydata)
        self.mapper.SetLookupTable(surface_map.lookup_table)
        self.mapper.SetScalarRange(surface_map.scalar_range)
        if surface_map.color_array:
            self.mapper.SetScalarModeToUsePointFieldData()
            self.mapper.SelectColorArray(surface_map.color_array)
            self.mapper.SetColorModeToDirectScalars()
        else:
            self.mapper.SetScalarModeToUsePointData()
            self.mapper.SetColorModeToMapScalars()
        self.mapper.SetScalarVisibility(
            bool(
                surface_map.color_array
                or surface_map.polydata.GetPointData().GetScalars() is not None
            )
        )
        self.scalar_bar.SetLookupTable(surface_map.lookup_table)
        self.scalar_bar.SetTitle(f"{surface_map.unit}       ")

    def show(self, visible):
        for actor in self.actors:
            actor.SetVisibility(visible)
