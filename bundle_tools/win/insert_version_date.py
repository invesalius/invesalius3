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

# -*- coding: UTF-8 -*-

import pathlib
import sys


def edit_file(path: str, date: str, commit_hash: str, nightly: bool) -> None:
    """
    This code inserts the date and hash of the last commit into dialogs.py so that
    the user can provide this information (about window) in any support request.

    Args:
        path (str): Path to the file to modify.
        date (str): Release date.
        commit_hash (str): Git commit hash.
        nightly (bool): Whether this is a nightly build.
    """

    with open(path, "r") as file:
        content = file.read()

    # path = invesalius/gui/dialog.py
    to_replace = "info.Version = const.INVESALIUS_VERSION"

    if nightly:
        new_content = (
            to_replace
            + " + '(Nightly)' + '\\n' + 'Release date: '+ '"
            + date
            + "'+'\\n Commit hash: "
            + commit_hash[0:9]
            + "...'"
        )
    else:
        new_content = (
            to_replace
            + "+ '\\n' + 'Release date: '+ '"
            + date
            + "'+'\\n Commit hash: "
            + commit_hash[0:9]
            + "...'"
        )

    with open(path, "w") as file:
        file.write(content.replace(to_replace, new_content))


if __name__ == "__main__":
    path: str = str(pathlib.Path(sys.argv[1]))
    date: str = sys.argv[2]
    commit_hash: str = sys.argv[3]
    nightly: bool = sys.argv[4].lower() == "true"

    edit_file(path, date, commit_hash, nightly)
