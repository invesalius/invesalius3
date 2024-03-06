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

from functools import partial
import itertools
import time

import numpy as np
try:
    import Trekker
    has_trekker = True
except ImportError:
    has_trekker = False

try:
    #TODO: the try-except could be done inside the mTMS() method call
    from invesalius.navigation.mtms import mTMS
    mTMS()
    has_mTMS = True
except:
    has_mTMS = False

import wx
import sys

try:
    import wx.lib.agw.foldpanelbar as fpb
except ImportError:
    import wx.lib.foldpanelbar as fpb

import wx.lib.platebtn as pbtn

import wx.lib.colourselect as csel
import wx.lib.masked.numctrl
from invesalius.pubsub import pub as Publisher

import invesalius.constants as const

import invesalius.data.coregistration as dcr
import invesalius.data.slice_ as sl
import invesalius.data.tractography as dti
import invesalius.data.record_coords as rec
import invesalius.data.vtk_utils as vtk_utils
import invesalius.data.bases as db
from invesalius.data.markers.marker import MarkerType, Marker
import invesalius.data.markers.marker_transformator

import invesalius.gui.dialogs as dlg
import invesalius.project as prj
import invesalius.session as ses

from invesalius import utils
from invesalius.gui import utils as gui_utils
from invesalius.navigation.iterativeclosestpoint import IterativeClosestPoint
from invesalius.navigation.navigation import Navigation
from invesalius.navigation.image import Image
from invesalius.navigation.tracker import Tracker

from invesalius.navigation.robot import Robot, RobotObjective

from invesalius.net.neuronavigation_api import NeuronavigationApi

HAS_PEDAL_CONNECTION = True
try:
    from invesalius.net.pedal_connection import PedalConnection
except ImportError:
    HAS_PEDAL_CONNECTION = False

from invesalius import inv_paths

BTN_NEW = wx.NewId()
BTN_IMPORT_LOCAL = wx.NewId()
        
def GetBitMapForBackground():
    image_file = os.path.join('head.png')
    bmp = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath(image_file)), wx.BITMAP_TYPE_PNG)
    return bmp


class TaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        inner_panel = InnerTaskPanel(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(inner_panel, 1, wx.EXPAND|wx.GROW|wx.BOTTOM|wx.RIGHT |
                  wx.LEFT, 7)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.Update()
        self.SetAutoLayout(1)

class InnerTaskPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        default_colour = self.GetBackgroundColour()
        background_colour = wx.Colour(255,255,255)
        self.SetBackgroundColour(background_colour)

        # Fold panel which contains navigation configurations
        fold_panel = FoldPanel(self)
        fold_panel.SetBackgroundColour(default_colour)

        # Add line sizer into main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(fold_panel, 1, wx.GROW|wx.EXPAND|wx.LEFT|wx.RIGHT, 5)
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
        sizer.Add(inner_panel, 0, wx.EXPAND|wx.GROW)
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

        fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                      (10, 600), 0, fpb.FPB_SINGLE_FOLD)
        gbs = wx.GridBagSizer(5,5)
        gbs.AddGrowableCol(0, 1)
        self.gbs = gbs

        # Initialize Navigation, Tracker, Robot, Image, and PedalConnection objects here to make them
        # available to several panels.

        tracker = Tracker()
        image = Image()
        pedal_connection = PedalConnection() if HAS_PEDAL_CONNECTION else None
        icp = IterativeClosestPoint()
        neuronavigation_api = NeuronavigationApi()
        navigation = Navigation(
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )
        robot = Robot(
            tracker=tracker,
            navigation=navigation,
            icp=icp,
        )

        self.tracker = tracker
        self.robot = robot
        self.image = image
        self.navigation = navigation

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_GRADIENT_V)
        style.SetFirstColour(default_colour)
        style.SetSecondColour(default_colour)

        item = fold_panel.AddFoldPanel(_("Coregistration"), collapsed=True)
        ntw = CoregistrationPanel(
            parent=item,
            navigation=navigation,
            tracker=tracker,
            robot=robot,
            icp=icp,
            image=image,
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )
        self.fold_panel = fold_panel
        self.__calc_best_size(ntw)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, spacing=0,
                                      leftSpacing=0, rightSpacing=0)
        fold_panel.Expand(fold_panel.GetFoldPanel(0))

        item = fold_panel.AddFoldPanel(_("Navigation"), collapsed=True)
        self.__id_nav = item.GetId()
        ntw = NavigationPanel(
            parent=item,
            navigation=navigation,
            tracker=tracker,
            robot=robot,
            icp=icp,
            image=image,
            pedal_connection=pedal_connection,
            neuronavigation_api=neuronavigation_api,
        )

        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item, ntw, spacing=0,
                                      leftSpacing=0, rightSpacing=0)
        self.fold_panel.Bind(fpb.EVT_CAPTIONBAR, self.OnFoldPressCaption)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(gbs, 1, wx.GROW|wx.EXPAND)
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
        #Publisher.subscribe(self.OnShowDbs, "Show dbs folder")
        #Publisher.subscribe(self.OnHideDbs, "Hide dbs folder")
        Publisher.subscribe(self.OpenNavigation, 'Open navigation menu')
        Publisher.subscribe(self.OnEnableState, "Enable state project")
    
    def __calc_best_size(self, panel):
        parent = panel.GetParent()
        panel.Reparent(self)

        gbs = self.gbs
        fold_panel = self.fold_panel

        # Calculating the size
        gbs.AddGrowableRow(1, 1)
        #gbs.AddGrowableRow(0, 1)
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
            Publisher.sendMessage('Back to image fiducials')

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

            Publisher.sendMessage('Update serial port', serial_port_in_use=True, com_port=com_port, baud_rate=baud_rate)
        else:
            Publisher.sendMessage('Update serial port', serial_port_in_use=False)

    # 'Show coil' button

    # Called when the 'Show coil' button is pressed elsewhere in code.
    def PressShowCoilButton(self, pressed=False):
        self.show_coil_button.SetValue(pressed)
        self.OnShowCoil()

    def EnableShowCoilButton(self, enabled=False):
        self.show_coil_button.Enable(enabled)

    def OnShowCoil(self, evt=None):
        pressed = self.show_coil_button.GetValue()
        Publisher.sendMessage('Show coil in viewer volume', state=pressed)

    # 'Lock to coil' button

    # Called when the 'Lock to coil' button is pressed elsewhere in code.
    def PressLockToCoilButton(self, pressed):
        self.lock_to_coil_button.SetValue(pressed)
        self.OnLockToCoilButton()

    def OnLockToCoilButton(self, evt=None, status=None):
        Publisher.sendMessage('Lock to coil', enabled=self.lock_to_coil_button.GetValue())

    def EnableLockToCoilButton(self, enabled):
        self.lock_to_coil_button.Enable(enabled)
    
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
        self.fold_panel.SetMinSize((self.fold_panel.GetSize()[0], sizeNeeded ))
        self.fold_panel.SetSize((self.fold_panel.GetSize()[0], sizeNeeded))

    def CheckRegistration(self):
        return self.tracker.AreTrackerFiducialsSet() and self.image.AreImageFiducialsSet() and self.navigation.GetObjectRegistration() is not None

    def OpenNavigation(self):
        self.fold_panel.Expand(self.fold_panel.GetFoldPanel(1))
    

class CoregistrationPanel(wx.Panel):
    def __init__(self, parent, navigation, tracker, robot, icp, image, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        #Changed from default color for OSX
        background_colour = (255, 255, 255)
        self.SetBackgroundColour(background_colour)

        book = wx.Notebook(self, -1,style= wx.BK_DEFAULT)
        book.Bind(wx.EVT_BOOKCTRL_PAGE_CHANGING, self.OnPageChanging)
        book.Bind(wx.EVT_BOOKCTRL_PAGE_CHANGED, self.OnPageChanged)
        if sys.platform != 'win32':
            book.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)

        self.navigation = navigation
        self.tracker = tracker
        self.robot = robot
        self.icp = icp
        self.image = image
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        book.AddPage(ImagePage(book, image), _("Image"))
        book.AddPage(TrackerPage(book, icp, tracker, navigation, pedal_connection, neuronavigation_api), _("Tracker"))
        book.AddPage(RefinePage(book, icp, tracker, image, navigation), _("Refine"))
        book.AddPage(StimulatorPage(book, navigation), _("Stimulator"))

        book.SetSelection(0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(book, 0, wx.EXPAND)
        self.SetSizer(sizer)

        book.Refresh()
        self.book = book
        self.__bind_events()
    
    def __bind_events(self):
        Publisher.subscribe(self._FoldTracker,
                                 'Next to tracker fiducials')
        Publisher.subscribe(self._FoldRefine,
                                 'Next to refine fiducials')
        Publisher.subscribe(self._FoldStimulator,
                                 'Next to stimulator fiducials')
        Publisher.subscribe(self._FoldImage,
                                 'Back to image fiducials')
        

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
                wx.MessageBox(_("Select image fiducials first"), _("InVesalius 3"))
        if old_page != 2:
            # Load data into refine tab
            Publisher.sendMessage("Update UI for refine tab")
        
        # new page validations
        if (old_page == 1) and (new_page == 2 or new_page == 3):
            # Do not allow user to move to other (forward) tabs if tracker fiducials not done.
            if self.image.AreImageFiducialsSet() and not self.tracker.AreTrackerFiducialsSet():
                self.book.SetSelection(1)
                wx.MessageBox(_("Select tracker fiducials first"), _("InVesalius 3"))

    def _FoldImage(self):
        """
        Fold image notebook page.
        """
        self.book.SetSelection(0)

    def _FoldTracker(self):
        """
        Fold tracker notebook page.
        """
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_CROSS)
        self.book.SetSelection(1)

    def _FoldRefine(self):
        """
        Fold refine notebook page.
        """
        self.book.SetSelection(2)

    def _FoldStimulator(self):
        """
        Fold mask notebook page.
        """
        self.book.SetSelection(3)

