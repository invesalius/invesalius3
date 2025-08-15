import wx
import wx.aui

from invesalius.i18n import tr as _


class NavigationWindowManager:
    def __init__(self, parent_wx_window, aui_manager):
        self.parent = parent_wx_window
        self.aui_manager = aui_manager
        self.nav_windows = {}  # Dicionário para rastrear as janelas: {id: window_object}

        # Init DualNavigation mode, It is a provisional way to navigate with two simultaneous targets.
        self.create_navigation_window()
        self.create_navigation_window(False)

    def create_navigation_window(self, show=True):
        from invesalius.gui.default_viewers import VolumeViewerCover

        new_window = VolumeViewerCover(self.parent)

        self.nav_windows[len(self.nav_windows)] = new_window

        self.add_window_to_layout(new_window)

        if not show:
            new_window.Hide()
        self.update_layout()

        return new_window

    def add_window_to_layout(self, window):
        info = (
            wx.aui.AuiPaneInfo()
            .Name(f"Volume_{window.GetId()}")
            .Caption(_("Volume"))
            .Centre()
            .MaximizeButton(True)
            .CloseButton(False)
        )
        self.aui_manager.AddPane(window, info)

    def destroy_navigation_window(self, window_id):
        if window_id in self.nav_windows:
            window = self.nav_windows[window_id]

            # 1. Remove da UI
            self.aui_manager.DetachPane(window)

            # 2. Chama a limpeza segura
            window.CleanupAndDestroy()

            # 3. Remove do nosso rastreador
            del self.nav_windows[window_id]

            # 4. Atualiza o layout
            self.update_layout()

    def update_layout(self):
        num_windows = len(self.nav_windows)
        if num_windows == 0:
            return

        # Itera sobre as janelas e aplica as novas configurações de layout
        for i, window in enumerate(self.nav_windows.values()):
            pane_info = self.aui_manager.GetPane(window)

            # Define a posição (esquerda, direita, etc.) e a proporção
            pane_info.Row(1).Layer(i)

        self.aui_manager.Update()

    def SetDualMode(self, state):
        print(self.nav_windows)
        print(len(self.nav_windows))
        if state:
            self.nav_windows[len(self.nav_windows) - 1].Show()
        else:
            self.nav_windows[len(self.nav_windows) - 1].Hide()
        self.update_layout()
