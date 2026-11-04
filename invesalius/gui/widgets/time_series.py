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

from math import floor, log10

import numpy as np
import vtkmodules.vtkRenderingContextOpenGL2  # noqa: F401
import vtkmodules.vtkRenderingFreeType  # noqa: F401
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
import wx
import wx.lib.platebtn as pbtn
import wx.svg
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkChartsCore import vtkAxis, vtkChart, vtkChartXY
from vtkmodules.vtkCommonDataModel import vtkTable
from vtkmodules.vtkRenderingContext2D import vtkContextTransform
from vtkmodules.vtkRenderingCore import vtkTextActor
from vtkmodules.vtkViewsContext2D import vtkContextView
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

from invesalius.i18n import tr as _


class TimeSeriesPanel(wx.Panel):
    GRAPH_HEIGHT = 120
    CHART_MARGIN = 12
    AXIS_LABEL_GAP = 6
    GRAPH_OFFSET_Y = 12
    HEADER_Y = 0.9
    COLLAPSED_HEIGHT = 24

    def __init__(self, parent):
        super().__init__(parent)
        self.playback = None
        self.on_seek = self.on_tick = None
        self._dragging = False
        self._collapsed = False
        self.body = body = wx.Panel(self)
        for window in (self, body):
            window.SetBackgroundColour(wx.BLACK)
            window.SetForegroundColour(wx.Colour(190, 190, 190))
        # Reserve tick-label spacing without reducing the curve's height.
        canvas_height = self.GRAPH_HEIGHT + self.AXIS_LABEL_GAP
        self.canvas = wxVTKRenderWindowInteractor(body, -1, size=(100, canvas_height))
        self.canvas.SetMinSize((100, canvas_height))
        self.view = vtkContextView()
        self.view.SetRenderWindow(self.canvas.GetRenderWindow())
        self.view.SetInteractor(self.canvas.GetRenderWindow().GetInteractor())
        self.view.GetRenderer().SetBackground(0, 0, 0)
        self.chart = vtkChartXY()
        self.chart.SetInteractive(False)
        self.chart.SetShowLegend(False)
        self.chart.GetBackgroundBrush().SetColor(0, 0, 0, 255)
        self.chart_transform = vtkContextTransform()
        self.chart_transform.GetTransform().Translate(0, -self.GRAPH_OFFSET_Y)
        self.chart_transform.AddItem(self.chart)
        self.view.GetScene().AddItem(self.chart_transform)
        self.header = vtkTextActor()
        self.header.SetInput("^ " + _("EEG/MEG time series"))
        self.header.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        self.header.SetPosition(0.995, self.HEADER_Y)
        text = self.header.GetTextProperty()
        text.SetColor(0.75, 0.75, 0.75)
        text.SetFontSize(10)
        text.SetJustificationToRight()
        text.SetVerticalJustificationToTop()
        text.SetBackgroundOpacity(0)
        self.view.GetRenderer().AddActor2D(self.header)
        for position in (vtkAxis.BOTTOM, vtkAxis.LEFT):
            axis = self.chart.GetAxis(position)
            axis.SetBehavior(vtkAxis.FIXED)
            axis.SetNotation(vtkAxis.FIXED_NOTATION)
            axis.SetNumberOfTicks(5 if position == vtkAxis.BOTTOM else 3)
            axis.SetGridVisible(position == vtkAxis.LEFT)
            axis.GetPen().SetColor(90, 90, 90, 255)
            axis.GetGridPen().SetColor(30, 30, 30, 255)
            for text in (axis.GetLabelProperties(), axis.GetTitleProperties()):
                text.SetColor(0.7, 0.7, 0.7)
            axis.GetLabelProperties().SetFontSize(12)
            axis.GetTitleProperties().SetFontSize(16)
        self.chart.GetAxis(vtkAxis.BOTTOM).SetLabelOffset(self.AXIS_LABEL_GAP)
        self.chart.SetHiddenAxisBorder(self.CHART_MARGIN)
        self.canvas.Enable(1)
        self.canvas.SetName(_("EEG/MEG time series. Press H to hide or show the graph."))
        self.canvas.SetToolTip(_("Hide time series (H)"))
        self.canvas.Bind(wx.EVT_LEFT_DOWN, self._on_press)
        self.canvas.Bind(wx.EVT_MOTION, self._on_motion)
        self.canvas.Bind(wx.EVT_LEFT_UP, self._on_release)
        self.canvas.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_release)
        self.canvas.Bind(wx.EVT_CHAR_HOOK, self._on_key)

        self._icons = {}
        for name, path in {
            "previous": "M3 3h2v10H3z M12 3v10L5 8z",
            "play": "M5 3l8 5-8 5z",
            "pause": "M4 3h3v10H4z M9 3h3v10H9z",
            "next": "M11 3h2v10h-2z M4 3l7 5-7 5z",
        }.items():
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
                f'<path fill="#b0b0b0" d="{path}"/></svg>'
            )
            self._icons[name] = wx.svg.SVGimage.CreateFromBytes(svg.encode()).ConvertToScaledBitmap(
                wx.Size(16, 16), self
            )
        self.previous = pbtn.PlateButton(
            body, bmp=self._icons["previous"], size=(28, 24), style=pbtn.PB_STYLE_SQUARE
        )
        self.play = pbtn.PlateButton(
            body, bmp=self._icons["play"], size=(28, 24), style=pbtn.PB_STYLE_SQUARE
        )
        self.next = pbtn.PlateButton(
            body, bmp=self._icons["next"], size=(28, 24), style=pbtn.PB_STYLE_SQUARE
        )
        for button, name in (
            (self.previous, _("Previous sample")),
            (self.play, _("Play")),
            (self.next, _("Next sample")),
        ):
            button.SetBackgroundColour(wx.BLACK)
            button.SetPressColor(wx.Colour(45, 45, 45))
            button.SetName(name)
            button.SetToolTip(name)
        self.speed = wx.Choice(
            body, choices=["0.01x", "0.05x", "0.1x", "0.25x", "0.5x", "1x", "2x"]
        )
        self.speed.SetBackgroundColour(wx.Colour(25, 25, 25))
        self.speed.SetForegroundColour(wx.Colour(176, 176, 176))
        self.speed.SetName(_("Playback speed"))
        self.speed.SetToolTip(_("Playback speed"))
        self.position = wx.StaticText(body)
        self.position.SetForegroundColour(wx.Colour(190, 190, 190))
        self.axis_title = wx.StaticText(body, style=wx.ALIGN_CENTER)
        self.axis_title.SetForegroundColour(wx.Colour(178, 178, 178))
        font = self.axis_title.GetFont()
        font.SetPixelSize(wx.Size(0, 16))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.axis_title.SetFont(font)
        controls = wx.BoxSizer(wx.HORIZONTAL)
        for widget in (self.previous, self.play, self.next, self.speed, self.position):
            controls.Add(widget, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        footer = wx.GridSizer(1, 3, 0, 0)
        footer.Add(controls, 0, wx.ALIGN_CENTER_VERTICAL)
        footer.Add(self.axis_title, 0, wx.ALIGN_CENTER)
        footer.AddSpacer(0)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(
            self.canvas,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            16,
        )
        self._footer_item = sizer.Add(footer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 4)
        body.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(body, 1, wx.EXPAND)
        self.SetSizer(outer)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        self.previous.Bind(wx.EVT_BUTTON, lambda event: self._step(-1))
        self.next.Bind(wx.EVT_BUTTON, lambda event: self._step(1))
        self.play.Bind(wx.EVT_BUTTON, self._on_play)
        self.speed.Bind(wx.EVT_CHOICE, self._on_speed)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

    def set_data(self, playback, values, unit, on_seek, on_tick):
        self.clear()
        self.playback = playback
        self.on_seek, self.on_tick = on_seek, on_tick
        axis = playback.axis
        self.time_scale = 1000 if axis.dt < 1 else 1
        self.time_unit = "ms" if self.time_scale == 1000 else "s"
        times = (axis.t0 + np.arange(axis.n_frames) * axis.dt) * self.time_scale
        self.chart.ClearPlots()
        self.table = vtkTable()
        for name, array in (("Time", times), ("RMS", values)):
            column = numpy_to_vtk(array, deep=True)
            column.SetName(name)
            self.table.AddColumn(column)
        curve = self.chart.AddPlot(vtkChart.LINE)
        curve.SetInputData(self.table, 0, 1)
        curve.SetColor(90, 185, 230, 255)
        curve.SetWidth(1.5)
        padding = axis.dt * self.time_scale / 2 if axis.n_frames == 1 else 0
        bottom = self.chart.GetAxis(vtkAxis.BOTTOM)
        bottom.SetTitle("")
        self.axis_title.SetLabel(_("Time") + f" ({self.time_unit})")
        bottom.SetRange(times[0] - padding, times[-1] + padding)
        left = self.chart.GetAxis(vtkAxis.LEFT)
        left.SetTitle(f"RMS ({unit})")
        limit = float(np.max(values)) * 1.1 or 1.0
        left.SetRange(0, limit)
        for chart_axis in (bottom, left):
            low, high = chart_axis.GetMinimum(), chart_axis.GetMaximum()
            chart_axis.SetPrecision(max(0, 2 - floor(log10(high - low))))
        self.cursor_table = vtkTable()
        for name, array in (("Time", np.zeros(2)), ("RMS", np.array([0, limit]))):
            column = numpy_to_vtk(array, deep=True)
            column.SetName(name)
            self.cursor_table.AddColumn(column)
        cursor = self.chart.AddPlot(vtkChart.LINE)
        cursor.SetInputData(self.cursor_table, 0, 1)
        cursor.SetColor(240, 155, 75, 255)
        cursor.SetWidth(1.0)
        self.speed.SetStringSelection(f"{playback.speed:g}x")
        self.sync()

    def sync(self):
        if self.playback is None:
            return
        playback = self.playback
        time = playback.time * self.time_scale
        cursor_time = self.cursor_table.GetColumn(0)
        cursor_time.SetValue(0, time)
        cursor_time.SetValue(1, time)
        cursor_time.Modified()
        self.cursor_table.Modified()
        self.position.SetLabel(
            f"{time:.2f} {self.time_unit}  ({playback.index + 1}/{playback.axis.n_frames})"
        )
        action = _("Pause") if playback.playing else _("Play")
        if self.play.GetName() != action:
            self.play.SetBitmap(self._icons["pause" if playback.playing else "play"])
            self.play.SetName(action)
            self.play.SetToolTip(action)
            self.play.Refresh()
        self.play.Enable(playback.axis.n_frames > 1)
        self.previous.Enable(playback.index > 0)
        self.next.Enable(playback.index < playback.axis.n_frames - 1)
        if playback.playing and not self.timer.IsRunning():
            self.timer.Start(33)
        elif not playback.playing:
            self.timer.Stop()
        if self.canvas.IsShownOnScreen():
            self.canvas.Render()

    def clear(self):
        self.timer.Stop()
        self._on_release(None)
        self.playback = None
        self.on_seek = self.on_tick = None

    def _on_play(self, event):
        if self.playback.playing:
            self.playback.pause()
        else:
            self.playback.play()
        self.on_tick()
        self.sync()

    def _step(self, offset):
        self.on_seek(self.playback.step(offset))
        self.sync()

    def _on_speed(self, event):
        self.playback.set_speed(float(self.speed.GetStringSelection()[:-1]))
        self.on_tick()
        self.sync()

    def _on_timer(self, event):
        if self.playback is not None:
            self.on_tick()
            self.sync()

    def _mouse_position(self, event):
        width, height = self.canvas.GetClientSize()
        render_width, render_height = self.canvas.GetRenderWindow().GetSize()
        return (
            event.GetX() * render_width / max(width, 1),
            (height - event.GetY()) * render_height / max(height, 1),
        )

    def _header_hit(self, event):
        x, y = self._mouse_position(event)
        renderer = self.view.GetRenderer()
        size = [0.0, 0.0]
        self.header.GetSize(renderer, size)
        right, top = self.header.GetPositionCoordinate().GetComputedDisplayValue(renderer)
        return (
            right - size[0] - 3 <= x <= right + 3
            and top - max(size[1], self.COLLAPSED_HEIGHT) <= y <= top + 3
        )

    def _seek_mouse(self, event):
        if self.playback is None or self._collapsed:
            return
        x, y = self._mouse_position(event)
        y += self.GRAPH_OFFSET_Y
        bottom = self.chart.GetAxis(vtkAxis.BOTTOM)
        left = self.chart.GetAxis(vtkAxis.LEFT)
        x1, x2 = bottom.GetPoint1()[0], bottom.GetPoint2()[0]
        y1, y2 = left.GetPoint1()[1], left.GetPoint2()[1]
        if x2 <= x1 or (not self._dragging and not (x1 <= x <= x2 and y1 <= y <= y2)):
            return
        if not self._dragging:
            self._dragging = True
            self.canvas.CaptureMouse()
        low, high = bottom.GetMinimum(), bottom.GetMaximum()
        time = low + (high - low) * (x - x1) / (x2 - x1)
        self.playback.pause()
        self.on_seek(self.playback.axis.index_at(time / self.time_scale))
        self.sync()

    def _on_press(self, event):
        self.canvas.SetFocus()
        if self._header_hit(event):
            self._on_fold(event)
        else:
            self._seek_mouse(event)

    def _on_motion(self, event):
        if self._dragging:
            self._seek_mouse(event)
        else:
            cursor = wx.CURSOR_HAND if self._header_hit(event) else wx.CURSOR_ARROW
            self.canvas.SetCursor(wx.Cursor(cursor))

    def _on_release(self, event):
        self._dragging = False
        if self.canvas.HasCapture():
            self.canvas.ReleaseMouse()

    def _on_fold(self, event):
        self._collapsed = not self._collapsed
        if self._collapsed and self.playback is not None:
            self.playback.pause()
            self.on_tick()
            self.sync()
        self._on_release(None)
        self.chart.SetVisible(not self._collapsed)
        self._footer_item.Show(not self._collapsed)
        self.canvas.SetMinSize(
            (
                100,
                self.COLLAPSED_HEIGHT
                if self._collapsed
                else self.GRAPH_HEIGHT + self.AXIS_LABEL_GAP,
            )
        )
        self.header.SetInput(("v " if self._collapsed else "^ ") + _("EEG/MEG time series"))
        action = _("Show time series (H)") if self._collapsed else _("Hide time series (H)")
        self.canvas.SetToolTip(action)
        self.InvalidateBestSize()
        self.body.Layout()
        self.Layout()
        self.GetParent().Layout()
        if self.canvas.IsShownOnScreen():
            self.canvas.Render()

    def _on_key(self, event):
        if event.GetKeyCode() in (ord("H"), ord("h")):
            self._on_fold(event)
        else:
            event.Skip()

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self.clear()
            self.canvas.GetRenderWindow().Finalize()
        event.Skip()
