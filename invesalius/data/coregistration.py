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

import numpy as np
import queue
import threading
from time import sleep

import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr


# TODO: Replace the use of degrees by radians in every part of the navigation pipeline

def object_marker_to_center(coord_raw, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw):
    """Translate and rotate the raw coordinate given by the tracking device to the reference system created during
    the object registration.

    :param coord_raw: Coordinates returned by the tracking device
    :type coord_raw: numpy.ndarray
    :param obj_ref_mode:
    :type obj_ref_mode: int
    :param t_obj_raw:
    :type t_obj_raw: numpy.ndarray
    :param s0_raw:
    :type s0_raw: numpy.ndarray
    :param r_s0_raw: rotation transformation from marker to object basis
    :type r_s0_raw: numpy.ndarray
    :return: 4 x 4 numpy double array
    :rtype: numpy.ndarray
    """

    as1, bs1, gs1 = np.radians(coord_raw[obj_ref_mode, 3:])
    r_probe = tr.euler_matrix(as1, bs1, gs1, 'rzyx')
    t_probe_raw = tr.translation_matrix(coord_raw[obj_ref_mode, :3])
    t_offset_aux = np.linalg.inv(r_s0_raw) @ r_probe @ t_obj_raw
    t_offset = np.identity(4)
    t_offset[:, -1] = t_offset_aux[:, -1]
    t_probe = s0_raw @ t_offset @ np.linalg.inv(s0_raw) @ t_probe_raw
    m_probe = tr.concatenate_matrices(t_probe, r_probe)

    return m_probe


def object_to_reference(coord_raw, m_probe):
    """Compute affine transformation matrix to the reference basis

    :param coord_raw: Coordinates returned by the tracking device
    :type coord_raw: numpy.ndarray
    :param m_probe: Probe coordinates
    :type m_probe: numpy.ndarray
    :return: 4 x 4 numpy double array
    :rtype: numpy.ndarray
    """

    a, b, g = np.radians(coord_raw[1, 3:])
    r_ref = tr.euler_matrix(a, b, g, 'rzyx')
    t_ref = tr.translation_matrix(coord_raw[1, :3])
    m_ref = tr.concatenate_matrices(t_ref, r_ref)

    m_dyn = np.linalg.inv(m_ref) @ m_probe
    return m_dyn


def tracker_to_image(m_change, m_probe_ref, r_obj_img, m_obj_raw, s0_dyn):
    """Compute affine transformation matrix to the reference basis

    :param m_change: Corregistration transformation obtained from fiducials
    :type m_change: numpy.ndarray
    :param m_probe_ref: Object or probe in reference coordinate system
    :type m_probe_ref: numpy.ndarray
    :param r_obj_img: Object coordinate system in image space (3d model)
    :type r_obj_img: numpy.ndarray
    :param m_obj_raw: Object basis in raw coordinates from tacker
    :type m_obj_raw: numpy.ndarray
    :param s0_dyn:
    :type s0_dyn: numpy.ndarray
    :return: 4 x 4 numpy double array
    :rtype: numpy.ndarray
    """

    m_img = m_change @ m_probe_ref
    r_obj = r_obj_img @ np.linalg.inv(m_obj_raw) @ np.linalg.inv(s0_dyn) @ m_probe_ref @ m_obj_raw
    m_img[:3, :3] = r_obj[:3, :3]
    return m_img


def corregistrate_object_dynamic(inp, coord_raw, ref_mode_id):

    m_change, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = inp

    # transform raw marker coordinate to object center
    m_probe = object_marker_to_center(coord_raw, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw)
    # transform object center to reference marker if specified as dynamic reference
    if ref_mode_id:
        m_probe_ref = object_to_reference(coord_raw, m_probe)
    else:
        m_probe_ref = m_probe
    # invert y coordinate
    m_probe_ref[2, -1] = -m_probe_ref[2, -1]
    # corregistrate from tracker to image space
    m_img = tracker_to_image(m_change, m_probe_ref, r_obj_img, m_obj_raw, s0_dyn)
    # compute rotation angles
    _, _, angles, _, _ = tr.decompose_matrix(m_img)
    # create output coordiante list
    coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
            np.degrees(angles[0]), np.degrees(angles[1]), np.degrees(angles[2])

    return coord, m_img


