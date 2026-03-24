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


import time
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import wx
from skimage.draw import polygon2mask
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleRubberBandZoom,
    vtkInteractorStyleTrackballCamera,
)
from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkCoordinate, vtkPointPicker, vtkPropPicker

import invesalius.constants as const
import invesalius.data.slice_ as slc
import invesalius.project as prj
import invesalius.session as ses
from invesalius.data.polygon_select import PolygonSelectCanvas
from invesalius.pubsub import pub as Publisher
from invesalius.utils import vtkarray_to_numpy
from invesalius_rs import mask_cut

PROP_MEASURE = 0.8

if TYPE_CHECKING:
    from vtkmodules.vtkRenderingCore import vtkCamera

    from invesalius.data.viewer_volume import Viewer


class Base3DInteractorStyle(vtkInteractorStyleTrackballCamera):
    def __init__(self, viewer: "Viewer"):
        self.right_pressed = False
        self.left_pressed = False
        self.middle_pressed = False

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.AddObserver("RightButtonPressEvent", self.OnPressRightButton)
        self.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)

        self.AddObserver("MiddleButtonPressEvent", self.OnMiddleButtonPressEvent)
        self.AddObserver("MiddleButtonReleaseEvent", self.OnMiddleButtonReleaseEvent)

        self.AddObserver("MouseMoveEvent", self.OnStatusbarMouseMove)
        self.AddObserver("LeaveEvent", self.OnStatusbarLeave)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status

    def OnStatusbarMouseMove(self, evt, obj):
        if self.nav_status:
            return
        Publisher.sendMessage("Update statusbar image info", info="Window: Volume")

    def OnStatusbarLeave(self, evt, obj):
        if self.nav_status:
            return
        Publisher.sendMessage("Clear statusbar image info")

    def OnPressLeftButton(self, evt, obj):
        self.left_pressed = True

    def OnReleaseLeftButton(self, evt, obj):
        self.left_pressed = False

    def OnPressRightButton(self, evt, obj):
        self.right_pressed = True

    def OnReleaseRightButton(self, evt, obj):
        self.right_pressed = False

    def OnMiddleButtonPressEvent(self, evt, obj):
        self.middle_pressed = True

    def OnMiddleButtonReleaseEvent(self, evt, obj):
        self.middle_pressed = False


class DefaultInteractorStyle(Base3DInteractorStyle):
    """
    Interactor style responsible for navigating 3d volume viewer using three mouse buttons:

    * Rotate by moving mouse with left button pressed.
    * Pan by moving mouse with middle button pressed.
    * Spin by moving mouse with right button pressed.
    * Select marker by clicking right button on the marker.
    * Focus camera by double clicking right button.
    """

    def __init__(self, viewer: "Viewer"):
        super().__init__(viewer)
        self.state_code = const.STATE_DEFAULT

        self.last_click_time = 0
        self.double_click_max_interval = 1.0  # in seconds

        self.nav_status = False

        self.viewer = viewer

        self.picker = vtkCellPicker()
        self.picker.SetTolerance(1e-3)
        self.viewer.interactor.SetPicker(self.picker)

        # Keep track of whether a marker was found under the mouse cursor.
        self.marker_found = False

        # Rotate using left button
        self.AddObserver("LeftButtonPressEvent", self.OnLeftClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnLeftRelease)

        # Pick marker using left button.
        self.AddObserver("LeftButtonPressEvent", self.PickMarker)

        # Spin using right button.
        self.AddObserver("RightButtonPressEvent", self.OnRightClick)
        self.AddObserver("RightButtonReleaseEvent", self.OnRightRelease)

        # Zoom using mouse wheel.
        self.AddObserver("MouseWheelForwardEvent", self.OnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)

        self.AddObserver("MouseMoveEvent", self.OnMouseMove)
        self.AddObserver("MiddleButtonReleaseEvent", self.OnMiddleRelease)

        # Set camera focus using left double-click.
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.SetCameraFocus)

        # Reset camera using right double-click.
        self.viewer.interactor.Bind(wx.EVT_RIGHT_DCLICK, self.ResetCamera)

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status

    def OnMiddleRelease(self, evt, obj):
        evt.EndPan()

    def OnMouseMove(self, evt, obj):
        if self.left_pressed:
            evt.Rotate()
            evt.OnLeftButtonDown()

        elif self.right_pressed:
            evt.Spin()
            evt.OnRightButtonDown()

        elif self.middle_pressed:
            evt.Pan()
            evt.OnMiddleButtonDown()

    def OnRightClick(self, evt, obj):
        evt.StartSpin()

    def OnRightRelease(self, evt, obj):
        evt.EndSpin()

    def OnLeftClick(self, evt, obj):
        evt.StartRotate()

    def OnLeftRelease(self, evt, obj):
        evt.EndRotate()

    def OnScrollForward(self, evt, obj):
        self.OnMouseWheelForward()

    def OnScrollBackward(self, evt, obj):
        self.OnMouseWheelBackward()

    def PickMarker(self, evt, obj):
        if self.nav_status:
            return
        # Get the mouse position in the viewer.
        x, y = self.viewer.get_vtk_mouse_position()

        # Temporarily hide all surfaces to allow the picker to pick markers without interference.
        self.viewer.surface_geometry.HideAllSurfaces()

        # Pick the actor under the mouse cursor.
        self.picker.Pick(x, y, 0, self.viewer.ren)

        # Show the surfaces again.
        self.viewer.surface_geometry.ShowAllSurfaces()

        actor = self.picker.GetActor()
        self.marker_found = actor

        if self.marker_found is not None:
            Publisher.sendMessage("Select marker by actor", actor=actor)

    def SetCameraFocus(self, evt):
        # If an actor was already found by PickMarker, use its center as the camera focus, otherwise
        # pick the actor under the mouse cursor, this time without hiding the surfaces.
        if self.nav_status:
            return
        if self.marker_found:
            actor = self.marker_found
        else:
            # Get the mouse position in the viewer.
            x, y = self.viewer.get_vtk_mouse_position()

            # Pick the actor under the mouse cursor.
            self.picker.Pick(x, y, 0, self.viewer.ren)

            actor = self.picker.GetActor()

            # If no actor was found, return early.
            if actor is None:
                return

        center = self.viewer.surface_geometry.GetSurfaceCenter(actor)

        renderer = self.viewer.ren
        camera = renderer.GetActiveCamera()
        camera.SetFocalPoint(center)
        renderer.ResetCameraClippingRange()

        renderer.Render()
        self.viewer.interactor.GetRenderWindow().Render()

    def ResetCamera(self, evt):
        if self.nav_status:
            return
        renderer = self.viewer.ren
        interactor = self.viewer.interactor

        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        interactor.Render()

    def CleanUp(self):
        """Clean up the interactor style."""
        # Note: when bind events in the viewer, they are not automatically removed when
        # the style is cleaned up! if the bind is in the style (i.e. self.AddObserver),
        # then it is ok.
        self.viewer.interactor.Unbind(wx.EVT_RIGHT_DCLICK, handler=self.ResetCamera)
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK, handler=self.SetCameraFocus)


class ZoomInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for zooming by clicking left mouse button and moving the mouse.
    """

    def __init__(self, viewer):
        super().__init__(viewer)

        self.state_code = const.STATE_ZOOM

        self.viewer = viewer

        self.RemoveObservers("LeftButtonPressEvent")
        self.RemoveObservers("LeftButtonReleaseEvent")

        self.AddObserver("MouseMoveEvent", self.OnMouseMoveZoom)

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.zoom_started = False

        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.ResetCamera)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        super().CleanUp()
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK, handler=self.ResetCamera)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnMouseMoveZoom(self, evt, obj):
        if self.zoom_started:
            evt.Dolly()
            evt.OnLeftButtonDown()

    def OnPressLeftButton(self, evt, obj):
        evt.StartDolly()
        self.zoom_started = True

    def OnReleaseLeftButton(self, evt, obj):
        evt.EndDolly()
        self.zoom_started = False

    def ResetCamera(self, evt):
        renderer = self.viewer.ren
        interactor = self.viewer.interactor

        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        interactor.Render()


class ZoomSLInteractorStyle(vtkInteractorStyleRubberBandZoom):
    """
    Interactor style responsible for zooming by selecting a region.
    """

    def __init__(self, viewer):
        self.viewer = viewer
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.ResetCamera)

        self.state_code = const.STATE_ZOOM_SL

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK, handler=self.ResetCamera)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def ResetCamera(self, evt):
        renderer = self.viewer.ren
        interactor = self.viewer.interactor

        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        interactor.Render()


class PanMoveInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for translating the camera by clicking left mouse button and moving the mouse.
    """

    def __init__(self, viewer):
        super().__init__(viewer)

        self.state_code = const.STATE_PAN

        self.viewer = viewer

        self.panning = False

        self.AddObserver("MouseMoveEvent", self.OnPanMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspan)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        super().CleanUp()
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK, handler=self.OnUnspan)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnPressLeftButton(self, evt, obj):
        self.panning = True

    def OnReleaseLeftButton(self, evt, obj):
        self.panning = False

    def OnPanMove(self, obj, evt):
        if self.panning:
            obj.Pan()
            obj.OnRightButtonDown()

    def OnUnspan(self, evt):
        self.viewer.ren.ResetCamera()
        self.viewer.interactor.Render()


class SpinInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for spinning the camera by clicking left mouse button and moving the mouse.
    """

    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)
        self.state_code = const.STATE_SPIN
        self.viewer = viewer
        self.spinning = False
        self.AddObserver("MouseMoveEvent", self.OnSpinMove)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        super().CleanUp()
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)

    def OnPressLeftButton(self, evt, obj):
        self.spinning = True

    def OnReleaseLeftButton(self, evt, obj):
        self.spinning = False

    def OnSpinMove(self, evt, obj):
        if self.spinning:
            evt.Spin()
            evt.OnRightButtonDown()


class WWWLInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for Window Level & Width functionality.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.state_code = const.STATE_WL

        self.viewer = viewer

        self.last_x = 0
        self.last_y = 0

        self.changing_wwwl = False

        self.RemoveObservers("LeftButtonPressEvent")
        self.RemoveObservers("LeftButtonReleaseEvent")

        self.AddObserver("MouseMoveEvent", self.OnWindowLevelMove)
        self.AddObserver("LeftButtonPressEvent", self.OnWindowLevelClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnWindowLevelRelease)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)
        self.viewer.on_wl = True
        if self.viewer.raycasting_volume:
            self.viewer.text.Show()
            self.viewer.interactor.Render()

    def CleanUp(self):
        super().CleanUp()
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        self.viewer.on_wl = True
        self.viewer.text.Hide()
        self.viewer.interactor.Render()

    def OnWindowLevelMove(self, obj, evt):
        if self.changing_wwwl:
            mouse_x, mouse_y = self.viewer.get_vtk_mouse_position()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            Publisher.sendMessage(
                "Set raycasting relative window and level", diff_wl=diff_x, diff_ww=diff_y
            )
            Publisher.sendMessage("Refresh raycasting widget points")
            Publisher.sendMessage("Render volume viewer")

    def OnWindowLevelClick(self, obj, evt):
        self.last_x, self.last_y = self.viewer.get_vtk_mouse_position()
        self.changing_wwwl = True

    def OnWindowLevelRelease(self, obj, evt):
        self.changing_wwwl = False


class LinearMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for linear measurements by clicking consecutive points in the volume viewer.
    Supports dragging measurement points to reposition them (GitHub Issue #16).
    Shows hand cursor when hovering over measurement points (GitHub Issue #39).
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.state_code = const.STATE_MEASURE_DISTANCE
        self._type = const.LINEAR
        self.measure_picker = vtkPropPicker()

        proj = prj.Project()
        self._radius = min(proj.spacing) * PROP_MEASURE

        # Import MeasureData to track measurements
        from invesalius.data.measures import MeasureData

        self.measures = MeasureData()
        self.selected = None  # Currently selected measurement point for dragging
        self.creating = None  # Measurement being created

        self._bind_events()

    def _bind_events(self):
        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertLinearMeasurePoint)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseMeasurePoint)
        self.AddObserver("MouseMoveEvent", self.OnMoveMeasurePoint)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)
        # Set crosshair cursor for better measurement accuracy
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_CROSS))

    def CleanUp(self):
        super().CleanUp()
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")
        # Restore default cursor when exiting measurement mode
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def OnInsertLinearMeasurePoint(self, obj, evt):
        x, y = self.viewer.get_vtk_mouse_position()

        # If already dragging a point, clicking again deselects it
        if self.selected:
            self.selected = None
            return

        # Check if user clicked on an existing measurement point
        selected = self._verify_clicked_3d(x, y)

        if selected:
            # Select the point for dragging - DON'T add a new point
            self.selected = selected
            return  # CRITICAL: Must return here to prevent adding new point
        else:
            # If not clicking on existing point, add new measurement point
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)
            x, y, z = self.measure_picker.GetPickPosition()
            if self.measure_picker.GetActor():
                self.left_pressed = False
                Publisher.sendMessage(
                    "Add measurement point",
                    position=(x, y, z),
                    type=self._type,
                    location=const.SURFACE,
                    radius=self._radius,
                )
                self.viewer.interactor.Render()
            else:
                self.left_pressed = True

    def OnReleaseMeasurePoint(self, obj, evt):
        """Handle mouse button release - finalize dragging if a point was selected."""
        if self.selected:
            # Show busy cursor before updating position (geodesic computation will start)
            Publisher.sendMessage("Begin busy cursor")

            # Update the final position
            x, y = self.viewer.get_vtk_mouse_position()
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)

            # Only update if we picked a valid surface point
            if self.measure_picker.GetActor():
                x, y, z = self.measure_picker.GetPickPosition()
                n, m, mr = self.selected
                idx = self.measures._list_measures.index((m, mr))
                Publisher.sendMessage(
                    "Change measurement point position", index=idx, npoint=n, pos=(x, y, z)
                )
                self.viewer.interactor.Render()
            else:
                # If no valid pick, restore cursor immediately
                Publisher.sendMessage("End busy cursor")

            # Deselect after release
            self.selected = None

    def OnMoveMeasurePoint(self, obj, evt):
        """Handle mouse movement - drag selected point or update cursor."""
        x, y = self.viewer.get_vtk_mouse_position()

        if self.selected:
            # Dragging a selected measurement point
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)

            # Only update position if we're picking a valid surface point
            if self.measure_picker.GetActor():
                px, py, pz = self.measure_picker.GetPickPosition()
                n, m, mr = self.selected
                idx = self.measures._list_measures.index((m, mr))
                Publisher.sendMessage(
                    "Change measurement point position", index=idx, npoint=n, pos=(px, py, pz)
                )
                self.viewer.interactor.Render()
        else:
            # Not dragging - check if hovering over a measurement point
            # Update cursor to hand icon if over a measurement point
            if self._verify_clicked_3d(x, y):
                self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            else:
                # Restore crosshair cursor when not hovering over a point (measurement mode is active)
                self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_CROSS))

    def _verify_clicked_3d(self, screen_x, screen_y, tolerance=10.0):
        """
        Check if the mouse click is near a measurement point in 3D view.
        Returns (point_index, measurement, measurement_renderer) tuple if found, None otherwise.

        Args:
            screen_x: Screen X coordinate
            screen_y: Screen Y coordinate
            tolerance: Distance tolerance in pixels (default 10.0)
        """
        tolerance_sq = tolerance**2
        coord = vtkCoordinate()
        coord.SetCoordinateSystemToWorld()

        # Check all surface measurements (3D measurements are stored with location=SURFACE)
        if const.SURFACE in self.measures.measures:
            for slice_num in self.measures.measures[const.SURFACE]:
                for m, mr in self.measures.measures[const.SURFACE][slice_num]:
                    if mr.IsComplete():
                        # Check each point in the measurement
                        for n, point in enumerate(m.points):
                            coord.SetValue(point)
                            # Convert world coordinates to display coordinates
                            display_coords = coord.GetComputedDisplayValue(self.viewer.ren)
                            dx = display_coords[0] - screen_x
                            dy = display_coords[1] - screen_y
                            dist_sq = dx * dx + dy * dy

                            if dist_sq <= tolerance_sq:
                                return (n, m, mr)

        return None


class CurvedMeasureInteractorStyle(LinearMeasureInteractorStyle):
    """
    Interactor style responsible for geodesic (curved) measurements by clicking
    two points on a 3D surface in the volume viewer.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.state_code = const.STATE_MEASURE_CURVED_LINEAR
        self._type = const.CURVED_LINEAR
        self._last_click_time = 0
        self._click_debounce = 0.2  # 200ms debounce

    def SetUp(self):
        super().SetUp()
        # Unbind default DClick Focus and bind our Finalize
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnFinalizeCurved)
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)
        # Set crosshair cursor for better measurement accuracy
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_CROSS))

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        # Restore default DClick Focus
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.SetCameraFocus)
        super().CleanUp()
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        # Restore default cursor when exiting measurement mode
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def OnFinalizeCurved(self, evt):
        """Finalize multi-point curved measurement on double-click."""
        multi = ses.Session().GetConfig("geodesic_multi_point", False)
        if multi:
            Publisher.sendMessage("Finalize measurement")
            # LOCK OUT any immediate trailing click events for 300ms
            self._last_click_time = time.time() + 0.3
            self.viewer.interactor.Render()
        evt.Skip()

    def OnInsertLinearMeasurePoint(self, obj, evt):
        # Prevent adding points on the second click of a double-click
        if self.viewer.interactor.GetRepeatCount() > 0:
            return

        # Debounce to prevent ghost clicks (e.g. from trackpad jitter or rapid events)
        current_time = time.time()
        if (current_time - self._last_click_time) < 0.25:  # 250ms debounce
            return
        self._last_click_time = current_time

        x, y = self.viewer.get_vtk_mouse_position()

        # Check if user clicked on an existing measurement point (for dragging)
        selected = self._verify_clicked_3d(x, y)
        if selected:
            # Just set selected, don't return - matches 2D behavior
            self.selected = selected
            # Don't add new point when selecting existing one
        else:
            # Add new measurement point only if not selecting existing one
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)
            x, y, z = self.measure_picker.GetPickPosition()
            actor = self.measure_picker.GetActor()

            # ONLY add points if we hit a surface mesh (not marker spheres or line tubes)
            is_surface = False
            for surface in self.viewer.surface_geometry.surfaces:
                if surface["original"]["actor"] == actor:
                    is_surface = True
                    break

            if actor and is_surface:
                self.left_pressed = False
                polydata = actor.GetMapper().GetInput()
                Publisher.sendMessage(
                    "Add measurement point",
                    position=(x, y, z),
                    type=self._type,
                    location=const.SURFACE,
                    radius=self._radius,
                    polydata=polydata,
                )
                # Explicitly render so the new point marker appears immediately
                Publisher.sendMessage("Render volume viewer")
            else:
                # Allow rotation by clicking on the background
                self.left_pressed = True

    def OnMouseMove(self, evt, obj):
        if self.left_pressed:
            # Only allow rotation, DON'T call OnLeftButtonDown()
            # which would trigger recursive clicks in this interactor style.
            evt.Rotate()


class AngularMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for angular measurements by clicking consecutive points in the volume viewer.
    Supports dragging measurement points to reposition them (GitHub Issue #16).
    Shows hand cursor when hovering over measurement points (GitHub Issue #39).
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.state_code = const.STATE_MEASURE_DISTANCE
        self.measure_picker = vtkPropPicker()

        proj = prj.Project()
        self._radius = min(proj.spacing) * PROP_MEASURE

        # Import MeasureData to track measurements
        from invesalius.data.measures import MeasureData

        self.measures = MeasureData()
        self.selected = None  # Currently selected measurement point for dragging

        self._bind_events()

    def _bind_events(self):
        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertAngularMeasurePoint)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseMeasurePoint)
        self.AddObserver("MouseMoveEvent", self.OnMoveMeasurePoint)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)
        # Set crosshair cursor for better measurement accuracy
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_CROSS))

    def CleanUp(self):
        super().CleanUp()
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")
        # Restore default cursor when exiting measurement mode
        self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def OnInsertAngularMeasurePoint(self, obj, evt):
        x, y = self.viewer.get_vtk_mouse_position()

        # If already dragging a point, clicking again deselects it
        if self.selected:
            self.selected = None
            return

        # Check if user clicked on an existing measurement point
        selected = self._verify_clicked_3d(x, y)
        if selected:
            # Select the point for dragging - DON'T add a new point
            self.selected = selected
            return  # CRITICAL: Must return here to prevent adding new point
        else:
            # If not clicking on existing point, add new measurement point
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)
            x, y, z = self.measure_picker.GetPickPosition()
            if self.measure_picker.GetActor():
                self.left_pressed = False
                Publisher.sendMessage(
                    "Add measurement point",
                    position=(x, y, z),
                    type=const.ANGULAR,
                    location=const.SURFACE,
                    radius=self._radius,
                )
                self.viewer.interactor.Render()
            else:
                self.left_pressed = True

    def OnReleaseMeasurePoint(self, obj, evt):
        """Handle mouse button release - finalize dragging if a point was selected."""
        if self.selected:
            # Show busy cursor before updating position (geodesic computation will start)
            Publisher.sendMessage("Begin busy cursor")

            # Update the final position
            x, y = self.viewer.get_vtk_mouse_position()
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)

            # Only update if we picked a valid surface point
            if self.measure_picker.GetActor():
                x, y, z = self.measure_picker.GetPickPosition()
                n, m, mr = self.selected
                idx = self.measures._list_measures.index((m, mr))
                Publisher.sendMessage(
                    "Change measurement point position", index=idx, npoint=n, pos=(x, y, z)
                )
                self.viewer.interactor.Render()
            else:
                # If no valid pick, restore cursor immediately
                Publisher.sendMessage("End busy cursor")

            # Deselect after release
            self.selected = None

    def OnMoveMeasurePoint(self, obj, evt):
        """Handle mouse movement - drag selected point or update cursor."""
        x, y = self.viewer.get_vtk_mouse_position()

        if self.selected:
            # Dragging a selected measurement point
            self.measure_picker.Pick(x, y, 0, self.viewer.ren)

            # Only update position if we're picking a valid surface point
            if self.measure_picker.GetActor():
                px, py, pz = self.measure_picker.GetPickPosition()
                n, m, mr = self.selected
                idx = self.measures._list_measures.index((m, mr))
                Publisher.sendMessage(
                    "Change measurement point position", index=idx, npoint=n, pos=(px, py, pz)
                )
                self.viewer.interactor.Render()
        else:
            # Not dragging - check if hovering over a measurement point
            # Update cursor to hand icon if over a measurement point
            if self._verify_clicked_3d(x, y):
                self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            else:
                # Restore crosshair cursor when not hovering over a point (measurement mode is active)
                self.viewer.interactor.SetCursor(wx.Cursor(wx.CURSOR_CROSS))

    def _verify_clicked_3d(self, screen_x, screen_y, tolerance=10.0):
        """
        Check if the mouse click is near a measurement point in 3D view.
        Returns (point_index, measurement, measurement_renderer) tuple if found, None otherwise.

        Args:
            screen_x: Screen X coordinate
            screen_y: Screen Y coordinate
            tolerance: Distance tolerance in pixels (default 10.0)
        """
        tolerance_sq = tolerance**2
        coord = vtkCoordinate()
        coord.SetCoordinateSystemToWorld()

        # Check all surface measurements (3D measurements are stored with location=SURFACE)
        if const.SURFACE in self.measures.measures:
            for slice_num in self.measures.measures[const.SURFACE]:
                for m, mr in self.measures.measures[const.SURFACE][slice_num]:
                    if mr.IsComplete():
                        # Check each point in the measurement
                        for n, point in enumerate(m.points):
                            coord.SetValue(point)
                            # Convert world coordinates to display coordinates
                            display_coords = coord.GetComputedDisplayValue(self.viewer.ren)
                            dx = display_coords[0] - screen_x
                            dy = display_coords[1] - screen_y
                            dist_sq = dx * dx + dy * dy

                            if dist_sq <= tolerance_sq:
                                return (n, m, mr)

        return None


class SeedInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for selecting sub-surfaces.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.picker = vtkPointPicker()

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertSeed)

    def OnInsertSeed(self, obj, evt):
        x, y = self.viewer.get_vtk_mouse_position()
        self.picker.Pick(x, y, 0, self.viewer.ren)
        point_id = self.picker.GetPointId()
        if point_id > -1:
            self.viewer.seed_points.append(point_id)
            self.viewer.interactor.Render()
        else:
            self.left_pressed = True


class CrossInteractorStyle(DefaultInteractorStyle):
    """
    This interactor style is used when the user enables the cross mode from the toolbar.

    When the user clicks on the volume viewer, it picks the position shown in the volume viewer
    in the location of the mouse click. The picked position is then used to update the position
    of the slices and the cross pointer.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.AddObserver("RightButtonPressEvent", self.UpdatePointer)
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnNavigationStatus, "Navigation status")

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status

    def SetUp(self):
        self.viewer.CreatePointer()

    def CleanUp(self):
        super().CleanUp()
        self.viewer.DeletePointer()

    def UpdatePointer(self, obj, evt):
        if self.nav_status:
            return
        self.viewer.CreatePointer()
        x, y = self.viewer.get_vtk_mouse_position()

        self.picker.Pick(x, y, 0, self.viewer.ren)

        x, y, z = self.picker.GetPickPosition()

        if self.picker.GetActor():
            Publisher.sendMessage("Update slices position", position=[x, -y, z])
            Publisher.sendMessage("Set cross focal point", position=[x, -y, z, None, None, None])
            Publisher.sendMessage("Update volume viewer pointer", position=[x, y, z])

            Publisher.sendMessage("Update slice viewer")
            Publisher.sendMessage("Render volume viewer")


class RegistrationInteractorStyle(DefaultInteractorStyle):
    """
    This interactor style is used during registration.

    When performing registration, the user can click on the volume viewer to select points for
    registration (i.e., left ear, right ear, and nasion).

    Identical to CrossInteractorStyle for now, but may be extended in the future.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.AddObserver("RightButtonPressEvent", self.UpdatePointer)

    def SetUp(self):
        self.viewer.CreatePointer()

    def CleanUp(self):
        super().CleanUp()
        self.viewer.DeletePointer()

    def UpdatePointer(self, obj, evt):
        x, y = self.viewer.get_vtk_mouse_position()

        self.picker.Pick(x, y, 0, self.viewer.ren)

        x, y, z = self.picker.GetPickPosition()

        if self.picker.GetActor():
            Publisher.sendMessage("Update slices position", position=[x, -y, z])
            Publisher.sendMessage("Set cross focal point", position=[x, -y, z, None, None, None])
            Publisher.sendMessage("Update volume viewer pointer", position=[x, y, z])

            Publisher.sendMessage("Update slice viewer")
            Publisher.sendMessage("Render volume viewer")


class NavigationInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style used for 3d volume viewer during navigation mode. The functions are the same as
    in the default interactor style: rotating, panning, and zooming.
    """

    def __init__(self, viewer):
        super().__init__(viewer)

    def OnMouseMove(self, evt, obj):
        # Do not allow to rotate, pan or zoom if the target mode is active.
        if self.viewer.IsTargetMode():
            return

        super().OnMouseMove(evt, obj)

    def OnScrollForward(self, evt, obj):
        # Do not allow to scroll forward with the mouse wheel if the target mode is active.
        if self.viewer.IsTargetMode():
            return

        super().OnScrollForward(evt, obj)

    def OnScrollBackward(self, evt, obj):
        # Do not allow to scroll backward with the mouse wheel if the target mode is active.
        if self.viewer.IsTargetMode():
            return

        super().OnScrollBackward(evt, obj)


class Mask3DEditorInteractorStyle(DefaultInteractorStyle):
    """Interactor style for selecting a polygon in the volume viewer.

    The polygon, once completed, is used to cut the mask volume using the projection of
    the polygon in the volume viewer.

    Bind events:
        * Left button press: inserts a point in the polygon.
        * Left button double click: completes the polygon connecting the last point to the
          first one.
    """

    def __init__(self, viewer: "Viewer"):
        super().__init__(viewer)

        # mask_data is captured in SetUp() after the mask preview is enabled,
        # so that do_threshold_to_all_slices() has already run.
        self.mask_data = None

        self.m3e_list: list[PolygonSelectCanvas] = []

        self.picker = vtkCellPicker()
        self.picker.PickFromListOn()

        self.edit_mode = const.MASK_3D_EDIT_INCLUDE
        self.depth_val = 1.0

        # keep track if we set preview here or not for UX
        self.has_set_mask_preview = False

        # Initialise resolution from the current viewer widget size so that
        # CutMaskFromPolygons always has a valid aspect ratio even before the
        # first "Receive volume viewer size" message arrives (fixes #1086).
        self.resolution: tuple[int, int] = tuple(viewer.GetSize())

        self._bind_events()
        Publisher.subscribe(self.ClearPolygons, "M3E clear polygons")

    def _bind_events(self):
        ## Remove observers and bindings from super
        self.RemoveObservers("LeftButtonPressEvent")
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK, handler=self.SetCameraFocus)
        self.RemoveObservers("MouseWheelForwardEvent")
        self.RemoveObservers("MouseWheelBackwardEvent")
        self.RemoveObservers("MouseMoveEvent")

        ## Bind events for this style
        self.viewer.canvas.subscribe_event("LeftButtonPressEvent", self.OnLeftButtonPress)
        self.viewer.canvas.subscribe_event(
            "LeftButtonDoubleClickEvent", self.OnLeftButtonDoubleClick
        )
        self.AddObserver("MouseMoveEvent", self.OnMouseMove)
        self.AddObserver("MouseWheelForwardEvent", self.OnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)

        sub = Publisher.subscribe
        sub(self.ReceiveVolumeViewerActiveCamera, "Receive volume viewer active camera")
        sub(self.ReceiveVolumeViewerSize, "Receive volume viewer size")
        sub(self.CutMaskFromPolygons, "M3E cut mask from 3D")
        sub(self.SetEditMode, "M3E set edit mode")
        sub(self.SetDepthValue, "M3E set depth value")
        sub(self.OnMaskChanged, "Change mask selected")

    def SetUp(self):
        """Set up is called just before the style is set in the interactor.

        This is called by the volume ``Viewer.SetInteractorStyle`` method.
        """
        for drawn_polygon in self.viewer.canvas.draw_list:
            if isinstance(drawn_polygon, PolygonSelectCanvas):
                drawn_polygon.visible = True
                drawn_polygon.set_interactive(True)
                self.m3e_list.append(drawn_polygon)

        # Synchronize edit mode and depth value from the GUI's current state
        import invesalius.pubsub as pub

        pub.pub.sendMessage("M3E ask for edit mode")
        pub.pub.sendMessage("M3E ask for depth value")

        if not ses.Session().mask_3d_preview:
            self.has_set_mask_preview = True
            Publisher.sendMessage("Enable mask 3D preview")

        # Capture mask_data HERE, after Enable mask 3D preview has called
        # do_threshold_to_all_slices().  Capturing it in __init__ was too early:
        # the mask matrix was still all-zeros at that point, so every cut would
        # restore to an empty mask.  Fixes #1086 (no-surface path).
        self.mask_data = slc.Slice().current_mask.matrix.copy()

        Publisher.sendMessage(
            "Update viewer caption", viewer_name="Volume", caption="Volume - 3D mask editor"
        )

        # If the mask preview was already active before entering this style,
        # just trigger a re-render (camera was already positioned when preview was enabled).
        if not self.has_set_mask_preview:
            Publisher.sendMessage("Render volume viewer")

        # Capture the mask snapshot AFTER enabling the 3D preview, which runs
        # do_threshold_to_all_slices and modifies the mask. This ensures
        # ClearPolygons restores the correct post-threshold mask state.
        self.mask_data = slc.Slice().current_mask.matrix.copy()

    def CleanUp(self):
        """Clean up is called when the interactor style is removed or changed.

        This is called by the volume ``Viewer.SetInteractorStyle`` method.
        """
        super().CleanUp()
        self.viewer.canvas.unsubscribe_event("LeftButtonPressEvent", self.OnLeftButtonPress)
        self.viewer.canvas.unsubscribe_event(
            "LeftButtonDoubleClickEvent", self.OnLeftButtonDoubleClick
        )

        # Issue #1078: When the 3D editor is disabled, polygons shouldn't just be hidden
        # (which doesn't work properly due to CanvasHandlerBase), they should be fully removed.
        # However, we cannot call self.ClearPolygons() because it also triggers
        # self.OnRestoreInitMask() which reverts the cut! Instead, just remove the canvases:
        self.viewer.canvas.draw_list = [
            drawn_item
            for drawn_item in self.viewer.canvas.draw_list
            if not isinstance(drawn_item, PolygonSelectCanvas)
        ]
        self.m3e_list.clear()

        if self.has_set_mask_preview:
            Publisher.sendMessage("Disable mask 3D preview")

        Publisher.sendMessage("Update viewer caption", viewer_name="Volume", caption="Volume")
        self.viewer.UpdateCanvas()

    def _display_to_world_focal_plane(
        self, display_x: float, display_y: float
    ) -> tuple[float, float, float]:
        """Convert display coordinates to world coordinates on the camera focal plane.
        Projects the given 2D display position onto the plane perpendicular to the
        camera view direction passing through the focal point. This allows polygon
        points to be stored in world space, so they remain aligned with the volume
        when the window is resized, zoomed, or panned.

        Args:
            display_x: X position in display (pixel) coordinates.
            display_y: Y position in display (pixel) coordinates.

        Returns:
            Tuple with (x, y, z) world coordinates on the focal plane.
        """
        renderer = self.viewer.ren
        focal_point = renderer.GetActiveCamera().GetFocalPoint()
        # Find the depth value of the focal point in display coordinates
        renderer.SetWorldPoint(*focal_point, 1.0)
        renderer.WorldToDisplay()
        focal_depth = renderer.GetDisplayPoint()[2]
        # Unproject the 2D mouse position at the focal plane depth
        renderer.SetDisplayPoint(display_x, display_y, focal_depth)
        renderer.DisplayToWorld()
        world_point = renderer.GetWorldPoint()
        w = world_point[3]
        return (world_point[0] / w, world_point[1] / w, world_point[2] / w)

    def SetEditMode(self, mode: int):
        """Set edit mode for the style.

        For now, the edit mode can only be include (0) or exclude (1). In include mode, the
        mask keeps what is inside the polygon, while in exclude mode, it keeps
        what is outside the polygon.

        Args:
            mode (int): The edit mode to set. ``0`` to keep inside polygons, ``1`` to keep outside polygon.
        """
        self.edit_mode = mode
        Publisher.sendMessage("M3E cut mask from 3D")

    def SetDepthValue(self, value: float):
        """Set the depth value for the mask editor (between 0 and 1).

        The depth value is used to determine how deep the mask will be edit in the
        volume. If ``value = 1.0``, the mask will be edited through the entire volume.

        Args:
            value (float): The depth value to set, between 0 and 1. ``0.0`` means no
            depth, ``1.0`` means full depth.
        """
        self.depth_val = value
        Publisher.sendMessage("M3E cut mask from 3D")

    def init_new_polygon(self):
        """Initialize a new polygon for the mask editor."""
        self.m3e_list.append(PolygonSelectCanvas())
        self.viewer.canvas.draw_list.append(self.m3e_list[-1])

    def ClearPolygons(self):
        """Clear all polygons from the viewer and clear masker list in the style."""
        self.viewer.canvas.draw_list = [
            drawn_item
            for drawn_item in self.viewer.canvas.draw_list
            if not isinstance(drawn_item, PolygonSelectCanvas)
        ]
        self.m3e_list.clear()
        self.OnRestoreInitMask()
        self.viewer.UpdateCanvas()

    def OnLeftButtonPress(self, evt):
        if self.viewer.interactor.GetShiftKey():
            # Delegate to standard camera rotation
            self.left_pressed = True
            self.StartRotate()
            return

        # Original polygon insertion logic
        self.OnInsertPolygonPoint(evt)

    def OnLeftButtonDoubleClick(self, evt):
        if self.viewer.interactor.GetShiftKey():
            # Delegate to standard camera focus
            self.SetCameraFocus(evt)
            return

        # Original polygon completion logic
        self.OnInsertPolygon(evt)

    def OnMouseMove(self, obj, evt):
        if self.viewer.interactor.GetShiftKey():
            # If standard camera manipulation was started via shift+left/middle/right click
            if self.left_pressed or self.middle_pressed or self.right_pressed:
                super().OnMouseMove(obj, evt)
                return

        super().OnMouseMove(obj, evt)

    def OnScrollForward(self, obj, evt):
        if self.viewer.interactor.GetShiftKey():
            super().OnScrollForward(obj, evt)
        else:
            self.OnMouseWheelForward()

    def OnScrollBackward(self, obj, evt):
        if self.viewer.interactor.GetShiftKey():
            super().OnScrollBackward(obj, evt)
        else:
            self.OnMouseWheelBackward()

    def OnInsertPolygonPoint(self, evt):
        """Insert a point in the polygon.

        If no polygon is open, it initializes a new one.
        """
        mouse_x, mouse_y = self.viewer.get_vtk_mouse_position()

        if len(self.m3e_list) == 0 or self.m3e_list[-1].complete:
            self.init_new_polygon()

        world_point = self._display_to_world_focal_plane(mouse_x, mouse_y)
        current_masker = self.m3e_list[-1]
        current_masker.insert_point((mouse_x, mouse_y), world_point)
        self.viewer.UpdateCanvas()

    def OnInsertPolygon(self, evt):
        """Complete the polygon by connecting the last point to the first one."""
        if len(self.m3e_list) > 0 and not self.m3e_list[-1].complete:
            self.m3e_list[-1].complete_polygon()
            Publisher.sendMessage("M3E cut mask from 3D")
            self.viewer.UpdateCanvas()

    def ReceiveVolumeViewerActiveCamera(self, cam: "vtkCamera"):
        """Receive the active camera from the volume viewer through pubsub.

        Args:
            cam (vtkCamera): The active camera from the volume viewer.
        """
        width, height = self.resolution

        near, far = self.clipping_range = cam.GetClippingRange()

        # This flip around the Y axis was done to countereffect the flip that vtk performs
        # in volume.py:780. If we do not flip back, what is being displayed is flipped,
        # although the actual coordinates are the initial ones, so the cutting gets wrong
        # after rotations around y or x.
        inv_Y_matrix = np.eye(4)
        inv_Y_matrix[1, 1] = -1

        # Composite transform world coordinates to viewport coordinates
        # This is a concatenation of the view transform (world coordinates to camera
        # coordinates) and the projection transform (camera coordinates to viewport
        # coordinates).
        M = cam.GetCompositeProjectionTransformMatrix(width / float(height), near, far)
        M = vtkarray_to_numpy(M)
        self.world_to_screen = M @ inv_Y_matrix

        # Get the model view matrix, which transforms world coordinates to camera
        # coordinates.
        MV = cam.GetViewTransformMatrix()
        MV = vtkarray_to_numpy(MV)
        self.world_to_camera_coordinates = MV @ inv_Y_matrix

    def ReceiveVolumeViewerSize(self, size: tuple[int, int]):
        """Receive the size of the volume viewer through pubsub.

        Args:
            size (tuple[int, int]): The size of the volume viewer in pixels (width,
            height).
        """
        self.resolution = size

    def OnRestoreInitMask(self):
        """Restore the initial mask data from when the style was setup."""
        _mat = self.mask_data[1:, 1:, 1:].copy()
        self.update_views(_mat)

    def get_filters(self) -> list[npt.NDArray]:
        """Create a boolean mask filter based on the polygon points and viewer size.

        Since polygon points are stored with parallel world coordinates,
        they are projected back to display coordinates using the current
        camera before generating the mask.
        """
        w, h = self.resolution
        renderer = self.viewer.ren
        coord = vtkCoordinate()
        filters = []
        for poly_canvas in self.m3e_list:
            display_points = []
            for world_pt in poly_canvas._world_points:
                coord.SetValue(world_pt)
                px, py = coord.GetComputedDoubleDisplayValue(renderer)
                display_points.append((px, py))
            filters.append(polygon2mask((w, h), display_points))
        return filters

    def CutMaskFromPolygons(self):
        """Edit mask data based on the polygons drawn in the 3D viewer."""
        completed_polygons = [m3e for m3e in self.m3e_list if m3e.complete]
        if len(completed_polygons) == 0:
            return

        if self.mask_data is None:
            return

        # All m3e will be updated with correct viewer settings
        Publisher.sendMessage("Send volume viewer size")
        Publisher.sendMessage("Send volume viewer active camera")

        # Guard: if the viewer has not reported a valid size yet (e.g. on the
        # very first Enable after a fresh DICOM import before the widget has
        # been fully painted), skip the cut to avoid an incorrect projection
        # matrix that would corrupt the mask.  The polygon stays in place so
        # the user can re-apply once the viewer is ready.  Fixes #1086.
        w, h = self.resolution
        if h == 0:
            return

        filters = self.get_filters()

        # OR operation in all masks to create a single filter mask
        filter = np.logical_or.reduce(filters).T

        # If the edit mode is to include, we invert the filter
        if self.edit_mode == const.MASK_3D_EDIT_INCLUDE:
            np.logical_not(filter, out=filter)

        _mat = self.mask_data[1:, 1:, 1:].copy()
        out = _mat.copy()

        slice = slc.Slice()
        sx, sy, sz = slice.spacing

        try:
            near, far = self.clipping_range
        except AttributeError:
            return

        depth = near + (far - near) * self.depth_val

        try:
            wts = self.world_to_screen
            wtc = self.world_to_camera_coordinates
        except AttributeError:
            return

        mask_cut(
            _mat,
            sx,
            sy,
            sz,
            depth,
            filter,
            wts,
            wtc,
            out,
            self.edit_mode,
        )

        self.update_views(out)

    def OnMaskChanged(self, index: int):
        """Refresh mask_data when the active mask changes (e.g. after Select Parts).

        Without this, the 3D editor keeps the stale matrix from the old mask,
        so the first polygon cut after a 'Select Parts' would restore the old
        mask instead of operating on the new one.  Fixes #1258.
        """
        cur_mask = slc.Slice().current_mask
        if cur_mask is not None:
            self.mask_data = cur_mask.matrix.copy()

    def update_views(self, _mat: npt.NDArray):
        """Update the views with the given mask data."""
        slice = slc.Slice()
        _cur_mask = slice.current_mask
        if _cur_mask is not None:
            _cur_mask.matrix[:] = 1
            _cur_mask.matrix[1:, 1:, 1:] = _mat
            _cur_mask.was_edited = True

            # Explicitly rebuild the VTK imagedata from the updated numpy matrix
            # so that the 3D volume re-renders with the new polygon-cut data.
            # Calling modified(all_volume=True) only calls imagedata.Modified()
            # which does NOT transfer the numpy changes into the VTK scalar array.
            # Fix for #1258: rebuild imagedata so 3D window reflects the cut.
            if _cur_mask.volume is not None and ses.Session().mask_3d_preview:
                _cur_mask.imagedata = _cur_mask.as_vtkimagedata()
                _cur_mask.volume.change_imagedata()

            _cur_mask.modified(all_volume=True)

        # Discard all buffers to reupdate view
        for ori in ["AXIAL", "CORONAL", "SAGITAL"]:
            slice.buffer_slices[ori].discard_buffer()

        # Save modification in the history
        _cur_mask.save_history(0, "VOLUME", _cur_mask.matrix.copy(), self.mask_data)

        Publisher.sendMessage("Render volume viewer")  # Fix #1258: re-render 3D window after cut
        Publisher.sendMessage("Reload actual slice")


class AnnotationInteractorStyle(LinearMeasureInteractorStyle):
    """
    Interactor style for placing annotations on 3D surfaces.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.state_code = const.STATE_MEASURE_ANNOTATION
        self._type = const.ANNOTATION

        self.AddObserver("MouseMoveEvent", self.OnMouseMove)

    def OnMouseMove(self, obj, evt):
        # We send the update message and let MeasurementManager decide if it's relevant.
        # This avoiding crashing on missing Project attributes while in transition.
        x, y = self.viewer.get_vtk_mouse_position()
        self.measure_picker.Pick(x, y, 0, self.viewer.ren)
        if self.measure_picker.GetActor():
            pos = self.measure_picker.GetPickPosition()
            Publisher.sendMessage("Update measurement point position", position=pos)

        super().OnMouseMove(obj, evt)


