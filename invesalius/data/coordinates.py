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

import invesalius.data.transformations as tr

from time import sleep
from random import uniform
from wx.lib.pubsub import pub as Publisher


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
        getcoord = {1: ClaronCoord,
                    2: PolhemusCoord,
                    3: PolhemusCoord,
                    4: PolhemusCoord,
                    5: DebugCoord}
        coord = getcoord[trck_id](trck_init, trck_id, ref_mode)
    else:
        print("Select Tracker")

    return coord


def ClaronCoord(trck_init, trck_id, ref_mode):
    trck = trck_init[0]
    scale = np.array([1.0, 1.0, -1.0])
    coord = None
    k = 0
    # TODO: try to replace 'while' and use some Claron internal computation

    if ref_mode:
        while k < 20:
            try:
                trck.Run()
                probe = np.array([trck.PositionTooltipX1, trck.PositionTooltipY1,
                                  trck.PositionTooltipZ1, trck.AngleX1, trck.AngleY1, trck.AngleZ1])
                reference = np.array([trck.PositionTooltipX2, trck.PositionTooltipY2,
                                      trck.PositionTooltipZ2, trck.AngleZ2,  trck.AngleY2, trck.AngleX2])
                k = 30
            except AttributeError:
                k += 1
                print("wait, collecting coordinates ...")
        if k == 30:
            coord = dynamic_reference(probe, reference)
            coord = (coord[0] * scale[0], coord[1] * scale[1], coord[2] * scale[2], coord[3], coord[4], coord[5])
    else:
        while k < 20:
            try:
                trck.Run()
                coord = np.array([trck.PositionTooltipX1 * scale[0], trck.PositionTooltipY1 * scale[1],
                                  trck.PositionTooltipZ1 * scale[2], trck.AngleX1, trck.AngleY1, trck.AngleZ1])

                k = 30
            except AttributeError:
                k += 1
                print("wait, collecting coordinates ...")

    Publisher.sendMessage('Sensors ID', [trck.probeID, trck.refID])

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
        coord = np.vstack([coord, coord3])

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
    trck_init.write("P")
    lines = trck_init.readlines()

    coord = None

    if lines[0][0] != '0':
        print("The Polhemus is not connected!")
    else:
        for s in lines:
            if s[1] == '1':
                data = s
            elif s[1] == '2':
                data = s

        # single ref mode
        if not ref_mode:
            data = data.replace('-', ' -')
            data = [s for s in data.split()]
            j = 0
            while j == 0:
                try:
                    plh1 = [float(s) for s in data[1:len(data)]]
                    j = 1
                except:
                    print("error!!")

            coord = data[0:6]
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

    sleep(0.05)

    coord1 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
                      uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])

    coord2 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
                       uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])

    coord3 = np.array([uniform(1, 200), uniform(1, 200), uniform(1, 200),
                       uniform(-180.0, 180.0), uniform(-180.0, 180.0), uniform(-180.0, 180.0)])

    Publisher.sendMessage('Sensors ID', [int(uniform(0, 5)), int(uniform(0, 5))])

    return np.vstack([coord1, coord2, coord3])


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

    T = tr.translation_matrix(reference[:3])
    R = tr.euler_matrix(a, b, g, 'rzyx')
    M = np.asmatrix(tr.concatenate_matrices(T, R))
    # M = tr.compose_matrix(angles=np.radians(reference[3:6]), translate=reference[:3])
    # print M
    probe_4 = np.vstack((np.asmatrix(probe[:3]).reshape([3, 1]), 1.))
    coord_rot = M.I * probe_4
    coord_rot = np.squeeze(np.asarray(coord_rot))

    return coord_rot[0], coord_rot[1], -coord_rot[2], probe[3], probe[4], probe[5]

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
    M = np.asmatrix(tr.concatenate_matrices(T, R))
    M_p = np.asmatrix(tr.concatenate_matrices(T_p, R_p))
    # M = tr.compose_matrix(angles=np.radians(reference[3:6]), translate=reference[:3])
    # print M

    M_dyn = M.I * M_p

    al, be, ga = tr.euler_from_matrix(M_dyn, 'rzyx')
    coord_rot = tr.translation_from_matrix(M_dyn)

    coord_rot = np.squeeze(coord_rot)

    # probe_4 = np.vstack((np.asmatrix(probe[:3]).reshape([3, 1]), 1.))
    # coord_rot_test = M.I * probe_4
    # coord_rot_test = np.squeeze(np.asarray(coord_rot_test))
    #
    # print "coord_rot: ", coord_rot
    # print "coord_rot_test: ", coord_rot_test
    # print "test: ", np.allclose(coord_rot, coord_rot_test[:3])

    return coord_rot[0], coord_rot[1], coord_rot[2], np.degrees(al), np.degrees(be), np.degrees(ga)

# def dynamic_reference_m3(probe, reference):
#     """
#     Apply dynamic reference correction to probe coordinates. Uses the alpha, beta and gama
#     rotation angles of reference to rotate the probe coordinate and returns the x, y, z
#     difference between probe and reference. Angles sequences and equation was extracted from
#     Polhemus manual and Attitude matrix in Wikipedia.
#     General equation is:
#     coord = Mrot * (probe - reference)
#     :param probe: sensor one defined as probe
#     :param reference: sensor two defined as reference
#     :return: rotated and translated coordinates
#     """
#
#     a, b, g = np.radians(reference[3:6])
#     a_p, b_p, g_p = np.radians(probe[3:6])
#
#     T = tr.translation_matrix(reference[:3])
#     T_p = tr.translation_matrix(probe[:3])
#     R = tr.euler_matrix(a, b, g, 'rzyx')
#     R_p = tr.euler_matrix(a_p, b_p, g_p, 'rzyx')
#     M = np.asmatrix(tr.concatenate_matrices(T, R))
#     M_p = np.asmatrix(tr.concatenate_matrices(T_p, R_p))
#     # M = tr.compose_matrix(angles=np.radians(reference[3:6]), translate=reference[:3])
#     # print M
#
#     M_dyn = M.I * M_p
#
#     # al, be, ga = tr.euler_from_matrix(M_dyn, 'rzyx')
#     # coord_rot = tr.translation_from_matrix(M_dyn)
#     #
#     # coord_rot = np.squeeze(coord_rot)
#
#     # probe_4 = np.vstack((np.asmatrix(probe[:3]).reshape([3, 1]), 1.))
#     # coord_rot_test = M.I * probe_4
#     # coord_rot_test = np.squeeze(np.asarray(coord_rot_test))
#     #
#     # print "coord_rot: ", coord_rot
#     # print "coord_rot_test: ", coord_rot_test
#     # print "test: ", np.allclose(coord_rot, coord_rot_test[:3])
#
#     return M_dyn


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
