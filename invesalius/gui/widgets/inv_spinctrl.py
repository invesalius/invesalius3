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
from typing import Any, Optional, Union

import wx


class InvSpinCtrl(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        id: int = wx.ID_ANY,
        value: int = 0,
        min_value: int = 1,
        max_value: int = 100,
        increment: int = 1,
        spin_button: bool = True,
        unit: str = "",
        size: wx.Size = wx.DefaultSize,
        style: int = wx.TE_RIGHT,
    ):
        super().__init__(parent, id, size=size)

        self._textctrl = wx.TextCtrl(self, -1, style=style)
        if spin_button and wx.Platform != "__WXGTK__":
            self._spinbtn: Optional[wx.SpinButton] = wx.SpinButton(self, -1)
        else:
            self._spinbtn = None

        self._value = 0
        self._last_value = 0
        self._min_value = 0
        self._max_value = 100
        self._increment = 1

        self.unit = unit

        self.SetMin(min_value)
        self.SetMax(max_value)
        self.SetValue(value)
        self.SetIncrement(increment)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._textctrl, 1, wx.EXPAND)
        if self._spinbtn:
            sizer.Add(self._spinbtn, 0, wx.EXPAND)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.__bind_events()

    def __bind_events(self) -> None:
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self._textctrl.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        if self._spinbtn:
            self._spinbtn.Bind(wx.EVT_SPIN_UP, self.OnSpinUp)
            self._spinbtn.Bind(wx.EVT_SPIN_DOWN, self.OnSpinDown)

    def SetIncrement(self, increment: int) -> None:
        self._increment = increment

    def SetMin(self, min_value: int) -> None:
        self._min_value = min_value
        self.SetValue(self._value)
        self.CalcSizeFromTextSize()

    def SetMax(self, max_value: int) -> None:
        self._max_value = max_value
        self.SetValue(self._value)
        self.CalcSizeFromTextSize()

    def SetRange(self, min_value: int, max_value: int) -> None:
        self.SetMin(min_value)
        self.SetMax(max_value)

    def GetValue(self) -> int:
        return self._value

    def SetValue(self, value: Union[float, str]) -> None:
        try:
            value = int(value)
        except ValueError:
            value = self._last_value

        if value < self._min_value:
            value = self._min_value

        if value > self._max_value:
            value = self._max_value

        self._value = value
        self._textctrl.SetValue(f"{self._value} {self.unit}")
        self._last_value = self._value

    def GetUnit(self) -> str:
        return self.unit

    def SetUnit(self, unit: str) -> None:
        self.unit = unit
        self.SetValue(self.GetValue())

    def CalcSizeFromTextSize(self, text: Optional[str] = None) -> None:
        # To calculate best width to spinctrl
        if text is None:
            text = "{}".format(max(len(str(self._max_value)), len(str(self._min_value)), 5) * "M")

        dc = wx.WindowDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(text)

        if self._spinbtn:
            spin = wx.SpinCtrl(self, -1)
            spin_width, spin_height = spin.GetBestSize()
            spin.Destroy()

            spinb = wx.SpinButton(self, -1)
            spinb_width, spinb_height = spinb.GetBestSize()
            spinb.Destroy()

            width += spinb_width
            if wx.Platform == "__WXMAC":
                height = max(height, spin_height, spinb_height)
            else:
                height = spin_height
        else:
            height = -1

        self.SetMinSize((width, height))
        self.Layout()

    def OnMouseWheel(self, evt: wx.MouseEvent) -> None:
        r = evt.GetWheelRotation()
        if r > 0:
            self.SetValue(self.GetValue() + self._increment)
        else:
            self.SetValue(self.GetValue() - self._increment)
        self.raise_event()
        evt.Skip()

    def OnKillFocus(self, evt: wx.FocusEvent) -> None:
        value = self._textctrl.GetValue()
        self.SetValue(value)
        self.raise_event()
        evt.Skip()

    def OnSpinDown(self, evt: wx.SpinEvent) -> None:
        self.SetValue(self.GetValue() - self._increment)
        self.raise_event()
        evt.Skip()

    def OnSpinUp(self, evt: wx.SpinEvent) -> None:
        self.SetValue(self.GetValue() + self._increment)
        self.raise_event()
        evt.Skip()

    def raise_event(self) -> None:
        event = wx.PyCommandEvent(wx.EVT_SPINCTRL.typeId, self.GetId())
        self.GetEventHandler().ProcessEvent(event)


