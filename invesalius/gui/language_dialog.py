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
import wx
import wx.combo

import i18n
import constants as const


class LanguageDialog(wx.Dialog):
    """Class define the language to be used in the InVesalius,
    exist chcLanguage that list language EN and PT. The language
    selected is writing in the config.ini"""

    def __init__(self, parent=None, startApp=None):
        super(LanguageDialog, self).__init__(parent, title='Language selection')
        self.__TranslateMessage__()
        self.__init_gui()
        self.Centre()
        
    def __init_combobox_bitmap__(self):
        """Initialize combobox bitmap"""
        
        self.locales = i18n.GetLocales().values()
        
        self.locales_key = i18n.GetLocales().keys()
        self.os_locale = i18n.GetLocaleOS()
        
        self.bitmapCmb = bitmapCmb = wx.combo.BitmapComboBox(self, style=wx.CB_READONLY)

        bmp_brazilian_flag = wx.Bitmap(os.path.join(const.ICON_DIR, "pt_BR.bmp"), wx.BITMAP_TYPE_BMP)
        bmp_english_flag = wx.Bitmap(os.path.join(const.ICON_DIR, "en_GB.bmp"), wx.BITMAP_TYPE_BMP)
        bmp_spanish_flag = wx.Bitmap(os.path.join(const.ICON_DIR, "es.bmp"), wx.BITMAP_TYPE_BMP)

        bitmapCmb.Append(self.locales[0], bmp_english_flag,"en_GB")
        bitmapCmb.Append(self.locales[1], bmp_brazilian_flag,"pt_BR")
        bitmapCmb.Append(self.locales[2], bmp_spanish_flag,"es")

        
        if (self.os_locale[0:2] == 'pt'):
            bitmapCmb.SetSelection(1)
        elif (self.os_locale[0:2] == 'es'):
            bitmapCmb.SetSelection(2)
        else:
            bitmapCmb.SetSelection(0)

    def __init_gui(self):
        self.txtMsg = wx.StaticText(self, -1,
              label=_('Choose user interface language'))

        btnsizer = wx.StdDialogButtonSizer()

        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        self.__init_combobox_bitmap__()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.txtMsg, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.bitmapCmb, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Fit(self)
        self.SetSizer(sizer)
        self.Layout()
        self.Update()
        self.SetAutoLayout(1)

    def GetSelectedLanguage(self):
        """Return String with Selected Language"""
        return self.locales_key[self.bitmapCmb.GetSelection()]

    def __TranslateMessage__(self):
        """Translate Messages of the Window"""
        os_language = i18n.GetLocaleOS()

        if(os_language[0:2] == 'pt'):
            _ = i18n.InstallLanguage('pt_BR')
        elif(os_language[0:2] == 'es'):
            _ = i18n.InstallLanguage('es')
        else:
            _ = i18n.InstallLanguage('en')

    def Cancel(self, event):
        """Close Frm_Language"""
        self.Close()
        event.Skip()
