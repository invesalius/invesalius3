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

"""Surface map data and shared presentation for navigation."""

from dataclasses import dataclass

from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import vtkActor, vtkColorTransferFunction, vtkPolyDataMapper


@dataclass
class SurfaceMap:
    polydata: vtkPolyData
    lookup_table: object
    scalar_range: tuple
    name: str
    unit: str
    color_array: str = ""

    def __post_init__(self):
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
                "range": list(lut.GetTableRange()),
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
        return cls(
            polydata,
            lut,
            tuple(metadata["range"]),
            metadata["name"],
            metadata["unit"],
            metadata.get("color_array", ""),
        )


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
