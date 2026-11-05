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

import logging
import os
import re

import numpy as np
import wx
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonColor import vtkColorSeries
from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR, mutable, vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkCellLocator, vtkPlane, vtkPolyData
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkCutter
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkIOLegacy import vtkPolyDataReader
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
from vtkmodules.vtkRenderingCore import vtkPolyDataMapper

import invesalius.constants as const
import invesalius.data.slice_ as sl
import invesalius.project as prj
from invesalius.data.visualization.surface_map_visualizer import ColorBar
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

log = logging.getLogger(__name__)

_HIGHLIGHT_RGB = (255, 165, 0)
_ARROW_LENGTH = 10.0

_EFIELD_ARRAY_CANDIDATES = ("magnE", "normE", "magnJ", "magn", "E", "scalars")

# Adjustable in the panel
EFIELD_SAMPLING_MAX_DISTANCE = 6.0

COLORS_ARRAY_NAME = "Colors"


def ReadEfieldSurface(path):
    polydata = _ReadEfieldPolyData(path)

    point_data = polydata.GetPointData()
    scalars = _SelectEfieldArray(point_data)
    vtk_vectors = point_data.GetVectors()
    vectors = numpy_support.vtk_to_numpy(vtk_vectors) if vtk_vectors is not None else None

    if scalars is not None:
        norms = numpy_support.vtk_to_numpy(scalars)
        if norms.ndim > 1:
            norms = np.linalg.norm(norms, axis=1)
    elif vectors is not None:
        norms = np.linalg.norm(vectors, axis=1)
    else:
        raise ValueError(
            "the surface has no point data to colour by (expected the E-field "
            "magnitude, e.g. 'magnE')"
        )

    return polydata, np.asarray(norms, dtype=float), vectors


def _ReadEfieldPolyData(path):
    extension = os.path.splitext(path)[1].lower()
    if extension == ".vtp":
        reader = vtkXMLPolyDataReader()
    elif extension == ".vtk":
        reader = vtkPolyDataReader()
        reader.ReadAllScalarsOn()
        reader.ReadAllVectorsOn()
    else:
        raise ValueError(
            f"unsupported E-field surface format '{extension}'. The SimNIBS server "
            "must send a VTK surface (.vtk/.vtp), not the raw .msh."
        )
    reader.SetFileName(path)
    reader.Update()

    _affine, affine_vtk, _img_shift = sl.Slice().get_world_to_invesalius_vtk_affine(inverse=False)

    transform = vtkTransform()
    transform.PostMultiply()
    transform.Concatenate(affine_vtk)

    transform_filter = vtkTransformPolyDataFilter()
    transform_filter.SetTransform(transform)
    transform_filter.SetInputData(reader.GetOutput())
    transform_filter.Update()

    polydata = transform_filter.GetOutput()
    if polydata is None or polydata.GetNumberOfPoints() == 0:
        raise ValueError("the E-field surface file is empty or could not be read")
    return polydata


def ShareGeometry(polydata):
    """A polydata sharing points and cells with its own point data."""
    shared = vtkPolyData()
    shared.SetPoints(polydata.GetPoints())
    shared.SetVerts(polydata.GetVerts())
    shared.SetLines(polydata.GetLines())
    shared.SetPolys(polydata.GetPolys())
    shared.SetStrips(polydata.GetStrips())

    normals = polydata.GetPointData().GetNormals()
    if normals is not None:
        shared.GetPointData().SetNormals(normals)
    return shared


def SampleEfieldOntoSurface(
    source_polydata, norms, target_polydata, max_distance=EFIELD_SAMPLING_MAX_DISTANCE
):
    """Carry the field values of the E-field mesh over to another surface."""
    from scipy.spatial import cKDTree

    source_points = numpy_support.vtk_to_numpy(source_polydata.GetPoints().GetData())
    target_points = numpy_support.vtk_to_numpy(target_polydata.GetPoints().GetData())
    if not len(source_points) or not len(target_points):
        return np.empty(0), [], np.empty(0, dtype=int), 0.0, float("inf")

    distances, indices = cKDTree(source_points).query(target_points, k=1)
    within = distances <= max_distance

    source_ids = indices[within]
    values = np.asarray(norms, dtype=float)[source_ids]
    point_ids = np.flatnonzero(within).tolist()
    coverage = float(np.count_nonzero(within)) / len(target_points)
    return values, point_ids, source_ids, coverage, float(np.min(distances))


