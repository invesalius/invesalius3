"""A surface representation, independent of the algorithm that produced it."""

from dataclasses import dataclass

from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction


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
