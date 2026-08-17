from invesalius.data.command import Command
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class CreateMaskCommand(Command):
    def __init__(self, mask):
        self.mask = mask
        self.index = None

    def execute(self):
        self.index = Project().AddMask(self.mask)
        Publisher.sendMessage("Add mask", mask=self.mask)

    def undo(self):
        if self.index is None:
            return
        Project().RemoveMask(self.index, cleanup=False)
        Publisher.sendMessage("Refresh Masks")


class DeleteMaskCommand(Command):
    def __init__(self, index):
        self.index = index
        self.mask = None

    def execute(self):
        project = Project()
        if self.index not in project.mask_dict:
            return
        self.mask = project.GetMask(self.index)
        # remove from project but don't cleanup (we need it for undo)
        project.RemoveMask(self.index, cleanup=False)
        Publisher.sendMessage("Remove masks", mask_indexes=[self.index])

    def undo(self):
        if self.mask is None:
            return
        Project().InsertMask(self.index, self.mask)
        Publisher.sendMessage("Refresh Masks")


class DuplicateMaskCommand(Command):
    def __init__(self, new_mask):
        self.new_mask = new_mask
        self.new_index = None

    def execute(self):
        self.new_index = Project().AddMask(self.new_mask)
        Publisher.sendMessage("Add mask", mask=self.new_mask)

    def undo(self):
        if self.new_index is None:
            return
        Project().RemoveMask(self.new_index, cleanup=False)
        Publisher.sendMessage("Refresh Masks")
