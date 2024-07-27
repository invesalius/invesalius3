import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import wx

if TYPE_CHECKING:
    import numpy as np

HISTOGRAM_LINE_COLOUR = (128, 128, 128)
HISTOGRAM_FILL_COLOUR = (64, 64, 64)
HISTOGRAM_LINE_WIDTH = 1

DEFAULT_COLOUR = (0, 0, 0)

TEXT_COLOUR = (255, 255, 255)
BACKGROUND_TEXT_COLOUR_RGBA = (255, 0, 0, 128)

GRADIENT_RGBA = 0.75 * 255

LINE_COLOUR = (128, 128, 128)
LINE_WIDTH = 2
RADIUS = 5

PADDING = 2


@dataclass(order=True)
class Node:
    value: float
    colour: Tuple[int, int, int] = field(compare=False)


class CLUTEvent(wx.PyCommandEvent):
    def __init__(self, evtType: int, id: int, nodes: List[Node]):
        wx.PyCommandEvent.__init__(self, evtType, id)
        self.nodes = nodes

    def GetNodes(self) -> List[Node]:
        return self.nodes


# Occurs when CLUT point is changing
myEVT_CLUT_NODE_CHANGED = wx.NewEventType()
EVT_CLUT_NODE_CHANGED = wx.PyEventBinder(myEVT_CLUT_NODE_CHANGED, 1)


