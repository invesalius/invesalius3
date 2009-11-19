#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------
import wx.lib.pubsub as ps
import vtk


import constants as const
from gui.dialogs import ProgressDialog 

# If you are frightened by the code bellow, or think it must have been result of
# an identation error, lookup at:
# Closures in Python (pt)
# http://devlog.waltercruz.com/closures
# http://montegasppa.blogspot.com/2007/01/tampinhas.html
# Closures not only in Python (en)
# http://en.wikipedia.org/wiki/Closure_%28computer_science%29
# http://www.ibm.com/developerworks/library/l-prog2.html
# http://jjinux.blogspot.com/2006/10/python-modifying-counter-in-closure.html

def ShowProgress(number_of_filters = 1,
                 dialog_type="GaugeProgress"):
    """
    To use this closure, do something like this:
        UpdateProgress = ShowProgress(NUM_FILTERS)
        UpdateProgress(vtkObject)
    """
    progress = [0]
    last_obj_progress = [0]
    if (dialog_type == "ProgressDialog"):
        dlg = ProgressDialog(100)
        

    # when the pipeline is larger than 1, we have to consider this object
    # percentage
    ratio = (100.0 / number_of_filters)
    
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
        if (dialog_type == "GaugeProgress"):
            ps.Publisher().sendMessage('Update status in GUI',
                                        (progress[0], label))
        else:
            if (int(progress[0]) == 99):
                progress[0] = 100
                
            if not(dlg.Update(progress[0],label)):
                dlg.Close()
            
        return progress[0]
        
    return UpdateProgress

class Text(object):
    def __init__(self):

        property = vtk.vtkTextProperty()
        property.SetFontSize(const.TEXT_SIZE)
        property.SetFontFamilyToArial()
        property.BoldOff()
        property.ItalicOff()
        property.ShadowOff()
        property.SetJustificationToLeft()
        property.SetVerticalJustificationToTop()
        property.SetColor(const.TEXT_COLOUR)
        self.property = property

        #mapper = vtk.vtkTextMapper()
        #mapper.SetTextProperty(property)
        #self.mapper = mapper

        x, y = const.TEXT_POSITION
        #actor = vtk.vtkActor2D()
        #actor.SetMapper(mapper)
        #actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        #actor.GetPositionCoordinate().SetValue(x,y)
        #self.actor = actor

        actor = vtk.vtkTextActor() 
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        actor.GetPositionCoordinate().SetValue(x,y) 
        actor.GetTextProperty().ShallowCopy(property) 
        self.actor = actor

    def BoldOn(self):
        self.property.BoldOn()
        self.actor.GetTextProperty().ShallowCopy(self.property)

    def SetColour(self, colour):
        self.property.SetColor(colour)
        self.actor.GetTextProperty().ShallowCopy(self.property)

    def SetSize(self, size):
        self.property.SetFontSize(size)
        self.actor.GetTextProperty().ShallowCopy(self.property)

    def SetValue(self, value):
        self.actor.SetInput(str(value))

    def SetPosition(self, position):
        self.actor.GetPositionCoordinate().SetValue(position[0],
                                                    position[1])

    def GetPosition(self, position):
        self.actor.GetPositionCoordinate().GetValue()

    def SetJustificationToRight(self):
        self.property.SetJustificationToRight()
        self.actor.GetTextProperty().ShallowCopy(self.property)

    def SetVerticalJustificationToBottom(self):
        self.property.SetVerticalJustificationToBottom()
        self.actor.GetTextProperty().ShallowCopy(self.property)

    def Show(self, value=1):
        if value:
            self.actor.VisibilityOn()
        else:
            self.actor.VisibilityOff()

    def Hide(self):
        self.actor.VisibilityOff()
