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

from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from invesalius.data.surface_scalar_map import SurfaceScalarMap


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
