import abc
import logging
from typing import List

class Command(abc.ABC):
    """
    Abstract base class for all undoable commands.
    """

    @abc.abstractmethod
    def execute(self):
        pass

    @abc.abstractmethod
    def undo(self):
        pass


    def redo(self):
        self.execute()

class CompositeCommand(Command):
    """
    Executes a list of commands sequentially. useful for batch operations.
    """
    def __init__(self):
        self._commands: List[Command] = []

    def add_command(self, command: Command):
        self._commands.append(command)

    def execute(self):
        for command in self._commands:
            command.execute()

    def undo(self):
        for command in reversed(self._commands):
            command.undo()


class UndoManager:
    """
    Manages the undo/redo stacks.
    """
    def __init__(self, max_history: int = 100):
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_history = max_history

    def execute(self, command: Command):
        """
        Executes a new command and adds it to the undo stack.
        Clears the redo stack.
        """
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._trim_history()

    def undo(self):
        """
        Undoes the last command.
        """
        if not self._undo_stack:
            return

        command = self._undo_stack.pop()
        try:
            command.undo()
        except Exception as e:
            logging.error(f"UndoManager.undo failed: {e}")
            import traceback
            traceback.print_exc()
        self._redo_stack.append(command)

    def redo(self):
        """
        Redoes the last undone command.
        """
        if not self._redo_stack:
            return

        command = self._redo_stack.pop()
        command.redo()
        self._undo_stack.append(command)

    def _trim_history(self):
        """
        Ensures the undo stack does not exceed the maximum history limit.
        """
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)  

    def clear(self):
        """
        Clears both undo and redo stacks.
        """
        self._undo_stack.clear()
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        """
        Returns True if there are commands to undo.
        """
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        """
        Returns True if there are commands to redo.
        """
        return bool(self._redo_stack)
