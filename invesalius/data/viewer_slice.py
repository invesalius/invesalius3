# -*- coding: utf-8 -*-
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

import collections
import itertools
import os
import tempfile

import numpy as np

import vtk
from vtk.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

import invesalius.data.styles as styles
import wx
import sys
from wx.lib.pubsub import pub as Publisher

try:
    from agw import floatspin as FS
except ImportError: # if it's not there locally, try the wxPython lib.
    import wx.lib.agw.floatspin as FS

import invesalius.constants as const
import invesalius.data.cursor_actors as ca
import invesalius.data.slice_ as sl
import invesalius.data.vtk_utils as vtku
import invesalius.project as project
import invesalius.data.slice_data as sd
import invesalius.utils as utils
import invesalius.session as ses
import invesalius.data.converters as converters
import invesalius.data.measures as measures

if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

ID_TO_TOOL_ITEM = {}
STR_WL = "WL: %d  WW: %d"

ORIENTATIONS = {
        "AXIAL": const.AXIAL,
        "CORONAL": const.CORONAL,
        "SAGITAL": const.SAGITAL,
        }


class ContourMIPConfig(wx.Panel):
    def __init__(self, prnt, orientation):
        wx.Panel.__init__(self, prnt)
        self.mip_size_spin = wx.SpinCtrl(self, -1, min=1, max=240,
                                         initial=const.PROJECTION_MIP_SIZE)
        self.mip_size_spin.SetValue(const.PROJECTION_MIP_SIZE)
        self.mip_size_spin.SetToolTip(wx.ToolTip(_("Number of slices used to compound the visualization.")))
        w, h = self.mip_size_spin.GetTextExtent('M')
        self.mip_size_spin.SetMinSize((5 * w + 10, -1))
        self.mip_size_spin.SetMaxSize((5 * w + 10, -1))

        self.border_spin = FS.FloatSpin(self, -1, min_val=0, max_val=10,
                                        increment=0.1,
                                        value=const.PROJECTION_BORDER_SIZE,
                                        digits=1, agwStyle=FS.FS_LEFT)
        self.border_spin.SetToolTip(wx.ToolTip(_("Controls the sharpness of the"
                                                 " contour. The greater the"
                                                 " value, the sharper the"
                                                 " contour.")))
        w, h = self.border_spin.GetTextExtent('M')
        self.border_spin.SetMinSize((5 * w + 10, -1))
        self.border_spin.SetMaxSize((5 * w + 10, -1))

        self.inverted = wx.CheckBox(self, -1, _("Inverted order"))
        self.inverted.SetToolTip(wx.ToolTip(_("If checked, the slices are"
                                              " traversed in descending"
                                              " order to compound the"
                                              " visualization instead of"
                                              " ascending order.")))

        txt_mip_size = wx.StaticText(self, -1, _("Number of slices"), style=wx.ALIGN_CENTER_HORIZONTAL)
        self.txt_mip_border = wx.StaticText(self, -1, _("Sharpness"))

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(txt_mip_size, 0, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.mip_size_spin, 0, wx.EXPAND)
        try:
            sizer.Add(10, 0)
        except TypeError:
            sizer.Add((10, 0))
        sizer.Add(self.txt_mip_border, 0, wx.EXPAND | wx.ALL, 2)
        sizer.Add(self.border_spin, 0, wx.EXPAND)
        try:
            sizer.Add(10, 0)
        except TypeError:
            sizer.Add((10, 0))
        sizer.Add(self.inverted, 0, wx.EXPAND)
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.orientation = orientation
        self.canvas = None

        self.mip_size_spin.Bind(wx.EVT_SPINCTRL, self.OnSetMIPSize)
        self.border_spin.Bind(wx.EVT_SPINCTRL, self.OnSetMIPBorder)
        self.inverted.Bind(wx.EVT_CHECKBOX, self.OnCheckInverted)

        Publisher.subscribe(self._set_projection_type, 'Set projection type')

    def OnSetMIPSize(self, number_slices):
        val = self.mip_size_spin.GetValue()
        Publisher.sendMessage('Set MIP size %s' % self.orientation, number_slices=val)

    def OnSetMIPBorder(self, evt):
        val = self.border_spin.GetValue()
        Publisher.sendMessage('Set MIP border %s' % self.orientation, border_size=val)

    def OnCheckInverted(self, evt):
        val = self.inverted.GetValue()
        Publisher.sendMessage('Set MIP Invert %s' % self.orientation, invert=val)

    def _set_projection_type(self, projection_id):
        if projection_id in (const.PROJECTION_MIDA,
                             const.PROJECTION_CONTOUR_MIDA):
            self.inverted.Enable()
        else:
            self.inverted.Disable()

        if projection_id in (const.PROJECTION_CONTOUR_MIP,
                             const.PROJECTION_CONTOUR_MIDA):
            self.border_spin.Enable()
            self.txt_mip_border.Enable()
        else:
            self.border_spin.Disable()
            self.txt_mip_border.Disable()


