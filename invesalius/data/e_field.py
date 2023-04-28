import queue
import threading
import time
from typing import Any, List, Union





import numpy as np
from vtkmodules.vtkCommonCore import vtkIdList


def Get_coil_position(m_img: np.ndarray) -> list:
    # coil position cp : the center point at the bottom of the coil casing,
    # corresponds to the origin of the coil template.
    # coil normal cn: outer normal of the coil, i.e. away from the head
    # coil tangent 1 ct1: long axis
    # coil tangent 2 ct2: short axis ~ direction of primary E under the coil
    # % rotation matrix for the coil coordinates
    # T = [ct1;ct2;cn];

    m_img_flip: np.ndarray = m_img.copy()
    m_img_flip[1, -1] = -m_img_flip[1, -1]
    cp: list = m_img_flip[:-1, -1].tolist()  # coil center
    cp = [x * 0.001 for x in cp]  # convert to meters

    ct1: np.ndarray = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
    ct2: np.ndarray = m_img_flip[:3, 0]  # is from left to right direction of the coil
    coil_dir: np.ndarray = m_img_flip[:-1, 0]
    coil_face: np.ndarray = m_img_flip[:-1, 1]
    cn: np.ndarray = np.cross(coil_dir, coil_face)
    T_rot: np.ndarray = np.append(ct1, ct2, axis=0)
    T_rot = np.append(T_rot, cn, axis=0) * 0.001  # append and convert to meters
    T_rot = T_rot.tolist()  # to list

    return [T_rot, cp]



class Visualize_E_field_Thread(threading.Thread):
    def __init__(self, queues: List[queue.Queue], event: threading.Event, sle: float, neuronavigation_api: Any, debug_efield_enorm: Union[np.ndarray, None]) -> None:
        threading.Thread.__init__(self, name='Visualize_E_field_Thread')
        #self.inp = inp #list of inputs
        self.efield_queue: queue.Queue = queues[0]
        self.e_field_norms_queue: queue.Queue = queues[1]
        self.e_field_IDs_queue: queue.Queue = queues[2]
        #self.tracts_queue = queues[1]
        # self.visualization_queue = visualization_queue
        self.event: threading.Event = event
        self.sle: float = sle
        self.neuronavigation_api: Any = neuronavigation_api
        self.ID_list: vtkIdList = vtkIdList()
        self.coord_old: List[float] = []
        if isinstance(debug_efield_enorm, np.ndarray):
            self.enorm_debug: np.ndarray = debug_efield_enorm
            self.debug: bool = True
        else:
            self.debug: bool = False

    def run(self) -> None:
        while not self.event.is_set():

            if not self.e_field_IDs_queue.empty():
                try:
                    self.ID_list = self.e_field_IDs_queue.get_nowait()
                    self.e_field_IDs_queue.task_done()
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
                                enorm: np.ndarray = self.enorm_debug
                            else:
                                enorm: np.ndarray = self.neuronavigation_api.update_efield(position=cp, orientation=coord[3:], T_rot=T_rot)
                            try:
                                self.e_field_norms_queue.put_nowait((enorm))
                            except queue.Full:
                                pass

                        self.coord_old = coord

            time.sleep(self.sle)

