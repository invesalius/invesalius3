import cv2
import cv2.aruco as aruco
import dlib
import numpy as np
from imutils import face_utils


class camera():
    def __init__(self):
        self.face_landmark_path = 'D:\\Repository\\camera_tracking\\Projeto_opencv_face_tracker\\shape_predictor_68_face_landmarks.dat'

        K = [6.5308391993466671e+002, 0.0, 3.1950000000000000e+002,
             0.0, 6.5308391993466671e+002, 2.3950000000000000e+002,
             0.0, 0.0, 1.0]
        #K = [1.74033827e+03, 0.00000000e+00, 5.83808276e+02,
        # 0.00000000e+00, 2.12379163e+03, 4.64720236e+02,
        # 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]
        D = [7.0834633684407095e-002, 6.9140193737175351e-002, 0.0, 0.0, -1.3073460323689292e+000]
        #D = [-8.09614536e-03,  4.66000740e+00, -1.81727801e-02, -4.32406078e-03,  -2.42935822e+02]

        self.cam_matrix = np.array(K).reshape(3, 3).astype(np.float32)
        self.dist_coeffs = np.array(D).reshape(5, 1).astype(np.float32)

        self.object_pts = np.float32([[6.825897, 6.760612, 4.402142],
                                 [1.330353, 7.122144, 6.903745],
                                 [-1.330353, 7.122144, 6.903745],
                                 [-6.825897, 6.760612, 4.402142],
                                 [5.311432, 5.485328, 3.987654],
                                 [1.789930, 5.393625, 4.413414],
                                 [-1.789930, 5.393625, 4.413414],
                                 [-5.311432, 5.485328, 3.987654],
                                 [2.005628, 1.409845, 6.165652],
                                 [-2.005628, 1.409845, 6.165652],
                                 [2.774015, -2.080775, 5.048531],
                                 [-2.774015, -2.080775, 5.048531],
                                 [0.000000, -3.116408, 6.097667],
                                 [0.000000, -7.415691, 4.070434]])

        self.reprojectsrc = np.float32([[10.0, 10.0, 10.0],
                                   [10.0, 10.0, -10.0],
                                   [10.0, -10.0, -10.0],
                                   [10.0, -10.0, 10.0],
                                   [-10.0, 10.0, 10.0],
                                   [-10.0, 10.0, -10.0],
                                   [-10.0, -10.0, -10.0],
                                   [-10.0, -10.0, 10.0]])

        self.line_pairs = [[0, 1], [1, 2], [2, 3], [3, 0],
                      [4, 5], [5, 6], [6, 7], [7, 4],
                      [0, 4], [1, 5], [2, 6], [3, 7]]

    def Initialize(self):

        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            print("Unable to connect to camera.")
            return
        self.detector = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor(self.face_landmark_path)

        self.ref = np.zeros(6)
        self.probe = np.zeros(6)
        self.cap.read()

        print("Initialization OK");


    def Run(self):
        ret, frame = self.cap.read()

        if ret:
            face_rects = self.detector(frame, 0)

            # operations on the frame come here
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            aruco_dict = aruco.Dictionary_get(aruco.DICT_6X6_250)
            parameters = aruco.DetectorParameters_create()

            # lists of ids and the corners beloning to each id
            corners, ids, rejectedImgPoints = aruco.detectMarkers(gray, aruco_dict, parameters=parameters)

            if len(face_rects) > 0:
                shape = self.predictor(frame, face_rects[0])
                shape = face_utils.shape_to_np(shape)

                _, euler_angle, translation_vec = self.get_head_pose(shape)
                angles = np.array([euler_angle[2], euler_angle[1], euler_angle[0]])
                self.ref = np.hstack([-10*translation_vec[:, 0], angles[:, 0]])

                ref_id = 1
            else:
                ref_id = 0

            if np.all(ids != None):
                # 0.05 = 5cm do marcador
                rvec, tvec, _ = aruco.estimatePoseSingleMarkers(corners[0], 0.05, self.cam_matrix,
                                                                self.dist_coeffs)  # Estimate pose of each marker and return the values rvet and tvec---different from camera coefficients

                # calc euler angle
                rotation_mat, _ = cv2.Rodrigues(rvec)
                pose_mat = cv2.hconcat((rotation_mat, np.transpose(tvec[0, 0])))
                _, _, _, _, _, _, euler_angle = cv2.decomposeProjectionMatrix(pose_mat)
                angles = np.array([euler_angle[2], euler_angle[1], euler_angle[0]])
                self.probe = np.hstack([1000*tvec[0,0,:], angles[:, 0]])
                probe_id = 1
            else:
                probe_id = 0

        return np.vstack([self.probe, self.ref]), probe_id, ref_id

    def Close(self):
        self.cap.release()

    def get_head_pose(self, shape):
        image_pts = np.float32([shape[17], shape[21], shape[22], shape[26], shape[36],
                                shape[39], shape[42], shape[45], shape[31], shape[35],
                                shape[48], shape[54], shape[57], shape[8]])

        _, rotation_vec, translation_vec = cv2.solvePnP(self.object_pts, image_pts, self.cam_matrix, self.dist_coeffs)

        reprojectdst, _ = cv2.projectPoints(self.reprojectsrc, rotation_vec, translation_vec,self.cam_matrix,
                                            self.dist_coeffs)

        reprojectdst = tuple(map(tuple, reprojectdst.reshape(8, 2)))

        # calc euler angle
        rotation_mat, _ = cv2.Rodrigues(rotation_vec)
        pose_mat = cv2.hconcat((rotation_mat, translation_vec))
        _, _, _, _, _, _, euler_angle = cv2.decomposeProjectionMatrix(pose_mat)

        return reprojectdst, euler_angle, translation_vec


