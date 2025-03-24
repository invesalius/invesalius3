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
import os

import wx

try:
    import wx.lib.agw.hyperlink as hl
except ImportError:
    import wx.lib.hyperlink as hl
import wx.lib.platebtn as pbtn

import invesalius.constants as const
from invesalius import inv_paths
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

BTN_IMPORT_LOCAL = wx.NewIdRef()
BTN_IMPORT_PACS = wx.NewIdRef()
BTN_OPEN_PROJECT = wx.NewIdRef()
BTN_IMPORT_NIFTI = wx.NewIdRef()


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT | wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        backgroud_colour = wx.Colour(255, 255, 255)

        self.SetBackgroundColour(backgroud_colour)
        self.SetAutoLayout(1)

        # Counter for projects loaded in current GUI
        self.proj_count = 0

        # Floating items (to be inserted)
        self.float_hyper_list = []

        # Fixed hyperlink items
        tooltip = _("Select DICOM files to be reconstructed")
        link_import_local = hl.HyperLinkCtrl(self, -1, _("Import DICOM images..."))
        link_import_local.SetUnderlines(False, False, False)
        link_import_local.SetBold(True)
        link_import_local.SetColours("BLACK", "BLACK", "BLACK")
        link_import_local.SetBackgroundColour(backgroud_colour)
        link_import_local.SetToolTip(tooltip)
        link_import_local.AutoBrowse(False)
        link_import_local.UpdateLink()
        link_import_local.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkImport)

        tooltip = _("Select NIFTI files to be reconstructed")
        link_import_nifti = hl.HyperLinkCtrl(self, -1, _("Import NIFTI images..."))
        link_import_nifti.SetUnderlines(False, False, False)
        link_import_nifti.SetBold(True)
        link_import_nifti.SetColours("BLACK", "BLACK", "BLACK")
        link_import_nifti.SetBackgroundColour(backgroud_colour)
        link_import_nifti.SetToolTip(tooltip)
        link_import_nifti.AutoBrowse(False)
        link_import_nifti.UpdateLink()
        link_import_nifti.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkImportNifti)

        # tooltip = "Import DICOM files from PACS server"
        # link_import_pacs = hl.HyperLinkCtrl(self, -1,"Load from PACS server...")
        # link_import_pacs.SetUnderlines(False, False, False)
        # link_import_pacs.SetColours("BLACK", "BLACK", "BLACK")
        # link_import_pacs.SetToolTip(tooltip)
        # link_import_pacs.AutoBrowse(False)
        # link_import_pacs.UpdateLink()
        # link_import_pacs.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkImportPACS)

        tooltip = _("Open an existing InVesalius project...")
        link_open_proj = hl.HyperLinkCtrl(self, -1, _("Open an existing project..."))
        link_open_proj.SetUnderlines(False, False, False)
        link_open_proj.SetBold(True)
        link_open_proj.SetColours("BLACK", "BLACK", "BLACK")
        link_open_proj.SetBackgroundColour(backgroud_colour)
        link_open_proj.SetToolTip(tooltip)
        link_open_proj.AutoBrowse(False)
        link_open_proj.UpdateLink()
        link_open_proj.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkOpenProject)

        # Image(s) for buttons
        BMP_IMPORT = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("file_import_original.png")), wx.BITMAP_TYPE_PNG
        )
        BMP_OPEN_PROJECT = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("file_open_original.png")), wx.BITMAP_TYPE_PNG
        )

        # Buttons related to hyperlinks
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT

        button_import_local = pbtn.PlateButton(
            self, BTN_IMPORT_LOCAL, "", BMP_IMPORT, style=button_style
        )
        button_import_local.SetBackgroundColour(self.GetBackgroundColour())
        button_import_nifti = pbtn.PlateButton(
            self, BTN_IMPORT_NIFTI, "", BMP_IMPORT, style=button_style
        )
        button_import_nifti.SetBackgroundColour(self.GetBackgroundColour())
        button_open_proj = pbtn.PlateButton(
            self, BTN_OPEN_PROJECT, "", BMP_OPEN_PROJECT, style=button_style
        )
        button_open_proj.SetBackgroundColour(self.GetBackgroundColour())

        # When using PlaneButton, it is necessary to bind events from parent win
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Tags and grid sizer for fixed items
        flag_link = wx.EXPAND | wx.GROW | wx.LEFT | wx.TOP
        flag_button = wx.EXPAND | wx.GROW

        # fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=2, vgap=0)
        fixed_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=2, vgap=0)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany(
            [  # (link_import_pacs, 1, flag_link, 3),
                # (button_import_pacs, 0, flag_button),
                (link_import_local, 1, flag_link, 3),
                (button_import_local, 0, flag_button),
                (link_import_nifti, 3, flag_link, 3),
                (button_import_nifti, 0, flag_button),
                (link_open_proj, 5, flag_link, 3),
                (button_open_proj, 0, flag_button),
            ]
        )

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(fixed_sizer, 0, wx.GROW | wx.EXPAND)

        # Update main sizer and panel layout
        self.SetSizer(main_sizer)
        self.Update()
        self.SetAutoLayout(1)
        self.sizer = main_sizer

        # Test load and unload specific projects' links
        self.TestLoadProjects2()
        # self.__bind_events()

    # def __bind_events(self):
    #    Publisher.subscribe(self.OnLoadRecentProjects, "Load recent projects")

    # def OnLoadRecentProjects(self, pubsub_evt):
    #    projects = pubsub_evt.data
    #    for tuple in projects:
    #        filename = tuple[1]
    #        path = tuple[0]
    #        self.LoadProject(filename, path)

    def TestLoadProjects2(self):
        import invesalius.session as ses

        session = ses.Session()
        recent_projects = session.GetConfig("recent_projects")

        for path, filename in recent_projects:
            self.LoadProject(filename, path)

    def TestLoadProjects(self):
        self.LoadProject("test1.inv3", "/Volumes/file/inv3")
        self.LoadProject("test2.inv3", "/Volumes/file/inv3")
        self.LoadProject("test3.inv3", "/Volumes/file/inv3")

    def LoadProject(self, proj_name="Unnamed", proj_dir=""):
        """
        Load into user interface name of invesalius.project into import task panel.
        Can be called 3 times in sequence.
        Call UnloadProjects to empty it.
        """
        # TODO: What todo when it is called more than 3 times?
        # TODO: Load from config file last 3 recent projects

        proj_path = os.path.join(proj_dir, proj_name)

        if self.proj_count < 3:
            self.proj_count += 1

            # Create name to be plot on GUI
            label = "     " + str(self.proj_count) + ". " + proj_name

            # Create corresponding hyperlink
            proj_link = hl.HyperLinkCtrl(self, -1, label)
            proj_link.SetUnderlines(False, False, False)
            proj_link.SetColours("BLACK", "BLACK", "BLACK")
            proj_link.SetBackgroundColour(self.GetBackgroundColour())
            proj_link.AutoBrowse(False)
            proj_link.UpdateLink()
            proj_link.Bind(hl.EVT_HYPERLINK_LEFT, lambda e: self.OpenProject(proj_path))

            # Add to existing frame
            self.sizer.Add(proj_link, 1, wx.GROW | wx.EXPAND | wx.ALL, 2)
            self.Update()

            # Add hyperlink to floating hyperlinks list
            self.float_hyper_list.append(proj_link)

    def OnLinkImport(self, event):
        self.ImportDicom()
        event.Skip()

    def OnLinkImportNifti(self, event):
        self.ImportNifti()
        event.Skip()

    def OnLinkImportPACS(self, event):
        self.ImportPACS()
        event.Skip()

    def OnLinkOpenProject(self, event):
        self.OpenProject()
        event.Skip()

    def ImportPACS(self):
        print("TODO: Send Signal - Import DICOM files from PACS")

    #######
    def ImportDicom(self):
        Publisher.sendMessage("Show import directory dialog")

    def ImportNifti(self):
        Publisher.sendMessage("Show import other files dialog", id_type=const.ID_NIFTI_IMPORT)

    def OpenProject(self, path=None):
        if path:
            Publisher.sendMessage("Open recent project", filepath=path)
        else:
            Publisher.sendMessage("Show open project dialog")

    def SaveAsProject(self):
        Publisher.sendMessage("Show save dialog", save_as=True)

    def SaveProject(self):
        Publisher.sendMessage("Show save dialog", save_as=False)

    def CloseProject(self):
        Publisher.sendMessage("Close Project")

    #######

    def OnButton(self, evt):
        id = evt.GetId()

        if id == BTN_IMPORT_LOCAL:
            self.ImportDicom()
        elif id == BTN_IMPORT_NIFTI:
            self.ImportNifti()
        elif id == BTN_IMPORT_PACS:
            self.ImportPACS()
        else:  # elif id == BTN_OPEN_PROJECT:
            self.OpenProject()

    def UnloadProjects(self):
        """
        Unload all projects from interface into import task panel.
        This will be called when the current project is closed.
        """

        # Remove each project from sizer
        for i in range(0, self.proj_count):
            self.sizer.Remove(self.float_hyper_list[i])

        # Delete hyperlinks
        for hyper in self.float_hyper_list:
            hyper.Destroy()
            del hyper

        # Update GUI
        self.sizer.Layout()
        self.Update()

        # Now we set projects loaded to 0
        self.proj_count = 0
        self.float_hyper_list = []
