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

import vtk
import wx

import invesalius.constants as const
import invesalius.project as prj

from pubsub import pub as Publisher


PROP_MEASURE = 0.8


class Base3DInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
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
    Interactor style responsible for Default functionalities:
    * Zoom moving mouse with right button pressed;
    * Change the slices with the scroll.
    """
    def __init__(self, viewer):
        super().__init__(viewer)
        self.state_code = const.STATE_DEFAULT

        self.viewer = viewer

        # Zoom using right button
        self.AddObserver("LeftButtonPressEvent",self.OnRotateLeftClick)
        self.AddObserver("LeftButtonReleaseEvent",self.OnRotateLeftRelease)

        self.AddObserver("RightButtonPressEvent",self.OnZoomRightClick)
        self.AddObserver("RightButtonReleaseEvent",self.OnZoomRightRelease)

        self.AddObserver("MouseMoveEvent", self.OnMouseMove)

        self.AddObserver("MouseWheelForwardEvent",self.OnScrollForward)
        self.AddObserver("MouseWheelBackwardEvent", self.OnScrollBackward)
        self.AddObserver("EnterEvent", self.OnFocus)

    def OnFocus(self, evt, obj):
        self.viewer.SetFocus()

    def OnMouseMove(self, evt, obj):
        if self.left_pressed:
            evt.Rotate()
            evt.OnLeftButtonDown()

        elif self.right_pressed:
            evt.Dolly()
            evt.OnRightButtonDown()

        elif self.middle_pressed:
            evt.Pan()
            evt.OnMiddleButtonDown()

    def OnRotateLeftClick(self, evt, obj):
        evt.StartRotate()

    def OnRotateLeftRelease(self, evt, obj):
        evt.OnLeftButtonUp()
        evt.EndRotate()

    def OnZoomRightClick(self, evt, obj):
        evt.StartDolly()

    def OnZoomRightRelease(self, evt, obj):
        evt.OnRightButtonUp()
        evt.EndDolly()

    def OnScrollForward(self, evt, obj):
        self.OnMouseWheelForward()

    def OnScrollBackward(self, evt, obj):
        self.OnMouseWheelBackward()


class ZoomInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for zoom with movement of the mouse and the
    left mouse button clicked.
    """
    def __init__(self, viewer):
        super().__init__(viewer)

        self.state_code = const.STATE_ZOOM

        self.viewer = viewer

        self.RemoveObservers("LeftButtonPressEvent")
        self.RemoveObservers("LeftButtonReleaseEvent")

        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)

        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=False)

    def OnPressLeftButton(self, evt, obj):
        self.right_pressed = True

    def OnReleaseLeftButton(self, obj, evt):
        self.right_pressed = False

    def OnUnZoom(self, evt):
        ren = self.viewer.ren
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        self.viewer.interactor.Render()


class ZoomSLInteractorStyle(vtk.vtkInteractorStyleRubberBandZoom):
    """
    Interactor style responsible for zoom by selecting a region.
    """
    def __init__(self, viewer):
        self.viewer = viewer
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnZoom)

        self.state_code = const.STATE_ZOOM_SL

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=False)

    def OnUnZoom(self, evt):
        ren = self.viewer.ren
        ren.ResetCamera()
        ren.ResetCameraClippingRange()
        self.viewer.interactor.Render()


class PanMoveInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for translate the camera.
    """
    def __init__(self, viewer):
        super().__init__(viewer)

        self.state_code = const.STATE_PAN

        self.viewer = viewer

        self.panning = False

        self.AddObserver("MouseMoveEvent", self.OnPanMove)
        self.viewer.interactor.Bind(wx.EVT_LEFT_DCLICK, self.OnUnspan)

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=True)

    def CleanUp(self):
        self.viewer.interactor.Unbind(wx.EVT_LEFT_DCLICK)
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=False)

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
    Interactor style responsible for spin the camera.
    """
    def __init__(self, viewer):
        DefaultInteractorStyle.__init__(self, viewer)
        self.state_code = const.STATE_SPIN
        self.viewer = viewer
        self.spinning = False
        self.AddObserver("MouseMoveEvent", self.OnSpinMove)

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=False)

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

        self.viewer =  viewer

        self.last_x = 0
        self.last_y = 0

        self.changing_wwwl = False

        self.RemoveObservers("LeftButtonPressEvent")
        self.RemoveObservers("LeftButtonReleaseEvent")

        self.AddObserver("MouseMoveEvent", self.OnWindowLevelMove)
        self.AddObserver("LeftButtonPressEvent", self.OnWindowLevelClick)
        self.AddObserver("LeftButtonReleaseEvent", self.OnWindowLevelRelease)

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=True)
        self.viewer.on_wl = True
        if self.viewer.raycasting_volume:
            self.viewer.text.Show()
            self.viewer.interactor.Render()

    def CleanUp(self):
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=False)
        self.viewer.on_wl = True
        self.viewer.text.Hide()
        self.viewer.interactor.Render()

    def OnWindowLevelMove(self, obj, evt):
        if self.changing_wwwl:
            iren = obj.GetInteractor()
            mouse_x, mouse_y = iren.GetEventPosition()
            diff_x = mouse_x - self.last_x
            diff_y = mouse_y - self.last_y
            self.last_x, self.last_y = mouse_x, mouse_y
            Publisher.sendMessage('Set raycasting relative window and level',
                                  diff_wl=diff_x, diff_ww=diff_y)
            Publisher.sendMessage('Refresh raycasting widget points')
            Publisher.sendMessage('Render volume viewer')

    def OnWindowLevelClick(self, obj, evt):
        iren = obj.GetInteractor()
        self.last_x, self.last_y = iren.GetLastEventPosition()
        self.changing_wwwl = True

    def OnWindowLevelRelease(self, obj, evt):
        self.changing_wwwl = False


class LinearMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert linear measurements.
    """
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.state_code = const.STATE_MEASURE_DISTANCE
        self.measure_picker = vtk.vtkPropPicker()

        proj = prj.Project()
        self._radius = min(proj.spacing) * PROP_MEASURE

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertLinearMeasurePoint)

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage('Toggle toolbar item',
                             _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertLinearMeasurePoint(self, obj, evt):
        x,y = self.viewer.interactor.GetEventPosition()
        self.measure_picker.Pick(x, y, 0, self.viewer.ren)
        x, y, z = self.measure_picker.GetPickPosition()
        if self.measure_picker.GetActor():
            self.left_pressed = False
            Publisher.sendMessage("Add measurement point",
                                  position=(x, y,z),
                                  type=const.LINEAR,
                                  location=const.SURFACE,
                                  radius=self._radius)
            self.viewer.interactor.Render()
        else:
            self.left_pressed = True


class AngularMeasureInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for insert linear measurements.
    """
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.state_code = const.STATE_MEASURE_DISTANCE
        self.measure_picker = vtk.vtkPropPicker()

        proj = prj.Project()
        self._radius = min(proj.spacing) * PROP_MEASURE

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertAngularMeasurePoint)

    def SetUp(self):
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=True)

    def CleanUp(self):
        Publisher.sendMessage('Toggle toolbar item', _id=self.state_code, value=False)
        Publisher.sendMessage("Remove incomplete measurements")

    def OnInsertAngularMeasurePoint(self, obj, evt):
        x,y = self.viewer.interactor.GetEventPosition()
        self.measure_picker.Pick(x, y, 0, self.viewer.ren)
        x, y, z = self.measure_picker.GetPickPosition()
        if self.measure_picker.GetActor():
            self.left_pressed = False
            Publisher.sendMessage("Add measurement point",
                                  position=(x, y,z),
                                  type=const.ANGULAR,
                                  location=const.SURFACE,
                                  radius=self._radius)
            self.viewer.interactor.Render()
        else:
            self.left_pressed = True


class SeedInteractorStyle(DefaultInteractorStyle):
    """
    Interactor style responsible for select sub surfaces.
    """
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.picker = vtk.vtkPointPicker()

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.OnInsertSeed)

    def OnInsertSeed(self, obj, evt):
        x,y = self.viewer.interactor.GetEventPosition()
        self.picker.Pick(x, y, 0, self.viewer.ren)
        point_id = self.picker.GetPointId()
        if point_id > -1:
            self.viewer.seed_points.append(point_id)
            self.viewer.interactor.Render()
        else:
            self.left_pressed = True


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
