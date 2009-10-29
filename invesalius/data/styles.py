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

import vtk

import constants as const

class ViewerStyle:
    def __init__(self):
        self.interactor = None
        self.style = None
        self.render = None
        
    def SetInteractor(self, interactor):

        # Setting style already defined in VTK
        if (self.style is None):
            self.style = vtk.vtkInteractorStyle()
        #self.style.SetInteractor(interactor)
        self.SetStyleConfig()
        interactor.SetInteractorStyle(style)

        # Saving data into attributes
        self.render = interactor.GetRenderWindow().GetRenderer()
        self.interactor = interactor
        
        # Call events
        self.__init_evt()

    def SetStyleConfig(self):
        print "calling parent"
        pass

    def __init_evt(self):
        style = self.style
        style.AddObserver("LeftButtonPressEvent", self.OnLeftButtonDown)
        style.AddObserver("LeftButtonReleaseEvent", self.OnLeftButtonUp)
        style.AddObserver("MiddleButtonPressEvent", self.OnMiddleButtonDown)
        style.AddObserver("MiddleButtonReleaseEvent", self.OnMiddleButtonUp)
        style.AddObserver("RightButtonPressEvent", self.OnRightButtonDown)
        style.AddObserver("RightButtonReleaseEvent", self.OnRightButtonUp)
        style.AddObserver("MouseWheelForwardEvent", self.OnScroll)
        style.AddObserver("MouseWheelBackwardEvent", self.OnScroll)

        style.AddObserver("MouseMoveEvent",self.OnMouseMove)
    
    def OnScroll(self, evt, str_evt):
        pass
    
    def OnLeftButtonDown(self, evt, str_evt):
        pass
    
    def OnLeftButtonUp(self, evt, str_evt):
        pass
    
    def OnMiddleButtonDown(self, evt, str_evt):
        pass
    
    def OnMiddleButtonUp(self, evt, str_evt):
        pass
    
    def OnRightButtonDown(self, evt, str_evt):
        pass
    
    def OnRightButtonUp(self, evt, str_evt):
        pass
    
    def OnMouseMove(self, evt, str_evt):
        pass
    
class ViewerStyleSlice(ViewerStyle):
    def __init__(self):
        ViewerStyle.__init__(self)
        self.orientation = 'AXIAL'
        
        self.style = vtk.vtkInteractorStyleImage()
        self.style.AutoAdjustCameraClippingRangeOn()
   
    def SetOrientation(self, orientation='AXIAL'):
        self.orientation = orientation
        
    def OnScroll(self, evt, evt_string):
        if evt_string == "MouseWheelForwardEvent":
            value = 1
        else: # elif evt_string =="MouseWheelBackwardEvent": 
            value = -1
        ps.Publisher().sendMessage(('Set scroll position', self.orientation), value)
        
class ViewerStyleSliceEditor(ViewerStyleSlice):

    def __init__(self):
        # FIXME: the idea is not using Slice from here...!
        #self.slice_ = slc.Slice()
        
        self.picker = vtk.vtkCellPicker() # define position where user clicked
        
        self.mouse_pressed = 0 # define if operation will executed run or not
        
        self.style = const.OP_ADD # define brush operation .OP_DEL, .OP_THRESH

        
    def SetData(self, actor_bounds, imagedata_dimensions):
        self.pos_converter = ViewerToImagedataPosConverter(actor_bounds,
                                                           imagedata_dimensions,
                                                           self.renderer)

    def SetStyleConfig(self):
        print "calling son"
        
    def SetOrientation(self, orient):
        
    def OnLeftButtonDown(self, evt, str_evt):
        self.mouse_pressed = 1
    
    def OnLeftButtonUp(self, evt, str_evt):
        self.mouse_pressed = 0
                
    def OnMouseMove(self, evt, str_evt):
        pos = self.interactor.GetEventPosition()
        wx = pos[0]
        wy = pos[1]

        self.pick.Pick(wx, wy, 0, self.render)
        x, y, z = self.picker.GetPickPosition()

        if self.mouse_pressed:
            #wx, wy = self.From3dToImagePixel(pos, (x, y, z))
            wx, wy = self.pos_converter.GetImagedataCoordinates(x, y, z)
            #self.CircleOperation(wx, wy, self.slice_) # TODO!
            ps.Publisher().sendMessage('Update edited imagedata', self.image)
            ps.Publisher().sendMessage('Update slice viewer', None)

        # update cursor
        self.cursor.SetPosition(x, y, z)  
        self.cursor.Update()

        obj.OnMouseMove()

        self.interactor.Render()
    
class ViewerToImagedataPosConverter():
    def __init__(self, actor_bounds, imagedata_dimensions, renderer):
        self.actor_bounds = actor_bounds
        self.imagedata_dimensions = imagedata_dimensions
        self.renderer = renderer
        
    def GetImagedataCoordinates(self, picker_position):
        x, y, z = picker_position

        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()
        c.SetValue(bounds[::2])
        xi, yi = c.GetComputedViewportValue(self.render)

        c.SetValue(bounds[1::2])
        xf, yf = c.GetComputedViewportValue(self.render)
        
        c.SetValue(x, y, z)
        wx, wy = c.GetComputedViewportValue(self.render)
        
        wx = wx - xi
        wy = wy - yi
        
        xf = xf - xi
        yf = yf - yi

        wx = (wx * self.imagedata_dimensions[0]) / xf
        wy = (wy * self.imagedata_dimensions[1]) / yf
        
        return wx, wy

################################################################################

#        style = vtk.vtkInteractorStyleImage()
#        style.SetInteractor(interactor)

#        interactor.SetInteractorStyle(style)
#        self.style = style

#self.interactor.SetCursor(cursors.ZOOM_IN_CURSOR)

################################################################################