def compute_marker_transformation(coord_raw, obj_ref_mode):
    psi, theta, phi = np.radians(coord_raw[obj_ref_mode, 3:])
    r_probe = tr.euler_matrix(psi, theta, phi, 'rzyx')
    t_probe = tr.translation_matrix(coord_raw[obj_ref_mode, :3])
    m_probe = tr.concatenate_matrices(t_probe, r_probe)
    return m_probe


def corregistrate_dynamic(inp, coord_raw, ref_mode_id):

    m_change, obj_ref_mode = inp

    # transform raw marker coordinate to object center
    m_probe = compute_marker_transformation(coord_raw, obj_ref_mode)
    # transform object center to reference marker if specified as dynamic reference
    if ref_mode_id:
        m_ref = compute_marker_transformation(coord_raw, 1)
        m_probe_ref = np.linalg.inv(m_ref) @ m_probe
    else:
        m_probe_ref = m_probe

    # invert y coordinate
    m_probe_ref[2, -1] = -m_probe_ref[2, -1]
    # corregistrate from tracker to image space
    m_img = m_change @ m_probe_ref
    # compute rotation angles
    _, _, angles, _, _ = tr.decompose_matrix(m_img)
    # create output coordiante list
    coord = m_img[0, -1], m_img[1, -1], m_img[2, -1],\
            np.degrees(angles[0]), np.degrees(angles[1]), np.degrees(angles[2])

    return coord, m_img


class CoordinateCorregistrate(threading.Thread):
    def __init__(self, ref_mode_id, trck_info, coreg_data, coord_queue, view_tracts, coord_tracts_queue, event, sle):
        threading.Thread.__init__(self, name='CoordCoregObject')
        self.ref_mode_id = ref_mode_id
        self.trck_info = trck_info
        self.coreg_data = coreg_data
        self.coord_queue = coord_queue
        self.view_tracts = view_tracts
        self.coord_tracts_queue = coord_tracts_queue
        self.event = event
        self.sle = sle

    def run(self):
        trck_info = self.trck_info
        coreg_data = self.coreg_data
        view_obj = 1

        trck_init, trck_id, trck_mode = trck_info
        # print('CoordCoreg: event {}'.format(self.event.is_set()))
        while not self.event.is_set():
            try:
                # print(f"Set the coordinate")
                coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
                # coord, m_img = corregistrate_object_dynamic(coreg_data, coord_raw, self.ref_mode_id)
                m_img = np.array([[0.38, -0.8, -0.45, 40.17],
                                  [0.82, 0.52, -0.24, 152.28],
                                  [0.43, -0.28, 0.86, 235.78],
                                  [0., 0., 0., 1.]])
                angles = [-0.318, -0.441, 1.134]
                coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
                        np.degrees(angles[0]), np.degrees(angles[1]), np.degrees(angles[2])
                m_img_flip = m_img.copy()
                m_img_flip[1, -1] = -m_img_flip[1, -1]
                # self.pipeline.set_message(m_img_flip)
                self.coord_queue.put_nowait([coord, m_img, view_obj])
                # print('CoordCoreg: put {}'.format(count))
                # count += 1

                if self.view_tracts:
                    self.coord_tracts_queue.put_nowait(m_img_flip)

                # The sleep has to be in both threads
                sleep(self.sle)
            except queue.Full:
                pass


class CoordinateCorregistrateNoObject(threading.Thread):
    def __init__(self, ref_mode_id, trck_info, coreg_data, coord_queue, view_tracts, coord_tracts_queue, event, sle):
        threading.Thread.__init__(self, name='CoordCoregNoObject')
        self.ref_mode_id = ref_mode_id
        self.trck_info = trck_info
        self.coreg_data = coreg_data
        self.coord_queue = coord_queue
        self.view_tracts = view_tracts
        self.coord_tracts_queue = coord_tracts_queue
        self.event = event
        self.sle = sle

    def run(self):
        trck_info = self.trck_info
        coreg_data = self.coreg_data
        view_obj = 0

        trck_init, trck_id, trck_mode = trck_info
        # print('CoordCoreg: event {}'.format(self.event.is_set()))
        while not self.event.is_set():
            try:
                # print(f"Set the coordinate")
                coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
                coord, m_img = corregistrate_dynamic(coreg_data, coord_raw, self.ref_mode_id)
                # print("Coord: ", coord)
                m_img_flip = m_img.copy()
                m_img_flip[1, -1] = -m_img_flip[1, -1]
                self.coord_queue.put_nowait([coord, m_img, view_obj])

                if self.view_tracts:
                    self.coord_tracts_queue.put_nowait(m_img_flip)

                # The sleep has to be in both threads
                sleep(self.sle)
            except queue.Full:
                pass


