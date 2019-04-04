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
import decimal

import wx


class InvSpinCtrl(wx.Panel):
    def __init__(
        self,
        parent,
        id=wx.ID_ANY,
        value=0,
        min_value=1,
        max_value=100,
        size=wx.DefaultSize,
    ):
        super().__init__(parent, id, size=size)

        self._textctrl = wx.TextCtrl(self, -1)

        self._value = 0
        self._last_value = 0
        self._min_value = 0
        self._max_value = 100

        self.SetMin(min_value)
        self.SetMax(max_value)
        self.SetValue(value)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._textctrl, 1, wx.EXPAND)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.__bind_events()

    def __bind_events(self):
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self._textctrl.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)

    def SetMin(self, min_value):
        self._min_value = min_value
        self.SetValue(self._value)

    def SetMax(self, max_value):
        self._max_value = max_value
        self.SetValue(self._value)

    def SetRange(self, min_value, max_value):
        self.SetMin(min_value)
        self.SetMax(max_value)

    def GetValue(self):
        return self._value

    def SetValue(self, value):
        try:
            value = int(value)
        except ValueError:
            value = self._last_value

        if value < self._min_value:
            value = self._min_value

        if value > self._max_value:
            value = self._max_value

        self._value = value
        self._textctrl.SetValue("{}".format(self._value))
        self._last_value = self._value

    def CalcSizeFromTextSize(self, text=None):
        if text is None:
            text = "{}".format(len(str(self._max_value)) * "M")
        self.SetMinSize(
            self._textctrl.GetSizeFromTextSize(self._textctrl.GetTextExtent(text))
        )

    def OnMouseWheel(self, evt):
        r = evt.GetWheelRotation()
        if r > 0:
            self.SetValue(self.GetValue() + 1)
        else:
            self.SetValue(self.GetValue() - 1)
        self.raise_event()
        evt.Skip()

    def OnKillFocus(self, evt):
        value = self._textctrl.GetValue()
        self.SetValue(value)
        self.raise_event()
        evt.Skip()

    def raise_event(self):
        event = wx.PyCommandEvent(wx.EVT_SPINCTRL.typeId, self.GetId())
        self.GetEventHandler().ProcessEvent(event)


class InvFloatSpinCtrl(wx.Panel):
    def __init__(
        self,
        parent,
        id=wx.ID_ANY,
        value=0.0,
        min_value=1.0,
        max_value=100.0,
        increment=0.1,
        digits=1,
        size=wx.DefaultSize,
    ):
        super().__init__(parent, id, size=size)

        self._textctrl = wx.TextCtrl(self, -1)

        self._digits = digits
        self._dec_context = decimal.Context(prec=digits)

        self._value = decimal.Decimal('0', self._dec_context)
        self._last_value = self._value
        self._min_value = decimal.Decimal('0', self._dec_context)
        self._max_value = decimal.Decimal('100', self._dec_context)
        self._increment = decimal.Decimal('0.1', self._dec_context)

        self.SetIncrement(increment)
        self.SetMin(min_value)
        self.SetMax(max_value)
        self.SetValue(value)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._textctrl, 1, wx.EXPAND)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.__bind_events()

    def __bind_events(self):
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self._textctrl.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)

    def _to_decimal(self, value):
        if not isinstance(value, str):
            value = '{:.{digits}f}'.format(value, digits=self._digits)
        return decimal.Decimal(value, self._dec_context)

    def SetDigits(self, digits):
        self._digits = digits
        self._dec_context = decimal.Context(prec=digits)

        self.SetIncrement(self._increment)
        self.SetMin(self._min_value)
        self.SetMax(self._max_value)
        self.SetValue(self._value)

    def SetIncrement(self, increment):
        self._increment = self._to_decimal(increment)

    def SetMin(self, min_value):
        self._min_value = self._to_decimal(min_value)
        self.SetValue(self._value)

    def SetMax(self, max_value):
        self._max_value = self._to_decimal(max_value)
        self.SetValue(self._value)

    def SetRange(self, min_value, max_value):
        self.SetMin(min_value)
        self.SetMax(max_value)

    def GetValue(self):
        return float(self._value)

    def SetValue(self, value):
        try:
            value = self._to_decimal(value)
        except decimal.InvalidOperation:
            value = self._last_value

        if value < self._min_value:
            value = self._min_value

        if value > self._max_value:
            value = self._max_value

        self._value = value
        self._textctrl.SetValue("{}".format(self._value))
        self._last_value = self._value

    def CalcSizeFromTextSize(self, text=None):
        if text is None:
            text = "{}.{}".format(self._max_value, "M" * self._digits)
        self.SetMinSize(
            self._textctrl.GetSizeFromTextSize(self._textctrl.GetTextExtent(text))
        )

    def OnMouseWheel(self, evt):
        r = evt.GetWheelRotation()
        if r > 0:
            self.SetValue(self._value + self._increment)
        else:
            self.SetValue(self._value - self._increment)
        self.raise_event()
        evt.Skip()

    def OnKillFocus(self, evt):
        value = self._textctrl.GetValue()
        self.SetValue(value)
        self.raise_event()
        evt.Skip()

    def raise_event(self):
        event = wx.PyCommandEvent(wx.EVT_SPINCTRL.typeId, self.GetId())
        self.GetEventHandler().ProcessEvent(event)
