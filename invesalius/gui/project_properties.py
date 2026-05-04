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

import wx

import invesalius.project as prj
from invesalius import constants as const
from invesalius.gui import utils
from invesalius.i18n import tr as _

ORIENTATION_LABEL = {
    const.AXIAL: _("Axial"),
    const.CORONAL: _("Coronal"),
    const.SAGITAL: _("Sagital"),
}


class ProjectProperties(wx.Dialog):
    def __init__(self, parent):
        super().__init__(
            id=-1,
            name="",
            parent=parent,
            style=wx.DEFAULT_FRAME_STYLE,
            title=_("Project Properties"),
        )
        self.Center(wx.BOTH)
        self._init_gui()

    def _init_gui(self):
        project = prj.Project()
        self.name_txt = wx.TextCtrl(self, -1, value=project.name)
        self.name_txt.SetMinSize((utils.calc_width_needed(self.name_txt, 30), -1))

        modality_txt = wx.TextCtrl(self, -1, value=project.modality, style=wx.TE_READONLY)

        try:
            orientation = ORIENTATION_LABEL[project.original_orientation]
        except KeyError:
            orientation = _("Other")

        orientation_txt = wx.TextCtrl(self, -1, value=orientation, style=wx.TE_READONLY)

        sx, sy, sz = project.spacing
        spacing_txt_x = wx.TextCtrl(self, -1, value=f"{sx:.5}", style=wx.TE_READONLY)
        spacing_txt_y = wx.TextCtrl(self, -1, value=f"{sy:.5}", style=wx.TE_READONLY)
        spacing_txt_z = wx.TextCtrl(self, -1, value=f"{sz:.5}", style=wx.TE_READONLY)

        name_sizer = wx.BoxSizer(wx.HORIZONTAL)
        name_sizer.Add(wx.StaticText(self, -1, _("Name")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        name_sizer.Add(self.name_txt, 1, wx.EXPAND | wx.ALL, 5)

        modality_sizer = wx.BoxSizer(wx.HORIZONTAL)
        modality_sizer.Add(
            wx.StaticText(self, -1, _("Modality")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
        )
        modality_sizer.Add(modality_txt, 1, wx.EXPAND | wx.ALL, 5)

        orientation_sizer = wx.BoxSizer(wx.HORIZONTAL)
        orientation_sizer.Add(
            wx.StaticText(self, -1, _("Orientation")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
        )
        orientation_sizer.Add(orientation_txt, 1, wx.EXPAND | wx.ALL, 5)

        spacing_sizer = wx.BoxSizer(wx.HORIZONTAL)
        spacing_sizer.Add(
            wx.StaticText(self, -1, _("Spacing")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
        )
        spacing_sizer.Add(spacing_txt_x, 1, wx.EXPAND | wx.ALL, 5)
        spacing_sizer.Add(spacing_txt_y, 1, wx.EXPAND | wx.ALL, 5)
        spacing_sizer.Add(spacing_txt_z, 1, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(name_sizer, 1, wx.EXPAND)
        main_sizer.Add(modality_sizer, 1, wx.EXPAND)
        main_sizer.Add(orientation_sizer, 1, wx.EXPAND)
        main_sizer.Add(spacing_sizer, 1, wx.EXPAND)
        main_sizer.Add(btn_sizer, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.Layout()
