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

import threading
from math import cos, sin
from random import uniform
from time import sleep
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple, Union

import numpy as np
import wx

import invesalius.constants as const
import invesalius.data.transformations as tr
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher

if TYPE_CHECKING:
    from invesalius.data.tracker_connection import TrackerConnection


class TrackerCoordinates:
    def __init__(self):
        self.coord: Optional[np.ndarray] = None
        self.marker_visibilities = [False, False, False]
        self.previous_marker_visibilities = self.marker_visibilities
        self.nav_status = False
        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self.OnUpdateNavigationStatus, "Navigation status")

    def OnUpdateNavigationStatus(self, nav_status: bool, vis_status) -> None:
        self.nav_status = nav_status

    def SetCoordinates(self, coord, marker_visibilities: List[bool]) -> None:
        self.coord = coord
        self.marker_visibilities = marker_visibilities
        if not self.nav_status:
            wx.CallAfter(
                Publisher.sendMessage,
                "From Neuronavigation: Update tracker poses",
                poses=self.coord.tolist(),
                visibilities=self.marker_visibilities,
            )
            if self.previous_marker_visibilities != self.marker_visibilities:
                wx.CallAfter(
                    Publisher.sendMessage,
                    "Sensors ID",
                    marker_visibilities=self.marker_visibilities,
                )
                wx.CallAfter(Publisher.sendMessage, "Render volume viewer")
                self.previous_marker_visibilities = self.marker_visibilities

    def GetCoordinates(self) -> Tuple[Optional[np.ndarray], List[bool]]:
        if self.nav_status:
            wx.CallAfter(
                Publisher.sendMessage,
                "From Neuronavigation: Update tracker poses",
                poses=self.coord.tolist(),
                visibilities=self.marker_visibilities,
            )
            if self.previous_marker_visibilities != self.marker_visibilities:
                wx.CallAfter(
                    Publisher.sendMessage,
                    "Sensors ID",
                    marker_visibilities=self.marker_visibilities,
                )
                self.previous_marker_visibilities = self.marker_visibilities

        return self.coord, self.marker_visibilities


def GetCoordinatesForThread(
    tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int
):
    """
    Read coordinates from spatial tracking devices using

    :param tracker_connection: Connection object of tracking device and connection type. See tracker_connection.py.
    :param tracker_id: ID of tracking device.
    :param ref_mode: Single or dynamic reference mode of tracking.
    :return: array of six coordinates (x, y, z, alpha, beta, gamma)
    """

    coord = None
    if tracker_id:
        getcoord = {
            const.MTC: ClaronCoord,
            const.FASTRAK: PolhemusCoord,
            const.ISOTRAKII: PolhemusCoord,
            const.PATRIOT: PolhemusCoord,
            const.CAMERA: CameraCoord,
            const.POLARIS: PolarisCoord,
            const.POLARISP4: PolarisP4Coord,
            const.OPTITRACK: OptitrackCoord,
            const.DEBUGTRACKRANDOM: DebugCoordRandom,
            const.DEBUGTRACKAPPROACH: DebugCoordRandom,
        }
        coord, marker_visibilities = getcoord[tracker_id](tracker_connection, tracker_id, ref_mode)
    else:
        print("Select Tracker")

    return coord, marker_visibilities


def PolarisP4Coord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    trck = tracker_connection.GetConnection()
    trck.Run()

    probe = trck.probe.decode(const.FS_ENCODE)
    ref = trck.ref.decode(const.FS_ENCODE)
    obj = trck.obj.decode(const.FS_ENCODE)

    probe = probe[2:]
    ref = ref[2:]
    obj = obj[2:]

    if probe[:7] == "MISSING":
        coord1 = np.hstack(([0, 0, 0], [0, 0, 0]))
    else:
        q = [int(probe[i : i + 6]) * 0.0001 for i in range(0, 24, 6)]
        t = [int(probe[i : i + 7]) * 0.01 for i in range(24, 45, 7)]
        angles_probe = np.degrees(tr.euler_from_quaternion(q, axes="rzyx"))
        trans_probe = np.array(t).astype(float)
        coord1 = np.hstack((trans_probe, angles_probe))

    if ref[:7] == "MISSING":
        coord2 = np.hstack(([0, 0, 0], [0, 0, 0]))
    else:
        q = [int(ref[i : i + 6]) * 0.0001 for i in range(0, 24, 6)]
        t = [int(ref[i : i + 7]) * 0.01 for i in range(24, 45, 7)]
        angles_ref = np.degrees(tr.euler_from_quaternion(q, axes="rzyx"))
        trans_ref = np.array(t).astype(float)
        coord2 = np.hstack((trans_ref, angles_ref))

    if obj[:7] == "MISSING":
        coord3 = np.hstack(([0, 0, 0], [0, 0, 0]))
    else:
        q = [int(obj[i : i + 6]) * 0.0001 for i in range(0, 24, 6)]
        t = [int(obj[i : i + 7]) * 0.01 for i in range(24, 45, 7)]
        angles_obj = np.degrees(tr.euler_from_quaternion(q, axes="rzyx"))
        trans_obj = np.array(t).astype(float)
        coord3 = np.hstack((trans_obj, angles_obj))

    coord = np.vstack([coord1, coord2, coord3])

    return coord, [trck.probeID, trck.refID, trck.objID]


def OptitrackCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    """

    Obtains coordinates and angles of tracking rigid bodies (Measurement Probe, Coil, Head). Converts orientations from quaternion
    rotations to Euler angles. This function uses Optitrack wrapper from Motive API 2.2.

    Parameters
    ----------
    :tracker_connection: tracker connection instance from OptitrackTrackerConnection class at tracker_connection.py
    :tracker_id: not used
    :ref_mode: not used

    Returns
    -------
    coord: position of tracking rigid bodies
    """
    trck = tracker_connection.GetConnection()
    trck.Run()

    scale = 1000 * np.array([1.0, 1.0, 1.0])  # coordinates are in millimeters in Motive API

    angles_probe = np.degrees(
        tr.euler_from_quaternion(
            [
                float(trck.qwToolTip),
                float(trck.qzToolTip),
                float(trck.qxToolTip),
                float(trck.qyToolTip),
            ],
            axes="rzyx",
        )
    )
    coord1 = np.array(
        [
            float(trck.PositionToolTipZ1) * scale[0],
            float(trck.PositionToolTipX1) * scale[1],
            float(trck.PositionToolTipY1) * scale[2],
        ]
    )
    coord1 = np.hstack((coord1, angles_probe))

    angles_head = np.degrees(
        tr.euler_from_quaternion(
            [float(trck.qwHead), float(trck.qzHead), float(trck.qxHead), float(trck.qyHead)],
            axes="rzyx",
        )
    )
    coord2 = np.array(
        [
            float(trck.PositionHeadZ1) * scale[0],
            float(trck.PositionHeadX1) * scale[1],
            float(trck.PositionHeadY1) * scale[2],
        ]
    )
    coord2 = np.hstack((coord2, angles_head))

    angles_coil = np.degrees(
        tr.euler_from_quaternion(
            [float(trck.qwCoil), float(trck.qzCoil), float(trck.qxCoil), float(trck.qyCoil)],
            axes="rzyx",
        )
    )
    coord3 = np.array(
        [
            float(trck.PositionCoilZ1) * scale[0],
            float(trck.PositionCoilX1) * scale[1],
            float(trck.PositionCoilY1) * scale[2],
        ]
    )
    coord3 = np.hstack((coord3, angles_coil))

    coord = np.vstack([coord1, coord2, coord3])

    return coord, [trck.probeID, trck.HeadID, trck.coilID]


def PolarisCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    trck = tracker_connection.GetConnection()
    trck.Run()

    probe = trck.probe.decode(const.FS_ENCODE).split(",")
    angles_probe = np.degrees(tr.euler_from_quaternion(probe[2:6], axes="rzyx"))
    trans_probe = np.array(probe[6:9]).astype(float)
    coord1 = np.hstack((trans_probe, angles_probe))

    ref = trck.ref.decode(const.FS_ENCODE).split(",")
    angles_ref = np.degrees(tr.euler_from_quaternion(ref[2:6], axes="rzyx"))
    trans_ref = np.array(ref[6:9]).astype(float)
    coord2 = np.hstack((trans_ref, angles_ref))

    obj_coords = []
    for i in range(trck.objs.size()):
        obj = trck.objs[i].decode(const.FS_ENCODE).split(",")
        angles_obj = np.degrees(tr.euler_from_quaternion(obj[2:6], axes="rzyx"))
        trans_obj = np.array(obj[6:9]).astype(float)
        obj_coords.append(np.hstack((trans_obj, angles_obj)))

    coord = np.vstack([coord1, coord2, *obj_coords])
    marker_visibilities = [trck.probeID, trck.refID] + list(trck.objIDs)

    return coord, marker_visibilities


def CameraCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode):
    trck = tracker_connection.GetConnection()
    coord, probeID, refID, coilID = trck.Run()

    return coord, [probeID, refID, coilID]


def ClaronCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    trck = tracker_connection.GetConnection()
    trck.Run()

    scale = np.array([1.0, 1.0, 1.0])

    coord1 = np.array(
        [
            float(trck.PositionTooltipX1) * scale[0],
            float(trck.PositionTooltipY1) * scale[1],
            float(trck.PositionTooltipZ1) * scale[2],
            float(trck.AngleZ1),
            float(trck.AngleY1),
            float(trck.AngleX1),
        ]
    )

    coord2 = np.array(
        [
            float(trck.PositionTooltipX2) * scale[0],
            float(trck.PositionTooltipY2) * scale[1],
            float(trck.PositionTooltipZ2) * scale[2],
            float(trck.AngleZ2),
            float(trck.AngleY2),
            float(trck.AngleX2),
        ]
    )

    coord3 = np.array(
        [
            float(trck.PositionTooltipX3) * scale[0],
            float(trck.PositionTooltipY3) * scale[1],
            float(trck.PositionTooltipZ3) * scale[2],
            float(trck.AngleZ3),
            float(trck.AngleY3),
            float(trck.AngleX3),
        ]
    )

    coord = np.vstack([coord1, coord2, coord3])

    return coord, [trck.probeID, trck.refID, trck.coilID]


def PolhemusCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    lib_mode = tracker_connection.GetLibMode()

    coord = None

    if lib_mode == "serial":
        coord = PolhemusSerialCoord(tracker_connection, tracker_id, ref_mode)

    elif lib_mode == "usb":
        coord = PolhemusUSBCoord(tracker_connection, tracker_id, ref_mode)

    elif lib_mode == "wrapper":
        coord = PolhemusWrapperCoord(tracker_connection, tracker_id, ref_mode)

    return coord, [True, True, True]


def PolhemusWrapperCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    trck = tracker_connection.GetConnection()
    trck.Run()

    scale = 10.0 * np.array([1.0, 1.0, 1.0])

    coord1 = np.array(
        [
            float(trck.PositionTooltipX1) * scale[0],
            float(trck.PositionTooltipY1) * scale[1],
            float(trck.PositionTooltipZ1) * scale[2],
            float(trck.AngleX1),
            float(trck.AngleY1),
            float(trck.AngleZ1),
        ]
    )

    coord2 = np.array(
        [
            float(trck.PositionTooltipX2) * scale[0],
            float(trck.PositionTooltipY2) * scale[1],
            float(trck.PositionTooltipZ2) * scale[2],
            float(trck.AngleX2),
            float(trck.AngleY2),
            float(trck.AngleZ2),
        ]
    )
    coord = np.vstack([coord1, coord2])

    if tracker_id == 2:
        coord3 = np.array(
            [
                float(trck.PositionTooltipX3) * scale[0],
                float(trck.PositionTooltipY3) * scale[1],
                float(trck.PositionTooltipZ3) * scale[2],
                float(trck.AngleX3),
                float(trck.AngleY3),
                float(trck.AngleZ3),
            ]
        )
        coord4 = np.array(
            [
                float(trck.PositionTooltipX4) * scale[0],
                float(trck.PositionTooltipY4) * scale[1],
                float(trck.PositionTooltipZ4) * scale[2],
                float(trck.AngleX4),
                float(trck.AngleY4),
                float(trck.AngleZ4),
            ]
        )
        coord = np.vstack([coord, coord3, coord4])

    if trck.StylusButton:
        Publisher.sendMessage("PLH Stylus Button On")

    return coord


def PolhemusUSBCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    trck = tracker_connection.GetConnection()

    endpoint = trck[0][(0, 0)][0]
    # Tried to write some settings to Polhemus in trackers.py while initializing the device.
    # TODO: Check if it's working properly.
    trck.write(0x02, "P")
    if tracker_id == 2:
        scale = 10.0 * np.array([1.0, 1.0, -1.0])
    else:
        scale = 25.4 * np.array([1.0, 1.0, -1.0])
    coord = None

    if ref_mode:
        data = trck.read(endpoint.bEndpointAddress, 2 * endpoint.wMaxPacketSize)
        data = str2float(data.tostring())

        # six coordinates of first and second sensor: x, y, z and alfa, beta and gama
        # jump one element for reference to avoid the sensor ID returned by Polhemus
        probe = data[0], data[1], data[2], data[3], data[4], data[5], data[6]
        reference = data[7], data[8], data[9], data[10], data[11], data[12], data[13]

        if probe.all() and reference.all():
            coord = dynamic_reference(probe, reference)
            coord = (
                coord[0] * scale[0],
                coord[1] * scale[1],
                coord[2] * scale[2],
                coord[3],
                coord[4],
                coord[5],
            )

        return coord

    else:
        data = trck.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize)
        coord = str2float(data.tostring())

        coord = np.array(
            (
                coord[0] * scale[0],
                coord[1] * scale[1],
                coord[2] * scale[2],
                coord[3],
                coord[4],
                coord[5],
            )
        )

        return coord


def PolhemusSerialCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    trck = tracker_connection.GetConnection()

    # mudanca para fastrak - ref 1 tem somente x, y, z
    # aoflt -> 0:letter 1:x 2:y 3:z
    # this method is not optimized to work with all trackers, only with ISOTRAK
    # serial connection is obsolete, remove in future
    trck.write(str.encode("P"))
    scale = 10.0 * np.array([1.0, 1.0, 1.0])
    lines = trck.readlines()

    if lines is None:
        print("The Polhemus is not connected!")
    else:
        data = lines[0]
        data = data.replace(str.encode("-"), str.encode(" -"))
        data = [s for s in data.split()]
        data = [float(s) for s in data[1 : len(data)]]
        probe = np.array(
            [data[0] * scale[0], data[1] * scale[1], data[2] * scale[2], data[3], data[4], data[5]]
        )

        if ref_mode:
            data2 = lines[1]
            data2 = data2.replace(str.encode("-"), str.encode(" -"))
            data2 = [s for s in data2.split()]
            data2 = [float(s) for s in data2[1 : len(data2)]]
            reference = np.array(
                [
                    data2[0] * scale[0],
                    data2[1] * scale[1],
                    data2[2] * scale[2],
                    data2[3],
                    data2[4],
                    data2[5],
                ]
            )
        else:
            reference = np.zeros(6)

        coord = np.vstack([probe, reference])

    return coord


