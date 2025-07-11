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

from typing import TYPE_CHECKING

import numpy as np
from skimage.draw import polygon2mask

import invesalius.constants as const
import invesalius.data.slice_ as slc
from invesalius.pubsub import pub as Publisher
from invesalius_cy.mask_cut import mask_cut, mask_cut_with_depth

if TYPE_CHECKING:
    from vtkmodules.vtkRenderingCore import vtkCamera


class Mask3DEditException(Exception):
    pass


class Mask3DEditor:
    resolution: tuple[int, int]
    clipping_range: tuple[float, float]

    def __init__(self):
        self.__bind_events()
        self.polygons_to_operate = []
        self.edit_mode = const.MASK_3D_EDIT_INCLUDE
        self.use_depth = False
        self.depth_val = None
        self.model_to_screen = None
        self.model_view = None

    def __bind_events(self):
        Publisher.subscribe(self.AddPolygon, "M3E add polygon")
        Publisher.subscribe(self.CutMaskFrom3D, "M3E cut mask from 3D")
        Publisher.subscribe(self.ClearPolygons, "M3E clear polygons")
        Publisher.subscribe(
            self.ReceiveVolumeViewerActiveCamera, "Receive volume viewer active camera"
        )
        Publisher.subscribe(self.ReceiveVolumeViewerSize, "Receive volume viewer size")
        Publisher.subscribe(self.SetEditMode, "M3E set edit mode")
        Publisher.subscribe(self.SetUseDepthForEdit, "M3E use depth")
        Publisher.subscribe(self.SetDepthValue, "M3E depth value")

    def AddPolygon(self, points):
        """
        Adds polygon to be used in the edit
        """
        self.polygons_to_operate.append(points)

    def ClearPolygons(self):
        """
        Discards all added polygons
        """
        self.polygons_to_operate = []

    def ReceiveVolumeViewerActiveCamera(self, cam: "vtkCamera"):
        width, height = self.resolution

        near, far = cam.GetClippingRange()

        # This flip around the Y axis was done to countereffect the flip that vtk performs
        # in volume.py:780. If we do not flip back, what is being displayed is flipped,
        # although the actual coordinates are the initial ones, so the cutting gets wrong
        # after rotations around y or x.
        inv_Y_matrix = np.eye(4)
        inv_Y_matrix[1, 1] = -1

        # Composite transform world coordinates to viewport coordinates
        # This is a concatenation of the view transform (world coordinates to camera
        # coordinates) and the projection transform (camera coordinates to viewport
        # coordinates).
        M = cam.GetCompositeProjectionTransformMatrix(width / float(height), near, far)
        M = vtkarray_to_numpy(M)
        self.world_to_screen = M @ inv_Y_matrix

        # Get the model view matrix, which transforms world coordinates to camera
        # coordinates.
        MV = cam.GetViewTransformMatrix()
        MV = vtkarray_to_numpy(MV)
        self.world_to_camera_coordinates = MV @ inv_Y_matrix

    def ReceiveVolumeViewerSize(self, size: tuple[int, int]):
        self.resolution = size

    def SetEditMode(self, mode):
        """
        Sets edit mode to either discard points within or outside
        the polygon.
        """
        self.edit_mode = mode

    def SetUseDepthForEdit(self, use):
        """
        Sets whether to perform a mask cut using depth or through all
        """
        self.use_depth = use

    def SetDepthValue(self, value):
        self.depth_val = value

    def _create_filter(self):
        """
        Based on the polygons and screen resolution,
        create a filter for the edit.
        """
        w, h = self.resolution
        # gets the mask of each polygon in the shape of the screen resolution
        polygon_masks = [
            polygon2mask((w, h), poly.polygon.points) for poly in self.polygons_to_operate
        ]

        # OR operation in all masks to create a single filter mask
        _filter = np.logical_or.reduce(polygon_masks)

        # If the edit mode is to include, we invert the filter
        if self.edit_mode == const.MASK_3D_EDIT_INCLUDE:
            np.logical_not(_filter, out=_filter)

        return _filter

    # Unoptimized implementation
    def _cut_mask(self, mask_data, spacing, _filter):
        """
        Cuts an Invesalius Mask with a filter (pixel-wise filter)
        mask_data: matrix data without metadata ([1:])
        spacing: the spacing used in the mask matrix
        _filter: matrix the same size as the viewer that rasterizes
        points to be edited
        """

        dz, dy, dx = mask_data.shape
        sx, sy, sz = spacing

        M = self.model_to_screen
        h, w = _filter.shape

        for z in range(dz):
            for y in range(dy):
                for x in range(dx):
                    # Voxel to world space
                    p0 = x * sx
                    p1 = y * sy
                    p2 = z * sz
                    p3 = 1.0

                    # _q = M * _p
                    _q0 = p0 * M[0, 0] + p1 * M[0, 1] + p2 * M[0, 2] + p3 * M[0, 3]
                    _q1 = p0 * M[1, 0] + p1 * M[1, 1] + p2 * M[1, 2] + p3 * M[1, 3]
                    _q2 = p0 * M[2, 0] + p1 * M[2, 1] + p2 * M[2, 2] + p3 * M[2, 3]
                    _q3 = p0 * M[3, 0] + p1 * M[3, 1] + p2 * M[3, 2] + p3 * M[3, 3]

                    if _q3 > 0:
                        q0 = _q0 / _q3
                        q1 = _q1 / _q3
                        q2 = _q2 / _q3

                        # Normalized coordinates back to pixels
                        px = (q0 / 2.0 + 0.5) * (w - 1)
                        py = (q1 / 2.0 + 0.5) * (h - 1)

                        if 0 <= px < w and 0 <= py < h:
                            if (
                                _filter[int(py), int(px)] == 1
                            ):  # NOTE: The lack of round here might be a problem
                                mask_data[z, y, x] = 0

    def CutMaskFrom3D(self):
        if len(self.polygons_to_operate) == 0:
            return

        s = slc.Slice()
        _cur_mask = s.current_mask

        Publisher.sendMessage("Send volume viewer size")
        Publisher.sendMessage("Send volume viewer active camera")

        if _cur_mask is None:
            raise Mask3DEditException("Attempted editing a non-existent mask")

        _filter = self._create_filter().T

        _prev_mat = _cur_mask.matrix.copy()

        # # Unoptimized implementation
        # self._cut_mask(_cur_mask.matrix[1:, 1:, 1:], s.spacing, _filter)

        # Optimized implementation
        _mat = _cur_mask.matrix[1:, 1:, 1:].copy()
        sx, sy, sz = s.spacing

        print(s.spacing)
        print(_mat.shape)

        if self.use_depth:
            near, far = self.clipping_range
            depth = near + (far - near) * self.depth_val
            mask_cut_with_depth(
                _mat,
                sx,
                sy,
                sz,
                depth,
                _filter,
                self.world_to_screen,
                self.world_to_camera_coordinates,
                _mat,
            )
        else:
            mask_cut(_mat, sx, sy, sz, _filter, self.world_to_screen, _mat)

        _cur_mask.matrix[1:, 1:, 1:] = _mat
        _cur_mask.was_edited = True
        _cur_mask.modified(all_volume=True)

        # Discard all buffers to reupdate view
        for ori in ["AXIAL", "CORONAL", "SAGITAL"]:
            s.buffer_slices[ori].discard_buffer()

        # Save modification in the history
        _cur_mask.save_history(0, "VOLUME", _cur_mask.matrix.copy(), _prev_mat)

        Publisher.sendMessage("Update mask 3D preview")
        Publisher.sendMessage("Reload actual slice")
