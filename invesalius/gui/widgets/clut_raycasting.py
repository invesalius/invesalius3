import bisect
import math
import sys

import cairo
import numpy
import wx
import wx.lib.wxcairo

FONT_COLOUR = (1, 1, 1)
LINE_COLOUR = (0.5, 0.5, 0.5)
LINE_WIDTH = 2
HISTOGRAM_LINE_WIDTH = 1
HISTOGRAM_LINE_COLOUR = (0.5, 0.5, 0.5)
HISTOGRAM_FILL_COLOUR = (0.25, 0.25, 0.25)
BACKGROUND_TEXT_COLOUR_RGBA = (1, 0, 0, 0.5)
TEXT_COLOUR = (1, 1, 1)
GRADIENT_RGBA = 0.75
RADIUS = 5
SELECTION_SIZE = 10

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
        self.ww = self.nodes[-1].graylevel - self.nodes[0].graylevel
        self.wl = self.nodes[0].graylevel + self.ww / 2.0

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
        self.padding = 5
        self.previous_wl = 0
        self.to_render = False
        self.dragged = False
        self.to_draw_points = 0
        self.point_dragged = None
        self.curve_dragged = None
        self.histogram_pixel_points = [[0,0]]
        self.histogram_array = [100,100]
        self.CalculatePixelPoints()
        self.__bind_events_wx()
        self.Show()

    def SetRange(self, range):
        """
        Se the range from hounsfield
        """
        self.init, self.end = range
        print "Range", range
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

    def OnEraseBackground(self, evt):
        pass

    def OnClick(self, evt):
        x, y = evt.GetPositionTuple()
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
            evt = CLUTEvent(myEVT_CLUT_CURVE_SELECTED, self.GetId(), curve)
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
                nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId(), n)
                self.GetEventHandler().ProcessEvent(nevt)
                return
        evt.Skip()

    def OnDoubleClick(self, evt):
        """
        Used to change the colour of a point
        """
        point = self._has_clicked_in_a_point(evt.GetPositionTuple())
        if point:
            colour = wx.GetColourFromUser(self)
            if colour.IsOk():
                i,j = point
                r, g, b = [x/255.0 for x in colour.Get()]
                self.colours[i][j]['red'] = r
                self.colours[i][j]['green'] = g
                self.colours[i][j]['blue'] = b
                print self.curves[i].nodes
                self.curves[i].nodes[j].colour = (r, g, b)
                self.Refresh()
                nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId(), i)
                self.GetEventHandler().ProcessEvent(nevt)
                return
        evt.Skip()

    def OnRighClick(self, evt):
        """
        Used to remove a point
        """
        point = self._has_clicked_in_a_point(evt.GetPositionTuple())
        if point:
            i, j = point
            print "RightClick", i, j
            self.RemovePoint(i, j)
            self.Refresh()
            nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId(), i)
            self.GetEventHandler().ProcessEvent(nevt)
            return
        n_curve = self._has_clicked_in_selection_curve(evt.GetPositionTuple())
        if n_curve is not None:
            print "Removing a curve"
            self.RemoveCurve(n_curve)
            self.Refresh()
            nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId(), n_curve)
            self.GetEventHandler().ProcessEvent(nevt)
        evt.Skip()

    def OnRelease(self, evt):
        """
        Generate a EVT_CLUT_POINT_CHANGED event indicating that a change has
        been occurred in the preset points.
        """
        if self.to_render:
            evt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId(), 0)
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
        init = self.init - 10 * direction
        end = self.end + 10 * direction
        print direction, init, end
        self.SetRange((init, end))
        self.Refresh()

    def OnMotion(self, evt):
        # User dragging a point
        x = evt.GetX()
        y = evt.GetY()
        if self.dragged and self.point_dragged:
            self.to_render = True
            i,j = self.point_dragged

            width, height= self.GetVirtualSizeTuple()

            if y >= height - self.padding:
                y = height - self.padding

            if y <= self.padding:
                y = self.padding

            if x < 0:
                x = 0

            if x > width:
                x = width

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
            evt = CLUTEvent(myEVT_CLUT_POINT , self.GetId(), i)
            self.GetEventHandler().ProcessEvent(evt)

        elif self.dragged and self.curve_dragged is not None:
            curve = self.curves[self.curve_dragged]
            curve.wl = self.PixelToHounsfield(x)
            curve.wl_px = x, self.OpacityToPixel(0)
            for node in curve.nodes:
                node.x += (x - self.previous_wl)
                node.graylevel = self.PixelToHounsfield(node.x)

            # The window level has been changed, raising a event!
            evt = CLUTEvent(myEVT_CLUT_CHANGED_CURVE_WL, self.GetId(),
                            self.curve_dragged)
            self.GetEventHandler().ProcessEvent(evt)

            self.previous_wl = x
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

    def _calculate_distance(self, p1, p2):
        return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) ** 0.5

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
            first_node = curve.nodes[0]
            last_node = curve.nodes[-1]
            xini, yini = first_node.x, first_node.y
            xend, yend = last_node.x, last_node.y
            gradient = cairo.LinearGradient(xini, height, xend, height)
            ctx.move_to(xini, yini)
            for node in curve.nodes:
                x, y = node.x, node.y
                r, g, b = node.colour
                ctx.line_to(x, y)
                gradient.add_color_stop_rgba((x - xini) * 1.0 / (xend - xini),
                                             r, g, b, GRADIENT_RGBA)
            ctx.line_to(x, height)
            ctx.line_to(xini, height)
            ctx.close_path()
            ctx.set_source(gradient)
            ctx.fill()

    def _draw_curves(self, ctx):
        for curve in self.curves:
            ctx.move_to(curve.nodes[0].x, curve.nodes[0].y)
            for node in curve.nodes:
                ctx.line_to(node.x, node.y)
            ctx.set_source_rgb(*LINE_COLOUR)
            ctx.stroke()

    def _draw_points(self, ctx):
        for curve in self.curves:
            for node in curve.nodes:
                ctx.arc(node.x, node.y, RADIUS, 0, math.pi * 2)
                ctx.set_source_rgb(*node.colour)
                ctx.fill_preserve()
                ctx.set_source_rgb(*LINE_COLOUR)
                ctx.stroke()

    def _draw_selected_point_text(self, ctx):
        ctx.select_font_face('Sans')
        ctx.set_font_size(15)
        i,j = self.point_dragged
        node = self.curves[i].nodes[j]
        x,y = node.x, node.y
        value = node.graylevel
        alpha = node.opacity
        widget_width = self.GetVirtualSizeTuple()[0]

        # To better understand text in cairo, see:
        # http://www.tortall.net/mu/wiki/CairoTutorial#understanding-text
        if ctx.text_extents("Value %d" % value)[2] > \
           ctx.text_extents("Alpha: %.3f" % alpha)[2]:
            text = "Value: %6d" % value
        else:
            text = "Alpha: %.3f" % alpha

        x_bearing, y_bearing, width, height, x_advance, y_advance\
                = ctx.text_extents(text)
        fascent, fdescent, fheight, fxadvance, fyadvance = ctx.font_extents()
        
        # The text box height is the double of text height plus 2, that is text
        # box border
        box_height = fheight * 2 + 2
        box_y = y - RADIUS - 1 - box_height

        # The bottom position of the text box mustn't be upper than the top of
        # the width to always appears in the widget
        if box_y <= self.padding:
            box_y = y + RADIUS + 1

        y_text1 = box_y + fascent
        y_text2 = y_text1 + fheight

        x_left = x + RADIUS + 1
        box_width = width + 2
        # The right position of the text box mustn't be in the widget area to
        # always appears in the widget
        if x_left + box_width > widget_width:
            x_left = x - box_width - 1 - RADIUS

        x_text = x_left + 1

        ctx.set_source_rgba(*BACKGROUND_TEXT_COLOUR_RGBA)
        ctx.rectangle(x_left, box_y,
                      box_width, box_height)
        ctx.fill()

        ctx.set_source_rgb(*TEXT_COLOUR)
        ctx.move_to(x_text, y_text1)
        ctx.show_text("Value: %d" % value) 
        ctx.move_to(x_text, y_text2)
        ctx.show_text("Alpha: %.3f" % alpha)

    def _draw_histogram(self, ctx, height):
        # The histogram
        x,y = self.histogram_pixel_points[0]
        print "=>", x,y
        ctx.move_to(x,y)
        ctx.set_line_width(HISTOGRAM_LINE_WIDTH)
        for x,y in self.histogram_pixel_points:
            ctx.line_to(x,y)
        ctx.line_to(x, height)
        ctx.line_to(0, height)
        x,y = self.histogram_pixel_points[0]
        ctx.line_to(x, y)
        ctx.set_source_rgb(*HISTOGRAM_FILL_COLOUR)
        ctx.fill_preserve()
        ctx.set_source_rgb(*HISTOGRAM_LINE_COLOUR)
        ctx.stroke()

    def _draw_selection_curve(self, ctx, height):
        for curve in self.curves:
            x_center, y_center = curve.wl_px
            ctx.rectangle(x_center-SELECTION_SIZE/2.0, y_center, SELECTION_SIZE,
                         SELECTION_SIZE)
            ctx.set_source_rgb(0,0,0)
            ctx.fill_preserve()
            ctx.set_source_rgb(*LINE_COLOUR)
            ctx.stroke()

    def Render(self, dc):
        ctx = wx.lib.wxcairo.ContextFromDC(dc)
        width, height= self.GetVirtualSizeTuple()
        height -= (self.padding * 2)
        width -= self.padding

        self._draw_histogram(ctx, height)
        ctx.set_line_width(LINE_WIDTH)
        self._draw_gradient(ctx, height)
        self._draw_curves(ctx)
        self._draw_points(ctx)
        self._draw_selection_curve(ctx, height)
        if sys.platform != "darwin": 
            if self.point_dragged:
                self._draw_selected_point_text(ctx)

    def _build_histogram(self):
        width, height= self.GetVirtualSizeTuple()
        width -= self.padding
        height -= self.padding
        y_init = 0
        y_end = math.log(max(self.histogram_array))
        print y_end
        proportion_x = width * 1.0 / (self.end - self.init)
        proportion_y = height * 1.0 / (y_end - y_init)
        print ":) ", y_end, proportion_y
        self.histogram_pixel_points = []
        for i in xrange(len(self.histogram_array)):
            if self.histogram_array[i]:
                y = math.log(self.histogram_array[i])
            else:
                y = 0
            x = self.init+ i
            x = (x + abs(self.init)) * proportion_x
            y = height - y * proportion_y
            self.histogram_pixel_points.append((x, y))

    def __sort_pixel_points(self):
        """
        Sort the pixel points (colours and points) maintaining the reference
        between colours and points. It's necessary mainly in negative window
        width when the user interacts with this widgets.
        """
        for n, (point, colour) in enumerate(zip(self.points, self.colours)):
            point_colour = zip(point, colour)
            point_colour.sort(key=lambda x: x[0]['x'])
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
                node.colour = colour['red'], colour['green'], colour['blue']
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
        width,height = self.GetVirtualSizeTuple()
        width -= self.padding
        proportion = width * 1.0 / (self.end - self.init)
        x = (graylevel - self.init) * proportion
        return x

    def OpacityToPixel(self, opacity):
        """
        Given a Opacity point returns a pixel point in the canvas.
        """
        width,height = self.GetVirtualSizeTuple()
        height -= (self.padding * 2)
        y = height - (opacity * height) + self.padding
        return y

    def PixelToHounsfield(self, x):
        """
        Translate from pixel point to Hounsfield scale.
        """
        width, height= self.GetVirtualSizeTuple()
        width -= self.padding
        proportion = width * 1.0 / (self.end - self.init)
        graylevel = x / proportion - abs(self.init)
        return graylevel

    def PixelToOpacity(self, y):
        """
        Translate from pixel point to opacity.
        """
        width, height= self.GetVirtualSizeTuple()
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

    def SetHistrogramArray(self, h_array):
        self.histogram_array = h_array

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
myEVT_CLUT_SLIDER_CHANGED = wx.NewEventType()
EVT_CLUT_SLIDER_CHANGED = wx.PyEventBinder(myEVT_CLUT_SLIDER_CHANGED, 1)

# Occurs when CLUT point is changing
myEVT_CLUT_POINT = wx.NewEventType()
EVT_CLUT_POINT = wx.PyEventBinder(myEVT_CLUT_POINT, 1)

# Occurs when a CLUT point was changed
myEVT_CLUT_POINT_CHANGED = wx.NewEventType()
EVT_CLUT_POINT_CHANGED = wx.PyEventBinder(myEVT_CLUT_POINT_CHANGED, 1)

# Selected a curve
myEVT_CLUT_CURVE_SELECTED = wx.NewEventType()
EVT_CLUT_CURVE_SELECTED = wx.PyEventBinder(myEVT_CLUT_CURVE_SELECTED, 1)

# Changed the wl from a curve
myEVT_CLUT_CHANGED_CURVE_WL = wx.NewEventType()
EVT_CLUT_CHANGED_CURVE_WL = wx.PyEventBinder(myEVT_CLUT_CHANGED_CURVE_WL, 1)
