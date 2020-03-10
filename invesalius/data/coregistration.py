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

import threading
from time import sleep

from numpy import asmatrix, mat, degrees, radians, identity
import wx
from wx.lib.pubsub import pub as Publisher
import numpy as np

import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr
import invesalius.data.bases as bases

# TODO: Optimize navigation thread. Remove the infinite loop and optimize sleep.


class CoregistrationStatic(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, coreg_data, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.coreg_data = coreg_data
        self.nav_id = nav_id
        self.trck_info = trck_info
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):
        # m_change = self.coreg_data[0]
        # obj_ref_mode = self.coreg_data[2]
        #
        # trck_init = self.trck_info[0]
        # trck_id = self.trck_info[1]
        # trck_mode = self.trck_info[2]

        m_change, obj_ref_mode = self.coreg_data
        trck_init, trck_id, trck_mode = self.trck_info

        while self.nav_id:
            coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)

            psi, theta, phi = coord_raw[obj_ref_mode, 3:]
            t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))

            t_probe_raw[2, -1] = -t_probe_raw[2, -1]

            m_img = m_change * t_probe_raw

            coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], psi, theta, phi

            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)

            # TODO: Optimize the value of sleep for each tracking device.
            sleep(0.175)

            if self._pause_:
                return


class CoregistrationDynamic(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, coreg_data, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.__bind_events()
        self.coreg_data = coreg_data
        self.nav_id = nav_id
        self.trck_info = trck_info
        self.m_icp = None
        self.icp = False
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def __bind_events(self):
        Publisher.subscribe(self.UpdateICP, 'Update ICP matrix')

    def UpdateICP(self, m_icp, flag):
        self.m_icp = m_icp
        self.icp = flag

    def run(self):
        m_change, obj_ref_mode = self.coreg_data
        trck_init, trck_id, trck_mode = self.trck_info

        while self.nav_id:
            coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)

            psi, theta, phi = radians(coord_raw[obj_ref_mode, 3:])
            r_probe = tr.euler_matrix(psi, theta, phi, 'rzyx')
            t_probe = tr.translation_matrix(coord_raw[obj_ref_mode, :3])
            m_probe = asmatrix(tr.concatenate_matrices(t_probe, r_probe))

            psi_ref, theta_ref, phi_ref = radians(coord_raw[1, 3:])
            r_ref = tr.euler_matrix(psi_ref, theta_ref, phi_ref, 'rzyx')
            t_ref = tr.translation_matrix(coord_raw[1, :3])
            m_ref = asmatrix(tr.concatenate_matrices(t_ref, r_ref))

            m_dyn = m_ref.I * m_probe
            m_dyn[2, -1] = -m_dyn[2, -1]

            #a multiplicacao nao pode ser direta m_icp * m_change * m_dyn, deve ser feita separadamente  m_icp * (m_change * m_dyn)
            m_img = m_change * m_dyn
            if self.icp:
                flip = m_img[0, -1], m_img[1, -1], m_img[2, -1]
                m_img[0, -1], m_img[1, -1], m_img[2, -1] = bases.flip_x(flip)
                coord_img = np.transpose(np.array([m_img[0, -1], m_img[1, -1], m_img[2, -1], m_img[3, -1]]))
                m_img[0, -1], m_img[1, -1], m_img[2, -1], _ = self.m_icp @ coord_img
                m_img[1, -1] = -m_img[1, -1]

            scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)

            coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
                    degrees(angles[0]), degrees(angles[1]), degrees(angles[2])

            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)

            # TODO: Optimize the value of sleep for each tracking device.
            sleep(0.175)

            if self._pause_:
                return


class CoregistrationDynamic_old(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, bases, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.bases = bases
        self.nav_id = nav_id
        self.trck_info = trck_info
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):
        m_inv = self.bases[0]
        n = self.bases[1]
        q1 = self.bases[2]
        q2 = self.bases[3]
        trck_init = self.trck_info[0]
        trck_id = self.trck_info[1]
        trck_mode = self.trck_info[2]

        while self.nav_id:
            # trck_coord, probe, reference = dco.GetCoordinates(trck_init, trck_id, trck_mode)
            coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)

            trck_coord = dco.dynamic_reference(coord_raw[0, :], coord_raw[1, :])

            trck_xyz = mat([[trck_coord[0]], [trck_coord[1]], [trck_coord[2]]])
            img = q1 + (m_inv * n) * (trck_xyz - q2)

            coord = (float(img[0]), float(img[1]), float(img[2]), trck_coord[3],
                     trck_coord[4], trck_coord[5])
            angles = coord_raw[0, 3:6]

            # Tried several combinations and different locations to send the messages,
            # however only this one does not block the GUI during navigation.
            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=None, position=coord)
            wx.CallAfter(Publisher.sendMessage, 'Set camera in volume', coord)
            wx.CallAfter(Publisher.sendMessage, 'Update tracker angles', angles)

            # TODO: Optimize the value of sleep for each tracking device.
            # Debug tracker is not working with 0.175 so changed to 0.2
            # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
            # sleep(.3)
            sleep(0.175)

            if self._pause_:
                return


