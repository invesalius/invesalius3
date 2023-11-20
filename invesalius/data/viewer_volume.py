# -*- coding: utf-8 -*-
import math
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

# from math import cos, sin
import os
import sys

import numpy as np
import wx
import queue
# TODO: Check that these imports are not used -- vtkLookupTable, vtkMinimalStandardRandomSequence, vtkPoints, vtkUnsignedCharArray
from vtkmodules.vtkCommonComputationalGeometry import vtkParametricTorus
from vtkmodules.vtkCommonCore import (
    vtkIdList,
    vtkMath,
    vtkLookupTable,
    vtkPoints,
    vtkUnsignedCharArray,
    vtkDoubleArray,
    mutable
)
from vtkmodules.vtkCommonColor import (
    vtkColorSeries,
    vtkNamedColors
)
from vtkmodules.vtkCommonDataModel import (
    vtkPolyData,
    vtkCellLocator,
)
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import (
    vtkPolyDataNormals,
    vtkCenterOfMass,
    vtkGlyph3D
)
from vtkmodules.vtkFiltersModeling import vtkBandedPolyDataContourFilter
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkFiltersHybrid import vtkRenderLargeImage
from vtkmodules.vtkFiltersSources import (
    vtkArrowSource,
    vtkDiskSource,
    vtkLineSource,
    vtkParametricFunctionSource,
    vtkSphereSource,
)
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkInteractionWidgets import (
    vtkImagePlaneWidget,
    vtkOrientationMarkerWidget,
)
from vtkmodules.vtkIOExport import (
    vtkIVExporter,
    vtkOBJExporter,
    vtkPOVExporter,
    vtkRIBExporter,
    vtkVRMLExporter,
    vtkX3DExporter,
)
from vtkmodules.vtkIOGeometry import vtkSTLReader
from vtkmodules.vtkIOImage import (
    vtkBMPWriter,
    vtkJPEGWriter,
    vtkPNGWriter,
    vtkPostScriptWriter,
    vtkTIFFWriter,
)
from vtkmodules.vtkRenderingAnnotation import vtkAnnotatedCubeActor, vtkAxesActor, vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPointPicker,
    vtkPolyDataMapper,
    vtkProperty,
    vtkPropPicker,
    vtkRenderer,
    vtkWindowToImageFilter,
)
from vtk import vtkCommand
from vtkmodules.vtkRenderingOpenGL2 import vtkCompositePolyDataMapper2
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

from invesalius.data.ruler_volume import GenericLeftRulerVolume
from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX
from invesalius.pubsub import pub as Publisher
import random
from scipy.spatial import distance

from imageio import imsave

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr
import invesalius.data.polydata_utils as pu
import invesalius.data.slice_ as sl
import invesalius.data.styles_3d as styles
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.project as prj
import invesalius.session as ses
import invesalius.style as st
import invesalius.utils as utils

from invesalius import inv_paths
from invesalius.math_utils import inner1d

if sys.platform == 'win32':
    try:
        import win32api
        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

PROP_MEASURE = 0.8

#  from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX, Polygon

