"""EEG actors and selection, owned by the navigation view."""

import numpy as np
import vtk

import invesalius.data.coordinates as dco
from invesalius.pubsub import pub as Publisher


class EEGVisualizer:
    def __init__(self, renderer, actor_factory, electrodes):
        self.renderer = renderer
        self.actor_factory = actor_factory
        self.electrodes = electrodes
        self.actors = {}
        self.highlighted_uuid = None
        self.labels_visible = electrodes.labels_visible
        self.is_navigating = electrodes.navigation_on
        Publisher.subscribe(self.SyncElectrodes, "EEG electrodes changed")
        Publisher.subscribe(self.SetLabelsVisibility, "Set EEG electrode labels visibility")
        Publisher.subscribe(self.HighlightElectrode, "Highlight EEG electrode")
        Publisher.subscribe(self.UnhighlightElectrode, "Unhighlight EEG electrode")
        Publisher.subscribe(self.SelectElectrodeByActor, "Select EEG electrode by actor")
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")
        self.SyncElectrodes()

    def dispose(self):
        Publisher.unsubscribe_owner(self)
        for actors in self.actors.values():
            for actor in actors:
                self.renderer.RemoveActor(actor)
        self.actors.clear()

    def OnNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = bool(nav_status)
        if self.is_navigating:
            self.UnhighlightElectrode()

    def SyncElectrodes(self):
        electrodes = {item.electrode_uuid: item for item in self.electrodes.electrodes}
        for electrode_uuid in self.actors.keys() - electrodes.keys():
            for actor in self.actors.pop(electrode_uuid):
                self.renderer.RemoveActor(actor)
            if self.highlighted_uuid == electrode_uuid:
                self.highlighted_uuid = None
        for electrode_uuid, electrode in electrodes.items():
            if electrode_uuid not in self.actors:
                self.actors[electrode_uuid] = self._CreateActors(electrode)
                for actor in self.actors[electrode_uuid]:
                    self.renderer.AddActor(actor)
            actor, label = self.actors[electrode_uuid]
            self.renderer.SetPropVisibility(actor, electrode.visible)
            self.renderer.SetPropVisibility(label, electrode.visible and self.labels_visible)
        self._Render()

    def _CreateActors(self, electrode):
        position = list(electrode.position)
        position[1] *= -1
        actor = self.actor_factory.CreateTorus(
            (0, 0, 0),
            (0, 0, 0),
            electrode.colour,
            ring_radius=3.0,
            cross_section_radius=0.8,
        )
        transform = vtk.vtkTransform()
        transform.SetMatrix(
            self.actor_factory.CreateVTKObjectMatrix(position, electrode.orientation)
        )
        actor.SetUserTransform(transform)
        actor.GetProperty().SetOpacity(0.8)
        label = vtk.vtkBillboardTextActor3D()
        label.SetInput(electrode.label)
        label.SetPosition(position[0], position[1], position[2] + 6.0)
        label.PickableOff()
        text = label.GetTextProperty()
        text.SetFontSize(28)
        text.SetColor(electrode.colour)
        text.SetBold(True)
        text.SetShadow(True)
        text.SetShadowOffset(2, -2)
        text.SetFrame(True)
        text.SetFrameColor(0.2, 0.2, 0.2)
        text.SetFrameWidth(2)
        text.SetBackgroundColor(0.3, 0.3, 0.3)
        text.SetBackgroundOpacity(0.85)
        return actor, label

    def SetLabelsVisibility(self, visible):
        self.labels_visible = bool(visible)
        self.SyncElectrodes()

    def SelectElectrodeByActor(self, actor):
        if self.is_navigating:
            return
        for electrode_uuid, (electrode_actor, _label) in self.actors.items():
            if actor is electrode_actor:
                Publisher.sendMessage("Select EEG electrode", electrode_uuid=electrode_uuid)
                return

    def HighlightElectrode(self, electrode_uuid):
        if self.is_navigating or electrode_uuid not in self.actors:
            return
        self.UnhighlightElectrode()
        actor, _label = self.actors[electrode_uuid]
        actor.GetProperty().SetColor(0.0, 0.5, 1.0)
        actor.SetScale(1.01)
        self.highlighted_uuid = electrode_uuid
        self._FocusCamera(self.electrodes.get(electrode_uuid))
        self._Render()

    def UnhighlightElectrode(self):
        if self.highlighted_uuid is None:
            return
        electrode = self.electrodes.get(self.highlighted_uuid)
        if electrode is not None and self.highlighted_uuid in self.actors:
            actor, _label = self.actors[self.highlighted_uuid]
            actor.GetProperty().SetColor(electrode.colour)
            actor.SetScale(1.0)
        self.highlighted_uuid = None
        self._Render()

    def _FocusCamera(self, electrode):
        target = np.asarray(electrode.position, dtype=float).copy()
        target[1] *= -1
        rotation = dco.coordinates_to_transformation_matrix(
            position=(0, 0, 0), orientation=electrode.orientation, axes="sxyz"
        )
        normal = rotation[:3, 2]
        camera = self.renderer.GetActiveCamera()
        distance = np.linalg.norm(np.asarray(camera.GetPosition()) - camera.GetFocalPoint())
        if distance < 50.0:
            distance = 250.0
        camera.SetFocalPoint(*target)
        camera.SetPosition(*(target + normal * distance))
        camera.SetViewUp(0, 1, 0) if abs(normal[2]) > 0.99 else camera.SetViewUp(0, 0, 1)
        self.renderer.ResetCameraClippingRange()

    def _Render(self):
        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")
