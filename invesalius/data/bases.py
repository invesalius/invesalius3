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
    Calculate the origin and matrix for coordinate system transformation.
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

    g1 = g1/np.sqrt(np.dot(g1, g1))
    g2 = g2/np.sqrt(np.dot(g2, g2))
    g3 = g3/np.sqrt(np.dot(g3, g3))

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
    lamb = np.dot(sub1, sub2)/np.dot(sub1, sub1)

    q = p1 + lamb*sub1
    g1 = p3 - q
    g2 = p1 - q

    if not g1.any():
        g1 = p2 - q

    g3 = np.cross(g1, g2)

    g1 = g1/np.sqrt(np.dot(g1, g1))
    g2 = g2/np.sqrt(np.dot(g2, g2))
    g3 = g3/np.sqrt(np.dot(g3, g3))

    m = np.zeros([3, 3])
    m[:, 0] = g1/np.sqrt(np.dot(g1, g1))
    m[:, 1] = g2/np.sqrt(np.dot(g2, g2))
    m[:, 2] = g3/np.sqrt(np.dot(g3, g3))

    return m, q


# def calculate_fre(fiducials, minv, n, q, o):
#     """
#     Calculate the Fiducial Registration Error for neuronavigation.
#
#     :param fiducials: array of 6 rows (image and tracker fiducials) and 3 columns (x, y, z) with coordinates
#     :param minv: inverse matrix given by base creation
#     :param n: base change matrix given by base creation
#     :param q: origin of first base
#     :param o: origin of second base
#     :return: float number of fiducial registration error
#     """
#
#     img = np.zeros([3, 3])
#     dist = np.zeros([3, 1])
#
#     q1 = np.mat(q).reshape(3, 1)
#     q2 = np.mat(o).reshape(3, 1)
#
#     p1 = np.mat(fiducials[3, :]).reshape(3, 1)
#     p2 = np.mat(fiducials[4, :]).reshape(3, 1)
#     p3 = np.mat(fiducials[5, :]).reshape(3, 1)
#
#     img[0, :] = np.asarray((q1 + (minv * n) * (p1 - q2)).reshape(1, 3))
#     img[1, :] = np.asarray((q1 + (minv * n) * (p2 - q2)).reshape(1, 3))
#     img[2, :] = np.asarray((q1 + (minv * n) * (p3 - q2)).reshape(1, 3))
#
#     dist[0] = np.sqrt(np.sum(np.power((img[0, :] - fiducials[0, :]), 2)))
#     dist[1] = np.sqrt(np.sum(np.power((img[1, :] - fiducials[1, :]), 2)))
#     dist[2] = np.sqrt(np.sum(np.power((img[2, :] - fiducials[2, :]), 2)))
#
#     return float(np.sqrt(np.sum(dist ** 2) / 3))


def calculate_fre_m(fiducials):
    """
    Calculate the Fiducial Registration Error for neuronavigation.

    :param fiducials: array of 6 rows (image and tracker fiducials) and 3 columns (x, y, z) with coordinates
    :param minv: inverse matrix given by base creation
    :param n: base change matrix given by base creation
    :param q: origin of first base
    :param o: origin of second base
    :return: float number of fiducial registration error
    """

    m, q1, minv = base_creation_old(fiducials[:3, :])
    n, q2, ninv = base_creation_old(fiducials[3:, :])

    # TODO: replace the old by the new base creation
    # the values differ greatly if FRE is computed using the old or new base_creation
    # check the reason for the difference, because they should be the same
    # m, q1 = base_creation(fiducials[:3, :])
    # n, q2 = base_creation(fiducials[3:, :])
    # minv = np.linalg.inv(m)

    img = np.zeros([3, 3])
    dist = np.zeros([3, 1])

    q1 = q1.reshape(3, 1)
    q2 = q2.reshape(3, 1)

    p1 = fiducials[3, :].reshape(3, 1)
    p2 = fiducials[4, :].reshape(3, 1)
    p3 = fiducials[5, :].reshape(3, 1)

    img[0, :] = (q1 + (minv @ n) * (p1 - q2)).reshape(1, 3)
    img[1, :] = (q1 + (minv @ n) * (p2 - q2)).reshape(1, 3)
    img[2, :] = (q1 + (minv @ n) * (p3 - q2)).reshape(1, 3)

    dist[0] = np.sqrt(np.sum(np.power((img[0, :] - fiducials[0, :]), 2)))
    dist[1] = np.sqrt(np.sum(np.power((img[1, :] - fiducials[1, :]), 2)))
    dist[2] = np.sqrt(np.sum(np.power((img[2, :] - fiducials[2, :]), 2)))

    return float(np.sqrt(np.sum(dist ** 2) / 3))


