import sys

from functools import partial

import invesalius.constants as const
import invesalius.session as ses
import wx
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher

from invesalius.navigation.tracker import Tracker
from invesalius.navigation.robot import Robot

class Preferences(wx.Dialog):
    def __init__(
        self,
        parent,
        id_=-1,
        title=_("Preferences"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    ):
        super().__init__(parent, id_, title, style=style)
        self.tracker = Tracker()
        self.robot = Robot(
            tracker=self.tracker
        )

        self.book = wx.Notebook(self, -1)
        #self.pnl_viewer2d = Viewer2D(self.book)
        self.pnl_viewer3d = Viewer3D(self.book)
        self.pnl_tracker = TrackerPage(self.book, self.tracker, self.robot)
        #  self.pnl_surface = SurfaceCreation(self)
        self.pnl_language = Language(self.book)

        #self.book.AddPage(self.pnl_viewer2d, _("2D Visualization"))
        self.book.AddPage(self.pnl_viewer3d, _("Visualization"))
        self.book.AddPage(self.pnl_tracker, _("Tracker"))
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
        #viewer2d = self.pnl_viewer2d.GetSelection()
        values.update(lang)
        values.update(viewer)

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

        #self.pnl_viewer2d.LoadSelection(values)
        self.pnl_viewer3d.LoadSelection(values)
        self.pnl_language.LoadSelection(values)


class Viewer3D(wx.Panel):
    def __init__(self, parent):

        wx.Panel.__init__(self, parent)

        bsizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("3D Visualization"))
        lbl_inter = wx.StaticText(bsizer.GetStaticBox(), -1, _("Surface Interpolation "))
        rb_inter = self.rb_inter = wx.RadioBox(
            bsizer.GetStaticBox(),
            -1,
            "",
            choices=["Flat", "Gouraud", "Phong"],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )

        bsizer.Add(lbl_inter, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 10)
        bsizer.Add(rb_inter, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        lbl_rendering = wx.StaticText(bsizer.GetStaticBox(), -1, _("Volume Rendering"))
        rb_rendering = self.rb_rendering = wx.RadioBox(
            bsizer.GetStaticBox(),
            -1,
            choices=["CPU", _(u"GPU (NVidia video cards only)")],
            majorDimension=2,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )
        bsizer.Add(lbl_rendering, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 10)
        bsizer.Add(rb_rendering, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        bsizer_slices = wx.StaticBoxSizer(wx.VERTICAL, self, _("2D Visualization"))
        lbl_inter_sl = wx.StaticText(bsizer_slices.GetStaticBox(), -1, _("Slice Interpolation "))
        rb_inter_sl = self.rb_inter_sl = wx.RadioBox(
            bsizer_slices.GetStaticBox(),
            -1,
            choices=[_("Yes"), _("No")],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )

        bsizer_slices.Add(lbl_inter_sl, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 10)
        bsizer_slices.Add(rb_inter_sl, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer_slices, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        border.Add(bsizer, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        
        self.SetSizerAndFit(border)
        self.Layout()

    def GetSelection(self):

        options = {
            const.RENDERING: self.rb_rendering.GetSelection(),
            const.SURFACE_INTERPOLATION: self.rb_inter.GetSelection(),
            const.SLICE_INTERPOLATION: self.rb_inter_sl.GetSelection()
        }

        return options

    def LoadSelection(self, values):
        rendering = values[const.RENDERING]
        surface_interpolation = values[const.SURFACE_INTERPOLATION]
        slice_interpolation = values[const.SLICE_INTERPOLATION]

        self.rb_rendering.SetSelection(int(rendering))
        self.rb_inter.SetSelection(int(surface_interpolation))
        self.rb_inter_sl.SetSelection(int(slice_interpolation))

class TrackerPage(wx.Panel):
    def __init__(self, parent, tracker, robot):
        wx.Panel.__init__(self, parent)

        self.__bind_events()

        self.tracker = tracker
        self.robot = robot

        # ComboBox for spatial tracker device selection
        tracker_options = [_("Select")] + self.tracker.get_trackers()
        select_tracker_elem = wx.ComboBox(self, -1, "", size=(145, -1),
                                          choices=tracker_options, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        tooltip = wx.ToolTip(_("Choose the tracking device"))
        select_tracker_elem.SetToolTip(tooltip)
        select_tracker_elem.SetSelection(self.tracker.tracker_id)
        select_tracker_elem.Bind(wx.EVT_COMBOBOX, partial(self.OnChooseTracker, ctrl=select_tracker_elem))
        self.select_tracker_elem = select_tracker_elem

        select_tracker_label = wx.StaticText(self, -1, _('Choose the tracking device: '))


        # ComboBox for tracker reference mode
        tooltip = wx.ToolTip(_("Choose the navigation reference mode"))
        choice_ref = wx.ComboBox(self, -1, "",
                                 choices=const.REF_MODE, style=wx.CB_DROPDOWN|wx.CB_READONLY)
        choice_ref.SetSelection(const.DEFAULT_REF_MODE)
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(wx.EVT_COMBOBOX, partial(self.OnChooseReferenceMode, ctrl=select_tracker_elem))
        self.choice_ref = choice_ref

        choice_ref_label = wx.StaticText(self, -1, _('Choose the navigation reference mode: '))

        ref_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=5, vgap=5)
        ref_sizer.AddMany([
            (select_tracker_label, wx.LEFT),
            (select_tracker_elem, wx.RIGHT),
            (choice_ref_label, wx.LEFT),
            (choice_ref, wx.RIGHT)
        ])
        ref_sizer.Layout()

        sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Setup tracker"))
        sizer.Add(ref_sizer, 1, wx.ALL | wx.FIXED_MINSIZE, 20)

        lbl_rob = wx.StaticText(self, -1, _("Robot tracking device :"))
        btn_rob = wx.Button(self, -1, _("Setup"))
        btn_rob.SetToolTip("Setup robot tracking")
        btn_rob.Enable(1)
        btn_rob.Bind(wx.EVT_BUTTON, self.OnRobot)
        self.btn_rob = btn_rob

        rob_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        rob_sizer.AddMany([
            (lbl_rob, 0, wx.LEFT),
            (btn_rob, 0, wx.RIGHT)
        ])

        rob_static_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Setup robot"))
        rob_static_sizer.Add(rob_sizer, 1, wx.ALL | wx.FIXED_MINSIZE, 20)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([
            (sizer, 0, wx.ALL | wx.EXPAND, 10),
            (rob_static_sizer, 0, wx.ALL | wx.EXPAND, 10)
        ])
        self.SetSizerAndFit(main_sizer)
        self.Layout()

    def __bind_events(self):
        pass

    def OnChooseTracker(self, evt, ctrl):
        self.HideParent()

        Publisher.sendMessage('Update status text in GUI',
                              label=_("Configuring tracker ..."))
        if hasattr(evt, 'GetSelection'):
            choice = evt.GetSelection()
        else:
            choice = None

        #self.DisconnectTracker()
        self.tracker.ResetTrackerFiducials()
        self.tracker.SetTracker(choice)
       
        self.ShowParent()
    
    def OnChooseReferenceMode(self, evt, ctrl):
        pass

    def HideParent(self):  # hide preferences dialog box
        self.GetGrandParent().Hide()
    
    def ShowParent(self):  # show preferences dialog box
        self.GetGrandParent().Show()

    def OnRobot(self, evt):
        self.HideParent()

        success = self.robot.ConfigureRobot()
        if success:
            self.robot.InitializeRobot()
        else:
            #self.DisconnectTracker()
            pass
        
        self.ShowParent()


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



# Deprecated code
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

