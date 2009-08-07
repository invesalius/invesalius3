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
import wx.lib.agw.fourwaysplitter as fws
import data.viewer_slice as slice_viewer
import data.viewer_volume as volume_viewer


class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50),
                          size=wx.Size(744, 656))

        self.__init_aui_manager()
        #self.__init_four_way_splitter()
        #self.__init_mix()

    def __init_aui_manager(self):
        self.aui_manager = wx.aui.AuiManager()
        self.aui_manager.SetManagedWindow(self)


        # TODO: Testar mais e verificar melhor opcao
        
        # Position
        # volume          | pos = 0
        # sagital         | pos = 1
        # coronal         | pos = 2
        # axial           | pos = 3
        # Automatico: assim que painel eh inserido ele ocupa local mais acima na janela (menor numero de posicao)
        
        # Layer
        # Layer 0 | Layer 1 | Layer 2 | ...
        # Automatico: todos sao colocados no mesmo layer
        
        # O que eh o Dockable?
        
        # Row
        # Row 0 | Row 1
        # Idem ao layer
        
        # Como funciona Direction?
        
        # Primeira alternativa:
        # modo: 2 no Layer 0, 2 no Layer 1 por exemplo - posicao automatica (ao inves de Layer pode ser utilizado Row)
        # problema: sash control soh aparece no sentido ertical
        # tentativa de solucionar problema seria utilizar Fixed, mas qdo se aciona maximizar nao maximiza inteiro

        p1 = slice_viewer.Viewer(self, "AXIAL")
        s1 = wx.aui.AuiPaneInfo().Centre().Row(0).\
             Name("Axial Slice").Caption("Axial slice").\
             MaximizeButton(True).CloseButton(False)
             
        p2 = slice_viewer.Viewer(self, "CORONAL")
        s2 = wx.aui.AuiPaneInfo().Centre().Row(0).\
             Name("Coronal Slice").Caption("Coronal slice").\
             MaximizeButton(True).CloseButton(False)
        
        p3 = slice_viewer.Viewer(self, "SAGITAL")
        s3 = wx.aui.AuiPaneInfo().Centre().Row(1).\
             Name("Sagital Slice").Caption("Sagital slice").\
             MaximizeButton(True).CloseButton(False)
             
        p4 = VolumeViewerCover(self)
        s4 = wx.aui.AuiPaneInfo().Row(1).Name("Volume").\
             Bottom().Centre().Caption("Volume").\
             MaximizeButton(True).CloseButton(False)
        
        if sys.platform == 'win32':
            self.aui_manager.AddPane(p1, s1)
            self.aui_manager.AddPane(p2, s2)
            self.aui_manager.AddPane(p3, s3)
            self.aui_manager.AddPane(p4, s4)
        else:
            self.aui_manager.AddPane(p4, s4)
            self.aui_manager.AddPane(p3, s3)
            self.aui_manager.AddPane(p2, s2)
            self.aui_manager.AddPane(p1, s1)
        
        self.aui_manager.Update()
        

    def __init_four_way_splitter(self):

        splitter = fws.FourWaySplitter(self, style=wx.SP_LIVE_UPDATE)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

        p1 = slice_viewer.Viewer(self, "AXIAL")
        splitter.AppendWindow(p1)
        
        p2 = slice_viewer.Viewer(self, "CORONAL")
        splitter.AppendWindow(p2)
        
        p3 = slice_viewer.Viewer(self, "SAGITAL")
        splitter.AppendWindow(p3)
        
        p4 = volume_viewer.Viewer(self)
        splitter.AppendWindow(p4)

        
    def __init_mix(self):
        aui_manager = wx.aui.AuiManager()
        aui_manager.SetManagedWindow(self)


        splitter = fws.FourWaySplitter(self, style=wx.SP_LIVE_UPDATE)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)


        p1 = slice_viewer.Viewer(self, "AXIAL")
        aui_manager.AddPane(p1, 
                                 wx.aui.AuiPaneInfo().
                                 Name("Axial Slice").Caption("Axial slice").
                                 MaximizeButton(True).CloseButton(False))
        
        p2 = slice_viewer.Viewer(self, "CORONAL")
        aui_manager.AddPane(p2, 
                                 wx.aui.AuiPaneInfo().
                                 Name("Coronal Slice").Caption("Coronal slice").
                                 MaximizeButton(True).CloseButton(False))

        p3 = slice_viewer.Viewer(self, "SAGITAL")
        aui_manager.AddPane(p3, 
                                 wx.aui.AuiPaneInfo().
                                 Name("Sagittal Slice").Caption("Sagittal slice").
                                 MaximizeButton(True).CloseButton(False))

        #p4 = volume_viewer.Viewer(self)
        aui_manager.AddPane(VolumeViewerCover, 
                                 wx.aui.AuiPaneInfo().
                                 Name("Volume").Caption("Volume").
                                 MaximizeButton(True).CloseButton(False))

        splitter.AppendWindow(p1)
        splitter.AppendWindow(p2)
        splitter.AppendWindow(p3)
        splitter.AppendWindow(p4)


        aui_manager.Update()
        
