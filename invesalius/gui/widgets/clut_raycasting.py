import bisect
import math
import plistlib
import sys

import cairo
import numpy
import wx
import wx.lib.pubsub as ps
import wx.lib.wxcairo

import project

FONT_COLOUR = (1, 1, 1)
LINE_COLOUR = (0.5, 0.5, 0.5)
LINE_WIDTH = 2
HISTOGRAM_LINE_WIDTH = 1
HISTOGRAM_LINE_COLOUR = (0.5, 0.5, 0.5)
HISTOGRAM_FILL_COLOUR = (0.25, 0.25, 0.25)
BACKGROUND_TEXT_COLOUR_RGBA = (1, 0, 0, 0.5)
GRADIENT_RGBA = 0.75
RADIUS = 5

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
        self.points = []#plistlib.readPlist(sys.argv[-1])['16bitClutCurves']
        self.colours = []#plistlib.readPlist(sys.argv[-1])['16bitClutColors']
        self.init = -1024
        self.end = 2000
        self.padding = 5
        self.to_render = False
        self.to_draw_points = 0
        self.histogram_pixel_points = [[0,0]]
        self.histogram_array = [100,100]
        self.CreatePixelArray()
        #self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        #self.SetSizer(self.sizer)
        #self.DrawControls()
        self.dragged = False
        self.point_dragged = None
        self.DoBind()
        #self.__bind_events()
        #self.SetAutoLayout(True)
        #self.sizer.Fit(self)
        self.Show()
        #self.LoadVolume()

    def SetRange(self, range):
        self.init, self.end = range
        print "Range", range
        self.CreatePixelArray()

    def SetPadding(self, padding):
        self.padding = padding

    def DoBind(self):
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_LEFT_DOWN , self.OnClick)
        self.Bind(wx.EVT_LEFT_DCLICK , self.OnDoubleClick)
        self.Bind(wx.EVT_LEFT_UP , self.OnRelease)
        self.Bind(wx.EVT_RIGHT_DOWN , self.OnRighClick)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)

        ps.Publisher().subscribe(self.SetRaycastPreset,
                                'Set raycasting preset')

    def OnEraseBackground(self, evt):
        pass

    def OnClick(self, evt):
        point = self._has_clicked_in_a_point(evt.GetPositionTuple())
        if point:
            self.dragged = True
            self.point_dragged = point
            self.Refresh()
            return
        else:
            p = self._has_clicked_in_line(evt.GetPositionTuple())
            if p:
                n, p = p
                self.points[n].insert(p, {'x': 0, 'y': 0})
                self.pixels_points[n].insert(p, list(evt.GetPositionTuple()))
                self.colours[n].insert(p, {'red': 0, 'green': 0, 'blue': 0})
                self.PixelToHounsfield(n, p)
                self.Refresh()
                nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId())
                self.GetEventHandler().ProcessEvent(nevt)
                return
        evt.Skip()

    def OnDoubleClick(self, evt):
        point = self._has_clicked_in_a_point(evt.GetPositionTuple())
        if point:
            colour = wx.GetColourFromUser(self)
            if colour.IsOk():
                i,j = self.point_dragged
                r, g, b = [x/255.0 for x in colour.Get()]
                self.colours[i][j]['red'] = r
                self.colours[i][j]['green'] = g
                self.colours[i][j]['blue'] = b
                self.Refresh()
                nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId())
                self.GetEventHandler().ProcessEvent(nevt)
                return
        evt.Skip()

    def _has_clicked_in_a_point(self, position):
        """
        returns the index from the selected point
        """
        for i,curve in enumerate(self.pixels_points):
            for j,point in enumerate(curve):
                if self._calculate_distance(point, position) <= RADIUS:
                    return (i, j)
        return None

    def _has_clicked_in_line(self, position):
        for n, point in enumerate(self.pixels_points):
            p = bisect.bisect([i[0] for i in point], position[0])
            print p
            if p != 0 and p != len(point):
                x1, y1 = point[p-1]
                x2, y2 = position
                x3, y3 = point[p]
                if  int(float(x2 - x1) / (x3 - x2)) - int(float(y2 - y1) / (y3 - y2)) == 0:
                    return (n, p)
        return None

    def _calculate_distance(self, p1, p2):
        return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) ** 0.5

    def OnRighClick(self, evt):
        point = self._has_clicked_in_a_point(evt.GetPositionTuple())
        if point:
            i, j = point
            print "RightClick", i, j
            self.pixels_points[i].pop(j)
            self.points[i].pop(j)
            self.colours[i].pop(j)
            if (i, j) == self.point_dragged:
                self.point_dragged = None
            if len(self.points[i]) == 1:
                self.points.pop(i)
                self.pixels_points.pop(i)
                self.colours.pop(i)
            self.Refresh()
            nevt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId())
            self.GetEventHandler().ProcessEvent(nevt)
            return
        evt.Skip()

    def OnRelease(self, evt):
        if self.to_render:
            evt = CLUTEvent(myEVT_CLUT_POINT_CHANGED, self.GetId())
            self.GetEventHandler().ProcessEvent(evt)
        self.dragged = False
        self.to_render = False

    def OnWheel(self, evt):
        direction = evt.GetWheelRotation() / evt.GetWheelDelta()
        init = self.init - 10 * direction
        end = self.end + 10 * direction
        print direction, init, end
        self.SetRange((init, end))
        self.Refresh()

    def OnMotion(self, evt):
        if self.dragged:
            self.to_render = True
            i,j = self.point_dragged
            x = evt.GetX()
            y = evt.GetY()

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
            if j > 0 and x <= self.pixels_points[i][j-1][0]:
                x = self.pixels_points[i][j-1][0] + 1

            # A point must be lower than the previous one, but the last one
            if j < len(self.pixels_points[i]) -1 \
               and x >= self.pixels_points[i][j+1][0]:
                x = self.pixels_points[i][j+1][0] - 1

            self.pixels_points[i][j][0] = x
            self.pixels_points[i][j][1] = y
            self.PixelToHounsfield(i,j)
            self.Refresh()
            evt = CLUTEvent(myEVT_CLUT_POINT , self.GetId())
            self.GetEventHandler().ProcessEvent(evt)
        else:
            evt.Skip()

    def OnPaint(self, evt):
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.Brush('Black'))
        dc.Clear()
        if self.to_draw_points:
            self.Render(dc)

    def OnSize(self, evt):
        self.CreatePixelArray()
        self.Refresh()
    
    def _draw_gradient(self, ctx, height):
        #The gradient
        height += self.padding
        for i, curve in enumerate(self.pixels_points):
            x, y = curve[0]
            xini, yini = curve[0]
            xend, yend = curve[-1]
            gradient = cairo.LinearGradient(xini, height, xend, height)
            ctx.move_to(x, y)
            for j, point in enumerate(curve):
                x, y = point
                ctx.line_to(x, y)
                r = self.colours[i][j]['red']
                g = self.colours[i][j]['green']
                b = self.colours[i][j]['blue']
                gradient.add_color_stop_rgba((x - xini) * 1.0 / (xend - xini),
                                             r, g, b, GRADIENT_RGBA)
            ctx.line_to(x, height)
            ctx.line_to(xini, height)
            ctx.close_path()
            ctx.set_source(gradient)
            ctx.fill()

    def _draw_curves(self, ctx):
        #Drawing the lines
        for curve in self.pixels_points:
            x,y = curve[0]
            ctx.move_to(x, y)
            for point in curve:
                x,y = point
                ctx.line_to(x, y)
            ctx.set_source_rgb(*LINE_COLOUR)
            ctx.stroke()

    def _draw_points(self, ctx):
        #Drawing the circles that represents the points
        for i, curve in enumerate(self.pixels_points):
            for j, point in enumerate(curve):
                x,y = point
                r = self.colours[i][j]['red']
                g = self.colours[i][j]['green']
                b = self.colours[i][j]['blue']
                ctx.arc(x, y, RADIUS, 0, math.pi * 2)
                ctx.set_source_rgb(r, g, b)
                ctx.fill_preserve()
                ctx.set_source_rgb(*LINE_COLOUR)
                ctx.stroke()
                #ctx.move_to(x, y)

    def _draw_selected_point_text(self, ctx):
        ctx.select_font_face('Sans')
        ctx.set_font_size(15)
        i,j = self.point_dragged
        x,y = self.pixels_points[i][j]
        value = self.points[i][j]['x']
        alpha = self.points[i][j]['y']
        x_bearing, y_bearing, width, height, x_advance, y_advance\
                = ctx.text_extents("Value %6d" % value)

        widget_width = self.GetVirtualSizeTuple()[0]

        fheight = ctx.font_extents()[2]
        y_superior = y - RADIUS * 2 - 2 + y_bearing * 2
        y_inferior = fheight * 2

        # The bottom position of the text box mustn't be upper thant the top of
        # the width to always appears in the widget
        if y_superior <= self.padding:
            y_superior = y
            y_text1 = y + height
            y_text2 = y_text1 + 1 + fheight
        else:
            y_text1 = y - RADIUS - 1
            y_text2 = y_text1 - 1 - fheight

        x_left = x + RADIUS + 1
        rectangle_width = width + RADIUS + 1
        # The right position of the text box mustn't be in the widget area to
        # always appears in the widget
        if x_left + rectangle_width > widget_width:
            x_left = x - rectangle_width - 1 - RADIUS
            x_text = x_left - 1
        else:
            x_text = x + RADIUS + 1

        ctx.set_source_rgba(*BACKGROUND_TEXT_COLOUR_RGBA)
        ctx.rectangle(x_left, y_superior,
                      rectangle_width, y_inferior)
        ctx.fill()
        
        ctx.set_source_rgb(1, 1, 1)
        ctx.move_to(x_text, y_text1)
        ctx.show_text("Value: %6d" % value) 
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

    def _draw_selection_curve(self, ctx, width):
        for curve in self.pixels_points:
            x_center = (curve[0][0] + curve[-1][0])/2.0
            print "x_center", curve[0][0], curve[-1][0], x_center
            ctx.set_source_rgb(*LINE_COLOUR)
            ctx.stroke()
            ctx.rectangle(x_center-5, width-5, 10, 10)
            ctx.set_source_rgb(0,0,0)
            ctx.fill_preserve()

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
        self._draw_selection_curve(ctx, width)
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


    def CreatePixelArray(self):
        self.pixels_points = []
        for curve in self.points:
            self.pixels_points.append([self.HounsfieldToPixel(i) for i in curve])
        self._build_histogram()

    def HounsfieldToPixel(self, h_pt):
        """
        Given a Hounsfield point(graylevel, opacity), returns a pixel point in the canvas.
        """
        width,height = self.GetVirtualSizeTuple()
        width -= self.padding
        height -= (self.padding * 2)
        proportion = width * 1.0 / (self.end - self.init)
        x = (h_pt['x'] - self.init) * proportion
        y = height - (h_pt['y'] * height) + self.padding
        print y
        return [x,y]

    def PixelToHounsfield(self, i, j):
        """
        Given a Hounsfield point(graylevel, opacity), returns a pixel point in the canvas.
        """
        width, height= self.GetVirtualSizeTuple()
        width -= self.padding
        height -= (self.padding * 2)
        proportion = width * 1.0 / (self.end - self.init)
        x = self.pixels_points[i][j][0] / proportion - abs(self.init)
        y = (height - self.pixels_points[i][j][1] + self.padding) * 1.0 / height
        self.points[i][j]['x'] = x
        self.points[i][j]['y'] = y
        self.colours[i][j]
        print x,y

    def SetRaycastPreset(self, preset):
        preset = project.Project().raycasting_preset
        print preset
        if not preset:
            self.to_draw_points = 0
        elif preset['advancedCLUT']:
            self.to_draw_points = 1
            self.points = preset['16bitClutCurves']
            self.colours = preset['16bitClutColors']
            self.CreatePixelArray()
        else:
            self.to_draw_points = 0

    def SetHistrogramArray(self, h_array):
        self.histogram_array = h_array

class CLUTEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id):
        wx.PyCommandEvent.__init__(self, evtType, id)


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

class App(wx.App):
    def OnInit(self):
        str_type = sys.argv[-1].split("/")[-1].split(".")[0]
        self.frame = CLUTRaycastingWidget(None, -1, "InVesalius 3 - Raycasting: "+ str_type)
        self.frame.SetPreset(plistlib.readPlist(sys.argv[-1]))
        self.frame.Center()
        self.SetTopWindow(self.frame)
        return True

if __name__ == '__main__':
    app = App()
    app.MainLoop()
