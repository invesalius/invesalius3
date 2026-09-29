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
# from math import cos, sin
import os
import sys

import numpy as np
import wx
from imageio import imsave
from vtk import vtkCommand

# TODO: Check that these imports are not used -- vtkLookupTable, vtkMinimalStandardRandomSequence, vtkPoints, vtkUnsignedCharArray
from vtkmodules.vtkFiltersCore import vtkCenterOfMass
from vtkmodules.vtkFiltersHybrid import vtkRenderLargeImage
from vtkmodules.vtkFiltersSources import (
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
from vtkmodules.vtkIOImage import (
    vtkBMPWriter,
    vtkJPEGWriter,
    vtkPNGWriter,
    vtkPostScriptWriter,
    vtkTIFFWriter,
)
from vtkmodules.vtkRenderingAnnotation import vtkAnnotatedCubeActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkAssembly,
    vtkPointPicker,
    vtkPolyDataMapper,
    vtkProperty,
    vtkPropPicker,
    vtkRenderer,
    vtkWindowToImageFilter,
)
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor

import invesalius.constants as const
import invesalius.data.styles_3d as styles
import invesalius.data.vtk_utils as vtku
import invesalius.project as prj
import invesalius.session as ses
import invesalius.style as st
import invesalius.utils as utils
from invesalius.data.actor_factory import ActorFactory
from invesalius.data.markers.surface_geometry import SurfaceGeometry
from invesalius.data.ruler_volume import GenericLeftRulerVolume
from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        win32api = None  # type: ignore[assignment]
        _has_win32api = False
else:
    win32api = None  # type: ignore[assignment]
    _has_win32api = False

PROP_MEASURE = 0.8

#  from invesalius.gui.widgets.canvas_renderer import CanvasRendererCTX, Polygon


