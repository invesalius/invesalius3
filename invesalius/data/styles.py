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

import multiprocessing
import os
import tempfile
import time
from concurrent import futures
from typing import Optional

import numpy as np
import wx
from scipy import ndimage
from scipy.ndimage import generate_binary_structure, watershed_ift

try:
    # Skimage >= 0.19
    from skimage.segmentation import watershed
except ImportError:
    from skimage.morphology import watershed

from vtkmodules.vtkFiltersSources import vtkLineSource
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleImage,
    vtkInteractorStyleRubberBandZoom,
)
from vtkmodules.vtkRenderingCore import (
    vtkActor2D,
    vtkCellPicker,
    vtkCoordinate,
    vtkPolyDataMapper2D,
    vtkWorldPointPicker,
)

import invesalius.constants as const
import invesalius.data.cursor_actors as ca
import invesalius.data.geometry as geom

# For tracts
import invesalius.data.tractography as dtr
import invesalius.data.transformations as transformations
import invesalius.data.watershed_process as watershed_process
import invesalius.gui.dialogs as dialogs
import invesalius.session as ses
import invesalius.utils as utils
from invesalius.data.imagedata_utils import get_LUT_value, get_LUT_value_255
from invesalius.data.measures import CircleDensityMeasure, MeasureData, PolygonDensityMeasure
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius_cy import floodfill

# import invesalius.project as prj

# from time import sleep
# ---

ORIENTATIONS = {
    "AXIAL": const.AXIAL,
    "CORONAL": const.CORONAL,
    "SAGITAL": const.SAGITAL,
}

BRUSH_FOREGROUND = 1
BRUSH_BACKGROUND = 2
BRUSH_ERASE = 0

WATERSHED_OPERATIONS = {
    _("Erase"): BRUSH_ERASE,
    _("Foreground"): BRUSH_FOREGROUND,
    _("Background"): BRUSH_BACKGROUND,
}


class BaseImageInteractorStyle(vtkInteractorStyleImage):
    def __init__(self, viewer):
        self.viewer = viewer

        self.right_pressed = False
        self.left_pressed = False
        self.middle_pressed = False

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.AddObserver("RightButtonPressEvent", self.OnPressRightButton)
        self.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)

        self.AddObserver("MiddleButtonPressEvent", self.OnMiddleButtonPressEvent)
        self.AddObserver("MiddleButtonReleaseEvent", self.OnMiddleButtonReleaseEvent)

    def OnPressLeftButton(self, evt, obj):
        self.left_pressed = True

    def OnReleaseLeftButton(self, evt, obj):
        self.left_pressed = False

    def OnPressRightButton(self, evt, obj):
        self.right_pressed = True
        self.viewer.last_position_mouse_move = self.viewer.interactor.GetLastEventPosition()

    def OnReleaseRightButton(self, evt, obj):
        self.right_pressed = False

    def OnMiddleButtonPressEvent(self, evt, obj):
        self.middle_pressed = True

    def OnMiddleButtonReleaseEvent(self, evt, obj):
        self.middle_pressed = False

    def GetMousePosition(self):
        mx, my = self.viewer.get_vtk_mouse_position()
        return mx, my

    def GetPickPosition(self, mouse_position=None):
        if mouse_position is None:
            mx, my = self.GetMousePosition()
        else:
            mx, my = mouse_position
        iren = self.viewer.interactor
        render = iren.FindPokedRenderer(mx, my)
        self.picker.Pick(mx, my, 0, render)
        x, y, z = self.picker.GetPickPosition()
        return (x, y, z)


class DefaultInteractorStyle(BaseImageInteractorStyle):
    """
    Interactor style responsible for Default functionalities:
    * Zoom moving mouse with right button pressed;
    * Change the slices with the scroll.
    """

    def __init__(self, viewer):
        BaseImageInteractorStyle.__init__(self, viewer)

        self.state_code = const.STATE_DEFAULT

        self.viewer = viewer

        # Zoom using right button
        self.AddObserver("RightButtonPressEvent", self.OnZoomRightClick)
        self.AddObserver("RightButtonReleaseEvent", self.OnZoomRightRelease)
        self.AddObserver("MouseMoveEvent", self.OnZoomRightMove)

        self.AddObserver("MouseWheelForwardEvent", self.OnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)

    def OnZoomRightMove(self, evt, obj):
        if self.right_pressed:
            evt.Dolly()
            evt.OnRightButtonDown()

        elif self.middle_pressed:
            evt.Pan()
            evt.OnMiddleButtonDown()

    def OnZoomRightClick(self, evt, obj):
        evt.StartDolly()

    def OnZoomRightRelease(self, evt, obj):
        evt.OnRightButtonUp()
        self.right_pressed = False

    def OnScrollForward(self, evt, obj):
        iren = self.viewer.interactor
        viewer = self.viewer
        if iren.GetShiftKey():
            opacity = viewer.slice_.opacity + 0.1
            if opacity <= 1:
                viewer.slice_.opacity = opacity
                self.viewer.slice_.buffer_slices["AXIAL"].discard_vtk_mask()
                self.viewer.slice_.buffer_slices["CORONAL"].discard_vtk_mask()
                self.viewer.slice_.buffer_slices["SAGITAL"].discard_vtk_mask()
                Publisher.sendMessage("Reload actual slice")
        else:
            self.viewer.OnScrollForward()

    def OnScrollBackward(self, evt, obj):
        iren = self.viewer.interactor
        viewer = self.viewer

        if iren.GetShiftKey():
            opacity = viewer.slice_.opacity - 0.1
            if opacity >= 0.1:
                viewer.slice_.opacity = opacity
                self.viewer.slice_.buffer_slices["AXIAL"].discard_vtk_mask()
                self.viewer.slice_.buffer_slices["CORONAL"].discard_vtk_mask()
                self.viewer.slice_.buffer_slices["SAGITAL"].discard_vtk_mask()
                Publisher.sendMessage("Reload actual slice")
        else:
            self.viewer.OnScrollBackward()


class BaseImageEditionInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        super().__init__(viewer)

        self.viewer = viewer
        self.orientation = self.viewer.orientation

        self.picker = vtkWorldPointPicker()
        self.matrix = None

        self.cursor = None
        self.brush_size = const.BRUSH_SIZE
        self.brush_format = const.DEFAULT_BRUSH_FORMAT
        self.brush_colour = const.BRUSH_COLOUR
        self._set_cursor()

        self.fill_value = 254

        self.AddObserver("EnterEvent", self.OnBIEnterInteractor)
        self.AddObserver("LeaveEvent", self.OnBILeaveInteractor)

        self.AddObserver("LeftButtonPressEvent", self.OnBIBrushClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnBIBrushRelease)
        self.AddObserver("MouseMoveEvent", self.OnBIBrushMove)

        self.RemoveObservers("MouseWheelForwardEvent")
        self.RemoveObservers("MouseWheelBackwardEvent")
        self.AddObserver("MouseWheelForwardEvent", self.OnBIScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnBIScrollBackward)

    def _set_cursor(self):
        if const.DEFAULT_BRUSH_FORMAT == const.BRUSH_SQUARE:
            self.cursor = ca.CursorRectangle()
        elif const.DEFAULT_BRUSH_FORMAT == const.BRUSH_CIRCLE:
            self.cursor = ca.CursorCircle()

        self.cursor.SetOrientation(self.orientation)
        n = self.viewer.slice_data.number
        coordinates = {"SAGITAL": [n, 0, 0], "CORONAL": [0, n, 0], "AXIAL": [0, 0, n]}
        self.cursor.SetPosition(coordinates[self.orientation])
        spacing = self.viewer.slice_.spacing
        self.cursor.SetSpacing(spacing)
        self.cursor.SetColour(self.viewer._brush_cursor_colour)
        self.cursor.SetSize(self.brush_size)
        self.viewer.slice_data.SetCursor(self.cursor)

    def set_brush_size(self, size):
        self.brush_size = size
        self._set_cursor()

    def set_brush_format(self, format):
        self.brush_format = format
        self._set_cursor()

    def set_brush_operation(self, operation):
        self.brush_operation = operation
        self._set_cursor()

    def set_fill_value(self, fill_value):
        self.fill_value = fill_value

    def set_matrix(self, matrix):
        self.matrix = matrix

    def OnBIEnterInteractor(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return
        self.viewer.slice_data.cursor.Show()
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_BLANK))
        self.viewer.interactor.Render()

    def OnBILeaveInteractor(self, obj, evt):
        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def OnBIBrushClick(self, obj, evt):
        try:
            self.before_brush_click()
        except AttributeError:
            pass

        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        viewer = self.viewer
        iren = viewer.interactor
        # operation = self.config.operation

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = self.GetMousePosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        slice_data.cursor.Show()

        wx, wy, wz = viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        position = viewer.get_slice_pixel_coord_by_world_pos(wx, wy, wz)
        index = slice_data.number

        cursor = slice_data.cursor
        radius = cursor.radius

        slice_data.cursor.SetPosition((wx, wy, wz))

        self.edit_mask_pixel(
            self.fill_value, index, cursor.GetPixels(), position, radius, viewer.orientation
        )

        try:
            self.after_brush_click()
        except AttributeError:
            pass

        viewer.OnScrollBar()

    def OnBIBrushMove(self, obj, evt):
        try:
            self.before_brush_move()
        except AttributeError:
            pass

        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = self.GetMousePosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)
        # operation = self.config.operation

        wx, wy, wz = viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        slice_data.cursor.SetPosition((wx, wy, wz))

        if self.left_pressed:
            cursor = slice_data.cursor
            radius = cursor.radius

            position = viewer.get_slice_pixel_coord_by_world_pos(wx, wy, wz)
            index = slice_data.number

            slice_data.cursor.SetPosition((wx, wy, wz))
            self.edit_mask_pixel(
                self.fill_value, index, cursor.GetPixels(), position, radius, viewer.orientation
            )
            try:
                self.after_brush_move()
            except AttributeError:
                pass
            viewer.OnScrollBar(update3D=False)
        else:
            viewer.interactor.Render()

    def OnBIBrushRelease(self, evt, obj):
        try:
            self.before_brush_release()
        except AttributeError:
            pass

        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        self.after_brush_release()
        self.viewer.discard_mask_cache(all_orientations=True, vtk_cache=True)
        Publisher.sendMessage("Reload actual slice")

    def edit_mask_pixel(self, fill_value, n, index, position, radius, orientation):
        if orientation == "AXIAL":
            matrix = self.matrix[n, :, :]
        elif orientation == "CORONAL":
            matrix = self.matrix[:, n, :]
        elif orientation == "SAGITAL":
            matrix = self.matrix[:, :, n]

        spacing = self.viewer.slice_.spacing
        if hasattr(position, "__iter__"):
            px, py = position
            if orientation == "AXIAL":
                sx = spacing[0]
                sy = spacing[1]
            elif orientation == "CORONAL":
                sx = spacing[0]
                sy = spacing[2]
            elif orientation == "SAGITAL":
                sx = spacing[2]
                sy = spacing[1]

        else:
            if orientation == "AXIAL":
                sx = spacing[0]
                sy = spacing[1]
                py = position / matrix.shape[1]
                px = position % matrix.shape[1]
            elif orientation == "CORONAL":
                sx = spacing[0]
                sy = spacing[2]
                py = position / matrix.shape[1]
                px = position % matrix.shape[1]
            elif orientation == "SAGITAL":
                sx = spacing[2]  # noqa: F841
                sy = spacing[1]  # noqa: F841
                py = position / matrix.shape[1]
                px = position % matrix.shape[1]

        cx = index.shape[1] / 2 + 1
        cy = index.shape[0] / 2 + 1
        xi = int(px - index.shape[1] + cx)
        xf = int(xi + index.shape[1])
        yi = int(py - index.shape[0] + cy)
        yf = int(yi + index.shape[0])

        if yi < 0:
            index = index[abs(yi) :, :]
            yi = 0
        if yf > matrix.shape[0]:
            index = index[: index.shape[0] - (yf - matrix.shape[0]), :]
            yf = matrix.shape[0]

        if xi < 0:
            index = index[:, abs(xi) :]
            xi = 0
        if xf > matrix.shape[1]:
            index = index[:, : index.shape[1] - (xf - matrix.shape[1])]
            xf = matrix.shape[1]

        # Verifying if the points is over the image array.
        if (not 0 <= xi <= matrix.shape[1] and not 0 <= xf <= matrix.shape[1]) or (
            not 0 <= yi <= matrix.shape[0] and not 0 <= yf <= matrix.shape[0]
        ):
            return

        roi_m = matrix[yi:yf, xi:xf]

        # Checking if roi_i has at least one element.
        if roi_m.size:
            roi_m[index] = self.fill_value

    def OnBIScrollForward(self, evt, obj):
        iren = self.viewer.interactor
        if iren.GetControlKey():
            size = self.brush_size + 1
            if size <= 100:
                self.set_brush_size(size)
        else:
            self.OnScrollForward(obj, evt)

    def OnBIScrollBackward(self, evt, obj):
        iren = self.viewer.interactor
        if iren.GetControlKey():
            size = self.brush_size - 1
            if size > 0:
                self.set_brush_size(size)
        else:
            self.OnScrollBackward(obj, evt)


class NavigationInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style used for slice viewers during navigation mode:

    Displays the cross that shows the selected point, but does not allow the user to move it manually
    by clicking and dragging the mouse.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)
        self.viewer = viewer

    def SetUp(self):
        self.viewer.set_cross_visibility(1)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.set_cross_visibility(0)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)


class CrossInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style used for slice visualization when the 'cross' icon has been selected from the toolbar.

    The style displays the cross in each slice and allows the user to move the cross in the slices by clicking and dragging the mouse.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_CROSS

        self.viewer = viewer
        self.orientation = viewer.orientation
        self.slice_actor = viewer.slice_data.actor
        self.slice_data = viewer.slice_data

        self.picker = vtkWorldPointPicker()

        self.AddObserver("MouseMoveEvent", self.OnCrossMove)
        self.AddObserver("LeftButtonPressEvent", self.OnCrossMouseClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

    def SetUp(self):
        self.viewer.set_cross_visibility(1)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.set_cross_visibility(0)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnCrossMouseClick(self, obj, evt):
        iren = obj.GetInteractor()
        self.ChangeCrossPosition(iren)

    def OnCrossMove(self, obj, evt):
        # The user moved the mouse with left button pressed
        if self.left_pressed:
            iren = obj.GetInteractor()
            self.ChangeCrossPosition(iren)

    def ChangeCrossPosition(self, iren):
        mouse_x, mouse_y = self.GetMousePosition()
        x, y, z = self.viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        self.viewer.UpdateSlicesPosition([x, y, z])

        # Update the position of the cross in other slices.
        Publisher.sendMessage("Set cross focal point", position=[x, y, z, None, None, None])

        # Update the pointer in the volume viewer.
        #
        # We are moving from slice coordinates to volume coordinates, so we need to invert the y coordinate.
        Publisher.sendMessage("Update volume viewer pointer", position=[x, -y, z])
        Publisher.sendMessage("Update slice viewer")

    def OnScrollBar(self, *args, **kwargs):
        # Update other slice's cross according to the new focal point from
        # the actual orientation.
        x, y, z = self.viewer.cross.GetFocalPoint()
        self.viewer.UpdateSlicesPosition([x, y, z])
        # This "Set cross" message is needed to update the cross in the other slices
        Publisher.sendMessage("Set cross focal point", position=[x, y, z, None, None, None])
        Publisher.sendMessage("Update slice viewer")


class TractsInteractorStyle(CrossInteractorStyle):
    """
    Interactor style responsible for tracts visualization.
    """

    def __init__(self, viewer):
        CrossInteractorStyle.__init__(self, viewer)

        # self.state_code = const.SLICE_STATE_TRACTS

        self.viewer = viewer
        # print("Im fucking brilliant!")
        self.tracts = None

        # data_dir = b'C:\Users\deoliv1\OneDrive\data\dti'
        # FOD_path = b"sub-P0_dwi_FOD.nii"
        # full_path = os.path.join(data_dir, FOD_path)
        # self.tracker = Trekker.tracker(full_path)
        # self.orientation = viewer.orientation
        # self.slice_actor = viewer.slice_data.actor
        # self.slice_data = viewer.slice_data

        # self.picker = vtkWorldPointPicker()

        self.AddObserver("MouseMoveEvent", self.OnTractsMove)
        self.AddObserver("LeftButtonPressEvent", self.OnTractsMouseClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnTractsReleaseLeftButton)

    # def SetUp(self):
    #     self.viewer.set_cross_visibility(1)
    #     Publisher.sendMessage('Toggle toolbar item',
    #                           _id=self.state_code, value=True)

    # def CleanUp(self):
    #     self.viewer.set_cross_visibility(0)
    #     Publisher.sendMessage('Toggle toolbar item',
    #                           _id=self.state_code, value=False)

    def OnTractsMove(self, obj, evt):
        # The user moved the mouse with left button pressed
        if self.left_pressed:
            # print("OnTractsMove interactor style")
            # iren = obj.GetInteractor()
            self.ChangeTracts(True)

    def OnTractsMouseClick(self, obj, evt):
        # print("Single mouse click")
        # self.tracts = dtr.compute_and_visualize_tracts(self.tracker, self.seed, self.left_pressed)
        self.ChangeTracts(True)

    def OnTractsReleaseLeftButton(self, obj, evt):
        # time.sleep(3.)
        self.tracts.stop()
        # self.ChangeCrossPosition(iren)

    def ChangeTracts(self, pressed):
        # print("Trying to compute tracts")
        self.tracts = dtr.compute_and_visualize_tracts(
            self.tracker, self.seed, self.affine_vtk, pressed
        )
        # mouse_x, mouse_y = iren.GetEventPosition()
        # wx, wy, wz = self.viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        # px, py = self.viewer.get_slice_pixel_coord_by_world_pos(wx, wy, wz)
        # coord = self.viewer.calcultate_scroll_position(px, py)
        # Publisher.sendMessage('Update cross position', position=(wx, wy, wz))
        # # self.ScrollSlice(coord)
        # Publisher.sendMessage('Set ball reference position', position=(wx, wy, wz))
        # Publisher.sendMessage('Co-registered points',  arg=None, position=(wx, wy, wz, 0., 0., 0.))

        # iren.Render()

    # def ScrollSlice(self, coord):
    #     if self.orientation == "AXIAL":
    #         Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
    #                                    index=coord[0])
    #         Publisher.sendMessage(('Set scroll position', 'CORONAL'),
    #                                    index=coord[1])
    #     elif self.orientation == "SAGITAL":
    #         Publisher.sendMessage(('Set scroll position', 'AXIAL'),
    #                                    index=coord[2])
    #         Publisher.sendMessage(('Set scroll position', 'CORONAL'),
    #                                    index=coord[1])
    #     elif self.orientation == "CORONAL":
    #         Publisher.sendMessage(('Set scroll position', 'AXIAL'),
    #                                    index=coord[2])
    #         Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
    #                                    index=coord[0])


class WWWLInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for Window Level & Width functionality.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.STATE_WL

        self.viewer = viewer

        self.last_x = 0
        self.last_y = 0

        self.acum_achange_window = viewer.slice_.window_width
        self.acum_achange_level = viewer.slice_.window_level

        self.AddObserver("MouseMoveEvent", self.OnWindowLevelMove)
        self.AddObserver("LeftButtonPressEvent", self.OnWindowLevelClick)

    def SetUp(self):
        self.viewer.on_wl = True
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)
        self.viewer.canvas.draw_list.append(self.viewer.wl_text)
        self.viewer.UpdateCanvas()

    def CleanUp(self):
        self.viewer.on_wl = False
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        if self.viewer.wl_text is not None:
            self.viewer.canvas.draw_list.remove(self.viewer.wl_text)
            self.viewer.UpdateCanvas()

    def OnWindowLevelMove(self, obj, evt):
        if self.left_pressed:
            # iren = obj.GetInteractor()
            mouse_x, mouse_y = self.GetMousePosition()
            self.acum_achange_window += mouse_x - self.last_x
            self.acum_achange_level += mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y

            Publisher.sendMessage(
                "Bright and contrast adjustment image",
                window=self.acum_achange_window,
                level=self.acum_achange_level,
            )

            # self.SetWLText(self.acum_achange_level,
            #              self.acum_achange_window)

            const.WINDOW_LEVEL["Manual"] = (self.acum_achange_window, self.acum_achange_level)
            Publisher.sendMessage("Check window and level other")
            Publisher.sendMessage(
                "Update window level value",
                window=self.acum_achange_window,
                level=self.acum_achange_level,
            )
            # Necessary update the slice plane in the volume case exists
            Publisher.sendMessage("Update slice viewer")
            Publisher.sendMessage("Render volume viewer")

    def OnWindowLevelClick(self, obj, evt):
        iren = obj.GetInteractor()
        self.last_x, self.last_y = iren.GetLastEventPosition()

        self.acum_achange_window = self.viewer.slice_.window_width
        self.acum_achange_level = self.viewer.slice_.window_level


class LinearMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert linear measurements.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.STATE_MEASURE_DISTANCE

        self.viewer = viewer
        self.orientation = viewer.orientation
        self.slice_data = viewer.slice_data

        self.measures = MeasureData()
        self.selected = None
        self.creating = None

        self._type = const.LINEAR

        spacing = self.slice_data.actor.GetInput().GetSpacing()

        if self.orientation == "AXIAL":
            self.radius = min(spacing[1], spacing[2]) * 0.8
            self._ori = const.AXIAL

        elif self.orientation == "CORONAL":
            self.radius = min(spacing[0], spacing[1]) * 0.8
            self._ori = const.CORONAL

        elif self.orientation == "SAGITAL":
            self.radius = min(spacing[1], spacing[2]) * 0.8
            self._ori = const.SAGITAL

        self.picker = vtkCellPicker()
        self.picker.PickFromListOn()

        self._bind_events()

    def _bind_events(self):
        self.AddObserver("LeftButtonPressEvent", self.OnInsertMeasurePoint)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseMeasurePoint)
        self.AddObserver("MouseMoveEvent", self.OnMoveMeasurePoint)
        self.AddObserver("LeaveEvent", self.OnLeaveMeasureInteractor)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        self.picker.PickFromListOff()
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertMeasurePoint(self, obj, evt):
        slice_number = self.slice_data.number
        x, y, z = self._get_pos_clicked()
        mx, my = self.GetMousePosition()

        if self.selected:
            self.selected = None
            self.viewer.scroll_enabled = True
            return

        if self.creating:
            n, m, mr = self.creating
            if mr.IsComplete():
                self.creating = None
                self.viewer.scroll_enabled = True
            else:
                Publisher.sendMessage(
                    "Add measurement point",
                    position=(x, y, z),
                    type=self._type,
                    location=ORIENTATIONS[self.orientation],
                    slice_number=slice_number,
                    radius=self.radius,
                )
                n = len(m.points) - 1
                self.creating = n, m, mr
                self.viewer.UpdateCanvas()
                self.viewer.scroll_enabled = False
            return

        selected = self._verify_clicked_display(mx, my)
        if selected:
            self.selected = selected
            self.viewer.scroll_enabled = False
        else:
            if self.picker.GetViewProp():
                # renderer = self.viewer.slice_data.renderer
                Publisher.sendMessage(
                    "Add measurement point",
                    position=(x, y, z),
                    type=self._type,
                    location=ORIENTATIONS[self.orientation],
                    slice_number=slice_number,
                    radius=self.radius,
                )
                Publisher.sendMessage(
                    "Add measurement point",
                    position=(x, y, z),
                    type=self._type,
                    location=ORIENTATIONS[self.orientation],
                    slice_number=slice_number,
                    radius=self.radius,
                )

                n, (m, mr) = 1, self.measures.measures[self._ori][slice_number][-1]
                self.creating = n, m, mr
                self.viewer.UpdateCanvas()
                self.viewer.scroll_enabled = False

    def OnReleaseMeasurePoint(self, obj, evt):
        if self.selected:
            n, m, mr = self.selected
            x, y, z = self._get_pos_clicked()
            idx = self.measures._list_measures.index((m, mr))
            Publisher.sendMessage(
                "Change measurement point position", index=idx, npoint=n, pos=(x, y, z)
            )
            self.viewer.UpdateCanvas()
            self.selected = None
            self.viewer.scroll_enabled = True

    def OnMoveMeasurePoint(self, obj, evt):
        x, y, z = self._get_pos_clicked()
        if self.selected:
            n, m, mr = self.selected
            idx = self.measures._list_measures.index((m, mr))
            Publisher.sendMessage(
                "Change measurement point position", index=idx, npoint=n, pos=(x, y, z)
            )
            self.viewer.UpdateCanvas()

        elif self.creating:
            n, m, mr = self.creating
            idx = self.measures._list_measures.index((m, mr))
            Publisher.sendMessage(
                "Change measurement point position", index=idx, npoint=n, pos=(x, y, z)
            )
            self.viewer.UpdateCanvas()

        else:
            mx, my = self.GetMousePosition()
            if self._verify_clicked_display(mx, my):
                self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            else:
                self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def OnLeaveMeasureInteractor(self, obj, evt):
        if self.creating or self.selected:
            n, m, mr = self.creating
            if not mr.IsComplete():
                Publisher.sendMessage("Remove incomplete measurements")
            self.creating = None
            self.selected = None
            self.viewer.UpdateCanvas()
            self.viewer.scroll_enabled = True

    def _get_pos_clicked(self):
        self.picker.AddPickList(self.slice_data.actor)
        x, y, z = self.GetPickPosition()
        self.picker.DeletePickList(self.slice_data.actor)
        return (x, y, z)

    def _verify_clicked(self, x, y, z):
        slice_number = self.slice_data.number
        sx, sy, sz = self.viewer.slice_.spacing
        if self.orientation == "AXIAL":
            max_dist = 2 * max(sx, sy)
        elif self.orientation == "CORONAL":
            max_dist = 2 * max(sx, sz)
        elif self.orientation == "SAGITAL":
            max_dist = 2 * max(sy, sz)

        if slice_number in self.measures.measures[self._ori]:
            for m, mr in self.measures.measures[self._ori][slice_number]:
                if mr.IsComplete():
                    for n, p in enumerate(m.points):
                        px, py, pz = p
                        dist = ((px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2) ** 0.5
                        if dist < max_dist:
                            return (n, m, mr)
        return None

    def _verify_clicked_display(self, x, y, max_dist=5.0):
        slice_number = self.slice_data.number
        max_dist = max_dist**2
        coord = vtkCoordinate()
        if slice_number in self.measures.measures[self._ori]:
            for m, mr in self.measures.measures[self._ori][slice_number]:
                if mr.IsComplete():
                    for n, p in enumerate(m.points):
                        coord.SetValue(p)
                        cx, cy = coord.GetComputedDisplayValue(self.viewer.slice_data.renderer)
                        dist = (cx - x) ** 2 + (cy - y) ** 2
                        if dist <= max_dist:
                            return (n, m, mr)
        return None


class AngularMeasureInteractorStyle(LinearMeasureInteractorStyle):
    def __init__(self, viewer):
        LinearMeasureInteractorStyle.__init__(self, viewer)
        self._type = const.ANGULAR

        self.state_code = const.STATE_MEASURE_ANGLE


class DensityMeasureStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for density measurements.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.STATE_MEASURE_DENSITY

        self.format = "polygon"

        self._last_measure = None

        self.viewer = viewer
        self.orientation = viewer.orientation
        self.slice_data = viewer.slice_data

        self.picker = vtkCellPicker()
        self.picker.PickFromListOn()

        self.measures = MeasureData()

        self._bind_events()

    def _bind_events(self):
        #  self.AddObserver("LeftButtonPressEvent", self.OnInsertPoint)
        #  self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseMeasurePoint)
        #  self.AddObserver("MouseMoveEvent", self.OnMoveMeasurePoint)
        #  self.AddObserver("LeaveEvent", self.OnLeaveMeasureInteractor)
        self.viewer.canvas.subscribe_event("LeftButtonPressEvent", self.OnInsertPoint)
        self.viewer.canvas.subscribe_event("LeftButtonDoubleClickEvent", self.OnInsertPolygon)

    def SetUp(self):
        for n in self.viewer.draw_by_slice_number:
            for i in self.viewer.draw_by_slice_number[n]:
                if isinstance(i, PolygonDensityMeasure):
                    i.set_interactive(True)
        self.viewer.canvas.Refresh()

    def CleanUp(self):
        self.viewer.canvas.unsubscribe_event("LeftButtonPressEvent", self.OnInsertPoint)
        self.viewer.canvas.unsubscribe_event("LeftButtonDoubleClickEvent", self.OnInsertPolygon)
        old_list = self.viewer.draw_by_slice_number
        self.viewer.draw_by_slice_number.clear()
        for n in old_list:
            for i in old_list[n]:
                if isinstance(i, PolygonDensityMeasure):
                    if i.complete:
                        self.viewer.draw_by_slice_number[n].append(i)
                else:
                    self.viewer.draw_by_slice_number[n].append(i)

        self.viewer.UpdateCanvas()

    def _2d_to_3d(self, pos):
        mx, my = pos
        iren = self.viewer.interactor
        render = iren.FindPokedRenderer(mx, my)
        self.picker.AddPickList(self.slice_data.actor)
        self.picker.Pick(mx, my, 0, render)
        x, y, z = self.picker.GetPickPosition()
        self.picker.DeletePickList(self.slice_data.actor)
        return (x, y, z)

    def _pick_position(self):
        # iren = self.viewer.interactor
        mx, my = self.GetMousePosition()
        return (mx, my)

    def _get_pos_clicked(self):
        mouse_x, mouse_y = self.GetMousePosition()
        position = self.viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        return position

    def OnInsertPoint(self, evt):
        mouse_x, mouse_y = evt.position
        print("OnInsertPoint", evt.position)
        n = self.viewer.slice_data.number
        pos = self.viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)

        if self.format == "ellipse":
            pp1 = self.viewer.get_coordinate_cursor(mouse_x + 50, mouse_y, self.picker)
            pp2 = self.viewer.get_coordinate_cursor(mouse_x, mouse_y + 50, self.picker)

            m = CircleDensityMeasure(self.orientation, n)
            m.set_center(pos)
            m.set_point1(pp1)
            m.set_point2(pp2)
            m.calc_density()
            _new_measure = True
            Publisher.sendMessage("Add density measurement", density_measure=m)
        elif self.format == "polygon":
            if self._last_measure is None:
                m = PolygonDensityMeasure(self.orientation, n)
                _new_measure = True
            else:
                m = self._last_measure
                _new_measure = False
                if m.slice_number != n:
                    self.viewer.draw_by_slice_number[m.slice_number].remove(m)
                    del m
                    m = PolygonDensityMeasure(self.orientation, n)
                    _new_measure = True

            m.insert_point(pos)

            if _new_measure:
                self.viewer.draw_by_slice_number[n].append(m)

                if self._last_measure:
                    self._last_measure.set_interactive(False)

                self._last_measure = m
            #  m.calc_density()

        self.viewer.UpdateCanvas()

    def OnInsertPolygon(self, evt):
        if self.format == "polygon" and self._last_measure:
            m = self._last_measure
            if len(m.points) >= 3:
                n = self.viewer.slice_data.number
                print(self.viewer.draw_by_slice_number[n], m)
                self.viewer.draw_by_slice_number[n].remove(m)
                m.complete_polygon()
                self._last_measure = None
                Publisher.sendMessage("Add density measurement", density_measure=m)
                self.viewer.UpdateCanvas()


class DensityMeasureEllipseStyle(DensityMeasureStyle):
    def __init__(self, viewer):
        DensityMeasureStyle.__init__(self, viewer)
        self.state_code = const.STATE_MEASURE_DENSITY_ELLIPSE
        self.format = "ellipse"


class DensityMeasurePolygonStyle(DensityMeasureStyle):
    def __init__(self, viewer):
        DensityMeasureStyle.__init__(self, viewer)
        self.state_code = const.STATE_MEASURE_DENSITY_POLYGON
        self.format = "polygon"


class PanMoveInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for translate the camera.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.STATE_PAN

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnPanMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspan)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

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

        self.state_code = const.STATE_SPIN

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnSpinMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspin)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnSpinMove(self, obj, evt):
        iren = obj.GetInteractor()
        mouse_x, mouse_y = iren.GetLastEventPosition()
        ren = iren.FindPokedRenderer(mouse_x, mouse_y)
        cam = ren.GetActiveCamera()
        if self.left_pressed:
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

        self.state_code = const.STATE_ZOOM

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnZoomMoveLeft)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnZoomMoveLeft(self, obj, evt):
        if self.left_pressed:
            obj.Dolly()
            obj.OnRightButtonDown()

    def OnUnZoom(self, evt):
        mouse_x, mouse_y = self.viewer.interactor.GetLastEventPosition()
        ren = self.viewer.interactor.FindPokedRenderer(mouse_x, mouse_y)
        # slice_data = self.get_slice_data(ren)
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        # self.Reposition(slice_data)
        self.viewer.interactor.Render()


class ZoomSLInteractorStyle(vtkInteractorStyleRubberBandZoom):
    """
    Interactor style responsible for zoom by selecting a region.
    """

    def __init__(self, viewer):
        self.viewer = viewer
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

        self.state_code = const.STATE_ZOOM_SL

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnUnZoom(self, evt):
        mouse_x, mouse_y = self.viewer.interactor.GetLastEventPosition()
        ren = self.viewer.interactor.FindPokedRenderer(mouse_x, mouse_y)
        # slice_data = self.get_slice_data(ren)
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        # self.Reposition(slice_data)
        self.viewer.interactor.Render()


class ChangeSliceInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for change slice moving the mouse.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_SCROLL

        self.viewer = viewer

        self.AddObserver("MouseMoveEvent", self.OnChangeSliceMove)
        self.AddObserver("LeftButtonPressEvent", self.OnChangeSliceClick)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnChangeSliceMove(self, evt, obj):
        if self.left_pressed:
            min = 0
            max = self.viewer.slice_.GetMaxSliceNumber(self.viewer.orientation)

            position = self.viewer.interactor.GetLastEventPosition()
            # scroll_position = self.viewer.scroll.GetThumbPosition()

            if (position[1] > self.last_position) and (self.acum_achange_slice > min):
                self.acum_achange_slice -= 1
            elif (position[1] < self.last_position) and (self.acum_achange_slice < max):
                self.acum_achange_slice += 1
            self.last_position = position[1]

            self.viewer.scroll.SetThumbPosition(self.acum_achange_slice)
            self.viewer.OnScrollBar()

    def OnChangeSliceClick(self, evt, obj):
        position = self.viewer.interactor.GetLastEventPosition()
        self.acum_achange_slice = self.viewer.scroll.GetThumbPosition()
        self.last_position = position[1]


class EditorConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.operation = const.BRUSH_THRESH
        self.cursor_type = const.BRUSH_CIRCLE
        self.cursor_size = const.BRUSH_SIZE
        self.cursor_unit = "mm"


class EditorInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_EDITOR

        self.viewer = viewer
        self.orientation = self.viewer.orientation

        self.config = EditorConfig()

        self.picker = vtkWorldPointPicker()

        self.AddObserver("EnterEvent", self.OnEnterInteractor)
        self.AddObserver("LeaveEvent", self.OnLeaveInteractor)

        self.AddObserver("LeftButtonPressEvent", self.OnBrushClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnBrushRelease)
        self.AddObserver("MouseMoveEvent", self.OnBrushMove)

        self.RemoveObservers("MouseWheelForwardEvent")
        self.RemoveObservers("MouseWheelBackwardEvent")
        self.AddObserver("MouseWheelForwardEvent", self.EOnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.EOnScrollBackward)

        Publisher.subscribe(self.set_bsize, "Set edition brush size")
        Publisher.subscribe(self.set_bunit, "Set edition brush unit")
        Publisher.subscribe(self.set_bformat, "Set brush format")
        Publisher.subscribe(self.set_boperation, "Set edition operation")

        self._set_cursor()
        self.viewer.slice_data.cursor.Show(0)

    def SetUp(self):
        x, y = self.viewer.interactor.ScreenToClient(wx.GetMousePosition())
        if self.viewer.interactor.HitTest((x, y)) == wx.HT_WINDOW_INSIDE:
            self.viewer.slice_data.cursor.Show()

            y = self.viewer.interactor.GetSize()[1] - y
            w_x, w_y, w_z = self.viewer.get_coordinate_cursor(x, y, self.picker)
            self.viewer.slice_data.cursor.SetPosition((w_x, w_y, w_z))

            self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_BLANK))
            self.viewer.interactor.Render()

    def CleanUp(self):
        Publisher.unsubscribe(self.set_bsize, "Set edition brush size")
        Publisher.unsubscribe(self.set_bunit, "Set edition brush unit")
        Publisher.unsubscribe(self.set_bformat, "Set brush format")
        Publisher.unsubscribe(self.set_boperation, "Set edition operation")

        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def set_bsize(self, size):
        self.config.cursor_size = size
        self.viewer.slice_data.cursor.SetSize(size)

    def set_bunit(self, unit):
        self.config.cursor_unit = unit
        self.viewer.slice_data.cursor.SetUnit(unit)

    def set_bformat(self, cursor_format):
        self.config.cursor_type = cursor_format
        self._set_cursor()

    def set_boperation(self, operation):
        self.config.operation = operation

    def _set_cursor(self):
        if self.config.cursor_type == const.BRUSH_SQUARE:
            cursor = ca.CursorRectangle()
        elif self.config.cursor_type == const.BRUSH_CIRCLE:
            cursor = ca.CursorCircle()

        cursor.SetOrientation(self.orientation)
        n = self.viewer.slice_data.number
        coordinates = {"SAGITAL": [n, 0, 0], "CORONAL": [0, n, 0], "AXIAL": [0, 0, n]}
        cursor.SetPosition(coordinates[self.orientation])
        spacing = self.viewer.slice_.spacing
        cursor.SetSpacing(spacing)
        cursor.SetColour(self.viewer._brush_cursor_colour)
        cursor.SetSize(self.config.cursor_size)
        cursor.SetUnit(self.config.cursor_unit)
        self.viewer.slice_data.SetCursor(cursor)

    def OnEnterInteractor(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return
        self.viewer.slice_data.cursor.Show()
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_BLANK))
        self.viewer.interactor.Render()

    def OnLeaveInteractor(self, obj, evt):
        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def OnBrushClick(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
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

        mouse_x, mouse_y = self.GetMousePosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        # TODO: Improve!
        # for i in self.slice_data_list:
        # i.cursor.Show(0)
        slice_data.cursor.Show()

        wx, wy, wz = viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        position = viewer.get_slice_pixel_coord_by_world_pos(wx, wy, wz)

        cursor = slice_data.cursor
        radius = cursor.radius

        slice_data.cursor.SetPosition((wx, wy, wz))
        viewer.slice_.edit_mask_pixel(
            operation, cursor.GetPixels(), position, radius, viewer.orientation
        )
        # viewer._flush_buffer = True

        # TODO: To create a new function to reload images to viewer.
        viewer.OnScrollBar()

    def OnBrushMove(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = self.GetMousePosition()
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

        wx, wy, wz = viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        slice_data.cursor.SetPosition((wx, wy, wz))

        if self.left_pressed:
            cursor = slice_data.cursor
            radius = cursor.radius

            position = viewer.get_slice_pixel_coord_by_world_pos(wx, wy, wz)

            slice_data.cursor.SetPosition((wx, wy, wz))
            viewer.slice_.edit_mask_pixel(
                operation, cursor.GetPixels(), position, radius, viewer.orientation
            )

            viewer.OnScrollBar(update3D=False)

        else:
            viewer.interactor.Render()

    def OnBrushRelease(self, evt, obj):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        self.viewer._flush_buffer = True
        self.viewer.slice_.apply_slice_buffer_to_mask(self.orientation)
        self.viewer._flush_buffer = False
        self.viewer.slice_.current_mask.modified()

    def EOnScrollForward(self, evt, obj):
        iren = self.viewer.interactor
        # viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = self.GetMousePosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size += 1

            if size <= 100:
                Publisher.sendMessage("Set edition brush size", size=size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollForward(obj, evt)

    def EOnScrollBackward(self, evt, obj):
        iren = self.viewer.interactor
        # viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = self.GetMousePosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size -= 1

            if size > 0:
                Publisher.sendMessage("Set edition brush size", size=size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollBackward(obj, evt)


class WatershedProgressWindow:
    def __init__(self, process):
        self.process = process
        self.title = "InVesalius 3"
        self.msg = _("Applying watershed ...")
        self.style = wx.PD_APP_MODAL | wx.PD_APP_MODAL | wx.PD_CAN_ABORT

        self.dlg = wx.ProgressDialog(
            self.title, self.msg, parent=wx.GetApp().GetTopWindow(), style=self.style
        )

        self.dlg.Bind(wx.EVT_BUTTON, self.Cancel)
        self.dlg.Show()

    def Cancel(self, evt):
        self.process.terminate()

    def Update(self):
        self.dlg.Pulse()

    def Close(self):
        self.dlg.Destroy()


class WatershedConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.algorithm = "Watershed"
        self.con_2d = 4
        self.con_3d = 6
        self.mg_size = 3
        self.use_ww_wl = True
        self.operation = BRUSH_FOREGROUND
        self.cursor_type = const.BRUSH_CIRCLE
        self.cursor_size = const.BRUSH_SIZE
        self.cursor_unit = "mm"

        Publisher.subscribe(self.set_operation, "Set watershed operation")
        Publisher.subscribe(self.set_use_ww_wl, "Set use ww wl")

        Publisher.subscribe(self.set_algorithm, "Set watershed algorithm")
        Publisher.subscribe(self.set_2dcon, "Set watershed 2d con")
        Publisher.subscribe(self.set_3dcon, "Set watershed 3d con")
        Publisher.subscribe(self.set_gaussian_size, "Set watershed gaussian size")

    def set_operation(self, operation):
        self.operation = WATERSHED_OPERATIONS[operation]

    def set_use_ww_wl(self, use_ww_wl):
        self.use_ww_wl = use_ww_wl

    def set_algorithm(self, algorithm):
        self.algorithm = algorithm

    def set_2dcon(self, con_2d):
        self.con_2d = con_2d

    def set_3dcon(self, con_3d):
        self.con_3d = con_3d

    def set_gaussian_size(self, size):
        self.mg_size = size


WALGORITHM = {"Watershed": watershed, "Watershed IFT": watershed_ift}
CON2D = {4: 1, 8: 2}
CON3D = {6: 1, 18: 2, 26: 3}


class WaterShedInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_WATERSHED

        self.viewer = viewer
        self.orientation = self.viewer.orientation
        self.matrix = None

        self.config = WatershedConfig()

        self.picker = vtkWorldPointPicker()

        self.AddObserver("EnterEvent", self.OnEnterInteractor)
        self.AddObserver("LeaveEvent", self.OnLeaveInteractor)

        self.RemoveObservers("MouseWheelForwardEvent")
        self.RemoveObservers("MouseWheelBackwardEvent")
        self.AddObserver("MouseWheelForwardEvent", self.WOnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.WOnScrollBackward)

        self.AddObserver("LeftButtonPressEvent", self.OnBrushClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnBrushRelease)
        self.AddObserver("MouseMoveEvent", self.OnBrushMove)

        Publisher.subscribe(self.expand_watershed, "Expand watershed to 3D " + self.orientation)
        Publisher.subscribe(self.set_bsize, "Set watershed brush size")
        Publisher.subscribe(self.set_bunit, "Set watershed brush unit")
        Publisher.subscribe(self.set_bformat, "Set watershed brush format")

        self._set_cursor()
        self.viewer.slice_data.cursor.Show(0)

    def SetUp(self):
        # mask = self.viewer.slice_.current_mask.matrix
        self._create_mask()
        self.viewer.slice_.to_show_aux = "watershed"
        self.viewer.OnScrollBar()

        x, y = self.viewer.interactor.ScreenToClient(wx.GetMousePosition())
        if self.viewer.interactor.HitTest((x, y)) == wx.HT_WINDOW_INSIDE:
            self.viewer.slice_data.cursor.Show()

            y = self.viewer.interactor.GetSize()[1] - y
            w_x, w_y, w_z = self.viewer.get_coordinate_cursor(x, y, self.picker)
            self.viewer.slice_data.cursor.SetPosition((w_x, w_y, w_z))

            self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_BLANK))
            self.viewer.interactor.Render()

    def CleanUp(self):
        # self._remove_mask()
        Publisher.unsubscribe(self.expand_watershed, "Expand watershed to 3D " + self.orientation)
        Publisher.unsubscribe(self.set_bformat, "Set watershed brush format")
        Publisher.unsubscribe(self.set_bsize, "Set watershed brush size")
        self.RemoveAllObservers()
        self.viewer.slice_.to_show_aux = ""
        self.viewer.OnScrollBar()

        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def _create_mask(self):
        if self.matrix is None:
            try:
                self.matrix = self.viewer.slice_.aux_matrices["watershed"]
            except KeyError:
                self.temp_file, self.matrix = self.viewer.slice_.create_temp_mask()
                self.viewer.slice_.aux_matrices["watershed"] = self.matrix

    def _remove_mask(self):
        if self.matrix is not None:
            self.matrix = None
            os.remove(self.temp_file)
            print("deleting", self.temp_file)

    def _set_cursor(self):
        if self.config.cursor_type == const.BRUSH_SQUARE:
            cursor = ca.CursorRectangle()
        elif self.config.cursor_type == const.BRUSH_CIRCLE:
            cursor = ca.CursorCircle()

        cursor.SetOrientation(self.orientation)
        n = self.viewer.slice_data.number
        coordinates = {"SAGITAL": [n, 0, 0], "CORONAL": [0, n, 0], "AXIAL": [0, 0, n]}
        cursor.SetPosition(coordinates[self.orientation])
        spacing = self.viewer.slice_.spacing
        cursor.SetSpacing(spacing)
        cursor.SetColour(self.viewer._brush_cursor_colour)
        cursor.SetSize(self.config.cursor_size)
        cursor.SetUnit(self.config.cursor_unit)
        self.viewer.slice_data.SetCursor(cursor)

    def set_bsize(self, size):
        self.config.cursor_size = size
        self.viewer.slice_data.cursor.SetSize(size)

    def set_bunit(self, unit):
        self.config.cursor_unit = unit
        self.viewer.slice_data.cursor.SetUnit(unit)

    def set_bformat(self, brush_format):
        self.config.cursor_type = brush_format
        self._set_cursor()

    def OnEnterInteractor(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return
        self.viewer.slice_data.cursor.Show()
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_BLANK))
        self.viewer.interactor.Render()

    def OnLeaveInteractor(self, obj, evt):
        self.viewer.slice_data.cursor.Show(0)
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self.viewer.interactor.Render()

    def WOnScrollBackward(self, obj, evt):
        iren = self.viewer.interactor
        # viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = self.GetMousePosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size -= 1

            if size > 0:
                Publisher.sendMessage("Set watershed brush size", size=size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollBackward(obj, evt)

    def WOnScrollForward(self, obj, evt):
        iren = self.viewer.interactor
        # viewer = self.viewer
        if iren.GetControlKey():
            mouse_x, mouse_y = self.GetMousePosition()
            render = iren.FindPokedRenderer(mouse_x, mouse_y)
            slice_data = self.viewer.get_slice_data(render)
            cursor = slice_data.cursor
            size = cursor.radius * 2
            size += 1

            if size <= 100:
                Publisher.sendMessage("Set watershed brush size", size=size)
                cursor.SetPosition(cursor.position)
                self.viewer.interactor.Render()
        else:
            self.OnScrollForward(obj, evt)

    def OnBrushClick(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = self.GetMousePosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        coord = self.viewer.get_coordinate_cursor(mouse_x, mouse_y, picker=None)
        position = self.viewer.get_slice_pixel_coord_by_screen_pos(mouse_x, mouse_y, self.picker)

        slice_data.cursor.Show()
        slice_data.cursor.SetPosition(coord)

        cursor = slice_data.cursor
        radius = cursor.radius

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
        self.edit_mask_pixel(operation, n, cursor.GetPixels(), position, radius, self.orientation)
        # if self.orientation == "AXIAL":
        #     mask = self.matrix[n, :, :]
        # elif self.orientation == "CORONAL":
        #     mask = self.matrix[:, n, :]
        # elif self.orientation == "SAGITAL":
        #     mask = self.matrix[:, :, n]
        # TODO: To create a new function to reload images to viewer.
        viewer.OnScrollBar()

    def OnBrushMove(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        viewer = self.viewer
        iren = viewer.interactor

        viewer._set_editor_cursor_visibility(1)

        mouse_x, mouse_y = self.GetMousePosition()
        render = iren.FindPokedRenderer(mouse_x, mouse_y)
        slice_data = viewer.get_slice_data(render)

        coord = self.viewer.get_coordinate_cursor(mouse_x, mouse_y, self.picker)
        slice_data.cursor.SetPosition(coord)

        if self.left_pressed:
            cursor = slice_data.cursor
            position = self.viewer.get_slice_pixel_coord_by_world_pos(*coord)
            radius = cursor.radius

            if isinstance(position, int) and position < 0:
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
            self.edit_mask_pixel(
                operation, n, cursor.GetPixels(), position, radius, self.orientation
            )
            # if self.orientation == "AXIAL":
            #     mask = self.matrix[n, :, :]
            # elif self.orientation == "CORONAL":
            #     mask = self.matrix[:, n, :]
            # elif self.orientation == "SAGITAL":
            #     mask = self.matrix[:, :, n]
            # TODO: To create a new function to reload images to viewer.
            viewer.OnScrollBar(update3D=False)

        else:
            viewer.interactor.Render()

    def OnBrushRelease(self, evt, obj):
        n = self.viewer.slice_data.number
        self.viewer.slice_.discard_all_buffers()
        if self.orientation == "AXIAL":
            image = self.viewer.slice_.matrix[n]
            mask = self.viewer.slice_.current_mask.matrix[n + 1, 1:, 1:]
            self.viewer.slice_.current_mask.matrix[n + 1, 0, 0] = 1
            markers = self.matrix[n]

        elif self.orientation == "CORONAL":
            image = self.viewer.slice_.matrix[:, n, :]
            mask = self.viewer.slice_.current_mask.matrix[1:, n + 1, 1:]
            self.viewer.slice_.current_mask.matrix[0, n + 1, 0]
            markers = self.matrix[:, n, :]

        elif self.orientation == "SAGITAL":
            image = self.viewer.slice_.matrix[:, :, n]
            mask = self.viewer.slice_.current_mask.matrix[1:, 1:, n + 1]
            self.viewer.slice_.current_mask.matrix[0, 0, n + 1]
            markers = self.matrix[:, :, n]

        ww = self.viewer.slice_.window_width
        wl = self.viewer.slice_.window_level

        if BRUSH_BACKGROUND in markers and BRUSH_FOREGROUND in markers:
            # w_algorithm = WALGORITHM[self.config.algorithm]
            bstruct = generate_binary_structure(2, CON2D[self.config.con_2d])
            if self.config.use_ww_wl:
                if self.config.algorithm == "Watershed":
                    tmp_image = ndimage.morphological_gradient(
                        get_LUT_value(image, ww, wl).astype("uint16"), self.config.mg_size
                    )
                    tmp_mask = watershed(tmp_image, markers.astype("int16"), bstruct)
                else:
                    # tmp_image = ndimage.gaussian_filter(get_LUT_value(image, ww, wl).astype('uint16'), self.config.mg_size)
                    # tmp_image = ndimage.morphological_gradient(
                    # get_LUT_value(image, ww, wl).astype('uint16'),
                    # self.config.mg_size)
                    tmp_image = get_LUT_value(image, ww, wl).astype("uint16")
                    # markers[markers == 2] = -1
                    tmp_mask = watershed_ift(tmp_image, markers.astype("int16"), bstruct)
                    # markers[markers == -1] = 2
                    # tmp_mask[tmp_mask == -1]  = 2

            else:
                if self.config.algorithm == "Watershed":
                    tmp_image = ndimage.morphological_gradient(
                        (image - image.min()).astype("uint16"), self.config.mg_size
                    )
                    tmp_mask = watershed(tmp_image, markers.astype("int16"), bstruct)
                else:
                    # tmp_image = (image - image.min()).astype('uint16')
                    # tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
                    # tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
                    tmp_image = image - image.min().astype("uint16")
                    tmp_mask = watershed_ift(tmp_image, markers.astype("int16"), bstruct)

            if self.viewer.overwrite_mask:
                mask[:] = 0
                mask[tmp_mask == 1] = 253
            else:
                mask[(tmp_mask == 2) & ((mask == 0) | (mask == 2) | (mask == 253))] = 2
                mask[(tmp_mask == 1) & ((mask == 0) | (mask == 2) | (mask == 253))] = 253

            self.viewer.slice_.current_mask.was_edited = True
            self.viewer.slice_.current_mask.modified()
            self.viewer.slice_.current_mask.clear_history()

            # Marking the project as changed
            session = ses.Session()
            session.ChangeProject()

        Publisher.sendMessage("Reload actual slice")

    def edit_mask_pixel(self, operation, n, index, position, radius, orientation):
        if orientation == "AXIAL":
            mask = self.matrix[n, :, :]
        elif orientation == "CORONAL":
            mask = self.matrix[:, n, :]
        elif orientation == "SAGITAL":
            mask = self.matrix[:, :, n]

        spacing = self.viewer.slice_.spacing
        if hasattr(position, "__iter__"):
            px, py = position
            if orientation == "AXIAL":
                sx = spacing[0]
                sy = spacing[1]
            elif orientation == "CORONAL":
                sx = spacing[0]
                sy = spacing[2]
            elif orientation == "SAGITAL":
                sx = spacing[2]
                sy = spacing[1]

        else:
            if orientation == "AXIAL":
                sx = spacing[0]
                sy = spacing[1]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == "CORONAL":
                sx = spacing[0]
                sy = spacing[2]
                py = position / mask.shape[1]
                px = position % mask.shape[1]
            elif orientation == "SAGITAL":
                sx = spacing[2]  # noqa: F841
                sy = spacing[1]  # noqa: F841
                py = position / mask.shape[1]
                px = position % mask.shape[1]

        cx = index.shape[1] / 2 + 1
        cy = index.shape[0] / 2 + 1
        xi = int(px - index.shape[1] + cx)
        xf = int(xi + index.shape[1])
        yi = int(py - index.shape[0] + cy)
        yf = int(yi + index.shape[0])

        if yi < 0:
            index = index[abs(yi) :, :]
            yi = 0
        if yf > mask.shape[0]:
            index = index[: index.shape[0] - (yf - mask.shape[0]), :]
            yf = mask.shape[0]

        if xi < 0:
            index = index[:, abs(xi) :]
            xi = 0
        if xf > mask.shape[1]:
            index = index[:, : index.shape[1] - (xf - mask.shape[1])]
            xf = mask.shape[1]

        # Verifying if the points is over the image array.
        if (not 0 <= xi <= mask.shape[1] and not 0 <= xf <= mask.shape[1]) or (
            not 0 <= yi <= mask.shape[0] and not 0 <= yf <= mask.shape[0]
        ):
            return

        roi_m = mask[yi:yf, xi:xf]

        # Checking if roi_i has at least one element.
        if roi_m.size:
            roi_m[index] = operation

    def expand_watershed(self):
        markers = self.matrix
        image = self.viewer.slice_.matrix
        self.viewer.slice_.do_threshold_to_all_slices()
        mask = self.viewer.slice_.current_mask.matrix[1:, 1:, 1:]
        ww = self.viewer.slice_.window_width
        wl = self.viewer.slice_.window_level
        if BRUSH_BACKGROUND in markers and BRUSH_FOREGROUND in markers:
            # w_algorithm = WALGORITHM[self.config.algorithm]
            bstruct = generate_binary_structure(3, CON3D[self.config.con_3d])
            fd, tfile = tempfile.mkstemp()
            tmp_mask = np.memmap(tfile, shape=mask.shape, dtype=mask.dtype, mode="w+")
            q = multiprocessing.Queue()
            p = multiprocessing.Process(
                target=watershed_process.do_watershed,
                args=(
                    image,
                    markers,
                    tfile,
                    tmp_mask.shape,
                    bstruct,
                    self.config.algorithm,
                    self.config.mg_size,
                    self.config.use_ww_wl,
                    wl,
                    ww,
                    q,
                ),
            )

            os.close(fd)
            wp = WatershedProgressWindow(p)
            p.start()

            while q.empty() and p.is_alive():
                time.sleep(0.5)
                wp.Update()
                wx.Yield()

            wp.Close()
            del wp

            w_x, w_y = wx.GetMousePosition()
            x, y = self.viewer.ScreenToClient((w_x, w_y))
            flag = self.viewer.interactor.HitTest((x, y))

            if flag == wx.HT_WINDOW_INSIDE:
                self.OnEnterInteractor(None, None)

            if q.empty():
                return
            # do_watershed(image, markers, tmp_mask, bstruct, self.config.algorithm,
            # self.config.mg_size, self.config.use_ww_wl, wl, ww)
            # if self.config.use_ww_wl:
            # if self.config.algorithm == 'Watershed':
            # tmp_image = ndimage.morphological_gradient(
            # get_LUT_value(image, ww, wl).astype('uint16'),
            # self.config.mg_size)
            # tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
            # else:
            # tmp_image = get_LUT_value(image, ww, wl).astype('uint16')
            ##tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
            ##tmp_image = ndimage.morphological_gradient(
            ##get_LUT_value(image, ww, wl).astype('uint16'),
            ##self.config.mg_size)
            # tmp_mask = watershed_ift(tmp_image, markers.astype('int16'), bstruct)
            # else:
            # if self.config.algorithm == 'Watershed':
            # tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
            # tmp_mask = watershed(tmp_image, markers.astype('int16'), bstruct)
            # else:
            # tmp_image = (image - image.min()).astype('uint16')
            ##tmp_image = ndimage.gaussian_filter(tmp_image, self.config.mg_size)
            ##tmp_image = ndimage.morphological_gradient((image - image.min()).astype('uint16'), self.config.mg_size)
            # tmp_mask = watershed_ift(tmp_image, markers.astype('int8'), bstruct)

            if self.viewer.overwrite_mask:
                mask[:] = 0
                mask[tmp_mask == 1] = 253
            else:
                mask[(tmp_mask == 2) & ((mask == 0) | (mask == 2) | (mask == 253))] = 2
                mask[(tmp_mask == 1) & ((mask == 0) | (mask == 2) | (mask == 253))] = 253

            self.viewer.slice_.current_mask.modified(True)

            self.viewer.slice_.discard_all_buffers()
            self.viewer.slice_.current_mask.clear_history()
            Publisher.sendMessage("Reload actual slice")

            # Marking the project as changed
            session = ses.Session()
            session.ChangeProject()


class ReorientImageInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for image reorientation
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_REORIENT

        self.viewer = viewer

        self.line1 = None
        self.line2 = None

        self.actors = []

        self._over_center = False
        self.dragging = False
        self.to_rot = False

        self.picker = vtkWorldPointPicker()

        self.AddObserver("LeftButtonPressEvent", self.OnLeftClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnLeftRelease)
        self.AddObserver("MouseMoveEvent", self.OnMouseMove)
        self.viewer.slice_data.renderer.AddObserver("StartEvent", self.OnUpdate)

        if self.viewer.orientation == "AXIAL":
            Publisher.subscribe(self._set_reorientation_angles, "Set reorientation angles")

        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnDblClick)

    def SetUp(self):
        self.draw_lines()
        Publisher.sendMessage("Hide current mask")
        Publisher.sendMessage("Reload actual slice")

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)

        for actor in self.actors:
            self.viewer.slice_data.renderer.RemoveActor(actor)

        self.viewer.slice_.rotations = [0, 0, 0]
        self.viewer.slice_.q_orientation = np.array((1, 0, 0, 0))
        self._discard_buffers()
        Publisher.sendMessage("Close reorient dialog")
        Publisher.sendMessage("Show current mask")

    def OnLeftClick(self, obj, evt):
        if self._over_center:
            self.dragging = True
        else:
            x, y = self.GetMousePosition()
            w, h = self.viewer.interactor.GetSize()

            self.picker.Pick(h / 2.0, w / 2.0, 0, self.viewer.slice_data.renderer)
            cx, cy, cz = self.viewer.slice_.center

            self.picker.Pick(x, y, 0, self.viewer.slice_data.renderer)
            x, y, z = self.picker.GetPickPosition()

            self.p0 = self.get_image_point_coord(x, y, z)
            self.to_rot = True

    def OnLeftRelease(self, obj, evt):
        self.dragging = False

        if self.to_rot:
            Publisher.sendMessage("Reload actual slice")
            self.to_rot = False

    def OnMouseMove(self, obj, evt):
        """
        This event is responsible to reorient image, set mouse cursors
        """
        if self.dragging:
            self._move_center_rot()
        elif self.to_rot:
            self._rotate()
        else:
            # Getting mouse position
            # iren = self.viewer.interactor
            mx, my = self.GetMousePosition()

            # Getting center value
            center = self.viewer.slice_.center
            coord = vtkCoordinate()
            coord.SetValue(center)
            cx, cy = coord.GetComputedDisplayValue(self.viewer.slice_data.renderer)

            dist_center = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5
            if dist_center <= 15:
                self._over_center = True
                cursor = wx.Cursor(wx.CURSOR_SIZENESW)
            else:
                self._over_center = False
                cursor = wx.Cursor(wx.CURSOR_DEFAULT)

            self.viewer.interactor.SetCursor(cursor)

    def OnUpdate(self, obj, evt):
        w, h = self.viewer.slice_data.renderer.GetSize()

        center = self.viewer.slice_.center
        coord = vtkCoordinate()
        coord.SetValue(center)
        x, y = coord.GetComputedDisplayValue(self.viewer.slice_data.renderer)

        self.line1.SetPoint1(0, y, 0)
        self.line1.SetPoint2(w, y, 0)
        self.line1.Update()

        self.line2.SetPoint1(x, 0, 0)
        self.line2.SetPoint2(x, h, 0)
        self.line2.Update()

    def OnDblClick(self, evt):
        self.viewer.slice_.rotations = [0, 0, 0]
        self.viewer.slice_.q_orientation = np.array((1, 0, 0, 0))

        Publisher.sendMessage("Update reorient angles", angles=(0, 0, 0))

        self._discard_buffers()
        self.viewer.slice_.current_mask.clear_history()
        Publisher.sendMessage("Reload actual slice")

    def _move_center_rot(self):
        # iren = self.viewer.interactor
        mx, my = self.GetMousePosition()

        icx, icy, icz = self.viewer.slice_.center

        self.picker.Pick(mx, my, 0, self.viewer.slice_data.renderer)
        x, y, z = self.picker.GetPickPosition()

        if self.viewer.orientation == "AXIAL":
            self.viewer.slice_.center = (x, y, icz)
        elif self.viewer.orientation == "CORONAL":
            self.viewer.slice_.center = (x, icy, z)
        elif self.viewer.orientation == "SAGITAL":
            self.viewer.slice_.center = (icx, y, z)

        self._discard_buffers()
        self.viewer.slice_.current_mask.clear_history()
        Publisher.sendMessage("Reload actual slice")

    def _rotate(self):
        # Getting mouse position
        # iren = self.viewer.interactor
        mx, my = self.GetMousePosition()

        cx, cy, cz = self.viewer.slice_.center

        self.picker.Pick(mx, my, 0, self.viewer.slice_data.renderer)
        x, y, z = self.picker.GetPickPosition()

        if self.viewer.orientation == "AXIAL":
            p1 = np.array((y - cy, x - cx))
        elif self.viewer.orientation == "CORONAL":
            p1 = np.array((z - cz, x - cx))
        elif self.viewer.orientation == "SAGITAL":
            p1 = np.array((z - cz, y - cy))
        p0 = self.p0
        p1 = self.get_image_point_coord(x, y, z)

        axis = np.cross(p0, p1)
        norm = np.linalg.norm(axis)
        if norm == 0:
            return
        axis = axis / norm
        angle = np.arccos(np.dot(p0, p1) / (np.linalg.norm(p0) * np.linalg.norm(p1)))

        self.viewer.slice_.q_orientation = transformations.quaternion_multiply(
            self.viewer.slice_.q_orientation, transformations.quaternion_about_axis(angle, axis)
        )

        az, ay, ax = transformations.euler_from_quaternion(self.viewer.slice_.q_orientation)
        Publisher.sendMessage("Update reorient angles", angles=(ax, ay, az))

        self._discard_buffers()
        if self.viewer.slice_.current_mask:
            self.viewer.slice_.current_mask.clear_history()
        Publisher.sendMessage(f"Reload actual slice {self.viewer.orientation}")
        self.p0 = self.get_image_point_coord(x, y, z)

    def get_image_point_coord(self, x, y, z):
        cx, cy, cz = self.viewer.slice_.center
        if self.viewer.orientation == "AXIAL":
            z = cz
        elif self.viewer.orientation == "CORONAL":
            y = cy
        elif self.viewer.orientation == "SAGITAL":
            x = cx

        x, y, z = x - cx, y - cy, z - cz

        M = transformations.quaternion_matrix(self.viewer.slice_.q_orientation)
        tcoord = np.array((z, y, x, 1)).dot(M)
        tcoord = tcoord[:3] / tcoord[3]

        #  print (z, y, x), tcoord
        return tcoord

    def _set_reorientation_angles(self, angles):
        ax, ay, az = angles
        q = transformations.quaternion_from_euler(az, ay, ax)
        self.viewer.slice_.q_orientation = q

        self._discard_buffers()
        self.viewer.slice_.current_mask.clear_history()
        Publisher.sendMessage("Reload actual slice")

    def _create_line(self, x0, y0, x1, y1, color):
        line = vtkLineSource()
        line.SetPoint1(x0, y0, 0)
        line.SetPoint2(x1, y1, 0)

        coord = vtkCoordinate()
        coord.SetCoordinateSystemToDisplay()

        mapper = vtkPolyDataMapper2D()
        mapper.SetTransformCoordinate(coord)
        mapper.SetInputConnection(line.GetOutputPort())
        mapper.Update()

        actor = vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetProperty().SetLineWidth(2.0)
        actor.GetProperty().SetColor(color)
        actor.GetProperty().SetOpacity(0.5)

        self.viewer.slice_data.renderer.AddActor(actor)

        self.actors.append(actor)

        return line

    def draw_lines(self):
        if self.viewer.orientation == "AXIAL":
            color1 = (0, 1, 0)
            color2 = (0, 0, 1)
        elif self.viewer.orientation == "CORONAL":
            color1 = (1, 0, 0)
            color2 = (0, 0, 1)
        elif self.viewer.orientation == "SAGITAL":
            color1 = (1, 0, 0)
            color2 = (0, 1, 0)

        self.line1 = self._create_line(0, 0.5, 1, 0.5, color1)
        self.line2 = self._create_line(0.5, 0, 0.5, 1, color2)

    def _discard_buffers(self):
        for buffer_ in self.viewer.slice_.buffer_slices.values():
            buffer_.discard_vtk_image()
            buffer_.discard_image()


class FFillConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.dlg_visible = False
        self.target = "2D"
        self.con_2d = 4
        self.con_3d = 6


class FloodFillMaskInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_MASK_FFILL

        self.viewer = viewer
        self.orientation = self.viewer.orientation

        self.picker = vtkWorldPointPicker()
        self.slice_actor = viewer.slice_data.actor
        self.slice_data = viewer.slice_data

        self.config = FFillConfig()
        self.dlg_ffill = None

        # InVesalius uses the following values to mark non selected parts in a
        # mask:
        # 0 - Threshold
        # 1 - Manual edition and  floodfill
        # 2 - Watershed
        self.t0 = 0
        self.t1 = 2
        self.fill_value = 254

        self._dlg_title = _("Fill holes")
        self._progr_title = _("Fill hole")
        self._progr_msg = _("Filling hole ...")

        self.AddObserver("LeftButtonPressEvent", self.OnFFClick)

    def SetUp(self):
        if not self.config.dlg_visible:
            self.config.dlg_visible = True
            self.dlg_ffill = dialogs.FFillOptionsDialog(self._dlg_title, self.config)
            self.dlg_ffill.Show()

    def CleanUp(self):
        if (self.dlg_ffill is not None) and (self.config.dlg_visible):
            self.config.dlg_visible = False
            self.dlg_ffill.Destroy()
            self.dlg_ffill = None

    def OnFFClick(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        # viewer = self.viewer
        # iren = viewer.interactor
        mouse_x, mouse_y = self.GetMousePosition()
        x, y, z = self.viewer.get_voxel_coord_by_screen_pos(mouse_x, mouse_y, self.picker)

        mask = self.viewer.slice_.current_mask.matrix[1:, 1:, 1:]
        if mask[z, y, x] < self.t0 or mask[z, y, x] > self.t1:
            return

        if self.config.target == "3D":
            bstruct = np.array(
                generate_binary_structure(3, CON3D[self.config.con_3d]), dtype="uint8"
            )
            self.viewer.slice_.do_threshold_to_all_slices()
            cp_mask = self.viewer.slice_.current_mask.matrix.copy()
        else:
            _bstruct = generate_binary_structure(2, CON2D[self.config.con_2d])
            if self.orientation == "AXIAL":
                bstruct = np.zeros((1, 3, 3), dtype="uint8")
                bstruct[0] = _bstruct
            elif self.orientation == "CORONAL":
                bstruct = np.zeros((3, 1, 3), dtype="uint8")
                bstruct[:, 0, :] = _bstruct
            elif self.orientation == "SAGITAL":
                bstruct = np.zeros((3, 3, 1), dtype="uint8")
                bstruct[:, :, 0] = _bstruct

        if self.config.target == "2D":
            floodfill.floodfill_threshold(
                mask, [[x, y, z]], self.t0, self.t1, self.fill_value, bstruct, mask
            )
            b_mask = self.viewer.slice_.buffer_slices[self.orientation].mask
            index = self.viewer.slice_.buffer_slices[self.orientation].index

            if self.orientation == "AXIAL":
                p_mask = mask[index, :, :].copy()
            elif self.orientation == "CORONAL":
                p_mask = mask[:, index, :].copy()
            elif self.orientation == "SAGITAL":
                p_mask = mask[:, :, index].copy()

            self.viewer.slice_.current_mask.save_history(index, self.orientation, p_mask, b_mask)
        else:
            with futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    floodfill.floodfill_threshold,
                    mask,
                    [[x, y, z]],
                    self.t0,
                    self.t1,
                    self.fill_value,
                    bstruct,
                    mask,
                )

                dlg = wx.ProgressDialog(
                    self._progr_title,
                    self._progr_msg,
                    parent=wx.GetApp().GetTopWindow(),
                    style=wx.PD_APP_MODAL,
                )
                while not future.done():
                    dlg.Pulse()
                    time.sleep(0.1)

                dlg.Destroy()

            self.viewer.slice_.current_mask.save_history(
                0, "VOLUME", self.viewer.slice_.current_mask.matrix.copy(), cp_mask
            )

        self.viewer.slice_.buffer_slices["AXIAL"].discard_mask()
        self.viewer.slice_.buffer_slices["CORONAL"].discard_mask()
        self.viewer.slice_.buffer_slices["SAGITAL"].discard_mask()

        self.viewer.slice_.buffer_slices["AXIAL"].discard_vtk_mask()
        self.viewer.slice_.buffer_slices["CORONAL"].discard_vtk_mask()
        self.viewer.slice_.buffer_slices["SAGITAL"].discard_vtk_mask()

        self.viewer.slice_.current_mask.was_edited = True
        self.viewer.slice_.current_mask.modified(True)
        Publisher.sendMessage("Reload actual slice")


class RemoveMaskPartsInteractorStyle(FloodFillMaskInteractorStyle):
    def __init__(self, viewer):
        FloodFillMaskInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_REMOVE_MASK_PARTS
        # InVesalius uses the following values to mark selected parts in a
        # mask:
        # 255 - Threshold
        # 254 - Manual edition and  floodfill
        # 253 - Watershed
        self.t0 = 253
        self.t1 = 255
        self.fill_value = 1

        self._dlg_title = _("Remove parts")
        self._progr_title = _("Remove part")
        self._progr_msg = _("Removing part ...")


class CropMaskConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.dlg_visible = False


class CropMaskInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_CROP_MASK

        self.viewer = viewer
        self.orientation = self.viewer.orientation
        self.picker = vtkWorldPointPicker()
        self.slice_actor = viewer.slice_data.actor
        self.slice_data = viewer.slice_data
        self.draw_retangle = None

        self.config = CropMaskConfig()

    def __evts__(self):
        self.AddObserver("MouseMoveEvent", self.OnMove)
        self.AddObserver("LeftButtonPressEvent", self.OnLeftPressed)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        Publisher.subscribe(self.CropMask, "Crop mask")

    def OnMove(self, obj, evt):
        x, y = self.GetMousePosition()
        self.draw_retangle.MouseMove(x, y)

    def OnLeftPressed(self, obj, evt):
        self.draw_retangle.mouse_pressed = True
        x, y = self.GetMousePosition()
        self.draw_retangle.LeftPressed(x, y)

    def OnReleaseLeftButton(self, obj, evt):
        self.draw_retangle.mouse_pressed = False
        self.draw_retangle.ReleaseLeft()

    def SetUp(self):
        self.draw_retangle = geom.DrawCrop2DRetangle()
        self.draw_retangle.SetViewer(self.viewer)

        self.viewer.canvas.draw_list.append(self.draw_retangle)
        self.viewer.UpdateCanvas()

        if not (self.config.dlg_visible):
            self.config.dlg_visible = True

            dlg = dialogs.CropOptionsDialog(self.config)
            dlg.UpdateValues(self.draw_retangle.box.GetLimits())
            dlg.Show()

        self.__evts__()
        # self.draw_lines()
        # Publisher.sendMessage('Hide current mask')
        # Publisher.sendMessage('Reload actual slice')

    def CleanUp(self):
        self.viewer.canvas.draw_list.remove(self.draw_retangle)
        Publisher.sendMessage("Redraw canvas")

    def CropMask(self):
        if self.viewer.orientation == "AXIAL":
            xi, xf, yi, yf, zi, zf = self.draw_retangle.box.GetLimits()

            xi += 1
            xf += 1

            yi += 1
            yf += 1

            zi += 1
            zf += 1

            self.viewer.slice_.do_threshold_to_all_slices()
            cp_mask = self.viewer.slice_.current_mask.matrix.copy()

            tmp_mask = self.viewer.slice_.current_mask.matrix[
                zi - 1 : zf + 1, yi - 1 : yf + 1, xi - 1 : xf + 1
            ].copy()

            self.viewer.slice_.current_mask.matrix[:] = 1

            self.viewer.slice_.current_mask.matrix[
                zi - 1 : zf + 1, yi - 1 : yf + 1, xi - 1 : xf + 1
            ] = tmp_mask

            self.viewer.slice_.current_mask.save_history(
                0, "VOLUME", self.viewer.slice_.current_mask.matrix.copy(), cp_mask
            )

            self.viewer.slice_.buffer_slices["AXIAL"].discard_mask()
            self.viewer.slice_.buffer_slices["CORONAL"].discard_mask()
            self.viewer.slice_.buffer_slices["SAGITAL"].discard_mask()

            self.viewer.slice_.buffer_slices["AXIAL"].discard_vtk_mask()
            self.viewer.slice_.buffer_slices["CORONAL"].discard_vtk_mask()
            self.viewer.slice_.buffer_slices["SAGITAL"].discard_vtk_mask()

            self.viewer.slice_.current_mask.was_edited = True
            self.viewer.slice_.current_mask.modified(True)
            Publisher.sendMessage("Reload actual slice")


class SelectPartConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.mask = None
        self.con_3d = 6
        self.dlg_visible = False
        self.mask_name = ""


class SelectMaskPartsInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_SELECT_MASK_PARTS

        self.viewer = viewer
        self.orientation = self.viewer.orientation

        self.picker = vtkWorldPointPicker()
        self.slice_actor = viewer.slice_data.actor
        self.slice_data = viewer.slice_data

        self.config = SelectPartConfig()
        self.dlg = None

        # InVesalius uses the following values to mark selected parts in a
        # mask:
        # 255 - Threshold
        # 254 - Manual edition and  floodfill
        # 253 - Watershed
        self.t0 = 253
        self.t1 = 255
        self.fill_value = 254

        self.AddObserver("LeftButtonPressEvent", self.OnSelect)

    def SetUp(self):
        if not self.config.dlg_visible:
            import invesalius.data.mask as mask

            default_name = const.MASK_NAME_PATTERN % (mask.Mask.general_index + 2)

            self.config.mask_name = default_name
            self.config.dlg_visible = True
            self.dlg = dialogs.SelectPartsOptionsDialog(self.config)
            self.dlg.Show()

    def CleanUp(self):
        if self.dlg is None:
            return

        dialog_return = self.dlg.GetReturnCode()

        if self.config.dlg_visible:
            self.config.dlg_visible = False
            self.dlg.Destroy()
            self.dlg = None

        if self.config.mask:
            if dialog_return == wx.OK:
                self.config.mask.name = self.config.mask_name
                self.viewer.slice_._add_mask_into_proj(self.config.mask)
                self.viewer.slice_.SelectCurrentMask(self.config.mask.index)
                Publisher.sendMessage("Change mask selected", index=self.config.mask.index)

            del self.viewer.slice_.aux_matrices["SELECT"]
            self.viewer.slice_.to_show_aux = ""
            Publisher.sendMessage("Reload actual slice")
            self.config.mask = None

    def OnSelect(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        iren = self.viewer.interactor
        mouse_x, mouse_y = self.GetMousePosition()
        x, y, z = self.viewer.get_voxel_coord_by_screen_pos(mouse_x, mouse_y, self.picker)

        mask = self.viewer.slice_.current_mask.matrix[1:, 1:, 1:]

        bstruct = np.array(generate_binary_structure(3, CON3D[self.config.con_3d]), dtype="uint8")
        self.viewer.slice_.do_threshold_to_all_slices()

        if self.config.mask is None:
            self._create_new_mask()

        if iren.GetControlKey():
            floodfill.floodfill_threshold(
                self.config.mask.matrix[1:, 1:, 1:],
                [[x, y, z]],
                254,
                255,
                0,
                bstruct,
                self.config.mask.matrix[1:, 1:, 1:],
            )
        else:
            floodfill.floodfill_threshold(
                mask,
                [[x, y, z]],
                self.t0,
                self.t1,
                self.fill_value,
                bstruct,
                self.config.mask.matrix[1:, 1:, 1:],
            )

        self.viewer.slice_.aux_matrices["SELECT"] = self.config.mask.matrix[1:, 1:, 1:]
        self.viewer.slice_.to_show_aux = "SELECT"

        self.config.mask.was_edited = True
        Publisher.sendMessage("Reload actual slice")

    def _create_new_mask(self):
        mask = self.viewer.slice_.create_new_mask(show=False, add_to_project=False)
        mask.was_edited = True
        mask.matrix[0, :, :] = 1
        mask.matrix[:, 0, :] = 1
        mask.matrix[:, :, 0] = 1

        self.config.mask = mask


class FFillSegmentationConfig(metaclass=utils.Singleton):
    def __init__(self):
        self.dlg_visible = False
        self.dlg = None
        self.target = "2D"
        self.con_2d = 4
        self.con_3d = 6

        self.t0: Optional[int] = None
        self.t1: Optional[int] = None

        self.fill_value = 254

        self.method = "dynamic"

        self.dev_min = 25
        self.dev_max = 25

        self.use_ww_wl = True

        self.confid_mult = 2.5
        self.confid_iters = 3


class FloodFillSegmentInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)

        self.state_code = const.SLICE_STATE_FFILL_SEGMENTATION

        self.viewer = viewer
        self.orientation = self.viewer.orientation

        self.picker = vtkWorldPointPicker()
        self.slice_actor = viewer.slice_data.actor
        self.slice_data = viewer.slice_data

        self.config = FFillSegmentationConfig()

        self._progr_title = _("Region growing")
        self._progr_msg = _("Segmenting ...")

        self.AddObserver("LeftButtonPressEvent", self.OnFFClick)

    def SetUp(self):
        if not self.config.dlg_visible:
            if self.config.t0 is None:
                image = self.viewer.slice_.matrix
                _min, _max = image.min(), image.max()

                self.config.t0 = int(_min + (3.0 / 4.0) * (_max - _min))
                self.config.t1 = int(_max)

            self.config.dlg_visible = True
            self.config.dlg = dialogs.FFillSegmentationOptionsDialog(self.config)
            self.config.dlg.Show()

    def CleanUp(self):
        if (self.config.dlg is not None) and (self.config.dlg_visible):
            self.config.dlg_visible = False
            self.config.dlg.Destroy()
            self.config.dlg = None

    def OnFFClick(self, obj, evt):
        if self.viewer.slice_.buffer_slices[self.orientation].mask is None:
            return

        if self.config.target == "3D":
            self.do_3d_seg()
        else:
            self.do_2d_seg()

        self.viewer.slice_.buffer_slices["AXIAL"].discard_mask()
        self.viewer.slice_.buffer_slices["CORONAL"].discard_mask()
        self.viewer.slice_.buffer_slices["SAGITAL"].discard_mask()

        self.viewer.slice_.buffer_slices["AXIAL"].discard_vtk_mask()
        self.viewer.slice_.buffer_slices["CORONAL"].discard_vtk_mask()
        self.viewer.slice_.buffer_slices["SAGITAL"].discard_vtk_mask()

        self.viewer.slice_.current_mask.was_edited = True
        self.viewer.slice_.current_mask.modified(self.config.target == "3D")
        Publisher.sendMessage("Reload actual slice")

    def do_2d_seg(self):
        # viewer = self.viewer
        # iren = viewer.interactor
        mouse_x, mouse_y = self.GetMousePosition()
        x, y = self.viewer.get_slice_pixel_coord_by_screen_pos(mouse_x, mouse_y, self.picker)

        mask = self.viewer.slice_.buffer_slices[self.orientation].mask.copy()
        image = self.viewer.slice_.buffer_slices[self.orientation].image

        if self.config.method == "confidence":
            dy, dx = image.shape
            image = image.reshape((1, dy, dx))
            mask = mask.reshape((1, dy, dx))

            bstruct = np.array(
                generate_binary_structure(2, CON2D[self.config.con_2d]), dtype="uint8"
            )
            bstruct = bstruct.reshape((1, 3, 3))

            out_mask = self.do_rg_confidence(image, mask, (x, y, 0), bstruct)
        else:
            if self.config.method == "threshold":
                v = image[y, x]
                t0 = self.config.t0
                t1 = self.config.t1

            elif self.config.method == "dynamic":
                if self.config.use_ww_wl:
                    print("Using WW&WL")
                    ww = self.viewer.slice_.window_width
                    wl = self.viewer.slice_.window_level
                    image = get_LUT_value_255(image, ww, wl)

                v = image[y, x]

                t0 = v - self.config.dev_min
                t1 = v + self.config.dev_max

            if image[y, x] < t0 or image[y, x] > t1:
                return

            dy, dx = image.shape
            image = image.reshape((1, dy, dx))
            mask = mask.reshape((1, dy, dx))

            out_mask = np.zeros_like(mask)

            bstruct = np.array(
                generate_binary_structure(2, CON2D[self.config.con_2d]), dtype="uint8"
            )
            bstruct = bstruct.reshape((1, 3, 3))

            floodfill.floodfill_threshold(image, [[x, y, 0]], t0, t1, 1, bstruct, out_mask)

        mask[out_mask.astype("bool")] = self.config.fill_value

        index = self.viewer.slice_.buffer_slices[self.orientation].index
        b_mask = self.viewer.slice_.buffer_slices[self.orientation].mask
        vol_mask = self.viewer.slice_.current_mask.matrix[1:, 1:, 1:]

        if self.orientation == "AXIAL":
            vol_mask[index, :, :] = mask
        elif self.orientation == "CORONAL":
            vol_mask[:, index, :] = mask
        elif self.orientation == "SAGITAL":
            vol_mask[:, :, index] = mask

        self.viewer.slice_.current_mask.save_history(index, self.orientation, mask, b_mask)

    def do_3d_seg(self):
        # viewer = self.viewer
        # iren = viewer.interactor
        mouse_x, mouse_y = self.GetMousePosition()
        x, y, z = self.viewer.get_voxel_coord_by_screen_pos(mouse_x, mouse_y, self.picker)

        mask = self.viewer.slice_.current_mask.matrix[1:, 1:, 1:]
        image = self.viewer.slice_.matrix

        if self.config.method != "confidence":
            if self.config.method == "threshold":
                v = image[z, y, x]
                t0 = self.config.t0
                t1 = self.config.t1

            elif self.config.method == "dynamic":
                if self.config.use_ww_wl:
                    print("Using WW&WL")
                    ww = self.viewer.slice_.window_width
                    wl = self.viewer.slice_.window_level
                    image = get_LUT_value_255(image, ww, wl)

                v = image[z, y, x]

                t0 = v - self.config.dev_min
                t1 = v + self.config.dev_max

            if image[z, y, x] < t0 or image[z, y, x] > t1:
                return

        bstruct = np.array(generate_binary_structure(3, CON3D[self.config.con_3d]), dtype="uint8")
        self.viewer.slice_.do_threshold_to_all_slices()
        cp_mask = self.viewer.slice_.current_mask.matrix.copy()

        if self.config.method == "confidence":
            with futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.do_rg_confidence, image, mask, (x, y, z), bstruct)

                self.config.dlg.panel_ffill_progress.Enable()
                self.config.dlg.panel_ffill_progress.StartTimer()
                while not future.done():
                    self.config.dlg.panel_ffill_progress.Pulse()
                    self.config.dlg.Update()
                    time.sleep(0.1)
                self.config.dlg.panel_ffill_progress.StopTimer()
                self.config.dlg.panel_ffill_progress.Disable()
                out_mask = future.result()
        else:
            out_mask = np.zeros_like(mask)
            with futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    floodfill.floodfill_threshold, image, [[x, y, z]], t0, t1, 1, bstruct, out_mask
                )

                self.config.dlg.panel_ffill_progress.Enable()
                self.config.dlg.panel_ffill_progress.StartTimer()
                while not future.done():
                    self.config.dlg.panel_ffill_progress.Pulse()
                    self.config.dlg.Update()
                    time.sleep(0.1)
                self.config.dlg.panel_ffill_progress.StopTimer()
                self.config.dlg.panel_ffill_progress.Disable()

        mask[out_mask.astype("bool")] = self.config.fill_value

        self.viewer.slice_.current_mask.save_history(
            0, "VOLUME", self.viewer.slice_.current_mask.matrix.copy(), cp_mask
        )

    def do_rg_confidence(self, image, mask, p, bstruct):
        x, y, z = p
        if self.config.use_ww_wl:
            ww = self.viewer.slice_.window_width
            wl = self.viewer.slice_.window_level
            image = get_LUT_value_255(image, ww, wl)
        bool_mask = np.zeros_like(mask, dtype="bool")
        out_mask = np.zeros_like(mask)

        for k in range(int(z - 1), int(z + 2)):
            if k < 0 or k >= bool_mask.shape[0]:
                continue
            for j in range(int(y - 1), int(y + 2)):
                if j < 0 or j >= bool_mask.shape[1]:
                    continue
                for i in range(int(x - 1), int(x + 2)):
                    if i < 0 or i >= bool_mask.shape[2]:
                        continue
                    bool_mask[k, j, i] = True

        for i in range(self.config.confid_iters):
            var = np.std(image[bool_mask])
            mean = np.mean(image[bool_mask])

            t0 = mean - var * self.config.confid_mult
            t1 = mean + var * self.config.confid_mult

            floodfill.floodfill_threshold(image, [[x, y, z]], t0, t1, 1, bstruct, out_mask)

            bool_mask[out_mask == 1] = True

        return out_mask


