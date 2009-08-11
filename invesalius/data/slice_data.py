class SliceData(object):
    def __init__(self):
        self.renderer = None
        self.actor = None
        self.number = 0
        self.cursor = None

    def SetCursor(self, cursor):
        if self.cursor:
            self.renderer.RemoveActor(self.cursor.actor)
        self.renderer.AddActor(cursor.actor)
        self.cursor = cursor
