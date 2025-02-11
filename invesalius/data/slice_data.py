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

import invesalius.constants as const
import invesalius.data.vtk_utils as vu

BORDER_UP = 1
BORDER_DOWN = 2
BORDER_LEFT = 4
BORDER_RIGHT = 8
BORDER_ALL = BORDER_UP | BORDER_DOWN | BORDER_LEFT | BORDER_RIGHT
BORDER_NONE = 0


class SliceData:
    def __init__(self):
        self.actor = None
        self.cursor = None
        self.text = None
        self.layer = 99
        self.number = 0
        self.orientation = "AXIAL"
        self.renderer = None
        self.canvas_renderer = None
        self.overlay_renderer = None
        self.__create_text()

    def __create_text(self):
        colour = const.ORIENTATION_COLOUR[self.orientation]

        text = vu.TextZero()
        text.SetColour(colour)
        text.SetSize(const.TEXT_SIZE_LARGE)
        text.SetPosition(const.TEXT_POS_LEFT_DOWN_ZERO)
        text.SetSymbolicSize(wx.FONTSIZE_LARGE)
        # text.SetVerticalJustificationToBottom()
        text.SetValue(self.number)
        self.text = text

    def SetCursor(self, cursor):
        if self.cursor:
            self.overlay_renderer.RemoveActor(self.cursor.actor)
        self.overlay_renderer.AddActor(cursor.actor)
        self.cursor = cursor

    def SetNumber(self, init, end=None):
        if end is None:
            self.number = init
            self.text.SetValue("%d" % self.number)
        else:
            self.number = init
            self.text.SetValue("%d - %d" % (init, end))
        self.text.SetPosition(const.TEXT_POS_LEFT_DOWN_ZERO)

    def SetOrientation(self, orientation):
        self.orientation = orientation

    def Hide(self):
        self.overlay_renderer.RemoveActor(self.actor)
        self.renderer.RemoveActor(self.text.actor)

    def Show(self):
        self.renderer.AddActor(self.actor)
        self.renderer.AddActor(self.text.actor)

    def draw_to_canvas(self, gc, canvas):
        w, h = self.renderer.GetSize()
        colour = const.ORIENTATION_COLOUR[self.orientation]
        canvas.draw_rectangle(
            (0, 0), w, h, line_colour=[255 * i for i in colour] + [255], line_width=2
        )
        self.text.draw_to_canvas(gc, canvas)