class Styles:
    styles = {
        const.STATE_DEFAULT: DefaultInteractorStyle,
        const.SLICE_STATE_CROSS: CrossInteractorStyle,
        # Use the same style during registration that is used when enabling cross mode on the toolbar;
        # that is, allow selecting point from the slices using the mouse.
        const.STATE_REGISTRATION: CrossInteractorStyle,
        const.STATE_WL: WWWLInteractorStyle,
        const.STATE_MEASURE_DISTANCE: LinearMeasureInteractorStyle,
        const.STATE_MEASURE_ANGLE: AngularMeasureInteractorStyle,
        const.STATE_MEASURE_DENSITY_ELLIPSE: DensityMeasureEllipseStyle,
        const.STATE_MEASURE_DENSITY_POLYGON: DensityMeasurePolygonStyle,
        const.STATE_NAVIGATION: NavigationInteractorStyle,
        const.STATE_PAN: PanMoveInteractorStyle,
        const.STATE_SPIN: SpinInteractorStyle,
        const.STATE_ZOOM: ZoomInteractorStyle,
        const.STATE_ZOOM_SL: ZoomSLInteractorStyle,
        const.SLICE_STATE_SCROLL: ChangeSliceInteractorStyle,
        const.SLICE_STATE_EDITOR: EditorInteractorStyle,
        const.SLICE_STATE_WATERSHED: WaterShedInteractorStyle,
        const.SLICE_STATE_REORIENT: ReorientImageInteractorStyle,
        const.SLICE_STATE_MASK_FFILL: FloodFillMaskInteractorStyle,
        const.SLICE_STATE_REMOVE_MASK_PARTS: RemoveMaskPartsInteractorStyle,
        const.SLICE_STATE_SELECT_MASK_PARTS: SelectMaskPartsInteractorStyle,
        const.SLICE_STATE_FFILL_SEGMENTATION: FloodFillSegmentInteractorStyle,
        const.SLICE_STATE_CROP_MASK: CropMaskInteractorStyle,
        const.SLICE_STATE_TRACTS: TractsInteractorStyle,
    }

    @classmethod
    def add_style(cls, style_cls, level=1):
        if style_cls in cls.styles.values():
            for style_id in cls.styles:
                if cls.styles[style_id] == style_cls:
                    const.SLICE_STYLES.append(style_id)
                    const.STYLE_LEVEL[style_id] = level
                    return style_id

        new_style_id = max(cls.styles) + 1
        cls.styles[new_style_id] = style_cls
        const.SLICE_STYLES.append(new_style_id)
        const.STYLE_LEVEL[new_style_id] = level
        return new_style_id

    @classmethod
    def remove_style(cls, style_id):
        del cls.styles[style_id]

    @classmethod
    def get_style(cls, style):
        return cls.styles[style]
