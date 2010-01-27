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

import array
import sys

import numpy
import vtk
import wx
import wx.lib.intctrl
import wx.lib.pubsub as ps

MINBORDER=1
MAXBORDER=2

class SliderData(object):
    def __init__(self, minRange, maxRange, minValue, maxValue, colour):
        """
        minRange: The minimum value accepted.
        maxRange: The maximum value accepted.
        minValue: initial minimum value.
        maxValue: initial maximum value.
        colour: the colour associated, must be in RGBA form.
        """
        self.minRange = minRange
        self.maxRange = maxRange
        self.minValue = minValue
        self.maxValue = maxValue
        self.colour = colour
        self.wasChanged = True

    def GetMinValue(self):
        return self.minValue

    def GetMaxValue(self):
        return self.maxValue

    def SetMinValue(self, value):
        if value < self.minRange:
            value = self.minRange
        self.minValue = value
        self.wasChanged = True

    def SetMaxValue(self, value):
        if value > self.maxRange:
            value = self.maxRange
        self.maxValue = value
        self.wasChanged = True

    def GetMinRange(self):
        return self.minRange

    def GetMaxRange(self):
        return self.maxRange

    def SetMinRange(self, value):
        if value < self.minValue:
            self.SetMinValue(value)
        self.minRange = value
        self.wasChanged = True

    def SetMaxRange(self, value):
        if value > self.maxValue:
            self.SetMaxValue(value)
        self.maxRange = value
        self.wasChanged = True

    def GetColour(self):
        return self.colour

    def SetColour(self, colour):
        self.colour = colour
        self.wasChanged = True

    def GetRange(self):
        return self.maxRange - self.minRange


class SliderControler(object):
    def __init__(self, slider):
        self.slider = slider
        ps.Publisher().subscribe(self.SetMinValue, "ChangeMinValue")
        ps.Publisher().subscribe(self.SetMaxValue, "ChangeMaxValue")

    def SetMinValue(self, data):
        self.slider.SetMinValue(data.data)

    def SetMaxValue(self, data):
        self.slider.SetMaxValue(data.data)

    def GetMinValue(self):
        return self.slider.GetMinValue()

    def GetMaxValue(self):
        return self.slider.GetMaxValue()


class SliderBorder(object):
    def __init__(self, pos, width, WindowWidth, type):
        """
        pos: initial border's position
        width: border's width
        """
        self.pos = pos
        self.width = width
        self.WindowWidth = WindowWidth
        self.type = type

    def IsOver(self, x):
        """
        Is the mouse over border?
        """
        return self.pos <= x <= self.pos + self.width

    def DoSlide(self, slide):
        """
        Move the border
        """
        self.pos += slide
        if self.type == MINBORDER and self.pos < 0:
            self.pos = 0
        elif self.type == MAXBORDER and self.pos+self.width >= self.WindowWidth:
           self.pos = self.WindowWidth - self.width

    def SetPosition(self, pos):
        """
        Move the border
        """
        self.pos = pos
        if self.type == MINBORDER and self.pos < 0:
            self.pos = 0
        elif self.type == MAXBORDER and self.pos+self.width >= self.WindowWidth:
           self.pos = self.WindowWidth - self.width

    def GetCursor(self):
        """
        This function returns the cursor related to the SliderBorder
        """
        return wx.StockCursor(wx.CURSOR_SIZEWE)

    def SetWindowWidth(self, width):
        self.WindowWith = width

    def GetPosition(self):
        return self.pos


