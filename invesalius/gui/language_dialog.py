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

import os
import sys
import wx

try:
    from wx.adv import BitmapComboBox
except ImportError:
    from wx.combo import BitmapComboBox

import invesalius.i18n as i18n

from typing import List, Tuple, Union, Optional

file_path: str = os.path.split(__file__)[0]

if hasattr(sys, "frozen") and (
    sys.frozen == "windows_exe" or sys.frozen == "console_exe"
):
    abs_file_path: str = os.path.abspath(
        file_path + os.sep + ".." + os.sep + ".." + os.sep + ".." + os.sep + ".."
    )
    ICON_DIR: str = os.path.abspath(os.path.join(abs_file_path, "icons"))
else:
    ICON_DIR: str = os.path.abspath(os.path.join(file_path, "..", "..", "icons"))

# MAC App
if not os.path.exists(ICON_DIR):
    ICON_DIR: str = os.path.abspath(
        os.path.join(file_path, "..", "..", "..", "..", "..", "icons")
    )


class ComboBoxLanguage:
    def __init__(self, parent: wx.Window) -> None:
        """Initialize combobox bitmap"""

        # Retrieve locales dictionary
        dict_locales: dict = i18n.GetLocales()

        # Retrieve locales names and sort them
        self.locales: List[str] = list(dict_locales.values())
        self.locales.sort()

        # Retrieve locales keys (eg: pt_BR for Portuguese(Brazilian))
        self.locales_key: List[str] = [dict_locales.get_key(value)[0] for value in self.locales]

        # Find out OS locale
        self.os_locale: str = i18n.GetLocaleOS()

        try:
            os_lang: str = self.os_locale[0:2]
        except TypeError:
            os_lang: str = None

        # Default selection will be English
        selection: int = self.locales_key.index("en")

        # Create bitmap combo
        self.bitmapCmb = bitmapCmb = BitmapComboBox(parent, style=wx.CB_READONLY)
        for key in self.locales_key:
            # Based on composed flag filename, get bitmap
            filepath: str = os.path.join(ICON_DIR, "%s.png" % (key))
            bmp: wx.Bitmap = wx.Bitmap(filepath, wx.BITMAP_TYPE_PNG)
            # Add bitmap and info to Combo
            bitmapCmb.Append(dict_locales[key], bmp, key)
            # Set default combo item if available on the list
            if os_lang and key.startswith(os_lang):
                selection = self.locales_key.index(key)
                bitmapCmb.SetSelection(selection)

    def GetComboBox(self) -> wx.BitmapComboBox:
        return self.bitmapCmb

    def GetLocalesKey(self) -> List[str]:
        return self.locales_key


class LanguageDialog(wx.Dialog):
    """Class define the language to be used in the InVesalius,
    exist chcLanguage that list language EN and PT. The language
    selected is writing in the config.ini"""

    def __init__(self, parent: wx.Window = None, startApp: bool = None) -> None:
        super(LanguageDialog, self).__init__(parent, title="")
        self.__TranslateMessage__()
        self.SetTitle(_("Language selection"))
        self.__init_gui()
        self.Centre()

    # def __init_combobox_bitmap__(self):
    #    """Initialize combobox bitmap"""

    #    # Retrieve locales dictionary
    #    dict_locales = i18n.GetLocales()

    #    # Retrieve locales names and sort them
    #    self.locales = dict_locales.values()
    #    self.locales.sort()

    #    # Retrieve locales keys (eg: pt_BR for Portuguese(Brazilian))
    #    self.locales_key = [dict_locales.get_key(value)[0] for value in self.locales]

    #    # Find out OS locale
    #    self.os_locale = i18n.GetLocaleOS()

    #    os_lang = self.os_locale[0:2]

    #    # Default selection will be English
    #    selection = self.locales_key.index('en')

    #    # Create bitmap combo
    #    self.bitmapCmb = bitmapCmb = BitmapComboBox(self, style=wx.CB_READONLY)
    #    for key in self.locales_key:
    #        # Based on composed flag filename, get bitmap
    #        filepath =  os.path.join(ICON_DIR, "%s.png"%(key))
    #        bmp = wx.Bitmap(filepath, wx.BITMAP_TYPE_PNG)
    #        # Add bitmap and info to Combo
    #        bitmapCmb.Append(dict_locales[key], bmp, key)
    #        # Set default combo item if available on the list
    #        if key.startswith(os_lang):
    #            selection = self.locales_key.index(key)
    #            bitmapCmb.SetSelection(selection)

    def GetComboBox(self) -> wx.BitmapComboBox:
        return self.bitmapCmb

    def __init_gui(self) -> None:
        self.txtMsg: wx.StaticText = wx.StaticText(self, -1, label=_("Choose user interface language"))

        btnsizer: wx.StdDialogButtonSizer = wx.StdDialogButtonSizer()

        btn: wx.Button = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn: wx.Button = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        # self.__init_combobox_bitmap__()
        self.cmb: ComboBoxLanguage = ComboBoxLanguage(self)
        self.bitmapCmb: wx.BitmapComboBox = self.cmb.GetComboBox()

        sizer: wx.BoxSizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.txtMsg, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.bitmapCmb, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def GetSelectedLanguage(self) -> str:
        """Return String with Selected Language"""
        self.locales_key: List[str] = self.cmb.GetLocalesKey()
        return self.locales_key[self.bitmapCmb.GetSelection()]

    def __TranslateMessage__(self) -> None:
        """Translate Messages of the Window"""
        os_language: str = i18n.GetLocaleOS()

        if os_language[0:2] == "pt":
            _ = i18n.InstallLanguage("pt_BR")
        elif os_language[0:2] == "es":
            _ = i18n.InstallLanguage("es")
        else:
            _ = i18n.InstallLanguage("en")

    def Cancel(self, event: wx.Event) -> None:
        """Close Frm_Language"""
        self.Close()
        event.Skip()
