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
import multiprocessing
from optparse import OptionParser
import os
import sys

import gui.language_dialog as lang_dlg
import i18n
from session import Session


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


class SplashScreen(wx.SplashScreen):
    def __init__(self):

        session = Session()
        if not (session.ReadSession()):
            session.CreateItens()     
        
        if not(session.ReadLanguage()):
            
            ldlg = lang_dlg.LanguageDialog()

            try:
                if (ldlg.ShowModal() == wx.ID_OK):
                    lang = ldlg.GetSelectedLanguage()
                    session.SetLanguage(lang)
                    _ = i18n.InstallLanguage(lang)
            except(wx._core.PyAssertionError): #TODO: error win64
                    lang = ldlg.GetSelectedLanguage()
                    session.SetLanguage(lang)
                    _ = i18n.InstallLanguage(lang)
                
        else:
            lang = session.GetLanguage()
            _ = i18n.InstallLanguage(lang)
        
        if (lang.startswith('pt')): #Necessy, pt noted as pt_BR
            icon_file = "splash_pt.png"
        else:
            icon_file = "splash_" + lang + ".png"
        
        path = os.path.join("..","icons", icon_file)
        
        bmp = wx.Image(path).ConvertToBitmap()
        
        wx.SplashScreen.__init__(self, bitmap=bmp,
                                 splashStyle=wx.SPLASH_CENTRE_ON_SCREEN | wx.SPLASH_TIMEOUT,
                                 milliseconds=1500, id=-1, parent=None)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        
        from gui.frame import Frame
        from control import Controller
        from project import Project


        self.main = Frame(None)
        self.control = Controller(self.main)

        self.fc = wx.FutureCall(1, self.ShowMain)

    def OnClose(self, evt):
        # Make sure the default handler runs too so this window gets
        # destroyed
        evt.Skip()
        self.Hide()
        
        # if the timer is still running then go ahead and show the
        # main frame now
        if self.fc.IsRunning():
            self.fc.Stop()
            
            session = Session()
            #if not (session.ReadSession()):
            #    session.CreateItens()
        
            lang = session.GetLanguage()
            print lang
            
            i18n.InstallLanguage(lang)
            self.ShowMain()


    def ShowMain(self):
        self.main.Show()

        if self.fc.IsRunning():
            self.Raise()
        
class InVesalius(wx.App):
    def OnInit(self):
        self.SetAppName("InVesalius 3")
        splash = SplashScreen()
        self.control = splash.control
        self.frame = splash.main
        splash.Show()

        return True

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
        
    session = Session()
        
    if options.debug:
        # The user passed the debug option?
        # Yes!
        # Then all pubsub message must be printed.
        ps.Publisher().subscribe(print_events, ps.ALL_TOPICS)
        
        session.debug = 1
    
    if options.dicom_dir:
        # The user passed directory to me?
        import_dir = options.dicom_dir
        ps.Publisher().sendMessage('Import directory', import_dir)
        return True
   
    # Check if there is a file path somewhere in what the user wrote
    else:
        i = len(args) 
        while i:
            i -= 1
            file = args[i]
            if os.path.isfile(file):
                path = os.path.abspath(file)
                ps.Publisher().sendMessage('Open project', path)
                i = 0
                return True
    return False
 

def print_events(data):
    print data.topic

def main():
    application = InVesalius(0)
    parse_comand_line()
    #application.ShowFrame()
    application.MainLoop()

if __name__ == '__main__':
    
    # Needed in win 32 exe
    if hasattr(sys,"frozen") and sys.frozen == "windows_exe":
         multiprocessing.freeze_support()
         
         # wxPython log
         #sys.stdout = open("stdout.log" ,"w")
         sys.stderr = open("stderr.log", "w")
         
    # Add current directory to PYTHONPATH
    sys.path.append(".")
    
    # Init application
    main()
    
