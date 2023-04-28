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
from typing import List, Dict, Any, Type, cast, overload, TYPE_CHECKING
import wx
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleRubberBandZoom,
    vtkInteractorStyleTrackballCamera,
)
from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkPointPicker, vtkPropPicker


import invesalius.constants as const
import invesalius.project as prj

from invesalius.pubsub import pub as Publisher


PROP_MEASURE: float = 0.8


class Base3DInteractorStyle(vtkInteractorStyleTrackballCamera):
    def __init__(self, viewer: wx.Window) -> None:
        self.right_pressed: bool = False
        self.left_pressed: bool = False
        self.middle_pressed: bool = False

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.AddObserver("RightButtonPressEvent", self.OnPressRightButton)
        self.AddObserver("RightButtonReleaseEvent", self.OnReleaseRightButton)

        self.AddObserver("MiddleButtonPressEvent", self.OnMiddleButtonPressEvent)
        self.AddObserver("MiddleButtonReleaseEvent", self.OnMiddleButtonReleaseEvent)

    def OnPressLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.left_pressed = True

    def OnReleaseLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.left_pressed = False

    def OnPressRightButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.right_pressed = True

    def OnReleaseRightButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.right_pressed = False

    def OnMiddleButtonPressEvent(self, evt: wx.MouseEvent, obj: object) -> None:
        self.middle_pressed = True

    def OnMiddleButtonReleaseEvent(self, evt: wx.MouseEvent, obj: object) -> None:
        self.middle_pressed = False


class DefaultInteractorStyle(Base3DInteractorStyle):
    """
    Interactor style responsible for Default functionalities:
    * Zoom moving mouse with right button pressed;
    * Change the slices with the scroll.
    """
    def __init__(self, viewer: wx.Window) -> None:
        super().__init__(viewer)
        self.state_code: int = const.STATE_DEFAULT

        self.viewer: wx.Window = viewer

        # Zoom using right button
        self.AddObserver("LeftButtonPressEvent",self.OnRotateLeftClick)
        self.AddObserver("LeftButtonReleaseEvent",self.OnRotateLeftRelease)

        self.AddObserver("RightButtonPressEvent",self.OnZoomRightClick)
        self.AddObserver("RightButtonReleaseEvent",self.OnZoomRightRelease)

        self.AddObserver("MouseMoveEvent", self.OnMouseMove)

        self.AddObserver("MouseWheelForwardEvent",self.OnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)
        self.AddObserver("EnterEvent", self.OnFocus)

    def OnFocus(self, evt: wx.MouseEvent, obj: object) -> None:
        self.viewer.SetFocus()

    def OnMouseMove(self, evt: wx.MouseEvent, obj: object) -> None:
        if self.left_pressed:
            evt.Rotate()
            evt.OnLeftButtonDown()

        elif self.right_pressed:
            evt.Dolly()
            evt.OnRightButtonDown()

        elif self.middle_pressed:
            evt.Pan()
            evt.OnMiddleButtonDown()

    def OnRotateLeftClick(self, evt: wx.MouseEvent, obj: object) -> None:
        evt.StartRotate()

    def OnRotateLeftRelease(self, evt: wx.MouseEvent, obj: object) -> None:
        evt.OnLeftButtonUp()
        evt.EndRotate()

    def OnZoomRightClick(self, evt: wx.MouseEvent, obj: object) -> None:
        evt.StartDolly()

    def OnZoomRightRelease(self, evt: wx.MouseEvent, obj: object) -> None:
        evt.OnRightButtonUp()
        evt.EndDolly()

    def OnScrollForward(self, evt: wx.MouseEvent, obj: object) -> None:
        self.OnMouseWheelForward()

    def OnScrollBackward(self, evt: wx.MouseEvent, obj: object) -> None:
        self.OnMouseWheelBackward()


class ZoomInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for zoom with movement of the mouse and the
    left mouse button clicked.
    """
    def __init__(self, viewer: wx.Window) -> None:
        super().__init__(viewer)

        self.state_code: int = const.STATE_ZOOM

        self.viewer: wx.Window = viewer

        self.RemoveObservers("LeftButtonPressEvent")
        self.RemoveObservers("LeftButtonReleaseEvent")

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=True)

    def CleanUp(self) -> None:
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=False)

    def OnPressLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.right_pressed = True

    def OnReleaseLeftButton(self, obj: object, evt: wx.MouseEvent) -> None:
        self.right_pressed = False

    def OnUnZoom(self, evt: wx.MouseEvent) -> None:
        ren = self.viewer.ren
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        self.viewer.interactor.Render()



class ZoomSLInteractorStyle(vtkInteractorStyleRubberBandZoom):
    """
    Interactor style responsible for zoom by selecting a region.
    """
    def __init__(self, viewer: wx.Window) -> None:
        self.viewer: wx.Window = viewer
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

        self.state_code: int = const.STATE_ZOOM_SL

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=True)

    def CleanUp(self) -> None:
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=False)

    def OnUnZoom(self, evt: wx.MouseEvent) -> None:
        ren = self.viewer.ren
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        self.viewer.interactor.Render()


class PanMoveInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for translate the camera.
    """
    def __init__(self, viewer: wx.Window) -> None:
        super().__init__(viewer)

        self.state_code: int = const.STATE_PAN

        self.viewer: wx.Window = viewer

        self.panning: bool = False

        self.AddObserver("MouseMoveEvent", self.OnPanMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspan)

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=True)

    def CleanUp(self) -> None:
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=False)

    def OnPressLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.panning = True

    def OnReleaseLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.panning = False

    def OnPanMove(self, obj: object, evt: wx.MouseEvent) -> None:
        if self.panning:
            obj.Pan()
            obj.OnRightButtonDown()

    def OnUnspan(self, evt: wx.MouseEvent) -> None:
        self.viewer.ren.ResetCamera()
        self.viewer.interactor.Render()



class SpinInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for spin the camera.
    """
    def __init__(self, viewer: wx.Window) -> None:
        DefaultInteractorStyle.__init__(self, viewer)
        self.state_code: int = const.STATE_SPIN
        self.viewer: wx.Window = viewer
        self.spinning: bool = False
        self.AddObserver("MouseMoveEvent", self.OnSpinMove)

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=True)

    def CleanUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=False)

    def OnPressLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.spinning = True

    def OnReleaseLeftButton(self, evt: wx.MouseEvent, obj: object) -> None:
        self.spinning = False

    def OnSpinMove(self, evt: wx.MouseEvent, obj: object) -> None:
        if self.spinning:
            evt.Spin()
            evt.OnRightButtonDown()


class WWWLInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for Window Level & Width functionality.
    """
    def __init__(self, viewer: wx.Window) -> None:
        super().__init__(viewer)
        self.state_code: int = const.STATE_WL

        self.viewer: wx.Window =  viewer

        self.last_x: int = 0
        self.last_y: int = 0

        self.changing_wwwl: bool = False

        self.RemoveObservers("LeftButtonPressEvent")
        self.RemoveObservers("LeftButtonReleaseEvent")

        self.AddObserver("MouseMoveEvent", self.OnWindowLevelMove)
        self.AddObserver("LeftButtonPressEvent", self.OnWindowLevelClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnWindowLevelRelease)

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=True)
        self.viewer.on_wl = True
        if self.viewer.raycasting_volume:
            self.viewer.text.Show()
            self.viewer.interactor.Render()

    def CleanUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=False)
        self.viewer.on_wl = True
        self.viewer.text.Hide()
        self.viewer.interactor.Render()

    def OnWindowLevelMove(self, obj: object, evt: wx.MouseEvent) -> None:
        if self.changing_wwwl:
            mouse_x, mouse_y = self.viewer.get_vtk_mouse_position()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            Publisher.sendMessage('Set raycasting relative window and level',
                                  diff_wl=diff_x, diff_ww=diff_y)
            Publisher.sendMessage('Refresh raycasting widget points')
            Publisher.sendMessage('Render volume viewer')

    def OnWindowLevelClick(self, obj: object, evt: wx.MouseEvent) -> None:
        self.last_x, self.last_y = self.viewer.get_vtk_mouse_position()
        self.changing_wwwl = True

    def OnWindowLevelRelease(self, obj: object, evt: wx.MouseEvent) -> None:
        self.changing_wwwl = False



class LinearMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert linear measurements.
    """
    def __init__(self, viewer: vtkRenderWindowInteractor) -> None:
        super().__init__(viewer)
        self.viewer: vtkRenderWindowInteractor = viewer
        self.state_code: int = const.STATE_MEASURE_DISTANCE
        self.measure_picker: vtkPropPicker = vtkPropPicker()

        proj: prj.Project = prj.Project()
        self._radius: float = min(proj.spacing) * PROP_MEASURE

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertLinearMeasurePoint)

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=True)

    def CleanUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertLinearMeasurePoint(self, obj: Any, evt: Any) -> None:
        x: float
        y: float
        x,y = self.viewer.get_vtk_mouse_position()
        self.measure_picker.Pick(x, y, 0, self.viewer.ren)
        x: float
        y: float
        z: float
        x, y, z = self.measure_picker.GetPickPosition()
        if self.measure_picker.GetActor():
            self.left_pressed: bool = False
            Publisher.sendMessage("Add measurement point",
                                  position=(x, y,z),
                                  type=const.LINEAR,
                                  location=const.SURFACE,
                                  radius=self._radius)
            self.viewer.interactor.Render()
        else:
            self.left_pressed: bool = True


class AngularMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert linear measurements.
    """
    def __init__(self, viewer: vtkRenderWindowInteractor) -> None:
        super().__init__(viewer)
        self.viewer: vtkRenderWindowInteractor = viewer
        self.state_code: int = const.STATE_MEASURE_DISTANCE
        self.measure_picker: vtkPropPicker = vtkPropPicker()

        proj: prj.Project = prj.Project()
        self._radius: float = min(proj.spacing) * PROP_MEASURE

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertAngularMeasurePoint)

    def SetUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=True)

    def CleanUp(self) -> None:
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertAngularMeasurePoint(self, obj: Any, evt: Any) -> None:
        x: float
        y: float
        x,y = self.viewer.get_vtk_mouse_position()
        self.measure_picker.Pick(x, y, 0, self.viewer.ren)
        x: float
        y: float
        z: float
        x, y, z = self.measure_picker.GetPickPosition()
        if self.measure_picker.GetActor():
            self.left_pressed: bool = False
            Publisher.sendMessage("Add measurement point",
                                  position=(x, y,z),
                                  type=const.ANGULAR,
                                  location=const.SURFACE,
                                  radius=self._radius)
            self.viewer.interactor.Render()
        else:
            self.left_pressed: bool = True


class SeedInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for select sub surfaces.
    """
    def __init__(self, viewer: vtkRenderWindowInteractor) -> None:
        super().__init__(viewer)
        self.viewer: vtkRenderWindowInteractor = viewer
        self.picker: vtkPointPicker = vtkPointPicker()

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertSeed)

    def OnInsertSeed(self, obj: Any, evt: Any) -> None:
        x: float
        y: float
        x,y = self.viewer.get_vtk_mouse_position()
        self.picker.Pick(x, y, 0, self.viewer.ren)
        point_id: int = self.picker.GetPointId()
        if point_id > -1:
            self.viewer.seed_points.append(point_id)
            self.viewer.interactor.Render()
        else:
            self.left_pressed: bool = True



class CrossInteractorStyle(DefaultInteractorStyle):
    def __init__(self, viewer: vtkRenderWindowInteractor) -> None:
        super().__init__(viewer)

        self.state_code: int = const.SLICE_STATE_CROSS
        self.picker: vtkCellPicker = vtkCellPicker()
        self.picker.SetTolerance(1e-3)
        # self.picker.SetUseCells(True)
        self.viewer.interactor.SetPicker(self.picker)
        self.AddObserver("LeftButtonPressEvent", self.OnCrossMouseClick)

    def SetUp(self) -> None:
        print("SetUP")

    def CleanUp(self) -> None:
        print("CleanUp")

    def OnCrossMouseClick(self, obj: Any, evt: Any) -> None:
        x: float
        y: float
        x, y = self.viewer.get_vtk_mouse_position()
        self.picker.Pick(x, y, 0, self.viewer.ren)
        x: float
        y: float
        z: float
        x, y, z = self.picker.GetPickPosition()
        if self.picker.GetActor():
            self.viewer.set_camera_position: bool = False
            Publisher.sendMessage('Update slices position', position=[x, -y, z])
            Publisher.sendMessage('Set cross focal point', position=[x, -y, z, None, None, None])
            Publisher.sendMessage('Update slice viewer')
            Publisher.sendMessage('Render volume viewer')
            self.viewer.set_camera_position: bool = True


class Styles:
    styles: Dict[int, Type[DefaultInteractorStyle]] = {
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
    }

    @classmethod
    def add_style(cls, style_cls: Type[DefaultInteractorStyle], level: int = 1) -> int:
        if style_cls in cls.styles.values():
            for style_id in cls.styles:
                if cls.styles[style_id] == style_cls:
                    const.STYLE_LEVEL[style_id] = level
                    return style_id

        new_style_id: int = max(cls.styles) + 1
        cls.styles[new_style_id] = style_cls
        const.STYLE_LEVEL[new_style_id] = level
        return new_style_id

    @classmethod
    def remove_style(cls, style_id: int) -> None:
        del cls.styles[style_id]

    @classmethod
    def get_style(cls, style: int) -> Type[DefaultInteractorStyle]:
        return cls.styles[style]

    @classmethod
    def has_style(cls, style: int) -> bool:
        return style in cls.styles

