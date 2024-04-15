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

try:
    import configparser as ConfigParser
except ImportError:
    import ConfigParser

import locale
import gettext
import os
import sys
from invesalius.session import Session
 
import invesalius.utils as utl
 
def GetLocales(): 
    """Return a dictionary which defines supported languages""" 
    d = utl.TwoWaysDictionary ({'zh_CN': u'简体中文', 
                                'zh_TW': u'繁体中文', 
                                'en': u'English', 
                                'es': u'Español', 
                                'pt_BR': u'Português (Brasil)', 
                                'pt': u'Português',
                                'fr':u'Français', 
                                'el_GR':u'Ελληνική', 
                                'it':'Italiano', 
                                'de_DE': 'Deutsch',
                                'cs': u'Čeština', 
                                'tr_TR': u'Türkçe',
                                'ca': u'Català',
                                'ko': u'한국어',
                                'ro': u'Română',
                                'ru': u'Русский',
                                'ja': u'日本語',
                                'be': u'Беларуская',
                                'uz': u'O‘zbek',}) 
    return d 
 
def GetLocaleOS(): 
        """Return language of the operating system.""" 
        if sys.platform == 'darwin': 
            #The app can't get the location then it has to set
            #it manually returning english
            #locale.setlocale(locale.LC_ALL, "") 
            #return locale.getlocale()[0]
            return "en" 
 
        return locale.getdefaultlocale()[0] 
 
def InstallLanguage(language):
    file_path = os.path.split(__file__)[0]

    abs_file_path = os.path.abspath(file_path + os.sep + "..")

    if hasattr(sys, "frozen") and (sys.frozen == "windows_exe" or sys.frozen == "console_exe"):
        abs_file_path = os.path.abspath(abs_file_path + os.sep + ".." + os.sep + "..")

    language_dir = os.path.join(abs_file_path, 'locale')

    # MAC app
    if not os.path.exists(language_dir):
        abs_file_path = os.path.abspath(os.path.join(file_path, '..', '..',  '..', '..'))
        language_dir = os.path.join(abs_file_path, 'locale')

    lang = gettext.translation('invesalius', language_dir, languages=[language])

    # Using unicode
    try:
        lang.install(unicode=1)
        return lang.ugettext
    except TypeError:
        lang.install()
        return lang.gettext


class Translator:
    def __init__(self):
        self.gettext = None
        self._lang_fallback = 'en'

    def __call__(self, message: str) -> str:
        if self.gettext is None:
            lang = Session().GetConfig('language')
            if not lang:
                lang = self._lang_fallback
            self.gettext = InstallLanguage(lang)
        return self.gettext(message)

    def reset(self):
        self.gettext = None


tr = Translator()
