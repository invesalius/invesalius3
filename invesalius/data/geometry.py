# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br/
#               http://www.cti.gov.br/invesalius
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

import math

import numpy as np
from vtkmodules.vtkRenderingCore import vtkCoordinate

import invesalius.constants as const
import invesalius.utils as utils
from invesalius.pubsub import pub as Publisher


class Box(metaclass=utils.Singleton):
    """
    This class is a data structure for storing the
    coordinates (min and max) of box used in crop-mask.
    """

    def __init__(self):
        self.xi = None
        self.xf = None

        self.yi = None
        self.yf = None

        self.zi = None
        self.zf = None

        self.size_x = None
        self.size_y = None
        self.size_z = None

        self.sagital = {}
        self.coronal = {}
        self.axial = {}

        self.xs = None
        self.ys = None
        self.zs = None

        self.first_run = True

    def SetX(self, i, f):
        self.xi = i
        self.xf = f
        self.size_x = f

    def SetY(self, i, f):
        self.yi = i
        self.yf = f
        self.size_y = f

    def SetZ(self, i, f):
        self.zi = i
        self.zf = f
        self.size_z = f

    def SetSpacing(self, x, y, z):
        self.xs = x
        self.ys = y
        self.zs = z

        self.xi = self.xi * self.xs
        self.xf = self.xf * self.xs

        self.yi = self.yi * self.ys
        self.yf = self.yf * self.ys

        self.zi = self.zi * self.zs
        self.zf = self.zf * self.zs

        self.size_x = self.size_x * self.xs
        self.size_y = self.size_y * self.ys
        self.size_z = self.size_z * self.zs

        if self.first_run:
            self.first_run = False

    def MakeMatrix(self):
        """
        Update values in a matrix to each orientation.
        """

        self.sagital[const.SAGITAL_LEFT] = [
            [self.xi, self.yi - (self.ys / 2), self.zi],
            [self.xi, self.yi - (self.ys / 2), self.zf],
        ]

        self.sagital[const.SAGITAL_RIGHT] = [
            [self.xi, self.yf + (self.ys / 2), self.zi],
            [self.xi, self.yf + (self.ys / 2), self.zf],
        ]

        self.sagital[const.SAGITAL_BOTTOM] = [
            [self.xi, self.yi, self.zi - (self.zs / 2)],
            [self.xi, self.yf, self.zi - (self.zs / 2)],
        ]

        self.sagital[const.SAGITAL_UPPER] = [
            [self.xi, self.yi, self.zf + (self.zs / 2)],
            [self.xi, self.yf, self.zf + (self.zs / 2)],
        ]

        self.coronal[const.CORONAL_BOTTOM] = [
            [self.xi, self.yi, self.zi - (self.zs / 2)],
            [self.xf, self.yf, self.zi - (self.zs / 2)],
        ]

        self.coronal[const.CORONAL_UPPER] = [
            [self.xi, self.yi, self.zf + (self.zs / 2)],
            [self.xf, self.yf, self.zf + (self.zs / 2)],
        ]

        self.coronal[const.CORONAL_LEFT] = [
            [self.xi - (self.xs / 2), self.yi, self.zi],
            [self.xi - (self.xs / 2), self.yf, self.zf],
        ]

        self.coronal[const.CORONAL_RIGHT] = [
            [self.xf + (self.xs / 2), self.yi, self.zi],
            [self.xf + (self.xs / 2), self.yf, self.zf],
        ]

        self.axial[const.AXIAL_BOTTOM] = [
            [self.xi, self.yi - (self.ys / 2), self.zi],
            [self.xf, self.yi - (self.ys / 2), self.zf],
        ]

        self.axial[const.AXIAL_UPPER] = [
            [self.xi, self.yf + (self.ys / 2), self.zi],
            [self.xf, self.yf + (self.ys / 2), self.zf],
        ]

        self.axial[const.AXIAL_LEFT] = [
            [self.xi - (self.xs / 2), self.yi, self.zi],
            [self.xi - (self.xs / 2), self.yf, self.zf],
        ]

        self.axial[const.AXIAL_RIGHT] = [
            [self.xf + (self.xs / 2), self.yi, self.zi],
            [self.xf + (self.xs / 2), self.yf, self.zf],
        ]

        Publisher.sendMessage("Update crop limits into gui", limits=self.GetLimits())

    def GetLimits(self):
        """
        Return the bounding box limits (initial and final) in x, y and z.
        """

        limits = [
            int(self.xi / self.xs),
            int(self.xf / self.xs),
            int(self.yi / self.ys),
            int(self.yf / self.ys),
            int(self.zi / self.zs),
            int(self.zf / self.zs),
        ]

        return limits

    def UpdatePositionBySideBox(self, pc, axis, position):
        """
        Checks the coordinates are in any side of box and update it.
        Is necessary to move limits of box.
        """

        if axis == "AXIAL":
            if position == const.AXIAL_UPPER:
                if pc[1] > self.yi and pc[1] > 0 and pc[1] <= self.size_y:
                    self.yf = pc[1]

            if position == const.AXIAL_BOTTOM:
                if pc[1] < self.yf and pc[1] >= 0:
                    self.yi = pc[1]

            if position == const.AXIAL_LEFT:
                if pc[0] < self.xf and pc[0] >= 0:
                    self.xi = pc[0]

            if position == const.AXIAL_RIGHT:
                if pc[0] > self.xi and pc[0] <= self.size_x:
                    self.xf = pc[0]

        if axis == "SAGITAL":
            if position == const.SAGITAL_UPPER:
                if pc[2] > self.zi and pc[2] > 0 and pc[2] <= self.size_z:
                    self.zf = pc[2]

            if position == const.SAGITAL_BOTTOM:
                if pc[2] < self.zf and pc[2] >= 0:
                    self.zi = pc[2]

            if position == const.SAGITAL_LEFT:
                if pc[1] < self.yf and pc[1] >= 0:
                    self.yi = pc[1]

            if position == const.SAGITAL_RIGHT:
                if pc[1] > self.yi and pc[1] <= self.size_y:
                    self.yf = pc[1]

        if axis == "CORONAL":
            if position == const.CORONAL_UPPER:
                if pc[2] > self.zi and pc[2] > 0 and pc[2] <= self.size_z:
                    self.zf = pc[2]

            if position == const.CORONAL_BOTTOM:
                if pc[2] < self.zf and pc[2] >= 0:
                    self.zi = pc[2]

            if position == const.CORONAL_LEFT:
                if pc[0] < self.xf and pc[0] >= 0:
                    self.xi = pc[0]

            if position == const.CORONAL_RIGHT:
                if pc[0] > self.yi and pc[0] <= self.size_y:
                    self.xf = pc[0]

        self.MakeMatrix()

    def UpdatePositionByInsideBox(self, pc, axis):
        """
        Checks the coordinates are inside the box and update it.
        Is necessary to move box in pan event.
        """

        if axis == "AXIAL":
            if self.yf + pc[1] <= self.size_y and self.yi + pc[1] >= 0:
                self.yf = self.yf + pc[1]
                self.yi = self.yi + pc[1]

            if self.xf + pc[0] <= self.size_x and self.xi + pc[0] >= 0:
                self.xf = self.xf + pc[0]
                self.xi = self.xi + pc[0]

        if axis == "SAGITAL":
            if self.yf + pc[1] <= self.size_y and self.yi + pc[1] >= 0:
                self.yf = self.yf + pc[1]
                self.yi = self.yi + pc[1]

            if self.zf + pc[2] <= self.size_z and self.zi + pc[2] >= 0:
                self.zf = self.zf + pc[2]
                self.zi = self.zi + pc[2]

        if axis == "CORONAL":
            if self.xf + pc[0] <= self.size_x and self.xi + pc[0] >= 0:
                self.xf = self.xf + pc[0]
                self.xi = self.xi + pc[0]

            if self.zf + pc[2] <= self.size_z and self.zi + pc[2] >= 0:
                self.zf = self.zf + pc[2]
                self.zi = self.zi + pc[2]

        self.MakeMatrix()


