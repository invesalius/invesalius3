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

import os

import wx
import wx.lib.agw.hyperlink as hl
import wx.lib.platebtn as pbtn

import invesalius.constants as constants
from invesalius import inv_paths
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher
from invesalius.session import Session

ID_BTN_MEASURE_LINEAR = wx.NewIdRef()
ID_BTN_MEASURE_ANGULAR = wx.NewIdRef()
ID_BTN_MEASURE_CURVED = wx.NewIdRef()
ID_BTN_ANNOTATION = wx.NewIdRef()


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        self.SetAutoLayout(1)

        # Counter for projects loaded in current GUI
        self.proj_count = 0

        # Floating items (to be inserted)
        self.float_hyper_list = []

        # Fixed text and hyperlink items
        tooltip = _("Measure distances")
        txt_measure = wx.StaticText(self, -1, _("Measure"))
        txt_measure.SetToolTip(tooltip)

        tooltip = _("Add text annotations")
        txt_annotation = hl.HyperLinkCtrl(self, -1, _("Add text annotations"))
        txt_annotation.SetUnderlines(False, False, False)
        txt_annotation.SetColours("BLACK", "BLACK", "BLACK")
        txt_annotation.SetToolTip(tooltip)
        txt_annotation.AutoBrowse(False)
        txt_annotation.UpdateLink()
        txt_annotation.Bind(hl.EVT_HYPERLINK_LEFT, self.OnTextAnnotation)

        # Image(s) for buttons
        BMP_ANNOTATE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "annotation.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_ANGLE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "measure_angle_original.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_DISTANCE = wx.Bitmap(
            os.path.join(inv_paths.ICON_DIR, "measure_line_original.png"), wx.BITMAP_TYPE_PNG
        )
        BMP_ANNOTATE.SetWidth(25)
        BMP_ANNOTATE.SetHeight(25)
        BMP_ANGLE.SetWidth(25)
        BMP_ANGLE.SetHeight(25)
        BMP_DISTANCE.SetWidth(25)
        BMP_DISTANCE.SetHeight(25)

        # Buttons related to hyperlinks
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT

        button_measure_linear = pbtn.PlateButton(
            self, ID_BTN_MEASURE_LINEAR, "", BMP_DISTANCE, style=button_style
        )
        button_measure_angular = pbtn.PlateButton(
            self, ID_BTN_MEASURE_ANGULAR, "", BMP_ANGLE, style=button_style
        )
        button_measure_angular.SetToolTip(_("Measure angles"))

        button_measure_curved = pbtn.PlateButton(
            self, ID_BTN_MEASURE_CURVED, "", BMP_DISTANCE, style=button_style
        )
        button_measure_curved.SetToolTip(
            _("Measure curved distance on surface\nClick to select: Two points or Multi-points")
        )

        button_annotation = pbtn.PlateButton(
            self, ID_BTN_ANNOTATION, "", BMP_ANNOTATE, style=button_style
        )

        # When using PlateButton, it is necessary to bind events from parent win
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Layout: row 0 has Measure label, linear btn, angular btn, curved btn
        sizer = wx.GridBagSizer(hgap=0, vgap=0)
        sizer.Add(txt_measure, pos=(0, 0), flag=wx.GROW | wx.EXPAND | wx.TOP, border=3)
        sizer.Add(button_measure_linear, pos=(0, 1), flag=wx.GROW | wx.EXPAND)
        sizer.Add(button_measure_angular, pos=(0, 2), flag=wx.GROW | wx.EXPAND)
        sizer.Add(button_measure_curved, pos=(0, 3), flag=wx.GROW | wx.EXPAND)
        sizer.Add(txt_annotation, pos=(1, 0), flag=wx.GROW | wx.EXPAND)
        sizer.Add(button_annotation, pos=(1, 2), span=(2, 1), flag=wx.GROW | wx.EXPAND)
        sizer.AddGrowableCol(0)

        # Update main sizer and panel layout
        self.SetSizer(sizer)
        self.Fit()

    def OnTextAnnotation(self, evt=None):
        print("TODO: Send Signal - Add text annotation (both 2d and 3d)")

    def OnLinkLinearMeasure(self):
        Publisher.sendMessage("Enable style", style=constants.STATE_MEASURE_DISTANCE)

    def OnLinkAngularMeasure(self):
        Publisher.sendMessage("Enable style", style=constants.STATE_MEASURE_ANGULAR)

    def OnLinkCurvedMeasure(self):
        Publisher.sendMessage("Enable style", style=constants.STATE_MEASURE_CURVED_LINEAR)

    def OnCurvedMeasureClick(self):
        """Show a guaranteed modal dialog for curved ruler mode selection."""
        choices = [_("Two points"), _("Multi-points")]
        # Get the currently saved setting to pre-select the right choice
        current_multi = Session().GetConfig("geodesic_multi_point", False)
        dlg = wx.SingleChoiceDialog(
            self,
            _("Select curved measurement mode:"),
            _("Curved Ruler"),
            choices,
        )
        dlg.SetSelection(1 if current_multi else 0)
        if dlg.ShowModal() == wx.ID_OK:
            multi = dlg.GetSelection() == 1
            Session().SetConfig("geodesic_multi_point", multi)
            self.OnLinkCurvedMeasure()
        dlg.Destroy()

    def OnButton(self, evt):
        id = evt.GetId()

        if id == ID_BTN_MEASURE_LINEAR:
            self.OnLinkLinearMeasure()
        elif id == ID_BTN_MEASURE_ANGULAR:
            self.OnLinkAngularMeasure()
        elif id == ID_BTN_MEASURE_CURVED:
            self.OnCurvedMeasureClick()
        else:  # elif id == ID_BTN_ANNOTATION:
            self.OnTextAnnotation()