class InvFloatSpinCtrl(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        id: int = wx.ID_ANY,
        value: float = 0.0,
        min_value: float = 1.0,
        max_value: float = 100.0,
        increment: float = 0.1,
        digits: int = 1,
        spin_button: bool = True,
        size: wx.Size = wx.DefaultSize,
        style: int = wx.TE_RIGHT,
    ):
        super().__init__(parent, id, size=size)

        self._textctrl = wx.TextCtrl(self, -1, style=style)
        if spin_button and wx.Platform != "__WXGTK__":
            self._spinbtn: Optional[wx.SpinButton] = wx.SpinButton(self, -1)
        else:
            self._spinbtn = None

        self._digits = digits
        self._dec_context = decimal.Context(prec=digits)

        self._value = decimal.Decimal("0", self._dec_context)
        self._last_value = self._value
        self._min_value = decimal.Decimal("0", self._dec_context)
        self._max_value = decimal.Decimal("100", self._dec_context)
        self._increment = decimal.Decimal("0.1", self._dec_context)

        self.SetIncrement(increment)
        self.SetMin(min_value)
        self.SetMax(max_value)
        self.SetValue(value)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._textctrl, 1, wx.EXPAND)
        if self._spinbtn:
            sizer.Add(self._spinbtn, 0, wx.EXPAND)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.__bind_events()

    def __bind_events(self) -> None:
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self._textctrl.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        if self._spinbtn:
            self._spinbtn.Bind(wx.EVT_SPIN_UP, self.OnSpinUp)
            self._spinbtn.Bind(wx.EVT_SPIN_DOWN, self.OnSpinDown)

    def _to_decimal(self, value: Union[decimal.Decimal, float, str]) -> decimal.Decimal:
        if not isinstance(value, str):
            value = "{:.{digits}f}".format(value, digits=self._digits)
        return decimal.Decimal(value, self._dec_context)

    def SetDigits(self, digits: int) -> None:
        self._digits = digits
        self._dec_context = decimal.Context(prec=digits)

        self.SetIncrement(self._increment)
        self.SetMin(self._min_value)
        self.SetMax(self._max_value)
        self.SetValue(self._value)

    def SetIncrement(self, increment: Union[decimal.Decimal, float, str]) -> None:
        self._increment = self._to_decimal(increment)

    def SetMin(self, min_value: Union[decimal.Decimal, float, str]) -> None:
        self._min_value = self._to_decimal(min_value)
        self.SetValue(self._value)

    def SetMax(self, max_value: Union[decimal.Decimal, float, str]) -> None:
        self._max_value = self._to_decimal(max_value)
        self.SetValue(self._value)

    def SetRange(
        self,
        min_value: Union[decimal.Decimal, float, str],
        max_value: Union[decimal.Decimal, float, str],
    ) -> None:
        self.SetMin(min_value)
        self.SetMax(max_value)

    def GetValue(self) -> float:
        return float(self._value)

    def SetValue(self, value: Any) -> None:
        try:
            value = self._to_decimal(value)
        except decimal.InvalidOperation:
            value = self._last_value

        if value < self._min_value:
            value = self._min_value

        if value > self._max_value:
            value = self._max_value

        self._value = value
        self._textctrl.SetValue(f"{self._value}")
        self._last_value = self._value

    def CalcSizeFromTextSize(self, text: Optional[str] = None) -> None:
        # To calculate best width to spinctrl
        if text is None:
            text = "{}".format(max(len(str(self._max_value)), len(str(self._min_value))) * "M")

        dc = wx.WindowDC(self)
        dc.SetFont(self.GetFont())
        width, height = dc.GetTextExtent(text)

        spin = wx.SpinCtrl(self, -1)
        spin_width, spin_height = spin.GetBestSize()
        spin.Destroy()

        if self._spinbtn:
            spin = wx.SpinCtrl(self, -1)
            spin_width, spin_height = spin.GetBestSize()
            spin.Destroy()

            spinb = wx.SpinButton(self, -1)
            spinb_width, spinb_height = spinb.GetBestSize()
            spinb.Destroy()

            width += spinb_width
            if wx.Platform == "__WXMAC":
                height = max(height, spin_height, spinb_height)
            else:
                height = spin_height
        else:
            height = -1

        self.SetMinSize((width, height))
        self.Layout()

    def OnMouseWheel(self, evt: wx.MouseEvent) -> None:
        r = evt.GetWheelRotation()
        if r > 0:
            self.SetValue(self._value + self._increment)
        else:
            self.SetValue(self._value - self._increment)
        self.raise_event()
        evt.Skip()

    def OnKillFocus(self, evt: wx.FocusEvent) -> None:
        value = self._textctrl.GetValue()
        self.SetValue(value)
        self.raise_event()
        evt.Skip()

    def OnSpinDown(self, evt: wx.SpinEvent) -> None:
        self.SetValue(self._value - self._increment)
        self.raise_event()
        evt.Skip()

    def OnSpinUp(self, evt: wx.SpinEvent) -> None:
        self.SetValue(self._value + self._increment)
        self.raise_event()
        evt.Skip()

    def raise_event(self) -> None:
        event = wx.PyCommandEvent(wx.EVT_SPINCTRL.typeId, self.GetId())
        self.GetEventHandler().ProcessEvent(event)
