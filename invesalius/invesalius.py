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

from optparse import OptionParser
import os
import sys

# TODO: This should be called during installation
# ----------------------------------------------------------------------

path = os.path.join(os.path.expanduser('~'), ".invesalius", "presets")
try:
    os.makedirs(path)
except OSError:
    #print "Warning: Directory (probably) exists"
    pass
# ----------------------------------------------------------------------

import wx
import wx.lib.pubsub as ps

from gui.frame import Frame
from control import Controller
from project import Project

class InVesalius(wx.App):
    def OnInit(self):
        self.main = Frame(None)
        self.control = Controller(self.main)
        self.SetAppName("InVesalius 3")
        return True
        
    def ShowFrame(self):
        self.main.Show()
        self.SetTopWindow(self.main)

def parse_comand_line():
    """
    Handle command line arguments.
    """
    parser = OptionParser()

    # Add comand line option debug(-d or --debug) to print all pubsub message is
    # being sent
    parser.add_option("-d", "--debug", action="store_true", dest="debug")
    parser.add_option("-i", "--import", action="store", dest="directory")
    options, args = parser.parse_args()

    if options.debug:
        # The user passed the debug option?
        # Yes!
        # Then all pubsub message must be printed.
        ps.Publisher().subscribe(print_events, ps.ALL_TOPICS)
        
        proj = Project()
        proj.debug = 1
    
    if options.directory:
        # The user passed directory to me?
        import_dir = options.directory
        ps.Publisher().sendMessage('Import directory', import_dir)
    else:
        print "Hey, guy you must pass a directory to me!"

def print_events(data):
    print data.topic

def main():
    application = InVesalius(0)
    parse_comand_line()
    application.ShowFrame()
    application.MainLoop()

if __name__ == '__main__':
    # Add current directory to PYTHONPATH
    sys.path.append(".")
    # Init application
    main()
    
