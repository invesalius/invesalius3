import os
import sys
from functools import partial

import numpy as np
import wx

import invesalius.constants as const
import invesalius.data.vtk_utils as vtk_utils
import invesalius.gui.dialogs as dlg
import invesalius.gui.log as log
import invesalius.session as ses
from invesalius import inv_paths, utils
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.i18n import tr as _
from invesalius.navigation.navigation import Navigation
from invesalius.navigation.robot import Robot
from invesalius.navigation.tracker import Tracker
from invesalius.net.neuronavigation_api import NeuronavigationApi
from invesalius.net.pedal_connection import PedalConnector
from invesalius.pubsub import pub as Publisher


class Preferences(wx.Dialog):
    def __init__(
        self,
        parent,
        page,
        id_=-1,
        title=_("Preferences"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    ):
        super().__init__(parent, id_, title, style=style)

        self.book = wx.Notebook(self, -1)

        self.have_log_tab = 1

        self.visualization_tab = VisualizationTab(self.book)
        self.language_tab = LanguageTab(self.book)
        if self.have_log_tab == 1:
            self.logging_tab = LoggingTab(self.book)

        self.book.AddPage(self.visualization_tab, _("Visualization"))

        session = ses.Session()
        mode = session.GetConfig("mode")
        if mode == const.MODE_NAVIGATOR:
            tracker = Tracker()
            robot = Robot()
            neuronavigation_api = NeuronavigationApi()
            pedal_connector = PedalConnector(neuronavigation_api, self)
            navigation = Navigation(
                pedal_connector=pedal_connector,
                neuronavigation_api=neuronavigation_api,
            )

            self.navigation_tab = NavigationTab(self.book, navigation)
            self.tracker_tab = TrackerTab(self.book, tracker, robot)
            self.object_tab = ObjectTab(
                self.book, navigation, tracker, pedal_connector, neuronavigation_api
            )

            self.book.AddPage(self.navigation_tab, _("Navigation"))
            self.book.AddPage(self.tracker_tab, _("Tracker"))
            self.book.AddPage(self.object_tab, _("TMS Coil"))

        self.book.AddPage(self.language_tab, _("Language"))
        if self.have_log_tab == 1:
            self.book.AddPage(self.logging_tab, _("Logging"))

        btnsizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        min_width = max([i.GetMinWidth() for i in (self.book.GetChildren())])
        min_height = max([i.GetMinHeight() for i in (self.book.GetChildren())])
        if sys.platform.startswith("linux"):
            self.book.SetMinClientSize((min_width * 2, min_height * 2))
        self.book.SetSelection(page)

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

        lang = self.language_tab.GetSelection()
        viewer = self.visualization_tab.GetSelection()

        values.update(lang)
        values.update(viewer)

        if self.have_log_tab == 1:
            logging = self.logging_tab.GetSelection()
            values.update(logging)

        return values

    def LoadPreferences(self):
        session = ses.Session()
        rendering = session.GetConfig("rendering")
        surface_interpolation = session.GetConfig("surface_interpolation")
        language = session.GetConfig("language")
        slice_interpolation = session.GetConfig("slice_interpolation")

        # logger = log.MyLogger()
        file_logging = log.invLogger.GetConfig("file_logging")
        file_logging_level = log.invLogger.GetConfig("file_logging_level")
        append_log_file = log.invLogger.GetConfig("append_log_file")
        logging_file = log.invLogger.GetConfig("logging_file")
        console_logging = log.invLogger.GetConfig("console_logging")
        console_logging_level = log.invLogger.GetConfig("console_logging_level")

        mode = session.GetConfig("mode")

        if mode == const.MODE_NAVIGATOR:
            self.object_tab.LoadConfig()

        values = {
            const.RENDERING: rendering,
            const.SURFACE_INTERPOLATION: surface_interpolation,
            const.LANGUAGE: language,
            const.SLICE_INTERPOLATION: slice_interpolation,
            const.FILE_LOGGING: file_logging,
            const.FILE_LOGGING_LEVEL: file_logging_level,
            const.APPEND_LOG_FILE: append_log_file,
            const.LOGFILE: logging_file,
            const.CONSOLE_LOGGING: console_logging,
            const.CONSOLE_LOGGING_LEVEL: console_logging_level,
        }

        self.visualization_tab.LoadSelection(values)
        self.language_tab.LoadSelection(values)
        if self.have_log_tab == 1:
            self.logging_tab.LoadSelection(values)


class VisualizationTab(wx.Panel):
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
            choices=["CPU", _("GPU (NVidia video cards only)")],
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
            const.SLICE_INTERPOLATION: self.rb_inter_sl.GetSelection(),
        }
        return options

    def LoadSelection(self, values):
        rendering = values[const.RENDERING]
        surface_interpolation = values[const.SURFACE_INTERPOLATION]
        slice_interpolation = values[const.SLICE_INTERPOLATION]

        self.rb_rendering.SetSelection(int(rendering))
        self.rb_inter.SetSelection(int(surface_interpolation))
        self.rb_inter_sl.SetSelection(int(slice_interpolation))


