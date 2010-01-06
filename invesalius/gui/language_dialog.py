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

def create(parent):
    return LanguageDialog(parent)

class LanguageDialog(wx.Dialog):
    """Class define the language to be used in the InVesalius,
    exist chcLanguage that list language EN and PT. The language
    selected is writing in the config.ini"""

    def __init__(self, parent, startApp = None):

        self.__TranslateMessage__()

        self.pre = pre = wx.PreDialog()
        pre.SetExtraStyle(wx.DIALOG_MODAL)

        pre.Create(parent, -1, 'Language selection',  size = wx.Size(250, 150), 
                   pos = wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE)
        self.PostCreate(pre)

        icon_path = os.path.join(const.ICON_DIR, "invesalius.ico")        
        pre.SetIcon(wx.Icon(icon_path, wx.BITMAP_TYPE_ICO))

        self.pnl = wx.Panel(id=-1, name='pnl',
              parent=pre, pos=wx.Point(0, 0), size=wx.Size(250, 160),
              style=wx.TAB_TRAVERSAL)

        self.txtMsg = wx.StaticText(id=1,
              label=_('Choose user interface language'),
              name='txtMsg', parent=self.pnl, pos=wx.Point(15,
              10), size=wx.Size(200, 13), style=0)

        self.bxSizer = wx.BoxSizer(orient=wx.VERTICAL)
        self.bxSizer.AddWindow(self.pnl, 1, wx.GROW|wx.ALIGN_CENTRE)

        btnsizer = wx.StdDialogButtonSizer()

        if wx.Platform != "__WXMSW__":
            btn = wx.ContextHelpButton(self)
            btnsizer.AddButton(btn)

        btnsizer.SetOrientation(wx.CENTER)

        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        self.bxSizer.AddSizer(btnsizer, 1,  wx.GROW|wx.ALIGN_CENTRE)

        self.__init_combobox_bitmap__()

        self.SetSizer(self.bxSizer)


    def __init_combobox_bitmap__(self):
        """Initialize combobox bitmap"""
        
        self.locales = i18n.GetLocales().values()
        
        self.locales_key = i18n.GetLocales().keys()
        self.os_locale = i18n.GetLocaleOS()
        
        
        self.bitmapCmb = bitmapCmb = wx.combo.BitmapComboBox(self.pnl, pos=(32,34), 
                                                             size=(180,22), style=wx.CB_READONLY)

        bmp_brazilian_flag = wx.Bitmap(os.path.join(const.ICON_DIR, "pt_BR.bmp"), wx.BITMAP_TYPE_BMP)
        bmp_english_flag = wx.Bitmap(os.path.join(const.ICON_DIR, "en_GB.bmp"), wx.BITMAP_TYPE_BMP)
        bmp_spanish_flag = wx.Bitmap(os.path.join(const.ICON_DIR, "es.bmp"), wx.BITMAP_TYPE_BMP)

        bitmapCmb.Append(self.locales[0], bmp_brazilian_flag,"pt_BR")
        bitmapCmb.Append(self.locales[1], bmp_english_flag,"en_GB")
        bitmapCmb.Append(self.locales[2], bmp_spanish_flag,"es")


        if (self.os_locale[0:2] == 'pt'):
            bitmapCmb.SetSelection(0)
        elif (self.os_locale[0:2] == 'es'):
            bitmapCmb.SetSelection(2)
        else:
            bitmapCmb.SetSelection(1)

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
            _ = i18n.InstallLanguage('en_GB')

    def Cancel(self, event):
        """Close Frm_Language"""
        self.Close()
        event.Skip()
