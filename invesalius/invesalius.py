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
from session import Session

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
    parser.add_option("-i", "--import", action="store", dest="dicom_dir")

    options, args = parser.parse_args()
    print "ARRRRRGHs", args


    if options.debug:
        # The user passed the debug option?
        # Yes!
        # Then all pubsub message must be printed.
        ps.Publisher().subscribe(print_events, ps.ALL_TOPICS)
        
        session = Session()
        session.debug = 1
    
    elif options.dicom_dir:
        # The user passed directory to me?
        import_dir = options.dicom_dir
        ps.Publisher().sendMessage('Import directory', import_dir)
        #print "Hey, guy you must pass a directory to me!"
    #else:
    #    print "Hey, guy, you need to pass a inv3 file to me!"
   
    # Check if there is a file path somewhere in what the user wrote
    i = len(args) 
    while i:
        i -= 1
        file = args[i]
        if os.path.isfile(file):
            path = os.path.abspath(file)
            ps.Publisher().sendMessage('Open project', path)
            i = 0
 

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
    