class Viewer(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, size=wx.Size(320, 320))
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.interaction_style = st.StyleStateManager()

        self.initial_focus = None

        self.static_markers = []
        self.static_arrows = []
        self.static_markers_efield = []
        self.plot_vector = None
        self.style = None

        interactor = wxVTKRenderWindowInteractor(self, -1, size = self.GetSize())
        self.interactor = interactor
        self.interactor.SetRenderWhenDisabled(True)

        self.enable_style(const.STATE_DEFAULT)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(interactor, 1, wx.EXPAND)
        self.sizer = sizer
        self.SetSizer(sizer)
        self.Layout()

        # It would be more correct (API-wise) to call interactor.Initialize() and
        # interactor.Start() here, but Initialize() calls RenderWindow.Render().
        # That Render() call will get through before we can setup the
        # RenderWindow() to render via the wxWidgets-created context; this
        # causes flashing on some platforms and downright breaks things on
        # other platforms.  Instead, we call widget.Enable().  This means
        # that the RWI::Initialized ivar is not set, but in THIS SPECIFIC CASE,
        # that doesn't matter.
        interactor.Enable(1)

        ren = vtkRenderer()
        self.ren = ren

        canvas_renderer = vtkRenderer()
        canvas_renderer.SetLayer(1)
        canvas_renderer.SetInteractive(0)
        canvas_renderer.PreserveDepthBufferOn()
        self.canvas_renderer = canvas_renderer

        interactor.GetRenderWindow().SetNumberOfLayers(2)
        interactor.GetRenderWindow().AddRenderer(ren)
        interactor.GetRenderWindow().AddRenderer(canvas_renderer)

        self.raycasting_volume = False

        self.onclick = False

        self.text = vtku.TextZero()
        self.text.SetValue("")
        self.text.SetPosition(const.TEXT_POS_LEFT_UP)
        if sys.platform == 'darwin':
            font_size = const.TEXT_SIZE_LARGE * self.GetContentScaleFactor()
            self.text.SetSize(int(round(font_size, 0)))
        self.ren.AddActor(self.text.actor)

        #  self.polygon = Polygon(None, is_3d=False)

        # Enable canvas for ruler to be drawn
        self.canvas = CanvasRendererCTX(self, self.ren, self.canvas_renderer)
        self.prev_view_port_height = None
        # self.canvas.draw_list.append(self.text)
        # self.canvas.draw_list.append(self.polygon)
        # axes = vtkAxesActor()
        # axes.SetXAxisLabelText('x')
        # axes.SetYAxisLabelText('y')
        # axes.SetZAxisLabelText('z')
        # axes.SetTotalLength(50, 50, 50)
        #
        # self.ren.AddActor(axes)
        self.ruler = None

        self.slice_plane = None

        self.view_angle = None

        self.__bind_events()
        self.__bind_events_wx()

        self.mouse_pressed = 0
        self.on_wl = False

        self.picker = vtkPointPicker()
        interactor.SetPicker(self.picker)
        self.seed_points = []

        self.points_reference = []

        self.measure_picker = vtkPropPicker()
        #self.measure_picker.SetTolerance(0.005)
        self.measures = []

        self.repositioned_axial_plan = 0
        self.repositioned_sagital_plan = 0
        self.repositioned_coronal_plan = 0
        self.added_actor = 0

        self.camera_state = const.CAM_MODE
        self.camera_show_object = None

        self.nav_status = False

        self.ball_actor = None
        self.obj_actor = None
        self.obj_axes = None
        self.obj_name = False
        self.show_object = False
        self.obj_actor_list = None
        self.arrow_actor_list = None
        self.pTarget = [0., 0., 0.]

        # self.obj_axes = None
        self.x_actor = None
        self.y_actor = None
        self.z_actor = None
        self.mark_actor = None
        self.obj_projection_arrow_actor = None
        self.object_orientation_torus_actor = None
        self._mode_cross = False
        self._to_show_ball = 0
        self._ball_ref_visibility = False

        self.probe = False
        self.ref = False
        self.obj = False

        self.timer = False
        self.index = False

        self.target_coord = None
        self.aim_actor = None
        self.dummy_coil_actor = None
        self.dummy_robot_actor = None
        self.dummy_probe_actor = None
        self.dummy_ref_actor = None
        self.dummy_obj_actor = None
        self.target_mode = False
        self.polydata = None
        self.use_default_object = True
        self.anglethreshold = const.COIL_ANGLES_THRESHOLD
        self.distthreshold = const.COIL_COORD_THRESHOLD
        self.angle_arrow_projection_threshold = const.COIL_ANGLE_ARROW_PROJECTION_THRESHOLD

        self.actor_tracts = None
        self.actor_peel = None

        self.surface = None

        self.seed_offset = const.SEED_OFFSET
        self.radius_list = vtkIdList()
        self.colors_init = vtkUnsignedCharArray()
        self.plot_no_connection = False

        self.set_camera_position = True
        self.old_coord = np.zeros((6,),dtype=float)

        self.efield_mesh = None
        self.max_efield_vector = None
        self.ball_max_vector = None
        self.ball_GoGEfieldVector = None
        self.GoGEfieldVector = None
        self.vectorfield_actor =None
        self.efield_scalar_bar = None
        self.edge_actor= None
        #self.dummy_efield_coil_actor = None
        self.target_at_cortex = None


        self.LoadConfig()

    def UpdateCanvas(self):
        if self.canvas is not None:
            self.canvas.modified = True
            self.interactor.Render()

    def EnableRuler(self):
        self.ruler = GenericLeftRulerVolume(self)
        self.interactor.AddObserver(vtkCommand.AnyEvent, self.OnInteractorEvent)
        Publisher.sendMessage('Send ruler visibility status')

    def ShowRuler(self):
        if self.ruler and (self.ruler not in self.canvas.draw_list):
            self.canvas.draw_list.append(self.ruler)
            self.prev_view_port_height = round(self.ren.GetActiveCamera().GetParallelScale(), 4)
        self.UpdateCanvas()

    def HideRuler(self):
        if self.canvas and self.ruler and self.ruler in self.canvas.draw_list:
            self.canvas.draw_list.remove(self.ruler)
            self.prev_view_port_height = None
        self.UpdateCanvas()

    def OnRulerVisibilityStatus(self, status):
        if status and self.canvas and self.ruler:
            self.ShowRuler()

    def OnHideRuler(self):
        self.HideRuler()

    def OnShowRuler(self):
        self.ShowRuler()

    def OnInteractorEvent(self, sender, event):
        if self.canvas and self.ruler and self.ruler in self.canvas.draw_list:
            view_port_height = round(self.ren.GetActiveCamera().GetParallelScale(), 4)
            if view_port_height != self.prev_view_port_height:
                self.prev_view_port_height = view_port_height
                self.UpdateCanvas()

    def __bind_events(self):
        Publisher.subscribe(self.LoadActor,
                                 'Load surface actor into viewer')
        Publisher.subscribe(self.RemoveActor,
                                'Remove surface actor from viewer')
        # Publisher.subscribe(self.OnShowSurface, 'Show surface')
        Publisher.subscribe(self.UpdateRender,
                                 'Render volume viewer')
        Publisher.subscribe(self.ChangeBackgroundColour,
                        'Change volume viewer background colour')

        # Related to raycasting
        Publisher.subscribe(self.LoadVolume,
                                 'Load volume into viewer')
        Publisher.subscribe(self.UnloadVolume,
                                 'Unload volume')
        Publisher.subscribe(self.OnSetWindowLevelText,
                            'Set volume window and level text')
        Publisher.subscribe(self.OnHideRaycasting,
                                'Hide raycasting volume')
        Publisher.subscribe(self.OnShowRaycasting,
                                'Update raycasting preset')
        ###
        Publisher.subscribe(self.AppendActor,'AppendActor')
        Publisher.subscribe(self.SetWidgetInteractor,
                                'Set Widget Interactor')
        Publisher.subscribe(self.OnSetViewAngle,
                                'Set volume view angle')

        Publisher.subscribe(self.OnDisableBrightContrast,
                                 'Set interaction mode '+
                                  str(const.MODE_SLICE_EDITOR))

        Publisher.subscribe(self.OnExportSurface, 'Export surface to file')

        Publisher.subscribe(self.LoadSlicePlane, 'Load slice plane')

        Publisher.subscribe(self.ResetCamClippingRange, 'Reset cam clipping range')

        Publisher.subscribe(self.SetVolumeCameraState, 'Update volume camera state')

        Publisher.subscribe(self.enable_style, 'Enable style')
        Publisher.subscribe(self.OnDisableStyle, 'Disable style')

        Publisher.subscribe(self.OnHideText,
                                 'Hide text actors on viewers')

        Publisher.subscribe(self.AddActors, 'Add actors ' + str(const.SURFACE))
        Publisher.subscribe(self.RemoveActors, 'Remove actors ' + str(const.SURFACE))

        Publisher.subscribe(self.OnShowText,
                                 'Show text actors on viewers')
        Publisher.subscribe(self.OnShowRuler,
                            'Show rulers on viewers')
        Publisher.subscribe(self.OnHideRuler,
                            'Hide rulers on viewers')
        Publisher.subscribe(self.OnRulerVisibilityStatus, 'Receive ruler visibility status')
        Publisher.subscribe(self.OnCloseProject, 'Close project data')

        Publisher.subscribe(self.RemoveAllActor, 'Remove all volume actors')

        Publisher.subscribe(self.OnExportPicture,'Export picture to file')

        Publisher.subscribe(self.OnStartSeed,'Create surface by seeding - start')
        Publisher.subscribe(self.OnEndSeed,'Create surface by seeding - end')

        Publisher.subscribe(self.SetStereoMode, 'Set stereo mode')

        Publisher.subscribe(self.Reposition3DPlane, 'Reposition 3D Plane')

        Publisher.subscribe(self.RemoveVolume, 'Remove Volume')

        Publisher.subscribe(self.UpdateCameraBallPosition, 'Set cross focal point')

        Publisher.subscribe(self.OnSensors, 'Sensors ID')
        Publisher.subscribe(self.OnRemoveSensorsID, 'Remove sensors ID')

        # Related to marker creation in navigation tools
        Publisher.subscribe(self.AddMarker, 'Add marker')
        Publisher.subscribe(self.HideAllMarkers, 'Hide all markers')
        Publisher.subscribe(self.ShowAllMarkers, 'Show all markers')
        Publisher.subscribe(self.RemoveAllMarkers, 'Remove all markers')
        Publisher.subscribe(self.RemoveMultipleMarkers, 'Remove multiple markers')
        Publisher.subscribe(self.BlinkMarker, 'Blink Marker')
        Publisher.subscribe(self.StopBlinkMarker, 'Stop Blink Marker')
        Publisher.subscribe(self.SetNewColor, 'Set new color')
        Publisher.subscribe(self.SetMarkers, 'Set markers')

        # Related to UI state
        Publisher.subscribe(self.ShowObject, 'Show-coil checked')

        # Related to object tracking during neuronavigation
        Publisher.subscribe(self.OnNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateObjectOrientation, 'Update object matrix')
        Publisher.subscribe(self.UpdateObjectArrowOrientation, 'Update object arrow matrix')
        Publisher.subscribe(self.UpdateEfieldPointLocation, 'Update point location for e-field calculation')
        Publisher.subscribe(self.GetEnorm, 'Get enorm')
        Publisher.subscribe(self.ConfigureObject, 'Configure object')
        Publisher.subscribe(self.TrackObject, 'Track object')

        Publisher.subscribe(self.ActivateTargetMode, 'Target navigation mode')
        Publisher.subscribe(self.OnUpdateObjectTargetGuide, 'Update object matrix')
        Publisher.subscribe(self.OnUpdateTargetCoordinates, 'Update target')
        Publisher.subscribe(self.OnDisableOrEnableCoilTracker, 'Disable or enable coil tracker')
        Publisher.subscribe(self.OnTargetMarkerTransparency, 'Set target transparency')
        Publisher.subscribe(self.OnUpdateAngleThreshold, 'Update angle threshold')
        Publisher.subscribe(self.OnUpdateDistThreshold, 'Update dist threshold')
        Publisher.subscribe(self.OnUpdateTracts, 'Update tracts')
        Publisher.subscribe(self.OnUpdateEfieldvis, 'Update efield vis')
        Publisher.subscribe(self.InitializeColorArray, 'Initialize color array')
        Publisher.subscribe(self.OnRemoveTracts, 'Remove tracts')
        Publisher.subscribe(self.UpdateSeedOffset, 'Update seed offset')
        Publisher.subscribe(self.UpdateMarkerOffsetState, 'Update marker offset state')
        Publisher.subscribe(self.AddPeeledSurface, 'Update peel')
        Publisher.subscribe(self.InitEfield, 'Initialize E-field brain')
        Publisher.subscribe(self.GetPeelCenters, 'Get peel centers and normals')
        Publisher.subscribe(self.InitLocatorViewer, 'Get init locator')
        Publisher.subscribe(self.GetPeelCenters, 'Get peel centers and normals')
        Publisher.subscribe(self.InitLocatorViewer, 'Get init locator')
        Publisher.subscribe(self.load_mask_preview, 'Load mask preview')
        Publisher.subscribe(self.remove_mask_preview, 'Remove mask preview')
        Publisher.subscribe(self.GetEfieldActor, 'Send Actor')
        Publisher.subscribe(self.ReturnToDefaultColorActor, 'Recolor again')
        Publisher.subscribe(self.SaveEfieldData, 'Save Efield data')
        Publisher.subscribe(self.SavedAllEfieldData, 'Save all Efield data')
        Publisher.subscribe(self.SaveEfieldTargetData, 'Save target data')
        Publisher.subscribe(self.GetTargetSavedEfieldData, 'Get target index efield')
        Publisher.subscribe(self.CheckStatusSavedEfieldData, 'Check efield data')
        Publisher.subscribe(self.GetNeuronavigationApi, 'Get Neuronavigation Api')
        Publisher.subscribe(self.UpdateEfieldPointLocationOffline,'Update interseccion offline')
        Publisher.subscribe(self.MaxEfieldActor, 'Show max Efield actor')
        Publisher.subscribe(self.CoGEfieldActor, 'Show CoG Efield actor')
        Publisher.subscribe(self.CalculateDistanceMaxEfieldCoGE, 'Show distance between Max and CoG Efield')
        Publisher.subscribe(self.EfieldVectors, 'Show Efield vectors')
        Publisher.subscribe(self.RecolorEfieldActor, 'Recolor efield actor')
        Publisher.subscribe(self.GetScalpEfield, 'Send scalp index')
        # Related to robot tracking during neuronavigation
        Publisher.subscribe(self.ActivateRobotMode, 'Robot navigation mode')
        Publisher.subscribe(self.OnUpdateRobotStatus, 'Update robot status')
        Publisher.subscribe(self.GetCoilPosition, 'Calculate position and rotation')
        Publisher.subscribe(self.CreateCortexProjectionOnScalp, 'Send efield target position on brain')
        Publisher.subscribe(self.UpdateEfieldThreshold, 'Update Efield Threshold')
        Publisher.subscribe(self.UpdateEfieldROISize, 'Update Efield ROI size')

    def SaveConfig(self):
        object_path = self.obj_name.decode(const.FS_ENCODE) if self.obj_name is not None else None
        use_default_object = self.use_default_object

        state = {
            'object_path': object_path,
            'use_default_object': use_default_object,
        }

        session = ses.Session()
        session.SetConfig('viewer', state)

    def LoadConfig(self):
        session = ses.Session()
        state = session.GetConfig('viewer')

        if state is None:
            return

        object_path = state['object_path']
        use_default_object = state['use_default_object']

        self.obj_name = object_path.encode(const.FS_ENCODE) if object_path is not None else None
        self.use_default_object = use_default_object
        # Automatically enable and check 'Track object' checkbox and uncheck 'Disable Volume Camera' checkbox.
        Publisher.sendMessage('Enable track-object checkbox', enabled=True)
        Publisher.sendMessage('Check track-object checkbox', checked=True)
        Publisher.sendMessage('Check volume camera checkbox', checked=False)

        Publisher.sendMessage('Disable target mode')
        self.polydata = pu.LoadPolydata(path=object_path) if object_path is not None else None

    def get_vtk_mouse_position(self):
        """
        Get Mouse position inside a wxVTKRenderWindowInteractorself. Return a
        tuple with X and Y position.
        Please use this instead of using iren.GetEventPosition because it's
        not returning the correct values on Mac with HighDPI display, maybe
        the same is happing with Windows and Linux, we need to test.
        """
        mposx, mposy = wx.GetMousePosition()
        cposx, cposy = self.interactor.ScreenToClient((mposx, mposy))
        mx, my = cposx, self.interactor.GetSize()[1] - cposy
        if sys.platform == 'darwin':
            # It's needed to mutiple by scale factor in HighDPI because of
            # https://docs.wxpython.org/wx.glcanvas.GLCanvas.html
            # For now we are doing this only on Mac but it may be needed on
            # Windows and Linux too.
            scale = self.interactor.GetContentScaleFactor()
            mx *= scale
            my *= scale
        return int(mx), int(my)

    def SetStereoMode(self, mode):
        ren_win = self.interactor.GetRenderWindow()

        if mode == const.STEREO_OFF:
            ren_win.StereoRenderOff()
        else:

            if mode == const.STEREO_RED_BLUE:
                ren_win.SetStereoTypeToRedBlue()
            elif mode == const.STEREO_CRISTAL:
                ren_win.SetStereoTypeToCrystalEyes()
            elif mode == const.STEREO_INTERLACED:
                ren_win.SetStereoTypeToInterlaced()
            elif mode == const.STEREO_LEFT:
                ren_win.SetStereoTypeToLeft()
            elif mode == const.STEREO_RIGHT:
                ren_win.SetStereoTypeToRight()
            elif mode == const.STEREO_DRESDEN:
                ren_win.SetStereoTypeToDresden()
            elif mode == const.STEREO_CHECKBOARD:
                ren_win.SetStereoTypeToCheckerboard()
            elif mode == const.STEREO_ANAGLYPH:
                ren_win.SetStereoTypeToAnaglyph()

            ren_win.StereoRenderOn()

        self.UpdateRender()

    def check_ball_reference(self):
        self._mode_cross = True
        # self._check_and_set_ball_visibility()
        #if not self.actor_peel:
        self._ball_ref_visibility = True
        #else:
        #    self._ball_ref_visibility = False
        # if self._to_show_ball:
        if not self.ball_actor: #and not self.actor_peel:
            self.CreateBallReference()
            #self.ball_actor.SetVisibility(1)
        #else:
         #   self.ball_actor.SetVisibility(0)
        self.UpdateRender()

    def uncheck_ball_reference(self):
        self._mode_cross = False
        # self.RemoveBallReference()
        self._ball_ref_visibility = True
        if self.ball_actor:
            self.ren.RemoveActor(self.ball_actor)
            self.ball_actor = None

        self.UpdateRender()
    
    
    def OnSensors(self, markers_flag):
        probe_id, ref_id, obj_id = markers_flag

        if not self.probe:
            self.probe = True
            self.CreateSensorID()

        green_color = const.GREEN_COLOR_FLOAT
        red_color = const.RED_COLOR_FLOAT

        if probe_id:
            colour1 = green_color
        else:
            colour1 = red_color
        if ref_id:
            colour2 = green_color
        else:
            colour2 = red_color
        if obj_id:
            colour3 = green_color
        else:
            colour3 = red_color

        self.dummy_probe_actor.GetProperty().SetColor(colour1)
        self.dummy_ref_actor.GetProperty().SetColor(colour2)
        self.dummy_obj_actor.GetProperty().SetColor(colour3)

    def CreateSensorID(self):
        self.ren_probe = vtkRenderer()
        self.ren_probe.SetLayer(1)

        self.interactor.GetRenderWindow().AddRenderer(self.ren_probe)
        self.ren_probe.SetViewport(0.01, 0.79, 0.15, 0.97)
        filename = os.path.join(inv_paths.OBJ_DIR, "stylus.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())
        mapper.SetScalarVisibility(0)

        dummy_probe_actor = vtkActor()
        dummy_probe_actor.SetMapper(mapper)
        dummy_probe_actor.GetProperty().SetColor(1, 1, 1)
        dummy_probe_actor.GetProperty().SetOpacity(1.)
        self.dummy_probe_actor = dummy_probe_actor

        self.ren_probe.AddActor(dummy_probe_actor)
        self.ren_probe.InteractiveOff()

        self.ren_ref = vtkRenderer()
        self.ren_ref.SetLayer(1)

        self.interactor.GetRenderWindow().AddRenderer(self.ren_ref)
        self.ren_ref.SetViewport(0.01, 0.57, 0.15, 0.79)
        filename = os.path.join(inv_paths.OBJ_DIR, "head.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())
        mapper.SetScalarVisibility(0)

        dummy_ref_actor = vtkActor()
        dummy_ref_actor.SetMapper(mapper)
        dummy_ref_actor.GetProperty().SetColor(1, 1, 1)
        dummy_ref_actor.GetProperty().SetOpacity(1.)
        self.dummy_ref_actor = dummy_ref_actor

        self.ren_ref.AddActor(dummy_ref_actor)
        self.ren_ref.InteractiveOff()

        self.ren_obj = vtkRenderer()
        self.ren_obj.SetLayer(1)

        self.interactor.GetRenderWindow().AddRenderer(self.ren_obj)
        self.ren_obj.SetViewport(0.01, 0.40, 0.15, 0.57)
        filename = os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil_no_handle.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())
        mapper.SetScalarVisibility(0)

        dummy_obj_actor = vtkActor()
        dummy_obj_actor.SetMapper(mapper)
        dummy_obj_actor.GetProperty().SetColor(1, 1, 1)
        dummy_obj_actor.GetProperty().SetOpacity(1.)
        self.dummy_obj_actor = dummy_obj_actor

        self.ren_obj.AddActor(dummy_obj_actor)
        self.ren_obj.InteractiveOff()

    def OnRemoveSensorsID(self):
        if self.probe:
            self.ren_probe.RemoveActor(self.dummy_probe_actor)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren_probe)
            self.ren_ref.RemoveActor(self.dummy_ref_actor)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren_ref)
            self.ren_obj.RemoveActor(self.dummy_obj_actor)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren_obj)
            self.probe = self.ref = self.obj = False
            self.UpdateRender()

    # def OnShowSurface(self, index, visibility):
    #     if visibility:
    #         self._to_show_ball += 1
    #     else:
    #         self._to_show_ball -= 1
    #     self._check_and_set_ball_visibility()

    def OnStartSeed(self):
        self.seed_points = []

    def OnEndSeed(self):
        Publisher.sendMessage("Create surface from seeds",
                              seeds=self.seed_points)

    def OnExportPicture(self, orientation, filename, filetype):
        if orientation == const.VOLUME:
            Publisher.sendMessage('Begin busy cursor')
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)
                self._export_picture(orientation, win_filename, filetype)
            else:
                self._export_picture(orientation, filename, filetype)
            Publisher.sendMessage('End busy cursor')

    def _export_picture(self, id, filename, filetype):
            if filetype == const.FILETYPE_POV:
                renwin = self.interactor.GetRenderWindow()
                image = vtkWindowToImageFilter()
                image.SetInput(renwin)
                writer = vtkPOVExporter()
                writer.SetFileName(filename.encode(const.FS_ENCODE))
                writer.SetRenderWindow(renwin)
                writer.Write()
            else:
                #Use tiling to generate a large rendering.
                image = vtkRenderLargeImage()
                image.SetInput(self.ren)
                image.SetMagnification(1)
                image.Update()

                image = image.GetOutput()

                # write image file
                if (filetype == const.FILETYPE_BMP):
                    writer = vtkBMPWriter()
                elif (filetype == const.FILETYPE_JPG):
                    writer =  vtkJPEGWriter()
                elif (filetype == const.FILETYPE_PNG):
                    writer = vtkPNGWriter()
                elif (filetype == const.FILETYPE_PS):
                    writer = vtkPostScriptWriter()
                elif (filetype == const.FILETYPE_TIF):
                    writer = vtkTIFFWriter()
                    filename = u"%s.tif"%filename.strip(".tif")

                writer.SetInputData(image)
                writer.SetFileName(filename.encode(const.FS_ENCODE))
                writer.Write()

            if not os.path.exists(filename):
                wx.MessageBox(_("InVesalius was not able to export this picture"), _("Export picture error"))


    def OnCloseProject(self):
        if self.raycasting_volume:
            self.raycasting_volume = False

        if  self.slice_plane:
            self.slice_plane.Disable()
            self.slice_plane.DeletePlanes()
            del self.slice_plane
            Publisher.sendMessage('Uncheck image plane menu')
            self.mouse_pressed = 0
            self.on_wl = False
            self.slice_plane = 0

        self.interaction_style.Reset()
        self.SetInteractorStyle(const.STATE_DEFAULT)

    def OnHideText(self):
        self.text.Hide()
        self.UpdateRender()

    def OnShowText(self):
        if self.on_wl:
            self.text.Show()
            self.UpdateRender()

    def AddActors(self, actors):
        "Inserting actors"
        for actor in actors:
            self.ren.AddActor(actor)

    def RemoveVolume(self):
        volumes = self.ren.GetVolumes()
        if (volumes.GetNumberOfItems()):
            self.ren.RemoveVolume(volumes.GetLastProp())
            if not self.nav_status:
                self.UpdateRender()
            # self._to_show_ball -= 1
            # self._check_and_set_ball_visibility()

    def RemoveActors(self, actors):
        "Remove a list of actors"
        for actor in actors:
            self.ren.RemoveActor(actor)

    def AddPointReference(self, position, radius=1, colour=(1, 0, 0)):
        """
        Add a point representation in the given x,y,z position with a optional
        radius and colour.
        """
        point = vtkSphereSource()
        point.SetCenter(position)
        point.SetRadius(radius)

        mapper = vtkPolyDataMapper()
        mapper.SetInput(point.GetOutput())

        p = vtkProperty()
        p.SetColor(colour)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(p)
        actor.PickableOff()

        self.ren.AddActor(actor)
        self.points_reference.append(actor)

    def RemoveAllPointsReference(self):
        for actor in self.points_reference:
            self.ren.RemoveActor(actor)
        self.points_reference = []

    def RemovePointReference(self, point):
        """
        Remove the point reference. The point argument is the position that is
        added.
        """
        actor = self.points_reference.pop(point)
        self.ren.RemoveActor(actor)

    def SetMarkers(self, markers):
        """
        Set all markers, overwriting the previous markers.
        """
        self.RemoveAllMarkers(len(self.static_markers))

        target_selected = False
        for marker in markers:

            ball_id = marker["ball_id"]
            size = marker["size"]
            colour = marker["colour"]
            position = marker["position"]
            orientation = marker["orientation"]
            target = marker["target"]
            arrow_flag = marker["arrow_flag"]

            self.AddMarker(
                marker_id=ball_id,
                size=size,
                colour=colour,
                position=position,
                orientation=orientation,
                arrow_flag=arrow_flag,
            )

            if target:
                Publisher.sendMessage('Update target', coord=position + orientation)
                target_selected = True

        if not target_selected:
            self.RemoveTarget()

        self.UpdateRender()

    def AddMarker(self, marker_id, size, colour, position, orientation, arrow_flag):
        """
        Markers created by navigation tools and rendered in volume viewer.
        """
        self.marker_id = marker_id
        position_flip = list(position)
        position_flip[1] = -position_flip[1]

        if arrow_flag:
            """
            Markers arrow with orientation created by navigation tools and rendered in volume viewer.
            """
            marker_actor = self.CreateActorArrow(position_flip, orientation, colour, const.ARROW_MARKER_SIZE)
            if self.efield_mesh is not None and self.nav_status is True:
                vtk_colors = vtkNamedColors()
                marker_actor_brain =  self.DrawVectors(self.efield_mesh.GetPoint(self.Idmax), [self.max_efield_array[0], self.max_efield_array[1], self.max_efield_array[2]],vtk_colors.GetColor3d('Orange'), scale_factor=3)
                Publisher.sendMessage('Save target data', target_list_index=marker_id, position=self.efield_mesh.GetPoint(self.Idmax),
                                      orientation=[self.max_efield_array[0], self.max_efield_array[1], self.max_efield_array[2]], plot_efield_vectors=self.plot_vector)

                self.static_markers_efield.append(marker_actor_brain)
                self.ren.AddActor(marker_actor_brain)

        else:
            marker_actor = self.CreateActorBall(position_flip, colour, size)

        # adding a new actor for the marker
        self.static_markers.append(marker_actor)

        self.ren.AddActor(self.static_markers[self.marker_id])
        self.marker_id += 1
        if not self.nav_status:
            self.UpdateRender()

    def add_marker(self, coord, color):
        """Simplified version for creating a spherical marker in the 3D scene

        :param coord:
        :param color:
        :return: vtkActor
        """

        ball_ref = vtkSphereSource()
        ball_ref.SetRadius(1.5)
        ball_ref.SetCenter(coord)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtkProperty()
        prop.SetColor(color)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(prop)
        actor.PickableOff()
        actor.GetProperty().SetOpacity(1.)
        return actor

    def HideAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            self.static_markers[i].SetVisibility(0)
        if not self.nav_status:
            self.UpdateRender()

    def ShowAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            self.static_markers[i].SetVisibility(1)
        if not self.nav_status:
            self.UpdateRender()

    def RemoveAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            self.ren.RemoveActor(self.static_markers[i])
        self.static_markers = []
        if not self.nav_status:
            self.UpdateRender()

    def RemoveMultipleMarkers(self, indexes):
        for i in reversed(indexes):
            self.ren.RemoveActor(self.static_markers[i])
            del self.static_markers[i]
            self.marker_id = self.marker_id - 1
        if not self.nav_status:
            self.UpdateRender()

    def BlinkMarker(self, index):
        if self.timer:
            self.timer.Stop()
            self.static_markers[self.index].SetVisibility(1)
        self.index = index
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnBlinkMarker, self.timer)
        self.timer.Start(500)
        self.timer_count = 0

    def OnBlinkMarker(self, evt):
        self.static_markers[self.index].SetVisibility(int(self.timer_count % 2))
        if not self.nav_status:
            self.UpdateRender()
        self.timer_count += 1

    def StopBlinkMarker(self, index=None):
        if self.timer:
            self.timer.Stop()
            if index is None:
                self.static_markers[self.index].SetVisibility(1)
                if not self.nav_status:
                    self.UpdateRender()
            self.index = False

    def SetNewColor(self, index, color):
        self.static_markers[index].GetProperty().SetColor([round(s / 255.0, 3) for s in color])
        if not self.nav_status:
            self.UpdateRender()

    def OnTargetMarkerTransparency(self, status, index):
        if status:
            self.static_markers[index].GetProperty().SetOpacity(1)
            # self.staticballs[index].GetProperty().SetOpacity(0.4)
        else:
            self.static_markers[index].GetProperty().SetOpacity(1)

    def OnUpdateAngleThreshold(self, angle):
        self.anglethreshold = angle

    def OnUpdateDistThreshold(self, dist_threshold):
        self.distthreshold = dist_threshold

    def ActivateTargetMode(self, evt=None, target_mode=None):

        vtk_colors = vtkNamedColors()
        self.target_mode = target_mode
        if self.target_coord and self.target_mode:
            if self.actor_peel:
                self.object_orientation_torus_actor.SetVisibility(0)
                self.obj_projection_arrow_actor.SetVisibility(0)
            self.CreateTargetAim()

            # Create a line
            self.ren.SetViewport(0, 0, 0.75, 1)
            self.ren2 = vtkRenderer()

            self.interactor.GetRenderWindow().AddRenderer(self.ren2)
            self.ren2.SetViewport(0.75, 0, 1, 1)
            self.CreateTextDistance()

            obj_polydata = vtku.CreateObjectPolyData(self.obj_name)

            normals = vtkPolyDataNormals()
            normals.SetInputData(obj_polydata)
            normals.SetFeatureAngle(80)
            normals.AutoOrientNormalsOn()
            normals.Update()

            mapper = vtkPolyDataMapper()
            mapper.SetInputData(normals.GetOutput())
            mapper.ScalarVisibilityOff()
            #mapper.ImmediateModeRenderingOn()  # improve performance

            obj_roll = vtkActor()
            obj_roll.SetMapper(mapper)
            obj_roll.GetProperty().SetColor(1, 1, 1)
            # obj_roll.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
            # obj_roll.GetProperty().SetSpecular(30)
            # obj_roll.GetProperty().SetSpecularPower(80)
            obj_roll.SetPosition(0, 25, -30)
            obj_roll.RotateX(-60)
            obj_roll.RotateZ(180)

            obj_yaw = vtkActor()
            obj_yaw.SetMapper(mapper)
            obj_yaw.GetProperty().SetColor(1, 1, 1)
            # obj_yaw.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
            # obj_yaw.GetProperty().SetSpecular(30)
            # obj_yaw.GetProperty().SetSpecularPower(80)
            obj_yaw.SetPosition(0, -115, 5)
            obj_yaw.RotateZ(180)

            obj_pitch = vtkActor()
            obj_pitch.SetMapper(mapper)
            obj_pitch.GetProperty().SetColor(1, 1, 1)
            # obj_pitch.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
            # obj_pitch.GetProperty().SetSpecular(30)
            # obj_pitch.GetProperty().SetSpecularPower(80)
            obj_pitch.SetPosition(5, -265, 5)
            obj_pitch.RotateY(90)
            obj_pitch.RotateZ(180)

            arrow_roll_z1 = self.CreateArrowActor([-50, -35, 12], [-50, -35, 50])
            arrow_roll_z1.GetProperty().SetColor(1, 1, 0)
            arrow_roll_z1.RotateX(-60)
            arrow_roll_z1.RotateZ(180)
            arrow_roll_z2 = self.CreateArrowActor([50, -35, 0], [50, -35, -50])
            arrow_roll_z2.GetProperty().SetColor(1, 1, 0)
            arrow_roll_z2.RotateX(-60)
            arrow_roll_z2.RotateZ(180)

            arrow_yaw_y1 = self.CreateArrowActor([-50, -35, 0], [-50, 5, 0])
            arrow_yaw_y1.GetProperty().SetColor(0, 1, 0)
            arrow_yaw_y1.SetPosition(0, -150, 0)
            arrow_yaw_y1.RotateZ(180)
            arrow_yaw_y2 = self.CreateArrowActor([50, -35, 0], [50, -75, 0])
            arrow_yaw_y2.GetProperty().SetColor(0, 1, 0)
            arrow_yaw_y2.SetPosition(0, -150, 0)
            arrow_yaw_y2.RotateZ(180)

            arrow_pitch_x1 = self.CreateArrowActor([0, 65, 38], [0, 65, 68])
            arrow_pitch_x1.GetProperty().SetColor(1, 0, 0)
            arrow_pitch_x1.SetPosition(0, -300, 0)
            arrow_pitch_x1.RotateY(90)
            arrow_pitch_x1.RotateZ(180)
            arrow_pitch_x2 = self.CreateArrowActor([0, -55, 5], [0, -55, -30])
            arrow_pitch_x2.GetProperty().SetColor(1, 0, 0)
            arrow_pitch_x2.SetPosition(0, -300, 0)
            arrow_pitch_x2.RotateY(90)
            arrow_pitch_x2.RotateZ(180)

            self.obj_actor_list = obj_roll, obj_yaw, obj_pitch
            self.arrow_actor_list = arrow_roll_z1, arrow_roll_z2, arrow_yaw_y1, arrow_yaw_y2,\
                                     arrow_pitch_x1, arrow_pitch_x2

            for ind in self.obj_actor_list:
                self.ren2.AddActor(ind)

            for ind in self.arrow_actor_list:
                self.ren2.AddActor(ind)

            self.ren.ResetCamera()
            self.SetCameraTarget()
            #self.ren.GetActiveCamera().Zoom(4)

            self.ren2.ResetCamera()
            self.ren2.GetActiveCamera().Zoom(2)
            self.ren2.InteractiveOff()
            if not self.nav_status:
                self.UpdateRender()

        else:
            self.DisableCoilTracker()
            self.camera_show_object = None
            if self.actor_peel:
                if self.object_orientation_torus_actor:
                    self.object_orientation_torus_actor.SetVisibility(1)
                if self.obj_projection_arrow_actor:
                    self.obj_projection_arrow_actor.SetVisibility(1)

    def OnUpdateObjectTargetGuide(self, m_img, coord):
        vtk_colors = vtkNamedColors()

        if self.target_coord and self.target_mode:

            target_dist = distance.euclidean(coord[0:3],
                                             (self.target_coord[0], -self.target_coord[1], self.target_coord[2]))

            # self.txt.SetCoilDistanceValue(target_dist)
            self.tdist.SetValue('Distance: ' + str("{:06.2f}".format(target_dist)) + ' mm')
            self.ren.ResetCamera()
            self.SetCameraTarget()
            if target_dist > 100:
                target_dist = 100
            # ((-0.0404*dst) + 5.0404) is the linear equation to normalize the zoom between 1 and 5 times with
            # the distance between 1 and 100 mm
            self.ren.GetActiveCamera().Zoom((-0.0404 * target_dist) + 5.0404)

            if target_dist <= self.distthreshold:
                thrdist = True
                self.aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                if not self.show_object:
                    self.aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_HIDDEN_OPACITY)
            else:
                thrdist = False
                self.aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Yellow'))
                self.aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)

            m_img_flip = m_img.copy()
            m_img_flip[1, -1] = -m_img_flip[1, -1]
            distance_to_target_robot = dcr.ComputeRelativeDistanceToTarget(target_coord=self.target_coord, m_img=m_img_flip)
            wx.CallAfter(Publisher.sendMessage, 'Distance to the target', distance=distance_to_target_robot)
            distance_to_target = distance_to_target_robot.copy()
            if distance_to_target[3] > const.ARROW_UPPER_LIMIT:
                distance_to_target[3] = const.ARROW_UPPER_LIMIT
            elif distance_to_target[3] < -const.ARROW_UPPER_LIMIT:
                distance_to_target[3] = -const.ARROW_UPPER_LIMIT
            coordrx_arrow = const.ARROW_SCALE * distance_to_target[3]

            if distance_to_target[4] > const.ARROW_UPPER_LIMIT:
                distance_to_target[4] = const.ARROW_UPPER_LIMIT
            elif distance_to_target[4] < -const.ARROW_UPPER_LIMIT:
                distance_to_target[4] = -const.ARROW_UPPER_LIMIT
            coordry_arrow = const.ARROW_SCALE * distance_to_target[4]

            if distance_to_target[5] > const.ARROW_UPPER_LIMIT:
                distance_to_target[5] = const.ARROW_UPPER_LIMIT
            elif distance_to_target[5] < -const.ARROW_UPPER_LIMIT:
                distance_to_target[5] = -const.ARROW_UPPER_LIMIT
            coordrz_arrow = const.ARROW_SCALE * distance_to_target[5]

            for ind in self.arrow_actor_list:
                self.ren2.RemoveActor(ind)

            if self.anglethreshold * const.ARROW_SCALE > coordrx_arrow > -self.anglethreshold * const.ARROW_SCALE:
                thrcoordx = True
                # self.obj_actor_list[0].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.obj_actor_list[0].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordx = False
                # self.obj_actor_list[0].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
                self.obj_actor_list[0].GetProperty().SetColor(1, 1, 1)

            offset = 5

            arrow_roll_x1 = self.CreateArrowActor([-55, -35, offset], [-55, -35, offset - coordrx_arrow])
            arrow_roll_x1.RotateX(-60)
            arrow_roll_x1.RotateZ(180)
            arrow_roll_x1.GetProperty().SetColor(1, 1, 0)

            arrow_roll_x2 = self.CreateArrowActor([55, -35, offset], [55, -35, offset + coordrx_arrow])
            arrow_roll_x2.RotateX(-60)
            arrow_roll_x2.RotateZ(180)
            arrow_roll_x2.GetProperty().SetColor(1, 1, 0)

            if self.anglethreshold * const.ARROW_SCALE > coordrz_arrow > -self.anglethreshold * const.ARROW_SCALE:
                thrcoordz = True
                # self.obj_actor_list[1].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.obj_actor_list[1].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordz = False
                # self.obj_actor_list[1].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
                self.obj_actor_list[1].GetProperty().SetColor(1, 1, 1)

            offset = -35

            arrow_yaw_z1 = self.CreateArrowActor([-55, offset, 0], [-55, offset - coordrz_arrow, 0])
            arrow_yaw_z1.SetPosition(0, -150, 0)
            arrow_yaw_z1.RotateZ(180)
            arrow_yaw_z1.GetProperty().SetColor(0, 1, 0)

            arrow_yaw_z2 = self.CreateArrowActor([55, offset, 0], [55, offset + coordrz_arrow, 0])
            arrow_yaw_z2.SetPosition(0, -150, 0)
            arrow_yaw_z2.RotateZ(180)
            arrow_yaw_z2.GetProperty().SetColor(0, 1, 0)

            if self.anglethreshold * const.ARROW_SCALE > coordry_arrow > -self.anglethreshold * const.ARROW_SCALE:
                thrcoordy = True
                #self.obj_actor_list[2].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.obj_actor_list[2].GetProperty().SetColor(0, 1, 0)
            else:
                thrcoordy = False
                #self.obj_actor_list[2].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
                self.obj_actor_list[2].GetProperty().SetColor(1, 1, 1)

            offset = 38
            arrow_pitch_y1 = self.CreateArrowActor([0, 65, offset], [0, 65, offset + coordry_arrow])
            arrow_pitch_y1.SetPosition(0, -300, 0)
            arrow_pitch_y1.RotateY(90)
            arrow_pitch_y1.RotateZ(180)
            arrow_pitch_y1.GetProperty().SetColor(1, 0, 0)

            offset = 5
            arrow_pitch_y2 = self.CreateArrowActor([0, -55, offset], [0, -55, offset - coordry_arrow])
            arrow_pitch_y2.SetPosition(0, -300, 0)
            arrow_pitch_y2.RotateY(90)
            arrow_pitch_y2.RotateZ(180)
            arrow_pitch_y2.GetProperty().SetColor(1, 0, 0)

            if thrdist and thrcoordx and thrcoordy and thrcoordz:
                self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                wx.CallAfter(Publisher.sendMessage, 'Coil at target', state=True)
            else:
                self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkOrange'))
                wx.CallAfter(Publisher.sendMessage, 'Coil at target', state=False)

            self.arrow_actor_list = arrow_roll_x1, arrow_roll_x2, arrow_yaw_z1, arrow_yaw_z2, \
                                    arrow_pitch_y1, arrow_pitch_y2

            for ind in self.arrow_actor_list:
                self.ren2.AddActor(ind)

    def OnUpdateTargetCoordinates(self, coord):
        if coord is not None:
            self.target_coord = coord
            self.target_coord[1] = -self.target_coord[1]
            self.CreateTargetAim()
            Publisher.sendMessage('Target selected', status=True)
            print("Target updated to coordinates {}".format(coord))

    def RemoveTarget(self):
        self.target_mode = None
        self.target_coord = None
        self.RemoveTargetAim()
        Publisher.sendMessage('Target selected', status=False)

    def OnDisableOrEnableCoilTracker(self, status):
        if not status:
            self.RemoveTarget()
            self.DisableCoilTracker()

    def CreateVTKObjectMatrix(self, direction, orientation):
        m_img = dco.coordinates_to_transformation_matrix(
            position=direction,
            orientation=orientation,
            axes='sxyz',
        )
        m_img = np.asmatrix(m_img)

        m_img_vtk = vtkMatrix4x4()

        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        return m_img_vtk

    def CreateTargetAim(self):
        if self.aim_actor:
            self.RemoveTargetAim()
            self.aim_actor = None

        vtk_colors = vtkNamedColors()

        self.m_img_vtk = self.CreateVTKObjectMatrix(self.target_coord[:3], self.target_coord[3:])

        filename = os.path.join(inv_paths.OBJ_DIR, "aim.stl")

        reader = vtkSTLReader()
        reader.SetFileName(filename)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())

        # Transform the polydata
        transform = vtkTransform()
        transform.SetMatrix(self.m_img_vtk)
        transformPD = vtkTransformPolyDataFilter()
        transformPD.SetTransform(transform)
        transformPD.SetInputConnection(reader.GetOutputPort())
        transformPD.Update()
        # mapper transform
        mapper.SetInputConnection(transformPD.GetOutputPort())

        aim_actor = vtkActor()
        aim_actor.SetMapper(mapper)
        aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Yellow'))
        aim_actor.GetProperty().SetSpecular(.2)
        aim_actor.GetProperty().SetSpecularPower(100)
        aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)
        self.aim_actor = aim_actor
        self.ren.AddActor(aim_actor)

        if self.use_default_object:
            obj_polydata = vtku.CreateObjectPolyData(os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil_no_handle.stl"))
        else:
            obj_polydata = self.polydata

        transform = vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()

        normals = vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        obj_mapper = vtkPolyDataMapper()
        obj_mapper.SetInputData(normals.GetOutput())
        obj_mapper.ScalarVisibilityOff()
        #obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.dummy_coil_actor = vtkActor()
        self.dummy_coil_actor.SetMapper(obj_mapper)
        self.dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkOrange'))
        self.dummy_coil_actor.GetProperty().SetSpecular(0.5)
        self.dummy_coil_actor.GetProperty().SetSpecularPower(10)
        self.dummy_coil_actor.GetProperty().SetOpacity(.3)
        self.dummy_coil_actor.SetVisibility(self.show_object)
        self.dummy_coil_actor.SetUserMatrix(self.m_img_vtk)

        self.ren.AddActor(self.dummy_coil_actor)
        if not self.nav_status:
            self.UpdateRender()

    def RemoveTargetAim(self):
        self.ren.RemoveActor(self.aim_actor)
        self.ren.RemoveActor(self.dummy_coil_actor)
        if not self.nav_status:
            self.UpdateRender()

    def CreateTextDistance(self):
        tdist = vtku.Text()
        tdist.SetSize(const.TEXT_SIZE_DIST_NAV)
        tdist.SetPosition((const.X, 1.-const.Y))
        tdist.SetVerticalJustificationToBottom()
        tdist.BoldOn()
        self.ren.AddActor(tdist.actor)
        self.tdist = tdist


    def AddLine(self):
        line_source = vtkLineSource()
        line_source.SetPoint1(0, 0, 0)
        line_source.SetPoint2(100, 100, 100)

        line_mapper = vtkPolyDataMapper()
        line_mapper.SetInputConnection(line_source.GetOutputPort())

        line_actor = vtkActor()
        line_actor.SetMapper(line_mapper)

        self.ren.AddActor(line_actor)

    def DisableCoilTracker(self):
        try:
            self.ren.SetViewport(0, 0, 1, 1)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren2)
            self.SetViewAngle(const.VOL_FRONT)
            self.ren.RemoveActor(self.tdist.actor)
            self.CreateTargetAim()
            if not self.nav_status:
                self.UpdateRender()
        except:
            None

    def CreateArrowActor(self, startPoint, endPoint):
        # Compute a basis
        normalizedX = [0 for i in range(3)]
        normalizedY = [0 for i in range(3)]
        normalizedZ = [0 for i in range(3)]

        # The X axis is a vector from start to end
        math = vtkMath()
        math.Subtract(endPoint, startPoint, normalizedX)
        length = math.Norm(normalizedX)
        math.Normalize(normalizedX)

        # The Z axis is an arbitrary vector cross X
        arbitrary = [0 for i in range(3)]
        arbitrary[0] = random.uniform(-10, 10)
        arbitrary[1] = random.uniform(-10, 10)
        arbitrary[2] = random.uniform(-10, 10)
        math.Cross(normalizedX, arbitrary, normalizedZ)
        math.Normalize(normalizedZ)

        # The Y axis is Z cross X
        math.Cross(normalizedZ, normalizedX, normalizedY)
        matrix = vtkMatrix4x4()

        # Create the direction cosine matrix
        matrix.Identity()
        for i in range(3):
            matrix.SetElement(i, 0, normalizedX[i])
            matrix.SetElement(i, 1, normalizedY[i])
            matrix.SetElement(i, 2, normalizedZ[i])

        # Apply the transforms arrow 1
        transform_1 = vtkTransform()
        transform_1.Translate(startPoint)
        transform_1.Concatenate(matrix)
        transform_1.Scale(length, length, length)
        # source
        arrowSource1 = vtkArrowSource()
        arrowSource1.SetTipResolution(50)
        # Create a mapper and actor
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(arrowSource1.GetOutputPort())
        # Transform the polydata
        transformPD = vtkTransformPolyDataFilter()
        transformPD.SetTransform(transform_1)
        transformPD.SetInputConnection(arrowSource1.GetOutputPort())
        # mapper transform
        mapper.SetInputConnection(transformPD.GetOutputPort())
        # actor
        actor_arrow = vtkActor()
        actor_arrow.SetMapper(mapper)

        return actor_arrow

    def CenterOfMass(self):
        barycenter = [0.0, 0.0, 0.0]
        proj = prj.Project()
        try:
            surface = proj.surface_dict[0].polydata
        except KeyError:
            print("There is not any surface created")
            return barycenter

        polydata = surface

        centerOfMass = vtkCenterOfMass()
        centerOfMass.SetInputData(polydata)
        centerOfMass.SetUseScalarsAsWeights(False)
        centerOfMass.Update()

        barycenter = centerOfMass.GetCenter()

        return barycenter

    def Plane(self, x0, pTarget):
        v3 = np.array(pTarget) - x0  # normal to the plane
        v3 = v3 / np.linalg.norm(v3)  # unit vector

        d = np.dot(v3, x0)
        # prevents division by zero.
        if v3[0] == 0.0:
            v3[0] = 1e-09

        x1 = np.array([(d - v3[1] - v3[2]) / v3[0], 1, 1])
        v2 = x1 - x0
        v2 = v2 / np.linalg.norm(v2)  # unit vector
        v1 = np.cross(v3, v2)
        v1 = v1 / np.linalg.norm(v1)  # unit vector
        x2 = x0 + v1
        # calculates the matrix for the change of coordinate systems (from canonical to the plane's).
        # remember that, in np.dot(M,p), even though p is a line vector (e.g.,np.array([1,2,3])), it is treated as a column for the dot multiplication.
        M_plane_inv = np.array([[v1[0], v2[0], v3[0], x0[0]],
                                [v1[1], v2[1], v3[1], x0[1]],
                                [v1[2], v2[2], v3[2], x0[2]],
                                [0, 0, 0, 1]])

        return v3, M_plane_inv

    def SetCameraTarget(self):
        cam_focus = self.target_coord[0:3]
        cam = self.ren.GetActiveCamera()

        oldcamVTK = vtkMatrix4x4()
        oldcamVTK.DeepCopy(cam.GetViewTransformMatrix())

        newvtk = vtkMatrix4x4()
        newvtk.Multiply4x4(self.m_img_vtk, oldcamVTK, newvtk)

        transform = vtkTransform()
        transform.SetMatrix(newvtk)
        transform.Update()
        cam.ApplyTransform(transform)

        cam.Roll(90)

        cam_pos0 = np.array(cam.GetPosition())
        cam_focus0 = np.array(cam.GetFocalPoint())
        v0 = cam_pos0 - cam_focus0
        v0n = np.sqrt(inner1d(v0, v0))

        v1 = np.array([cam_focus[0] - cam_focus0[0], cam_focus[1] - cam_focus0[1], cam_focus[2] - cam_focus0[2]])
        v1n = np.sqrt(inner1d(v1, v1))
        if not v1n:
            v1n = 1.0
        cam_pos = (v1 / v1n) * v0n + cam_focus
        cam.SetFocalPoint(cam_focus)
        cam.SetPosition(cam_pos)

    def CreateBallReference(self):
        """
        Red sphere on volume visualization to reference center of
        cross in slice planes.
        The sphere's radius will be scale times bigger than the average of
        image spacing values.
        """
        scale = 2.0
        proj = prj.Project()
        s = proj.spacing
        r = (s[0] + s[1] + s[2]) / 3.0 * scale

        ball_source = vtkSphereSource()
        ball_source.SetRadius(r)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(ball_source.GetOutputPort())

        self.ball_actor = vtkActor()
        self.ball_actor.SetMapper(mapper)
        self.ball_actor.GetProperty().SetColor(1, 0, 0)
        self.ball_actor.PickableOff()

        self.ren.AddActor(self.ball_actor)

    # def SetCrossFocalPoint(self, position):
    #     self.UpdateCameraBallPosition(None, position)

    def UpdateCameraBallPosition(self, position):
        #if not self.actor_peel:
        if self.ball_actor is not None:
            coord_flip = list(position[:3])
            coord_flip[1] = -coord_flip[1]
            self.ball_actor.SetPosition(coord_flip)
            if self.set_camera_position:
                self.SetVolumeCamera(coord_flip)
            if not self.nav_status:
                self.UpdateRender()

    def AddObjectActor(self, obj_name):
        """
        Coil for navigation rendered in volume viewer.
        """
        vtk_colors = vtkNamedColors()
        obj_polydata = vtku.CreateObjectPolyData(obj_name)

        transform = vtkTransform()
        transform.RotateZ(90)

        transform_filt = vtkTransformPolyDataFilter()
        transform_filt.SetTransform(transform)
        transform_filt.SetInputData(obj_polydata)
        transform_filt.Update()

        normals = vtkPolyDataNormals()
        normals.SetInputData(transform_filt.GetOutput())
        normals.SetFeatureAngle(80)
        normals.AutoOrientNormalsOn()
        normals.Update()

        obj_mapper = vtkPolyDataMapper()
        obj_mapper.SetInputData(normals.GetOutput())
        obj_mapper.ScalarVisibilityOff()
        #obj_mapper.ImmediateModeRenderingOn()  # improve performance

        self.obj_actor = vtkActor()
        self.obj_actor.SetMapper(obj_mapper)
        self.obj_actor.GetProperty().SetAmbientColor(vtk_colors.GetColor3d('GhostWhite'))
        self.obj_actor.GetProperty().SetSpecular(30)
        self.obj_actor.GetProperty().SetSpecularPower(80)
        self.obj_actor.GetProperty().SetOpacity(.4)
        self.obj_actor.SetVisibility(0)

        self.x_actor = self.add_line([0., 0., 0.], [1., 0., 0.], color=[.0, .0, 1.0])
        self.y_actor = self.add_line([0., 0., 0.], [0., 1., 0.], color=[.0, 1.0, .0])
        self.z_actor = self.add_line([0., 0., 0.], [0., 0., 1.], color=[1.0, .0, .0])

        self.obj_projection_arrow_actor = self.CreateActorArrow([0., 0., 0.], [0., 0., 0.], vtk_colors.GetColor3d('Red'),
                                                                8)
        self.object_orientation_torus_actor = self.AddTorus([0., 0., 0.], [0., 0., 0.],
                                                            vtk_colors.GetColor3d('Red'))

        #self.obj_projection_arrow_actor.SetVisibility(False)
        #self.object_orientation_torus_actor.SetVisibility(False)
        self.ren.AddActor(self.obj_actor)
        self.ren.AddActor(self.x_actor)
        self.ren.AddActor(self.y_actor)
        self.ren.AddActor(self.z_actor)
        self.x_actor.SetVisibility(0)
        self.y_actor.SetVisibility(0)
        self.z_actor.SetVisibility(0)
        #self.ren.AddActor(self.obj_projection_arrow_actor)
        #self.ren.AddActor(self.object_orientation_torus_actor)
        # self.obj_axes = vtk.vtkAxesActor()
        # self.obj_axes.SetShaftTypeToCylinder()
        # self.obj_axes.SetXAxisLabelText("x")
        # self.obj_axes.SetYAxisLabelText("y")
        # self.obj_axes.SetZAxisLabelText("z")
        # self.obj_axes.SetTotalLength(50.0, 50.0, 50.0)

        # self.ren.AddActor(self.obj_axes)

    def AddObjectOrientationDisk(self, position, orientation, color=[0.0, 0.0, 1.0]):
        # Create a disk to show target
        disk = vtkDiskSource()
        disk.SetInnerRadius(5)
        disk.SetOuterRadius(15)
        disk.SetRadialResolution(100)
        disk.SetCircumferentialResolution(100)
        disk.Update()

        disk_mapper = vtkPolyDataMapper()
        disk_mapper.SetInputData(disk.GetOutput())
        disk_actor = vtkActor()
        disk_actor.SetMapper(disk_mapper)
        disk_actor.GetProperty().SetColor(color)
        disk_actor.GetProperty().SetOpacity(1)
        disk_actor.SetPosition(position)
        disk_actor.SetOrientation(orientation)

        return disk_actor

    def AddTorus(self, position, orientation, color=[0.0, 0.0, 1.0]):
        torus = vtkParametricTorus()
        torus.SetRingRadius(2)
        torus.SetCrossSectionRadius(1)

        torusSource = vtkParametricFunctionSource()
        torusSource.SetParametricFunction(torus)
        torusSource.Update()

        torusMapper = vtkPolyDataMapper()
        torusMapper.SetInputConnection(torusSource.GetOutputPort())
        torusMapper.SetScalarRange(0, 360)

        torusActor = vtkActor()
        torusActor.SetMapper(torusMapper)
        torusActor.GetProperty().SetDiffuseColor(color)
        torusActor.SetPosition(position)
        torusActor.SetOrientation(orientation)

        return torusActor

    def CreateActorBall(self, coord_flip, colour=[0.0, 0.0, 1.0], size=2):
        ball_ref = vtkSphereSource()
        ball_ref.SetRadius(size)
        ball_ref.SetCenter(coord_flip)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtkProperty()
        prop.SetColor(colour)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(prop)
        actor.PickableOff()

        return actor

    def CreateActorArrow(self, direction, orientation, colour=[0.0, 0.0, 1.0], size=const.ARROW_MARKER_SIZE):
        arrow = vtkArrowSource()
        arrow.SetArrowOriginToCenter()
        arrow.SetTipResolution(40)
        arrow.SetShaftResolution(40)
        arrow.SetShaftRadius(0.05)
        arrow.SetTipRadius(0.15)
        arrow.SetTipLength(0.35)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(arrow.GetOutputPort())

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(colour)
        actor.GetProperty().SetLineWidth(5)
        actor.AddPosition(0, 0, 0)
        actor.SetScale(size)

        m_img_vtk = self.CreateVTKObjectMatrix(direction, orientation)
        actor.SetUserMatrix(m_img_vtk)

        return actor

    def ObjectArrowLocation(self, m_img, coord):
        # m_img[:3, 0] is from posterior to anterior direction of the coil
        # m_img[:3, 1] is from left to right direction of the coil
        # m_img[:3, 2] is from bottom to up direction of the coil
        vec_length = 70
        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]
        p1 = m_img_flip[:-1, -1]  # coil center
        coil_dir = m_img_flip[:-1, 0]
        coil_face = m_img_flip[:-1, 1]

        coil_norm = np.cross(coil_dir, coil_face)
        p2_norm = p1 - vec_length * coil_norm # point normal to the coil away from the center by vec_length
        coil_dir = np.array([coord[3], coord[4], coord[5]])

        return coil_dir, p2_norm, coil_norm, p1


    def add_line(self, p1, p2, color=[0.0, 0.0, 1.0]):
        line = vtkLineSource()
        line.SetPoint1(p1)
        line.SetPoint2(p2)

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(line.GetOutputPort())

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(color)

        return actor

    def AddPeeledSurface(self, flag, actor):
        if self.actor_peel:
            self.ren.RemoveActor(self.actor_peel)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.actor_peel = None
            if self.ball_actor:
                self.ball_actor.SetVisibility(1)

        if flag and actor:
            self.ren.AddActor(actor)
            self.actor_peel = actor
            self.ren.AddActor(self.object_orientation_torus_actor)
            self.ren.AddActor(self.obj_projection_arrow_actor)

        if not self.nav_status:
            self.UpdateRender()

    def GetPeelCenters(self, centers, normals):
        self.peel_centers = centers
        self.peel_normals = normals

    def InitLocatorViewer(self, locator):
        self.locator = locator

    def RecolorEfieldActor(self):
        self.efield_mesh_normals_viewer.Modified()

    def DrawVectors(self, position, orientation, color, scale_factor=10):
        points = vtkPoints()
        vectors = vtkDoubleArray()
        vectors.SetNumberOfComponents(3)
        points.InsertNextPoint(position)
        vectors.InsertNextTuple3(orientation[0], orientation[1], orientation[2])
        dataset = vtkPolyData()
        dataset.SetPoints(points)
        dataset.GetPointData().SetVectors(vectors)
        arrowSource = vtkArrowSource()
        glyphFilter = vtkGlyph3D()
        glyphFilter.SetSourceConnection(arrowSource.GetOutputPort())
        glyphFilter.SetInputData(dataset)
        glyphFilter.SetScaleFactor(scale_factor)
        glyphFilter.Update()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(glyphFilter.GetOutput())
        Actor = vtkActor()
        Actor.SetMapper(mapper)
        Actor.GetProperty().SetColor(color)
        return Actor

    def MaxEfieldActor(self):
        vtk_colors = vtkNamedColors()
        if self.max_efield_vector and self.ball_max_vector is not None:
            self.ren.RemoveActor(self.max_efield_vector)
            self.ren.RemoveActor(self.ball_max_vector)
        self.position_max = self.efield_mesh.GetPoint(self.Idmax)
        orientation = [self.max_efield_array[0], self.max_efield_array[1], self.max_efield_array[2]]
        self.max_efield_vector= self.DrawVectors(self.position_max, orientation, vtk_colors.GetColor3d('Red'))
        self.ball_max_vector = self.CreateActorBall(self.position_max, vtk_colors.GetColor3d('Red'), 0.5)
        self.ren.AddActor(self.max_efield_vector)
        self.ren.AddActor(self.ball_max_vector)

    def CoGEfieldActor(self):
        vtk_colors = vtkNamedColors()
        if self.GoGEfieldVector and self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.ren.RemoveActor(self.ball_GoGEfieldVector)
        orientation = [self.max_efield_array[0] , self.max_efield_array[1], self.max_efield_array[2]]
        [self.center_gravity_id] = self.FindCenterofGravity( )
        self.GoGEfieldVector = self.DrawVectors(self.center_gravity_id, orientation,vtk_colors.GetColor3d('Blue'))
        self.ball_GoGEfieldVector = self.CreateActorBall(self.center_gravity_id, vtk_colors.GetColor3d('Blue'),0.5)
        self.ren.AddActor(self.GoGEfieldVector)
        self.ren.AddActor(self.ball_GoGEfieldVector)

    def CreateTextLegend(self, FontSize, Position):
        TextLegend = vtku.Text()
        TextLegend.SetSize(FontSize)
        TextLegend.SetPosition(Position)
        TextLegend.BoldOn()
        return TextLegend

    def CreateEfieldSpreadLegend(self):
        self.SpreadEfieldFactorTextActor = self.CreateTextLegend(const.TEXT_SIZE_DIST_NAV,(0.35, 0.9))
        self.ren.AddActor(self.SpreadEfieldFactorTextActor.actor)

    def CalculateDistanceMaxEfieldCoGE(self):
        distance_efield = distance.euclidean(self.center_gravity_id, self.position_max)
        self.SpreadEfieldFactorTextActor.SetValue('Spread distance: ' + str("{:04.2f}".format(distance_efield)))

    def EfieldVectors(self):
        vtk_colors = vtkNamedColors()
        if self.vectorfield_actor is not None:
            self.ren.RemoveActor(self.vectorfield_actor)
        points = vtkPoints()
        vectors = vtkDoubleArray()
        vectors.SetNumberOfComponents(3)

        for i in range(self.radius_list.GetNumberOfIds()):
            point = self.efield_mesh.GetPoint(self.radius_list.GetId(i))
            points.InsertNextPoint(point)
            vectors.InsertNextTuple3(self.e_field_col1[i], self.e_field_col2[i], self.e_field_col3[i])

        dataset = vtkPolyData()
        dataset.SetPoints(points)
        dataset.GetPointData().SetVectors(vectors)

        arrowSource= vtkArrowSource()

        glyphFilter = vtkGlyph3D()
        glyphFilter.SetSourceConnection(arrowSource.GetOutputPort())
        glyphFilter.SetInputData(dataset)
        glyphFilter.SetScaleFactor(1)
        glyphFilter.Update()

        mapper =vtkPolyDataMapper()
        mapper.SetInputData(glyphFilter.GetOutput())

        self.vectorfield_actor = vtkActor()
        self.vectorfield_actor.SetMapper(mapper)
        self.vectorfield_actor.GetProperty().SetColor(vtk_colors.GetColor3d('Blue'))

        self.ren.AddActor(self.vectorfield_actor)
        self.interactor.Update()

    def SaveEfieldTargetData(self, target_list_index, position, orientation, plot_efield_vectors):
        if len(self.Id_list)>0:
            enorms_list = list(self.e_field_norms)
            if plot_efield_vectors:
                e_field_vectors = list(self.max_efield_array)#[list(self.e_field_col1), list(self.e_field_col2), list(self.e_field_col3)]
                self.target_radius_list.append([target_list_index, self.Id_list, enorms_list, self.Idmax, position, orientation, self.coil_position_Trot, e_field_vectors, self.heights])
            else:
                self.target_radius_list.append([target_list_index, self.Id_list, enorms_list, self.Idmax, position, orientation, self.coil_position_Trot])

    def GetTargetSavedEfieldData(self, target_index_list):
        if len(self.target_radius_list)>0:
            target_index = 0
            for i in range(len(self.target_radius_list)):
                if target_index_list == self.target_radius_list[i][0]:
                    target_index= i
                    self.saved_target_data = self.target_radius_list[target_index]
                    break

        #location_previous_max = self.saved_target_data[3]
        #saved_efield_data = self.saved_target_data[2]

    def CheckStatusSavedEfieldData(self):
        indexes_saved_list = []
        if len(self.target_radius_list)>0:
            efield_data_loaded= True
            for i in range(len(self.target_radius_list)):
                indexes_saved_list.append(self.target_radius_list[i][0])
            indexes_saved_list= np.array(indexes_saved_list)
        else:
            efield_data_loaded = False
        Publisher.sendMessage('Get status of Efield saved data', efield_data_loaded=efield_data_loaded, indexes_saved_list= indexes_saved_list )

    def InitializeColorArray(self):
        self.colors_init.SetNumberOfComponents(3)
        self.colors_init.SetName('Colors')
        color = 3 * [const.CORTEX_COLOR]
        for i in range(self.efield_mesh.GetNumberOfCells()):
            self.colors_init.InsertTuple(i, color)

    def ReturnToDefaultColorActor(self):
        self.efield_mesh.GetPointData().SetScalars(self.colors_init)
        wx.CallAfter(Publisher.sendMessage, 'Initialize color array')
        wx.CallAfter(Publisher.sendMessage, 'Recolor efield actor')

    def CreateLUTTableForEfield(self, min, max):
        lut = vtkLookupTable()
        lut.SetTableRange(min, max)
        colorSeries = vtkColorSeries()
        seriesEnum = colorSeries.BREWER_SEQUENTIAL_BLUE_PURPLE_9
        colorSeries.SetColorScheme(seriesEnum)
        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        return lut

    def GetEfieldMaxMin(self, e_field_norms):
        self.e_field_norms = e_field_norms
        max = np.amax(self.e_field_norms)
        min = np.amin(self.e_field_norms)
        self.efield_min = min
        self.efield_max = max
        #self.Idmax = np.array(self.e_field_norms).argmax()
        wx.CallAfter(Publisher.sendMessage, 'Update efield vis')

    def FindClosestValueEfieldEdges(self, arr, threshold):
        closest_value = min(arr, key = lambda x: abs(x-threshold))
        closest_index = np.argmin(np.abs(arr-closest_value))
        return closest_index

    def CalculateEdgesEfield(self):
        if self.edge_actor is not None:
            self.ren.RemoveViewProp(self.edge_actor)
        named_colors = vtkNamedColors()
        second_lut = self.CreateLUTTableForEfield(self.efield_min, self.efield_max)
        second_lut.SetNumberOfTableValues(5)

        bcf = vtkBandedPolyDataContourFilter()
        bcf.SetInputData(self.efield_mesh)
        bcf.ClippingOn()

        lower_edge = self.FindClosestValueEfieldEdges(np.array(self.e_field_norms), self.efield_min)
        middle_edge = self.FindClosestValueEfieldEdges(np.array(self.e_field_norms), self.efield_max * 0.2)
        middle_edge1 = self.FindClosestValueEfieldEdges(np.array(self.e_field_norms), self.efield_max * 0.7)
        upper_edge = self.FindClosestValueEfieldEdges(np.array(self.e_field_norms), self.efield_max * 0.9)
        lower_edge = self.efield_mesh.GetPoint(lower_edge)
        middle_edge = self.efield_mesh.GetPoint(middle_edge)
        middle_edge1 = self.efield_mesh.GetPoint(middle_edge1)
        upper_edge = self.efield_mesh.GetPoint(upper_edge)

        edges = [ lower_edge, middle_edge, middle_edge1, upper_edge]
        for i in range(len(edges)):
            bcf.SetValue(i, edges[i][2])
        bcf.SetScalarModeToIndex()
        bcf.GenerateContourEdgesOn()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(bcf.GetOutputPort())
        mapper.SetLookupTable(second_lut)
        mapper.SetScalarModeToUsePointData()

        actor = vtkActor()
        actor.SetMapper(mapper)

        edge_mapper = vtkPolyDataMapper()
        edge_mapper.SetInputData(bcf.GetContourEdgesOutput())
        edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()

        self.edge_actor = vtkActor()
        self.edge_actor.SetMapper(edge_mapper)
        self.edge_actor.GetProperty().SetColor(named_colors.GetColor3d('Black'))
        self.edge_actor.GetProperty().SetLineWidth(3.0)
        actor.GetProperty().SetOpacity(0)
        self.ren.AddViewProp(actor)
        self.ren.AddViewProp(self.edge_actor)

        self.efield_scalar_bar.SetLookupTable(self.efield_lut)
        self.ren.AddActor2D(self.efield_scalar_bar)

    def GetIndexesAboveThreshold(self):
        cell_id_indexes = []
        indexes = [index for index, value in enumerate(self.e_field_norms) if
                   value > self.efield_max * self.efield_threshold]
        for index, value in enumerate(indexes):
            cell_id_indexes.append(self.Id_list[value])
        return cell_id_indexes

    def UpdateEfieldThreshold(self, data):
        self.efield_threshold = data

    def UpdateEfieldROISize(self, data):
        self.efield_ROISize = data
        self.radius_list.Reset()

    def FindCenterofGravity(self):
        cell_id_indexes = self.GetIndexesAboveThreshold()
        weights = []
        positions = []
        for index, value in enumerate(cell_id_indexes):
            weights.append(self.e_field_norms[index])
            positions.append(self.efield_mesh.GetPoint(value))
        self.SegmentEfieldMax(positions, weights)
        self.DetectClustersEfieldSpread(positions)
        x_weighted = []
        y_weighted = []
        z_weighted = []
        for i, (x, y, z) in enumerate(positions):
            x_weighted.append(x * weights[i])
            y_weighted.append(y * weights[i])
            z_weighted.append(z * weights[i])
        sum_x = sum(x_weighted)
        sum_y = sum(y_weighted)
        sum_z = sum(z_weighted)
        sum_weights = sum(weights)

        center_gravity_x = sum_x / sum_weights
        center_gravity_y = sum_y / sum_weights
        center_gravity_z = sum_z / sum_weights

        query_point = [center_gravity_x, center_gravity_y, center_gravity_z]
        closest_point = [0.0, 0.0, 0.0]
        cell_id = mutable(0)
        sub_id = mutable(0)
        distance = mutable(0.0)
        self.locator_efield_cell.FindClosestPoint(query_point, closest_point, cell_id, sub_id, distance)
        return [closest_point]

    def DetectClustersEfieldSpread(self, points):
        from sklearn.cluster import DBSCAN
        dbscan = DBSCAN(eps=5, min_samples=2).fit(points)
        labels = dbscan.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0 )
        self.ClusterEfieldTextActor.SetValue('Clusters above '+ str(int(self.efield_threshold*100)) + '% percent: ' + str(n_clusters))

    def CreateClustersEfieldLegend(self):
        self.ClusterEfieldTextActor = self.CreateTextLegend(const.TEXT_SIZE_DIST_NAV,const.TEXT_POS_LEFT_UP)
        self.ren.AddActor(self.ClusterEfieldTextActor.actor)

    def SegmentEfieldMax(self, positions, values):
        self.heights = []
        for i, pos in enumerate(positions):
            self.heights.append([pos, values[i]])

    def GetEfieldActor(self, e_field_actor):
        self.efield_actor  = e_field_actor

    def FindPointsAroundRadiusEfield(self, cellId):
        radius = int(self.efield_ROISize)
        self.locator_efield.FindPointsWithinRadius(radius, self.e_field_mesh_centers.GetPoint(cellId), self.radius_list)

    # def GetCellIDsfromlistPoints(self, vlist, mesh):
    #     cell_ids_array = []
    #     pts1 = vtkIdList()
    #     for i in range(vlist.GetNumberOfIds()):
    #         mesh.GetPointCells(vlist.GetId(i), pts1)
    #         for j in range(pts1.GetNumberOfIds()):
    #             cell_ids_array.append(pts1.GetId(j))
    #     return cell_ids_array
    #
    # def CreatePoissonSurface(self, input_points, mesh):
    #     import vtk
    #     points = vtkPoints()
    #     for i in range(input_points.GetNumberOfIds()):
    #         point = mesh.GetPoint(input_points.GetId(i))
    #         points.InsertNextPoint(point)
    #
    #     input_polydata = vtkPolyData()
    #     input_polydata.SetPoints(points)
    #
    #     delaunay_3d = vtk.vtkDelaunay3D()
    #     delaunay_3d.SetAlpha(100)
    #     delaunay_3d.BoundingTriangulationOff()
    #     delaunay_3d.SetInputData(input_polydata)
    #
    #     surface_filter = vtk.vtkDataSetSurfaceFilter()
    #     surface_filter.SetInputConnection(delaunay_3d.GetOutputPort())
    #     surface_filter.Update()
    #     output_polydata = surface_filter.GetOutput()
    #
    #     # Create a mapper and actor
    #     mapper = vtk.vtkPolyDataMapper()
    #     mapper.SetInputConnection(surface_filter.GetOutputPort())
    #
    #     actor = vtk.vtkActor()
    #     actor.SetMapper(mapper)
    #
    #     #self.ren.AddActor(actor)
    #     return output_polydata

    def CreateCortexProjectionOnScalp(self, marker_id, position, orientation):
        self.target_at_cortex = None
        self.scalp_mesh = self.scalp_actor.GetMapper().GetInput()
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.target_at_cortex = position_flip
        point_scalp = self.FindClosestPointToMesh(position_flip, self.scalp_mesh)
        Publisher.sendMessage('Create Marker from tangential', point = point_scalp, orientation =orientation)

    def ShowEfieldAtCortexTarget(self):
        if self.target_at_cortex is not None:
            import vtk
            cell_number = 0
            index = self.efield_mesh.FindPoint(self.target_at_cortex)

            #cell_id = self.locator_efield_cell.FindCell(self.target_at_cortex)
            # idlist = vtkIdList()
            # self.locator_efield.FindPointsWithinRadius(5, self.e_field_mesh_centers.GetPoint(cell_id), idlist)
            # index = cell_id
            # print('cell Id:', cell_id)
            # color = [255, 165, 0]
            # for i in range(idlist.GetNumberOfIds()):
            #     self.colors_init.InsertTuple(idlist.GetId(i), color)
            for i in range(self.radius_list.GetNumberOfIds()):
                if index == self.radius_list.GetId(i):
                    cell_number = i
                    self.EfieldAtTargetLegend.SetValue(
                        'Efield at Target: ' + str("{:04.2f}".format(self.e_field_norms[cell_number])))

                    break
                else:
                    continue
            #wx.CallAfter(Publisher.sendMessage, 'Recolor efield actor')

    def CreateEfieldAtTargetLegend(self):
        self.EfieldAtTargetLegend = self.CreateTextLegend(const.TEXT_SIZE_DIST_NAV,(0.35, 0.97))
        self.ren.AddActor(self.EfieldAtTargetLegend.actor)

    # def getAdjacentCells(self, mesh, cellId):
    #     # get points that make up the cellId of mesh
    #     cellPoints = vtkIdList()
    #     mesh.GetCellPoints(cellId, cellPoints)
    #     # get all cells that are connected to these points
    #     cellNeighbors = vtkIdList()
    #     for i in range(0, cellPoints.GetNumberOfIds()):
    #         pointId = cellPoints.GetId(i)
    #         connectedCells = vtkIdList()
    #         mesh.GetPointCells(pointId, connectedCells)
    #
    #         for j in range(0, connectedCells.GetNumberOfIds()):
    #             connectedCellId = connectedCells.GetId(j)
    #
    #             # remove duplicate and the original cellId
    #             if connectedCellId != cellId:
    #                 cellNeighbors.InsertUniqueId(connectedCellId)
    #     return cellNeighbors
    #
    # def get_cell_centers(self,mesh):
    #     # Calculate cell centers
    #     import vtk
    #     cell_centers = vtk.vtkCellCenters()
    #     cell_centers.SetInputData(mesh)
    #     cell_centers.Update()
    #     return cell_centers.GetOutput()
    # def get_center(self, cell):
    #     bounds = cell.GetBounds()
    #     center = [0, 0, 0]
    #     center[0] = (bounds[1] - bounds[0]) / 2 + bounds[0]
    #     center[1] = (bounds[3] - bounds[2]) / 2 + bounds[2]
    #     center[2] = (bounds[5] - bounds[4]) / 2 + bounds[4]
    #     return center
    #
    # def find_nearest_cellid(self, mesh, cellId):
    #     from scipy.spatial import cKDTree
    #     cell_centers = self.get_cell_centers(mesh)  # Get cell centers
    #     tree = cKDTree([cell_centers.GetPoint(i) for i in range(cell_centers.GetNumberOfPoints())])
    #
    #     center = self.get_center(mesh.GetCell(cellId))  # Calculate center of the cell with given cellId
    #
    #     # Query nearest cell and exclude itself
    #     dists, ids = tree.query(center, 2)  # Query two nearest cells
    #     nearest_cell_id = ids[1] if ids[0] == cellId else ids[0]
    #
    #     return nearest_cell_id, dists[1]
    #
    # def GetNormals(self,mesh):
    #     # Compute normals of triangles
    #     normalComputer = vtkPolyDataNormals()  # This computes normals of the triangles on the peel
    #     normalComputer.SetInputData(mesh)
    #     normalComputer.ComputePointNormalsOff()
    #     normalComputer.ComputeCellNormalsOn()
    #     normalComputer.Update()
    #     # This converts to the normals to an array for easy access
    #     normals = normalComputer.GetOutput().GetCellData().GetNormals()
    #     return normals
    #
    # def SetInitialCoilOrientation(self, point, orientation):
    #     import invesalius.data.transformations as tr
    #
    #     angles = orientation
    #     translate = list(point)
    #     m_img = tr.compose_matrix(angles = angles, translate = translate)
    #     img_vtk = self.CreateVTKObjectMatrix(direction = point, orientation=angles)
    #     if self.dummy_efield_coil_actor is not None:
    #         self.ren.RemoveActor(self.dummy_efield_coil_actor)
    #     self.dummy_efield_coil_actor = self.CreateDummyCoilForEfieldCoilPlacement()
    #     self.dummy_efield_coil_actor.SetUserMatrix(img_vtk)
    #     self.ren.AddActor(self.dummy_efield_coil_actor)
    #     m_img_flip = m_img.copy()
    #     m_img_flip[1,-1] = -m_img_flip[1,-1]
    #     cp = m_img_flip[:-1, -1]  # coil center
    #     cp = cp * 0.001  # convert to meters
    #     cp = cp.tolist()
    #
    #     ct1 = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
    #     ct2 = m_img_flip[:3, 0]  # is from left to right direction of the coil
    #     coil_dir = m_img_flip[:-1, 0]
    #     coil_face = m_img_flip[:-1, 1]
    #     cn = np.cross(coil_dir, coil_face)
    #     T_rot = np.append(ct1, ct2, axis=0)
    #     T_rot = np.append(T_rot, cn, axis=0) * 0.001  # append and convert to meters
    #     T_rot = T_rot.tolist()  # to list
    #     return [T_rot, cp]
    #
    # def CreateDummyCoilForEfieldCoilPlacement(self):
    #     vtk_colors = vtkNamedColors()
    #
    #     obj_polydata = vtku.CreateObjectPolyData(os.path.join(inv_paths.OBJ_DIR, "magstim_fig8_coil_no_handle.stl"))
    #     transform = vtkTransform()
    #     transform.RotateZ(90)
    #
    #     transform_filt = vtkTransformPolyDataFilter()
    #     transform_filt.SetTransform(transform)
    #     transform_filt.SetInputData(obj_polydata)
    #     transform_filt.Update()
    #
    #     normals = vtkPolyDataNormals()
    #     normals.SetInputData(transform_filt.GetOutput())
    #     normals.SetFeatureAngle(80)
    #     normals.AutoOrientNormalsOn()
    #     normals.Update()
    #
    #     obj_mapper = vtkPolyDataMapper()
    #     obj_mapper.SetInputData(normals.GetOutput())
    #     obj_mapper.ScalarVisibilityOff()
    #     dummy_coil_actor = vtkActor()
    #     dummy_coil_actor.SetMapper(obj_mapper)
    #     dummy_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkBlue'))
    #     dummy_coil_actor.GetProperty().SetSpecular(0.5)
    #     dummy_coil_actor.GetProperty().SetSpecularPower(10)
    #     dummy_coil_actor.GetProperty().SetOpacity(.3)
    #
    #     return dummy_coil_actor
    #
    # def ScanNormalsforCoilPlacement(self, cortex_id_cell):
    #     vtk_colors = vtkNamedColors()
    #     point_array = []
    #     for i in range(self.scalp.mesh_normals.GetNumberOfTuples()):
    #         pointnormal_scalp = self.scalp.mesh_normals.GetTuple(i)
    #         angle = np.rad2deg(np.arccos(np.dot(pointnormal_scalp, self.e_field_mesh_normals.GetTuple(cortex_id_cell))))
    #         if angle < 7:
    #             point_array.append(self.scalp_mesh.GetPoint(i))
    #             self.ren.AddActor(self.CreateActorBall(self.scalp_mesh.GetPoint(i), colour=vtk_colors.GetColor3d('Pink'), size=5))
    #     point = self.FindClosestPoint(point_array, self.efield_mesh.GetPoint(cortex_id_cell))
    #     return point

    def FindClosestPointToMesh(self, point,mesh):
        closest_distance = float('inf')
        closest_point = None
        point = np.array(point)
        for i in range(mesh.GetNumberOfCells()):
            distance_sq = np.linalg.norm(np.array(self.scalp_mesh.GetPoint(i)) -point)
            if distance_sq < closest_distance:
                closest_distance = distance_sq
                closest_point = self.scalp_mesh.GetPoint(i)
        return closest_point

    def GetScalpEfield(self, scalp_actor):
        self.scalp_actor =  scalp_actor

    def InitEfield(self, e_field_brain):
        self.e_field_mesh_normals =e_field_brain.e_field_mesh_normals
        self.e_field_mesh_centers = e_field_brain.e_field_mesh_centers
        self.locator_efield = e_field_brain.locator_efield
        self.locator_efield_cell = e_field_brain.locator_efield_Cell
        self.efield_mesh = e_field_brain.e_field_mesh
        self.efield_mapper = e_field_brain.efield_mapper
        self.efield_mesh_normals_viewer = vtkPolyDataNormals()
        self.efield_mesh_normals_viewer.SetInputData(self.efield_mesh)
        self.efield_mesh_normals_viewer.SetFeatureAngle(80)
        self.efield_mesh_normals_viewer.AutoOrientNormalsOn()
        self.efield_mesh_normals_viewer.Update()
        self.efield_mapper.SetInputConnection(self.efield_mesh_normals_viewer.GetOutputPort())
        self.efield_mapper.ScalarVisibilityOn()
        self.efield_actor.SetMapper(self.efield_mapper)
        self.efield_actor.GetProperty().SetBackfaceCulling(1)
        self.efield_coords = None
        self.coil_position = None
        self.coil_position_Trot = None
        self.e_field_norms = None
        self.efield_threshold = const.EFIELD_MAX_RANGE_SCALE
        self.efield_ROISize = const.EFIELD_ROI_SIZE
        self.target_radius_list=[]
        self.CreateEfieldSpreadLegend()
        self.CreateClustersEfieldLegend()
        self.CreateEfieldAtTargetLegend()

        if self.max_efield_vector and self.ball_max_vector is not None:
            self.ren.RemoveActor(self.max_efield_vector)
            self.ren.RemoveActor(self.ball_max_vector)

        if self.GoGEfieldVector and self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.ren.RemoveActor(self.ball_GoGEfieldVector)

        if self.vectorfield_actor is not None:
            self.ren.RemoveActor(self.vectorfield_actor)

        if self.efield_scalar_bar is not None:
            self.ren.RemoveActor(self.efield_scalar_bar)

        self.efield_scalar_bar = e_field_brain.efield_scalar_bar
        #self.efield_lut = e_field_brain.lut

        if self.edge_actor is not None:
            self.ren.RemoveActor(self.edge_actor)

    def GetNeuronavigationApi(self, neuronavigation_api):
        self.neuronavigation_api = neuronavigation_api

    def ShowEfieldintheintersection(self, intersectingCellIds, p1, coil_norm, coil_dir):
        closestDist = 100
        # if find intersection , calculate angle and add actors
        if intersectingCellIds.GetNumberOfIds() != 0:
            for i in range(intersectingCellIds.GetNumberOfIds()):
                cellId = intersectingCellIds.GetId(i)
                point = np.array(self.e_field_mesh_centers.GetPoint(cellId))
                distance = np.linalg.norm(point - p1)
                if distance < closestDist:
                    closestDist = distance
                    closestPoint = point
                    pointnormal = np.array(self.e_field_mesh_normals.GetTuple(cellId))
                    angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
                    self.FindPointsAroundRadiusEfield(cellId)
                    self.radius_list.Sort()
        else:
            self.radius_list.Reset()

    def OnUpdateEfieldvis(self):
        if len(self.Id_list) !=0:
            self.efield_lut = self.CreateLUTTableForEfield(self.efield_min, self.efield_max)
            self.CalculateEdgesEfield()
            self.colors_init.SetNumberOfComponents(3)
            self.colors_init.Fill(const.CORTEX_COLOR)
            for h in range(len(self.Id_list)):
                 dcolor = 3 * [0.0]
                 index_id = self.Id_list[h]
                 if self.plot_vector:
                    self.efield_lut.GetColor(self.e_field_norms[h], dcolor)
                 else:
                    self.efield_lut.GetColor(self.e_field_norms[index_id], dcolor)
                 color = 3 * [0.0]
                 for j in range(0, 3):
                     color[j] = int(255.0 * dcolor[j])
                 self.colors_init.InsertTuple(index_id, color)
            self.efield_mesh.GetPointData().SetScalars(self.colors_init)
            wx.CallAfter(Publisher.sendMessage, 'Recolor efield actor')
            if self.vectorfield_actor is not None:
                self.ren.RemoveActor(self.vectorfield_actor)
            if self.plot_vector:
                wx.CallAfter(Publisher.sendMessage, 'Show max Efield actor')
                wx.CallAfter(Publisher.sendMessage, 'Show CoG Efield actor')
                wx.CallAfter(Publisher.sendMessage, 'Show distance between Max and CoG Efield')
                self.ShowEfieldAtCortexTarget()
                if self.plot_no_connection:
                    wx.CallAfter(Publisher.sendMessage,'Show Efield vectors')
                    self.plot_vector= False
                    self.plot_no_connection = False
        else:
            wx.CallAfter(Publisher.sendMessage,'Recolor again')

    def UpdateEfieldPointLocation(self, m_img, coord, queue_IDs):
        #TODO: In the future, remove the "put_nowait" and mesh processing to another module (maybe e_field.py)
        # this might work because a python instance from the 3D mesh can be edited in the thread. Check how to extract
        # the instance from the desired mesh for visualization and if it works. Optimally, there should be no
        # processing or threading related commands inside viewer_volume.
        [coil_dir, norm, coil_norm, p1]= self.ObjectArrowLocation(m_img, coord)
        intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        try:
            self.e_field_IDs_queue = queue_IDs
            if self.radius_list.GetNumberOfIds() != 0:
                if np.all(self.old_coord != coord):
                    self.e_field_IDs_queue.put_nowait((self.radius_list))
                self.old_coord = np.array([coord])
        except queue.Full:
            pass

    def UpdateEfieldPointLocationOffline(self, m_img, coord):
        [coil_dir, norm, coil_norm, p1] = self.ObjectArrowLocation(m_img, coord)
        intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        id_list = []
        for h in range(self.radius_list.GetNumberOfIds()):
            id_list.append(self.radius_list.GetId(h))
        Publisher.sendMessage('Get ID list', ID_list = id_list)
        self.plot_no_connection = True

    def GetCoilPosition(self, position, orientation):
        m_img = tr.compose_matrix(angles=orientation, translate=position)
        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]
        cp = m_img_flip[:-1, -1]  # coil center
        cp = cp * 0.001  # convert to meters
        cp = cp.tolist()

        ct1 = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
        ct2 = m_img_flip[:3, 0]  # is from left to right direction of the coil
        coil_dir = m_img_flip[:-1, 0]
        coil_face = m_img_flip[:-1, 1]
        cn = np.cross(coil_dir, coil_face)
        T_rot = np.append(ct1, ct2, axis=0)
        T_rot = np.append(T_rot, cn, axis=0)  # append
        T_rot = T_rot.tolist()  # to list
        Publisher.sendMessage('Send coil position and rotation', T_rot=T_rot, cp=cp, m_img=m_img)


    def GetEnorm(self, enorm_data, plot_vector):
        self.e_field_col1=[]
        self.e_field_col2=[]
        self.e_field_col3=[]
        session = ses.Session()
        self.plot_vector = plot_vector
        self.coil_position_Trot = enorm_data[0]
        self.coil_position = enorm_data[1]
        self.efield_coords = enorm_data[2]
        self.Id_list = enorm_data[4]
        if self.plot_vector:
            if session.GetConfig('debug_efield'):
                self.e_field_norms = enorm_data[3][self.Id_list,0]
                self.e_field_col1 = enorm_data[3][self.Id_list,1]
                self.e_field_col2 = enorm_data[3][self.Id_list,1]
                self.e_field_col3 = enorm_data[3][self.Id_list,3]
                self.Idmax = np.array(self.Id_list[np.array(self.e_field_norms).argmax()])
                max =np.array(self.e_field_norms).argmax()
                self.max_efield_array = [self.e_field_col1[max],self.e_field_col2[max],self.e_field_col3[max] ]
            else:
                self.e_field_norms = enorm_data[3].enorm
                self.e_field_col1 = enorm_data[3].column1
                self.e_field_col2 = enorm_data[3].column2
                self.e_field_col3 = enorm_data[3].column3
                self.max_efield_array = enorm_data[3].mvector
                self.Idmax = self.Id_list[enorm_data[3].maxindex]
        else:
            self.e_field_norms = enorm_data[3]
            self.Idmax = np.array(self.e_field_norms).argmax()

        #self.Idmax = np.array(self.e_field_norms).argmax()
            #wx.CallAfter(Publisher.sendMessage, 'Update efield vis')
        self.GetEfieldMaxMin(self.e_field_norms)

    def SaveEfieldData(self, filename, plot_efield_vectors):
        import invesalius.data.imagedata_utils as imagedata_utils
        import csv
        all_data=[]
        header = ['T_rot','coil position','coords position', 'coords', 'Enorm', 'efield vectors']
        if self.efield_coords is not None:
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
            position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
            orientation=[self.efield_coords[3], self.efield_coords[4], self.efield_coords[5]],
                 )
            efield_coords_position = [list(position_world), list(orientation_world)]
        if plot_efield_vectors:
            e_field_vectors = list(self.max_efield_array)#[list(self.e_field_col1), list(self.e_field_col2), list(self.e_field_col3)]
            all_data.append([self.coil_position_Trot, self.coil_position, efield_coords_position, self.efield_coords, list(self.e_field_norms), e_field_vectors])

        else:
            all_data.append([self.coil_position_Trot, self.coil_position, efield_coords_position, self.efield_coords, list(self.e_field_norms)])

        with open(filename, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(all_data)

    def SavedAllEfieldData(self, filename):
        import invesalius.data.imagedata_utils as imagedata_utils
        import csv
        header = ['target index', 'norm cell indexes', 'enorm', 'ID cell Max', 'position', 'orientation', 'Trot', 'efield vectors', 'heights']
        all_data = list(self.target_radius_list)
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(all_data)

    def GetCellIntersection(self, p1, p2, locator):
        vtk_colors = vtkNamedColors()
        # This find store the triangles that intersect the coil's normal
        intersectingCellIds = vtkIdList()
        #for debugging
        #self.x_actor = self.add_line(p1,p2,vtk_colors.GetColor3d('Blue'))
        #self.ren.AddActor(self.x_actor) # remove comment for testing
        locator.FindCellsAlongLine(p1, p2, .001, intersectingCellIds)
        return intersectingCellIds

    def ShowCoilProjection(self, intersectingCellIds, p1, coil_norm, coil_dir):
        vtk_colors = vtkNamedColors()
        closestDist = 50

        #if find intersection , calculate angle and add actors
        if intersectingCellIds.GetNumberOfIds() != 0:
            for i in range(intersectingCellIds.GetNumberOfIds()):
                cellId = intersectingCellIds.GetId(i)
                point = np.array(self.peel_centers.GetPoint(cellId))
                distance = np.linalg.norm(point - p1)

                self.ren.RemoveActor(self.y_actor)

                if distance < closestDist:
                    closestDist = distance
                    closestPoint = point
                    pointnormal = np.array(self.peel_normals.GetTuple(cellId))
                    angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
                    #print('the angle:', angle)

                    #for debbuging
                    self.y_actor = self.add_line(closestPoint, closestPoint + 75 * pointnormal,
                                                         vtk_colors.GetColor3d('Yellow'))

                    #self.ren.AddActor(self.y_actor)# remove comment for testing


                    self.ren.AddActor(self.obj_projection_arrow_actor)
                    self.ren.AddActor(self.object_orientation_torus_actor)
                    self.ball_actor.SetVisibility(0)
                    self.obj_projection_arrow_actor.SetPosition(closestPoint)
                    self.obj_projection_arrow_actor.SetOrientation(coil_dir)

                    self.object_orientation_torus_actor.SetPosition(closestPoint)
                    self.object_orientation_torus_actor.SetOrientation(coil_dir)

                    # change color of arrow and disk according to angle
                    if angle < self.angle_arrow_projection_threshold:
                        self.object_orientation_torus_actor.GetProperty().SetDiffuseColor([51/255,176/255,102/255])
                        self.obj_projection_arrow_actor.GetProperty().SetColor([55/255,120/255,163/255])
                    else:
                        self.object_orientation_torus_actor.GetProperty().SetDiffuseColor([240/255,146/255,105/255])
                        self.obj_projection_arrow_actor.GetProperty().SetColor([240/255,146/255,105/255])
                else:
                    self.ren.RemoveActor(self.y_actor)

        else:
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.ren.RemoveActor(self.x_actor)
            self.ball_actor.SetVisibility(1)


    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        self.tracts_status = vis_status[1]

        if self.nav_status:
            self.pTarget = self.CenterOfMass()
            if self.obj_actor:
                self.obj_actor.SetVisibility(self.show_object)
                #self.x_actor.SetVisibility(self.show_object)
                #self.y_actor.SetVisibility(self.show_object)
                #self.z_actor.SetVisibility(self.show_object)
                #self.object_orientation_torus_actor.SetVisibility(self.show_object)
                #self.obj_projection_arrow_actor.SetVisibility(self.show_object)
        self.camera_show_object = None
        self.UpdateRender()

    def UpdateSeedOffset(self, data):
        self.seed_offset = data

    def UpdateMarkerOffsetState(self, create=False):
        if create:
            if not self.mark_actor:
                self.mark_actor = self.add_marker([0., 0., 0.], color=[0., 1., 1.])
                self.ren.AddActor(self.mark_actor)
        else:
            if self.mark_actor:
                self.ren.RemoveActor(self.mark_actor)
                self.mark_actor = None
        self.UpdateRender()

    def UpdateObjectOrientation(self, m_img, coord):
        # print("Update object orientation")

        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]

        # translate coregistered coordinate to display a marker where Trekker seed is computed
        # coord_offset = m_img_flip[:3, -1] - self.seed_offset * m_img_flip[:3, 2]

        # print("m_img copy in viewer_vol: {}".format(m_img_copy))

        # m_img[:3, 0] is from posterior to anterior direction of the coil
        # m_img[:3, 1] is from left to right direction of the coil
        # m_img[:3, 2] is from bottom to up direction of the coil

        m_img_vtk = vtku.numpy_to_vtkMatrix4x4(m_img_flip)

        self.obj_actor.SetUserMatrix(m_img_vtk)
        # self.obj_axes.SetUserMatrix(m_rot_vtk)
        self.x_actor.SetUserMatrix(m_img_vtk)
        self.y_actor.SetUserMatrix(m_img_vtk)
        self.z_actor.SetUserMatrix(m_img_vtk)

    def UpdateObjectArrowOrientation(self, m_img, coord, flag):
        [coil_dir, norm, coil_norm, p1 ]= self.ObjectArrowLocation(m_img,coord)

        if flag:
            self.ren.RemoveActor(self.x_actor)
            #self.ren.RemoveActor(self.y_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator)
            self.ShowCoilProjection(intersectingCellIds, p1, coil_norm, coil_dir)

    def RemoveObjectActor(self):
        self.ren.RemoveActor(self.obj_actor)
        self.ren.RemoveActor(self.x_actor)
        self.ren.RemoveActor(self.y_actor)
        self.ren.RemoveActor(self.z_actor)
        self.ren.RemoveActor(self.mark_actor)
        self.ren.RemoveActor(self.obj_projection_arrow_actor)
        self.ren.RemoveActor(self.object_orientation_torus_actor)
        self.obj_actor = None
        self.x_actor = None
        self.y_actor = None
        self.z_actor = None
        self.mark_actor = None
        self.obj_projection_arrow_actor = None
        self.object_orientation_torus_actor = None

    def ConfigureObject(self, obj_name=None, polydata=None, use_default_object=True):
        self.obj_name = obj_name
        self.polydata = polydata
        self.use_default_object = use_default_object

        self.SaveConfig()

    def TrackObject(self, enabled):
        if enabled:
            if self.obj_name:
                if self.obj_actor:
                    self.RemoveObjectActor()
                self.AddObjectActor(self.obj_name)
        else:
            if self.obj_actor:
                self.RemoveObjectActor()
        if not self.nav_status:
            self.UpdateRender()

    def ShowObject(self, checked):
        self.show_object = checked
        if self.dummy_coil_actor is not None:
            self.dummy_coil_actor.SetVisibility(self.show_object)

        if self.obj_actor:
            self.obj_actor.SetVisibility(self.show_object)
            self.x_actor.SetVisibility(self.show_object)
            self.y_actor.SetVisibility(self.show_object)
            self.z_actor.SetVisibility(self.show_object)
            #if self.actor_peel:
            #    self.ball_actor.SetVisibility(0)
            #else:
            #    self.ball_actor.SetVisibility(1)

        if self.aim_actor is not None and self.show_object:
            self.aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)

        if not self.nav_status:
            self.UpdateRender()

    def OnUpdateTracts(self, root=None, affine_vtk=None, coord_offset=None, coord_offset_w=None):
        mapper = vtkCompositePolyDataMapper2()
        mapper.SetInputDataObject(root)

        self.actor_tracts = vtkActor()
        self.actor_tracts.SetMapper(mapper)
        self.actor_tracts.SetUserMatrix(affine_vtk)

        self.ren.AddActor(self.actor_tracts)
        if self.mark_actor:
            self.mark_actor.SetPosition(coord_offset)
        self.Refresh()

    def OnRemoveTracts(self):
        if self.actor_tracts:
            self.ren.RemoveActor(self.actor_tracts)
            self.actor_tracts = None
            self.Refresh()

    def ActivateRobotMode(self, robot_mode=None):
        if robot_mode:
            self.ren_robot = vtkRenderer()
            self.ren_robot.SetLayer(1)

            self.interactor.GetRenderWindow().AddRenderer(self.ren_robot)
            self.ren_robot.SetViewport(0.01, 0.19, 0.15, 0.39)
            filename = os.path.join(inv_paths.OBJ_DIR, "robot.stl")

            reader = vtkSTLReader()
            reader.SetFileName(filename)
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(reader.GetOutputPort())

            dummy_robot_actor = vtkActor()
            dummy_robot_actor.SetMapper(mapper)
            dummy_robot_actor.GetProperty().SetColor(1, 1, 1)
            dummy_robot_actor.GetProperty().SetOpacity(1.)
            self.dummy_robot_actor = dummy_robot_actor

            self.ren_robot.AddActor(dummy_robot_actor)
            self.ren_robot.InteractiveOff()

            self.UpdateRender()
        else:
            self.DisableRobotMode()

    def OnUpdateRobotStatus(self, robot_status):
        if self.dummy_robot_actor:
            if robot_status:
                self.dummy_robot_actor.GetProperty().SetColor(0, 1, 0)
            else:
                self.dummy_robot_actor.GetProperty().SetColor(1, 0, 0)

    def DisableRobotMode(self):
        if self.dummy_robot_actor:
            self.ren_robot.RemoveActor(self.dummy_robot_actor)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren_robot)
            self.UpdateRender()

    def __bind_events_wx(self):
        #self.Bind(wx.EVT_SIZE, self.OnSize)
        #  self.canvas.subscribe_event('LeftButtonPressEvent', self.on_insert_point)
        pass

    def on_insert_point(self, evt):
        pos = evt.position
        self.polygon.append_point(pos)
        self.canvas.Refresh()

        arr = self.canvas.draw_element_to_array([self.polygon,])
        imsave('/tmp/polygon.png', arr)

    def SetInteractorStyle(self, state):
        cleanup = getattr(self.style, 'CleanUp', None)
        if cleanup:
            self.style.CleanUp()

        del self.style

        style = styles.Styles.get_style(state)(self)

        setup = getattr(style, 'SetUp', None)
        if setup:
            style.SetUp()

        self.style = style
        self.interactor.SetInteractorStyle(style)

        self.UpdateRender()

        self.state = state

    def enable_style(self, style):
        if styles.Styles.has_style(style):
            new_state = self.interaction_style.AddState(style)
            self.SetInteractorStyle(new_state)
        else:
            new_state = self.interaction_style.RemoveState(style)
            self.SetInteractorStyle(new_state)

    def OnDisableStyle(self, style):
        new_state = self.interaction_style.RemoveState(style)
        self.SetInteractorStyle(new_state)

    def ResetCamClippingRange(self):
        self.ren.ResetCamera()
        self.ren.ResetCameraClippingRange()

    def SetVolumeCameraState(self, camera_state):
        self.camera_state = camera_state
        self.camera_show_object = None

    # def SetVolumeCamera(self, arg, position):
    def SetVolumeCamera(self, cam_focus):
        if self.camera_state:
            # TODO: exclude dependency on initial focus
            # cam_focus = np.array(bases.flip_x(position[:3]))
            # cam_focus = np.array(bases.flip_x(position))
            cam = self.ren.GetActiveCamera()

            if self.initial_focus is None:
                self.initial_focus = np.array(cam.GetFocalPoint())

            cam_pos0 = np.array(cam.GetPosition())
            cam_focus0 = np.array(cam.GetFocalPoint())
            v0 = cam_pos0 - cam_focus0
            v0n = np.sqrt(inner1d(v0, v0))

            if self.camera_show_object is None:
                self.camera_show_object = self.show_object

            if self.camera_show_object:
                v1 = np.array([cam_focus[0] - self.pTarget[0], cam_focus[1] - self.pTarget[1], cam_focus[2] - self.pTarget[2]])
            else:
                v1 = cam_focus - self.initial_focus

            v1n = np.sqrt(inner1d(v1, v1))
            if not v1n:
                v1n = 1.0
            cam_pos = (v1/v1n)*v0n + cam_focus

            cam.SetFocalPoint(cam_focus)
            cam.SetPosition(cam_pos)

        # It works without doing the reset. Check with trackers if there is any difference.
        # Need to be outside condition for sphere marker position update
        # self.ren.ResetCameraClippingRange()
        # self.ren.ResetCamera()

    def OnExportSurface(self, filename, filetype, convert_to_world=False):
        if filetype not in (const.FILETYPE_STL,
                            const.FILETYPE_VTP,
                            const.FILETYPE_PLY,
                            const.FILETYPE_STL_ASCII):
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)
                self._export_surface(win_filename, filetype)
            else:
                self._export_surface(filename, filetype)

    def _export_surface(self, filename, filetype):
        fileprefix = filename.split(".")[-2]
        renwin = self.interactor.GetRenderWindow()

        if filetype == const.FILETYPE_RIB:
            writer = vtkRIBExporter()
            writer.SetFilePrefix(fileprefix)
            writer.SetTexturePrefix(fileprefix)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_VRML:
            writer = vtkVRMLExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_X3D:
            writer = vtkX3DExporter()
            writer.SetInput(renwin)
            writer.SetFileName(filename)
            writer.Update()
            writer.Write()
        elif filetype == const.FILETYPE_OBJ:
            writer = vtkOBJExporter()
            writer.SetFilePrefix(fileprefix)
            writer.SetInput(renwin)
            writer.Write()
        elif filetype == const.FILETYPE_IV:
            writer = vtkIVExporter()
            writer.SetFileName(filename)
            writer.SetInput(renwin)
            writer.Write()

    def OnEnableBrightContrast(self):
        style = self.style
        style.AddObserver("MouseMoveEvent", self.OnMove)
        style.AddObserver("LeftButtonPressEvent", self.OnClick)
        style.AddObserver("LeftButtonReleaseEvent", self.OnRelease)

    def OnDisableBrightContrast(self):
        style = vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        self.style = style

    def OnSetWindowLevelText(self, ww, wl):
        if self.raycasting_volume:
            self.text.SetValue("WL: %d  WW: %d"%(wl, ww))
            #  self.canvas.modified = True

    def OnShowRaycasting(self):
        if not self.raycasting_volume:
            self.raycasting_volume = True
            # self._to_show_ball += 1
            # self._check_and_set_ball_visibility()
            if self.on_wl:
                self.text.Show()

    def OnHideRaycasting(self):
        self.raycasting_volume = False
        self.text.Hide()
        # self._to_show_ball -= 1
        # self._check_and_set_ball_visibility()

    def OnSize(self, evt):
        self.UpdateRender()
        self.Refresh()
        self.interactor.UpdateWindowUI()
        self.interactor.Update()
        evt.Skip()

    def ChangeBackgroundColour(self, colour):
        self.ren.SetBackground(colour[:3])
        self.UpdateRender()

    def LoadActor(self, actor):
        self.added_actor = 1
        ren = self.ren
        ren.AddActor(actor)

        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
            self.view_angle = 1
        else:
            ren.ResetCamera()
            ren.ResetCameraClippingRange()

        #self.ShowOrientationCube()
        self.UpdateRender()
        # self._to_show_ball += 1
        # self._check_and_set_ball_visibility()

        # make camera projection to parallel
        self.ren.GetActiveCamera().ParallelProjectionOn()

        # use the 3D surface actor for measurement calculations
        self.surface = actor
        self.EnableRuler()


    def RemoveActor(self, actor):
        utils.debug("RemoveActor")
        ren = self.ren
        ren.RemoveActor(actor)
        if not self.nav_status:
            self.UpdateRender()
        # self._to_show_ball -= 1
        # self._check_and_set_ball_visibility()

        # remove the ruler if visible
        if self.ruler:
            self.HideRuler()

    def RemoveAllActor(self):
        utils.debug("RemoveAllActor")
        self.ren.RemoveAllProps()
        Publisher.sendMessage('Render volume viewer')

    def LoadSlicePlane(self):
        self.slice_plane = SlicePlane()

    def LoadVolume(self, volume, colour, ww, wl):
        self.raycasting_volume = True
        # self._to_show_ball += 1
        # self._check_and_set_ball_visibility()

        self.light = self.ren.GetLights().GetNextItem()

        self.ren.AddVolume(volume)
        self.text.SetValue("WL: %d  WW: %d"%(wl, ww))

        if self.on_wl:
            self.text.Show()
        else:
            self.text.Hide()

        self.ren.SetBackground(colour)

        if not (self.view_angle):
            self.SetViewAngle(const.VOL_FRONT)
        else:
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()

        self.UpdateRender()

        # make camera projection to parallel
        self.ren.GetActiveCamera().ParallelProjectionOn()

        # if there is no 3D surface, use the volume render for measurement calculation
        if not self.added_actor:
            self.surface = volume
        self.EnableRuler()

    def UnloadVolume(self, volume):
        self.ren.RemoveVolume(volume)
        del volume
        self.raycasting_volume = False
        # self._to_show_ball -= 1
        # self._check_and_set_ball_visibility()

        # remove the ruler if visible
        if self.ruler:
            self.HideRuler()

    def load_mask_preview(self, mask_3d_actor, flag=True):
        if flag:
            self.ren.AddVolume(mask_3d_actor)
        else:
            self.ren.RemoveVolume(mask_3d_actor)

        if self.ren.GetActors().GetNumberOfItems() == 0 and self.ren.GetVolumes().GetNumberOfItems() == 1:
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()

    def remove_mask_preview(self, mask_3d_actor):
        self.ren.RemoveVolume(mask_3d_actor)

    def OnSetViewAngle(self, view):
        self.SetViewAngle(view)

    def SetViewAngle(self, view):
        cam = self.ren.GetActiveCamera()
        cam.SetFocalPoint(0,0,0)

        proj = prj.Project()
        orig_orien = proj.original_orientation

        xv,yv,zv = const.VOLUME_POSITION[const.AXIAL][0][view]
        xp,yp,zp = const.VOLUME_POSITION[const.AXIAL][1][view]

        cam.SetViewUp(xv,yv,zv)
        cam.SetPosition(xp,yp,zp)

        self.ren.ResetCameraClippingRange()
        self.ren.ResetCamera()
        if not self.nav_status:
            self.UpdateRender()

    def ShowOrientationCube(self):
        cube = vtkAnnotatedCubeActor()
        cube.GetXMinusFaceProperty().SetColor(1,0,0)
        cube.GetXPlusFaceProperty().SetColor(1,0,0)
        cube.GetYMinusFaceProperty().SetColor(0,1,0)
        cube.GetYPlusFaceProperty().SetColor(0,1,0)
        cube.GetZMinusFaceProperty().SetColor(0,0,1)
        cube.GetZPlusFaceProperty().SetColor(0,0,1)
        cube.GetTextEdgesProperty().SetColor(0,0,0)

        # anatomic labelling
        cube.SetXPlusFaceText ("A")
        cube.SetXMinusFaceText("P")
        cube.SetYPlusFaceText ("L")
        cube.SetYMinusFaceText("R")
        cube.SetZPlusFaceText ("S")
        cube.SetZMinusFaceText("I")

        axes = vtkAxesActor()
        axes.SetShaftTypeToCylinder()
        axes.SetTipTypeToCone()
        axes.SetXAxisLabelText("X")
        axes.SetYAxisLabelText("Y")
        axes.SetZAxisLabelText("Z")
        #axes.SetNormalizedLabelPosition(.5, .5, .5)

        orientation_widget = vtkOrientationMarkerWidget()
        orientation_widget.SetOrientationMarker(cube)
        orientation_widget.SetViewport(0.85,0.85,1.0,1.0)
        #orientation_widget.SetOrientationMarker(axes)
        orientation_widget.SetInteractor(self.interactor)
        orientation_widget.SetEnabled(1)
        orientation_widget.On()
        orientation_widget.InteractiveOff()

    def UpdateRender(self):
        self.interactor.Render()

    def SetWidgetInteractor(self, widget=None):
        widget.SetInteractor(self.interactor._Iren)

    def AppendActor(self, actor):
        self.ren.AddActor(actor)

    def Reposition3DPlane(self, plane_label):
        if not(self.added_actor) and not(self.raycasting_volume):
            if not(self.repositioned_axial_plan) and (plane_label == 'Axial'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_axial_plan = 1

            elif not(self.repositioned_sagital_plan) and (plane_label == 'Sagital'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_sagital_plan = 1

            elif not(self.repositioned_coronal_plan) and (plane_label == 'Coronal'):
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_coronal_plan = 1

    # def _check_and_set_ball_visibility(self):
    #     #TODO: When creating Raycasting volume and cross is pressed, it is not
    #     # automatically creating the ball reference.
    #     # print("mode_cross, show_ball, ball_vis ", self._mode_cross, self._to_show_ball, self._ball_ref_visibility)
    #     if self._mode_cross:
    #         if self._to_show_ball > 0 and not self._ball_ref_visibility:
    #             self.ActivateBallReference()
    #             self.interactor.Render()
    #         elif not self._to_show_ball and self._ball_ref_visibility:
    #             self.RemoveBallReference()
    #             self.interactor.Render()

class SlicePlane:
    def __init__(self):
        project = prj.Project()
        self.original_orientation = project.original_orientation
        self.Create()
        self.enabled = False
        self.__bind_evt()

    def __bind_evt(self):
        Publisher.subscribe(self.Enable, 'Enable plane')
        Publisher.subscribe(self.Disable, 'Disable plane')
        Publisher.subscribe(self.ChangeSlice, 'Change slice from slice plane')
        Publisher.subscribe(self.UpdateAllSlice, 'Update all slice')

    def Create(self):
        plane_x = self.plane_x = vtkImagePlaneWidget()
        plane_x.InteractionOff()
        #Publisher.sendMessage('Input Image in the widget', 
                                                #(plane_x, 'SAGITAL'))
        plane_x.SetPlaneOrientationToXAxes()
        plane_x.TextureVisibilityOn()
        plane_x.SetLeftButtonAction(0)
        plane_x.SetRightButtonAction(0)
        plane_x.SetMiddleButtonAction(0)
        cursor_property = plane_x.GetCursorProperty()
        cursor_property.SetOpacity(0)

        plane_y = self.plane_y = vtkImagePlaneWidget()
        plane_y.DisplayTextOff()
        #Publisher.sendMessage('Input Image in the widget', 
                                                #(plane_y, 'CORONAL'))
        plane_y.SetPlaneOrientationToYAxes()
        plane_y.TextureVisibilityOn()
        plane_y.SetLeftButtonAction(0)
        plane_y.SetRightButtonAction(0)
        plane_y.SetMiddleButtonAction(0)
        prop1 = plane_y.GetPlaneProperty()
        cursor_property = plane_y.GetCursorProperty()
        cursor_property.SetOpacity(0) 

        plane_z = self.plane_z = vtkImagePlaneWidget()
        plane_z.InteractionOff()
        #Publisher.sendMessage('Input Image in the widget', 
                                                #(plane_z, 'AXIAL'))
        plane_z.SetPlaneOrientationToZAxes()
        plane_z.TextureVisibilityOn()
        plane_z.SetLeftButtonAction(0)
        plane_z.SetRightButtonAction(0)
        plane_z.SetMiddleButtonAction(0)
       
        cursor_property = plane_z.GetCursorProperty()
        cursor_property.SetOpacity(0) 


        prop3 = plane_z.GetPlaneProperty()
        prop3.SetColor(1, 0, 0)
        
        selected_prop3 = plane_z.GetSelectedPlaneProperty() 
        selected_prop3.SetColor(1,0,0)
    
        prop1 = plane_x.GetPlaneProperty()
        prop1.SetColor(0, 0, 1)

        selected_prop1 = plane_x.GetSelectedPlaneProperty()           
        selected_prop1.SetColor(0, 0, 1)
        
        prop2 = plane_y.GetPlaneProperty()
        prop2.SetColor(0, 1, 0)

        selected_prop2 = plane_y.GetSelectedPlaneProperty()           
        selected_prop2.SetColor(0, 1, 0)

        Publisher.sendMessage('Set Widget Interactor', widget=plane_x)
        Publisher.sendMessage('Set Widget Interactor', widget=plane_y)
        Publisher.sendMessage('Set Widget Interactor', widget=plane_z)

        self.Render()

    def Enable(self, plane_label=None):
        if plane_label:
            if(plane_label == "Axial"):
                self.plane_z.On()
            elif(plane_label == "Coronal"):
                self.plane_y.On()
            elif(plane_label == "Sagital"):
                self.plane_x.On()
            Publisher.sendMessage('Reposition 3D Plane', plane_label=plane_label)
        else:
            self.plane_z.On()
            self.plane_x.On()
            self.plane_y.On()
            Publisher.sendMessage('Set volume view angle',
                                  view=const.VOL_ISO)
        self.Render()

    def Disable(self, plane_label=None):
        if plane_label:
            if(plane_label == "Axial"):
                self.plane_z.Off()
            elif(plane_label == "Coronal"):
                self.plane_y.Off()
            elif(plane_label == "Sagital"):
                self.plane_x.Off()
        else:
            self.plane_z.Off()
            self.plane_x.Off()
            self.plane_y.Off()

        self.Render()

    def Render(self):
        Publisher.sendMessage('Render volume viewer')    

    def ChangeSlice(self, orientation, index):
        if  orientation == "CORONAL" and self.plane_y.GetEnabled():
            Publisher.sendMessage('Update slice 3D',
                                  widget=self.plane_y,
                                  orientation=orientation)
            self.Render()
        elif orientation == "SAGITAL" and self.plane_x.GetEnabled():
            Publisher.sendMessage('Update slice 3D', 
                                  widget=self.plane_x,
                                  orientation=orientation)
            self.Render()
        elif orientation == 'AXIAL' and self.plane_z.GetEnabled() :
            Publisher.sendMessage('Update slice 3D',
                                  widget=self.plane_z,
                                  orientation=orientation)
            self.Render()

    def UpdateAllSlice(self):
        Publisher.sendMessage('Update slice 3D',
                              widget=self.plane_y,
                              orientation="CORONAL")
        Publisher.sendMessage('Update slice 3D',
                              widget=self.plane_x,
                              orientation="SAGITAL")
        Publisher.sendMessage('Update slice 3D',
                              widget=self.plane_z,
                              orientation="AXIAL")

    def DeletePlanes(self):
        del self.plane_x
        del self.plane_y
        del self.plane_z

