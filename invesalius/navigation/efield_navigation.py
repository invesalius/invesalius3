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

"""E-field navigation integration and surface-mode lifecycle."""

import queue

import numpy as np
import wx
from vtkmodules.vtkCommonCore import mutable, vtkIdList

import invesalius.constants as const
import invesalius.data.transformations as tr
import invesalius.data.vtk_utils as vtku
import invesalius.session as ses
from invesalius.data.visualization.efield_visualizer import EFieldVisualizer
from invesalius.data.visualization.surface_painting import SurfacePainting
from invesalius.i18n import tr as _
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class EFieldNavigation:
    """Own E-field ROI selection, results, targeting data and exports."""

    def __init__(self, scene, interactor, actor_factory, refresh):
        self.plot_vector = None
        self.efield_data_revision = None
        self.position_max_revision = None
        self.position_max = None
        self.center_gravity_position = None
        self.radius_list = vtkIdList()
        self.last_efield_cell_id = None
        self.plot_no_connection = False
        self.old_coord = np.zeros((6,), dtype=float)
        self.efield_mesh = None
        self.e_field_norms = None
        self.efield_threshold = const.EFIELD_MAX_RANGE_SCALE
        self.efield_ROISize = const.EFIELD_ROI_SIZE
        self.efield_painting_token = None
        self.target_at_cortex = None
        self.save_automatically = False
        self.positions_above_threshold = None
        self.cell_id_indexes_above_threshold = None
        self.Id_list = []
        self.target_radius_list = []
        self.visualizer = EFieldVisualizer(self, scene, interactor, actor_factory, refresh)
        self._bind_events()

    def dispose(self):
        Publisher.unsubscribe_owner(self)
        self.StopEfieldPainting()
        self.visualizer.dispose()

    def _bind_events(self):
        Publisher.subscribe(
            self.UpdateEfieldPointLocation, "Update point location for e-field calculation"
        )
        Publisher.subscribe(self.GetEnorm, "Get enorm")
        Publisher.subscribe(self.InitEfield, "Initialize E-field brain")
        Publisher.subscribe(self.StopEfieldPainting, "Stop E-field surface painting")
        Publisher.subscribe(self.SaveEfieldData, "Save Efield data")
        Publisher.subscribe(self.SavedAllEfieldData, "Save all Efield data")
        Publisher.subscribe(self.SaveEfieldTargetData, "Save target data")
        Publisher.subscribe(self.ClearSaveEfieldData, "Clear saved efield data")
        Publisher.subscribe(self.GetTargetSavedEfieldData, "Get target index efield")
        Publisher.subscribe(self.CheckStatusSavedEfieldData, "Check efield data")
        Publisher.subscribe(self.UpdateEfieldPointLocationOffline, "Update interseccion offline")
        Publisher.subscribe(self.GetScalpEfield, "Send scalp index")
        Publisher.subscribe(self.GetCoilPosition, "Calculate position and rotation")
        Publisher.subscribe(
            self.CreateCortexProjectionOnScalp, "Send efield target position on brain"
        )
        Publisher.subscribe(self.UpdateEfieldThreshold, "Update Efield Threshold")
        Publisher.subscribe(self.UpdateEfieldROISize, "Update Efield ROI size")
        Publisher.subscribe(self.CoGEforCortexMarker, "Get Cortex position")
        Publisher.subscribe(self.GetTargetPositions, "Get targets Ids for mtms")
        Publisher.subscribe(self.GetTargetPathmTMS, "Send targeting file path")
        Publisher.subscribe(self.GetdIsfromCoord, "Send mtms coords")
        Publisher.subscribe(
            self.EnableSaveAutomaticallyEfieldData, "Save automatically efield data"
        )
        Publisher.subscribe(self.Getdiperdtforreport, "Get diperdt used in efield calculation")
        Publisher.subscribe(self.UpdateTractSeedBasedEfield, "Update tract seed based efield")
        Publisher.subscribe(self.Get_meshes_paths_to_report, "Get path meshes")

    def StopEfieldPainting(self):
        self.efield_painting_token = None
        self.e_field_norms = None
        self.radius_list.Reset()
        self.visualizer.clear()

    def CoGEforCortexMarker(self):
        if self.e_field_norms is not None:
            [cell_id_indexes, positions_above_threshold] = self.GetIndexesAboveThreshold(0.98)
            center_gravity_position_for_marker = self.FindCenterofGravity(
                cell_id_indexes, positions_above_threshold
            )
            center_gravity_orientation_for_marker = [
                self.max_efield_array[0],
                self.max_efield_array[1],
                self.max_efield_array[2],
            ]
            Publisher.sendMessage(
                "Update Cortex Marker",
                CoGposition=center_gravity_position_for_marker,
                CoGorientation=center_gravity_orientation_for_marker,
            )

    def SaveCortexMarker(self, marker_id):
        if self.save_automatically:
            import time

            import invesalius.gui.dialogs as dlg
            import invesalius.project as prj

            proj = prj.Project()
            timestamp = time.localtime(time.time())
            stamp_date = f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
            stamp_time = f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
            sep = "-"

            if self.path_meshes is None:
                import os

                current_folder_path = os.getcwd()
            else:
                current_folder_path = self.path_meshes

            parts = [current_folder_path, "/", stamp_date, stamp_time, proj.name, "Efield"]
            default_filename = sep.join(parts) + ".csv"

            filename = dlg.ShowLoadSaveDialog(
                message=_("Save markers as..."),
                wildcard="(*.csv)|*.csv",
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                default_filename=default_filename,
            )

            if not filename:
                return

            Publisher.sendMessage(
                "Save Efield data",
                filename=filename,
                plot_efield_vectors=self.plot_efield_vectors,
                marker_id=marker_id,
            )

    def EnableSaveAutomaticallyEfieldData(self, enable, path_meshes, plot_efield_vectors):
        self.save_automatically = enable
        self.path_meshes = path_meshes
        self.plot_efield_vectors = plot_efield_vectors

    def SaveEfieldTargetData(self, target_list_index, position, orientation, plot_efield_vectors):
        if len(self.Id_list) > 0:
            if self.efield_coords is not None:
                import invesalius.data.imagedata_utils as imagedata_utils

                position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                    position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
                    orientation=[
                        self.efield_coords[3],
                        self.efield_coords[4],
                        self.efield_coords[5],
                    ],
                )
                efield_coords_position = [list(position_world), list(orientation_world)]
            enorms_list = list(self.e_field_norms_to_save)
            if plot_efield_vectors:
                if self.plot_no_connection:
                    e_field_vectors = [
                        [list(self.e_field_col1_to_save)],
                        [list(self.e_field_col2_to_save)],
                        [list(self.e_field_col3_to_save)],
                    ]
                else:
                    e_field_vectors = list(self.max_efield_array)
                self.target_radius_list.append(
                    [
                        target_list_index,
                        self.coil_position_Trot,
                        self.coil_position,
                        efield_coords_position,
                        self.efield_coords,
                        enorms_list,
                        e_field_vectors,
                        self.Id_list,
                        self.Idmax,
                        self.focal_factor_members,
                        self.efield_threshold,
                        self.efield_ROISize,
                        self.mtms_coord,
                        self.diperdt,
                        self.ci,
                        self.co,
                        self.path_meshes,
                        self.meshes_file,
                        self.cortex_file,
                        self.coil_model,
                    ]
                )
            else:
                self.target_radius_list.append(
                    [
                        target_list_index,
                        self.Id_list,
                        enorms_list,
                        self.Idmax,
                        self.coil_position,
                        efield_coords_position,
                        self.efield_coords,
                        self.coil_position_Trot,
                    ]
                )

    def ClearSaveEfieldData(self):
        self.target_radius_list.clear()

    def GetTargetSavedEfieldData(self, target_index_list):
        if len(self.target_radius_list) > 0:
            target_index = 0
            for i in range(len(self.target_radius_list)):
                if target_index_list == self.target_radius_list[i][0]:
                    target_index = i
                    self.saved_target_data = self.target_radius_list[target_index]
                    break

    def GetTargetPathmTMS(self, targeting_file):
        self.targeting_file = targeting_file

    def GetTargetPositions(self, target1_origin, target2):
        if self.visualizer.mTMSCoordTextActor is None:
            self.visualizer.CreateEfieldmTMSCoorlegend()
        self.mtms_coord = None
        x_diff = round(target1_origin[0] - target2[0])
        y_diff = round(target1_origin[1] - target2[1])
        csv_filename = self.targeting_file
        target_numbers = [-x_diff, y_diff, 0]
        self.matching_row = self.find_and_extract_data(csv_filename, target_numbers)
        dIs = self.mTMS_multiplyFactor(1000)
        Publisher.sendMessage("Get dI for mtms", dIs=dIs)
        self.visualizer.mTMSCoordTextActor.SetValue("mTMS coords: " + str(target_numbers))
        self.mtms_coord = target_numbers

    def GetdIsfromCoord(self, mtms_coord):
        if self.visualizer.mTMSCoordTextActor is None:
            self.visualizer.CreateEfieldmTMSCoorlegend()
        self.mtms_coord = None
        self.matching_row = self.find_and_extract_data(self.targeting_file, mtms_coord)
        dIs = self.mTMS_multiplyFactor(1000)
        Publisher.sendMessage("Get dI for mtms", dIs=dIs)
        self.visualizer.mTMSCoordTextActor.SetValue("mTMS coords: " + str(mtms_coord))
        self.mtms_coord = mtms_coord

    def mTMS_multiplyFactor(self, factor):
        result = []
        for row in self.matching_row:
            convert = float(row) * factor
            result.append(convert)
        return result

    def find_and_extract_data(self, csv_filename, target_numbers):
        import csv

        matching_rows = []

        with open(csv_filename) as csvfile:
            csv_reader = csv.reader(csvfile)
            for row in csv_reader:
                # Extract the first three numbers from the current row
                first_three_numbers = list(map(float, row[:3]))

                # Check if the first three numbers match the target numbers
                if first_three_numbers == target_numbers:
                    # If there's a match, append the row (excluding the first three numbers)
                    matching_rows = row[3:8]
                    break

        return matching_rows

    def CheckStatusSavedEfieldData(self):
        indexes_saved_list = []
        if len(self.target_radius_list) > 0:
            efield_data_loaded = True
            for i in range(len(self.target_radius_list)):
                indexes_saved_list.append(self.target_radius_list[i][0])
            indexes_saved_list = np.array(indexes_saved_list)
        else:
            efield_data_loaded = False
        Publisher.sendMessage(
            "Get status of Efield saved data",
            efield_data_loaded=efield_data_loaded,
            indexes_saved_list=indexes_saved_list,
        )

    def GetEfieldMaxMin(self, e_field_norms):
        self.e_field_norms = e_field_norms
        efield_max = np.amax(self.e_field_norms)
        efield_min = np.amin(self.e_field_norms)
        self.efield_min = efield_min
        self.efield_max = efield_max
        # self.Idmax = np.array(self.e_field_norms).argmax()
        wx.CallAfter(self.visualizer.OnUpdateEfieldvis, self.efield_painting_token)

    def GetIndexesAboveThreshold(self, threshold):
        cell_id_indexes = []
        positions = []
        indexes = [
            index
            for index, value in enumerate(self.e_field_norms)
            if value > self.efield_max * threshold
        ]
        for index, value in enumerate(indexes):
            cell_id_indexes.append(self.Id_list[value])
            positions.append(self.efield_mesh.GetPoint(self.Id_list[value]))
        return [cell_id_indexes, positions]

    def UpdateEfieldThreshold(self, data):
        self.efield_threshold = data

    def UpdateEfieldROISize(self, data):
        self.efield_ROISize = data
        self.radius_list.Reset()
        self.last_efield_cell_id = None

    def FindCenterofGravity(self, cell_id_indexes, positions):
        if not cell_id_indexes or not positions:
            return None

        weights = []
        for index, value in enumerate(cell_id_indexes):
            weights.append(self.e_field_norms[index])
        sum_weights = sum(weights)
        if sum_weights == 0:
            return None

        x_weighted = []
        y_weighted = []
        z_weighted = []
        for i, (x, y, z) in enumerate(positions):
            x_weighted.append(x * weights[i])
            y_weighted.append(y * weights[i])
            z_weighted.append(z * weights[i])
        sum_x = sum(x_weighted)
        sum_y = sum(y_weighted)
        sum_z = sum(z_weighted)

        center_gravity_x = sum_x / sum_weights
        center_gravity_y = sum_y / sum_weights
        center_gravity_z = sum_z / sum_weights

        query_point = [center_gravity_x, center_gravity_y, center_gravity_z]
        center_gravity = [0.0, 0.0, 0.0]
        cell_id = mutable(0)
        sub_id = mutable(0)
        distance = mutable(0.0)
        self.locator_efield_cell.FindClosestPoint(
            query_point, center_gravity, cell_id, sub_id, distance
        )
        return center_gravity

    def FindPointsAroundRadiusEfield(self, cellId):
        radius = int(self.efield_ROISize)
        self.locator_efield.FindPointsWithinRadius(
            radius, self.e_field_mesh_centers.GetPoint(cellId), self.radius_list
        )

    def CreateCortexProjectionOnScalp(self, marker_id, position, orientation):
        self.target_at_cortex = None
        self.scalp_mesh = self.scalp_actor.GetMapper().GetInput()
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.target_at_cortex = position_flip
        point_scalp = self.FindClosestPointToMesh(position_flip, self.scalp_mesh)
        self.visualizer.CreateEfieldAtTargetLegend()
        Publisher.sendMessage(
            "Create Marker from tangential", point=point_scalp, orientation=orientation
        )

    def FindClosestPointToMesh(self, point, mesh):
        closest_distance = float("inf")
        closest_point = None
        point = np.array(point)
        for i in range(mesh.GetNumberOfCells()):
            distance_sq = np.linalg.norm(np.array(self.scalp_mesh.GetPoint(i)) - point)
            if distance_sq < closest_distance:
                closest_distance = distance_sq
                closest_point = self.scalp_mesh.GetPoint(i)
        return closest_point

    def GetScalpEfield(self, scalp_actor):
        self.scalp_actor = scalp_actor

    def InitEfield(self, e_field_brain, painting_token):
        self.efield_painting_token = painting_token
        self.e_field_mesh_normals = e_field_brain.e_field_mesh_normals
        self.e_field_mesh_centers = e_field_brain.e_field_mesh_centers
        self.locator_efield = e_field_brain.locator_efield
        self.locator_efield_cell = e_field_brain.locator_efield_Cell
        self.efield_mesh = e_field_brain.e_field_mesh
        self.efield_coords = None
        self.coil_position = None
        self.coil_position_Trot = None
        self.e_field_norms = None
        self.e_field_norms_to_save = None
        self.last_efield_cell_id = None
        self.target_radius_list = []
        self.focal_factor_members = []
        self.distance_efield = None
        self.mtms_coord = []
        # self.diperdt = None

        self.visualizer.RemoveEfieldTargetingActors()
        self.visualizer.RemoveEfieldVectorActor()
        self.visualizer.RemoveEfieldEdges()

        self.radius_list.Reset()
        self.old_coord = None
        self.visualizer.efield_lut = self.visualizer.CreateLUTTableForEfield(0, 1)
        self.visualizer.InitializeColorArray()
        self.visualizer.RecolorEfieldActor()

    def ShowEfieldintheintersection(self, intersectingCellIds, p1, coil_norm, coil_dir):
        closestDist = 100
        closestCellId = None
        # if find intersection , calculate angle and add actors
        if intersectingCellIds.GetNumberOfIds() != 0:
            for i in range(intersectingCellIds.GetNumberOfIds()):
                cellId = intersectingCellIds.GetId(i)
                point = np.array(self.e_field_mesh_centers.GetPoint(cellId))
                distance = np.linalg.norm(point - p1)
                if distance < closestDist:
                    closestDist = distance
                    closestCellId = cellId
                    # closestPoint = point
                    # pointnormal = np.array(self.e_field_mesh_normals.GetTuple(cellId))
                    # angle = np.rad2deg(np.arccos(np.dot(pointnormal, coil_norm)))
            if closestCellId is not None and closestCellId != self.last_efield_cell_id:
                self.FindPointsAroundRadiusEfield(closestCellId)
                self.radius_list.Sort()
                self.last_efield_cell_id = closestCellId
        else:
            self.radius_list.Reset()
            self.last_efield_cell_id = None

    def UpdateEfieldPointLocation(self, m_img, coord, queue_IDs):
        if self.efield_painting_token is None:
            return
        [coil_dir, norm, coil_norm, p1] = tr.coil_projection_ray(m_img, coord)
        intersectingCellIds = vtku.find_cells_along_line(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        try:
            self.e_field_IDs_queue = queue_IDs
            if self.radius_list.GetNumberOfIds() != 0:
                if self.old_coord is None or not np.array_equal(self.old_coord, coord):
                    self.e_field_IDs_queue.put_nowait(self.radius_list)
                self.old_coord = np.array(coord)
        except queue.Full:
            pass

    def UpdateTractSeedBasedEfield(
        self, coord_tracts_queue, fallback_m_img=None, current_revision=None
    ):
        if (
            getattr(self, "position_max", None) is None
            or self.position_max_revision != current_revision
        ):
            if fallback_m_img is not None:
                try:
                    m_img_flip = fallback_m_img.copy()
                    m_img_flip[1, -1] = -m_img_flip[1, -1]
                    coord_tracts_queue.clear()
                    coord_tracts_queue.put_nowait(m_img_flip)
                except queue.Full:
                    pass
            return

        if not np.all(np.isfinite(self.position_max)):
            return

        orientation = [0, 0, 0]
        m_img = tr.compose_matrix(angles=np.radians(orientation), translate=self.position_max)
        try:
            coord_tracts_queue.clear()
            coord_tracts_queue.put_nowait(m_img)
        except queue.Full:
            pass

    def UpdateEfieldPointLocationOffline(self, m_img, coord, list_index):
        [coil_dir, norm, coil_norm, p1] = tr.coil_projection_ray(m_img, coord)
        intersectingCellIds = vtku.find_cells_along_line(p1, norm, self.locator_efield_cell)
        self.ShowEfieldintheintersection(intersectingCellIds, p1, coil_norm, coil_dir)
        id_list = []
        for h in range(self.radius_list.GetNumberOfIds()):
            id_list.append(self.radius_list.GetId(h))
        Publisher.sendMessage("Get ID list", ID_list=id_list)
        self.plot_no_connection = True
        self.list_index_efield_vectors = list_index

    def GetCoilPosition(self, position, orientation):
        m_img = tr.compose_matrix(angles=np.radians(orientation), translate=position)
        m_img_flip = m_img.copy()
        # m_img_flip[1, -1] = -m_img_flip[1, -1]
        cp = m_img_flip[:-1, -1]  # coil center
        cp = cp * 0.001  # convert to meters
        cp = cp.tolist()

        ct1 = m_img_flip[:3, 1]  # is from posterior to anterior direction of the coil
        ct2 = m_img_flip[:3, 0]  # is from left to right direction of the coil
        coil_dir = m_img_flip[:-1, 0]
        coil_face = m_img_flip[:-1, 1]
        cn = np.cross(coil_dir, coil_face)
        T_rot = np.append(-ct1, ct2, axis=0)
        T_rot = np.append(T_rot, cn, axis=0)  # append
        T_rot = T_rot.tolist()  # to list
        Publisher.sendMessage("Send coil position and rotation", T_rot=T_rot, cp=cp, m_img=m_img)

    def GetEnorm(self, enorm_data, plot_vector, current_revision=None):
        if self.efield_painting_token is None:
            return
        result_revision = enorm_data[5] if len(enorm_data) > 5 else current_revision
        if current_revision is not None and result_revision != current_revision:
            self.visualizer.RemoveEfieldTargetingActors()
            return

        if enorm_data[3] is None:
            self.visualizer.RemoveEfieldTargetingActors()
            return

        self.e_field_col1 = []
        self.e_field_col2 = []
        self.e_field_col3 = []
        session = ses.Session()
        self.plot_vector = plot_vector
        self.efield_data_revision = result_revision
        self.coil_position_Trot = enorm_data[0]
        self.coil_position = enorm_data[1]
        self.efield_coords = enorm_data[2]
        self.Id_list = enorm_data[4]
        if session.GetConfig("debug_efield"):
            self.e_field_norms = enorm_data[3][self.Id_list, 0]
            self.e_field_col1 = enorm_data[3][self.Id_list, 1]
            self.e_field_col2 = enorm_data[3][self.Id_list, 2]  # LUKATODO: is this a typo?
            self.e_field_col3 = enorm_data[3][self.Id_list, 3]
            self.Idmax = np.array(self.Id_list[np.array(self.e_field_norms).argmax()])
            max_idx = np.array(self.e_field_norms).argmax()
            self.max_efield_array = [
                self.e_field_col1[max_idx],
                self.e_field_col2[max_idx],
                self.e_field_col3[max_idx],
            ]
            self.e_field_norms_to_save = enorm_data[3][:, 0]
            self.e_field_col1_to_save = enorm_data[3][:, 1]
            self.e_field_col2_to_save = enorm_data[3][:, 2]
            self.e_field_col3_to_save = enorm_data[3][:, 3]
        else:
            if not hasattr(enorm_data[3], "enorm") or not hasattr(enorm_data[3], "mvector"):
                self.visualizer.RemoveEfieldTargetingActors()
                return

            self.e_field_norms_to_save = enorm_data[3].enorm
            if len(self.e_field_norms_to_save) == 0:
                self.visualizer.RemoveEfieldTargetingActors()
                return
            if self.Id_list and max(self.Id_list) >= len(self.e_field_norms_to_save):
                self.visualizer.RemoveEfieldTargetingActors()
                return

            self.e_field_norms = [self.e_field_norms_to_save[i] for i in self.Id_list]
            self.e_field_col1 = enorm_data[3].column1
            self.e_field_col2 = enorm_data[3].column2
            self.e_field_col3 = enorm_data[3].column3
            self.e_field_col1_to_save = enorm_data[3].column1
            self.e_field_col2_to_save = enorm_data[3].column2
            self.e_field_col3_to_save = enorm_data[3].column3
            if len(self.e_field_col1) > 1:
                K = len(self.e_field_norms_to_save)
                col1 = np.asarray(self.e_field_col1, dtype=float)
                col2 = np.asarray(self.e_field_col2, dtype=float)
                col3 = np.asarray(self.e_field_col3, dtype=float)
                N = col1.size // K
                if N > 1:
                    self.e_field_col1 = col1.reshape(N, -1).sum(axis=0)
                    self.e_field_col2 = col2.reshape(N, -1).sum(axis=0)
                    self.e_field_col3 = col3.reshape(N, -1).sum(axis=0)

                self.e_field_col1 = [self.e_field_col1[i] for i in self.Id_list]
                self.e_field_col2 = [self.e_field_col2[i] for i in self.Id_list]
                self.e_field_col3 = [self.e_field_col3[i] for i in self.Id_list]

            self.max_efield_array = enorm_data[3].mvector
            self.Idmax = enorm_data[3].maxindex
            if self.save_automatically and self.plot_no_connection:
                import time

                import invesalius.gui.dialogs as dlg
                import invesalius.project as prj

                proj = prj.Project()
                timestamp = time.localtime(time.time())
                stamp_date = (
                    f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
                )
                stamp_time = (
                    f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
                )
                sep = "-"

                if self.path_meshes is None:
                    import os

                    current_folder_path = os.getcwd()
                else:
                    current_folder_path = self.path_meshes

                parts = [current_folder_path, "/", stamp_date, stamp_time, proj.name, "Efield"]
                default_filename = sep.join(parts) + ".csv"

                filename = dlg.ShowLoadSaveDialog(
                    message=_("Save markers as..."),
                    wildcard="(*.csv)|*.csv",
                    style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                    default_filename=default_filename,
                )

                if not filename:
                    return

                Publisher.sendMessage(
                    "Save Efield data",
                    filename=filename,
                    plot_efield_vectors=self.plot_efield_vectors,
                    marker_id=self.list_index_efield_vectors,
                )
        self.GetEfieldMaxMin(self.e_field_norms)

    def SaveEfieldData(self, filename, plot_efield_vectors, marker_id):
        import csv

        import invesalius.data.imagedata_utils as imagedata_utils

        all_data = []

        header = [
            "Marker ID",
            "Rotation matrix for coil coordinates",
            "Coil center",
            "Coil position in world coordinates",
            "InVesalius coordinates",
            "Enorm",
            "Efield vectors",
            "Enorm cell indexes (ROI)",
            "ID cell max",
            "Focal factors",
            "Efield threshold",
            "Efield ROI size",
            "mTMS coordinates",
            "diperdt",
            "ci",
            "co",
            "path meshes",
            "meshes file",
            "cortex file",
            "coil model file",
        ]
        if self.efield_coords is not None:
            position_world, orientation_world = imagedata_utils.convert_invesalius_to_world(
                position=[self.efield_coords[0], self.efield_coords[1], self.efield_coords[2]],
                orientation=[self.efield_coords[3], self.efield_coords[4], self.efield_coords[5]],
            )
            efield_coords_position = [list(position_world), list(orientation_world)]
        if plot_efield_vectors:
            if self.plot_no_connection:
                e_field_vectors = [
                    [list(self.e_field_col1_to_save)],
                    [list(self.e_field_col2_to_save)],
                    [list(self.e_field_col3_to_save)],
                ]
            else:
                e_field_vectors = list(self.max_efield_array)
            all_data.append(
                [
                    marker_id,
                    self.coil_position_Trot,
                    self.coil_position,
                    efield_coords_position,
                    self.efield_coords,
                    list(self.e_field_norms_to_save),
                    e_field_vectors,
                    self.Id_list,
                    self.Idmax,
                    self.focal_factor_members,
                    self.efield_threshold,
                    self.efield_ROISize,
                    self.mtms_coord,
                    self.diperdt,
                    self.ci,
                    self.co,
                    self.path_meshes,
                    self.meshes_file,
                    self.cortex_file,
                    self.coil_model,
                ]
            )

        else:
            all_data.append(
                [
                    marker_id,
                    self.coil_position_Trot,
                    self.coil_position,
                    efield_coords_position,
                    self.efield_coords,
                    list(self.e_field_norms_to_save),
                ]
            )

        with open(filename, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(all_data)

    def SavedAllEfieldData(self, filename):
        import csv

        header = [
            "Marker ID",
            "Rotation matrix for coil coordinates",
            "Coil center",
            "Coil position in world coordinates",
            "InVesalius coordinates",
            "Enorm",
            "Efield vectors",
            "Enorm cell indexes (ROI)",
            "ID cell Max",
            "Focal factors",
            "Efield threshold",
            "Efield ROI size",
            "mTMS coordinates",
            "diperdt",
            "ci",
            "co",
            "path meshes",
            "meshes file",
            "cortex file",
            "coil model file",
        ]
        all_data = list(self.target_radius_list)
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(all_data)

    def Getdiperdtforreport(self, diperdt, ci, co):
        self.diperdt = diperdt
        self.ci = ci
        self.co = co

    def Get_meshes_paths_to_report(self, path_meshes, cortex_file, meshes_file, coilmodel):
        self.meshes_file = meshes_file
        self.cortex_file = cortex_file
        self.path_meshes = path_meshes
        self.coil_model = coilmodel


class EFieldSurfaceMode:
    name = "E-field"
    requires_navigation = True

    def __init__(self, navigation):
        self.navigation = navigation
        self.brain = None
        self.source_surface = None
        self.painting = SurfacePainting()
        self.painting.register(self)
        Publisher.subscribe(self.remove_surface, "Discard surface painting")
        Publisher.subscribe(self.clear, "Close project data")

    @property
    def available(self):
        return self.brain is not None and self.navigation.e_field_enabled

    @available.setter
    def available(self, enabled):
        self.navigation.e_field_enabled = enabled

    def configure(self, brain, surface):
        self.clear()
        self.brain = brain
        self.source_surface = surface

    def supports_surface(self, surface):
        return True

    def default_surface(self):
        brain = Project().GetBrainSurface()
        return brain if brain is not None and brain.supports_painting else self.source_surface

    def start(self, surface, token):
        self.painting.presentation.replace_source(self.name, self.source_surface, surface)
        self.navigation.MarkEfieldParametersChanged()
        Publisher.sendMessage(
            "Initialize E-field brain", e_field_brain=self.brain, painting_token=token
        )
        self.navigation.e_field_loaded = True

    def stop(self):
        self.navigation.e_field_loaded = False
        self.navigation.MarkEfieldParametersChanged()
        self.navigation.efield_queue.clear()
        self.navigation.e_field_norms_queue.clear()
        self.navigation.e_field_IDs_queue.clear()
        Publisher.sendMessage("Stop E-field surface painting")

    def remove_surface(self, surface):
        if surface is self.source_surface:
            self.clear()

    def clear(self):
        self.painting.reset(self)
        self.brain = None
        self.source_surface = None

    def dispose(self):
        self.painting.unregister(self)
        self.brain = None
        self.source_surface = None
        Publisher.unsubscribe_owner(self)
