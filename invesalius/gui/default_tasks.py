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

import wx
import wx.lib.agw.foldpanelbar as fpb

import invesalius.constants as const
import invesalius.gui.data_notebook as nb
import invesalius.gui.task_exporter as exporter
import invesalius.gui.task_importer as importer
import invesalius.gui.task_imports as imports
import invesalius.gui.task_navigator as navigator
import invesalius.gui.task_slice as slice_
import invesalius.gui.task_surface as surface
import invesalius.session as ses
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

FPB_DEFAULT_STYLE = 2621440


def GetCollapsedIconData():
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\
\x00\x00\x00\x1f\xf3\xffa\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\
\x00\x01\x8eIDAT8\x8d\xa5\x93-n\xe4@\x10\x85?g\x03\n6lh)\xc4\xd2\x12\xc3\x81\
\xd6\xa2I\x90\x154\xb9\x81\x8f1G\xc8\x11\x16\x86\xcd\xa0\x99F\xb3A\x91\xa1\
\xc9J&\x96L"5lX\xcc\x0bl\xf7v\xb2\x7fZ\xa5\x98\xebU\xbdz\xf5\\\x9deW\x9f\xf8\
H\\\xbfO|{y\x9dT\x15P\x04\x01\x01UPUD\x84\xdb/7YZ\x9f\xa5\n\xce\x97aRU\x8a\
\xdc`\xacA\x00\x04P\xf0!0\xf6\x81\xa0\xf0p\xff9\xfb\x85\xe0|\x19&T)K\x8b\x18\
\xf9\xa3\xe4\xbe\xf3\x8c^#\xc9\xd5\n\xa8*\xc5?\x9a\x01\x8a\xd2b\r\x1cN\xc3\
\x14\t\xce\x97a\xb2F0Ks\xd58\xaa\xc6\xc5\xa6\xf7\xdfya\xe7\xbdR\x13M2\xf9\
\xf9qKQ\x1fi\xf6-\x00~T\xfac\x1dq#\x82,\xe5q\x05\x91D\xba@\xefj\xba1\xf0\xdc\
zzW\xcff&\xb8,\x89\xa8@Q\xd6\xaaf\xdfRm,\xee\xb1BDxr#\xae\xf5|\xddo\xd6\xe2H\
\x18\x15\x84\xa0q@]\xe54\x8d\xa3\xedf\x05M\xe3\xd8Uy\xc4\x15\x8d\xf5\xd7\x8b\
~\x82\x0fh\x0e"\xb0\xad,\xee\xb8c\xbb\x18\xe7\x8e;6\xa5\x89\x04\xde\xff\x1c\
\x16\xef\xe0p\xfa>\x19\x11\xca\x8d\x8d\xe0\x93\x1b\x01\xd8m\xf3(;x\xa5\xef=\
\xb7w\xf3\x1d$\x7f\xc1\xe0\xbd\xa7\xeb\xa0(,"Kc\x12\xc1+\xfd\xe8\tI\xee\xed)\
\xbf\xbcN\xc1{D\x04k\x05#\x12\xfd\xf2a\xde[\x81\x87\xbb\xdf\x9cr\x1a\x87\xd3\
0)\xba>\x83\xd5\xb97o\xe0\xaf\x04\xff\x13?\x00\xd2\xfb\xa9`z\xac\x80w\x00\
\x00\x00\x00IEND\xaeB`\x82'


def GetCollapsedIconBitmap():
    return wx.Bitmap(GetCollapsedIconImage())


def GetCollapsedIconImage():
    from io import BytesIO

    stream = BytesIO(GetCollapsedIconData())
    return wx.Image(stream)


def GetExpandedIconData():
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\
\x00\x00\x00\x1f\xf3\xffa\x00\x00\x00\x04sBIT\x08\x08\x08\x08|\x08d\x88\x00\
\x00\x01\x9fIDAT8\x8d\x95\x93\xa1\x8e\xdc0\x14EO\xb2\xc4\xd0\xd2\x12\xb7(mI\
\xa4%V\xd1lQT4[4-\x9a\xfe\xc1\xc2|\xc6\xc2~BY\x83:A3E\xd3\xa0*\xa4\xd2\x90H!\
\x95\x0c\r\r\x1fK\x81g\xb2\x99\x84\xb4\x0fY\xd6\xbb\xc7\xf7>=\'Iz\xc3\xbcv\
\xfbn\xb8\x9c\x15 \xe7\xf3\xc7\x0fw\xc9\xbc7\x99\x03\x0e\xfbn0\x99F+\x85R\
\x80RH\x10\x82\x08\xde\x05\x1ef\x90+\xc0\xe1\xd8\ryn\xd0Z-\\A\xb4\xd2\xf7\
\x9e\xfbwoF\xc8\x088\x1c\xbbae\xb3\xe8y&\x9a\xdf\xf5\xbd\xe7\xfem\x84\xa4\
\x97\xccYf\x16\x8d\xdb\xb2a]\xfeX\x18\xc9s\xc3\xe1\x18\xe7\x94\x12cb\xcc\xb5\
\xfa\xb1l8\xf5\x01\xe7\x84\xc7\xb2Y@\xb2\xcc0\x02\xb4\x9a\x88%\xbe\xdc\xb4\
\x9e\xb6Zs\xaa74\xadg[6\x88<\xb7]\xc6\x14\x1dL\x86\xe6\x83\xa0\x81\xba\xda\
\x10\x02x/\xd4\xd5\x06\r\x840!\x9c\x1fM\x92\xf4\x86\x9f\xbf\xfe\x0c\xd6\x9ae\
\xd6u\x8d \xf4\xf5\x165\x9b\x8f\x04\xe1\xc5\xcb\xdb$\x05\x90\xa97@\x04lQas\
\xcd*7\x14\xdb\x9aY\xcb\xb8\\\xe9E\x10|\xbc\xf2^\xb0E\x85\xc95_\x9f\n\xaa/\
\x05\x10\x81\xce\xc9\xa8\xf6><G\xd8\xed\xbbA)X\xd9\x0c\x01\x9a\xc6Q\x14\xd9h\
[\x04\xda\xd6c\xadFkE\xf0\xc2\xab\xd7\xb7\xc9\x08\x00\xf8\xf6\xbd\x1b\x8cQ\
\xd8|\xb9\x0f\xd3\x9a\x8a\xc7\x08\x00\x9f?\xdd%\xde\x07\xda\x93\xc3{\x19C\
\x8a\x9c\x03\x0b8\x17\xe8\x9d\xbf\x02.>\x13\xc0n\xff{PJ\xc5\xfdP\x11""<\xbc\
\xff\x87\xdf\xf8\xbf\xf5\x17FF\xaf\x8f\x8b\xd3\xe6K\x00\x00\x00\x00IEND\xaeB\
`\x82'


def GetExpandedIconBitmap():
    return wx.Bitmap(GetExpandedIconImage())


def GetExpandedIconImage():
    from io import BytesIO

    stream = BytesIO(GetExpandedIconData())
    return wx.Image(stream)


# Main panel
class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5), size=wx.Size(350, 656))

        # sizer = wx.BoxSizer(wx.VERTICAL)
        gbs = wx.GridBagSizer(5, 5)
        # sizer.Add(UpperTaskPanel(self), 5, wx.EXPAND|wx.GROW)
        self.uppertaskpanel = UpperTaskPanel(self)
        gbs.Add(self.uppertaskpanel, (0, 0), flag=wx.EXPAND)
        self.lowertaskpanel = LowerTaskPanel(self)
        # sizer.Add(LowerTaskPanel(self), 3, wx.EXPAND|wx.GROW)
        gbs.Add(self.lowertaskpanel, (1, 0), flag=wx.EXPAND | wx.ALIGN_BOTTOM)

        gbs.AddGrowableCol(0)

        gbs.AddGrowableRow(0, 1)
        gbs.AddGrowableRow(1, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gbs, 1, wx.EXPAND)

        self.gbs = gbs

        # self.SetSizerAndFit(sizer)
        self.SetSizer(sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetNavigationMode, "Set navigation mode")

    def SetNavigationMode(self, status):
        self.navigation_mode_status = status
        session = ses.Session()
        if status:
            session.SetConfig("mode", const.MODE_NAVIGATOR)
        else:
            Publisher.sendMessage("Hide target button")
            session.SetConfig("mode", const.MODE_RP)
        self.gbs.Hide(self.uppertaskpanel)
        self.uppertaskpanel.Destroy()
        self.uppertaskpanel = UpperTaskPanel(self)
        self.gbs.Add(self.uppertaskpanel, (0, 0), flag=wx.EXPAND)
        self.Layout()
        self.Refresh()
        project_status = session.GetConfig("project_status")
        if project_status != const.PROJECT_STATUS_CLOSED:
            Publisher.sendMessage("Load project data")
            Publisher.sendMessage("Enable state project", state=True)


# Lower fold panel
class LowerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=(150, -1))
        fold_panel = fpb.FoldPanelBar(
            self, -1, style=FPB_DEFAULT_STYLE, agwStyle=fpb.FPB_COLLAPSE_TO_BOTTOM
        )

        self.fold_panel = fold_panel
        fold_panel.Bind(fpb.EVT_CAPTIONBAR, self.OnCaptionBar)

        self.enable_items = []
        self.overwrite = False

        gbs = wx.GridBagSizer(5, 5)
        gbs.AddGrowableCol(0, 1)
        self.gbs = gbs

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gbs, 1, wx.GROW | wx.EXPAND)
        self.SetSizer(sizer)

        image_list = wx.ImageList(16, 16)
        image_list.Add(GetExpandedIconBitmap())
        image_list.Add(GetCollapsedIconBitmap())

        # Fold 1 - Data
        item = fold_panel.AddFoldPanel(_("Data"), collapsed=False, foldIcons=image_list)
        # style = fold_panel.GetCaptionStyle(item)
        # col = style.GetFirstColour()
        self.enable_items.append(item)

        # npanel = wx.Panel(self, -1)
        self.npanel = nb.NotebookPanel(item)

        self.__calc_best_size(self.npanel)

        fold_panel.AddFoldPanelWindow(
            item,
            self.npanel,  # fpb.FPB_ALIGN_WIDTH, #Spacing= 0,
            leftSpacing=0,
            rightSpacing=0,
        )

        gbs.AddGrowableRow(0, 1)
        gbs.Add(fold_panel, (0, 0), flag=wx.EXPAND)
        gbs.Layout()
        item.ResizePanel()
        self.ResizeFPB()

        sizer.Fit(self)
        self.Fit()

        self.SetStateProjectClose()
        self.__bind_events()

    def __calc_best_size(self, panel):
        parent = panel.GetParent()
        panel.Reparent(self)

        gbs = self.gbs
        fold_panel = self.fold_panel

        # Calculating the size
        gbs.AddGrowableRow(1, 1)
        # gbs.AddGrowableRow(0, 1)
        gbs.Add(fold_panel, (0, 0), flag=wx.EXPAND)
        gbs.Add(panel, (1, 0), flag=wx.EXPAND)
        gbs.Layout()
        self.Fit()
        size = panel.GetSize()

        gbs.Remove(1)
        gbs.Remove(0)
        gbs.RemoveGrowableRow(1)

        panel.Reparent(parent)
        panel.SetInitialSize(size)
        self.SetInitialSize(self.GetSize())

    def __bind_events(self):
        Publisher.subscribe(self.OnEnableState, "Enable state project")

    def OnCaptionBar(self, evt):
        evt.Skip()
        wx.CallAfter(self.ResizeFPB)

    def OnEnableState(self, state):
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()

    def SetStateProjectClose(self):
        for item in self.enable_items:
            item.Disable()

    def SetStateProjectOpen(self):
        for item in self.enable_items:
            item.Enable()

    def ResizeFPB(self):
        y_needed = self.fold_panel.GetPanelsLength(0, 0)[2]
        x_current, _ = self.GetSize()
        self.SetMinSize((x_current, y_needed))
        self.GetParent().Layout()