class ImagePage(wx.Panel):
    def __init__(self, parent, image):
        wx.Panel.__init__(self, parent)

        self.image = image
        self.btns_set_fiducial = [None, None, None]
        self.numctrls_fiducial = [[], [], []]
        self.current_coord = 0, 0, 0, None, None, None

        self.bg_bmp = GetBitMapForBackground()
        # Toggle buttons for image fiducials
        background = wx.StaticBitmap(self, -1, self.bg_bmp, (0, 0))
        for n, fiducial in enumerate(const.IMAGE_FIDUCIALS):
            button_id = fiducial['button_id']
            label = fiducial['label']
            tip = fiducial['tip']

            ctrl = wx.ToggleButton(self, button_id, label=label, style=wx.BU_EXACTFIT)
            ctrl.SetToolTip(wx.ToolTip(tip))
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
        top_sizer.AddMany([
            (start_button),
            (reset_button)
            ])

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(next_button)

        sizer = wx.GridBagSizer(5, 5)
        sizer.Add(self.btns_set_fiducial[1], wx.GBPosition(1, 0), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(self.btns_set_fiducial[2], wx.GBPosition(0, 2), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.btns_set_fiducial[0], wx.GBPosition(1, 3), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(background, wx.GBPosition(1, 2))

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([
            (top_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10), 
            (sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, 5), 
            (bottom_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.TOP, 30)])
        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.LoadImageFiducials, 'Load image fiducials')
        Publisher.subscribe(self.SetImageFiducial, 'Set image fiducial')
        Publisher.subscribe(self.UpdateImageCoordinates, 'Set cross focal point')
        Publisher.subscribe(self.OnResetImageFiducials, "Reset image fiducials")
        Publisher.subscribe(self._OnStateProject, "Enable state project")

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
        fiducial = self.GetFiducialByAttribute(const.IMAGE_FIDUCIALS, 'fiducial_name', label[:2])

        fiducial_index = fiducial['fiducial_index']
        fiducial_name = fiducial['fiducial_name']

        Publisher.sendMessage('Set image fiducial', fiducial_name=fiducial_name, position=position)

        self.btns_set_fiducial[fiducial_index].SetValue(True)
        for m in [0, 1, 2]:
            self.numctrls_fiducial[fiducial_index][m].SetValue(position[m])
        
        self.UpdateNextButton()

    def GetFiducialByAttribute(self, fiducials, attribute_name, attribute_value):
        found = [fiducial for fiducial in fiducials if fiducial[attribute_name] == attribute_value]

        assert len(found) != 0, "No fiducial found for which {} = {}".format(attribute_name, attribute_value)
        return found[0]

    def SetImageFiducial(self, fiducial_name, position):
        fiducial = self.GetFiducialByAttribute(const.IMAGE_FIDUCIALS, 'fiducial_name', fiducial_name)
        fiducial_index = fiducial['fiducial_index']

        self.image.SetImageFiducial(fiducial_index, position)
        self.UpdateNextButton()

    def UpdateImageCoordinates(self, position):
        self.current_coord = position

        for m in [0, 1, 2]:
            if not self.btns_set_fiducial[m].GetValue():
                for n in [0, 1, 2]:
                    self.numctrls_fiducial[m][n].SetValue(float(position[n]))

    def OnImageFiducials(self, n, evt):
        fiducial_name = const.IMAGE_FIDUCIALS[n]['fiducial_name']

        if self.btns_set_fiducial[n].GetValue():
            position = self.numctrls_fiducial[n][0].GetValue(),\
                       self.numctrls_fiducial[n][1].GetValue(),\
                       self.numctrls_fiducial[n][2].GetValue()
        else:
            for m in [0, 1, 2]:
                self.numctrls_fiducial[n][m].SetValue(float(self.current_coord[m]))
            position = np.nan

        Publisher.sendMessage('Set image fiducial', fiducial_name=fiducial_name, position=position)

    def OnNext(self, evt):
        Publisher.sendMessage("Next to tracker fiducials")

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

    def OnStartRegistration(self, evt, ctrl):
        value = ctrl.GetValue()
        if value:
            Publisher.sendMessage("Enable style", style=const.STATE_REGISTRATION)
            for button in self.btns_set_fiducial:
                button.Enable()
            self.start_button.SetLabel("Stop registration")
        else:
            self.start_button.SetLabel("Start registration")
            for button in self.btns_set_fiducial:
                button.Disable()
            Publisher.sendMessage("Disable style", style=const.STATE_REGISTRATION)

class TrackerPage(wx.Panel):
    def __init__(self, parent, icp, tracker, navigation, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)

        self.icp = icp
        self.tracker = tracker
        self.navigation = navigation
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        self.btns_set_fiducial = [None, None, None]
        self.numctrls_fiducial = [[], [], []]
        self.current_coord = 0, 0, 0, None, None, None
        self.tracker_fiducial_being_set = None
        for n in [0, 1, 2]:
            if not self.tracker.IsTrackerFiducialSet(n):
                self.tracker_fiducial_being_set = n
                break
            

        self.bg_bmp = GetBitMapForBackground()
        RED_COLOR = const.RED_COLOR_RGB
        self.RED_COLOR = RED_COLOR
        GREEN_COLOR = const.GREEN_COLOR_RGB
        self.GREEN_COLOR = GREEN_COLOR
        YELLOW_COLOR = (255, 196, 0)
        self.YELLOW_COLOR = YELLOW_COLOR

        # Toggle buttons for image fiducials
        background = wx.StaticBitmap(self, -1, self.bg_bmp, (0, 0))
        for n, fiducial in enumerate(const.TRACKER_FIDUCIALS):
            button_id = fiducial['button_id']
            label = fiducial['label']
            tip = fiducial['tip']

            # ctrl = wx.ToggleButton(self, button_id, label=label, style=wx.BU_EXACTFIT)
            # ctrl.SetToolTip(wx.ToolTip(tip))
            # ctrl.SetBackgroundColour((255, 0, 0))
            # ctrl.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnTrackerFiducials, i=n, ctrl=ctrl))
            # ctrl.SetValue(self.tracker.IsTrackerFiducialSet(n))
            # ctrl.Disable()
            w, h = wx.ScreenDC().GetTextExtent("M"*len(label))
            ctrl = wx.StaticText(self, button_id, label='', style=wx.TE_READONLY | wx.ALIGN_CENTER| wx.ST_NO_AUTORESIZE, size=(55, h+5))
            ctrl.SetLabel(label)
            ctrl.SetToolTip(wx.ToolTip(tip))
            if self.tracker.IsTrackerFiducialSet(n):
                ctrl.SetBackgroundColour(GREEN_COLOR)
            else:
                ctrl.SetBackgroundColour(RED_COLOR)

            self.btns_set_fiducial[n] = ctrl

        for m in range(len(self.btns_set_fiducial)):
            for n in range(3):
                value = self.tracker.GetTrackerFiducialForUI(m, n)
                self.numctrls_fiducial[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1, value=value, )
                    )
                self.numctrls_fiducial[m][n].Hide()
        
        register_button = wx.Button(self, label="Record Fiducial")
        register_button.Bind(wx.EVT_BUTTON, partial(self.OnRegister, ctrl=register_button))
        register_button.Disable()
        self.register_button = register_button

        start_button = wx.ToggleButton(self, label="Start Patient Registration")
        start_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnStartRegistration, ctrl=start_button))
        self.start_button = start_button

        reset_button = wx.Button(self, label="Reset", style=wx.BU_EXACTFIT)
        reset_button.Bind(wx.EVT_BUTTON, partial(self.OnReset, ctrl=reset_button))
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
        main_label = wx.StaticText(self, -1, _("No tracker selected!"))

        if tracker_status:
            main_label.SetLabel(self.tracker.get_trackers()[self.tracker.GetTrackerId() - 1])
        
        self.main_label = main_label

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.AddMany([
            (start_button),
            (reset_button)
            ])

        middle_sizer = wx.BoxSizer(wx.HORIZONTAL)
        middle_sizer.AddMany([
            (current_label),
            (main_label)
        ])
        
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.AddMany([
            (back_button, 0, wx.EXPAND),
            (preferences_button, 0, wx.EXPAND),
            (next_button, 0, wx.EXPAND)
        ])

        sizer = wx.GridBagSizer(5, 5)
        sizer.Add(self.btns_set_fiducial[1], wx.GBPosition(1, 0), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(self.btns_set_fiducial[2], wx.GBPosition(0, 2), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.btns_set_fiducial[0], wx.GBPosition(1, 3), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(background, wx.GBPosition(1, 2))
        sizer.Add(register_button, wx.GBPosition(2, 2), span=wx.GBSpan(1, 2), flag=wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([
            (top_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10), 
            (sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, 5),
            (middle_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20),
            (5, 5),
            (bottom_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)])
        
        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.SetTrackerFiducial, 'Set tracker fiducial')
        Publisher.subscribe(self.OnNextEnable, "Next enable for tracker fiducials")
        Publisher.subscribe(self.OnNextDisable, "Next disable for tracker fiducials")
        Publisher.subscribe(self.OnTrackerChanged, "Tracker changed")
        Publisher.subscribe(self.OnResetTrackerFiducials, "Reset tracker fiducials")

    def LabelHandler(self, ctrl, n=None):
        if self.tracker.IsTrackerFiducialSet(n):
            ctrl.SetBackgroundColour(self.GREEN_COLOR)
        elif n == self.tracker_fiducial_being_set:
            ctrl.SetBackgroundColour(self.YELLOW_COLOR)
        else:
            ctrl.SetBackgroundColour(self.RED_COLOR)

        ctrl.Refresh()

    def GetFiducialByAttribute(self, fiducials, attribute_name, attribute_value):
        found = [fiducial for fiducial in fiducials if fiducial[attribute_name] == attribute_value]

        assert len(found) != 0, "No fiducial found for which {} = {}".format(attribute_name, attribute_value)
        return found[0]

    def SetTrackerFiducial(self, fiducial_name):
        # if not self.tracker.IsTrackerInitialized():
        #     dlg.ShowNavigationTrackerWarning(0, 'choose')
        #     return

        fiducial = self.GetFiducialByAttribute(const.TRACKER_FIDUCIALS, 'fiducial_name', fiducial_name)
        fiducial_index = fiducial['fiducial_index']

        # XXX: The reference mode is fetched from navigation object, however it seems like not quite
        #      navigation-related attribute here, as the reference mode used during the fiducial registration
        #      is more concerned with the calibration than the navigation.
        #
        ref_mode_id = self.navigation.GetReferenceMode()
        self.tracker.SetTrackerFiducial(ref_mode_id, fiducial_index)

        self.ResetICP()
        if self.tracker.AreTrackerFiducialsSet():
            self.OnNextEnable()
            self.OnRegisterDisable()
        else:
            self.OnNextDisable()
            self.OnRegisterEnable()
        #self.tracker.UpdateUI(self.select_tracker_elem, self.numctrls_fiducial, self.txtctrl_fre)

    def set_fiducial_callback(self, state, index=None):
        if state:
            if index is None:
                index = self.tracker_fiducial_being_set
                fiducial_name = const.TRACKER_FIDUCIALS[index]['fiducial_name']
                Publisher.sendMessage('Set tracker fiducial', fiducial_name=fiducial_name)
                self.LabelHandler(self.btns_set_fiducial[index], index)                    
            else:
                fiducial_name = const.TRACKER_FIDUCIALS[index]['fiducial_name']
                Publisher.sendMessage('Set tracker fiducial', fiducial_name=fiducial_name)

        if self.tracker.AreTrackerFiducialsSet():
            if self.pedal_connection is not None:
                self.pedal_connection.remove_callback(name='fiducial')

            if self.neuronavigation_api is not None:
                self.neuronavigation_api.remove_pedal_callback(name='fiducial')
            
            self.tracker_fiducial_being_set = None
        else:
            for n in [0, 1, 2]:
                if not self.tracker.IsTrackerFiducialSet(n):
                    self.tracker_fiducial_being_set = n
                    self.LabelHandler(self.btns_set_fiducial[n], n)
                    break
            else:
                self.tracker_fiducial_being_set = None

    def OnTrackerFiducials(self, evt, i, ctrl):
        value = ctrl.GetValue()
        self.set_fiducial_callback(True, index=i)
        self.btns_set_fiducial[i].SetValue(self.tracker.IsTrackerFiducialSet(i))
        if self.tracker.AreTrackerFiducialsSet():
            if self.start_button.GetValue():
                self.start_button.SetValue(False)
                self.OnStartRegistration(self.start_button, self.start_button)

    def OnRegister(self, evt, ctrl):
        self.set_fiducial_callback(True)
        if self.tracker.AreTrackerFiducialsSet():
            if self.start_button.GetValue():
                self.start_button.SetValue(False)

    def ResetICP(self):
        self.icp.ResetICP()
        #self.checkbox_icp.Enable(False)
        #self.checkbox_icp.SetValue(False)

    def OnReset(self, evt, ctrl):
        self.tracker.ResetTrackerFiducials()
        self.OnResetTrackerFiducials()

    def OnResetTrackerFiducials(self):
        self.tracker_fiducial_being_set = None
        self.OnNextDisable()
        self.OnRegisterDisable()
        for i, button in enumerate(self.btns_set_fiducial):
            self.LabelHandler(button, i)
        self.start_button.SetValue(False)
        self.OnStartRegistration(self.start_button, self.start_button)

    def OnNext(self, evt):
        Publisher.sendMessage("Next to refine fiducials")
    
    def OnBack(self, evt):
        Publisher.sendMessage('Back to image fiducials')
    
    def OnPreferences(self, evt):
        Publisher.sendMessage("Open preferences menu", page=2)

    def OnRegisterEnable(self):
        self.register_button.Enable()

    def OnRegisterDisable(self):
        self.register_button.Disable()

    def OnNextEnable(self):
        self.next_button.Enable()

    def OnNextDisable(self):
        self.next_button.Disable()

    def OnStartRegistration(self, evt, ctrl):
        value = ctrl.GetValue()
        for n in [0, 1, 2]:
            if not self.tracker.IsTrackerFiducialSet(n):
                self.tracker_fiducial_being_set = n
                break
        if value:
            if not self.tracker.IsTrackerInitialized():
                print(self.tracker.tracker_connection, self.tracker.tracker_id)
                self.start_button.SetValue(False)
                dlg.ShowNavigationTrackerWarning(0, 'choose')
            else:
                if self.pedal_connection is not None:
                    self.pedal_connection.add_callback(
                        name='fiducial',
                        callback=self.set_fiducial_callback,
                        remove_when_released=False,
                    )

                if self.neuronavigation_api is not None:
                    self.neuronavigation_api.add_pedal_callback(
                        name='fiducial',
                        callback=self.set_fiducial_callback,
                        remove_when_released=False,
                    )
                
                if self.tracker_fiducial_being_set is None:
                    return
                else:
                    self.LabelHandler(self.btns_set_fiducial[self.tracker_fiducial_being_set], self.tracker_fiducial_being_set)

                if not self.tracker.AreTrackerFiducialsSet():
                    self.OnRegisterEnable()

    def OnTrackerChanged(self):
        if self.tracker.GetTrackerId() != const.DEFAULT_TRACKER:
            self.main_label.SetLabel(self.tracker.get_trackers()[self.tracker.GetTrackerId() - 1])
        else:
            self.main_label.SetLabel(_("No tracker selected!"))

class RefinePage(wx.Panel):
    def __init__(self, parent, icp, tracker, image, navigation):

        wx.Panel.__init__(self, parent)
        self.icp = icp
        self.tracker = tracker
        self.image = image
        self.navigation = navigation

        self.numctrls_fiducial = [[], [], [], [], [], []]
        const_labels = [label for label in const.FIDUCIAL_LABELS]
        labels = const_labels + const_labels # duplicate labels for image and tracker
        self.labels = [wx.StaticText(self, -1, _(label)) for label in labels]

        for m in range(6):
            for n in range(3):
                if m <= 2:
                    value = self.image.GetImageFiducialForUI(m, n)
                else:
                    value = self.tracker.GetTrackerFiducialForUI(m - 3, n)

                self.numctrls_fiducial[m].append(
                    wx.lib.masked.numctrl.NumCtrl(parent=self, integerWidth=4, fractionWidth=1, value=value))
        
        txt_label_image = wx.StaticText(self, -1, _("Image Fiducials:"))
        txt_label_image.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        coord_sizer = wx.GridBagSizer(hgap=5, vgap=0)

        for m in range(3):
            coord_sizer.Add(self.labels[m], pos=wx.GBPosition(m, 0))
            for n in range(3):
                coord_sizer.Add(self.numctrls_fiducial[m][n], pos=wx.GBPosition(m, n+1))
                if m in range(6):
                    self.numctrls_fiducial[m][n].SetEditable(False)
        
        txt_label_track = wx.StaticText(self, -1, _("Tracker Fiducials:"))
        txt_label_track.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        coord_sizer_track = wx.GridBagSizer(hgap=5, vgap=0)

        for m in range(3, 6):
            coord_sizer_track.Add(self.labels[m], pos=wx.GBPosition(m-3, 0))
            for n in range(3):
                coord_sizer_track.Add(self.numctrls_fiducial[m][n], pos=wx.GBPosition(m-3, n+1))
                if m in range(1, 6):
                    self.numctrls_fiducial[m][n].SetEditable(False)

        txt_fre = wx.StaticText(self, -1, _('FRE:'))
        tooltip = wx.ToolTip(_("Fiducial registration error"))
        txt_fre.SetToolTip(tooltip)

        value = self.icp.GetFreForUI()
        txtctrl_fre = wx.TextCtrl(self, value=value, size=wx.Size(60, -1), style=wx.TE_CENTRE)
        txtctrl_fre.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        txtctrl_fre.SetBackgroundColour('WHITE')
        txtctrl_fre.SetEditable(0)
        txtctrl_fre.SetToolTip(tooltip)
        self.txtctrl_fre = txtctrl_fre

        self.OnUpdateUI()

        fre_sizer = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        fre_sizer.AddMany([
            (txt_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL),
            (txtctrl_fre, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)
                           
        ])
        
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
        button_sizer.AddMany([
            (back_button, 0, wx.EXPAND),
            (refine_button, 0, wx.EXPAND),
            (next_button, 0, wx.EXPAND)
        ])

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([
            (txt_label_image, 0, wx.EXPAND | wx.ALL, 10),
            (coord_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
            (txt_label_track, 0, wx.EXPAND | wx.ALL, 10),
            (coord_sizer_track, 0, wx.ALIGN_CENTER_HORIZONTAL),
            (10, 10, 0),
            (fre_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL),
            (button_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 20),
            (10, 10, 0)
        ])
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
        Publisher.sendMessage('Back to image fiducials')
    
    def OnNext(self, evt):
        Publisher.sendMessage('Next to stimulator fiducials')

    def OnRefine(self, evt):
        self.icp.RegisterICP(self.navigation, self.tracker)
        if self.icp.use_icp:
            self.UpdateUI()


class StimulatorPage(wx.Panel):
    def __init__(self, parent, navigation):

        wx.Panel.__init__(self, parent)
        self.navigation = navigation

        border = wx.FlexGridSizer(2, 3, 5)
        object_reg = self.navigation.GetObjectRegistration()
        self.object_reg = object_reg
        
        lbl = wx.StaticText(self, -1, _("No stimulator selected!"))
        lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.lbl = lbl

        config_txt = wx.StaticText(self, -1, "")
        self.config_txt = config_txt
        self.config_txt.Hide()

        lbl_edit = wx.StaticText(self, -1, _("Edit Configuration:"))
        btn_edit = wx.Button(self, -1, _("Preferences"))
        btn_edit.SetToolTip("Open preferences menu")
        btn_edit.Bind(wx.EVT_BUTTON, self.OnEditPreferences)

        border.AddMany([
            (lbl, 1, wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10),
            (0, 0),
            (config_txt, 1, wx.EXPAND | wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10),
            (0, 0),
            (lbl_edit, 1, wx.EXPAND | wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10),
            (btn_edit, 0, wx.EXPAND | wx.ALL | wx.ALIGN_LEFT, 10)
        ])

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
        main_sizer.AddMany([
            (border, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10),
            (bottom_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.TOP, 20)
        ])
        
        self.SetSizerAndFit(main_sizer)
        self.Layout()
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.OnObjectUpdate, 'Update object registration')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
        Publisher.subscribe(self.OnCloseProject, 'Remove object data')
    
    def OnCloseProject(self):
        Publisher.sendMessage('Press track object button', pressed=False)
        Publisher.sendMessage('Enable track object button', enabled=False)

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
        Publisher.sendMessage('Open preferences menu', page=3)
    
    def OnNext(self, evt):
        Publisher.sendMessage('Open navigation menu')

class NavigationPanel(wx.Panel):
    def __init__(self, parent, navigation, tracker, robot, icp, image, pedal_connection, neuronavigation_api):
        wx.Panel.__init__(self, parent)

        self.navigation = navigation
        self.tracker = tracker
        self.robot = robot
        self.icp = icp
        self.image = image
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        self.__bind_events()

        self.control_panel = ControlPanel(self, self.navigation, self.tracker, self.robot, self.icp, self.image, self.pedal_connection, self.neuronavigation_api)
        self.marker_panel = MarkersPanel(self, self.navigation, self.tracker, self.robot, self.icp, self.control_panel)

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.Add(self.marker_panel, 1, wx.GROW | wx.EXPAND )

        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(self.control_panel, 0, wx.EXPAND | wx.TOP, 20)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([(top_sizer, 1, wx.EXPAND | wx.GROW),
                            (bottom_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)
                            ])
        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)
        self.Update()

    def __bind_events(self):
        Publisher.subscribe(self.OnCloseProject, 'Close project data')
    
    def OnCloseProject(self):
        self.tracker.ResetTrackerFiducials()
        self.image.ResetImageFiducials()

        Publisher.sendMessage('Disconnect tracker')
        Publisher.sendMessage('Show and track coil', enabled=False)
        Publisher.sendMessage('Delete all markers')
        Publisher.sendMessage("Update marker offset state", create=False)
        Publisher.sendMessage("Remove tracts")
        Publisher.sendMessage("Disable style", style=const.SLICE_STATE_CROSS)
        # TODO: Reset camera initial focus
        Publisher.sendMessage('Reset cam clipping range')
        self.navigation.StopNavigation()
        self.navigation.__init__(
            pedal_connection=self.pedal_connection,
            neuronavigation_api=self.neuronavigation_api
        )
        self.tracker.__init__()
        self.icp.__init__()

    
class ControlPanel(wx.Panel):
    def __init__(self, parent, navigation, tracker, robot, icp, image, pedal_connection, neuronavigation_api):

        wx.Panel.__init__(self, parent)
        
        # Initialize global variables
        self.navigation = navigation
        self.tracker = tracker
        self.robot = robot
        self.icp = icp
        self.image = image
        self.pedal_connection = pedal_connection
        self.neuronavigation_api = neuronavigation_api

        self.nav_status = False
        self.target_mode = False
        self.track_obj = False

        self.navigation_status = False

        self.target_selected = False

        # Toggle button for neuronavigation
        tooltip = wx.ToolTip(_("Start navigation"))
        btn_nav = wx.ToggleButton(self, -1, _("Start neuronavigation"), size=wx.Size(80, -1))
        btn_nav.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        btn_nav.SetToolTip(tooltip)
        self.btn_nav = btn_nav
        self.btn_nav.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnStartNavigationButton, btn_nav=self.btn_nav))
    
        # Constants for bitmap parent toggle button
        ICON_SIZE = (48, 48)
        RED_COLOR = const.RED_COLOR_RGB
        self.RED_COLOR = RED_COLOR
        GREEN_COLOR = const.GREEN_COLOR_RGB
        self.GREEN_COLOR = GREEN_COLOR
        GREY_COLOR = (217, 217, 217)
        self.GREY_COLOR = GREY_COLOR

        # Toggle Button for Tractography
        tooltip = wx.ToolTip(_(u"Control Tractography"))
        BMP_TRACT = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("tract.png")), wx.BITMAP_TYPE_PNG)
        tractography_checkbox = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        tractography_checkbox.SetBackgroundColour(GREY_COLOR)
        tractography_checkbox.SetBitmap(BMP_TRACT)
        tractography_checkbox.SetValue(False)
        tractography_checkbox.Enable(False)
        tractography_checkbox.SetToolTip(tooltip)
        tractography_checkbox.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnTractographyCheckbox, ctrl=tractography_checkbox))
        self.tractography_checkbox = tractography_checkbox

        # Toggle Button to track object or simply the stylus
        tooltip = wx.ToolTip(_(u"Track the object"))
        BMP_TRACK = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("coil.png")), wx.BITMAP_TYPE_PNG)
        track_object_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        track_object_button.SetBackgroundColour(GREY_COLOR)
        track_object_button.SetBitmap(BMP_TRACK)
        track_object_button.SetValue(False)
        if not self.track_obj:
            track_object_button.Enable(False)
        track_object_button.SetToolTip(tooltip)
        track_object_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnTrackObjectButton, ctrl=track_object_button))
        self.track_object_button = track_object_button

        # Toggle Button for Lock to Target
        tooltip = wx.ToolTip(_(u"Allow triggering stimulation pulse only if the coil is at the target"))
        BMP_LOCK = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("lock_to_target.png")), wx.BITMAP_TYPE_PNG)
        lock_to_target_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        lock_to_target_button.SetBackgroundColour(GREY_COLOR)
        lock_to_target_button.SetBitmap(BMP_LOCK)
        lock_to_target_button.SetValue(False)
        lock_to_target_button.Enable(False)
        lock_to_target_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnLockToTargetButton, ctrl=lock_to_target_button))
        lock_to_target_button.SetToolTip(tooltip)
        self.lock_to_target_button = lock_to_target_button

        # Toggle button for showing coil during navigation
        tooltip = wx.ToolTip(_("Show and track TMS coil"))
        BMP_SHOW_COIL = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("coil_eye.png")), wx.BITMAP_TYPE_PNG)
        show_coil_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        show_coil_button.SetBackgroundColour(GREY_COLOR)
        show_coil_button.SetBitmap(BMP_SHOW_COIL)
        show_coil_button.SetToolTip(tooltip)
        show_coil_button.SetValue(False)
        show_coil_button.Enable(False)
        show_coil_button.Bind(wx.EVT_TOGGLEBUTTON, self.OnShowCoil)
        self.show_coil_button = show_coil_button

        # Toggle button for locking camera to coil during navigation
        tooltip = wx.ToolTip(_("Lock to coil"))
        BMP_UPDATE = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("orbit.png")), wx.BITMAP_TYPE_PNG)
        lock_to_coil_button =  wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        lock_to_coil_button.SetBitmap(BMP_UPDATE)
        lock_to_coil_button.SetToolTip(tooltip)
        lock_to_coil_button.SetValue(const.LOCK_TO_COIL_AS_DEFAULT)
        if lock_to_coil_button.IsEnabled():
            lock_to_coil_button.SetBackgroundColour(GREEN_COLOR)
        else:
            lock_to_coil_button.SetBackgroundColour(RED_COLOR)
        lock_to_coil_button.Bind(wx.EVT_TOGGLEBUTTON, self.OnLockToCoilButton)
        self.lock_to_coil_button = lock_to_coil_button

        # Toggle Button to use serial port to trigger pulse signal and create markers
        tooltip = wx.ToolTip(_("Enable serial port communication to trigger pulse and create markers"))
        BMP_PORT = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("wave.png")), wx.BITMAP_TYPE_PNG)
        checkbox_serial_port = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        checkbox_serial_port.SetBackgroundColour(RED_COLOR)
        checkbox_serial_port.SetBitmap(BMP_PORT)
        checkbox_serial_port.SetToolTip(tooltip)
        checkbox_serial_port.SetValue(False)
        checkbox_serial_port.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnEnableSerialPort, ctrl=checkbox_serial_port))
        self.checkbox_serial_port = checkbox_serial_port

        #Toggle Button for Efield
        tooltip = wx.ToolTip(_(u"Control E-Field"))
        BMP_FIELD = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("field.png")), wx.BITMAP_TYPE_PNG)
        efield_checkbox = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        efield_checkbox.SetBackgroundColour(GREY_COLOR)
        efield_checkbox.SetBitmap(BMP_FIELD)
        efield_checkbox.SetValue(False)
        efield_checkbox.Enable(False)
        efield_checkbox.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnEfieldCheckbox, ctrl=efield_checkbox))
        efield_checkbox.SetToolTip(tooltip)
        self.efield_checkbox = efield_checkbox

        #Toggle Button for Target Mode
        tooltip = wx.ToolTip(_(u"Target mode"))
        BMP_TARGET = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("target.png")), wx.BITMAP_TYPE_PNG)
        target_mode_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        target_mode_button.SetBackgroundColour(GREY_COLOR)
        target_mode_button.SetBitmap(BMP_TARGET)
        target_mode_button.SetValue(False)
        target_mode_button.Enable(False)
        target_mode_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnTargetButton))
        target_mode_button.SetToolTip(tooltip)
        self.target_mode_button = target_mode_button
        self.UpdateTargetButton()

        # Toggle button for tracking target with robot during navigation
        tooltip = wx.ToolTip(_("Track target with robot"))
        BMP_TRACK_TARGET = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("robot_track_target.png")), wx.BITMAP_TYPE_PNG)
        robot_track_target_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        robot_track_target_button.SetBackgroundColour(GREY_COLOR)
        robot_track_target_button.SetBitmap(BMP_TRACK_TARGET)
        robot_track_target_button.SetToolTip(tooltip)
        robot_track_target_button.SetValue(False)
        robot_track_target_button.Enable(False)
        robot_track_target_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnRobotTrackTargetButton, ctrl=robot_track_target_button))
        self.robot_track_target_button = robot_track_target_button

        # Toggle button for moving robot away from head
        tooltip = wx.ToolTip(_("Move robot away from head"))
        BMP_ENABLE_MOVE_AWAY = wx.Bitmap(str(inv_paths.ICON_DIR.joinpath("robot_move_away.png")), wx.BITMAP_TYPE_PNG)
        robot_move_away_button = wx.ToggleButton(self, -1, "", style=pbtn.PB_STYLE_SQUARE, size=ICON_SIZE)
        robot_move_away_button.SetBackgroundColour(GREY_COLOR)
        robot_move_away_button.SetBitmap(BMP_ENABLE_MOVE_AWAY)
        robot_move_away_button.SetToolTip(tooltip)
        robot_move_away_button.SetValue(False)
        robot_move_away_button.Enable(False)
        robot_move_away_button.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnRobotMoveAwayButton, ctrl=robot_move_away_button))
        self.robot_move_away_button = robot_move_away_button

        # Sizers
        start_navigation_button_sizer = wx.BoxSizer(wx.VERTICAL)
        start_navigation_button_sizer.AddMany([
            (btn_nav, 0, wx.EXPAND | wx.GROW),
        ])

        navigation_buttons_sizer = wx.FlexGridSizer(4, 5, 5)
        navigation_buttons_sizer.AddMany([
            (tractography_checkbox),
            (lock_to_coil_button),
            (target_mode_button),
            (track_object_button),
            (checkbox_serial_port),
            (efield_checkbox),
            (lock_to_target_button),
            (show_coil_button),
        ])

        robot_buttons_sizer = wx.FlexGridSizer(2, 5, 5)
        robot_buttons_sizer.AddMany([
            (robot_track_target_button),
            (robot_move_away_button),
        ])

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddMany([
            (start_navigation_button_sizer, 0, wx.EXPAND | wx.ALL, 10),
            (navigation_buttons_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP | wx.BOTTOM , 20),
            (robot_buttons_sizer, 0, wx.ALIGN_LEFT | wx.TOP | wx.BOTTOM , 20)
        ])

        self.sizer = main_sizer
        self.SetSizerAndFit(main_sizer)

        self.__bind_events()
        self.Update()
        self.LoadConfig()

    def __bind_events(self):
        Publisher.subscribe(self.OnStartNavigation, 'Start navigation')
        Publisher.subscribe(self.OnStopNavigation, 'Stop navigation')
        Publisher.subscribe(self.OnCheckStatus, 'Navigation status')
        Publisher.subscribe(self.SetTarget, 'Set target')
        Publisher.subscribe(self.UnsetTarget, 'Unset target')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')

        Publisher.subscribe(self.OnRobotStatus, "Robot connection status")
        Publisher.subscribe(self.SetTargetMode, 'Set target mode')

        Publisher.subscribe(self.UpdateTractsVisualization, 'Update tracts visualization')

        # Externally press/unpress and enable/disable buttons.
        Publisher.subscribe(self.PressShowCoilButton, 'Press show-coil button')
        Publisher.subscribe(self.EnableShowCoilButton, 'Enable show-coil button')

        Publisher.subscribe(self.PressLockToCoilButton, 'Press lock to coil button')
        Publisher.subscribe(self.EnableLockToCoilButton, 'Enable lock to coil button')

        Publisher.subscribe(self.PressTrackObjectButton, 'Press track object button')
        Publisher.subscribe(self.EnableTrackObjectButton, 'Enable track object button')

        Publisher.subscribe(self.PressRobotTrackTargetButton, 'Press robot button')
        Publisher.subscribe(self.EnableRobotTrackTargetButton, 'Enable robot button')

        Publisher.subscribe(self.PressRobotMoveAwayButton, 'Press move away button')
        Publisher.subscribe(self.EnableRobotMoveAwayButton, 'Enable move away button')

        Publisher.subscribe(self.ShowTargetButton, 'Show target button')
        Publisher.subscribe(self.HideTargetButton, 'Hide target button')
        Publisher.subscribe(self.PressTargetModeButton, 'Press target mode button')

        # Conditions for enabling 'target mode' button:
        Publisher.subscribe(self.TrackObject, 'Track object')

        #Tractography
        Publisher.subscribe(self.UpdateTrekkerObject, 'Update Trekker object')
        Publisher.subscribe(self.UpdateNumTracts, 'Update number of tracts')
        Publisher.subscribe(self.UpdateSeedOffset, 'Update seed offset')
        Publisher.subscribe(self.UpdateSeedRadius, 'Update seed radius')
        Publisher.subscribe(self.UpdateNumberThreads, 'Update number of threads')
        Publisher.subscribe(self.UpdateTractsVisualization, 'Update tracts visualization')
        Publisher.subscribe(self.UpdatePeelVisualization, 'Update peel visualization')
        Publisher.subscribe(self.UpdateEfieldVisualization, 'Update e-field visualization')
        Publisher.subscribe(self.EnableACT, 'Enable ACT')
        Publisher.subscribe(self.UpdateACTData, 'Update ACT data')

    # Config 
    def SaveConfig(self):
        track_object = self.track_object_button
        state = {
            'track_object': {
                'checked': track_object.GetValue(),
                'enabled': track_object.IsEnabled(),
            }
        }

        session = ses.Session()
        session.SetConfig('object_registration_panel', state)

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig('object_registration_panel')

        if state is None:
            return

        track_object = state['track_object']

        self.EnableTrackObjectButton(track_object['enabled'])
        self.PressTrackObjectButton(track_object['checked'])

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
        ctrl.Enable(state)
        ctrl.SetBackgroundColour(self.GREY_COLOR)

    # Navigation 
    def OnStartNavigation(self):
        if not self.tracker.AreTrackerFiducialsSet() or not self.image.AreImageFiducialsSet():
            wx.MessageBox(_("Invalid fiducials, select all coordinates."), _("InVesalius 3"))

        elif not self.tracker.IsTrackerInitialized():
            dlg.ShowNavigationTrackerWarning(0, 'choose')
            errors = True

        else:
            # Prepare GUI for navigation.
            Publisher.sendMessage("Enable style", style=const.STATE_NAVIGATION)
            Publisher.sendMessage("Hide current mask")

            self.navigation.EstimateTrackerToInVTransformationMatrix(self.tracker, self.image)
            self.navigation.StartNavigation(self.tracker, self.icp)

    def OnStartNavigationButton(self, evt, btn_nav):
        nav_id = btn_nav.GetValue()
        if not nav_id:
            wx.CallAfter(Publisher.sendMessage, 'Stop navigation')
            tooltip = wx.ToolTip(_("Start neuronavigation"))
            btn_nav.SetToolTip(tooltip)
            btn_nav.SetLabelText(_("Start neuronavigation"))
        else:
            Publisher.sendMessage("Start navigation")
            if self.nav_status:
                tooltip = wx.ToolTip(_("Stop neuronavigation"))
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
        enable_track_object = obj_registration is not None and obj_registration[0] is not None and not nav_status
        self.EnableTrackObjectButton(enable_track_object)

    # Robot
    def OnRobotStatus(self, data):
        if data:
            self.Layout()

    # Enable robot buttons if:
    #
    #   - Navigation is on
    #   - Target is set
    #   - Target mode is on
    #   - Robot is connected
    #
    def UpdateRobotButtons(self):
        enabled = self.nav_status and self.target_selected and self.target_mode and self.robot.IsConnected()
        self.EnableRobotTrackTargetButton(enabled=enabled)
        self.EnableRobotMoveAwayButton(enabled=enabled)

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
        Publisher.sendMessage('Update tracts visualization', data=self.view_tracts)
        if not self.view_tracts:
            Publisher.sendMessage('Remove tracts')
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
        Publisher.sendMessage('Track object', enabled=pressed)

        # Disable or enable 'Show coil' button, based on if 'Track object' button is pressed.
        Publisher.sendMessage('Enable show-coil button', enabled=pressed)

        # Also, automatically press or unpress 'Show coil' button.
        Publisher.sendMessage('Press show-coil button', pressed=pressed)

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
        Publisher.sendMessage('Show coil in viewer volume', state=pressed)

    # 'Lock to coil' button
    def PressLockToCoilButton(self, pressed):
        self.UpdateToggleButton(self.lock_to_coil_button, pressed)
        self.OnLockToCoilButton()

    def OnLockToCoilButton(self, evt=None, status=None):
        self.UpdateToggleButton(self.lock_to_coil_button)
        pressed = self.lock_to_coil_button.GetValue()
        Publisher.sendMessage('Lock to coil', enabled=pressed)

    def EnableLockToCoilButton(self, enabled):
        self.EnableToggleButton(self.lock_to_coil_button, enabled)
        self.UpdateToggleButton(self.lock_to_coil_button)
    
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

            Publisher.sendMessage('Update serial port', serial_port_in_use=True, com_port=com_port, baud_rate=baud_rate)
        else:
            Publisher.sendMessage('Update serial port', serial_port_in_use=False)

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

        # If enabling target mode, also press it on automatically.
        pressed = enabled

        self.EnableToggleButton(self.target_mode_button, enabled)
        self.PressTargetModeButton(pressed)

    def PressTargetModeButton(self, pressed):
        self.UpdateToggleButton(self.target_mode_button, pressed)
        self.OnTargetButton()

    def OnTargetButton(self, evt=None):
        pressed = self.target_mode_button.GetValue()
        self.UpdateToggleButton(self.target_mode_button, pressed)
        
        Publisher.sendMessage('Set target mode', enabled=pressed)
        if pressed:
            Publisher.sendMessage('Press lock to coil button', pressed=False)
            Publisher.sendMessage('Enable lock to coil button', enabled=False)

            # Set robot objective to NONE when target mode is disabled.
            self.robot.SetObjective(RobotObjective.NONE)
        else:
            Publisher.sendMessage('Enable lock to coil button', enabled=True)

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


