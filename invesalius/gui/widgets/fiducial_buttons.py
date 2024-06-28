# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
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
# --------------------------------------------------------------------
from functools import partial

import wx
import invesalius.constants as const
from wx.lib.masked.numctrl import NumCtrl


class OrderedFiducialButtons:
    def __init__(self, parent, fiducial_definitions, is_fiducial_set, get_fiducial_coord=None, set_actor_colors=None,
                 order=None):
        """
        Class to initialize fiducials GUI and to keep track of the order to set fiducials.

        :param parent: parent for wx elements
        :param fiducial_definitions: const.OBJECT_FIDUCIALS or const.TRACKER_FIDUCIALS
        :param is_fiducial_set: Function taking fiducial index as parameter, returning True if that
                                fiducial is set, False otherwise.
        :param get_fiducial_coord: Function to retrieve value for NumCtrl. Takes fiducial index and
                                   coordinate index as parameters, returns value.
        :param set_actor_colors: Function taking fiducial index and float color as parameter, changing
                                 the color of relevant actors to match the fiducial index.
        :param order: list of indices representing default order to record fiducials
        """
        count = len(fiducial_definitions)
        self.is_fiducial_set = is_fiducial_set
        self.get_fiducial_coord = get_fiducial_coord
        self.set_actor_colors = set_actor_colors
        self.order: list[int] = order or list(range(count))

        self.buttons: list[wx.Button] = []
        self.numctrls: list[list[NumCtrl]] = []

        self.focused_index: int | None = None
        self.focused: wx.Button | None = None

        self.COLOR_NOT_SET = 0
        self.COLOR_FOCUSED = 1
        self.COLOR_SET = 2

        # Initialize buttons
        for n, fiducial in enumerate(fiducial_definitions):
            button_id = fiducial['button_id']
            label = fiducial['label']
            tip = fiducial['tip']

            w, h = wx.ScreenDC().GetTextExtent("M"*len(label))
            ctrl = wx.Button(parent, button_id, label='', size=(55, h+5))
            ctrl.SetLabel(label)
            ctrl.SetToolTip(tip)
            ctrl.Bind(wx.EVT_BUTTON, partial(self._OnButton, n=n))
            self.buttons.append(ctrl)

        # Initialize NumCtrls
        for n in range(count):
            coords = []
            for coord_index in range(3):
                numctrl = wx.lib.masked.numctrl.NumCtrl(parent=parent, integerWidth=4, fractionWidth=1)
                numctrl.Hide()
                coords.append(numctrl)
            self.numctrls.append(coords)

        self.Update()

    def __getitem__(self, n):
        return self.buttons[n]

    def __iter__(self):
        return iter(self.buttons)

    @property
    def focused(self):
        if self.focused_index is None:
            return None
        else:
            return self.buttons[self.focused_index]

    @focused.setter
    def focused(self, new_focus):
        if new_focus is None:
            self.focused_index = None
            return

        for n, button in enumerate(self.buttons):
            if new_focus is button:
                self.focused_index = n
                return
        raise ValueError

    def _TrySetActorColors(self, n, color_float):
        if self.set_actor_colors is not None:
            self.set_actor_colors(n, color_float)

    def _SetColor(self, n, color):
        button = self.buttons[n]
        if color == self.COLOR_SET:
            button.SetBackgroundColour(const.GREEN_COLOR_RGB)
            self._TrySetActorColors(n, const.GREEN_COLOR_FLOAT)
        elif color == self.COLOR_FOCUSED:
            button.SetBackgroundColour(const.YELLOW_COLOR_RGB)
            self._TrySetActorColors(n, const.YELLOW_COLOR_FLOAT)
        else:
            button.SetBackgroundColour(const.RED_COLOR_RGB)
            self._TrySetActorColors(n, const.RED_COLOR_FLOAT)

    def _RefreshColors(self):
        for n, button in enumerate(self.buttons):
            if self.is_fiducial_set(n):
                self._SetColor(n, self.COLOR_SET)
            else:
                self._SetColor(n, self.COLOR_NOT_SET)
        if self.focused is not None:
            self._SetColor(self.focused_index, self.COLOR_FOCUSED)

    def _UpdateControls(self):
        if self.get_fiducial_coord is None:
            return

        for n, element in enumerate(self.numctrls):
            for i, numctrl in enumerate(element):
                value = self.get_fiducial_coord(n, i)
                numctrl.SetValue(value)

    def _UpdateControl(self, n):
        if self.get_fiducial_coord is None:
            return

        for i, numctrl in enumerate(self.numctrls[n]):
            value = self.get_fiducial_coord(n, i)
            numctrl.SetValue(value)

    def Update(self):
        self._UpdateControls()
        self._RefreshColors()

    def FocusNext(self):
        for n in self.order:
            if not self.is_fiducial_set(n):
                self.Focus(n)
                break

    def ClearFocus(self):
        if self.focused is not None:
            self._SetColor(self.focused_index, self.COLOR_NOT_SET)
            self.focused = None

    def _OnButton(self, evt, n):
        self.Focus(n)

    def Focus(self, n):
        self.ClearFocus()
        self.focused = self.buttons[n]
        self._SetColor(self.focused_index, self.COLOR_FOCUSED)

    def SetFocused(self):
        self._SetColor(self.focused_index, self.COLOR_SET)
        self._UpdateControl(self.focused_index)
        self.focused = None
        self.FocusNext()

    def Set(self, n):
        self.Focus(n)
        self.SetFocused()

    def Unset(self, n):
        self._SetColor(n, self.COLOR_NOT_SET)
        self.FocusNext()