class Viewer(wx.Panel):
    """General 3D scene, rendering infrastructure and volume tools."""

    def __init__(self, parent):
        display_size = wx.GetDisplaySize()
        # Set the initial volume wx.Panel size as half the screen resolution to fix the issue
        # with small target guide icons when loading a state file with target selected
        x = int(display_size[0] / 2)
        y = int(display_size[1] / 2)
        wx.Panel.__init__(self, parent, size=wx.Size(x, y))
        self._disposed = False
        self._call_laters = []
        self._ruler_observer_tag = None
        self._cube_render_observer_tag = None
        self.navigation = None
        self.active_view = self
        self._navigation_mode = None
        self._scene_viewport = (0.0, 0.0, 1.0, 1.0)
        self.SetBackgroundColour(wx.Colour(0, 0, 0))

        self.interaction_style = st.StyleStateManager()

        self.initial_focus = None

        self.style = None

        interactor = wxVTKRenderWindowInteractor(self, -1, size=self.GetSize())
        self.interactor = interactor
        self.interactor.SetRenderWhenDisabled(True)

        self.nav_status = False
        self.target_mode = False

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
        self.target_guide_renderer = None

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
        if sys.platform == "darwin":
            font_size = const.TEXT_SIZE_LARGE * self.GetContentScaleFactor()
            self.text.SetSize(int(round(font_size, 0)))
        self.ren.AddActor(self.text.actor)

        #  self.polygon = Polygon(None, is_3d=False)

        # Enable canvas for ruler to be drawn
        self.canvas = CanvasRendererCTX(self, self.ren, self.canvas_renderer)
        self.prev_view_port_height = None
        self.ruler = None
        self.orientation_widget = None  # VTK orientation cube widget

        self.slice_plane = None

        self.view_angle = None

        self._bind_events()
        self.__bind_events_wx()

        self.mouse_pressed = 0
        self.on_wl = False

        self.picker = vtkPointPicker()
        interactor.SetPicker(self.picker)
        self.seed_points = []

        self.points_reference = []

        self.measure_picker = vtkPropPicker()
        # self.measure_picker.SetTolerance(0.005)
        self.measures = []

        self.repositioned_axial_plan = 0
        self.repositioned_sagital_plan = 0
        self.repositioned_coronal_plan = 0
        self.surface_added = False

        self.use_volumetric_camera = False
        self.camera_show_object = None

        # Pointer is the ball that is shown to indicate the 3D point in the volume viewer that corresponds to the
        # selected slice positions. The same pointer is also used to show the point selected from the 3D viewer by
        # right-clicking on it.
        self.pointer_actor = None

        # A dict to store the current camera settings; used when enabling target mode to store the current
        # camera. When disabling target mode, the stored camera settings are used to restore the camera.
        self.stored_camera_settings = None

        self.surface = None
        self.surface_geometry = SurfaceGeometry()

        # An object that can be used to create actors, such as lines, arrows, and spheres.
        self.actor_factory = ActorFactory()

        # SSAO state tracking
        self.ssao_enabled = False
        self.ssao_pass = None
        self.ssao_before_measurement = False  # Track SSAO state before entering measurement mode

        # self.renderers = (self.target_guide_renderer, ren, canvas_renderer)

        renwin = interactor.GetRenderWindow().GetRenderers()
        renwin.InitTraversal()

        self.renderers = []
        for i in range(renwin.GetNumberOfItems()):
            renderer = renwin.GetNextItem()
            self.renderers.append(renderer)

        # Request the orientation cube visibility status with a small delay
        # to ensure the interactor has time to initialize during app startup.
        self._call_later(1000, Publisher.sendMessage, "Send orientation cube visibility status")
        self.SetNavigationMode(ses.Session().GetConfig("mode") == const.MODE_NAVIGATOR)

    def _call_later(self, delay, callable_, *args, **kwargs):
        if self._disposed:
            return None

        timer = wx.CallLater(delay, callable_, *args, **kwargs)
        self._call_laters.append(timer)
        return timer

    def _map_scene_viewport(self, viewport):
        scene_x_min, scene_y_min, scene_x_max, scene_y_max = self._scene_viewport
        x_min, y_min, x_max, y_max = viewport
        scene_width = scene_x_max - scene_x_min
        scene_height = scene_y_max - scene_y_min
        return (
            scene_x_min + x_min * scene_width,
            scene_y_min + y_min * scene_height,
            scene_x_min + x_max * scene_width,
            scene_y_min + y_max * scene_height,
        )

    def _set_renderer_viewport(self, renderer, viewport):
        renderer.SetViewport(*self._map_scene_viewport(viewport))

    def _apply_scene_viewport(self):
        self._set_renderer_viewport(self.ren, (0.0, 0.0, 1.0, 1.0))
        self._set_renderer_viewport(self.canvas_renderer, (0.0, 0.0, 1.0, 1.0))
        if self.orientation_widget is not None:
            self.orientation_widget.SetViewport(*self._map_scene_viewport((0.85, 0.0, 1.0, 0.15)))

    def SetSceneViewport(self, viewport):
        """Position this scene inside the shared render window."""
        self._scene_viewport = tuple(viewport)
        self._apply_scene_viewport()

    def capture_state(self):
        """Capture the general-view state changed while navigation is active."""
        return {
            "camera": self.GetCameraSettings(),
            "interaction_stack": self.interaction_style.stack.copy(),
            "scene_viewport": self._scene_viewport,
        }

    def restore_state(self, state):
        """Restore the relevant general-view state after leaving navigation."""
        if state is None:
            return
        self.ApplyCameraSettings(state["camera"])
        self.interaction_style.stack = state["interaction_stack"].copy()
        self.SetInteractorStyle(self.interaction_style.GetActualState())
        self.SetSceneViewport(state["scene_viewport"])

    def dispose(self):
        if self._disposed:
            return
        if self.navigation is not None:
            self.navigation.dispose()
            self.navigation = None
        self._disposed = True
        Publisher.unsubscribe_owner(self)
        for timer in self._call_laters:
            try:
                if timer.IsRunning():
                    timer.Stop()
            except RuntimeError:
                pass
        self._call_laters.clear()
        if self.slice_plane:
            self.slice_plane.dispose()
            self.slice_plane = None
        if self.orientation_widget is not None:
            try:
                self.orientation_widget.SetEnabled(0)
            except Exception:
                pass
        if self._cube_render_observer_tag is not None:
            try:
                self.ren.RemoveObserver(self._cube_render_observer_tag)
            except Exception:
                pass
            self._cube_render_observer_tag = None
        if self._ruler_observer_tag is not None:
            try:
                self.interactor.RemoveObserver(self._ruler_observer_tag)
            except Exception:
                pass
            self._ruler_observer_tag = None
        try:
            self.interactor.Disable()
        except Exception:
            pass

    def OnDestroy(self, evt):
        if evt.GetEventObject() is self:
            self.dispose()
        evt.Skip()

    def _bind_events(self):
        Publisher.subscribe(self.AddSurface, "Load surface actor into viewer")
        Publisher.subscribe(self.RemoveSurface, "Remove surface actor from viewer")
        Publisher.subscribe(self.UpdateRender, "Render volume viewer")
        Publisher.subscribe(self.ChangeBackgroundColour, "Change volume viewer background colour")
        Publisher.subscribe(self.LoadVolume, "Load volume into viewer")
        Publisher.subscribe(self.UnloadVolume, "Unload volume")
        Publisher.subscribe(self.OnSetWindowLevelText, "Set volume window and level text")
        Publisher.subscribe(self.OnHideRaycasting, "Hide raycasting volume")
        Publisher.subscribe(self.OnShowRaycasting, "Update raycasting preset")
        Publisher.subscribe(self.AppendActor, "AppendActor")
        Publisher.subscribe(self.SetWidgetInteractor, "Set Widget Interactor")
        Publisher.subscribe(self.OnSetViewAngle, "Set volume view angle")
        Publisher.subscribe(
            self.OnDisableBrightContrast, "Set interaction mode " + str(const.MODE_SLICE_EDITOR)
        )
        Publisher.subscribe(self.LoadSlicePlane, "Load slice plane")
        Publisher.subscribe(self.ResetCamClippingRange, "Reset cam clipping range")
        Publisher.subscribe(self.SendActiveCamera, "Send volume viewer active camera")
        Publisher.subscribe(self.SendViewerSize, "Send volume viewer size")
        Publisher.subscribe(self.enable_style, "Enable style")
        Publisher.subscribe(self.OnDisableStyle, "Disable style")
        Publisher.subscribe(self.OnHideText, "Hide text actors on viewers")
        Publisher.subscribe(self.AddActors, "Add actors " + str(const.SURFACE))
        Publisher.subscribe(self.RemoveActors, "Remove actors " + str(const.SURFACE))
        Publisher.subscribe(self.OnShowText, "Show text actors on viewers")
        Publisher.subscribe(self.OnShowRuler, "Show rulers on viewers")
        Publisher.subscribe(self.OnHideRuler, "Hide rulers on viewers")
        Publisher.subscribe(self.OnRulerVisibilityStatus, "Receive ruler visibility status")
        Publisher.subscribe(self.OnShowOrientationCube, "Show orientation cube")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.FocusCamera, "Focus volume camera")
        Publisher.subscribe(self.RemoveAllActors, "Remove all volume actors")
        Publisher.subscribe(self.SetStereoMode, "Set stereo mode")
        Publisher.subscribe(self.Reposition3DPlane, "Reposition 3D Plane")
        Publisher.subscribe(self.UpdatePointer, "Update volume viewer pointer")
        Publisher.subscribe(self.RemoveVolume, "Remove Volume")
        Publisher.subscribe(self._EnableSSAO, "Enable SSAO")
        Publisher.subscribe(self._DisableSSAO, "Disable SSAO")
        Publisher.subscribe(self._ApplySSAOAfterProjectLoad, "Project loaded successfully")
        Publisher.subscribe(self.OnExportSurface, "Export surface to file")
        Publisher.subscribe(self.OnExportPicture, "Export picture to file")
        Publisher.subscribe(self.OnStartSeed, "Create surface by seeding - start")
        Publisher.subscribe(self.OnEndSeed, "Create surface by seeding - end")
        Publisher.subscribe(self.load_mask_preview, "Load mask preview")
        Publisher.subscribe(self.remove_mask_preview, "Remove mask preview")
        Publisher.subscribe(self.SetNavigationMode, "Set navigation mode")

    def SetNavigationMode(self, status):
        if self._disposed:
            return
        status = bool(status)
        if status == self._navigation_mode:
            return

        if status:
            from invesalius.data.viewer_navigation import NavigationView

            self.navigation = NavigationView(self)
            self.navigation.activate()
            self.active_view = self.navigation
        else:
            if self.navigation is not None:
                self.navigation.dispose()
                self.navigation = None
            self.active_view = self
        self._navigation_mode = status

        Publisher.sendMessage("Send orientation cube visibility status")
        Publisher.sendMessage("Send ruler visibility status")
        Publisher.sendMessage(
            "Update viewer caption",
            viewer_name="Volume",
            caption=_("Navigation") if status else _("Volume"),
        )

    def UpdateCanvas(self):
        if self.canvas is not None:
            self.canvas.modified = True
            if not self.nav_status:
                self.UpdateRender()

    def EnableRuler(self):
        self.ruler = GenericLeftRulerVolume(self)
        if self._ruler_observer_tag is not None:
            self.interactor.RemoveObserver(self._ruler_observer_tag)
        self._ruler_observer_tag = self.interactor.AddObserver(
            vtkCommand.AnyEvent, self.OnInteractorEvent
        )
        Publisher.sendMessage("Send ruler visibility status")

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

    def OnShowOrientationCube(self, status):
        """
        Receive the requested visibility state for the orientation cube.
        """
        # Track the intended state to handle retry loop cancellation
        self._cube_request_on = status

        if status:
            # When no 3D surface exists yet, force the canonical front camera so
            # the cube starts with "A" (anterior) facing the viewer.
            if not self.view_angle:
                self.SetViewAngle(const.VOL_FRONT)

            # FORCE RE-CREATION to fix "1st click" and "2nd click" synchronization issues
            if self.orientation_widget:
                try:
                    self.orientation_widget.SetEnabled(0)
                except:  # noqa: E722 - preserve existing widget cleanup behavior
                    pass
                self.orientation_widget = None

            self._cube_retries = 0
            self._ShowOrientationCube()
        else:
            if self.orientation_widget:
                self.orientation_widget.SetEnabled(0)
                # Remove renderer observer so we stop updating a hidden cube.
                tag = getattr(self, "_cube_render_observer_tag", None)
                if tag is not None:
                    try:
                        self.ren.RemoveObserver(tag)
                    except Exception:
                        pass
                    self._cube_render_observer_tag = None
            self.UpdateRender()

    def _ShowOrientationCube(self):
        """
        Build and enable the 3D orientation cube (anatomical directions).
        """
        if self._disposed or not getattr(self, "_cube_request_on", False):
            return

        if not self.interactor:
            self._call_later(100, self._ShowOrientationCube)
            return

        if not self.interactor.GetInitialized():
            # Interactor not ready yet – retry up to 200 times (approx 20s total).
            # Force a render attempt to trigger initialization.
            self.interactor.Render()
            retries = getattr(self, "_cube_retries", 0)
            if retries < 200:
                self._cube_retries = retries + 1
                self._call_later(100, self._ShowOrientationCube)
            else:
                import logging

                logging.warning("Orientation cube failed to initialize: Interactor timeout")
                Publisher.sendMessage("Set orientation cube state", status=False)
                self._cube_retries = 0
            return

        try:
            # Build the annotated cube actor with anatomical labels.
            cube = vtkAnnotatedCubeActor()

            # Canonical anatomical mapping:
            # X axis -> Left/Right, Y axis -> Posterior/Anterior, Z axis -> Top/Bottom.
            # With VOL_FRONT camera (0, -1, 0), the Y- face is visible => "A".
            cube.GetXPlusFaceProperty().SetColor(0.7, 0.1, 0.1)  # L – Left
            cube.GetXMinusFaceProperty().SetColor(0.7, 0.1, 0.1)  # R – Right
            cube.GetYPlusFaceProperty().SetColor(0.1, 0.7, 0.1)  # P – Posterior
            cube.GetYMinusFaceProperty().SetColor(0.1, 0.7, 0.1)  # A – Anterior
            cube.GetZPlusFaceProperty().SetColor(0.1, 0.1, 0.7)  # T – Top
            cube.GetZMinusFaceProperty().SetColor(0.1, 0.1, 0.7)  # B – Bottom
            cube.GetTextEdgesProperty().SetColor(0.5, 0.5, 0.5)

            proj = prj.Project()
            if proj.original_orientation == const.SAGITAL:
                x_plus, x_minus = "L", "R"
                patient_orient = getattr(proj, "patient_orientation", None)

                if patient_orient is not None and len(patient_orient) == 6:
                    row_y, row_z = patient_orient[1], patient_orient[2]
                    col_y, col_z = patient_orient[4], patient_orient[5]
                    normal_x = (row_y * col_z) - (row_z * col_y)

                    if normal_x < 0:
                        x_plus, x_minus = "R", "L"
                else:
                    # Maintainer fallback request if patient_orientation is missing
                    x_plus, x_minus = "R", "L"

                cube.SetXPlusFaceText(_(x_plus))
                cube.SetXMinusFaceText(_(x_minus))
                cube.SetYPlusFaceText(_("A"))
                cube.SetYMinusFaceText(_("P"))
            else:
                cube.SetXPlusFaceText(_("L"))
                cube.SetXMinusFaceText(_("R"))
                cube.SetYPlusFaceText(_("P"))
                cube.SetYMinusFaceText(_("A"))
            # Use built-in face text for T/B.
            # SetZFaceTextRotation applies the SAME angle to both Z faces; since T (+Z)
            # and B (-Z) have opposite normals, +90 makes T upright but B upside-down.
            # _UpdateOrientationCubeZTextRotation() switches between +90 and -90 on
            # every render based on the camera's Z position relative to the focal point,
            # so whichever Z face is currently visible always appears upright.
            cube.SetZPlusFaceText(_("T"))
            cube.SetZMinusFaceText(_("B"))
            cube.SetZFaceTextRotation(90)  # initial default; updated dynamically
            # Store reference so _UpdateOrientationCubeZTextRotation can reach the actor.
            self._orientation_cube_actor = cube

            # Wrap in vtkAssembly to ensure the orientation is preserved.
            assembly = vtkAssembly()
            assembly.AddPart(cube)

            widget = vtkOrientationMarkerWidget()
            widget.SetOrientationMarker(assembly)
            widget.SetViewport(*self._map_scene_viewport((0.85, 0.0, 1.0, 0.15)))
            widget.SetInteractor(self.interactor)
            widget.SetEnabled(1)
            widget.InteractiveOff()  # Fixed position – does not move with mouse
            self.orientation_widget = widget

            # Reset retries once successfully shown
            self._cube_retries = 0

            # Add a renderer StartEvent observer so _UpdateOrientationCubeZTextRotation
            # is called before EVERY render — including those from VTK mouse-rotation
            # events that bypass InVesalius's UpdateRender().  Without this, the
            # Z-face text rotation can get stuck at the wrong value whenever the cube
            # is first created (skull may have just changed the focal point) and not
            # get corrected until the next Publisher-triggered render.
            existing_tag = getattr(self, "_cube_render_observer_tag", None)
            if existing_tag is not None:
                try:
                    self.ren.RemoveObserver(existing_tag)
                except Exception:
                    pass
            self._cube_render_observer_tag = self.ren.AddObserver(
                "StartEvent", lambda *_: self._UpdateOrientationCubeZTextRotation()
            )

            self._UpdateOrientationCubeZTextRotation()
            self.UpdateRender()
        except Exception as e:
            import logging

            logging.error("Failed to show orientation cube: %s", e)

    def _UpdateOrientationCubeZTextRotation(self):
        """
        Dynamically keep Z-face letters (T/B) upright by switching
        SetZFaceTextRotation between +90 and -90 based on the camera position.

        Reason: vtkAnnotatedCubeActor exposes only ONE Z-face rotation value
        that applies identically to both the T (+Z) and B (-Z) faces.  Because
        those faces have opposite normals, +90 makes T upright but leaves B
        rotated 180°, while -90 does the reverse.  We resolve this by switching
        the value on every render so that whichever face the camera is looking
        at always appears upright.
        """
        cube = getattr(self, "_orientation_cube_actor", None)
        if cube is None:
            return
        camera = self.ren.GetActiveCamera()
        cam_z = camera.GetPosition()[2]
        focal_z = camera.GetFocalPoint()[2]
        # Camera above focal point → T face is towards camera → use +90
        # Camera below focal point → B face is towards camera → use -90
        rotation = 90 if cam_z >= focal_z else -90
        cube.SetZFaceTextRotation(rotation)

    def OnInteractorEvent(self, sender, event):
        if self._disposed:
            return
        if self.canvas and self.ruler and self.ruler in self.canvas.draw_list:
            view_port_height = round(self.ren.GetActiveCamera().GetParallelScale(), 4)
            if view_port_height != self.prev_view_port_height:
                self.prev_view_port_height = view_port_height
                self.UpdateCanvas()

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
        if sys.platform == "darwin":
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
        if not self.nav_status:
            self.UpdateRender()

    def DeletePointer(self):
        if self.pointer_actor:
            self.ren.RemoveActor(self.pointer_actor)
            self.pointer_actor = None
        self.UpdateRender()

    def OnCloseProject(self):
        if self.navigation is not None and self.navigation.target_coord is not None:
            self.navigation.OnUnsetTarget(None)

        # Disable the orientation cube widget cleanly to prevent visualization
        # artifacts across projects, but leave the object intact so the Python
        # GC can clean it up safely during application exit without segfaulting.
        if self.orientation_widget is not None:
            try:
                self.orientation_widget.SetEnabled(0)
            except Exception:
                pass

        if self.raycasting_volume:
            self.raycasting_volume = False

        if self.slice_plane:
            self.slice_plane.dispose()
            Publisher.sendMessage("Uncheck image plane menu")
            self.mouse_pressed = 0
            self.on_wl = False
            self.slice_plane = None

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
        if not actors:
            return
        from vtkmodules.vtkRenderingCore import vtkActor2D

        for actor in actors:
            if actor is None:
                continue
            if isinstance(actor, vtkActor2D):
                self.ren.AddActor2D(actor)
            else:
                self.ren.AddActor(actor)

    def RemoveVolume(self):
        volumes = self.ren.GetVolumes()
        if volumes.GetNumberOfItems():
            self.ren.RemoveVolume(volumes.GetLastProp())
            if not self.nav_status:
                self.UpdateRender()

    def RemoveActors(self, actors):
        "Remove a list of actors"
        from vtkmodules.vtkRenderingCore import vtkActor2D

        for actor in actors:
            if actor is None:
                continue
            if isinstance(actor, vtkActor2D):
                self.ren.RemoveActor2D(actor)
            else:
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

    def IsTargetMode(self):
        return self.target_mode

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

    def UpdatePointer(self, position):
        """
        Update the position of the pointer sphere. It is done when the navigation without object is on,
        slice planes are moved or a new point is selected from the volume viewer.
        """
        # Update the pointer sphere.
        if self.pointer_actor is None:
            self.CreatePointer()

        # Hide the pointer during targeting, as it would cover the coil center donut
        if self.nav_status:
            self.pointer_actor.SetVisibility(not self.target_mode)
        else:
            self.pointer_actor.SetVisibility(True)

        self.pointer_actor.SetPosition(position)
        # Update the render window manually, as it is not updated automatically when not navigating.
        if not self.nav_status:
            self.UpdateRender()

    def FocusCamera(self, position):
        """
        Orbit the camera around the current focal point (the skull's center)
        so that the measurement exactly faces the screen, without shifting the skull.
        """
        cam = self.ren.GetActiveCamera()

        center = np.array(cam.GetFocalPoint())
        old_pos = np.array(cam.GetPosition())
        target = np.array(position)

        # Calculate distance from camera to center to maintain zoom level
        distance = np.linalg.norm(old_pos - center)

        # Vector from center of the volume pointing outward toward the measurement
        direction = target - center
        dir_norm = np.linalg.norm(direction)

        if dir_norm > 0:
            direction = direction / dir_norm

            # Orbit to the new position while staring back at the center
            new_pos = center + direction * distance

            cam.SetPosition(new_pos[0], new_pos[1], new_pos[2])
            cam.SetViewUp(0, 0, 1)
            self.ren.ResetCameraClippingRange()

        if not self.nav_status:
            self.UpdateRender()

    def __bind_events_wx(self):
        # self.Bind(wx.EVT_SIZE, self.OnSize)
        #  self.canvas.subscribe_event('LeftButtonPressEvent', self.on_insert_point)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)

    def on_insert_point(self, evt):
        pos = evt.position
        self.polygon.append_point(pos)
        self.canvas.Refresh()

        arr = self.canvas.draw_element_to_array(
            [
                self.polygon,
            ]
        )
        imsave("/tmp/polygon.png", arr)

    def SetInteractorStyle(self, state):
        # Check if we're entering or exiting a measurement state
        measurement_states = {
            const.STATE_MEASURE_DISTANCE,
            const.STATE_MEASURE_ANGLE,
            const.STATE_MEASURE_CURVED_LINEAR,
            const.STATE_MEASURE_ANNOTATION,
        }

        entering_measurement = state in measurement_states
        exiting_measurement = (
            hasattr(self, "state")
            and self.state in measurement_states
            and state not in measurement_states
        )

        # Temporarily disable SSAO when entering measurement mode
        if entering_measurement and self.ssao_enabled:
            self.ssao_before_measurement = True
            self._DisableSSAO()

        cleanup = getattr(self.style, "CleanUp", None)
        if cleanup:
            self.style.CleanUp()

        if self.style is not None:
            Publisher.unsubscribe_owner(self.style)

        del self.style

        style = styles.Styles.get_style(state)(self)

        setup = getattr(style, "SetUp", None)
        if setup:
            style.SetUp()

        self.style = style
        self.interactor.SetInteractorStyle(style)

        self.UpdateRender()

        self.state = state

        # Re-enable SSAO when exiting measurement mode (if it was enabled before)
        if exiting_measurement and self.ssao_before_measurement:
            self.ssao_before_measurement = False
            self._EnableSSAO()

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

    def SendActiveCamera(self):
        cam = self.ren.GetActiveCamera()
        Publisher.sendMessage("Receive volume viewer active camera", cam=cam)

    def SendViewerSize(self):
        width, height = self.interactor.GetRenderWindow().GetSize()
        Publisher.sendMessage("Receive volume viewer size", size=(width, height))

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
            self.text.SetValue("WL: %d  WW: %d" % (wl, ww))

    def OnShowRaycasting(self):
        if not self.raycasting_volume:
            self.raycasting_volume = True
            # self._to_show_ball += 1
            # self._check_and_set_ball_visibility()
            if self.on_wl:
                self.text.Show()

            # Disable SSAO when volume rendering is shown (SSAO is only for surfaces)
            if self.ssao_enabled:
                self._DisableSSAO()

    def OnHideRaycasting(self):
        self.raycasting_volume = False
        self.text.Hide()

    def OnSize(self, evt):
        """Handle window resize event to reposition camera for current view"""
        evt.Skip()  # Allow other handlers to process the event first

        # Defer camera repositioning until after the window has fully resized
        # This ensures we get the correct viewport dimensions
        if hasattr(self, "view_angle") and self.view_angle is not None:
            wx.CallAfter(self._DeferredRepositionCamera)

    def _DeferredRepositionCamera(self):
        if self._disposed:
            return
        """Reposition camera after window resize is complete"""
        try:
            # Force render window to update its size
            render_window = self.interactor.GetRenderWindow()
            if render_window:
                render_window.Modified()
                # Give VTK a moment to update internal state
                render_window.Render()

            # Now reposition with correct viewport dimensions
            self.RepositionCamera(self.view_angle)

            if not self.nav_status:
                self.UpdateRender()
        except Exception:
            # If repositioning fails, just skip it
            pass

    def ChangeBackgroundColour(self, colour):
        self.ren.SetBackground(colour[:3])
        self.UpdateRender()

    def AddSurface(self, actor):
        # Add the actor to the renderer.
        ren = self.ren
        ren.AddActor(actor)

        self.surface_added = True

        # make camera projection to parallel (do this early)
        self.ren.GetActiveCamera().ParallelProjectionOn()

        if not self.view_angle:
            # Force actor to update its bounds before repositioning
            actor.Modified()
            ren.ResetCameraClippingRange()

            self.SetViewAngle(const.VOL_FRONT)
            self.view_angle = 1
        else:
            # Force actor to update its bounds before repositioning
            actor.Modified()
            ren.ResetCamera()
            ren.ResetCameraClippingRange()
            self.stored_camera_settings = self.GetCameraSettings()
        if not self.nav_status:
            self.UpdateRender()

        # use the 3D surface actor for measurement calculations
        self.surface = actor

        self.EnableRuler()

        # Apply SSAO if enabled in preferences (for newly created surfaces)
        # Note: For .inv3 file loading, _ApplySSAOAfterProjectLoad will handle it
        session = ses.Session()
        ssao_enabled = session.GetConfig("ssao_enabled", False)
        if ssao_enabled and not self.ssao_enabled:
            self._EnableSSAO()

    def RemoveSurface(self, actor):
        # Remove the actor from the renderer.
        self.ren.RemoveActor(actor)
        if not self.nav_status:
            self.UpdateRender()

        # Remove the ruler if visible.
        if self.ruler:
            self.HideRuler()

    def RemoveAllActors(self):
        self.ren.RemoveAllProps()
        if not self.nav_status:
            self.UpdateRender()

    def LoadSlicePlane(self):
        if self.slice_plane:
            self.slice_plane.dispose()
        self.slice_plane = SlicePlane()

    def LoadVolume(self, volume, colour, ww, wl):
        self.raycasting_volume = True
        # self._to_show_ball += 1
        # self._check_and_set_ball_visibility()

        # Disable SSAO when volume rendering is loaded (SSAO is only for surfaces)
        if self.ssao_enabled:
            self._DisableSSAO()

        self.light = self.ren.GetLights().GetNextItem()

        self.ren.AddVolume(volume)
        self.text.SetValue("WL: %d  WW: %d" % (wl, ww))

        if self.on_wl:
            self.text.Show()
        else:
            self.text.Hide()

        self.ren.SetBackground(colour)

        # make camera projection to parallel (do this early)
        self.ren.GetActiveCamera().ParallelProjectionOn()

        if not (self.view_angle):
            # Force volume to update its bounds before repositioning
            volume.Modified()
            self.ren.ResetCameraClippingRange()

            self.SetViewAngle(const.VOL_FRONT)
            self.view_angle = 1
        else:
            # Force volume to update its bounds before repositioning
            volume.Modified()
            self.ren.ResetCamera()
            self.ren.ResetCameraClippingRange()
            # Apply improved camera positioning for better fit-to-view
            self.RepositionCamera(const.VOL_FRONT)
        if not self.nav_status:
            self.UpdateRender()

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

    def OnSetViewAngle(self, view):
        self.SetViewAngle(view)

    def GetCameraSettings(self):
        camera = self.ren.GetActiveCamera()
        settings = {
            "position": camera.GetPosition(),
            "focal_point": camera.GetFocalPoint(),
            "view_up": camera.GetViewUp(),
            "clipping_range": camera.GetClippingRange(),
            "view_angle": camera.GetViewAngle(),
            "parallel_scale": camera.GetParallelScale(),
        }
        return settings

    def ApplyCameraSettings(self, settings):
        camera = self.ren.GetActiveCamera()
        camera.SetPosition(settings["position"])
        camera.SetFocalPoint(settings["focal_point"])
        camera.SetViewUp(settings["view_up"])
        camera.SetClippingRange(settings["clipping_range"])
        camera.SetViewAngle(settings["view_angle"])
        camera.SetParallelScale(settings["parallel_scale"])

    def RepositionCamera(self, view):
        """
        Adjust camera scaling for optimal fit-to-view of 3D objects.
        Similar to the 2D slice Reposition() method from #1299, but adapted for 3D rendering.
        """
        cam = self.ren.GetActiveCamera()

        # Get viewport dimensions first - if not ready, we can't reposition
        viewport_width, viewport_height = self.ren.GetSize()

        if viewport_width <= 0 or viewport_height <= 0:
            # Viewport not ready yet, skip repositioning
            return

        # Get all actors in the scene to compute combined bounds
        actors = self.ren.GetActors()
        volumes = self.ren.GetVolumes()

        # Collect all bounds
        all_bounds = []

        actors.InitTraversal()
        actor = actors.GetNextItem()
        while actor:
            # Force actor to compute bounds if needed
            actor.Modified()
            bounds = actor.GetBounds()
            if bounds and len(bounds) == 6 and bounds[0] != bounds[1]:  # Valid bounds
                all_bounds.append(bounds)
            actor = actors.GetNextItem()

        volumes.InitTraversal()
        volume = volumes.GetNextItem()
        while volume:
            # Force volume to compute bounds if needed
            volume.Modified()
            bounds = volume.GetBounds()
            if bounds and len(bounds) == 6 and bounds[0] != bounds[1]:  # Valid bounds
                all_bounds.append(bounds)
            volume = volumes.GetNextItem()

        # If no valid bounds, nothing to reposition
        if not all_bounds:
            return

        # Compute combined bounding box
        x_min = min(b[0] for b in all_bounds)
        x_max = max(b[1] for b in all_bounds)
        y_min = min(b[2] for b in all_bounds)
        y_max = max(b[3] for b in all_bounds)
        z_min = min(b[4] for b in all_bounds)
        z_max = max(b[5] for b in all_bounds)

        x_size = x_max - x_min
        y_size = y_max - y_min
        z_size = z_max - z_min

        viewport_aspect = viewport_width / viewport_height

        # Determine which dimensions are visible based on camera position
        # This maps the 3D bounding box to the 2D viewport plane
        cam_pos = cam.GetPosition()

        # Normalize camera position to determine primary viewing direction
        import math

        cam_dist = math.sqrt(cam_pos[0] ** 2 + cam_pos[1] ** 2 + cam_pos[2] ** 2)
        if cam_dist == 0:
            return

        cam_dir = [cam_pos[0] / cam_dist, cam_pos[1] / cam_dist, cam_pos[2] / cam_dist]

        # Determine visible dimensions based on dominant camera direction
        # For orthogonal views, use the two dimensions perpendicular to view direction
        abs_x, abs_y, abs_z = abs(cam_dir[0]), abs(cam_dir[1]), abs(cam_dir[2])

        # Check if this is explicitly ISO view FIRST
        is_iso_view = (view == const.VOL_ISO) if hasattr(const, "VOL_ISO") else False

        # Check if this is an oblique view by checking camera direction
        is_oblique = (
            not (abs_y > abs_x and abs_y > abs_z)
            and not (abs_x > abs_y and abs_x > abs_z)
            and not (abs_z > abs_x and abs_z > abs_y)
        )

        # For ISO view, ALWAYS use projection-based calculation regardless of camera direction
        if is_iso_view or is_oblique:
            # Oblique view (ISO): Account for all three dimensions
            # In isometric view, the object is rotated so all dimensions contribute to what's visible
            # For a full body (tall object), the height is critical and gets projected at an angle

            # Calculate the 3D diagonal - this represents the maximum extent in any direction
            diagonal_3d = math.sqrt(x_size**2 + y_size**2 + z_size**2)

            # For width and height, use a conservative estimate
            # Width sees contribution from X and Y dimensions
            # Height sees contribution from Y and Z dimensions (critical for tall objects)
            width = math.sqrt(x_size**2 + y_size**2)
            height = math.sqrt(y_size**2 + z_size**2)

            # Ensure we use at least the diagonal for the larger dimension
            # This prevents clipping for elongated objects
            max_dim = max(width, height)
            if max_dim < diagonal_3d * 0.8:
                # If our estimate is too small, use a larger value
                if width > height:
                    width = diagonal_3d * 0.85
                else:
                    height = diagonal_3d * 0.85
        elif abs_y > abs_x and abs_y > abs_z:
            width = x_size
            height = z_size
        elif abs_x > abs_y and abs_x > abs_z:
            # Looking along X-axis (RIGHT/LEFT): sees YZ plane
            width = y_size
            height = z_size
        elif abs_z > abs_x and abs_z > abs_y:
            # Looking along Z-axis (TOP/BOTTOM): sees XY plane
            width = x_size
            height = y_size

        if width <= 0 or height <= 0:
            return

        # Calculate object aspect ratio
        object_aspect = width / height

        # Compute proper parallel scale for optimal fit
        # ParallelScale is half the height of the view in world coordinates
        scale_x = (width / viewport_aspect) / 2.0
        scale_y = height / 2.0

        # Use maximum scale to fill viewport as much as possible
        scale = max(scale_x, scale_y)

        # Adaptive margin based on aspect ratio difference
        aspect_ratio_diff = abs(object_aspect - viewport_aspect) / max(
            object_aspect, viewport_aspect
        )

        # Apply margins based on view type (is_iso_view and is_oblique were calculated earlier)
        if is_iso_view or is_oblique:
            # ISO/oblique views: use moderate margins
            # The dimension calculation already accounts for the rotation
            if viewport_aspect >= 1.8:
                margin = 1.25  # Very wide displays
            elif viewport_aspect >= 1.5:
                margin = 1.28  # Wide displays (3:2)
            elif viewport_aspect >= 1.3:
                margin = 1.26  # Moderate displays (4:3)
            elif viewport_aspect >= 1.0:
                margin = 1.25  # Square displays
            else:
                margin = 1.30  # Narrow/portrait displays

            # Additional safety for very small viewports
            if viewport_height < 400:
                margin *= 1.10  # Add 10% extra margin for small windows
        elif aspect_ratio_diff < 0.1:
            # Very similar aspect ratios - moderate margin to prevent edge clipping
            margin = 1.15
        elif aspect_ratio_diff < 0.3:
            # Moderate difference - reasonable margin
            margin = 1.20
        else:
            # Large difference - larger margin
            margin = 1.25

        scale *= margin

        # Apply the calculated scale
        cam.SetParallelScale(scale)
        self.ren.ResetCameraClippingRange()

    def SetViewAngle(self, view):
        # Store the current view angle for resize handling
        self.view_angle = view

        cam = self.ren.GetActiveCamera()

        # Enable parallel projection for consistent scaling
        cam.ParallelProjectionOn()

        cam.SetFocalPoint(0, 0, 0)

        proj = prj.Project()
        orientation = proj.original_orientation

        # In Sagittal scans, the Z-spacing growth order is often backward, reversing the physical sides.
        # We remap the visual requests (Front, Back, etc.) to the underlying coordinate systems.
        if orientation == const.SAGITAL:
            sagital_mapping = {
                const.VOL_FRONT: const.VOL_BACK,
                const.VOL_BACK: const.VOL_FRONT,
            }
            patient_orient = getattr(proj, "patient_orientation", None)

            if patient_orient is not None and len(patient_orient) == 6:
                row_y, row_z = patient_orient[1], patient_orient[2]
                col_y, col_z = patient_orient[4], patient_orient[5]
                normal_x = (row_y * col_z) - (row_z * col_y)

                if normal_x < 0:
                    sagital_mapping[const.VOL_RIGHT] = const.VOL_LEFT
                    sagital_mapping[const.VOL_LEFT] = const.VOL_RIGHT
            else:
                # Maintainer fallback request to apply inversion if orientation is missing
                sagital_mapping[const.VOL_RIGHT] = const.VOL_LEFT
                sagital_mapping[const.VOL_LEFT] = const.VOL_RIGHT

            view = sagital_mapping.get(view, view)

        # Ensure orientation is valid; fallback to AXIAL if not defined in constants
        if orientation not in const.VOLUME_POSITION:
            orientation = const.AXIAL

        xv, yv, zv = const.VOLUME_POSITION[orientation][0][view]
        xp, yp, zp = const.VOLUME_POSITION[orientation][1][view]

        # Dynamically correct Isometric camera pointing on Sagittal datasets
        if orientation == const.SAGITAL and view == const.VOL_ISO:
            yp = 1  # Sagittal maps Anterior to Y=+1 natively

            patient_orient = getattr(proj, "patient_orientation", None)
            if patient_orient is not None and len(patient_orient) == 6:
                row_y, row_z = patient_orient[1], patient_orient[2]
                col_y, col_z = patient_orient[4], patient_orient[5]
                normal_x = (row_y * col_z) - (row_z * col_y)
                if normal_x < 0:
                    xp = (
                        -xp
                    )  # Flip X to see the 'L' side instead of the 'R' side on inverted arrays
            else:
                # Maintainer fallback: apply inversion if orientation is missing
                xp = -xp

        cam.SetViewUp(xv, yv, zv)
        cam.SetPosition(xp, yp, zp)

        self.ren.ResetCameraClippingRange()
        self.ren.ResetCamera()

        # Apply improved camera positioning for better fit-to-view
        # Note: We need to ensure the render window is properly initialized
        # before calculating optimal scale
        try:
            self.RepositionCamera(view)
        except Exception:
            # If repositioning fails (e.g., viewport not ready),
            # the ResetCamera() above will still provide a reasonable view
            pass

        if not self.nav_status:
            self.UpdateRender()

    def UpdateRender(self):
        if self._disposed:
            return
        self._UpdateOrientationCubeZTextRotation()
        self.interactor.Render()

    def SetWidgetInteractor(self, widget=None):
        widget.SetInteractor(self.interactor._Iren)

    def AppendActor(self, actor):
        self.ren.AddActor(actor)

    def _EnableSSAO(self):
        if self._disposed:
            return
        if self.ssao_enabled:
            return

        # Don't enable SSAO during measurement mode (it interferes with picking)
        measurement_states = {
            const.STATE_MEASURE_DISTANCE,
            const.STATE_MEASURE_ANGLE,
            const.STATE_MEASURE_CURVED_LINEAR,
            const.STATE_MEASURE_ANNOTATION,
        }
        if hasattr(self, "state") and self.state in measurement_states:
            # Remember that user wants SSAO enabled, so it will be restored after measurement
            self.ssao_before_measurement = True
            return

        # SSAO should only be applied to surfaces, not volume rendering
        if not self.surface_added or self.raycasting_volume:
            return

        render_window = self.interactor.GetRenderWindow()

        if not render_window:
            return

        if render_window.GetNeverRendered():
            return

        try:
            from vtkmodules.vtkRenderingOpenGL2 import (
                vtkCameraPass,
                vtkRenderStepsPass,
                vtkSSAOPass,
            )

            basic_passes = vtkRenderStepsPass()

            ssao = vtkSSAOPass()
            ssao.SetRadius(0.5)
            ssao.SetBias(0.01)
            ssao.SetKernelSize(128)

            ssao.SetDelegatePass(basic_passes)

            camera_pass = vtkCameraPass()
            camera_pass.SetDelegatePass(ssao)

            self.ren.SetPass(camera_pass)
            self.ssao_pass = camera_pass
            self.ssao_enabled = True

            # Don't save to config here - only Preferences dialog should save
            # session = ses.Session()
            # session.SetConfig("ssao_enabled", True)

            self.UpdateRender()

        except (ImportError, AttributeError):
            pass

    def _DisableSSAO(self):
        if not self.ssao_enabled:
            return

        self.ren.SetPass(None)
        self.ssao_pass = None
        self.ssao_enabled = False

        # Don't save to config here - only Preferences dialog should save
        # session = ses.Session()
        # session.SetConfig("ssao_enabled", False)

        self.UpdateRender()

    def _ApplySSAOAfterProjectLoad(self):
        """Apply SSAO after project is fully loaded from .inv3 file"""
        # Check if SSAO is enabled in preferences
        session = ses.Session()
        ssao_enabled = session.GetConfig("ssao_enabled", False)

        # Only apply if enabled in preferences, surface exists, and not already enabled
        if (
            ssao_enabled
            and self.surface_added
            and not self.ssao_enabled
            and not self.raycasting_volume
        ):
            # Use a timer to retry SSAO application after the window has been rendered
            # This is needed because when loading from .inv3, the render window may not be ready yet

            self._call_later(500, self._RetryEnableSSAO)  # Retry after 500ms

    def _RetryEnableSSAO(self):
        """Retry enabling SSAO after a delay to ensure render window is ready"""
        if self._disposed:
            return
        render_window = self.interactor.GetRenderWindow()
        if render_window:
            if not render_window.GetNeverRendered():
                # Render window is ready, apply SSAO
                self._EnableSSAO()
            else:
                # Render window still not rendered, retry again after another delay

                self._call_later(500, self._RetryEnableSSAO)

    def Reposition3DPlane(self, plane_label):
        if not self.surface_added and not self.raycasting_volume:
            if not self.repositioned_axial_plan and plane_label == "Axial":
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_axial_plan = 1

            elif not self.repositioned_sagital_plan and plane_label == "Sagital":
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_sagital_plan = 1

            elif not self.repositioned_coronal_plan and plane_label == "Coronal":
                self.SetViewAngle(const.VOL_ISO)
                self.repositioned_coronal_plan = 1

    def OnStartSeed(self):
        self.seed_points = []

    def OnEndSeed(self):
        Publisher.sendMessage("Create surface from seeds", seeds=self.seed_points)

    def OnExportPicture(self, orientation, filename, filetype):
        if orientation == const.VOLUME:
            Publisher.sendMessage("Begin busy cursor")
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)  # type: ignore
                self._export_picture(orientation, win_filename, filetype)
            else:
                self._export_picture(orientation, filename, filetype)
            Publisher.sendMessage("End busy cursor")

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
            # Use tiling to generate a large rendering.
            image = vtkRenderLargeImage()
            image.SetInput(self.ren)
            image.SetMagnification(1)
            image.Update()

            image = image.GetOutput()

            # write image file
            if filetype == const.FILETYPE_BMP:
                writer = vtkBMPWriter()
            elif filetype == const.FILETYPE_JPG:
                writer = vtkJPEGWriter()
            elif filetype == const.FILETYPE_PNG:
                writer = vtkPNGWriter()
            elif filetype == const.FILETYPE_PS:
                writer = vtkPostScriptWriter()
            elif filetype == const.FILETYPE_TIF:
                writer = vtkTIFFWriter()
                filename = "{}.tif".format(filename.strip(".tif"))

            writer.SetInputData(image)
            writer.SetFileName(filename.encode(const.FS_ENCODE))
            writer.Write()

        if not os.path.exists(filename):
            wx.MessageBox(
                _("InVesalius was not able to export this picture"), _("Export picture error")
            )

    def OnExportSurface(self, filename, filetype, convert_to_world=False):
        if filetype not in (
            const.FILETYPE_STL,
            const.FILETYPE_VTP,
            const.FILETYPE_PLY,
            const.FILETYPE_STL_ASCII,
            const.FILETYPE_3MF,
        ):
            if _has_win32api:
                utils.touch(filename)
                win_filename = win32api.GetShortPathName(filename)  # type: ignore
                self._export_surface(win_filename, filetype)
            else:
                self._export_surface(filename, filetype)

    def ChangeRenderOrderToExportFile(self):
        """
        Due to the need for self.target_guide_renderer, which is the neuronavigation renderer,
        to be added first, it is necessary to change the order of the renderers in order to
        correctly export the files in obj, vrml, etc. formats. So that only ren and
        canvas_renderer are kept.

        TODO: It is recommended to improve the order in which renderers work in the future.
        """
        if self.target_guide_renderer is None:
            return

        renwin = self.interactor.GetRenderWindow()
        self._target_guide_was_attached = renwin.HasRenderer(self.target_guide_renderer)
        if self._target_guide_was_attached:
            renwin.RemoveRenderer(self.target_guide_renderer)

        self.interactor.Render()

    def RestoreRenderOrderAfterExportFile(self):
        """
        Restores renderer order after export, keeping self.target_guide_renderer,
        ren and canvas_renderer
        """
        if self.target_guide_renderer is None or not getattr(
            self, "_target_guide_was_attached", False
        ):
            return

        renwin = self.interactor.GetRenderWindow()
        for renderer in self.renderers:
            renwin.RemoveRenderer(renderer)
        renwin.AddRenderer(self.target_guide_renderer)
        renwin.SetNumberOfLayers(2)
        for renderer in self.renderers:
            renwin.AddRenderer(renderer)

        self._target_guide_was_attached = False
        self.interactor.Render()

    def _export_surface(self, filename, filetype):
        fileprefix = filename.split(".")[-2]
        renwin = self.interactor.GetRenderWindow()

        self.ChangeRenderOrderToExportFile()

        progress = wx.ProgressDialog(
            "Exporting",
            "Preparing export...",
            maximum=100,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME,
        )
        progress_destroyed = False

        try:
            num_updates = 20
            for i in range(num_updates):
                percent = int(i * 89 / num_updates)
                keep_going, _ = progress.Update(percent, f"Exporting file: {percent}%")
                if not keep_going:
                    progress.Destroy()
                    progress_destroyed = True
                    wx.MessageBox(
                        "Export cancelled by user.", "Export Cancelled", wx.OK | wx.ICON_INFORMATION
                    )
                    return  # If User cancels
                wx.MilliSleep(30)
                wx.Yield()

            progress.Update(90, "Finalizing export...")
            wx.MilliSleep(100)
            wx.Yield()

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
            else:
                raise ValueError("Unsupported filetype")

            progress.Update(100, "Export Complete")
            wx.MilliSleep(100)
            # Used by surface.py if needed
            wx.Yield()
            self.export_successful = True

            wx.MessageBox(
                "Export completed successfully.", "Export success", wx.OK | wx.ICON_INFORMATION
            )

        except Exception as e:
            wx.MessageBox(f"Export failed: {e}", "Export Error", wx.OK | wx.ICON_ERROR)
        finally:
            self.RestoreRenderOrderAfterExportFile()
            if progress and not progress_destroyed:
                try:
                    progress.Destroy()
                except Exception:
                    pass

    def load_mask_preview(self, mask_3d_actor, flag=True):
        if flag:
            self.ren.AddVolume(mask_3d_actor)
        else:
            self.ren.RemoveVolume(mask_3d_actor)

        if flag:
            if not self.view_angle:
                self.SetViewAngle(const.VOL_FRONT)
                self.view_angle = 1

            # Match the parallel projection used by AddSurface/LoadVolume so that
            # GetCompositeProjectionTransformMatrix produces a correct world-to-screen
            # matrix for the 3D mask editor (fixes #1086 – "Edit in 3D" without a
            # surface generated first).
            self.ren.GetActiveCamera().ParallelProjectionOn()

        self.UpdateRender()

    def remove_mask_preview(self, mask_3d_actor):
        self.ren.RemoveVolume(mask_3d_actor)


