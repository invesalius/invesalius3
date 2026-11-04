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

"""Offline cortical source maps using the existing surface painting lifecycle."""

import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction

from invesalius.data.time_series import Playback
from invesalius.data.visualization.surface_map_visualizer import ColorBar, SurfaceMap
from invesalius.data.visualization.surface_painting import SurfacePainting
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher
from invesalius.reader.source_reconstruction import read_source_config


class SourceReconstructionMode:
    name = "Source reconstruction"
    requires_navigation = True

    def __init__(self, surface_manager):
        self.surface_manager = surface_manager
        self.painting = SurfacePainting()
        self.series = None
        self.surface = None
        self.surface_map = None
        self.playback = None
        self.token = None
        self.frame_index = None
        self.available = False
        self.painting.register(self)
        Publisher.subscribe(self.load, "Load source reconstruction")
        Publisher.subscribe(self.set_frame, "Set source reconstruction frame")
        Publisher.subscribe(self.discard_surface, "Discard surface painting")

    def load(self, filename):
        """Prepare the entire candidate before replacing the current source map."""
        if not self.painting.navigation_mode:
            raise ValueError("Switch to navigation mode before loading a source reconstruction.")
        series = read_source_config(filename)
        surface_map = self._create_map(series)
        manager = self.surface_manager
        convert_to_inv = manager.convert_to_inv
        try:
            # The source map has already been converted to viewer coordinates.
            manager.convert_to_inv = False
            surface_index = manager.CreateSurfaceFromPolydata(
                surface_map.polydata, name=series.name, category=self.name, colour=(0.8, 0.8, 0.8)
            )
        finally:
            manager.convert_to_inv = convert_to_inv
        surface = Project().surface_dict[surface_index]
        previous = self.series, self.surface, self.surface_map, self.playback
        was_active = self.token is not None
        self.painting.reset(self)
        self.series, self.surface, self.surface_map = series, surface, surface_map
        self.playback = Playback(series.axis)
        self.frame_index = None
        try:
            self.painting.set_available(self, True)
            if not self.painting.select(surface, self.name):
                raise RuntimeError("The imported source surface cannot display source maps.")
        except Exception:
            self.painting.reset(self)
            self.series, self.surface, self.surface_map, self.playback = previous
            self.frame_index = None
            self.painting.set_available(self, self.series is not None)
            try:
                if was_active:
                    self.painting.select(self.surface, self.name)
            finally:
                Publisher.sendMessage("Remove surfaces", surface_indexes=[surface.index])
            raise
        old_surface = previous[1]
        if old_surface is not None and old_surface in Project().surface_dict.values():
            Publisher.sendMessage("Remove surfaces", surface_indexes=[old_surface.index])
        Publisher.sendMessage("Repopulate surfaces")

    def _create_map(self, series):
        from invesalius.data.slice_ import Slice

        slic = Slice()
        affine = np.asarray(slic.affine)
        if (
            slic.matrix is None
            or affine.shape != (4, 4)
            or not np.isfinite(affine).all()
            or np.linalg.matrix_rank(affine) != 4
        ):
            raise ValueError("The project must have valid anatomical world coordinates.")
        points = vtkPoints()
        points.SetData(numpy_to_vtk(series.points, deep=True))
        connectivity = np.column_stack(
            [np.full(len(series.triangles), 3, dtype=np.int64), series.triangles]
        ).ravel()
        cells = vtkCellArray()
        cells.SetCells(len(series.triangles), numpy_to_vtkIdTypeArray(connectivity, deep=True))
        polydata = vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetPolys(cells)
        polydata = self.surface_manager.ConvertPolydataToInv(polydata)
        normals = vtkPolyDataNormals()
        normals.SetInputData(polydata)
        # Splitting duplicates vertices and would break STC's original vertex IDs.
        normals.SplittingOff()
        normals.AutoOrientNormalsOn()
        normals.Update()
        polydata = normals.GetOutput()
        if polydata.GetNumberOfPoints() != len(series.points):
            raise ValueError("Source visualization must preserve the cortical vertex IDs.")
        coordinates = vtk_to_numpy(polydata.GetPoints().GetData())
        if not np.isfinite(coordinates).all():
            raise ValueError("Source geometry cannot be represented in project coordinates.")
        values = np.full(polydata.GetNumberOfPoints(), np.nan, dtype=np.float32)
        polydata.GetPointData().SetScalars(numpy_to_vtk(values, deep=True))
        limit = max(abs(value) for value in series.scalar_range) or 1.0
        lut = vtkColorTransferFunction()
        lut.AddRGBPoint(-limit, 0.15, 0.3, 0.85)
        lut.AddRGBPoint(0, 0.85, 0.85, 0.85)
        lut.AddRGBPoint(limit, 0.85, 0.15, 0.1)
        lut.SetNanColor(0.65, 0.65, 0.65)
        return SurfaceMap(
            polydata,
            lut,
            (-limit, limit),
            series.name,
            series.unit,
            color_bar=ColorBar(title=series.unit),
        )

    def supports_surface(self, surface):
        return surface is self.surface

    def default_surface(self):
        return self.surface

    def start(self, surface, token):
        self.token = token
        self._show_frame()

    def stop(self):
        if self.playback is not None:
            self.playback.pause()
        self.token = None

    def set_frame(self, frame_index):
        if self.playback is None:
            raise RuntimeError("Load a source reconstruction before selecting a frame.")
        self.playback.seek(frame_index)
        if self.token is not None:
            self._show_frame()

    def tick(self):
        """Called on the GUI thread by the future player's timer."""
        if self.token is None:
            return None
        frame_index = self.playback.tick()
        if frame_index != self.frame_index:
            self._show_frame()
        return frame_index

    def _show_frame(self):
        frame = self.series.read_frame(self.playback.index)
        scalars = self.surface_map.polydata.GetPointData().GetScalars()
        values = vtk_to_numpy(scalars)
        mapped = self.series.vertex_sources >= 0
        values.fill(np.nan)
        values[mapped] = frame[self.series.vertex_sources[mapped]]
        scalars.Modified()
        self.frame_index = self.playback.index
        self.painting.update(self.name, self.token, self.surface_map)

    def discard_surface(self, surface):
        if surface is self.surface:
            self.clear()

    def clear(self):
        self.painting.reset(self)
        self.series = None
        self.surface = None
        self.surface_map = None
        self.playback = None
        self.frame_index = None
