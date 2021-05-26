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

from math import sin, cos
import numpy as np

import invesalius.data.bases as db
import invesalius.data.transformations as tr
import invesalius.constants as const

from time import sleep
from random import uniform
from pubsub import pub as Publisher


def GetCoordinates(trck_init, trck_id, ref_mode):

    """
    Read coordinates from spatial tracking devices using

    :param trck_init: Initialization variable of tracking device and connection type. See tracker.py.
    :param trck_id: ID of tracking device.
    :param ref_mode: Single or dynamic reference mode of tracking.
    :return: array of six coordinates (x, y, z, alpha, beta, gamma)
    """

    coord = None
    if trck_id:
        getcoord = {const.MTC: ClaronCoord,
                    const.FASTRAK: PolhemusCoord,
                    const.ISOTRAKII: PolhemusCoord,
                    const.PATRIOT: PolhemusCoord,
                    const.CAMERA: CameraCoord,
                    const.POLARIS: PolarisCoord,
                    const.OPTITRACK: OptitrackCoord,
                    const.DEBUGTRACK: DebugCoord}
        coord = getcoord[trck_id](trck_init, trck_id, ref_mode)
    else:
        print("Select Tracker")

    return coord

def OptitrackCoord(trck_init, trck_id, ref_mode):
    trck=trck_init[0]

    trck.Run()


    scale =  100*np.array([1.0, 1.0, 1.0])

    #angles_probe = np.array(tr.euler_matrix(float(trck.RollToolTip), float(trck.PitchToolTip), float(trck.YawToolTip), axes='rzyx'))
    # coord1 = np.array([float(trck.PositionToolTipX1) * scale[0], float(trck.PositionToolTipY1) * scale[1],
    #                    float(trck.PositionToolTipZ1) * scale[2], float(trck.RollToolTip), float(trck.PitchToolTip), float(trck.YawToolTip) ])
    # coord2 = np.array([float(trck.PositionHeadX1) * scale[0], float(trck.PositionHeadY1) * scale[1],
    #                    float(trck.PositionHeadZ1) * scale[2],
    #                    float(trck.YawHead), float(trck.PitchHead), float(trck.RollHead)])
    # coord3 = np.array([float(trck.PositionCoilX1) * scale[0], float(trck.PositionCoilY1) * scale[1],
    #                    float(trck.PositionCoilZ1) * scale[2],
    #                    float(trck.YawCoil), float(trck.PitchCoil), float(trck.RollCoil)])

    angles_probe = np.array(tr.euler_from_quaternion([float(trck.qxToolTip), float(trck.qyToolTip), float(trck.qzToolTip), float(trck.qwToolTip)], axes='rzyx'))
    coord1 = np.array([float(trck.PositionToolTipX1) * scale[0], float(trck.PositionToolTipY1) * scale[1],
                       float(trck.PositionToolTipZ1) * scale[2]])
    coord1 = np.hstack((coord1, angles_probe))

    angles_head = np.array(tr.euler_from_quaternion([float(trck.qxHead), float(trck.qyHead), float(trck.qzHead), float(trck.qwHead)], axes='rzyx'))
    coord2 = np.array([float(trck.PositionHeadX1) * scale[0], float(trck.PositionHeadY1) * scale[1],
                       float(trck.PositionHeadZ1) * scale[2]])
    coord2 = np.hstack((coord2, angles_head))

    angles_coil = np.array(tr.euler_from_quaternion([float(trck.qxCoil), float(trck.qyCoil), float(trck.qzCoil), float(trck.qwCoil)], axes='rzyx'))
    coord3 = np.array([float(trck.PositionCoilX1) * scale[0], float(trck.PositionCoilY1) * scale[1],
                       float(trck.PositionCoilZ1) * scale[2]])
    coord3 = np.hstack((coord3, angles_coil))

    coord = np.vstack([coord1, coord2, coord3])
    print(coord)
    return coord


def PolarisCoord(trck_init, trck_id, ref_mode):
    trck = trck_init[0]
    trck.Run()

    probe = trck.probe.decode(const.FS_ENCODE).split(',')
    angles_probe = np.degrees(tr.euler_from_quaternion(probe[2:6], axes='rzyx'))
    trans_probe = np.array(probe[6:9]).astype(float)
    coord1 = np.hstack((trans_probe, angles_probe))

    ref = trck.ref.decode(const.FS_ENCODE).split(',')
    angles_ref = np.degrees(tr.euler_from_quaternion(ref[2:6], axes='rzyx'))
    trans_ref = np.array(ref[6:9]).astype(float)
    coord2 = np.hstack((trans_ref, angles_ref))

    obj = trck.obj.decode(const.FS_ENCODE).split(',')
    angles_obj = np.degrees(tr.euler_from_quaternion(obj[2:6], axes='rzyx'))
    trans_obj = np.array(obj[6:9]).astype(float)
    coord3 = np.hstack((trans_obj, angles_obj))

    coord = np.vstack([coord1, coord2, coord3])
    # Publisher.sendMessage('Sensors ID', probe_id=trck.probeID, ref_id=trck.refID, obj_id=trck.objID)

    return coord

