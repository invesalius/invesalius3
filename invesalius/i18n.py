#!/usr/bin/env python
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

import ConfigParser
import locale
import gettext
import os
import sys

import utils as utl

def GetLocales():
    """Return a dictionary which defines supported languages"""
    d = utl.TwoWaysDictionary ({'zh_TW': u'中文',
                                'en': u'English',
                                'es': u'Español',
                                'ko': u'조선어',
                                'pt_BR': u'Português (Brasil)',
                                'pt': u'Português (Portugal)',
                                'fr':u'Français',
                                'el_GR':u'Ελληνική',
                                'it_IT':'Italiano',
                                'de_DE': 'Deutsch'})
    return d

def GetLocaleOS():
        """Return language of the operating system."""
	default_locale = 'en'
	locales_dict = GetLocales()

        if sys.platform == 'darwin':
            locale.setlocale(locale.LC_ALL, "")
            os_locale = locale.getlocale()[0]
	else:
	    os_locale = locale.getdefaultlocale()[0]

        if os_locale:
	    if os_locale in locales_dict.keys():
		default_locale = os_locale
	    else:
		for l in locales_dict:
		    if l.startswith(os_locale):
                        default_locale = l
        return default_locale

def InstallLanguage(language):
    language_dir = os.path.abspath(os.path.join('..','locale'))
    lang = gettext.translation('invesalius', language_dir,\
                                   languages=[language], codeset='utf8')
    # Using unicode
    lang.install(unicode=1)
    return lang.ugettext
