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


# mode.py
# to be instanced inside Controller (control.py)


# IMPORTANT: When adding a new state, remember o insert it into LEVEL
# dictionary


# RULE:
# default is the only level 0
# states controlled somehow by taskmenu are level 1
# states controlled by toolbar are level 2
# LEVEL = {SLICE_STATE_DEFAULT: 0,
#         SLICE_STATE_EDITOR: 1,
#         SLICE_STATE_WL: 2,
#         SLICE_STATE_SPIN: 2,
#         SLICE_STATE_ZOOM: 2,
#         SLICE_STATE_ZOOM_SL: 2}
# ----------------------
# TODO: Add to viewer_slice.py:

# ps.Publisher().subscribe(self.OnSetMode, 'Set slice mode')

# def OnSetMode(self, pubsub_evt):
#    mode = pubsub_evt.data
# according to mode, set cursor, interaction, etc
# ----------------------
# TODO: Add GUI classes (frame, tasks related to slice, toolbar):

# always bind to this class (regarding slice mode) and not to
# viewer_slice directly

# example - pseudo code
# def OnToggleButtonSpin(self, evt)
#    if evt.toggle: # doesn't exist, just to illustrate
#        ps.Publisher().sendMessage('Enable mode', const.SLICE_STATE_ZOOM)
#    else:
#        ps.Publisher().subscribe('Disable mode', const.SLICE_STATE_ZOOM)


# ----------------------


import invesalius.constants as const


class StyleStateManager:
    # don't need to be singleton, only needs to be instantiated inside
    # (Controller) self.slice_mode = SliceMode()

    def __init__(self):
        self.stack: dict[int, int] = {}

        # push default value to stack
        self.stack[const.STYLE_LEVEL[const.STATE_DEFAULT]] = const.STATE_DEFAULT

    def AddState(self, state: int) -> int:
        level = const.STYLE_LEVEL[state]
        max(self.stack.keys())

        # Insert new state into stack
        self.stack[level] = state

        new_max_level = max(self.stack.keys())
        return self.stack[new_max_level]

    def RemoveState(self, state: int) -> int:
        level = const.STYLE_LEVEL[state]
        if level in self.stack.keys():
            max_level = max(self.stack.keys())

            # Remove item from stack
            self.stack.pop(level)

            # New max level
            new_max_level = max(self.stack.keys())

            # Only will affect InVesalius behaviour if the highest
            # level in stack has been removed
            if level == max_level:
                self.stack[new_max_level]

            return self.stack[new_max_level]

        max_level = max(self.stack.keys())
        return self.stack[max_level]

    def GetActualState(self) -> int:
        max_level = max(self.stack.keys())
        state = self.stack[max_level]
        return state

    def Reset(self) -> None:
        self.stack = {}
        self.stack[const.STYLE_LEVEL[const.STATE_DEFAULT]] = const.STATE_DEFAULT
