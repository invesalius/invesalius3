# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

"""Surface map data and shared presentation for live and offline sources."""

from dataclasses import asdict, dataclass, field
from math import isfinite

from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkColorTransferFunction,
    vtkPolyDataMapper,
    vtkTextProperty,
)


@dataclass(frozen=True)
class ColorBar:
    """Appearance and normalized anchor for a surface map legend."""

    position: tuple = (0.06, 0.06)
    compact: bool = True
    title: str = ""

    def __post_init__(self):
        if len(self.position) != 2 or not all(
            isfinite(value) and 0 <= value <= 1 for value in self.position
        ):
            raise ValueError("Color bar position must contain two normalized coordinates.")
        if not isinstance(self.compact, bool) or not isinstance(self.title, str):
            raise ValueError("Invalid color bar appearance.")

    def create_actor(self):
        actor = vtkScalarBarActor()
        actor.SetOrientationToVertical()
        if self.compact:
            actor.SetNumberOfLabels(4)
            actor.SetLabelFormat("%.3g")
            actor.SetTitleRatio(0.1)
            actor.SetMaximumWidthInPixels(70)
            actor.GetTitleTextProperty().SetFontSize(1)
            actor.GetLabelTextProperty().SetFontSize(9)
            actor.SetWidth(0.1)
            actor.SetHeight(0.3)
            actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        else:
            text_property = vtkTextProperty()
            text_property.SetFontSize(3)
            text_property.SetJustificationToCentered()
            actor.SetNumberOfLabels(2)
            actor.SetTitleTextProperty(text_property)
        actor.SetTitle(self.title)
        actor.SetPosition(self.position)
        actor.SetVisibility(True)
        return actor


@dataclass
class SurfaceMap:
    """Map on its own mesh, already aligned to the viewer's coordinates in millimeters."""

    polydata: vtkPolyData
    lookup_table: object
    scalar_range: tuple
    name: str
    unit: str
    color_array: str = ""
    color_bar: ColorBar = field(default_factory=ColorBar)

    def __post_init__(self):
        if not isinstance(self.lookup_table, (vtkLookupTable, vtkColorTransferFunction)):
            raise TypeError("Unsupported surface lookup table.")
        if isinstance(self.lookup_table, vtkColorTransferFunction):
            self.scalar_range = self.lookup_table.GetRange()
        if (
            len(self.scalar_range) != 2
            or not all(isfinite(value) for value in self.scalar_range)
            or self.scalar_range[0] > self.scalar_range[1]
        ):
            raise ValueError("Surface map range must contain two ordered, finite values.")
        point_data = self.polydata.GetPointData()
        values = (
            point_data.GetArray(self.color_array) if self.color_array else point_data.GetScalars()
        )
        components = (3, 4) if self.color_array else (1,)
        if values is not None and (
            values.GetNumberOfTuples() != self.polydata.GetNumberOfPoints()
            or values.GetNumberOfComponents() not in components
        ):
            raise ValueError("Surface map values must match the surface points.")
        if self.color_array and values is None:
            raise ValueError("The surface map color array is missing.")

    def snapshot(self):
        polydata = vtkPolyData()
        polydata.DeepCopy(self.polydata)
        return self.from_metadata(polydata, self.metadata())

    def metadata(self):
        lut = self.lookup_table
        if isinstance(lut, vtkColorTransferFunction):
            colors = []
            for index in range(lut.GetSize()):
                node = [0.0] * 6
                lut.GetNodeValue(index, node)
                colors.append(node)
            table = {"kind": "transfer", "colors": colors}
        elif isinstance(lut, vtkLookupTable):
            table = {
                "kind": "table",
                "colors": [lut.GetTableValue(i) for i in range(lut.GetNumberOfTableValues())],
                "range": list(self.scalar_range),
            }
        else:
            raise TypeError("Unsupported surface lookup table.")
        table["nan_color"] = list(lut.GetNanColor())
        return {
            "name": self.name,
            "unit": self.unit,
            "range": list(self.scalar_range),
            "color_array": self.color_array,
            "lookup_table": table,
            "color_bar": asdict(self.color_bar),
        }

    @classmethod
    def from_metadata(cls, polydata, metadata):
        table = metadata["lookup_table"]
        if table["kind"] == "transfer":
            lut = vtkColorTransferFunction()
            for node in table["colors"]:
                lut.AddRGBPoint(*node)
        elif table["kind"] == "table":
            lut = vtkLookupTable()
            lut.SetNumberOfTableValues(len(table["colors"]))
            lut.SetTableRange(table["range"])
            lut.Build()
            for index, color in enumerate(table["colors"]):
                lut.SetTableValue(index, *color)
        else:
            raise ValueError("Invalid surface lookup table.")
        lut.SetNanColor(*table["nan_color"])
        color_bar = dict(metadata.get("color_bar", {}))
        if "position" in color_bar:
            color_bar["position"] = tuple(color_bar["position"])
        return cls(
            polydata,
            lut,
            tuple(metadata["range"]),
            metadata["name"],
            metadata["unit"],
            metadata.get("color_array", ""),
            ColorBar(**color_bar),
        )


class SurfaceMapVisualizer:
    def __init__(self, color_bar=None):
        self.color_bar = color_bar if color_bar is not None else ColorBar()
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor()
        self.actor.SetMapper(self.mapper)
        self.scalar_bar = self.color_bar.create_actor()
        self.actors = (self.actor, self.scalar_bar)

    def set_map(self, surface_map):
        if isinstance(surface_map.lookup_table, vtkLookupTable):
            surface_map.lookup_table.SetTableRange(surface_map.scalar_range)
        self.mapper.SetInputData(surface_map.polydata)
        self.mapper.SetLookupTable(surface_map.lookup_table)
        self.mapper.SetScalarRange(surface_map.scalar_range)
        self.mapper.UseLookupTableScalarRangeOn()
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
        self.scalar_bar.SetTitle(self.color_bar.title or f"{surface_map.unit}       ")

    def show(self, visible):
        for actor in self.actors:
            actor.SetVisibility(visible)
