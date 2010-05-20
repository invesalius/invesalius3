#!/usr/bin/env python
# -*- coding: UTF-8 -*-

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
import sys

import numpy
import wx

from wx.lib import intctrl

PUSH_WIDTH = 7

myEVT_SLIDER_CHANGE = wx.NewEventType()
EVT_SLIDER_CHANGE = wx.PyEventBinder(myEVT_SLIDER_CHANGE, 1)

myEVT_THRESHOLD_CHANGE = wx.NewEventType()
EVT_THRESHOLD_CHANGE = wx.PyEventBinder(myEVT_THRESHOLD_CHANGE, 1)

class SliderEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id, minRange, maxRange, minValue, maxValue):
        wx.PyCommandEvent.__init__(self, evtType, id,)
        self.min_range = minRange
        self.max_range = maxRange
        self.minimun = minValue
        self.maximun = maxValue

class GradientSlider(wx.Panel):
    def __init__(self, parent, id, minRange, maxRange, minValue, maxValue, colour):
        super(GradientSlider, self).__init__(parent, id, size = (100, 25))
        self._bind_events_wx()

        self.min_range = minRange
        self.max_range = maxRange
        self.minimun = minValue
        self.maximun = maxValue
        self.colour = colour
        self.selected = 0

        self.CalculateControlPositions()

    def _bind_events_wx(self):
        self.Bind(wx.EVT_LEFT_DOWN, self.OnClick)
        self.Bind(wx.EVT_LEFT_UP, self.OnRelease)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackGround)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def OnPaint(self, evt):
        dc = wx.BufferedPaintDC(self)
        dc.Clear()
        
        w, h = self.GetSize()
        width_gradient = w - 2*PUSH_WIDTH
        height_gradient = h
        x_init_gradient = PUSH_WIDTH
        y_init_gradient = 0

        x_init_push1 = self.min_position - PUSH_WIDTH
        x_init_push2 = self.max_position

        width_transparency = self.max_position - self.min_position

        pen = wx.Pen((0, 0, 0))
        brush = wx.Brush((0, 0, 0))
        dc.SetPen(pen)
        dc.SetBrush(brush)
        dc.DrawRectangle(0, 0, PUSH_WIDTH, h)

        pen = wx.Pen((255, 255, 255))
        brush = wx.Brush((255, 255, 255))
        dc.SetPen(pen)
        dc.SetBrush(brush)
        dc.DrawRectangle(x_init_gradient + width_gradient, 0, PUSH_WIDTH, h)

        dc.GradientFillLinear((x_init_gradient, y_init_gradient,
                               width_gradient, height_gradient),
                              (0, 0, 0), (255,255, 255))
        
        n = wx.RendererNative_Get()
        n.DrawPushButton(self, dc, (x_init_push1, 0, PUSH_WIDTH, h))
        n.DrawPushButton(self, dc, (x_init_push2, 0, PUSH_WIDTH, h))

        bytes = numpy.array(self.colour * width_transparency * h, 'B')
        try:
            slider = wx.BitmapFromBufferRGBA(width_transparency, h, bytes)
        except:
            pass
        else:
            dc.DrawBitmap(slider, self.min_position, 0, True)

    def OnEraseBackGround(self, evt):
        pass

    def OnMotion(self, evt):
        x = evt.GetX()
        w, h = self.GetSize()
        if self.selected == 1:
            x -= self._delta
            if x - PUSH_WIDTH < 0:
                x = PUSH_WIDTH
            elif x >= self.max_position:
                x = self.max_position

            value = self._min_position_to_minimun(x)
            self.minimun = value
            self.min_position = x
            self.Refresh()
            self._generate_event()
        
        elif self.selected == 2:
            x -= self._delta
            if x + PUSH_WIDTH > w:
                x = w - PUSH_WIDTH
            elif x < self.min_position:
                x = self.min_position

            value = self._max_position_to_maximun(x)
            self.maximun = value
            self.max_position = x
            self.Refresh()
            self._generate_event()

        elif self.selected == 3:
            x -= self._delta
            slider_size = self.max_position - self.min_position
            diff_values = self.maximun - self.minimun
            
            if x - PUSH_WIDTH < 0:
                min_x = PUSH_WIDTH
                self.minimun = self._min_position_to_minimun(min_x)
                self.maximun = self.minimun + diff_values
                self.CalculateControlPositions()
            
            elif x + slider_size + PUSH_WIDTH > w:
                max_x = w - PUSH_WIDTH
                self.maximun = self._max_position_to_maximun(max_x)
                self.minimun = self.maximun - diff_values
                self.CalculateControlPositions()

            else:
                min_x = x
                self.minimun = self._min_position_to_minimun(min_x)
                self.maximun = self.minimun + diff_values
                self.CalculateControlPositions()

            self.Refresh()
            self._generate_event()
        evt.Skip()


    def OnClick(self, evt):
        x = evt.GetX()
        if self.min_position - PUSH_WIDTH <= x <= self.min_position:
            self.selected = 1
            self._delta = x - self.min_position
        elif self.max_position <= x <= self.max_position + PUSH_WIDTH:
            self.selected = 2
            self._delta = x - self.max_position
        elif self.min_position <= x <= self.max_position:
            self.selected = 3
            self._delta = x - self.min_position
        evt.Skip()

    def OnRelease(self, evt):
        self.selected = 0
        evt.Skip()

    def OnSize(self, evt):
        self.CalculateControlPositions()
        self.Refresh()
        evt.Skip()

    def CalculateControlPositions(self):
        """
        Calculates the Min and Max control position based on the size of this
        widget.
        """
        w, h = self.GetSize()
        window_width = w - 2*PUSH_WIDTH
        proportion = window_width / float(self.max_range - self.min_range)

        self.min_position = int(round((self.minimun - self.min_range) * \
                                      proportion)) + PUSH_WIDTH
        self.max_position = int(round((self.maximun - self.min_range) * \
                                      proportion)) + PUSH_WIDTH
        print self.min_position, self.max_position

    def _max_position_to_maximun(self, max_position):
        """ 
        Calculates the min and max value based on the control positions.
        """
        w, h = self.GetSize()
        window_width = w - 2*PUSH_WIDTH
        proportion = window_width / float(self.max_range - self.min_range)

        maximun = int(round((max_position - PUSH_WIDTH)/proportion + \
                self.min_range))

        return maximun

    def _min_position_to_minimun(self, min_position):
        w, h = self.GetSize()
        window_width = w - 2*PUSH_WIDTH
        proportion = window_width / float(self.max_range - self.min_range)

        minimun = int(round((min_position - PUSH_WIDTH)/proportion + \
                self.min_range))

        return minimun

    def SetColour(self, colour):
        self.colour = colour

    def SetMinRange(self, min_range):
        self.min_range = min_range
        self.CalculateControlPositions()
        self.Refresh()

    def SetMaxRange(self, max_range):
        self.max_range = max_range
        self.CalculateControlPositions()
        self.Refresh()

    def SetMinimun(self, minimun):
        self.minimun = minimun
        self.CalculateControlPositions()
        self.Refresh()

    def SetMaximun(self, maximun):
        self.maximun = maximun
        self.CalculateControlPositions()
        self.Refresh()

    def _generate_event(self):
        evt = SliderEvent(myEVT_SLIDER_CHANGE, self.GetId(), self.min_range,
                          self.max_range, self.minimun, self.maximun)
        self.GetEventHandler().ProcessEvent(evt)


