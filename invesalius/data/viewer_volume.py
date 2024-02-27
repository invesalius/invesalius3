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
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.data.markers.marker_viewer import MarkerViewer
from invesalius.data.markers.surface_geometry import SurfaceGeometry
from invesalius.data.actor_factory import ActorFactory
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
from invesalius.i18n import tr as _

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
        self.surface_added = False

        self.lock_to_coil = const.LOCK_TO_COIL_AS_DEFAULT
        self.camera_show_object = None

        self.nav_status = False

        # Pointer is the ball that is shown to indicate the 3D point in the volume viewer that corresponds to the
        # selected slice positions. The same pointer is also used to show the point selected from the 3D viewer by
        # right-clicking on it.
        self.pointer_actor = None

        # The actor for showing the actual coil in the volume viewer.
        self.coil_actor = None

        # The actor for showing the center of the actual coil in the volume viewer.
        self.coil_center_actor = None

        # The actor for showing the target coil in the volume viewer.
        self.target_coil_actor = None

        self.obj_axes = None
        self.obj_name = False
        self.show_coil = False
        self.coil_actor_list = None
        self.arrow_actor_list = None
        self.pTarget = [0., 0., 0.]

        self.distance_text = None

        # self.obj_axes = None
        self.x_actor = None
        self.y_actor = None
        self.z_actor = None
        self.mark_actor = None
        self.obj_projection_arrow_actor = None
        self.object_orientation_torus_actor = None
        self._to_show_ball = 0
        self.highlighted_marker_index = None

        self.probe = False
        self.ref = False
        self.obj = False

        self.target_coord = None
        self.active_aim_actor = None

        self.dummy_robot_actor = None
        self.dummy_probe_actor = None
        self.dummy_ref_actor = None
        self.dummy_obj_actor = None
        self.target_mode = False
        self.polydata = None
        self.use_default_object = True
        self.anglethreshold = const.COIL_ANGLES_THRESHOLD
        self.distance_threshold = const.COIL_COORD_THRESHOLD
        self.angle_arrow_projection_threshold = const.COIL_ANGLE_ARROW_PROJECTION_THRESHOLD

        self.actor_tracts = None
        self.actor_peel = None

        self.surface = None

        self.surface_geometry = SurfaceGeometry()
        self.projection_actor = None

        # An object that can be used to create actors, such as lines, arrows, and spheres.
        self.actor_factory = ActorFactory()

        # An object that can be used to manage the highlighting of markers in the 3D viewer. Later this class could be
        # extended to handle other marker-related functionality, such as adding and removing markers, etc.
        self.marker_viewer = MarkerViewer(
            renderer=self.ren,
            actor_factory=self.actor_factory,
        )

        self.seed_offset = const.SEED_OFFSET
        self.radius_list = vtkIdList()
        self.colors_init = vtkUnsignedCharArray()
        self.plot_no_connection = False

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
        self.SpreadEfieldFactorTextActor = None
        self.mTMSCoordTextActor = None
        self.EfieldAtTargetLegend = None
        self.ClusterEfieldTextActor = None
        self.enableefieldabovethreshold = False
        self.efield_tools = False
        self.save_automatically = False
        self.positions_above_threshold = None
        self.cell_id_indexes_above_threshold = None
        self.LoadConfig()

    def UpdateCanvas(self):
        if self.canvas is not None:
            self.canvas.modified = True
            if not self.nav_status:
                self.UpdateRender()

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
        Publisher.subscribe(self.AddSurface,
                                 'Load surface actor into viewer')
        Publisher.subscribe(self.RemoveSurface,
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

        Publisher.subscribe(self.SetLockToCoil, 'Lock to coil')

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

        Publisher.subscribe(self.RemoveAllActors, 'Remove all volume actors')

        Publisher.subscribe(self.OnExportPicture,'Export picture to file')

        Publisher.subscribe(self.OnStartSeed,'Create surface by seeding - start')
        Publisher.subscribe(self.OnEndSeed,'Create surface by seeding - end')

        Publisher.subscribe(self.SetStereoMode, 'Set stereo mode')

        Publisher.subscribe(self.Reposition3DPlane, 'Reposition 3D Plane')

        Publisher.subscribe(self.UpdatePointer, 'Update volume viewer pointer')

        Publisher.subscribe(self.RemoveVolume, 'Remove Volume')
        Publisher.subscribe(self.UpdateCamera, 'Update camera')

        Publisher.subscribe(self.OnSensors, 'Sensors ID')
        Publisher.subscribe(self.OnRemoveSensorsID, 'Remove sensors ID')

        # Related to marker creation in navigation tools
        Publisher.subscribe(self.AddMarker, 'Add marker')
        Publisher.subscribe(self.UpdateMarker, 'Update marker')
        Publisher.subscribe(self.HideAllMarkers, 'Hide all markers')
        Publisher.subscribe(self.ShowAllMarkers, 'Show all markers')
        Publisher.subscribe(self.RemoveAllMarkers, 'Remove all markers')
        Publisher.subscribe(self.RemoveMultipleMarkers, 'Remove multiple markers')
        Publisher.subscribe(self.HighlightMarker, 'Highlight marker')
        Publisher.subscribe(self.UnhighlightMarker, 'Unhighlight marker')
        Publisher.subscribe(self.SetNewColor, 'Set new color')
        Publisher.subscribe(self.SetMarkers, 'Set markers')

        # Related to UI state
        Publisher.subscribe(self.ShowCoil, 'Show coil in viewer volume')

        # Related to object tracking during neuronavigation
        Publisher.subscribe(self.OnNavigationStatus, 'Navigation status')
        Publisher.subscribe(self.UpdateCoilPose, 'Update object matrix')
        Publisher.subscribe(self.UpdateArrowPose, 'Update object arrow matrix')
        Publisher.subscribe(self.UpdateEfieldPointLocation, 'Update point location for e-field calculation')
        Publisher.subscribe(self.GetEnorm, 'Get enorm')
        Publisher.subscribe(self.ConfigureObject, 'Configure object')
        Publisher.subscribe(self.TrackObject, 'Track object')

        Publisher.subscribe(self.ActivateTargetMode, 'Target navigation mode')
        Publisher.subscribe(self.OnUpdateObjectTargetGuide, 'Update object matrix')
        Publisher.subscribe(self.OnSetNewTarget, 'Update target')
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
        Publisher.subscribe(self.OnUpdateRobotStatus, 'Update robot status')
        Publisher.subscribe(self.GetCoilPosition, 'Calculate position and rotation')
        Publisher.subscribe(self.CreateCortexProjectionOnScalp, 'Send efield target position on brain')
        Publisher.subscribe(self.UpdateEfieldThreshold, 'Update Efield Threshold')
        Publisher.subscribe(self.UpdateEfieldROISize, 'Update Efield ROI size')
        Publisher.subscribe(self.SetEfieldTargetAtCortex, 'Set as Efield target at cortex')
        Publisher.subscribe(self.EnableShowEfieldAboveThreshold, 'Show area above threshold')
        Publisher.subscribe(self.EnableEfieldTools, 'Enable Efield tools')
        Publisher.subscribe(self.ClearTargetAtCortex, 'Clear efield target at cortex')
        Publisher.subscribe(self.CoGEforCortexMarker, 'Get Cortex position')
        Publisher.subscribe(self.AddCortexMarkerActor, 'Add cortex marker actor')
        Publisher.subscribe(self.CortexMarkersVisualization, 'Display efield markers at cortex')
        Publisher.subscribe(self.GetTargetPositions, 'Get targets Ids for mtms')
        Publisher.subscribe(self.GetTargetPathmTMS, 'Send targeting file path')
        Publisher.subscribe(self.GetdIsfromCoord,'Send mtms coords')
        Publisher.subscribe(self.EnableSaveAutomaticallyEfieldData, 'Save automatically efield data')

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

        # Automatically enable and press 'Track object' button and unpress 'Lock to coil' button.
        Publisher.sendMessage('Enable track object button', enabled=True)
        Publisher.sendMessage('Press track object button', pressed=True)
        Publisher.sendMessage('Press lock to coil button', pressed=False)
        Publisher.sendMessage('Press target mode button', pressed=False)

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

    def CreatePointer(self):
        """
        Create pointer and add it to the renderer.
        
        The pointer refers to the ball that is shown to indicate the 3D point in the volume viewer that corresponds to the
        selected slice positions. The same pointer is also used to show the point selected from the 3D viewer by right-clicking on it.
        """
        if not self.pointer_actor:
            actor = self.actor_factory.CreatePointer()

            # Store the pointer actor.
            self.pointer_actor = actor        
            
            # Add the actor to the renderer.
            self.ren.AddActor(actor)

        self.UpdateRender()

    def DeletePointer(self):
        if self.pointer_actor:
            self.ren.RemoveActor(self.pointer_actor)
            self.pointer_actor = None
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
        self.RemoveAllMarkers()

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

    def AddMarker(self, marker):
        """
        Add a marker created by navigation tools for the volume viewer to be render.
        """
        marker_id = marker.marker_id
        marker_type = marker.marker_type
        position = marker.position
        orientation = marker.orientation
        colour = marker.colour
        size = marker.size
        cortex_marker = marker.cortex_position_orientation

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]
        
        # For 'fiducial' type markers, create a ball. TODO: This could be changed to something more distinctive.
        if marker_type == MarkerType.FIDUCIAL:
            actor = self.actor_factory.CreateBall(position_flipped, colour, size)

        # For 'landmark' type markers, create a ball.
        elif marker_type == MarkerType.LANDMARK:
            actor = self.actor_factory.CreateBall(position_flipped, colour, size)

        # For 'brain target' type markers, create an arrow.
        elif marker_type == MarkerType.BRAIN_TARGET:
            actor = self.actor_factory.CreateArrowUsingDirection(position_flipped, orientation, colour, const.ARROW_MARKER_SIZE)

        # For 'coil target' type markers, create a crosshair.
        elif marker_type == MarkerType.COIL_TARGET:
            actor = self.actor_factory.CreateAim(position_flipped, orientation, colour)

        # For 'coil' type markers, create a smaller crosshair; they are generated when pulses are
        # given; hence, they easily clutter the volume viewer if they are too big.
        elif marker_type == MarkerType.COIL_POSE:
            actor = self.actor_factory.CreateAim(position_flipped, orientation, colour, scale=0.3)

        # For 'electric field target' type markers, create an arrow.
        elif marker_type == MarkerType.ELECTRIC_FIELD_TARGET:
            actor = self.actor_factory.CreateArrowUsingDirection(position_flipped, orientation, colour, const.ARROW_MARKER_SIZE)
            if cortex_marker[0] is not None:
                Publisher.sendMessage('Add cortex marker actor', position_orientation=cortex_marker, marker_id=marker_id)

        else:
            assert False, "Invalid marker type."

        # Add marker to the list of all markers.
        self.static_markers.append(
            {
                "marker_id": marker_id,
                "actor": actor,
                "position": position_flipped,
                "orientation": orientation,
                "colour": colour,
                "marker_type": marker_type,
                "highlighted": False,
            }
        )
        self.ren.AddActor(actor)

    def UpdateMarker(self, index, position, orientation):
        """
        Update the position and orientation of a marker.
        """
        marker = self.static_markers[index]
        
        actor = marker["actor"]
        colour = marker["colour"]
        highlighted = marker["highlighted"]

        position_flipped = list(position)
        position_flipped[1] = -position_flipped[1]

        # XXX: Workaround because modifying the original actor does not seem to work using
        #   method UpdatePositionAndOrientation in ActorFactory; instead, create a new actor
        #   and remove the old one. This only works for coil target markers, as the new actor
        #   created is of a fixed type (aim).
        new_actor = self.actor_factory.CreateAim(position_flipped, orientation, colour)

        if highlighted:
            self.marker_viewer.UnhighlightMarker()

        marker["actor"] = new_actor
        marker["position"] = position_flipped
        marker["orientation"] = orientation

        self.ren.RemoveActor(actor)
        self.ren.AddActor(new_actor)

        if highlighted:
            self.marker_viewer.HighlightMarker(marker)

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
            actor = self.static_markers[i]["actor"]
            actor.SetVisibility(0)

        self.UpdateRender()

    def ShowAllMarkers(self, indexes):
        ballid = indexes
        for i in range(0, ballid):
            actor = self.static_markers[i]["actor"]
            actor.SetVisibility(1)

        self.UpdateRender()

    def RemoveAllMarkers(self):
        num_of_markers = len(self.static_markers)
        for i in range(num_of_markers):
            actor = self.static_markers[i]["actor"]
            self.ren.RemoveActor(actor)
        self.static_markers = []

        if len(self.static_markers_efield) > 0:
            for i in range(len(self.static_markers_efield)):
                self.ren.RemoveActor(self.static_markers_efield[i][0])
            self.static_markers_efield= []

        self.UpdateRender()

    def RemoveMultipleMarkers(self, indexes):
        for i in reversed(indexes):

            # TODO: Not sure what this is doing, it should be cleaned up.
            if len(self.static_markers_efield) > 0:
                index = [h for h, row in enumerate(self.static_markers_efield) if row[1] == i]
                if index:
                    index = int(index[0])
                    self.ren.RemoveActor(self.static_markers_efield[index][0])
                    del self.static_markers_efield[index]
                if i != len(self.static_markers)-1:
                    for j in range(len(self.static_markers_efield)):
                        self.static_markers_efield[j][1] -= 1

            actor = self.static_markers[i]["actor"]
            self.ren.RemoveActor(actor)

            del self.static_markers[i]

        self.UpdateRender()

    def HighlightMarker(self, index):
        # Return early in case the index is out of bounds.
        if index >= len(self.static_markers) or index < 0:
            return

        marker = self.static_markers[index]

        self.marker_viewer.HighlightMarker(marker)
        self.UpdateRender()

    def UnhighlightMarker(self):
        self.marker_viewer.UnhighlightMarker()
        self.UpdateRender()

    def SetNewColor(self, index, color):
        actor = self.static_markers[index]["actor"]
        actor.GetProperty().SetColor([round(s / 255.0, 3) for s in color])

        self.UpdateRender()

    def OnTargetMarkerTransparency(self, status, index):
        actor = self.static_markers[index]["actor"]
        if status:
            actor.GetProperty().SetOpacity(1)
            # actor.GetProperty().SetOpacity(0.4)
        else:
            actor.GetProperty().SetOpacity(1)

    def OnUpdateAngleThreshold(self, angle):
        self.anglethreshold = angle

    def OnUpdateDistThreshold(self, dist_threshold):
        self.distance_threshold = dist_threshold

    def IsTargetMode(self):
        return self.target_mode

    def ActivateTargetMode(self, evt=None, target_mode=False):
        vtk_colors = vtkNamedColors()
        self.target_mode = target_mode

        if self.target_coord and self.target_mode:
            # Set the transformation matrix for the target.
            self.m_target = self.CreateVTKObjectMatrix(self.target_coord[:3], self.target_coord[3:])

            if self.actor_peel:
                self.object_orientation_torus_actor.SetVisibility(0)
                self.obj_projection_arrow_actor.SetVisibility(0)
            self.CreateTargetAim()

            # Create a line
            self.ren.SetViewport(0, 0, 0.75, 1)
            self.ren2 = vtkRenderer()

            self.interactor.GetRenderWindow().AddRenderer(self.ren2)
            self.ren2.SetViewport(0.75, 0, 1, 1)

            # Remove the previous actor for 'distance' text
            if self.distance_text is not None:
                self.ren.RemoveActor(self.distance_text.actor)

            # Create new actor for 'distance' text
            distance_text = self.CreateDistanceText()
            self.ren.AddActor(distance_text.actor)

            # Store the object for 'distance' text so it can be modified when distance changes.
            self.distance_text = distance_text

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

            arrow_roll_z1 = self.actor_factory.CreateArrow([-50, -35, 12], [-50, -35, 50])
            arrow_roll_z1.GetProperty().SetColor(1, 1, 0)
            arrow_roll_z1.RotateX(-60)
            arrow_roll_z1.RotateZ(180)
            arrow_roll_z2 = self.actor_factory.CreateArrow([50, -35, 0], [50, -35, -50])
            arrow_roll_z2.GetProperty().SetColor(1, 1, 0)
            arrow_roll_z2.RotateX(-60)
            arrow_roll_z2.RotateZ(180)

            arrow_yaw_y1 = self.actor_factory.CreateArrow([-50, -35, 0], [-50, 5, 0])
            arrow_yaw_y1.GetProperty().SetColor(0, 1, 0)
            arrow_yaw_y1.SetPosition(0, -150, 0)
            arrow_yaw_y1.RotateZ(180)
            arrow_yaw_y2 = self.actor_factory.CreateArrow([50, -35, 0], [50, -75, 0])
            arrow_yaw_y2.GetProperty().SetColor(0, 1, 0)
            arrow_yaw_y2.SetPosition(0, -150, 0)
            arrow_yaw_y2.RotateZ(180)

            arrow_pitch_x1 = self.actor_factory.CreateArrow([0, 65, 38], [0, 65, 68])
            arrow_pitch_x1.GetProperty().SetColor(1, 0, 0)
            arrow_pitch_x1.SetPosition(0, -300, 0)
            arrow_pitch_x1.RotateY(90)
            arrow_pitch_x1.RotateZ(180)
            arrow_pitch_x2 = self.actor_factory.CreateArrow([0, -55, 5], [0, -55, -30])
            arrow_pitch_x2.GetProperty().SetColor(1, 0, 0)
            arrow_pitch_x2.SetPosition(0, -300, 0)
            arrow_pitch_x2.RotateY(90)
            arrow_pitch_x2.RotateZ(180)

            self.coil_actor_list = obj_roll, obj_yaw, obj_pitch
            self.arrow_actor_list = arrow_roll_z1, arrow_roll_z2, arrow_yaw_y1, arrow_yaw_y2,\
                                     arrow_pitch_x1, arrow_pitch_x2

            for ind in self.coil_actor_list:
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
            distance_to_target = distance.euclidean(coord[0:3],
                                             (self.target_coord[0], -self.target_coord[1], self.target_coord[2]))
            # self.txt.SetCoilDistanceValue(distance_to_target)

            formatted_distance = "Distance: {: >5.1f} mm".format(distance_to_target)
            self.distance_text.SetValue(formatted_distance)

            self.ren.ResetCamera()
            self.SetCameraTarget()
            if distance_to_target > 100:
                distance_to_target = 100
            # ((-0.0404*dst) + 5.0404) is the linear equation to normalize the zoom between 1 and 5 times with
            # the distance between 1 and 100 mm
            self.ren.GetActiveCamera().Zoom((-0.0404 * distance_to_target) + 5.0404)

            if distance_to_target <= self.distance_threshold:
                is_under_distance_threshold = True
                self.active_aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                if not self.show_coil:
                    self.active_aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_HIDDEN_OPACITY)
            else:
                is_under_distance_threshold = False
                self.active_aim_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Yellow'))
                self.active_aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)

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
                is_under_x_angle_threshold = True
                # self.coil_actor_list[0].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.coil_actor_list[0].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_x_angle_threshold = False
                # self.coil_actor_list[0].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
                self.coil_actor_list[0].GetProperty().SetColor(1, 1, 1)

            offset = 5

            arrow_roll_x1 = self.actor_factory.CreateArrow([-55, -35, offset], [-55, -35, offset - coordrx_arrow])
            arrow_roll_x1.RotateX(-60)
            arrow_roll_x1.RotateZ(180)
            arrow_roll_x1.GetProperty().SetColor(1, 1, 0)

            arrow_roll_x2 = self.actor_factory.CreateArrow([55, -35, offset], [55, -35, offset + coordrx_arrow])
            arrow_roll_x2.RotateX(-60)
            arrow_roll_x2.RotateZ(180)
            arrow_roll_x2.GetProperty().SetColor(1, 1, 0)

            if self.anglethreshold * const.ARROW_SCALE > coordrz_arrow > -self.anglethreshold * const.ARROW_SCALE:
                is_under_z_angle_threshold = True
                # self.coil_actor_list[1].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.coil_actor_list[1].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_z_angle_threshold = False
                # self.coil_actor_list[1].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
                self.coil_actor_list[1].GetProperty().SetColor(1, 1, 1)

            offset = -35

            arrow_yaw_z1 = self.actor_factory.CreateArrow([-55, offset, 0], [-55, offset - coordrz_arrow, 0])
            arrow_yaw_z1.SetPosition(0, -150, 0)
            arrow_yaw_z1.RotateZ(180)
            arrow_yaw_z1.GetProperty().SetColor(0, 1, 0)

            arrow_yaw_z2 = self.actor_factory.CreateArrow([55, offset, 0], [55, offset + coordrz_arrow, 0])
            arrow_yaw_z2.SetPosition(0, -150, 0)
            arrow_yaw_z2.RotateZ(180)
            arrow_yaw_z2.GetProperty().SetColor(0, 1, 0)

            if self.anglethreshold * const.ARROW_SCALE > coordry_arrow > -self.anglethreshold * const.ARROW_SCALE:
                is_under_y_angle_threshold = True
                #self.coil_actor_list[2].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('Green'))
                self.coil_actor_list[2].GetProperty().SetColor(0, 1, 0)
            else:
                is_under_y_angle_threshold = False
                #self.coil_actor_list[2].GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('GhostWhite'))
                self.coil_actor_list[2].GetProperty().SetColor(1, 1, 1)

            offset = 38
            arrow_pitch_y1 = self.actor_factory.CreateArrow([0, 65, offset], [0, 65, offset + coordry_arrow])
            arrow_pitch_y1.SetPosition(0, -300, 0)
            arrow_pitch_y1.RotateY(90)
            arrow_pitch_y1.RotateZ(180)
            arrow_pitch_y1.GetProperty().SetColor(1, 0, 0)

            offset = 5
            arrow_pitch_y2 = self.actor_factory.CreateArrow([0, -55, offset], [0, -55, offset - coordry_arrow])
            arrow_pitch_y2.SetPosition(0, -300, 0)
            arrow_pitch_y2.RotateY(90)
            arrow_pitch_y2.RotateZ(180)
            arrow_pitch_y2.GetProperty().SetColor(1, 0, 0)

            # Combine all the conditions to check if the coil is at the target.
            coil_at_target = is_under_distance_threshold and \
                             is_under_x_angle_threshold and \
                             is_under_y_angle_threshold and \
                             is_under_z_angle_threshold

            wx.CallAfter(Publisher.sendMessage, 'Coil at target', state=coil_at_target)

            # Set the color of the coil actors based on whether the coil is at the target or not.
            coil_actor_color = vtk_colors.GetColor3d('Green') if coil_at_target else vtk_colors.GetColor3d('DarkOrange')

            # Set the color of both target coil (representing the target) and the coil center (representing the actual coil).
            self.target_coil_actor.GetProperty().SetDiffuseColor(coil_actor_color)
            self.coil_center_actor.GetProperty().SetDiffuseColor(coil_actor_color)

            self.arrow_actor_list = arrow_roll_x1, arrow_roll_x2, arrow_yaw_z1, arrow_yaw_z2, \
                                    arrow_pitch_y1, arrow_pitch_y2

            for ind in self.arrow_actor_list:
                self.ren2.AddActor(ind)

    def OnSetNewTarget(self, coord):
        if coord is not None:
            # Store the new target coordinates and create a new transformation matrix for the target.
            self.target_coord = coord
            self.m_target = self.CreateVTKObjectMatrix(coord[:3], coord[3:])

            self.CreateTargetAim()
            Publisher.sendMessage('Target selected', status=True)
            print("Target updated to coordinates {}".format(coord))

    def RemoveTarget(self):
        self.target_mode = False
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
        if self.active_aim_actor:
            self.RemoveTargetAim()
            self.active_aim_actor = None

        vtk_colors = vtkNamedColors()

        aim_actor = self.actor_factory.CreateAim(self.target_coord[:3], self.target_coord[3:], vtk_colors.GetColor3d('DarkOrange'))

        # Store the currently active aim actor.
        self.active_aim_actor = aim_actor

        # Add the aim actor to the renderer.
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

        self.target_coil_actor = vtkActor()
        self.target_coil_actor.SetMapper(obj_mapper)
        self.target_coil_actor.GetProperty().SetDiffuseColor(vtk_colors.GetColor3d('DarkOrange'))
        self.target_coil_actor.GetProperty().SetSpecular(0.5)
        self.target_coil_actor.GetProperty().SetSpecularPower(10)
        self.target_coil_actor.GetProperty().SetOpacity(.3)
        self.target_coil_actor.SetVisibility(self.show_coil)
        self.target_coil_actor.SetUserMatrix(self.m_target)

        self.ren.AddActor(self.target_coil_actor)
        if not self.nav_status:
            self.UpdateRender()

    def RemoveTargetAim(self):
        self.ren.RemoveActor(self.active_aim_actor)
        self.ren.RemoveActor(self.target_coil_actor)
        if not self.nav_status:
            self.UpdateRender()

    def CreateDistanceText(self):
        distance_text = vtku.Text()

        distance_text.SetSize(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION)
        distance_text.SetPosition((const.X, 1.-const.Y))
        distance_text.SetVerticalJustificationToBottom()
        distance_text.BoldOn()

        return distance_text

    def DisableCoilTracker(self):
        try:
            self.ren.SetViewport(0, 0, 1, 1)
            self.interactor.GetRenderWindow().RemoveRenderer(self.ren2)
            self.SetViewAngle(const.VOL_FRONT)
            self.ren.RemoveActor(self.distance_text.actor)
            self.CreateTargetAim()
            if not self.nav_status:
                self.UpdateRender()
        except:
            None

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
        newvtk.Multiply4x4(self.m_target, oldcamVTK, newvtk)

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

    def UpdatePointer(self, position):
        """
        When not navigating, update the position of the pointer sphere. It is done
        when the slice planes are moved or a new point is selected from the volume viewer.
        """
        coord_flip = list(position[:3])
        coord_flip[1] = -coord_flip[1]

        # Update the pointer sphere when not navigating.
        if self.pointer_actor is not None and not self.nav_status:
            self.pointer_actor.SetPosition(coord_flip)

            # Update the render window manually, as it is not updated automatically when not navigating.
            self.UpdateRender()

    def UpdateCamera(self, position):
        """
        During navigation, update camera position to lock to the coil if enabled in the
        user interface.
        """
        coord_flip = list(position[:3])
        coord_flip[1] = -coord_flip[1]

        # Lock camera position to the coil if enabled in the user interface.
        if self.lock_to_coil:
            self.LockToCoil(coord_flip)

    def AddCoilActor(self, obj_name):
        """
        Add actors for actual coil, coil center, and x, y, and z-axes to the renderer.
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

        coil_actor = vtkActor()
        coil_actor.SetMapper(obj_mapper)
        coil_actor.GetProperty().SetAmbientColor(vtk_colors.GetColor3d('GhostWhite'))
        coil_actor.GetProperty().SetSpecular(30)
        coil_actor.GetProperty().SetSpecularPower(80)
        coil_actor.GetProperty().SetOpacity(.4)
        coil_actor.SetVisibility(0)

        self.coil_actor = coil_actor

        # Create an actor for the coil center.
        coil_center_actor = self.actor_factory.CreateTorus(
            position=[0., 0., 0.],
            orientation=[0., 0., 0.],
            colour=vtk_colors.GetColor3d('Red'),
            scale=0.5,
        )
        self.coil_center_actor = coil_center_actor

        # Create actors for the x, y, and z-axes.
        self.x_actor = self.actor_factory.CreateLine([0., 0., 0.], [1., 0., 0.], colour=[.0, .0, 1.0])
        self.y_actor = self.actor_factory.CreateLine([0., 0., 0.], [0., 1., 0.], colour=[.0, 1.0, .0])
        self.z_actor = self.actor_factory.CreateLine([0., 0., 0.], [0., 0., 1.], colour=[1.0, .0, .0])

        self.obj_projection_arrow_actor = self.actor_factory.CreateArrowUsingDirection(
            position=[0., 0., 0.],
            orientation=[0., 0., 0.],
            colour=vtk_colors.GetColor3d('Red'),
            size=8
        )
        self.object_orientation_torus_actor = self.actor_factory.CreateTorus(
            position=[0., 0., 0.],
            orientation=[0., 0., 0.],
            colour=vtk_colors.GetColor3d('Red')
        )

        self.ren.AddActor(self.coil_actor)
        self.ren.AddActor(self.coil_center_actor)
        self.ren.AddActor(self.x_actor)
        self.ren.AddActor(self.y_actor)
        self.ren.AddActor(self.z_actor)
        self.x_actor.SetVisibility(0)
        self.y_actor.SetVisibility(0)
        self.z_actor.SetVisibility(0)

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

    def AddPeeledSurface(self, flag, actor):
        if self.actor_peel:
            self.ren.RemoveActor(self.actor_peel)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.actor_peel = None
            if self.pointer_actor:
                self.pointer_actor.SetVisibility(1)

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
        self.ball_max_vector = self.actor_factory.CreateBall(self.position_max, vtk_colors.GetColor3d('Red'), 0.5)
        self.ren.AddActor(self.max_efield_vector)
        self.ren.AddActor(self.ball_max_vector)

    def CoGEfieldActor(self):
        vtk_colors = vtkNamedColors()
        if self.GoGEfieldVector and self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.ren.RemoveActor(self.ball_GoGEfieldVector)
        orientation = [self.max_efield_array[0] , self.max_efield_array[1], self.max_efield_array[2]]
        [self.cell_id_indexes_above_threshold, self.positions_above_threshold]= self.GetIndexesAboveThreshold(self.efield_threshold)
        self.center_gravity_position = self.FindCenterofGravity(self.cell_id_indexes_above_threshold, self.positions_above_threshold)
        self.GoGEfieldVector = self.DrawVectors(self.center_gravity_position, orientation, vtk_colors.GetColor3d('Blue'))
        self.ball_GoGEfieldVector = self.actor_factory.CreateBall(self.center_gravity_position, vtk_colors.GetColor3d('Blue'), 0.5)
        self.ren.AddActor(self.GoGEfieldVector)
        self.ren.AddActor(self.ball_GoGEfieldVector)

    def CoGEforCortexMarker(self):
        if self.e_field_norms is not None:
            [cell_id_indexes, positions_above_threshold] = self.GetIndexesAboveThreshold(0.98)
            center_gravity_position_for_marker = self.FindCenterofGravity(cell_id_indexes, positions_above_threshold)
            center_gravity_orientation_for_marker = [self.max_efield_array[0], self.max_efield_array[1],
                                           self.max_efield_array[2]]
            Publisher.sendMessage('Update Cortex Marker', CoGposition = center_gravity_position_for_marker, CoGorientation = center_gravity_orientation_for_marker)
        # Publisher.sendMessage('Save target data', target_list_index=marker_id, position= center_gravity_position_for_marker,
        #                       orientation= center_gravity_orientation_for_marker, plot_efield_vectors=self.plot_vector)
        #return [marker_actor_brain, center_gravity_position_for_marker, center_gravity_orientation_for_marker]

    def AddCortexMarkerActor(self, position_orientation, marker_id):
        vtk_colors = vtkNamedColors()
        marker_actor_brain = self.DrawVectors(position_orientation[:3],
                                              position_orientation[3:], vtk_colors.GetColor3d('Orange'),
                                              scale_factor=3)
        self.static_markers_efield.append([marker_actor_brain, marker_id])
        self.ren.AddActor(marker_actor_brain)
        if self.save_automatically:
            import invesalius.project as prj
            import time
            import invesalius.gui.dialogs as dlg
            proj = prj.Project()
            timestamp = time.localtime(time.time())
            stamp_date = '{:0>4d}{:0>2d}{:0>2d}'.format(timestamp.tm_year, timestamp.tm_mon, timestamp.tm_mday)
            stamp_time = '{:0>2d}{:0>2d}{:0>2d}'.format(timestamp.tm_hour, timestamp.tm_min, timestamp.tm_sec)
            sep = '-'

            if self.path_meshes is None:
                import os
                current_folder_path = os.getcwd()
            else:
                current_folder_path = self.path_meshes

            parts = [current_folder_path, '/', stamp_date, stamp_time, proj.name, 'Efield']
            default_filename = sep.join(parts) + '.csv'

            filename = dlg.ShowLoadSaveDialog(message=_(u"Save markers as..."),
                                              wildcard='(*.csv)|*.csv',
                                              style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                              default_filename=default_filename)

            if not filename:
                return

            Publisher.sendMessage('Save Efield data', filename=filename, plot_efield_vectors=self.plot_efield_vectors, marker_id = marker_id)

    def EnableSaveAutomaticallyEfieldData(self, enable, path_meshes, plot_efield_vectors):
        self.save_automatically = enable
        self.path_meshes = path_meshes
        self.plot_efield_vectors = plot_efield_vectors

    def CortexMarkersVisualization(self, display_flag):
        for i in range(len(self.static_markers_efield)):
            if display_flag:
                self.ren.AddActor(self.static_markers_efield[i][0])
            else:
                self.ren.RemoveActor(self.static_markers_efield[i][0])

    def CreateTextLegend(self, FontSize, Position):
        TextLegend = vtku.Text()
        TextLegend.SetSize(FontSize)
        TextLegend.SetPosition(Position)
        TextLegend.BoldOn()
        return TextLegend

    def CreateEfieldSpreadLegend(self):
        self.SpreadEfieldFactorTextActor = self.CreateTextLegend(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION,(0.4, 0.9))
        self.ren.AddActor(self.SpreadEfieldFactorTextActor.actor)

    def CalculateDistanceMaxEfieldCoGE(self):
        self.distance_efield = distance.euclidean(self.center_gravity_position, self.position_max)
        self.SpreadEfieldFactorTextActor.SetValue('Spread distance: ' + str("{:04.2f}".format(self.distance_efield)))

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
            if self.efield_coords is not None:
                import invesalius.data.imagedata_utils as imagedata_utils

                position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                    position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
                    orientation=[self.efield_coords[3], self.efield_coords[4], self.efield_coords[5]],
                )
                efield_coords_position = [list(position_world), list(orientation_world)]
            enorms_list = list(self.e_field_norms)
            if plot_efield_vectors:
                e_field_vectors = list(self.max_efield_array)
                self.target_radius_list.append([target_list_index, self.Id_list, enorms_list, self.Idmax, self.coil_position, efield_coords_position, self.efield_coords,  self.coil_position_Trot, e_field_vectors, self.focal_factor_members, self.efield_threshold, self.efield_ROISize, self.mtms_coord])
                self.mtms_coord = None
            else:
                self.target_radius_list.append([target_list_index, self.Id_list, enorms_list, self.Idmax, self.coil_position, efield_coords_position, self.efield_coords, self.coil_position_Trot])

    def GetTargetSavedEfieldData(self, target_index_list):
        if len(self.target_radius_list)>0:
            target_index = 0
            for i in range(len(self.target_radius_list)):
                if target_index_list == self.target_radius_list[i][0]:
                    target_index= i
                    self.saved_target_data = self.target_radius_list[target_index]
                    break

    def CreateEfieldmTMSCoorlegend(self):
        self.mTMSCoordTextActor = self.CreateTextLegend(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION,(0.4, 0.2))
        self.ren.AddActor(self.mTMSCoordTextActor.actor)

    def GetTargetPathmTMS(self,targeting_file):
        self.targeting_file = targeting_file

    def GetTargetPositions(self, target1_origin, target2):
        if self.mTMSCoordTextActor is None:
            self.CreateEfieldmTMSCoorlegend()
        self.mtms_coord = None
        x_diff = round(target1_origin[0]- target2[0])
        y_diff = round(target1_origin[1]- target2[1])
        csv_filename = self.targeting_file
        target_numbers = [-x_diff, y_diff, 0]
        self.matching_row = self.find_and_extract_data(csv_filename, target_numbers)
        dIs = self.mTMS_multiplyFactor(1000)
        Publisher.sendMessage('Get dI for mtms', dIs = dIs)
        self.mTMSCoordTextActor.SetValue('mTMS coords: '+ str(target_numbers))
        self.mtms_coord = target_numbers

    def GetdIsfromCoord(self,mtms_coord):
        if self.mTMSCoordTextActor is None:
            self.CreateEfieldmTMSCoorlegend()
        self.mtms_coord = None
        self.matching_row = self.find_and_extract_data(self.targeting_file, mtms_coord)
        dIs = self.mTMS_multiplyFactor(1000)
        Publisher.sendMessage('Get dI for mtms', dIs=dIs)
        self.mTMSCoordTextActor.SetValue('mTMS coords: ' + str(mtms_coord))
        self.mtms_coord = mtms_coord

    def mTMS_multiplyFactor(self, factor):
        result = []
        for row in self.matching_row:
            convert = float(row) * factor
            result.append(convert)
        return result

    def find_and_extract_data(self,csv_filename, target_numbers):
        import csv
        matching_rows = []

        with open(csv_filename, 'r') as csvfile:
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                # Extract the first three numbers from the current row
                first_three_numbers = list(map(float, row[:3]))

                # Check if the first three numbers match the target numbers
                if first_three_numbers == target_numbers:
                    # If there's a match, append the row (excluding the first three numbers)
                    matching_rows = row[3:8]
                    break

        return matching_rows

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

    def GetIndexesAboveThreshold(self, threshold):
        cell_id_indexes = []
        positions = []
        indexes = [index for index, value in enumerate(self.e_field_norms) if
                   value > self.efield_max * threshold]
        for index, value in enumerate(indexes):
            cell_id_indexes.append(self.Id_list[value])
            positions.append(self.efield_mesh.GetPoint(self.Id_list[value]))
        return [cell_id_indexes, positions]

    def UpdateEfieldThreshold(self, data):
        self.efield_threshold = data

    def UpdateEfieldROISize(self, data):
        self.efield_ROISize = data
        self.radius_list.Reset()

    def EnableEfieldTools(self, enable):
        self.efield_tools = enable
        if self.efield_tools:
            self.CreateEfieldSpreadLegend()
            self.CreateClustersEfieldLegend()
        elif not self.efield_tools and self.ClusterEfieldTextActor is not None:
            self.ren.RemoveActor(self.ClusterEfieldTextActor.actor)
            self.ren.RemoveActor(self.SpreadEfieldFactorTextActor.actor)

    def FindCenterofGravity(self, cell_id_indexes, positions):
        weights = []
        for index, value in enumerate(cell_id_indexes):
            weights.append(self.e_field_norms[index])
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
        center_gravity = [0.0, 0.0, 0.0]
        cell_id = mutable(0)
        sub_id = mutable(0)
        distance = mutable(0.0)
        self.locator_efield_cell.FindClosestPoint(query_point, center_gravity, cell_id, sub_id, distance)
        return center_gravity

    def DetectClustersEfieldSpread(self, points):
        from sklearn.cluster import DBSCAN
        from sklearn.metrics import pairwise_distances

        points = np.array(points) if isinstance(points, list) else points
        dbscan = DBSCAN(eps=5, min_samples=1).fit(points)
        labels = dbscan.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        core_sample_indices = dbscan.core_sample_indices_
        cluster_centers = points[core_sample_indices, :]
        representative_centers = np.array([cluster.mean(axis=0) for cluster in np.split(cluster_centers, np.cumsum(
            np.unique(dbscan.labels_, return_counts=True)[1])[:-1])])
        distances_between_representatives = np.max(pairwise_distances(representative_centers))
        focal_factor = n_clusters/len(self.Id_list) + distances_between_representatives/30 + self.distance_efield/15
        focal_factor = 1/focal_factor
        self.ClusterEfieldTextActor.SetValue('Clusters above '+ str(int(self.efield_threshold*100)) + '% percent: ' +
                                             str(n_clusters)+ '\n' +' distance:' +str(distances_between_representatives) +
                                            '\n'+ 'Focal Factor: ' + '  '+str(focal_factor))
        self.focal_factor_members = [n_clusters, n_clusters/len(self.Id_list), distances_between_representatives,distances_between_representatives/30, self.distance_efield, self.distance_efield/15,focal_factor]

    def CreateClustersEfieldLegend(self):
        self.ClusterEfieldTextActor = self.CreateTextLegend(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION,(0.03, 0.99))
        self.ren.AddActor(self.ClusterEfieldTextActor.actor)

    def EnableShowEfieldAboveThreshold(self, enable):
        self.enableefieldabovethreshold = enable

    def SegmentEfieldMax(self, cell_id_indexes):
        color = [255, 165, 0]
        for j , value in enumerate(cell_id_indexes):
            self.colors_init.InsertTuple(value, color)

    def GetEfieldActor(self, e_field_actor):
        self.efield_actor  = e_field_actor

    def FindPointsAroundRadiusEfield(self, cellId):
        radius = int(self.efield_ROISize)
        self.locator_efield.FindPointsWithinRadius(radius, self.e_field_mesh_centers.GetPoint(cellId), self.radius_list)

    def CreateCortexProjectionOnScalp(self, marker_id, position, orientation):
        self.target_at_cortex = None
        self.scalp_mesh = self.scalp_actor.GetMapper().GetInput()
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.target_at_cortex = position_flip
        point_scalp = self.FindClosestPointToMesh(position_flip, self.scalp_mesh)
        self.CreateEfieldAtTargetLegend()
        Publisher.sendMessage('Create Marker from tangential', point = point_scalp, orientation =orientation)

    def ClearTargetAtCortex(self):
        self.target_at_cortex = None
        if self.EfieldAtTargetLegend is not None:
            self.ren.RemoveActor(self.EfieldAtTargetLegend.actor)

    def SetEfieldTargetAtCortex(self, position, orientation):
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.target_at_cortex = position_flip
        self.CreateEfieldAtTargetLegend()


    def ShowEfieldAtCortexTarget(self):
        if self.target_at_cortex is not None:
            import vtk
            index = self.efield_mesh.FindPoint(self.target_at_cortex)
            if index in self.Id_list:
                cell_number = self.Id_list.index(index)
                self.EfieldAtTargetLegend.SetValue(
                    'Efield at Target: ' + str("{:04.2f}".format(self.e_field_norms[cell_number])))
            else:
                self.EfieldAtTargetLegend.SetValue(
                    'Efield at Target: ' + str("{:04.2f}".format(0)))

    def CreateEfieldAtTargetLegend(self):
        if self.EfieldAtTargetLegend is not None:
            self.ren.RemoveActor(self.EfieldAtTargetLegend.actor)
        self.EfieldAtTargetLegend = self.CreateTextLegend(const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION,(0.4, 0.96))
        self.ren.AddActor(self.EfieldAtTargetLegend.actor)

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
        self.focal_factor_members=[]
        self.distance_efield = None
        self.mtms_coord = None

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

        if self.ClusterEfieldTextActor is not None:
            self.ren.RemoveActor(self.ClusterEfieldTextActor.actor)

        if self.SpreadEfieldFactorTextActor is not None:
            self.ren.RemoveActor(self.SpreadEfieldFactorTextActor.actor)

        self.efield_scalar_bar = e_field_brain.efield_scalar_bar

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
        if self.radius_list.GetNumberOfIds() !=0:
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
                wx.CallAfter(Publisher.sendMessage,'Show max Efield actor')
                wx.CallAfter(Publisher.sendMessage,'Show CoG Efield actor')
                if self.efield_tools:
                    wx.CallAfter(Publisher.sendMessage, 'Show distance between Max and CoG Efield')
                    if self.positions_above_threshold is not None:
                        self.DetectClustersEfieldSpread(self.positions_above_threshold)
                if self.enableefieldabovethreshold and self.cell_id_indexes_above_threshold is not None:
                    self.SegmentEfieldMax(self.cell_id_indexes_above_threshold)
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

    def UpdateEfieldPointLocationOffline(self, m_img, coord, list_index):
        [coil_dir, norm, coil_norm, p1] = self.ObjectArrowLocation(m_img, coord)
        intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        id_list = []
        for h in range(self.radius_list.GetNumberOfIds()):
            id_list.append(self.radius_list.GetId(h))
        Publisher.sendMessage('Get ID list', ID_list = id_list)
        self.plot_no_connection = True
        self.list_index_efield_vectors = list_index

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
                if self.save_automatically and self.plot_no_connection:
                    import invesalius.project as prj
                    import time
                    import invesalius.gui.dialogs as dlg
                    proj = prj.Project()
                    timestamp = time.localtime(time.time())
                    stamp_date = '{:0>4d}{:0>2d}{:0>2d}'.format(timestamp.tm_year, timestamp.tm_mon, timestamp.tm_mday)
                    stamp_time = '{:0>2d}{:0>2d}{:0>2d}'.format(timestamp.tm_hour, timestamp.tm_min, timestamp.tm_sec)
                    sep = '-'

                    if self.path_meshes is None:
                        import os
                        current_folder_path = os.getcwd()
                    else:
                        current_folder_path = self.path_meshes

                    parts = [current_folder_path, '/', stamp_date, stamp_time, proj.name, 'Efield']
                    default_filename = sep.join(parts) + '.csv'

                    filename = dlg.ShowLoadSaveDialog(message=_(u"Save markers as..."),
                                                      wildcard='(*.csv)|*.csv',
                                                      style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                                      default_filename=default_filename)

                    if not filename:
                        return

                    Publisher.sendMessage('Save Efield data', filename=filename,
                                          plot_efield_vectors=self.plot_efield_vectors, marker_id = self.list_index_efield_vectors )
        else:
            self.e_field_norms = enorm_data[3]
            self.Idmax = np.array(self.e_field_norms).argmax()

        self.GetEfieldMaxMin(self.e_field_norms)

    def SaveEfieldData(self, filename, plot_efield_vectors, marker_id):
        import invesalius.data.imagedata_utils as imagedata_utils
        import csv
        all_data=[]

        header = ['Marker ID', 'T_rot','Coil center','Coil position in world coordinates', 'InVesalius coordinates', 'Enorm','ID cell max', 'Efield vectors', 'Enorm cell indexes', 'Focal factors', 'Efield threshold', 'Efield ROI size', 'Mtms_coord']
        if self.efield_coords is not None:
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
            position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
            orientation=[self.efield_coords[3], self.efield_coords[4], self.efield_coords[5]],
                 )
            efield_coords_position = [list(position_world), list(orientation_world)]
        if plot_efield_vectors:
            if self.plot_no_connection:
                e_field_vectors = [list(self.e_field_col1), list(self.e_field_col2), list(self.e_field_col3)]
            else:
                e_field_vectors = list(self.max_efield_array)
            all_data.append([marker_id, self.coil_position_Trot, self.coil_position, efield_coords_position, self.efield_coords, list(self.e_field_norms), self.Idmax, e_field_vectors, self.Id_list, self.focal_factor_members, self.efield_threshold, self.efield_ROISize, self.mtms_coord])
            #REMOVE THIS
            self.mtms_coord = None
        else:
            all_data.append([marker_id, self.coil_position_Trot, self.coil_position, efield_coords_position, self.efield_coords, list(self.e_field_norms)])

        with open(filename, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(all_data)

    def SavedAllEfieldData(self, filename):
        import invesalius.data.imagedata_utils as imagedata_utils
        import csv
        header = ['Marker ID', 'Enorm cell indexes', 'Enorm', 'ID cell Max', 'Coil center','Coil position world coordinates','InVesalius coordinates','T_rot', 'Efield vectors', 'Focal factors', 'Efield threshold', 'Efield ROI size', 'Mtms_coord']
        all_data = list(self.target_radius_list)
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(all_data)

    def GetCellIntersection(self, p1, p2, locator):
        vtk_colors = vtkNamedColors()
        # This find store the triangles that intersect the coil's normal
        intersectingCellIds = vtkIdList()
        locator.FindCellsAlongLine(p1, p2, .001, intersectingCellIds)
        return intersectingCellIds

    def ShowCoilProjection(self, intersectingCellIds, p1, coil_norm, coil_dir):
        vtk_colors = vtkNamedColors()
        closestDist = 50

        # If intersection is was found, calculate angle and add actors.
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

                    # For debugging
                    self.y_actor = self.actor_factory.CreateLine(closestPoint, closestPoint + 75 * pointnormal,
                                                                     vtk_colors.GetColor3d('Yellow'))

                    #self.ren.AddActor(self.y_actor)# remove comment for testing

                    self.ren.AddActor(self.obj_projection_arrow_actor)
                    self.ren.AddActor(self.object_orientation_torus_actor)
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

    def OnNavigationStatus(self, nav_status, vis_status):
        self.nav_status = nav_status
        self.tracts_status = vis_status[1]

        if self.nav_status:
            self.pTarget = self.CenterOfMass()
            if self.coil_actor:
                self.coil_actor.SetVisibility(self.show_coil)
                #self.x_actor.SetVisibility(self.show_coil)
                #self.y_actor.SetVisibility(self.show_coil)
                #self.z_actor.SetVisibility(self.show_coil)
                #self.object_orientation_torus_actor.SetVisibility(self.show_coil)
                #self.obj_projection_arrow_actor.SetVisibility(self.show_coil)
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

    def UpdateCoilPose(self, m_img, coord):
        m_img_flip = m_img.copy()
        m_img_flip[1, -1] = -m_img_flip[1, -1]

        # translate coregistered coordinate to display a marker where Trekker seed is computed
        # coord_offset = m_img_flip[:3, -1] - self.seed_offset * m_img_flip[:3, 2]

        # print("m_img copy in viewer_vol: {}".format(m_img_copy))

        # m_img[:3, 0] is from posterior to anterior direction of the coil
        # m_img[:3, 1] is from left to right direction of the coil
        # m_img[:3, 2] is from bottom to up direction of the coil

        m_img_vtk = vtku.numpy_to_vtkMatrix4x4(m_img_flip)

        self.coil_actor.SetUserMatrix(m_img_vtk)
        self.coil_center_actor.SetUserMatrix(m_img_vtk)
        self.x_actor.SetUserMatrix(m_img_vtk)
        self.y_actor.SetUserMatrix(m_img_vtk)
        self.z_actor.SetUserMatrix(m_img_vtk)

    def UpdateArrowPose(self, m_img, coord, flag):
        [coil_dir, norm, coil_norm, p1 ]= self.ObjectArrowLocation(m_img,coord)

        if flag:
            self.ren.RemoveActor(self.x_actor)
            #self.ren.RemoveActor(self.y_actor)
            self.ren.RemoveActor(self.obj_projection_arrow_actor)
            self.ren.RemoveActor(self.object_orientation_torus_actor)
            intersectingCellIds = self.GetCellIntersection(p1, norm, self.locator)
            self.ShowCoilProjection(intersectingCellIds, p1, coil_norm, coil_dir)

    def RemoveObjectActor(self):
        self.ren.RemoveActor(self.coil_actor)
        self.ren.RemoveActor(self.x_actor)
        self.ren.RemoveActor(self.y_actor)
        self.ren.RemoveActor(self.z_actor)
        self.ren.RemoveActor(self.mark_actor)
        self.ren.RemoveActor(self.obj_projection_arrow_actor)
        self.ren.RemoveActor(self.object_orientation_torus_actor)
        self.coil_actor = None
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
                if self.coil_actor:
                    self.RemoveObjectActor()
                self.AddCoilActor(self.obj_name)
        else:
            if self.coil_actor:
                self.RemoveObjectActor()
        if not self.nav_status:
            self.UpdateRender()

    # Called when 'show coil' button is pressed in the user interface.
    def ShowCoil(self, state):
        self.show_coil = state

        if self.target_coil_actor is not None:
            self.target_coil_actor.SetVisibility(state)

        if self.coil_actor:
            self.coil_actor.SetVisibility(state)
            self.x_actor.SetVisibility(state)
            self.y_actor.SetVisibility(state)
            self.z_actor.SetVisibility(state)

        if self.active_aim_actor is not None and state:
            self.active_aim_actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)

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

    def OnUpdateRobotStatus(self, robot_status):
        if self.dummy_robot_actor:
            if robot_status:
                self.dummy_robot_actor.GetProperty().SetColor(0, 1, 0)
            else:
                self.dummy_robot_actor.GetProperty().SetColor(1, 0, 0)

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

    def SetLockToCoil(self, enabled):
        self.lock_to_coil = enabled
        self.camera_show_object = None

    def LockToCoil(self, cam_focus):
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
            self.camera_show_object = self.show_coil

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

    def AddSurface(self, actor):
        # Add the actor to the renderer.
        ren = self.ren
        ren.AddActor(actor)

        self.surface_added = True

        if not self.view_angle:
            self.SetViewAngle(const.VOL_FRONT)
            self.view_angle = 1
        else:
            ren.ResetCamera()
            ren.ResetCameraClippingRange()

        self.UpdateRender()

        # make camera projection to parallel
        self.ren.GetActiveCamera().ParallelProjectionOn()

        # use the 3D surface actor for measurement calculations
        self.surface = actor
        self.EnableRuler()

    def RemoveSurface(self, actor):
        # Remove the actor from the renderer.
        self.ren.RemoveActor(actor)
        self.UpdateRender()

        # Remove the ruler if visible.
        if self.ruler:
            self.HideRuler()

    def RemoveAllActors(self):
        self.ren.RemoveAllProps()
        self.UpdateRender()

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
        if not self.surface_added:
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
        if not self.surface_added and not self.raycasting_volume:
            if not self.repositioned_axial_plan and plane_label == 'Axial':
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_axial_plan = 1

            elif not self.repositioned_sagital_plan and plane_label == 'Sagital':
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_sagital_plan = 1

            elif not self.repositioned_coronal_plan and plane_label == 'Coronal':
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_coronal_plan = 1

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

        Publisher.sendMessage('Render volume viewer')

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

        Publisher.sendMessage('Render volume viewer')

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

        Publisher.sendMessage('Render volume viewer')

    def ChangeSlice(self, orientation, index):
        if  orientation == "CORONAL" and self.plane_y.GetEnabled():
            Publisher.sendMessage('Update slice 3D',
                                  widget=self.plane_y,
                                  orientation=orientation)
            Publisher.sendMessage('Render volume viewer')

        elif orientation == "SAGITAL" and self.plane_x.GetEnabled():
            Publisher.sendMessage('Update slice 3D', 
                                  widget=self.plane_x,
                                  orientation=orientation)
            Publisher.sendMessage('Render volume viewer')

        elif orientation == 'AXIAL' and self.plane_z.GetEnabled() :
            Publisher.sendMessage('Update slice 3D',
                                  widget=self.plane_z,
                                  orientation=orientation)
            Publisher.sendMessage('Render volume viewer')

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

