#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------

import bisect
import math
import os
import sys

import numpy
import wx
from invesalius.pubsub import pub as Publisher

import invesalius.gui.dialogs as dialog
import invesalius.constants as const

from invesalius import inv_paths

FONT_COLOUR = (1, 1, 1)
LINE_COLOUR = (128, 128, 128)
LINE_WIDTH = 2
HISTOGRAM_LINE_WIDTH = 1
HISTOGRAM_LINE_COLOUR = (128, 128, 128)
HISTOGRAM_FILL_COLOUR = (64, 64, 64)
BACKGROUND_TEXT_COLOUR_RGBA = (255, 0, 0, 128)
TEXT_COLOUR = (255, 255, 255)
GRADIENT_RGBA = 0.75 * 255
RADIUS = 5
SELECTION_SIZE = 10
TOOLBAR_SIZE = 30
TOOLBAR_COLOUR = (25 , 25, 25)
RANGE = 10
PADDING = 2

class Node(object):
    """
    Represents the points in the raycasting preset. Contains its colour,
    graylevel (hounsfield scale), opacity, x and y position in the widget.
    """
    def __init__(self):
        self.colour = None
        self.x = 0
        self.y = 0
        self.graylevel = 0
        self.opacity = 0


class Curve(object):
    """
    Represents the curves in the raycasting preset. It contains the point nodes from
    the curve and its window width & level.
    """
    def __init__(self):
        self.wl = 0
        self.ww = 0
        self.wl_px = 0
        self.nodes = []

    def CalculateWWWl(self):
        """
        Called when the curve width(ww) or position(wl) is modified.
        """
        self.ww = self.nodes[-1].graylevel - self.nodes[0].graylevel
        self.wl = self.nodes[0].graylevel + self.ww / 2.0


class Histogram(object):
    def __init__(self):
        self.init = -1024
        self.end = 2000
        self.points = ()


class Button(object):
    """
    The button in the clut raycasting.
    """
    def __init__(self):
        self.image = None
        self.position = (0, 0)
        self.size = (24, 24)

    def HasClicked(self, position):
        """
        Test if the button was clicked.
        """
        m_x, m_y = position
        i_x, i_y = self.position
        w, h = self.size
        if i_x < m_x < i_x + w and \
           i_y < m_y < i_y + h:
            return True
        else:
            return False