class GradientCtrl(wx.Panel):
    def __init__(self, parent, id, minRange, maxRange, minValue, maxValue, colour):
        super(GradientCtrl, self).__init__(parent, id)
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.SetAutoLayout(1)
        self.min_range = minRange
        self.max_range = maxRange
        self.minimun = minValue
        self.maximun = maxValue
        self.colour = colour
        self._draw_controls()
        self._bind_events_wx()
        self.SetBackgroundColour((0, 255, 0))
        self.Show()

    def _draw_controls(self):
        self.gradient_slider = GradientSlider(self, -1, self.min_range,
                                              self.max_range, self.minimun,
                                              self.maximun, self.colour)

        self.spin_min = intctrl.IntCtrl(self, size=(40,20), 
                                        style=wx.TE_PROCESS_ENTER)
        self.spin_min.SetValue(self.minimun)
        if sys.platform != 'win32':
            self.spin_min.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        self.spin_max = intctrl.IntCtrl(self, size=(40,20), 
                                        style=wx.TE_PROCESS_ENTER)
        self.spin_max.SetValue(self.maximun)
        if sys.platform != 'win32':
            self.spin_max.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.spin_min, 0, wx.EXPAND)
        sizer.Add(self.gradient_slider, 1, wx.EXPAND)
        sizer.Add(self.spin_max, 0, wx.EXPAND)
        self.sizer.Add(sizer, 1, wx.EXPAND)

    def _bind_events_wx(self):
        self.gradient_slider.Bind(EVT_SLIDER_CHANGE, self.OnSlider)

        # self.spin_min.Bind(wx.lib.intctrl.EVT_INT, self.ChangeMinValue)
        self.spin_min.Bind(wx.EVT_KILL_FOCUS, self._FireSpinMinChange)
        self.spin_min.Bind(wx.EVT_TEXT_ENTER, self._FireSpinMinChange)
        self.spin_min.Bind(wx.EVT_MOUSEWHEEL, self.OnMinMouseWheel)

        # self.spin_max.Bind(wx.lib.intctrl.EVT_INT, self.ChangeMaxValue)
        self.spin_max.Bind(wx.EVT_KILL_FOCUS, self._FireSpinMaxChange)
        self.spin_max.Bind(wx.EVT_TEXT_ENTER, self._FireSpinMaxChange)
        self.spin_max.Bind(wx.EVT_MOUSEWHEEL, self.OnMaxMouseWheel)

    def OnSlider(self, evt):
        self.spin_min.SetValue(evt.minimun)
        self.spin_max.SetValue(evt.maximun)
        self.minimun = evt.minimun
        self.maximun = evt.maximun
        self._GenerateEvent()

    def _FireSpinMinChange(self, evt):
        value = int(self.spin_min.GetValue())
        if value != self.GetMinValue():
            self.gradient_slider.SetMinimun(value)
            self.minimun = value
            self._GenerateEvent()

    def _FireSpinMaxChange(self, evt):
        value = int(self.spin_max.GetValue())
        if value != self.GetMaxValue():
            self.gradient_slider.SetMaximun(value)
            self.maximun = value
            self._GenerateEvent()

    def OnMinMouseWheel(self, e):
        v = self.GetMinValue() + e.GetWheelRotation()/e.GetWheelDelta()
        self.SetMinValue(v)

    def OnMaxMouseWheel(self, e):
        v = self.GetMaxValue() + e.GetWheelRotation()/e.GetWheelDelta()
        self.SetMaxValue(v)

    def SetColour(self, colour):
        colour = colour + [90,]
        self.colour = colour
        self.gradient_slider.SetColour(colour)
        self.gradient_slider.Refresh()

    def SetMaxRange(self, value):
        self.spin_min.SetMax(value)
        self.spin_max.SetMax(value)
        self.gradient_slider.SetMaxRange(value)

    def SetMinRange(self, value):
        self.spin_min.SetMin(value)
        self.spin_max.SetMin(value)
        self.gradient_slider.SetMinRange(value)

    def SetMaxValue(self, value):
        value = int(value)
        self.spin_max.SetValue(value)
        self.gradient_slider.SetMaximun(value)
        self.maximun = value

    def SetMinValue(self, value):
        value = int(value)
        self.spin_min.SetValue(value)
        self.gradient_slider.SetMinimun(value)
        self.minimun = value

    def ChangeMinValue(self, e):
        # Why do I need to change slide min value if it has been changed for
        # the user?
        print "ChangeMinValue", self.slided
        if not self.slided:
            self.gradient_slider.SetMinValue(int(self.spin_min.GetValue()))
            self._GenerateEvent()

    def ChangeMaxValue(self, e):
        # Why do I need to change slide min value if it has been changed for
        # the user?
        if not self.slided:
            self.gradient_slider.SetMaxValue(int(self.spin_max.GetValue()))
            self._GenerateEvent()

    def GetMaxValue(self):
        return self.maximun

    def GetMinValue(self):
        return self.minimun

    def _GenerateEvent(self):
        evt = SliderEvent(myEVT_THRESHOLD_CHANGE, self.GetId(), self.min_range,
                          self.max_range, self.minimun, self.maximun)
        self.GetEventHandler().ProcessEvent(evt)
