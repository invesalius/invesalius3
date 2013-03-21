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

from wx.lib.pubsub import pub as Publisher

import constants as const

class ZoomInteractorStyle(vtk.vtkInteractorStyleImage):
    """
    Interactor style responsible for zoom the camera.
    """
    def __init__(self):
        self.right_pressed = False

        # Zoom using right button
        self.AddObserver("RightButtonPressEvent",self.OnZoomRightClick)
        self.AddObserver("MouseMoveEvent", self.OnZoomRightMove)
        self.AddObserver("RightButtonReleaseEvent", self.OnZoomRightRelease)

    def OnZoomRightMove(self, evt, obj):
        if (self.right_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

    def OnZoomRightClick(self, evt, obj):
        self.right_pressed = 1
        evt.StartDolly()

    def OnZoomRightRelease(self, evt, obj):
        self.right_pressed = False

class CrossInteractorStyle(ZoomInteractorStyle):
    """
    Interactor style responsible for the Cross.
    """
    def __init__(self, orientation, slice_data):
        ZoomInteractorStyle.__init__(self)

        self.orientation = orientation
        self.slice_actor = slice_data.actor
        self.slice_data = slice_data

        self.left_pressed = False
        self.picker = vtk.vtkWorldPointPicker()

        self.AddObserver("MouseMoveEvent", self.OnCrossMove)
        self.AddObserver("LeftButtonPressEvent", self.OnCrossMouseClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

    def OnCrossMouseClick(self, obj, evt):
        self.left_pressed = True
        iren = obj.GetInteractor()
        self.ChangeCrossPosition(iren)

    def OnCrossMove(self, obj, evt):
        # The user moved the mouse with left button pressed
        if self.left_pressed:
            print "OnCrossMove interactor style"
            iren = obj.GetInteractor()
            self.ChangeCrossPosition(iren)

    def OnReleaseLeftButton(self, obj, evt):
        self.left_pressed = False

    def ChangeCrossPosition(self, iren):
        mouse_x, mouse_y = iren.GetEventPosition()
        ren = iren.GetRenderWindow().GetRenderers().GetFirstRenderer()
        self.picker.Pick(mouse_x, mouse_y, 0, ren)

        # Get in what slice data the click occurred
        # pick to get click position in the 3d world
        coord_cross = self.get_coordinate_cursor()
        position = self.slice_actor.GetInput().FindPoint(coord_cross)
        # Forcing focal point to be setted in the center of the pixel.
        coord_cross = self.slice_actor.GetInput().GetPoint(position)

        coord = self.calcultate_scroll_position(position)   
        self.ScrollSlice(coord)

        Publisher.sendMessage('Update cross position', coord_cross)
        Publisher.sendMessage('Set ball reference position based on bound',
                                   coord_cross)
        Publisher.sendMessage('Set camera in volume', coord_cross)
        Publisher.sendMessage('Render volume viewer')
        
        iren.Render()

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.picker.GetPickPosition()
        bounds = self.slice_actor.GetBounds()
        if bounds[0] == bounds[1]:
            x = bounds[0]
        elif bounds[2] == bounds[3]:
            y = bounds[2]
        elif bounds[4] == bounds[5]:
            z = bounds[4]
        return x, y, z

    def calcultate_scroll_position(self, position):
        # Based in the given coord (x, y, z), returns a list with the scroll positions for each
        # orientation, being the first position the sagital, second the coronal
        # and the last, axial.

        if self.orientation == 'AXIAL':
            image_width = self.slice_actor.GetInput().GetDimensions()[0]
            axial = self.slice_data.number
            coronal = position / image_width
            sagital = position % image_width

        elif self.orientation == 'CORONAL':
            image_width = self.slice_actor.GetInput().GetDimensions()[0]
            axial = position / image_width
            coronal = self.slice_data.number
            sagital = position % image_width

        elif self.orientation == 'SAGITAL':
            image_width = self.slice_actor.GetInput().GetDimensions()[1]
            axial = position / image_width
            coronal = position % image_width
            sagital = self.slice_data.number

        return sagital, coronal, axial

    def ScrollSlice(self, coord):
        if self.orientation == "AXIAL":
            Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])
            Publisher.sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
        elif self.orientation == "SAGITAL":
            Publisher.sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])
            Publisher.sendMessage(('Set scroll position', 'CORONAL'),
                                       coord[1])
        elif self.orientation == "CORONAL":
            Publisher.sendMessage(('Set scroll position', 'AXIAL'),
                                       coord[2])
            Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
                                       coord[0])


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
        pass
        
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
