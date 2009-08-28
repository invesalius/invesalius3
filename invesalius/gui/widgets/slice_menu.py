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
import sys

import wx
import wx.lib.pubsub as ps
import constants as const

class SliceMenu(wx.Menu):
    def __init__(self):
        wx.Menu.__init__(self)
        self.ID_TO_TOOL_ITEM = {}
        
        #------------ Sub menu of the window and level ----------
        submenu_wl = wx.Menu()        
        new_id = wx.NewId()
        wl_item = wx.MenuItem(submenu_wl, new_id,\
                            'Default', kind=wx.ITEM_RADIO)
        submenu_wl.AppendItem(wl_item)
        self.ID_TO_TOOL_ITEM[new_id] = 'Default'
        for name in sorted(const.WINDOW_LEVEL):
            if not(name == 'Default'):
                new_id = wx.NewId()
                wl_item = wx.MenuItem(submenu_wl, new_id,\
                                    name, kind=wx.ITEM_RADIO)
                submenu_wl.AppendItem(wl_item)
                self.ID_TO_TOOL_ITEM[new_id] = name

        #------------ Sub menu of the pseudo colors -------------
        submenu_pseudo_colors = wx.Menu()
        new_id = wx.NewId()
        color_item = wx.MenuItem(submenu_pseudo_colors, new_id,\
                            'Default (Gray)', kind=wx.ITEM_RADIO)
        submenu_pseudo_colors.AppendItem(color_item)
        self.ID_TO_TOOL_ITEM[new_id] = 'Default (Gray)'
        for name in sorted(const.SLICE_COLOR_TABLE):
            if not(name == 'Default (Gray)'):
                new_id = wx.NewId()
                color_item = wx.MenuItem(submenu_wl, new_id,\
                                    name, kind=wx.ITEM_RADIO)
                submenu_pseudo_colors.AppendItem(color_item)
                self.ID_TO_TOOL_ITEM[new_id] = name
        
        #------------ Sub menu of the image tiling ---------------
        submenu_image_tiling = wx.Menu()
        for name in sorted(const.IMAGE_TILING):
            new_id = wx.NewId()
            image_tiling_item = wx.MenuItem(submenu_image_tiling, new_id,\
                                name, kind=wx.ITEM_RADIO)
            submenu_image_tiling.AppendItem(image_tiling_item)
            self.ID_TO_TOOL_ITEM[new_id] = name

        # Add sub itens in the menu
        self.AppendMenu(-1, "Window Width & Level", submenu_wl)
        self.AppendMenu(-1, "Pseudo Colors", submenu_pseudo_colors)
        self.AppendMenu(-1, "Image Tiling", submenu_image_tiling)            
        
        # It doesn't work in Linux
        self.Bind(wx.EVT_MENU, self.OnPopup)
        # In Linux the bind must be putted in the submenu
        if sys.platform == 'linux2':
            submenu_wl.Bind(wx.EVT_MENU, self.OnPopup)
            submenu_pseudo_colors.Bind(wx.EVT_MENU, self.OnPopup)
            submenu_image_tiling.Bind(wx.EVT_MENU, self.OnPopup)
    
    def OnPopup(self, evt):
        
        id = evt.GetId()
        key = self.ID_TO_TOOL_ITEM[evt.GetId()]
        
        if(key in const.WINDOW_LEVEL.keys()):
            window, level = const.WINDOW_LEVEL[key]
            ps.Publisher().sendMessage('Bright and contrast adjustment image',
                    (window, level))
            ps.Publisher().sendMessage('Update window level value',\
               (window, level))
            ps.Publisher().sendMessage('Update window and level text',\
                           "WL: %d  WW: %d"%(level, window))
            ps.Publisher().sendMessage('Update slice viewer')
            
        elif(key in const.SLICE_COLOR_TABLE.keys()):
            values = const.SLICE_COLOR_TABLE[key]
            ps.Publisher().sendMessage('Change color table from background image', values)
            ps.Publisher().sendMessage('Update slice viewer')
            
        elif(key in const.IMAGE_TILING.keys()):
            values = const.IMAGE_TILING[key]
            ps.Publisher().sendMessage('Set slice viewer layout', values)
            ps.Publisher().sendMessage('Update slice viewer')
            
        evt.Skip()

