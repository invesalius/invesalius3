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
import itertools
import os
import time
from functools import partial

import numpy as np

try:
    # TODO: the try-except could be done inside the mTMS() method call
    from invesalius.navigation.mtms import mTMS

    mTMS()
    has_mTMS = True
except:
    has_mTMS = False

import sys
import uuid

import wx

try:
    import wx.lib.agw.foldpanelbar as fpb
except ImportError:
    import wx.lib.foldpanelbar as fpb

import wx.lib.colourselect as csel
import wx.lib.masked.numctrl
import wx.lib.platebtn as pbtn
from wx.lib.mixins.listctrl import ColumnSorterMixin

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
import invesalius.project as prj
import invesalius.session as ses
from invesalius import inv_paths, utils
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.gui.widgets.fiducial_buttons import OrderedFiducialButtons
from invesalius.navigation.navigation import NavigationHub
from invesalius.navigation.robot import RobotObjective
from invesalius.pubsub import pub as Publisher

BTN_NEW = wx.NewIdRef()
BTN_IMPORT_LOCAL = wx.NewIdRef()


def GetBitMapForBackground():
    image_file = os.path.join("head.png")
    bmp = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath(image_file)), wx.BITMAP_TYPE_PNG)
    return bmp


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
        default_colour = self.GetBackgroundColour()
        background_colour = wx.Colour(255, 255, 255)
        self.SetBackgroundColour(background_colour)

        # Fold panel which contains navigation configurations
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)

        # Add line sizer into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(fold_panel, 1, wx.GROW | wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        main_sizer.AddSpacer(5)
        main_sizer.Fit(self)

        self.SetSizerAndFit(main_sizer)
        self.Update()
        self.SetAutoLayout(1)

        self.sizer = main_sizer


class FoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerFoldPanel(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(inner_panel, 0, wx.EXPAND | wx.GROW)
        sizer.Fit(self)

        self.SetSizerAndFit(sizer)
        self.Update()
        self.SetAutoLayout(1)


class InnerFoldPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.__bind_events()
        # Fold panel and its style settings
        # FIXME: If we dont insert a value in size or if we set wx.DefaultSize,
        # the fold_panel doesnt show. This means that, for some reason, Sizer
        # is not working properly in this panel. It might be on some child or
        # parent panel. Perhaps we need to insert the item into the sizer also...
        # Study this.

        fold_panel = fpb.FoldPanelBar(
            self, -1, wx.DefaultPosition, (10, 800), 0, fpb.FPB_SINGLE_FOLD
        )
        gbs = wx.GridBagSizer(5, 5)
        gbs.AddGrowableCol(0, 1)
        self.gbs = gbs

        # Initialize Navigation, Tracker, Robot, Image, and PedalConnection objects here to make them
        # available to several panels.
        nav_hub = NavigationHub(window=self)

        self.nav_hub = nav_hub
        self.tracker = nav_hub.tracker
        self.image = nav_hub.image
        self.navigation = nav_hub.navigation
        self.mep_visualizer = nav_hub.mep_visualizer

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        item = fold_panel.AddFoldPanel(_("Coregistration"), collapsed=True)
        ntw = CoregistrationPanel(parent=item, nav_hub=nav_hub)
        self.fold_panel = fold_panel
        self.__calc_best_size(ntw)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, spacing=0, leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        item = fold_panel.AddFoldPanel(_("Navigation"), collapsed=True)
        self.__id_nav = item.GetId()
        ntw = NavigationPanel(parent=item, nav_hub=nav_hub)

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, spacing=0, leftSpacing=0, rightSpacing=0)
        self.fold_panel.Bind(fpb.EVT_CAPTIONBAR, self.OnFoldPressCaption)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gbs, 1, wx.GROW | wx.EXPAND)
        self.SetSizer(sizer)
        sizer.Fit(self)

        self.track_obj = False
        gbs.Add(fold_panel, (0, 0), flag=wx.EXPAND)
        gbs.Layout()
        sizer.Fit(self)
        self.Fit()

        self.__bind_events()
        self.Update()
        self.SetAutoLayout(1)

    def __bind_events(self):
        # Publisher.subscribe(self.OnShowDbs, "Show dbs folder")
        # Publisher.subscribe(self.OnHideDbs, "Hide dbs folder")
        Publisher.subscribe(self.OpenNavigation, "Open navigation menu")
        Publisher.subscribe(self.OnEnableState, "Enable state project")

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

    def OnEnableState(self, state):
        if not state:
            self.fold_panel.Expand(self.fold_panel.GetFoldPanel(0))
            Publisher.sendMessage("Move to image page")

    def OnShowDbs(self):
        self.dbs_item.Show()

    def OnHideDbs(self):
        self.dbs_item.Hide()

    def OnCheckStatus(self, nav_status, vis_status):
        if nav_status:
            self.checkbox_serial_port.Enable(False)
        else:
            self.checkbox_serial_port.Enable(True)

    def OnEnableSerialPort(self, evt, ctrl):
        if ctrl.GetValue():
            from wx import ID_OK

            dlg_port = dlg.SetCOMPort(select_baud_rate=False)

            if dlg_port.ShowModal() != ID_OK:
                ctrl.SetValue(False)
                return

            com_port = dlg_port.GetCOMPort()
            baud_rate = 115200

            Publisher.sendMessage(
                "Update serial port",
                serial_port_in_use=True,
                com_port=com_port,
                baud_rate=baud_rate,
            )
        else:
            Publisher.sendMessage("Update serial port", serial_port_in_use=False)

    # 'Show coil' button

    # Called when the 'Show coil' button is pressed elsewhere in code.
    def PressShowCoilButton(self, pressed=False):
        self.show_coil_button.SetValue(pressed)
        self.OnShowCoil()

    def EnableShowCoilButton(self, enabled=False):
        self.show_coil_button.Enable(enabled)

    def OnShowCoil(self, evt=None):
        pressed = self.show_coil_button.GetValue()
        Publisher.sendMessage("Show coil in viewer volume", state=pressed)

    def OnFoldPressCaption(self, evt):
        id = evt.GetTag().GetId()
        expanded = evt.GetFoldStatus()

        if id == self.__id_nav:
            status = self.CheckRegistration()

        if not expanded:
            self.fold_panel.Expand(evt.GetTag())
        else:
            self.fold_panel.Collapse(evt.GetTag())

    def ResizeFPB(self):
        sizeNeeded = self.fold_panel.GetPanelsLength(0, 0)[2]
        self.fold_panel.SetMinSize((self.fold_panel.GetSize()[0], sizeNeeded))
        self.fold_panel.SetSize((self.fold_panel.GetSize()[0], sizeNeeded))

    def CheckRegistration(self):
        return (
            self.tracker.AreTrackerFiducialsSet()
            and self.image.AreImageFiducialsSet()
            and self.navigation.GetObjectRegistration() is not None
        )

    def OpenNavigation(self):
        self.fold_panel.Expand(self.fold_panel.GetFoldPanel(1))


class CoregistrationPanel(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        # Changed from default color for OSX
        background_colour = (255, 255, 255)
        self.SetBackgroundColour(background_colour)

        book = wx.Notebook(self, -1, style=wx.BK_DEFAULT)
        book.Bind(wx.EVT_BOOKCTRL_PAGE_CHANGING, self.OnPageChanging)
        book.Bind(wx.EVT_BOOKCTRL_PAGE_CHANGED, self.OnPageChanged)
        if sys.platform != "win32":
            book.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        self.nav_hub = nav_hub
        self.tracker = nav_hub.tracker
        self.image = nav_hub.image

        book.AddPage(ImagePage(book, nav_hub), _("Image"))
        book.AddPage(TrackerPage(book, nav_hub), _("Patient"))
        book.AddPage(RefinePage(book, nav_hub), _("Refine"))
        book.AddPage(StimulatorPage(book, nav_hub), _("TMS Coil"))

        book.SetSelection(0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(book, 0, wx.EXPAND)
        self.SetSizer(sizer)

        book.Refresh()
        self.book = book
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self._FoldTracker, "Move to tracker page")
        Publisher.subscribe(self._FoldRefine, "Move to refine page")
        Publisher.subscribe(self._FoldStimulator, "Move to stimulator page")
        Publisher.subscribe(self._FoldImage, "Move to image page")

    def OnPageChanging(self, evt):
        page = evt.GetOldSelection()

    def OnPageChanged(self, evt):
        old_page = evt.GetOldSelection()
        new_page = evt.GetSelection()

        # old page validations
        if old_page == 0:
            # Do not allow user to move to other (forward) tabs if image fiducials not done.
            if not self.image.AreImageFiducialsSet():
                self.book.SetSelection(0)
                wx.MessageBox(_("Please do the image registration first."), _("InVesalius 3"))
        if old_page != 2:
            # Load data into refine tab
            Publisher.sendMessage("Update UI for refine tab")

        # new page validations
        if (old_page == 1) and (new_page == 2 or new_page == 3):
            # Do not allow user to move to other (forward) tabs if tracker fiducials not done.
            if self.image.AreImageFiducialsSet() and not self.tracker.AreTrackerFiducialsSet():
                self.book.SetSelection(1)
                wx.MessageBox(_("Please do the tracker registration first."), _("InVesalius 3"))

    # Unfold specific notebook pages
    def _FoldImage(self):
        self.book.SetSelection(0)

    def _FoldTracker(self):
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_CROSS)
        self.book.SetSelection(1)

    def _FoldRefine(self):
        self.book.SetSelection(2)

    def _FoldStimulator(self):
        self.book.SetSelection(3)


class ImagePage(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)

        self.image = nav_hub.image
        self.btns_set_fiducial = [None, None, None]
        self.numctrls_fiducial = [[], [], []]
        self.current_coord = 0, 0, 0, None, None, None

        self.bg_bmp = GetBitMapForBackground()
        # Toggle buttons for image fiducials
        background = wx.StaticBitmap(self, -1, self.bg_bmp, (0, 0))
        for n, fiducial in enumerate(const.IMAGE_FIDUCIALS):
            button_id = fiducial["button_id"]
            label = fiducial["label"]
            tip = fiducial["tip"]

            ctrl = wx.ToggleButton(self, button_id, label=label, style=wx.BU_EXACTFIT)
            ctrl.SetToolTip(tip)
            ctrl.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnImageFiducials, n))
            ctrl.Disable()

            self.btns_set_fiducial[n] = ctrl

        for m in range(len(self.btns_set_fiducial)):
            for n in range(3):
                self.numctrls_fiducial[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1)
                )
                self.numctrls_fiducial[m][n].Hide()

        start_button = wx.ToggleButton(self, label="Start Registration")
        start_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnStartRegistration, ctrl=start_button))
        self.start_button = start_button

        reset_button = wx.Button(self, label="Reset", style=wx.BU_EXACTFIT)
        reset_button.Bind(wx.EVT_BUTTON, partial(self.OnReset, ctrl=reset_button))
        self.reset_button = reset_button

        next_button = wx.Button(self, label="Next")
        next_button.Bind(wx.EVT_BUTTON, partial(self.OnNext))
        next_button.Disable()
        self.next_button = next_button

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.AddMany([(start_button), (reset_button)])

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(next_button)

        sizer = wx.GridBagSizer(5, 5)
        sizer.Add(
            self.btns_set_fiducial[1],
            wx.GBPosition(1, 0),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        sizer.Add(
            self.btns_set_fiducial[2],
            wx.GBPosition(0, 2),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_HORIZONTAL,
        )
        sizer.Add(
            self.btns_set_fiducial[0],
            wx.GBPosition(1, 3),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        sizer.Add(background, wx.GBPosition(1, 2))

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [
                (top_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10),
                (sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, 5),
                (bottom_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.TOP, 30),
            ]
        )
        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.LoadImageFiducials, "Load image fiducials")
        Publisher.subscribe(self.SetImageFiducial, "Set image fiducial")
        Publisher.subscribe(self.UpdateImageCoordinates, "Set cross focal point")
        Publisher.subscribe(self.OnResetImageFiducials, "Reset image fiducials")
        Publisher.subscribe(self._OnStateProject, "Enable state project")
        Publisher.subscribe(self.StopRegistration, "Stop image registration")

    def _OnStateProject(self, state):
        self.UpdateData()

    def UpdateData(self):
        """
        Update UI elements based on fiducial data in self.image
        """
        for m, btn in enumerate(self.btns_set_fiducial):
            btn.SetValue(self.image.IsImageFiducialSet(m))

            for n in range(3):
                value = self.image.GetImageFiducialForUI(m, n)
                self.numctrls_fiducial[m][n].SetValue(value)

        self.UpdateNextButton()

    def LoadImageFiducials(self, label, position):
        fiducial = self.GetFiducialByAttribute(const.IMAGE_FIDUCIALS, "fiducial_name", label[:2])

        fiducial_index = fiducial["fiducial_index"]
        fiducial_name = fiducial["fiducial_name"]

        Publisher.sendMessage("Set image fiducial", fiducial_name=fiducial_name, position=position)

        self.btns_set_fiducial[fiducial_index].SetValue(True)
        for m in [0, 1, 2]:
            self.numctrls_fiducial[fiducial_index][m].SetValue(position[m])

        self.UpdateNextButton()

    def GetFiducialByAttribute(self, fiducials, attribute_name, attribute_value):
        found = [fiducial for fiducial in fiducials if fiducial[attribute_name] == attribute_value]

        assert len(found) != 0, "No fiducial found for which {} = {}".format(
            attribute_name, attribute_value
        )
        return found[0]

    def SetImageFiducial(self, fiducial_name, position):
        fiducial = self.GetFiducialByAttribute(
            const.IMAGE_FIDUCIALS, "fiducial_name", fiducial_name
        )
        fiducial_index = fiducial["fiducial_index"]

        self.image.SetImageFiducial(fiducial_index, position)

        if self.image.AreImageFiducialsSet():
            self.StopRegistration()
        self.UpdateNextButton()

    def UpdateImageCoordinates(self, position):
        self.current_coord = position

        for m in [0, 1, 2]:
            if not self.btns_set_fiducial[m].GetValue():
                for n in [0, 1, 2]:
                    self.numctrls_fiducial[m][n].SetValue(float(position[n]))

    def OnImageFiducials(self, n, evt):
        fiducial_name = const.IMAGE_FIDUCIALS[n]["fiducial_name"]

        if self.btns_set_fiducial[n].GetValue():
            position = (
                self.numctrls_fiducial[n][0].GetValue(),
                self.numctrls_fiducial[n][1].GetValue(),
                self.numctrls_fiducial[n][2].GetValue(),
            )
        else:
            for m in [0, 1, 2]:
                self.numctrls_fiducial[n][m].SetValue(float(self.current_coord[m]))
            position = np.nan

        Publisher.sendMessage("Set image fiducial", fiducial_name=fiducial_name, position=position)

    def OnNext(self, evt):
        Publisher.sendMessage("Move to tracker page")

    def UpdateNextButton(self):
        self.next_button.Enable(self.image.AreImageFiducialsSet())

    def OnReset(self, evt, ctrl):
        self.image.ResetImageFiducials()
        self.OnResetImageFiducials()

    def OnResetImageFiducials(self):
        self.next_button.Disable()
        for ctrl in self.btns_set_fiducial:
            ctrl.SetValue(False)
        self.start_button.SetValue(False)
        self.OnStartRegistration(self.start_button, self.start_button)

    def StartRegistration(self):
        Publisher.sendMessage("Enable style", style=const.STATE_REGISTRATION)
        for button in self.btns_set_fiducial:
            button.Enable()
        self.start_button.SetLabel("Stop Registration")
        self.start_button.SetValue(True)

    def StopRegistration(self):
        self.start_button.SetLabel("Start Registration")
        self.start_button.SetValue(False)
        for button in self.btns_set_fiducial:
            button.Disable()
        Publisher.sendMessage("Disable style", style=const.STATE_REGISTRATION)

    def OnStartRegistration(self, evt, ctrl):
        value = ctrl.GetValue()
        if value:
            self.StartRegistration()
        else:
            self.StopRegistration()


