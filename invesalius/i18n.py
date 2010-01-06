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

import constants as const

def GetLocales():
    """Return a dictionary which defines supported languages"""
    locale_descriptions = {'es': u'Español',
                           'en_GB': u'English',
                           'pt_BR': u'Português (Brasil)'}
    return locale_descriptions
    
def GetLocaleOS():
        """Return language of the operating system."""
        os_language = locale.getdefaultlocale()[0]
        return os_language
    
def InstallLanguage(language):
    
    lang = gettext.translation('invesalius', const.LANGUAGE_DIR,\
                                   languages=[language], codeset='utf8')
    lang.install()
    return lang.gettext
