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

import os
import sys

import wx
import wx.lib.hyperlink as hl
#import wx.lib.platebtn as pbtn
#import wx.lib.pubsub as ps

#import constants as const
#import gui.dialogs as dlg
#import project as proj

class TaskPanel(wx.Panel):
    """
    This panel works as a "frame", drawing a white margin arround 
    the panel that really matters (InnerTaskPanel).
    """
    def __init__(self, parent):
        # note: don't change this class!!!
        wx.Panel.__init__(self, parent)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(InnerTaskPanel(self), 1, wx.EXPAND | wx.GROW |
                                 wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class InnerTaskPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(wx.Colour(255,255,255))
        self.SetAutoLayout(1)
        
        # Bind events
        self.__bind_events()
        self.__bind_wx_events()

    def __init_gui(self):
        link_export_picture = hl.HyperLinkCtrl(self, -1,
                                            _("Testing..."))
        link_export_picture.SetUnderlines(False, False, False)
        link_export_picture.SetColours("BLACK", "BLACK", "BLACK")
        link_export_picture.SetToolTip(tooltip)
        link_export_picture.AutoBrowse(False)
        link_export_picture.UpdateLink()
        #link_export_picture.Bind(hl.EVT_HYPERLINK_LEFT,
        #                         self.OnLinkExportPicture)

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
        pass
