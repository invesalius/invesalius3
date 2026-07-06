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
import wx
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton

class HistoryManager(metaclass=Singleton):
    def __init__(self, max_history_size=50):
        self._undo_stack = []
        self._redo_stack = []
        self._max_history_size = max_history_size
        self._bind_events()

    def _bind_events(self):
        Publisher.subscribe(self.undo, "Undo edition")
        Publisher.subscribe(self.redo, "Redo edition")
        Publisher.subscribe(self.clear, "Close project data")

    def execute_command(self, command):
        """
        Executes a command and adds it to the undo stack.
        Clears the redo stack.
        """
        try:
            command.execute()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

        self._undo_stack.append(command)
        if len(self._undo_stack) > self._max_history_size:
            self._undo_stack.pop(0)

        self._redo_stack.clear()
        self._update_ui()
        return True

    def undo(self):
        if not self._undo_stack:
            return

        command = self._undo_stack.pop()
        try:
            command.undo()
        except Exception as e:
            import traceback
            traceback.print_exc()
            # If undo fails, we might be in an inconsistent state
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._update_ui()
            return

        self._redo_stack.append(command)
        self._update_ui()

    def redo(self):
        if not self._redo_stack:
            return

        command = self._redo_stack.pop()
        try:
            command.execute()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._update_ui()
            return

        self._undo_stack.append(command)
        self._update_ui()

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_ui()

    def _update_ui(self):
        undo_label = f"Undo {self._undo_stack[-1].get_name()}" if self._undo_stack else "Undo"
        redo_label = f"Redo {self._redo_stack[-1].get_name()}" if self._redo_stack else "Redo"
        
        Publisher.sendMessage("Update undo label", label=undo_label)
        Publisher.sendMessage("Update redo label", label=redo_label)
        Publisher.sendMessage("Enable undo", value=bool(self._undo_stack))
        Publisher.sendMessage("Enable redo", value=bool(self._redo_stack))