class SliderControl(object):
    def __init__(self, sliderData, width, height):
        """
        sliderData: associated sliderData, where the info is.
        width: SliderControl's width
        height: SliderControl's height
        """
        self.width = width
        self.height = height
        self.imgSlider = None
        self.SliderData = sliderData
        self.ToResize = False
        ps.Publisher().subscribe(self.SetMinValue, "SetMinValue")

    def Resize(self, WindowWidth, WindowHeight):
        """
        Occurs when parent panel resizes, then the slider resize too keeping the
        proportion
        """
        self.WindowWidth = WindowWidth
        self.MinBorder.SetWindowWidth(WindowWidth)
        self.MaxBorder.SetWindowWidth(WindowWidth)
        proportion = WindowWidth/float(self.SliderData.GetRange())
        self.MinPoint = int(round((self.SliderData.GetMinValue() -\
                                   self.SliderData.minRange) * proportion))
        self.MaxPoint = int(round((self.SliderData.GetMaxValue() -\
                                   self.SliderData.minRange)* proportion))
        self.width = self.MaxPoint - self.MinPoint
        self.height = WindowHeight
        self.ToResize = True

    def GetSliderControl(self):
        """
        Returns the slider control
        """
        if not self.imgSlider or self.ToResize or self.SliderData.wasChanged:
            bytes = numpy.array(self.SliderData.GetColour() * self.width * self.height, 'B')
            self.imgSlider = wx.BitmapFromBufferRGBA(self.width, self.height, bytes)
            self.ToResize = False
            self.SliderData.wasChanged = False
        return self.imgSlider

    def GetCursor(self):
        """
        Returns the slider associated to the SliderControl
        """
        return wx.StockCursor(wx.CURSOR_ARROW)

    def DoSlide(self, slide):
        """
        Moves the SliderControl with associated borders
        """
        if slide + self.MinPoint >= 0 \
           and slide + self.MaxPoint <= self.WindowWidth:
            self.MinPoint += slide
            self.MaxPoint = self.MinPoint + self.width
            self.SetMinValueByMinPoint()
            self.SetMaxValueByMaxPoint()
            self.MinBorder.DoSlide(slide)
            self.MaxBorder.DoSlide(slide)

    def IsOver(self, x):
        """
        The mouse cursor is over me?
        """
        return self.MinPoint <= x <= self.MaxPoint

    def SetMinValueByMinPoint(self):
        """
        Sets the minimum slider value based on the min point position
        """
        proportion = self.WindowWidth/float(self.SliderData.GetRange())
        self.SliderData.SetMinValue(int(round(self.MinPoint/proportion +\
                                    self.SliderData.minRange)))

    def SetMaxValueByMaxPoint(self):
        """
        Sets the maximum slider values based on the max point position
        """
        proportion = self.WindowWidth/float(self.SliderData.GetRange())
        self.SliderData.SetMaxValue(int(round(self.MaxPoint/proportion +\
                                             self.SliderData.minRange)))

    def SetMaxPointByMaxValue(self):
        proportion = self.WindowWidth/float(self.SliderData.GetRange())
        #self.SetMaxPoint(int((self.SliderData.GetMaxValue() \
        #                     -self.SliderData.minRange)*proportion))
        self.MaxBorder.pos = self.MaxPoint

    def SetMinPointByMinValue(self):
        proportion = self.WindowWidth/float(self.SliderData.GetRange())
        #self.SetMinPoint(int((self.SliderData.GetMinValue() \
        #                      -self.SliderData.minRange)*proportion))
        self.MinBorder.pos = self.MinPoint

    def SetMinPoint(self, x):
        """
        Sets the min point position in pixels
        """
        self.MinPoint = x
        self.width = self.MaxPoint - self.MinPoint
        self.SetMinValueByMinPoint()
        self.ToResize = True

    def SetMaxPoint(self, x):
        """
        Sets the max point position in pixels
        """
        self.MaxPoint = x
        self.width = self.MaxPoint - self.MinPoint
        self.SetMaxValueByMaxPoint()
        self.ToResize = True

    def SetMinValue(self, min):
        self.SliderData.SetMinValue(min)
        proportion = self.WindowWidth/float(self.SliderData.GetRange())
        self.MinPoint = int(round((min - self.SliderData.minRange) * proportion))
        self.width = self.MaxPoint - self.MinPoint
        self.ToResize = True
        self.MinBorder.pos = self.MinPoint

    def SetMaxValue(self, max):
        self.SliderData.SetMaxValue(max)
        proportion = self.WindowWidth/float(self.SliderData.GetRange())
        self.MaxPoint = int(round((max - self.SliderData.minRange) * proportion))
        self.width = self.MaxPoint - self.MinPoint
        self.ToResize = True
        self.MaxBorder.pos = self.MaxPoint - self.MaxBorder.width

    def SetMinBorder(self, border):
        """
        Hello, I'm the min border. I do the hard work to squeeze and stretch
        the slider body together with my brother max border.
        """
        self.MinBorder = border

    def SetMaxBorder(self, border):
        """
        And I'm the max border. I do the same work of my brother, I'm in the
        right side, while he is in left side.
        """
        self.MaxBorder = border

    def Calculate(self, object):
        """
        Calculate the new min or max point based on the border brothers position.
        """
        if object is self.MinBorder:
            self.SetMinPoint(object.pos)
        elif object is self.MaxBorder:
            self.SetMaxPoint(object.pos)


