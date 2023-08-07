import sys

import invesalius.constants as const
import invesalius.session as ses
import wx
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher
from invesalius.i18n import tr as _


class Preferences(wx.Dialog):
    def __init__(
        self,
        parent,
        id_=-1,
        title=_("Preferences"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    ):
        super().__init__(parent, id_, title, style=style)

        self.book = wx.Notebook(self, -1)
        self.pnl_viewer2d = Viewer2D(self.book)
        self.pnl_viewer3d = Viewer3D(self.book)
        #  self.pnl_surface = SurfaceCreation(self)
        self.pnl_language = Language(self.book)

        self.book.AddPage(self.pnl_viewer2d, _("2D Visualization"))
        self.book.AddPage(self.pnl_viewer3d, _("3D Visualization"))
        #  self.book.AddPage(self.pnl_surface, _("Surface creation"))
        self.book.AddPage(self.pnl_language, _("Language"))

        btnsizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)

        min_width = max([i.GetMinWidth() for i in (self.book.GetChildren())])
        min_height = max([i.GetMinHeight() for i in (self.book.GetChildren())])
        if sys.platform.startswith("linux"):
            self.book.SetMinClientSize((min_width * 2, min_height * 2))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.book, 1, wx.EXPAND | wx.ALL)
        sizer.Add(btnsizer, 0, wx.GROW | wx.RIGHT | wx.TOP | wx.BOTTOM, 5)
        self.SetSizerAndFit(sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.LoadPreferences, "Load Preferences")

    def GetPreferences(self):
        values = {}
        lang = self.pnl_language.GetSelection()
        viewer = self.pnl_viewer3d.GetSelection()
        viewer2d = self.pnl_viewer2d.GetSelection()
        values.update(lang)
        values.update(viewer)
        values.update(viewer2d)

        return values

    def LoadPreferences(self):
        session = ses.Session()

        rendering = session.GetConfig('rendering')
        surface_interpolation = session.GetConfig('surface_interpolation')
        language = session.GetConfig('language')
        slice_interpolation = session.GetConfig('slice_interpolation')

        values = {
            const.RENDERING: rendering,
            const.SURFACE_INTERPOLATION: surface_interpolation,
            const.LANGUAGE: language,
            const.SLICE_INTERPOLATION: slice_interpolation,
        }

        self.pnl_viewer2d.LoadSelection(values)
        self.pnl_viewer3d.LoadSelection(values)
        self.pnl_language.LoadSelection(values)


class Viewer3D(wx.Panel):
    def __init__(self, parent):

        wx.Panel.__init__(self, parent)

        bsizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Surface"))
        lbl_inter = wx.StaticText(bsizer.GetStaticBox(), -1, _("Interpolation "))
        rb_inter = self.rb_inter = wx.RadioBox(
            bsizer.GetStaticBox(),
            -1,
            "",
            choices=["Flat", "Gouraud", "Phong"],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )

        bsizer.Add(lbl_inter, 0, wx.TOP | wx.LEFT, 10)
        bsizer.Add(rb_inter, 0, wx.TOP | wx.LEFT, 0)

        #  box_rendering = wx.StaticBox(self, -1, _("Volume rendering"))
        bsizer_ren = wx.StaticBoxSizer(wx.VERTICAL, self, _("Volume rendering"))
        lbl_rendering = wx.StaticText(bsizer_ren.GetStaticBox(), -1, _("Rendering"))
        rb_rendering = self.rb_rendering = wx.RadioBox(
            bsizer_ren.GetStaticBox(),
            -1,
            choices=["CPU", _(u"GPU (NVidia video cards only)")],
            majorDimension=2,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )

        bsizer_ren.Add(lbl_rendering, 0, wx.TOP | wx.LEFT, 10)
        bsizer_ren.Add(rb_rendering, 0, wx.TOP | wx.LEFT, 0)

        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer, 1, wx.EXPAND | wx.ALL, 10)
        border.Add(bsizer_ren, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(border)
        self.Layout()

    def GetSelection(self):

        options = {
            const.RENDERING: self.rb_rendering.GetSelection(),
            const.SURFACE_INTERPOLATION: self.rb_inter.GetSelection(),
        }

        return options

    def LoadSelection(self, values):
        rendering = values[const.RENDERING]
        surface_interpolation = values[const.SURFACE_INTERPOLATION]

        self.rb_rendering.SetSelection(int(rendering))
        self.rb_inter.SetSelection(int(surface_interpolation))


class Viewer2D(wx.Panel):
    def __init__(self, parent):

        wx.Panel.__init__(self, parent)

        bsizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Slices"))
        lbl_inter = wx.StaticText(bsizer.GetStaticBox(), -1, _("Interpolated "))
        rb_inter = self.rb_inter = wx.RadioBox(
            bsizer.GetStaticBox(),
            -1,
            choices=[_("Yes"), _("No")],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )

        bsizer.Add(lbl_inter, 0, wx.TOP | wx.LEFT, 10)
        bsizer.Add(rb_inter, 0, wx.TOP | wx.LEFT, 0)

        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(border)
        self.Layout()

    def GetSelection(self):

        options = {const.SLICE_INTERPOLATION: self.rb_inter.GetSelection()}

        return options

    def LoadSelection(self, values):
        value = values[const.SLICE_INTERPOLATION]
        self.rb_inter.SetSelection(int(value))


class Language(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        bsizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Language"))
        self.lg = lg = ComboBoxLanguage(bsizer.GetStaticBox())
        self.cmb_lang = cmb_lang = lg.GetComboBox()
        text = wx.StaticText(
            bsizer.GetStaticBox(),
            -1,
            _("Language settings will be applied \n the next time InVesalius starts."),
        )
        bsizer.Add(cmb_lang, 0, wx.EXPAND | wx.ALL, 10)
        bsizer.AddSpacer(5)
        bsizer.Add(text, 0, wx.EXPAND | wx.ALL, 10)

        border = wx.BoxSizer()
        border.Add(bsizer, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(border)
        self.Layout()

    def GetSelection(self):
        selection = self.cmb_lang.GetSelection()
        locales = self.lg.GetLocalesKey()
        options = {const.LANGUAGE: locales[selection]}
        return options

    def LoadSelection(self, values):
        language = values[const.LANGUAGE]
        locales = self.lg.GetLocalesKey()
        selection = locales.index(language)
        self.cmb_lang.SetSelection(int(selection))


class SurfaceCreation(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.rb_fill_border = wx.RadioBox(
            self,
            -1,
            _("Fill border holes"),
            choices=[_("Yes"), _("No")],
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.rb_fill_border)

        self.SetSizerAndFit(sizer)

    def GetSelection(self):
        return {}

    def LoadSelection(self, values):
        pass