class DrawCrop2DRetangle:
    """
    This class is responsible for draw and control user
    interactions with the box. Each side of box is displayed in an
    anatomical orientation (axial, sagital or coronal).
    """

    def __init__(self):
        self.viewer = None
        self.points_in_display = {}
        self.box = None
        self.mouse_pressed = False
        self.canvas = None
        self.status_move = None
        self.crop_pan = None
        self.last_x = 0
        self.last_y = 0
        self.last_z = 0
        self.layer = 0

    def MouseMove(self, x, y):
        self.MouseInLine(x, y)

        # x_pos_sl_, y_pos_sl_ = self.viewer.get_slice_pixel_coord_by_screen_pos(x, y)
        slice_spacing = self.viewer.slice_.spacing
        xs, ys, zs = slice_spacing

        # x_pos_sl = x_pos_sl_ * xs
        # y_pos_sl = y_pos_sl_ * ys

        x, y, z = self.viewer.get_voxel_coord_by_screen_pos(x, y)

        if self.viewer.orientation == "AXIAL":
            if self.status_move == const.AXIAL_UPPER or self.status_move == const.AXIAL_BOTTOM:
                Publisher.sendMessage("Set interactor resize NS cursor")
            elif self.status_move == const.AXIAL_LEFT or self.status_move == const.AXIAL_RIGHT:
                Publisher.sendMessage("Set interactor resize WE cursor")
            elif self.crop_pan == const.CROP_PAN:
                Publisher.sendMessage("Set interactor resize NSWE cursor")
            else:
                Publisher.sendMessage("Set interactor default cursor")

        if self.viewer.orientation == "SAGITAL":
            if self.status_move == const.SAGITAL_UPPER or self.status_move == const.SAGITAL_BOTTOM:
                Publisher.sendMessage("Set interactor resize NS cursor")
            elif self.status_move == const.SAGITAL_LEFT or self.status_move == const.SAGITAL_RIGHT:
                Publisher.sendMessage("Set interactor resize WE cursor")
            elif self.crop_pan == const.CROP_PAN:
                Publisher.sendMessage("Set interactor resize NSWE cursor")
            else:
                Publisher.sendMessage("Set interactor default cursor")

        if self.viewer.orientation == "CORONAL":
            if self.status_move == const.CORONAL_UPPER or self.status_move == const.CORONAL_BOTTOM:
                Publisher.sendMessage("Set interactor resize NS cursor")
            elif self.status_move == const.CORONAL_LEFT or self.status_move == const.CORONAL_RIGHT:
                Publisher.sendMessage("Set interactor resize WE cursor")
            elif self.crop_pan == const.CROP_PAN:
                Publisher.sendMessage("Set interactor resize NSWE cursor")
            else:
                Publisher.sendMessage("Set interactor default cursor")

        if self.mouse_pressed and self.status_move:
            self.box.UpdatePositionBySideBox(
                (x * xs, y * ys, z * zs), self.viewer.orientation, self.status_move
            )

        nv_x = x - self.last_x
        nv_y = y - self.last_y
        nv_z = z - self.last_z

        if self.mouse_pressed and self.crop_pan:
            self.box.UpdatePositionByInsideBox(
                (nv_x * xs, nv_y * ys, nv_z * zs), self.viewer.orientation
            )

        self.last_x = x
        self.last_y = y
        self.last_z = z

        Publisher.sendMessage("Redraw canvas")

    def ReleaseLeft(self):
        self.status_move = None

    def LeftPressed(self, x, y):
        self.mouse_pressed = True

    def MouseInLine(self, x, y):
        x_pos_sl_, y_pos_sl_ = self.viewer.get_slice_pixel_coord_by_screen_pos(x, y)

        slice_spacing = self.viewer.slice_.spacing
        xs, ys, zs = slice_spacing

        if self.viewer.orientation == "AXIAL":
            x_pos_sl = x_pos_sl_ * xs
            y_pos_sl = y_pos_sl_ * ys

            for k, p in self.box.axial.items():
                p0 = p[0]
                p1 = p[1]

                dist = self.distance_from_point_line(
                    (p0[0], p0[1]), (p1[0], p1[1]), (x_pos_sl, y_pos_sl)
                )

                if dist <= 2:
                    if self.point_between_line(p0, p1, (x_pos_sl, y_pos_sl), "AXIAL"):
                        self.status_move = k
                        break

                if (
                    self.point_into_box(p0, p1, (x_pos_sl, y_pos_sl), "AXIAL")
                    and self.status_move is None
                ):
                    self.crop_pan = const.CROP_PAN
                    # break
                else:
                    if self.crop_pan:
                        self.crop_pan = None
                        break

                if not (self.mouse_pressed) and k != self.status_move:
                    self.status_move = None

        if self.viewer.orientation == "CORONAL":
            x_pos_sl = x_pos_sl_ * xs
            y_pos_sl = y_pos_sl_ * zs

            for k, p in self.box.coronal.items():
                p0 = p[0]
                p1 = p[1]

                dist = self.distance_from_point_line(
                    (p0[0], p0[2]), (p1[0], p1[2]), (x_pos_sl, y_pos_sl)
                )
                if dist <= 2:
                    if self.point_between_line(p0, p1, (x_pos_sl, y_pos_sl), "CORONAL"):
                        self.status_move = k
                        break

                if (
                    self.point_into_box(p0, p1, (x_pos_sl, y_pos_sl), "CORONAL")
                    and self.status_move is None
                ):
                    self.crop_pan = const.CROP_PAN
                    # break
                else:
                    if self.crop_pan:
                        self.crop_pan = None
                        break

                if not (self.mouse_pressed) and k != self.status_move:
                    self.status_move = None

        if self.viewer.orientation == "SAGITAL":
            x_pos_sl = x_pos_sl_ * ys
            y_pos_sl = y_pos_sl_ * zs

            for k, p in self.box.sagital.items():
                p0 = p[0]
                p1 = p[1]

                dist = self.distance_from_point_line(
                    (p0[1], p0[2]), (p1[1], p1[2]), (x_pos_sl, y_pos_sl)
                )

                if dist <= 2:
                    if self.point_between_line(p0, p1, (x_pos_sl, y_pos_sl), "SAGITAL"):
                        self.status_move = k
                        break

                if (
                    self.point_into_box(p0, p1, (x_pos_sl, y_pos_sl), "SAGITAL")
                    and self.status_move is None
                ):
                    self.crop_pan = const.CROP_PAN
                    # break
                else:
                    if self.crop_pan:
                        self.crop_pan = None
                        break

                if not (self.mouse_pressed) and k != self.status_move:
                    self.status_move = None

    def draw_to_canvas(self, gc, canvas):
        """
        Draws to an wx.GraphicsContext.

        Parameters:
            gc: is a wx.GraphicsContext
            canvas: the canvas it's being drawn.
        """
        self.canvas = canvas
        self.UpdateValues(canvas)

    def point_into_box(self, p1, p2, pc, axis):
        if axis == "AXIAL":
            if (
                pc[0] > self.box.xi + 10
                and pc[0] < self.box.xf - 10
                and pc[1] - 10 > self.box.yi
                and pc[1] < self.box.yf - 10
            ):
                return True
            else:
                return False

        if axis == "SAGITAL":
            if (
                pc[0] > self.box.yi + 10
                and pc[0] < self.box.yf - 10
                and pc[1] - 10 > self.box.zi
                and pc[1] < self.box.zf - 10
            ):
                return True
            else:
                return False

        if axis == "CORONAL":
            if (
                pc[0] > self.box.xi + 10
                and pc[0] < self.box.xf - 10
                and pc[1] - 10 > self.box.zi
                and pc[1] < self.box.zf - 10
            ):
                return True
            else:
                return False

    def point_between_line(self, p1, p2, pc, axis):
        """
        Checks whether a point is in the line limits
        """

        if axis == "AXIAL":
            if p1[0] < pc[0] and p2[0] > pc[0]:  # x axis
                return True
            elif p1[1] < pc[1] and p2[1] > pc[1]:  # y axis
                return True
            else:
                return False
        elif axis == "SAGITAL":
            if p1[1] < pc[0] and p2[1] > pc[0]:  # y axis
                return True
            elif p1[2] < pc[1] and p2[2] > pc[1]:  # z axis
                return True
            else:
                return False
        elif axis == "CORONAL":
            if p1[0] < pc[0] and p2[0] > pc[0]:  # x axis
                return True
            elif p1[2] < pc[1] and p2[2] > pc[1]:  # z axis
                return True
            else:
                return False

    def distance_from_point_line(self, p1, p2, pc):
        """
        Calculate the distance from point pc to a line formed by p1 and p2.
        """

        # TODO: Same function into clut_raycasting
        # Create a function to organize it.

        # Create a vector pc-p1 and p2-p1
        A = np.array(pc) - np.array(p1)
        B = np.array(p2) - np.array(p1)
        # Calculate the size from those vectors
        len_A = np.linalg.norm(A)
        len_B = np.linalg.norm(B)
        # calculate the angle theta (in radians) between those vector
        theta = math.acos(np.dot(A, B) / (len_A * len_B))
        # Using the sin from theta, calculate the adjacent leg, which is the
        # distance from the point to the line
        distance = math.sin(theta) * len_A
        return distance

    def Coord3DtoDisplay(self, x, y, z, canvas):
        coord = vtkCoordinate()
        coord.SetValue(x, y, z)
        cx, cy = coord.GetComputedDisplayValue(canvas.evt_renderer)

        return (cx, cy)

    def MakeBox(self):
        slice_size = self.viewer.slice_.matrix.shape
        zf, yf, xf = slice_size[0] - 1, slice_size[1] - 1, slice_size[2] - 1

        slice_spacing = self.viewer.slice_.spacing
        xs, ys, zs = slice_spacing

        self.box = box = Box()

        if self.box.first_run:
            box.SetX(0, xf)
            box.SetY(0, yf)
            box.SetZ(0, zf)
            box.SetSpacing(xs, ys, zs)
            box.MakeMatrix()

    def UpdateValues(self, canvas):
        box = self.box
        slice_number = self.viewer.slice_data.number

        slice_spacing = self.viewer.slice_.spacing
        xs, ys, zs = slice_spacing

        if canvas.orientation == "AXIAL":
            for points in box.axial.values():
                pi_x, pi_y, pi_z = points[0]
                pf_x, pf_y, pf_z = points[1]

                s_cxi, s_cyi = self.Coord3DtoDisplay(pi_x, pi_y, pi_z, canvas)
                s_cxf, s_cyf = self.Coord3DtoDisplay(pf_x, pf_y, pf_z, canvas)

                sn = slice_number * zs
                if sn >= box.zi and sn <= box.zf:
                    canvas.draw_line((s_cxi, s_cyi), (s_cxf, s_cyf), colour=(255, 255, 255, 255))

        elif canvas.orientation == "CORONAL":
            for points in box.coronal.values():
                pi_x, pi_y, pi_z = points[0]
                pf_x, pf_y, pf_z = points[1]

                s_cxi, s_cyi = self.Coord3DtoDisplay(pi_x, pi_y, pi_z, canvas)
                s_cxf, s_cyf = self.Coord3DtoDisplay(pf_x, pf_y, pf_z, canvas)

                sn = slice_number * ys

                if sn >= box.yi and sn <= box.yf:
                    canvas.draw_line((s_cxi, s_cyi), (s_cxf, s_cyf), colour=(255, 255, 255, 255))

        elif canvas.orientation == "SAGITAL":
            for points in box.sagital.values():
                pi_x, pi_y, pi_z = points[0]
                pf_x, pf_y, pf_z = points[1]

                s_cxi, s_cyi = self.Coord3DtoDisplay(pi_x, pi_y, pi_z, canvas)
                s_cxf, s_cyf = self.Coord3DtoDisplay(pf_x, pf_y, pf_z, canvas)

                sn = slice_number * xs
                if sn >= box.xi and sn <= box.xf:
                    canvas.draw_line((s_cxi, s_cyi), (s_cxf, s_cyf), colour=(255, 255, 255, 255))

    def SetViewer(self, viewer):
        self.viewer = viewer
        self.MakeBox()
