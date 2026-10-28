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

"""Navigation-only surface painting and presentation."""

from typing import Protocol

import numpy as np

import invesalius.constants as const
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher
from invesalius.session import Session
from invesalius.utils import Singleton


class PaintingMode(Protocol):
    name: str
    available: bool

    def default_surface(self): ...
    def start(self, surface, token): ...
    def stop(self): ...


class SurfacePresentation:
    """Resolve original representations and temporary surface replacements."""

    def __init__(self, painting, original):
        self.painting = painting
        self.original = original
        self.replaced_sources = {}

    def visible(self, surface):
        return bool(surface.is_shown and surface not in self.replaced_sources.values())

    @staticmethod
    def is_original(surface):
        return not surface.painting_mode and surface.display_map is None

    def show_original(self, surface, actor):
        actor.SetVisibility(
            self.visible(surface)
            and self.is_original(surface)
            and self.original.actor_for(surface) is None
        )
        self.original.refresh()

    def replace_source(self, name, source, target):
        if source is not target:
            self.replaced_sources[name] = source
            self.painting._changed(source)

    def release_source(self, name):
        source = self.replaced_sources.pop(name, None)
        if source is not None:
            self.painting._changed(source)


class SurfacePeeling:
    """Keep peeling as an alternative to the brain's original presentation."""

    def __init__(self, painting):
        self.painting = painting
        self.source = None
        self.enabled = False
        self.actor = None
        Publisher.subscribe(self.brain_changed, "Brain surface changed")
        Publisher.subscribe(self.set_navigation_mode, "Set surface navigation mode")
        Publisher.subscribe(self.clear, "Close surface painting")
        Publisher.subscribe(self.restore, "Project loaded successfully")

    @property
    def brain(self):
        return Project().peel

    @property
    def depth(self):
        return self.brain.depth if self.brain is not None else const.PEEL_DEPTH

    @property
    def max_depth(self):
        return self.brain.numberOfPeels if self.brain is not None else const.MAX_PEEL_DEPTH

    @property
    def selected(self):
        return self.brain.selected if self.brain is not None else True

    def available(self, surface):
        return (
            self.painting.enabled
            and self.actor is not None
            and surface is Project().GetBrainSurface()
        )

    def actor_for(self, surface):
        return self.actor if self.available(surface) and self.selected else None

    def select(self, surface, selected):
        if self.available(surface):
            self.brain.selected = selected
            self.painting._changed(surface)
            Session().ChangeProject()

    @staticmethod
    def build(source):
        from invesalius.data.brainmesh_handler import Brain
        from invesalius.data.slice_ import Slice

        slic = Slice()
        from_file = isinstance(source, str)
        affine = slic.affine.copy() if from_file else np.eye(4)
        brain = Brain(const.MAX_PEEL_DEPTH, slic.window_width, slic.window_level, affine, Project())
        if from_file:
            brain.from_mask_file(source)
        else:
            brain.from_mask(source)
        geometry = brain.peel[0]
        if not geometry.GetNumberOfPoints() or not geometry.GetNumberOfCells():
            raise ValueError("The brain mask does not contain usable geometry.")
        return brain

    def configure(self, brain, source):
        Project().peel = brain
        self.source = source
        self.set_enabled(True)
        Session().ChangeProject()

    def set_enabled(self, enabled):
        self.enabled = enabled and self.brain is not None
        self._publish()

    def set_depth(self, depth):
        if self.brain is not None and depth != self.depth:
            self.brain.depth = depth
            self._publish()
            Session().ChangeProject()

    def restore(self):
        if self.painting.enabled:
            self.set_enabled(self.brain is not None)

    def _publish(self):
        actor = self.brain.get_actor(self.depth) if self.enabled else None
        if self.actor is not None:
            self.actor.SetVisibility(False)
        self.actor = actor
        if actor is not None:
            Publisher.sendMessage(
                "Get peel centers and normals",
                centers=self.brain.peel_centers,
                normals=self.brain.peel_normals,
            )
            Publisher.sendMessage("Get init locator", locator=self.brain.locator)
        surface = Project().GetBrainSurface()
        if surface is not None:
            self.painting._changed(surface)
        self.refresh()
        Publisher.sendMessage("Update peel", flag=self.enabled, actor=actor)
        Publisher.sendMessage("Update peel visualization", data=self.enabled)
        Publisher.sendMessage("Surface peel changed")

    def refresh(self):
        surface = Project().GetBrainSurface()
        presentation = self.painting.presentation
        visible = bool(
            self.painting.enabled
            and self.actor is not None
            and self.selected
            and (
                surface is None
                or (presentation.visible(surface) and presentation.is_original(surface))
            )
        )
        if self.actor is not None:
            self.actor.GetProperty().SetOpacity(
                1 - surface.transparency if surface is not None else const.BRAIN_OPACITY
            )
            self.actor.SetVisibility(visible)
        Publisher.sendMessage("Update peel visibility", visible=visible)

    def brain_changed(self, previous, surface):
        for candidate in (previous, surface):
            if candidate is not None and candidate in Project().surface_dict.values():
                self.painting._changed(candidate)
        self.refresh()

    def set_navigation_mode(self, status):
        if not status:
            self.clear()

    def clear(self):
        self.source = None
        self.set_enabled(False)