class LoggingTab(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        # File Logging Selection
        bsizer_logging = wx.StaticBoxSizer(wx.VERTICAL, self, _("File Logging Options"))

        bsizer_file_logging = wx.BoxSizer(wx.HORIZONTAL)

        rb_file_logging = self.rb_file_logging = wx.RadioBox(
            self,
            -1,
            label="Do Logging",
            choices=["No", "Yes"],
            majorDimension=2,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER | wx.FIXED_MINSIZE,
        )
        bsizer_file_logging.Add(rb_file_logging, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5)

        rb_append_file = self.rb_append_file = wx.RadioBox(
            self,  # bsizer_file_logging.GetStaticBox(),
            -1,
            label="Append File",
            choices=["No", "Yes"],
            majorDimension=2,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER | wx.FIXED_MINSIZE,
        )

        lbl_file_logging_level = wx.StaticText(self, -1, _(" Logging Level "))
        cb_file_logging_level = self.cb_file_logging_level = wx.Choice(
            self,
            -1,
            name="Logging Level",
            choices=const.LOGGING_LEVEL_TYPES,
        )
        bsizer_file_logging.Add(rb_append_file, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5)
        bsizer_file_logging.Add(lbl_file_logging_level, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5)
        bsizer_file_logging.Add(cb_file_logging_level, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5)

        bsizer_logging.Add(bsizer_file_logging, 0, wx.TOP | wx.LEFT | wx.EXPAND, 0)

        bsizer_log_filename = wx.BoxSizer(wx.HORIZONTAL)

        lbl_log_file_label = wx.StaticText(self, -1, _("File:"))
        tc_log_file_name = self.tc_log_file_name = wx.TextCtrl(
            self, -1, "", style=wx.TE_READONLY | wx.TE_LEFT, size=(300, -1)
        )
        tc_log_file_name.SetForegroundColour(wx.BLUE)
        bt_log_file_select = wx.Button(self, label="Modify")  # bsizer_file_logging.GetStaticBox()
        bt_log_file_select.Bind(wx.EVT_BUTTON, self.OnModifyButton)
        bsizer_log_filename.Add(
            lbl_log_file_label, 0, wx.TOP | wx.LEFT, 0
        )  # | wx.FIXED_MINSIZE, 0)
        bsizer_log_filename.Add(tc_log_file_name, 0, wx.TOP | wx.LEFT, 0)  # | wx.FIXED_MINSIZE, 0)
        bsizer_log_filename.Add(
            bt_log_file_select, 0, wx.TOP | wx.LEFT, 0
        )  # | wx.FIXED_MINSIZE, 0)
        bsizer_logging.Add(bsizer_log_filename, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        # Console Logging Selection
        bsizer_console_logging = wx.StaticBoxSizer(
            wx.HORIZONTAL, self, _(" Console Logging Options")
        )

        rb_console_logging = self.rb_console_logging = wx.RadioBox(
            bsizer_console_logging.GetStaticBox(),
            -1,
            label="Do logging",
            choices=["No", "Yes"],
            majorDimension=2,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER | wx.FIXED_MINSIZE,
        )
        bsizer_console_logging.Add(rb_console_logging, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5)
        lbl_console_logging_level = wx.StaticText(
            bsizer_console_logging.GetStaticBox(), -1, _(" Logging Level ")
        )
        cb_console_logging_level = self.cb_console_logging_level = wx.Choice(
            bsizer_console_logging.GetStaticBox(),
            -1,
            choices=const.LOGGING_LEVEL_TYPES,
        )
        bsizer_console_logging.Add(
            lbl_console_logging_level, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5
        )
        bsizer_console_logging.Add(
            cb_console_logging_level, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 5
        )

        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer_logging, 1, wx.EXPAND | wx.ALL, 10)  # | wx.FIXED_MINSIZE, 10)
        border.Add(bsizer_console_logging, 1, wx.EXPAND | wx.ALL, 10)  # | wx.FIXED_MINSIZE, 10)
        self.SetSizerAndFit(border)

        self.Layout()

    @log.call_tracking_decorator
    def OnModifyButton(self, e):
        logging_file = self.tc_log_file_name.GetValue()
        path, fname = os.path.split(logging_file)
        dlg = wx.FileDialog(
            self,
            message="Save Log Contents",
            defaultDir=path,  # os.getcwd(),
            defaultFile=fname,  # default_file,
            wildcard="Log files (*.log)|*.log",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dlg.ShowModal() == wx.ID_CANCEL:
            dlg.Destroy()
            return False

        file_path = dlg.GetPath()
        self.tc_log_file_name.SetValue(file_path)
        dlg.Destroy()
        return True

    def GetSelection(self):
        options = {
            const.FILE_LOGGING: self.rb_file_logging.GetSelection(),
            const.FILE_LOGGING_LEVEL: self.cb_file_logging_level.GetSelection(),
            const.APPEND_LOG_FILE: self.rb_append_file.GetSelection(),
            const.LOGFILE: self.tc_log_file_name.GetValue(),
            const.CONSOLE_LOGGING: self.rb_console_logging.GetSelection(),
            const.CONSOLE_LOGGING_LEVEL: self.cb_console_logging_level.GetSelection(),
        }
        # session = ses.Session()
        # logger = log.MyLogger()

        file_logging = self.rb_file_logging.GetSelection()
        log.invLogger.SetConfig("file_logging", file_logging)
        file_logging_level = self.cb_file_logging_level.GetSelection()
        log.invLogger.SetConfig("file_logging_level", file_logging_level)
        append_log_file = self.rb_append_file.GetSelection()
        log.invLogger.SetConfig("append_log_file", append_log_file)
        logging_file = self.tc_log_file_name.GetValue()
        log.invLogger.SetConfig("logging_file", logging_file)
        console_logging = self.rb_console_logging.GetSelection()
        log.invLogger.SetConfig("console_logging", console_logging)
        console_logging_level = self.cb_console_logging_level.GetSelection()
        log.invLogger.SetConfig("console_logging_level", console_logging_level)
        log.invLogger.configureLogging()

        return options

    def LoadSelection(self, values):
        file_logging = values[const.FILE_LOGGING]
        file_logging_level = values[const.FILE_LOGGING_LEVEL]
        append_log_file = values[const.APPEND_LOG_FILE]
        logging_file = values[const.LOGFILE]
        console_logging = values[const.CONSOLE_LOGGING]
        console_logging_level = values[const.CONSOLE_LOGGING_LEVEL]

        self.rb_file_logging.SetSelection(int(file_logging))
        self.cb_file_logging_level.SetSelection(int(file_logging_level))
        self.rb_append_file.SetSelection(int(append_log_file))
        self.tc_log_file_name.SetValue(logging_file)
        self.rb_console_logging.SetSelection(int(console_logging))
        self.cb_console_logging_level.SetSelection(int(console_logging_level))


class NavigationTab(wx.Panel):
    def __init__(self, parent, navigation):
        wx.Panel.__init__(self, parent)

        self.session = ses.Session()
        self.navigation = navigation
        self.sleep_nav = self.navigation.sleep_nav
        self.sleep_coord = const.SLEEP_COORDINATES

        self.LoadConfig()

        text_note = wx.StaticText(
            self, -1, _("Note: Using too low sleep times can result in Invesalius crashing!")
        )
        # Change sleep pause between navigation loops
        nav_sleep = wx.StaticText(self, -1, _("Navigation Sleep (s):"))
        spin_nav_sleep = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        spin_nav_sleep.Enable(1)
        spin_nav_sleep.SetRange(0.01, 10.0)
        spin_nav_sleep.SetValue(self.sleep_nav)
        spin_nav_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectNavSleep, ctrl=spin_nav_sleep))
        spin_nav_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectNavSleep, ctrl=spin_nav_sleep))

        # Change sleep pause between coordinate update
        coord_sleep = wx.StaticText(self, -1, _("Coordinate Sleep (s):"))
        spin_coord_sleep = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.01)
        spin_coord_sleep.Enable(1)
        spin_coord_sleep.SetRange(0.01, 10.0)
        spin_coord_sleep.SetValue(self.sleep_coord)
        spin_coord_sleep.Bind(wx.EVT_TEXT, partial(self.OnSelectCoordSleep, ctrl=spin_coord_sleep))
        spin_coord_sleep.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectCoordSleep, ctrl=spin_coord_sleep)
        )

        line_nav_sleep = wx.BoxSizer(wx.HORIZONTAL)
        line_nav_sleep.AddMany(
            [
                (nav_sleep, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 5),
                (spin_nav_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, 5),
            ]
        )

        line_coord_sleep = wx.BoxSizer(wx.HORIZONTAL)
        line_coord_sleep.AddMany(
            [
                (coord_sleep, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 5),
                (spin_coord_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, 5),
            ]
        )

        # Add line sizers into main sizer
        conf_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Sleep time configuration"))
        conf_sizer.AddMany(
            [
                (text_note, 0, wx.ALL, 10),
                (line_nav_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
                (line_coord_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
            ]
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(conf_sizer, 0, wx.ALL | wx.EXPAND, 10)
        self.SetSizerAndFit(main_sizer)
        self.Layout()

    def OnSelectNavSleep(self, evt, ctrl):
        self.sleep_nav = ctrl.GetValue()
        self.navigation.UpdateNavSleep(self.sleep_nav)

        self.session.SetConfig("sleep_nav", self.sleep_nav)

    def OnSelectCoordSleep(self, evt, ctrl):
        self.sleep_coord = ctrl.GetValue()
        Publisher.sendMessage("Update coord sleep", data=self.sleep_coord)

        self.session.SetConfig("sleep_coord", self.sleep_nav)

    def LoadConfig(self):
        sleep_nav = self.session.GetConfig("sleep_nav")
        sleep_coord = self.session.GetConfig("sleep_coord")

        if sleep_nav is not None:
            self.sleep_nav = sleep_nav

        if sleep_coord is not None:
            self.sleep_coord = sleep_coord


class ObjectTab(wx.Panel):
    def __init__(self, parent, navigation, tracker, pedal_connector, neuronavigation_api):
        wx.Panel.__init__(self, parent)

        self.session = ses.Session()

        self.coil_list = const.COIL

        self.tracker = tracker
        self.pedal_connector = pedal_connector
        self.neuronavigation_api = neuronavigation_api
        self.navigation = navigation
        self.obj_fiducials = None
        self.obj_orients = None
        self.obj_ref_mode = None
        self.coil_path = None
        self.__bind_events()
        self.timestamp = const.TIMESTAMP
        self.LoadConfig()

        # Buttons for TMS coil configuration
        tooltip = _("New TMS coil configuration")
        btn_new = wx.Button(self, -1, _("New"), size=wx.Size(65, 23))
        btn_new.SetToolTip(tooltip)
        btn_new.Enable(1)
        btn_new.Bind(wx.EVT_BUTTON, self.OnCreateNewCoil)
        self.btn_new = btn_new

        tooltip = _("Load TMS coil configuration from a file")
        btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadCoil)
        self.btn_load = btn_load

        tooltip = _("Save current TMS coil configuration to a file")
        btn_save = wx.Button(self, -1, _("Save"), size=wx.Size(65, 23))
        btn_save.SetToolTip(tooltip)
        btn_save.Enable(1)
        btn_save.Bind(wx.EVT_BUTTON, self.OnSaveCoil)
        self.btn_save = btn_save

        self.config_txt = config_txt = wx.StaticText(self, -1, "None")
        data = self.navigation.GetObjectRegistration()
        self.OnObjectUpdate(data)

        lbl = wx.StaticText(self, -1, _("Current Configuration:"))
        lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        lbl_new = wx.StaticText(self, -1, _("Create new configuration: "))
        lbl_load = wx.StaticText(self, -1, _("Load configuration from file: "))
        lbl_save = wx.StaticText(self, -1, _("Save configuration to file: "))

        load_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("TMS coil registration"))
        inner_load_sizer = wx.FlexGridSizer(2, 4, 5)
        inner_load_sizer.AddMany(
            [
                (lbl, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (config_txt, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (lbl_new, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (btn_new, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (lbl_load, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (btn_load, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (lbl_save, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (btn_save, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            ]
        )
        load_sizer.Add(inner_load_sizer, 0, wx.ALL | wx.EXPAND, 10)
        # Change angles threshold
        text_angles = wx.StaticText(self, -1, _("Angle threshold (degrees):"))
        spin_size_angles = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23))
        spin_size_angles.SetRange(0.1, 99)
        spin_size_angles.SetValue(self.angle_threshold)
        spin_size_angles.Bind(
            wx.EVT_TEXT, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles)
        )
        spin_size_angles.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles)
        )

        # Change dist threshold
        text_dist = wx.StaticText(self, -1, _("Distance threshold (mm):"))
        spin_size_dist = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23))
        spin_size_dist.SetRange(0.1, 99)
        spin_size_dist.SetValue(self.distance_threshold)
        spin_size_dist.Bind(
            wx.EVT_TEXT, partial(self.OnSelectDistanceThreshold, ctrl=spin_size_dist)
        )
        spin_size_dist.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectDistanceThreshold, ctrl=spin_size_dist)
        )

        # Change timestamp interval
        text_timestamp = wx.StaticText(self, -1, _("Timestamp interval (s):"))
        spin_timestamp_dist = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc=0.1)
        spin_timestamp_dist.SetRange(0.5, 60.0)
        spin_timestamp_dist.SetValue(self.timestamp)
        spin_timestamp_dist.Bind(
            wx.EVT_TEXT, partial(self.OnSelectTimestamp, ctrl=spin_timestamp_dist)
        )
        spin_timestamp_dist.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectTimestamp, ctrl=spin_timestamp_dist)
        )
        self.spin_timestamp_dist = spin_timestamp_dist

        # Create a horizontal sizer to threshold configs
        line_angle_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_angle_threshold.AddMany(
            [
                (text_angles, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 5),
                (spin_size_angles, 0, wx.ALL | wx.EXPAND | wx.GROW, 5),
            ]
        )

        line_dist_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_dist_threshold.AddMany(
            [
                (text_dist, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 5),
                (spin_size_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5),
            ]
        )

        line_timestamp = wx.BoxSizer(wx.HORIZONTAL)
        line_timestamp.AddMany(
            [
                (text_timestamp, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 5),
                (spin_timestamp_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5),
            ]
        )

        # Add line sizers into main sizer
        conf_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Settings"))
        conf_sizer.AddMany(
            [
                (line_angle_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20),
                (line_dist_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20),
                (line_timestamp, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20),
            ]
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [(load_sizer, 0, wx.ALL | wx.EXPAND, 10), (conf_sizer, 0, wx.ALL | wx.EXPAND, 10)]
        )
        self.SetSizerAndFit(main_sizer)
        self.Layout()

    def __bind_events(self):
        Publisher.subscribe(self.OnObjectUpdate, "Update object registration")

    def LoadConfig(self):
        self.angle_threshold = (
            self.session.GetConfig("angle_threshold") or const.DEFAULT_ANGLE_THRESHOLD
        )
        self.distance_threshold = (
            self.session.GetConfig("distance_threshold") or const.DEFAULT_DISTANCE_THRESHOLD
        )

        state = self.session.GetConfig("navigation")

        if state is not None:
            object_fiducials = np.array(state["object_fiducials"])
            object_orientations = np.array(state["object_orientations"])
            object_reference_mode = state["object_reference_mode"]
            object_name = state["object_name"].encode(const.FS_ENCODE)

            self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.coil_path = (
                object_fiducials,
                object_orientations,
                object_reference_mode,
                object_name,
            )

    def OnCreateNewCoil(self, event=None):
        if self.tracker.IsTrackerInitialized():
            dialog = dlg.ObjectCalibrationDialog(
                self.tracker, self.pedal_connector, self.neuronavigation_api
            )
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    obj_fiducials, obj_orients, obj_ref_mode, coil_path, polydata = (
                        dialog.GetValue()
                    )

                    self.neuronavigation_api.update_coil_mesh(polydata)

                    if np.isfinite(obj_fiducials).all() and np.isfinite(obj_orients).all():
                        Publisher.sendMessage(
                            "Update object registration",
                            data=(obj_fiducials, obj_orients, obj_ref_mode, coil_path),
                        )
                        Publisher.sendMessage("Update status text in GUI", label=_("Ready"))
                        Publisher.sendMessage(
                            "Configure coil",
                            coil_path=coil_path,
                            polydata=polydata,
                        )

                        # Automatically enable and check 'Track object' checkbox and uncheck 'Disable Volume Camera' checkbox.
                        Publisher.sendMessage("Enable track object button", enabled=True)
                        Publisher.sendMessage("Press track object button", pressed=True)

                        Publisher.sendMessage("Press target mode button", pressed=False)

            except wx.PyAssertionError:  # TODO FIX: win64
                pass
            dialog.Destroy()
        else:
            dlg.ShowNavigationTrackerWarning(0, "choose")

    def OnLoadCoil(self, event=None):
        filename = dlg.ShowLoadSaveDialog(
            message=_("Load object registration"), wildcard=_("Registration files (*.obr)|*.obr")
        )
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # coil_path = 'magstim_coil_dell_laptop.obr'
        # filename = os.path.join(data_dir, coil_path)

        try:
            if filename:
                with open(filename) as text_file:
                    data = [s.split("\t") for s in text_file.readlines()]

                registration_coordinates = np.array(data[1:]).astype(np.float32)
                obj_fiducials = registration_coordinates[:, :3]
                obj_orients = registration_coordinates[:, 3:]

                coil_path = data[0][1].encode(const.FS_ENCODE)
                obj_ref_mode = int(data[0][-1])

                if not os.path.exists(coil_path):
                    coil_path = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                polydata = vtk_utils.CreateObjectPolyData(coil_path)
                if polydata:
                    self.neuronavigation_api.update_coil_mesh(polydata)
                else:
                    coil_path = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                Publisher.sendMessage(
                    "Update object registration",
                    data=(obj_fiducials, obj_orients, obj_ref_mode, coil_path),
                )
                Publisher.sendMessage(
                    "Update status text in GUI", label=_("Object file successfully loaded")
                )
                Publisher.sendMessage(
                    "Configure coil",
                    coil_path=coil_path,
                    polydata=polydata,
                )

                # Automatically enable and check 'Track object' checkbox and uncheck 'Disable Volume Camera' checkbox.
                Publisher.sendMessage("Enable track object button", enabled=True)
                Publisher.sendMessage("Press track object button", pressed=True)
                Publisher.sendMessage("Press target mode button", pressed=False)

                msg = _("Object file successfully loaded")
                wx.MessageBox(msg, _("InVesalius 3"))
        except Exception:
            wx.MessageBox(_("Object registration file incompatible."), _("InVesalius 3"))
            Publisher.sendMessage("Update status text in GUI", label="")

    def OnSaveCoil(self, evt):
        obj_fiducials, obj_orients, obj_ref_mode, coil_path = (
            self.navigation.GetObjectRegistration()
        )
        if np.isnan(obj_fiducials).any() or np.isnan(obj_orients).any():
            wx.MessageBox(_("Digitize all object fiducials before saving"), _("Save error"))
        else:
            filename = dlg.ShowLoadSaveDialog(
                message=_("Save object registration as..."),
                wildcard=_("Registration files (*.obr)|*.obr"),
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                default_filename="object_registration.obr",
                save_ext="obr",
            )
            if filename:
                hdr = (
                    "Object"
                    + "\t"
                    + utils.decode(coil_path, const.FS_ENCODE)
                    + "\t"
                    + "Reference"
                    + "\t"
                    + str("%d" % obj_ref_mode)
                )
                data = np.hstack([obj_fiducials, obj_orients])
                np.savetxt(filename, data, fmt="%.4f", delimiter="\t", newline="\n", header=hdr)
                wx.MessageBox(_("Object file successfully saved"), _("Save"))

    def OnSelectAngleThreshold(self, evt, ctrl):
        self.angle_threshold = ctrl.GetValue()
        Publisher.sendMessage("Update angle threshold", angle=self.angle_threshold)

        self.session.SetConfig("angle_threshold", self.angle_threshold)

    def OnSelectDistanceThreshold(self, evt, ctrl):
        self.distance_threshold = ctrl.GetValue()
        Publisher.sendMessage("Update distance threshold", dist_threshold=self.distance_threshold)

        self.session.SetConfig("distance_threshold", self.distance_threshold)

    def OnSelectTimestamp(self, evt, ctrl):
        self.timestamp = ctrl.GetValue()

    def OnObjectUpdate(self, data=None):
        if data:
            label = os.path.basename(data[-1])
        else:
            label = "None"
        self.config_txt.SetLabel(label)


