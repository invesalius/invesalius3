import sys
import os

from functools import partial
import nibabel as nb
import numpy as np
import invesalius.constants as const
import invesalius.session as ses
import invesalius.gui.dialogs as dlg
import invesalius.data.vtk_utils as vtk_utils
from invesalius import inv_paths

import wx
from invesalius import utils
from invesalius.gui.language_dialog import ComboBoxLanguage
from invesalius.pubsub import pub as Publisher

from invesalius.navigation.tracker import Tracker
from invesalius.navigation.robot import Robot
from invesalius.net.neuronavigation_api import NeuronavigationApi

HAS_PEDAL_CONNECTION = True
try:
    from invesalius.net.pedal_connection import PedalConnection
except ImportError:
    HAS_PEDAL_CONNECTION = False

class Preferences(wx.Dialog):
    def __init__(
        self,
        parent,
        id_=-1,
        title=_("Preferences"),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    ):
        super().__init__(parent, id_, title, style=style)
        tracker = Tracker()
        robot = Robot()

        pedal_connection = PedalConnection() if HAS_PEDAL_CONNECTION else None
        neuronavigation_api = NeuronavigationApi()

        self.book = wx.Notebook(self, -1)

        self.pnl_viewer3d = Viewer3D(self.book)
        self.pnl_language = Language(self.book)

        self.book.AddPage(self.pnl_viewer3d, _("Visualization"))
        session = ses.Session()
        mode = session.GetConfig('mode')
        if mode == const.MODE_NAVIGATOR:
            self.pnl_tracker = TrackerPage(self.book, tracker, robot)
            self.pnl_object = ObjectPage(self.book, tracker, pedal_connection, neuronavigation_api)
            self.book.AddPage(self.pnl_tracker, _("Tracker"))
            self.book.AddPage(self.pnl_object, _("Stimulator"))
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
        values.update(lang)
        values.update(viewer)

        return values

    def LoadPreferences(self):
        session = ses.Session()

        rendering = session.GetConfig('rendering')
        surface_interpolation = session.GetConfig('surface_interpolation')
        language = session.GetConfig('language')
        slice_interpolation = session.GetConfig('slice_interpolation')
        session = ses.Session()
        mode = session.GetConfig('mode')
        if mode == const.MODE_NAVIGATOR:
            self.pnl_object.LoadConfig()

        values = {
            const.RENDERING: rendering,
            const.SURFACE_INTERPOLATION: surface_interpolation,
            const.LANGUAGE: language,
            const.SLICE_INTERPOLATION: slice_interpolation,
        }

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

class ObjectPage(wx.Panel):
    def __init__(self, parent, tracker, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)

        self.coil_list = const.COIL
        
        self.tracker = tracker
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        self.__bind_events()
        self.obj_fiducials = None
        self.obj_orients = None
        self.obj_ref_mode = None
        self.obj_name = None
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
            lbl = wx.StaticText(self, -1, _("Current Configuration:"))
            lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
            config_txt = wx.StaticText(self, -1, os.path.basename(self.obj_name))

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
        else:
            lbl_new = wx.StaticText(self, -1, _("Create a new stimulator registration: "))
            lbl_load = wx.StaticText(self, -1, _("Load a stimulator registration: "))
            lbl_save = wx.StaticText(self, -1, _("Save current stimulator registration: "))

            load_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Stimulator registration"))
            inner_load_sizer = wx.FlexGridSizer(2, 3, 5)
            inner_load_sizer.AddMany([
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
        pass

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
                    self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name, polydata, use_default_object = dialog.GetValue()

                    self.neuronavigation_api.update_coil_mesh(polydata)

                    if np.isfinite(self.obj_fiducials).all() and np.isfinite(self.obj_orients).all():
                        Publisher.sendMessage('Update object registration',
                                              data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
                        Publisher.sendMessage('Update status text in GUI',
                                              label=_("Ready"))
                        Publisher.sendMessage(
                            'Configure object',
                            obj_name=self.obj_name,
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

        try:
            if filename:
                with open(filename, 'r') as text_file:
                    data = [s.split('\t') for s in text_file.readlines()]

                registration_coordinates = np.array(data[1:]).astype(np.float32)
                self.obj_fiducials = registration_coordinates[:, :3]
                self.obj_orients = registration_coordinates[:, 3:]

                self.obj_name = data[0][1].encode(const.FS_ENCODE)
                self.obj_ref_mode = int(data[0][-1])

                if not os.path.exists(self.obj_name):
                    self.obj_name = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                polydata = vtk_utils.CreateObjectPolyData(self.obj_name)
                if polydata:
                    self.neuronavigation_api.update_coil_mesh(polydata)
                else:
                    self.obj_name = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                if os.path.basename(self.obj_name) == "magstim_fig8_coil.stl":
                    use_default_object = True
                else:
                    use_default_object = False

                Publisher.sendMessage('Update object registration',
                                      data=(self.obj_fiducials, self.obj_orients, self.obj_ref_mode, self.obj_name))
                Publisher.sendMessage('Update status text in GUI',
                                      label=_("Object file successfully loaded"))
                Publisher.sendMessage(
                    'Configure object',
                    obj_name=self.obj_name,
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
        if np.isnan(self.obj_fiducials).any() or np.isnan(self.obj_orients).any():
            wx.MessageBox(_("Digitize all object fiducials before saving"), _("Save error"))
        else:
            filename = dlg.ShowLoadSaveDialog(message=_(u"Save object registration as..."),
                                              wildcard=_("Registration files (*.obr)|*.obr"),
                                              style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                              default_filename="object_registration.obr", save_ext="obr")
            if filename:
                hdr = 'Object' + "\t" + utils.decode(self.obj_name, const.FS_ENCODE) + "\t" + 'Reference' + "\t" + str('%d' % self.obj_ref_mode)
                data = np.hstack([self.obj_fiducials, self.obj_orients])
                np.savetxt(filename, data, fmt='%.4f', delimiter='\t', newline='\n', header=hdr)
                wx.MessageBox(_("Object file successfully saved"), _("Save"))

    def OnSelectAngleThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update angle threshold', angle=ctrl.GetValue())

    def OnSelectDistThreshold(self, evt, ctrl):
        Publisher.sendMessage('Update dist threshold', dist_threshold=ctrl.GetValue())

    def OnSelectTimestamp(self, evt, ctrl):
        self.timestamp = ctrl.GetValue()

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
            (btn_rob_con, 0, wx.RIGHT)
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
        if data:
            self.status_text.SetLabelText("Robot is fully setup!")
            self.btn_rob_con.SetLabel("Register Again")
            self.btn_rob_con.Show()
            self.btn_rob_con.Layout()

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