class GradientPanel(wx.Panel):
    def __init__(self, parent, id, sliderData):
        super(GradientPanel, self).__init__(parent, id, size=wx.Size(200,50))
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.SetMinSize((100, 20))
        self.imgGradient = None
        self.SliderData = sliderData
        self.Slider = SliderControl(self.SliderData, 1, 1)
        self.BorderMin = SliderBorder(self.SliderData.GetMinValue(), 7,
                                      self.GetSize().GetWidth(),
                                      MINBORDER)
        self.BorderMax = SliderBorder(self.SliderData.GetMaxValue()-10, 7,
                                      self.GetSize().GetWidth(),
                                      MAXBORDER)
        self.Slider.SetMinBorder(self.BorderMin)
        self.Slider.SetMaxBorder(self.BorderMax)
        self._DoBinds()
        self.Show()

    def _DoBinds(self):
        self.Bind(wx.EVT_LEFT_DOWN, self.OnClick)
        self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackGround)
        self.Bind(wx.EVT_MOTION, self.OnMotion)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)

    def GetMin(self):
        return self.SliderData.GetMinValue()

    def GetMax(self):
        return self.SliderData.GetMaxValue()

    def SetMinValue(self, min):
        self.Slider.SetMinValue(min)
        self.Refresh()

    def SetMaxValue(self, max):
        self.Slider.SetMaxValue(max)
        self.Refresh()

    def GetObjectAt(self, x):
        """
        Is there a object(border or slider) at this x position? Then return it
        to me.
        """
        if self.BorderMin.IsOver(x):
            return self.BorderMin
        elif self.BorderMax.IsOver(x):
            return self.BorderMax
        elif self.Slider.IsOver(x):
            return self.Slider
        else:
            return None

    def DrawSliderControl(self, dc):
        try:
            dc.DrawBitmap(self.Slider.GetSliderControl(),
                          self.Slider.MinPoint, 0, True)
        except (ValueError, RuntimeError):
            print "ERROR"

    def DrawSliderBorders(self, dc):
        n = wx.RendererNative_Get()
        n.DrawPushButton(self, dc, (self.BorderMin.pos, 0,
                                    self.BorderMin.width,
                                    self.Slider.height))
        n.DrawPushButton(self, dc, (self.BorderMax.pos, 0,
                                    self.BorderMax.width,
                                    self.Slider.height))

    def OnPaint(self, e):
        """
        Occurs when panel must be refreshed, it redraw the sliderControl and
        borders.
        """
        dc = wx.BufferedPaintDC(self)
        dc.Clear()
        w,h = self.GetSize()
        dc.GradientFillLinear((0, 0, w, h), (0, 0, 0), (255, 255, 255))
        self.DrawSliderControl(dc)
        self.DrawSliderBorders(dc)

    def OnEraseBackGround(self, e):
        pass

    def OnSize(self, e):
        """
        OMG! Incredible how I fatten and become thin easily, then I must adjust my
        clothes(SliderControl and the borders).
        """
        w,h = self.GetSize()
        if w > 0:
            self.Slider.Resize(w, h)
            self.BorderMin.pos = self.Slider.MinPoint
            self.BorderMax.pos = self.Slider.MaxPoint - self.BorderMax.width
            self.Refresh()
        e.Skip()

    def OnClick(self, e):
        """
        Occurs when the user click in the panel. It verifies if the click was
        over an object and memorise the mouse position to do the slide.
        """
        self.SelectedObject = self.GetObjectAt(e.GetX())
        self.MousePositionX = e.GetX()

    def OnLeftUp(self, e):
        """
        Occurs when left mouse button is freed then the selected object must be
        freed too.
        """
        self.SelectedObject = None

    def OnMotion(self, e):
        """
        This is where the slide occurs ...
        """
        x = e.GetX()
        # but the user must be dragging a selected object
        if e.Dragging() and self.SelectedObject:
            slide = x - self.MousePositionX
            self.MousePositionX += slide
            self.SetCursor(self.SelectedObject.GetCursor())
            if isinstance(self.SelectedObject, SliderControl):
                self.SelectedObject.DoSlide(slide)
            else:
                self.SelectedObject.SetPosition(x)
            self.Slider.Calculate(self.SelectedObject)
            if self.GetMin() >= self.GetMax():
                self.SetMinValue(self.GetMax()-1)
                self.Slider.SetMinPointByMinValue()
            dc = wx.ClientDC(self)
            evt = SliderEvent(myEVT_SLIDER_CHANGE, self.GetId())
            self.GetEventHandler().ProcessEvent(evt)
            self.Refresh()
        # else only the mouse cursor must be changed based on the object the
        # mouse is over
        else:
            try:
                self.SetCursor(self.GetObjectAt(x).GetCursor())
            except AttributeError:
                self.SetCursor(wx.NullCursor)

    def OnMouseWheel(self, e):
        v = e.GetWheelRotation()/e.GetWheelDelta()
        self.SliderData.SetMinValue(self.SliderData.GetMinValue()+v)
        self.SliderData.SetMaxValue(self.SliderData.GetMaxValue()+v)
        evt = SliderEvent(myEVT_SLIDER_CHANGE, self.GetId())
        self.GetEventHandler().ProcessEvent(evt)
        self.Refresh()