def CameraCoord(trck_init, trck_id, ref_mode):
    trck = trck_init[0]
    coord, probeID, refID = trck.Run()
    Publisher.sendMessage('Sensors ID', probe_id=probeID, ref_id=refID)
    return coord

def ClaronCoord(trck_init, trck_id, ref_mode):
    trck = trck_init[0]
    trck.Run()
    scale = np.array([1.0, 1.0, 1.0])

    coord1 = np.array([float(trck.PositionTooltipX1)*scale[0], float(trck.PositionTooltipY1)*scale[1],
                      float(trck.PositionTooltipZ1)*scale[2],
                      float(trck.AngleZ1), float(trck.AngleY1), float(trck.AngleX1)])

    coord2 = np.array([float(trck.PositionTooltipX2)*scale[0], float(trck.PositionTooltipY2)*scale[1],
                       float(trck.PositionTooltipZ2)*scale[2],
                       float(trck.AngleZ2), float(trck.AngleY2), float(trck.AngleX2)])

    coord3 = np.array([float(trck.PositionTooltipX3) * scale[0], float(trck.PositionTooltipY3) * scale[1],
                       float(trck.PositionTooltipZ3) * scale[2],
                       float(trck.AngleZ3), float(trck.AngleY3), float(trck.AngleX3)])

    coord = np.vstack([coord1, coord2, coord3])

    Publisher.sendMessage('Sensors ID', probe_id=trck.probeID, ref_id=trck.refID)

    return coord


def PolhemusCoord(trck, trck_id, ref_mode):
    coord = None

    if trck[1] == 'serial':
        coord = PolhemusSerialCoord(trck[0], trck_id, ref_mode)

    elif trck[1] == 'usb':
        coord = PolhemusUSBCoord(trck[0], trck_id, ref_mode)

    elif trck[1] == 'wrapper':
        coord = PolhemusWrapperCoord(trck[0], trck_id, ref_mode)

    return coord


def PolhemusWrapperCoord(trck, trck_id, ref_mode):

    trck.Run()
    scale = 10.0 * np.array([1., 1., 1.])

    coord1 = np.array([float(trck.PositionTooltipX1)*scale[0], float(trck.PositionTooltipY1)*scale[1],
                      float(trck.PositionTooltipZ1)*scale[2],
                      float(trck.AngleX1), float(trck.AngleY1), float(trck.AngleZ1)])

    coord2 = np.array([float(trck.PositionTooltipX2)*scale[0], float(trck.PositionTooltipY2)*scale[1],
                       float(trck.PositionTooltipZ2)*scale[2],
                       float(trck.AngleX2), float(trck.AngleY2), float(trck.AngleZ2)])
    coord = np.vstack([coord1, coord2])

    if trck_id == 2:
        coord3 = np.array([float(trck.PositionTooltipX3) * scale[0], float(trck.PositionTooltipY3) * scale[1],
                           float(trck.PositionTooltipZ3) * scale[2],
                           float(trck.AngleX3), float(trck.AngleY3), float(trck.AngleZ3)])
        coord4 = np.array([float(trck.PositionTooltipX4) * scale[0], float(trck.PositionTooltipY4) * scale[1],
                           float(trck.PositionTooltipZ4) * scale[2],
                           float(trck.AngleX4), float(trck.AngleY4), float(trck.AngleZ4)])
        coord = np.vstack([coord, coord3, coord4])

    if trck.StylusButton:
        Publisher.sendMessage('PLH Stylus Button On')

    return coord


def PolhemusUSBCoord(trck, trck_id, ref_mode):
    endpoint = trck[0][(0, 0)][0]
    # Tried to write some settings to Polhemus in trackers.py while initializing the device.
    # TODO: Check if it's working properly.
    trck.write(0x02, "P")
    if trck_id == 2:
        scale = 10. * np.array([1., 1.0, -1.0])
    else:
        scale = 25.4 * np.array([1., 1.0, -1.0])
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
            coord = (coord[0] * scale[0], coord[1] * scale[1], coord[2] * scale[2], coord[3], coord[4], coord[5])

        return coord

    else:
        data = trck.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize)
        coord = str2float(data.tostring())

        coord = np.array((coord[0] * scale[0], coord[1] * scale[1], coord[2] * scale[2],
                          coord[3], coord[4], coord[5]))

        return coord


def PolhemusSerialCoord(trck_init, trck_id, ref_mode):
    # mudanca para fastrak - ref 1 tem somente x, y, z
    # aoflt -> 0:letter 1:x 2:y 3:z
    # this method is not optimized to work with all trackers, only with ISOTRAK
    # serial connection is obsolete, remove in future
    trck_init.write(str.encode("P"))
    scale = 10. * np.array([1., 1.0, 1.0])
    lines = trck_init.readlines()

    if lines is None:
        print("The Polhemus is not connected!")
    else:
        data = lines[0]
        data = data.replace(str.encode('-'), str.encode(' -'))
        data = [s for s in data.split()]
        data = [float(s) for s in data[1:len(data)]]
        probe = np.array([data[0] * scale[0], data[1] * scale[1], data[2] * scale[2], data[3], data[4], data[5]])

        if ref_mode:
            data2 = lines[1]
            data2 = data2.replace(str.encode('-'), str.encode(' -'))
            data2 = [s for s in data2.split()]
            data2 = [float(s) for s in data2[1:len(data2)]]
            reference = np.array(
                [data2[0] * scale[0], data2[1] * scale[1], data2[2] * scale[2], data2[3], data2[4], data2[5]])
        else:
            reference = np.zeros(6)

        coord = np.vstack([probe, reference])

    return coord


