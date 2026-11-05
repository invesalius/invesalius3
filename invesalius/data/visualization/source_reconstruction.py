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

from dataclasses import replace

import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData, vtkStaticPointLocator
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction

import invesalius.constants as const
from invesalius.data.eeg import read_source_config, read_source_reconstruction
from invesalius.data.time_series import Playback
from invesalius.data.visualization.surface_map_visualizer import ColorBar, SurfaceMap
from invesalius.data.visualization.surface_painting import SurfacePainting
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class SourceReconstructionMode:
    name = "EEG/MEG"
    requires_navigation = True

    def __init__(self, surface_manager):
        self.surface_manager = surface_manager
        self.painting = SurfacePainting()
        self.series = None
        self.surface_map = None
        self.playback = None
        self.token = None
        self.frame_index = None
        self.selected_source = None
        self.source_values = None
        self.representation = "pial"
        self.hemispheres_visible = (True, True)
        self._representation_maps = {}
        self._cross_position = None
        self._source_locator = None
        self._cross_enabled = False
        self.available = False
        self.painting.register(self)
        Publisher.subscribe(self.load, "Load source reconstruction")
        Publisher.subscribe(self.set_frame, "Set source reconstruction frame")
        Publisher.subscribe(self.set_display, "Set source reconstruction display")
        Publisher.subscribe(self.brain_changed, "Brain surface changed")
        Publisher.subscribe(self.select_cross_source, "Set cross focal point")
        Publisher.subscribe(self.cross_tool_changed, "Toggle toolbar item")

    def load(self, filename=None, config=None):
        """Prepare the entire candidate before replacing the current source map."""
        if not self.painting.navigation_mode:
            raise ValueError("Switch to navigation mode before loading a source reconstruction.")
        if (filename is None) == (config is None):
            raise ValueError("Provide a source configuration file or import settings.")
        series = (
            read_source_config(filename) if config is None else read_source_reconstruction(config)
        )
        surface_map = self._create_map(series)
        surface = Project().GetBrainSurface()
        if surface is not None and not surface.supports_painting:
            raise ValueError("The designated brain surface cannot display source maps.")
        created_surface = None
        if surface is None:
            manager = self.surface_manager
            convert_to_inv = manager.convert_to_inv
            try:
                # The source map has already been converted to viewer coordinates.
                manager.convert_to_inv = False
                surface_index = manager.CreateSurfaceFromPolydata(
                    surface_map.polydata,
                    name="Brain",
                    colour=(0.8, 0.8, 0.8),
                    anatomical_role="brain",
                )
            finally:
                manager.convert_to_inv = convert_to_inv
            surface = created_surface = Project().surface_dict[surface_index]
        previous = (
            self.series,
            self.surface_map,
            self.playback,
            self.selected_source,
            self.source_values,
            self.representation,
            self.hemispheres_visible,
            self._representation_maps,
            self._cross_position,
        )
        previous_mode = surface.painting_mode
        self.painting.reset(self)
        self.series, self.surface_map = series, surface_map
        self.representation = "pial"
        self.hemispheres_visible = (True, True)
        self._representation_maps = {"pial": surface_map}
        self._cross_position = None
        self.playback = Playback(series.axis)
        self.selected_source = self.source_values = None
        self._source_locator = None
        self.frame_index = None
        try:
            self.painting.set_available(self, True)
            if not self.painting.select(surface, self.name):
                raise RuntimeError("The imported source surface cannot display source maps.")
        except Exception:
            self.painting.reset(self)
            (
                self.series,
                self.surface_map,
                self.playback,
                self.selected_source,
                self.source_values,
                self.representation,
                self.hemispheres_visible,
                self._representation_maps,
                self._cross_position,
            ) = previous
            self.frame_index = None
            self.painting.set_available(self, self.series is not None)
            try:
                if previous_mode:
                    self.painting.select(surface, previous_mode)
            finally:
                if created_surface is not None:
                    Publisher.sendMessage(
                        "Remove surfaces", surface_indexes=[created_surface.index]
                    )
            Publisher.sendMessage("Source reconstruction changed", mode=self)
            raise
        if created_surface is not None:
            Publisher.sendMessage("Repopulate surfaces")

    def _create_map(self, series, surface_points=None):
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
        points.SetData(
            numpy_to_vtk(series.points if surface_points is None else surface_points, deep=True)
        )
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
        minimum, maximum = series.scalar_range
        limit = max(abs(minimum), abs(maximum)) or 1.0
        if minimum >= 0:
            scalar_range = (0.0, limit)
        elif maximum <= 0:
            scalar_range = (-limit, 0.0)
        else:
            scalar_range = (-limit, limit)
        lut = vtkColorTransferFunction()
        if scalar_range[0] < 0:
            lut.AddRGBPoint(-limit, 0.15, 0.3, 0.85)
        lut.AddRGBPoint(0, 0.85, 0.85, 0.85)
        if scalar_range[1] > 0:
            lut.AddRGBPoint(limit, 0.85, 0.15, 0.1)
        lut.SetNanColor(0.65, 0.65, 0.65)
        return SurfaceMap(
            polydata,
            lut,
            scalar_range,
            series.name,
            series.unit,
            color_bar=ColorBar(position=(0.82, 0.1), compact=False, title=series.unit),
        )

    def supports_surface(self, surface):
        return surface is Project().GetBrainSurface()

    def default_surface(self):
        surface = Project().GetBrainSurface()
        return surface if surface is not None and surface.supports_painting else None

    @property
    def display_active(self):
        surface = self.painting.targets.get(self.name)
        return (
            self.token is not None
            and surface is Project().GetBrainSurface()
            and surface is not None
            and surface.painting_mode == self.name
        )

    def set_display(self, representation, left, right):
        if self.series is None or not self.display_active:
            raise ValueError("Select the EEG/MEG color map on Brain before changing its display.")
        visible = (left, right)
        if representation == self.representation and visible == self.hemispheres_visible:
            return
        candidate = self._representation_maps.get(representation)
        if candidate is None:
            candidate = self._create_map(
                self.series, self.series.read_surface_points(representation)
            )
        triangles = vtk_to_numpy(candidate.polydata.GetPolys().GetConnectivityArray()).reshape(
            -1, 3
        )
        left_faces = triangles[:, 0] < self.series.hemisphere_sizes[0]
        triangles = triangles[(left_faces & left) | (~left_faces & right)]
        connectivity = np.column_stack(
            [np.full(len(triangles), 3, dtype=np.int64), triangles]
        ).ravel()
        cells = vtkCellArray()
        cells.SetCells(len(triangles), numpy_to_vtkIdTypeArray(connectivity, deep=True))
        # Keep every point ID: hiding a hemisphere only removes its displayed triangles.
        polydata = vtkPolyData()
        polydata.ShallowCopy(candidate.polydata)
        polydata.SetPolys(cells)
        display = replace(candidate, polydata=polydata)
        previous = (
            self.surface_map,
            self.representation,
            self.hemispheres_visible,
            self.selected_source,
            self.source_values,
        )
        self._representation_maps[representation] = candidate
        self.surface_map = display
        self.representation = representation
        self.hemispheres_visible = visible
        try:
            if self._cross_position is not None:
                self.select_cross_source(self._cross_position)
            self._show_frame()
        except Exception:
            (
                self.surface_map,
                self.representation,
                self.hemispheres_visible,
                self.selected_source,
                self.source_values,
            ) = previous
            self.painting.update(self.name, self.token, self.surface_map)
            Publisher.sendMessage("Source reconstruction changed", mode=self)
            raise

    def brain_changed(self, previous, surface):
        target = self.painting.targets.get(self.name)
        if target is not None and target is not surface:
            self.painting.stop(self.name)
            self.painting.targets.pop(self.name, None)

    def start(self, surface, token):
        self.token = token
        self._show_frame()

    def stop(self):
        if self.playback is not None:
            self.playback.pause()
        self.token = None
        Publisher.sendMessage("Source reconstruction changed", mode=self)

    def set_frame(self, frame_index):
        if self.playback is None:
            raise RuntimeError("Load a source reconstruction before selecting a frame.")
        self.playback.seek(frame_index)
        if self.token is not None:
            self._show_frame()

    @property
    def source_label(self):
        if self.selected_source is None:
            return ""
        source_index = self.selected_source
        for side, stc in zip(("LH", "RH"), self.series.hemispheres):
            if source_index < len(stc.vertices):
                return f"{side} {int(stc.vertices[source_index])}"
            source_index -= len(stc.vertices)

    def cross_tool_changed(self, _id, value):
        if _id != const.SLICE_STATE_CROSS:
            return
        self._cross_enabled = bool(value)
        if not self._cross_enabled and self.selected_source is not None:
            self.selected_source = self.source_values = None
            Publisher.sendMessage("Source reconstruction changed", mode=self)

    def select_cross_source(self, position):
        if not self._cross_enabled or self.series is None or self.surface_map is None:
            return
        try:
            point = np.asarray(position[:3], dtype=float)
        except (TypeError, ValueError):
            return
        if point.shape != (3,) or not np.isfinite(point).all():
            return
        self._cross_position = point.copy()
        # Cross coordinates use the slice convention; the source mesh uses the 3D convention.
        point = point * [1, -1, 1]
        polydata = self._representation_maps["pial"].polydata
        bounds = polydata.GetBounds()
        source_index = None
        if all(bounds[2 * axis] <= point[axis] <= bounds[2 * axis + 1] for axis in range(3)):
            if self._source_locator is None or self._source_locator.GetDataSet() is not polydata:
                self._source_locator = vtkStaticPointLocator()
                self._source_locator.SetDataSet(polydata)
                self._source_locator.BuildLocator()
            vertex = self._source_locator.FindClosestPoint(point)
            if vertex >= 0:
                mapped = int(self.series.vertex_sources[vertex])
                hemisphere = 0 if vertex < self.series.hemisphere_sizes[0] else 1
                if mapped >= 0 and self.hemispheres_visible[hemisphere]:
                    source_index = mapped
        if source_index == self.selected_source:
            return
        self.selected_source = source_index
        self.source_values = (
            self.series.read_source(source_index) if source_index is not None else None
        )
        Publisher.sendMessage("Source reconstruction changed", mode=self)

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
        Publisher.sendMessage("Source reconstruction changed", mode=self)

    def clear(self):
        self.painting.reset(self)
        self.series = None
        self.surface_map = None
        self.playback = None
        self.frame_index = None
        self.selected_source = self.source_values = None
        self._source_locator = None
        self._cross_position = None
        self._representation_maps.clear()
        self.representation = "pial"
        self.hemispheres_visible = (True, True)
        Publisher.sendMessage("Source reconstruction changed", mode=self)