class GradientSlider(wx.Panel):
    def __init__(self, parent, id, minRange, maxRange, min, max, colour):
        super(GradientSlider, self).__init__(parent, id)
        self.slided = 0
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.SetAutoLayout(1)
        self.SliderData = SliderData(minRange, maxRange, min, max, colour)
        self.transparency = colour[3]
        self.DrawControls()
        #ps.Publisher().subscribe(self.SetMinValue, ('SetMinValue'))
        self.Show()
        self.__bind_events()

    def __bind_events(self):
        ps.Publisher().subscribe(self.SetColour, 'Change Gradient Colour')
        ps.Publisher().subscribe(self.SetMinValue, 'Change Gradient MinValue')
        ps.Publisher().subscribe(self.SetMaxValue, 'Change Gradient MaxValue')

    def DrawControls(self):
        """self.SpinMin = wx.SpinCtrl(parent=self,
                                   id=-1,
                                   initial=self.SliderData.minValue,
                                   min=self.SliderData.minRange,
                                   max=self.SliderData.maxRange,
                                   size=wx.Size(55,15))
        self.SpinMin.SetValue(self.SliderData.minValue) # needed in MacOS 10.5.5

        for child in self.SpinMin.GetChildren():
           if isinstance(child, wx.TextCtrl):
               child.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        self.SpinMax = wx.SpinCtrl(parent=self,
                                   id=-1,
                                   initial=self.SliderData.maxValue,
                                   min=self.SliderData.minRange,
                                   max=self.SliderData.maxRange,
                                   size=wx.Size(55,15))
        self.SpinMax.SetValue(self.SliderData.maxValue) # needed in MacOS 10.5.5

        for child in self.SpinMax.GetChildren():
           if isinstance(child, wx.TextCtrl):
               child.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)"""


        self.SpinMin = wx.lib.intctrl.IntCtrl(self, size=(40,20))
        #self.SpinMin.SetLimited(True)
        self.SpinMin.SetBounds(self.SliderData.minRange, self.SliderData.maxRange)
        if sys.platform != 'win32':
            self.SpinMin.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.SpinMin.SetValue(self.SliderData.minRange)

        self.SpinMax = wx.lib.intctrl.IntCtrl(self, size=(40,20))
        #self.SpinMax.SetLimited(True)
        self.SpinMax.SetBounds(self.SliderData.minRange, self.SliderData.maxRange)
        if sys.platform != 'win32':
            self.SpinMax.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        self.SpinMax.SetValue(self.SliderData.maxRange)

        self.GradientPanel = GradientPanel(self, -1, self.SliderData)
        self.sizer.Add(self.SpinMin, 0, wx.CENTRE)#, wx.EXPAND)
        self.sizer.AddSpacer(5)
        self.sizer.Add(self.GradientPanel, 2, wx.CENTRE)#, wx.EXPAND)
        self.sizer.AddSpacer(5)
        self.sizer.Add(self.SpinMax, 0, wx.CENTRE)#, wx.EXPAND)
        self._DoBinds()

    def _DoBinds(self):
        self.SpinMin.Bind(wx.lib.intctrl.EVT_INT, self.ChangeMinValue)
        self.SpinMax.Bind(wx.lib.intctrl.EVT_INT, self.ChangeMaxValue)
        # Scroll over the min and max field
        self.SpinMax.Bind(wx.EVT_MOUSEWHEEL, self.OnMaxMouseWheel)
        self.SpinMin.Bind(wx.EVT_MOUSEWHEEL, self.OnMinMouseWheel)
        self.Bind(EVT_SLIDER_CHANGE, self.OnSlider, self.GradientPanel)

    def OnMinMouseWheel(self, e):
        v = self.GetMinValue() + e.GetWheelRotation()/e.GetWheelDelta()
        self.SetMinValue(v)

    def OnMaxMouseWheel(self, e):
        v = self.GetMaxValue() + e.GetWheelRotation()/e.GetWheelDelta()
        self.SetMaxValue(v)

    def ChangeMinValue(self, e):
        # Why do I need to change slide min value if it has been changed for
        # the user?

        if not self.slided:
            self.GradientPanel.SetMinValue(int(self.SpinMin.GetValue()))
            self._GenerateEvent()

    def ChangeMaxValue(self, e):
        # Why do I need to change slide min value if it has been changed for
        # the user?
        if not self.slided:
            self.GradientPanel.SetMaxValue(int(self.SpinMax.GetValue()))
            self._GenerateEvent()

    def OnSlider(self, e):
        self.slided = 1
        self.SpinMin.SetValue(int(self.SliderData.GetMinValue()))
        self.SpinMax.SetValue(int(self.SliderData.GetMaxValue()))
        self.slided = 0
        self._GenerateEvent()

    def SetMinValue(self, value):
        try:
            value = value.data
        except AttributeError:
            pass
        self.GradientPanel.SetMinValue(value)
        self.SpinMin.SetValue(int(value))
        self.GradientPanel.Refresh()

    def SetMaxValue(self, value):
        try:
            value = value.data
        except AttributeError:
            pass
        self.GradientPanel.SetMaxValue(value)
        self.SpinMax.SetValue(int(value))
        self.GradientPanel.Refresh()

    def SetMaxRange(self, value):
        print "Setting max range ", value
        self.SliderData.SetMaxRange(value)
        self.SpinMin.SetMax(value)
        self.SpinMax.SetMax(value)
        self.GradientPanel.Refresh()

    def SetMinRange(self, value):
        self.SliderData.SetMinRange(value)
        self.SpinMin.SetMin(value)
        self.SpinMax.SetMin(value)
        self.GradientPanel.Refresh()

    def GetMaxValue(self):
        return self.SliderData.GetMaxValue()

    def GetMinValue(self):
        return self.SliderData.GetMinValue()

    def GetSliderData(self):
        """
        Returns the associated SliderData.
        """
        return self.SliderData

    def SetColour(self, colour, transparency=None):
        """
        Set colour of the slider, the colour must be in RGB format.
        And values varying 0-255.
        """
        if transparency is not None:
            A = transparency
        else:
            A = self.transparency
        (R,G,B) = colour
        self.SliderData.SetColour((R,G,B,A))
        self.GradientPanel.Refresh()

    def _GenerateEvent(self):
        evt = SliderEvent(myEVT_THRESHOLD_CHANGE, self.GetId())
        self.GetEventHandler().ProcessEvent(evt)

class SliderEvent(wx.PyCommandEvent):
    def __init__(self , evtType, id):
        wx.PyCommandEvent.__init__(self, evtType, id)

myEVT_SLIDER_CHANGE = wx.NewEventType()
# This event occurs when the user do slide, used only internaly
EVT_SLIDER_CHANGE = wx.PyEventBinder(myEVT_SLIDER_CHANGE, 1)

myEVT_THRESHOLD_CHANGE = wx.NewEventType()
# This event occurs when the user change the threshold.
EVT_THRESHOLD_CHANGE = wx.PyEventBinder(myEVT_THRESHOLD_CHANGE, 1)