class SlicePlane:
    def __init__(self):
        self._disposed = False
        project = prj.Project()
        self.original_orientation = project.original_orientation
        self.Create()
        self.enabled = False
        self.__bind_evt()

    def __bind_evt(self):
        Publisher.subscribe(self.Enable, "Enable plane")
        Publisher.subscribe(self.Disable, "Disable plane")
        Publisher.subscribe(self.ChangeSlice, "Change slice from slice plane")
        Publisher.subscribe(self.UpdateAllSlice, "Update all slice")

    def dispose(self):
        if self._disposed:
            return

        self._disposed = True
        Publisher.unsubscribe_owner(self)
        for plane in (self.plane_x, self.plane_y, self.plane_z):
            plane.Off()
        self.DeletePlanes()

    def Create(self):
        plane_x = self.plane_x = vtkImagePlaneWidget()
        plane_x.InteractionOff()
        # Publisher.sendMessage('Input Image in the widget',
        # (plane_x, 'SAGITAL'))
        plane_x.SetPlaneOrientationToXAxes()
        plane_x.TextureVisibilityOn()
        plane_x.SetLeftButtonAction(0)
        plane_x.SetRightButtonAction(0)
        plane_x.SetMiddleButtonAction(0)
        cursor_property = plane_x.GetCursorProperty()
        cursor_property.SetOpacity(0)

        plane_y = self.plane_y = vtkImagePlaneWidget()
        plane_y.DisplayTextOff()
        # Publisher.sendMessage('Input Image in the widget',
        # (plane_y, 'CORONAL'))
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
        # Publisher.sendMessage('Input Image in the widget',
        # (plane_z, 'AXIAL'))
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
        selected_prop3.SetColor(1, 0, 0)

        prop1 = plane_x.GetPlaneProperty()
        prop1.SetColor(0, 0, 1)

        selected_prop1 = plane_x.GetSelectedPlaneProperty()
        selected_prop1.SetColor(0, 0, 1)

        prop2 = plane_y.GetPlaneProperty()
        prop2.SetColor(0, 1, 0)

        selected_prop2 = plane_y.GetSelectedPlaneProperty()
        selected_prop2.SetColor(0, 1, 0)

        Publisher.sendMessage("Set Widget Interactor", widget=plane_x)
        Publisher.sendMessage("Set Widget Interactor", widget=plane_y)
        Publisher.sendMessage("Set Widget Interactor", widget=plane_z)

        Publisher.sendMessage("Render volume viewer")

    def Enable(self, plane_label=None):
        """
        Enable slice widgets (axial, coronal, sagittal) in the volume viewer.

        Parameters
        ----------
        plane_label : str or None, optional
            The label of the plane to enable. Accepted values are "Axial",
            "Coronal", "Sagital". If ``None``, all planes are enabled.
        """
        if plane_label:
            if plane_label == "Axial":
                self.plane_z.On()
                Publisher.sendMessage("Update slice 3D", widget=self.plane_z, orientation="AXIAL")
            elif plane_label == "Coronal":
                self.plane_y.On()
                Publisher.sendMessage("Update slice 3D", widget=self.plane_y, orientation="CORONAL")
            elif plane_label == "Sagital":
                self.plane_x.On()
                Publisher.sendMessage("Update slice 3D", widget=self.plane_x, orientation="SAGITAL")
            Publisher.sendMessage("Reposition 3D Plane", plane_label=plane_label)
        else:
            self.plane_z.On()
            self.plane_x.On()
            self.plane_y.On()
            Publisher.sendMessage("Set volume view angle", view=const.VOL_ISO)
            Publisher.sendMessage("Update all slice")

        Publisher.sendMessage("Render volume viewer")

    def Disable(self, plane_label=None):
        if plane_label:
            if plane_label == "Axial":
                self.plane_z.Off()
            elif plane_label == "Coronal":
                self.plane_y.Off()
            elif plane_label == "Sagital":
                self.plane_x.Off()
        else:
            self.plane_z.Off()
            self.plane_x.Off()
            self.plane_y.Off()

        Publisher.sendMessage("Render volume viewer")

    def ChangeSlice(self, orientation, index):
        if orientation == "CORONAL" and self.plane_y.GetEnabled():
            Publisher.sendMessage("Update slice 3D", widget=self.plane_y, orientation=orientation)
            Publisher.sendMessage("Render volume viewer")

        elif orientation == "SAGITAL" and self.plane_x.GetEnabled():
            Publisher.sendMessage("Update slice 3D", widget=self.plane_x, orientation=orientation)
            Publisher.sendMessage("Render volume viewer")

        elif orientation == "AXIAL" and self.plane_z.GetEnabled():
            Publisher.sendMessage("Update slice 3D", widget=self.plane_z, orientation=orientation)
            Publisher.sendMessage("Render volume viewer")

    def UpdateAllSlice(self):
        Publisher.sendMessage("Update slice 3D", widget=self.plane_y, orientation="CORONAL")
        Publisher.sendMessage("Update slice 3D", widget=self.plane_x, orientation="SAGITAL")
        Publisher.sendMessage("Update slice 3D", widget=self.plane_z, orientation="AXIAL")

    def DeletePlanes(self):
        self.plane_x = None
        self.plane_y = None
        self.plane_z = None
