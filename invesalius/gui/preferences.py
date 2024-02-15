import sys
import os

from functools import partial
import nibabel as nb
import numpy as np
import invesalius.constants as const
import invesalius.session as ses
import invesalius.gui.dialogs as dlg0
import invesalius.data.vtk_utils as vtk_utils
from invesalius import inv_paths

import wx
from invesalius import utils
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher

from invesalius.navigation.tracker import Tracker
from invesalius.navigation.robot import Robot
from invesalius.net.neuronavigation_api import NeuronavigationApi
from invesalius.navigation.navigation import Navigation

HAS_PEDAL_CONNECTION = True
try:
    from invesalius.net.pedal_connection import PedalConnection
except ImportError:
    HAS_PEDAL_CONNECTION = False

class Preferences(wx.Dialog):
    def __init__(
        self,
        parent,
        page, 
        id_=-1,
        title=_("Preferences"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
    ):
        super().__init__(parent, id_, title, style=style)
        tracker = Tracker()
        robot = Robot()
        pedal_connection = PedalConnection() if HAS_PEDAL_CONNECTION else None
        neuronavigation_api = NeuronavigationApi()
        navigation = Navigation(
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )

        self.book = wx.Notebook(self, -1)

        self.pnl_viewer3d = Viewer3D(self.book)
        self.pnl_language = Language(self.book)
        self.pnl_logging = Logging(self.book)

        self.book.AddPage(self.pnl_viewer3d, _("Visualization"))
        session = ses.Session()
        mode = session.GetConfig('mode')
        if mode == const.MODE_NAVIGATOR:
            self.pnl_navigation = NavigationPage(self.book, navigation)
            self.pnl_tracker = TrackerPage(self.book, tracker, robot)
            self.pnl_object = ObjectPage(self.book, navigation, tracker, pedal_connection, neuronavigation_api)
            self.book.AddPage(self.pnl_navigation, _("Navigation"))
            self.book.AddPage(self.pnl_tracker, _("Tracker"))
            self.book.AddPage(self.pnl_object, _("Stimulator"))

        self.book.AddPage(self.pnl_language, _("Language"))
        self.book.AddPage(self.pnl_logging, _("Logging"))

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
        lang = self.pnl_language.GetSelection()
        viewer = self.pnl_viewer3d.GetSelection()
        logging = self.pnl_logging.GetSelection()

        values.update(lang)
        values.update(viewer)
        values.update(logging)
        return values

    def LoadPreferences(self):
        session = ses.Session()

        rendering = session.GetConfig('rendering')
        surface_interpolation = session.GetConfig('surface_interpolation')
        language = session.GetConfig('language')
        slice_interpolation = session.GetConfig('slice_interpolation')
        do_logging = session.GetConfig('do_logging')
        logging_level = session.GetConfig('logging_level')
        append_log_file = session.GetConfig('append_log_file')
        logging_file  = session.GetConfig('logging_file')

        #session = ses.Session()
        mode = session.GetConfig('mode')
        if mode == const.MODE_NAVIGATOR:
            self.pnl_object.LoadConfig()

        values = {
            const.RENDERING: rendering,
            const.SURFACE_INTERPOLATION: surface_interpolation,
            const.LANGUAGE: language,
            const.SLICE_INTERPOLATION: slice_interpolation,
            const.LOGGING: do_logging,
            const.LOGGING_LEVEL: logging_level,
            const.APPEND_LOG_FILE: append_log_file,           
            const.LOGFILE: logging_file,
        }

        self.pnl_viewer3d.LoadSelection(values)
        self.pnl_language.LoadSelection(values)
        self.pnl_logging.LoadSelection(values)

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

class Logging(wx.Panel):
    def __init__(self, parent):

        wx.Panel.__init__(self, parent)
        
        bsizer_do_logging = wx.StaticBoxSizer(wx.VERTICAL, self, _("Do Logging"))
        rb_logging = self.rb_logging = wx.RadioBox(
            bsizer_do_logging.GetStaticBox(),
            -1,
            choices=["No", "Yes"],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )
        bsizer_do_logging.Add(rb_logging, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        bsizer_logging_level = wx.StaticBoxSizer(wx.VERTICAL, self, _("Logging level"))
        rb_logging_level = self.rb_logging_level = wx.RadioBox(
            bsizer_logging_level.GetStaticBox(),
            -1,
            choices=["NOTSET", "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
            majorDimension=6,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )
        bsizer_logging_level.Add(rb_logging_level, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        bsizer_append_log_file = wx.StaticBoxSizer(wx.VERTICAL, self, _("Append Log file"))
        rb_append_file = self.rb_append_file = wx.RadioBox(
            bsizer_append_log_file.GetStaticBox(),
            -1,
            choices=["No", "Yes"],
            majorDimension=3,
            style=wx.RA_SPECIFY_COLS | wx.NO_BORDER,
        )
        bsizer_append_log_file.Add(rb_append_file, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        bsizer_log_file_name = wx.StaticBoxSizer(wx.VERTICAL, self, _("Log file name"))
        lbl_log_file_label = wx.StaticText(bsizer_log_file_name.GetStaticBox(), -1, _("Current file:"))
        tc_log_file_name = self.tc_log_file_name = wx.TextCtrl(
            bsizer_log_file_name.GetStaticBox(), -1, "", 
            style = wx.TE_READONLY | wx.TE_LEFT | wx.TE_MULTILINE , 
            size=(300, -1))
        tc_log_file_name.SetForegroundColour(wx.RED)
        bt_log_file_select = wx.Button(bsizer_log_file_name.GetStaticBox(), label="Modify")
        bsizer_log_file_name.Add(lbl_log_file_label, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)
        bsizer_log_file_name.Add(tc_log_file_name, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)
        bsizer_log_file_name.Add(bt_log_file_select, 0, wx.TOP | wx.LEFT | wx.FIXED_MINSIZE, 0)

        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer_do_logging, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        border.Add(bsizer_logging_level, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        border.Add(bsizer_append_log_file, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        border.Add(bsizer_log_file_name, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        self.SetSizerAndFit(border)

        bt_log_file_select.Bind(wx.EVT_BUTTON, self.OnModifyButton)
        self.Layout()

    def OnModifyButton(self,e):
        logging_file = self.tc_log_file_name.GetValue()
        path, fname = os.path.split(logging_file)
        dlg = wx.FileDialog(self, message = "Save Log Contents",
            defaultDir = path, #os.getcwd(),
            defaultFile = fname, #default_file,
            wildcard = "Log files (*.log)|*.log",
            style = wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_CANCEL:
            dlg.Destroy()
            return False

        file_path = dlg.GetPath()
        self.tc_log_file_name.SetValue(file_path)
        dlg.Destroy()
        return True

    def GetSelection(self):

        options = {
            const.LOGGING: self.rb_logging.GetSelection(),
            const.LOGGING_LEVEL: self.rb_logging_level.GetSelection(),
            const.APPEND_LOG_FILE: self.rb_append_file.GetSelection(),
            const.LOGFILE: self.tc_log_file_name.GetValue(),
        }
        return options

    def LoadSelection(self, values):
        logging = values[const.LOGGING]
        logging_level = values[const.LOGGING_LEVEL]
        append_log_file = values[const.APPEND_LOG_FILE]
        logging_file = values[const.LOGFILE]
        
        self.rb_logging.SetSelection(int(logging))
        self.rb_logging_level.SetSelection(int(logging_level))
        self.rb_append_file.SetSelection(int(append_log_file))
        self.tc_log_file_name.SetValue(logging_file)

class NavigationPage(wx.Panel):
    def __init__(self, parent, navigation):
        wx.Panel.__init__(self, parent)
        self.navigation = navigation
        self.sleep_nav = self.navigation.sleep_nav
        self.sleep_coord = const.SLEEP_COORDINATES

        text_note = wx.StaticText(self, -1, _("Note: Using too low sleep times can result in Invesalius crashing!"))
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
        spin_coord_sleep.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectCoordSleep, ctrl=spin_coord_sleep))

        line_nav_sleep = wx.BoxSizer(wx.HORIZONTAL)
        line_nav_sleep.AddMany([
            (nav_sleep, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
            (spin_nav_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)
            ])

        line_coord_sleep = wx.BoxSizer(wx.HORIZONTAL)
        line_coord_sleep.AddMany([
            (coord_sleep, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
            (spin_coord_sleep, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)
            ])

        # Add line sizers into main sizer
        conf_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Sleep time configuration"))
        conf_sizer.AddMany([
            (text_note, 0, wx.ALL, 10),
            (line_nav_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
            (line_coord_sleep, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        ])

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(conf_sizer, 0, wx.ALL | wx.EXPAND, 10)
        self.SetSizerAndFit(main_sizer)
        self.Layout()

    def OnSelectNavSleep(self, evt, ctrl):
        self.sleep_nav = ctrl.GetValue()
        self.navigation.UpdateNavSleep(self.sleep_nav)

    def OnSelectCoordSleep(self, evt, ctrl):
        self.sleep_coord = ctrl.GetValue()
        Publisher.sendMessage('Update coord sleep', data=self.sleep_coord)
        
class ObjectPage(wx.Panel):
    def __init__(self, parent, navigation, tracker, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)

        self.coil_list = const.COIL
        
        self.tracker = tracker
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api
        self.navigation = navigation
        self.obj_fiducials = None
        self.obj_orients = None
        self.obj_ref_mode = None
        self.obj_name = None
        self.__bind_events()
        self.timestamp = const.TIMESTAMP
        self.state = self.LoadConfig()

        # Button for creating new stimulator
        tooltip = wx.ToolTip(_("Create new stimulator"))
        btn_new = wx.Button(self, -1, _("New"), size=wx.Size(65, 23))
        btn_new.SetToolTip(tooltip)
        btn_new.Enable(1)
        btn_new.Bind(wx.EVT_BUTTON, self.OnCreateNewCoil)
        self.btn_new = btn_new

        # Button for loading stimulator config file
        tooltip = wx.ToolTip(_("Load stimulator configuration file"))
        btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadCoil)
        self.btn_load = btn_load

        # Save button for saving stimulator config file
        tooltip = wx.ToolTip(_(u"Save stimulator configuration file"))
        btn_save = wx.Button(self, -1, _(u"Save"), size=wx.Size(65, 23))
        btn_save.SetToolTip(tooltip)
        btn_save.Enable(1)
        btn_save.Bind(wx.EVT_BUTTON, self.OnSaveCoil)
        self.btn_save = btn_save
        
        if self.state:
            config_txt = wx.StaticText(self, -1, os.path.basename(self.obj_name))
        else:
            config_txt = wx.StaticText(self, -1, "None")

        self.config_txt = config_txt    
        lbl = wx.StaticText(self, -1, _("Current Configuration:"))
        lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        lbl_new = wx.StaticText(self, -1, _("Create a new stimulator registration: "))
        lbl_load = wx.StaticText(self, -1, _("Load a stimulator registration: "))
        lbl_save = wx.StaticText(self, -1, _("Save current stimulator registration: "))

        load_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Stimulator registration"))
        inner_load_sizer = wx.FlexGridSizer(2, 4, 5)
        inner_load_sizer.AddMany([
            (lbl, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (config_txt, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (lbl_new, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (btn_new, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (lbl_load, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (btn_load, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (lbl_save, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            (btn_save, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
        ])
        load_sizer.Add(inner_load_sizer, 0, wx.ALL | wx.EXPAND, 10)
        # Change angles threshold
        text_angles = wx.StaticText(self, -1, _("Angle threshold [degrees]:"))
        spin_size_angles = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23))
        spin_size_angles.SetRange(0.1, 99)
        spin_size_angles.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_angles.Bind(wx.EVT_TEXT, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))
        spin_size_angles.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectAngleThreshold, ctrl=spin_size_angles))

        # Change dist threshold
        text_dist = wx.StaticText(self, -1, _("Distance threshold [mm]:"))
        spin_size_dist = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23))
        spin_size_dist.SetRange(0.1, 99)
        spin_size_dist.SetValue(const.COIL_ANGLES_THRESHOLD)
        spin_size_dist.Bind(wx.EVT_TEXT, partial(self.OnSelectDistThreshold, ctrl=spin_size_dist))
        spin_size_dist.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectDistThreshold, ctrl=spin_size_dist))

        # Change timestamp interval
        text_timestamp = wx.StaticText(self, -1, _("Timestamp interval [s]:"))
        spin_timestamp_dist = wx.SpinCtrlDouble(self, -1, "", size=wx.Size(50, 23), inc = 0.1)
        spin_timestamp_dist.SetRange(0.5, 60.0)
        spin_timestamp_dist.SetValue(self.timestamp)
        spin_timestamp_dist.Bind(wx.EVT_TEXT, partial(self.OnSelectTimestamp, ctrl=spin_timestamp_dist))
        spin_timestamp_dist.Bind(wx.EVT_SPINCTRL, partial(self.OnSelectTimestamp, ctrl=spin_timestamp_dist))
        self.spin_timestamp_dist = spin_timestamp_dist

        # Create a horizontal sizer to threshold configs
        line_angle_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_angle_threshold.AddMany([
            (text_angles, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
            (spin_size_angles, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)
            ])

        line_dist_threshold = wx.BoxSizer(wx.HORIZONTAL)
        line_dist_threshold.AddMany([
            (text_dist, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
            (spin_size_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)
            ])

        line_timestamp = wx.BoxSizer(wx.HORIZONTAL)
        line_timestamp.AddMany([
            (text_timestamp, 1, wx.EXPAND | wx.GROW | wx.TOP| wx.RIGHT | wx.LEFT, 5),
            (spin_timestamp_dist, 0, wx.ALL | wx.EXPAND | wx.GROW, 5)
            ])

        # Add line sizers into main sizer
        conf_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Stimulator configuration"))
        conf_sizer.AddMany([
            (line_angle_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20),
            (line_dist_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20),
            (line_timestamp, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)
        ])

        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([
            (load_sizer, 0, wx.ALL | wx.EXPAND, 10),
            (conf_sizer, 0, wx.ALL | wx.EXPAND, 10)
        ])
        self.SetSizerAndFit(main_sizer)
        self.Layout()

    def __bind_events(self):
        Publisher.subscribe(self.OnObjectUpdate, 'Update object registration')

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig('navigation')

        if state is None:
            return False

        object_fiducials = np.array(state['object_fiducials'])
        object_orientations = np.array(state['object_orientations'])
        object_reference_mode = state['object_reference_mode']
        object_name = state['object_name'].encode(const.FS_ENCODE)

        self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name = object_fiducials, object_orientations, object_reference_mode, object_name
        return True

    def OnCreateNewCoil(self, event=None):
        if self.tracker.IsTrackerInitialized():
            dialog = dlg.ObjectCalibrationDialog(self.tracker, self.pedal_connection, self.neuronavigation_api)
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    obj_fiducials, obj_orients, obj_ref_mode, obj_name, polydata, use_default_object = dialog.GetValue()

                    self.neuronavigation_api.update_coil_mesh(polydata)

                    if np.isfinite(obj_fiducials).all() and np.isfinite(obj_orients).all():
                        Publisher.sendMessage('Update object registration',
                                              data=(obj_fiducials, obj_orients, obj_ref_mode, obj_name))
                        Publisher.sendMessage('Update status text in GUI',
                                              label=_("Ready"))
                        Publisher.sendMessage(
                            'Configure object',
                            obj_name=obj_name,
                            polydata=polydata,
                            use_default_object=use_default_object,
                        )

                        # Automatically enable and check 'Track object' checkbox and uncheck 'Disable Volume Camera' checkbox.
                        Publisher.sendMessage('Enable track-object checkbox', enabled=True)
                        Publisher.sendMessage('Check track-object checkbox', checked=True)
                        Publisher.sendMessage('Check volume camera checkbox', checked=False)

                        Publisher.sendMessage('Disable target mode')

            except wx._core.PyAssertionError:  # TODO FIX: win64
                pass
            dialog.Destroy()
        else:
            dlg.ShowNavigationTrackerWarning(0, 'choose')

    def OnLoadCoil(self, event=None):
        filename = dlg.ShowLoadSaveDialog(message=_(u"Load object registration"),
                                          wildcard=_("Registration files (*.obr)|*.obr"))
        # data_dir = os.environ.get('OneDrive') + r'\data\dti_navigation\baran\anat_reg_improve_20200609'
        # coil_path = 'magstim_coil_dell_laptop.obr'
        # filename = os.path.join(data_dir, coil_path)

        try:
            if filename:
                with open(filename, 'r') as text_file:
                    data = [s.split('\t') for s in text_file.readlines()]

                registration_coordinates = np.array(data[1:]).astype(np.float32)
                obj_fiducials = registration_coordinates[:, :3]
                obj_orients = registration_coordinates[:, 3:]

                obj_name = data[0][1].encode(const.FS_ENCODE)
                obj_ref_mode = int(data[0][-1])

                if not os.path.exists(obj_name):
                    obj_name = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                polydata = vtk_utils.CreateObjectPolyData(obj_name)
                if polydata:
                    self.neuronavigation_api.update_coil_mesh(polydata)
                else:
                    obj_name = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                if os.path.basename(obj_name) == "magstim_fig8_coil.stl":
                    use_default_object = True
                else:
                    use_default_object = False

                Publisher.sendMessage('Update object registration',
                                      data=(obj_fiducials, obj_orients, obj_ref_mode, obj_name))
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Object file successfully loaded"))
                Publisher.sendMessage(
                    'Configure object',
                    obj_name=obj_name,
                    polydata=polydata,
                    use_default_object=use_default_object
                )

                # Automatically enable and check 'Track object' checkbox and uncheck 'Disable Volume Camera' checkbox.
                Publisher.sendMessage('Enable track-object checkbox', enabled=True)
                Publisher.sendMessage('Check track-object checkbox', checked=True)
                Publisher.sendMessage('Check volume camera checkbox', checked=False)

                Publisher.sendMessage('Disable target mode')
                if use_default_object:
                    msg = _("Default object file successfully loaded")
                else:
                    msg = _("Object file successfully loaded")
                wx.MessageBox(msg, _("InVesalius 3"))
        except:
            wx.MessageBox(_("Object registration file incompatible."), _("InVesalius 3"))
            Publisher.sendMessage('Update status text in GUI', label="")

    def OnSaveCoil(self, evt):
        obj_fiducials, obj_orients, obj_ref_mode, obj_name = self.navigation.GetObjectRegistration()
        if np.isnan(obj_fiducials).any() or np.isnan(obj_orients).any():
            wx.MessageBox(_("Digitize all object fiducials before saving"), _("Save error"))
        else:
            filename = dlg.ShowLoadSaveDialog(message=_(u"Save object registration as..."),
                                              wildcard=_("Registration files (*.obr)|*.obr"),
                                              style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                              default_filename="object_registration.obr", save_ext="obr")
            if filename:
                hdr = 'Object' + "\t" + utils.decode(obj_name, const.FS_ENCODE) + "\t" + 'Reference' + "\t" + str('%d' % obj_ref_mode)
                data = np.hstack([obj_fiducials, obj_orients])
                np.savetxt(filename, data, fmt='%.4f', delimiter='\t', newline='\n', header=hdr)
                wx.MessageBox(_("Object file successfully saved"), _("Save"))

    def OnSelectAngleThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update angle threshold', angle=ctrl.GetValue())

    def OnSelectDistThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update dist threshold', dist_threshold=ctrl.GetValue())

    def OnSelectTimestamp(self, evt, ctrl):
        self.timestamp = ctrl.GetValue()

    def OnObjectUpdate(self, data=None):
        self.config_txt.SetLabel(os.path.basename(data[-1]))

class TrackerPage(wx.Panel):
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
        choice_ref = wx.ComboBox(self, -1, "", size=(145, -1),
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
        
        lbl_rob = wx.StaticText(self, -1, _("Select IP for robot device: "))

        # ComboBox for spatial tracker device selection
        tooltip = wx.ToolTip(_("Choose or type the robot IP"))
        robot_ip_options = [_("Select robot IP:")] + const.ROBOT_ElFIN_IP
        choice_IP = wx.ComboBox(self, -1, "",
                                  choices=robot_ip_options, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER)
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
        rob_sizer.AddMany([
            (lbl_rob, 0, wx.LEFT),
            (choice_IP, 1, wx.EXPAND),
            (btn_rob, 0, wx.LEFT | wx.ALIGN_CENTER_HORIZONTAL, 15),
            (status_text, wx.LEFT | wx.ALIGN_CENTER_HORIZONTAL, 15),
            (0, 0),
            (btn_rob_con, 0, wx.LEFT | wx.ALIGN_CENTER_HORIZONTAL, 15)
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
        Publisher.subscribe(self.ShowParent, "Show preferences dialog")
        Publisher.subscribe(self.OnRobotStatus, "Robot connection status")
        Publisher.subscribe(self.OnTransformationMatrix, "Load robot transformation matrix")
    
    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig('robot')

        if state is None:
            return False

        self.robot_ip = state['robot_ip']
        self.matrix_tracker_to_robot = np.array(state['tracker_to_robot'])

        return True

    def OnChooseTracker(self, evt, ctrl):
        self.HideParent()
        Publisher.sendMessage('Begin busy cursor')
        Publisher.sendMessage('Update status text in GUI',
                              label=_("Configuring tracker ..."))
        if hasattr(evt, 'GetSelection'):
            choice = evt.GetSelection()
        else:
            choice = None

        self.tracker.DisconnectTracker()
        self.robot.DisconnectRobot()
        self.tracker.ResetTrackerFiducials()
        self.tracker.SetTracker(choice)
        Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
        Publisher.sendMessage("Tracker changed")
        ctrl.SetSelection(self.tracker.tracker_id)
        self.ShowParent()
        Publisher.sendMessage('End busy cursor')

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
            self.robot.DisconnectRobot()
            self.status_text.SetLabelText("Trying to connect to robot...")
            self.btn_rob_con.Hide()
            self.robot.SetRobotIP(self.robot_ip)
            Publisher.sendMessage('Connect to robot', robot_IP=self.robot_ip)

    def OnRobotRegister(self, evt):
        self.HideParent()
        self.robot.RegisterRobot()
        self.ShowParent()
    
    def OnRobotStatus(self, data):
        if data:
            self.status_text.SetLabelText("Setup robot transformation matrix:")
            self.btn_rob_con.Show()

    def OnTransformationMatrix(self, data):
        if self.robot.matrix_tracker_to_robot is not None:
            self.status_text.SetLabelText("Robot is fully setup!")
            self.btn_rob_con.SetLabel("Register Again")
            self.btn_rob_con.Show()
            self.btn_rob_con.Layout()
            self.Parent.Update()

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


'''
Deprecated code

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

'''