def DebugCoord(trk_init, trck_id, ref_mode):
    """
    Method to simulate a tracking device for debug and error check. Generate a random
    x, y, z, alfa, beta and gama coordinates in interval [1, 200[
    :param trk_init: tracker initialization instance
    :param ref_mode: flag for singular of dynamic reference
    :param trck_id: id of tracking device
    :return: six coordinates x, y, z, alfa, beta and gama
    """

    # Started to take a more reasonable, limited random coordinate generator based on
    # the collected fiducials, but it is more complicated than this. It should account for the
    # dynamic reference computation
    # if trk_init:
    #     fiducials = trk_init[3:, :]
    #     fids_max = fiducials.max(axis=0)
    #     fids_min = fiducials.min(axis=0)
    #     fids_lim = np.hstack((fids_min[np.newaxis, :].T, fids_max[np.newaxis, :].T))
    #
    #     dx = fids_max[]
    #     dt = [-180, 180]
    #
    # else:

    dx = [-70, 70]
    dt = [-180, 180]

    coord1 = np.array([uniform(*dx), uniform(*dx), uniform(*dx),
                      uniform(*dt), uniform(*dt), uniform(*dt)])
    coord2 = np.array([uniform(*dx), uniform(*dx), uniform(*dx),
                      uniform(*dt), uniform(*dt), uniform(*dt)])
    coord3 = np.array([uniform(*dx), uniform(*dx), uniform(*dx),
                       uniform(*dt), uniform(*dt), uniform(*dt)])
    coord4 = np.array([uniform(*dx), uniform(*dx), uniform(*dx),
                       uniform(*dt), uniform(*dt), uniform(*dt)])

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

    Publisher.sendMessage('Sensors ID', probe_id=int(uniform(0, 5)), ref_id=int(uniform(0, 5)), obj_id=int(uniform(0, 5)))

    return np.vstack([coord1, coord2, coord3, coord4])


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
    m_rot = np.mat([[cos(a) * cos(b), sin(b) * sin(g) * cos(a) - cos(g) * sin(a),
                    cos(a) * sin(b) * cos(g) + sin(a) * sin(g)],
                   [cos(b) * sin(a), sin(b) * sin(g) * sin(a) + cos(g) * cos(a),
                    cos(g) * sin(b) * sin(a) - sin(g) * cos(a)],
                   [-sin(b), sin(g) * cos(b), cos(b) * cos(g)]])

    # coord_rot = m_rot.T * vet
    coord_rot = vet*m_rot
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
    a, b, g = np.radians(reference[3:6])

    trans = tr.translation_matrix(reference[:3])
    rot = tr.euler_matrix(a, b, g, 'rzyx')
    affine = tr.concatenate_matrices(trans, rot)
    probe_4 = np.vstack((probe[:3].reshape([3, 1]), 1.))
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

    a, b, g = np.radians(reference[3:6])
    a_p, b_p, g_p = np.radians(probe[3:6])

    T = tr.translation_matrix(reference[:3])
    T_p = tr.translation_matrix(probe[:3])
    R = tr.euler_matrix(a, b, g, 'rzyx')
    R_p = tr.euler_matrix(a_p, b_p, g_p, 'rzyx')
    M = tr.concatenate_matrices(T, R)
    M_p = tr.concatenate_matrices(T_p, R_p)

    M_dyn = np.linalg.inv(M) @ M_p

    al, be, ga = tr.euler_from_matrix(M_dyn, 'rzyx')
    coord_rot = tr.translation_from_matrix(M_dyn)

    coord_rot = np.squeeze(coord_rot)

    return coord_rot[0], coord_rot[1], coord_rot[2], np.degrees(al), np.degrees(be), np.degrees(ga)


def str2float(data):
    """
    Converts string detected wth Polhemus device to float array of coordinates. This method applies
    a correction for the minus sign in string that raises error while splitting the string into coordinates.
    :param data: string of coordinates read with Polhemus
    :return: six float coordinates x, y, z, alpha, beta and gamma
    """

    count = 0
    for i, j in enumerate(data):
        if j == '-':
            data = data[:i + count] + ' ' + data[i + count:]
            count += 1

    data = [s for s in data.split()]
    data = [float(s) for s in data[1:len(data)]]

    return data


def offset_coordinate(p_old, norm_vec, offset):
    """
    Translate the coordinates of a point along a vector
    :param p_old: (x, y, z) array with current point coordinates
    :param norm_vec: (vx, vy, vz) array with normal vector coordinates
    :param offset: double representing the magnitude of offset
    :return: (x_new, y_new, z_new) array of offset coordinates
    """
    p_offset = p_old - offset * norm_vec
    return p_offset