class CanvasRendererCTX:
    def __init__(self, evt_renderer, canvas_renderer, orientation=None):
        """
        A Canvas to render over a vtktRenderer.

        Params:
            evt_renderer: a vtkRenderer which this class is going to watch for
                any render event to update the canvas content.
            canvas_renderer: the vtkRenderer where the canvas is going to be
                added.

        This class uses wx.GraphicsContext to render to a vtkImage.

        TODO: Verify why in Windows the color are strange when using transparency.
        TODO: Add support to evento (ex. click on a square)
        """
        self.canvas_renderer = canvas_renderer
        self.evt_renderer = evt_renderer
        self._size = self.canvas_renderer.GetSize()
        self.draw_list = []
        self.orientation = orientation
        self.gc = None
        self.last_cam_modif_time = -1
        self.modified = True
        self._drawn = False
        self._init_canvas()
        evt_renderer.AddObserver("StartEvent", self.OnPaint)

    def _init_canvas(self):
        w, h = self._size
        self._array = np.zeros((h, w, 4), dtype=np.uint8)

        self._cv_image = converters.np_rgba_to_vtk(self._array)

        self.mapper = vtk.vtkImageMapper()
        self.mapper.SetInputData(self._cv_image)
        self.mapper.SetColorWindow(255)
        self.mapper.SetColorLevel(128)

        self.actor = vtk.vtkActor2D()
        self.actor.SetPosition(0, 0)
        self.actor.SetMapper(self.mapper)
        self.actor.GetProperty().SetOpacity(0.99)

        self.canvas_renderer.AddActor2D(self.actor)

        self.rgb = np.zeros((h, w, 3), dtype=np.uint8)
        self.alpha = np.zeros((h, w, 1), dtype=np.uint8)

        self.bitmap = wx.EmptyBitmapRGBA(w, h)
        try:
            self.image = wx.Image(w, h, self.rgb, self.alpha)
        except TypeError:
            self.image = wx.ImageFromBuffer(w, h, self.rgb, self.alpha)

    def _resize_canvas(self, w, h):
        self._array = np.zeros((h, w, 4), dtype=np.uint8)
        self._cv_image = converters.np_rgba_to_vtk(self._array)
        self.mapper.SetInputData(self._cv_image)
        self.mapper.Update()

        self.rgb = np.zeros((h, w, 3), dtype=np.uint8)
        self.alpha = np.zeros((h, w, 1), dtype=np.uint8)

        self.bitmap = wx.EmptyBitmapRGBA(w, h)
        try:
            self.image = wx.Image(w, h, self.rgb, self.alpha)
        except TypeError:
            self.image = wx.ImageFromBuffer(w, h, self.rgb, self.alpha)

        self.modified = True

    def remove_from_renderer(self):
        self.canvas_renderer.RemoveActor(self.actor)
        self.evt_renderer.RemoveObservers("StartEvent")

    def OnPaint(self, evt, obj):
        size = self.canvas_renderer.GetSize()
        w, h = size
        if self._size != size:
            self._size = size
            self._resize_canvas(w, h)

        cam_modif_time = self.evt_renderer.GetActiveCamera().GetMTime()
        if (not self.modified) and cam_modif_time == self.last_cam_modif_time:
            return

        self.last_cam_modif_time = cam_modif_time

        self._array[:] = 0

        coord = vtk.vtkCoordinate()

        self.image.SetDataBuffer(self.rgb)
        self.image.SetAlphaBuffer(self.alpha)
        self.image.Clear()
        gc = wx.GraphicsContext.Create(self.image)
        if sys.platform != 'darwin':
            gc.SetAntialiasMode(0)

        self.gc = gc

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        #  font.SetWeight(wx.BOLD)
        font = gc.CreateFont(font, (0, 0, 255))
        gc.SetFont(font)

        pen = wx.Pen(wx.Colour(255, 0, 0, 128), 2, wx.SOLID)
        brush = wx.Brush(wx.Colour(0, 255, 0, 128))
        gc.SetPen(pen)
        gc.SetBrush(brush)
        gc.Scale(1, -1)

        for d in self.draw_list:
            d.draw_to_canvas(gc, self)

        gc.Destroy()

        self.gc = None

        if self._drawn:
            self.bitmap = self.image.ConvertToBitmap()
            self.bitmap.CopyToBuffer(self._array, wx.BitmapBufferFormat_RGBA)

        self._cv_image.Modified()
        self.modified = False
        self._drawn = False

    def calc_text_size(self, text, font=None):
        """
        Given an unicode text and a font returns the width and height of the
        rendered text in pixels.

        Params:
            text: An unicode text.
            font: An wxFont.

        Returns:
            A tuple with width and height values in pixels
        """
        if self.gc is None:
            return None
        gc = self.gc

        if font is None:
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

        _font = gc.CreateFont(font)
        gc.SetFont(_font)
        w, h = gc.GetTextExtent(text)
        return w, h

    def draw_line(self, pos0, pos1, arrow_start=False, arrow_end=False, colour=(255, 0, 0, 128), width=2, style=wx.SOLID):
        """
        Draw a line from pos0 to pos1

        Params:
            pos0: the start of the line position (x, y).
            pos1: the end of the line position (x, y).
            arrow_start: if to draw a arrow at the start of the line.
            arrow_end: if to draw a arrow at the end of the line.
            colour: RGBA line colour.
            width: the width of line.
            style: default wx.SOLID.
        """
        if self.gc is None:
            return None
        gc = self.gc

        p0x, p0y = pos0
        p1x, p1y = pos1

        p0y = -p0y
        p1y = -p1y

        pen = wx.Pen(wx.Colour(*[int(c) for c in colour]), width, wx.SOLID)
        pen.SetCap(wx.CAP_BUTT)
        gc.SetPen(pen)

        path = gc.CreatePath()
        path.MoveToPoint(p0x, p0y)
        path.AddLineToPoint(p1x, p1y)
        gc.StrokePath(path)

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font = gc.CreateFont(font)
        gc.SetFont(font)
        w, h = gc.GetTextExtent("M")

        p0 = np.array((p0x, p0y))
        p3 = np.array((p1x, p1y))
        if arrow_start:
            v = p3 - p0
            v = v / np.linalg.norm(v)
            iv = np.array((v[1], -v[0]))
            p1 = p0 + w*v + iv*w/2.0
            p2 = p0 + w*v + (-iv)*w/2.0

            path = gc.CreatePath()
            path.MoveToPoint(p0)
            path.AddLineToPoint(p1)
            path.MoveToPoint(p0)
            path.AddLineToPoint(p2)
            gc.StrokePath(path)

        if arrow_end:
            v = p3 - p0
            v = v / np.linalg.norm(v)
            iv = np.array((v[1], -v[0]))
            p1 = p3 - w*v + iv*w/2.0
            p2 = p3 - w*v + (-iv)*w/2.0

            path = gc.CreatePath()
            path.MoveToPoint(p3)
            path.AddLineToPoint(p1)
            path.MoveToPoint(p3)
            path.AddLineToPoint(p2)
            gc.StrokePath(path)

        self._drawn = True

    def draw_circle(self, center, radius, width=2, line_colour=(255, 0, 0, 128), fill_colour=(0, 0, 0, 0)):
        """
        Draw a circle centered at center with the given radius.

        Params:
            center: (x, y) position.
            radius: float number.
            width: line width.
            line_colour: RGBA line colour
            fill_colour: RGBA fill colour.
        """
        if self.gc is None:
            return None
        gc = self.gc

        pen = wx.Pen(wx.Colour(*line_colour), width, wx.SOLID)
        gc.SetPen(pen)

        brush = wx.Brush(wx.Colour(*fill_colour))
        gc.SetBrush(brush)

        cx, cy = center
        cy = -cy

        path = gc.CreatePath()
        path.AddCircle(cx, cy, 2.5)
        gc.StrokePath(path)
        gc.FillPath(path)
        self._drawn = True

    def draw_rectangle(self, pos, width, height, line_colour=(255, 0, 0, 128), fill_colour=(0, 0, 0, 0)):
        """
        Draw a rectangle with its top left at pos and with the given width and height.

        Params:
            pos: The top left pos (x, y) of the rectangle.
            width: width of the rectangle.
            height: heigth of the rectangle.
            line_colour: RGBA line colour.
            fill_colour: RGBA fill colour.
        """
        if self.gc is None:
            return None
        gc = self.gc

        px, py = pos
        gc.SetPen(wx.Pen(line_colour))
        gc.SetBrush(wx.Brush(fill_colour))
        gc.DrawRectangle(px, py, width, height)
        self._drawn = True

    def draw_text(self, text, pos, font=None, txt_colour=(255, 255, 255)):
        """
        Draw text.

        Params:
            text: an unicode text.
            pos: (x, y) top left position.
            font: if None it'll use the default gui font.
            txt_colour: RGB text colour
        """
        if self.gc is None:
            return None
        gc = self.gc

        if font is None:
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

        font = gc.CreateFont(font, txt_colour)
        gc.SetFont(font)

        px, py = pos
        py = -py

        gc.DrawText(text, px, py)
        self._drawn = True

    def draw_text_box(self, text, pos, font=None, txt_colour=(255, 255, 255), bg_colour=(128, 128, 128, 128), border=5):
        """
        Draw text inside a text box.

        Params:
            text: an unicode text.
            pos: (x, y) top left position.
            font: if None it'll use the default gui font.
            txt_colour: RGB text colour
            bg_colour: RGBA box colour
            border: the border size.
        """
        if self.gc is None:
            return None
        gc = self.gc

        if font is None:
            font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

        _font = gc.CreateFont(font, txt_colour)
        gc.SetFont(_font)
        w, h = gc.GetTextExtent(text)

        px, py = pos

        # Drawing the box
        cw, ch = w + border * 2, h + border * 2
        self.draw_rectangle((px, -py), cw, ch, bg_colour, bg_colour)

        # Drawing the text
        tpx, tpy = px + border, py - border
        self.draw_text(text, (tpx, tpy), font, txt_colour)
        self._drawn = True

    def draw_arc(self, center, p0, p1, line_colour=(255, 0, 0, 128), width=2):
        """
        Draw an arc passing in p0 and p1 centered at center.

        Params:
            center: (x, y) center of the arc.
            p0: (x, y).
            p1: (x, y).
            line_colour: RGBA line colour.
            width: width of the line.
        """
        if self.gc is None:
            return None
        gc = self.gc
        pen = wx.Pen(wx.Colour(*[int(c) for c in line_colour]), width, wx.SOLID)
        gc.SetPen(pen)

        c = np.array(center)
        v0 = np.array(p0) - c
        v1 = np.array(p1) - c

        c[1] = -c[1]
        v0[1] = -v0[1]
        v1[1] = -v1[1]

        s0 = np.linalg.norm(v0)
        s1 = np.linalg.norm(v1)

        a0 = np.arctan2(v0[1] , v0[0])
        a1 = np.arctan2(v1[1] , v1[0])

        if (a1 - a0) % (np.pi*2) < (a0 - a1) % (np.pi*2):
            sa = a0
            ea = a1
        else:
            sa = a1
            ea = a0

        path = gc.CreatePath()
        path.AddArc(float(c[0]), float(c[1]), float(min(s0, s1)), float(sa), float(ea), True)
        gc.StrokePath(path)
        self._drawn = True


