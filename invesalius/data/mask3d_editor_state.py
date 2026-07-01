from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import wx
from skimage.draw import polygon2mask
from vtkmodules.vtkRenderingCore import vtkCoordinate

import invesalius.constants as const
import invesalius.data.slice_ as slc
import invesalius.session as ses
from invesalius.data.polygon_select import PolygonSelectCanvas
from invesalius.pubsub import pub as Publisher
from invesalius.utils import vtkarray_to_numpy
from invesalius_rs import mask_cut


@dataclass
class Mask3DEditorState:
    """State manager for the 3D Mask Editor.

    This class handles the core logic of managing mask 3D edits, such as storing
    polygons, determining depth/edit mode, and cutting the 3D volume.
    It decouples the heavy data operations from the VTK UI loop.
    """

    viewer: Any
    mask_data: npt.NDArray | None = None
    m3e_list: list[PolygonSelectCanvas] = field(default_factory=list)
    edit_mode: int = const.MASK_3D_EDIT_INCLUDE
    depth_val: float = 1.0
    has_set_mask_preview: bool = False

    resolution: tuple[int, int] = field(init=False)
    world_to_screen: npt.NDArray | None = field(default=None, init=False)
    world_to_camera_coordinates: npt.NDArray | None = field(default=None, init=False)
    clipping_range: tuple[float, float] | None = field(default=None, init=False)

    def __post_init__(self):
        self.resolution = tuple(self.viewer.GetSize())
        self._bind_events()

    def _bind_events(self):
        sub = Publisher.subscribe
        sub(self.ClearPolygons, "M3E clear polygons")
        sub(self.ReceiveVolumeViewerActiveCamera, "Receive volume viewer active camera")
        sub(self.ReceiveVolumeViewerSize, "Receive volume viewer size")
        sub(self.CutMaskFromPolygons, "M3E cut mask from 3D")
        sub(self.SetEditMode, "M3E set edit mode")
        sub(self.SetDepthValue, "M3E set depth value")
        sub(self.OnMaskChanged, "Change mask selected")

    def setup_state(self):
        """Called when the editor is activated."""
        for drawn_polygon in self.viewer.canvas.draw_list:
            if isinstance(drawn_polygon, PolygonSelectCanvas):
                drawn_polygon.visible = True
                drawn_polygon.set_interactive(True)
                self.m3e_list.append(drawn_polygon)

        Publisher.sendMessage("M3E ask for edit mode")
        Publisher.sendMessage("M3E ask for depth value")

        if not ses.Session().mask_3d_preview:
            self.has_set_mask_preview = True
            Publisher.sendMessage("Enable mask 3D preview")

        if slc.Slice().current_mask:
            self.mask_data = slc.Slice().current_mask.matrix.copy()

        if not self.has_set_mask_preview:
            Publisher.sendMessage("Render volume viewer")

    def cleanup_state(self):
        """Called when the editor is deactivated."""
        self.viewer.canvas.draw_list = [
            drawn_item
            for drawn_item in self.viewer.canvas.draw_list
            if not isinstance(drawn_item, PolygonSelectCanvas)
        ]
        self.m3e_list.clear()

        if self.has_set_mask_preview:
            Publisher.sendMessage("Disable mask 3D preview")

    def SetEditMode(self, mode: int):
        self.edit_mode = mode
        Publisher.sendMessage("M3E cut mask from 3D")

    def SetDepthValue(self, value: float):
        self.depth_val = value
        Publisher.sendMessage("M3E cut mask from 3D")

    def init_new_polygon(self):
        self.m3e_list.append(PolygonSelectCanvas())
        self.viewer.canvas.draw_list.append(self.m3e_list[-1])

    def insert_point(self, mouse_x, mouse_y, world_point):
        if len(self.m3e_list) == 0 or self.m3e_list[-1].complete:
            self.init_new_polygon()

        current_masker = self.m3e_list[-1]
        current_masker.insert_point((mouse_x, mouse_y), world_point)
        self.viewer.UpdateCanvas()

    def complete_current_polygon(self):
        if len(self.m3e_list) > 0 and not self.m3e_list[-1].complete:
            self.m3e_list[-1].complete_polygon()
            Publisher.sendMessage("M3E cut mask from 3D")
            self.viewer.UpdateCanvas()

    def ClearPolygons(self):
        self.viewer.canvas.draw_list = [
            drawn_item
            for drawn_item in self.viewer.canvas.draw_list
            if not isinstance(drawn_item, PolygonSelectCanvas)
        ]
        self.m3e_list.clear()
        self.OnRestoreInitMask()
        self.viewer.UpdateCanvas()

    def ReceiveVolumeViewerActiveCamera(self, cam):
        width, height = self.resolution
        near, far = self.clipping_range = cam.GetClippingRange()

        inv_Y_matrix = np.eye(4)
        inv_Y_matrix[1, 1] = -1

        M = cam.GetCompositeProjectionTransformMatrix(width / float(height), near, far)
        M = vtkarray_to_numpy(M)
        self.world_to_screen = M @ inv_Y_matrix

        MV = cam.GetViewTransformMatrix()
        MV = vtkarray_to_numpy(MV)
        self.world_to_camera_coordinates = MV @ inv_Y_matrix

    def ReceiveVolumeViewerSize(self, size: tuple[int, int]):
        self.resolution = size

    def OnRestoreInitMask(self):
        if self.mask_data is not None:
            _mat = self.mask_data[1:, 1:, 1:].copy()
            self.update_views(_mat)

    def get_filters(self) -> list[npt.NDArray]:
        w, h = self.resolution
        renderer = self.viewer.ren
        coord = vtkCoordinate()
        filters = []
        for poly_canvas in self.m3e_list:
            display_points = []
            for world_pt in poly_canvas._world_points:
                coord.SetValue(world_pt)
                px, py = coord.GetComputedDoubleDisplayValue(renderer)
                display_points.append((px, py))
            filters.append(polygon2mask((w, h), display_points))
        return filters

    def CutMaskFromPolygons(self):
        completed_polygons = [m3e for m3e in self.m3e_list if m3e.complete]
        if len(completed_polygons) == 0:
            return

        if self.mask_data is None:
            return

        Publisher.sendMessage("Send volume viewer size")
        Publisher.sendMessage("Send volume viewer active camera")

        w, h = self.resolution
        if h == 0:
            return

        filters = self.get_filters()
        filter = np.logical_or.reduce(filters).T

        if self.edit_mode == const.MASK_3D_EDIT_INCLUDE:
            np.logical_not(filter, out=filter)

        _mat = self.mask_data[1:, 1:, 1:].copy()
        out = _mat.copy()

        slice = slc.Slice()
        sx, sy, sz = slice.spacing

        if (
            self.clipping_range is None
            or self.world_to_screen is None
            or self.world_to_camera_coordinates is None
        ):
            return

        near, far = self.clipping_range
        depth = near + (far - near) * self.depth_val

        wts = self.world_to_screen
        wtc = self.world_to_camera_coordinates

        mask_cut(_mat, sx, sy, sz, depth, filter, wts, wtc, out, self.edit_mode)  # type: ignore

        self.update_views(out)

    def OnMaskChanged(self, index: int):
        cur_mask = slc.Slice().current_mask
        if cur_mask is not None:
            self.mask_data = cur_mask.matrix.copy()

    def update_views(self, _mat: npt.NDArray):
        slice = slc.Slice()
        _cur_mask = slice.current_mask
        if _cur_mask is not None:
            _cur_mask.matrix[:] = 1  # type: ignore
            _cur_mask.matrix[1:, 1:, 1:] = _mat  # type: ignore
            _cur_mask.was_edited = True

            if _cur_mask.volume is not None and ses.Session().mask_3d_preview:
                _cur_mask.imagedata = _cur_mask.as_vtkimagedata()
                _cur_mask.volume.change_imagedata()

            _cur_mask.modified(all_volume=True)

        for ori in ["AXIAL", "CORONAL", "SAGITAL"]:
            slice.buffer_slices[ori].discard_buffer()

        if _cur_mask is not None:
            _cur_mask.save_history(0, "VOLUME", _cur_mask.matrix.copy(), self.mask_data)

        Publisher.sendMessage("Render volume viewer")
        Publisher.sendMessage("Reload actual slice")
