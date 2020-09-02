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

from pubsub import pub as Publisher


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
        #  self.viewer.on_wl = True
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=True)
        #  self.viewer.canvas.draw_list.append(self.viewer.wl_text)
        #  self.viewer.UpdateCanvas()

    def CleanUp(self):
        #  self.viewer.on_wl = False
        Publisher.sendMessage('Toggle toolbar item',
                              _id=self.state_code, value=False)
        #  if self.viewer.wl_text is not None:
            #  self.viewer.canvas.draw_list.remove(self.viewer.wl_text)
            #  self.viewer.UpdateCanvas()

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


class Styles:
    styles = {
        const.STATE_DEFAULT: DefaultInteractorStyle,
        const.STATE_ZOOM: ZoomInteractorStyle,
        const.STATE_ZOOM_SL: ZoomSLInteractorStyle,
        const.STATE_WL: WWWLInteractorStyle,
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
