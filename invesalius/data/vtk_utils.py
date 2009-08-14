import wx.lib.pubsub as ps
import vtk

import constants as const

# If you are frightened by the code bellow, or think it must have been result of
# an identation error, lookup at:
# Closures in Python (pt)
# http://devlog.waltercruz.com/closures
# http://montegasppa.blogspot.com/2007/01/tampinhas.html
# Closures not only in Python (en)
# http://en.wikipedia.org/wiki/Closure_%28computer_science%29
# http://www.ibm.com/developerworks/library/l-prog2.html
# http://jjinux.blogspot.com/2006/10/python-modifying-counter-in-closure.html

def ShowProgress(number_of_filters = 1):
    """
    To use this closure, do something like this:
        UpdateProgress = ShowProgress(NUM_FILTERS)
        UpdateProgress(vtkObject)
    """
    progress = [0]
    last_obj_progress = [0]

    # when the pipeline is larger than 1, we have to consider this object
    # percentage
    ratio = 100.0 / number_of_filters
    
    def UpdateProgress(obj, label=""):
        """
        Show progress on GUI according to pipeline execution.
        """
        # object progress is cummulative and is between 0.0 - 1.0
        obj_progress = obj.GetProgress()
        
        # as it is cummulative, we need to compute the diference, to be
        # appended on the interface
        if obj_progress < last_obj_progress[0]: # current obj != previous obj
            difference = obj_progress # 0
        else: # current obj == previous obj
            difference = obj_progress - last_obj_progress[0]
        
        last_obj_progress[0] = obj_progress

        # final progress status value
        progress[0] = progress[0] + ratio*difference
        
        # Tell GUI to update progress status value
        ps.Publisher().sendMessage('Update status in GUI',
                                    (progress[0], label))
        return progress[0]
        
    return UpdateProgress

class Text(object):
    def __init__(self):

        property = vtk.vtkTextProperty()
        property.SetFontSize(const.TEXT_SIZE)
        property.SetFontFamilyToArial()
        property.BoldOff()
        property.ItalicOff()
        property.ShadowOn()
        property.SetJustificationToLeft()
        property.SetVerticalJustificationToTop()
        property.SetColor(const.TEXT_COLOUR)
        self.property = property

        mapper = vtk.vtkTextMapper()
        mapper.SetTextProperty(property)
        self.mapper = mapper

        x, y = const.TEXT_POSITION
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        actor.GetPositionCoordinate().SetValue(x,y)
        self.actor = actor

    def SetValue(self, value):
        self.mapper.SetInput(str(value))

    def SetPosition(self, position):
        self.actor.SetPositionCoordinate().SetValue(position)

    def Show(self, value=1):
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()
