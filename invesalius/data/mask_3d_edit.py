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
from invesalius.data.polygon_select import PolygonSelectCanvas
from invesalius.pubsub import pub as Publisher
from invesalius.utils import vtkarray_to_numpy
from invesalius_cy.mask_cut import mask_cut, mask_cut_with_depth

if TYPE_CHECKING:
    from vtkmodules.vtkRenderingCore import vtkCamera


class Mask3DEditException(Exception):
    pass


class Mask3DEditor(PolygonSelectCanvas):
    # def get_filter(self, resolution: tuple[int, int]) -> npt.NDArray:
    #     """Create a boolean mask filter based on the polygon points and viewer size."""
    #     w, h = resolution
    #     # get the mask of the polygon in the shape of the screen resolution
    #     filter = polygon2mask((w, h), self.polygon.points)
    #
    #     return filter

    # def CutMaskFrom3D(self):
    #     if not self.complete:
    #         return
    #
    #     Publisher.sendMessage("Send volume viewer size")
    #     Publisher.sendMessage("Send volume viewer active camera")
    #
    #     _filter = self._create_filter().T
    #
    #     # # Unoptimized implementation
    #     # self._cut_mask(self.mask_data[1:, 1:, 1:], s.spacing, _filter)
    #
    #     # Optimized implementation
    #     _mat = self.mask_data[1:, 1:, 1:].copy()
    #
    #     slice = slc.Slice()
    #     sx, sy, sz = slice.spacing
    #
    #     if self.use_depth:
    #         near, far = self.clipping_range
    #         depth = near + (far - near) * self.depth_val
    #         mask_cut_with_depth(
    #             _mat,
    #             sx,
    #             sy,
    #             sz,
    #             depth,
    #             _filter,
    #             self.world_to_screen,
    #             self.world_to_camera_coordinates,
    #             _mat,
    #         )
    #     else:
    #         mask_cut(_mat, sx, sy, sz, _filter, self.world_to_screen, _mat)
    #
    #     _cur_mask = slice.current_mask
    #     _cur_mask.matrix[1:, 1:, 1:] = _mat
    #     _cur_mask.was_edited = True
    #     _cur_mask.modified(all_volume=True)
    #
    #     # Discard all buffers to reupdate view
    #     for ori in ["AXIAL", "CORONAL", "SAGITAL"]:
    #         slice.buffer_slices[ori].discard_buffer()
    #
    #     # Save modification in the history
    #     _cur_mask.save_history(0, "VOLUME", _cur_mask.matrix.copy(), self.mask_data)
    #
    #     Publisher.sendMessage("Update mask 3D preview")
    #     Publisher.sendMessage("Reload actual slice")
    #
    # # Unoptimized implementation
    # def _cut_mask(self, mask_data, spacing, _filter):
    #     """
    #     Cuts an Invesalius Mask with a filter (pixel-wise filter)
    #     mask_data: matrix data without metadata ([1:])
    #     spacing: the spacing used in the mask matrix
    #     _filter: matrix the same size as the viewer that rasterizes
    #     points to be edited
    #     """
    #
    #     def coord_transform(x, y, z, affine):
    #         squeeze = not hasattr(x, "__iter__")
    #         x = np.asanyarray(x)
    #         shape = x.shape
    #         coords = np.c_[
    #             np.atleast_1d(x).flat,
    #             np.atleast_1d(y).flat,
    #             np.atleast_1d(z).flat,
    #             np.ones_like(np.atleast_1d(z).flat),
    #         ].T
    #         x, y, z, _ = np.dot(affine, coords)
    #         if squeeze:
    #             return x.squeeze(), y.squeeze(), z.squeeze()
    #         return np.reshape(x, shape), np.reshape(y, shape), np.reshape(z, shape)
    #
    #     true_indices = np.where(mask_data)
    #     if len(true_indices[0]) == 0:
    #         # No True voxels in mask
    #         return np.zeros_like(mask_data, dtype=bool)
    #
    #     # Get coordinates of True voxels only
    #     x_coords, y_coords, z_coords = true_indices
    #     voxel_coordinates = np.column_stack((z_coords, y_coords, x_coords)).T
    #
    #     # Voxel to world is voxel * spacing (i.e. scale matrix)
    #     scale_matrix = np.eye(4)
    #     scale_matrix[:3, :3] *= spacing
    #
    #     # We want check for each voxel if it is inside the polygon projection (i.e. the
    #     # filter mask)
    #     affine = self.world_to_screen @ scale_matrix
    #
    #     # we don't care about the depth, only if it is within the width x height values
    #     # inside the polygon
    #     width_coords, height_coords, _ = coord_transform(*voxel_coordinates, affine)
    #
    #     # The vtk matrix for the viewport is in the range [-1, 1] for both width and
    #     # height. Transforming to width and height coordinates.
    #     width_coords_within_resolution = np.round(
    #         (width_coords / 2.0 + 0.5) * (self.resolution[0] - 1)
    #     ).astype(int)
    #     height_coords_within_resolution = np.round(
    #         (height_coords / 2.0 + 0.5) * (self.resolution[1] - 1)
    #     ).astype(int)
    #
    #     # Check which coordinates are within screen bounds
    #     valid_screen_coords = (
    #         (width_coords_within_resolution >= 0)
    #         & (width_coords_within_resolution < self.resolution[0])
    #         & (height_coords_within_resolution >= 0)
    #         & (height_coords_within_resolution < self.resolution[1])
    #     )
    #
    #     valid_indices = np.where(valid_screen_coords)[0]
    #
    #     valid_w = width_coords_within_resolution[valid_screen_coords]
    #     valid_h = height_coords_within_resolution[valid_screen_coords]
    #
    #     # Check filter values at these coordinates
    #     filter_values = _filter.T[valid_h, valid_w]
    #     # Set corresponding voxels to True in result
    #     valid_voxel_indices = valid_indices[filter_values]
    #     if len(valid_voxel_indices) > 0:
    #         mask_data[
    #             x_coords[valid_voxel_indices],
    #             y_coords[valid_voxel_indices],
    #             z_coords[valid_voxel_indices],
    #         ] = 0

    # dz, dy, dx = mask_data.shape
    # sx, sy, sz = spacing
    # # Only get coordinates where mask is True
    # true_indices = np.where(mask_data)
    # if len(true_indices[0]) == 0:
    #     # No True voxels in mask
    #     return np.zeros_like(mask_data, dtype=bool)
    #
    # # Get coordinates of True voxels only
    # x_coords = true_indices[2]  # x coordinates
    # y_coords = true_indices[1]  # y coordinates
    # z_coords = true_indices[0]  # z coordinates
    #
    # M = self.world_to_screen
    # h, w = _filter.T.shape
    #
    # for z, y, x in zip(z_coords, y_coords, x_coords):
    #     # Voxel to world space
    #     p0 = x * sx
    #     p1 = y * sy
    #     p2 = z * sz
    #     p3 = 1.0
    #
    #     # _q = M * _p
    #     _q0 = p0 * M[0, 0] + p1 * M[0, 1] + p2 * M[0, 2] + p3 * M[0, 3]
    #     _q1 = p0 * M[1, 0] + p1 * M[1, 1] + p2 * M[1, 2] + p3 * M[1, 3]
    #     _q2 = p0 * M[2, 0] + p1 * M[2, 1] + p2 * M[2, 2] + p3 * M[2, 3]
    #     _q3 = p0 * M[3, 0] + p1 * M[3, 1] + p2 * M[3, 2] + p3 * M[3, 3]
    #
    #     if _q3 > 0:
    #         q0 = _q0 / _q3
    #         q1 = _q1 / _q3
    #         q2 = _q2 / _q3
    #
    #         # Normalized coordinates back to pixels
    #         px = (q0 / 2.0 + 0.5) * (w - 1)
    #         py = (q1 / 2.0 + 0.5) * (h - 1)
    #
    #         if 0 <= px < w and 0 <= py < h:
    #             if (
    #                 _filter.T[int(py), int(px)] == 1
    #             ):  # NOTE: The lack of round here might be a problem
    #                 mask_data[z, y, x] = 0
