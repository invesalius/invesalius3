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
import sys

import wx

import invesalius.constants as const
import invesalius.data.viewer_slice as slice_viewer
import invesalius.gui.widgets.slice_menu as slice_menu_
import invesalius.session as ses
from invesalius.i18n import tr as _
from invesalius.navigation.navigation_views_manager import NavigationWindowManager
from invesalius.pubsub import pub as Publisher


class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(0, 50), size=wx.Size(744, 656))

        self.__init_aui_manager()
        self.__bind_events_wx()
        self.__bind_events()
        # self.__init_four_way_splitter()
        # self.__init_mix()

    def __init_aui_manager(self):
        self.aui_manager = wx.aui.AuiManager()
        self.aui_manager.SetManagedWindow(self)

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

        self.p1 = slice_viewer.Viewer(self, "AXIAL")
        self.s1 = (
            wx.aui.AuiPaneInfo()
            .Centre()
            .Row(0)
            .Name("Axial Slice")
            .Caption(_("Axial slice"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        self.p2 = slice_viewer.Viewer(self, "CORONAL")
        self.s2 = (
            wx.aui.AuiPaneInfo()
            .Centre()
            .Row(0)
            .Name("Coronal Slice")
            .Caption(_("Coronal slice"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        self.p3 = slice_viewer.Viewer(self, "SAGITAL")
        self.s3 = (
            wx.aui.AuiPaneInfo()
            .Centre()
            .Row(1)
            .Name("Sagittal Slice")
            .Caption(_("Sagittal slice"))
            .MaximizeButton(True)
            .CloseButton(False)
        )

        # Create navigation manager and views
        self.nav_manager = NavigationWindowManager(self, self.aui_manager)

        menu = slice_menu_.SliceMenu()
        self.p1.SetPopupMenu(menu)
        self.p2.SetPopupMenu(menu)
        self.p3.SetPopupMenu(menu)

        if sys.platform == "win32" or wx.VERSION >= (4, 1):
            self.aui_manager.AddPane(self.p1, self.s1)
            self.aui_manager.AddPane(self.p2, self.s2)
            self.aui_manager.AddPane(self.p3, self.s3)

            nav_windows = self.nav_manager.nav_windows
            for i, window in enumerate(nav_windows.values()):
                self.nav_manager.add_window_to_layout(window=window["window"], row=i + 1)
        else:
            self.aui_manager.AddPane(self.p3, self.s3)
            self.aui_manager.AddPane(self.p2, self.s2)
            self.aui_manager.AddPane(self.p1, self.s1)

            nav_windows = self.nav_manager.nav_windows
            for i, window in enumerate(nav_windows.values()):
                self.nav_manager.add_window_to_layout(window=window["window"], row=i + 1)

        self.aui_manager.Update()

        session = ses.Session()
        if session.GetConfig("mode") != const.MODE_NAVIGATOR:
            Publisher.sendMessage("Hide target button")

    def __bind_events_wx(self):
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_MAXIMIZE, self.OnMaximize)
        self.aui_manager.Bind(wx.aui.EVT_AUI_PANE_RESTORE, self.OnRestore)

    def __bind_events(self):
        Publisher.subscribe(self.OnSetSimultaneousMode, "Set simultaneous multicoil mode")
        Publisher.subscribe(self.OnSetTargetMode, "Set target mode")
        Publisher.subscribe(self.OnStartNavigation, "Start navigation")
        Publisher.subscribe(self._Exit, "Exit")

    def OnSetSimultaneousMode(self, state=True, coils_list=None):
        if state:
            self.nav_manager.SetDualMode(True)
            # Hide slice viewers
            self.aui_manager.GetPane(self.p1).Hide()
            self.aui_manager.GetPane(self.p2).Hide()
            self.aui_manager.GetPane(self.p3).Hide()
        else:
            # Hide the second navigation view
            if len(self.nav_manager.nav_windows) > 1:
                self.nav_manager.SetDualMode(False)
            # Show slice viewers
            self.aui_manager.GetPane(self.p1).Show()
            self.aui_manager.GetPane(self.p2).Show()
            self.aui_manager.GetPane(self.p3).Show()
        self.aui_manager.Update()

    def OnSetTargetMode(self, enabled=True):
        if enabled:
            self.MaximizeViewerVolume()
        else:
            self.RestoreViewerVolume()

    def OnStartNavigation(self):
        self.MaximizeViewerVolume()

    def RestoreViewerVolume(self):
        self.aui_manager.RestoreMaximizedPane()
        Publisher.sendMessage("Hide raycasting widget")
        self.aui_manager.Update()

    def MaximizeViewerVolume(self):
        # Restore volume viewer to make sure it is not already maximized before attempting to maximize it
        # to fix the issue with panes locking into the maximized state where they cannot be restored
        self.RestoreViewerVolume()
        view = self.nav_manager.GetMainView()
        if view is not None:
            self.aui_manager.MaximizePane(self.aui_manager.GetPane(view))
        Publisher.sendMessage("Show raycasting widget")
        self.aui_manager.Update()

    def OnMaximize(self, evt):
        if evt.GetPane().name.startswith("Volume_"):
            Publisher.sendMessage("Show raycasting widget")

    def OnRestore(self, evt):
        if evt.GetPane().name.startswith("Volume_"):
            Publisher.sendMessage("Hide raycasting widget")

    def _Exit(self):
        self.aui_manager.UnInit()

    def Cleanup(self):
        Publisher.unsubscribe(self.ShowRaycastingWidget, "Show raycasting widget")
        Publisher.unsubscribe(self.HideRaycastingWidget, "Hide raycasting widget")
        Publisher.unsubscribe(self.OnSetRaycastPreset, "Update raycasting preset")
        Publisher.unsubscribe(self.RefreshPoints, "Refresh raycasting widget points")
        Publisher.unsubscribe(self.LoadHistogram, "Load histogram")
        Publisher.unsubscribe(self._Exit, "Exit")

        if self.volume_viewer_instance:
            self.volume_viewer_instance.Cleanup()