def RobotCoord(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    tracker_id = tracker_connection.GetTrackerId()

    coord_tracker, marker_visibilities = GetCoordinatesForThread(
        tracker_connection, tracker_id, ref_mode
    )

    return np.vstack([coord_tracker[0], coord_tracker[1], coord_tracker[2]]), marker_visibilities


def DebugCoordRandom(tracker_connection: "TrackerConnection", tracker_id: int, ref_mode: int):
    """
    Method to simulate a tracking device for debug and error check. Generate a random
    x, y, z, alfa, beta and gama coordinates in interval [1, 200[
    :param tracker_connection: tracker connection instance
    :param ref_mode: flag for singular of dynamic reference
    :param tracker_id: id of tracking device
    :return: six coordinates x, y, z, alfa, beta and gama
    """

    # Started to take a more reasonable, limited random coordinate generator based on
    # the collected fiducials, but it is more complicated than this. It should account for the
    # dynamic reference computation
    # trck = tracker_connection.GetConnection()
    # if trck:
    #     fiducials = trck[3:, :]
    #     fids_max = fiducials.max(axis=0)
    #     fids_min = fiducials.min(axis=0)
    #     fids_lim = np.hstack((fids_min[np.newaxis, :].T, fids_max[np.newaxis, :].T))
    #
    #     dx = fids_max[]
    #     dt = [-180, 180]
    #
    # else:

    dx = [-30, 30]
    dt = [-180, 180]

    coord1 = np.array(
        [uniform(*dx), uniform(*dx), uniform(*dx), uniform(*dt), uniform(*dt), uniform(*dt)]
    )
    coord2 = np.array(
        [uniform(*dx), uniform(*dx), uniform(*dx), uniform(*dt), uniform(*dt), uniform(*dt)]
    )
    coord3 = np.array(
        [uniform(*dx), uniform(*dx), uniform(*dx), uniform(*dt), uniform(*dt), uniform(*dt)]
    )
    coord4 = np.array(
        [uniform(*dx), uniform(*dx), uniform(*dx), uniform(*dt), uniform(*dt), uniform(*dt)]
    )
    coord5 = np.array(
        [uniform(*dx), uniform(*dx), uniform(*dx), uniform(*dt), uniform(*dt), uniform(*dt)]
    )

    sleep(0.15)

    # coord1 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
    #                    uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])
    #
    # coord2 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
    #                    uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])
    #
    # coord3 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
    #                    uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])
    #
    # coord4 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
    #                    uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])

    # Always make the markers visible when using debug tracker; this enables registration, as it
    # is not possible to registering without markers.
    marker_visibilities = [True, True, True, True, True]

    return np.vstack([coord1, coord2, coord3, coord4, coord5]), marker_visibilities


def coordinates_to_transformation_matrix(
    position: Union[Sequence[float], np.ndarray],
    orientation: Union[Sequence[float], np.ndarray],
    axes: str = "sxyz",
) -> np.ndarray:
    """
    Transform vectors consisting of position and orientation (in Euler angles) in 3d-space into a 4x4
    transformation matrix that combines the rotation and translation.
    :param position: A vector of three coordinates.
    :param orientation: A vector of three Euler angles in degrees.
    :param axes: The order in which the rotations are done for the axes. See transformations.py for details. Defaults to 'sxyz'.
    :return: The transformation matrix (4x4).
    """
    a, b, g = np.radians(orientation)

    r_ref = tr.euler_matrix(a, b, g, axes=axes)
    t_ref = tr.translation_matrix(position)

    m_img = tr.concatenate_matrices(t_ref, r_ref)

    return m_img


def transformation_matrix_to_coordinates(matrix, axes="sxyz"):
    """
    Given a matrix that combines the rotation and translation, return the position and the orientation
    determined by the matrix. The orientation is given as three Euler angles.
    The inverse of coordinates_of_transformation_matrix when the parameter 'axes' matches.
    :param matrix: A 4x4 transformation matrix.
    :param axes: The order in which the rotations are done for the axes. See transformations.py for details. Defaults to 'sxyz'.
    :return: The position (a vector of length 3) and Euler angles for the orientation in degrees (a vector of length 3).
    """
    angles = tr.euler_from_matrix(matrix, axes=axes)
    angles_as_deg = np.degrees(angles)

    translation = tr.translation_from_matrix(matrix)

    return translation, angles_as_deg


def dynamic_reference(probe, reference):
    """
    Apply dynamic reference correction to probe coordinates. Uses the alpha, beta and gama
    rotation angles of reference to rotate the probe coordinate and returns the x, y, z
    difference between probe and reference. Angles sequences and equation was extracted from
    Polhemus manual and Attitude matrix in Wikipedia.
    General equation is:
    coord = Mrot * (probe - reference)
    :param probe: sensor one defined as probe
    :param reference: sensor two defined as reference
    :return: rotated and translated coordinates
    """
    a, b, g = np.radians(reference[3:6])

    vet = np.asmatrix(probe[0:3] - reference[0:3])
    # vet = np.mat(vet.reshape(3, 1))

    # Attitude matrix given by Patriot manual
    # a: rotation of plane (X, Y) around Z axis (azimuth)
    # b: rotation of plane (X', Z) around Y' axis (elevation)
    # a: rotation of plane (Y', Z') around X'' axis (roll)
    m_rot = np.asmatrix(
        [
            [
                cos(a) * cos(b),
                sin(b) * sin(g) * cos(a) - cos(g) * sin(a),
                cos(a) * sin(b) * cos(g) + sin(a) * sin(g),
            ],
            [
                cos(b) * sin(a),
                sin(b) * sin(g) * sin(a) + cos(g) * cos(a),
                cos(g) * sin(b) * sin(a) - sin(g) * cos(a),
            ],
            [-sin(b), sin(g) * cos(b), cos(b) * cos(g)],
        ]
    )

    # coord_rot = m_rot.T * vet
    coord_rot = vet * m_rot
    coord_rot = np.squeeze(np.asarray(coord_rot))

    return coord_rot[0], coord_rot[1], -coord_rot[2], probe[3], probe[4], probe[5]


def dynamic_reference_m(probe, reference):
    """
    Apply dynamic reference correction to probe coordinates. Uses the alpha, beta and gama
    rotation angles of reference to rotate the probe coordinate and returns the x, y, z
    difference between probe and reference. Angles sequences and equation was extracted from
    Polhemus manual and Attitude matrix in Wikipedia.
    General equation is:
    coord = Mrot * (probe - reference)
    :param probe: sensor one defined as probe
    :param reference: sensor two defined as reference
    :return: rotated and translated coordinates
    """
    affine = coordinates_to_transformation_matrix(
        position=reference[:3],
        orientation=reference[3:],
        axes="rzyx",
    )
    probe_4 = np.vstack((probe[:3].reshape([3, 1]), 1.0))
    coord_rot = np.linalg.inv(affine) @ probe_4
    # minus sign to the z coordinate
    coord_rot[2, 0] = -coord_rot[2, 0]
    coord_rot = coord_rot[:3, 0].tolist()
    coord_rot.extend(probe[3:])

    return coord_rot


def dynamic_reference_m2(probe, reference):
    """
    Apply dynamic reference correction to probe coordinates. Uses the alpha, beta and gama
    rotation angles of reference to rotate the probe coordinate and returns the x, y, z
    difference between probe and reference. Angles sequences and equation was extracted from
    Polhemus manual and Attitude matrix in Wikipedia.
    General equation is:
    coord = Mrot * (probe - reference)
    :param probe: sensor one defined as probe
    :param reference: sensor two defined as reference
    :return: rotated and translated coordinates
    """

    M = coordinates_to_transformation_matrix(
        position=reference[:3],
        orientation=reference[3:],
        axes="rzyx",
    )
    M_p = coordinates_to_transformation_matrix(
        position=probe[:3],
        orientation=probe[3:],
        axes="rzyx",
    )

    M_dyn = np.linalg.inv(M) @ M_p

    al, be, ga = tr.euler_from_matrix(M_dyn, "rzyx")
    coord_rot = tr.translation_from_matrix(M_dyn)

    coord_rot = np.squeeze(coord_rot)

    return coord_rot[0], coord_rot[1], coord_rot[2], np.degrees(al), np.degrees(be), np.degrees(ga)


def str2float(data: str) -> List[float]:
    """
    Converts string detected wth Polhemus device to float array of coordinates. This method applies
    a correction for the minus sign in string that raises error while splitting the string into coordinates.
    :param data: string of coordinates read with Polhemus
    :return: six float coordinates x, y, z, alpha, beta and gamma
    """

    count = 0
    for i, j in enumerate(data):
        if j == "-":
            data = data[: i + count] + " " + data[i + count :]
            count += 1

    new_data = [s for s in data.split()]
    ret = [float(s) for s in new_data[1 : len(new_data)]]

    return ret


def offset_coordinate(p_old: np.ndarray, norm_vec: np.ndarray, offset: float) -> np.ndarray:
    """
    Translate the coordinates of a point along a vector
    :param p_old: (x, y, z) array with current point coordinates
    :param norm_vec: (vx, vy, vz) array with normal vector coordinates
    :param offset: double representing the magnitude of offset
    :return: (x_new, y_new, z_new) array of offset coordinates
    """
    p_offset = p_old - offset * norm_vec
    return p_offset


class ReceiveCoordinates(threading.Thread):
    def __init__(
        self,
        tracker_connection: "TrackerConnection",
        tracker_id: int,
        TrackerCoordinates: TrackerCoordinates,
        event: threading.Event,
    ):
        threading.Thread.__init__(self, name="ReceiveCoordinates")
        self.__bind_events()

        session = ses.Session()
        sleep_coord = session.GetConfig("sleep_coord", const.SLEEP_COORDINATES)

        self.sleep_coord = sleep_coord
        self.tracker_connection = tracker_connection
        self.tracker_id = tracker_id
        self.event = event
        self.TrackerCoordinates = TrackerCoordinates

    def __bind_events(self) -> None:
        Publisher.subscribe(self.UpdateCoordSleep, "Update coord sleep")

    def UpdateCoordSleep(self, data) -> None:
        self.sleep_coord = data

    def run(self) -> None:
        while not self.event.is_set():
            coord_raw, marker_visibilities = GetCoordinatesForThread(
                self.tracker_connection, self.tracker_id, const.DEFAULT_REF_MODE
            )
            self.TrackerCoordinates.SetCoordinates(coord_raw, marker_visibilities)
            sleep(self.sleep_coord)