class TrackerPage(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)

        self.icp = nav_hub.icp
        self.tracker = nav_hub.tracker
        self.navigation = nav_hub.navigation
        self.pedal_connector = nav_hub.pedal_connector

        self.START_REGISTRATION_LABEL = _("Start Patient Registration")
        self.STOP_REGISTRATION_LABEL = _("Stop Patient Registration")
        self.registration_on = False

        self.bg_bmp = GetBitMapForBackground()

        # Toggle buttons for image fiducials
        self.fiducial_buttons = OrderedFiducialButtons(
            self,
            const.TRACKER_FIDUCIALS,
            self.tracker.IsTrackerFiducialSet,
            order=const.FIDUCIAL_REGISTRATION_ORDER,
        )
        background = wx.StaticBitmap(self, -1, self.bg_bmp, (0, 0))

        for index, btn in enumerate(self.fiducial_buttons):
            btn.Bind(wx.EVT_BUTTON, partial(self.OnFiducialButton, index))
            btn.Disable()

        self.fiducial_buttons.Update()

        register_button = wx.Button(self, label="Record Fiducial")
        register_button.Bind(wx.EVT_BUTTON, partial(self.OnRegister))
        register_button.Disable()
        self.register_button = register_button

        start_button = wx.ToggleButton(self, label="Start Patient Registration")
        start_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnStartRegistration, ctrl=start_button))
        self.start_button = start_button

        reset_button = wx.Button(self, label="Reset", style=wx.BU_EXACTFIT)
        reset_button.Bind(wx.EVT_BUTTON, partial(self.OnReset))
        self.reset_button = reset_button

        back_button = wx.Button(self, label="Back")
        back_button.Bind(wx.EVT_BUTTON, partial(self.OnBack))
        self.back_button = back_button

        preferences_button = wx.Button(self, label="Change tracker")
        preferences_button.Bind(wx.EVT_BUTTON, partial(self.OnPreferences))
        self.preferences_button = preferences_button

        next_button = wx.Button(self, label="Next")
        next_button.Bind(wx.EVT_BUTTON, partial(self.OnNext))
        if not self.tracker.AreTrackerFiducialsSet():
            next_button.Disable()
        self.next_button = next_button

        tracker_status = self.tracker.IsTrackerInitialized()
        current_label = wx.StaticText(self, -1, _("Current tracker: "))
        current_label.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        main_label = wx.StaticText(self, -1, _("No tracker selected"))

        if tracker_status:
            main_label.SetLabel(self.tracker.get_trackers()[self.tracker.GetTrackerId() - 1])

        self.main_label = main_label

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.AddMany([(start_button), (reset_button)])

        middle_sizer = wx.BoxSizer(wx.HORIZONTAL)
        middle_sizer.AddMany([(current_label), (main_label)])

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.AddMany(
            [
                (back_button, 0, wx.EXPAND),
                (preferences_button, 0, wx.EXPAND),
                (next_button, 0, wx.EXPAND),
            ]
        )

        sizer = wx.GridBagSizer(5, 5)
        sizer.Add(
            self.fiducial_buttons[1],
            wx.GBPosition(1, 0),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        sizer.Add(
            self.fiducial_buttons[2],
            wx.GBPosition(0, 2),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_HORIZONTAL,
        )
        sizer.Add(
            self.fiducial_buttons[0],
            wx.GBPosition(1, 3),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )

        sizer.Add(background, wx.GBPosition(1, 2))

        sizer.Add(
            register_button,
            wx.GBPosition(2, 2),
            span=wx.GBSpan(1, 2),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.EXPAND,
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [
                (top_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10),
                (sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, 5),
                (middle_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20),
                (5, 5),
                (bottom_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20),
            ]
        )

        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetTrackerFiducial, "Set tracker fiducial")
        Publisher.subscribe(self.OnTrackerChanged, "Tracker changed")
        Publisher.subscribe(self.OnResetTrackerFiducials, "Reset tracker fiducials")

    def UpdateElements(self):
        if self.tracker.AreTrackerFiducialsSet():
            self.next_button.Enable()
        else:
            self.next_button.Disable()
        self.fiducial_buttons.Update()

    def StartRegistration(self):
        if not self.tracker.IsTrackerInitialized():
            self.start_button.SetValue(False)
            dlg.ShowNavigationTrackerWarning(0, "choose")
            return

        self.registration_on = True
        for button in self.fiducial_buttons:
            button.Enable()
        self.fiducial_buttons.FocusNext()
        self.register_button.Enable()
        self.start_button.SetLabel(self.STOP_REGISTRATION_LABEL)

        def set_fiducial_callback(state):
            index = self.fiducial_buttons.focused_index
            if state and index is not None:
                self.SetTrackerFiducial(index)

        self.pedal_connector.add_callback(
            "fiducial", set_fiducial_callback, remove_when_released=False
        )

    def StopRegistration(self):
        self.registration_on = False
        for button in self.fiducial_buttons:
            button.Disable()

        self.fiducial_buttons.ClearFocus()
        self.register_button.Disable()
        self.start_button.SetValue(False)
        self.start_button.SetLabel(self.START_REGISTRATION_LABEL)

        self.pedal_connector.remove_callback("fiducial")

    def GetFiducialByAttribute(self, fiducials, attribute_name, attribute_value):
        found = [fiducial for fiducial in fiducials if fiducial[attribute_name] == attribute_value]

        assert len(found) != 0, "No fiducial found for which {} = {}".format(
            attribute_name, attribute_value
        )
        return found[0]

    def OnSetTrackerFiducial(self, fiducial_name):
        fiducial = self.GetFiducialByAttribute(
            const.TRACKER_FIDUCIALS,
            "fiducial_name",
            fiducial_name,
        )
        fiducial_index = fiducial["fiducial_index"]
        self.SetTrackerFiducial(fiducial_index)

    def SetTrackerFiducial(self, fiducial_index):
        # XXX: The reference mode is fetched from navigation object, however it seems like not quite
        #      navigation-related attribute here, as the reference mode used during the fiducial registration
        #      is more concerned with the calibration than the navigation.
        #
        ref_mode_id = self.navigation.GetReferenceMode()
        success = self.tracker.SetTrackerFiducial(ref_mode_id, fiducial_index)

        # Setting the fiducial is not successful if head or probe markers are not visible.
        # In that case, return early and do not move to the next fiducial.
        if not success:
            return

        self.ResetICP()
        self.fiducial_buttons.Set(fiducial_index)

        if self.tracker.AreTrackerFiducialsSet():
            # All tracker fiducials are set; publish a message to pass the fiducials to, e.g., robot.
            Publisher.sendMessage("Tracker fiducials set")

            self.next_button.Enable()
            self.StopRegistration()

        self.Refresh()

    def OnFiducialButton(self, index, evt):
        button = self.fiducial_buttons[index]

        if button is self.fiducial_buttons.focused:
            self.SetTrackerFiducial(index)
        elif not self.tracker.IsTrackerFiducialSet(index):
            self.fiducial_buttons.Focus(index)

    def OnRegister(self, evt):
        index = self.fiducial_buttons.focused_index
        if index is not None:
            self.SetTrackerFiducial(index)

    def ResetICP(self):
        self.icp.ResetICP()
        # self.checkbox_icp.Enable(False)
        # self.checkbox_icp.SetValue(False)

    def OnReset(self, evt):
        self.tracker.ResetTrackerFiducials()
        self.Refresh()

    def OnResetTrackerFiducials(self):
        self.UpdateElements()

        if self.registration_on:
            self.fiducial_buttons.FocusNext()

    def OnNext(self, evt):
        Publisher.sendMessage("Move to refine page")

    def OnBack(self, evt):
        Publisher.sendMessage("Move to image page")

    def OnPreferences(self, evt):
        Publisher.sendMessage("Open preferences menu", page=2)

    def OnStartRegistration(self, evt, ctrl):
        started = ctrl.GetValue()
        if started:
            self.tracker.ResetTrackerFiducials()
            self.StartRegistration()
        else:
            self.StopRegistration()

    def OnTrackerChanged(self):
        if self.tracker.GetTrackerId() != const.DEFAULT_TRACKER:
            self.main_label.SetLabel(self.tracker.get_trackers()[self.tracker.GetTrackerId() - 1])
        else:
            self.main_label.SetLabel(_("No tracker selected"))


