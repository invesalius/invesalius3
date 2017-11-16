from math import sqrt, pi
import numpy as np
import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr


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

    # q.shape = (3, 1)
    # q = np.matrix(q.copy())
    m_inv = m.I

    # print"M: ", m
    # print"q: ", q

    return m, q, m_inv

def base_creation_object(fiducials):
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
    g1 = p3 - q
    g2 = p1 - q

    # if not g1.any():
    #     g1 = p2 - q

    g3 = np.cross(g1, g2)

    g1 = g1/sqrt(np.dot(g1, g1))
    g2 = g2/sqrt(np.dot(g2, g2))
    g3 = g3/sqrt(np.dot(g3, g3))

    m = np.matrix([[g1[0], g2[0], g3[0]],
                   [g1[1], g2[1], g3[1]],
                   [g1[2], g2[2], g3[2]]])

    # q.shape = (3, 1)
    # q = np.matrix(q.copy())
    m_inv = m.I

    # print"M: ", m
    # print"q: ", q

    return m, q, m_inv


def calculate_fre(fiducials, minv, n, q, o):
    """
    Calculate the Fiducial Registration Error for neuronavigation.

    :param fiducials: array of 6 rows (image and tracker fiducials) and 3 columns (x, y, z) with coordinates
    :param minv: inverse matrix given by base creation
    :param n: base change matrix given by base creation
    :param q: origin of first base
    :param o: origin of second base
    :return: float number of fiducial registration error
    """

    img = np.zeros([3, 3])
    dist = np.zeros([3, 1])

    q1 = np.mat(q).reshape(3, 1)
    q2 = np.mat(o).reshape(3, 1)

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


def flip_x_m(point):
    """
    Rotate coordinates of a vector by pi around X axis in static reference frame.

    InVesalius also require to multiply the z coordinate by (-1). Possibly
    because the origin of coordinate system of imagedata is
    located in superior left corner and the origin of VTK scene coordinate
    system (polygonal surface) is in the interior left corner. Second
    possibility is the order of slice stacking

    :param point: list of coordinates x, y and z
    :return: rotated coordinates
    """

    point_4 = np.hstack((point, 1.)).reshape([4, 1])
    # point_4 = np.matrix(point + (0,)).reshape([4, 1])
    point_4[2, 0] = -point_4[2, 0]

    m_rot = np.asmatrix(tr.euler_matrix(pi, 0, 0))
    # m_rot_y = np.asmatrix(tr.euler_matrix(0, pi, 0))

    point_rot = m_rot*point_4

    return point_rot[0, 0], point_rot[1, 0], point_rot[2, 0]


def flip_x_m2(point):
    """
    Rotate coordinates of a vector by pi around X axis in static reference frame.

    InVesalius also require to multiply the z coordinate by (-1). Possibly
    because the origin of coordinate system of imagedata is
    located in superior left corner and the origin of VTK scene coordinate
    system (polygonal surface) is in the interior left corner. Second
    possibility is the order of slice stacking

    :param point: list of coordinates x, y and z
    :return: rotated coordinates
    """

    m_4 = np.asmatrix(np.identity(4))
    m_4[:3, :3] = point[:3, :3]
    # point_4 = np.matrix(point + (0,)).reshape([4, 1])
    # point_4[2, 0] = -point_4[2, 0]

    m_rot = np.asmatrix(tr.euler_matrix(pi, 0, 0))
    m_rot_z = np.asmatrix(tr.euler_matrix(0, 0, -pi/2))
    # m_rot_y = np.asmatrix(tr.euler_matrix(0, pi, 0))

    point_rot = m_rot_z*m_rot*m_4

    return point_rot


