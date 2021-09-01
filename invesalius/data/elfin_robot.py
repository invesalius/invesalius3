import numpy as np
import cv2
from time import time, sleep
import threading
import csv

import invesalius.data.elfin as elfin
import invesalius.data.transformations as tr
import invesalius.data.coregistration as dcr



class elfin_server():
    def __init__(self, server_ip, port_number):
        self.server_ip = server_ip
        self.port_number = port_number
        #print(cobot.ReadPcsActualPos())

    def Initialize(self):
        SIZE = 1024
        rbtID = 0
        self.cobot = elfin.elfin()
        self.cobot.connect(self.server_ip, self.port_number, SIZE, rbtID)
        print("conected!")

    def Run(self):
        #target = [540.0, -30.0, 850.0, 140.0, -81.0, -150.0]
        #print("starting move")
        return self.cobot.ReadPcsActualPos()

    def SendCoordinates(self, target):
        status = self.cobot.ReadMoveState()
        if status != 1009:
            self.cobot.MoveL(target)

    def SendCoordinatesArc(self, target_linear, target_arc):
        status = self.cobot.ReadMoveState()

        print(self.cobot.MoveL(target_linear))
        status = self.cobot.ReadMoveState()
        while status == 1009:
            sleep(0.5)
            print("moving...")
            print(self.cobot.ReadPcsActualPos())
            status = self.cobot.ReadMoveState()
        print("end move")

        print(self.cobot.MoveC(target_arc))
        status = self.cobot.ReadMoveState()
        while status == 1009:
            sleep(0.5)
            print("moving...")
            print(self.cobot.ReadPcsActualPos())
            status = self.cobot.ReadMoveState()
        print("end move")

    def StopRobot(self):
        self.cobot.GrpStop()
        sleep(0.1)

    def Close(self):
        self.cobot.close()

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
        coord_init = coord_vel[:int(len(coord_vel)/2)].mean(axis=0)
        coord_final = coord_vel[int(len(coord_vel)/2):].mean(axis=0)
        velocity = (coord_final - coord_init)/(timestamp[-1]-timestamp[0])
        distance = (coord_final - coord_init)

        return velocity, distance

    def Versores(self,init_point, final_point):
        init_point = np.array(init_point)
        final_point = np.array(final_point)
        norm = (sum((final_point-init_point)**2))**0.5
        versorfator = (((final_point-init_point)/norm)*70).tolist()

        return versorfator

    def arcmotion(self, actual_point, pc,coord_inv):

        p1 = coord_inv

        versorfator1_calculado = self.Versores(pc,actual_point)
        init_ext_point = actual_point[0]+versorfator1_calculado[0],\
                         actual_point[1]+versorfator1_calculado[1],\
                         actual_point[2]+versorfator1_calculado[2], \
                         actual_point[3], actual_point[4], actual_point[5]

        pm = ((p1[0]+actual_point[0])/2, (p1[1]+actual_point[1])/2,(p1[2]+actual_point[2])/2,0,0,0 ) #ponto médio da trajetória

        newarr = (np.array(self.Versores(pc,pm)))*2
        pontointermediario = pm[0]+newarr[0],pm[1]+newarr[1],pm[2]+newarr[2]

        versorfator3 = self.Versores(pc,p1)
        final_ext_point = p1[0]+versorfator3[0],p1[1]+versorfator3[1],p1[2]+versorfator3[2], coord_inv[3], coord_inv[4], coord_inv[5]
        final_ext_point_arc = final_ext_point = p1[0]+versorfator3[0],p1[1]+versorfator3[1],p1[2]+versorfator3[2], coord_inv[3], coord_inv[4], coord_inv[5],0
        #type_arc = 0
        target_arc = pontointermediario+final_ext_point_arc

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

            if self.velocity_std > 5:
                print('Velocity threshold activated')
                return False
            else:
                return True

        return False


    def head_move_compensation(self, current_ref, m_change_robot2ref):
        trans = tr.translation_matrix(current_ref[:3])
        a, b, g = np.radians(current_ref[3:6])
        rot = tr.euler_matrix(a, b, g, 'rzyx')
        M_current_ref = tr.concatenate_matrices(trans, rot)

        m_robot_new = M_current_ref @ m_change_robot2ref
        _, _, angles, translate, _ = tr.decompose_matrix(m_robot_new)
        angles = np.degrees(angles)

        return m_robot_new[0, -1], m_robot_new[1, -1], m_robot_new[2, -1], angles[0], angles[1], \
                    angles[2]

    def estimate_head_center(self, tracker, current_ref):
        m_probe_ref_left, m_probe_ref_right, m_probe_ref_nasion = tracker.GetMatrixTrackerFiducials()
        m_current_ref = dcr.compute_marker_transformation(np.array([current_ref]), 0)

        m_ear_left_new = m_current_ref @ m_probe_ref_left
        m_ear_right_new = m_current_ref @ m_probe_ref_right

        return (m_ear_left_new[:3, -1] + m_ear_right_new[:3, -1])/2

    def correction_distance_calculation_target(self, coord_inv,actual_point):
        #a posição atual do robo está embaixo disso
        sum = (coord_inv[0]-actual_point[0])**2\
              +(coord_inv[1]-actual_point[1])**2\
              +(coord_inv[2]-actual_point[2])**2
        correction_distance_compensation = pow(sum,0.5)

        return correction_distance_compensation


class RobotCoordinates():
    def __init__(self):
        self.coord = None

    def GetRobotCoordinates(self):
        return self.coord

