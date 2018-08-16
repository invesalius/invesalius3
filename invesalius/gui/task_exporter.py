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
import sys

import wx

try:
    import wx.lib.agw.hyperlink as hl
except ImportError:
    import wx.lib.hyperlink as hl

import wx.lib.platebtn as pbtn
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
import invesalius.project as proj

BTN_MASK = wx.NewId()
BTN_PICTURE = wx.NewId()
BTN_SURFACE = wx.NewId()
BTN_REPORT = wx.NewId()
BTN_REQUEST_RP = wx.NewId()

WILDCARD_SAVE_3D = "Inventor (*.iv)|*.iv|"\
                   "PLY (*.ply)|*.ply|"\
                   "Renderman (*.rib)|*.rib|"\
                   "STL (*.stl)|*.stl|"\
                   "STL ASCII (*.stl)|*.stl|"\
                   "VRML (*.vrml)|*.vrml|"\
                   "VTK PolyData (*.vtp)|*.vtp|"\
                   "Wavefront (*.obj)|*.obj|"\
                   "X3D (*.x3d)|*.x3d"

INDEX_TO_TYPE_3D = {0: const.FILETYPE_IV,
                    1: const.FILETYPE_PLY,
                    2: const.FILETYPE_RIB,
                    3: const.FILETYPE_STL,
                    4: const.FILETYPE_STL_ASCII,
                    5: const.FILETYPE_VRML,
                    6: const.FILETYPE_VTP,
                    7: const.FILETYPE_OBJ,
                    8: const.FILETYPE_X3D}
INDEX_TO_EXTENSION = {0: "iv",
                      1: "ply",
                      2: "rib",
                      3: "stl",
                      4: "stl",
                      5: "vrml",
                      6: "vtp",
                      7: "obj",
                      8: "x3d"}

WILDCARD_SAVE_2D = "BMP (*.bmp)|*.bmp|"\
                   "JPEG (*.jpg)|*.jpg|"\
                   "PNG (*.png)|*.png|"\
                   "PostScript (*.ps)|*.ps|"\
                   "Povray (*.pov)|*.pov|"\
                   "TIFF (*.tiff)|*.tiff"
INDEX_TO_TYPE_2D = {0: const.FILETYPE_BMP,
                    1: const.FILETYPE_JPG,
                    2: const.FILETYPE_PNG,
                    3: const.FILETYPE_PS,
                    4: const.FILETYPE_POV,
                    5: const.FILETYPE_OBJ}