class RefinePage(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)
        self.icp = nav_hub.icp
        self.tracker = nav_hub.tracker
        self.image = nav_hub.image
        self.navigation = nav_hub.navigation

        self.numctrls_fiducial = [[], [], [], [], [], []]
        const_labels = [label for label in const.FIDUCIAL_LABELS]
        labels = const_labels + const_labels  # duplicate labels for image and tracker
        self.labels = [wx.StaticText(self, -1, _(label)) for label in labels]

        for m in range(6):
            for n in range(3):
                if m <= 2:
                    value = self.image.GetImageFiducialForUI(m, n)
                else:
                    value = self.tracker.GetTrackerFiducialForUI(m - 3, n)

                self.numctrls_fiducial[m].append(
                    wx.lib.masked.numctrl.NumCtrl(
                        parent=self, integerWidth=4, fractionWidth=1, value=value
                    )
                )

        txt_label_image = wx.StaticText(self, -1, _("Image Fiducials:"))
        txt_label_image.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        coord_sizer = wx.GridBagSizer(hgap=5, vgap=0)

        for m in range(3):
            coord_sizer.Add(self.labels[m], pos=wx.GBPosition(m, 0))
            for n in range(3):
                coord_sizer.Add(self.numctrls_fiducial[m][n], pos=wx.GBPosition(m, n + 1))
                if m in range(6):
                    self.numctrls_fiducial[m][n].SetEditable(False)

        txt_label_track = wx.StaticText(self, -1, _("Tracker Fiducials:"))
        txt_label_track.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        coord_sizer_track = wx.GridBagSizer(hgap=5, vgap=0)

        for m in range(3, 6):
            coord_sizer_track.Add(self.labels[m], pos=wx.GBPosition(m - 3, 0))
            for n in range(3):
                coord_sizer_track.Add(self.numctrls_fiducial[m][n], pos=wx.GBPosition(m - 3, n + 1))
                if m in range(1, 6):
                    self.numctrls_fiducial[m][n].SetEditable(False)

        txt_fre = wx.StaticText(self, -1, _("FRE:"))
        tooltip = _("Fiducial registration error")
        txt_fre.SetToolTip(tooltip)

        value = self.icp.GetFreForUI()
        txtctrl_fre = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        txtctrl_fre.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        txtctrl_fre.SetBackgroundColour("WHITE")
        txtctrl_fre.SetEditable(0)
        txtctrl_fre.SetToolTip(tooltip)
        self.txtctrl_fre = txtctrl_fre

        self.OnUpdateUI()

        fre_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        fre_sizer.AddMany(
            [
                (txt_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
                (txtctrl_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
            ]
        )

        back_button = wx.Button(self, label="Back")
        back_button.Bind(wx.EVT_BUTTON, partial(self.OnBack))
        self.back_button = back_button

        refine_button = wx.Button(self, label="Refine")
        refine_button.Bind(wx.EVT_BUTTON, partial(self.OnRefine))
        self.refine_button = refine_button

        next_button = wx.Button(self, label="Next")
        next_button.Bind(wx.EVT_BUTTON, partial(self.OnNext))
        self.next_button = next_button

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddMany(
            [
                (back_button, 0, wx.EXPAND),
                (refine_button, 0, wx.EXPAND),
                (next_button, 0, wx.EXPAND),
            ]
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [
                (txt_label_image, 0, wx.EXPAND | wx.ALL, 10),
                (coord_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                (txt_label_track, 0, wx.EXPAND | wx.ALL, 10),
                (coord_sizer_track, 0, wx.ALIGN_CENTER_HORIZONTAL),
                (10, 10, 0),
                (fre_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
                (button_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 20),
                (10, 10, 0),
            ]
        )
        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnUpdateUI, "Update UI for refine tab")
        Publisher.subscribe(self.OnResetTrackerFiducials, "Reset tracker fiducials")

    def OnUpdateUI(self):
        for m in range(6):
            for n in range(3):
                if m <= 2:
                    value = self.image.GetImageFiducialForUI(m, n)
                else:
                    value = self.tracker.GetTrackerFiducialForUI(m - 3, n)
                self.numctrls_fiducial[m][n].SetValue(value)

        if self.tracker.AreTrackerFiducialsSet() and self.image.AreImageFiducialsSet():
            self.navigation.EstimateTrackerToInVTransformationMatrix(self.tracker, self.image)
            self.navigation.UpdateFiducialRegistrationError(self.tracker, self.image)
            fre, fre_ok = self.navigation.GetFiducialRegistrationError(self.icp)

            self.txtctrl_fre.SetValue(str(round(fre, 2)))
            if fre_ok:
                self.txtctrl_fre.SetBackgroundColour(const.GREEN_COLOR_RGB)
            else:
                self.txtctrl_fre.SetBackgroundColour(const.RED_COLOR_RGB)

    def OnResetTrackerFiducials(self):
        for m in range(3):
            for n in range(3):
                value = self.tracker.GetTrackerFiducialForUI(m, n)
                self.numctrls_fiducial[m + 3][n].SetValue(value)

    def OnBack(self, evt):
        Publisher.sendMessage("Move to tracker page")

    def OnNext(self, evt):
        Publisher.sendMessage("Move to stimulator page")

    def OnRefine(self, evt):
        self.icp.RegisterICP(self.navigation, self.tracker)
        if self.icp.use_icp:
            self.OnUpdateUI()


class StimulatorPage(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)
        self.navigation = nav_hub.navigation

        border = wx.FlexGridSizer(2, 3, 5)
        object_reg = self.navigation.GetObjectRegistration()
        self.object_reg = object_reg

        lbl = wx.StaticText(self, -1, _("No TMS coil configured!"))
        lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.lbl = lbl

        config_txt = wx.StaticText(self, -1, "")
        self.config_txt = config_txt
        self.config_txt.Hide()

        lbl_edit = wx.StaticText(self, -1, _("Edit Configuration:"))
        btn_edit = wx.Button(self, -1, _("Preferences"))
        btn_edit.SetToolTip("Open preferences menu")
        btn_edit.Bind(wx.EVT_BUTTON, self.OnEditPreferences)

        border.AddMany(
            [
                (lbl, 1, wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10),
                (0, 0),
                (config_txt, 1, wx.EXPAND | wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10),
                (0, 0),
                (lbl_edit, 1, wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10),
                (btn_edit, 0, wx.EXPAND | wx.ALL | wx.ALIGN_LEFT, 10),
            ]
        )

        next_button = wx.Button(self, label="Proceed to navigation")
        next_button.Bind(wx.EVT_BUTTON, partial(self.OnNext))
        if self.object_reg is None:
            next_button.Disable()
        self.next_button = next_button

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(next_button)

        if self.object_reg is not None:
            self.OnObjectUpdate()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [
                (border, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10),
                (bottom_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.TOP, 20),
            ]
        )

        self.SetSizerAndFit(main_sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnObjectUpdate, "Update object registration")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnCloseProject, "Remove object data")

    def OnCloseProject(self):
        Publisher.sendMessage("Press track object button", pressed=False)
        Publisher.sendMessage("Enable track object button", enabled=False)

    def UpdateObjectRegistration(self):
        self.object_reg = self.navigation.GetObjectRegistration()

    def OnObjectUpdate(self, data=None):
        self.lbl.SetLabel("Current Configuration:")
        self.UpdateObjectRegistration()
        if self.object_reg is not None:
            self.config_txt.SetLabelText(os.path.basename(self.object_reg[-1]))
        else:
            self.config_txt.SetLabelText("None")
        self.lbl.Show()
        self.config_txt.Show()
        self.next_button.Enable()

    def OnEditPreferences(self, evt):
        Publisher.sendMessage("Open preferences menu", page=3)

    def OnNext(self, evt):
        Publisher.sendMessage("Open navigation menu")


class NavigationPanel(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)

        self.nav_hub = nav_hub
        self.navigation = nav_hub.navigation
        self.tracker = nav_hub.tracker
        self.icp = nav_hub.icp
        self.image = nav_hub.image
        self.pedal_connector = nav_hub.pedal_connector
        self.neuronavigation_api = nav_hub.neuronavigation_api
        self.mep_visualizer = nav_hub.mep_visualizer

        self.__bind_events()

        self.control_panel = ControlPanel(self, nav_hub)
        self.marker_panel = MarkersPanel(self, nav_hub)

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.Add(self.marker_panel, 1, wx.GROW | wx.EXPAND)

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(self.control_panel, 0, wx.EXPAND | wx.TOP, 5)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [(top_sizer, 1, wx.EXPAND | wx.GROW), (bottom_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)]
        )
        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.OnCloseProject, "Close project data")

    def OnCloseProject(self):
        self.tracker.ResetTrackerFiducials()
        self.image.ResetImageFiducials()

        Publisher.sendMessage("Disconnect tracker")
        Publisher.sendMessage("Delete all markers")
        Publisher.sendMessage("Update marker offset state", create=False)
        Publisher.sendMessage("Remove tracts")
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_CROSS)
        # TODO: Reset camera initial focus
        Publisher.sendMessage("Reset cam clipping range")
        self.navigation.StopNavigation()
        self.navigation.__init__(
            pedal_connector=self.pedal_connector, neuronavigation_api=self.neuronavigation_api
        )
        self.tracker.__init__()
        self.icp.__init__()


