import os
import sys
from functools import partial

import numpy as np
import wx
import wx.lib.colourselect as csel
from matplotlib import colors as mcolors

import invesalius.constants as const
import invesalius.data.vtk_utils as vtk_utils
import invesalius.gui.dialogs as dlg
import invesalius.gui.log as log
import invesalius.gui.widgets.gradient as grad
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
            self.object_tab = ObjectTab(self.book, navigation, tracker, pedal_connector)

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

        self.Bind(wx.EVT_BUTTON, self.OnOK, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnCharHook)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.book, 1, wx.EXPAND | wx.ALL)
        sizer.Add(btnsizer, 0, wx.GROW | wx.RIGHT | wx.TOP | wx.BOTTOM, 5)
        self.SetSizerAndFit(sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.LoadPreferences, "Load Preferences")

    def OnOK(self, event):
        Publisher.sendMessage("Save Preferences")
        try:
            self.EndModal(wx.ID_OK)
        except wx._core.wxAssertionError:
            self.Destroy()

    def OnCharHook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        if event.GetKeyCode() == wx.WXK_RETURN:
            self.OnOK(event)
        event.Skip()

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

        self.session = ses.Session()

        self.colormaps = [str(cmap) for cmap in const.MEP_COLORMAP_DEFINITIONS.keys()]
        self.number_colors = 4
        self.cluster_volume = None

        self.conf = dict(self.session.GetConfig("mep_configuration"))
        self.conf["mep_colormap"] = self.conf.get("mep_colormap", "Viridis")

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
        border.Add(bsizer_slices, 0, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)
        border.Add(bsizer, 1, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)

        # Creating MEP Mapping BoxSizer
        if self.conf.get("mep_enabled") is True:
            self.bsizer_mep = self.InitMEPMapping(None)
            border.Add(self.bsizer_mep, 0, wx.EXPAND | wx.ALL | wx.FIXED_MINSIZE, 10)

        self.SetSizerAndFit(border)
        self.Layout()

    def GetSelection(self):
        options = {
            const.RENDERING: self.rb_rendering.GetSelection(),
            const.SURFACE_INTERPOLATION: self.rb_inter.GetSelection(),
            const.SLICE_INTERPOLATION: self.rb_inter_sl.GetSelection(),
        }
        return options

    def InitMEPMapping(self, event):
        # Adding a new sized for MEP Mapping options
        # Structured as follows:
        # MEP Mapping
        # - Surface Selection -> ComboBox
        # - Gaussian Radius -> SpinCtrlDouble
        # - Gaussian Standard Deviation -> SpinCtrlDouble
        # - Select Colormap -> ComboBox + Image frame
        # - Color Map Values
        # -- Min Value -> SpinCtrlDouble
        # -- Low Value -> SpinCtrlDouble
        # -- Mid Value -> SpinCtrlDouble
        # -- Max Value -> SpinCtrlDouble
        # TODO: Add a button to apply the colormap to the current volume
        # TODO: Store MEP visualization settings in a

        bsizer_mep = wx.StaticBoxSizer(wx.VERTICAL, self, _("TMS Motor Mapping"))

        # Surface Selection
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        # Initializing the project singleton
        from invesalius import project as prj

        self.proj = prj.Project()

        combo_brain_surface_name = wx.ComboBox(
            bsizer_mep.GetStaticBox(), -1, size=(210, 23), style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        if sys.platform != "win32":
            combo_brain_surface_name.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
        # TODO: Sending the event to the MEP Visualizer to update the surface
        # combo_brain_surface_name.Bind(
        #     wx.EVT_COMBOBOX, self.OnComboNameBrainSurface)
        combo_brain_surface_name.Bind(wx.EVT_COMBOBOX, self.OnComboName)

        for n in range(len(self.proj.surface_dict)):
            combo_brain_surface_name.Insert(str(self.proj.surface_dict[n].name), n)

        self.combo_brain_surface_name = combo_brain_surface_name

        # Mask colour
        button_colour = csel.ColourSelect(
            bsizer_mep.GetStaticBox(), -1, colour=(0, 0, 255), size=(22, -1)
        )
        button_colour.Bind(csel.EVT_COLOURSELECT, self.OnSelectColour)
        self.button_colour = button_colour

        # Sizer which represents the first line
        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(combo_brain_surface_name, 1, wx.ALL | wx.EXPAND | wx.GROW, 7)
        line1.Add(button_colour, 0, wx.ALL | wx.EXPAND | wx.GROW, 7)

        surface_sel_lbl = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Brain Surface:"))
        surface_sel_lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        surface_sel_sizer = wx.BoxSizer(wx.HORIZONTAL)

        surface_sel_sizer.Add(surface_sel_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        # fixed_sizer.AddSpacer(7)
        surface_sel_sizer.Add(line1, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT, 5)

        # Gaussian Radius Line
        lbl_gaussian_radius = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Gaussian Radius:"))
        self.spin_gaussian_radius = wx.SpinCtrlDouble(
            bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(64, 23), inc=0.5
        )
        self.spin_gaussian_radius.Enable(1)
        self.spin_gaussian_radius.SetRange(1, 99)
        self.spin_gaussian_radius.SetValue(self.conf.get("gaussian_radius"))

        self.spin_gaussian_radius.Bind(
            wx.EVT_TEXT, partial(self.OnSelectGaussianRadius, ctrl=self.spin_gaussian_radius)
        )
        self.spin_gaussian_radius.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectGaussianRadius, ctrl=self.spin_gaussian_radius)
        )

        line_gaussian_radius = wx.BoxSizer(wx.HORIZONTAL)
        line_gaussian_radius.AddMany(
            [
                (lbl_gaussian_radius, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 0),
                (self.spin_gaussian_radius, 0, wx.ALL | wx.EXPAND | wx.GROW, 0),
            ]
        )

        # Gaussian Standard Deviation Line
        lbl_std_dev = wx.StaticText(
            bsizer_mep.GetStaticBox(), -1, _("Gaussian Standard Deviation:")
        )
        self.spin_std_dev = wx.SpinCtrlDouble(
            bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(64, 23), inc=0.01
        )
        self.spin_std_dev.Enable(1)
        self.spin_std_dev.SetRange(0.01, 5.0)
        self.spin_std_dev.SetValue(self.conf.get("gaussian_sharpness"))

        self.spin_std_dev.Bind(wx.EVT_TEXT, partial(self.OnSelectStdDev, ctrl=self.spin_std_dev))
        self.spin_std_dev.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectStdDev, ctrl=self.spin_std_dev)
        )

        line_std_dev = wx.BoxSizer(wx.HORIZONTAL)
        line_std_dev.AddMany(
            [
                (lbl_std_dev, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 0),
                (self.spin_std_dev, 0, wx.ALL | wx.EXPAND | wx.GROW, 0),
            ]
        )

        # Dimensions size line
        lbl_dims_size = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Dimensions size:"))
        self.spin_dims_size = wx.SpinCtrl(bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(64, 23))
        self.spin_dims_size.Enable(1)
        self.spin_dims_size.SetIncrement(5)
        self.spin_dims_size.SetRange(10, 100)
        self.spin_dims_size.SetValue(self.conf.get("dimensions_size"))

        self.spin_dims_size.Bind(
            wx.EVT_TEXT, partial(self.OnSelectDimsSize, ctrl=self.spin_dims_size)
        )
        self.spin_dims_size.Bind(
            wx.EVT_SPINCTRL, partial(self.OnSelectDimsSize, ctrl=self.spin_dims_size)
        )

        line_dims_size = wx.BoxSizer(wx.HORIZONTAL)
        line_dims_size.AddMany(
            [
                (lbl_dims_size, 1, wx.EXPAND | wx.GROW | wx.TOP | wx.RIGHT | wx.LEFT, 0),
                (self.spin_dims_size, 0, wx.ALL | wx.EXPAND | wx.GROW, 0),
            ]
        )

        # Select Colormap Line
        lbl_colormap = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Select Colormap:"))
        lbl_colormap.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))

        self.combo_thresh = wx.ComboBox(
            bsizer_mep.GetStaticBox(),
            -1,
            "",  # size=(15,-1),
            choices=self.colormaps,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        self.combo_thresh.Bind(wx.EVT_COMBOBOX, self.OnSelectColormap)
        # by default use the initial value set in the configuration
        self.combo_thresh.SetSelection(self.colormaps.index(self.conf.get("mep_colormap")))
        # self.combo_thresh.SetSelection(0)

        colors_gradient = self.GenerateColormapColors(
            self.conf.get("mep_colormap"), self.number_colors
        )

        self.gradient = grad.GradientDisp(
            bsizer_mep.GetStaticBox(), -1, -5000, 5000, -5000, 5000, colors_gradient
        )

        colormap_gradient_sizer = wx.BoxSizer(wx.HORIZONTAL)
        colormap_gradient_sizer.AddMany(
            [
                (self.combo_thresh, 0, wx.EXPAND | wx.GROW | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5),
                (self.gradient, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5),
            ]
        )

        colormap_sizer = wx.BoxSizer(wx.VERTICAL)

        colormap_sizer.AddMany(
            [
                (lbl_colormap, 0, wx.TOP | wx.BOTTOM | wx.LEFT, 5),
                (colormap_gradient_sizer, 0, wx.GROW | wx.SHRINK | wx.LEFT | wx.RIGHT, 5),
            ]
        )

        colormap_custom = wx.BoxSizer(wx.VERTICAL)

        lbl_colormap_ranges = wx.StaticText(
            bsizer_mep.GetStaticBox(), -1, _("Custom Colormap Ranges")
        )
        lbl_colormap_ranges.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))

        lbl_min = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Min Value (uV):"))

        self.spin_min = wx.SpinCtrlDouble(
            bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(70, 23), inc=10
        )
        self.spin_min.Enable(1)
        self.spin_min.SetRange(0, 10000)
        self.spin_min.SetValue(self.conf.get("colormap_range_uv").get("min"))

        lbl_low = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Low Value (uV):"))
        self.spin_low = wx.SpinCtrlDouble(
            bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(70, 23), inc=10
        )
        self.spin_low.Enable(1)
        self.spin_low.SetRange(0, 10000)
        self.spin_low.SetValue(self.conf.get("colormap_range_uv").get("low"))

        lbl_mid = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Mid Value (uV):"))
        self.spin_mid = wx.SpinCtrlDouble(
            bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(70, 23), inc=10
        )
        self.spin_mid.Enable(1)
        self.spin_mid.SetRange(0, 10000)
        self.spin_mid.SetValue(self.conf.get("colormap_range_uv").get("mid"))

        lbl_max = wx.StaticText(bsizer_mep.GetStaticBox(), -1, _("Max Value (uV):"))
        self.spin_max = wx.SpinCtrlDouble(
            bsizer_mep.GetStaticBox(), -1, "", size=wx.Size(70, 23), inc=10
        )
        self.spin_max.Enable(1)
        self.spin_max.SetRange(0, 10000)
        self.spin_max.SetValue(self.conf.get("colormap_range_uv").get("max"))

        line_cm_texts = wx.BoxSizer(wx.HORIZONTAL)
        line_cm_texts.AddMany(
            [
                (lbl_min, 1, wx.EXPAND | wx.GROW | wx.RIGHT | wx.LEFT, 5),
                (lbl_low, 1, wx.EXPAND | wx.GROW | wx.RIGHT | wx.LEFT, 5),
                (lbl_mid, 1, wx.EXPAND | wx.GROW | wx.RIGHT | wx.LEFT, 5),
                (lbl_max, 1, wx.EXPAND | wx.GROW | wx.RIGHT | wx.LEFT, 5),
            ]
        )

        line_cm_spins = wx.BoxSizer(wx.HORIZONTAL)
        line_cm_spins.AddMany(
            [
                (self.spin_min, 0, wx.RIGHT | wx.LEFT | wx.EXPAND | wx.GROW, 12),
                (self.spin_low, 0, wx.RIGHT | wx.LEFT | wx.EXPAND | wx.GROW, 12),
                (self.spin_mid, 0, wx.RIGHT | wx.LEFT | wx.EXPAND | wx.GROW, 12),
                (self.spin_max, 0, wx.RIGHT | wx.LEFT | wx.EXPAND | wx.GROW, 12),
            ]
        )

        # Binding events for the colormap ranges
        for ctrl in zip(
            [self.spin_min, self.spin_low, self.spin_mid, self.spin_max],
            ["min", "low", "mid", "max"],
        ):
            ctrl[0].Bind(
                wx.EVT_TEXT, partial(self.OnSelectColormapRange, ctrl=ctrl[0], key=ctrl[1])
            )
            ctrl[0].Bind(
                wx.EVT_SPINCTRL, partial(self.OnSelectColormapRange, ctrl=ctrl[0], key=ctrl[1])
            )

        colormap_custom.AddMany(
            [
                (lbl_colormap_ranges, 0, wx.TOP | wx.BOTTOM | wx.LEFT, 5),
                (line_cm_texts, 0, wx.GROW | wx.SHRINK | wx.LEFT | wx.RIGHT, 0),
                (line_cm_spins, 0, wx.GROW | wx.SHRINK | wx.LEFT | wx.RIGHT, 0),
            ]
        )

        # Reset to defaults button
        btn_reset = wx.Button(bsizer_mep.GetStaticBox(), -1, _("Reset to defaults"))
        btn_reset.Bind(wx.EVT_BUTTON, self.ResetMEPSettings)

        # centered button reset
        colormap_custom.Add(btn_reset, 0, wx.ALIGN_CENTER | wx.TOP, 15)

        colormap_sizer.Add(colormap_custom, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        bsizer_mep.AddMany(
            [
                (surface_sel_sizer, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
                (line_gaussian_radius, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
                (line_std_dev, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
                (line_dims_size, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
                (colormap_sizer, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5),
            ]
        )

        return bsizer_mep

    def ResetMEPSettings(self, event):
        # fire an event that will reset the MEP settings to the default values in MEP Visualizer
        Publisher.sendMessage("Reset MEP Config")
        # self.session.SetConfig('mep_configuration', self.conf)
        self.UpdateMEPFromSession()

    def UpdateMEPFromSession(self):
        self.conf = dict(self.session.GetConfig("mep_configuration"))
        self.spin_gaussian_radius.SetValue(self.conf.get("gaussian_radius"))
        self.spin_std_dev.SetValue(self.conf.get("gaussian_sharpness"))
        self.spin_dims_size.SetValue(self.conf.get("dimensions_size"))

        self.combo_thresh.SetSelection(self.colormaps.index(self.conf.get("mep_colormap")))
        partial(self.OnSelectColormap, event=None, ctrl=self.combo_thresh)
        partial(self.OnSelectColormapRange, event=None, ctrl=self.spin_min, key="min")

        ranges = self.conf.get("colormap_range_uv")
        ranges = dict(ranges)
        self.spin_min.SetValue(ranges.get("min"))
        self.spin_low.SetValue(ranges.get("low"))
        self.spin_mid.SetValue(ranges.get("mid"))
        self.spin_max.SetValue(ranges.get("max"))

    def OnSelectStdDev(self, evt, ctrl):
        self.conf["gaussian_sharpness"] = ctrl.GetValue()
        # Save the configuration
        self.session.SetConfig("mep_configuration", self.conf)

    def OnSelectGaussianRadius(self, evt, ctrl):
        self.conf["gaussian_radius"] = ctrl.GetValue()
        # Save the configuration
        self.session.SetConfig("mep_configuration", self.conf)

    def OnSelectDimsSize(self, evt, ctrl):
        self.conf["dimensions_size"] = ctrl.GetValue()
        # Save the configuration
        self.session.SetConfig("mep_configuration", self.conf)

    def OnSelectColormapRange(self, evt, ctrl, key):
        self.conf["colormap_range_uv"][key] = ctrl.GetValue()
        self.session.SetConfig("mep_configuration", self.conf)

    def LoadSelection(self, values):
        rendering = values[const.RENDERING]
        surface_interpolation = values[const.SURFACE_INTERPOLATION]
        slice_interpolation = values[const.SLICE_INTERPOLATION]

        self.rb_rendering.SetSelection(int(rendering))
        self.rb_inter.SetSelection(int(surface_interpolation))
        self.rb_inter_sl.SetSelection(int(slice_interpolation))

    def OnSelectColormap(self, event=None):
        self.conf["mep_colormap"] = self.colormaps[self.combo_thresh.GetSelection()]
        colors = self.GenerateColormapColors(self.conf.get("mep_colormap"), self.number_colors)

        # Save the configuration
        self.session.SetConfig("mep_configuration", self.conf)
        Publisher.sendMessage("Save Preferences")
        self.UpdateGradient(self.gradient, colors)

    def GenerateColormapColors(self, colormap_name, number_colors=4):
        # Extract colors and positions
        color_def = const.MEP_COLORMAP_DEFINITIONS[colormap_name]
        colors = list(color_def.values())
        positions = [0.0, 0.25, 0.5, 1.0]  # Assuming even spacing between colors

        # Create LinearSegmentedColormap
        cmap = mcolors.LinearSegmentedColormap.from_list(
            colormap_name, list(zip(positions, colors))
        )
        colors_gradient = [
            (
                int(255 * cmap(i)[0]),
                int(255 * cmap(i)[1]),
                int(255 * cmap(i)[2]),
                int(255 * cmap(i)[3]),
            )
            for i in np.linspace(0, 1, number_colors)
        ]

        return colors_gradient

    def UpdateGradient(self, gradient, colors):
        gradient.SetGradientColours(colors)
        gradient.Refresh()
        gradient.Update()

        self.Refresh()
        self.Update()
        self.Show(True)

    def OnComboName(self, evt):
        from invesalius import project as prj

        self.proj = prj.Project()
        surface_index = self.combo_brain_surface_name.GetSelection()
        Publisher.sendMessage("Show single surface", index=surface_index, visibility=True)
        Publisher.sendMessage("Get brain surface actor", index=surface_index)
        Publisher.sendMessage("Press motor map button", pressed=True)

        self.button_colour.SetColour(
            [int(value * 255) for value in self.proj.surface_dict[surface_index].colour]
        )

    def OnSelectColour(self, evt):
        colour = [value / 255.0 for value in self.button_colour.GetColour()]
        Publisher.sendMessage(
            "Set surface colour",
            surface_index=self.combo_brain_surface_name.GetSelection(),
            colour=colour,
        )


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
    def __init__(self, parent, navigation, tracker, pedal_connector):
        wx.Panel.__init__(self, parent)

        self.session = ses.Session()

        self.coil_list = const.COIL

        self.tracker = tracker
        self.pedal_connector = pedal_connector
        self.navigation = navigation
        self.robot = Robot()
        self.coil_registrations = {}
        self.__bind_events()

        ### Sizer for TMS coil configuration ###
        self.config_lbl = wx.StaticText(self, -1, _("Current Configuration:"))
        self.config_lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))

        self.config_txt = wx.StaticText(
            self,
            -1,
            f"{os.path.basename(self.coil_registrations.get('default_coil', {}).get('path', 'None'))}",
        )

        tooltip = _("New TMS coil configuration")
        btn_new = wx.Button(self, -1, _("New"), size=wx.Size(65, 23))
        btn_new.SetToolTip(tooltip)
        btn_new.Enable(1)
        btn_new.Bind(wx.EVT_BUTTON, self.OnCreateNewCoil)

        tooltip = _("Load TMS coil configuration from an OBR file")
        btn_load = wx.Button(self, -1, _("Load"), size=wx.Size(65, 23))
        btn_load.SetToolTip(tooltip)
        btn_load.Enable(1)
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadCoilFromOBR)

        tooltip = _("Save TMS coil configuration to a file")
        btn_save = wx.Button(self, -1, _("Save"), size=wx.Size(65, 23))
        btn_save.SetToolTip(tooltip)
        btn_save.Enable(1)
        btn_save.Bind(wx.EVT_BUTTON, self.OnSaveCoilToOBR)

        coil_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("TMS coil registration"))
        inner_coil_sizer = wx.FlexGridSizer(3, 4, 5)
        inner_coil_sizer.AddMany(
            [
                (self.config_lbl, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (self.config_txt, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                ((0, 0), 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (btn_new, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (btn_load, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (btn_save, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            ]
        )
        coil_sizer.Add(inner_coil_sizer, 0, wx.ALL | wx.EXPAND, 10)

        ### Sizer for settings (conf_sizer) ###

        # Angle/Dist thresholds
        self.angle_threshold = self.session.GetConfig(
            "angle_threshold", const.DEFAULT_ANGLE_THRESHOLD
        )
        self.distance_threshold = self.session.GetConfig(
            "distance_threshold", const.DEFAULT_DISTANCE_THRESHOLD
        )

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

        conf_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Settings"))
        conf_sizer.AddMany(
            [
                (line_angle_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10),
                (line_dist_threshold, 0, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10),
            ]
        )

        ### Sizer for choosing which coils to use in navigation (multicoil)
        self.sel_sizer = sel_sizer = wx.StaticBoxSizer(
            wx.VERTICAL,
            self,
            _(
                f"TMS coil selection ({len(navigation.coil_registrations)} out of {navigation.n_coils})"
            ),
        )
        self.inner_sel_sizer = inner_sel_sizer = wx.FlexGridSizer(10, 1, 1)

        # Coils are selected by toggling coil-buttons
        self.coil_btns = {}
        self.no_coils_lbl = None
        if len(self.coil_registrations) == 0:
            self.no_coils_lbl = wx.StaticText(
                self, -1, _("No coils found in config.json. Create or load new coils below.")
            )
            inner_sel_sizer.Add(self.no_coils_lbl, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5)
        sel_sizer.Add(inner_sel_sizer, 0, wx.ALL | wx.EXPAND, 10)

        ### Sizer for choosing which coil is attached to the robot (multicoil) ###
        self.robot_sizer = robot_sizer = wx.StaticBoxSizer(
            wx.VERTICAL,
            self,
            _("Robot coil selection"),
        )
        self.inner_robot_sizer = inner_robot_sizer = wx.FlexGridSizer(2, 1, 1)

        self.robot_lbl = wx.StaticText(self, -1, _("Robot is connected. Coil attached to robot: "))
        self.choice_robot_coil = choice_robot_coil = wx.ComboBox(
            self,
            -1,
            f"{self.robot.GetCoilName() or ''}",
            size=wx.Size(90, 23),
            choices=list(
                self.navigation.coil_registrations
            ),  # List of coils selected for navigation
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )

        choice_robot_coil.SetToolTip(
            "Specify which coil is attached to the robot",
        )

        choice_robot_coil.Bind(wx.EVT_COMBOBOX, self.OnChoiceRobotCoil)

        if not self.robot.IsConnected():
            self.robot_lbl.SetLabel("Robot is not connected")
            choice_robot_coil.Show(False)  # Hide the combobox

        inner_robot_sizer.AddMany(
            [
                (self.robot_lbl, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
                (choice_robot_coil, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5),
            ]
        )

        robot_sizer.Add(inner_robot_sizer, 0, wx.ALL | wx.EXPAND, 10)

        ### Main sizer that contains all of the above GUI sizers ###
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [
                (coil_sizer, 0, wx.ALL | wx.EXPAND, 10),
                (sel_sizer, 0, wx.ALL | wx.EXPAND, 10),
                (robot_sizer, 0, wx.ALL | wx.EXPAND, 10),
                (conf_sizer, 0, wx.ALL | wx.EXPAND, 10),
            ]
        )
        self.SetSizerAndFit(main_sizer)

        self.LoadConfig()
        self.Layout()

    def __bind_events(self):
        Publisher.subscribe(self.OnSetCoilCount, "Reset coil selection")
        Publisher.subscribe(
            self.OnRobotConnectionStatus, "Robot to Neuronavigation: Robot connection status"
        )

    def OnRobotConnectionStatus(self, data):
        if data is None:
            return

        self.choice_robot_coil.Show(data)
        if data:
            self.robot_lbl.SetLabel("Robot is connected. Coil attached to robot: ")
        else:
            self.robot_lbl.SetLabel("Robot is not connected.")

    def OnChoiceRobotCoil(self, event):
        robot_coil_name = event.GetEventObject().GetStringSelection()
        self.robot.SetCoilName(robot_coil_name)

    def AddCoilButton(self, coil_name, show_button=True):
        if self.no_coils_lbl is not None:
            self.no_coils_lbl.Destroy()  # Remove obsolete message
            self.no_coils_lbl = None

        # Create a new button with coil_name if it doesn't already exist
        if coil_name not in self.coil_btns:
            coil_btn = wx.ToggleButton(self, -1, coil_name[:8], size=wx.Size(88, 17))
            coil_btn.SetToolTip(coil_name)
            coil_btn.Bind(
                wx.EVT_TOGGLEBUTTON, lambda event, name=coil_name: self.OnSelectCoil(event, name)
            )
            coil_btn.Bind(
                wx.EVT_RIGHT_DOWN, lambda event, name=coil_name: self.OnRightClickCoil(event, name)
            )
            coil_btn.Show(show_button)
            self.coil_btns[coil_name] = (coil_btn, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5)

            self.inner_sel_sizer.Add(coil_btn, 1, wx.EXPAND, 5)

    def ShowMulticoilGUI(self, show_multicoil):
        # Show/hide singlecoil configuration text
        self.config_txt.Show(not show_multicoil)
        self.config_lbl.Show(not show_multicoil)

        # Show/hide multicoil GUI elements
        self.sel_sizer.GetStaticBox().Show(show_multicoil)
        self.sel_sizer.ShowItems(show_multicoil)

        self.robot_sizer.GetStaticBox().Show(show_multicoil)
        self.robot_sizer.ShowItems(show_multicoil)

        # Show the robot coil combobox only if the robot is connected
        self.choice_robot_coil.Show(show_multicoil and self.robot.IsConnected())

        self.Layout()

    def OnSetCoilCount(self, n_coils):
        multicoil_mode = n_coils > 1

        if multicoil_mode:
            # Update multicoil GUI elements
            self.sel_sizer.GetStaticBox().SetLabel(f"TMS coil selection (0 out of {n_coils})")

            # Reset (enable and unpress) all coil-buttons
            for btn, *junk in self.coil_btns.values():
                btn.Enable()
                btn.SetValue(False)

        self.ShowMulticoilGUI(multicoil_mode)

    def LoadConfig(self):
        state = self.session.GetConfig("navigation", {})
        n_coils = state.get("n_coils", 1)
        multicoil_mode = n_coils > 1
        self.ShowMulticoilGUI(multicoil_mode)

        self.coil_registrations = self.session.GetConfig("coil_registrations", {})
        # Add a button for each coil
        for coil_name in self.coil_registrations:
            self.AddCoilButton(coil_name, show_button=multicoil_mode)

        # Press the buttons for coils that were selected in config file
        selected_coils = state.get("selected_coils", [])
        for coil_name in selected_coils:
            self.coil_btns[coil_name][0].SetValue(True)

        # Update labels
        self.config_txt.SetLabel(
            f"{os.path.basename(self.coil_registrations.get('default_coil', {}).get('path', 'None'))}"
        )

        n_coils_selected = len(selected_coils)
        self.sel_sizer.GetStaticBox().SetLabel(
            f"TMS coil selection ({n_coils_selected} out of {n_coils})"
        )

        if n_coils_selected == n_coils:
            self.CoilSelectionDone()

    def CoilSelectionDone(self):
        if self.navigation.n_coils == 1:  # Tell the robot the coil name
            self.robot.SetCoilName(next(iter(self.navigation.coil_registrations)))

        Publisher.sendMessage("Coil selection done", done=True)
        Publisher.sendMessage("Update status text in GUI", label=_("Ready"))

        # Allow only n_coils buttons to be pressed, so disable unpressed coil-buttons
        for btn, *junk in self.coil_btns.values():
            btn.Enable(btn.GetValue())

    def OnSelectCoil(self, event=None, name=None, select=False):
        if name is None:
            if not select:  # Unselect all coils
                Publisher.sendMessage("Reset coil selection", n_coils=self.navigation.n_coils)
            return

        coil_registration = None
        navigation = self.navigation

        if select or (event is not None and event.GetSelection()):  # If coil is selected
            coil_registration = self.coil_registrations[name]

            # Check that the index of the chosen coil does not conflict with other selected coils
            obj_id = coil_registration["obj_id"]
            selected_registrations = navigation.coil_registrations
            conflicting_coil_name = next(
                (
                    coil_name
                    for coil_name, registration in selected_registrations.items()
                    if registration["obj_id"] == obj_id
                ),
                None,
            )
            if conflicting_coil_name is not None:
                wx.MessageBox(
                    _(
                        f"Cannot select this coil, its index (obj_id = {obj_id}) conflicts with selected coil: {conflicting_coil_name}"
                    ),
                    _("InVesalius 3"),
                )
                self.coil_btns[name][0].SetValue(
                    False
                )  # Unpress the coil-button since its selection just failed
                return

            # Check that the tracker used to configure the coil matches the currently used tracker
            elif (obj_tracker_id := coil_registration["tracker_id"]) != self.tracker.tracker_id:
                wx.MessageBox(
                    _(
                        f"Cannot select this coil, its tracker [{const.TRACKERS[obj_tracker_id - 1]}] does not match the selected tracker [{const.TRACKERS[self.tracker.tracker_id - 1]}]"
                    ),
                    _("InVesalius 3"),
                )
                self.coil_btns[name][0].SetValue(False)  # Unpress the button
                return

            # Press the coil button here in case selection was done via code without pressing button
            self.coil_btns[name][0].SetValue(True)

        # Select/Unselect coil
        Publisher.sendMessage("Select coil", coil_name=name, coil_registration=coil_registration)

        n_coils_selected = len(navigation.coil_registrations)
        n_coils = navigation.n_coils

        # Update labels telling which coil is selected (for single coil mode) and how many coils to select (for multicoil mode)
        self.config_txt.SetLabel(
            f"{os.path.basename(self.coil_registrations.get('default_coil', {}).get('path', 'None'))}"
        )
        self.sel_sizer.GetStaticBox().SetLabel(
            f"TMS coil selection ({n_coils_selected} out of {n_coils})"
        )

        # Update robot coil combobox
        if self.choice_robot_coil is not None:
            self.choice_robot_coil.Set(list(navigation.coil_registrations))
            self.choice_robot_coil.SetStringSelection(self.robot.GetCoilName() or "")

        if n_coils_selected == n_coils:
            self.CoilSelectionDone()
        else:  # Enable all buttons
            Publisher.sendMessage("Coil selection done", done=False)
            for btn, *junk in self.coil_btns.values():
                btn.Enable(True)

    def OnRightClickCoil(self, event, name):
        def DeleteCoil(event, name):
            # Unselect the coil first
            self.OnSelectCoil(name, select=False)
            del self.coil_registrations[name]

            # Remove the coil-button
            self.coil_btns[name][0].Destroy()
            del self.coil_btns[name]

            # Remove the coil from the config file
            self.session.SetConfig("coil_registrations", self.coil_registrations)

            # Remove coil from navigation and CoilVisualizer
            Publisher.sendMessage("Select coil", coil_name=name, coil_registration=None)

        menu = wx.Menu()
        delete_coil = menu.Append(wx.ID_ANY, "Delete coil")
        save_coil = menu.Append(wx.ID_ANY, "Save coil to OBR file")

        self.Bind(wx.EVT_MENU, (lambda event, name=name: DeleteCoil(event, name)), delete_coil)
        self.Bind(
            wx.EVT_MENU,
            (lambda event, name=name: self.OnSaveCoilToOBR(event, coil_name=name)),
            save_coil,
        )
        self.PopupMenu(menu)
        menu.Destroy()

    def OnCreateNewCoil(self, event=None):
        # Create a coil registration and save it by the given name
        # Also used to edit coil registrations by overwriting to the same name
        if self.tracker.IsTrackerInitialized():
            dialog = dlg.ObjectCalibrationDialog(
                self.tracker,
                self.navigation.n_coils,
                self.pedal_connector,
            )
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    (coil_name, coil_path, obj_fiducials, obj_orients, obj_id, tracker_id) = (
                        dialog.GetValue()
                    )

                    if coil_name in self.coil_registrations and coil_name != "default_coil":
                        # Warn that we are overwriting an old registration
                        dialog = wx.TextEntryDialog(
                            None,
                            _(
                                "A registration with this name already exists. Enter a new name or overwrite an old coil registration"
                            ),
                            _("Warning: Coil Name Conflict"),
                            value=coil_name,
                        )
                        if dialog.ShowModal() == wx.ID_OK:
                            coil_name = (
                                dialog.GetValue().strip()
                            )  # Update coil_name with user input
                            dialog.Destroy()
                        else:
                            dialog.Destroy()
                            return  # Cancel the operation if the user closes the dialog or cancels

                    if np.isfinite(obj_fiducials).all() and np.isfinite(obj_orients).all():
                        coil_registration = {
                            "fiducials": obj_fiducials.tolist(),
                            "orientations": obj_orients.tolist(),
                            "obj_id": obj_id,
                            "tracker_id": tracker_id,
                            "path": coil_path.decode(const.FS_ENCODE),
                        }
                        self.coil_registrations[coil_name] = coil_registration
                        self.session.SetConfig("coil_registrations", self.coil_registrations)
                        self.AddCoilButton(coil_name)  # Add a button for this coil to GUI

                        # if we just edited a currently selected coil_name, unselect it (to avoid possible conflicts caused by new registration)
                        coil_btn = self.coil_btns[coil_name][0]
                        if coil_btn.GetValue():
                            coil_btn.SetValue(False)
                            self.OnSelectCoil(name=coil_name, select=False)

                        # Select the coil that was just created (if all coils have not been selected)
                        if len(self.navigation.coil_registrations) < self.navigation.n_coils:
                            self.OnSelectCoil(name=coil_name, select=True)
                        else:
                            coil_btn.Enable(
                                False
                            )  # All coils have been selected so disable the new button

                        # Show button only in multicoil mode
                        coil_btn.Show(self.navigation.n_coils > 1)

                    self.Layout()

            except wx.PyAssertionError:  # TODO FIX: win64
                pass
            dialog.Destroy()
        else:
            dlg.ShowNavigationTrackerWarning(0, "choose")

    def OnLoadCoilFromOBR(self, event=None):
        filename = dlg.ShowLoadSaveDialog(
            message=_("Load object registration"), wildcard=_("Registration files (*.obr)|*.obr")
        )

        try:
            if filename:
                with open(filename, "r") as text_file:
                    data = [s.split("\t") for s in text_file.readlines()]

                registration_coordinates = np.array(data[1:]).astype(np.float32)
                obj_fiducials = registration_coordinates[:, :3]
                obj_orients = registration_coordinates[:, 3:]

                coil_name = data[0][0][2:]
                coil_path = data[0][1].encode(const.FS_ENCODE)
                tracker_id = int(data[0][3])
                obj_id = int(data[0][-1])
                coil_name = "default_coil" if self.navigation.n_coils == 1 else coil_name

                # Handle old OBR file which lacks coil_name and tracker information
                if len(data[0]) < 6:
                    coil_name = "default_coil"
                    tracker_id = self.tracker.tracker_id

                if coil_name in self.coil_registrations and coil_name != "default_coil":
                    # Warn that we are overwriting an old registration
                    dialog = wx.TextEntryDialog(
                        None,
                        _(
                            "A registration with this name already exists. Enter a new name or overwrite an old coil registration"
                        ),
                        _("Warning: Coil Name Conflict"),
                        value=coil_name,
                    )
                    if dialog.ShowModal() == wx.ID_OK:
                        coil_name = dialog.GetValue().strip()  # Update coil_name with user input
                    else:
                        return  # Cancel the operation if the user closes the dialog or cancels
                    dialog.Destroy()

                if not os.path.exists(coil_path):
                    coil_path = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                polydata = vtk_utils.CreateObjectPolyData(coil_path)
                if not polydata:
                    coil_path = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil.stl")

                if np.isfinite(obj_fiducials).all() and np.isfinite(obj_orients).all():
                    coil_registration = {
                        "fiducials": obj_fiducials.tolist(),
                        "orientations": obj_orients.tolist(),
                        "obj_id": obj_id,
                        "tracker_id": tracker_id,
                        "path": coil_path.decode(const.FS_ENCODE),
                    }
                    self.coil_registrations[coil_name] = coil_registration
                    self.session.SetConfig("coil_registrations", self.coil_registrations)
                    self.AddCoilButton(coil_name)  # Add a button for this coil to GUI

                    # if we just overwrote a currently selected coil_name, unselect it (to avoid possible conflicts caused by this loaded registration)
                    coil_btn = self.coil_btns[coil_name][0]
                    if coil_btn.GetValue():
                        coil_btn.SetValue(False)
                        self.OnSelectCoil(name=coil_name, select=False)
                    elif self.navigation.CoilSelectionDone():
                        coil_btn.Enable(False)

                    if self.navigation.n_coils == 1:
                        # Select the coil that was just loaded for navigation
                        self.OnSelectCoil(
                            name="default_coil", select=False
                        )  # We have to unselect 1st since single coil mode causes edge-case bug
                        self.OnSelectCoil(name="default_coil", select=True)
                        # Hide the coil-button
                        coil_btn.Show(False)

                    self.Layout()

                Publisher.sendMessage(
                    "Update status text in GUI", label=_("Object file successfully loaded")
                )

                msg = _("Object file successfully loaded")
                wx.MessageBox(msg, _("InVesalius 3"))
        except:
            wx.MessageBox(_("Object registration file incompatible."), _("InVesalius 3"))
            Publisher.sendMessage("Update status text in GUI", label="")

    def OnSaveCoilToOBR(self, evt, coil_name=None):
        if coil_name is None:
            if self.navigation.n_coils > 1 and self.coil_registrations:
                # Specify the coil name if multicoil mode and if any exist
                dialog = wx.SingleChoiceDialog(
                    None,
                    _("Select which coil registration to save"),
                    _("Saving coil registration"),
                    choices=list(self.coil_registrations),
                )
                if dialog.ShowModal() == wx.ID_OK:
                    coil_name = dialog.GetStringSelection()
                else:
                    return  # Cancel the operation if the user closes the dialog or cancels
                dialog.Destroy()
            else:
                # In single coil mode there is only one coil to save
                coil_name = next(iter(self.coil_registrations), None)

        coil_registration = self.coil_registrations.get(coil_name, None)

        if coil_registration is None:  # No registration found by this name
            wx.MessageBox(_("Failed to save registration: No registration to save!"), _("Save"))
            return

        filename = dlg.ShowLoadSaveDialog(
            message=_("Save object registration as..."),
            wildcard=_("Registration files (*.obr)|*.obr"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            default_filename="object_registration.obr",
            save_ext="obr",
        )
        if filename:
            hdr = (
                coil_name
                + "\t"
                + utils.decode(coil_registration["path"], const.FS_ENCODE)
                + "\t"
                + "Tracker"
                + "\t"
                + str("%d" % coil_registration["tracker_id"])
                + "\t"
                + "Index"
                + "\t"
                + str("%d" % coil_registration["obj_id"])
            )
            data = np.hstack([coil_registration["fiducials"], coil_registration["orientations"]])
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


class TrackerTab(wx.Panel):
    def __init__(self, parent, tracker, robot):
        wx.Panel.__init__(self, parent)

        self.__bind_events()

        self.tracker = tracker
        self.robot = robot
        self.robot_ip = None
        self.matrix_tracker_to_robot = None
        self.n_coils = 1
        self.LoadConfig()

        # ComboBox for choosing the no. of coils to track
        n_coils_options = [str(n) for n in range(1, 10)]
        select_n_coils_elem = wx.ComboBox(
            self,
            -1,
            "",
            size=(145, -1),
            choices=n_coils_options,
            style=wx.CB_DROPDOWN | wx.CB_READONLY,
        )
        tooltip = _("Choose the number of coils to track")
        select_n_coils_elem.SetToolTip(tooltip)
        select_n_coils_elem.SetSelection(self.n_coils - 1)
        select_n_coils_elem.Bind(
            wx.EVT_COMBOBOX, partial(self.OnChooseNoOfCoils, ctrl=select_n_coils_elem)
        )

        select_n_coils_label = wx.StaticText(self, -1, _("Choose the number of coils to track:"))

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

        ref_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=5, vgap=5)
        ref_sizer.AddMany(
            [
                (select_n_coils_label, wx.LEFT),
                (select_n_coils_elem, wx.RIGHT),
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
        self.n_coils = session.GetConfig("navigation", {}).get("n_coils", 1)

        state = session.GetConfig("robot", {})

        self.robot_ip = state.get("robot_ip", None)
        self.matrix_tracker_to_robot = state.get("tracker_to_robot", None)
        if self.matrix_tracker_to_robot is not None:
            self.matrix_tracker_to_robot = np.array(self.matrix_tracker_to_robot)

    def OnChooseNoOfCoils(self, evt, ctrl):
        old_n_coils = self.n_coils
        if hasattr(evt, "GetSelection"):
            choice = evt.GetSelection()
            self.n_coils = choice + 1
        else:
            self.n_coils = 1

        if self.n_coils != old_n_coils:  # if n_coils was changed reset connection
            tracker_id = self.tracker.tracker_id
            self.tracker.DisconnectTracker()
            self.tracker.SetTracker(tracker_id, n_coils=self.n_coils)

        ctrl.SetSelection(self.n_coils - 1)
        Publisher.sendMessage("Reset coil selection", n_coils=self.n_coils)
        Publisher.sendMessage("Coil selection done", done=False)

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
        self.tracker.SetTracker(choice, n_coils=self.n_coils)
        Publisher.sendMessage("Update status text in GUI", label=_("Ready"))
        Publisher.sendMessage("Tracker changed")
        Publisher.sendMessage("Reset coil selection", n_coils=self.n_coils)
        Publisher.sendMessage("Coil selection done", done=False)
        ctrl.SetSelection(self.tracker.tracker_id)
        Publisher.sendMessage("End busy cursor")
        if sys.platform == "darwin":
            wx.CallAfter(self.GetParent().Show)
        else:
            self.ShowParent()

    def OnChooseReferenceMode(self, evt, ctrl):
        Navigation(None, None).SetReferenceMode(evt.GetSelection())

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
