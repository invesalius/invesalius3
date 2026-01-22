from invesalius.data.command import Command
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class CreateMaskCommand(Command):
    def __init__(self, mask):
        self.mask = mask
        self.index = None

    def execute(self):
        self.index = Project().AddMask(self.mask)
        Publisher.sendMessage('Add mask', mask=self.mask)

    def undo(self):
        Project().RemoveMask(self.index)
        Publisher.sendMessage('Remove masks', mask_indexes=[self.index])



class DeleteMaskCommand(Command):
    def __init__(self, index):
        self.index = index
        self.mask = None

    def execute(self):
        project = Project()
        self.mask = project.GetMask(self.index)
        project.RemoveMask(self.index, cleanup=False)
        Publisher.sendMessage('Remove masks', mask_indexes=[self.index])

    def undo(self):
        if self.mask is None:
            return
        Project().InsertMask(self.index, self.mask)
        Publisher.sendMessage('Add mask', mask=self.mask)


class DuplicateMaskCommand(Command):
    def __init__(self, new_mask):
        self.new_mask = new_mask
        self.new_index = None

    def execute(self):
        self.new_index = Project().AddMask(self.new_mask)
        Publisher.sendMessage('Add mask', mask=self.new_mask)

    def undo(self):
        Project().RemoveMask(self.new_index, cleanup=False)
        Publisher.sendMessage('Remove masks', mask_indexes=[self.new_index])