class Styles:
    styles = {
        const.STATE_DEFAULT: DefaultInteractorStyle,
        const.STATE_ZOOM: ZoomInteractorStyle,
        const.STATE_ZOOM_SL: ZoomSLInteractorStyle,
        const.STATE_PAN: PanMoveInteractorStyle,
        const.STATE_SPIN: SpinInteractorStyle,
        const.STATE_WL: WWWLInteractorStyle,
        const.STATE_MEASURE_DISTANCE: LinearMeasureInteractorStyle,
        const.STATE_MEASURE_CURVED_LINEAR: CurvedMeasureInteractorStyle,
        const.STATE_MEASURE_ANGLE: AngularMeasureInteractorStyle,
        const.STATE_MEASURE_ANNOTATION: AnnotationInteractorStyle,
        const.VOLUME_STATE_SEED: SeedInteractorStyle,
        const.SLICE_STATE_CROSS: CrossInteractorStyle,
        const.STATE_NAVIGATION: NavigationInteractorStyle,
        const.STATE_REGISTRATION: RegistrationInteractorStyle,
        const.STATE_MASK_3D_EDIT: Mask3DEditorInteractorStyle,
    }

    @classmethod
    def add_style(cls, style_cls, level=1):
        if style_cls in cls.styles.values():
            for style_id in cls.styles:
                if cls.styles[style_id] == style_cls:
                    const.STYLE_LEVEL[style_id] = level
                    return style_id

        new_style_id = max(cls.styles) + 1
        cls.styles[new_style_id] = style_cls
        const.STYLE_LEVEL[new_style_id] = level
        return new_style_id

    @classmethod
    def remove_style(cls, style_id):
        del cls.styles[style_id]

    @classmethod
    def get_style(cls, style):
        return cls.styles[style]

    @classmethod
    def has_style(cls, style):
        return style in cls.styles
