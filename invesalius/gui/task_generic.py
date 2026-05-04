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


import wx
import wx.lib.hyperlink as hl

from invesalius.i18n import tr as _


class TaskPanel(wx.Panel):
    """
    This panel works as a "frame", drawing a white margin arround
    the panel that really matters (InnerTaskPanel).
    """

    def __init__(self, parent):
        # note: don't change this class!!!
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

        # Build GUI
        self.__init_gui()

        # Bind events
        self.__bind_events()
        self.__bind_wx_events()

    def __init_gui(self):
        """
        Build widgets in current panel
        """
        # Create widgets to be inserted in this panel
        link_test = hl.HyperLinkCtrl(self, -1, _("Testing..."))
        link_test.SetUnderlines(False, False, False)
        link_test.SetColours("BLACK", "BLACK", "BLACK")
        link_test.AutoBrowse(False)
        link_test.UpdateLink()
        self.link_test = link_test

        # Add line sizers into main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(link_test, 0, wx.GROW | wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

    def __bind_events(self):
        """
        Bind pubsub events
        """
        # Example: ps.Publisher().subscribe("Test")
        pass

    def __bind_wx_events(self):
        """
        Bind wx general events
        """
        # Example: self.Bind(wx.EVT_BUTTON, self.OnButton)
        self.link_test.Bind(hl.EVT_HYPERLINK_LEFT, self.OnTest)

    def OnTest(self, event):
        """
        Describe what this method does
        """
        event.Skip()
