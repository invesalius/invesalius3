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


import wx
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleRubberBandZoom,
    vtkInteractorStyleTrackballCamera,
)
from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkPointPicker, vtkPropPicker

import invesalius.constants as const
import invesalius.project as prj
from invesalius.pubsub import pub as Publisher

PROP_MEASURE = 0.8


class Base3DInteractorStyle(vtkInteractorStyleTrackballCamera):
    def __init__(self, viewer):
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

    def __init__(self, viewer):
        super().__init__(viewer)
        self.state_code = const.STATE_DEFAULT

        self.last_click_time = 0
        self.double_click_max_interval = 1.0  # in seconds

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

        # Set camera focus using left double-click.
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.SetCameraFocus)

        # Reset camera using right double-click.
        self.viewer.interactor.Bind(wx.EVT_RIGHT_DCLICK, self.ResetCamera)

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
        self.viewer.interactor.InvokeEvent("StartSpinEvent")

    def OnRightRelease(self, evt, obj):
        self.viewer.interactor.InvokeEvent("EndSpinEvent")

    def OnLeftClick(self, evt, obj):
        evt.StartRotate()

    def OnLeftRelease(self, evt, obj):
        evt.EndRotate()

    def OnScrollForward(self, evt, obj):
        self.OnMouseWheelForward()

    def OnScrollBackward(self, evt, obj):
        self.OnMouseWheelBackward()

    def PickMarker(self, evt, obj):
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
        renderer = self.viewer.ren
        interactor = self.viewer.interactor

        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        interactor.Render()


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
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
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
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
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
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
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
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.state_code = const.STATE_MEASURE_DISTANCE
        self.measure_picker = vtkPropPicker()

        proj = prj.Project()
        self._radius = min(proj.spacing) * PROP_MEASURE

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertLinearMeasurePoint)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertLinearMeasurePoint(self, obj, evt):
        x, y = self.viewer.get_vtk_mouse_position()
        self.measure_picker.Pick(x, y, 0, self.viewer.ren)
        x, y, z = self.measure_picker.GetPickPosition()
        if self.measure_picker.GetActor():
            self.left_pressed = False
            Publisher.sendMessage(
                "Add measurement point",
                position=(x, y, z),
                type=const.LINEAR,
                location=const.SURFACE,
                radius=self._radius,
            )
            self.viewer.interactor.Render()
        else:
            self.left_pressed = True


class AngularMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for angular measurements by clicking consecutive points in the volume viewer.
    """

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.state_code = const.STATE_MEASURE_DISTANCE
        self.measure_picker = vtkPropPicker()

        proj = prj.Project()
        self._radius = min(proj.spacing) * PROP_MEASURE

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertAngularMeasurePoint)

    def SetUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage("Toggle toolbar item", _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertAngularMeasurePoint(self, obj, evt):
        x, y = self.viewer.get_vtk_mouse_position()
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

    def SetUp(self):
        self.viewer.CreatePointer()

    def CleanUp(self):
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


class Styles:
    styles = {
        const.STATE_DEFAULT: DefaultInteractorStyle,
        const.STATE_ZOOM: ZoomInteractorStyle,
        const.STATE_ZOOM_SL: ZoomSLInteractorStyle,
        const.STATE_PAN: PanMoveInteractorStyle,
        const.STATE_SPIN: SpinInteractorStyle,
        const.STATE_WL: WWWLInteractorStyle,
        const.STATE_MEASURE_DISTANCE: LinearMeasureInteractorStyle,
        const.STATE_MEASURE_ANGLE: AngularMeasureInteractorStyle,
        const.VOLUME_STATE_SEED: SeedInteractorStyle,
        const.SLICE_STATE_CROSS: CrossInteractorStyle,
        const.STATE_NAVIGATION: NavigationInteractorStyle,
        const.STATE_REGISTRATION: RegistrationInteractorStyle,
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
