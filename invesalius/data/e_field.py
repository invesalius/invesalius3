import queue
import threading
import time

import numpy as np
from vtkmodules.vtkCommonCore import (
    vtkIdList)
import csv
from invesalius.pubsub import pub as Publisher

# def ObjectArrowLocation(self, m_img, coord):
#     # m_img[:3, 0] is from posterior to anterior direction of the coil
#     # m_img[:3, 1] is from left to right direction of the coil
#     # m_img[:3, 2] is from bottom to up direction of the coil
#     vec_length = 70
#     m_img_flip = m_img.copy()
#     m_img_flip[1, -1] = -m_img_flip[1, -1]
#     p1 = m_img_flip[:-1, -1]  # coil center
#     coil_dir = m_img_flip[:-1, 0]
#     coil_face = m_img_flip[:-1, 1]
#
#     coil_norm = np.cross(coil_dir, coil_face)
#     p2_norm = p1 - vec_length * coil_norm  # point normal to the coil away from the center by vec_length
#     coil_dir = np.array([coord[3], coord[4], coord[5]])
#
#     return coil_dir, p2_norm, coil_norm, p1
#
# def GetCellIntersection(self, p1, p2, locator):
#     vtk_colors = vtkNamedColors()
#     # This find store the triangles that intersect the coil's normal
#     intersectingCellIds = vtkIdList()
#     #for debugging
#     self.x_actor = self.add_line(p1,p2,vtk_colors.GetColor3d('Blue'))
#     #self.ren.AddActor(self.x_actor) # remove comment for testing
#     locator.FindCellsAlongLine(p1, p2, .001, intersectingCellIds)
#     return intersectingCellIds
#
# def ShowEfieldintheintersection(self, intersectingCellIds, p1, coil_norm, coil_dir):
#     closestDist = 100
#     # if find intersection , calculate angle and add actors
#     if intersectingCellIds.GetNumberOfIds() != 0:
#         for i in range(intersectingCellIds.GetNumberOfIds()):
#             cellId = intersectingCellIds.GetId(i)
#             point = np.array(self.e_field_mesh_centers.GetPoint(cellId))
#             distance = np.linalg.norm(point - p1)
#             if distance < closestDist:
#                 closestDist = distance
#                 pointnormal = np.array(self.e_field_mesh_normals.GetTuple(cellId))
#                 angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
#                 self.FindPointsAroundRadiusEfield(cellId)
#                 self.radius_list.Sort()
#     return self.radius_list

def Get_coil_position( m_img):
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
    T_rot = np.append(T_rot, cn, axis=0) * 0.001  # append and convert to meters
    T_rot = T_rot.tolist()  # to list

    return [T_rot,cp]

class Visualize_E_field_Thread(threading.Thread):

    def __init__(self, queues, event, sle, neuronavigation_api):


        threading.Thread.__init__(self, name='Visualize_E_field_Thread')
        #self.inp = inp #list of inputs
        # self.coord_queue = coord_queue
        self.efield_queue = queues[0]
        self.e_field_norms_queue = queues[1]
        self.e_field_IDs_queue = queues[2]
        #self.tracts_queue = queues[1]
        # self.visualization_queue = visualization_queue
        self.event = event
        self.sle = sle
        self.neuronavigation_api = neuronavigation_api
        self.ID_list = vtkIdList()
        self.coord_old = []
        #self.enorm_debug = self.load_temporarly_e_field_CSV()
        self.debug = True
    def run(self):


        while not self.event.is_set():
            try:
                if not self.e_field_IDs_queue.empty():
                    try:
                        self.ID_list = self.e_field_IDs_queue.get_nowait()
                    finally:
                        self.e_field_IDs_queue.task_done()

                    [m_img, coord] = self.efield_queue.get_nowait()

                    self.efield_queue.task_done()
                    if self.ID_list.GetNumberOfIds() != 0:
                        if np.all(self.coord_old != coord):
                            [T_rot, cp] = Get_coil_position(m_img)
                            #if self.debug:
                            #    enorm = self.enorm_debug
                            #else:
                            enorm = self.neuronavigation_api.update_efield(position=cp, orientation=coord[3:], T_rot=T_rot)
                            self.e_field_norms_queue.put_nowait((enorm))

                        self.coord_old = coord
                time.sleep(self.sle)
            # if no coordinates pass
            except queue.Empty:
                # print("Empty queue in tractography")
                pass
            # if queue is full mark as done (may not be needed in this new "nowait" method)
            except queue.Full:
                # self.coord_queue.task_done()
                self.efield_queue.task_done()
                self.e_field_IDs_queue.task_done()
                #pass

    def load_temporarly_e_field_CSV(self):
        filename = r'C:\Users\anaso\Documents\Data\e-field_simulation\Enorm_inCoilpoint200sorted.csv'
        with open(filename, 'r') as file:
            my_reader = csv.reader(file, delimiter=',')
            rows = []
            for row in my_reader:
                rows.append(row)
        e_field = rows
        e_field_norms = np.array(e_field).astype(float)

        # ###Colors###
        # max = np.amax(e_field_norms)
        # min = np.amin(e_field_norms)
        # print('minz: {:< 6.3}'.format(min))
        # print('maxz: {:< 6.3}'.format(max))
        return e_field_norms