class ControlPanel(wx.Panel):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)

        self.navigation = nav_hub.navigation
        self.tracker = nav_hub.tracker
        self.robot = nav_hub.robot
        self.icp = nav_hub.icp
        self.image = nav_hub.image
        self.mep_visualizer = nav_hub.mep_visualizer

        self.nav_status = False
        self.target_mode = False
        self.track_obj = False

        self.navigation_status = False

        self.target_selected = False

        # Toggle button for neuronavigation
        tooltip = _("Start navigation")
        btn_nav = wx.ToggleButton(self, -1, _("Start neuronavigation"), size=wx.Size(80, -1))
        btn_nav.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        btn_nav.SetToolTip(tooltip)
        self.btn_nav = btn_nav
        self.btn_nav.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnStartNavigationButton, btn_nav=self.btn_nav)
        )

        # Constants for bitmap parent toggle button
        ICON_SIZE = (48, 48)
        RED_COLOR = const.RED_COLOR_RGB
        self.RED_COLOR = RED_COLOR
        GREEN_COLOR = const.GREEN_COLOR_RGB
        self.GREEN_COLOR = GREEN_COLOR
        GREY_COLOR = (217, 217, 217)
        self.GREY_COLOR = GREY_COLOR

        # Toggle Button for Tractography
        tooltip = _("Control Tractography")
        BMP_TRACT = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("tract.png")), wx.BITMAP_TYPE_PNG)
        tractography_checkbox = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        tractography_checkbox.SetBackgroundColour(GREY_COLOR)
        tractography_checkbox.SetBitmap(BMP_TRACT)
        tractography_checkbox.SetValue(False)
        tractography_checkbox.Enable(False)
        tractography_checkbox.SetToolTip(tooltip)
        tractography_checkbox.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnTractographyCheckbox, ctrl=tractography_checkbox)
        )
        self.tractography_checkbox = tractography_checkbox

        # Toggle button to track the coil
        tooltip = _("Track coil")
        BMP_TRACK = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("coil.png")), wx.BITMAP_TYPE_PNG)
        track_object_button = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        track_object_button.SetBackgroundColour(GREY_COLOR)
        track_object_button.SetBitmap(BMP_TRACK)
        track_object_button.SetValue(False)
        if not self.track_obj:
            track_object_button.Enable(False)
        track_object_button.SetToolTip(tooltip)
        track_object_button.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnTrackObjectButton, ctrl=track_object_button)
        )
        self.track_object_button = track_object_button

        # Toggle button for allowing triggering only if coil is at target
        tooltip = _("Allow triggering only if the coil is at the target")
        BMP_LOCK = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("lock_to_target.png")), wx.BITMAP_TYPE_PNG
        )
        lock_to_target_button = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        lock_to_target_button.SetBackgroundColour(GREY_COLOR)
        lock_to_target_button.SetBitmap(BMP_LOCK)
        lock_to_target_button.SetValue(False)
        lock_to_target_button.Enable(False)
        lock_to_target_button.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnLockToTargetButton, ctrl=lock_to_target_button)
        )
        lock_to_target_button.SetToolTip(tooltip)
        self.lock_to_target_button = lock_to_target_button

        # Toggle button for showing coil during navigation
        tooltip = _("Show coil")
        BMP_SHOW_COIL = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("coil_eye.png")), wx.BITMAP_TYPE_PNG
        )
        show_coil_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        show_coil_button.SetBackgroundColour(GREY_COLOR)
        show_coil_button.SetBitmap(BMP_SHOW_COIL)
        show_coil_button.SetToolTip(tooltip)
        show_coil_button.SetValue(False)
        show_coil_button.Enable(False)
        show_coil_button.Bind(wx.EVT_TOGGLEBUTTON, self.OnShowCoil)
        self.show_coil_button = show_coil_button

        # Toggle Button to use serial port to trigger pulse signal and create markers
        tooltip = _("Enable serial port communication to trigger pulse and create markers")
        BMP_PORT = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("wave.png")), wx.BITMAP_TYPE_PNG)
        checkbox_serial_port = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        checkbox_serial_port.SetBackgroundColour(RED_COLOR)
        checkbox_serial_port.SetBitmap(BMP_PORT)
        checkbox_serial_port.SetToolTip(tooltip)
        checkbox_serial_port.SetValue(False)
        checkbox_serial_port.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnEnableSerialPort, ctrl=checkbox_serial_port)
        )
        self.checkbox_serial_port = checkbox_serial_port

        # Toggle Button for Efield
        tooltip = _("Control E-Field")
        BMP_FIELD = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("field.png")), wx.BITMAP_TYPE_PNG)
        efield_checkbox = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        efield_checkbox.SetBackgroundColour(GREY_COLOR)
        efield_checkbox.SetBitmap(BMP_FIELD)
        efield_checkbox.SetValue(False)
        efield_checkbox.Enable(False)
        efield_checkbox.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnEfieldCheckbox, ctrl=efield_checkbox)
        )
        efield_checkbox.SetToolTip(tooltip)
        self.efield_checkbox = efield_checkbox

        # Toggle Button for Target Mode
        tooltip = _("Target mode")
        BMP_TARGET = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("target.png")), wx.BITMAP_TYPE_PNG)
        target_mode_button = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        target_mode_button.SetBackgroundColour(GREY_COLOR)
        target_mode_button.SetBitmap(BMP_TARGET)
        target_mode_button.SetValue(False)
        target_mode_button.Enable(False)
        target_mode_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnTargetButton))
        target_mode_button.SetToolTip(tooltip)
        self.target_mode_button = target_mode_button
        self.UpdateTargetButton()

        # Toggle button for tracking target with robot during navigation
        tooltip = _("Track target with robot")
        BMP_TRACK_TARGET = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("robot_track_target.png")), wx.BITMAP_TYPE_PNG
        )
        robot_track_target_button = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        robot_track_target_button.SetBackgroundColour(GREY_COLOR)
        robot_track_target_button.SetBitmap(BMP_TRACK_TARGET)
        robot_track_target_button.SetToolTip(tooltip)
        robot_track_target_button.SetValue(False)
        robot_track_target_button.Enable(False)
        robot_track_target_button.Bind(
            wx.EVT_TOGGLEBUTTON,
            partial(self.OnRobotTrackTargetButton, ctrl=robot_track_target_button),
        )
        self.robot_track_target_button = robot_track_target_button

        # Toggle button for moving robot away from head
        tooltip = _("Move robot away from head")
        BMP_ENABLE_MOVE_AWAY = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("robot_move_away.png")), wx.BITMAP_TYPE_PNG
        )
        robot_move_away_button = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        robot_move_away_button.SetBackgroundColour(GREY_COLOR)
        robot_move_away_button.SetBitmap(BMP_ENABLE_MOVE_AWAY)
        robot_move_away_button.SetToolTip(tooltip)
        robot_move_away_button.SetValue(False)
        robot_move_away_button.Enable(False)

        robot_move_away_button.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnRobotMoveAwayButton, ctrl=robot_move_away_button)
        )
        self.robot_move_away_button = robot_move_away_button

        # Toggle button for displaying TMS motor mapping on brain
        tooltip = _("Show TMS motor mapping on brain")
        BMP_MOTOR_MAP = wx.Bitmap(
            str(inv_paths.ICON_DIR.joinpath("brain_eye.png")), wx.BITMAP_TYPE_PNG
        )
        show_motor_map_button = wx.ToggleButton(
            self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE
        )
        show_motor_map_button.SetBackgroundColour(GREY_COLOR)
        show_motor_map_button.SetBitmap(BMP_MOTOR_MAP)
        show_motor_map_button.SetToolTip(tooltip)
        show_motor_map_button.SetValue(False)
        show_motor_map_button.Enable(True)

        show_motor_map_button.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnShowMotorMapButton, ctrl=show_motor_map_button)
        )
        self.show_motor_map_button = show_motor_map_button

        # Sizers
        start_navigation_button_sizer = wx.BoxSizer(wx.VERTICAL)
        start_navigation_button_sizer.AddMany(
            [
                (btn_nav, 0, wx.EXPAND | wx.GROW),
            ]
        )

        navigation_buttons_sizer = wx.FlexGridSizer(4, 5, 5)
        navigation_buttons_sizer.AddMany(
            [
                (tractography_checkbox),
                (target_mode_button),
                (track_object_button),
                (checkbox_serial_port),
                (efield_checkbox),
                (lock_to_target_button),
                (show_coil_button),
                (show_motor_map_button),
            ]
        )

        robot_buttons_sizer = wx.FlexGridSizer(2, 5, 5)
        robot_buttons_sizer.AddMany(
            [
                (robot_track_target_button),
                (robot_move_away_button),
            ]
        )

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany(
            [
                (start_navigation_button_sizer, 0, wx.EXPAND | wx.ALL, 10),
                (navigation_buttons_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM, 10),
                (robot_buttons_sizer, 0, wx.ALIGN_LEFT | wx.TOP | wx.BOTTOM, 5),
            ]
        )

        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)

        self.__bind_events()
        self.Update()
        self.LoadConfig()

    def __bind_events(self):
        Publisher.subscribe(self.OnStartNavigation, "Start navigation")
        Publisher.subscribe(self.OnStopNavigation, "Stop navigation")
        Publisher.subscribe(self.OnCheckStatus, "Navigation status")
        Publisher.subscribe(self.SetTarget, "Set target")
        Publisher.subscribe(self.UnsetTarget, "Unset target")
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")

        Publisher.subscribe(self.OnRobotStatus, "Robot to Neuronavigation: Robot connection status")
        Publisher.subscribe(self.SetTargetMode, "Set target mode")

        Publisher.subscribe(self.UpdateTractsVisualization, "Update tracts visualization")

        # Externally press/unpress and enable/disable buttons.
        Publisher.subscribe(self.PressShowCoilButton, "Press show-coil button")
        Publisher.subscribe(self.EnableShowCoilButton, "Enable show-coil button")

        Publisher.subscribe(self.PressTrackObjectButton, "Press track object button")
        Publisher.subscribe(self.EnableTrackObjectButton, "Enable track object button")

        Publisher.subscribe(self.PressRobotTrackTargetButton, "Press robot button")
        Publisher.subscribe(self.EnableRobotTrackTargetButton, "Enable robot button")

        Publisher.subscribe(self.PressRobotMoveAwayButton, "Press move away button")
        Publisher.subscribe(self.EnableRobotMoveAwayButton, "Enable move away button")

        Publisher.subscribe(self.ShowTargetButton, "Show target button")
        Publisher.subscribe(self.HideTargetButton, "Hide target button")
        Publisher.subscribe(self.PressTargetModeButton, "Press target mode button")

        Publisher.subscribe(self.PressMotorMapButton, "Press motor map button")
        Publisher.subscribe(self.EnableMotorMapButton, "Enable motor map button")

        # Conditions for enabling 'target mode' button:
        Publisher.subscribe(self.TrackObject, "Track object")

        # Tractography
        Publisher.subscribe(self.UpdateTrekkerObject, "Update Trekker object")
        Publisher.subscribe(self.UpdateNumTracts, "Update number of tracts")
        Publisher.subscribe(self.UpdateSeedOffset, "Update seed offset")
        Publisher.subscribe(self.UpdateSeedRadius, "Update seed radius")
        Publisher.subscribe(self.UpdateNumberThreads, "Update number of threads")
        Publisher.subscribe(self.UpdateTractsVisualization, "Update tracts visualization")
        Publisher.subscribe(self.UpdatePeelVisualization, "Update peel visualization")
        Publisher.subscribe(self.UpdateEfieldVisualization, "Update e-field visualization")
        Publisher.subscribe(self.EnableACT, "Enable ACT")
        Publisher.subscribe(self.UpdateACTData, "Update ACT data")

    # Config
    def SaveConfig(self):
        track_object = self.track_object_button
        state = {
            "track_object": {
                "checked": track_object.GetValue(),
                "enabled": track_object.IsEnabled(),
            }
        }

        session = ses.Session()
        session.SetConfig("object_registration_panel", state)

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig("object_registration_panel")

        if state is None:
            return

        track_object = state["track_object"]

        self.EnableTrackObjectButton(track_object["enabled"])
        self.PressTrackObjectButton(track_object["checked"])

    # Toggle Button Helpers
    def UpdateToggleButton(self, ctrl, state=None):
        # Changes background colour based on current state of toggle button if state is not set,
        # otherwise, uses state to set value.
        if state is None:
            state = ctrl.GetValue()

        ctrl.SetValue(state)

        if state:
            ctrl.SetBackgroundColour(self.GREEN_COLOR)
        else:
            ctrl.SetBackgroundColour(self.RED_COLOR)

    def EnableToggleButton(self, ctrl, state):
        # Check if the button state is not changed, if so, return early. This is to prevent
        # unnecessary updates to the button.
        if ctrl.IsEnabled() == state:
            return

        ctrl.Enable(state)
        ctrl.SetBackgroundColour(self.GREY_COLOR)

    # Navigation
    def OnStartNavigation(self):
        if not self.tracker.AreTrackerFiducialsSet() or not self.image.AreImageFiducialsSet():
            wx.MessageBox(_("Invalid fiducials, select all coordinates."), _("InVesalius 3"))

        elif not self.tracker.IsTrackerInitialized():
            dlg.ShowNavigationTrackerWarning(0, "choose")
            errors = True

        else:
            # Prepare GUI for navigation.
            Publisher.sendMessage("Enable style", style=const.STATE_NAVIGATION)
            Publisher.sendMessage("Hide current mask")

            self.navigation.EstimateTrackerToInVTransformationMatrix(self.tracker, self.image)
            self.navigation.StartNavigation(self.tracker, self.icp)

            # Ensure that the target is sent to robot when navigation starts.
            self.robot.SendTargetToRobot()

    def OnStartNavigationButton(self, evt, btn_nav):
        nav_id = btn_nav.GetValue()
        if not nav_id:
            wx.CallAfter(Publisher.sendMessage, "Stop navigation")
            tooltip = _("Start neuronavigation")
            btn_nav.SetToolTip(tooltip)
            btn_nav.SetLabelText(_("Start neuronavigation"))
        else:
            Publisher.sendMessage("Start navigation")
            if self.nav_status:
                tooltip = _("Stop neuronavigation")
                btn_nav.SetToolTip(tooltip)
                btn_nav.SetLabelText(_("Stop neuronavigation"))
            else:
                btn_nav.SetValue(False)

    def OnStopNavigation(self):
        Publisher.sendMessage("Disable style", style=const.STATE_NAVIGATION)

        # Set robot objective to NONE when stopping navigation.
        self.robot.SetObjective(RobotObjective.NONE)

        self.navigation.StopNavigation()

    def UnsetTarget(self, marker):
        self.navigation.target = None
        self.target_selected = False
        self.UpdateTargetButton()

    def SetTarget(self, marker):
        coord = marker.position + marker.orientation

        # TODO: The coordinate systems of slice viewers and volume viewer should be unified, so that this coordinate
        #   flip wouldn't be needed.
        coord[1] = -coord[1]

        self.navigation.target = coord

        self.EnableToggleButton(self.lock_to_target_button, 1)
        self.UpdateToggleButton(self.lock_to_target_button, True)
        self.navigation.SetLockToTarget(True)

        self.target_selected = True
        self.UpdateTargetButton()
        self.UpdateRobotButtons()

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if not nav_status:
            self.nav_status = False
            self.current_orientation = None, None, None
        else:
            self.nav_status = True

        # Update robot button when navigation status is changed.
        self.UpdateRobotButtons()

    def OnCheckStatus(self, nav_status, vis_status):
        if nav_status:
            self.UpdateToggleButton(self.checkbox_serial_port)
            self.EnableToggleButton(self.checkbox_serial_port, 0)
        else:
            self.EnableToggleButton(self.checkbox_serial_port, 1)
            self.UpdateToggleButton(self.checkbox_serial_port)

        # Enable/Disable track-object checkbox if navigation is off/on and object registration is valid.
        obj_registration = self.navigation.GetObjectRegistration()
        enable_track_object = (
            obj_registration is not None and obj_registration[0] is not None and not nav_status
        )
        self.EnableTrackObjectButton(enable_track_object)

    # Robot
    def OnRobotStatus(self, data):
        if data:
            self.Layout()

    def UpdateRobotButtons(self):
        # Enable 'track target' robot button if:
        #
        #   - Navigation is on
        #   - Target is set
        #   - Target mode is on
        #   - Robot is connected
        track_target_button_enabled = (
            self.nav_status
            and self.target_selected
            and self.target_mode
            and self.robot.IsConnected()
        )
        self.EnableRobotTrackTargetButton(enabled=track_target_button_enabled)

        # Enable 'move away' robot button if robot is connected.
        move_away_button_enabled = self.robot.IsConnected()
        self.EnableRobotMoveAwayButton(enabled=move_away_button_enabled)

    def SetTargetMode(self, enabled=False):
        self.target_mode = enabled

        # Update robot button state when target mode is changed.
        self.UpdateRobotButtons()

        # Set robot objective to NONE when target mode is off.
        if not enabled:
            self.robot.SetObjective(RobotObjective.NONE)

    # Tractography
    def OnTractographyCheckbox(self, evt, ctrl):
        self.view_tracts = ctrl.GetValue()
        self.UpdateToggleButton(ctrl)
        Publisher.sendMessage("Update tracts visualization", data=self.view_tracts)
        if not self.view_tracts:
            Publisher.sendMessage("Remove tracts")
            Publisher.sendMessage("Update marker offset state", create=False)

    def UpdateTractsVisualization(self, data):
        self.navigation.view_tracts = data
        self.EnableToggleButton(self.tractography_checkbox, 1)
        self.UpdateToggleButton(self.tractography_checkbox, data)

    def UpdatePeelVisualization(self, data):
        self.navigation.peel_loaded = data

    def UpdateEfieldVisualization(self, data):
        self.navigation.e_field_loaded = data

    def UpdateTrekkerObject(self, data):
        # self.trk_inp = data
        self.navigation.trekker = data

    def UpdateNumTracts(self, data):
        self.navigation.n_tracts = data

    def UpdateSeedOffset(self, data):
        self.navigation.seed_offset = data

    def UpdateSeedRadius(self, data):
        self.navigation.seed_radius = data

    def UpdateNumberThreads(self, data):
        self.navigation.n_threads = data

    def UpdateACTData(self, data):
        self.navigation.act_data = data

    def EnableACT(self, data):
        self.navigation.enable_act = data

    # 'Track object' button
    def EnableTrackObjectButton(self, enabled):
        self.EnableToggleButton(self.track_object_button, enabled)
        self.UpdateToggleButton(self.track_object_button)
        self.SaveConfig()

    def PressTrackObjectButton(self, pressed):
        self.UpdateToggleButton(self.track_object_button, pressed)
        self.OnTrackObjectButton()
        self.SaveConfig()

    def OnTrackObjectButton(self, evt=None, ctrl=None):
        if ctrl is not None:
            self.UpdateToggleButton(ctrl)
        pressed = self.track_object_button.GetValue()
        Publisher.sendMessage("Track object", enabled=pressed)
        if not pressed:
            Publisher.sendMessage("Press target mode button", pressed=pressed)

        # Disable or enable 'Show coil' button, based on if 'Track object' button is pressed.
        Publisher.sendMessage("Enable show-coil button", enabled=pressed)

        # Also, automatically press or unpress 'Show coil' button.
        Publisher.sendMessage("Press show-coil button", pressed=pressed)

        self.SaveConfig()

    # 'Lock to Target' button
    def OnLockToTargetButton(self, evt, ctrl):
        self.UpdateToggleButton(ctrl)
        value = ctrl.GetValue()
        self.navigation.SetLockToTarget(value)

    # 'Show coil' button
    def PressShowCoilButton(self, pressed=False):
        self.UpdateToggleButton(self.show_coil_button, pressed)
        self.OnShowCoil()

    def EnableShowCoilButton(self, enabled=False):
        self.EnableToggleButton(self.show_coil_button, enabled)
        self.UpdateToggleButton(self.show_coil_button)

    def OnShowCoil(self, evt=None):
        self.UpdateToggleButton(self.show_coil_button)
        pressed = self.show_coil_button.GetValue()
        Publisher.sendMessage("Show coil in viewer volume", state=pressed)

    # 'Serial Port Com'
    def OnEnableSerialPort(self, evt, ctrl):
        self.UpdateToggleButton(ctrl)
        if ctrl.GetValue():
            from wx import ID_OK

            dlg_port = dlg.SetCOMPort(select_baud_rate=False)

            if dlg_port.ShowModal() != ID_OK:
                self.UpdateToggleButton(ctrl, False)
                return

            com_port = dlg_port.GetCOMPort()
            baud_rate = 115200

            Publisher.sendMessage(
                "Update serial port",
                serial_port_in_use=True,
                com_port=com_port,
                baud_rate=baud_rate,
            )
        else:
            Publisher.sendMessage("Update serial port", serial_port_in_use=False)

    # 'E Field'
    def OnEfieldCheckbox(self, evt, ctrl):
        self.UpdateToggleButton(ctrl)

    # 'Target mode' button
    def TrackObject(self, enabled):
        self.track_obj = enabled
        self.UpdateTargetButton()

    def ShowTargetButton(self):
        self.target_mode_button.Show()

    def HideTargetButton(self):
        self.target_mode_button.Hide()

    def UpdateTargetButton(self):
        # Enable or disable 'Target mode' button based on if target is selected and if 'Track object' button is pressed.
        enabled = self.target_selected and self.track_obj
        self.EnableToggleButton(self.target_mode_button, enabled)

    def PressTargetModeButton(self, pressed):
        # If pressed, ensure that the button is also enabled.
        if pressed:
            self.EnableToggleButton(self.target_mode_button, True)

        self.UpdateToggleButton(self.target_mode_button, pressed)
        self.OnTargetButton()

    def OnTargetButton(self, evt=None):
        pressed = self.target_mode_button.GetValue()
        self.UpdateToggleButton(self.target_mode_button, pressed)

        Publisher.sendMessage("Set target mode", enabled=pressed)
        if pressed:
            # Set robot objective to NONE when target mode is enabled.
            self.robot.SetObjective(RobotObjective.NONE)

    # Robot-related buttons

    # 'Track target with robot' button
    def EnableRobotTrackTargetButton(self, enabled=False):
        self.EnableToggleButton(self.robot_track_target_button, enabled)
        self.UpdateToggleButton(self.robot_track_target_button)

    def PressRobotTrackTargetButton(self, pressed):
        self.UpdateToggleButton(self.robot_track_target_button, pressed)
        self.OnRobotTrackTargetButton()

    def OnRobotTrackTargetButton(self, evt=None, ctrl=None):
        self.UpdateToggleButton(self.robot_track_target_button)
        pressed = self.robot_track_target_button.GetValue()
        if pressed:
            self.robot.SetObjective(RobotObjective.TRACK_TARGET)
        else:
            # If 'Robot' button is unpressed, set robot objective to NONE, but do not override
            # objective set by another button; hence this check.
            if self.robot.objective == RobotObjective.TRACK_TARGET:
                self.robot.SetObjective(RobotObjective.NONE)

    # 'Move away' button
    def EnableRobotMoveAwayButton(self, enabled=False):
        self.EnableToggleButton(self.robot_move_away_button, enabled)
        self.UpdateToggleButton(self.robot_move_away_button)

    def PressRobotMoveAwayButton(self, pressed):
        self.UpdateToggleButton(self.robot_move_away_button, pressed)
        self.OnRobotMoveAwayButton()

    def OnRobotMoveAwayButton(self, evt=None, ctrl=None):
        self.UpdateToggleButton(self.robot_move_away_button)
        pressed = self.robot_move_away_button.GetValue()
        if pressed:
            self.robot.SetObjective(RobotObjective.MOVE_AWAY_FROM_HEAD)
        else:
            # If 'Move away' button is unpressed, set robot objective to NONE, but do not override
            # objective set by another button; hence this check.
            if self.robot.objective == RobotObjective.MOVE_AWAY_FROM_HEAD:
                self.robot.SetObjective(RobotObjective.NONE)

    # TMS Motor Mapping related
    # 'Motor Map' button
    def PressMotorMapButton(self, pressed=False):
        self.UpdateToggleButton(self.show_motor_map_button, pressed)
        self.OnShowMotorMapButton()

    def EnableMotorMapButton(self, enabled=False):
        self.EnableToggleButton(self.show_motor_map_button, enabled)
        self.UpdateToggleButton(self.show_motor_map_button)

    def OnShowMotorMapButton(self, evt=None, ctrl=None):
        pressed = self.show_motor_map_button.GetValue()
        if self.mep_visualizer.DisplayMotorMap(show=pressed):
            self.UpdateToggleButton(self.show_motor_map_button)