class TrackerTab(wx.Panel):
    def __init__(self, parent, tracker, robot):
        wx.Panel.__init__(self, parent)

        self.__bind_events()

        self.tracker = tracker
        self.robot = robot
        self.robot_ip = None
        self.matrix_tracker_to_robot = None
        self.state = self.LoadConfig()

        # ComboBox for spatial tracker device selection
        tracker_options = [_("Select")] + self.tracker.get_trackers()
        select_tracker_elem = wx.ComboBox(
            self,
            -1,
            "",
            size=(145, -1),
            choices=tracker_options,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        tooltip = _("Choose the tracking device")
        select_tracker_elem.SetToolTip(tooltip)
        select_tracker_elem.SetSelection(self.tracker.tracker_id)
        select_tracker_elem.Bind(
            wx.EVT_COMBOBOX, partial(self.OnChooseTracker, ctrl=select_tracker_elem)
        )
        self.select_tracker_elem = select_tracker_elem

        select_tracker_label = wx.StaticText(self, -1, _("Choose the tracking device: "))

        # ComboBox for tracker reference mode
        tooltip = _("Choose the navigation reference mode")
        choice_ref = wx.ComboBox(
            self,
            -1,
            "",
            size=(145, -1),
            choices=const.REF_MODE,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        choice_ref.SetSelection(const.DEFAULT_REF_MODE)
        choice_ref.SetToolTip(tooltip)
        choice_ref.Bind(
            wx.EVT_COMBOBOX, partial(self.OnChooseReferenceMode, ctrl=select_tracker_elem)
        )
        self.choice_ref = choice_ref

        choice_ref_label = wx.StaticText(self, -1, _("Choose the navigation reference mode: "))

        ref_sizer = wx.FlexGridSizer(rows=2, cols=2, hgap=5, vgap=5)
        ref_sizer.AddMany(
            [
                (select_tracker_label, wx.LEFT),
                (select_tracker_elem, wx.RIGHT),
                (choice_ref_label, wx.LEFT),
                (choice_ref, wx.RIGHT),
            ]
        )
        ref_sizer.Layout()

        sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Setup tracker"))
        sizer.Add(ref_sizer, 1, wx.ALL | wx.FIXED_MINSIZE, 20)

        lbl_rob = wx.StaticText(self, -1, _("Select IP for robot device: "))

        # ComboBox for spatial tracker device selection
        tooltip = _("Choose or type the robot IP")
        robot_ip_options = [_("Select robot IP:")] + const.ROBOT_ElFIN_IP + const.ROBOT_DOBOT_IP
        choice_IP = wx.ComboBox(
            self, -1, "", choices=robot_ip_options, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER
        )
        choice_IP.SetToolTip(tooltip)
        if self.robot.robot_ip is not None:
            choice_IP.SetSelection(robot_ip_options.index(self.robot.robot_ip))
        else:
            choice_IP.SetSelection(0)
        choice_IP.Bind(wx.EVT_COMBOBOX, partial(self.OnChoiceIP, ctrl=choice_IP))
        choice_IP.Bind(wx.EVT_TEXT, partial(self.OnTxt_Ent, ctrl=choice_IP))
        self.choice_IP = choice_IP

        btn_rob = wx.Button(self, -1, _("Connect"))
        btn_rob.SetToolTip("Connect to IP")
        btn_rob.Enable(1)
        btn_rob.Bind(wx.EVT_BUTTON, self.OnRobotConnect)
        self.btn_rob = btn_rob

        status_text = wx.StaticText(self, -1, "Status")
        if self.robot.IsConnected():
            status_text.SetLabelText("Robot is connected!")
            if self.robot.matrix_tracker_to_robot is not None:
                status_text.SetLabelText("Robot is fully setup!")
        else:
            status_text.SetLabelText("Robot is not connected!")
        self.status_text = status_text

        btn_rob_con = wx.Button(self, -1, _("Register"))
        btn_rob_con.SetToolTip("Register robot tracking")
        btn_rob_con.Enable(1)
        btn_rob_con.Bind(wx.EVT_BUTTON, self.OnRobotRegister)
        if self.robot.IsConnected():
            if self.matrix_tracker_to_robot is None:
                btn_rob_con.Show()
            else:
                btn_rob_con.SetLabel("Register Again")
                btn_rob_con.Show()
        else:
            btn_rob_con.Hide()
        self.btn_rob_con = btn_rob_con

        rob_sizer = wx.FlexGridSizer(rows=2, cols=3, hgap=5, vgap=5)
        rob_sizer.AddMany(
            [
                (lbl_rob, 0, wx.LEFT),
                (choice_IP, 1, wx.EXPAND),
                (btn_rob, 0, wx.LEFT | wx.ALIGN_CENTER_HORIZONTAL, 15),
                (status_text, wx.LEFT | wx.ALIGN_CENTER_HORIZONTAL, 15),
                (0, 0),
                (btn_rob_con, 0, wx.LEFT | wx.ALIGN_CENTER_HORIZONTAL, 15),
            ]
        )

        rob_static_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Setup robot"))
        rob_static_sizer.Add(rob_sizer, 1, wx.ALL | wx.FIXED_MINSIZE, 20)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [(sizer, 0, wx.ALL | wx.EXPAND, 10), (rob_static_sizer, 0, wx.ALL | wx.EXPAND, 10)]
        )
        self.SetSizerAndFit(main_sizer)
        self.Layout()

    def __bind_events(self):
        Publisher.subscribe(self.ShowParent, "Show preferences dialog")
        Publisher.subscribe(self.OnRobotStatus, "Robot to Neuronavigation: Robot connection status")
        Publisher.subscribe(
            self.OnSetRobotTransformationMatrix,
            "Neuronavigation to Robot: Set robot transformation matrix",
        )

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig("robot")

        if state is None:
            return False

        self.robot_ip = state["robot_ip"]
        self.matrix_tracker_to_robot = np.array(state["tracker_to_robot"])

        return True

    def OnChooseTracker(self, evt, ctrl):
        if sys.platform == "darwin":
            wx.CallAfter(self.GetParent().Hide)
        else:
            self.HideParent()
        Publisher.sendMessage("Begin busy cursor")
        Publisher.sendMessage("Update status text in GUI", label=_("Configuring tracker ..."))
        if hasattr(evt, "GetSelection"):
            choice = evt.GetSelection()
        else:
            choice = None

        self.tracker.DisconnectTracker()
        self.tracker.ResetTrackerFiducials()
        self.tracker.SetTracker(choice)
        Publisher.sendMessage("Update status text in GUI", label=_("Ready"))
        Publisher.sendMessage("Tracker changed")
        ctrl.SetSelection(self.tracker.tracker_id)
        Publisher.sendMessage("End busy cursor")
        if sys.platform == "darwin":
            wx.CallAfter(self.GetParent().Show)
        else:
            self.ShowParent()

    def OnChooseReferenceMode(self, evt, ctrl):
        # Probably need to refactor object registration as a whole to use the
        # OnChooseReferenceMode function which was used earlier. It can be found in
        # the deprecated code in ObjectRegistrationPanel in task_navigator.py.
        pass

    def HideParent(self):  # hide preferences dialog box
        self.GetGrandParent().Hide()

    def ShowParent(self):  # show preferences dialog box
        self.GetGrandParent().Show()

    def OnTxt_Ent(self, evt, ctrl):
        self.robot_ip = str(ctrl.GetValue())

    def OnChoiceIP(self, evt, ctrl):
        self.robot_ip = ctrl.GetStringSelection()

    def OnRobotConnect(self, evt):
        if self.robot_ip is not None:
            self.status_text.SetLabelText("Trying to connect to robot...")
            self.btn_rob_con.Hide()
            self.robot.SetRobotIP(self.robot_ip)
            Publisher.sendMessage(
                "Neuronavigation to Robot: Connect to robot", robot_IP=self.robot_ip
            )

    def OnRobotRegister(self, evt):
        if sys.platform == "darwin":
            wx.CallAfter(self.GetParent().Hide)
        else:
            self.HideParent()
        self.robot.RegisterRobot()
        if sys.platform == "darwin":
            wx.CallAfter(self.GetParent().Show)
        else:
            self.ShowParent()

    def OnRobotStatus(self, data):
        if data:
            self.status_text.SetLabelText("Setup robot transformation matrix:")
            self.btn_rob_con.Show()

    def OnSetRobotTransformationMatrix(self, data):
        if self.robot.matrix_tracker_to_robot is not None:
            self.status_text.SetLabelText("Robot is fully setup!")
            self.btn_rob_con.SetLabel("Register Again")
            self.btn_rob_con.Show()
            self.btn_rob_con.Layout()
            self.Parent.Update()


class LanguageTab(wx.Panel):
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
