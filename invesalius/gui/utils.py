# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
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
# --------------------------------------------------------------------

import wx


def calc_width_needed(widget, num_chars):
    width, height = widget.GetTextExtent("M" * num_chars)
    return width


class CenteredBitmapToggleButton(wx.ToggleButton):
    def __init__(self, parent, id, bitmap, style=wx.NO_BORDER, size=None):
        super(CenteredBitmapToggleButton, self).__init__(parent, id, style=style, size=size)
        self.bitmap = bitmap

        # Bind the paint event to a custom handler
        self.Bind(wx.EVT_PAINT, self.on_paint)

        # Bind the size event to handle resizing
        self.Bind(wx.EVT_SIZE, self.on_size)

    def on_paint(self, event):
        # Create a buffered device context for flicker-free drawing
        dc = wx.BufferedPaintDC(self)

        # Clear the button area
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()

        # Get the size of the button and the bitmap
        button_size = self.GetSize()
        bitmap_size = self.bitmap.GetSize()

        # Calculate the position to center the bitmap
        x = (button_size[0] - bitmap_size[0]) // 2
        y = (button_size[1] - bitmap_size[1]) // 2

        # Draw the bitmap at the calculated position
        dc.DrawBitmap(self.bitmap, x, y, True)

        # Draw the button's border
        dc.SetPen(wx.Pen(wx.SystemSettings.GetColour(wx.SYS_COLOUR_ACTIVEBORDER)))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRectangle(0, 0, button_size.x, button_size.y)

    def on_size(self, event):
        # Refresh the button to trigger a repaint
        self.Refresh()
        event.Skip()
