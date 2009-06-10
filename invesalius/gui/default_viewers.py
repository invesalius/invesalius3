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
import wx.lib.agw.fourwaysplitter as fws
import data.viewer_slice as slice_viewer
import data.viewer_volume as volume_viewer

class SamplePane(wx.Panel):
    """
    Just a simple test window to put into the splitter.
    """
    def __init__(self, parent, colour, label):
        wx.Panel.__init__(self, parent, style=wx.BORDER_SUNKEN)
        self.SetBackgroundColour(colour)
        wx.StaticText(self, -1, label, (5,5))

    def SetOtherLabel(self, label):
        wx.StaticText(self, -1, label, (5, 30))


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

        self.aui_manager.AddPane(slice_viewer.Viewer(self, "AXIAL"), 
                                 wx.aui.AuiPaneInfo().Centre().Row(0).
                                 Name("Axial Slice").Caption("Axial slice").
                                 MaximizeButton(True).CloseButton(False))

        self.aui_manager.AddPane(slice_viewer.Viewer(self, "CORONAL"), 
                                 wx.aui.AuiPaneInfo().Centre().Row(0).#Fixed().
                                 Name("Coronal Slice").Caption("Coronal slice").
                                 MaximizeButton(True).CloseButton(False))
                          
        self.aui_manager.AddPane(slice_viewer.Viewer(self, "SAGITAL"), 
                                 wx.aui.AuiPaneInfo().Centre().Row(1).#Fixed().
                                   Name("Sagital Slice").Caption("Sagital slice").
                                   MaximizeButton(True).CloseButton(False))

        self.aui_manager.AddPane(volume_viewer.Viewer(self),
                                 wx.aui.AuiPaneInfo().Row(1).Name("Volume").
                                 Bottom().Centre().Caption("Volume").
                                 MaximizeButton(True).CloseButton(False))

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

        p4 = volume_viewer.Viewer(self)
        aui_manager.AddPane(p4, 
                                 wx.aui.AuiPaneInfo().
                                 Name("Volume").Caption("Volume").
                                 MaximizeButton(True).CloseButton(False))

        splitter.AppendWindow(p1)
        splitter.AppendWindow(p2)
        splitter.AppendWindow(p3)
        splitter.AppendWindow(p4)


        aui_manager.Update()