# The function flip_x_m is deprecated and was replaced by a simple minus multiplication of the Y coordinate as follows:
# coord_flip = list(coord)
# coord_flip[1] = -coord_flip[1]

# def flip_x_m(point):
#     """
#     Rotate coordinates of a vector by pi around X axis in static reference frame.
#
#     InVesalius also require to multiply the z coordinate by (-1). Possibly
#     because the origin of coordinate system of imagedata is
#     located in superior left corner and the origin of VTK scene coordinate
#     system (polygonal surface) is in the interior left corner. Second
#     possibility is the order of slice stacking
#
#     :param point: list of coordinates x, y and z
#     :return: rotated coordinates
#     """
#
#     point_4 = np.hstack((point, 1.)).reshape(4, 1)
#     point_4[2, 0] = -point_4[2, 0]
#
#     m_rot = tr.euler_matrix(np.pi, 0, 0)
#
#     point_rot = m_rot @ point_4
#
#     return point_rot


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
    t_s0_raw = tr.translation_matrix(coords[3, :3])
    r_s0_raw = tr.euler_matrix(np.radians(coords[3, 3]), np.radians(coords[3, 4]),
                             np.radians(coords[3, 5]), 'rzyx')
    s0_raw = tr.concatenate_matrices(t_s0_raw, r_s0_raw)

    # compute change of basis for object fiducials in source frame
    base_obj_raw, q_obj_raw = base_creation(fids_raw[:3, :3])
    r_obj_raw = np.identity(4)
    r_obj_raw[:3, :3] = base_obj_raw[:3, :3]
    t_obj_raw = tr.translation_matrix(q_obj_raw)
    m_obj_raw = tr.concatenate_matrices(t_obj_raw, r_obj_raw)

    for ic in range(0, 4):
        if coord_raw.any():
            # compute object fiducials in reference frame
            fids_dyn[ic, :] = dco.dynamic_reference_m2(coords[ic, :], coord_raw[1, :])
        else:
            # compute object fiducials in source frame
            fids_dyn[ic, :] = coords[ic, :]
        fids_dyn[ic, 2] = -fids_dyn[ic, 2]

        # compute object fiducials in vtk head frame
        a, b, g = np.radians(fids_dyn[ic, 3:])
        T_p = tr.translation_matrix(fids_dyn[ic, :3])
        R_p = tr.euler_matrix(a, b, g, 'rzyx')
        M_p = tr.concatenate_matrices(T_p, R_p)
        M_img = m_change @ M_p

        angles_img = np.degrees(np.asarray(tr.euler_from_matrix(M_img, 'rzyx')))
        coord_img = list(M_img[:3, -1])
        coord_img[1] = -coord_img[1]

        fids_img[ic, :] = np.hstack((coord_img, angles_img))

    # compute object base change in vtk head frame
    base_obj_img, _ = base_creation(fids_img[:3, :3])
    r_obj_img = np.identity(4)
    r_obj_img[:3, :3] = base_obj_img[:3, :3]

    # compute initial alignment of probe fixed in the object in reference (or static) frame
    s0_trans_dyn = tr.translation_matrix(fids_dyn[3, :3])
    s0_rot_dyn = tr.euler_matrix(np.radians(fids_dyn[3, 3]), np.radians(fids_dyn[3, 4]),
                                             np.radians(fids_dyn[3, 5]), 'rzyx')
    s0_dyn = tr.concatenate_matrices(s0_trans_dyn, s0_rot_dyn)

    return t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img