def object_registration(fiducials, orients, coord_raw, m_change):
    """

    :param fiducials:
    :param orients:
    :return:
    """

    coords = np.hstack((fiducials, orients))
    fids_s0 = np.zeros([3, 3])
    fids_dyn = np.zeros([4, 6])
    fids_img = np.zeros([4, 6])

    # this block is to compute object coordinates in reference frame
    for ic in range(0, 3):
        fids_dyn[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coord_raw[1, :])

    fids_dyn[3, :] = dco.dynamic_reference_m2(coords[4, :], coord_raw[1, :])
    fids_dyn[:, 2] = -fids_dyn[:, 2]

    for ic in range(0, 4):
        a, b, g = np.radians(fids_dyn[ic, 3:])
        T_p = tr.translation_matrix(fids_dyn[ic, :3])
        R_p = tr.euler_matrix(a, b, g, 'rzyx')
        M_p = np.asmatrix(tr.concatenate_matrices(T_p, R_p))
        M_img = np.asmatrix(m_change) * M_p

        angles = np.degrees(np.asarray(tr.euler_from_matrix(M_img, 'rzyx')))
        coords = np.asarray(flip_x_m(tr.translation_from_matrix(M_img)))

        fids_img[ic, :] = np.hstack((coords, angles))

    for ic in range(0, 3):
        fids_s0[ic, :] = dco.dynamic_reference_m2(fids_img[ic, :], fids_img[3, :])[:3]

    # this block is to compute object coordinates in source frame
    # for ic in range(0, 3):
    #     fids_raw[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coords[4, :])[:3]
    #
    # fids_raw[3, :] = coords[4, :]

    s0_trans = tr.translation_matrix(fids_img[3, :3])
    s0_rot = tr.euler_matrix(np.radians(fids_img[3, 3]), np.radians(fids_img[3, 4]),
                             np.radians(fids_img[3, 5]), 'rzyx')
    S0 = np.asmatrix(tr.concatenate_matrices(s0_trans, s0_rot))

    m_obj_0, q_obj_0, m_inv_obj_0 = base_creation_object(fids_s0[:3, :3])
    m_obj_rot_0 = np.asmatrix(np.identity(4))
    m_obj_rot_0[:3, :3] = m_obj_0[:3, :3]
    m_obj_trans_0 = np.asmatrix(tr.translation_matrix(q_obj_0))
    m_obj_base_0 = np.asmatrix(tr.concatenate_matrices(m_obj_trans_0, m_obj_rot_0))

    # obj_img = np.array([[0., 0., 1.], [0., 0., -1.], [1., 0., 0.]])
    # m_obj_all = tr.affine_matrix_from_points(fids_img[:3, :3].T, obj_img.T,
    #                                          shear=False, scale=False)
    # scale_all, shear_all, angles_all, trans_all, persp_all = tr.decompose_matrix(m_obj_all)
    # rotate_all = tr.euler_matrix(*angles_all)

    m_obj, q_obj, m_inv_obj = base_creation_object(fids_img[:3, :3])
    m_obj_rot = np.asmatrix(np.identity(4))
    m_obj_rot[:3, :3] = m_obj[:3, :3]
    m_obj_trans = np.asmatrix(tr.translation_matrix(q_obj))
    m_obj_base = np.asmatrix(tr.concatenate_matrices(m_obj_trans, m_obj_rot))

    # print "m_obj: ", m_obj
    # print "m_obj_all: ", m_obj_all
    # print "q_obj: ", q_obj
    # print "rotate_all: ", rotate_all

    return fids_s0, fids_img, S0, m_obj_rot, m_obj_trans, m_obj_base, np.asmatrix(s0_rot), np.asmatrix(s0_trans), m_obj_trans_0, m_obj_rot_0, m_obj_base_0


def object_registration_m(fiducials, orients, coord_raw, m_change):
    """

    :param fiducials:
    :param orients:
    :return:
    """

    coords = np.hstack((fiducials, orients))
    fids_s0 = np.zeros([3, 3])
    fids_raw = np.zeros([4, 6])
    fids_img = np.zeros([4, 6])

    # this block is to compute object coordinates in source frame
    for ic in range(0, 3):
        fids_s0[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coords[4, :])[:3]

    # fids_raw[3, :] = coords[4, :]

    s0_trans = tr.translation_matrix(coords[4, :3])
    s0_rot = tr.euler_matrix(np.radians(coords[3, 3]), np.radians(coords[3, 4]),
                             np.radians(coords[3, 5]), 'rzyx')
    S0 = np.asmatrix(tr.concatenate_matrices(s0_trans, s0_rot))

    m_obj_0, q_obj_0, m_inv_obj_0 = base_creation_object(fids_s0[:3, :3])
    m_obj_rot_0 = np.asmatrix(np.identity(4))
    m_obj_rot_0[:3, :3] = m_obj_0[:3, :3]
    m_obj_trans_0 = np.asmatrix(tr.translation_matrix(q_obj_0))
    m_obj_base_0 = np.asmatrix(tr.concatenate_matrices(m_obj_trans_0, m_obj_rot_0))

    # obj_img = np.array([[0., 0., 1.], [0., 0., -1.], [1., 0., 0.]])
    # m_obj_all = tr.affine_matrix_from_points(fids_img[:3, :3].T, obj_img.T,
    #                                          shear=False, scale=False)
    # scale_all, shear_all, angles_all, trans_all, persp_all = tr.decompose_matrix(m_obj_all)
    # rotate_all = tr.euler_matrix(*angles_all)

    # m_obj, q_obj, m_inv_obj = base_creation_object(fids_img[:3, :3])
    # m_obj_rot = np.asmatrix(np.identity(4))
    # m_obj_rot[:3, :3] = m_obj[:3, :3]
    # m_obj_trans = np.asmatrix(tr.translation_matrix(q_obj))
    # m_obj_base = np.asmatrix(tr.concatenate_matrices(m_obj_trans, m_obj_rot))

    # print "m_obj: ", m_obj
    # print "m_obj_all: ", m_obj_all
    # print "q_obj: ", q_obj
    # print "rotate_all: ", rotate_all

    return fids_s0, fids_img, S0, None, None, None, np.asmatrix(s0_rot), np.asmatrix(s0_trans), m_obj_trans_0, m_obj_rot_0, m_obj_base_0