class MarkersPanel(wx.Panel):
    def __init__(self, parent, navigation, tracker, robot, icp, control):
        wx.Panel.__init__(self, parent)
        try:
            default_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENUBAR)
        except AttributeError:
            default_colour = wx.SystemSettings_GetColour(wx.SYS_COLOUR_MENUBAR)
        self.SetBackgroundColour(default_colour)

        self.SetAutoLayout(1)

        self.navigation = navigation
        self.tracker = tracker
        self.robot = robot
        self.icp = icp
        self.control = control
        if has_mTMS:
            self.mTMS = mTMS()
        else:
            self.mTMS = None

        self.marker_transformator = invesalius.data.markers.marker_transformator.MarkerTransformator()

        self.__bind_events()

        self.session = ses.Session()

        self.current_position = [0, 0, 0]
        self.current_orientation = [None, None, None]
        self.current_seed = 0, 0, 0
        self.cortex_position_orientation = [None, None, None, None, None, None]
        self.markers = []
        self.nav_status = False
        self.efield_data_saved = False
        self.efield_target_idx = None 

        self.marker_colour = const.MARKER_COLOUR
        self.marker_size = const.MARKER_SIZE
        self.arrow_marker_size = const.ARROW_MARKER_SIZE
        self.current_session = 1

        self.brain_actor = None
        # Change session
        spin_session = wx.SpinCtrl(self, -1, "", size=wx.Size(40, 23))
        spin_session.SetRange(1, 99)
        spin_session.SetValue(self.current_session)
        spin_session.SetToolTip("Set session")
        spin_session.Bind(wx.EVT_TEXT, partial(self.OnSessionChanged, ctrl=spin_session))
        spin_session.Bind(wx.EVT_SPINCTRL, partial(self.OnSessionChanged, ctrl=spin_session))

        # Marker colour select
        select_colour = csel.ColourSelect(self, -1, colour=[255*s for s in self.marker_colour], size=wx.Size(20, 23))
        select_colour.SetToolTip("Set colour")
        select_colour.Bind(csel.EVT_COLOURSELECT, partial(self.OnSelectColour, ctrl=select_colour))

        btn_create = wx.Button(self, -1, label=_('Create marker'), size=wx.Size(135, 23))
        btn_create.Bind(wx.EVT_BUTTON, self.OnCreateMarker)

        sizer_create = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        sizer_create.AddMany([(spin_session, 1),
                              (select_colour, 0),
                              (btn_create, 0)])

        # Buttons to save and load markers and to change its visibility as well
        btn_save = wx.Button(self, -1, label=_('Save'), size=wx.Size(65, 23))
        btn_save.Bind(wx.EVT_BUTTON, self.OnSaveMarkers)

        btn_load = wx.Button(self, -1, label=_('Load'), size=wx.Size(65, 23))
        btn_load.Bind(wx.EVT_BUTTON, self.OnLoadMarkers)

        btn_visibility = wx.ToggleButton(self, -1, _("Hide"), size=wx.Size(65, 23))
        btn_visibility.Bind(wx.EVT_TOGGLEBUTTON, partial(self.OnMarkersVisibility, ctrl=btn_visibility))

        sizer_btns = wx.FlexGridSizer(rows=1, cols=3, hgap=5, vgap=5)
        sizer_btns.AddMany([(btn_save, 1, wx.RIGHT),
                            (btn_load, 0, wx.LEFT | wx.RIGHT),
                            (btn_visibility, 0, wx.LEFT)])

        # Buttons to delete or remove markers
        btn_delete_single = wx.Button(self, -1, label=_('Remove'), size=wx.Size(65, 23))
        btn_delete_single.Bind(wx.EVT_BUTTON, self.OnDeleteMultipleMarkers)

        btn_delete_all = wx.Button(self, -1, label=_('Delete all'), size=wx.Size(135, 23))
        btn_delete_all.Bind(wx.EVT_BUTTON, self.OnDeleteAllMarkers)

        sizer_delete = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        sizer_delete.AddMany([(btn_delete_single, 1, wx.RIGHT),
                              (btn_delete_all, 0, wx.LEFT)])

        # List of markers
        marker_list_ctrl = wx.ListCtrl(self, -1, style=wx.LC_REPORT, size=wx.Size(0,120))
        marker_list_ctrl.InsertColumn(const.ID_COLUMN, '#')
        marker_list_ctrl.SetColumnWidth(const.ID_COLUMN, 24)

        marker_list_ctrl.InsertColumn(const.SESSION_COLUMN, 'Session')
        marker_list_ctrl.SetColumnWidth(const.SESSION_COLUMN, 51)

        marker_list_ctrl.InsertColumn(const.MARKER_TYPE_COLUMN, 'Type')
        marker_list_ctrl.SetColumnWidth(const.MARKER_TYPE_COLUMN, 77)

        marker_list_ctrl.InsertColumn(const.LABEL_COLUMN, 'Label')
        marker_list_ctrl.SetColumnWidth(const.LABEL_COLUMN, 95)

        marker_list_ctrl.InsertColumn(const.TARGET_COLUMN, 'Target')
        marker_list_ctrl.SetColumnWidth(const.TARGET_COLUMN, 45)

        marker_list_ctrl.InsertColumn(const.POINT_OF_INTEREST_TARGET_COLUMN, 'Efield Target')
        marker_list_ctrl.SetColumnWidth(const.POINT_OF_INTEREST_TARGET_COLUMN,45)

        if self.session.GetConfig('debug'):
            marker_list_ctrl.InsertColumn(const.X_COLUMN, 'X')
            marker_list_ctrl.SetColumnWidth(const.X_COLUMN, 45)

            marker_list_ctrl.InsertColumn(const.Y_COLUMN, 'Y')
            marker_list_ctrl.SetColumnWidth(const.Y_COLUMN, 45)

            marker_list_ctrl.InsertColumn(const.Z_COLUMN, 'Z')
            marker_list_ctrl.SetColumnWidth(const.Z_COLUMN, 45)

        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnMouseRightDown)
        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnMarkerFocused)
        marker_list_ctrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnMarkerUnfocused)
        
        # Intercept key-down events to have custom behaviour for the arrow keys (moving markers).
        marker_list_ctrl.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

        self.marker_list_ctrl = marker_list_ctrl

        # Add all lines into main sizer
        group_sizer = wx.BoxSizer(wx.VERTICAL)
        group_sizer.Add(sizer_create, 0, wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(sizer_btns, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(sizer_delete, 0, wx.BOTTOM | wx.ALIGN_CENTER_HORIZONTAL, 5)
        group_sizer.Add(marker_list_ctrl, 0, wx.EXPAND | wx.ALL, 5)
        group_sizer.Fit(self)

        self.SetSizer(group_sizer)
        self.Update()

        self.LoadState()

    def __bind_events(self):
        Publisher.subscribe(self.UpdateCurrentCoord, 'Set cross focal point')
        Publisher.subscribe(self.OnDeleteMultipleMarkers, 'Delete fiducial marker')
        Publisher.subscribe(self.OnDeleteAllMarkers, 'Delete all markers')
        Publisher.subscribe(self.OnCreateMarker, 'Create marker')
        Publisher.subscribe(self.UpdateNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateSeedCoordinates, 'Update tracts')
        Publisher.subscribe(self.OnChangeCurrentSession, 'Current session changed')
        Publisher.subscribe(self.UpdateMarkerOrientation, 'Open marker orientation dialog')
        Publisher.subscribe(self.AddPeeledSurface, 'Update peel')
        Publisher.subscribe(self.GetEfieldDataStatus, 'Get status of Efield saved data')
        Publisher.subscribe(self.GetIdList, 'Get ID list')
        Publisher.subscribe(self.GetRotationPosition, 'Send coil position and rotation')
        Publisher.subscribe(self.CreateMarkerEfield, 'Create Marker from tangential')
        Publisher.subscribe(self.UpdateCortexMarker, 'Update Cortex Marker')

    def SaveState(self):
        state = [marker.to_dict() for marker in self.markers]

        session = ses.Session()
        session.SetState('markers', state)

    def LoadState(self):
        session = ses.Session()
        state = session.GetState('markers')

        if state is None:
            return

        for d in state:
            if 'cortex_position_orientation' in d:
                cortex_position_orientation = d['cortex_position_orientation']
            else:
                cortex_position_orientation = None

            # Create enum from the corresponding integer that is saved in the state.
            marker_type = MarkerType(d['marker_type'])

            marker = self.CreateMarker(
                position=d['position'],
                orientation=d['orientation'],
                colour=d['colour'],
                size=d['size'],
                label=d['label'],
                marker_type=marker_type,
                # XXX: See comment below. Should be improved so that is_target wouldn't need to be set as False here.
                is_target=False,
                seed=d['seed'],
                session_id=d['session_id'],
                cortex_position_orientation=cortex_position_orientation,
            )
            # Note that we don't want to render the markers here for each loop iteration.
            self.AddMarker(marker, render=False)

            # XXX: Do the same thing as in OnLoadMarkers function: first create marker that is never set as a target,
            # then set as target if needed. This could be refactored so that a CreateMarker call would
            # suffice to set it as target.
            if d['is_target']:
                self.__set_marker_as_target(len(self.markers) - 1)

            if d['is_point_of_interest']:
                self.__set_marker_as_point_of_interest(len(self.markers) - 1)
                Publisher.sendMessage('Set as Efield target at cortex', position=d['position'],
                                        orientation=d['orientation'])

    def __find_target_marker_idx(self):
        """
        Return the index of the marker currently selected as target (there
        should be at most one). If there is no such marker, return None.
        """
        for i in range(len(self.markers)):
            if self.markers[i].is_target:
                return i
                
        return None

    def __find_point_of_interest_marker(self):
        for i in range(len(self.markers)):
            if self.markers[i].is_point_of_interest:
                return i

        return None

    def __get_brain_target_markers(self):
        """
        Return the index of the marker currently selected as target (there
        should be at most one). If there is no such marker, return None.
        """
        brain_target_list = []
        for i in range(len(self.markers)):
            if self.markers[i].marker_type == MarkerType.BRAIN_TARGET:
                brain_target_list.append(self.markers[i].coordinate)

        if brain_target_list:
            return brain_target_list

        return None

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

    def __delete_all_markers(self):
        """
        Delete all markers
        """
        for i in reversed(range(len(self.markers))):
            del self.markers[i]
            self.marker_list_ctrl.DeleteItem(i)

    def __delete_multiple_markers(self, indexes):
        """
        Delete multiple markers indexed by 'indexes'. Indexes must be sorted in
        the ascending order.
        """
        for i in reversed(indexes):
            Publisher.sendMessage('Delete marker', marker=self.markers[i])
            del self.markers[i]
            self.marker_list_ctrl.DeleteItem(i)
            for n in range(0, self.marker_list_ctrl.GetItemCount()):
                self.marker_list_ctrl.SetItem(n, 0, str(n + 1))

    def __delete_all_brain_targets(self):
        """
        Delete all brain targets markers
        """
        brain_target_index = []
        for index in range(len(self.markers)):
            if self.markers[index].marker_type == MarkerType.BRAIN_TARGET:
                brain_target_index.append(index)
        for index in reversed(brain_target_index):
            Publisher.sendMessage('Delete marker', marker=self.markers[index])
            self.marker_list_ctrl.SetItemBackgroundColour(index, 'white')
            del self.markers[index]
            self.marker_list_ctrl.DeleteItem(index)
            for n in range(0, self.marker_list_ctrl.GetItemCount()):
                self.marker_list_ctrl.SetItem(n, 0, str(n + 1))

    def __set_marker_as_point_of_interest(self, idx):
        """
        Set marker indexed by idx as the new point of interest. idx must be a valid index.
        """
        # Find the previous point of interest
        prev_idx = self.__find_point_of_interest_marker()

        # If the new point of interest is same as the previous do nothing
        if prev_idx == idx:
            return

        # Unset the previous point of interest
        if prev_idx is not None:
            self.markers[prev_idx].is_point_of_interest = False
            self.marker_list_ctrl.SetItemBackgroundColour(prev_idx, 'white')
            marker = self.markers[prev_idx]
            Publisher.sendMessage('Set target transparency', marker=marker, transparent=False)
            self.marker_list_ctrl.SetItem(prev_idx, const.POINT_OF_INTEREST_TARGET_COLUMN, "")

        # Set the new point of interest
        self.markers[idx].is_point_of_interest = True
        self.marker_list_ctrl.SetItemBackgroundColour(idx, 'PURPLE')
        self.marker_list_ctrl.SetItem(idx, const.POINT_OF_INTEREST_TARGET_COLUMN, _("Yes"))

    def __set_marker_as_target(self, idx):
        """
        Set marker indexed by idx as the new target. idx must be a valid index.
        """
        # Find the previous target
        prev_idx = self.__find_target_marker_idx()

        # If the new target is same as the previous do nothing.
        if prev_idx == idx:
            return

        # Unset the previous target
        if prev_idx is not None:
            self.markers[prev_idx].is_target = False
            self.marker_list_ctrl.SetItemBackgroundColour(prev_idx, 'white')
            marker = self.markers[prev_idx]
            Publisher.sendMessage('Set target transparency', marker=marker, transparent=False)
            self.marker_list_ctrl.SetItem(prev_idx, const.TARGET_COLUMN, "")

        # Set the new target
        marker = self.markers[idx]
        marker.is_target = True

        # Set the marker as the target in the list control.
        self.marker_list_ctrl.SetItemBackgroundColour(idx, 'RED')
        self.marker_list_ctrl.SetItem(idx, const.TARGET_COLUMN, _("Yes"))

        self.control.target_selected = True

        Publisher.sendMessage('Set target', marker=marker)
        Publisher.sendMessage('Set target transparency', marker=marker, transparent=True)

    @staticmethod
    def __list_fiducial_labels():
        """Return the list of marker labels denoting fiducials."""
        return list(itertools.chain(*(const.BTNS_IMG_MARKERS[i].values() for i in const.BTNS_IMG_MARKERS)))

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

    def UpdateSeedCoordinates(self, root=None, affine_vtk=None, coord_offset=(0, 0, 0), coord_offset_w=(0, 0, 0)):
        self.current_seed = coord_offset_w

    def UpdateCortexMarker(self, CoGposition, CoGorientation):
        self.cortex_position_orientation = CoGposition +  CoGorientation

    def OnMouseRightDown(self, evt):
        focused_marker_idx = self.marker_list_ctrl.GetFocusedItem()
        target_marker_idx = self.__find_target_marker_idx()
        marker_type = self.markers[focused_marker_idx].marker_type

        # Check if the currently focused marker is the active target.
        is_active_target = focused_marker_idx == target_marker_idx

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

        edit_id = menu_id.Append(0, _('Edit label'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuEditMarkerLabel, edit_id)

        color_id = menu_id.Append(1, _('Edit color'))
        menu_id.Bind(wx.EVT_MENU, self.OnMenuSetColor, color_id)

        # Allow duplicate only for markers that are not fiducials.
        if not is_fiducial:
            duplicate_menu_item = menu_id.Append(2, _('Duplicate'))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuDuplicateMarker, duplicate_menu_item)

        menu_id.AppendSeparator()

        # Show 'Set as target'/'Unset target' menu item only if the marker is a coil target.
        if is_coil_target:
            if is_active_target:
                target_menu_item = menu_id.Append(3, _('Unset target'))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuUnsetTarget, target_menu_item)
                if has_mTMS:
                    brain_target_menu_item= menu_id.Append(3, _('Set brain target'))
                    menu_id.Bind(wx.EVT_MENU, self.OnSetBrainTarget, brain_target_menu_item)
            else:
                target_menu_item = menu_id.Append(3, _('Set as target'))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuSetTarget, target_menu_item)

        # Show 'Create coil target' menu item if the marker is a coil pose.
        if is_coil_pose:
            # 'Create coil target' menu item.
            create_coil_target_menu_item = menu_id.Append(6, _('Create coil target'))
            menu_id.Bind(wx.EVT_MENU, self.OnCreateCoilTargetFromCoilPose, create_coil_target_menu_item)

        # Show 'Create brain target' and 'Create coil target' menu items only if the marker is a landmark.
        if is_landmark:
            # 'Create brain target' menu item.
            create_brain_target_menu_item = menu_id.Append(5, _('Create brain target'))
            menu_id.Bind(wx.EVT_MENU, self.OnCreateBrainTargetFromLandmark, create_brain_target_menu_item)

            # 'Create coil target' menu item.
            create_coil_target_menu_item = menu_id.Append(6, _('Create coil target'))
            menu_id.Bind(wx.EVT_MENU, self.OnCreateCoilTargetFromLandmark, create_coil_target_menu_item)

        is_brain_target = self.markers[self.marker_list_ctrl.GetFocusedItem()].marker_type == MarkerType.BRAIN_TARGET
        if is_brain_target and has_mTMS:
            send_brain_target_menu_item = menu_id.Append(7, _('Send brain target to mTMS'))
            menu_id.Bind(wx.EVT_MENU, self.OnSendBrainTarget, send_brain_target_menu_item)

        if self.nav_status and self.navigation.e_field_loaded:
            #Publisher.sendMessage('Check efield data')
            #if not tuple(np.argwhere(self.indexes_saved_lists == self.marker_list_ctrl.GetFocusedItem())):
            if self.__find_target_marker_idx()  == self.marker_list_ctrl.GetFocusedItem():
                efield_menu_item = menu_id.Append(8, _('Save Efield target Data'))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuSaveEfieldTargetData, efield_menu_item)

        if self.navigation.e_field_loaded:
            efield_target_menu_item = menu_id.Append(9, _('Set as Efield target 1 (origin)'))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuSetEfieldTarget, efield_target_menu_item)

            efield_target_menu_item = menu_id.Append(10, _('Set as Efield target 2'))
            menu_id.Bind(wx.EVT_MENU, self.OnMenuSetEfieldTarget2, efield_target_menu_item)
            # Publisher.sendMessage('Check efield data')
            # if self.efield_data_saved:
            #     if tuple(np.argwhere(self.indexes_saved_lists==self.marker_list_ctrl.GetFocusedItem())):
            #         if self.efield_target_idx  == self.marker_list_ctrl.GetFocusedItem():
            #             efield_target_menu_item  = menu_id.Append(9, _('Remove Efield target'))
            #             menu_id.Bind(wx.EVT_MENU, self.OnMenuRemoveEfieldTarget, efield_target_menu_item )
            #         else:
            #             efield_target_menu_item = menu_id.Append(9, _('Set as Efield target(compare)'))
            #             menu_id.Bind(wx.EVT_MENU, self.OnMenuSetEfieldTarget, efield_target_menu)

        if self.navigation.e_field_loaded and not self.nav_status:
            if self.__find_target_marker_idx() == self.marker_list_ctrl.GetFocusedItem():
                efield_vector_plot_menu_item = menu_id.Append(11,_('Show vector field'))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuShowVectorField, efield_vector_plot_menu_item)

        if self.navigation.e_field_loaded:
            if self.__find_point_of_interest_marker() == self.marker_list_ctrl.GetFocusedItem():
                create_efield_target = menu_id.Append(12, _('Remove Efield Cortex target'))
                menu_id.Bind(wx.EVT_MENU, self.OnMenuRemoveEfieldTargetatCortex, create_efield_target)
            else:
                create_efield_target = menu_id.Append(12, _('Set as Efield Cortex target'))
                menu_id.Bind(wx.EVT_MENU, self.OnSetEfieldBrainTarget, create_efield_target)
                self.marker_list_ctrl.GetFocusedItem()

        menu_id.AppendSeparator()

        self.PopupMenu(menu_id)
        menu_id.Destroy()

    def OnKeyDown(self, event):
        """
        When a key is pressed, move the focused marker in the direction specified by the key.

        The marker can be moved in the X- or Y-direction or rotated along the Z-axis using the keys
        'W', 'A', 'S', 'D', 'PageUp', and 'PageDown'.
        
        The marker can also be moved in the Z-direction using the '+' and '-' keys;
        '+' moves it closer to the scalp, and '-' moves it away from the scalp.

        The marker can only be moved if the navigation is off, except for the '+' and '-' keys.
        """
        keycode = event.GetKeyCode()

        focused_marker_idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.markers[focused_marker_idx]

        # Keycodes for the relevant keys.
        WXK_PLUS = 43
        WXK_PLUS_NUMPAD = 388
        WXK_MINUS = 45
        WXK_MINUS_NUMPAD = 390

        WXK_KEY_A = 65
        WXK_KEY_D = 68
        WXK_KEY_W = 87
        WXK_KEY_S = 83

        WXK_PAGEUP = 366
        WXK_PAGEDOWN = 367

        direction = None
        stay_on_scalp = True

        # Allow moving the marker in X- or Y-direction or rotating along Z-axis only if navigation is off.
        if keycode == WXK_KEY_S and not self.nav_status:
            direction = [0, -1, 0, 0, 0, 0]

        elif keycode == WXK_KEY_W and not self.nav_status:
            direction = [0, 1, 0, 0, 0, 0]

        elif keycode == WXK_KEY_A and not self.nav_status:
            direction = [-1, 0, 0, 0, 0, 0]

        elif keycode == WXK_KEY_D and not self.nav_status:
            direction = [1, 0, 0, 0, 0, 0]

        elif keycode == WXK_PAGEUP and not self.nav_status:
            stay_on_scalp = False
            direction = [0, 0, 0, 0, 0, 1]

        elif keycode == WXK_PAGEDOWN and not self.nav_status:
            stay_on_scalp = False
            direction = [0, 0, 0, 0, 0, -1]
                
        elif keycode in [WXK_PLUS, WXK_PLUS_NUMPAD]:
            stay_on_scalp = False
            direction = [0, 0, -1, 0, 0, 0]

        elif keycode in [WXK_MINUS, WXK_MINUS_NUMPAD]:
            stay_on_scalp = False
            direction = [0, 0, 1, 0, 0, 0]

        # Allow other key events to be processed normally, such as the arrow keys for
        # navigating the list control.
        if direction is None:
            event.Skip()
            return

        # Only allow moving markers of type 'coil target' using keyboard; otherwise, return early.
        if marker.marker_type != MarkerType.COIL_TARGET:
            return

        # Move the marker one unit in the direction specified by the key.
        displacement = 1 * np.array(direction)
        if stay_on_scalp:
            self.marker_transformator.MoveMarkerOnScalp(
                marker=marker,
                displacement_along_scalp_tangent=displacement,
            )
        else:
            self.marker_transformator.MoveMarker(
                marker=marker,
                displacement=displacement,
            )

        # Update the marker in the volume viewer.
        Publisher.sendMessage('Update marker', marker=marker, new_position=marker.position, new_orientation=marker.orientation)

        # Update the target if the marker is the active target.
        if marker.is_target:
            Publisher.sendMessage('Set target', marker=marker)

    # Called when a marker on the list gets the focus by the user left-clicking on it.
    def OnMarkerFocused(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.markers[idx]

        Publisher.sendMessage('Highlight marker', marker=marker)

    # Called when a marker on the list loses the focus by the user left-clicking on another marker.
    def OnMarkerUnfocused(self, evt):
        Publisher.sendMessage('Unhighlight marker')
        
    def OnCreateCoilTargetFromLandmark(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        if list_index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        # Create a duplicate of the selected marker.
        new_marker = self.markers[list_index].duplicate()

        # Project to the scalp.        
        self.marker_transformator.ProjectToScalp(
            marker=new_marker,
            # We are projecting the marker that is on the brain surface; hence, project to the opposite side
            # of the scalp because the normal vectors are unreliable on the brain side of the scalp.
            opposite_side=True,
        )

        # Set marker type to 'coil target'.
        new_marker.marker_type = MarkerType.COIL_TARGET

        # Add the new marker to the marker list and render it.
        self.AddMarker(new_marker, render=True)
        
        self.SaveState()

    def OnCreateCoilTargetFromCoilPose(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        if list_index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        # Create a duplicate of the selected marker.
        new_marker = self.markers[list_index].duplicate()

        # Set marker type to 'coil target'.
        new_marker.marker_type = MarkerType.COIL_TARGET

        # Add the new marker to the marker list and render it.
        self.AddMarker(new_marker, render=True)
        
        self.SaveState()

    def OnMenuEditMarkerLabel(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        if list_index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        new_label = dlg.ShowEnterMarkerID(self.marker_list_ctrl.GetItemText(list_index, const.LABEL_COLUMN))
        self.markers[list_index].label = str(new_label)
        self.marker_list_ctrl.SetItem(list_index, const.LABEL_COLUMN, new_label)

        self.SaveState()

    def OnMenuSetTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        # Set robot objective to NONE when a new target is selected. This prevents the robot from
        # automatically moving to the new target (which would be the case if robot objective was previously
        # set to TRACK_TARGET). Preventing the automatic moving makes robot movement more explicit and predictable.
        self.robot.SetObjective(RobotObjective.NONE)

        self.__set_marker_as_target(idx)

        self.SaveState()

    def OnMenuDuplicateMarker(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        # Create a duplicate of the selected marker.
        new_marker = self.markers[idx].duplicate()
        self.AddMarker(new_marker, render=True)

        self.SaveState()

    def GetEfieldDataStatus(self, efield_data_loaded, indexes_saved_list):
        self.indexes_saved_lists= []
        self.efield_data_saved = efield_data_loaded
        self.indexes_saved_lists = indexes_saved_list

    def CreateMarkerEfield(self, point, orientation):
        from vtkmodules.vtkCommonColor import (
            vtkNamedColors
        )
        vtk_colors = vtkNamedColors()
        position_flip = list(point)
        position_flip[1] = -position_flip[1]

        marker = self.CreateMarker(
            position=position_flip,
            orientation=list(orientation),
            colour=vtk_colors.GetColor3d('Orange'),
            size=2,
            marker_type=MarkerType.COIL_TARGET,
        )
        self.AddMarker(marker, render=True)

    def OnMenuShowVectorField(self, evt):
        session = ses.Session()
        list_index = self.marker_list_ctrl.GetFocusedItem()
        position = self.markers[list_index].position
        orientation = np.radians(self.markers[list_index].orientation)
        Publisher.sendMessage('Calculate position and rotation', position=position, orientation=orientation)
        coord = [position, orientation]
        coord = np.array(coord).flatten()

        #Check here, it resets the radious list
        Publisher.sendMessage('Update interseccion offline', m_img =self.m_img_offline, coord = coord, list_index = list_index)

        if session.GetConfig('debug_efield'):
            enorm = self.navigation.debug_efield_enorm
        else:
            enorm = self.navigation.neuronavigation_api.update_efield_vectorROI(position=self.cp,
                                                                      orientation=orientation,
                                                                      T_rot=self.T_rot,
                                                                      id_list=self.ID_list)
        enorm_data = [self.T_rot, self.cp, coord, enorm, self.ID_list]
        Publisher.sendMessage('Get enorm', enorm_data = enorm_data , plot_vector = True)

    def GetRotationPosition(self, T_rot, cp, m_img):
        self.T_rot = T_rot
        self.cp = cp
        self.m_img_offline = m_img

    def GetIdList(self, ID_list):
        self.ID_list = ID_list

    def OnMenuSetEfieldTarget(self,evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        self.__set_marker_as_target(idx)
        self.efield_target_idx_origin = idx

        #Publisher.sendMessage('Get target index efield', target_index_list = idx )

    def OnMenuSetEfieldTarget2(self,evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        if idx == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        efield_target_idx_2 = idx
        target1_origin = self.markers[self.efield_target_idx_origin].cortex_position_orientation
        target2 = self.markers[efield_target_idx_2].cortex_position_orientation
        Publisher.sendMessage('Get targets Ids for mtms', target1_origin = target1_origin, target2 = target2)

    def OnMenuSaveEfieldTargetData(self,evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        position = self.markers[list_index].position
        orientation = self.markers[list_index].orientation
        plot_efield_vectors = self.navigation.plot_efield_vectors
        Publisher.sendMessage('Save target data', target_list_index = list_index, position = position, orientation = orientation, plot_efield_vectors= plot_efield_vectors)

    def OnSetEfieldBrainTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        list_index = self.marker_list_ctrl.GetFocusedItem()
        position = self.markers[list_index].position
        orientation =  self.markers[list_index].orientation
        if all([o is None for o in orientation]):
            orientation = [0, 0, 0]

        self.__set_marker_as_point_of_interest(idx)
        Publisher.sendMessage('Send efield target position on brain', marker_id=list_index, position=position, orientation=orientation)
        self.SaveState()

    def OnCreateBrainTargetFromLandmark(self, evt):
        list_index = self.marker_list_ctrl.GetFocusedItem()
        position = self.markers[list_index].position
        orientation = self.markers[list_index].orientation

        dialog = dlg.CreateBrainTargetDialog(marker=position+orientation, brain_actor=self.brain_actor)
        if dialog.ShowModal() == wx.ID_OK:
            coil_position_list, coil_orientation_list, brain_position_list, brain_orientation_list = dialog.GetValue()

            position = list(coil_position_list[0])
            orientation = list(coil_orientation_list[0])
            marker = self.CreateMarker(
                position=position,
                orientation=orientation,
                # XXX: Setting the marker type to 'brain traget' is inconsistent with the variable names above ('coil_position_list' etc.);
                #   however, the dialog shown to the user by this function should be used exclusively for creating brain targets, hence the
                #   variable naming (and the internal logic of the dialog where it currently returns both coil targets and brain targets)
                #   should probably be modified to reflect that.
                marker_type=MarkerType.BRAIN_TARGET,
            )
            self.AddMarker(marker, render=True)

            for (position, orientation) in zip(brain_position_list, brain_orientation_list):
                marker = self.CreateMarker(
                    position=list(position),
                    orientation=list(orientation),
                    marker_type=MarkerType.BRAIN_TARGET,
                )
                self.AddMarker(marker, render=True)

        dialog.Destroy()

        self.SaveState()

    def OnMenuRemoveEfieldTarget(self,evt):
        idx = self.marker_list_ctrl.GetFocusedItem()

        marker = self.markers[idx]
        marker.is_target = False

        Publisher.sendMessage('Set target transparency', marker=marker, transparent=False)
        Publisher.sendMessage('Unset target', marker=marker)

        # Update the marker list control.
        self.marker_list_ctrl.SetItemBackgroundColour(idx, 'white')
        self.marker_list_ctrl.SetItem(idx, const.TARGET_COLUMN, "")

        self.efield_target_idx = None

    def OnMenuRemoveEfieldTargetatCortex(self,evt):
        idx = self.marker_list_ctrl.GetFocusedItem()

        marker = self.markers[idx]

        # TODO: Is this correct? Should it be "brain target"?
        marker.marker_type = MarkerType.LANDMARK

        self.marker_list_ctrl.SetItemBackgroundColour(idx, 'white')
        Publisher.sendMessage('Set target transparency', marker=marker, transparent=False)
        self.marker_list_ctrl.SetItem(idx, const.POINT_OF_INTEREST_TARGET_COLUMN, "")
        Publisher.sendMessage('Clear efield target at cortex')
        self.SaveState()

    def OnMenuUnsetTarget(self, evt):
        idx = self.marker_list_ctrl.GetFocusedItem()
        marker = self.markers[idx]
        marker.is_target = False

        Publisher.sendMessage('Set target transparency', marker=marker, transparent=False)
        Publisher.sendMessage('Unset target', marker=marker)

        # Update the marker list control.
        self.marker_list_ctrl.SetItemBackgroundColour(idx, 'white')
        self.marker_list_ctrl.SetItem(idx, const.TARGET_COLUMN, "")

        self.SaveState()

    def OnMenuSetColor(self, evt):
        index = self.marker_list_ctrl.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        current_color = [ch * 255 for ch in self.markers[index].colour]

        new_color = dlg.ShowColorDialog(color_current=current_color)

        if not new_color:
            return

        assert len(new_color) == 3

        marker = self.markers[index]

        # XXX: Seems like a slightly too early point for rounding; better to round only when the value
        #      is printed to the screen or file.
        #
        marker.colour = [round(s / 255.0, 3) for s in new_color]

        Publisher.sendMessage('Set new color', marker=marker, new_color=new_color)

        self.SaveState()

    def OnSetBrainTarget(self, evt):
        if isinstance(evt, int):
           self.marker_list_ctrl.Focus(evt)
        index = self.marker_list_ctrl.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        position = self.markers[index].position
        orientation = self.markers[index].orientation
        dialog = dlg.CreateBrainTargetDialog(mTMS=self.mTMS, marker=position+orientation, brain_target=True, brain_actor=self.brain_actor)

        if dialog.ShowModal() == wx.ID_OK:
            position_list, orientation_list = dialog.GetValueBrainTarget()
            for (position, orientation) in zip(position_list, orientation_list):
                marker = self.CreateMarker(
                    position=list(position),
                    orientation=list(orientation),
                    size=0.05,
                    marker_type=MarkerType.BRAIN_TARGET,
                )
                self.AddMarker(marker, render=True)
                
        dialog.Destroy()

        self.SaveState()

    def OnSendBrainTarget(self, evt):
        if isinstance(evt, int):
           self.marker_list_ctrl.Focus(evt)
        index = self.marker_list_ctrl.GetFocusedItem()
        if index == -1:
            wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return
        brain_target = self.markers[index].position + self.markers[index].orientation
        if self.__find_target_marker_idx():
            coil_pose = self.markers[self.__find_target_marker_idx()].position+self.markers[self.__find_target_marker_idx()].orientation
            if self.navigation.coil_at_target:
                self.mTMS.UpdateTarget(coil_pose, brain_target)
                #wx.CallAfter(Publisher.sendMessage, 'Send brain target to mTMS API', coil_pose=coil_pose, brain_target=brain_target)
                print("Send brain target to mTMS API")
            else:
                print("The coil is not at the target")
        else:
            print("Target not set")
    
    def OnSessionChanged(self, evt, ctrl):
        value = ctrl.GetValue()
        Publisher.sendMessage('Current session changed', new_session_id=value)
        
    def OnDeleteAllMarkers(self, evt=None):
        if evt is not None:
            result = dlg.ShowConfirmationDialog(msg=_("Delete all markers? Cannot be undone."))
            if result != wx.ID_OK:
                return

        idx = self.__find_target_marker_idx()
        if idx is not None:
            marker = self.markers[idx]
            Publisher.sendMessage('Unset target', marker=marker)

        Publisher.sendMessage('Delete markers', markers=self.markers)

        self.markers = []
        self.marker_list_ctrl.DeleteAllItems()

        self.SaveState()

    def OnDeleteMultipleMarkers(self, evt=None, label=None):
        # OnDeleteMultipleMarkers is used for both pubsub and button click events
        # Pubsub is used for fiducial handle and button click for all others

        if not evt:
            # Called through pubsub.

            indexes = []
            if label and (label in self.__list_fiducial_labels()):
                for id_n in range(self.marker_list_ctrl.GetItemCount()):
                    item = self.marker_list_ctrl.GetItem(id_n, const.LABEL_COLUMN)
                    if item.GetText() == label:
                        self.marker_list_ctrl.Focus(item.GetId())
                        indexes = [self.marker_list_ctrl.GetFocusedItem()]
        else:
            # Called using a button click.
            indexes = self.__get_selected_items()

        if not indexes:
            # Don't show the warning if called through pubsub
            if evt:
                wx.MessageBox(_("No data selected."), _("InVesalius 3"))
            return

        # If current target is removed, handle it as a special case.
        idx = self.__find_target_marker_idx()
        if idx in indexes:
            marker = self.markers[idx]
            Publisher.sendMessage('Unset target', marker=marker)

        self.__delete_multiple_markers(indexes)
        self.SaveState()

    def OnCreateMarker(self, evt=None, position=None, orientation=None, colour=None, size=None, label='*',
                       is_target=False, seed=None, session_id=None, marker_type=None, cortex_position_orientation=None):
        if self.nav_status and self.navigation.e_field_loaded:
            Publisher.sendMessage('Get Cortex position')

        # XXX: Set marker type to 'coil target' if created during navigation, otherwise 'landmark'. This enables creating
        #   coil targets during navigation. However, this logic shouldn't be inferred from the navigation status. Ideally,
        #   there would be two buttons for creating coil targets and landmarks, and the user would choose which one to create,
        #   or a similar explicit logic.
        #
        #   In addition, if marker_type is explicitly given as an argument (e.g., it is set to MarkerType.COIL or
        #   MarkerType.FIDUCIAL by the caller), do not automatically infer the marker type; only do it, if
        #   marker_type is None.
        if marker_type is None:
            marker_type = MarkerType.COIL_TARGET if self.nav_status else MarkerType.LANDMARK

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
        )
        self.AddMarker(marker, render=True)

        self.SaveState()

    def GetMarkersFromFile(self, filename, overwrite_image_fiducials):
        try:
            with open(filename, 'r') as file:
                magick_line = file.readline()
                assert magick_line.startswith(const.MARKER_FILE_MAGICK_STRING)
                version = int(magick_line.split('_')[-1])
                if version not in const.SUPPORTED_MARKER_FILE_VERSIONS:
                    wx.MessageBox(_("Unknown version of the markers file."), _("InVesalius 3"))
                    return

                file.readline() # skip the header line

                self.marker_list_ctrl.Hide()
                # Read the data lines and create markers
                for line in file.readlines():
                    marker = Marker(
                        version=version,
                    )
                    marker.from_csv_row(line)

                    # When loading markers from file, we first create a marker with is_target set to False, and then call __set_marker_as_target.
                    marker.is_target = False

                    # Note that we don't want to render the markers here for each loop iteration.
                    self.AddMarker(marker, render=False)

                    if overwrite_image_fiducials and marker.label in self.__list_fiducial_labels():
                        Publisher.sendMessage('Load image fiducials', label=marker.label, position=marker.position)

                    # Separately set the marker as target if needed.
                    if marker.is_target:
                        self.__set_marker_as_target(len(self.markers) - 1)

                    if marker.is_point_of_interest:
                        Publisher.sendMessage('Set as Efield target at cortex', position = marker.position, orientation = marker.orientation)

        except Exception as e:
            wx.MessageBox(_("Invalid markers file."), _("InVesalius 3"))
            utils.debug(e)

        self.marker_list_ctrl.Show()
        Publisher.sendMessage('Render volume viewer')
        self.SaveState()
        Publisher.sendMessage("Update UI for refine tab")

    def OnLoadMarkers(self, evt):
        """Loads markers from file and appends them to the current marker list.
        The file should contain no more than a single target marker. Also the
        file should not contain any fiducials already in the list."""

        last_directory = ses.Session().GetConfig('last_directory_3d_surface', '')
        dialog = dlg.FileSelectionDialog(_(u"Load markers"), last_directory, const.WILDCARD_MARKER_FILES)
        overwrite_checkbox = wx.CheckBox(dialog, -1, _("Overwrite current image fiducials"))
        dialog.sizer.Add(overwrite_checkbox, 0, wx.CENTER)
        dialog.FitSizers()
        if dialog.ShowModal() == wx.ID_OK:
            filename = dialog.GetPath()
            self.GetMarkersFromFile(filename, overwrite_checkbox.GetValue())

    def OnMarkersVisibility(self, evt, ctrl):
        if ctrl.GetValue():
            Publisher.sendMessage('Hide markers', markers=self.markers)
            ctrl.SetLabel('Show')
        else:
            Publisher.sendMessage('Show markers', markers=self.markers)
            ctrl.SetLabel('Hide')

    def OnSaveMarkers(self, evt):
        prj_data = prj.Project()
        timestamp = time.localtime(time.time())
        stamp_date = '{:0>4d}{:0>2d}{:0>2d}'.format(timestamp.tm_year, timestamp.tm_mon, timestamp.tm_mday)
        stamp_time = '{:0>2d}{:0>2d}{:0>2d}'.format(timestamp.tm_hour, timestamp.tm_min, timestamp.tm_sec)
        sep = '-'
        parts = [stamp_date, stamp_time, prj_data.name, 'markers']
        default_filename = sep.join(parts) + '.mkss'

        filename = dlg.ShowLoadSaveDialog(message=_(u"Save markers as..."),
                                          wildcard=const.WILDCARD_MARKER_FILES,
                                          style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                          default_filename=default_filename)

        if not filename:
            return

        version_line = '%s%i\n' % (const.MARKER_FILE_MAGICK_STRING, const.CURRENT_MARKER_FILE_VERSION)
        header_line = '%s\n' % Marker.to_csv_header()
        data_lines = [marker.to_csv_row() + '\n' for marker in self.markers]
        try:
            with open(filename, 'w', newline='') as file:
                file.writelines([version_line, header_line])
                file.writelines(data_lines)
                file.close()
        except:
            wx.MessageBox(_("Error writing markers file."), _("InVesalius 3"))  

    def OnSelectColour(self, evt, ctrl):
        # TODO: Make sure GetValue returns 3 numbers (without alpha)
        self.marker_colour = [colour / 255.0 for colour in ctrl.GetValue()][:3]

    def OnSelectSize(self, evt, ctrl):
        self.marker_size = ctrl.GetValue()

    def OnChangeCurrentSession(self, new_session_id):
        self.current_session = new_session_id

    def UpdateMarkerOrientation(self, marker_id=None):
        list_index = marker_id if marker_id else 0
        position = self.markers[list_index].position
        orientation = self.markers[list_index].orientation
        dialog = dlg.CreateBrainTargetDialog(mTMS=self.mTMS, marker=position+orientation)

        if dialog.ShowModal() == wx.ID_OK:
            orientation = dialog.GetValue()
            Publisher.sendMessage('Update target orientation',
                                  target_id=marker_id, orientation=list(orientation))
        dialog.Destroy()

    def AddPeeledSurface(self, flag, actor):
        self.brain_actor = actor

    def CreateMarker(self, position=None, orientation=None, colour=None, size=None, label='*', is_target=False, seed=None,
                     session_id=None, marker_type=MarkerType.LANDMARK, cortex_position_orientation=None):
        """
        Create a new marker object.
        """
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
        marker.cortex_position_orientation = cortex_position_orientation or self.cortex_position_orientation

        # Marker IDs start from zero, hence len(self.markers) will be the ID of the new marker.
        marker.marker_id = len(self.markers)

        if marker.marker_type == MarkerType.BRAIN_TARGET:
            marker.colour = [0, 0, 1]

        return marker

    def AddMarker(self, marker, render=True):
        """
        Given a marker object, add it to the list of markers and render the new marker.
        """
        if self.robot.IsConnected() and self.nav_status:
            current_head_robot_target_status = True
        else:
            current_head_robot_target_status = False

        Publisher.sendMessage('Add marker', marker=marker, render=render)
        self.markers.append(marker)

        # Add marker to the marker list in GUI.
        num_items = self.marker_list_ctrl.GetItemCount()

        list_entry = ["" for _ in range(0, const.TARGET_COLUMN)]
        list_entry[const.ID_COLUMN] = num_items
        list_entry[const.SESSION_COLUMN] = str(marker.session_id)
        list_entry[const.MARKER_TYPE_COLUMN] = marker.marker_type.human_readable
        list_entry[const.LABEL_COLUMN] = marker.label

        self.marker_list_ctrl.Append(list_entry)

        if marker.marker_type == MarkerType.BRAIN_TARGET:
            self.marker_list_ctrl.SetItemBackgroundColour(num_items, wx.Colour(102, 178, 255))

        if self.session.GetConfig('debug'):
            self.marker_list_ctrl.SetItem(num_items, const.X_COLUMN, str(round(marker.x, 1)))
            self.marker_list_ctrl.SetItem(num_items, const.Y_COLUMN, str(round(marker.y, 1)))
            self.marker_list_ctrl.SetItem(num_items, const.Z_COLUMN, str(round(marker.z, 1)))

        self.marker_list_ctrl.EnsureVisible(num_items)