# class CoregistrationStatic(threading.Thread):
#     """
#     Thread to update the coordinates with the fiducial points
#     co-registration method while the Navigation Button is pressed.
#     Sleep function in run method is used to avoid blocking GUI and
#     for better real-time navigation
#     """
#
#     def __init__(self, coreg_data, nav_id, trck_info):
#         threading.Thread.__init__(self)
#         self.coreg_data = coreg_data
#         self.nav_id = nav_id
#         self.trck_info = trck_info
#         self._pause_ = False
#         self.start()
#
#     def stop(self):
#         self._pause_ = True
#
#     def run(self):
#         # m_change = self.coreg_data[0]
#         # obj_ref_mode = self.coreg_data[2]
#         #
#         # trck_init = self.trck_info[0]
#         # trck_id = self.trck_info[1]
#         # trck_mode = self.trck_info[2]
#
#         m_change, obj_ref_mode = self.coreg_data
#         trck_init, trck_id, trck_mode = self.trck_info
#
#         while self.nav_id:
#             coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
#
#             psi, theta, phi = coord_raw[obj_ref_mode, 3:]
#             t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))
#
#             t_probe_raw[2, -1] = -t_probe_raw[2, -1]
#
#             m_img = m_change * t_probe_raw
#
#             coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], psi, theta, phi
#
#             wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)
#
#             # TODO: Optimize the value of sleep for each tracking device.
#             sleep(0.175)
#
#             if self._pause_:
#                 return
#
#
# class CoregistrationDynamic(threading.Thread):
#     """
#     Thread to update the coordinates with the fiducial points
#     co-registration method while the Navigation Button is pressed.
#     Sleep function in run method is used to avoid blocking GUI and
#     for better real-time navigation
#     """
#
#     def __init__(self, coreg_data, nav_id, trck_info):
#         threading.Thread.__init__(self)
#         self.coreg_data = coreg_data
#         self.nav_id = nav_id
#         self.trck_info = trck_info
#         # self.tracts_info = tracts_info
#         # self.tracts = None
#         self._pause_ = False
#         # self.start()
#
#     def stop(self):
#         # self.tracts.stop()
#         self._pause_ = True
#
#     def run(self):
#         m_change, obj_ref_mode = self.coreg_data
#         trck_init, trck_id, trck_mode = self.trck_info
#         # seed, tracker, affine, affine_vtk = self.tracts_info
#
#         while self.nav_id:
#             coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
#
#             psi, theta, phi = radians(coord_raw[obj_ref_mode, 3:])
#             r_probe = tr.euler_matrix(psi, theta, phi, 'rzyx')
#             t_probe = tr.translation_matrix(coord_raw[obj_ref_mode, :3])
#             m_probe = asmatrix(tr.concatenate_matrices(t_probe, r_probe))
#
#             psi_ref, theta_ref, phi_ref = radians(coord_raw[1, 3:])
#             r_ref = tr.euler_matrix(psi_ref, theta_ref, phi_ref, 'rzyx')
#             t_ref = tr.translation_matrix(coord_raw[1, :3])
#             m_ref = asmatrix(tr.concatenate_matrices(t_ref, r_ref))
#
#             m_dyn = m_ref.I * m_probe
#             m_dyn[2, -1] = -m_dyn[2, -1]
#
#             m_img = m_change * m_dyn
#
#             scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)
#
#             coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
#                     degrees(angles[0]), degrees(angles[1]), degrees(angles[2])
#
#             # pos_world_aux = np.ones([4, 1])
#             # pos_world_aux[:3, -1] = db.flip_x((m_img[0, -1], m_img[1, -1], m_img[2, -1]))[:3]
#             # pos_world = np.linalg.inv(affine) @ pos_world_aux
#             # seed_aux = pos_world.reshape([1, 4])[0, :3]
#             # seed = seed_aux[np.newaxis, :]
#             #
#             # self.tracts = dtr.compute_tracts(tracker, seed, affine_vtk, True)
#
#             # wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)
#             wx.CallAfter(Publisher.sendMessage, 'Update cross position', arg=m_img, position=coord)
#
#             # TODO: Optimize the value of sleep for each tracking device.
#             sleep(3.175)
#
#             if self._pause_:
#                 return
#
#
# class CoregistrationDynamic_old(threading.Thread):
#     """
#     Thread to update the coordinates with the fiducial points
#     co-registration method while the Navigation Button is pressed.
#     Sleep function in run method is used to avoid blocking GUI and
#     for better real-time navigation
#     """
#
#     def __init__(self, bases, nav_id, trck_info):
#         threading.Thread.__init__(self)
#         self.bases = bases
#         self.nav_id = nav_id
#         self.trck_info = trck_info
#         self._pause_ = False
#         self.start()
#
#     def stop(self):
#         self._pause_ = True
#
#     def run(self):
#         m_inv = self.bases[0]
#         n = self.bases[1]
#         q1 = self.bases[2]
#         q2 = self.bases[3]
#         trck_init = self.trck_info[0]
#         trck_id = self.trck_info[1]
#         trck_mode = self.trck_info[2]
#
#         while self.nav_id:
#             # trck_coord, probe, reference = dco.GetCoordinates(trck_init, trck_id, trck_mode)
#             coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
#
#             trck_coord = dco.dynamic_reference(coord_raw[0, :], coord_raw[1, :])
#
#             trck_xyz = mat([[trck_coord[0]], [trck_coord[1]], [trck_coord[2]]])
#             img = q1 + (m_inv * n) * (trck_xyz - q2)
#
#             coord = (float(img[0]), float(img[1]), float(img[2]), trck_coord[3],
#                      trck_coord[4], trck_coord[5])
#             angles = coord_raw[0, 3:6]
#
#             # Tried several combinations and different locations to send the messages,
#             # however only this one does not block the GUI during navigation.
#             wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=None, position=coord)
#             wx.CallAfter(Publisher.sendMessage, 'Set camera in volume', coord)
#             wx.CallAfter(Publisher.sendMessage, 'Update tracker angles', angles)
#
#             # TODO: Optimize the value of sleep for each tracking device.
#             # Debug tracker is not working with 0.175 so changed to 0.2
#             # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
#             # sleep(.3)
#             sleep(0.175)
#
#             if self._pause_:
#                 return
#
#
# class CoregistrationObjectStatic(threading.Thread):
#     """
#     Thread to update the coordinates with the fiducial points
#     co-registration method while the Navigation Button is pressed.
#     Sleep function in run method is used to avoid blocking GUI and
#     for better real-time navigation
#     """
#
#     def __init__(self, coreg_data, nav_id, trck_info):
#         threading.Thread.__init__(self)
#         self.coreg_data = coreg_data
#         self.nav_id = nav_id
#         self.trck_info = trck_info
#         self._pause_ = False
#         self.start()
#
#     def stop(self):
#         self._pause_ = True
#
#     def run(self):
#         # m_change = self.coreg_data[0]
#         # t_obj_raw = self.coreg_data[1]
#         # s0_raw = self.coreg_data[2]
#         # r_s0_raw = self.coreg_data[3]
#         # s0_dyn = self.coreg_data[4]
#         # m_obj_raw = self.coreg_data[5]
#         # r_obj_img = self.coreg_data[6]
#         # obj_ref_mode = self.coreg_data[7]
#         #
#         # trck_init = self.trck_info[0]
#         # trck_id = self.trck_info[1]
#         # trck_mode = self.trck_info[2]
#
#         m_change, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = self.coreg_data
#         trck_init, trck_id, trck_mode = self.trck_info
#
#         while self.nav_id:
#             coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
#
#             as1, bs1, gs1 = radians(coord_raw[obj_ref_mode, 3:])
#             r_probe = asmatrix(tr.euler_matrix(as1, bs1, gs1, 'rzyx'))
#             t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))
#             t_offset_aux = r_s0_raw.I * r_probe * t_obj_raw
#             t_offset = asmatrix(identity(4))
#             t_offset[:, -1] = t_offset_aux[:, -1]
#             t_probe = s0_raw * t_offset * s0_raw.I * t_probe_raw
#             m_probe = asmatrix(tr.concatenate_matrices(t_probe, r_probe))
#
#             m_probe[2, -1] = -m_probe[2, -1]
#
#             m_img = m_change * m_probe
#             r_obj = r_obj_img * m_obj_raw.I * s0_dyn.I * m_probe * m_obj_raw
#
#             m_img[:3, :3] = r_obj[:3, :3]
#
#             scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)
#
#             coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
#                     degrees(angles[0]), degrees(angles[1]), degrees(angles[2])
#
#             wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)
#             wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=coord)
#
#             # TODO: Optimize the value of sleep for each tracking device.
#             sleep(0.175)
#
#             # Debug tracker is not working with 0.175 so changed to 0.2
#             # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
#             # sleep(.3)
#
#             # partially working for translate and offset,
#             # but offset is kept always in same axis, have to fix for rotation
#             # M_dyn = M_reference.I * T_stylus
#             # M_dyn[2, -1] = -M_dyn[2, -1]
#             # M_dyn_ch = M_change * M_dyn
#             # ddd = M_dyn_ch[0, -1], M_dyn_ch[1, -1], M_dyn_ch[2, -1]
#             # M_dyn_ch[:3, -1] = asmatrix(db.flip_x_m(ddd)).reshape([3, 1])
#             # M_final = S0 * M_obj_trans_0 * S0.I * M_dyn_ch
#
#             # this works for static reference object rotation
#             # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_raw.I * R_stylus * M_obj_rot_raw
#             # this works for dynamic reference in rotation but not in translation
#             # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_dyn.I * R_reference.I * R_stylus * M_obj_rot_raw
#
#             if self._pause_:
#                 return
#
#
# class CoregistrationObjectDynamic(threading.Thread):
#     """
#     Thread to update the coordinates with the fiducial points
#     co-registration method while the Navigation Button is pressed.
#     Sleep function in run method is used to avoid blocking GUI and
#     for better real-time navigation
#     """
#
#     def __init__(self, coreg_data, nav_id, trck_info, tracts_info):
#         threading.Thread.__init__(self)
#         self.coreg_data = coreg_data
#         self.nav_id = nav_id
#         self.trck_info = trck_info
#         # self.tracts_info = tracts_info
#         # self.tracts = None
#         self._pause_ = False
#         self.start()
#
#     def stop(self):
#         # self.tracts.stop()
#         self._pause_ = True
#
#     def run(self):
#
#         m_change, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = self.coreg_data
#         trck_init, trck_id, trck_mode = self.trck_info
#         # seed, tracker, affine, affine_vtk = self.tracts_info
#
#         while self.nav_id:
#             coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)
#
#             as1, bs1, gs1 = radians(coord_raw[obj_ref_mode, 3:])
#             r_probe = asmatrix(tr.euler_matrix(as1, bs1, gs1, 'rzyx'))
#             t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))
#             t_offset_aux = r_s0_raw.I * r_probe * t_obj_raw
#             t_offset = asmatrix(identity(4))
#             t_offset[:, -1] = t_offset_aux[:, -1]
#             t_probe = s0_raw * t_offset * s0_raw.I * t_probe_raw
#             m_probe = asmatrix(tr.concatenate_matrices(t_probe, r_probe))
#
#             a, b, g = radians(coord_raw[1, 3:])
#             r_ref = tr.euler_matrix(a, b, g, 'rzyx')
#             t_ref = tr.translation_matrix(coord_raw[1, :3])
#             m_ref = asmatrix(tr.concatenate_matrices(t_ref, r_ref))
#
#             m_dyn = m_ref.I * m_probe
#             m_dyn[2, -1] = -m_dyn[2, -1]
#
#             m_img = m_change * m_dyn
#             r_obj = r_obj_img * m_obj_raw.I * s0_dyn.I * m_dyn * m_obj_raw
#
#             m_img[:3, :3] = r_obj[:3, :3]
#
#             scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)
#
#             coord = m_img[0, -1], m_img[1, -1], m_img[2, -1],\
#                     degrees(angles[0]), degrees(angles[1]), degrees(angles[2])
#
#             # norm_vec = m_img[:3, 2].reshape([1, 3]).tolist()
#             # p0 = m_img[:3, -1].reshape([1, 3]).tolist()
#             # p2 = [x - 30 * y for x, y in zip(p0[0], norm_vec[0])]
#             # m_tract = m_img.copy()
#             # m_tract[:3, -1] = np.reshape(np.asarray(p2)[np.newaxis, :], [3, 1])
#
#             # pos_world_aux = np.ones([4, 1])
#             # pos_world_aux[:3, -1] = db.flip_x((p2[0], p2[1], p2[2]))[:3]
#             # pos_world = np.linalg.inv(affine) @ pos_world_aux
#             # seed_aux = pos_world.reshape([1, 4])[0, :3]
#             # seed = seed_aux[np.newaxis, :]
#
#             # self.tracts = dtr.compute_tracts(tracker, seed, affine_vtk, True)
#
#             # wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)
#             wx.CallAfter(Publisher.sendMessage, 'Update cross position', arg=m_img, position=coord)
#             wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=coord)
#
#             # TODO: Optimize the value of sleep for each tracking device.
#             #sleep(2.175)
#             sleep(0.175)
#
#             # Debug tracker is not working with 0.175 so changed to 0.2
#             # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
#             # sleep(.3)
#
#             # partially working for translate and offset,
#             # but offset is kept always in same axis, have to fix for rotation
#             # M_dyn = M_reference.I * T_stylus
#             # M_dyn[2, -1] = -M_dyn[2, -1]
#             # M_dyn_ch = M_change * M_dyn
#             # ddd = M_dyn_ch[0, -1], M_dyn_ch[1, -1], M_dyn_ch[2, -1]
#             # M_dyn_ch[:3, -1] = asmatrix(db.flip_x_m(ddd)).reshape([3, 1])
#             # M_final = S0 * M_obj_trans_0 * S0.I * M_dyn_ch
#
#             # this works for static reference object rotation
#             # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_raw.I * R_stylus * M_obj_rot_raw
#             # this works for dynamic reference in rotation but not in translation
#             # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_dyn.I * R_reference.I * R_stylus * M_obj_rot_raw
#
#             if self._pause_:
#                 return
#
#
# def corregistrate_object(inp, coord_raw):
#     m_change, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = inp
#     as1, bs1, gs1 = radians(coord_raw[obj_ref_mode, 3:])
#     r_probe = tr.euler_matrix(as1, bs1, gs1, 'rzyx')
#     t_probe_raw = tr.translation_matrix(coord_raw[obj_ref_mode, :3])
#     t_offset_aux = np.linalg.inv(r_s0_raw) @ r_probe @ t_obj_raw
#     t_offset = identity(4)
#     t_offset[:, -1] = t_offset_aux[:, -1]
#     t_probe = s0_raw @ t_offset @ np.linalg.inv(s0_raw) @ t_probe_raw
#     m_probe = tr.concatenate_matrices(t_probe, r_probe)
#
#     a, b, g = radians(coord_raw[1, 3:])
#     r_ref = tr.euler_matrix(a, b, g, 'rzyx')
#     t_ref = tr.translation_matrix(coord_raw[1, :3])
#     m_ref = tr.concatenate_matrices(t_ref, r_ref)
#
#     m_dyn = np.linalg.inv(m_ref) @ m_probe
#     m_dyn[2, -1] = -m_dyn[2, -1]
#
#     m_img = m_change @ m_dyn
#     r_obj = r_obj_img @ np.linalg.inv(m_obj_raw) @ np.linalg.inv(s0_dyn) @ m_dyn @ m_obj_raw
#
#     m_img[:3, :3] = r_obj[:3, :3]
#
#     scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)
#
#     coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
#             degrees(angles[0]), degrees(angles[1]), degrees(angles[2])
#
#     return coord, m_img