def object_registration_m3(fiducials, orients, coord_raw, m_change):
    """

    :param fiducials:
    :param orients:
    :return:
    """

    coords_aux = np.hstack((fiducials, orients))
    mask = np.ones(len(coords_aux), dtype=bool)
    mask[[3]] = False
    coords = coords_aux[mask]

    fids_s0 = np.zeros([3, 3])
    fids_s0_dyn = np.zeros([3, 3])
    fids_dyn = np.zeros([4, 6])
    fids_img = np.zeros([4, 6])
    fids_raw = np.zeros([3, 3])

    # this block is to compute object coordinates in source frame
    for ic in range(0, 3):
        fids_raw[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coords[3, :])[:3]

    s0_trans_raw = np.asmatrix(tr.translation_matrix(coords[3, :3]))
    s0_rot_raw = np.asmatrix(tr.euler_matrix(np.radians(coords[3, 3]), np.radians(coords[3, 4]),
                             np.radians(coords[3, 5]), 'rzyx'))
    S0_raw = np.asmatrix(tr.concatenate_matrices(s0_trans_raw, s0_rot_raw))

    m_obj_raw, q_obj_raw, m_inv_obj_raw = base_creation_object(fids_raw[:3, :3])
    r_obj_raw = np.asmatrix(np.identity(4))
    r_obj_raw[:3, :3] = m_obj_raw[:3, :3]
    t_obj_raw = np.asmatrix(tr.translation_matrix(q_obj_raw))
    m_obj_base_raw = np.asmatrix(tr.concatenate_matrices(t_obj_raw, r_obj_raw))

    # this block is to compute object coordinates in reference frame
    for ic in range(0, 4):
        fids_dyn[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coord_raw[1, :])

    fids_dyn[:, 2] = -fids_dyn[:, 2]

    for ic in range(0, 3):
        fids_s0_dyn[ic, :] = dco.dynamic_reference_m2(fids_dyn[ic, :], fids_dyn[3, :])[:3]

    m_obj_dyn_0, q_obj_dyn_0, m_inv_obj_dyn_0 = base_creation_object(fids_s0_dyn[:3, :3])
    r_obj_dyn_0 = np.asmatrix(np.identity(4))
    r_obj_dyn_0[:3, :3] = m_obj_dyn_0[:3, :3]
    t_obj_dyn_0 = np.asmatrix(tr.translation_matrix(q_obj_dyn_0))
    m_obj_base_dyn_0 = np.asmatrix(tr.concatenate_matrices(t_obj_dyn_0, r_obj_dyn_0))

    s0_trans_dyn = np.asmatrix(tr.translation_matrix(fids_dyn[3, :3]))
    s0_rot_dyn = np.asmatrix(tr.euler_matrix(np.radians(fids_dyn[3, 3]), np.radians(fids_dyn[3, 4]),
                                             np.radians(fids_dyn[3, 5]), 'rzyx'))
    S0_dyn = np.asmatrix(tr.concatenate_matrices(s0_trans_dyn, s0_rot_dyn))

    m_obj_dyn, q_obj_dyn, m_inv_obj_dyn = base_creation_object(fids_dyn[:3, :3])
    r_obj_dyn = np.asmatrix(np.identity(4))
    r_obj_dyn[:3, :3] = m_obj_dyn[:3, :3]
    t_obj_dyn = np.asmatrix(tr.translation_matrix(q_obj_dyn))
    m_obj_base_dyn = np.asmatrix(tr.concatenate_matrices(t_obj_dyn, r_obj_dyn))

    for ic in range(0, 4):
        a, b, g = np.radians(fids_dyn[ic, 3:])
        T_p = tr.translation_matrix(fids_dyn[ic, :3])
        R_p = tr.euler_matrix(a, b, g, 'rzyx')
        M_p = np.asmatrix(tr.concatenate_matrices(T_p, R_p))
        M_img = np.asmatrix(m_change) * M_p

        angles_img = np.degrees(np.asarray(tr.euler_from_matrix(M_img, 'rzyx')))
        coords_img = np.asarray(flip_x_m(tr.translation_from_matrix(M_img)))

        fids_img[ic, :] = np.hstack((coords_img, angles_img))

    for ic in range(0, 3):
        fids_s0[ic, :] = dco.dynamic_reference_m2(fids_img[ic, :], fids_img[3, :])[:3]

    s0_trans = tr.translation_matrix(fids_img[3, :3])
    s0_rot = tr.euler_matrix(np.radians(fids_img[3, 3]), np.radians(fids_img[3, 4]),
                             np.radians(fids_img[3, 5]), 'rzyx')
    S0 = np.asmatrix(tr.concatenate_matrices(s0_trans, s0_rot))

    m_obj_0, q_obj_0, m_inv_obj_0 = base_creation_object(fids_s0[:3, :3])
    r_obj_0 = np.asmatrix(np.identity(4))
    r_obj_0[:3, :3] = m_obj_0[:3, :3]
    t_obj_0 = np.asmatrix(tr.translation_matrix(q_obj_0))
    m_obj_base_0 = np.asmatrix(tr.concatenate_matrices(t_obj_0, r_obj_0))

    m_obj, q_obj, m_inv_obj = base_creation_object(fids_img[:3, :3])
    r_obj = np.asmatrix(np.identity(4))
    r_obj[:3, :3] = m_obj[:3, :3]
    t_obj = np.asmatrix(tr.translation_matrix(q_obj))
    m_obj_base = np.asmatrix(tr.concatenate_matrices(t_obj, r_obj))

    # print "m_obj: ", m_obj
    # print "m_obj_all: ", m_obj_all
    # print "q_obj: ", q_obj
    # print "rotate_all: ", rotate_all

    return fids_s0, fids_img, S0, r_obj, t_obj, m_obj_base, np.asmatrix(s0_rot),\
           np.asmatrix(s0_trans), t_obj_0, r_obj_0, m_obj_base_0,\
           t_obj_raw, r_obj_raw, S0_raw, s0_rot_raw, t_obj_dyn, r_obj_dyn, S0_dyn,\
           s0_rot_dyn, s0_trans_dyn, m_obj_base_dyn, m_obj_base_raw,\
           m_obj_base_dyn_0, t_obj_dyn_0, r_obj_dyn_0