class CLUTImageDataWidget(wx.Panel):
    """
    Widget used to config the Lookup table from imagedata.
    """

    def __init__(
        self,
        parent: wx.Window,
        id: int,
        histogram: "np.ndarray",
        init: float,
        end: float,
        nodes: Optional[List[Node]] = None,
    ):
        super().__init__(parent, id)

        self.SetFocusIgnoringChildren()
        self.SetMinSize((400, 200))

        self.histogram = histogram

        self._init = init
        self._end = end

        self.i_init = init
        self.i_end = end

        self._range = 0.05 * (end - init)
        self._scale = 1.0

        if nodes is None:
            self.wl = (init + end) / 2.0
            self.ww = end - init

            self.nodes = [Node(init, (0, 0, 0)), Node(end, (255, 255, 255))]
        else:
            self.nodes = nodes
            self.nodes.sort()

            n0 = nodes[0]
            nn = nodes[-1]

            self.ww = nn.value - n0.value
            self.wl = (nn.value + n0.value) / 2.0

        self._s_init = init
        self._s_end = end

        self.middle_pressed = False
        self.right_pressed = False
        self.left_pressed = False

        self.selected_node: Optional[Node] = None
        self.last_selected: Optional[Node] = None

        self.first_show = True

        self._d_hist: List[Tuple[float, float]] = []

        self._build_drawn_hist()
        self.__bind_events_wx()

    @property
    def window_level(self) -> float:
        self.nodes.sort()
        p0 = self.nodes[0].value
        pn = self.nodes[-1].value
        return (pn + p0) / 2

    @property
    def window_width(self) -> float:
        self.nodes.sort()
        p0 = self.nodes[0].value
        pn = self.nodes[-1].value
        return pn - p0

    def __bind_events_wx(self) -> None:
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackGround)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)

        self.Bind(wx.EVT_MOTION, self.OnMotion)

        self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleClick)
        self.Bind(wx.EVT_MIDDLE_UP, self.OnMiddleRelease)

        self.Bind(wx.EVT_LEFT_DOWN, self.OnClick)
        self.Bind(wx.EVT_LEFT_UP, self.OnRelease)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)

        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightClick)

        self.Bind(wx.EVT_CHAR, self.OnKeyDown)

    def _build_drawn_hist(self) -> None:
        w, h = self.GetVirtualSize()
        # w = len(self.histogram)
        # h = 1080

        x_init = self._init
        x_end = self._end

        y_init = 0
        y_end = math.log(self.histogram.max() + 1)

        prop_x = (w) * 1.0 / (x_end - x_init)
        prop_y = (h) * 1.0 / (y_end - y_init)

        self._d_hist = []
        for i in range(w):
            x = i / prop_x + x_init - 1
            if self.i_init <= x < self.i_end:
                try:
                    y = math.log(self.histogram[int(x - self.i_init)] + 1) * prop_y
                except IndexError:
                    pass

                self._d_hist.append((i, y))

    def _interpolation(self, x: float):
        f = math.floor(x)
        c = math.ceil(x)
        h = self.histogram

        if f != c:
            return h[f] + (h[c] - h[f]) / (c - f) * (x - f)
        else:
            return h[int(x)]

    def OnEraseBackGround(self, evt: wx.Event) -> None:
        pass

    def OnSize(self, evt: wx.Event) -> None:
        if self.first_show:
            w, h = self.GetVirtualSize()
            init = self.pixel_to_hounsfield(-RADIUS)
            end = self.pixel_to_hounsfield(w + RADIUS)
            self._init = init
            self._end = end
            self._range = 0.05 * (end - init)

            self._s_init = init
            self._s_end = end

            self.first_show = False

        self._build_drawn_hist()
        self.Refresh()
        evt.Skip()

    def OnPaint(self, evt: wx.Event) -> None:
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.Brush("Black"))
        dc.Clear()

        self.draw_histogram(dc)
        self.draw_gradient(dc)

        if self.last_selected is not None:
            self.draw_text(dc, self.last_selected.value)

    def OnWheel(self, evt: wx.MouseEvent) -> None:
        """
        Increase or decrease the range from hounsfield scale showed. It
        doesn't change values in preset, only to visualization.
        """
        direction = evt.GetWheelRotation() / evt.GetWheelDelta()
        init = self._init - direction * self._range
        end = self._end + direction * self._range
        self.SetRange(init, end)
        self.Refresh()

    def OnMiddleClick(self, evt: wx.MouseEvent) -> None:
        self.middle_pressed = True
        self.last_x = self.pixel_to_hounsfield(evt.GetX())

    def OnMiddleRelease(self, evt: wx.Event) -> None:
        self.middle_pressed = False

    def OnClick(self, evt: wx.MouseEvent) -> None:
        px, py = evt.GetPosition()
        self.left_pressed = True
        self.selected_node = self.get_node_clicked(px, py)
        self.last_selected = self.selected_node
        if self.selected_node is not None:
            self.Refresh()

    def OnRelease(self, evt: wx.Event) -> None:
        self.left_pressed = False
        self.selected_node = None

    def OnDoubleClick(self, evt: wx.MouseEvent) -> None:
        w, h = self.GetVirtualSize()
        px, py = evt.GetPosition()

        # Verifying if the user double-click in a node-colour.
        selected_node = self.get_node_clicked(px, py)
        if selected_node:
            # The user double-clicked a node colour. Give the user the
            # option to change the color from this node.
            colour_dialog = wx.GetColourFromUser(self, (0, 0, 0))
            if colour_dialog.IsOk():
                r, g, b = colour_dialog.Get()[:3]
                selected_node.colour = r, g, b
                self._generate_event()
        else:
            # The user doesn't clicked in a node colour. Creates a new node
            # colour with the DEFAULT_COLOUR
            vx = self.pixel_to_hounsfield(px)
            node = Node(vx, DEFAULT_COLOUR)
            self.nodes.append(node)
            self._generate_event()

        self.Refresh()

    def OnRightClick(self, evt: wx.MouseEvent) -> None:
        w, h = self.GetVirtualSize()
        px, py = evt.GetPosition()
        selected_node = self.get_node_clicked(px, py)

        if selected_node:
            self.nodes.remove(selected_node)
            self._generate_event()
            self.Refresh()

    def OnMotion(self, evt: wx.MouseEvent) -> None:
        if self.middle_pressed:
            x = self.pixel_to_hounsfield(evt.GetX())
            dx = x - self.last_x
            init = self._init - dx
            end = self._end - dx
            self.SetRange(init, end)
            self.Refresh()
            self.last_x = x

        # The user is dragging a colour node
        elif self.left_pressed and self.selected_node:
            x = self.pixel_to_hounsfield(evt.GetX())
            self.selected_node.value = float(x)
            self.Refresh()

            # A point in the preset has been changed, raising a event
            self._generate_event()

    def OnKeyDown(self, evt: wx.KeyEvent) -> None:
        if self.last_selected is not None:
            # Right key - Increase node value
            if evt.GetKeyCode() in (wx.WXK_RIGHT, wx.WXK_NUMPAD_RIGHT):
                n = self.last_selected
                n.value = self.pixel_to_hounsfield(self.hounsfield_to_pixel(n.value) + 1)
                self.Refresh()
                self._generate_event()

            # Left key - Decrease node value
            elif evt.GetKeyCode() in (wx.WXK_LEFT, wx.WXK_NUMPAD_LEFT):
                n = self.last_selected
                n.value = self.pixel_to_hounsfield(self.hounsfield_to_pixel(n.value) - 1)
                self.Refresh()
                self._generate_event()

            # Enter key - Change node colour
            elif evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                n = self.last_selected
                colour_dialog = wx.GetColourFromUser(self, n.colour)
                if colour_dialog.IsOk():
                    r, g, b = colour_dialog.Get()
                    n.colour = r, g, b
                    self.Refresh()
                    self._generate_event()

            # Delete key - Deletes a node.
            elif evt.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                n = self.last_selected
                self.last_selected = None
                self.nodes.remove(n)
                self.Refresh()
                self._generate_event()

            # (Shift + )Tab key - selects the (previous) next node
            elif evt.GetKeyCode() == wx.WXK_TAB:
                n = self.last_selected
                self.nodes.sort()
                idx = self.nodes.index(n)
                if evt.ShiftDown():
                    nidx = (idx - 1) % len(self.nodes)
                else:
                    nidx = (idx + 1) % len(self.nodes)
                self.last_selected = self.nodes[nidx]
                self.Refresh()
        evt.Skip()

    def draw_histogram(
        self, dc: Union[wx.WindowDC, wx.MemoryDC, wx.PrinterDC, wx.MetafileDC]
    ) -> None:
        w, h = self.GetVirtualSize()
        ctx: wx.GraphicsContext = wx.GraphicsContext.Create(dc)

        ctx.SetPen(wx.Pen(HISTOGRAM_LINE_COLOUR, HISTOGRAM_LINE_WIDTH))
        ctx.SetBrush(wx.Brush(HISTOGRAM_FILL_COLOUR))

        path: wx.GraphicsPath = ctx.CreatePath()
        xi, yi = self._d_hist[0]
        path.MoveToPoint(xi, h - yi)
        for x, y in self._d_hist:
            path.AddLineToPoint(x, h - y)

        # w0 = self.pixel_to_hounsfield(0)
        # w1 = self.pixel_to_hounsfield(w - 1)
        ctx.Translate(self.hounsfield_to_pixel(self._s_init), 0)
        ctx.Scale(self._scale, 1.0)
        # ctx.Translate(-self.hounsfield_to_pixel(self._s_init), 0)
        # ctx.Translate(0, h)
        # ctx.Translate(0, -h)
        # ctx.Translate(0, h * h/1080.0 )
        ctx.PushState()
        ctx.StrokePath(path)
        ctx.PopState()
        path.AddLineToPoint(x, h)
        path.AddLineToPoint(xi, h)
        path.AddLineToPoint(*self._d_hist[0])
        ctx.FillPath(path)

    def draw_gradient(
        self, dc: Union[wx.WindowDC, wx.MemoryDC, wx.PrinterDC, wx.MetafileDC]
    ) -> None:
        w, h = self.GetVirtualSize()
        ctx: wx.GraphicsContext = wx.GraphicsContext.Create(dc)
        knodes = sorted(self.nodes)
        for ni, nj in zip(knodes[:-1], knodes[1:]):
            vi = round(self.hounsfield_to_pixel(ni.value))
            vj = round(self.hounsfield_to_pixel(nj.value))

            path: wx.GraphicsPath = ctx.CreatePath()
            path.AddRectangle(vi, 0, vj - vi, h)

            ci = ni.colour + (GRADIENT_RGBA,)
            cj = nj.colour + (GRADIENT_RGBA,)
            b = ctx.CreateLinearGradientBrush(vi, h, vj, h, ci, cj)
            ctx.SetBrush(b)
            ctx.SetPen(wx.TRANSPARENT_PEN)
            ctx.FillPath(path)

            self._draw_circle(vi, ni.colour, ctx)
            self._draw_circle(vj, nj.colour, ctx)

    def _draw_circle(self, px: float, color: Tuple[int, int, int], ctx: wx.GraphicsContext) -> None:
        w, h = self.GetVirtualSize()

        path: wx.GraphicsPath = ctx.CreatePath()
        path.AddCircle(px, h / 2, RADIUS)

        path.AddCircle(px, h / 2, RADIUS)
        ctx.SetPen(wx.Pen("white", LINE_WIDTH + 1))
        ctx.StrokePath(path)

        ctx.SetPen(wx.Pen(LINE_COLOUR, LINE_WIDTH - 1))
        ctx.SetBrush(wx.Brush(color))
        ctx.StrokePath(path)
        ctx.FillPath(path)

    def draw_text(
        self,
        dc: Union[wx.WindowDC, wx.MemoryDC, wx.PrinterDC, wx.MetafileDC],
        value: float,
    ) -> None:
        w, h = self.GetVirtualSize()
        ctx = wx.GraphicsContext.Create(dc)

        x = self.hounsfield_to_pixel(value)
        y = h / 2

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font.SetWeight(wx.BOLD)
        graphics_font = ctx.CreateFont(font, TEXT_COLOUR)
        ctx.SetFont(graphics_font)

        text = "Value: %-6d" % value

        wt, ht = ctx.GetTextExtent(text)

        wr, hr = wt + 2 * PADDING, ht + 2 * PADDING
        xr, yr = x + RADIUS, y - RADIUS - hr

        if xr + wr > w:
            xr = x - RADIUS - wr
        if yr < 0:
            yr = y + RADIUS

        xf, yf = xr + PADDING, yr + PADDING
        ctx.SetBrush(wx.Brush(BACKGROUND_TEXT_COLOUR_RGBA))
        ctx.SetPen(wx.Pen(BACKGROUND_TEXT_COLOUR_RGBA))
        ctx.DrawRectangle(xr, yr, wr, hr)
        ctx.DrawText(text, xf, yf)

    def _generate_event(self) -> None:
        evt = CLUTEvent(myEVT_CLUT_NODE_CHANGED, self.GetId(), self.nodes)
        self.GetEventHandler().ProcessEvent(evt)

    def hounsfield_to_pixel(self, x: float) -> float:
        w, h = self.GetVirtualSize()
        p = (x - self._init) * w * 1.0 / (self._end - self._init)
        return p

    def pixel_to_hounsfield(self, x: float) -> float:
        w, h = self.GetVirtualSize()
        prop_x = (self._end - self._init) / (w * 1.0)
        p = x * prop_x + self._init
        return p

    def get_node_clicked(self, px: int, py: int) -> Optional[Node]:
        w, h = self.GetVirtualSize()
        for n in self.nodes:
            x = self.hounsfield_to_pixel(n.value)
            y = h / 2

            if ((px - x) ** 2 + (py - y) ** 2) ** 0.5 <= RADIUS:
                return n

        return None

    def SetRange(self, init: float, end: float) -> None:
        """
        Sets the range from hounsfield
        """
        scale = (self._s_end - self._s_init) * 1.0 / (end - init)
        if scale <= 10.0:
            self._scale = scale
            self._init, self._end = init, end
            # self._build_drawn_hist()
