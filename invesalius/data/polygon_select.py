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


from typing import TYPE_CHECKING

import invesalius.constants as const
from invesalius.gui.widgets.canvas_renderer import CanvasHandlerBase, Polygon

if TYPE_CHECKING:
    import wx

    from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX


class PolygonSelectCanvas(CanvasHandlerBase):
    """Tool for selecting a polygon on a wx-based canvas.

    Inspired on PolygonDensityMeasure, stores and renders a polygon for a canvas.

    Args:
        colour (tuple): RGBA tuple for the polygon line color.
        interactive (bool): Whether the polygon is interactive.
    """

    def __init__(self, colour=(255, 0, 0, 255), interactive=True):
        super().__init__(None)

        self.colour = colour

        self.complete = False

        self.location = const.SURFACE
        self.index = 0

        self.polygon = Polygon(self, fill=False, closed=False, line_colour=self.colour, is_3d=False)
        self.polygon.layer = 1
        self.add_child(self.polygon)

        self.interactive = interactive

    def draw_to_canvas(self, gc: "wx.GraphicsContext", canvas: "CanvasRendererCTX") -> None:
        ## abstract method from super class. needs implementation but does nothing here
        super().draw_to_canvas(gc, canvas)

    def insert_point(self, point: tuple[int, int]):
        """Insert a new point to the polygon."""
        self.polygon.append_point(point)

    def complete_polygon(self):
        if len(self.polygon.points) >= 3:
            self.polygon.closed = True
            self.complete = True

    def IsComplete(self):
        return self.complete

    def SetVisibility(self, value):
        self.polygon.visible = value

    def set_interactive(self, value):
        self.interactive = bool(value)
        self.polygon.interactive = self.interactive
