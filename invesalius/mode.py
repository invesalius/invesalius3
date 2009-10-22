# mode.py
# to be instanced inside Controller (control.py)


# TODO: Add to constants.py:
#--------------------
# SLICE MODE
SLICE_STATE_DEFAULT = 0
SLICE_STATE_EDITOR = 1
SLICE_STATE_WL = 2
SLICE_STATE_SPIN = 3
SLICE_STATE_ZOOM = 4
SLICE_STATE_ZOOM_SL = 5
# IMPORTANT: When adding a new state, remember o insert it into LEVEL
# dictionary


# RULE:
# default is the only level 0
# states controlled somehow by taskmenu are level 1
# states controlled by toolbar are level 2
LEVEL = {SLICE_STATE_DEFAULT: 0,
         SLICE_STATE_EDITOR: 1,
         SLICE_STATE_WL: 2,
         SLICE_STATE_SPIN: 2,
         SLICE_STATE_ZOOM: 2,
         SLICE_STATE_ZOOM_SL: 2}
#----------------------
# TODO: Add to viewer_slice.py:

    ps.Publisher().subscribe(self.OnSetMode, 'Set slice mode')

def OnSetMode(self, pubsub_evt):
    mode = pubsub_evt.data
    # according to mode, set cursor, interaction, etc
#----------------------
# TODO: Add GUI classes (frame, tasks related to slice, toolbar):

# always bind to this class (regarding slice mode) and not to
# viewer_slice directly

# example - pseudo code
def OnToggleButtonSpin(self, evt)
    if evt.toggle: # doesn't exist, just to illustrate
        ps.Publisher().sendMessage('Enable mode', const.SLICE_STATE_ZOOM)
    else:
        ps.Publisher().subscribe('Disable mode', const.SLICE_STATE_ZOOM)


#----------------------


import constants as const

class SliceMode(object):
# don't need to be singleton, only needs to be instantiated inside
# (Controller) self.slice_mode = SliceMode()

    def __init__(self):
        self.stack = {}

        # push default value to stack
        self.stack[const.LEVEL[const.SLICE_STATE_DEFAULT]] = \
                    const.SLICE_STATE_DEFAULT

        # bind pubsub evt
        self.bind_events()

    def _bind_events(self):
        ps.Publisher().subscribe(self.OnEnableState, 'Enable mode')
        ps.Publisher().subscribe(self.OnDisableState, 'Disable mode')

    def OnEnableState(self, pubsub_evt):
        state = pubsub_evt.data
        self.AddState(state)

    def OnDisableState(self, pubsub_evt):
        state = pubsub_evt.data
        self.RemoveState(state)

    def AddState(self, state):
        level = const.LEVEL[state]
        max_level = max(self.stack.keys())

        # Insert new state into stack
        self.stack[level] = state 

        # Only will affect InVesalius behaviour if it is the highest
        # level in stack
        if level == max_level:
            # let viewer slice and other classes know this
            # change (cursor, interaction, etc)
            ps.Publisher().sendMessage('Set slice mode', state)

    def RemoveState(self, state):
        level = const.LEVEL[state]
        max_level = max(self.stack.keys())

        # Remove item from stack
        self.stack.popitem(level)

        # New max level
        new_max_level =  max(self.stack.keys())

        # Only will affect InVesalius behaviour if the highest
        # level in stack has been removed
        if level == max_level:
            new_state = self.stack[new_max_level]
            ps.Publisher().sendMessage('Set slice mode', state)
             