def object_registration_m4(fiducials, orients, m_dyn, m_change, m_ref):
    """

    :param fiducials:
    :param orients:
    :return:
    """

    fids_dyn = np.zeros([4, 6])
    fids_img = np.zeros([4, 6])
    fids_rot = np.asmatrix(np.ones([4, 5]))
    fids_rot_fin = np.asmatrix(np.ones([4, 5]))

    # this block is to compute object coordinates in source frame
    for ic in range(0, 5):
        fids_rot[:3, ic] = np.asarray(fiducials[ic, :]).reshape([3, 1])
        fids_rot_fin[:, ic] = m_ref.I * m_dyn * fids_rot[:, ic]

    fids_rot_fin[2, :] = -fids_rot_fin[2, :]

    # this block is to compute object coordinates in reference frame
    for ic in range(0, 3):
        fids_dyn[ic, :3] = fids_rot_fin[:3, ic].T

    for ic in range(0, 3):
        a, b, g = np.radians(fids_dyn[ic, 3:])
        T_p = tr.translation_matrix(fids_dyn[ic, :3])
        R_p = tr.euler_matrix(a, b, g, 'rzyx')
        M_p = np.asmatrix(tr.concatenate_matrices(T_p, R_p))
        M_img = np.asmatrix(m_change) * M_p

        angles = np.degrees(np.asarray(tr.euler_from_matrix(M_img, 'rzyx')))
        coords = np.asarray(flip_x_m(tr.translation_from_matrix(M_img)))

        fids_img[ic, :] = np.hstack((coords, angles))

    m_obj, q_obj, m_inv_obj = base_creation_object(fids_img[:3, :3])
    m_obj_rot = np.asmatrix(np.identity(4))
    m_obj_rot[:3, :3] = m_obj[:3, :3]
    m_obj_trans = np.asmatrix(tr.translation_matrix(q_obj))
    m_obj_base = np.asmatrix(tr.concatenate_matrices(m_obj_trans, m_obj_rot))

    return m_obj_rot