class MarkersPanel(wx.Panel, ColumnSorterMixin):
    def __init__(self, parent, nav_hub):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.navigation = nav_hub.navigation
        self.markers = nav_hub.markers

        if has_mTMS:
            self.mTMS = mTMS()
        else:
            self.mTMS = None

        self.__bind_events()

        self.session = ses.Session()

        self.currently_focused_marker = None
        self.current_position = [0, 0, 0]
        self.current_orientation = [None, None, None]
        self.current_seed = 0, 0, 0
        self.cortex_position_orientation = [None, None, None, None, None, None]
        self.nav_status = False
        self.efield_data_saved = False
        self.efield_target_idx = None

        self.marker_colour = const.MARKER_COLOUR
        self.marker_size = const.MARKER_SIZE
        self.arrow_marker_size = const.ARROW_MARKER_SIZE
        self.current_session = 1

        """ 
        Stores all the marker data that is visible in the GUI, as well as the marker UUID.
        Sorting the marker list in the GUI by column is based on values stored here. 
        """
        self.itemDataMap = {}

        self.brain_actor = None
        # Change session
        spin_session = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_session.SetRange(1, 99)
        spin_session.SetValue(self.current_session)
        spin_session.SetToolTip("Set session")
        spin_session.Bind(wx.EVT_TEXT, partial(self.OnSessionChanged, ctrl=spin_session))
        spin_session.Bind(wx.EVT_SPINCTRL, partial(self.OnSessionChanged, ctrl=spin_session))

        # Marker colour select
        select_colour = csel.ColourSelect(
            self, -1, colour=[255 * s for s in self.marker_colour], size=wx.Size(20, 23)
        )
        select_colour.SetToolTip("Set colour")
        select_colour.Bind(csel.EVT_COLOURSELECT, partial(self.OnSelectColour, ctrl=select_colour))

        btn_create = wx.Button(self, -1, label=_("Create marker"), size=wx.Size(135, 23))
        btn_create.Bind(wx.EVT_BUTTON, self.OnCreateMarker)

        sizer_create = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        sizer_create.AddMany([(spin_session, 1), (select_colour, 0), (btn_create, 0)])

        # Buttons to save and load markers and to change its visibility as well
        btn_save = wx.Button(self, -1, label=_("Save"), size=wx.Size(65, 23))
        btn_save.Bind(wx.EVT_BUTTON, self.OnSaveMarkers)

        btn_load = wx.Button(self, -1, label=_("Load"), size=wx.Size(65, 23))
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadMarkers)

        btn_show_hide_all = wx.ToggleButton(self, -1, _("Hide all"), size=wx.Size(65, 23))
        btn_show_hide_all.Bind(
            wx.EVT_TOGGLEBUTTON, partial(self.OnShowHideAllMarkers, ctrl=btn_show_hide_all)
        )

        sizer_btns = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        sizer_btns.AddMany(
            [
                (btn_save, 1, wx.RIGHT),
                (btn_load, 0, wx.LEFT | wx.RIGHT),
                (btn_show_hide_all, 0, wx.LEFT),
            ]
        )

        # Buttons to delete markers
        btn_delete_single = wx.Button(self, -1, label=_("Delete"), size=wx.Size(65, 23))
        btn_delete_single.Bind(wx.EVT_BUTTON, self.OnDeleteSelectedMarkers)

        btn_delete_all = wx.Button(self, -1, label=_("Delete all"), size=wx.Size(135, 23))
        btn_delete_all.Bind(wx.EVT_BUTTON, self.OnDeleteAllMarkers)

        sizer_delete = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        sizer_delete.AddMany([(btn_delete_single, 1, wx.RIGHT), (btn_delete_all, 0, wx.LEFT)])

        screen_width, screen_height = wx.DisplaySize()

        # The marker list height is set to 120 pixels (accommodating 4 markers) if the screen height is
        # at most 1080 pixels (a commonly used height in laptops). Otherwise, the height grows linearly with
        # the screen height.
        marker_list_height = max(120, int(screen_height / 4))

        marker_list_ctrl = wx.ListCtrl(
            self, -1, style=wx.LC_REPORT, size=wx.Size(0, marker_list_height)
        )
        marker_list_ctrl.InsertColumn(const.ID_COLUMN, "#")
        marker_list_ctrl.SetColumnWidth(const.ID_COLUMN, 24)

        marker_list_ctrl.InsertColumn(const.SESSION_COLUMN, "Session")
        marker_list_ctrl.SetColumnWidth(const.SESSION_COLUMN, 51)

        marker_list_ctrl.InsertColumn(const.MARKER_TYPE_COLUMN, "Type")
        marker_list_ctrl.SetColumnWidth(const.MARKER_TYPE_COLUMN, 77)

        marker_list_ctrl.InsertColumn(const.LABEL_COLUMN, "Label")
        marker_list_ctrl.SetColumnWidth(const.LABEL_COLUMN, 95)

        marker_list_ctrl.InsertColumn(const.TARGET_COLUMN, "Target")
        marker_list_ctrl.SetColumnWidth(const.TARGET_COLUMN, 45)

        marker_list_ctrl.InsertColumn(const.Z_OFFSET_COLUMN, "Z-offset")
        marker_list_ctrl.SetColumnWidth(const.Z_OFFSET_COLUMN, 45)

        marker_list_ctrl.InsertColumn(const.POINT_OF_INTEREST_TARGET_COLUMN, "Efield Target")
        marker_list_ctrl.SetColumnWidth(const.POINT_OF_INTEREST_TARGET_COLUMN, 45)

        marker_list_ctrl.InsertColumn(const.MEP_COLUMN, "MEP (uV)")
        marker_list_ctrl.SetColumnWidth(const.MEP_COLUMN, 45)

        if self.session.GetConfig("debug"):
            marker_list_ctrl.InsertColumn(const.X_COLUMN, "X")
            marker_list_ctrl.SetColumnWidth(const.X_COLUMN, 45)

            marker_list_ctrl.InsertColumn(const.Y_COLUMN, "Y")
            marker_list_ctrl.SetColumnWidth(const.Y_COLUMN, 45)

            marker_list_ctrl.InsertColumn(const.Z_COLUMN, "Z")
            marker_list_ctrl.SetColumnWidth(const.Z_COLUMN, 45)

        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnMouseRightDown)
        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnMarkerFocused)
        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnMarkerUnfocused)
        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.SetCameraToFocusOnMarker)

        self.marker_list_ctrl = marker_list_ctrl
        self.column_sorter = ColumnSorterMixin.__init__(
            self, self.marker_list_ctrl.GetColumnCount()
        )

        # In the future, it would be better if the panel could initialize itself based on markers in MarkersControl
        self.markers.LoadState()

        # Add all lines into main sizer
        group_sizer = wx.BoxSizer(wx.VERTICAL)
        group_sizer.Add(sizer_create, 0, wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(sizer_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(sizer_delete, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(marker_list_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        group_sizer.Fit(self)

        self.SetSizer(group_sizer)
        self.Update()

    # Required function for sorting the marker list
    def GetListCtrl(self):
        return self.marker_list_ctrl

    # Show ascending or descending indicator in the column after sorting
    def OnSortOrderChanged(self):
        column, ascending = self.GetSortState()
        self.marker_list_ctrl.ShowSortIndicator(column, ascending)

    def __bind_events(self):
        Publisher.subscribe(self.UpdateCurrentCoord, "Set cross focal point")

        # Called when selecting a marker in the volume viewer.
        Publisher.subscribe(self.OnSelectMarkerByActor, "Select marker by actor")

        Publisher.subscribe(self.OnDeleteFiducialMarker, "Delete fiducial marker")
        Publisher.subscribe(self.OnDeleteSelectedMarkers, "Delete selected markers")
        Publisher.subscribe(self.OnDeleteAllMarkers, "Delete all markers")
        Publisher.subscribe(self.OnCreateMarker, "Create marker")
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")
        Publisher.subscribe(self.UpdateSeedCoordinates, "Update tracts")
        Publisher.subscribe(self.OnChangeCurrentSession, "Current session changed")
        Publisher.subscribe(self.UpdateMarker, "Update marker")
        Publisher.subscribe(self.UpdateMarkerOrientation, "Open marker orientation dialog")
        Publisher.subscribe(self.AddPeeledSurface, "Update peel")
        Publisher.subscribe(self.GetEfieldDataStatus, "Get status of Efield saved data")
        Publisher.subscribe(self.GetIdList, "Get ID list")
        Publisher.subscribe(self.GetRotationPosition, "Send coil position and rotation")
        Publisher.subscribe(self.CreateMarkerEfield, "Create Marker from tangential")
        Publisher.subscribe(self.UpdateCortexMarker, "Update Cortex Marker")

        # Update marker_list_ctrl
        Publisher.subscribe(self._AddMarker, "Add marker")
        Publisher.subscribe(self._DeleteMarker, "Delete marker")
        Publisher.subscribe(self._DeleteMultiple, "Delete markers")
        Publisher.subscribe(self._SetPointOfInterest, "Set point of interest")
        Publisher.subscribe(self._SetTarget, "Set target")
        Publisher.subscribe(self._UnsetTarget, "Unset target")
        Publisher.subscribe(self._UnsetPointOfInterest, "Unset point of interest")
        Publisher.subscribe(self._UpdateMarkerLabel, "Update marker label")
        Publisher.subscribe(self._UpdateMEP, "Update marker mep")

    def __get_selected_items(self):
        """
        Returns a (possibly empty) list of the selected items in the list control.
        """
        selection = []

        next = self.marker_list_ctrl.GetFirstSelected()

        while next != -1:
            selection.append(next)
            next = self.marker_list_ctrl.GetNextSelected(next)

        return selection

    def __delete_multiple_markers(self, indexes):
        marker_ids = [self.__get_marker_id(idx) for idx in indexes]
        self.markers.DeleteMultiple(marker_ids)

    def _DeleteMarker(self, marker):
        deleted_marker_id = marker.marker_id
        deleted_marker_uuid = marker.marker_uuid
        idx = self.__find_marker_index(deleted_marker_id)
        self.marker_list_ctrl.DeleteItem(idx)
        print("_DeleteMarker:", deleted_marker_uuid)

        # Delete the marker from itemDataMap
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == deleted_marker_uuid:
                self.itemDataMap.pop(key)

        num_items = self.marker_list_ctrl.GetItemCount()
        for n in range(num_items):
            m_id = self.__get_marker_id(n)
            if m_id > deleted_marker_id:
                self.marker_list_ctrl.SetItem(n, const.ID_COLUMN, str(m_id - 1))

    def _DeleteMultiple(self, markers):
        if len(markers) == self.marker_list_ctrl.GetItemCount():
            self.marker_list_ctrl.DeleteAllItems()
            self.itemDataMap.clear()
            return

        min_for_fast_deletion = 10
        if len(markers) > min_for_fast_deletion:
            self.marker_list_ctrl.Hide()

        deleted_ids = []
        deleted_keys = []
        for marker in markers:
            idx = self.__find_marker_index(marker.marker_id)
            deleted_uuid = marker.marker_uuid
            for key, data in self.itemDataMap.items():
                current_uuid = data[-1]

                if current_uuid == deleted_uuid:
                    deleted_keys.append(key)

            self.marker_list_ctrl.DeleteItem(idx)
            deleted_ids.append(marker.marker_id)

        # Remove all the deleted markers from itemDataMap
        for key in deleted_keys:
            try:
                self.itemDataMap.pop(key)
            except KeyError:
                print("Invalid itemDataMap key:", key)

        num_items = self.marker_list_ctrl.GetItemCount()
        for n in range(num_items):
            m_id = self.__get_marker_id(n)
            reduction_in_m_id = 0
            for d_id in deleted_ids:
                if m_id > d_id:
                    reduction_in_m_id += 1
            self.marker_list_ctrl.SetItem(n, const.ID_COLUMN, str(m_id - reduction_in_m_id))

        self.marker_list_ctrl.Show()

    def _SetPointOfInterest(self, marker):
        idx = self.__find_marker_index(marker.marker_id)
        self.marker_list_ctrl.SetItemBackgroundColour(idx, "PURPLE")
        self.marker_list_ctrl.SetItem(idx, const.POINT_OF_INTEREST_TARGET_COLUMN, _("Yes"))
        uuid = marker.marker_uuid

        # Set the point of interest in itemDataMap
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == uuid:
                self.itemDataMap[key][const.POINT_OF_INTEREST_TARGET_COLUMN] = "Yes"

    def _UnsetPointOfInterest(self, marker):
        idx = self.__find_marker_index(marker.marker_id)

        self.marker_list_ctrl.SetItemBackgroundColour(idx, "white")
        self.marker_list_ctrl.SetItem(idx, const.POINT_OF_INTEREST_TARGET_COLUMN, "")
        uuid = marker.marker_uuid

        # Unset the point of interest in itemDataMap
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == uuid:
                self.itemDataMap[key][const.POINT_OF_INTEREST_TARGET_COLUMN] = ""

    def _UpdateMarkerLabel(self, marker):
        idx = self.__find_marker_index(marker.marker_id)
        self.marker_list_ctrl.SetItem(idx, const.LABEL_COLUMN, marker.label)

        # Update the marker label in self.itemDataMap so that sorting works
        uuid = marker.marker_uuid
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == uuid:
                self.itemDataMap[key][const.LABEL_COLUMN] = marker.label

    def _UpdateMEP(self, marker):
        idx = self.__find_marker_index(marker.marker_id)
        self.marker_list_ctrl.SetItem(idx, const.MEP_COLUMN, str(marker.mep_value))

        # Update the marker label in self.itemDataMap so that sorting works
        uuid = marker.marker_uuid
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == uuid:
                self.itemDataMap[key][const.MEP_COLUMN] = marker.mep_value

        # Trigger redraw MEP mapping
        Publisher.sendMessage("Redraw MEP mapping")

    @staticmethod
    def __list_fiducial_labels():
        """Return the list of marker labels denoting fiducials."""
        return list(
            itertools.chain(*(const.BTNS_IMG_MARKERS[i].values() for i in const.BTNS_IMG_MARKERS))
        )

    def UpdateCurrentCoord(self, position):
        self.current_position = list(position[:3])
        self.current_orientation = list(position[3:])
        if not self.navigation.track_obj:
            self.current_orientation = None, None, None

    def UpdateNavigationStatus(self, nav_status, vis_status):
        if not nav_status:
            self.nav_status = False
            self.current_orientation = None, None, None
        else:
            self.nav_status = True

    def UpdateSeedCoordinates(
        self, root=None, affine_vtk=None, coord_offset=(0, 0, 0), coord_offset_w=(0, 0, 0)
    ):
        self.current_seed = coord_offset_w

    def UpdateCortexMarker(self, CoGposition, CoGorientation):
        self.cortex_position_orientation = CoGposition + CoGorientation

    def OnMouseRightDown(self, evt):
        focused_marker_idx = self.marker_list_ctrl.GetFocusedItem()
        focused_marker = self.__get_marker(focused_marker_idx)
        marker_type = focused_marker.marker_type
        unique_menu_id = 1

        # Check if the currently focused marker is the active target.
        is_active_target = focused_marker.is_target

        # Check if the currently focused marker is of the type 'coil target'.
        is_coil_target = marker_type == MarkerType.COIL_TARGET

        # Check if the currently focused marker is of the type 'coil pose'.
        is_coil_pose = marker_type == MarkerType.COIL_POSE

        # Check if the currently focused marker is of the type 'landmark'.
        is_landmark = marker_type == MarkerType.LANDMARK

        # Check if the currently focused marker is of the type 'fiducial'.
        is_fiducial = marker_type == MarkerType.FIDUCIAL

        # Create the context menu.
        menu_id = wx.Menu()

        edit_id = menu_id.Append(unique_menu_id, _("Change label"))  # Use non-zero ID
        menu_id.Bind(wx.EVT_MENU, self.ChangeLabel, edit_id)

        color_id = menu_id.Append(
            unique_menu_id + 1, _("Change color")
        )  # Increment the unique_menu_id
        menu_id.Bind(wx.EVT_MENU, self.ChangeColor, color_id)

        delete_id = menu_id.Append(unique_menu_id + 2, _("Delete"))
        menu_id.Bind(wx.EVT_MENU, self.OnDeleteSelectedMarkers, delete_id)

        # Allow duplicate only for markers that are not fiducials.
        if not is_fiducial:
            duplicate_menu_item = menu_id.Append(unique_menu_id + 3, _("Duplicate"))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuDuplicateMarker, duplicate_menu_item)

        menu_id.AppendSeparator()
        # Show 'Set as target'/'Unset target' menu item only if the marker is a coil target.
        if is_coil_target:
            mep_menu_item = menu_id.Append(unique_menu_id + 4, _("Change MEP value"))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuChangeMEP, mep_menu_item)
            if is_active_target:
                target_menu_item = menu_id.Append(unique_menu_id + 5, _("Unset target"))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuUnsetTarget, target_menu_item)
                if has_mTMS:
                    brain_target_menu_item = menu_id.Append(
                        unique_menu_id + 4, _("Set brain target")
                    )
                    menu_id.Bind(wx.EVT_MENU, self.OnSetBrainTarget, brain_target_menu_item)
            else:
                target_menu_item = menu_id.Append(unique_menu_id + 5, _("Set as target"))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuSetTarget, target_menu_item)

        # Show 'Create coil target' menu item if the marker is a coil pose.
        if is_coil_pose:
            # 'Create coil target' menu item.
            create_coil_target_menu_item = menu_id.Append(
                unique_menu_id + 6, _("Create coil target")
            )
            menu_id.Bind(
                wx.EVT_MENU, self.OnCreateCoilTargetFromCoilPose, create_coil_target_menu_item
            )

        # Show 'Create brain target' and 'Create coil target' menu items only if the marker is a landmark.
        if is_landmark:
            # 'Create brain target' menu item.
            create_brain_target_menu_item = menu_id.Append(
                unique_menu_id + 5, _("Create brain target")
            )
            menu_id.Bind(
                wx.EVT_MENU, self.OnCreateBrainTargetFromLandmark, create_brain_target_menu_item
            )

            # 'Create coil target' menu item.
            create_coil_target_menu_item = menu_id.Append(
                unique_menu_id + 6, _("Create coil target")
            )
            menu_id.Bind(
                wx.EVT_MENU, self.OnCreateCoilTargetFromLandmark, create_coil_target_menu_item
            )

        is_brain_target = focused_marker.marker_type == MarkerType.BRAIN_TARGET
        if is_brain_target and has_mTMS:
            send_brain_target_menu_item = menu_id.Append(
                unique_menu_id + 7, _("Send brain target to mTMS")
            )
            menu_id.Bind(wx.EVT_MENU, self.OnSendBrainTarget, send_brain_target_menu_item)

        if self.nav_status and self.navigation.e_field_loaded:
            # Publisher.sendMessage('Check efield data')
            # if not tuple(np.argwhere(self.indexes_saved_lists == self.marker_list_ctrl.GetFocusedItem())):
            if is_active_target:
                efield_menu_item = menu_id.Append(unique_menu_id + 8, _("Save Efield target Data"))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuSaveEfieldTargetData, efield_menu_item)

        if self.navigation.e_field_loaded:
            efield_target_menu_item = menu_id.Append(
                unique_menu_id + 9, _("Set as Efield target 1 (origin)")
            )
            menu_id.Bind(wx.EVT_MENU, self.OnMenuSetEfieldTarget, efield_target_menu_item)

            efield_target_menu_item = menu_id.Append(
                unique_menu_id + 10, _("Set as Efield target 2")
            )
            menu_id.Bind(wx.EVT_MENU, self.OnMenuSetEfieldTarget2, efield_target_menu_item)
            # Publisher.sendMessage('Check efield data')
            # if self.efield_data_saved:
            #     if tuple(np.argwhere(self.indexes_saved_lists==self.marker_list_ctrl.GetFocusedItem())):
            #         if self.efield_target_idx  == self.marker_list_ctrl.GetFocusedItem():
            #             efield_target_menu_item  = menu_id.Append(unique_menu_id + 9, _('Remove Efield target'))
            #             menu_id.Bind(wx.EVT_MENU, self.OnMenuRemoveEfieldTarget, efield_target_menu_item )
            #         else:
            #             efield_target_menu_item = menu_id.Append(unique_menu_id + 9, _('Set as Efield target(compare)'))
            #             menu_id.Bind(wx.EVT_MENU, self.OnMenuSetEfieldTarget, efield_target_menu)

        if self.navigation.e_field_loaded and not self.nav_status:
            if is_active_target:
                efield_vector_plot_menu_item = menu_id.Append(
                    unique_menu_id + 11, _("Show vector field")
                )
                menu_id.Bind(wx.EVT_MENU, self.OnMenuShowVectorField, efield_vector_plot_menu_item)

        if self.navigation.e_field_loaded:
            if focused_marker.is_point_of_interest:
                create_efield_target = menu_id.Append(
                    unique_menu_id + 12, _("Remove Efield Cortex target")
                )
                menu_id.Bind(
                    wx.EVT_MENU, self.OnMenuRemoveEfieldTargetatCortex, create_efield_target
                )
            else:
                create_efield_target = menu_id.Append(
                    unique_menu_id + 12, _("Set as Efield Cortex target")
                )
                menu_id.Bind(wx.EVT_MENU, self.OnSetEfieldBrainTarget, create_efield_target)
                self.marker_list_ctrl.GetFocusedItem()

        menu_id.AppendSeparator()

        self.PopupMenu(menu_id)
        menu_id.Destroy()

    # Programmatically set the focus on the marker with the given index, simulating left click.
    def FocusOnMarker(self, idx):
        # Deselect the previously focused marker.
        if self.currently_focused_marker is not None:
            current_marker_idx = self.__find_marker_index(self.currently_focused_marker.marker_id)

            # If the marker has been deleted, it might not be found in the list of markers. In that case,
            # do not try to deselect it.
            if current_marker_idx is not None:
                self.marker_list_ctrl.SetItemState(
                    current_marker_idx, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                )

                # Trigger EVT_LIST_ITEM_DESELECTED event manually for the old item.
                event_deselect = wx.ListEvent(
                    wx.EVT_LIST_ITEM_DESELECTED.typeId, self.marker_list_ctrl.GetId()
                )
                event_deselect.SetIndex(current_marker_idx)
                event_deselect.SetEventObject(self.marker_list_ctrl)
                self.marker_list_ctrl.GetEventHandler().ProcessEvent(event_deselect)

        # Select the item.
        self.marker_list_ctrl.SetItemState(idx, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)

        # Focus on the item.
        self.marker_list_ctrl.SetItemState(idx, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
        self.marker_list_ctrl.EnsureVisible(idx)

        # Trigger EVT_LIST_ITEM_SELECTED event manually.
        event = wx.ListEvent(wx.EVT_LIST_ITEM_SELECTED.typeId, self.marker_list_ctrl.GetId())
        event.SetIndex(idx)
        event.SetEventObject(self.marker_list_ctrl)
        self.marker_list_ctrl.GetEventHandler().ProcessEvent(event)

    # Called when a marker on the list gets the focus by the user left-clicking on it.
    def OnMarkerFocused(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()

        # Selection of more than 1 marker not supported by MarkerTransformator
        if idx == -1:
            return

        marker_id = self.__get_marker_id(idx)
        marker = self.markers.list[marker_id]

        # XXX: There seems to be a bug in WxPython when selecting multiple items on the list using,
        #   e.g., shift and page-up/page-down keys. The bug is that the EVT_LIST_ITEM_SELECTED event
        #   is triggered repeatedly for the same item (the one that was first selected). This is a
        #   workaround to prevent the event from being triggered repeatedly for the same item.
        if self.currently_focused_marker is not None and marker == self.currently_focused_marker:
            return

        # When selecting multiple markers, e.g., by pressing ctrl while clicking on the markers, EVT_LIST_ITEM_SELECTED
        # event is triggered for each selected item, without triggering EVT_LIST_ITEM_DESELECTED event for the previously
        # selected item. By unhighlighting the previously focused marker here, we ensure that only one marker is highlighted
        # at a time.
        #
        # TODO: Support multiple highlighted markers at the same time.
        if self.currently_focused_marker is not None:
            # Unhighlight the previously focused marker in the viewer volume.
            Publisher.sendMessage("Unhighlight marker")

        self.currently_focused_marker = marker
        self.markers.SelectMarker(marker_id)

    # Called when a marker on the list loses the focus by the user left-clicking on another marker.
    #
    # Note: This is called also when re-clicking on the same marker that is already focused.
    def OnMarkerUnfocused(self, evt):
        self.markers.DeselectMarker()

    def SetCameraToFocusOnMarker(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.markers.list[idx]
        Publisher.sendMessage("Set camera to focus on marker", marker=marker)

    def OnCreateCoilTargetFromLandmark(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        if list_index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker = self.__get_marker(list_index)

        self.markers.CreateCoilTargetFromLandmark(marker)

    def OnCreateCoilTargetFromCoilPose(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        if list_index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker = self.__get_marker(list_index)

        self.markers.CreateCoilTargetFromCoilPose(marker)

    def ChangeLabel(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        if list_index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker = self.__get_marker(list_index)
        new_label = dlg.ShowEnterMarkerID(
            self.marker_list_ctrl.GetItemText(list_index, const.LABEL_COLUMN)
        )
        self.markers.ChangeLabel(marker, new_label)

    def OnMenuSetTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        marker_id = self.__get_marker_id(idx)
        self.markers.SetTarget(marker_id)

    def _SetTarget(self, marker):
        idx = self.__find_marker_index(marker.marker_id)
        self.marker_list_ctrl.SetItemBackgroundColour(idx, "RED")
        self.marker_list_ctrl.SetItem(idx, const.TARGET_COLUMN, _("Yes"))

        target_uuid = marker.marker_uuid

        # Set the target column to "Yes" in itemDataMap
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == target_uuid:
                self.itemDataMap[key][const.TARGET_COLUMN] = "Yes"

    def OnMenuDuplicateMarker(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        # Create a duplicate of the selected marker.
        new_marker = self.__get_marker(idx).duplicate()

        # Add suffix to marker name.
        new_marker.label = new_marker.label + " (copy)"

        self.markers.AddMarker(new_marker, render=True, focus=True)

    def GetEfieldDataStatus(self, efield_data_loaded, indexes_saved_list):
        self.indexes_saved_lists = []
        self.efield_data_saved = efield_data_loaded
        self.indexes_saved_lists = indexes_saved_list

    def CreateMarkerEfield(self, point, orientation):
        from vtkmodules.vtkCommonColor import vtkNamedColors

        vtk_colors = vtkNamedColors()
        position_flip = list(point)
        position_flip[1] = -position_flip[1]

        marker = self.CreateMarker(
            position=position_flip,
            orientation=list(orientation),
            colour=vtk_colors.GetColor3d("Orange"),
            size=2,
            marker_type=MarkerType.COIL_TARGET,
        )
        self.markers.AddMarker(marker, render=True, focus=True)

    def OnMenuShowVectorField(self, evt):
        session = ses.Session()
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.__get_marker(idx)
        position = marker.position
        orientation = np.radians(marker.orientation)
        Publisher.sendMessage(
            "Calculate position and rotation", position=position, orientation=orientation
        )
        coord = [position, orientation]
        coord = np.array(coord).flatten()

        # Check here, it resets the radious list
        Publisher.sendMessage(
            "Update interseccion offline",
            m_img=self.m_img_offline,
            coord=coord,
            list_index=marker.marker_id,
        )

        if session.GetConfig("debug_efield"):
            enorm = self.navigation.debug_efield_enorm
        else:
            enorm = self.navigation.neuronavigation_api.update_efield_vectorROI(
                position=self.cp, orientation=orientation, T_rot=self.T_rot, id_list=self.ID_list
            )
        enorm_data = [self.T_rot, self.cp, coord, enorm, self.ID_list]
        Publisher.sendMessage("Get enorm", enorm_data=enorm_data, plot_vector=True)

    def GetRotationPosition(self, T_rot, cp, m_img):
        self.T_rot = T_rot
        self.cp = cp
        self.m_img_offline = m_img

    def GetIdList(self, ID_list):
        self.ID_list = ID_list

    def OnMenuSetEfieldTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker_id = self.__get_marker_id(idx)
        self.markers.SetTarget(marker_id)
        self.efield_target_idx_origin = marker_id

        # Publisher.sendMessage('Get target index efield', target_index_list = marker_id )

    def OnMenuSetEfieldTarget2(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        efield_target_idx_2 = self.__get_marker_id(idx)
        target1_origin = self.markers.list[
            self.efield_target_idx_origin
        ].cortex_position_orientation
        target2 = self.markers.list[efield_target_idx_2].cortex_position_orientation
        Publisher.sendMessage(
            "Get targets Ids for mtms", target1_origin=target1_origin, target2=target2
        )

    def OnMenuSaveEfieldTargetData(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        marker = self.__get_marker(list_index)
        position = marker.position
        orientation = marker.orientation
        plot_efield_vectors = self.navigation.plot_efield_vectors
        Publisher.sendMessage(
            "Save target data",
            target_list_index=marker.marker_id,
            position=position,
            orientation=orientation,
            plot_efield_vectors=plot_efield_vectors,
        )

    def OnSetEfieldBrainTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.__get_marker(idx)
        position = marker.position
        orientation = marker.orientation
        marker_id = marker.marker_id
        if all([o is None for o in orientation]):
            orientation = [0, 0, 0]

        self.markers.SetPointOfInterest(marker_id)
        Publisher.sendMessage(
            "Send efield target position on brain",
            marker_id=marker_id,
            position=position,
            orientation=orientation,
        )

    def OnCreateBrainTargetFromLandmark(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        marker = self.__get_marker(list_index)
        position = marker.position
        orientation = marker.orientation

        dialog = dlg.CreateBrainTargetDialog(
            marker=position + orientation, brain_actor=self.brain_actor
        )
        if dialog.ShowModal() == wx.ID_OK:
            (
                coil_position_list,
                coil_orientation_list,
                brain_position_list,
                brain_orientation_list,
            ) = dialog.GetValue()

            position = list(coil_position_list[0])
            orientation = list(coil_orientation_list[0])
            marker = self.CreateMarker(
                position=position,
                orientation=orientation,
                # XXX: Setting the marker type to 'brain target' is inconsistent with the variable names above ('coil_position_list' etc.);
                #   however, the dialog shown to the user by this function should be used exclusively for creating brain targets, hence the
                #   variable naming (and the internal logic of the dialog where it currently returns both coil targets and brain targets)
                #   should probably be modified to reflect that.
                marker_type=MarkerType.BRAIN_TARGET,
            )
            self.markers.AddMarker(marker, render=True, focus=True)

            for position, orientation in zip(brain_position_list, brain_orientation_list):
                marker = self.CreateMarker(
                    position=list(position),
                    orientation=list(orientation),
                    marker_type=MarkerType.BRAIN_TARGET,
                )
                self.markers.AddMarker(marker, render=True, focus=False)

        dialog.Destroy()

    def OnMenuRemoveEfieldTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker_id = self.__get_marker_id(idx)

        self.markers.UnsetTarget(marker_id)

        self.efield_target_idx = None

    def OnMenuRemoveEfieldTargetatCortex(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.__get_marker(idx)

        # TODO: Is this correct? Should it be "brain target"?
        marker.marker_type = MarkerType.LANDMARK

        self.markers.UnsetPointOfInterest(marker.marker_id)
        Publisher.sendMessage("Clear efield target at cortex")

    def OnMenuUnsetTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker_id = self.__get_marker_id(idx)
        self.markers.UnsetTarget(marker_id)

    def OnMenuChangeMEP(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.__get_marker(idx)

        new_mep = dlg.ShowEnterMEPValue(self.marker_list_ctrl.GetItemText(idx, const.MEP_COLUMN))
        self.markers.ChangeMEP(marker, new_mep)

    def _UnsetTarget(self, marker):
        idx = self.__find_marker_index(marker.marker_id)

        # When unsetting a target, automatically unpress the target mode button.
        Publisher.sendMessage("Press target mode button", pressed=False)

        # Update the marker list control.
        self.marker_list_ctrl.SetItemBackgroundColour(idx, "white")
        self.marker_list_ctrl.SetItem(idx, const.TARGET_COLUMN, "")

        # Unset the target in itemDataMap
        target_uuid = marker.marker_uuid
        for key, data in self.itemDataMap.items():
            current_uuid = data[-1]
            if current_uuid == target_uuid:
                self.itemDataMap[key][const.TARGET_COLUMN] = ""

    def __find_marker_index(self, marker_id):
        """
        For a marker_id, returns the corresponding index in self.marker_list_ctrl.
        """
        num_items = self.marker_list_ctrl.GetItemCount()
        for idx in range(num_items):
            item_marker_id = self.__get_marker_id(idx)
            if item_marker_id == marker_id:
                return idx
        return None

    def __get_marker_id(self, idx):
        """
        For an index in self.marker_list_ctrl, returns the corresponding marker_id
        """
        list_item = self.marker_list_ctrl.GetItem(idx, const.ID_COLUMN)
        return int(list_item.GetText())

    def __get_marker(self, idx):
        """
        For an index in self.marker_list_ctrl, returns the corresponding marker
        """
        marker_id = self.__get_marker_id(idx)
        return self.markers.list[marker_id]

    def ChangeColor(self, evt):
        index = self.marker_list_ctrl.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker = self.__get_marker(index)

        current_color = marker.colour8bit
        new_color = dlg.ShowColorDialog(color_current=current_color)

        if not new_color:
            return

        self.markers.ChangeColor(marker, new_color)

    def OnSetBrainTarget(self, evt):
        if isinstance(evt, int):
            self.marker_list_ctrl.Focus(evt)
        index = self.marker_list_ctrl.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker = self.__get_marker(index)

        position = marker.position
        orientation = marker.orientation
        dialog = dlg.CreateBrainTargetDialog(
            mTMS=self.mTMS,
            marker=position + orientation,
            brain_target=True,
            brain_actor=self.brain_actor,
        )

        if dialog.ShowModal() == wx.ID_OK:
            position_list, orientation_list = dialog.GetValueBrainTarget()
            for position, orientation in zip(position_list, orientation_list):
                new_marker = self.CreateMarker(
                    position=list(position),
                    orientation=list(orientation),
                    size=0.05,
                    marker_type=MarkerType.BRAIN_TARGET,
                )
                self.markers.AddMarker(new_marker, render=True, focus=True)

        dialog.Destroy()

    def OnSendBrainTarget(self, evt):
        if isinstance(evt, int):
            self.marker_list_ctrl.Focus(evt)
        index = self.marker_list_ctrl.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        marker = self.__get_marker(index)
        brain_target = marker.position + marker.orientation
        target = self.markers.FindTarget()
        if target is not None:
            coil_pose = target.position + target.orientation
            if self.navigation.coil_at_target:
                self.mTMS.UpdateTarget(coil_pose, brain_target)
                # wx.CallAfter(Publisher.sendMessage, 'Send brain target to mTMS API', coil_pose=coil_pose, brain_target=brain_target)
                print("Send brain target to mTMS API")
            else:
                print("The coil is not at the target")
        else:
            print("Target not set")

    def OnSessionChanged(self, evt, ctrl):
        value = ctrl.GetValue()
        Publisher.sendMessage("Current session changed", new_session_id=value)

    def OnSelectMarkerByActor(self, actor):
        """
        Given an actor, select and focus on the corresponding marker in the list control.

        TODO: This is not in the optimal place. Ideally, information about the 3D view should not
              be passed to the markers panel. However, currently MarkersPanel is the only
              place where the list of markers, including information about their visualization, is
              stored.
        """
        for m, idx in zip(self.markers.list, range(len(self.markers.list))):
            visualization = m.visualization
            if visualization is None:
                continue

            if visualization["actor"] == actor:
                # Unselect the previously selected item.
                idx_old = self.marker_list_ctrl.GetFocusedItem()
                if idx_old != -1 and idx_old != idx:
                    self.marker_list_ctrl.Select(idx_old, on=False)

                # Focus and select the marker in the list control.
                self.marker_list_ctrl.Focus(idx)
                self.marker_list_ctrl.Select(idx, on=True)
                break

    def OnDeleteAllMarkers(self, evt=None):
        if evt is not None:
            result = dlg.ShowConfirmationDialog(msg=_("Delete all markers? Cannot be undone."))
            if result != wx.ID_OK:
                return
        self.markers.Clear()
        self.itemDataMap.clear()

    def OnDeleteFiducialMarker(self, label):
        indexes = []
        if label and (label in self.__list_fiducial_labels()):
            for id_n in range(self.marker_list_ctrl.GetItemCount()):
                item = self.marker_list_ctrl.GetItem(id_n, const.LABEL_COLUMN)
                if item.GetText() == label:
                    self.marker_list_ctrl.Focus(item.GetId())
                    indexes = [self.marker_list_ctrl.GetFocusedItem()]

        self.__delete_multiple_markers(indexes)

    def OnDeleteSelectedMarkers(self, evt=None):
        indexes = self.__get_selected_items()

        if not indexes:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        msg = _("Delete marker?") if len(indexes) == 1 else _("Delete markers?")

        result = dlg.ShowConfirmationDialog(msg=msg)
        if result != wx.ID_OK:
            return

        self.__delete_multiple_markers(indexes)

        # Re-focus on the marker with the same index as the first marker that was selected before deletion.
        if self.currently_focused_marker is not None:
            first_deleted_index = indexes[0]
            first_existing_index = (
                first_deleted_index
                if first_deleted_index < len(self.markers.list)
                else len(self.markers.list) - 1
            )

            self.FocusOnMarker(first_existing_index)

    def GetNextMarkerLabel(self):
        return self.markers.GetNextMarkerLabel()

    def OnCreateMarker(
        self,
        evt=None,
        position=None,
        orientation=None,
        colour=None,
        size=None,
        label=None,
        is_target=False,
        seed=None,
        session_id=None,
        marker_type=None,
        cortex_position_orientation=None,
        mep_value=None,
    ):
        if label is None:
            label = self.GetNextMarkerLabel()

        if self.nav_status and self.navigation.e_field_loaded:
            Publisher.sendMessage("Get Cortex position")

        # XXX: Set marker type to 'coil target' if created during navigation, otherwise 'landmark'. This enables creating
        #   coil targets during navigation. However, this logic shouldn't be inferred from the navigation status. Ideally,
        #   there would be two buttons for creating coil targets and landmarks, and the user would choose which one to create,
        #   or a similar explicit logic.
        #
        #   In addition, if marker_type is explicitly given as an argument (e.g., it is set to MarkerType.COIL or
        #   MarkerType.FIDUCIAL by the caller), do not automatically infer the marker type; only do it, if
        #   marker_type is None.
        if marker_type is None:
            marker_type = (
                MarkerType.COIL_TARGET
                if self.nav_status and self.navigation.track_obj
                else MarkerType.LANDMARK
            )

        marker = self.CreateMarker(
            position=position,
            orientation=orientation,
            colour=colour,
            size=size,
            label=label,
            is_target=is_target,
            seed=seed,
            session_id=session_id,
            marker_type=marker_type,
            cortex_position_orientation=cortex_position_orientation,
            mep_value=mep_value,
        )
        self.markers.AddMarker(marker, render=True, focus=True)

    # Given a string, try to parse it as an integer, float, or string.
    #
    # TODO: This shouldn't be here, but there's currently no good place for the function.
    #   If csv-related functions are moved to a separate module, this function should be moved there.
    def ParseValue(self, value):
        value = value.strip()

        # Check for integer, float, string encapsulated by quotes, and None.
        if value == "None":
            return None
        try:
            if "." in value:
                return float(value)
            return int(value)

        except ValueError:
            # Check for strings marked by quotes.
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            return value

    def GetMarkersFromFile(self, filename, overwrite_image_fiducials):
        try:
            with open(filename, "r") as file:
                magick_line = file.readline()
                assert magick_line.startswith(const.MARKER_FILE_MAGICK_STRING)
                version = int(magick_line.split("_")[-1])
                if version not in const.SUPPORTED_MARKER_FILE_VERSIONS:
                    wx.MessageBox(_("Unknown version of the markers file."), _("InVesalius 3"))
                    return

                # Use the first line after the magick_line as the names for dictionary keys.
                column_names = file.readline().strip().split("\t")
                column_names_parsed = [self.ParseValue(name) for name in column_names]

                markers_data = []
                for line in file:
                    values = line.strip().split("\t")
                    values_parsed = [self.ParseValue(value) for value in values]
                    marker_data = dict(zip(column_names_parsed, values_parsed))

                    markers_data.append(marker_data)

            self.marker_list_ctrl.Hide()

            # Create markers from the dictionary.
            for data in markers_data:
                marker = Marker(version=version)
                marker.from_dict(data)

                # When loading markers from file, we first create a marker with is_target set to False, and then call __set_marker_as_target.
                marker.is_target = False

                # Note that we don't want to render or focus on the markers here for each loop iteration.
                self.markers.AddMarker(marker, render=False)

                if overwrite_image_fiducials and marker.label in self.__list_fiducial_labels():
                    Publisher.sendMessage(
                        "Load image fiducials", label=marker.label, position=marker.position
                    )

        except Exception as e:
            wx.MessageBox(_("Invalid markers file."), _("InVesalius 3"))
            utils.debug(e)

        self.marker_list_ctrl.Show()
        Publisher.sendMessage("Render volume viewer")
        Publisher.sendMessage("Update UI for refine tab")
        self.markers.SaveState()

    def OnLoadMarkers(self, evt):
        """Loads markers from file and appends them to the current marker list.
        The file should contain no more than a single target marker. Also the
        file should not contain any fiducials already in the list."""

        last_directory = ses.Session().GetConfig("last_directory_3d_surface", "")
        dialog = dlg.FileSelectionDialog(
            _("Load markers"), last_directory, const.WILDCARD_MARKER_FILES
        )
        overwrite_checkbox = wx.CheckBox(dialog, -1, _("Overwrite current image fiducials"))
        dialog.sizer.Add(overwrite_checkbox, 0, wx.CENTER)
        dialog.FitSizers()
        if dialog.ShowModal() == wx.ID_OK:
            filename = dialog.GetPath()
            self.GetMarkersFromFile(filename, overwrite_checkbox.GetValue())

    def OnShowHideAllMarkers(self, evt, ctrl):
        if ctrl.GetValue():
            Publisher.sendMessage("Hide markers", markers=self.markers.list)
            ctrl.SetLabel("Show all")
        else:
            Publisher.sendMessage("Show markers", markers=self.markers.list)
            ctrl.SetLabel("Hide all")

    def OnSaveMarkers(self, evt):
        prj_data = prj.Project()
        timestamp = time.localtime(time.time())
        stamp_date = "{:0>4d}{:0>2d}{:0>2d}".format(
            timestamp.tm_year, timestamp.tm_mon, timestamp.tm_mday
        )
        stamp_time = "{:0>2d}{:0>2d}{:0>2d}".format(
            timestamp.tm_hour, timestamp.tm_min, timestamp.tm_sec
        )
        sep = "-"
        parts = [stamp_date, stamp_time, prj_data.name, "markers"]
        default_filename = sep.join(parts) + ".mkss"

        filename = dlg.ShowLoadSaveDialog(
            message=_("Save markers as..."),
            wildcard=const.WILDCARD_MARKER_FILES,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
            default_filename=default_filename,
        )

        if not filename:
            return

        version_line = "%s%i\n" % (
            const.MARKER_FILE_MAGICK_STRING,
            const.CURRENT_MARKER_FILE_VERSION,
        )
        header_line = "%s\n" % Marker.to_csv_header()
        data_lines = [marker.to_csv_row() + "\n" for marker in self.markers.list]
        try:
            with open(filename, "w", newline="") as file:
                file.writelines([version_line, header_line])
                file.writelines(data_lines)
                file.close()
        except Error as e:
            wx.MessageBox(_("Error writing markers file."), _("InVesalius 3"))
            utils.debug(e)

    def OnSelectColour(self, evt, ctrl):
        # TODO: Make sure GetValue returns 3 numbers (without alpha)
        self.marker_colour = [colour / 255.0 for colour in ctrl.GetValue()][:3]

    def OnSelectSize(self, evt, ctrl):
        self.marker_size = ctrl.GetValue()

    def OnChangeCurrentSession(self, new_session_id):
        self.current_session = new_session_id

    def UpdateMarker(self, marker, new_position, new_orientation):
        marker_id = marker.marker_id
        self.markers.list[marker_id].position = new_position
        self.markers.list[marker_id].orientation = new_orientation
        self.UpdateMarkerInList(marker)
        self.markers.SaveState()

    def UpdateMarkerInList(self, marker):
        idx = self.__find_marker_index(marker.marker_id)
        if idx is None:
            return

        z_offset_str = str(marker.z_offset) if marker.z_offset != 0.0 else ""
        self.marker_list_ctrl.SetItem(idx, const.Z_OFFSET_COLUMN, z_offset_str)

    def UpdateMarkerOrientation(self, marker_id=None):
        list_index = marker_id if marker_id else 0
        position = self.markers.list[list_index].position
        orientation = self.markers.list[list_index].orientation
        dialog = dlg.CreateBrainTargetDialog(mTMS=self.mTMS, marker=position + orientation)

        if dialog.ShowModal() == wx.ID_OK:
            orientation = dialog.GetValue()
            Publisher.sendMessage(
                "Update target orientation", target_id=marker_id, orientation=list(orientation)
            )
        dialog.Destroy()

    def AddPeeledSurface(self, flag, actor):
        self.brain_actor = actor

    def CreateMarker(
        self,
        position=None,
        orientation=None,
        colour=None,
        size=None,
        label=None,
        is_target=False,
        seed=None,
        session_id=None,
        marker_type=MarkerType.LANDMARK,
        cortex_position_orientation=None,
        z_offset=0.0,
        z_rotation=0.0,
        mep_value=None,
    ):
        """
        Create a new marker object.
        """
        if label is None:
            label = self.GetNextMarkerLabel()

        marker = Marker()

        marker.position = position or self.current_position
        marker.orientation = orientation or self.current_orientation

        marker.colour = colour or self.marker_colour
        marker.size = size or self.marker_size
        marker.label = label
        marker.is_target = is_target
        marker.seed = seed or self.current_seed
        marker.session_id = session_id or self.current_session
        marker.marker_type = marker_type
        marker.cortex_position_orientation = (
            cortex_position_orientation or self.cortex_position_orientation
        )
        marker.z_offset = z_offset
        marker.z_rotation = z_rotation
        marker.mep_value = mep_value

        # Marker IDs start from zero, hence len(self.markers) will be the ID of the new marker.
        marker.marker_id = len(self.markers.list)

        # Create an uuid for the marker
        marker.marker_uuid = str(uuid.uuid4())

        if marker.marker_type == MarkerType.BRAIN_TARGET:
            marker.colour = [0, 0, 1]

        return marker

    def _AddMarker(self, marker, render, focus):
        # Add marker to the marker list in GUI and to the itemDataMap.
        num_items = self.marker_list_ctrl.GetItemCount()

        key = 0
        if len(self.itemDataMap) > 0:
            # If itemDataMap is not empty, set the new key as last key + 1
            key = list(self.itemDataMap.keys())[-1] + 1

        list_entry = ["" for _ in range(0, const.X_COLUMN)]
        list_entry[const.ID_COLUMN] = num_items
        list_entry[const.SESSION_COLUMN] = str(marker.session_id)
        list_entry[const.MARKER_TYPE_COLUMN] = marker.marker_type.human_readable
        list_entry[const.LABEL_COLUMN] = marker.label
        list_entry[const.Z_OFFSET_COLUMN] = str(marker.z_offset) if marker.z_offset != 0.0 else ""
        list_entry[const.TARGET_COLUMN] = "Yes" if marker.is_target else ""
        list_entry[const.POINT_OF_INTEREST_TARGET_COLUMN] = (
            "Yes" if marker.is_point_of_interest else ""
        )
        list_entry[const.MEP_COLUMN] = str(marker.mep_value) if marker.mep_value else ""

        if self.session.GetConfig("debug"):
            list_entry.append(round(marker.x, 1))
            list_entry.append(round(marker.y, 1))
            list_entry.append(round(marker.z, 1))

        self.marker_list_ctrl.Append(list_entry)
        self.marker_list_ctrl.SetItemData(num_items, key)
        data_map_entry = list_entry.copy()

        # Add the UUID to the entry in itemDataMap
        data_map_entry.append(marker.marker_uuid)
        self.itemDataMap[key] = data_map_entry

        if marker.marker_type == MarkerType.BRAIN_TARGET:
            self.marker_list_ctrl.SetItemBackgroundColour(num_items, wx.Colour(102, 178, 255))

        self.marker_list_ctrl.EnsureVisible(num_items)

        # Focus on the added marker.
        if focus:
            self.FocusOnMarker(num_items)
