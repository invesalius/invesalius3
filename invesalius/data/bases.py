from math import sqrt
import numpy as np


def angle_calculation(ap_axis, coil_axis):
    """
    Calculate angle between two given axis (in degrees)

    :param ap_axis: anterior posterior axis represented
    :param coil_axis: tms coil axis
    :return: angle between the two given axes
    """

    ap_axis = np.array([ap_axis[0], ap_axis[1]])
    coil_axis = np.array([float(coil_axis[0]), float(coil_axis[1])])
    angle = np.rad2deg(np.arccos((np.dot(ap_axis, coil_axis))/(
        np.linalg.norm(ap_axis)*np.linalg.norm(coil_axis))))

    return float(angle)


def base_creation(fiducials):
    """
    Calculate the origin and matrix for coordinate system
    transformation.
    q: origin of coordinate system
    g1, g2, g3: orthogonal vectors of coordinate system

    :param fiducials: array of 3 rows (p1, p2, p3) and 3 columns (x, y, z) with fiducials coordinates
    :return: matrix and origin for base transformation
    """

    p1 = fiducials[0, :]
    p2 = fiducials[1, :]
    p3 = fiducials[2, :]

    sub1 = p2 - p1
    sub2 = p3 - p1
    lamb = (sub1[0]*sub2[0]+sub1[1]*sub2[1]+sub1[2]*sub2[2])/np.dot(sub1, sub1)

    q = p1 + lamb*sub1
    g1 = p1 - q
    g2 = p3 - q

    if not g1.any():
        g1 = p2 - q

    g3 = np.cross(g2, g1)

    g1 = g1/sqrt(np.dot(g1, g1))
    g2 = g2/sqrt(np.dot(g2, g2))
    g3 = g3/sqrt(np.dot(g3, g3))

    m = np.matrix([[g1[0], g1[1], g1[2]],
                   [g2[0], g2[1], g2[2]],
                   [g3[0], g3[1], g3[2]]])

    q.shape = (3, 1)
    q = np.matrix(q.copy())
    m_inv = m.I

    # print"M: ", m
    # print"q: ", q

    return m, q, m_inv


def calculate_fre(fiducials, minv, n, q1, q2):
    """
    Calculate the Fiducial Registration Error for neuronavigation.

    :param fiducials: array of 6 rows (image and tracker fiducials) and 3 columns (x, y, z) with coordinates
    :param minv: inverse matrix given by base creation
    :param n: base change matrix given by base creation
    :param q1: origin of first base
    :param q2: origin of second base
    :return: float number of fiducial registration error
    """

    img = np.zeros([3, 3])
    dist = np.zeros([3, 1])

    p1 = np.mat(fiducials[3, :]).reshape(3, 1)
    p2 = np.mat(fiducials[4, :]).reshape(3, 1)
    p3 = np.mat(fiducials[5, :]).reshape(3, 1)

    img[0, :] = np.asarray((q1 + (minv * n) * (p1 - q2)).reshape(1, 3))
    img[1, :] = np.asarray((q1 + (minv * n) * (p2 - q2)).reshape(1, 3))
    img[2, :] = np.asarray((q1 + (minv * n) * (p3 - q2)).reshape(1, 3))

    dist[0] = np.sqrt(np.sum(np.power((img[0, :] - fiducials[0, :]), 2)))
    dist[1] = np.sqrt(np.sum(np.power((img[1, :] - fiducials[1, :]), 2)))
    dist[2] = np.sqrt(np.sum(np.power((img[2, :] - fiducials[2, :]), 2)))

    return float(np.sqrt(np.sum(dist ** 2) / 3))


def flip_x(point):
    """
    Flip coordinates of a vector according to X axis
    Coronal Images do not require this transformation - 1 tested
    and for this case, at navigation, the z axis is inverted

    It's necessary to multiply the z coordinate by (-1). Possibly
    because the origin of coordinate system of imagedata is
    located in superior left corner and the origin of VTK scene coordinate
    system (polygonal surface) is in the interior left corner. Second
    possibility is the order of slice stacking

    :param point: list of coordinates x, y and z
    :return: flipped coordinates
    """

    # TODO: check if the Flip function is related to the X or Y axis

    point = np.matrix(point + (0,))
    point[0, 2] = -point[0, 2]

    m_rot = np.matrix([[1.0, 0.0, 0.0, 0.0],
                      [0.0, -1.0, 0.0, 0.0],
                      [0.0, 0.0, -1.0, 0.0],
                      [0.0, 0.0, 0.0, 1.0]])
    m_trans = np.matrix([[1.0, 0, 0, -point[0, 0]],
                        [0.0, 1.0, 0, -point[0, 1]],
                        [0.0, 0.0, 1.0, -point[0, 2]],
                        [0.0, 0.0, 0.0, 1.0]])
    m_trans_return = np.matrix([[1.0, 0, 0, point[0, 0]],
                               [0.0, 1.0, 0, point[0, 1]],
                               [0.0, 0.0, 1.0, point[0, 2]],
                               [0.0, 0.0, 0.0, 1.0]])
        
    point_rot = point*m_trans*m_rot*m_trans_return
    x, y, z = point_rot.tolist()[0][:3]

    return x, y, z


def object_registration(fiducials):
    """

    :param fiducials:
    :param bases_coreg:
    :return:
    """

    # minv, n, q1, q2 = bases_coreg

    obj_center_trck = np.asmatrix(fiducials[3, :]).reshape([3, 1])
    obj_sensor_trck = np.asmatrix(fiducials[4, :]).reshape([3, 1])
    # obj_center = q1 + (minv * n) * (obj_center_trck - q2)
    # obj_sensor = q1 + (minv * n) * (obj_sensor_trck - q2)
    # obj_center_img = obj_center[0, 0], obj_center[1, 0], obj_center[2, 0]
    # obj_sensor_img = obj_sensor[0, 0], obj_sensor[1, 0], obj_sensor[2, 0]
    fids = fiducials[0:4, :] - fiducials[4, :]
    # m_trck, q_trck, m_inv_trck = base_creation(fiducials)

    return obj_center_trck, obj_sensor_trck, fids
    # return obj_center_img, obj_sensor_trck, m_inv_trck, obj_center_trck, obj_sensor_img