class VolumeViewerCover(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(volume_viewer.Viewer(self), 1, wx.EXPAND|wx.GROW)
        sizer.Add(VolumeToolPanel(self), 0, wx.EXPAND)
        self.SetSizer(sizer)
        sizer.Fit(self)
        
import wx.lib.platebtn as pbtn
import wx.lib.buttons as btn
import wx.lib.pubsub as ps
import wx.lib.colourselect as csel

class VolumeToolPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size = (8,100))
        
        BMP_RAYCASTING = wx.Bitmap("../icons/volume_raycasting.png", wx.BITMAP_TYPE_PNG)
        BMP_RAYCASTING.SetWidth(22)
        BMP_RAYCASTING.SetHeight(22)

        BMP_POSITION = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        BMP_POSITION.SetWidth(22)
        BMP_POSITION.SetHeight(22)

        button_raycasting=btn.GenBitmapToggleButton(self, 1, BMP_RAYCASTING, size=(24,24))
        button_raycasting.Bind(wx.EVT_BUTTON, self.OnToggleRaycasting)
        self.button_raycasting = button_raycasting
        
        menu = wx.Menu()
        
        FRONT_BMP = wx.Bitmap("../icons/brush_circle.jpg", wx.BITMAP_TYPE_JPEG)
        item = wx.MenuItem(menu, 0, "Front")
        item.SetBitmap(FRONT_BMP)

        BACK_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        item2 = wx.MenuItem(menu, 1, "Back")
        item2.SetBitmap(BACK_BMP)
        
        TOP_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        item3 = wx.MenuItem(menu, 2, "Top")
        item3.SetBitmap(TOP_BMP)

        BOTTOM_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        item4 = wx.MenuItem(menu, 3, "Bottom")
        item4.SetBitmap(BOTTOM_BMP)

        RIGHT_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        item5 = wx.MenuItem(menu, 4, "Right")
        item5.SetBitmap(RIGHT_BMP)

        LEFT_BMP = wx.Bitmap("../icons/brush_square.jpg", wx.BITMAP_TYPE_JPEG)
        item6 = wx.MenuItem(menu, 5, "Left")
        item6.SetBitmap(LEFT_BMP)
        
        self.Bind(wx.EVT_MENU, self.OnMenu)
        
        menu.AppendItem(item)
        menu.AppendItem(item2)        
        menu.AppendItem(item3)
        menu.AppendItem(item4)
        menu.AppendItem(item5)
        menu.AppendItem(item6)
    
        button_position = pbtn.PlateButton(self, wx.ID_ANY,"", BMP_POSITION,
                                          style=pbtn.PB_STYLE_SQUARE, size=(24,24))
        
        button_position.SetMenu(menu)
        self.button_position = button_position
        
        button_colour= csel.ColourSelect(self, 111,colour=(0,0,0),size=(24,24))
        button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_colour = button_colour

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(button_colour, 0, wx.ALL, 1)
        sizer.Add(button_raycasting, 0, wx.ALL, 1)
        sizer.Add(button_position, 0, wx.ALL, 1)
        self.SetSizer(sizer)
        sizer.Fit(self)
        
    def OnMenu(self, evt):
        values = {0:"FRONT", 1:"BACK", 2:"TOP",\
                  3:"BOTTOM", 4:"RIGHT", 5:"LEFT"}
        ps.Publisher().sendMessage('Reposition Actor',\
                                   values[evt.GetId()])

    def OnSelectColour(self, evt):
        colour = c = [i/255.0 for i in evt.GetValue()]
        ps.Publisher().sendMessage('Change volume viewer background colour', colour)

    def OnToggleRaycasting(self, evt):
        if self.button_raycasting.GetToggle():
            #ps.Publisher().sendMessage('Create volume raycasting')
            ps.Publisher().sendMessage('Show raycasting volume')
        else:
            ps.Publisher().sendMessage('Hide raycasting volume')
