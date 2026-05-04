# -*- coding: UTF-8 -*-

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


import gettext
import locale
import os
import sys
from typing import Callable, Optional

import invesalius.utils as utl
from invesalius.inv_paths import LOCALE_DIR
from invesalius.session import Session


def GetLocales() -> utl.TwoWaysDictionary:
    """Return a dictionary which defines supported languages"""
    d = utl.TwoWaysDictionary(
        {
            "zh_CN": "简体中文",
            "zh_TW": "繁体中文",
            "en": "English",
            "es": "Español",
            "pt_BR": "Português (Brasil)",
            "pt": "Português",
            "fr": "Français",
            "el_GR": "Ελληνική",
            "it": "Italiano",
            "de_DE": "Deutsch",
            "cs": "Čeština",
            "tr_TR": "Türkçe",
            "ca": "Català",
            "ko": "한국어",
            "ro": "Română",
            "ru": "Русский",
            "ja": "日本語",
            "be": "Беларуская",
            "uz": "O‘zbek",
        }
    )
    return d


def GetLocaleOS() -> Optional[str]:
    """Return language of the operating system."""
    if sys.platform == "darwin":
        # The app can't get the location then it has to set
        # it manually returning english
        # locale.setlocale(locale.LC_ALL, "")
        # return locale.getlocale()[0]
        return "en"

    return locale.getdefaultlocale()[0]


def InstallLanguage(language: str) -> Callable[[str], str]:
    file_path = os.path.split(__file__)[0]
    language_dir = LOCALE_DIR
    if hasattr(sys, "frozen") and (
        getattr(sys, "frozen") == "windows_exe" or getattr(sys, "frozen") == "console_exe"
    ):
        abs_file_path = os.path.abspath(file_path + os.sep + "..")
        abs_file_path = os.path.abspath(abs_file_path + os.sep + ".." + os.sep + "..")
        language_dir = os.path.join(abs_file_path, "locale")

    # MAC app
    if not os.path.exists(language_dir):
        abs_file_path = os.path.abspath(os.path.join(file_path, "..", "..", "..", ".."))
        language_dir = os.path.join(abs_file_path, "locale")

    lang = gettext.translation("invesalius", language_dir, languages=[language])

    lang.install()
    return lang.gettext


class Translator:
    def __init__(self):
        self.gettext = None
        self._lang_fallback = "en"

    def __call__(self, message: str) -> str:
        if self.gettext is None:
            lang = Session().GetConfig("language")
            if not lang:
                lang = self._lang_fallback
            self.gettext = InstallLanguage(lang)
        return self.gettext(message)

    def reset(self) -> None:
        self.gettext = None


tr = Translator()
