import abc
from invesalius.pubsub import pub as Publisher

class Command(abc.ABC):
    @abc.abstractmethod
    def execute(self):
        pass

    @abc.abstractmethod
    def undo(self):
        pass

    @abc.abstractmethod
    def get_name(self) -> str:
        pass


class AddMaskCommand(Command):
    def __init__(self, mask):
        self.mask = mask
        self.index = None

    def execute(self):
        from invesalius.project import Project
        proj = Project()
        if self.index is None:
            self.index = proj.AddMask(self.mask)
        else:
            proj.InsertMask(self.index, self.mask)
        
        # Need to update UI about the newly added mask
        Publisher.sendMessage('Add mask', mask=self.mask)

    def undo(self):
        from invesalius.project import Project
        proj = Project()
        # RemoveMask must not cleanup the VTK/memory properties so we can redo
        proj.RemoveMask(self.index, cleanup=False)
        Publisher.sendMessage('Remove mask', index=self.index)

    def get_name(self) -> str:
        return "Add Mask"


class RemoveMaskCommand(Command):
    def __init__(self, index, mask):
        self.index = index
        self.mask = mask

    def execute(self):
        from invesalius.project import Project
        proj = Project()
        proj.RemoveMask(self.index, cleanup=False)
        Publisher.sendMessage('Remove mask', index=self.index)

    def undo(self):
        from invesalius.project import Project
        proj = Project()
        proj.InsertMask(self.index, self.mask)
        Publisher.sendMessage('Add mask', mask=self.mask)

    def get_name(self) -> str:
        return "Remove Mask"


class DuplicateMaskCommand(Command):
    def __init__(self, original_index, new_mask):
        self.original_index = original_index
        self.new_mask = new_mask
        self.new_index = None

    def execute(self):
        from invesalius.project import Project
        proj = Project()
        if self.new_index is None:
            self.new_index = proj.AddMask(self.new_mask)
        else:
            proj.InsertMask(self.new_index, self.new_mask)
        Publisher.sendMessage('Add mask', mask=self.new_mask)

    def undo(self):
        from invesalius.project import Project
        proj = Project()
        proj.RemoveMask(self.new_index, cleanup=False)
        Publisher.sendMessage('Remove mask', index=self.new_index)

    def get_name(self) -> str:
        return "Duplicate Mask"


class MaskEditCommand(Command):
    def __init__(self, mask, index, orientation, array, p_array, clean=False):
        self.mask = mask
        # Push the node to the mask's internal edition history
        self.mask.history.new_node(index, orientation, array, p_array, clean)
        self.actual_slices = None
        self._is_first_execute = True

    def execute(self):
        if self._is_first_execute:
            # First time, the edit is already applied in UI/Slice before this command is created.
            self._is_first_execute = False
            return
            
        # For redo, we actually need to apply it.
        if self.actual_slices is not None:
            self.mask.redo_history(self.actual_slices)
            self._discard_buffers_and_reload()

    def undo(self):
        import invesalius.data.slice_ as slc
        s = slc.Slice()
        buffer_slices = s.buffer_slices
        self.actual_slices = {
            "AXIAL": buffer_slices["AXIAL"].index,
            "CORONAL": buffer_slices["CORONAL"].index,
            "SAGITAL": buffer_slices["SAGITAL"].index,
            "VOLUME": 0,
        }
        self.mask.undo_history(self.actual_slices)
        self._discard_buffers_and_reload()

    def _discard_buffers_and_reload(self):
        import invesalius.data.slice_ as slc
        s = slc.Slice()
        for o in s.buffer_slices:
            s.buffer_slices[o].discard_mask()
            s.buffer_slices[o].discard_vtk_mask()
        Publisher.sendMessage("Reload actual slice")

    def get_name(self) -> str:
        return "Mask Edit"
