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
import os
import wx
import wx.lib.hyperlink as hl
import wx.lib.platebtn as pbtn
import wx.lib.embeddedimage as emb

BTN_IMPORT_LOCAL = wx.NewId()
BTN_IMPORT_PACS = wx.NewId()
BTN_OPEN_PROJECT = wx.NewId()

WILDCARD_OPEN = "InVesalius 1 project (*.promed)|*.promed|"\
                "InVesalius 2 project (*.inv)|*.inv|"\
                "InVesalius 3 project (*.iv3)|*.iv3|"\
                "All files (*.*)|*.*"


Devil = emb.PyEmbeddedImage(
    "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"
    "kwAAAABJRU5ErkJggg==")


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        
        inner_panel = InnerTaskPanel(self)
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)
                
        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)
        
class InnerTaskPanel(wx.Panel):        
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(wx.Colour(255,255,255))
        self.SetAutoLayout(1)

        # Counter for projects loaded in current GUI
        self.proj_count = 0
        
        # Floating items (to be inserted)
        self.float_hyper_list = []

        # Fixed hyperlink items
        tooltip = wx.ToolTip("Select DICOM files to be reconstructed")
        link_import_local = hl.HyperLinkCtrl(self, -1, "Open DICOM files...")
        link_import_local.SetUnderlines(False, False, False)
        link_import_local.SetColours("BLACK", "BLACK", "BLACK")
        link_import_local.SetToolTip(tooltip)
        link_import_local.AutoBrowse(False)
        link_import_local.UpdateLink()
        link_import_local.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkImport)

        tooltip = wx.ToolTip("Import DICOM files from PACS server")
        link_import_pacs = hl.HyperLinkCtrl(self, -1,"Load from PACS server...")
        link_import_pacs.SetUnderlines(False, False, False)
        link_import_pacs.SetColours("BLACK", "BLACK", "BLACK")
        link_import_pacs.SetToolTip(tooltip)
        link_import_pacs.AutoBrowse(False)
        link_import_pacs.UpdateLink()
        link_import_pacs.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkImportPACS)

        tooltip = wx.ToolTip("Open an existing InVesalius project...")
        link_open_proj = hl.HyperLinkCtrl(self,-1,"Open an existing project...")
        link_open_proj.SetUnderlines(False, False, False)
        link_open_proj.SetColours("BLACK", "BLACK", "BLACK")
        link_open_proj.SetToolTip(tooltip)
        link_open_proj.AutoBrowse(False)
        link_open_proj.UpdateLink()
        link_open_proj.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkOpenProject)
        
        # Image(s) for buttons
        bitmap = Devil.GetBitmap() # 32, 32
        bitmap.SetWidth(20)
        bitmap.SetHeight(20)
        
        # Buttons related to hyperlinks
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_NOBG
        
        button_import_local = pbtn.PlateButton(self, BTN_IMPORT_LOCAL, "",
                                               bitmap, style=button_style)
        button_import_pacs = pbtn.PlateButton(self, BTN_IMPORT_PACS, "", bitmap,
                                              style=button_style)
        button_open_proj = pbtn.PlateButton(self, BTN_OPEN_PROJECT, "",
                                            bitmap, style=button_style)

        # When using PlaneButton, it is necessary to bind events from parent win
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Tags and grid sizer for fixed items
        flag_link = wx.EXPAND|wx.GROW|wx.LEFT|wx.TOP
        flag_button = wx.EXPAND | wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=2, vgap=0)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany([ (link_import_local, 1, flag_link, 3),
                              (button_import_local, 0, flag_button),
                              (link_import_pacs, 1, flag_link, 3),
                              (button_import_pacs, 0, flag_button),
                              (link_open_proj, 1, flag_link, 3),
                              (button_open_proj, 0, flag_button) ])
        
        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(fixed_sizer, 0, wx.GROW|wx.EXPAND)
        
        # Update main sizer and panel layout        
        self.SetSizer(main_sizer)
        self.Fit()
        self.sizer = main_sizer
        
        # Test load and unload specific projects' links
        self.TestLoadProjects()
        #self.UnloadProjects()

        
    def OnLinkImport(self, evt=None):
        print "TODO: Send Signal - Import DICOM files"
        if evt:
            evt.Skip()
        
    def OnLinkImportPACS(self, evt=None):
        print "TODO: Send Signal - Import DICOM files from PACS"
        if evt:
            evt.Skip()
        
    def OnLinkOpenProject(self, evt=None, proj_name=""):
        if proj_name:
            print "TODO: Send Signal - Open project "+ proj_name
        else:
            dlg = wx.FileDialog(self, message="Open project...",
                                defaultDir=os.getcwd(), 
                                defaultFile="", wildcard=WILDCARD_OPEN,
                                style=wx.OPEN|wx.CHANGE_DIR)
            dlg.SetFilterIndex(3)
    
            # Show the dialog and retrieve the user response. If it is the OK response, 
            # process the data.
            if dlg.ShowModal() == wx.ID_OK:
                # This returns a Python list of files that were selected.
                proj_path = dlg.GetPath()
                proj_name = dlg.GetFilename()
                print "TODO: Send Signal - Open project "+ proj_path
                print "TODO: Send Signal - Change frame title "+ proj_name
    
            # Destroy the dialog. Don't do this until you are done with it!
            # BAD things can happen otherwise!
            dlg.Destroy()
            
        if evt:
            evt.Skip()
        
    def OnButton(self, evt):
        id = evt.GetId()
        
        if id == BTN_IMPORT_LOCAL:
            self.OnLinkImport()
        elif id == BTN_IMPORT_PACS:
            self.OnLinkImportPACS()
        else: #elif id == BTN_OPEN_PROJECT:
            self.OnLinkOpenProject()
        
    def TestLoadProjects(self):
        self.LoadProject("test1.inv")
        self.LoadProject("test2.inv")
        self.LoadProject("test3.inv")
    
    def LoadProject(self, proj_name="Unnamed"):
        """
        Load into user interface name of project into import task panel.
        Can be called 3 times in sequence.
        Call UnloadProjects to empty it.
        """
        # TODO: What todo when it is called more than 3 times?
        # TODO: Load from config file last 3 recent projects
        
        if (self.proj_count < 3):
            self.proj_count += 1
        
            # Create name to be plot on GUI
            label = "     "+str(self.proj_count)+". "+proj_name
        
            # Create corresponding hyperlink
            proj_link = hl.HyperLinkCtrl(self, -1, label)
            proj_link.SetUnderlines(False, False, False)
            proj_link.SetColours("BLACK", "BLACK", "BLACK")
            proj_link.AutoBrowse(False)
            proj_link.UpdateLink()
            proj_link.Bind(hl.EVT_HYPERLINK_LEFT,
                       lambda e: self.OnLinkOpenProject(e, proj_name))
            
            # Add to existing frame
            self.sizer.Add(proj_link, 1, wx.GROW | wx.EXPAND | wx.ALL, 2)
            self.Update()

            # Add hyperlink to floating hyperlinks list
            self.float_hyper_list.append(proj_link) 
            
    def UnloadProjects(self):
        """
        Unload all projects from interface into import task panel.
        This will be called when the current project is closed.
        """
        
        # Remove each project from sizer
        for i in xrange(0, self.proj_count):
            self.sizer.Remove(self.float_hyper_list[i])
            
        # Delete hyperlinks
        for hyper in self.float_hyper_list:
            hyper.Destroy()
            del(hyper)
            
        # Update GUI
        self.sizer.Layout()
        self.Update()
        
        # Now we set projects loaded to 0
        self.proj_count = 0
        self.float_hyper_list = []
        