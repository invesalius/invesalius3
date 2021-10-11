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
import cv2
from time import time

import invesalius.data.transformations as tr
import invesalius.data.coregistration as dcr
import invesalius.constants as const


class KalmanTracker:
    def __init__(self,
                 state_num=2,
                 cov_process=0.001,
                 cov_measure=0.1):

        self.state_num = state_num
        measure_num = 1

        # The filter itself.
        self.filter = cv2.KalmanFilter(state_num, measure_num, 0)

        self.state = np.zeros((state_num, 1), dtype=np.float32)
        self.measurement = np.array((measure_num, 1), np.float32)
        self.prediction = np.zeros((state_num, 1), np.float32)


        self.filter.transitionMatrix = np.array([[1, 1],
                                                 [0, 1]], np.float32)
        self.filter.measurementMatrix = np.array([[1, 1]], np.float32)
        self.filter.processNoiseCov = np.array([[1, 0],
                                                [0, 1]], np.float32) * cov_process
        self.filter.measurementNoiseCov = np.array( [[1]], np.float32) * cov_measure

    def update_kalman(self, measurement):
        self.prediction = self.filter.predict()
        self.measurement = np.array([[np.float32(measurement[0])]])

        self.filter.correct(self.measurement)
        self.state = self.filter.statePost


class TrackerProcessing:
    def __init__(self):
        self.coord_vel = []
        self.timestamp = []
        self.velocity_vector = []
        self.kalman_coord_vector = []
        self.velocity_std = 0

        self.tracker_stabilizers = [KalmanTracker(
            state_num=2,
            cov_process=0.001,
            cov_measure=0.1) for _ in range(6)]

    def kalman_filter(self, coord_tracker):
        kalman_array = []
        pose_np = np.array((coord_tracker[:3], coord_tracker[3:])).flatten()
        for value, ps_stb in zip(pose_np, self.tracker_stabilizers):
            ps_stb.update_kalman([value])
            kalman_array.append(ps_stb.state[0])
        coord_kalman = np.hstack(kalman_array)

        self.kalman_coord_vector.append(coord_kalman[:3])
        if len(self.kalman_coord_vector) < 20: #avoid initial fluctuations
            coord_kalman = coord_tracker
            print('initializing filter')
        else:
            del self.kalman_coord_vector[0]

        return coord_kalman

    def estimate_head_velocity(self, coord_vel, timestamp):
        coord_vel = np.vstack(np.array(coord_vel))
        coord_init = coord_vel[:int(len(coord_vel) / 2)].mean(axis=0)
        coord_final = coord_vel[int(len(coord_vel) / 2):].mean(axis=0)
        velocity = (coord_final - coord_init)/(timestamp[-1] - timestamp[0])
        distance = (coord_final - coord_init)

        return velocity, distance

    def versors(self, init_point, final_point):
        init_point = np.array(init_point)
        final_point = np.array(final_point)
        norm = (sum((final_point - init_point) ** 2)) ** 0.5
        versorfactor = (((final_point-init_point) / norm) * const.ROBOT_VERSOR_SCALE_FACTOR).tolist()

        return versorfactor

    def compute_arc_motion(self, actual_point, coord_head, coord_inv):
        p1 = coord_inv

        pc = coord_head[0], coord_head[1], coord_head[2], coord_inv[3], coord_inv[4], coord_inv[5]

        versorfactor1 = self.versors(pc, actual_point)
        init_ext_point = actual_point[0] + versorfactor1[0], \
                         actual_point[1] + versorfactor1[1], \
                         actual_point[2] + versorfactor1[2], \
                         actual_point[3], actual_point[4], actual_point[5]

        middle_point = ((p1[0] + actual_point[0]) / 2,
                        (p1[1] + actual_point[1]) / 2,
                        (p1[2] + actual_point[2]) / 2,
                        0, 0, 0)

        newarr = (np.array(self.versors(pc, middle_point))) * 2
        middle_arc_point = middle_point[0] + newarr[0], \
                           middle_point[1] + newarr[1], \
                           middle_point[2] + newarr[2]

        versorfactor3 = self.versors(pc, p1)

        final_ext_arc_point = p1[0] + versorfactor3[0], \
                              p1[1] + versorfactor3[1], \
                              p1[2] + versorfactor3[2], \
                              coord_inv[3], coord_inv[4], coord_inv[5], 0

        target_arc = middle_arc_point + final_ext_arc_point

        return init_ext_point, target_arc

    def head_move_threshold(self, current_ref):
        self.coord_vel.append(current_ref)
        self.timestamp.append(time())
        if len(self.coord_vel) >= 10:
            head_velocity, head_distance = self.estimate_head_velocity(self.coord_vel, self.timestamp)
            self.velocity_vector.append(head_velocity)

            del self.coord_vel[0]
            del self.timestamp[0]

            if len(self.velocity_vector) >= 30:
                self.velocity_std = np.std(self.velocity_vector)
                del self.velocity_vector[0]

            if self.velocity_std > const.ROBOT_HEAD_VELOCITY_THRESHOLD:
                print('Velocity threshold activated')
                return False
            else:
                return True

        return False

    def head_move_compensation(self, current_ref, m_change_robot_to_head):
        trans = tr.translation_matrix(current_ref[:3])
        a, b, g = np.radians(current_ref[3:6])
        rot = tr.euler_matrix(a, b, g, 'rzyx')
        M_current_ref = tr.concatenate_matrices(trans, rot)

        m_robot_new = M_current_ref @ m_change_robot_to_head
        _, _, angles, translate, _ = tr.decompose_matrix(m_robot_new)
        angles = np.degrees(angles)

        return m_robot_new[0, -1], m_robot_new[1, -1], m_robot_new[2, -1], angles[0], angles[1], angles[2]

    def estimate_head_center(self, tracker, current_ref):
        m_probe_ref_left, m_probe_ref_right, m_probe_ref_nasion = tracker.GetMatrixTrackerFiducials()
        m_current_ref = dcr.compute_marker_transformation(np.array([current_ref]), 0)

        m_ear_left_new = m_current_ref @ m_probe_ref_left
        m_ear_right_new = m_current_ref @ m_probe_ref_right

        return (m_ear_left_new[:3, -1] + m_ear_right_new[:3, -1])/2

    def correction_distance_calculation_target(self, coord_inv, actual_point):
        sum = (coord_inv[0]-actual_point[0]) ** 2\
              + (coord_inv[1]-actual_point[1]) ** 2\
              + (coord_inv[2]-actual_point[2]) ** 2
        correction_distance_compensation = pow(sum, 0.5)

        return correction_distance_compensation


