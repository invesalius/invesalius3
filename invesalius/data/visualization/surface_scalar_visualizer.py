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
"""Render scalar surface maps independently of their data source."""

from dataclasses import dataclass

from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import vtkActor, vtkColorTransferFunction, vtkPolyDataMapper


@dataclass
class SurfaceScalarMap:
    polydata: vtkPolyData
    name: str
    unit: str
    color_array: str | None = None

    def __post_init__(self):
        scalars = self.polydata.GetPointData().GetScalars()
        if scalars is not None and (
            scalars.GetNumberOfComponents() != 1
            or scalars.GetNumberOfTuples() != self.polydata.GetNumberOfPoints()
        ):
            raise ValueError("A scalar value is required for each surface point.")
        if self.color_array is not None:
            colors = self.polydata.GetPointData().GetArray(self.color_array)
            if (
                colors is None
                or colors.GetNumberOfComponents() not in (3, 4)
                or colors.GetNumberOfTuples() != self.polydata.GetNumberOfPoints()
            ):
                raise ValueError("A display color is required for each surface point.")


def GetLookupTableState(lookup_table):
    if isinstance(lookup_table, vtkColorTransferFunction):
        nodes = []
        for index in range(lookup_table.GetSize()):
            node = [0.0] * 6
            lookup_table.GetNodeValue(index, node)
            nodes.append(node)
        return {"kind": "transfer", "colors": nodes, "nan_color": lookup_table.GetNanColor()}
    if isinstance(lookup_table, vtkLookupTable):
        return {
            "kind": "table",
            "colors": [
                lookup_table.GetTableValue(i) for i in range(lookup_table.GetNumberOfTableValues())
            ],
            "range": lookup_table.GetTableRange(),
            "nan_color": lookup_table.GetNanColor(),
        }
    raise TypeError("Unsupported surface lookup table.")


def CreateLookupTable(state):
    if state["kind"] == "transfer":
        lookup_table = vtkColorTransferFunction()
        for node in state["colors"]:
            lookup_table.AddRGBPoint(*node)
    elif state["kind"] == "table":
        lookup_table = vtkLookupTable()
        lookup_table.SetNumberOfTableValues(len(state["colors"]))
        lookup_table.SetTableRange(state["range"])
        lookup_table.Build()
        for index, color in enumerate(state["colors"]):
            lookup_table.SetTableValue(index, *color)
    else:
        raise ValueError("Invalid surface lookup table.")
    lookup_table.SetNanColor(*state["nan_color"])
    return lookup_table


class SurfaceScalarVisualizer:
    def __init__(self):
        self.mapper = vtkPolyDataMapper()
        self.mapper.SetScalarModeToUsePointData()
        self.mapper.SetColorModeToMapScalars()

        self.actor = vtkActor()
        self.actor.SetMapper(self.mapper)
        self.actor.GetProperty().SetInterpolationToGouraud()

        self.scalar_bar = vtkScalarBarActor()
        self.scalar_bar.SetNumberOfLabels(4)
        self.scalar_bar.SetLabelFormat("%4.0f")
        self.scalar_bar.SetTitleRatio(0.1)
        self.scalar_bar.SetMaximumWidthInPixels(70)
        self.scalar_bar.GetTitleTextProperty().SetFontSize(1)
        self.scalar_bar.GetLabelTextProperty().SetFontSize(9)
        self.scalar_bar.SetWidth(0.1)
        self.scalar_bar.SetHeight(0.3)
        self.scalar_bar.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        self.scalar_bar.GetPositionCoordinate().SetValue(0.06, 0.06)
        self.actors = (self.actor, self.scalar_bar)

    def SetMap(self, surface_map: SurfaceScalarMap, lookup_table, scalar_range):
        normals = vtkPolyDataNormals()
        normals.SetInputData(surface_map.polydata)
        normals.ComputePointNormalsOff()
        normals.ComputeCellNormalsOff()
        normals.Update()

        self.mapper.SetInputData(normals.GetOutput())
        self.mapper.SetScalarRange(scalar_range)
        self.mapper.SetLookupTable(lookup_table)
        if surface_map.color_array is None:
            self.mapper.SetScalarModeToUsePointData()
            self.mapper.SetColorModeToMapScalars()
        else:
            self.mapper.SetScalarModeToUsePointFieldData()
            self.mapper.SelectColorArray(surface_map.color_array)
            self.mapper.SetColorModeToDirectScalars()
        self.mapper.SetScalarVisibility(
            surface_map.polydata.GetPointData().GetScalars() is not None
        )
        self.scalar_bar.SetLookupTable(lookup_table)
        self.scalar_bar.SetTitle(f"{surface_map.unit}       ")

    def Clear(self):
        self.mapper.RemoveAllInputs()
        self.mapper.SetLookupTable(None)
        self.scalar_bar.SetLookupTable(None)
        self.scalar_bar.SetTitle("")
