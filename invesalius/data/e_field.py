import queue
import threading
import time

import numpy as np


def Get_coil_position( m_img_flip):
    # coil position cp : the center point at the bottom of the coil casing,
    # corresponds to the origin of the coil template.
    # coil normal cn: outer normal of the coil, i.e. away from the head
    # coil tangent 1 ct1: long axis
    # coil tangent 2 ct2: short axis ~ direction of primary E under the coil
    # % rotation matrix for the coil coordinates
    # T = [ct1;ct2;cn];

    #m_img_flip = m_img.copy()
    #m_img_flip[1, -1] = -m_img_flip[1, -1]
    cp = m_img_flip[:-1, -1]  # coil center
    cp = cp * 0.001  # convert to meters
    cp = cp.tolist()

    ct1 = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
    ct2 = m_img_flip[:3, 0]  # is from left to right direction of the coil
    coil_dir = m_img_flip[:-1, 0]
    coil_face = m_img_flip[:-1, 1]
    cn = np.cross(coil_dir, coil_face)
    T_rot = np.append(ct1, ct2, axis=0)
    T_rot = np.append(T_rot, cn, axis=0) * 0.001  # append and convert to meters
    T_rot = T_rot.tolist()  # to list

    return [T_rot,cp]

class Visualize_E_field_Thread(threading.Thread):
    # TODO: Remove this class and create a case where no ACT is provided in the class ComputeTractsACTThread

    def __init__(self, queues, event, sle, neuronavigation_api):


        threading.Thread.__init__(self, name='Visualize_E_field_Thread')
        #self.inp = inp #list of inputs
        # self.coord_queue = coord_queue
        self.efield_queue = queues[0]
        self.e_field_norms = queues[1]
        #self.tracts_queue = queues[1]
        # self.visualization_queue = visualization_queue
        self.event = event
        self.sle = sle
        self.neuronavigation_api = neuronavigation_api

    def run(self):


        while not self.event.is_set():
            try:
                coord = [] # Rembmer to remove coord
                m_img_flip = self.efield_queue.get_nowait()
                [T_rot,cp] = Get_coil_position(m_img_flip)
                enorm = self.neuronavigation_api.update_efield(position=cp, orientation=coord, T_rot=T_rot)
                self.e_field_norms.put_nowait((enorm))
                self.efield_queue.task_done()
                time.sleep(self.sle)
            # if no coordinates pass
            except queue.Empty:
                # print("Empty queue in tractography")
                pass
            # if queue is full mark as done (may not be needed in this new "nowait" method)
            except queue.Full:
                # self.coord_queue.task_done()
                self.self.efield_queue.task_done()

