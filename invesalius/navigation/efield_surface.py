"""E-field processing lifecycle behind the common surface painting contract."""

from invesalius.navigation.surface_painting import SurfacePainting
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class EFieldSurfaceMode:
    name = "E-field"

    def __init__(self, navigation):
        self.navigation = navigation
        self.brain = None
        self.source_surface = None
        self.painting = SurfacePainting()
        self.painting.register(self)
        Publisher.subscribe(self.remove_surface, "Discard surface painting")
        Publisher.subscribe(self.clear, "Close project data")

    @property
    def available(self):
        return self.brain is not None and self.navigation.e_field_enabled

    @available.setter
    def available(self, enabled):
        self.navigation.e_field_enabled = enabled

    def configure(self, brain, surface):
        self.clear()
        self.brain = brain
        self.source_surface = surface

    def default_surface(self):
        return Project().GetBrainSurface() or self.source_surface

    def start(self, surface, token):
        self.navigation.MarkEfieldParametersChanged()
        Publisher.sendMessage(
            "Initialize E-field brain", e_field_brain=self.brain, painting_token=token
        )
        self.navigation.e_field_loaded = True

    def stop(self):
        self.navigation.e_field_loaded = False
        self.navigation.MarkEfieldParametersChanged()
        self.navigation.efield_queue.clear()
        self.navigation.e_field_norms_queue.clear()
        self.navigation.e_field_IDs_queue.clear()
        Publisher.sendMessage("Stop E-field surface painting")

    def remove_surface(self, surface):
        if surface is self.source_surface:
            self.clear()

    def clear(self):
        self.painting.set_available(self, False)
        self.brain = None
        self.source_surface = None
        self.painting.targets.pop(self.name, None)

    def dispose(self):
        self.clear()
        self.painting.unregister(self)
        Publisher.unsubscribe_owner(self)
