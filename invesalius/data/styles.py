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

import os
import multiprocessing
import tempfile
import time

import vtk
import wx

from wx.lib.pubsub import pub as Publisher

import constants as const
import converters
import cursor_actors as ca
import session as ses

import numpy as np

from scipy import ndimage
from scipy.misc import imsave
from scipy.ndimage import watershed_ift, generate_binary_structure
from skimage.morphology import watershed
from skimage import filter

import watershed_process

import utils

ORIENTATIONS = {
        "AXIAL": const.AXIAL,
        "CORONAL": const.CORONAL,
        "SAGITAL": const.SAGITAL,
        }

BRUSH_FOREGROUND=1
BRUSH_BACKGROUND=2
BRUSH_ERASE=0

WATERSHED_OPERATIONS = {_("Erase"): BRUSH_ERASE,
                        _("Foreground"): BRUSH_FOREGROUND,
                        _("Background"): BRUSH_BACKGROUND,}

def get_LUT_value(data, window, level):
    shape = data.shape
    data_ = data.ravel()
    data = np.piecewise(data_,
                        [data_ <= (level - 0.5 - (window-1)/2),
                         data_ > (level - 0.5 + (window-1)/2)],
                        [0, window, lambda data_: ((data_ - (level - 0.5))/(window-1) + 0.5)*(window)])
    data.shape = shape
    return data

class BaseImageInteractorStyle(vtk.vtkInteractorStyleImage):
    def __init__(self, viewer):
        self.right_pressed = False
        self.left_pressed = False
        self.middle_pressed = False

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.AddObserver("RightButtonPressEvent",self.OnPressRightButton)
        self.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)

        self.AddObserver("MiddleButtonPressEvent", self.OnMiddleButtonPressEvent)
        self.AddObserver("MiddleButtonReleaseEvent", self.OnMiddleButtonReleaseEvent)

    def OnPressLeftButton(self, evt, obj):
        self.left_pressed = True

    def OnReleaseLeftButton(self, evt, obj):
        self.left_pressed = False

    def OnPressRightButton(self, evt, obj):
        self.right_pressed = True
        self.viewer.last_position_mouse_move = \
            self.viewer.interactor.GetLastEventPosition()

    def OnReleaseRightButton(self, evt, obj):
        self.right_pressed = False

    def OnMiddleButtonPressEvent(self, evt, obj):
        self.middle_pressed = True

    def OnMiddleButtonReleaseEvent(self, evt, obj):
        self.middle_pressed = False


class DefaultInteractorStyle(BaseImageInteractorStyle):
    """
    Interactor style responsible for Default functionalities:
    * Zoom moving mouse with right button pressed;
    * Change the slices with the scroll.
    """
    def __init__(self, viewer):
        BaseImageInteractorStyle.__init__(self, viewer)

        self.viewer = viewer

        # Zoom using right button
        self.AddObserver("RightButtonPressEvent",self.OnZoomRightClick)
        self.AddObserver("MouseMoveEvent", self.OnZoomRightMove)

        self.AddObserver("MouseWheelForwardEvent",self.OnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)
        self.AddObserver("EnterEvent",self.OnFocus)

    def OnFocus(self, evt, obj):
        self.viewer.SetFocus()

    def OnZoomRightMove(self, evt, obj):
        if (self.right_pressed):
            evt.Dolly()
            evt.OnRightButtonDown()

        elif self.middle_pressed:
            evt.Pan()
            evt.OnMiddleButtonDown()

    def OnZoomRightClick(self, evt, obj):
        evt.StartDolly()

    def OnScrollForward(self, evt, obj):
        iren = self.viewer.interactor
        viewer = self.viewer
        if  iren.GetShiftKey():
            opacity = viewer.slice_.opacity + 0.1
            if opacity <= 1:
                viewer.slice_.opacity = opacity
                self.viewer.slice_.buffer_slices['AXIAL'].discard_vtk_mask()
                self.viewer.slice_.buffer_slices['CORONAL'].discard_vtk_mask()
                self.viewer.slice_.buffer_slices['SAGITAL'].discard_vtk_mask()
                Publisher.sendMessage('Reload actual slice')
        else:
            self.viewer.OnScrollForward()

    def OnScrollBackward(self, evt, obj):
        iren = self.viewer.interactor
        viewer = self.viewer

        if iren.GetShiftKey():
            opacity = viewer.slice_.opacity - 0.1
            if opacity >= 0.1:
                viewer.slice_.opacity = opacity
                self.viewer.slice_.buffer_slices['AXIAL'].discard_vtk_mask()
                self.viewer.slice_.buffer_slices['CORONAL'].discard_vtk_mask()
                self.viewer.slice_.buffer_slices['SAGITAL'].discard_vtk_mask()
                Publisher.sendMessage('Reload actual slice')
        else:
            self.viewer.OnScrollBackward()


class CrossInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for the Cross.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer
        self.orientation = viewer.orientation
        self.slice_actor = viewer.slice_data.actor
        self.slice_data = viewer.slice_data

        self.picker = vtk.vtkWorldPointPicker()

        self.AddObserver("MouseMoveEvent", self.OnCrossMove)
        self.AddObserver("LeftButtonPressEvent", self.OnCrossMouseClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

    def SetUp(self):
        self.viewer._set_cross_visibility(1)

    def CleanUp(self):
        self.viewer._set_cross_visibility(0)

    def OnCrossMouseClick(self, obj, evt):
        iren = obj.GetInteractor()
        self.ChangeCrossPosition(iren)

    def OnCrossMove(self, obj, evt):
        # The user moved the mouse with left button pressed
        if self.left_pressed:
            print "OnCrossMove interactor style"
            iren = obj.GetInteractor()
            self.ChangeCrossPosition(iren)

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
        Publisher.sendMessage('Update cross position', coord_cross)
        self.ScrollSlice(coord)
        Publisher.sendMessage('Set ball reference position based on bound',
                                   coord_cross)
        Publisher.sendMessage('Set camera in volume', coord_cross)
        Publisher.sendMessage('Render volume viewer')

        iren.Render()


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

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.picker.GetPickPosition()
        bounds = self.viewer.slice_data.actor.GetBounds()
        if bounds[0] == bounds[1]:
            x = bounds[0]
        elif bounds[2] == bounds[3]:
            y = bounds[2]
        elif bounds[4] == bounds[5]:
            z = bounds[4]
        return x, y, z


class WWWLInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for Window Level & Width functionality.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer =  viewer

        self.last_x = 0
        self.last_y = 0

        self.acum_achange_window = viewer.slice_.window_width
        self.acum_achange_level = viewer.slice_.window_level

        self.AddObserver("MouseMoveEvent", self.OnWindowLevelMove)
        self.AddObserver("LeftButtonPressEvent", self.OnWindowLevelClick)

    def SetUp(self):
        self.viewer.on_wl = True
        self.viewer.wl_text.Show()

    def CleanUp(self):
        self.viewer.on_wl = False
        self.viewer.wl_text.Hide()

    def OnWindowLevelMove(self, obj, evt):
        if (self.left_pressed):
            iren = obj.GetInteractor()
            mouse_x, mouse_y = iren.GetEventPosition()
            self.acum_achange_window += mouse_x - self.last_x
            self.acum_achange_level += mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y

            Publisher.sendMessage('Bright and contrast adjustment image',
                (self.acum_achange_window, self.acum_achange_level))

            #self.SetWLText(self.acum_achange_level,
            #              self.acum_achange_window)

            const.WINDOW_LEVEL['Manual'] = (self.acum_achange_window,\
                                           self.acum_achange_level)
            Publisher.sendMessage('Check window and level other')
            Publisher.sendMessage('Update window level value',(self.acum_achange_window,
                                                                self.acum_achange_level))
            #Necessary update the slice plane in the volume case exists
            Publisher.sendMessage('Update slice viewer')
            Publisher.sendMessage('Render volume viewer')

    def OnWindowLevelClick(self, obj, evt):
        iren = obj.GetInteractor()
        self.last_x, self.last_y = iren.GetLastEventPosition()

        self.acum_achange_window = viewer.slice_.window_width
        self.acum_achange_level = viewer.slice_.window_level


class LinearMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert linear measurements.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer
        self.orientation = viewer.orientation
        self.slice_data = viewer.slice_data

        spacing = self.slice_data.actor.GetInput().GetSpacing()

        if self.orientation == "AXIAL":
            self.radius = min(spacing[1], spacing[2]) * 0.8

        elif self.orientation == 'CORONAL':
            self.radius = min(spacing[0], spacing[1]) * 0.8

        elif self.orientation == 'SAGITAL':
            self.radius = min(spacing[1], spacing[2]) * 0.8

        self.picker = vtk.vtkCellPicker()

        self.AddObserver("LeftButtonPressEvent", self.OnInsertLinearMeasurePoint)

    def OnInsertLinearMeasurePoint(self, obj, evt):
        iren = obj.GetInteractor()
        x,y = iren.GetEventPosition()
        render = iren.FindPokedRenderer(x, y)
        slice_number = self.slice_data.number
        self.picker.Pick(x, y, 0, render)
        x, y, z = self.picker.GetPickPosition()
        if self.picker.GetViewProp():
            Publisher.sendMessage("Add measurement point",
                                  ((x, y,z), const.LINEAR,
                                   ORIENTATIONS[self.orientation],
                                   slice_number, self.radius))
            self.viewer.interactor.Render()

    def CleanUp(self):
        Publisher.sendMessage("Remove incomplete measurements")


class AngularMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert angular measurements.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer
        self.orientation = viewer.orientation
        self.slice_data = viewer.slice_data

        spacing = self.slice_data.actor.GetInput().GetSpacing()

        if self.orientation == "AXIAL":
            self.radius = min(spacing[1], spacing[2]) * 0.8

        elif self.orientation == 'CORONAL':
            self.radius = min(spacing[0], spacing[1]) * 0.8

        elif self.orientation == 'SAGITAL':
            self.radius = min(spacing[1], spacing[2]) * 0.8

        self.picker = vtk.vtkCellPicker()

        self.AddObserver("LeftButtonPressEvent", self.OnInsertAngularMeasurePoint)

    def OnInsertAngularMeasurePoint(self, obj, evt):
        iren = obj.GetInteractor()
        x,y = iren.GetEventPosition()
        render = iren.FindPokedRenderer(x, y)
        slice_number = self.slice_data.number
        self.picker.Pick(x, y, 0, render)
        x, y, z = self.picker.GetPickPosition()
        if self.picker.GetViewProp():
            Publisher.sendMessage("Add measurement point",
                                  ((x, y,z), const.ANGULAR,
                                   ORIENTATIONS[self.orientation],
                                   slice_number, self.radius))
            self.viewer.interactor.Render()


class PanMoveInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for translate the camera.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnPanMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspan)

    def OnPanMove(self, obj, evt):
        if self.left_pressed:
            obj.Pan()
            obj.OnRightButtonDown()

    def OnUnspan(self, evt):
        iren = self.viewer.interactor
        mouse_x, mouse_y = iren.GetLastEventPosition()
        ren = iren.FindPokedRenderer(mouse_x, mouse_y)
        ren.ResetCamera()
        iren.Render()


class SpinInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for spin the camera.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnSpinMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspin)

    def OnSpinMove(self, obj, evt):
        iren = obj.GetInteractor()
        mouse_x, mouse_y = iren.GetLastEventPosition()
        ren = iren.FindPokedRenderer(mouse_x, mouse_y)
        cam = ren.GetActiveCamera()
        if (self.left_pressed):
            self.viewer.UpdateTextDirection(cam)
            obj.Spin()
            obj.OnRightButtonDown()

    def OnUnspin(self, evt):
        orig_orien = 1
        iren = self.viewer.interactor
        mouse_x, mouse_y = iren.GetLastEventPosition()
        ren = iren.FindPokedRenderer(mouse_x, mouse_y)
        cam = ren.GetActiveCamera()
        cam.SetViewUp(const.SLICE_POSITION[orig_orien][0][self.viewer.orientation])
        self.viewer.ResetTextDirection(cam)
        iren.Render()


class ZoomInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for zoom with movement of the mouse and the
    left mouse button clicked.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnZoomMoveLeft)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

    def OnZoomMoveLeft(self, obj, evt):
        if self.left_pressed:
            obj.Dolly()
            obj.OnRightButtonDown()

    def OnUnZoom(self, evt):
        mouse_x, mouse_y = self.viewer.interactor.GetLastEventPosition()
        ren = self.viewer.interactor.FindPokedRenderer(mouse_x, mouse_y)
        #slice_data = self.get_slice_data(ren)
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        #self.Reposition(slice_data)
        self.viewer.interactor.Render()


class ZoomSLInteractorStyle(vtk.vtkInteractorStyleRubberBandZoom):
    """
    Interactor style responsible for zoom by selecting a region.
    """
    def __init__(self, viewer):
        self.viewer = viewer
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

    def OnUnZoom(self, evt):
        mouse_x, mouse_y = self.viewer.interactor.GetLastEventPosition()
        ren = self.viewer.interactor.FindPokedRenderer(mouse_x, mouse_y)
        #slice_data = self.get_slice_data(ren)
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        #self.Reposition(slice_data)
        self.viewer.interactor.Render()


class ChangeSliceInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for change slice moving the mouse.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnChangeSliceMove)
        self.AddObserver("LeftButtonPressEvent", self.OnChangeSliceClick)

    def OnChangeSliceMove(self, evt, obj):
        if self.left_pressed:
            min = 0
            max = self.viewer.slice_.GetMaxSliceNumber(self.viewer.orientation)

            position = self.viewer.interactor.GetLastEventPosition()
            scroll_position = self.viewer.scroll.GetThumbPosition()

            if (position[1] > self.last_position) and\
                            (self.acum_achange_slice > min):
                self.acum_achange_slice -= 1
            elif(position[1] < self.last_position) and\
                            (self.acum_achange_slice < max):
                 self.acum_achange_slice += 1
            self.last_position = position[1]

            self.viewer.scroll.SetThumbPosition(self.acum_achange_slice)
            self.viewer.OnScrollBar()

    def OnChangeSliceClick(self, evt, obj):
        position = self.viewer.interactor.GetLastEventPosition()
        self.acum_achange_slice = self.viewer.scroll.GetThumbPosition()
        self.last_position = position[1]


class EditorConfig(object):
    __metaclass__= utils.Singleton
    def __init__(self):
        self.operation = const.BRUSH_THRESH
        self.cursor_type = const.BRUSH_CIRCLE
        self.cursor_size = const.BRUSH_SIZE


class EditorInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer
        self.orientation = self.viewer.orientation

        self.config = EditorConfig()

        self.picker = vtk.vtkWorldPointPicker()

        self.AddObserver("EnterEvent", self.OnEnterInteractor)
        self.AddObserver("LeaveEvent", self.OnLeaveInteractor)

        self.AddObserver("LeftButtonPressEvent", self.OnBrushClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnBrushRelease)
        self.AddObserver("MouseMoveEvent", self.OnBrushMove)

        self.RemoveObservers("MouseWheelForwardEvent")
        self.RemoveObservers("MouseWheelBackwardEvent")
        self.AddObserver("MouseWheelForwardEvent",self.EOnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.EOnScrollBackward)

        Publisher.subscribe(self.set_bsize, 'Set edition brush size')
        Publisher.subscribe(self.set_bformat, 'Set brush format')
        Publisher.subscribe(self.set_boperation, 'Set edition operation')

        self._set_cursor()
        self.viewer.slice_data.cursor.Show(0)

    def CleanUp(self):
        Publisher.unsubscribe(self.set_bsize, 'Set edition brush size')
        Publisher.unsubscribe(self.set_bformat, 'Set brush format')
        Publisher.unsubscribe(self.set_boperation, 'Set edition operation')

    def set_bsize(self, pubsub_evt):
        size = pubsub_evt.data
        self.config.cursor_size = size
        self.viewer.slice_data.cursor.SetSize(size)

    def set_bformat(self, pubsub_evt):
        self.config.cursor_type = pubsub_evt.data
        self._set_cursor()

    def set_boperation(self, pubsub_evt):
        self.config.operation = pubsub_evt.data

    def _set_cursor(self):
        if self.config.cursor_type == const.BRUSH_SQUARE:
            cursor = ca.CursorRectangle()
        elif self.config.cursor_type == const.BRUSH_CIRCLE:
            cursor = ca.CursorCircle()

        cursor.SetOrientation(self.orientation)
        n = self.viewer.slice_data.number
        coordinates = {"SAGITAL": [n, 0, 0],
                       "CORONAL": [0, n, 0],
                       "AXIAL": [0, 0, n]}
        cursor.SetPosition(coordinates[self.orientation])
        spacing = self.viewer.slice_.spacing
        cursor.SetSpacing(spacing)
        cursor.SetColour(self.viewer._brush_cursor_colour)
        cursor.SetSize(self.config.cursor_size)
        self.viewer.slice_data.SetCursor(cursor)

    def OnEnterInteractor(self, obj, evt):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return
        self.viewer.slice_data.cursor.Show()
        self.viewer.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        self.viewer.interactor.Render()

    def OnLeaveInteractor(self, obj, evt):
        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def OnBrushClick(self, obj, evt):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return

        viewer = self.viewer
        iren = viewer.interactor

        operation = self.config.operation
        if operation == const.BRUSH_THRESH:
            if iren.GetControlKey():
                if iren.GetShiftKey():
                    operation = const.BRUSH_THRESH_ERASE_ONLY
                else:
                    operation = const.BRUSH_THRESH_ERASE
            elif iren.GetShiftKey():
                operation = const.BRUSH_THRESH_ADD_ONLY

        elif operation == const.BRUSH_ERASE and iren.GetControlKey():
            operation = const.BRUSH_DRAW

        elif operation == const.BRUSH_DRAW and iren.GetControlKey():
            operation = const.BRUSH_ERASE

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = iren.GetEventPosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)
        slice_data.cursor.Show()

        self.picker.Pick(mouse_x, mouse_y, 0, render)

        coord = self.get_coordinate_cursor()
        position = slice_data.actor.GetInput().FindPoint(coord)

        if position != -1:
            coord = slice_data.actor.GetInput().GetPoint(position)

        slice_data.cursor.SetPosition(coord)
        cursor = slice_data.cursor
        radius = cursor.radius

        if position < 0:
            position = viewer.calculate_matrix_position(coord)

        viewer.slice_.edit_mask_pixel(operation, cursor.GetPixels(),
                                    position, radius, viewer.orientation)
        #viewer._flush_buffer = True

        # TODO: To create a new function to reload images to viewer.
        viewer.OnScrollBar()

    def OnBrushMove(self, obj, evt):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = iren.GetEventPosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        operation = self.config.operation
        if operation == const.BRUSH_THRESH:
            if iren.GetControlKey():
                if iren.GetShiftKey():
                    operation = const.BRUSH_THRESH_ERASE_ONLY
                else:
                    operation = const.BRUSH_THRESH_ERASE
            elif iren.GetShiftKey():
                operation = const.BRUSH_THRESH_ADD_ONLY

        elif operation == const.BRUSH_ERASE and iren.GetControlKey():
            operation = const.BRUSH_DRAW

        elif operation == const.BRUSH_DRAW and iren.GetControlKey():
            operation = const.BRUSH_ERASE

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)

        self.picker.Pick(mouse_x, mouse_y, 0, render)

        #if (self.pick.GetViewProp()):
            #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        #else:
            #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

        coord = self.get_coordinate_cursor()
        position = viewer.slice_data.actor.GetInput().FindPoint(coord)

        # when position == -1 the cursos is not over the image, so is not
        # necessary to set the cursor position to world coordinate center of
        # pixel from slice image.
        if position != -1:
            coord = slice_data.actor.GetInput().GetPoint(position)
        slice_data.cursor.SetPosition(coord)
        #self.__update_cursor_position(slice_data, coord)

        if (self.left_pressed):
            cursor = slice_data.cursor
            position = slice_data.actor.GetInput().FindPoint(coord)
            radius = cursor.radius

            if position < 0:
                position = viewer.calculate_matrix_position(coord)

            viewer.slice_.edit_mask_pixel(operation, cursor.GetPixels(),
                                        position, radius, self.orientation)
            # TODO: To create a new function to reload images to viewer.
            viewer.OnScrollBar(update3D=False)

        else:
            viewer.interactor.Render()

    def OnBrushRelease(self, evt, obj):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return

        self.viewer._flush_buffer = True
        self.viewer.slice_.apply_slice_buffer_to_mask(self.orientation)
        self.viewer._flush_buffer = False

    def EOnScrollForward(self, evt, obj):
        iren = self.viewer.interactor
        viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = iren.GetEventPosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size += 1

            if size <= 100:
                Publisher.sendMessage('Set edition brush size', size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollForward(obj, evt)

    def EOnScrollBackward(self, evt, obj):
        iren = self.viewer.interactor
        viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = iren.GetEventPosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size -= 1

            if size > 0:
                Publisher.sendMessage('Set edition brush size', size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollBackward(obj, evt)

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.picker.GetPickPosition()
        bounds = self.viewer.slice_data.actor.GetBounds()
        if bounds[0] == bounds[1]:
            x = bounds[0]
        elif bounds[2] == bounds[3]:
            y = bounds[2]
        elif bounds[4] == bounds[5]:
            z = bounds[4]
        return x, y, z


class WatershedProgressWindow(object):
    def __init__(self, process):
        self.process = process
        self.title = "InVesalius 3"
        self.msg = _("Applying watershed ...")
        self.style = wx.PD_APP_MODAL | wx.PD_APP_MODAL | wx.PD_CAN_ABORT

        self.dlg = wx.ProgressDialog(self.title,
                                     self.msg,
                                     parent = None,
                                     style  = self.style)

        self.dlg.Bind(wx.EVT_BUTTON, self.Cancel)
        self.dlg.Show()

    def Cancel(self, evt):
        self.process.terminate()

    def Update(self):
        self.dlg.Pulse()

    def Close(self):
        self.dlg.Destroy()


class WatershedConfig(object):
    __metaclass__= utils.Singleton
    def __init__(self):
        self.algorithm = "Watershed"
        self.con_2d = 4
        self.con_3d = 6
        self.mg_size = 3
        self.use_ww_wl = True
        self.operation = BRUSH_FOREGROUND
        self.cursor_type = const.BRUSH_CIRCLE
        self.cursor_size = const.BRUSH_SIZE

        Publisher.subscribe(self.set_operation, 'Set watershed operation')
        Publisher.subscribe(self.set_use_ww_wl, 'Set use ww wl')

        Publisher.subscribe(self.set_algorithm, "Set watershed algorithm")
        Publisher.subscribe(self.set_2dcon, "Set watershed 2d con")
        Publisher.subscribe(self.set_3dcon, "Set watershed 3d con")
        Publisher.subscribe(self.set_gaussian_size, "Set watershed gaussian size")

    def set_operation(self, pubsub_evt):
        self.operation = WATERSHED_OPERATIONS[pubsub_evt.data]

    def set_use_ww_wl(self, pubsub_evt):
        self.use_ww_wl = pubsub_evt.data

    def set_algorithm(self, pubsub_evt):
        self.algorithm = pubsub_evt.data

    def set_2dcon(self, pubsub_evt):
        self.con_2d = pubsub_evt.data

    def set_3dcon(self, pubsub_evt):
        self.con_3d = pubsub_evt.data

    def set_gaussian_size(self, pubsub_evt):
        self.mg_size = pubsub_evt.data

WALGORITHM = {"Watershed": watershed,
             "Watershed IFT": watershed_ift}
CON2D = {4: 1, 8: 2}
CON3D = {6: 1, 18: 2, 26: 3}

class WaterShedInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer
        self.orientation = self.viewer.orientation
        self.matrix = None

        self.config = WatershedConfig()

        self.picker = vtk.vtkWorldPointPicker()

        self.AddObserver("EnterEvent", self.OnEnterInteractor)
        self.AddObserver("LeaveEvent", self.OnLeaveInteractor)

        self.RemoveObservers("MouseWheelForwardEvent")
        self.RemoveObservers("MouseWheelBackwardEvent")
        self.AddObserver("MouseWheelForwardEvent",self.WOnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.WOnScrollBackward)

        self.AddObserver("LeftButtonPressEvent", self.OnBrushClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnBrushRelease)
        self.AddObserver("MouseMoveEvent", self.OnBrushMove)

        Publisher.subscribe(self.expand_watershed, 'Expand watershed to 3D ' + self.orientation)
        Publisher.subscribe(self.set_bsize, 'Set watershed brush size')
        Publisher.subscribe(self.set_bformat, 'Set watershed brush format')

        self._set_cursor()
        self.viewer.slice_data.cursor.Show(0)

    def SetUp(self):
        mask = self.viewer.slice_.current_mask.matrix
        self._create_mask()
        self.viewer.slice_.to_show_aux = 'watershed'
        self.viewer.OnScrollBar()

    def CleanUp(self):
        #self._remove_mask()
        Publisher.unsubscribe(self.expand_watershed, 'Expand watershed to 3D ' + self.orientation)
        Publisher.unsubscribe(self.set_bformat, 'Set watershed brush format')
        Publisher.unsubscribe(self.set_bsize, 'Set watershed brush size')
        self.RemoveAllObservers()
        self.viewer.slice_.to_show_aux = ''
        self.viewer.OnScrollBar()

    def _create_mask(self):
        if self.matrix is None:
            try:
                self.matrix = self.viewer.slice_.aux_matrices['watershed']
            except KeyError:
                self.temp_file, self.matrix = self.viewer.slice_.create_temp_mask()
                self.viewer.slice_.aux_matrices['watershed'] = self.matrix

    def _remove_mask(self):
        if self.matrix is not None:
            self.matrix = None
            os.remove(self.temp_file)
            print "deleting", self.temp_file

    def _set_cursor(self):
        if self.config.cursor_type == const.BRUSH_SQUARE:
            cursor = ca.CursorRectangle()
        elif self.config.cursor_type == const.BRUSH_CIRCLE:
            cursor = ca.CursorCircle()

        cursor.SetOrientation(self.orientation)
        n = self.viewer.slice_data.number
        coordinates = {"SAGITAL": [n, 0, 0],
                       "CORONAL": [0, n, 0],
                       "AXIAL": [0, 0, n]}
        cursor.SetPosition(coordinates[self.orientation])
        spacing = self.viewer.slice_.spacing
        cursor.SetSpacing(spacing)
        cursor.SetColour(self.viewer._brush_cursor_colour)
        cursor.SetSize(self.config.cursor_size)
        self.viewer.slice_data.SetCursor(cursor)

    def set_bsize(self, pubsub_evt):
        size = pubsub_evt.data
        self.config.cursor_size = size
        self.viewer.slice_data.cursor.SetSize(size)

    def set_bformat(self, pubsub_evt):
        self.config.cursor_type = pubsub_evt.data
        self._set_cursor()

    def OnEnterInteractor(self, obj, evt):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return
        self.viewer.slice_data.cursor.Show()
        self.viewer.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        self.viewer.interactor.Render()

    def OnLeaveInteractor(self, obj, evt):
        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def WOnScrollBackward(self, obj, evt):
        iren = self.viewer.interactor
        viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = iren.GetEventPosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size -= 1

            if size > 0:
                Publisher.sendMessage('Set watershed brush size', size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollBackward(obj, evt)

    def WOnScrollForward(self, obj, evt):
        iren = self.viewer.interactor
        viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = iren.GetEventPosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size += 1

            if size <= 100:
                Publisher.sendMessage('Set watershed brush size', size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollForward(obj, evt)

    def OnBrushClick(self, obj, evt):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = iren.GetEventPosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)
        slice_data.cursor.Show()

        self.picker.Pick(mouse_x, mouse_y, 0, render)

        coord = self.get_coordinate_cursor()
        position = slice_data.actor.GetInput().FindPoint(coord)

        if position != -1:
            coord = slice_data.actor.GetInput().GetPoint(position)

        slice_data.cursor.SetPosition(coord)

        cursor = slice_data.cursor
        position = slice_data.actor.GetInput().FindPoint(coord)
        radius = cursor.radius

        if position < 0:
            position = viewer.calculate_matrix_position(coord)

        operation = self.config.operation

        if operation == BRUSH_FOREGROUND:
            if iren.GetControlKey():
                operation = BRUSH_BACKGROUND
            elif iren.GetShiftKey():
                operation = BRUSH_ERASE
        elif operation == BRUSH_BACKGROUND:
            if iren.GetControlKey():
                operation = BRUSH_FOREGROUND
            elif iren.GetShiftKey():
                operation = BRUSH_ERASE

        n = self.viewer.slice_data.number
        self.edit_mask_pixel(operation, n, cursor.GetPixels(),
                                    position, radius, self.orientation)
        if self.orientation == 'AXIAL':
            mask = self.matrix[n, :, :]
        elif self.orientation == 'CORONAL':
            mask = self.matrix[:, n, :]
        elif self.orientation == 'SAGITAL':
            mask = self.matrix[:, :, n]
        # TODO: To create a new function to reload images to viewer.
        viewer.OnScrollBar()

    def OnBrushMove(self, obj, evt):
        if (self.viewer.slice_.buffer_slices[self.orientation].mask is None):
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = iren.GetEventPosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        # TODO: Improve!
        #for i in self.slice_data_list:
            #i.cursor.Show(0)

        self.picker.Pick(mouse_x, mouse_y, 0, render)

        #if (self.pick.GetViewProp()):
            #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_BLANK))
        #else:
            #self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

        coord = self.get_coordinate_cursor()
        position = viewer.slice_data.actor.GetInput().FindPoint(coord)

        # when position == -1 the cursos is not over the image, so is not
        # necessary to set the cursor position to world coordinate center of
        # pixel from slice image.
        if position != -1:
            coord = slice_data.actor.GetInput().GetPoint(position)
        slice_data.cursor.SetPosition(coord)
        #self.__update_cursor_position(slice_data, coord)

        if (self.left_pressed):
            cursor = slice_data.cursor
            position = slice_data.actor.GetInput().FindPoint(coord)
            radius = cursor.radius

            if position < 0:
                position = viewer.calculate_matrix_position(coord)

            operation = self.config.operation

            if operation == BRUSH_FOREGROUND:
                if iren.GetControlKey():
                    operation = BRUSH_BACKGROUND
                elif iren.GetShiftKey():
                    operation = BRUSH_ERASE
            elif operation == BRUSH_BACKGROUND:
                if iren.GetControlKey():
                    operation = BRUSH_FOREGROUND
                elif iren.GetShiftKey():
                    operation = BRUSH_ERASE

            n = self.viewer.slice_data.number
            self.edit_mask_pixel(operation, n, cursor.GetPixels(),
                                        position, radius, self.orientation)
            if self.orientation == 'AXIAL':
                mask = self.matrix[n, :, :]
            elif self.orientation == 'CORONAL':
                mask = self.matrix[:, n, :]
            elif self.orientation == 'SAGITAL':
                mask = self.matrix[:, :, n]
            # TODO: To create a new function to reload images to viewer.
            viewer.OnScrollBar(update3D=False)

        else:
            viewer.interactor.Render()

    def OnBrushRelease(self, evt, obj):
        n = self.viewer.slice_data.number
        self.viewer.slice_.discard_all_buffers()
        if self.orientation == 'AXIAL':
            image = self.viewer.slice_.matrix[n]
            mask = self.viewer.slice_.current_mask.matrix[n+1, 1:, 1:]
            self.viewer.slice_.current_mask.matrix[n+1, 0, 0] = 1
            markers = self.matrix[n]

        elif self.orientation == 'CORONAL':
            image = self.viewer.slice_.matrix[:, n, :]
            mask = self.viewer.slice_.current_mask.matrix[1:, n+1, 1:]
            self.viewer.slice_.current_mask.matrix[0, n+1, 0]
            markers = self.matrix[:, n, :]

        elif self.orientation == 'SAGITAL':
            image = self.viewer.slice_.matrix[:, :, n]
            mask = self.viewer.slice_.current_mask.matrix[1: , 1:, n+1]
            self.viewer.slice_.current_mask.matrix[0 , 0, n+1]
            markers = self.matrix[:, :, n]


        ww = self.viewer.slice_.window_width
        wl = self.viewer.slice_.window_level

        if BRUSH_BACKGROUND in markers and BRUSH_FOREGROUND in markers:
            #w_algorithm = WALGORITHM[self.config.algorithm]
            bstruct = generate_binary_structure(2, CON2D[self.config.con_2d])
            if self.config.use_ww_wl:
                if self.config.algorithm == 'Watershed':
                    tmp_image = ndimage.morphological_gradient(
                                   get_LUT_value(image, ww, wl).astype('uint16'),
                                   self.config.mg_size)
                    tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
                else:
                    #tmp_image = ndimage.gaussian_filter(get_LUT_value(image, ww, wl).astype('uint16'), self.config.mg_size)
                    #tmp_image = ndimage.morphological_gradient(
                                   #get_LUT_value(image, ww, wl).astype('uint16'),
                                   #self.config.mg_size)
                    tmp_image = get_LUT_value(image, ww, wl).astype('uint16')
                    #markers[markers == 2] = -1
                    tmp_mask = watershed_ift(tmp_image, markers.astype('int16'), bstruct)
                    #markers[markers == -1] = 2
                    #tmp_mask[tmp_mask == -1]  = 2

            else:
                if self.config.algorithm == 'Watershed':
                    tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
                    tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
                else:
                    #tmp_image = (image - image.min()).astype('uint16')
                    #tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
                    #tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
                    tmp_image = image - image.min().astype('uint16')
                    tmp_mask = watershed_ift(tmp_image, markers.astype('int16'), bstruct)

            if self.viewer.overwrite_mask:
                mask[:] = 0
                mask[tmp_mask == 1] = 253
            else:
                mask[(tmp_mask==2) & ((mask == 0) | (mask == 2) | (mask == 253))] = 2
                mask[(tmp_mask==1) & ((mask == 0) | (mask == 2) | (mask == 253))] = 253


            self.viewer.slice_.current_mask.was_edited = True
            self.viewer.slice_.current_mask.clear_history()

            # Marking the project as changed
            session = ses.Session()
            session.ChangeProject()

        Publisher.sendMessage('Reload actual slice')

    def get_coordinate_cursor(self):
        # Find position
        x, y, z = self.picker.GetPickPosition()
        bounds = self.viewer.slice_data.actor.GetBounds()
        if bounds[0] == bounds[1]:
            x = bounds[0]
        elif bounds[2] == bounds[3]:
            y = bounds[2]
        elif bounds[4] == bounds[5]:
            z = bounds[4]
        return x, y, z

    def edit_mask_pixel(self, operation, n, index, position, radius, orientation):
        if orientation == 'AXIAL':
            mask = self.matrix[n, :, :]
        elif orientation == 'CORONAL':
            mask = self.matrix[:, n, :]
        elif orientation == 'SAGITAL':
            mask = self.matrix[:, :, n]

        spacing = self.viewer.slice_.spacing
        if hasattr(position, '__iter__'):
            py, px = position
            if orientation == 'AXIAL':
                sx = spacing[0]
                sy = spacing[1]
            elif orientation == 'CORONAL':
                sx = spacing[0]
                sy = spacing[2]
            elif orientation == 'SAGITAL':
                sx = spacing[2]
                sy = spacing[1]

        else:
            if orientation == 'AXIAL':
                sx = spacing[0]
                sy = spacing[1]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == 'CORONAL':
                sx = spacing[0]
                sy = spacing[2]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == 'SAGITAL':
                sx = spacing[2]
                sy = spacing[1]
                py = position / mask.shape[1]
                px = position % mask.shape[1]

        cx = index.shape[1] / 2 + 1
        cy = index.shape[0] / 2 + 1
        xi = px - index.shape[1] + cx
        xf = xi + index.shape[1]
        yi = py - index.shape[0] + cy
        yf = yi + index.shape[0]

        if yi < 0:
            index = index[abs(yi):,:]
            yi = 0
        if yf > mask.shape[0]:
            index = index[:index.shape[0]-(yf-mask.shape[0]), :]
            yf = mask.shape[0]

        if xi < 0:
            index = index[:,abs(xi):]
            xi = 0
        if xf > mask.shape[1]:
            index = index[:,:index.shape[1]-(xf-mask.shape[1])]
            xf = mask.shape[1]

        # Verifying if the points is over the image array.
        if (not 0 <= xi <= mask.shape[1] and not 0 <= xf <= mask.shape[1]) or \
           (not 0 <= yi <= mask.shape[0] and not 0 <= yf <= mask.shape[0]):
            return

        roi_m = mask[yi:yf,xi:xf]

        # Checking if roi_i has at least one element.
        if roi_m.size:
            roi_m[index] = operation

    def expand_watershed(self, pubsub_evt):
        markers = self.matrix
        image = self.viewer.slice_.matrix
        self.viewer.slice_.do_threshold_to_all_slices()
        mask = self.viewer.slice_.current_mask.matrix[1:, 1:, 1:]
        ww = self.viewer.slice_.window_width
        wl = self.viewer.slice_.window_level
        if BRUSH_BACKGROUND in markers and BRUSH_FOREGROUND in markers:
            #w_algorithm = WALGORITHM[self.config.algorithm]
            bstruct = generate_binary_structure(3, CON3D[self.config.con_3d])
            tfile = tempfile.mktemp()
            tmp_mask = np.memmap(tfile, shape=mask.shape, dtype=mask.dtype,
                                 mode='w+')
            q = multiprocessing.Queue()
            p = multiprocessing.Process(target=watershed_process.do_watershed, args=(image,
                                        markers, tfile, tmp_mask.shape, bstruct,
                                        self.config.algorithm,
                                        self.config.mg_size,
                                        self.config.use_ww_wl, wl, ww, q))

            wp = WatershedProgressWindow(p)
            p.start()

            while q.empty() and p.is_alive():
                time.sleep(0.5)
                wp.Update()
                wx.Yield()

            wp.Close()
            del wp

            w_x, w_y = wx.GetMousePosition()
            x, y = self.viewer.ScreenToClientXY(w_x, w_y)
            flag = self.viewer.interactor.HitTest((x, y))

            if flag == wx.HT_WINDOW_INSIDE:
                self.OnEnterInteractor(None, None)


            if q.empty():
                return
            #do_watershed(image, markers, tmp_mask, bstruct, self.config.algorithm,
                         #self.config.mg_size, self.config.use_ww_wl, wl, ww)
            #if self.config.use_ww_wl:
                #if self.config.algorithm == 'Watershed':
                    #tmp_image = ndimage.morphological_gradient(
                                   #get_LUT_value(image, ww, wl).astype('uint16'),
                                   #self.config.mg_size)
                    #tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
                #else:
                    #tmp_image = get_LUT_value(image, ww, wl).astype('uint16')
                    ##tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
                    ##tmp_image = ndimage.morphological_gradient(
                                   ##get_LUT_value(image, ww, wl).astype('uint16'),
                                   ##self.config.mg_size)
                    #tmp_mask = watershed_ift(tmp_image, markers.astype('int16'), bstruct)
            #else:
                #if self.config.algorithm == 'Watershed':
                    #tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
                    #tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
                #else:
                    #tmp_image = (image - image.min()).astype('uint16')
                    ##tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
                    ##tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
                    #tmp_mask = watershed_ift(tmp_image, markers.astype('int8'), bstruct)

            if self.viewer.overwrite_mask:
                mask[:] = 0
                mask[tmp_mask == 1] = 253
            else:
                mask[(tmp_mask==2) & ((mask == 0) | (mask == 2) | (mask == 253))] = 2
                mask[(tmp_mask==1) & ((mask == 0) | (mask == 2) | (mask == 253))] = 253

            #mask[:] = tmp_mask
            self.viewer.slice_.current_mask.matrix[0] = 1
            self.viewer.slice_.current_mask.matrix[:, 0, :] = 1
            self.viewer.slice_.current_mask.matrix[:, :, 0] = 1

            self.viewer.slice_.discard_all_buffers()
            self.viewer.slice_.current_mask.clear_history()
            Publisher.sendMessage('Reload actual slice')

            # Marking the project as changed
            session = ses.Session()
            session.ChangeProject()


class ReorientImageInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for image reorientation
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.viewer = viewer

        self.line1 = None
        self.line2 = None

        self.actors = []

        self.picker = vtk.vtkWorldPointPicker()

        self.AddObserver("KeyPressEvent", self.OnKeyPress)
        self.AddObserver("MouseMoveEvent", self.OnMouseMove)
        self.viewer.slice_data.renderer.AddObserver("StartEvent", self.OnUpdate)

    def SetUp(self):
        self.viewer.slice_.current_mask.is_shown = False
        self.draw_lines()
        Publisher.sendMessage('Reload actual slice')

    def CleanUp(self):
        for actor in self.actors:
            self.viewer.slice_data.renderer.RemoveActor(actor)

    def OnKeyPress(self, evt, obj):
        key = self.viewer.interactor.GetKeyCode()
        if key == '+':
            delta = 1
        elif key == '-':
            delta = -1
        else:
            return

        rx, ry, rz = self.viewer.slice_.rotations
        orientation = self.viewer.orientation
        if orientation == 'AXIAL':
            rz += np.deg2rad(delta)
        elif orientation == 'CORONAL':
            ry += np.deg2rad(delta)
        elif orientation == 'SAGITAL':
            rx += np.deg2rad(delta)

        self.viewer.slice_.rotations = (rx, ry, rz)

        for buffer_ in self.viewer.slice_.buffer_slices.values():
            buffer_.discard_vtk_image()
            buffer_.discard_image()

        self.viewer.slice_.current_mask.clear_history()
        Publisher.sendMessage('Reload actual slice')

    def OnMouseMove(self, obj, evt):
        """
        This event is responsible to reorient image, set mouse cursors
        """
        # Getting mouse position
        iren = self.viewer.interactor
        mx, my = iren.GetEventPosition()

        # Getting center value
        center = self.viewer.slice_.center
        coord = vtk.vtkCoordinate()
        coord.SetValue(center)
        cx, cy = coord.GetComputedDisplayValue(self.viewer.slice_data.renderer)

        dist_center = ((mx - cx)**2 + (my - cy)**2)**0.5

        if dist_center <= 15:
            cursor = wx.StockCursor(wx.CURSOR_SIZENESW)

            if self.left_pressed:
                self.picker.Pick(mx, my, 0, self.viewer.slice_data.renderer)
                x, y, z = self.picker.GetPickPosition()
                icx, icy, icz = self.viewer.slice_.center

                if self.viewer.orientation == 'AXIAL':
                    self.viewer.slice_.center = (x, y, icz)
                elif self.viewer.orientation == 'CORONAL':
                    self.viewer.slice_.center = (x, icy, z)
                elif self.viewer.orientation == 'SAGITAL':
                    self.viewer.slice_.center = (icx, y, z)
                Publisher.sendMessage('Update slice viewer')
        else:
            cursor = wx.StockCursor(wx.CURSOR_DEFAULT)

        self.viewer.interactor.SetCursor(cursor)

    def OnUpdate(self, obj, evt):
        w, h = self.viewer.slice_data.renderer.GetSize()

        center = self.viewer.slice_.center
        coord = vtk.vtkCoordinate()
        coord.SetValue(center)
        x, y = coord.GetComputedDisplayValue(self.viewer.slice_data.renderer)

        self.line1.SetPoint1(0, y, 0)
        self.line1.SetPoint2(w, y, 0)
        self.line1.Update()

        self.line2.SetPoint1(x, 0, 0)
        self.line2.SetPoint2(x, h, 0)
        self.line2.Update()

    def _create_line(self, x0, y0, x1, y1, color):
        line = vtk.vtkLineSource()
        line.SetPoint1(x0, y0, 0)
        line.SetPoint2(x1, y1, 0)

        coord = vtk.vtkCoordinate()
        coord.SetCoordinateSystemToDisplay()

        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetTransformCoordinate(coord)
        mapper.SetInputConnection(line.GetOutputPort())
        mapper.Update()

        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetProperty().SetLineWidth(2.0)
        actor.GetProperty().SetColor(color)

        self.viewer.slice_data.renderer.AddActor(actor)

        self.actors.append(actor)

        return line

    def draw_lines(self):
        if self.viewer.orientation == 'AXIAL':
            color1 = (0, 1, 0)
            color2 = (0, 0, 1)
        elif self.viewer.orientation == 'CORONAL':
            color1 = (1, 0, 0)
            color2 = (0, 0, 1)
        elif self.viewer.orientation == 'SAGITAL':
            color1 = (1, 0, 0)
            color2 = (0, 1, 0)

        self.line1 = self._create_line(0, 0.5, 1, 0.5, color1)
        self.line2 = self._create_line(0.5, 0, 0.5, 1, color2)


def get_style(style):
    STYLES = {
        const.STATE_DEFAULT: DefaultInteractorStyle,
        const.SLICE_STATE_CROSS: CrossInteractorStyle,
        const.STATE_WL: WWWLInteractorStyle,
        const.STATE_MEASURE_DISTANCE: LinearMeasureInteractorStyle,
        const.STATE_MEASURE_ANGLE: AngularMeasureInteractorStyle,
        const.STATE_PAN: PanMoveInteractorStyle,
        const.STATE_SPIN: SpinInteractorStyle,
        const.STATE_ZOOM: ZoomInteractorStyle,
        const.STATE_ZOOM_SL: ZoomSLInteractorStyle,
        const.SLICE_STATE_SCROLL: ChangeSliceInteractorStyle,
        const.SLICE_STATE_EDITOR: EditorInteractorStyle,
        const.SLICE_STATE_WATERSHED: WaterShedInteractorStyle,
        const.SLICE_STATE_REORIENT: ReorientImageInteractorStyle,
    }
    return STYLES[style]
