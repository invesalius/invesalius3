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

"""Navigation-only mode selection and exclusive destinations for surface painting."""

from typing import Protocol

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


class SurfacePeeling:
    """Keep peeling as an alternative to the brain's original presentation."""

    def __init__(self, painting):
        self.painting = painting
        self.actor = None
        self.selected = True
        Publisher.subscribe(self.update, "Update peel")
        Publisher.subscribe(self.brain_changed, "Brain surface changed")
        Publisher.subscribe(self.set_navigation_mode, "Set surface navigation mode")
        Publisher.subscribe(self.clear, "Close surface painting")

    def available(self, surface):
        return (
            self.painting.enabled
            and self.actor is not None
            and surface is Project().GetBrainSurface()
        )

    def uses_peel(self, surface):
        return (
            self.available(surface)
            and self.selected
            and not surface.painting_mode
            and surface.display_map is None
        )

    def select(self, surface, selected):
        if self.available(surface):
            self.selected = selected
            self.painting._changed(surface)

    def update(self, flag, actor):
        if self.actor is not None:
            self.actor.SetVisibility(False)
        if flag and actor is not self.actor:
            self.selected = True
        self.actor = actor if flag else None
        surface = Project().GetBrainSurface()
        if surface is not None:
            self.painting._changed(surface)
        self.refresh()

    def refresh(self):
        surface = Project().GetBrainSurface()
        visible = bool(
            self.painting.enabled
            and self.actor is not None
            and self.selected
            and (surface is None or (surface.is_shown and self.uses_peel(surface)))
        )
        if self.actor is not None:
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
        Publisher.sendMessage("Update peel", flag=False, actor=None)


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
        if not self.enabled or surface.frozen_map is not None:
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