class CoregistrationObjectStatic(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, coreg_data, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.coreg_data = coreg_data
        self.nav_id = nav_id
        self.trck_info = trck_info
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):
        # m_change = self.coreg_data[0]
        # t_obj_raw = self.coreg_data[1]
        # s0_raw = self.coreg_data[2]
        # r_s0_raw = self.coreg_data[3]
        # s0_dyn = self.coreg_data[4]
        # m_obj_raw = self.coreg_data[5]
        # r_obj_img = self.coreg_data[6]
        # obj_ref_mode = self.coreg_data[7]
        #
        # trck_init = self.trck_info[0]
        # trck_id = self.trck_info[1]
        # trck_mode = self.trck_info[2]

        m_change, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = self.coreg_data
        trck_init, trck_id, trck_mode = self.trck_info

        while self.nav_id:
            coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)

            as1, bs1, gs1 = radians(coord_raw[obj_ref_mode, 3:])
            r_probe = asmatrix(tr.euler_matrix(as1, bs1, gs1, 'rzyx'))
            t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))
            t_offset_aux = r_s0_raw.I * r_probe * t_obj_raw
            t_offset = asmatrix(identity(4))
            t_offset[:, -1] = t_offset_aux[:, -1]
            t_probe = s0_raw * t_offset * s0_raw.I * t_probe_raw
            m_probe = asmatrix(tr.concatenate_matrices(t_probe, r_probe))

            m_probe[2, -1] = -m_probe[2, -1]

            m_img = m_change * m_probe
            r_obj = r_obj_img * m_obj_raw.I * s0_dyn.I * m_probe * m_obj_raw

            m_img[:3, :3] = r_obj[:3, :3]

            scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)

            coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], \
                    degrees(angles[0]), degrees(angles[1]), degrees(angles[2])

            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)
            wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=coord)

            # TODO: Optimize the value of sleep for each tracking device.
            sleep(0.175)

            # Debug tracker is not working with 0.175 so changed to 0.2
            # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
            # sleep(.3)

            # partially working for translate and offset,
            # but offset is kept always in same axis, have to fix for rotation
            # M_dyn = M_reference.I * T_stylus
            # M_dyn[2, -1] = -M_dyn[2, -1]
            # M_dyn_ch = M_change * M_dyn
            # ddd = M_dyn_ch[0, -1], M_dyn_ch[1, -1], M_dyn_ch[2, -1]
            # M_dyn_ch[:3, -1] = asmatrix(db.flip_x_m(ddd)).reshape([3, 1])
            # M_final = S0 * M_obj_trans_0 * S0.I * M_dyn_ch

            # this works for static reference object rotation
            # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_raw.I * R_stylus * M_obj_rot_raw
            # this works for dynamic reference in rotation but not in translation
            # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_dyn.I * R_reference.I * R_stylus * M_obj_rot_raw

            if self._pause_:
                return


class CoregistrationObjectDynamic(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, coreg_data, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.coreg_data = coreg_data
        self.nav_id = nav_id
        self.trck_info = trck_info
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):

        m_change, obj_ref_mode, t_obj_raw, s0_raw, r_s0_raw, s0_dyn, m_obj_raw, r_obj_img = self.coreg_data
        trck_init, trck_id, trck_mode = self.trck_info

        while self.nav_id:
            coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)

            as1, bs1, gs1 = radians(coord_raw[obj_ref_mode, 3:])
            r_probe = asmatrix(tr.euler_matrix(as1, bs1, gs1, 'rzyx'))
            t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))
            t_offset_aux = r_s0_raw.I * r_probe * t_obj_raw
            t_offset = asmatrix(identity(4))
            t_offset[:, -1] = t_offset_aux[:, -1]
            t_probe = s0_raw * t_offset * s0_raw.I * t_probe_raw
            m_probe = asmatrix(tr.concatenate_matrices(t_probe, r_probe))

            a, b, g = radians(coord_raw[1, 3:])
            r_ref = tr.euler_matrix(a, b, g, 'rzyx')
            t_ref = tr.translation_matrix(coord_raw[1, :3])
            m_ref = asmatrix(tr.concatenate_matrices(t_ref, r_ref))

            m_dyn = m_ref.I * m_probe
            m_dyn[2, -1] = -m_dyn[2, -1]

            m_img = m_change * m_dyn
            r_obj = r_obj_img * m_obj_raw.I * s0_dyn.I * m_dyn * m_obj_raw

            m_img[:3, :3] = r_obj[:3, :3]

            scale, shear, angles, trans, persp = tr.decompose_matrix(m_img)

            coord = m_img[0, -1], m_img[1, -1], m_img[2, -1],\
                    degrees(angles[0]), degrees(angles[1]), degrees(angles[2])

            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)
            wx.CallAfter(Publisher.sendMessage, 'Update object matrix', m_img=m_img, coord=coord)

            # TODO: Optimize the value of sleep for each tracking device.
            sleep(0.175)

            # Debug tracker is not working with 0.175 so changed to 0.2
            # However, 0.2 is too low update frequency ~5 Hz. Need optimization URGENTLY.
            # sleep(.3)

            # partially working for translate and offset,
            # but offset is kept always in same axis, have to fix for rotation
            # M_dyn = M_reference.I * T_stylus
            # M_dyn[2, -1] = -M_dyn[2, -1]
            # M_dyn_ch = M_change * M_dyn
            # ddd = M_dyn_ch[0, -1], M_dyn_ch[1, -1], M_dyn_ch[2, -1]
            # M_dyn_ch[:3, -1] = asmatrix(db.flip_x_m(ddd)).reshape([3, 1])
            # M_final = S0 * M_obj_trans_0 * S0.I * M_dyn_ch

            # this works for static reference object rotation
            # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_raw.I * R_stylus * M_obj_rot_raw
            # this works for dynamic reference in rotation but not in translation
            # R_dyn = M_vtk * M_obj_rot_raw.I * S0_rot_dyn.I * R_reference.I * R_stylus * M_obj_rot_raw

            if self._pause_:
                return