class SurfacePainting(metaclass=Singleton):
    def __init__(self):
        self.modes = {}
        self.targets = {}
        self.tokens = {}
        self.enabled = Session().GetConfig("mode") == const.MODE_NAVIGATOR
        Publisher.subscribe(self.set_navigation_mode, "Set surface navigation mode")
        Publisher.subscribe(self.remove_surface, "Discard surface painting")
        Publisher.subscribe(self.close, "Close surface painting")
        self.peeling = SurfacePeeling(self)
        self.presentation = SurfacePresentation(self, self.peeling)

    def register(self, mode: PaintingMode):
        previous = self.modes.get(mode.name)
        if previous is not None and previous is not mode:
            self.unregister(previous)
        self.modes[mode.name] = mode

    def unregister(self, mode):
        if self.modes.get(mode.name) is mode:
            self.reset(mode)
            self.modes.pop(mode.name)

    def reset(self, mode):
        self.set_available(mode, False)
        self.targets.pop(mode.name, None)

    def available_modes(self, surface):
        if not self.enabled or surface.frozen_map is not None or not surface.has_geometry:
            return ()
        return tuple(mode for mode in self.modes.values() if mode.available)

    def set_available(self, mode, available):
        mode.available = available
        if not available:
            self.stop(mode.name)
        Publisher.sendMessage("Surface painting availability changed", mode=mode)

    def select(self, surface, name=""):
        if not self.enabled:
            return False
        if not name:
            if surface.painting_mode:
                self.stop(surface.painting_mode)
            return True
        mode = self.modes[name]
        if surface is None:
            surface = self.targets.get(name) or mode.default_surface()
        if surface is None or surface not in Project().surface_dict.values():
            return False
        if mode not in self.available_modes(surface):
            return False
        if self.targets.get(name) is surface and name in self.tokens:
            return True
        self.stop(name)
        if surface.painting_mode:
            self.stop(surface.painting_mode)
        token = object()
        self.targets[name] = surface
        self.tokens[name] = token
        surface.painting_mode = name
        try:
            mode.start(surface, token)
        except Exception:
            self.stop(name)
            raise
        self._changed(surface)
        return True

    def stop(self, name):
        token = self.tokens.pop(name, None)
        surface = self.targets.get(name)
        if surface is not None and surface.painting_mode == name:
            surface.painting_mode = ""
            surface.display_map = None
        if token is not None:
            self.modes[name].stop()
        self.presentation.release_source(name)
        if surface is not None:
            self._changed(surface)

    def update(self, name, token, surface_map):
        if not self.enabled or token is None or self.tokens.get(name) is not token:
            return
        surface = self.targets[name]
        surface.display_map = surface_map
        Publisher.sendMessage("Update surface presentation", surface=surface)
        Publisher.sendMessage("Render volume viewer")

    def remove_surface(self, surface):
        for name, target in list(self.targets.items()):
            if target is surface:
                self.stop(name)
                self.targets.pop(name)

    def set_navigation_mode(self, status):
        if self.enabled == status:
            return
        self.enabled = status
        if not status:
            for name in list(self.tokens):
                self.stop(name)
        for surface in Project().surface_dict.values():
            surface.display_map = surface.frozen_map if status else None
            self._changed(surface)

    def close(self):
        for name in list(self.tokens):
            self.stop(name)
        self.targets.clear()

    @staticmethod
    def _changed(surface):
        Publisher.sendMessage("Update surface presentation", surface=surface)
        Publisher.sendMessage("Update surface info in GUI", surface=surface)
        Publisher.sendMessage("Render volume viewer")
