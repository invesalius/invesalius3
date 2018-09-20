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

myEVT_SLIDER_CHANGED = wx.NewEventType()
EVT_SLIDER_CHANGED = wx.PyEventBinder(myEVT_SLIDER_CHANGED, 1)

myEVT_SLIDER_CHANGING = wx.NewEventType()
EVT_SLIDER_CHANGING = wx.PyEventBinder(myEVT_SLIDER_CHANGING, 1)

myEVT_THRESHOLD_CHANGED = wx.NewEventType()
EVT_THRESHOLD_CHANGED = wx.PyEventBinder(myEVT_THRESHOLD_CHANGED, 1)

myEVT_THRESHOLD_CHANGING = wx.NewEventType()
EVT_THRESHOLD_CHANGING = wx.PyEventBinder(myEVT_THRESHOLD_CHANGING, 1)

class SliderEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id, minRange, maxRange, minValue, maxValue):
        wx.PyCommandEvent.__init__(self, evtType, id,)
        self.min_range = minRange
        self.max_range = maxRange
        self.minimun = minValue
        self.maximun = maxValue

class GradientSlider(wx.Panel):
    # This widget is formed by a gradient background (black-white), two push
    # buttons change the min and max values respectively and a slider which you can drag to
    # change the both min and max values.
    def __init__(self, parent, id, minRange, maxRange, minValue, maxValue, colour):
        # minRange: the minimal value
        # maxrange: the maximum value
        # minValue: the least value in the range
        # maxValue: the most value in the range
        # colour: colour used in this widget.
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

        if sys.platform == 'win32':
            self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeaveWindow)

        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def OnLeaveWindow(self, evt):
        self.selected = 0
        evt.Skip()

        
    def OnPaint(self, evt):
        # Where the magic happens. Here the controls are drawn.
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

        # Drawing the left blank area.
        pen = wx.Pen((0, 0, 0))
        brush = wx.Brush((0, 0, 0))
        dc.SetPen(pen)
        dc.SetBrush(brush)
        dc.DrawRectangle(0, 0, PUSH_WIDTH, h)

        # Drawing the right blank area.
        pen = wx.Pen((255, 255, 255))
        brush = wx.Brush((255, 255, 255))
        dc.SetPen(pen)
        dc.SetBrush(brush)
        dc.DrawRectangle(x_init_gradient + width_gradient, 0, PUSH_WIDTH, h)

        # Drawing the gradient.
        dc.GradientFillLinear((x_init_gradient, y_init_gradient,
                               width_gradient, height_gradient),
                              (0, 0, 0), (255,255, 255))

        try:
            n = wx.RendererNative.Get()
        except AttributeError:
            n = wx.RendererNative_Get()

        # Drawing the push buttons
        n.DrawPushButton(self, dc, (x_init_push1, 0, PUSH_WIDTH, h))
        n.DrawPushButton(self, dc, (x_init_push2, 0, PUSH_WIDTH, h))

        # Drawing the transparent slider.
        bytes = numpy.array(self.colour * width_transparency * h, 'B')
        try:
            slider = wx.BitmapFromBufferRGBA(width_transparency, h, bytes)
        except:
            pass
        else:
            dc.DrawBitmap(slider, self.min_position, 0, True)

    def OnEraseBackGround(self, evt):
        # Only to avoid this widget to flick.
        pass

    def OnMotion(self, evt):
        x = evt.GetX()
        w, h = self.GetSize()

        # user is only moving the mouse, not changing the max our min values
        if not self.selected:
            # The user is over a push button, change the cursor.
            if self._is_over_what(x) in (1, 2):
                self.SetCursor(wx.StockCursor(wx.CURSOR_SIZEWE))
            else:
                self.SetCursor(wx.NullCursor)

        # The user is moving the first PUSH (Min)
        elif self.selected == 1:
            x -= self._delta
            if x - PUSH_WIDTH < 0:
                x = PUSH_WIDTH
            elif x >= self.max_position:
                x = self.max_position

            value = self._min_position_to_minimun(x)
            self.minimun = value
            self.min_position = x
            self._generate_event(myEVT_SLIDER_CHANGING)
            self.Refresh()
        
        # The user is moving the second push (Max)
        elif self.selected == 2:
            x -= self._delta
            if x + PUSH_WIDTH > w:
                x = w - PUSH_WIDTH
            elif x < self.min_position:
                x = self.min_position

            value = self._max_position_to_maximun(x)
            self.maximun = value
            self.max_position = x
            self._generate_event(myEVT_SLIDER_CHANGING)
            self.Refresh()

        # The user is moving the slide.
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

            self._generate_event(myEVT_SLIDER_CHANGING)
            self.Refresh()
        evt.Skip()


    def OnClick(self, evt):
        x = evt.GetX()
        self.selected = self._is_over_what(x)
        if self.selected == 1:
            self._delta = x - self.min_position
        elif self.selected == 2:
            self._delta = x - self.max_position
        elif self.selected == 3:
            self._delta = x - self.min_position
        evt.Skip()

    def OnRelease(self, evt):
        if self.selected:
            self.selected = 0
            self._generate_event(myEVT_SLIDER_CHANGED)
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

    def _is_over_what(self, position_x):
        # Test if the given position (x) is over some object. Return 1 to first
        # pus, 2 to second push, 3 to slide and 0 to nothing.
        if self.min_position - PUSH_WIDTH <= position_x <= self.min_position:
            return 1
        elif self.max_position <= position_x <= self.max_position + PUSH_WIDTH:
            return 2
        elif self.min_position <= position_x <= self.max_position:
            return 3
        else:
            return 0

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

    def GetMaxValue(self):
        return self.maximun

    def GetMinValue(self):
        return self.minimun

    def _generate_event(self, event):
        evt = SliderEvent(event, self.GetId(), self.min_range,
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
        self.colour = colour[:3]
        self.changed = False
        self._draw_controls()
        self._bind_events_wx()
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
        sizer.Add(self.spin_min, 0, wx.EXPAND | wx.RIGHT, 2)
        sizer.Add(self.gradient_slider, 1, wx.EXPAND)
        sizer.Add(self.spin_max, 0, wx.EXPAND | wx.LEFT, 2)
        self.sizer.Add(sizer, 1, wx.EXPAND)

    def _bind_events_wx(self):
        self.gradient_slider.Bind(EVT_SLIDER_CHANGING, self.OnSliding)
        self.gradient_slider.Bind(EVT_SLIDER_CHANGED, self.OnSlider)

        # self.spin_min.Bind(wx.lib.intctrl.EVT_INT, self.ChangeMinValue)
        self.spin_min.Bind(wx.EVT_LEAVE_WINDOW, self._FireSpinMinChange)
        self.spin_min.Bind(wx.EVT_KILL_FOCUS, self._FireSpinMinChange)
        #self.spin_min.Bind(wx.EVT_KEY_DOWN, self._FireSpinMinChange)
        self.spin_min.Bind(wx.EVT_MOUSEWHEEL, self.OnMinMouseWheel)

        # self.spin_max.Bind(wx.lib.intctrl.EVT_INT, self.ChangeMaxValue)
        self.spin_max.Bind(wx.EVT_LEAVE_WINDOW, self._FireSpinMaxChange)
        self.spin_max.Bind(wx.EVT_KILL_FOCUS, self._FireSpinMaxChange)
        #self.spin_max.Bind(wx.EVT_KEY_DOWN, self._FireSpinMaxChange)
        self.spin_max.Bind(wx.EVT_MOUSEWHEEL, self.OnMaxMouseWheel)

    def OnSlider(self, evt):
        self.spin_min.SetValue(evt.minimun)
        self.spin_max.SetValue(evt.maximun)
        self.minimun = evt.minimun
        self.maximun = evt.maximun
        self._GenerateEvent(myEVT_THRESHOLD_CHANGED)

    def OnSliding(self, evt):
        self.spin_min.SetValue(evt.minimun)
        self.spin_max.SetValue(evt.maximun)
        self.minimun = evt.minimun
        self.maximun = evt.maximun
        self._GenerateEvent(myEVT_THRESHOLD_CHANGING)

    def _FireSpinMinChange(self, evt):
        evt.Skip()
        value = int(self.spin_min.GetValue())
        if value < self.min_range or value > self.max_range:
            self.spin_min.SetValue(self.minimun)
            return

        if value != self.GetMinValue() or self.changed:
            self.SetMinValue(value)
            self._GenerateEvent(myEVT_THRESHOLD_CHANGED)

    def _FireSpinMinChanged(self, evt):
        if self.changed:
            self._GenerateEvent(myEVT_THRESHOLD_CHANGED)

    def _FireSpinMaxChange(self, evt):
        evt.Skip()
        value = int(self.spin_max.GetValue())
        if value < self.min_range or value > self.max_range:
            self.spin_max.SetValue(self.maximun)
            return

        if value != self.GetMaxValue() or self.changed:
            self.SetMaxValue(value)
            self._GenerateEvent(myEVT_THRESHOLD_CHANGED)

    def _FireSpinMaxChanged(self, evt):
        if self.changed:
            self._GenerateEvent(myEVT_THRESHOLD_CHANGED)

    def OnMinMouseWheel(self, e):
        """ 
        When the user wheel the mouse over min texbox
        """
        v = self.GetMinValue() + e.GetWheelRotation()/e.GetWheelDelta()
        self.SetMinValue(v)
        self._GenerateEvent(myEVT_THRESHOLD_CHANGING)

    def OnMaxMouseWheel(self, e):
        """ 
        When the user wheel the mouse over max texbox
        """
        v = self.GetMaxValue() + e.GetWheelRotation()/e.GetWheelDelta()
        self.SetMaxValue(v)
        self._GenerateEvent(myEVT_THRESHOLD_CHANGING)

    def SetColour(self, colour):
        colour = list(colour[:3]) + [90,]
        self.colour = colour
        self.gradient_slider.SetColour(colour)
        self.gradient_slider.Refresh()

    def SetMaxRange(self, value):
        self.spin_min.SetMax(value)
        self.spin_max.SetMax(value)
        self.gradient_slider.SetMaxRange(value)
        self.max_range = value
        if value > self.max_range:
            value = self.max_range

    def SetMinRange(self, value):
        self.spin_min.SetMin(value)
        self.spin_max.SetMin(value)
        self.gradient_slider.SetMinRange(value)
        self.min_range = value
        if value < self.min_range:
            value = self.min_range

    def SetMaxValue(self, value):
        if value is not None:
            value = int(value)
            if value > self.max_range:
                value = int(self.max_range)
            self.spin_max.SetValue(value)
            self.gradient_slider.SetMaximun(value)
            self.maximun = value

    def SetMinValue(self, value):
        if value is not None:
            value = int(value)
            if value < self.min_range:
                value = int(self.min_range)
            self.spin_min.SetValue(value)
            self.gradient_slider.SetMinimun(value)
            self.minimun = value

    def ChangeMinValue(self, e):
        # Why do I need to change slide min value if it has been changed for
        # the user?
        if not self.slided:
            self.gradient_slider.SetMinValue(int(self.spin_min.GetValue()))
            self._GenerateEvent(myEVT_THRESHOLD_CHANGE)

    def ChangeMaxValue(self, e):
        # Why do I need to change slide max value if it has been changed for
        # the user?
        if not self.slided:
            self.gradient_slider.SetMaxValue(int(self.spin_max.GetValue()))
            self._GenerateEvent(myEVT_THRESHOLD_CHANGE)

    def GetMaxValue(self):
        return self.maximun

    def GetMinValue(self):
        return self.minimun

    def _GenerateEvent(self, event):
        if event == myEVT_THRESHOLD_CHANGING:
            self.changed = True
        elif event == myEVT_THRESHOLD_CHANGED :
            self.changed = False

        evt = SliderEvent(event, self.GetId(), self.min_range,
                          self.max_range, self.minimun, self.maximun)
        self.GetEventHandler().ProcessEvent(evt)
