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

import wx
import wx.lib.pubsub as ps
import constants as const

class SliceMenu(wx.Menu):
    def __init__(self):
        wx.Menu.__init__(self)
        self.ID_TO_TOOL_ITEM = {}
        submenu_wl = wx.Menu()
        for name in sorted(const.WINDOW_LEVEL):
            new_id = wx.NewId()
            wl_item = wx.MenuItem(submenu_wl, new_id,\
                                name, kind=wx.ITEM_RADIO)
            submenu_wl.AppendItem(wl_item)
            self.ID_TO_TOOL_ITEM[new_id] = name
        self.AppendMenu(-1, "Window Width & Level", submenu_wl)
        submenu_wl.Bind(wx.EVT_MENU, self.OnPopupWindowLevel)


    def OnPopupWindowLevel(self, evt):
        key = self.ID_TO_TOOL_ITEM[evt.GetId()]
        window, level = const.WINDOW_LEVEL[key]
        ps.Publisher().sendMessage('Bright and contrast adjustment image',
                (window, level))
        ps.Publisher().sendMessage('Update slice viewer')
        evt.Skip()