def BuildPointTree(polydata):
    """A nearest-point index over the mesh, built once and reused across surfaces"""
    from scipy.spatial import cKDTree

    return cKDTree(numpy_support.vtk_to_numpy(polydata.GetPoints().GetData()))


def EstimateCoverage(
    tree, target_polydata, max_distance=EFIELD_SAMPLING_MAX_DISTANCE, samples=2000
):
    """Share of a surface the field reaches, judged on a thinned set of its points"""
    points = numpy_support.vtk_to_numpy(target_polydata.GetPoints().GetData())
    if not len(points):
        return 0.0
    if len(points) > samples:
        points = points[:: len(points) // samples + 1]
    distances, _ = tree.query(points, k=1)
    return float(np.count_nonzero(distances <= max_distance)) / len(points)


def IsDefaultTarget(name):
    """True for a surface name the field belongs on, to break ties between the ones it reaches"""
    words = set(re.split(r"[^a-z0-9]+", name.lower()))
    return bool(words & {"gm", "gray", "grey", "cortex"})


def ColorsFromLUT(values, lut):
    """Look `values` up in `lut`, as an (N, 3) uint8 array."""
    table = numpy_support.vtk_to_numpy(lut.GetTable()).reshape(-1, 4)[:, :3]
    minimum, maximum = lut.GetTableRange()
    values = np.asarray(values, dtype=float)
    if maximum <= minimum:
        indexes = np.zeros(len(values), dtype=int)
    else:
        scaled = (values - minimum) / (maximum - minimum) * len(table)
        indexes = np.clip(scaled.astype(int), 0, len(table) - 1)
    return table[indexes].astype(np.uint8)


def BuildColorArray(number_of_points, point_ids, values, lut, base_colour=None):
    """A per-point colour array for a surface, with the unsampled points left plain."""
    base = np.asarray(const.CORTEX_COLOR if base_colour is None else base_colour, dtype=np.uint8)
    rgb = np.tile(base, (number_of_points, 1))
    if len(point_ids):
        rgb[np.asarray(point_ids, dtype=int)] = ColorsFromLUT(values, lut)

    colors = numpy_support.numpy_to_vtk(
        np.ascontiguousarray(rgb), deep=True, array_type=VTK_UNSIGNED_CHAR
    )
    colors.SetNumberOfComponents(3)
    colors.SetName(COLORS_ARRAY_NAME)
    return colors


def CreateCutter(polydata):
    plane = vtkPlane()
    cutter = vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputData(polydata)
    return cutter, plane


def _SelectEfieldArray(point_data):
    active = point_data.GetScalars()
    if active is not None:
        return active

    for name in _EFIELD_ARRAY_CANDIDATES:
        array = point_data.GetArray(name)
        if array is not None:
            return array

    for i in range(point_data.GetNumberOfArrays()):
        array = point_data.GetArray(i)
        if array is not None and array.GetNumberOfComponents() == 1:
            return array

    return None


class SimnibsEfieldVisualizer:
    """Paint a SimNIBS E-field result onto the project surfaces."""

    def __init__(self, ren, actor_factory, render):
        self.ren = ren
        self.actor_factory = actor_factory
        self.render = render
        self.source = None
        self.targets = []
        self.surface_actor = None
        self.dropping_surface = False
        self.colormap = None
        self.opacity = 1.0
        self.max_distance = EFIELD_SAMPLING_MAX_DISTANCE
        self.threshold = const.EFIELD_MAX_RANGE_SCALE
        self.highlight = False
        self.maximum = 0.0
        self.scalar_bar = None
        self.arrows = []
        self._reply = None
        self._bind_events()

    def _bind_events(self):
        Publisher.subscribe(self.Load, "Load SimNIBS efield into viewer")
        Publisher.subscribe(self.Remove, "Remove SimNIBS efield from viewer")
        Publisher.subscribe(self.SetSurfaces, "Set SimNIBS efield surfaces")
        Publisher.subscribe(self.SetColormap, "Set SimNIBS efield colormap")
        Publisher.subscribe(self.SetOpacity, "Set SimNIBS efield opacity")
        Publisher.subscribe(self.SetThreshold, "Set SimNIBS efield threshold")
        Publisher.subscribe(self.SetHighlight, "Set SimNIBS efield highlight")
        Publisher.subscribe(self.Release, "Remove surface actor from viewer")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnActor, "Send Actor")

    def dispose(self):
        Publisher.unsubscribe_owner(self)

    def Load(
        self,
        filepath,
        target_surfaces=None,
        colormap=None,
        threshold=None,
        opacity=None,
        max_distance=None,
    ):
        polydata, norms, vectors = ReadEfieldSurface(filepath)

        if colormap is not None:
            self.colormap = colormap
        if threshold is not None:
            self.threshold = float(threshold)
        if opacity is not None:
            self.opacity = float(opacity)
        if max_distance is not None:
            self.max_distance = float(max_distance)

        self.source = (polydata, norms, vectors)
        # Nothing chosen at load time means the best surface is picked here.
        self._Paint(target_surfaces, choose=True)

    def SetSurfaces(self, target_surfaces, max_distance=None):
        if max_distance is not None:
            self.max_distance = float(max_distance)
        if self.source is not None:
            self._Paint(target_surfaces)

    def SetColormap(self, colormap):
        self.colormap = colormap
        self._Redraw()

    def SetThreshold(self, threshold):
        self.threshold = float(threshold)
        self._Redraw()

    def SetHighlight(self, enable):
        self.highlight = bool(enable)
        self._Redraw()

    def SetOpacity(self, opacity):
        self.opacity = float(opacity)
        if self.targets:
            self._Stagger()
            self.render()

    def Remove(self):
        if not self.targets and self.source is None:
            return
        self._Clear()
        self._DropSurface()
        self.render()
        self._TellCrossSections([])

    def Release(self, actor):
        """A painted surface left the viewer, so the field goes with it."""
        if self.dropping_surface or not any(t["actor"] is actor for t in self.targets):
            return
        # Removing surfaces from here would re-enter the surface manager mid-loop.
        self._Clear()
        self.render()
        self._TellCrossSections([])

    def OnCloseProject(self):
        self._Clear()
        self.surface_actor = None
        self._TellCrossSections([])

    def OnActor(self, e_field_actor):
        self._reply = e_field_actor

    def _Paint(self, target_surfaces, choose=False):
        polydata, norms, _vectors = self.source
        painted, refused = self._Prepare(target_surfaces or [], polydata, norms)
        if not painted:
            if target_surfaces and self.targets:
                raise ValueError(self._Refusal(refused))
            chosen = self._BestSurface(polydata) if choose and not target_surfaces else None
            if chosen is None:
                chosen = self._CreateSurface(polydata)
            painted = self._Prepare([chosen], polydata, norms)[0]
            if not painted:
                raise ValueError("the E-field surface could not be shown")

        self._Hide()
        self._Show(painted)
        self._DropSurface()
        self._TellCrossSections([target["display"] for target in self.targets])
        self._PublishTargets(refused)

    def _Prepare(self, surface_indexes, polydata, norms):
        surface_dict = prj.Project().surface_dict
        painted, refused = [], []
        for surface_index in surface_indexes:
            if surface_index not in surface_dict:
                continue
            name = str(surface_dict[surface_index].name)
            actor = self._GetSurfaceActor(surface_index)
            geometry = self._Geometry(actor)
            if geometry is None or geometry.GetNumberOfPoints() == 0:
                refused.append((name, None))
                continue

            values, point_ids, source_ids, coverage, closest = SampleEfieldOntoSurface(
                polydata, norms, geometry, self.max_distance
            )
            if not point_ids:
                refused.append((name, closest))
                continue

            painted.append(
                {
                    "actor": actor,
                    "name": name,
                    "geometry": geometry,
                    "display": ShareGeometry(geometry),
                    "values": values,
                    "point_ids": point_ids,
                    "source_ids": source_ids,
                    "coverage": coverage,
                    "mapper": None,
                    "opacity": 1.0,
                    "backface_culling": 0,
                }
            )
        return painted, refused

    def _BestSurface(self, polydata):
        """The surface to use when the user has not chosen one."""
        tree = BuildPointTree(polydata)
        best, best_rank = None, None
        for surface_index, surface in prj.Project().surface_dict.items():
            geometry = self._Geometry(self._GetSurfaceActor(surface_index))
            if geometry is None:
                continue
            coverage = EstimateCoverage(tree, geometry, self.max_distance)
            if coverage <= 0:
                continue
            rank = (IsDefaultTarget(str(surface.name)), coverage)
            if best_rank is None or rank > best_rank:
                best, best_rank = surface_index, rank
        return best

    def _Geometry(self, actor):
        if actor is None:
            return None
        for target in self.targets:
            if target["actor"] is actor:
                return target["geometry"]
        mapper = actor.GetMapper()
        return mapper.GetInput() if mapper is not None else None

    def _GetSurfaceActor(self, surface_index):
        self._reply = None
        try:
            Publisher.sendMessage("Get Actor", surface_index=surface_index)
        except KeyError:
            pass
        actor, self._reply = self._reply, None
        return actor

    def _SurfaceIndexFromActor(self, actor):
        for surface_index in prj.Project().surface_dict:
            if self._GetSurfaceActor(surface_index) is actor:
                return surface_index
        return None

    def _Show(self, painted):
        for target in painted:
            actor = target["actor"]
            prop = actor.GetProperty()
            target["mapper"] = actor.GetMapper()
            target["opacity"] = prop.GetOpacity()
            target["backface_culling"] = prop.GetBackfaceCulling()

            mapper = vtkPolyDataMapper()
            mapper.SetInputData(target["display"])
            mapper.ScalarVisibilityOn()
            actor.SetMapper(mapper)
            prop.SetBackfaceCulling(1)

        self.targets = painted
        self.maximum = float(np.max(painted[0]["values"]))
        self._Stagger()
        self._Draw()

    def _Hide(self):
        for target in self.targets:
            actor = target["actor"]
            if target["mapper"] is not None:
                actor.SetMapper(target["mapper"])
            actor.GetProperty().SetOpacity(target["opacity"])
            actor.GetProperty().SetBackfaceCulling(target["backface_culling"])
        self.targets = []

    def _Clear(self):
        self._RemoveArrows()
        if self.scalar_bar is not None:
            self.ren.RemoveActor2D(self.scalar_bar)
            self.scalar_bar = None
        self._Hide()
        self.source = None

    def _Stagger(self):
        """Fade the outer surfaces, as nested ones would otherwise hide the inner ones."""
        targets = self.targets
        base = self.opacity
        if len(targets) < 2:
            for target in targets:
                target["actor"].GetProperty().SetOpacity(base)
            return

        outer = min(const.SIMNIBS_EFIELD_OUTER_OPACITY, base)
        # Widest bounding box first, which for nested surfaces is the outermost.
        order = sorted(targets, key=lambda t: t["display"].GetLength(), reverse=True)
        for rank, target in enumerate(order):
            opacity = outer + (base - outer) * rank / (len(order) - 1)
            target["actor"].GetProperty().SetOpacity(opacity)

    def _Redraw(self):
        if self.targets:
            self._Draw()
            self._TellCrossSections()

    def _Draw(self):
        lut = self._Lut()
        for target in self.targets:
            self._Colour(target, lut)

        if self.scalar_bar is None:
            self.scalar_bar = ColorBar(
                position=(0.82, 0.1), compact=False, title="E (V/m)"
            ).create_actor()
            self.ren.AddActor2D(self.scalar_bar)
        self.scalar_bar.SetLookupTable(lut)

        self._ShowArrows()
        self.render()

    def _Lut(self):
        lut = vtkLookupTable()
        lut.SetTableRange(0, self.maximum)
        definition = const.MEP_COLORMAP_DEFINITIONS.get(self.colormap)
        if definition is None:
            series = vtkColorSeries()
            series.SetColorScheme(series.BREWER_SEQUENTIAL_BLUE_PURPLE_9)
            series.BuildLookupTable(lut, series.ORDINAL)
        else:
            from matplotlib.colors import LinearSegmentedColormap

            positions = [0.0, 0.25, 0.5, 1.0]  # min, low, mid, max
            cmap = LinearSegmentedColormap.from_list(
                self.colormap, list(zip(positions, definition.values()))
            )
            lut.SetNumberOfTableValues(256)
            for i in range(256):
                lut.SetTableValue(i, *cmap(i / 255))
            lut.Build()

        if self.highlight:
            n = lut.GetNumberOfTableValues()
            for i in range(n):
                if i / (n - 1) >= self.threshold:
                    lut.SetTableValue(i, *(np.array(_HIGHLIGHT_RGB) / 255.0), 1.0)
        return lut

    def _Colour(self, target, lut):
        display = target["display"]
        colors = BuildColorArray(
            display.GetNumberOfPoints(), target["point_ids"], target["values"], lut
        )
        if self.highlight:
            above = target["values"] > self.maximum * self.threshold
            rgb = numpy_support.vtk_to_numpy(colors)
            rgb[np.asarray(target["point_ids"])[above]] = _HIGHLIGHT_RGB
        display.GetPointData().SetScalars(colors)
        display.Modified()

    def _ShowArrows(self):
        """Arrows at the field maximum (red) and the centre of gravity above threshold (blue)."""
        self._RemoveArrows()
        vectors = self.source[2]
        if vectors is None:
            return

        target = self.targets[0]
        values = target["values"]
        point_ids = np.asarray(target["point_ids"])
        top = int(np.argmax(values))
        direction = np.asarray(vectors)[target["source_ids"][top]]
        display = target["display"]
        self._AddArrow(display.GetPoint(int(point_ids[top])), direction, (1.0, 0.0, 0.0))

        above = values > self.maximum * self.threshold
        weights = values[above]
        if weights.sum() <= 0:
            return
        points = numpy_support.vtk_to_numpy(display.GetPoints().GetData())[point_ids[above]]
        centre = weights @ points / weights.sum()
        self._AddArrow(self._OnSurface(target, centre), direction, (0.0, 0.0, 1.0))

    def _OnSurface(self, target, point):
        if "locator" not in target:
            target["locator"] = vtkCellLocator()
            target["locator"].SetDataSet(target["display"])
            target["locator"].BuildLocator()
        closest = [0.0, 0.0, 0.0]
        target["locator"].FindClosestPoint(
            [float(x) for x in point], closest, mutable(0), mutable(0), mutable(0.0)
        )
        return closest

    def _AddArrow(self, position, direction, colour):
        length = float(np.linalg.norm(direction))
        if length == 0:
            return
        end = np.asarray(position) + _ARROW_LENGTH * np.asarray(direction) / length
        arrow = self.actor_factory.CreateArrow(list(position), [float(x) for x in end])
        arrow.GetProperty().SetColor(colour)
        ball = self.actor_factory.CreateBall(position, colour, 0.5)
        for actor in (arrow, ball):
            self.ren.AddActor(actor)
            self.arrows.append(actor)

    def _RemoveArrows(self):
        for actor in self.arrows:
            self.ren.RemoveActor(actor)
        self.arrows = []

    def _TellCrossSections(self, polydatas=None):
        try:
            if polydatas is None:
                Publisher.sendMessage("Update SimNIBS efield cross sections")
            else:
                Publisher.sendMessage("Set SimNIBS efield cross sections", polydatas=polydatas)
        except Exception:  # noqa: BLE001 - the 3D view is already correct
            log.exception("SimNIBS E-field cross sections could not be updated")

    def _PublishTargets(self, refused=()):
        painted = [
            (self._SurfaceIndexFromActor(target["actor"]), target["name"], target["coverage"])
            for target in self.targets
        ]
        Publisher.sendMessage("SimNIBS efield painted", painted=painted, refused=list(refused))

    @staticmethod
    def _Refusal(refused):
        if not refused:
            return "no surface was given to paint the E-field on"
        reasons = [
            f"{name} has no geometry to paint on"
            if closest is None
            else f"{name} is {closest:.1f} mm away from the E-field mesh"
            for name, closest in refused
        ]
        return "the E-field does not reach the chosen surface: " + "; ".join(reasons)

    def _CreateSurface(self, polydata):
        """Add the SimNIBS mesh to the project, for when no surface of its own can carry the field."""
        Publisher.sendMessage(
            "Create surface from polydata",
            polydata=polydata,
            name=_("E-field (SimNIBS)"),
            scalar=True,
        )
        surface_dict = prj.Project().surface_dict
        if not surface_dict:
            return None
        surface_index = max(surface_dict)
        self.surface_actor = self._GetSurfaceActor(surface_index)
        wx.CallAfter(Publisher.sendMessage, "Repopulate surfaces")
        return surface_index

    def _DropSurface(self):
        actor = self.surface_actor
        if actor is None or any(t["actor"] is actor for t in self.targets):
            return

        self.surface_actor = None
        surface_index = self._SurfaceIndexFromActor(actor)
        if surface_index is None:
            return

        self.dropping_surface = True
        try:
            Publisher.sendMessage("Remove surfaces", surface_indexes=[surface_index])
        finally:
            self.dropping_surface = False
        wx.CallAfter(Publisher.sendMessage, "Repopulate surfaces")
