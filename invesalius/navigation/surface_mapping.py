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

from vtkmodules.vtkCommonDataModel import vtkPolyData

import invesalius.project as prj
import invesalius.session as ses
from invesalius.data.visualization.surface_scalar_visualizer import (
    CreateLookupTable,
    GetLookupTableState,
    SurfaceScalarMap,
    SurfaceScalarVisualizer,
)
from invesalius.pubsub import pub as Publisher


class NavigationSurfaceManager:
    """Own surface mapping while the navigation workspace is active."""

    def __init__(self, surfaces):
        self.surfaces = surfaces
        self.map_visualizers = {}
        Publisher.subscribe(self.UpdateScalarSurface, "Update scalar surface")
        Publisher.subscribe(self.ShowScalarSurface, "Show scalar surface")
        Publisher.subscribe(self.SetScalarSurfaceSource, "Set scalar surface source")
        Publisher.subscribe(self.SetScalarSourceEnabled, "Set scalar source enabled")
        Publisher.subscribe(self.SetSurfaceMap, "Set surface map")
        Publisher.subscribe(self.SetSurfaceRole, "Set surface role")
        Publisher.subscribe(self._RemoveSurfaceMaps, "Discard surface mapping")
        Publisher.subscribe(self._ConfigureSurfaceMap, "Update surface presentation")
        Publisher.subscribe(self.OnLoadSurfaceDict, "Load surface dict")
        Publisher.subscribe(self.OnCloseProject, "Close surface mapping")
        self.OnLoadSurfaceDict(prj.Project().surface_dict)

    def OnLoadSurfaceDict(self, surface_dict):
        project = prj.Project()
        for source, state in project.scalar_sources.items():
            if state["surface"] is not None and state["surface"] not in surface_dict.values():
                state.update(surface=None, enabled=False)
                Publisher.sendMessage("Scalar surface removed", source=source)
        for surface in list(self.map_visualizers):
            if surface not in surface_dict.values():
                self._RemoveSurfaceMaps(surface)
        for surface in surface_dict.values():
            for source in surface.scalar_maps:
                state = project.scalar_sources.setdefault(
                    source, {"enabled": False, "surface": None}
                )
                if state["surface"] is None:
                    state["surface"] = surface
            if surface.can_use_as_geometry:
                self._ConfigureSurfaceMap(surface)

    def OnCloseProject(self):
        surfaces = set(self.map_visualizers)
        surfaces.update(
            state["surface"]
            for state in prj.Project().scalar_sources.values()
            if state["surface"] is not None
        )
        for surface in surfaces:
            self._RemoveSurfaceMaps(surface)
        for state in prj.Project().scalar_sources.values():
            state.update(surface=None, enabled=False)

    def dispose(self):
        project = prj.Project()
        for source, state in project.scalar_sources.items():
            if state["enabled"]:
                self.SetScalarSourceEnabled(source, False)
        Publisher.sendMessage("Close surface mapping")
        Publisher.unsubscribe_owner(self)
        for surface in project.surface_dict.values():
            surface.active_scalar_map = ""

    def UpdateScalarSurface(self, surface_map, lookup_table, scalar_range, source):
        proj = prj.Project()
        state = proj.scalar_sources.get(source)
        if state is None or state["surface"] not in proj.GetGeometrySurfaces().values():
            return
        surface = state["surface"]
        config = {
            "name": surface_map.name,
            "unit": surface_map.unit,
            "range": list(scalar_range),
            "lookup_table": GetLookupTableState(lookup_table),
        }
        if surface_map.color_array is not None:
            config["color_array"] = surface_map.color_array
        polydata = vtkPolyData()
        polydata.ShallowCopy(surface_map.polydata)
        surface.scalar_maps[source] = dict(config, polydata=polydata)
        if surface.active_scalar_map == source:
            self._ConfigureSurfaceMap(surface)
        ses.Session().ChangeProject()
        Publisher.sendMessage("Render volume viewer")

    def ShowScalarSurface(self, source, visibility):
        self.SetScalarSourceEnabled(source, visibility)
        state = prj.Project().scalar_sources[source]
        surface = state["surface"]
        if visibility and surface is not None:
            surface.active_scalar_map = source
            self._ConfigureSurfaceMap(surface)
            Publisher.sendMessage("Update surface info in GUI", surface=surface)
            Publisher.sendMessage("Render volume viewer")

    def SetScalarSourceEnabled(self, source, enabled):
        proj = prj.Project()
        state = proj.scalar_sources.setdefault(source, {"enabled": False, "surface": None})
        was_enabled = state["enabled"]
        state["enabled"] = enabled
        if not enabled:
            for surface in proj.GetGeometrySurfaces().values():
                if surface.active_scalar_map == source:
                    surface.active_scalar_map = ""
                    self._ConfigureSurfaceMap(surface)
                    Publisher.sendMessage("Update surface info in GUI", surface=surface)
            if was_enabled:
                Publisher.sendMessage("Scalar source disabled", source=source)
            Publisher.sendMessage("Render volume viewer")

    def SetScalarSurfaceSource(self, source, surface_index):
        proj = prj.Project()
        surface = proj.GetGeometrySurfaces().get(surface_index)
        if surface is None:
            return
        state = proj.scalar_sources.setdefault(source, {"enabled": False, "surface": None})
        previous = state["surface"]
        if previous is surface:
            return
        state["surface"] = surface
        if previous is not None:
            config = previous.scalar_maps.pop(source, None)
            if config is not None and source != "MEP":
                surface.scalar_maps[source] = config
            if previous.active_scalar_map == source:
                previous.active_scalar_map = ""
            self._ConfigureSurfaceMap(previous)
            Publisher.sendMessage("Update surface info in GUI", surface=previous)
        ses.Session().ChangeProject()

    def SetSurfaceMap(self, surface_index, source=""):
        proj = prj.Project()
        surface = proj.GetGeometrySurfaces().get(surface_index)
        if surface is None:
            return
        if source:
            if not proj.GetSurfaceMapModes(surface_index).get(source, False):
                return
            if source == "MEP":
                Publisher.sendMessage("Get brain surface actor", index=surface_index)
            else:
                self.SetScalarSurfaceSource(source, surface_index)
        else:
            for map_source, state in proj.scalar_sources.items():
                if state["surface"] is surface and state["enabled"]:
                    self.SetScalarSourceEnabled(map_source, False)
        surface.active_scalar_map = source
        self._ConfigureSurfaceMap(surface)
        Publisher.sendMessage("Update surface info in GUI", surface=surface)
        Publisher.sendMessage("Render volume viewer")

    def SetSurfaceRole(self, surface_index, role):
        prj.Project().SetSurfaceRole(surface_index, role)
        ses.Session().ChangeProject()

    def _ConfigureSurfaceMap(self, surface):
        actor = self.surfaces.actors_dict.get(surface.index)
        if actor is None:
            return
        source = surface.active_scalar_map
        config = surface.scalar_maps.get(source)
        active = config is not None and prj.Project().scalar_sources.get(source, {}).get(
            "enabled", False
        )
        actor.SetVisibility(surface.is_shown and not active)
        visualizer = self.map_visualizers.get(surface)
        if active:
            if visualizer is None:
                visualizer = SurfaceScalarVisualizer()
                self.map_visualizers[surface] = visualizer
                for prop in visualizer.actors:
                    Publisher.sendMessage("AppendActor", actor=prop)
            visualizer.SetMap(
                SurfaceScalarMap(
                    config["polydata"], config["name"], config["unit"], config.get("color_array")
                ),
                CreateLookupTable(config["lookup_table"]),
                config["range"],
            )
            visualizer.actor.GetProperty().DeepCopy(actor.GetProperty())
        elif visualizer is not None:
            visualizer.Clear()
        if visualizer is not None:
            for prop in visualizer.actors:
                prop.SetVisibility(bool(active and surface.is_shown))

    def _RemoveSurfaceMaps(self, surface):
        visualizer = self.map_visualizers.pop(surface, None)
        if visualizer is not None:
            for prop in visualizer.actors:
                Publisher.sendMessage("Remove surface actor from viewer", actor=prop)
            visualizer.Clear()
        for source, state in prj.Project().scalar_sources.items():
            if state["surface"] is surface:
                state.update(surface=None, enabled=False)
                Publisher.sendMessage("Scalar surface removed", source=source)