class CLUTRaycastingWidget(wx.Panel):
    """
    This class represents the frame where images is showed
    """

    def __init__(self, parent, id):
        """
        Constructor.
        
        parent -- parent of this frame
        """
        super(CLUTRaycastingWidget, self).__init__(parent, id)
        self.points = []
        self.colours = []
        self.curves = []
        self.init = -1024
        self.end = 2000
        self.Histogram = Histogram()
        self.padding = 5
        self.previous_wl = 0
        self.to_render = False
        self.dragged = False
        self.middle_drag = False
        self.to_draw_points = 0
        self.point_dragged = None
        self.curve_dragged = None
        self.histogram_array = [100,100]
        self.CalculatePixelPoints()
        self.__bind_events_wx()
        self._build_buttons()
        self.Show()

    def SetRange(self, range):
        """
        Se the range from hounsfield
        """
        self.init, self.end = range
        self.CalculatePixelPoints()

    def SetPadding(self, padding):
        self.padding = padding

    def __bind_events_wx(self):
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_LEFT_DOWN , self.OnClick)
        self.Bind(wx.EVT_LEFT_DCLICK , self.OnDoubleClick)
        self.Bind(wx.EVT_LEFT_UP , self.OnRelease)
        self.Bind(wx.EVT_RIGHT_DOWN , self.OnRighClick)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleClick)
        self.Bind(wx.EVT_MIDDLE_UP, self.OnMiddleRelease)

    def OnEraseBackground(self, evt):
        pass

    def OnClick(self, evt):
        x, y = evt.GetPosition()
        if self.save_button.HasClicked((x, y)):
            filename = dialog.ShowSavePresetDialog()
            if filename:
                Publisher.sendMessage('Save raycasting preset', preset_name=filename)
        point = self._has_clicked_in_a_point((x, y))
        # A point has been selected. It can be dragged.
        if point:
            self.dragged = True
            self.point_dragged = point
            self.Refresh()
            return
        curve = self._has_clicked_in_selection_curve((x, y))
        if curve is not None:
            self.dragged = True
            self.previous_wl = x
            self.curve_dragged = curve
            evt = CLUTEvent(myEVT_CLUT_CURVE_SELECT, self.GetId(), curve)
            self.GetEventHandler().ProcessEvent(evt)
            return
        else:
            p = self._has_clicked_in_line((x, y))
            # The user clicked in the line. Insert a new point.
            if p:
                n, p = p
                self.points[n].insert(p, {'x': 0, 'y': 0})
                self.colours[n].insert(p, {'red': 0, 'green': 0, 'blue': 0})
                self.points[n][p]['x'] = self.PixelToHounsfield(x)
                self.points[n][p]['y'] = self.PixelToOpacity(y)

                node = Node()
                node.colour = (0, 0, 0)
                node.x = x
                node.y = y
                node.graylevel = self.points[n][p]['x']
                node.opacity = self.points[n][p]['y']
                self.curves[n].nodes.insert(p, node)

                self.Refresh()
                nevt = CLUTEvent(myEVT_CLUT_POINT_RELEASE, self.GetId(), n)
                self.GetEventHandler().ProcessEvent(nevt)
                return
        evt.Skip()

    def OnDoubleClick(self, evt):
        """
        Used to change the colour of a point
        """
        point = self._has_clicked_in_a_point(evt.GetPosition())
        if point:
            i, j = point
            actual_colour = self.curves[i].nodes[j].colour
            colour_dialog = wx.GetColourFromUser(self, actual_colour)
            if colour_dialog.IsOk():
                i,j = point

                r, g, b, a = colour_dialog.Get()

                self.colours[i][j]['red'] = r / 255.0
                self.colours[i][j]['green'] = g / 255.0
                self.colours[i][j]['blue'] = b / 255.0
                self.curves[i].nodes[j].colour = (r, g, b)
                self.Refresh()
                nevt = CLUTEvent(myEVT_CLUT_POINT_RELEASE, self.GetId(), i)
                self.GetEventHandler().ProcessEvent(nevt)
                return
        evt.Skip()

    def OnRighClick(self, evt):
        """
        Used to remove a point
        """
        point = self._has_clicked_in_a_point(evt.GetPosition())
        if point:
            i, j = point
            self.RemovePoint(i, j)
            self.Refresh()
            nevt = CLUTEvent(myEVT_CLUT_POINT_RELEASE, self.GetId(), i)
            self.GetEventHandler().ProcessEvent(nevt)
            return
        n_curve = self._has_clicked_in_selection_curve(evt.GetPosition())
        if n_curve is not None:
            self.RemoveCurve(n_curve)
            self.Refresh()
            nevt = CLUTEvent(myEVT_CLUT_POINT_RELEASE, self.GetId(), n_curve)
            self.GetEventHandler().ProcessEvent(nevt)
        evt.Skip()

    def OnRelease(self, evt):
        """
        Generate a EVT_CLUT_POINT_CHANGED event indicating that a change has
        been occurred in the preset points.
        """
        if self.to_render:
            evt = CLUTEvent(myEVT_CLUT_POINT_RELEASE, self.GetId(), 0)
            self.GetEventHandler().ProcessEvent(evt)
        self.dragged = False
        self.curve_dragged = None
        self.point_dragged = None
        self.to_render = False
        self.previous_wl = 0

    def OnWheel(self, evt):
        """
        Increase or decrease the range from hounsfield scale showed. It
        doesn't change values in preset, only to visualization.
        """
        direction = evt.GetWheelRotation() / evt.GetWheelDelta()
        init = self.init - RANGE * direction
        end = self.end + RANGE * direction
        self.SetRange((init, end))
        self.Refresh()

    def OnMiddleClick(self, evt):
        self.middle_drag = True
        self.last_position = evt.GetX()

    def OnMiddleRelease(self, evt):
        self.middle_drag = False

    def OnMotion(self, evt):
        # User dragging a point
        x = evt.GetX()
        y = evt.GetY()
        if self.dragged and self.point_dragged:
            self._move_node(x, y)
        elif self.dragged and self.curve_dragged is not None:
            self._move_curve(x, y)
        elif self.middle_drag:
            d = self.PixelToHounsfield(x) - self.PixelToHounsfield(self.last_position)
            self.SetRange((self.init - d, self.end - d))
            self.last_position = x
            self.Refresh()
        else:
            evt.Skip()

    def OnPaint(self, evt):
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.Brush('Black'))
        dc.Clear()
        if self.to_draw_points:
            self.Render(dc)

    def OnSize(self, evt):
        self.CalculatePixelPoints()
        self.Refresh()

    def _has_clicked_in_a_point(self, position):
        """
        returns the index from the selected point
        """
        for i, curve in enumerate(self.curves):
            for j, node in enumerate(curve.nodes):
                if self._calculate_distance((node.x, node.y), position) <= RADIUS:
                    return (i, j)
        return None

    def distance_from_point_line(self, p1, p2, pc):
        """
        Calculate the distance from point pc to a line formed by p1 and p2.
        """
        # Create a vector pc-p1 and p2-p1
        A = numpy.array(pc) - numpy.array(p1)
        B = numpy.array(p2) - numpy.array(p1)
        # Calculate the size from those vectors
        len_A = numpy.linalg.norm(A)
        len_B = numpy.linalg.norm(B)
        # calculate the angle theta (in radians) between those vector
        theta = math.acos(numpy.dot(A, B) / (len_A * len_B))
        # Using the sin from theta, calculate the adjacent leg, which is the
        # distance from the point to the line
        distance = math.sin(theta) * len_A
        return distance

    def _has_clicked_in_selection_curve(self, position):
        x, y = position
        for i, curve in enumerate(self.curves):
            if self._calculate_distance(curve.wl_px, position) <= RADIUS:
                return i
        return None

    def _has_clicked_in_line(self, clicked_point):
        """ 
        Verify if was clicked in a line. If yes, it returns the insertion
        clicked_point in the point list.
        """
        for n, curve in enumerate(self.curves):
            position = bisect.bisect([node.x for node in curve.nodes],
                              clicked_point[0])
            if position != 0 and position != len(curve.nodes):
                p1 = curve.nodes[position-1].x, curve.nodes[position-1].y
                p2 = curve.nodes[position].x, curve.nodes[position].y
                if self.distance_from_point_line(p1, p2, clicked_point) <= 5:
                    return (n, position)
        return None

    def _has_clicked_in_save(self, clicked_point):
        x, y = clicked_point
        if self.padding < x < self.padding + 24 and \
           self.padding < y < self.padding + 24:
            return True
        else:
            return False

    def _calculate_distance(self, p1, p2):
        return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) ** 0.5

    def _move_node(self, x, y):
        self.to_render = True
        i,j = self.point_dragged

        width, height= self.GetVirtualSize()

        if y >= height - self.padding:
            y = height - self.padding

        if y <= self.padding:
            y = self.padding

        x = max(x, 0)

        if x > width:
            x = width

        x = max(x, TOOLBAR_SIZE)

        # A point must be greater than the previous one, but the first one
        if j > 0 and x <= self.curves[i].nodes[j-1].x:
            x = self.curves[i].nodes[j-1].x + 1

        # A point must be lower than the previous one, but the last one
        if j < len(self.curves[i].nodes) -1 \
           and x >= self.curves[i].nodes[j+1].x:
            x = self.curves[i].nodes[j+1].x - 1

        graylevel = self.PixelToHounsfield(x)
        opacity = self.PixelToOpacity(y)
        self.points[i][j]['x'] = graylevel
        self.points[i][j]['y'] = opacity
        self.curves[i].nodes[j].x = x
        self.curves[i].nodes[j].y = y
        self.curves[i].nodes[j].graylevel = graylevel
        self.curves[i].nodes[j].opacity = opacity
        for curve in self.curves:
            curve.CalculateWWWl()
            curve.wl_px = (self.HounsfieldToPixel(curve.wl),
                           self.OpacityToPixel(0))
        self.Refresh()

        # A point in the preset has been changed, raising a event
        evt = CLUTEvent(myEVT_CLUT_POINT_MOVE , self.GetId(), i)
        self.GetEventHandler().ProcessEvent(evt)

    def _move_curve(self, x, y):
        curve = self.curves[self.curve_dragged]
        curve.wl = self.PixelToHounsfield(x)
        curve.wl_px = x, self.OpacityToPixel(0)
        for node in curve.nodes:
            node.x += (x - self.previous_wl)
            node.graylevel = self.PixelToHounsfield(node.x)

        self.previous_wl = x
        self.to_draw_points = True
        self.Refresh()

        # The window level has been changed, raising a event!
        evt = CLUTEvent(myEVT_CLUT_CURVE_WL_CHANGE, self.GetId(),
                        self.curve_dragged)
        self.GetEventHandler().ProcessEvent(evt)

    def RemovePoint(self, i, j):
        """
        The point the point in the given i,j index
        """
        self.points[i].pop(j)
        self.colours[i].pop(j)

        self.curves[i].nodes.pop(j)
        # If the point to removed is that was selected before and have a
        # textbox, then remove the point and the textbox
        if (i, j) == self.point_dragged:
            self.point_dragged = None
        # If there is textbox and the point to remove is before it, then
        # decrement the index referenced to point that have the textbox.
        elif self.point_dragged and i == self.point_dragged[0] \
                and j < self.point_dragged[1]:
            new_i = self.point_dragged[0]
            new_j = self.point_dragged[1] - 1
            self.point_dragged = (new_i, new_j)
        # Can't have only one point in the curve
        if len(self.points[i]) == 1:
            self.RemoveCurve(i)
        else:
            curve = self.curves[i]
            curve.CalculateWWWl()
            curve.wl_px = (self.HounsfieldToPixel(curve.wl),
                           self.OpacityToPixel(0))

    def RemoveCurve(self, n_curve):
        self.points.pop(n_curve)
        self.colours.pop(n_curve)
        self.point_dragged = None

        self.curves.pop(n_curve)


    def _draw_gradient(self, ctx, height):
        #The gradient
        height += self.padding
        for curve in self.curves:
            for nodei, nodej in zip(curve.nodes[:-1], curve.nodes[1:]):
                path = ctx.CreatePath()
                path.MoveToPoint(int(nodei.x), height)
                path.AddLineToPoint(int(nodei.x), height)
                path.AddLineToPoint(int(nodei.x), nodei.y)
                path.AddLineToPoint(int(nodej.x), nodej.y)
                path.AddLineToPoint(int(nodej.x), height)

                colouri = nodei.colour[0],nodei.colour[1],nodei.colour[2], GRADIENT_RGBA
                colourj = nodej.colour[0],nodej.colour[1],nodej.colour[2], GRADIENT_RGBA
                b = ctx.CreateLinearGradientBrush(int(nodei.x), height,
                                                  int(nodej.x), height,
                                                  colouri, colourj)
                ctx.SetBrush(b)
                ctx.SetPen(wx.TRANSPARENT_PEN)
                ctx.FillPath(path)

    def _draw_curves(self, ctx):
        path = ctx.CreatePath()
        ctx.SetPen(wx.Pen(LINE_COLOUR, LINE_WIDTH))
        for curve in self.curves:
            path.MoveToPoint(curve.nodes[0].x, curve.nodes[0].y)
            for node in curve.nodes:
                path.AddLineToPoint(node.x, node.y)
            ctx.StrokePath(path)

    def _draw_points(self, ctx):
        for curve in self.curves:
            for node in curve.nodes:
                path = ctx.CreatePath()
                ctx.SetPen(wx.Pen(LINE_COLOUR, LINE_WIDTH))
                ctx.SetBrush(wx.Brush(node.colour))
                path.AddCircle(node.x, node.y, RADIUS)
                ctx.DrawPath(path)

    def _draw_selected_point_text(self, ctx):
        i,j = self.point_dragged
        node = self.curves[i].nodes[j]
        x,y = node.x, node.y
        value = node.graylevel
        alpha = node.opacity
        widget_width, widget_height = self.GetVirtualSize()

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font.SetWeight(wx.BOLD)
        font = ctx.CreateFont(font, TEXT_COLOUR)
        ctx.SetFont(font)

        text1 = _("Value: %-6d" % value)
        text2 = _("Alpha: %-.3f" % alpha)

        if ctx.GetTextExtent(text1)[0] > ctx.GetTextExtent(text2)[0]:
            wt, ht = ctx.GetTextExtent(text1)
        else:
            wt, ht = ctx.GetTextExtent(text2)

        wr, hr = wt + 2 * PADDING, ht * 2 + 2 * PADDING
        xr, yr = x + RADIUS, y - RADIUS - hr
        
        if xr + wr > widget_width:
            xr = x - RADIUS - wr
        if yr < 0:
            yr = y + RADIUS

        xf, yf = xr + PADDING, yr + PADDING

        ctx.SetBrush(wx.Brush(BACKGROUND_TEXT_COLOUR_RGBA))
        ctx.SetPen(wx.Pen(BACKGROUND_TEXT_COLOUR_RGBA))
        ctx.DrawRectangle(xr, yr, wr, hr)
        ctx.DrawText(text1, xf, yf)
        ctx.DrawText(text2, xf, yf + ht)

    def _draw_histogram(self, ctx, height):
        # The histogram
        x,y = self.Histogram.points[0]

        ctx.SetPen(wx.Pen(HISTOGRAM_LINE_COLOUR, HISTOGRAM_LINE_WIDTH))
        ctx.SetBrush(wx.Brush(HISTOGRAM_FILL_COLOUR))

        path = ctx.CreatePath()
        path.MoveToPoint(x,y)
        for x,y in self.Histogram.points:
            path.AddLineToPoint(x, y)

        ctx.PushState()
        ctx.StrokePath(path)
        ctx.PopState()
        path.AddLineToPoint(x, height + self.padding)
        path.AddLineToPoint(self.HounsfieldToPixel(self.Histogram.init), height + self.padding)
        x,y = self.Histogram.points[0]
        path.AddLineToPoint(x, y)
        ctx.FillPath(path)

    def _draw_selection_curve(self, ctx, height):
        ctx.SetPen(wx.Pen(LINE_COLOUR, LINE_WIDTH))
        ctx.SetBrush(wx.Brush((0, 0, 0)))
        for curve in self.curves:
            x_center, y_center = curve.wl_px
            ctx.DrawRectangle(x_center-SELECTION_SIZE/2.0, y_center, 
                              SELECTION_SIZE, SELECTION_SIZE)

    def _draw_tool_bar(self, ctx, height):
        ctx.SetPen(wx.TRANSPARENT_PEN)
        ctx.SetBrush(wx.Brush(TOOLBAR_COLOUR))
        ctx.DrawRectangle(0, 0, TOOLBAR_SIZE, height + self.padding * 2)
        image = self.save_button.image
        w, h = self.save_button.size
        x = (TOOLBAR_SIZE - w) / 2.0
        y = self.padding
        self.save_button.position = (x, y)
        ctx.DrawBitmap(image, x, y, w, h)

    def Render(self, dc):
        ctx = wx.GraphicsContext.Create(dc)
        width, height= self.GetVirtualSize()
        height -= (self.padding * 2)
        width -= self.padding

        self._draw_histogram(ctx, height)
        self._draw_gradient(ctx, height)
        self._draw_curves(ctx)
        self._draw_points(ctx)
        self._draw_selection_curve(ctx, height)
        self._draw_tool_bar(ctx, height)
        if self.point_dragged:
            self._draw_selected_point_text(ctx)

    def _build_histogram(self):
        width, height = self.GetVirtualSize()
        width -= self.padding
        height -= (self.padding * 2)
        x_init = self.Histogram.init
        x_end = self.Histogram.end
        y_init = 0
        y_end = math.log(max(self.histogram_array))
        proportion_x = width * 1.0 / (x_end - x_init)
        proportion_y = height * 1.0 / (y_end - y_init)
        self.Histogram.points = []
        for i in range(0, len(self.histogram_array), 5):
            if self.histogram_array[i]:
                y = math.log(self.histogram_array[i])
            else:
                y = 0
            x = self.HounsfieldToPixel(x_init + i)
            y = height - y * proportion_y + self.padding
            self.Histogram.points.append((x, y))

    def _build_buttons(self):
        img = wx.Image(os.path.join(inv_paths.ICON_DIR, 'Floppy.png'))
        width = img.GetWidth()
        height = img.GetHeight()
        self.save_button = Button()
        self.save_button.image = wx.Bitmap(img)
        self.save_button.size = (width, height)

    def __sort_pixel_points(self):
        """
        Sort the pixel points (colours and points) maintaining the reference
        between colours and points. It's necessary mainly in negative window
        width when the user interacts with this widgets.
        """
        for n, (point, colour) in enumerate(zip(self.points, self.colours)):
            point_colour = zip(point, colour)
            point_colour = sorted(point_colour, key=lambda x: x[0]['x'])
            self.points[n] = [i[0] for i in point_colour]
            self.colours[n] = [i[1] for i in point_colour]

    def CalculatePixelPoints(self):
        """
        Create a list with points (in pixel x, y coordinate) to draw based in
        the preset points (Hounsfield scale, opacity).
        """
        self.curves = []
        self.__sort_pixel_points()
        for points, colours in zip(self.points, self.colours):
            curve = Curve()
            for point, colour in zip(points, colours):
                x = self.HounsfieldToPixel(point['x'])
                y = self.OpacityToPixel(point['y'])
                node = Node()
                node.x = x
                node.y = y
                node.graylevel = point['x']
                node.opacity = point['y']
                node.colour = (int(colour['red'] * 255), 
                               int(colour['green'] * 255),
                               int(colour['blue'] * 255))
                curve.nodes.append(node)
            curve.CalculateWWWl()
            curve.wl_px = (self.HounsfieldToPixel(curve.wl),
                           self.OpacityToPixel(0))
            self.curves.append(curve)
        self._build_histogram()

    def HounsfieldToPixel(self, graylevel):
        """
        Given a Hounsfield point returns a pixel point in the canvas.
        """
        width,height = self.GetVirtualSize()
        width -= (TOOLBAR_SIZE)
        proportion = width * 1.0 / (self.end - self.init)
        x = (graylevel - self.init) * proportion + TOOLBAR_SIZE
        return x

    def OpacityToPixel(self, opacity):
        """
        Given a Opacity point returns a pixel point in the canvas.
        """
        width,height = self.GetVirtualSize()
        height -= (self.padding * 2)
        y = height - (opacity * height) + self.padding
        return y

    def PixelToHounsfield(self, x):
        """
        Translate from pixel point to Hounsfield scale.
        """
        width, height= self.GetVirtualSize()
        width -= (TOOLBAR_SIZE)
        proportion = width * 1.0 / (self.end - self.init)
        graylevel = (x - TOOLBAR_SIZE) / proportion - abs(self.init)
        return graylevel

    def PixelToOpacity(self, y):
        """
        Translate from pixel point to opacity.
        """
        width, height= self.GetVirtualSize()
        height -= (self.padding * 2)
        opacity = (height - y + self.padding) * 1.0 / height
        return opacity

    def SetRaycastPreset(self, preset):
        if not preset:
            self.to_draw_points = 0
        elif preset['advancedCLUT']:
            self.to_draw_points = 1
            self.points = preset['16bitClutCurves']
            self.colours = preset['16bitClutColors']
            self.CalculatePixelPoints()
        else:
            self.to_draw_points = 0
        self.Refresh()

    def SetHistogramArray(self, h_array, range):
        self.histogram_array = h_array
        self.Histogram.init = range[0]
        self.Histogram.end = range[1]

    def GetCurveWWWl(self, curve):
        return (self.curves[curve].ww, self.curves[curve].wl)

class CLUTEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id, curve):
        wx.PyCommandEvent.__init__(self, evtType, id)
        self.curve = curve
    def GetCurve(self):
        return self.curve


# Occurs when CLUT is sliding
myEVT_CLUT_SLIDER = wx.NewEventType()
EVT_CLUT_SLIDER = wx.PyEventBinder(myEVT_CLUT_SLIDER, 1)

# Occurs when CLUT was slided
myEVT_CLUT_SLIDER_CHANGE = wx.NewEventType()
EVT_CLUT_SLIDER_CHANGE = wx.PyEventBinder(myEVT_CLUT_SLIDER_CHANGE, 1)

# Occurs when CLUT point is changing
myEVT_CLUT_POINT_MOVE = wx.NewEventType()
EVT_CLUT_POINT_MOVE = wx.PyEventBinder(myEVT_CLUT_POINT_MOVE, 1)

# Occurs when a CLUT point was changed
myEVT_CLUT_POINT_RELEASE = wx.NewEventType()
EVT_CLUT_POINT_RELEASE = wx.PyEventBinder(myEVT_CLUT_POINT_RELEASE, 1)

# Selected a curve
myEVT_CLUT_CURVE_SELECT = wx.NewEventType()
EVT_CLUT_CURVE_SELECT = wx.PyEventBinder(myEVT_CLUT_CURVE_SELECT, 1)

# Changed the wl from a curve
myEVT_CLUT_CURVE_WL_CHANGE = wx.NewEventType()
EVT_CLUT_CURVE_WL_CHANGE = wx.PyEventBinder(myEVT_CLUT_CURVE_WL_CHANGE, 1)
