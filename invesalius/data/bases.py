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


def base_creation_old(fiducials):
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

    m_inv = m.I

    return m, q, m_inv


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
    g1 = p3 - q
    g2 = p1 - q

    if not g1.any():
        g1 = p2 - q

    g3 = np.cross(g1, g2)

    g1 = g1/sqrt(np.dot(g1, g1))
    g2 = g2/sqrt(np.dot(g2, g2))
    g3 = g3/sqrt(np.dot(g3, g3))

    m = np.matrix([[g1[0], g2[0], g3[0]],
                   [g1[1], g2[1], g3[1]],
                   [g1[2], g2[2], g3[2]]])

    m_inv = m.I

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
    point_4[2, 0] = -point_4[2, 0]

    m_rot = np.asmatrix(tr.euler_matrix(pi, 0, 0))

    point_rot = m_rot*point_4

    return point_rot[0, 0], point_rot[1, 0], point_rot[2, 0]


def object_registration(fiducials, orients, coord_raw, m_change):
    """

    :param fiducials: 3x3 array of fiducials translations
    :param orients: 3x3 array of fiducials orientations in degrees
    :param coord_raw: nx6 array of coordinates from tracking device where n = 1 is the reference attached to the head
    :param m_change: 3x3 array representing change of basis from head in tracking system to vtk head system
    :return:
    """

    coords_aux = np.hstack((fiducials, orients))
    mask = np.ones(len(coords_aux), dtype=bool)
    mask[[3]] = False
    coords = coords_aux[mask]

    fids_dyn = np.zeros([4, 6])
    fids_img = np.zeros([4, 6])
    fids_raw = np.zeros([3, 3])

    # compute fiducials of object with reference to the fixed probe in source frame
    for ic in range(0, 3):
        fids_raw[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coords[3, :])[:3]

    # compute initial alignment of probe fixed in the object in source frame
    t_s0_raw = np.asmatrix(tr.translation_matrix(coords[3, :3]))
    r_s0_raw = np.asmatrix(tr.euler_matrix(np.radians(coords[3, 3]), np.radians(coords[3, 4]),
                             np.radians(coords[3, 5]), 'rzyx'))
    s0_raw = np.asmatrix(tr.concatenate_matrices(t_s0_raw, r_s0_raw))

    # compute change of basis for object fiducials in source frame
    base_obj_raw, q_obj_raw, base_inv_obj_raw = base_creation(fids_raw[:3, :3])
    r_obj_raw = np.asmatrix(np.identity(4))
    r_obj_raw[:3, :3] = base_obj_raw[:3, :3]
    t_obj_raw = np.asmatrix(tr.translation_matrix(q_obj_raw))
    m_obj_raw = np.asmatrix(tr.concatenate_matrices(t_obj_raw, r_obj_raw))

    for ic in range(0, 4):
        if coord_raw.any():
            # compute object fiducials in reference frame
            fids_dyn[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coord_raw[1, :])
            fids_dyn[ic, 2] = -fids_dyn[ic, 2]
        else:
            # compute object fiducials in source frame
            fids_dyn[ic, :] = coords[ic, :]

        # compute object fiducials in vtk head frame
        a, b, g = np.radians(fids_dyn[ic, 3:])
        T_p = tr.translation_matrix(fids_dyn[ic, :3])
        R_p = tr.euler_matrix(a, b, g, 'rzyx')
        M_p = np.asmatrix(tr.concatenate_matrices(T_p, R_p))
        M_img = np.asmatrix(m_change) * M_p

        angles_img = np.degrees(np.asarray(tr.euler_from_matrix(M_img, 'rzyx')))
        coord_img = np.asarray(flip_x_m(tr.translation_from_matrix(M_img)))

        fids_img[ic, :] = np.hstack((coord_img, angles_img))

    # compute object base change in vtk head frame
    base_obj_img, q_obj_img, base_inv_obj_img = base_creation(fids_img[:3, :3])
    r_obj_img = np.asmatrix(np.identity(4))
    r_obj_img[:3, :3] = base_obj_img[:3, :3]

    # compute initial alignment of probe fixed in the object in reference (or static) frame
    s0_trans_dyn = np.asmatrix(tr.translation_matrix(fids_dyn[3, :3]))
    s0_rot_dyn = np.asmatrix(tr.euler_matrix(np.radians(fids_dyn[3, 3]), np.radians(fids_dyn[3, 4]),
                                             np.radians(fids_dyn[3, 5]), 'rzyx'))
    s0_dyn = np.asmatrix(tr.concatenate_matrices(s0_trans_dyn, s0_rot_dyn))

    return t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img
