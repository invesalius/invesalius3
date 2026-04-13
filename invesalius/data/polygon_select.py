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


from typing import TYPE_CHECKING, List, Tuple

from vtkmodules.vtkRenderingCore import vtkCoordinate

import invesalius.constants as const
from invesalius.gui.widgets.canvas_renderer import CanvasHandlerBase, Polygon
from invesalius.pubsub import pub as Publisher

if TYPE_CHECKING:
    import wx

    from invesalius.gui.widgets.canvas_renderer import CanvasEvent, CanvasRendererCTX


def _display_to_world(renderer, display_x, display_y):
    """Convert display coordinates to world coordinates on the camera focal plane."""
    focal_point = renderer.GetActiveCamera().GetFocalPoint()
    renderer.SetWorldPoint(*focal_point, 1.0)
    renderer.WorldToDisplay()
    focal_depth = renderer.GetDisplayPoint()[2]
    renderer.SetDisplayPoint(display_x, display_y, focal_depth)
    renderer.DisplayToWorld()
    wp = renderer.GetWorldPoint()
    w = wp[3]
    return (wp[0] / w, wp[1] / w, wp[2] / w)


class PolygonSelectCanvas(CanvasHandlerBase):
    """Tool for selecting a polygon on a wx-based canvas.

    Inspired on PolygonDensityMeasure, stores and renders a polygon for a canvas.

    Args:
        colour (tuple[int, int, int, int]): RGBA tuple for the polygon line color.
        interactive (bool): Whether the polygon is interactive.
    """

    def __init__(
        self, colour: Tuple[int, int, int, int] = (255, 0, 0, 255), interactive: bool = True
    ):
        super().__init__(None)

        self.location = const.SURFACE
        self.index = 0

        self.polygon = Polygon(self, fill=False, closed=False, line_colour=colour, is_3d=False)
        self.polygon.layer = 1
        self.add_child(self.polygon)
        self.complete = False

        self.interactive = interactive

        # Parallel list of 3D world coordinates for each polygon point.
        self._world_points: List[Tuple[float, float, float]] = []
        # Track camera/viewport state to detect changes that require reprojection.
        self._last_camera_mtime: int = 0
        self._last_renderer_size: Tuple[int, int] = (0, 0)

    def draw_to_canvas(self, gc: "wx.GraphicsContext", canvas: "CanvasRendererCTX") -> None:
        ## abstract method from super class. needs implementation but does nothing here
        """Reproject world coordinates to display coords only when camera/viewport changes.
        During normal interaction (dragging), points are not overwritten,
        preserving smooth point-dragging behavior.
        """
        if self._world_points and len(self._world_points) == len(self.polygon.points):
            renderer = canvas.evt_renderer
            camera = renderer.GetActiveCamera()
            current_mtime = camera.GetMTime()
            current_size = renderer.GetSize()
            if current_mtime != self._last_camera_mtime or current_size != self._last_renderer_size:
                # Camera or viewport changed — reproject world points to display
                coord = vtkCoordinate()
                for i, world_pt in enumerate(self._world_points):
                    coord.SetValue(world_pt)
                    px, py = coord.GetComputedDoubleDisplayValue(renderer)
                    self.polygon.points[i] = (px, py)
                    if i < len(self.polygon.handlers):
                        self.polygon.handlers[i].position = (px, py)
                self._last_camera_mtime = current_mtime
                self._last_renderer_size = current_size
        super().draw_to_canvas(gc, canvas)

    def on_mouse_move(self, _evt: "CanvasEvent"):
        pass

    def on_drag_end(self, evt: "CanvasEvent"):
        """Update world coordinates from the dragged display positions, then cut."""
        if hasattr(evt, "renderer") and evt.renderer is not None:
            renderer = evt.renderer
            for i, display_pt in enumerate(self.polygon.points):
                if i < len(self._world_points):
                    self._world_points[i] = _display_to_world(
                        renderer, display_pt[0], display_pt[1]
                    )
        Publisher.sendMessage("M3E cut mask from 3D")

    def insert_point(
        self,
        display_point: Tuple[float, float],
        world_point: Tuple[float, float, float],
    ):
        """Insert a new point to the polygon.

        Args:
            display_point: The 2D display coordinates (px, py) from the mouse.
            world_point: The corresponding 3D world coordinates on the focal plane.
        """
        self.polygon.append_point(display_point)
        self._world_points.append(world_point)

    def complete_polygon(self):
        if len(self.polygon.points) >= 3:
            self.polygon.closed = True
            self.complete = True

    def IsComplete(self):
        return self.complete

    def SetVisibility(self, value: bool):
        self.polygon.visible = value

    def set_interactive(self, value: bool):
        self.interactive = bool(value)
        self.polygon.interactive = self.interactive
