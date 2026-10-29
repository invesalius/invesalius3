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

"""E-field presentation in the navigation scene."""

import numpy as np
from scipy.spatial import distance
from vtkmodules.vtkCommonColor import vtkColorSeries, vtkNamedColors
from vtkmodules.vtkCommonCore import vtkDoubleArray, vtkLookupTable, vtkPoints, vtkUnsignedCharArray
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkFiltersCore import vtkGlyph3D
from vtkmodules.vtkFiltersModeling import vtkBandedPolyDataContourFilter
from vtkmodules.vtkFiltersSources import vtkArrowSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

import invesalius.constants as const
import invesalius.data.vtk_utils as vtku
from invesalius.data.visualization.surface_map_visualizer import SurfaceMap
from invesalius.data.visualization.surface_painting import SurfacePainting
from invesalius.pubsub import pub as Publisher


class EFieldVisualizer:
    """Own E-field maps, vectors, contours and targeting actors."""

    def __init__(self, efield, scene, interactor, actor_factory, refresh):
        self.efield = efield
        self.scene = scene
        self.ren = scene.ren
        self.interactor = interactor
        self.actor_factory = actor_factory
        self.Refresh = refresh
        self.static_markers_efield = []
        self.colors_init = vtkUnsignedCharArray()
        self.max_efield_vector = None
        self.ball_max_vector = None
        self.ball_GoGEfieldVector = None
        self.GoGEfieldVector = None
        self.vectorfield_actor = None
        self.edge_fill_actor = None
        self.edge_actor = None
        self.show_efield_edges = False
        self.SpreadEfieldFactorTextActor = None
        self.mTMSCoordTextActor = None
        self.EfieldAtTargetLegend = None
        self.ClusterEfieldTextActor = None
        self.enableefieldabovethreshold = False
        self.efield_tools = False
        self._bind_events()

    def _bind_events(self):
        Publisher.subscribe(self.DeleteEFieldMarkers, "Delete markers")
        Publisher.subscribe(self.OnUpdateEfieldvis, "Update efield vis")
        Publisher.subscribe(self.InitializeColorArray, "Initialize color array")
        Publisher.subscribe(self.ReturnToDefaultColorActor, "Recolor again")
        Publisher.subscribe(self.MaxEfieldActor, "Show max Efield actor")
        Publisher.subscribe(self.CoGEfieldActor, "Show CoG Efield actor")
        Publisher.subscribe(
            self.CalculateDistanceMaxEfieldCoGE, "Show distance between Max and CoG Efield"
        )
        Publisher.subscribe(self.EfieldVectors, "Show Efield vectors")
        Publisher.subscribe(self.RecolorEfieldActor, "Recolor efield actor")
        Publisher.subscribe(self.SetEfieldTargetAtCortex, "Set as Efield target at cortex")
        Publisher.subscribe(self.EnableShowEfieldAboveThreshold, "Show area above threshold")
        Publisher.subscribe(self.ShowEfieldContours, "Show Efield contours")
        Publisher.subscribe(self.EnableEfieldTools, "Enable Efield tools")
        Publisher.subscribe(self.ClearTargetAtCortex, "Clear efield target at cortex")
        Publisher.subscribe(self.AddCortexMarkerActor, "Add cortex marker actor")
        Publisher.subscribe(self.CortexMarkersVisualization, "Display efield markers at cortex")

    def clear(self):
        self.RemoveEfieldTargetingActors()
        self.RemoveEfieldVectorActor()
        self.RemoveEfieldEdges()
        for legend in (
            self.ClusterEfieldTextActor,
            self.SpreadEfieldFactorTextActor,
            self.EfieldAtTargetLegend,
        ):
            if legend is not None:
                legend.SetValue("")

    def dispose(self):
        Publisher.unsubscribe_owner(self)
        self.clear()
        self.DeleteEFieldMarkers(())
        for legend in (
            self.ClusterEfieldTextActor,
            self.SpreadEfieldFactorTextActor,
            self.EfieldAtTargetLegend,
            self.mTMSCoordTextActor,
        ):
            if legend is not None:
                self.ren.RemoveActor(legend.actor)

    def DeleteEFieldMarkers(self, markers):
        if len(self.static_markers_efield) > 0:
            for i in range(len(self.static_markers_efield)):
                self.ren.RemoveActor(self.static_markers_efield[i][0])
            self.static_markers_efield = []

    def RecolorEfieldActor(self, token=None):
        if self.efield.efield_painting_token is None or (
            token is not None and token is not self.efield.efield_painting_token
        ):
            return
        polydata = vtkPolyData()
        polydata.ShallowCopy(self.efield.efield_mesh)
        if self.efield.e_field_norms is not None:
            polydata = self.CreateEfieldScalarPolyData(outside_value=float("nan"))
        polydata.GetPointData().AddArray(self.colors_init)
        SurfacePainting().update(
            "E-field",
            self.efield.efield_painting_token,
            SurfaceMap(
                polydata,
                self.efield_lut,
                self.efield_lut.GetTableRange(),
                "E-field",
                "V/m",
                color_array="Colors",
            ),
        )

    def DrawVectors(self, position, orientation, color, scale_factor=10):
        points = vtkPoints()
        vectors = vtkDoubleArray()
        vectors.SetNumberOfComponents(3)
        points.InsertNextPoint(position)
        vectors.InsertNextTuple3(orientation[0], orientation[1], orientation[2])
        dataset = vtkPolyData()
        dataset.SetPoints(points)
        dataset.GetPointData().SetVectors(vectors)
        arrowSource = vtkArrowSource()
        glyphFilter = vtkGlyph3D()
        glyphFilter.SetSourceConnection(arrowSource.GetOutputPort())
        glyphFilter.SetInputData(dataset)
        glyphFilter.SetScaleFactor(scale_factor)
        glyphFilter.Update()
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(glyphFilter.GetOutput())
        Actor = vtkActor()
        Actor.SetMapper(mapper)
        Actor.GetProperty().SetColor(color)
        return Actor

    def HasEfieldVectorData(self):
        return (
            self.efield.efield_mesh is not None
            and self.efield.e_field_norms is not None
            and getattr(self.efield, "Id_list", None) is not None
            and len(self.efield.Id_list) > 0
            and getattr(self.efield, "Idmax", None) is not None
            and getattr(self.efield, "max_efield_array", None) is not None
        )

    def RemoveEfieldTargetingActors(self):
        if self.max_efield_vector is not None:
            self.ren.RemoveActor(self.max_efield_vector)
            self.max_efield_vector = None
        if self.ball_max_vector is not None:
            self.ren.RemoveActor(self.ball_max_vector)
            self.ball_max_vector = None
        if self.GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.GoGEfieldVector = None
        if self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.ball_GoGEfieldVector)
            self.ball_GoGEfieldVector = None
        self.efield.position_max = None
        self.efield.position_max_revision = None
        self.efield.center_gravity_position = None

    def RemoveEfieldVectorActor(self):
        if self.vectorfield_actor is not None:
            self.ren.RemoveActor(self.vectorfield_actor)
            self.vectorfield_actor = None

    def MaxEfieldActor(self):
        if not self.HasEfieldVectorData():
            self.RemoveEfieldTargetingActors()
            return

        vtk_colors = vtkNamedColors()
        if self.max_efield_vector and self.ball_max_vector is not None:
            self.ren.RemoveActor(self.max_efield_vector)
            self.ren.RemoveActor(self.ball_max_vector)
        self.efield.position_max = self.efield.efield_mesh.GetPoint(self.efield.Idmax)
        self.efield.position_max_revision = self.efield.efield_data_revision
        orientation = [
            self.efield.max_efield_array[0],
            self.efield.max_efield_array[1],
            self.efield.max_efield_array[2],
        ]
        self.max_efield_vector = self.DrawVectors(
            self.efield.position_max, orientation, vtk_colors.GetColor3d("Red")
        )
        self.ball_max_vector = self.actor_factory.CreateBall(
            self.efield.position_max, vtk_colors.GetColor3d("Red"), 0.5
        )
        self.ren.AddActor(self.max_efield_vector)
        self.ren.AddActor(self.ball_max_vector)

    def CoGEfieldActor(self):
        if not self.HasEfieldVectorData():
            self.RemoveEfieldTargetingActors()
            return

        vtk_colors = vtkNamedColors()
        if self.GoGEfieldVector and self.ball_GoGEfieldVector is not None:
            self.ren.RemoveActor(self.GoGEfieldVector)
            self.ren.RemoveActor(self.ball_GoGEfieldVector)
        orientation = [
            self.efield.max_efield_array[0],
            self.efield.max_efield_array[1],
            self.efield.max_efield_array[2],
        ]
        if not self.efield.cell_id_indexes_above_threshold:
            return

        self.efield.center_gravity_position = self.efield.FindCenterofGravity(
            self.efield.cell_id_indexes_above_threshold, self.efield.positions_above_threshold
        )
        if self.efield.center_gravity_position is None:
            return

        self.GoGEfieldVector = self.DrawVectors(
            self.efield.center_gravity_position, orientation, vtk_colors.GetColor3d("Blue")
        )
        self.ball_GoGEfieldVector = self.actor_factory.CreateBall(
            self.efield.center_gravity_position, vtk_colors.GetColor3d("Blue"), 0.5
        )
        self.ren.AddActor(self.GoGEfieldVector)
        self.ren.AddActor(self.ball_GoGEfieldVector)

    def AddCortexMarkerActor(self, position_orientation, marker_id):
        vtk_colors = vtkNamedColors()
        marker_actor_brain = self.DrawVectors(
            position_orientation[:3],
            position_orientation[3:],
            vtk_colors.GetColor3d("Orange"),
            scale_factor=3,
        )
        self.static_markers_efield.append([marker_actor_brain, marker_id])
        self.ren.AddActor(marker_actor_brain)
        self.efield.SaveCortexMarker(marker_id)

    def CortexMarkersVisualization(self, display_flag):
        for i in range(len(self.static_markers_efield)):
            if display_flag:
                self.ren.AddActor(self.static_markers_efield[i][0])
            else:
                self.ren.RemoveActor(self.static_markers_efield[i][0])

    def CreateTextLegend(self, FontSize, Position):
        TextLegend = vtku.Text()
        TextLegend.SetSize(FontSize)
        TextLegend.SetPosition(Position)
        TextLegend.BoldOn()
        return TextLegend

    def CreateEfieldSpreadLegend(self):
        self.SpreadEfieldFactorTextActor = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.4, 0.9)
        )
        self.ren.AddActor(self.SpreadEfieldFactorTextActor.actor)

    def CalculateDistanceMaxEfieldCoGE(self):
        if (
            getattr(self.efield, "center_gravity_position", None) is None
            or getattr(self.efield, "position_max", None) is None
            or self.SpreadEfieldFactorTextActor is None
        ):
            return

        self.efield.distance_efield = distance.euclidean(
            self.efield.center_gravity_position, self.efield.position_max
        )
        self.SpreadEfieldFactorTextActor.SetValue(
            "Spread distance: " + str(f"{self.efield.distance_efield:04.2f}")
        )

    def EfieldVectors(self):
        vtk_colors = vtkNamedColors()
        self.RemoveEfieldVectorActor()
        points = vtkPoints()
        vectors = vtkDoubleArray()
        vectors.SetNumberOfComponents(3)

        for i in range(self.efield.radius_list.GetNumberOfIds()):
            point = self.efield.efield_mesh.GetPoint(self.efield.radius_list.GetId(i))
            points.InsertNextPoint(point)
            vectors.InsertNextTuple3(
                self.efield.e_field_col1[i],
                self.efield.e_field_col2[i],
                self.efield.e_field_col3[i],
            )

        dataset = vtkPolyData()
        dataset.SetPoints(points)
        dataset.GetPointData().SetVectors(vectors)

        arrowSource = vtkArrowSource()

        glyphFilter = vtkGlyph3D()
        glyphFilter.SetSourceConnection(arrowSource.GetOutputPort())
        glyphFilter.SetInputData(dataset)
        glyphFilter.SetScaleFactor(2)
        glyphFilter.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(glyphFilter.GetOutput())

        self.vectorfield_actor = vtkActor()
        self.vectorfield_actor.SetMapper(mapper)
        self.vectorfield_actor.GetProperty().SetColor(vtk_colors.GetColor3d("Blue"))

        self.ren.AddActor(self.vectorfield_actor)
        self.interactor.Update()

    def CreateEfieldmTMSCoorlegend(self):
        self.mTMSCoordTextActor = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.4, 0.2)
        )
        self.ren.AddActor(self.mTMSCoordTextActor.actor)

    def InitializeColorArray(self):
        if self.efield.efield_painting_token is None:
            return
        self.colors_init.SetNumberOfComponents(3)
        self.colors_init.SetName("Colors")
        self.colors_init.SetNumberOfTuples(self.efield.efield_mesh.GetNumberOfPoints())
        for component, value in enumerate(const.CORTEX_COLOR):
            self.colors_init.FillComponent(component, value)

    def ReturnToDefaultColorActor(self):
        if self.efield.efield_painting_token is None:
            return
        self.RemoveEfieldTargetingActors()
        self.InitializeColorArray()
        self.RecolorEfieldActor()

    def CreateLUTTableForEfield(self, min, max, highlight_threshold=False):
        lut = vtkLookupTable()
        lut.SetTableRange(min, max)
        colorSeries = vtkColorSeries()
        seriesEnum = colorSeries.BREWER_SEQUENTIAL_BLUE_PURPLE_9
        colorSeries.SetColorScheme(seriesEnum)
        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        n = lut.GetNumberOfTableValues()
        threshold = self.efield.efield_threshold
        if highlight_threshold:
            highlight_rgb = (255, 165, 0)
            for i in range(n):
                norm_val = i / (n - 1)
                if norm_val >= threshold:
                    lut.SetTableValue(i, *(np.array(highlight_rgb) / 255.0), 1.0)
        return lut

    def CreateEfieldScalarPolyData(self, outside_value=None):
        values = np.asarray(self.efield.e_field_norms, dtype=float)
        n_points = self.efield.efield_mesh.GetNumberOfPoints()

        scalars = vtkDoubleArray()
        scalars.SetName("EFieldNorm")
        scalars.SetNumberOfComponents(1)
        scalars.SetNumberOfTuples(n_points)
        scalars.FillComponent(0, self.efield.efield_min if outside_value is None else outside_value)

        if len(values) == n_points:
            for point_id, value in enumerate(values):
                scalars.SetValue(point_id, value)
        else:
            for point_id, value in zip(self.efield.Id_list, values):
                scalars.SetValue(point_id, value)

        scalar_polydata = vtkPolyData()
        scalar_polydata.ShallowCopy(self.efield.efield_mesh)
        scalar_polydata.GetPointData().SetScalars(scalars)
        return scalar_polydata

    def CalculateEdgesEfield(self):
        self.RemoveEfieldEdges()
        if self.efield.efield_max <= self.efield.efield_min:
            return

        named_colors = vtkNamedColors()
        second_lut = self.CreateLUTTableForEfield(self.efield.efield_min, self.efield.efield_max)
        scalar_polydata = self.CreateEfieldScalarPolyData()

        bcf = vtkBandedPolyDataContourFilter()
        bcf.SetInputData(scalar_polydata)
        bcf.ClippingOn()
        bcf.SetScalarModeToValue()

        value_range = self.efield.efield_max - self.efield.efield_min
        contour_values = [
            self.efield.efield_min,
            # self.efield.efield_min + value_range * 0.2,
            self.efield.efield_min + value_range * 0.7,
            self.efield.efield_min + value_range * 0.9,
        ]
        for i, value in enumerate(contour_values):
            bcf.SetValue(i, value)
        bcf.GenerateContourEdgesOn()
        bcf.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(bcf.GetOutputPort())
        mapper.SetLookupTable(second_lut)
        mapper.SetScalarModeToUsePointData()
        mapper.SetScalarRange(self.efield.efield_min, self.efield.efield_max)

        self.edge_fill_actor = vtkActor()
        self.edge_fill_actor.SetMapper(mapper)

        edge_mapper = vtkPolyDataMapper()
        edge_mapper.SetInputData(bcf.GetContourEdgesOutput())
        edge_mapper.SetLookupTable(second_lut)
        edge_mapper.SetScalarRange(self.efield.efield_min, self.efield.efield_max)
        edge_mapper.ScalarVisibilityOff()
        edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()

        self.edge_actor = vtkActor()
        self.edge_actor.SetMapper(edge_mapper)
        self.edge_actor.GetProperty().SetColor(named_colors.GetColor3d("Black"))
        self.edge_actor.GetProperty().SetLineWidth(3.0)
        self.edge_fill_actor.GetProperty().SetOpacity(0)
        self.ren.AddViewProp(self.edge_fill_actor)
        self.ren.AddViewProp(self.edge_actor)

    def RemoveEfieldEdges(self):
        if self.edge_actor is not None:
            self.ren.RemoveViewProp(self.edge_actor)
            self.edge_actor = None
        if self.edge_fill_actor is not None:
            self.ren.RemoveViewProp(self.edge_fill_actor)
            self.edge_fill_actor = None

    def ShowEfieldContours(self, enable):
        self.show_efield_edges = enable
        if not enable:
            self.RemoveEfieldEdges()
            self.Refresh()
            return

        if (
            self.efield.e_field_norms is not None
            and self.efield.efield_mesh is not None
            and self.efield.radius_list.GetNumberOfIds() != 0
            and not self.scene.tracts_status
            and self.scene.actor_tracts is None
        ):
            self.CalculateEdgesEfield()
            self.Refresh()

    def EnableEfieldTools(self, enable):
        self.efield_tools = enable
        if self.efield_tools:
            self.CreateEfieldSpreadLegend()
            self.CreateClustersEfieldLegend()
        elif not self.efield_tools and self.ClusterEfieldTextActor is not None:
            self.ren.RemoveActor(self.ClusterEfieldTextActor.actor)
            self.ren.RemoveActor(self.SpreadEfieldFactorTextActor.actor)

    def DetectClustersEfieldSpread(self, points):
        from sklearn.cluster import DBSCAN
        from sklearn.metrics import pairwise_distances

        if (
            points is None
            or len(points) == 0
            or self.efield.distance_efield is None
            or self.ClusterEfieldTextActor is None
            or getattr(self.efield, "Id_list", None) is None
            or len(self.efield.Id_list) == 0
        ):
            return

        points = np.array(points) if isinstance(points, list) else points
        dbscan = DBSCAN(eps=5, min_samples=1).fit(points)
        labels = dbscan.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        core_sample_indices = dbscan.core_sample_indices_
        cluster_centers = points[core_sample_indices, :]
        representative_centers = np.array(
            [
                cluster.mean(axis=0)
                for cluster in np.split(
                    cluster_centers,
                    np.cumsum(np.unique(dbscan.labels_, return_counts=True)[1])[:-1],
                )
            ]
        )
        distances_between_representatives = np.max(pairwise_distances(representative_centers))
        focal_factor = (
            n_clusters / len(self.efield.Id_list)
            + distances_between_representatives / 30
            + self.efield.distance_efield / 15
        )
        focal_factor = 1 / focal_factor
        self.ClusterEfieldTextActor.SetValue(
            "Clusters above "
            + str(int(self.efield.efield_threshold * 100))
            + "% percent: "
            + str(n_clusters)
            + "\n"
            + "Distance: "
            + str(f"{distances_between_representatives:04.2f}")
            + "\n"
            + "Focal Factor: "
            + str(f"{focal_factor:04.2f}")
        )

        self.efield.focal_factor_members = [
            n_clusters,
            n_clusters / len(self.efield.Id_list),
            distances_between_representatives,
            distances_between_representatives / 30,
            self.efield.distance_efield,
            self.efield.distance_efield / 15,
            focal_factor,
        ]

    def CreateClustersEfieldLegend(self):
        self.ClusterEfieldTextActor = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.12, 0.99)
        )
        self.ren.AddActor(self.ClusterEfieldTextActor.actor)

    def EnableShowEfieldAboveThreshold(self, enable):
        self.enableefieldabovethreshold = enable

    def SegmentEfieldMax(self, cell_id_indexes):
        color = [255, 165, 0]
        for j, value in enumerate(cell_id_indexes):
            self.colors_init.InsertTuple(value, color)

    def ClearTargetAtCortex(self):
        self.efield.target_at_cortex = None
        if self.EfieldAtTargetLegend is not None:
            self.ren.RemoveActor(self.EfieldAtTargetLegend.actor)

    def SetEfieldTargetAtCortex(self, position, orientation):
        position_flip = position
        position_flip[1] = -position_flip[1]
        self.efield.target_at_cortex = position_flip
        self.CreateEfieldAtTargetLegend()

    def ShowEfieldAtCortexTarget(self):
        if self.efield.target_at_cortex is not None:
            index = self.efield.efield_mesh.FindPoint(self.efield.target_at_cortex)
            if index in self.efield.Id_list:
                cell_number = self.efield.Id_list.index(index)
                self.EfieldAtTargetLegend.SetValue(
                    "Efield at Target: " + str(f"{self.efield.e_field_norms[cell_number]:04.2f}")
                )
            else:
                self.EfieldAtTargetLegend.SetValue("Efield at Target: " + str(f"{0:04.2f}"))

    def CreateEfieldAtTargetLegend(self):
        if self.EfieldAtTargetLegend is not None:
            self.ren.RemoveActor(self.EfieldAtTargetLegend.actor)
        self.EfieldAtTargetLegend = self.CreateTextLegend(
            const.TEXT_SIZE_DISTANCE_DURING_NAVIGATION, (0.4, 0.96)
        )
        self.ren.AddActor(self.EfieldAtTargetLegend.actor)

    def OnUpdateEfieldvis(self, token=None):
        if self.efield.efield_painting_token is None or (
            token is not None and token is not self.efield.efield_painting_token
        ):
            return
        if self.efield.radius_list.GetNumberOfIds() != 0:
            self.efield_lut = self.CreateLUTTableForEfield(
                0, self.efield.efield_max, highlight_threshold=self.enableefieldabovethreshold
            )
            [self.efield.cell_id_indexes_above_threshold, self.efield.positions_above_threshold] = (
                self.efield.GetIndexesAboveThreshold(self.efield.efield_threshold)
            )
            if (
                not self.show_efield_edges
                or self.scene.tracts_status
                or self.scene.actor_tracts is not None
            ):
                self.RemoveEfieldEdges()
            else:
                self.CalculateEdgesEfield()
            self.InitializeColorArray()
            for h in range(len(self.efield.Id_list)):
                dcolor = 3 * [0.0]
                index_id = self.efield.Id_list[h]
                self.efield_lut.GetColor(self.efield.e_field_norms[h], dcolor)
                color = 3 * [0.0]
                for j in range(0, 3):
                    color[j] = int(255.0 * dcolor[j])
                self.colors_init.InsertTuple(index_id, color)
            self.RemoveEfieldVectorActor()
            Publisher.sendMessage("Show max Efield actor")
            Publisher.sendMessage("Show CoG Efield actor")
            if self.efield_tools:
                Publisher.sendMessage("Show distance between Max and CoG Efield")
                if self.efield.positions_above_threshold is not None:
                    self.DetectClustersEfieldSpread(self.efield.positions_above_threshold)
            if (
                self.enableefieldabovethreshold
                and self.efield.cell_id_indexes_above_threshold is not None
            ):
                self.SegmentEfieldMax(self.efield.cell_id_indexes_above_threshold)
            self.RecolorEfieldActor()
            self.ShowEfieldAtCortexTarget()
            if self.efield.plot_no_connection:
                Publisher.sendMessage("Show Efield vectors")
                self.efield.plot_vector = False
                self.efield.plot_no_connection = False
        else:
            self.ReturnToDefaultColorActor()
