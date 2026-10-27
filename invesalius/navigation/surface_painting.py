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


class SurfacePainting(metaclass=Singleton):
    def __init__(self):
        self.modes = {}
        self.targets = {}
        self.tokens = {}
        self.enabled = Session().GetConfig("mode") == const.MODE_NAVIGATOR
        Publisher.subscribe(self.set_navigation_mode, "Set surface navigation mode")
        Publisher.subscribe(self.remove_surface, "Discard surface painting")
        Publisher.subscribe(self.close, "Close surface painting")

    def register(self, mode: PaintingMode):
        previous = self.modes.get(mode.name)
        if previous is not None and previous is not mode:
            self.unregister(previous)
        self.modes[mode.name] = mode

    def unregister(self, mode):
        if self.modes.get(mode.name) is mode:
            self.stop(mode.name)
            self.modes.pop(mode.name)
            self.targets.pop(mode.name, None)

    def available_modes(self, surface):
        if not self.enabled or surface.frozen_map is not None:
            return ()
        return tuple(mode for mode in self.modes.values() if mode.available)

    def set_available(self, mode, available):
        mode.available = available
        if not available:
            self.stop(mode.name)

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
