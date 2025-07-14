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
# --------------------------------------------------------------------------

import wx
import wx.py.shell

from invesalius.i18n import tr as _


class InteractiveShellPanel(wx.Panel):
    """
    Interactive Python shell panel for debugging and development.
    """

    def __init__(self, parent, app_context={}, introText=""):
        """
        Initialize the shell panel.

        Args:
            parent: Parent window
            app_context: Dictionary of objects to expose in shell namespace
        """
        super().__init__(parent)

        # Create shell widget
        self.shell = wx.py.shell.Shell(self, locals=app_context, introText=introText)

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.shell, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def update_context(self, new_context):
        """Update the shell's local namespace with new objects."""
        if hasattr(self.shell, "interp"):
            self.shell.interp.locals.update(new_context)


class InteractiveShellFrame(wx.Frame):
    """
    Standalone frame for the interactive shell.
    """

    def __init__(self, parent, app_context=None, introText=""):
        """
        Initialize the shell frame.

        Args:
            parent: Parent window
            app_context: Dictionary of objects to expose in shell namespace
        """
        super().__init__(
            parent,
            title=_("InVesalius Interactive Python Shell"),
            size=(800, 600),
            style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )

        # Create shell panel
        self.shell_panel = InteractiveShellPanel(self, app_context, introText)

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.shell_panel, 1, wx.EXPAND)
        self.SetSizer(sizer)

        # Center on parent
        self.CenterOnParent()

    def update_context(self, new_context):
        """Update the shell's context."""
        self.shell_panel.update_context(new_context)
