# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------

import queue
import threading
import time

import numpy as np
from vtkmodules.vtkCommonCore import vtkIdList
from vtkmodules.vtkCommonDataModel import vtkCellLocator, vtkPointLocator

import invesalius.data.imagedata_utils as imagedata_utils
import invesalius.data.transformations as tr


class EFieldBrain:
    """Keep the calculation mesh and its spatial lookup structures together."""

    def __init__(self, mesh):
        from invesalius.data.brainmesh_handler import GetCenters, GetNormals

        self.e_field_mesh = mesh
        self.locator_efield_Cell = vtkCellLocator()
        self.locator_efield_Cell.SetDataSet(mesh)
        self.locator_efield_Cell.BuildLocator()
        self.locator_efield = vtkPointLocator()
        self.locator_efield.SetDataSet(mesh)
        self.locator_efield.BuildLocator()
        self.e_field_mesh_normals = GetNormals(mesh)
        self.e_field_mesh_centers = GetCenters(mesh)


def Get_coil_position(coords):
    # coil position cp : the center point at the bottom of the coil casing,
    # corresponds to the origin of the coil template.
    # coil normal cn: outer normal of the coil, i.e. away from the head
    # coil tangent 1 ct1: long axis
    # coil tangent 2 ct2: short axis ~ direction of primary E under the coil
    # % rotation matrix for the coil coordinates
    # T = [ct1;ct2;cn];

    position, orientation = imagedata_utils.convert_invesalius_to_world(
        position=[coords[0], coords[1], coords[2]],
        orientation=[coords[3], coords[4], coords[5]],
    )
    m_img = tr.compose_matrix(angles=np.radians(orientation), translate=position)
    m_img_flip = m_img.copy()
    # m_img_flip[1, -1] = -m_img_flip[1, -1]
    cp = m_img_flip[:-1, -1]  # coil center
    cp = cp * 0.001  # convert to meters
    cp = cp.tolist()

    ct1 = m_img_flip[:3, 1]  # is from left to right direction of the coil
    ct2 = m_img_flip[:3, 0]  # is from posterior to anterior direction of the coil
    coil_dir = m_img_flip[:-1, 0]
    coil_face = m_img_flip[:-1, 1]
    cn = np.cross(coil_dir, coil_face)
    T_rot = np.append(-ct1, ct2, axis=0)
    T_rot = np.append(T_rot, cn, axis=0)  # append
    T_rot = T_rot.tolist()  # to list

    return [T_rot, cp]


class EFieldCalculationThread(threading.Thread):
    def __init__(
        self, queues, event, sle, neuronavigation_api, debug_efield_enorm, plot_vectors, navigation
    ):
        threading.Thread.__init__(self, name="EFieldCalculationThread")
        # self.inp = inp #list of inputs
        self.efield_queue = queues[0]
        self.e_field_norms_queue = queues[1]
        self.e_field_IDs_queue = queues[2]
        # self.tracts_queue = queues[1]
        # self.visualization_queue = visualization_queue
        self.event = event
        self.sle = sle
        self.neuronavigation_api = neuronavigation_api
        self.navigation = navigation
        self.ID_list = vtkIdList()
        if isinstance(debug_efield_enorm, np.ndarray):
            self.enorm_debug = debug_efield_enorm
            self.debug = True
        else:
            self.debug = False
        self.plot_vectors = plot_vectors
        self.coord_old = None
        self.revision_old = None

    def run(self):
        while not self.event.is_set():
            if not self.e_field_IDs_queue.empty():
                try:
                    self.ID_list = self.e_field_IDs_queue.get_nowait()
                    self.e_field_IDs_queue.task_done()
                    id_list = []
                    for h in range(self.ID_list.GetNumberOfIds()):
                        id_list.append(self.ID_list.GetId(h))
                except queue.Empty:
                    continue

                if not self.efield_queue.empty():
                    try:
                        efield_payload = self.efield_queue.get_nowait()
                        self.efield_queue.task_done()
                    except queue.Empty:
                        continue

                    if len(efield_payload) == 3:
                        _m_img, coord, revision = efield_payload
                    else:
                        _m_img, coord = efield_payload
                        revision = None

                    if (
                        not self.navigation.e_field_loaded
                        or revision != self.navigation.e_field_revision
                    ):
                        continue

                    if self.ID_list.GetNumberOfIds() != 0:
                        if (
                            self.coord_old is None
                            or not np.array_equal(self.coord_old, coord)
                            or self.revision_old != revision
                        ):
                            [T_rot, cp] = Get_coil_position(coord)
                            if self.debug:
                                enorm = self.enorm_debug
                            else:
                                enorm = self.neuronavigation_api.update_efield_vectorROIMax(
                                    position=cp,
                                    orientation=coord[3:],
                                    T_rot=T_rot,
                                    id_list=id_list,
                                )
                            try:
                                self.e_field_norms_queue.put_nowait(
                                    [T_rot, cp, coord, enorm, id_list, revision]
                                )

                            except queue.Full:
                                pass

                            self.coord_old = np.array(coord)
                            self.revision_old = revision

            time.sleep(self.sle)
