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

"""Display offline EEG/MEG reconstructions through the shared surface painting modes.

Convert imported cortical geometry to viewer coordinates and update its VTK scalars
as playback advances. Surface selection and actor visibility use the same lifecycle
as MEP and electric-field maps.
"""

from dataclasses import replace

import numpy as np
from scipy.sparse import issparse
from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData, vtkStaticPointLocator
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction

import invesalius.constants as const
from invesalius.data.source_reconstruction import read_source_config, read_source_reconstruction
from invesalius.data.time_series import Playback
from invesalius.data.visualization.surface_map_visualizer import ColorBar, SurfaceMap
from invesalius.data.visualization.surface_painting_visualizer import SurfacePainting
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class SourceReconstructionMode:
    """Connect imported source samples, playback and the Brain surface's EEG/MEG map.

    Keep imported reconstructions and display meshes for the active data set. Preserve
    source vertex IDs when switching representations or hiding hemispheres. Publish frame and
    source-selection changes so the viewer and timeline show the same samples.
    """

    name = "EEG/MEG"
    requires_navigation = True

    def __init__(self, surface_manager):
        self.surface_manager = surface_manager
        self.painting = SurfacePainting()
        self.reconstructions = []
        self.series = None
        self.surface_map = None
        self.playback = None
        self.token = None
        self.frame_index = None
        self.selected_source = None
        self.source_values = None
        self.representation = "surface"
        self.hemispheres_visible = (True, True)
        self._representation_maps = {}
        self._representation_data = {}
        self._cross_position = None
        self._source_locator = None
        self._cross_enabled = False
        self.available = False
        self.painting.register(self)
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.load, "Load source reconstruction")
        Publisher.subscribe(self.set_frame, "Set source reconstruction frame")
        Publisher.subscribe(self.set_display, "Set source reconstruction display")
        Publisher.subscribe(self.set_signal_display, "Set source reconstruction signal display")
        Publisher.subscribe(self.brain_changed, "Brain surface changed")
        Publisher.subscribe(self.select_cross_source, "Set cross focal point")
        Publisher.subscribe(self.cross_tool_changed, "Toggle toolbar item")

    def load(self, filename=None, config=None):
        """Validate and activate a reconstruction before adding it to the loaded list."""
        if not self.painting.navigation_mode:
            raise ValueError("Switch to navigation mode before loading a source reconstruction.")
        if (filename is None) == (config is None):
            raise ValueError("Provide a source configuration file or import settings.")
        series = (
            read_source_config(filename) if config is None else read_source_reconstruction(config)
        )
        self._activate(series)
        self.reconstructions.append(series)
        Publisher.sendMessage("Source reconstruction changed", mode=self)

    @property
    def reconstruction_names(self):
        return tuple(
            f"{index + 1}. {series.name}" for index, series in enumerate(self.reconstructions)
        )

    @property
    def reconstruction_index(self):
        return next(
            (index for index, series in enumerate(self.reconstructions) if series is self.series),
            -1,
        )

    def select_reconstruction(self, index):
        if not 0 <= index < len(self.reconstructions):
            raise IndexError("Reconstruction index is outside the loaded list.")
        series = self.reconstructions[index]
        if series is not self.series:
            self._activate(series)

    def remove_reconstruction(self, index):
        if not 0 <= index < len(self.reconstructions):
            raise IndexError("Reconstruction index is outside the loaded list.")
        if self.reconstructions[index] is self.series:
            if len(self.reconstructions) == 1:
                self.clear()
                return
            self._activate(self.reconstructions[index - 1 if index else 1])
        self.reconstructions.pop(index)
        Publisher.sendMessage("Source reconstruction changed", mode=self)

    def _activate(self, series):
        """Replace only the active display, restoring it if the new map cannot be shown."""
        if not self.painting.navigation_mode:
            raise ValueError("Switch to navigation mode before loading a source reconstruction.")
        surface_map, source_mapping, hemispheres = self._create_map(series)
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
            self._representation_data,
            self._cross_position,
        )
        previous_mode = surface.painting_mode
        self.painting.reset(self)
        self.series, self.surface_map = series, surface_map
        self.representation = series.base_representation
        self.hemispheres_visible = (True, True)
        self._representation_maps = {series.base_representation: surface_map}
        self._representation_data = {series.base_representation: (source_mapping, hemispheres)}
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
                self._representation_data,
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

    def _create_map(self, series, representation=None):
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
        surface_points, triangles, source_mapping, hemispheres = series.read_surface(
            representation or series.base_representation
        )
        points = vtkPoints()
        points.SetData(numpy_to_vtk(surface_points, deep=True))
        connectivity = np.column_stack(
            [np.full(len(triangles), 3, dtype=np.int64), triangles]
        ).ravel()
        cells = vtkCellArray()
        cells.SetCells(len(triangles), numpy_to_vtkIdTypeArray(connectivity, deep=True))
        polydata = vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetPolys(cells)
        polydata = self.surface_manager.ConvertPolydataToInv(polydata)
        normals = vtkPolyDataNormals()
        normals.SetInputData(polydata)
        # Splitting duplicates vertices and would break the original source vertex IDs.
        normals.SplittingOff()
        normals.AutoOrientNormalsOn()
        normals.Update()
        polydata = normals.GetOutput()
        if polydata.GetNumberOfPoints() != len(surface_points):
            raise ValueError("Source visualization must preserve the cortical vertex IDs.")
        coordinates = vtk_to_numpy(polydata.GetPoints().GetData())
        if not np.isfinite(coordinates).all():
            raise ValueError("Source geometry cannot be represented in project coordinates.")
        values = np.full(polydata.GetNumberOfPoints(), np.nan, dtype=np.float64)
        polydata.GetPointData().SetScalars(numpy_to_vtk(values, deep=True))
        surface_map = SurfaceMap(
            polydata,
            vtkColorTransferFunction(),
            (0.0, 1.0),
            series.name,
            series.display_unit,
            color_bar=ColorBar(position=(0.82, 0.1), compact=False),
        )
        self._set_map_scale(surface_map, series)
        return surface_map, source_mapping, hemispheres

    def _set_map_scale(self, surface_map, series):
        factor = series.display_scale[0]
        minimum, maximum = (value * factor for value in series.scalar_range)
        limit = max(abs(minimum), abs(maximum)) or 1.0
        if minimum >= 0:
            scalar_range = (0.0, limit)
        elif maximum <= 0:
            scalar_range = (-limit, 0.0)
        else:
            scalar_range = (-limit, limit)
        lut = surface_map.lookup_table
        lut.RemoveAllPoints()
        if scalar_range[0] < 0:
            lut.AddRGBPoint(-limit, 0.15, 0.3, 0.85)
        lut.AddRGBPoint(0, 0.85, 0.85, 0.85)
        if scalar_range[1] > 0:
            lut.AddRGBPoint(limit, 0.85, 0.15, 0.1)
        lut.SetNanColor(0.65, 0.65, 0.65)
        surface_map.scalar_range = scalar_range
        surface_map.unit = series.display_unit or series.unit
        surface_map.color_bar = replace(surface_map.color_bar, title=series.display_title)

    def set_signal_display(self, unit, display_unit, automatic_scale):
        if self.series is None:
            return
        if not all(isinstance(value, str) and value.strip() for value in (unit, display_unit)):
            raise ValueError("Select nonempty source and display units.")
        series = self.series
        previous = series.source_unit, series.display_unit, series.automatic_scale
        settings = unit.strip(), display_unit.strip(), bool(automatic_scale)
        if settings == previous:
            return
        series.source_unit, series.display_unit, series.automatic_scale = settings
        try:
            series.display_scale
        except ValueError:
            series.source_unit, series.display_unit, series.automatic_scale = previous
            raise
        for surface_map in (*self._representation_maps.values(), self.surface_map):
            self._set_map_scale(surface_map, series)
        if self.token is not None:
            self._show_frame()
        else:
            Publisher.sendMessage("Source reconstruction changed", mode=self)

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
            candidate, mapping, hemispheres = self._create_map(self.series, representation)
            self._representation_data[representation] = (mapping, hemispheres)
        triangles = vtk_to_numpy(candidate.polydata.GetPolys().GetConnectivityArray()).reshape(
            -1, 3
        )
        hemispheres = self._representation_data[representation][1]
        if hemispheres is not None:
            visible_faces = np.asarray(visible)[hemispheres[triangles]].all(axis=1)
            triangles = triangles[visible_faces]
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
        return self.series.source_label(self.selected_source)

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
        polydata = self._representation_maps[self.series.base_representation].polydata
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
                visible = True
                if self.series.has_hemispheres:
                    hemisphere = (
                        self.series.vertex_hemispheres[vertex]
                        if self.series.vertex_hemispheres is not None
                        else int(vertex >= self.series.hemisphere_sizes[0])
                    )
                    visible = self.hemispheres_visible[hemisphere]
                if mapped >= 0 and visible:
                    source_index = mapped
        if source_index == self.selected_source:
            return
        self.selected_source = source_index
        self.source_values = (
            self.series.read_source(source_index) if source_index is not None else None
        )
        Publisher.sendMessage("Source reconstruction changed", mode=self)

    def tick(self):
        """Advance playback and refresh the map on the timeline's GUI timer tick."""
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
        mapping = self._representation_data[self.representation][0]
        factor = self.series.display_scale[0]
        if issparse(mapping):
            values[:] = (mapping @ frame) * factor
        else:
            mapped = mapping >= 0
            values.fill(np.nan)
            values[mapped] = np.multiply(frame[mapping[mapped]], factor, dtype=np.float64)
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
        self._representation_data.clear()
        self.representation = "surface"
        self.hemispheres_visible = (True, True)
        self.reconstructions.clear()
        Publisher.sendMessage("Source reconstruction changed", mode=self)