class Viewer(wx.Panel):

    def __init__(self, prnt, orientation='AXIAL'):
        wx.Panel.__init__(self, prnt, size=wx.Size(320, 300))

        #colour = [255*c for c in const.ORIENTATION_COLOUR[orientation]]
        #self.SetBackgroundColour(colour)

        # Interactor additional style

        self._number_slices = const.PROJECTION_MIP_SIZE
        self._mip_inverted = False

        self.style = None
        self.last_position_mouse_move = ()
        self.state = const.STATE_DEFAULT

        self.overwrite_mask = False

        # All renderers and image actors in this viewer
        self.slice_data_list = []
        self.slice_data = None

        self.slice_actor = None
        self.interpolation_slice_status = True

        self.canvas = None

        # The layout from slice_data, the first is number of cols, the second
        # is the number of rows
        self.layout = (1, 1)
        self.orientation_texts = []

        self.measures = measures.MeasureData()
        self.actors_by_slice_number = collections.defaultdict(list)
        self.renderers_by_slice_number = {}

        self.orientation = orientation
        self.slice_number = 0
        self.scroll_enabled = True

        self.__init_gui()

        self._brush_cursor_op = const.DEFAULT_BRUSH_OP
        self._brush_cursor_size = const.BRUSH_SIZE
        self._brush_cursor_colour = const.BRUSH_COLOUR
        self._brush_cursor_type = const.DEFAULT_BRUSH_OP
        self.cursor = None
        self.wl_text = None
        self.on_wl = False
        self.on_text = False
        # VTK pipeline and actors
        self.__config_interactor()
        self.cross_actor = vtk.vtkActor()

        self.__bind_events()
        self.__bind_events_wx()

        self._flush_buffer = False

    def __init_gui(self):
        self.interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())

        scroll = wx.ScrollBar(self, -1, style=wx.SB_VERTICAL)
        self.scroll = scroll

        self.mip_ctrls = ContourMIPConfig(self, self.orientation)
        self.mip_ctrls.Hide()

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.interactor, 1, wx.EXPAND|wx.GROW)
        sizer.Add(scroll, 0, wx.EXPAND|wx.GROW)

        background_sizer = wx.BoxSizer(wx.VERTICAL)
        background_sizer.Add(sizer, 1, wx.EXPAND|wx.GROW|wx.ALL, 2)
        #background_sizer.Add(self.mip_ctrls, 0, wx.EXPAND|wx.GROW|wx.ALL, 2)
        self.SetSizer(background_sizer)
        background_sizer.Fit(self)

        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

        self.pick = vtk.vtkWorldPointPicker()
        self.interactor.SetPicker(self.pick)

    def OnContextMenu(self, evt):
        if (self.last_position_mouse_move ==\
              self.interactor.GetLastEventPosition()):
            self.menu.caller = self
            self.PopupMenu(self.menu)
        evt.Skip()

    def SetPopupMenu(self, menu):
        self.menu = menu

    def SetLayout(self, layout):
        self.layout = layout
        if (layout == (1,1)) and self.on_text:
            self.ShowTextActors()
        else:
            self.HideTextActors(change_status=False)

        slice_ = sl.Slice()
        self.LoadRenderers(slice_.GetOutput())
        self.__configure_renderers()
        self.__configure_scroll()

    def HideTextActors(self, change_status=True):
        try:
            self.canvas.draw_list.remove(self.wl_text)
        except (ValueError, AttributeError):
            pass

        [self.canvas.draw_list.remove(t) for t in self.orientation_texts]
        self.UpdateCanvas()
        if change_status:
            self.on_text = False

    def ShowTextActors(self):
        if self.on_wl and self.wl_text:
            self.canvas.draw_list.append(self.wl_text)
        [self.canvas.draw_list.append(t) for t in self.orientation_texts]
        self.UpdateCanvas()
        self.on_text = True

    def __set_layout(self, layout):
        self.SetLayout(layout)

    def __config_interactor(self):
        style = vtk.vtkInteractorStyleImage()

        interactor = self.interactor
        interactor.SetInteractorStyle(style)

    def SetInteractorStyle(self, state):
        cleanup = getattr(self.style, 'CleanUp', None)
        if cleanup:
            self.style.CleanUp()

        del self.style
        
        style = styles.get_style(state)(self)

        setup = getattr(style, 'SetUp', None)
        if setup:
            style.SetUp()

        self.style = style
        self.interactor.SetInteractorStyle(style)
        self.interactor.Render()

        self.state = state

    def UpdateWindowLevelValue(self, window, level):
        self.acum_achange_window, self.acum_achange_level = (window, level)
        self.SetWLText(window, level)

        slc = sl.Slice()
        slc._update_wwwl_widget_nodes(window, level)

        Publisher.sendMessage('Update all slice')
        Publisher.sendMessage('Update clut imagedata widget')

    def UpdateWindowLevelText(self, window, level):
        self.acum_achange_window, self.acum_achange_level = window, level
        self.SetWLText(window, level)
        self.interactor.Render()

    def OnClutChange(self, evt):
        Publisher.sendMessage('Change colour table from background image from widget',
                              nodes=evt.GetNodes())
        slc = sl.Slice()
        Publisher.sendMessage('Update window level value',
                              window=slc.window_width,
                              level=slc.window_level)

    def SetWLText(self, window_width, window_level):
        value = STR_WL%(window_level, window_width)
        if (self.wl_text):
            self.wl_text.SetValue(value)
            self.canvas.modified = True
            #self.interactor.Render()

    def EnableText(self):
        if not (self.wl_text):
            proj = project.Project()
            colour = const.ORIENTATION_COLOUR[self.orientation]

            # Window & Level text
            self.wl_text = vtku.TextZero()
            self.wl_text.SetPosition(const.TEXT_POS_LEFT_UP)
            self.wl_text.SetSymbolicSize(wx.FONTSIZE_LARGE)
            self.SetWLText(proj.level, proj.window)

            # Orientation text
            if self.orientation == 'AXIAL':
                values = [_('R'), _('L'), _('A'), _('P')]
            elif self.orientation == 'SAGITAL':
                values = [_('P'), _('A'), _('T'), _('B')]
            else:
                values = [_('R'), _('L'), _('T'), _('B')]

            left_text = self.left_text = vtku.TextZero()
            left_text.ShadowOff()
            left_text.SetColour(colour)
            left_text.SetPosition(const.TEXT_POS_VCENTRE_LEFT)
            left_text.SetVerticalJustificationToCentered()
            left_text.SetValue(values[0])
            left_text.SetSymbolicSize(wx.FONTSIZE_LARGE)

            right_text = self.right_text = vtku.TextZero()
            right_text.ShadowOff()
            right_text.SetColour(colour)
            right_text.SetPosition(const.TEXT_POS_VCENTRE_RIGHT_ZERO)
            right_text.SetVerticalJustificationToCentered()
            right_text.SetJustificationToRight()
            right_text.SetValue(values[1])
            right_text.SetSymbolicSize(wx.FONTSIZE_LARGE)

            up_text = self.up_text = vtku.TextZero()
            up_text.ShadowOff()
            up_text.SetColour(colour)
            up_text.SetPosition(const.TEXT_POS_HCENTRE_UP)
            up_text.SetJustificationToCentered()
            up_text.SetValue(values[2])
            up_text.SetSymbolicSize(wx.FONTSIZE_LARGE)

            down_text = self.down_text = vtku.TextZero()
            down_text.ShadowOff()
            down_text.SetColour(colour)
            down_text.SetPosition(const.TEXT_POS_HCENTRE_DOWN_ZERO)
            down_text.SetJustificationToCentered()
            down_text.SetVerticalJustificationToBottom()
            down_text.SetValue(values[3])
            down_text.SetSymbolicSize(wx.FONTSIZE_LARGE)

            self.orientation_texts = [left_text, right_text, up_text,
                                      down_text]

    def RenderTextDirection(self, directions):
        # Values are on ccw order, starting from the top:
        self.up_text.SetValue(directions[0])
        self.left_text.SetValue(directions[1])
        self.down_text.SetValue(directions[2])
        self.right_text.SetValue(directions[3])
        self.interactor.Render()

    def ResetTextDirection(self, cam):
        # Values are on ccw order, starting from the top:
        if self.orientation == 'AXIAL':
            values = [_("A"), _("R"), _("P"), _("L")]
        elif self.orientation == 'CORONAL':
            values = [_("T"), _("R"), _("B"), _("L")]
        else: # 'SAGITAL':
            values = [_("T"), _("P"), _("B"), _("A")]

        self.RenderTextDirection(values)
        self.interactor.Render()

    def UpdateTextDirection(self, cam):
        croll = cam.GetRoll()
        if (self.orientation == 'AXIAL'):

            if (croll >= -2 and croll <= 1):
                self.RenderTextDirection([_("A"), _("R"), _("P"), _("L")])

            elif(croll > 1 and croll <= 44):
                self.RenderTextDirection([_("AL"), _("RA"), _("PR"), _("LP")])

            elif(croll > 44 and croll <= 88):
               self.RenderTextDirection([_("LA"), _("AR"), _("RP"), _("PL")])

            elif(croll > 89 and croll <= 91):
               self.RenderTextDirection([_("L"), _("A"), _("R"), _("P")])

            elif(croll > 91 and croll <= 135):
               self.RenderTextDirection([_("LP"), _("AL"), _("RA"), _("PR")])

            elif(croll > 135 and croll <= 177):
                self.RenderTextDirection([_("PL"), _("LA"), _("AR"), _("RP")])

            elif(croll >= -180 and croll <= -178) or (croll < 180 and croll > 177):
                self.RenderTextDirection([_("P"), _("L"), _("A"), _("R")])

            elif(croll >= -177 and croll <= -133):
                self.RenderTextDirection([_("PR"), _("LP"), _("AL"), _("RA")])

            elif(croll >= -132 and croll <= -101):
                self.RenderTextDirection([_("RP"), _("PL"), _("LA"), _("AR")])

            elif(croll >= -101 and croll <= -87):
                self.RenderTextDirection([_("R"), _("P"), _("L"), _("A")])

            elif(croll >= -86 and croll <= -42):
                self.RenderTextDirection([_("RA"), _("PR"), _("LP"), _("AL")])

            elif(croll >= -41 and croll <= -2):
                self.RenderTextDirection([_("AR"), _("RP"), _("PL"), _("LA")])

        elif(self.orientation == "CORONAL"):

            if (croll >= -2 and croll <= 1):
                self.RenderTextDirection([_("T"), _("R"), _("B"), _("L")])

            elif(croll > 1 and croll <= 44):
                self.RenderTextDirection([_("TL"), _("RT"), _("BR"), _("LB")])

            elif(croll > 44 and croll <= 88):
               self.RenderTextDirection([_("LT"), _("TR"), _("RB"), _("BL")])

            elif(croll > 89 and croll <= 91):
               self.RenderTextDirection([_("L"), _("T"), _("R"), _("B")])

            elif(croll > 91 and croll <= 135):
               self.RenderTextDirection([_("LB"), _("TL"), _("RT"), _("BR")])

            elif(croll > 135 and croll <= 177):
                self.RenderTextDirection([_("BL"), _("LT"), _("TR"), _("RB")])

            elif(croll >= -180 and croll <= -178) or (croll < 180 and croll > 177):
                self.RenderTextDirection([_("B"), _("L"), _("T"), _("R")])

            elif(croll >= -177 and croll <= -133):
                self.RenderTextDirection([_("BR"), _("LB"), _("TL"), _("RT")])

            elif(croll >= -132 and croll <= -101):
                self.RenderTextDirection([_("RB"), _("BL"), _("LT"), _("TR")])

            elif(croll >= -101 and croll <= -87):
                self.RenderTextDirection([_("R"), _("B"), _("L"), _("T")])

            elif(croll >= -86 and croll <= -42):
                self.RenderTextDirection([_("RT"), _("BR"), _("LB"), _("TL")])

            elif(croll >= -41 and croll <= -2):
                self.RenderTextDirection([_("TR"), _("RB"), _("BL"), _("LT")])

        elif(self.orientation == "SAGITAL"):

            if(croll >= -101 and croll <= -87):
                self.RenderTextDirection([_("T"), _("P"), _("B"), _("A")])

            elif(croll >= -86 and croll <= -42):
                self.RenderTextDirection([_("TA"), _("PT"), _("BP"), _("AB")])

            elif(croll >= -41 and croll <= -2):
                self.RenderTextDirection([_("AT"), _("TP"), _("PB"), _("BA")])

            elif (croll >= -2 and croll <= 1):
                self.RenderTextDirection([_("A"), _("T"), _("P"), _("B")])

            elif(croll > 1 and croll <= 44):
                self.RenderTextDirection([_("AB"), _("TA"), _("PT"), _("BP")])

            elif(croll > 44 and croll <= 88):
               self.RenderTextDirection([_("BA"), _("AT"), _("TP"), _("PB")])

            elif(croll > 89 and croll <= 91):
               self.RenderTextDirection([_("B"), _("A"), _("T"), _("P")])

            elif(croll > 91 and croll <= 135):
               self.RenderTextDirection([_("BP"), _("AB"), _("TA"), _("PT")])

            elif(croll > 135 and croll <= 177):
                self.RenderTextDirection([_("PB"), _("BA"), _("AT"), _("TP")])

            elif(croll >= -180 and croll <= -178) or (croll < 180 and croll > 177):
                self.RenderTextDirection([_("P"), _("B"), _("A"), _("T")])

            elif(croll >= -177 and croll <= -133):
                self.RenderTextDirection([_("PT"), _("BP"), _("AB"), _("TA")])

            elif(croll >= -132 and croll <= -101):
                self.RenderTextDirection([_("TP"), _("PB"), _("BA"), _("AT")])


    def Reposition(self, slice_data):
        """
        Based on code of method Zoom in the
        vtkInteractorStyleRubberBandZoom, the of
        vtk 5.4.3
        """
        ren = slice_data.renderer
        size = ren.GetSize()

        ren.ResetCamera()
        ren.GetActiveCamera().Zoom(1.0)
        self.interactor.Render()

    def ChangeBrushColour(self, colour):
        vtk_colour = colour
        self._brush_cursor_colour = vtk_colour
        if (self.cursor):
            for slice_data in self.slice_data_list:
                slice_data.cursor.SetColour(vtk_colour)

    def SetBrushColour(self, colour):
        colour_vtk = [colour/float(255) for colour in colour]
        self._brush_cursor_colour = colour_vtk
        if self.slice_data.cursor:
            self.slice_data.cursor.SetColour(colour_vtk)

    def UpdateSlicesNavigation(self, arg, position):
        # Get point from base change
        ux, uy, uz = position[:3]
        px, py = self.get_slice_pixel_coord_by_world_pos(ux, uy, uz)
        coord = self.calcultate_scroll_position(px, py)

        self.cross.SetFocalPoint((ux, uy, uz))
        self.ScrollSlice(coord)
        Publisher.sendMessage('Set ball reference position', position=(ux, uy, uz))

    def ScrollSlice(self, coord):
        if self.orientation == "AXIAL":
            Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
                                       index=coord[0])
            Publisher.sendMessage(('Set scroll position', 'CORONAL'),
                                       index=coord[1])
        elif self.orientation == "SAGITAL":
            Publisher.sendMessage(('Set scroll position', 'AXIAL'),
                                       index=coord[2])
            Publisher.sendMessage(('Set scroll position', 'CORONAL'),
                                       index=coord[1])
        elif self.orientation == "CORONAL":
            Publisher.sendMessage(('Set scroll position', 'AXIAL'),
                                       index=coord[2])
            Publisher.sendMessage(('Set scroll position', 'SAGITAL'),
                                       index=coord[0])

    def get_slice_data(self, render):
        #for slice_data in self.slice_data_list:
            #if slice_data.renderer is render:
                #return slice_data
        # WARN: Return the only slice_data used in this slice_viewer.
        return self.slice_data

    def calcultate_scroll_position(self, x, y):
        # Based in the given coord (x, y), returns a list with the scroll positions for each
        # orientation, being the first position the sagital, second the coronal
        # and the last, axial.
        if self.orientation == 'AXIAL':
            axial = self.slice_data.number
            coronal = y
            sagital = x

        elif self.orientation == 'CORONAL':
            axial = y
            coronal = self.slice_data.number
            sagital = x

        elif self.orientation == 'SAGITAL':
            axial = y
            coronal = x
            sagital = self.slice_data.number

        return sagital, coronal, axial

    def calculate_matrix_position(self, coord):
        x, y, z = coord
        xi, xf, yi, yf, zi, zf = self.slice_data.actor.GetBounds()
        if self.orientation == 'AXIAL':
            mx = round((x - xi)/self.slice_.spacing[0], 0)
            my = round((y - yi)/self.slice_.spacing[1], 0)
        elif self.orientation == 'CORONAL':
            mx = round((x - xi)/self.slice_.spacing[0], 0)
            my = round((z - zi)/self.slice_.spacing[2], 0)
        elif self.orientation == 'SAGITAL':
            mx = round((y - yi)/self.slice_.spacing[1], 0)
            my = round((z - zi)/self.slice_.spacing[2], 0)
        return int(mx), int(my)

    def get_coordinate_cursor(self, mx, my, picker=None):
        """
        Given the mx, my screen position returns the x, y, z position in world
        coordinates.

        Parameters
            mx (int): x position.
            my (int): y position
            picker: the picker used to get calculate the voxel coordinate.

        Returns:
            world coordinate (x, y, z)
        """
        if picker is None:
            picker = self.pick

        slice_data = self.slice_data
        renderer = slice_data.renderer

        picker.Pick(mx, my, 0, renderer)
        x, y, z = picker.GetPickPosition()
        bounds = self.slice_data.actor.GetBounds()
        if bounds[0] == bounds[1]:
            x = bounds[0]
        elif bounds[2] == bounds[3]:
            y = bounds[2]
        elif bounds[4] == bounds[5]:
            z = bounds[4]
        return x, y, z

    def get_coordinate_cursor_edition(self, slice_data, picker=None):
        # Find position
        actor = slice_data.actor
        slice_number = slice_data.number
        if picker is None:
            picker = self.pick

        x, y, z = picker.GetPickPosition()

        # First we fix the position origin, based on vtkActor bounds
        bounds = actor.GetBounds()
        bound_xi, bound_xf, bound_yi, bound_yf, bound_zi, bound_zf = bounds
        x = float(x - bound_xi)
        y = float(y - bound_yi)
        z = float(z - bound_zi)

        dx = bound_xf - bound_xi
        dy = bound_yf - bound_yi
        dz = bound_zf - bound_zi

        dimensions = self.slice_.matrix.shape

        try:
            x = (x * dimensions[2]) / dx
        except ZeroDivisionError:
            x = slice_number
        try:
            y = (y * dimensions[1]) / dy
        except ZeroDivisionError:
            y = slice_number
        try:
            z = (z * dimensions[0]) / dz
        except ZeroDivisionError:
            z = slice_number

        return x, y, z

    def get_voxel_coord_by_screen_pos(self, mx, my, picker=None):
        """
        Given the (mx, my) screen position returns the voxel coordinate
        of the volume at (that mx, my) position.

        Parameters:
            mx (int): x position.
            my (int): y position
            picker: the picker used to get calculate the voxel coordinate.

        Returns:
            voxel_coordinate (x, y, z): voxel coordinate inside the matrix. Can
                be used to access the voxel value inside the matrix.
        """
        if picker is None:
            picker = self.pick

        wx, wy, wz = self.get_coordinate_cursor(mx, my, picker)
        x, y, z = self.get_voxel_coord_by_world_pos(wx, wy, wz)

        return (x, y, z)

    def get_voxel_coord_by_world_pos(self, wx, wy, wz):
        """
        Given the (x, my) screen position returns the voxel coordinate
        of the volume at (that mx, my) position.

        Parameters:
            wx (float): x position.
            wy (float): y position
            wz (float): z position

        Returns:
            voxel_coordinate (x, y, z): voxel coordinate inside the matrix. Can
                be used to access the voxel value inside the matrix.
        """
        px, py = self.get_slice_pixel_coord_by_world_pos(wx, wy, wz)
        x, y, z = self.calcultate_scroll_position(px, py)

        return (int(x), int(y), int(z))


    def get_slice_pixel_coord_by_screen_pos(self, mx, my, picker=None):
        """
        Given the (mx, my) screen position returns the pixel coordinate
        of the slice at (that mx, my) position.

        Parameters:
            mx (int): x position.
            my (int): y position
            picker: the picker used to get calculate the pixel coordinate.

        Returns:
            voxel_coordinate (x, y): voxel coordinate inside the matrix. Can
                be used to access the voxel value inside the matrix.
        """
        if picker is None:
            picker = self.pick

        wx, wy, wz = self.get_coordinate_cursor(mx, my, picker)
        x, y = self.get_slice_pixel_coord_by_world_pos(wx, wy, wz)
        return int(x), int(y)

    def get_slice_pixel_coord_by_world_pos(self, wx, wy, wz):
        """
        Given the (wx, wy, wz) world position returns the pixel coordinate
        of the slice at (that mx, my) position.

        Parameters:
            mx (int): x position.
            my (int): y position
            picker: the picker used to get calculate the pixel coordinate.

        Returns:
            voxel_coordinate (x, y): voxel coordinate inside the matrix. Can
                be used to access the voxel value inside the matrix.
        """
        coord = wx, wy, wz
        px, py = self.calculate_matrix_position(coord)

        return px, py

    def get_coord_inside_volume(self, mx, my, picker=None):
        if picker is None:
            picker = self.pick

        slice_data = self.slice_data
        renderer = slice_data.renderer

        coord = self.get_coordinate_cursor(picker)
        position = slice_data.actor.GetInput().FindPoint(coord)

        if position != -1:
            coord = slice_data.actor.GetInput().GetPoint(position)

        return coord

    def __bind_events(self):
        Publisher.subscribe(self.LoadImagedata,
                                 'Load slice to viewer')
        Publisher.subscribe(self.SetBrushColour,
                                 'Change mask colour')
        Publisher.subscribe(self.UpdateRender,
                                 'Update slice viewer')
        Publisher.subscribe(self.UpdateRender,
                                 'Update slice viewer %s' % self.orientation)
        Publisher.subscribe(self.UpdateCanvas,
                            'Redraw canvas')
        Publisher.subscribe(self.UpdateCanvas,
                            'Redraw canvas %s' % self.orientation)
        Publisher.subscribe(self.ChangeSliceNumber,
                                 ('Set scroll position',
                                  self.orientation))
        Publisher.subscribe(self.__update_cross_position,
                                'Update cross position')
        Publisher.subscribe(self.UpdateSlicesNavigation,
                            'Co-registered points')
        ###
        #  Publisher.subscribe(self.ChangeBrushColour,
                                 #  'Add mask')

        Publisher.subscribe(self.UpdateWindowLevelValue,
                            'Update window level value')

        Publisher.subscribe(self.UpdateWindowLevelText,
                            'Update window level text')

        #Publisher.subscribe(self._set_cross_visibility,\
        #                         'Set cross visibility')
        ###
        Publisher.subscribe(self.__set_layout,
                                'Set slice viewer layout')

        Publisher.subscribe(self.OnSetInteractorStyle,
                                'Set slice interaction style')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')

        #####
        Publisher.subscribe(self.OnShowText,
                                 'Show text actors on viewers')
        Publisher.subscribe(self.OnHideText,
                                 'Hide text actors on viewers')
        Publisher.subscribe(self.OnExportPicture,'Export picture to file')
        Publisher.subscribe(self.SetDefaultCursor, 'Set interactor default cursor')

        Publisher.subscribe(self.SetSizeNSCursor, 'Set interactor resize NS cursor')
        Publisher.subscribe(self.SetSizeWECursor, 'Set interactor resize WE cursor')
        Publisher.subscribe(self.SetSizeNWSECursor, 'Set interactor resize NSWE cursor')

        Publisher.subscribe(self.AddActors, 'Add actors ' + str(ORIENTATIONS[self.orientation]))
        Publisher.subscribe(self.RemoveActors, 'Remove actors ' + str(ORIENTATIONS[self.orientation]))
        Publisher.subscribe(self.OnSwapVolumeAxes, 'Swap volume axes')

        Publisher.subscribe(self.ReloadActualSlice, 'Reload actual slice')
        Publisher.subscribe(self.ReloadActualSlice, 'Reload actual slice %s' % self.orientation)
        Publisher.subscribe(self.OnUpdateScroll, 'Update scroll')


        # MIP
        Publisher.subscribe(self.OnSetMIPSize, 'Set MIP size %s' % self.orientation)
        Publisher.subscribe(self.OnSetMIPBorder, 'Set MIP border %s' % self.orientation)
        Publisher.subscribe(self.OnSetMIPInvert, 'Set MIP Invert %s' % self.orientation)
        Publisher.subscribe(self.OnShowMIPInterface, 'Show MIP interface')

        Publisher.subscribe(self.OnSetOverwriteMask, "Set overwrite mask")

        Publisher.subscribe(self.RefreshViewer, "Refresh viewer")
        Publisher.subscribe(self.SetInterpolatedSlices, "Set interpolated slices")
        Publisher.subscribe(self.UpdateInterpolatedSlice, "Update Slice Interpolation")


    def RefreshViewer(self):
        self.Refresh()

    def SetDefaultCursor(self):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

    def SetSizeNSCursor(self):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZENS))

    def SetSizeWECursor(self):
        self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZEWE))

    def SetSizeNWSECursor(self):
        if sys.platform.startswith('linux'):
            self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZENWSE))
        else:
            self.interactor.SetCursor(wx.StockCursor(wx.CURSOR_SIZING))

    def OnExportPicture(self, orientation, filename, filetype):
        dict = {"AXIAL": const.AXIAL,
                "CORONAL": const.CORONAL,
                "SAGITAL": const.SAGITAL}

        if orientation == dict[self.orientation]:
            Publisher.sendMessage('Begin busy cursor')
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)
                self._export_picture(orientation, win_filename, filetype)
            else:
                self._export_picture(orientation, filename, filetype)
            Publisher.sendMessage('End busy cursor')

    def _export_picture(self, id, filename, filetype):
        view_prop_list = []
        view_prop_list.append(self.slice_data.box_actor)
        self.slice_data.renderer.RemoveViewProp(self.slice_data.box_actor)

        dict = {"AXIAL": const.AXIAL,
                "CORONAL": const.CORONAL,
                "SAGITAL": const.SAGITAL}

        if id == dict[self.orientation]:
            if filetype == const.FILETYPE_POV:
                renwin = self.interactor.GetRenderWindow()
                image = vtk.vtkWindowToImageFilter()
                image.SetInput(renwin)
                writer = vtk.vtkPOVExporter()
                writer.SetFilePrefix(filename.split(".")[0])
                writer.SetRenderWindow(renwin)
                writer.Write()
            else:
                ren = self.slice_data.renderer
                #Use tiling to generate a large rendering.
                image = vtk.vtkRenderLargeImage()
                image.SetInput(ren)
                image.SetMagnification(1)
                image.Update()

                image = image.GetOutput()


                # write image file
                if (filetype == const.FILETYPE_BMP):
                    writer = vtk.vtkBMPWriter()
                elif (filetype == const.FILETYPE_JPG):
                    writer =  vtk.vtkJPEGWriter()
                elif (filetype == const.FILETYPE_PNG):
                    writer = vtk.vtkPNGWriter()
                elif (filetype == const.FILETYPE_PS):
                    writer = vtk.vtkPostScriptWriter()
                elif (filetype == const.FILETYPE_TIF):
                    writer = vtk.vtkTIFFWriter()
                    filename = "%s.tif"%filename.strip(".tif")

                writer.SetInputData(image)
                writer.SetFileName(filename.encode(const.FS_ENCODE))
                writer.Write()

            if not os.path.exists(filename):
                wx.MessageBox(_("InVesalius was not able to export this picture"), _("Export picture error"))

            for actor in view_prop_list:
                self.slice_data.renderer.AddViewProp(actor)

        Publisher.sendMessage('End busy cursor')

    def OnShowText(self):
        self.ShowTextActors()

    def OnHideText(self):
        self.HideTextActors()

    def OnCloseProject(self):
        self.CloseProject()

    def CloseProject(self):
        for slice_data in self.slice_data_list:
            del slice_data

        self.slice_data_list = []
        self.layout = (1, 1)

        del self.slice_data
        self.slice_data = None

        if self.canvas:
            self.canvas.draw_list = []
            self.canvas.remove_from_renderer()
            self.canvas = None

        self.orientation_texts = []

        self.slice_number = 0
        self.cursor = None
        self.wl_text = None
        self.pick = vtk.vtkWorldPointPicker()

    def OnSetInteractorStyle(self, style):
        self.SetInteractorStyle(style)

        if (style not in [const.SLICE_STATE_EDITOR, const.SLICE_STATE_WATERSHED]):
            Publisher.sendMessage('Set interactor default cursor')

    def __bind_events_wx(self):
        self.scroll.Bind(wx.EVT_SCROLL, self.OnScrollBar)
        self.scroll.Bind(wx.EVT_SCROLL_THUMBTRACK, self.OnScrollBarRelease)
        #self.scroll.Bind(wx.EVT_SCROLL_ENDSCROLL, self.OnScrollBarRelease)
        self.interactor.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.interactor.Bind(wx.EVT_RIGHT_UP, self.OnContextMenu)
        self.interactor.Bind(wx.EVT_SIZE, self.OnSize)

    def LoadImagedata(self, mask_dict):
        self.SetInput(mask_dict)

    def LoadRenderers(self, imagedata):
        number_renderers = self.layout[0] * self.layout[1]
        diff = number_renderers - len(self.slice_data_list)
        if diff > 0:
            for i in range(diff):
                slice_data = self.create_slice_window(imagedata)
                self.slice_data_list.append(slice_data)
        elif diff < 0:
            to_remove = self.slice_data_list[number_renderers::]
            for slice_data in to_remove:
                self.interactor.GetRenderWindow().RemoveRenderer(slice_data.renderer)
            self.slice_data_list = self.slice_data_list[:number_renderers]

    def __configure_renderers(self):
        proportion_x = 1.0 / self.layout[0]
        proportion_y = 1.0 / self.layout[1]
        # The (0,0) in VTK is in bottom left. So the creation from renderers
        # must be # in inverted order, from the top left to bottom right
        w, h = self.interactor.GetRenderWindow().GetSize()
        w *= proportion_x
        h *= proportion_y
        n = 0
        for j in range(self.layout[1]-1, -1, -1):
            for i in range(self.layout[0]):
                slice_xi = i*proportion_x
                slice_xf = (i+1)*proportion_x
                slice_yi = j*proportion_y
                slice_yf = (j+1)*proportion_y

                position = (slice_xi, slice_yi, slice_xf, slice_yf)
                slice_data = self.slice_data_list[n]
                slice_data.renderer.SetViewport(position)
                # Text actor position
                x, y = const.TEXT_POS_LEFT_DOWN
                slice_data.text.SetPosition((x+slice_xi,y+slice_yi))
                slice_data.SetCursor(self.__create_cursor())
                slice_data.SetSize((w, h))
                self.__update_camera(slice_data)

                style = 0
                if j == 0:
                    style = style | sd.BORDER_DOWN
                if j == self.layout[1] - 1:
                    style = style | sd.BORDER_UP

                if i == 0:
                    style = style | sd.BORDER_LEFT
                if i == self.layout[0] - 1:
                    style = style | sd.BORDER_RIGHT

                slice_data.SetBorderStyle(style)
                n += 1

    def __create_cursor(self):
        cursor = ca.CursorCircle()
        cursor.SetOrientation(self.orientation)
        #self.__update_cursor_position([i for i in actor_bound[1::2]])
        cursor.SetColour(self._brush_cursor_colour)
        cursor.SetSpacing(self.slice_.spacing)
        cursor.Show(0)
        self.cursor_ = cursor
        return cursor

    def SetInput(self, mask_dict):
        self.slice_ = sl.Slice()

        max_slice_number = sl.Slice().GetNumberOfSlices(self.orientation)
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                 max_slice_number)

        self.slice_data = self.create_slice_window()
        self.slice_data.SetCursor(self.__create_cursor())
        self.cam = self.slice_data.renderer.GetActiveCamera()
        self.__build_cross_lines()

        self.canvas = CanvasRendererCTX(self.slice_data.renderer, self.slice_data.canvas_renderer, self.orientation)
        self.canvas.draw_list.append(self.slice_data.text)

        # Set the slice number to the last slice to ensure the camera if far
        # enough to show all slices.
        self.set_slice_number(max_slice_number - 1)
        self.__update_camera()
        self.slice_data.renderer.ResetCamera()
        self.interactor.GetRenderWindow().AddRenderer(self.slice_data.renderer)
        self.interactor.Render()

        self.EnableText()
        self.wl_text.Hide()
        ## Insert cursor
        self.SetInteractorStyle(const.STATE_DEFAULT)

    def __build_cross_lines(self):
        renderer = self.slice_data.overlay_renderer

        cross = vtk.vtkCursor3D()
        cross.AllOff()
        cross.AxesOn()
        self.cross = cross

        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        cross_mapper = vtk.vtkPolyDataMapper()
        cross_mapper.SetInputConnection(cross.GetOutputPort())
        #cross_mapper.SetTransformCoordinate(c)

        p = vtk.vtkProperty()
        p.SetColor(1, 0, 0)

        cross_actor = vtk.vtkActor()
        cross_actor.SetMapper(cross_mapper)
        cross_actor.SetProperty(p)
        cross_actor.VisibilityOff()
        # Only the slices are pickable
        cross_actor.PickableOff()
        self.cross_actor = cross_actor

        renderer.AddActor(cross_actor)

    def __update_cross_position(self, position):
        self.cross.SetFocalPoint(position)

    def _set_cross_visibility(self, visibility):
        self.cross_actor.SetVisibility(visibility)

    def _set_editor_cursor_visibility(self, visibility):
        for slice_data in self.slice_data_list:
            slice_data.cursor.actor.SetVisibility(visibility)

    def SetOrientation(self, orientation):
        self.orientation = orientation
        for slice_data in self.slice_data_list:
            self.__update_camera(slice_data)

    def create_slice_window(self):
        renderer = vtk.vtkRenderer()
        renderer.SetLayer(0)
        cam = renderer.GetActiveCamera()

        canvas_renderer = vtk.vtkRenderer()
        canvas_renderer.SetLayer(1)
        canvas_renderer.SetActiveCamera(cam)
        canvas_renderer.SetInteractive(0)
        canvas_renderer.PreserveDepthBufferOn()

        overlay_renderer = vtk.vtkRenderer()
        overlay_renderer.SetLayer(2)
        overlay_renderer.SetActiveCamera(cam)
        overlay_renderer.SetInteractive(0)

        self.interactor.GetRenderWindow().SetNumberOfLayers(3)
        self.interactor.GetRenderWindow().AddRenderer(overlay_renderer)
        self.interactor.GetRenderWindow().AddRenderer(canvas_renderer)
        self.interactor.GetRenderWindow().AddRenderer(renderer)

        actor = vtk.vtkImageActor()
        self.slice_actor = actor
        # TODO: Create a option to let the user set if he wants to interpolate
        # the slice images.
       
        if int(ses.Session().slice_interpolation) == 1:
            actor.InterpolateOff()
        else:
            actor.InterpolateOn()

        slice_data = sd.SliceData()
        slice_data.SetOrientation(self.orientation)
        slice_data.renderer = renderer
        slice_data.canvas_renderer = canvas_renderer
        slice_data.overlay_renderer = overlay_renderer
        slice_data.actor = actor
        slice_data.SetBorderStyle(sd.BORDER_ALL)
        renderer.AddActor(actor)
        #  renderer.AddActor(slice_data.text.actor)
        renderer.AddViewProp(slice_data.box_actor)

        return slice_data

    def UpdateInterpolatedSlice(self):
        if self.slice_actor != None:
            if ses.Session().slice_interpolation:
                self.slice_actor.InterpolateOff()
            else:
                self.slice_actor.InterpolateOn()
            self.interactor.Render()


    def SetInterpolatedSlices(self, flag):
        self.interpolation_slice_status = flag
        if self.slice_actor != None:
            if self.interpolation_slice_status == True:
                self.slice_actor.InterpolateOn()
            else:
                self.slice_actor.InterpolateOff()
            self.interactor.Render()

    def __update_camera(self):
        orientation = self.orientation
        proj = project.Project()
        orig_orien = proj.original_orientation

        self.cam.SetFocalPoint(0, 0, 0)
        self.cam.SetViewUp(const.SLICE_POSITION[orig_orien][0][self.orientation])
        self.cam.SetPosition(const.SLICE_POSITION[orig_orien][1][self.orientation])
        #self.cam.ComputeViewPlaneNormal()
        #self.cam.OrthogonalizeViewUp()
        self.cam.ParallelProjectionOn()

    def __update_display_extent(self, image):
        self.slice_data.actor.SetDisplayExtent(image.GetExtent())
        self.slice_data.renderer.ResetCameraClippingRange()

    def UpdateRender(self):
        self.interactor.Render()

    def UpdateCanvas(self, evt=None):
        if self.canvas is not None:
            cp_draw_list = self.canvas.draw_list[:]
            self.canvas.draw_list = []

            # Removing all measures
            for i in cp_draw_list:
                if not isinstance(i, (measures.AngularMeasure, measures.LinearMeasure)):
                    self.canvas.draw_list.append(i)

            # Then add all needed measures
            for (m, mr) in self.measures.get(self.orientation, self.slice_data.number):
                if m.visible:
                    self.canvas.draw_list.append(mr)

            self.canvas.modified = True
            self.interactor.Render()

    def __configure_scroll(self):
        actor = self.slice_data_list[0].actor
        number_of_slices = self.layout[0] * self.layout[1]
        max_slice_number = actor.GetSliceNumberMax()/ \
                number_of_slices
        if actor.GetSliceNumberMax()% number_of_slices:
            max_slice_number += 1
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                                     max_slice_number)
        self.set_scroll_position(0)

    @property
    def number_slices(self):
        return self._number_slices

    @number_slices.setter
    def number_slices(self, val):
        if val != self._number_slices:
            self._number_slices = val
            buffer_ = self.slice_.buffer_slices[self.orientation]
            buffer_.discard_buffer()

    def set_scroll_position(self, position):
        self.scroll.SetThumbPosition(position)
        self.OnScrollBar()

    def UpdateSlice3D(self, pos):
        original_orientation = project.Project().original_orientation
        pos = self.scroll.GetThumbPosition()
        Publisher.sendMessage('Change slice from slice plane',
                              orientation=self.orientation, index=pos)

    def OnScrollBar(self, evt=None, update3D=True):
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
        if update3D:
            self.UpdateSlice3D(pos)
        if self.state == const.SLICE_STATE_CROSS:
            # Update other slice's cross according to the new focal point from
            # the actual orientation.
            focal_point = self.cross.GetFocalPoint()
            Publisher.sendMessage('Update cross position', position=focal_point)
            Publisher.sendMessage('Update slice viewer')
        else:
            self.interactor.Render()
        if evt:
            if self._flush_buffer:
                self.slice_.apply_slice_buffer_to_mask(self.orientation)
            evt.Skip()

    def OnScrollBarRelease(self, evt):
        pos = self.scroll.GetThumbPosition()
        evt.Skip()

    def OnKeyDown(self, evt=None, obj=None):
        pos = self.scroll.GetThumbPosition()
        skip = True

        min = 0
        max = self.slice_.GetMaxSliceNumber(self.orientation)

        projections = {wx.WXK_NUMPAD0 : const.PROJECTION_NORMAL,
                       wx.WXK_NUMPAD1 : const.PROJECTION_MaxIP,
                       wx.WXK_NUMPAD2 : const.PROJECTION_MinIP,
                       wx.WXK_NUMPAD3 : const.PROJECTION_MeanIP,
                       wx.WXK_NUMPAD4 : const.PROJECTION_MIDA,
                       wx.WXK_NUMPAD5 : const.PROJECTION_CONTOUR_MIP,
                       wx.WXK_NUMPAD6 : const.PROJECTION_CONTOUR_MIDA,}

        if self._flush_buffer:
            self.slice_.apply_slice_buffer_to_mask(self.orientation)

        if (evt.GetKeyCode() == wx.WXK_UP and pos > min):
            self.OnScrollForward()
            self.OnScrollBar()

        elif (evt.GetKeyCode() == wx.WXK_DOWN and pos < max):
            self.OnScrollBackward()
            self.OnScrollBar()

        elif (evt.GetKeyCode() == wx.WXK_NUMPAD_ADD):
            actual_value = self.mip_ctrls.mip_size_spin.GetValue()
            self.mip_ctrls.mip_size_spin.SetValue(actual_value + 1)
            if self.mip_ctrls.mip_size_spin.GetValue() != actual_value:
                self.number_slices = self.mip_ctrls.mip_size_spin.GetValue()
                self.ReloadActualSlice()

        elif (evt.GetKeyCode() == wx.WXK_NUMPAD_SUBTRACT):
            actual_value = self.mip_ctrls.mip_size_spin.GetValue()
            self.mip_ctrls.mip_size_spin.SetValue(actual_value - 1)
            if self.mip_ctrls.mip_size_spin.GetValue() != actual_value:
                self.number_slices = self.mip_ctrls.mip_size_spin.GetValue()
                self.ReloadActualSlice()

        elif evt.GetKeyCode() in projections:
            self.slice_.SetTypeProjection(projections[evt.GetKeyCode()])
            Publisher.sendMessage('Set projection type', projection_id=projections[evt.GetKeyCode()])
            Publisher.sendMessage('Reload actual slice')
            skip = False

        self.UpdateSlice3D(pos)
        self.interactor.Render()

        if evt and skip:
            evt.Skip()

    def OnScrollForward(self, evt=None, obj=None):
        if not self.scroll_enabled:
            return
        pos = self.scroll.GetThumbPosition()
        min = 0

        if(pos > min):
            if self._flush_buffer:
                self.slice_.apply_slice_buffer_to_mask(self.orientation)
            pos = pos - 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()

    def OnScrollBackward(self, evt=None, obj=None):
        if not self.scroll_enabled:
            return
        pos = self.scroll.GetThumbPosition()
        max = self.slice_.GetMaxSliceNumber(self.orientation)

        if(pos < max):
            if self._flush_buffer:
                self.slice_.apply_slice_buffer_to_mask(self.orientation)
            pos = pos + 1
            self.scroll.SetThumbPosition(pos)
            self.OnScrollBar()

    def OnSize(self, evt):
        w, h = evt.GetSize()
        w = float(w)
        h = float(h)
        if self.slice_data:
            self.slice_data.SetSize((w, h))
        evt.Skip()

    def OnSetMIPSize(self, number_slices):
        self.number_slices = number_slices
        self.ReloadActualSlice()

    def OnSetMIPBorder(self, border_size):
        self.slice_.n_border = border_size
        buffer_ = self.slice_.buffer_slices[self.orientation]
        buffer_.discard_buffer()
        self.ReloadActualSlice()

    def OnSetMIPInvert(self, invert):
        self._mip_inverted = invert
        buffer_ = self.slice_.buffer_slices[self.orientation]
        buffer_.discard_buffer()
        self.ReloadActualSlice()

    def OnShowMIPInterface(self, flag):
        if flag:
            if not self.mip_ctrls.Shown:
                self.mip_ctrls.Show()
                self.GetSizer().Add(self.mip_ctrls, 0, wx.EXPAND|wx.GROW|wx.ALL, 2)
                self.Layout()
        else:
            self.mip_ctrls.Hide()
            self.GetSizer().Detach(self.mip_ctrls)
            self.Layout()

    def OnSetOverwriteMask(self, flag):
        self.overwrite_mask = flag

    def set_slice_number(self, index):
        inverted = self.mip_ctrls.inverted.GetValue()
        border_size = self.mip_ctrls.border_spin.GetValue()
        image = self.slice_.GetSlices(self.orientation, index,
                                      self.number_slices, inverted, border_size)
        self.slice_data.actor.SetInputData(image)
        for actor in self.actors_by_slice_number[self.slice_data.number]:
            self.slice_data.renderer.RemoveActor(actor)
        for actor in self.actors_by_slice_number[index]:
            self.slice_data.renderer.AddActor(actor)

        for (m, mr) in self.measures.get(self.orientation, self.slice_data.number):
            try:
                self.canvas.draw_list.remove(mr)
            except ValueError:
                pass

        for (m, mr) in self.measures.get(self.orientation, index):
            if m.visible:
                self.canvas.draw_list.append(mr)

        if self.slice_._type_projection == const.PROJECTION_NORMAL:
            self.slice_data.SetNumber(index)
        else:
            max_slices = self.slice_.GetMaxSliceNumber(self.orientation)
            end = min(max_slices, index + self.number_slices - 1)
            self.slice_data.SetNumber(index, end)
        self.__update_display_extent(image)
        self.cross.SetModelBounds(self.slice_data.actor.GetBounds())

    def ChangeSliceNumber(self, index):
        #self.set_slice_number(index)
        self.scroll.SetThumbPosition(index)
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
        self.interactor.Render()

    def ReloadActualSlice(self):
        pos = self.scroll.GetThumbPosition()
        self.set_slice_number(pos)
        self.interactor.Render()

    def OnUpdateScroll(self):
        max_slice_number = sl.Slice().GetNumberOfSlices(self.orientation)
        self.scroll.SetScrollbar(wx.SB_VERTICAL, 1, max_slice_number,
                                 max_slice_number)

    def OnSwapVolumeAxes(self, axes):
        # Adjusting cursor spacing to match the spacing from the actual slice
        # orientation
        axis0, axis1 = axes
        cursor = self.slice_data.cursor
        spacing = cursor.spacing
        if (axis0, axis1) == (2, 1):
            cursor.SetSpacing((spacing[1], spacing[0], spacing[2]))
        elif (axis0, axis1) == (2, 0):
            cursor.SetSpacing((spacing[2], spacing[1], spacing[0]))
        elif (axis0, axis1) == (1, 0):
            cursor.SetSpacing((spacing[0], spacing[2], spacing[1]))

        self.slice_data.renderer.ResetCamera()

    def AddActors(self, actors, slice_number):
        "Inserting actors"
        pos = self.scroll.GetThumbPosition()
        #try:
            #renderer = self.renderers_by_slice_number[slice_number]
            #for actor in actors:
                #renderer.AddActor(actor)
        #except KeyError:
            #pass
        if pos == slice_number:
            for actor in actors:
                self.slice_data.renderer.AddActor(actor)

        self.actors_by_slice_number[slice_number].extend(actors)

    def RemoveActors(self, actors, slice_number):
        "Remove a list of actors"
        try:
            renderer = self.renderers_by_slice_number[slice_number]
        except KeyError:
            for actor in actors:
                self.actors_by_slice_number[slice_number].remove(actor)
                self.slice_data.renderer.RemoveActor(actor)
        else:
            for actor in actors:
                # Remove the actor from the renderer
                renderer.RemoveActor(actor)
                # and remove the actor from the actor's list
                self.actors_by_slice_number[slice_number].remove(actor)