WILDCARD_SAVE_MASK = "VTK ImageData (*.vti)|*.vti"


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 1, wx.EXPAND | wx.GROW | wx.BOTTOM | wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class InnerTaskPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        backgroud_colour = wx.Colour(255,255,255)
        self.SetBackgroundColour(backgroud_colour)
        self.SetAutoLayout(1)

        # Counter for projects loaded in current GUI

        # Fixed hyperlink items
        tooltip = wx.ToolTip(_("Export InVesalius screen to an image file"))
        link_export_picture = hl.HyperLinkCtrl(self, -1,
                                            _("Export picture..."))
        link_export_picture.SetUnderlines(False, False, False)
        link_export_picture.SetBold(True)
        link_export_picture.SetColours("BLACK", "BLACK", "BLACK")
        link_export_picture.SetBackgroundColour(self.GetBackgroundColour())
        link_export_picture.SetToolTip(tooltip)
        link_export_picture.AutoBrowse(False)
        link_export_picture.UpdateLink()
        link_export_picture.Bind(hl.EVT_HYPERLINK_LEFT,
                                 self.OnLinkExportPicture)

        tooltip = wx.ToolTip(_("Export 3D surface"))
        link_export_surface = hl.HyperLinkCtrl(self, -1,_("Export 3D surface..."))
        link_export_surface.SetUnderlines(False, False, False)
        link_export_surface.SetBold(True)
        link_export_surface.SetColours("BLACK", "BLACK", "BLACK")
        link_export_surface.SetBackgroundColour(self.GetBackgroundColour())
        link_export_surface.SetToolTip(tooltip)
        link_export_surface.AutoBrowse(False)
        link_export_surface.UpdateLink()
        link_export_surface.Bind(hl.EVT_HYPERLINK_LEFT,
                              self.OnLinkExportSurface)

        #tooltip = wx.ToolTip(_("Export 3D mask (voxels)"))
        #link_export_mask = hl.HyperLinkCtrl(self, -1,_("Export mask..."))
        #link_export_mask.SetUnderlines(False, False, False)
        #link_export_mask.SetColours("BLACK", "BLACK", "BLACK")
        #link_export_mask.SetToolTip(tooltip)
        #link_export_mask.AutoBrowse(False)
        #link_export_mask.UpdateLink()
        #link_export_mask.Bind(hl.EVT_HYPERLINK_LEFT,
        #                      self.OnLinkExportMask)


        #tooltip = wx.ToolTip("Request rapid prototyping services")
        #link_request_rp = hl.HyperLinkCtrl(self,-1,"Request rapid prototyping...")
        #link_request_rp.SetUnderlines(False, False, False)
        #link_request_rp.SetColours("BLACK", "BLACK", "BLACK")
        #link_request_rp.SetToolTip(tooltip)
        #link_request_rp.AutoBrowse(False)
        #link_request_rp.UpdateLink()
        #link_request_rp.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkRequestRP)

        #tooltip = wx.ToolTip("Open report tool...")
        #link_report = hl.HyperLinkCtrl(self,-1,"Open report tool...")
        #link_report.SetUnderlines(False, False, False)
        #link_report.SetColours("BLACK", "BLACK", "BLACK")
        #link_report.SetToolTip(tooltip)
        #link_report.AutoBrowse(False)
        #link_report.UpdateLink()
        #link_report.Bind(hl.EVT_HYPERLINK_LEFT, self.OnLinkReport)


        # Image(s) for buttons
        if sys.platform == 'darwin':
            BMP_EXPORT_SURFACE = wx.Bitmap(\
                                  os.path.join(const.ICON_DIR, "surface_export_original.png"),
                                  wx.BITMAP_TYPE_PNG).ConvertToImage()\
                                          .Rescale(25, 25).ConvertToBitmap()
            BMP_TAKE_PICTURE = wx.Bitmap(\
                                 os.path.join(const.ICON_DIR, "tool_photo_original.png"),
                                 wx.BITMAP_TYPE_PNG).ConvertToImage()\
                                          .Rescale(25, 25).ConvertToBitmap()

            #BMP_EXPORT_MASK = wx.Bitmap("../icons/mask.png",
            #                            wx.BITMAP_TYPE_PNG)
        else:
            BMP_EXPORT_SURFACE = wx.Bitmap(os.path.join(const.ICON_DIR, "surface_export.png"),
                                        wx.BITMAP_TYPE_PNG).ConvertToImage()\
                                          .Rescale(25, 25).ConvertToBitmap()

            BMP_TAKE_PICTURE = wx.Bitmap(os.path.join(const.ICON_DIR, "tool_photo.png"),
                                     wx.BITMAP_TYPE_PNG).ConvertToImage()\
                                          .Rescale(25, 25).ConvertToBitmap()

            #BMP_EXPORT_MASK = wx.Bitmap("../icons/mask_small.png",
            #                            wx.BITMAP_TYPE_PNG)



        # Buttons related to hyperlinks
        button_style = pbtn.PB_STYLE_SQUARE | pbtn.PB_STYLE_DEFAULT

        button_picture = pbtn.PlateButton(self, BTN_PICTURE, "",
                                               BMP_TAKE_PICTURE,
                                               style=button_style)
        button_picture.SetBackgroundColour(self.GetBackgroundColour())
        self.button_picture = button_picture

        button_surface = pbtn.PlateButton(self, BTN_SURFACE, "",
                                                BMP_EXPORT_SURFACE,
                                              style=button_style)
        button_surface.SetBackgroundColour(self.GetBackgroundColour())
        #button_mask = pbtn.PlateButton(self, BTN_MASK, "",
        #                                BMP_EXPORT_MASK,
        #                                style=button_style)
        #button_request_rp = pbtn.PlateButton(self, BTN_REQUEST_RP, "",
        #                                    BMP_IMPORT, style=button_style)
        #button_report = pbtn.PlateButton(self, BTN_REPORT, "",
        #                                 BMP_IMPORT,
        #                                 style=button_style)

        # When using PlaneButton, it is necessary to bind events from parent win
        self.Bind(wx.EVT_BUTTON, self.OnButton)

        # Tags and grid sizer for fixed items
        flag_link = wx.EXPAND|wx.GROW|wx.LEFT|wx.TOP
        flag_button = wx.EXPAND | wx.GROW

        fixed_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=2, vgap=0)
        fixed_sizer.AddGrowableCol(0, 1)
        fixed_sizer.AddMany([ (link_export_picture, 1, flag_link, 3),
                              (button_picture, 0, flag_button),
                              (link_export_surface, 1, flag_link, 3),
                              (button_surface, 0, flag_button),])
                              #(link_export_mask, 1, flag_link, 3),
                              #(button_mask, 0, flag_button)])
                              #(link_report, 0, flag_link, 3),
                              #(button_report, 0, flag_button),
                              #(link_request_rp, 1, flag_link, 3),
                              #(button_request_rp, 0, flag_button)])

        # Add line sizers into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(fixed_sizer, 0, wx.GROW|wx.EXPAND)

        # Update main sizer and panel layout
        self.SetSizer(main_sizer)
        self.Fit()
        self.sizer = main_sizer
        self.__init_menu()

    def __init_menu(self):


        menu = wx.Menu()
        self.id_to_name = {const.AXIAL:_("Axial slice"),
                           const.CORONAL:_("Coronal slice"),
                           const.SAGITAL:_("Sagittal slice"),
                           const.VOLUME:_("Volume")}

        for id in self.id_to_name:
            item = wx.MenuItem(menu, id, self.id_to_name[id])
            menu.AppendItem(item)

        self.menu_picture = menu
        menu.Bind(wx.EVT_MENU, self.OnMenuPicture)

    def OnMenuPicture(self, evt):
        id = evt.GetId()
        value = dlg.ExportPicture(self.id_to_name[id])
        if value:
            filename, filetype = value
            Publisher.sendMessage('Export picture to file',
                                  orientation=id, filename=filename, filetype=filetype)



    def OnLinkExportPicture(self, evt=None):
        self.button_picture.PopupMenu(self.menu_picture)


    def OnLinkExportMask(self, evt=None):
        project = proj.Project()
        if sys.platform == 'win32':
            project_name = project.name
        else:
            project_name = project.name+".vti"


        dlg = wx.FileDialog(None,
                            "Save mask as...", # title
                            "", # last used directory
                            project_name, # filename
                            WILDCARD_SAVE_MASK,
                            wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
        dlg.SetFilterIndex(0) # default is VTI

        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            extension = "vti"
            if sys.platform != 'win32':
                if filename.split(".")[-1] != extension:
                    filename = filename + "."+ extension
            filetype = const.FILETYPE_IMAGEDATA
            Publisher.sendMessage('Export mask to file',
                                  filename=filename,
                                  filetype=filetype)


    def OnLinkExportSurface(self, evt=None):
        "OnLinkExportSurface"
        project = proj.Project()
        n_surface = 0

        for index in project.surface_dict:
            if project.surface_dict[index].is_shown:
                n_surface += 1

        if n_surface:
            if sys.platform == 'win32':
                project_name = project.name
            else:
                project_name = project.name+".stl"


            dlg = wx.FileDialog(None,
                                _("Save 3D surface as..."), # title
                                "", # last used directory
                                project_name, # filename
                                WILDCARD_SAVE_3D,
                                wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
            dlg.SetFilterIndex(3) # default is STL

            if dlg.ShowModal() == wx.ID_OK:
                filetype_index = dlg.GetFilterIndex()
                filetype = INDEX_TO_TYPE_3D[filetype_index]
                filename = dlg.GetPath()
                extension = INDEX_TO_EXTENSION[filetype_index]
                if sys.platform != 'win32':
                    if filename.split(".")[-1] != extension:
                        filename = filename + "."+ extension
                Publisher.sendMessage('Export surface to file',
                                      filename=filename, filetype=filetype)
                if not os.path.exists(filename):
                    dlg = wx.MessageDialog(None,
                                       _("It was not possible to save the surface."),
                                       _("Error saving surface"),
                                       wx.OK | wx.ICON_ERROR)
                    dlg.ShowModal()
                    dlg.Destroy()
        else:
            dlg = wx.MessageDialog(None,
                    _("You need to create a surface and make it ") +
                    _("visible before exporting it."),
                    'InVesalius 3',
                    wx.OK | wx.ICON_INFORMATION)
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()

    def OnLinkRequestRP(self, evt=None):
        pass

    def OnLinkReport(self, evt=None):
        pass

    def OnButton(self, evt):
        id = evt.GetId()
        if id == BTN_PICTURE:
            self.OnLinkExportPicture()
        elif id == BTN_SURFACE:
            self.OnLinkExportSurface()
        elif id == BTN_REPORT:
            self.OnLinkReport()
        elif id == BTN_REQUEST_RP:
            self.OnLinkRequestRP()
        else:# id == BTN_MASK:
            self.OnLinkExportMask()
