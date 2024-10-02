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
from copy import deepcopy

import numpy as np
import wx
from vtk import vtkColorTransferFunction
from vtkmodules.vtkCommonCore import (
    vtkDoubleArray,
    vtkPoints,
)
from vtkmodules.vtkCommonDataModel import (
    vtkImageData,
    vtkPolyData,
)
from vtkmodules.vtkFiltersCore import (
    vtkDecimatePro,
    vtkImplicitPolyDataDistance,
    vtkPolyDataNormals,
    vtkResampleWithDataSet,
    vtkTriangleFilter,
)
from vtkmodules.vtkFiltersPoints import (
    vtkGaussianKernel,
    vtkPointInterpolator,
)
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPointGaussianMapper,
    vtkPolyDataMapper,
)

import invesalius.constants as const
import invesalius.data.transformations as transformations
import invesalius.gui.dialogs as dialogs
import invesalius.session as ses
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.navigation.markers import MarkersControl
from invesalius.pubsub import pub as Publisher


class MEPVisualizer:
    def __init__(self):
        self.points = vtkPolyData()
        self.surface = None
        self.surface_index = None
        self.decimate_surface = None
        self.colored_surface_actor = None
        self.point_actor = None
        self.bounds = None

        self.colorBarActor = None
        self.actors_dict = {}  # Dictionary to store all actors created by the MEP visualizer
        self.marker_storage = []

        self.is_navigating = False

        self._config_params = deepcopy(const.DEFAULT_MEP_CONFIG_PARAMS)
        self.__bind_events()
        self._LoadUserParameters()

    # --- Event Handling ---

    def __bind_events(self):
        Publisher.subscribe(self._ResetConfigParams, "Reset MEP Config")
        Publisher.subscribe(self.UpdateConfig, "Save Preferences")
        # Publisher.subscribe(self.UpdateMEPPoints, "Update marker list")
        # Publisher.subscribe(self.SetBrainSurface, "Set MEP brain surface")
        Publisher.subscribe(self.UpdateMEPPoints, "Redraw MEP mapping")
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")
        Publisher.subscribe(self.SetBrainSurface, "Load brain surface actor")
        Publisher.subscribe(self.OnCloseProject, "Close project data")
        Publisher.subscribe(self.OnRemoveSurfaces, "Remove surfaces")

    # --- Configuration Management ---

    def _LoadUserParameters(self):
        session = ses.Session()
        config = session.GetConfig("mep_configuration")
        if config:  # If there is a configuration saved in a previous session
            self._config_params.update(config)
        else:
            session.SetConfig("mep_configuration", self._config_params)

    def _ResetConfigParams(self):
        defaults = deepcopy(const.DEFAULT_MEP_CONFIG_PARAMS)
        ses.Session().SetConfig("mep_configuration", defaults)
        self._config_params = deepcopy(defaults)

    def _SaveUserParameters(self):
        ses.Session().SetConfig("mep_configuration", self._config_params)

    def UpdateConfig(self):
        self._config_params = deepcopy(ses.Session().GetConfig("mep_configuration"))
        self.UpdateVisualization()

    # --- Motor Map Display ---

    def DisplayMotorMap(self, show: bool):
        if show:
            self._config_params["mep_enabled"] = True
            if not self.surface:
                wx.MessageBox(
                    "Please select a brain surface from preferences.",
                    "MEP Mapping",
                    wx.OK | wx.ICON_INFORMATION,
                )
                self._SaveUserParameters()
                Publisher.sendMessage("Open preferences menu", page=0)
                return False
            progress_dialog = dialogs.BrainSurfaceLoadingProgressWindow()
            progress_dialog.Update(value=20, msg="Preparing brain surface...")
            Publisher.sendMessage("Hide all surfaces")
            self.UpdateVisualization()
            progress_dialog.Update(value=50, msg="Preparing brain surface...")
            self.UpdateMEPPoints()
            progress_dialog.Close()
        else:
            self._config_params["mep_enabled"] = False
            self._CleanupVisualization()
            if self.surface:  # Shows the original surface
                Publisher.sendMessage(
                    "Show surface",
                    index=self.surface_index,
                    visibility=True,
                )
            self.marker_storage = []
        self._SaveUserParameters()

        return True

    # --- Data Interpolation and Visualization ---

    def InterpolateData(self):
        surface = self.decimate_surface
        points = self.points
        if not surface:
            # TODO: Show modal dialog to select a surface from project
            return
        if not points:
            raise ValueError("MEP Visualizer: No point data found")

        gaussian_sharpness = self._config_params["gaussian_sharpness"]
        gaussian_radius = self._config_params["gaussian_radius"]
        dims_size = self._config_params["dimensions_size"]
        dims = np.array([dims_size, dims_size, dims_size])

        box = vtkImageData()
        box.SetDimensions(dims)
        box.SetSpacing((self.bounds[1::2] - self.bounds[:-1:2]) / (dims - 1))
        box.SetOrigin(self.bounds[::2])

        gaussian_kernel = vtkGaussianKernel()
        gaussian_kernel.SetSharpness(gaussian_sharpness)
        gaussian_kernel.SetRadius(gaussian_radius)

        interpolator = vtkPointInterpolator()
        interpolator.SetInputData(box)
        interpolator.SetSourceData(points)
        interpolator.SetKernel(gaussian_kernel)

        resample = vtkResampleWithDataSet()

        polydata = surface.GetOutput()
        resample.SetInputData(polydata)
        resample.SetSourceConnection(interpolator.GetOutputPort())
        resample.SetPassPointArrays(1)
        resample.Update()
        return resample.GetOutput()

    def _CustomColormap(self, choice=None):
        """
        Creates a color transfer function with a 4-color heatmap.

        Args:
            choice (str): The name of the color combination (refer to the 'color_maps' dictionary).

        Returns:
            vtkColorTransferFunction: The created color transfer function.
        """

        color_function = vtkColorTransferFunction()
        choice = choice or self._config_params["mep_colormap"]

        color_maps = const.MEP_COLORMAP_DEFINITIONS

        if choice in color_maps:
            for value, color in color_maps[choice].items():
                color_function.AddRGBPoint(self._config_params["colormap_range_uv"][value], *color)
        else:
            raise ValueError(
                f"Invalid choice '{choice}'. Choose from: {', '.join(color_maps.keys())}"
            )

        return color_function

    def DecimateBrainSurface(self):
        triangle_filter = vtkTriangleFilter()
        triangle_filter.SetInputData(
            self.surface.GetMapper().GetInput()
        )  # Use vtkPolyData directly
        triangle_filter.Update()  # Perform triangulation
        triangulated_polydata = triangle_filter.GetOutput()

        # Setup the decimation filter
        decimate_filter = vtkDecimatePro()
        decimate_filter.SetInputData(triangulated_polydata)
        decimate_filter.SetTargetReduction(0.6)  # Reduce the number of triangles by 60%
        decimate_filter.PreserveTopologyOn()  # Preserve the topology
        decimate_filter.Update()
        return decimate_filter

    def SetBrainSurface(self, actor: vtkActor, index: int):
        self.surface = actor
        self.surface_index = index
        self.decimate_surface = self.DecimateBrainSurface()
        self.bounds = np.array(actor.GetBounds())
        self.marker_storage = []
        if self._config_params["mep_enabled"]:
            Publisher.sendMessage("Show surface", index=index, visibility=False)
        self._SaveUserParameters()

    def _FilterMarkers(self, markers_list):
        """
        Checks if the markers were updated and if those updated are of type coil_target
        """
        if not markers_list:
            return [], False

        markers = []
        for marker in markers_list:
            markers.append(marker.to_dict())

        # TODO: use modified markers list to make projection_on_surface
        # Find objects in the new list that are not in the old list (added)
        added_objects = [
            new_obj
            for new_obj in markers
            if not any((new_obj == old_obj) for old_obj in self.marker_storage)
        ]

        # Find objects in the old list that are not in the new list (removed)
        removed_objects = [
            old_obj
            for old_obj in self.marker_storage
            if not any((old_obj == new_obj) for new_obj in markers)
        ]

        # Check if the lists have changed
        if not bool(added_objects or removed_objects):
            return None, True

        # Check if the markers are coil target markers
        coil_markers = []
        for marker in markers_list:
            if marker.marker_type == MarkerType.COIL_TARGET:
                coil_markers.append(marker)

        self.marker_storage = markers

        return coil_markers, False

    def collision_detection(self, m_point):
        distance_function = vtkImplicitPolyDataDistance()
        distance_function.SetInput(self.decimate_surface.GetOutput())
        distance = distance_function.EvaluateFunction(m_point[:3, -1])
        if distance > 30 or distance < 1:
            print("no collision")
            return m_point[:3, -1]

        t_translation = transformations.translation_matrix([0, 0, -distance])
        m_point_t = m_point @ t_translation
        return m_point_t[:3, -1]

    def projection_on_surface(self, marker):
        print("projecting target on brain surface")
        a, b, g = np.radians(marker.orientation[:3])
        r_ref = transformations.euler_matrix(a, b, g, axes="sxyz")
        t_ref = transformations.translation_matrix(
            [marker.position[0], marker.position[1], marker.position[2]]
        )
        m_point = transformations.concatenate_matrices(t_ref, r_ref)
        m_point[1, -1] = -m_point[1, -1]
        new_coord = self.collision_detection(m_point)

        return new_coord

    def UpdateMEPPoints(self):
        """
        Updates or creates the point data with MEP values from a list of markers.

        Args:
            markers (List[Marker]): The list of marker objects to add/update points for.
            clear_old (bool, default=False): If True, clears all existing points before updating.
        """
        if not self._config_params["mep_enabled"]:
            return
        if not self.surface:
            return

        markers, skip = self._FilterMarkers(MarkersControl().list)
        if not markers:
            self.points = vtkPolyData()
            self.UpdateVisualization()
            return
        if skip:  # Saves computation if the markers are not updated or irrelevant
            return

        points = vtkPoints()

        point_data = self.points.GetPointData()
        mep_array = vtkDoubleArray()
        mep_array.SetName("MEP")
        point_data.AddArray(mep_array)

        for marker in markers:
            if not marker.x_cortex and not marker.y_cortex and not marker.z_cortex:
                projected_point = self.projection_on_surface(marker)
                marker.cortex_position_orientation = [
                    projected_point[0],
                    -projected_point[1],
                    projected_point[2],
                    marker.orientation[0],
                    marker.orientation[1],
                    marker.orientation[2],
                ]

            points.InsertNextPoint(marker.x_cortex, -marker.y_cortex, marker.z_cortex)
            mep_value = marker.mep_value or 0
            mep_array.InsertNextValue(mep_value)
        MarkersControl().SaveState()

        self.points.SetPoints(points)
        self.points.GetPointData().SetActiveScalars("MEP")
        self.points.Modified()
        if self._config_params["mep_enabled"]:
            self.UpdateVisualization()

    def UpdateVisualization(self):
        if not self._config_params["mep_enabled"] or not self.surface:
            return

        self._CleanupVisualization()

        interpolated_data = self.InterpolateData()
        self.colored_surface_actor = self.CreateColoredSurface(interpolated_data)
        self.point_actor = self.CreatePointActor(
            self.points, (self._config_params["threshold_down"], self._config_params["range_up"])
        )
        self.colorBarActor = self.CreateColorbarActor()

        Publisher.sendMessage("AppendActor", actor=self.colored_surface_actor)
        Publisher.sendMessage("AppendActor", actor=self.point_actor)
        Publisher.sendMessage("AppendActor", actor=self.colorBarActor)

        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def CreateColorbarActor(self, lut=None) -> vtkActor:
        if lut is None:
            lut = self._CustomColormap(self._config_params["mep_colormap"])
        colorBarActor = vtkScalarBarActor()
        colorBarActor.SetLookupTable(lut)
        colorBarActor.SetNumberOfLabels(4)
        colorBarActor.SetLabelFormat("%4.0f")
        colorBarActor.SetTitle("µV       ")
        # FIXME: Set the title to be a little bit smaller
        colorBarActor.SetTitleRatio(0.1)
        colorBarActor.SetMaximumWidthInPixels(70)
        # move title to below
        colorBarActor.GetTitleTextProperty().SetFontSize(1)

        # FIXME: Set the label text size to be a little bit smaller
        label_text_property = colorBarActor.GetLabelTextProperty()
        label_text_property.SetFontSize(9)
        # label_text_property.SetColor(0, 0, 0)

        colorBarActor.SetLabelTextProperty(label_text_property)

        # resize colorbar
        colorBarActor.SetWidth(0.1)
        colorBarActor.SetHeight(0.3)

        colorBarActor.SetVisibility(1)

        # set position of the colorbar to the bottom left corner
        colorBarActor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        colorBarActor.GetPositionCoordinate().SetValue(0.06, 0.06)
        # Track the created actor
        self.actors_dict[id(colorBarActor)] = colorBarActor
        return colorBarActor

    def CreateColoredSurface(self, poly_data) -> vtkActor:
        """Creates the actor for the surface with color mapping."""
        normals = vtkPolyDataNormals()
        normals.SetInputData(poly_data)
        normals.ComputePointNormalsOff()
        normals.ComputeCellNormalsOff()
        normals.Update()

        data_range = (self._config_params["threshold_down"], self._config_params["range_up"])

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        if data_range is None:
            data_range = (self._config_params["threshold_down"], self._config_params["range_up"])
        mapper.SetScalarRange(data_range)

        lut = self._CustomColormap()
        mapper.SetLookupTable(lut)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetInterpolationToGouraud()
        self.actors_dict[id(actor)] = actor
        return actor

    def CreatePointActor(self, points, data_range):
        """Creates the actor for the data points."""
        point_mapper = vtkPointGaussianMapper()
        point_mapper.SetInputData(points)
        point_mapper.SetScalarRange(data_range)
        point_mapper.SetScaleFactor(0.5)
        point_mapper.EmissiveOff()
        point_mapper.SetSplatShaderCode(
            "//VTK::Color::Impl\n"
            "float dist = dot(offsetVCVSOutput.xy,offsetVCVSOutput.xy);\n"
            "if (dist > 1.0) {\n"
            "  discard;\n"
            "} else {\n"
            "  float scale = (1.0 - dist);\n"
            "  ambientColor *= scale;\n"
            "  diffuseColor *= scale;\n"
            "}\n"
        )

        lut = self._CustomColormap()
        point_mapper.SetLookupTable(lut)

        point_actor = vtkActor()
        point_actor.SetMapper(point_mapper)

        self.actors_dict[id(point_actor)] = point_actor
        return point_actor

    def _CleanupVisualization(self):
        for actor in self.actors_dict.values():
            Publisher.sendMessage("Remove surface actor from viewer", actor=actor)

        self.actors_dict.clear()

        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def UpdateNavigationStatus(self, nav_status, vis_status):
        self.is_navigating = nav_status

    def OnRemoveSurfaces(self, surface_indexes):
        for index in surface_indexes:
            if index == self.surface_index:
                self.surface = None
                self.surface_index = None
                self.DisplayMotorMap(False)
                self._config_params["mep_enabled"] = False
                self._SaveUserParameters()
                Publisher.sendMessage("Press motor map button", pressed=False)

    def OnCloseProject(self):
        """Cleanup the visualization when the project is closed."""
        self.DisplayMotorMap(False)
        self._config_params["mep_enabled"] = False
        self.points = vtkPolyData()
        self.surface = None
        self.surface_index = None
        self.decimate_surface = None
        self.colored_surface_actor = None
        self.point_actor = None
        self.bounds = None
        self.colorBarActor = None
        self.actors_dict = {}
        Publisher.sendMessage("Press motor map button", pressed=False)
        self._SaveUserParameters()