# Upper fold panel
class UpperTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        fold_panel = fpb.FoldPanelBar(
            self, -1, wx.DefaultPosition, wx.DefaultSize, FPB_DEFAULT_STYLE, fpb.FPB_SINGLE_FOLD
        )

        image_list = wx.ImageList(16, 16)
        image_list.Add(GetExpandedIconBitmap())
        image_list.Add(GetCollapsedIconBitmap())

        self.enable_items = []
        self.overwrite = False

        session = ses.Session()
        mode = session.GetConfig("mode")

        print("Mode: ", mode)

        if mode == const.MODE_RP:
            tasks = [
                (_("Load data"), importer.TaskPanel),
                (_("Select region of interest"), slice_.TaskPanel),
                (_("Configure 3D surface"), surface.TaskPanel),
                (_("Export data"), exporter.TaskPanel),
            ]

        elif mode == const.MODE_NAVIGATOR:
            tasks = [
                (_("Imports Section"), imports.TaskPanel),
                (_("Navigation Section"), navigator.TaskPanel),
            ]

        for i in range(len(tasks)):
            (name, panel) = tasks[i]

            # Create panel
            if mode == const.MODE_RP:
                item = fold_panel.AddFoldPanel(
                    "%d. %s" % (i + 1, name), collapsed=True, foldIcons=image_list
                )
            else:
                item = fold_panel.AddFoldPanel(f"{name}", collapsed=True, foldIcons=image_list)
            # style = fold_panel.GetCaptionStyle(item)
            # col = style.GetFirstColour()

            # Add panel to FoldPanel
            fold_panel.AddFoldPanelWindow(
                item,
                panel(item),
                # Spacing= 0,
                leftSpacing=0,
                rightSpacing=0,
            )

            # All items, except the first one, should be disabled if
            # no data has been imported initially.
            if i != 0:
                self.enable_items.append(item)

            # If it is related to mask, this value should be kept
            # It is used as reference to set mouse cursor related to
            # slice editor.
            if mode == const.MODE_RP:
                if name == _("Select region of interest"):
                    self.__id_slice = item.GetId()
                elif name == _("Configure 3D surface"):
                    self.__id_surface = item.GetId()

        fold_panel.Expand(fold_panel.GetFoldPanel(0))
        self.fold_panel = fold_panel
        self.image_list = image_list

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(fold_panel, 1, wx.GROW | wx.EXPAND)
        self.sizer = sizer
        self.SetStateProjectClose()
        self.SetSizerAndFit(sizer)
        self.__bind_events()

    def __bind_events(self):
        session = ses.Session()
        mode = session.GetConfig("mode")
        if mode == const.MODE_RP:
            self.fold_panel.Bind(fpb.EVT_CAPTIONBAR, self.OnFoldPressCaption)
            Publisher.subscribe(self.OnOverwrite, "Create surface from index")
            Publisher.subscribe(self.OnFoldSurface, "Fold surface task")
            Publisher.subscribe(self.OnFoldExport, "Fold export task")
        Publisher.subscribe(self.OnEnableState, "Enable state project")
        # Publisher.subscribe(self.SetNavigationMode, "Set navigation mode")

    def OnOverwrite(self, surface_parameters):
        self.overwrite = surface_parameters["options"]["overwrite"]

    def OnFoldSurface(self):
        if not self.overwrite:
            self.fold_panel.Expand(self.fold_panel.GetFoldPanel(2))

    def OnFoldExport(self):
        self.fold_panel.Expand(self.fold_panel.GetFoldPanel(3))

    def OnEnableState(self, state):
        if state:
            self.SetStateProjectOpen()
        else:
            self.SetStateProjectClose()

    def SetStateProjectClose(self):
        self.fold_panel.Expand(self.fold_panel.GetFoldPanel(0))
        for item in self.enable_items:
            item.Disable()

    def SetStateProjectOpen(self):
        session = ses.Session()
        mode = session.GetConfig("mode")
        if mode == const.MODE_RP:
            self.fold_panel.Expand(self.fold_panel.GetFoldPanel(1))
        for item in self.enable_items:
            item.Enable()

    def OnFoldPressCaption(self, evt):
        id = evt.GetTag().GetId()
        # closed = evt.GetFoldStatus()

        if id == self.__id_slice:
            Publisher.sendMessage("Retrieve task slice style")
            Publisher.sendMessage("Fold mask page")
        elif id == self.__id_surface:
            Publisher.sendMessage("Fold surface page")
        else:
            Publisher.sendMessage("Disable task slice style")

        evt.Skip()
        wx.CallAfter(self.ResizeFPB)

    def ResizeFPB(self):
        sizeNeeded = self.fold_panel.GetPanelsLength(0, 0)[2]
        self.fold_panel.SetMinSize((self.fold_panel.GetSize()[0], sizeNeeded))
        self.fold_panel.SetSize((self.fold_panel.GetSize()[0], sizeNeeded))
