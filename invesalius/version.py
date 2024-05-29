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

# This file is based on Django code (version 10377):
# django/trunk/django/utils/version.py
# Available at http://code.djangoproject.com/

import os
import os.path
import re

# DEPRECATED. Check the use o Dunamai (https://github.com/mtkennerly/dunamai) to have git commit
def get_svn_revision(path=None):
    """
    Returns the SVN revision in the form pspb-XXXX,
    where XXXX is the revision number.

    Returns pspb-unknown if anything goes wrong, such as an unexpected
    format of internal SVN files.

    If path is provided, it should be a directory whose SVN info you want to
    inspect. If it's not provided, this will use the current
    directory.
    """
    rev = None
    if path is None:
        path = os.curdir
        entries_path = '%s/.svn/entries' % path
 	
    try:
        entries = open(entries_path, 'r').read()
    except IOError:
        pass
    else:
        # Versions >= 7 of the entries file are flat text.  The first line is
        # the version number. The next set of digits after 'dir' is the revision.
        if re.match('(\d+)', entries):
            rev_match = re.search('\d+\s+dir\s+(\d+)', entries)
            if rev_match:
                rev = rev_match.groups()[0]
        # Older XML versions of the file specify revision as an attribute of
        # the first entries node.
        else:
            from xml.dom import minidom
            dom = minidom.parse(entries_path)
            rev = dom.getElementsByTagName('entry')[0].getAttribute('revision')

    if rev:
        return 'pspb-%s' % rev
    return 'pspb-unknown'

