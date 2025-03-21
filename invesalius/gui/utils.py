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
# --------------------------------------------------------------------
import logging
from typing import TYPE_CHECKING

import wx

from invesalius.error_handling import (
    show_error,
    show_info,
    show_message,
    show_question,
    show_warning,
)

# Re-export the functions from error_handling for backward compatibility
__all__ = ["show_message", "show_info", "show_warning", "show_error", "show_question"]


# Add these functions to make it easier to migrate existing code
def message_dialog(message, title="InVesalius 3", style=wx.OK | wx.ICON_INFORMATION):
    """
    Show a message dialog and log it with the appropriate level.

    This is a convenience function to make it easier to migrate from wx.MessageBox.

    Parameters:
    -----------
    message : str
        The message to display and log.
    title : str
        The title of the message box.
    style : int
        The style of the message box (wx.OK, wx.ICON_INFORMATION, wx.ICON_WARNING, etc.).

    Returns:
    --------
    int
        The result of the message box.
    """
    # Determine the log level based on the style
    log_level = logging.INFO
    if style & wx.ICON_WARNING:
        log_level = logging.WARNING
    elif style & wx.ICON_ERROR:
        log_level = logging.ERROR

    return show_message(title, message, style, log_level)


if TYPE_CHECKING:
    import wx


def calc_width_needed(widget: "wx.Window", num_chars: int) -> int:
    width, height = widget.GetTextExtent("M" * num_chars)
    return width
