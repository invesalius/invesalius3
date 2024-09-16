import queue
import threading
import time

import numpy as np
from vtkmodules.vtkCommonCore import vtkIdList


def Get_coil_position(m_img):
    # coil position cp : the center point at the bottom of the coil casing,
    # corresponds to the origin of the coil template.
    # coil normal cn: outer normal of the coil, i.e. away from the head
    # coil tangent 1 ct1: long axis
    # coil tangent 2 ct2: short axis ~ direction of primary E under the coil
    # % rotation matrix for the coil coordinates
    # T = [ct1;ct2;cn];

    m_img_flip = m_img.copy()
    m_img_flip[1, -1] = -m_img_flip[1, -1]
    cp = m_img_flip[:-1, -1]  # coil center
    cp = cp * 0.001  # convert to meters
    cp = cp.tolist()

    ct1 = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
    ct2 = m_img_flip[:3, 0]  # is from left to right direction of the coil
    coil_dir = m_img_flip[:-1, 0]
    coil_face = m_img_flip[:-1, 1]
    cn = np.cross(coil_dir, coil_face)
    T_rot = np.append(ct1, ct2, axis=0)
    T_rot = np.append(T_rot, cn, axis=0)  # append
    T_rot = T_rot.tolist()  # to list

    return [T_rot, cp]


class Visualize_E_field_Thread(threading.Thread):
    def __init__(self, queues, event, sle, neuronavigation_api, debug_efield_enorm, plot_vectors):
        threading.Thread.__init__(self, name="Visualize_E_field_Thread")
        # self.inp = inp #list of inputs
        self.efield_queue = queues[0]
        self.e_field_norms_queue = queues[1]
        self.e_field_IDs_queue = queues[2]
        # self.tracts_queue = queues[1]
        # self.visualization_queue = visualization_queue
        self.event = event
        self.sle = sle
        self.neuronavigation_api = neuronavigation_api
        self.ID_list = vtkIdList()
        self.coord_old = []
        if isinstance(debug_efield_enorm, np.ndarray):
            self.enorm_debug = debug_efield_enorm
            self.debug = True
        else:
            self.debug = False
        self.plot_vectors = plot_vectors

    def run(self):
        while not self.event.is_set():
            if not self.e_field_IDs_queue.empty():
                try:
                    self.ID_list = self.e_field_IDs_queue.get_nowait()
                    self.e_field_IDs_queue.task_done()
                    id_list = []
                    for h in range(self.ID_list.GetNumberOfIds()):
                        id_list.append(self.ID_list.GetId(h))
                except queue.Full:
                    self.e_field_IDs_queue.task_done()

                if not self.efield_queue.empty():
                    try:
                        [m_img, coord] = self.efield_queue.get_nowait()
                        self.efield_queue.task_done()
                    except queue.Full:
                        self.efield_queue.task_done()

                    if self.ID_list.GetNumberOfIds() != 0:
                        if np.all(self.coord_old != coord):
                            [T_rot, cp] = Get_coil_position(m_img)
                            if self.debug:
                                enorm = self.enorm_debug
                            else:
                                if self.plot_vectors:
                                    enorm = self.neuronavigation_api.update_efield_vectorROIMax(
                                        position=cp,
                                        orientation=coord[3:],
                                        T_rot=T_rot,
                                        id_list=id_list,
                                    )
                                else:
                                    enorm = self.neuronavigation_api.update_efield(
                                        position=cp, orientation=coord[3:], T_rot=T_rot
                                    )
                            try:
                                self.e_field_norms_queue.put_nowait(
                                    [T_rot, cp, coord, enorm, id_list]
                                )

                            except queue.Full:
                                pass

                            self.coord_old = coord

            time.sleep(self.sle)