class ControlRobot(threading.Thread):
    def __init__(self, trck_init, tracker, robotcoordinates, queues, process_tracker, event):
        threading.Thread.__init__(self, name='ControlRobot')

        self.trck_init_robot = trck_init[1][0]
        self.trck_init_tracker = trck_init[0]
        self.trk_id = trck_init[2]
        self.tracker = tracker
        self.robotcoordinates = robotcoordinates
        self.robot_tracker_flag = False
        self.objattarget_flag = False
        self.target_flag = False
        self.m_change_robot2ref = None
        self.coord_inv_old = None
        self.coord_queue = queues[0]
        self.robottarget_queue = queues[1]
        self.objattarget_queue = queues[2]
        self.process_tracker = process_tracker
        self.event = event
        self.time_start = time()
        self.fieldnames = ["time",
                           "x_robot", "y_robot", "z_robot", "a_robot", "b_robot", "c_robot",
                           "x_tracker_obj", "y_tracker_obj", "z_tracker_obj", "a_tracker_obj", "b_tracker_obj", "c_tracker_obj",
                           "velocity_std", "target"]
        with open('data_robot_and_tracker.csv', 'w', newline='') as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=self.fieldnames)
            csv_writer.writeheader()

    def getcoordsfromdevices(self):
        coord_robot_raw = self.trck_init_robot.Run()
        coord_robot = np.array(coord_robot_raw)
        coord_robot[3], coord_robot[5] = coord_robot[5], coord_robot[3]
        self.robotcoordinates.coord = coord_robot

        coord_raw, markers_flag = self.tracker.TrackerCoordinates.GetCoordinates()

        return coord_raw, coord_robot_raw, markers_flag

    def control(self, coords_tracker_in_robot, coord_robot_raw, markers_flag):
        coord_ref_tracker_in_robot = coords_tracker_in_robot[1]
        coord_obj_tracker_in_robot = coords_tracker_in_robot[2]

        if self.robot_tracker_flag:
            current_ref = coord_ref_tracker_in_robot
            if current_ref is not None and markers_flag[1]:
                current_ref_filtered = self.process_tracker.kalman_filter(current_ref)
                if self.process_tracker.head_move_threshold(current_ref_filtered):
                    coord_inv = self.process_tracker.head_move_compensation(current_ref_filtered,
                                                                            self.m_change_robot2ref)
                    if self.coord_inv_old is None:
                        self.coord_inv_old = coord_inv

                    if np.allclose(np.array(coord_inv), np.array(coord_robot_raw), 0, 0.01):
                        # print("At target within range 5")
                        pass
                    elif not np.allclose(np.array(coord_inv), np.array(self.coord_inv_old), 0, 5):
                        # print("stop")
                        self.trck_init_robot.StopRobot()
                        self.coord_inv_old = coord_inv
                    else:
                        #print(self.process_tracker.estimate_head_center(self.tracker, current_ref_filtered))
                        if self.process_tracker.correction_distance_calculation_target(coord_inv,coord_robot_raw) < 100:
                            self.trck_init_robot.SendCoordinates(coord_inv)

                        elif self.process_tracker.correction_distance_calculation_target(coord_inv,coord_robot_raw) >= 100:
                            actual_point = coord_robot_raw

                            pc = 756,-90,188, coord_inv[3], coord_inv[4], coord_inv[5]

                            self.trck_init_robot.StopRobot()
                            target_linear, target_arc = self.process_tracker.arcmotion(coord_robot_raw, pc, coord_inv)
                            self.trck_init_robot.SendCoordinatesArc(target_linear, target_arc)
                            self.trck_init_robot.StopRobot()
                            self.trck_init_robot.SendCoordinates(coord_inv)
                            sleep(10)
                        self.coord_inv_old = coord_inv
            else:
                self.trck_init_robot.StopRobot()

    def run(self):

        while not self.event.is_set():
            coords_tracker_in_robot, coord_robot_raw, markers_flag = self.getcoordsfromdevices()

            if self.robottarget_queue.empty():
                None
            else:
                self.robot_tracker_flag, self.m_change_robot2ref = self.robottarget_queue.get_nowait()
                self.robottarget_queue.task_done()

            if self.objattarget_queue.empty():
                None
            else:
                self.target_flag = self.objattarget_queue.get_nowait()
                self.objattarget_queue.task_done()

            self.control(coords_tracker_in_robot, coord_robot_raw, markers_flag)

            # if not self.robottarget_queue.empty():
            #     self.robottarget_queue.task_done()
            # if not self.objattarget_queue.empty():
            #     self.objattarget_queue.task_done()


            with open('data_robot_and_tracker.csv', 'a', newline='') as csv_file:
                csv_writer = csv.DictWriter(csv_file, fieldnames=self.fieldnames)

                info = {
                    "time": time() - self.time_start,
                    "x_robot": coord_robot_raw[0],
                    "y_robot": coord_robot_raw[1],
                    "z_robot": coord_robot_raw[2],
                    "a_robot": coord_robot_raw[3],
                    "b_robot": coord_robot_raw[4],
                    "c_robot": coord_robot_raw[5],
                    "x_tracker_obj": coords_tracker_in_robot[2][0],
                    "y_tracker_obj": coords_tracker_in_robot[2][1],
                    "z_tracker_obj": coords_tracker_in_robot[2][2],
                    "a_tracker_obj": coords_tracker_in_robot[2][3],
                    "b_tracker_obj": coords_tracker_in_robot[2][4],
                    "c_tracker_obj": coords_tracker_in_robot[2][5],
                    "velocity_std": self.process_tracker.velocity_std,
                    "target": self.target_flag
                }

                csv_writer.writerow(info)

            sleep(0.01)