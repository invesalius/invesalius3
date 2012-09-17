#!/usr/local/bin/python
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
#-------------------------------------------------------------------------


import wx
import urllib2
import sys
import platform
import i18n


if (len(sys.argv)>2):
    print "Usage: python update.py <language>"
    sys.exit()

if (len(sys.argv)==1):
    print "No language specified. Assuming english (en)."
    lang = 'en'
else:
    lang = sys.argv[1]
    
print lang
# Check if there is a language set (if session file exists
_ = i18n.InstallLanguage(lang)

print "Checking updates..."
URL = "http://www.cti.gov.br/dt3d/invesalius/update/checkupdate_"+sys.platform+"_"+platform.architecture()[0]+".php"
#URL = "http://home.ruppert.com.br/aaa.php"
response = urllib2.urlopen(URL,timeout=5)
last = response.readline().rstrip()
url = response.readline().rstrip()
if (last!="3.0 beta 3"):
    print "  ...New update found!!! -> version:", last #, ", url=",url
    from time import sleep
    sleep(1)
    app=wx.App()
    msg=_("A new version of InVesalius is available. Do you want to open the download website now?")
    title=_("Invesalius Update")
    msgdlg = wx.MessageDialog(None,msg,title, wx.YES_NO | wx.ICON_INFORMATION)
    if (msgdlg.ShowModal()==wx.ID_YES):
        wx.LaunchDefaultBrowser(url)
    msgdlg.Destroy()
    app.MainLoop()


