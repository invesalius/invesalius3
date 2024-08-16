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
import random
from copy import deepcopy

import numpy as np
import vtk
import wx
from vtk import vtkColorTransferFunction
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)

import invesalius.constants as const
import invesalius.session as ses
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.navigation.markers import MarkersControl
from invesalius.pubsub import pub as Publisher


class MEPVisualizer:
    def __init__(self):
        self.points = vtk.vtkPolyData()
        self.surface = None
        self.colored_surface_actor = None
        self.point_actore = None

        self.colorBarActor = None
        self.actors_dict = {}  # Dictionary to store all actors created by the MEP visualizer

        self.marker_storage = None
        self.first_load = True

        self.is_navigating = False

        self.dims_size = 10

        self._config_params = deepcopy(const.DEFAULT_MEP_CONFIG_PARAMS)
        self.__bind_events()
        self._LoadUserParameters()

    # --- Event Handling ---

    def __bind_events(self):
        Publisher.subscribe(self.DisplayMotorMap, "Show motor map")
        Publisher.subscribe(self._ResetConfigParams, "Reset MEP Config")
        Publisher.subscribe(self.UpdateConfig, "Save Preferences")
        # Publisher.subscribe(self.UpdateMEPPoints, "Update marker list")
        # Publisher.subscribe(self.SetBrainSurface, "Set MEP brain surface")
        Publisher.subscribe(self.UpdateMEPPoints, "Redraw MEP mapping")
        Publisher.subscribe(self.UpdateNavigationStatus, "Navigation status")
        Publisher.subscribe(self.SetBrainSurface, "Load visible surface actor")
        Publisher.subscribe(self.OnCloseProject, "Close project data")

    # --- Configuration Management ---

    def _LoadUserParameters(self):
        session = ses.Session()
        config = session.GetConfig("mep_configuration")
        if config:  # If there is a configuration saved in a previous session
            config["enabled_once"] = False
            config["mep_enabled"] = False
            if (
                config["brain_surface_index"] is not None
            ):  # If there is a surface already selected then there is no point of showing the message
                config["enabled_once"] = True
            self._config_params.update(config)
        else:
            session.SetConfig("mep_configuration", self._config_params)

    def _ResetConfigParams(self):
        defaults = deepcopy(const.DEFAULT_MEP_CONFIG_PARAMS)
        if self._config_params["enabled_once"]:
            defaults["enabled_once"] = True
            defaults["bounds"] = self._config_params[
                "bounds"
            ]  # Keep the bounds of the surface if it was already selected (to avoid recalculating)
            defaults["brain_surface_index"] = self._config_params[
                "brain_surface_index"
            ]  # Keep the previously selected index

        ses.Session().SetConfig("mep_configuration", defaults)
        self._config_params = deepcopy(defaults)

    def _SaveUserParameters(self):
        ses.Session().SetConfig("mep_configuration", self._config_params)

    def UpdateConfig(self):
        self._config_params = deepcopy(ses.Session().GetConfig("mep_configuration"))
        # self.UpdateMEPPoints([])
        self.UpdateVisualization()

    # --- Motor Map Display ---

    def DisplayMotorMap(self, show: bool):
        if show:
            self._config_params["mep_enabled"] = True
            if self._config_params["brain_surface_index"] is None:
                wx.MessageBox(
                    "Please select a surface from preferences.",
                    "MEP Mapping",
                    wx.OK | wx.ICON_INFORMATION,
                )
                self._config_params["enabled_once"] = True
                self._SaveUserParameters()
                return

            if self.colorBarActor:
                Publisher.sendMessage("Remove surface actor from viewer", actor=self.colorBarActor)
                Publisher.sendMessage("Remove surface actor from viewer", actor=self.surface)
            self.colorBarActor = self.CreateColorbarActor()
            if self._config_params["brain_surface_index"] is not None:  # Hides the original surface
                Publisher.sendMessage(
                    "Show surface",
                    index=self._config_params["brain_surface_index"],
                    visibility=False,
                )
                if self.first_load:
                    Publisher.sendMessage(
                        "Show only surface",
                        surface_index=self._config_params["brain_surface_index"],
                    )
                    Publisher.sendMessage("Get visible surface actor")
                    self.first_load = False

            self.UpdateVisualization()
        else:
            self._config_params["mep_enabled"] = False
            self._CleanupVisualization()
            if self._config_params["brain_surface_index"] is not None:  # Shows the original surface
                Publisher.sendMessage(
                    "Show surface",
                    index=self._config_params["brain_surface_index"],
                    visibility=True,
                )
        self._SaveUserParameters()

    # --- Data Interpolation and Visualization ---

    def InterpolateData(self):
        surface = self.surface
        points = self.points
        if not surface:
            # TODO: Show modal dialog to select a surface from project
            return
        if not points:
            raise ValueError("MEP Visualizer: No point data found")

        bounds = np.array(self._config_params["bounds"])
        gaussian_sharpness = self._config_params["gaussian_sharpness"]
        gaussian_radius = self._config_params["gaussian_radius"]
        dims_size = self.dims_size
        dims = np.array([dims_size, dims_size, dims_size])

        box = vtk.vtkImageData()
        box.SetDimensions(dims)
        box.SetSpacing((bounds[1::2] - bounds[:-1:2]) / (dims - 1))
        box.SetOrigin(bounds[::2])

        gaussian_kernel = vtk.vtkGaussianKernel()
        gaussian_kernel.SetSharpness(gaussian_sharpness)
        gaussian_kernel.SetRadius(gaussian_radius)

        interpolator = vtk.vtkPointInterpolator()
        interpolator.SetInputData(box)
        interpolator.SetSourceData(points)
        interpolator.SetKernel(gaussian_kernel)

        resample = vtk.vtkResampleWithDataSet()

        polydata = surface.GetMapper().GetInput()
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

    def QueryBrainSurface(self):
        Publisher.sendMessage(
            "Show only surface", surface_index=self._config_params["brain_surface_index"]
        )
        Publisher.sendMessage("Get visible surface actor")

    def SetBrainSurface(self, actor: vtk.vtkActor, index: int):
        self.surface = actor
        self.actors_dict[id(actor)] = actor
        self._config_params["bounds"] = list(np.array(actor.GetBounds()))
        self._config_params["brain_surface_index"] = index
        self.UpdateVisualization()
        # hide the original surface if MEP is enabled
        if self._config_params["mep_enabled"]:
            Publisher.sendMessage("Show surface", index=index, visibility=False)
        self._SaveUserParameters()

    def _FilterMarkers(self, markers: list[Marker]):
        """
        Checks if the markers were updated and if those updated are of type coil_target
        """

        self.marker_storage = self.marker_storage or markers

        if not markers:
            return [], False

        # Check if the markers are coil target markers
        coil_markers = []
        for marker in markers:
            if marker.marker_type == MarkerType.COIL_TARGET:
                coil_markers.append(marker)

        # check if the coil markers were changed compared to the stored markers
        skip = coil_markers == self.marker_storage

        return coil_markers, skip

    def UpdateMEPPoints(self):
        """
        Updates or creates the point data with MEP values from a list of markers.

        Args:
            markers (List[Marker]): The list of marker objects to add/update points for.
            clear_old (bool, default=False): If True, clears all existing points before updating.
        """
        markers, skip = self._FilterMarkers(MarkersControl().list)

        if skip or not markers:  # Saves computation if the markers are not updated or irrelevant
            return

        points = vtk.vtkPoints()

        point_data = self.points.GetPointData()
        mep_array = vtk.vtkDoubleArray()
        mep_array.SetName("MEP")
        point_data.AddArray(mep_array)

        for marker in markers:
            new_point_id = points.InsertNextPoint(
                marker.position[0], -marker.position[1], marker.position[2]
            )
            mep_value = marker.mep_value or 0
            mep_array.InsertNextValue(mep_value)

        self.points.SetPoints(points)
        self.points.GetPointData().SetActiveScalars("MEP")
        self.points.Modified()
        if self._config_params["mep_enabled"]:
            self.UpdateVisualization()

    def UpdateVisualization(self):
        if not self._config_params["mep_enabled"]:
            return

        self._CleanupVisualization()

        interpolated_data = self.InterpolateData()
        self.colored_surface_actor = self.CreateColoredSurface(interpolated_data)
        self.point_actor = self.CreatePointActor(
            self.points, (self._config_params["threshold_down"], self._config_params["range_up"])
        )
        self.colorBarActor = self.CreateColorbarActor()

        Publisher.sendMessage("AppendActor", actor=self.colored_surface_actor)
        Publisher.sendMessage("AppendActor", actor=self.surface)
        Publisher.sendMessage("AppendActor", actor=self.point_actor)
        Publisher.sendMessage("AppendActor", actor=self.colorBarActor)

        if not self.is_navigating:
            Publisher.sendMessage("Render volume viewer")

    def CreateColorbarActor(self, lut=None) -> vtk.vtkActor:
        if lut is None:
            lut = self._CustomColormap(self._config_params["mep_colormap"])
        colorBarActor = vtk.vtkScalarBarActor()
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

    def CreateColoredSurface(self, poly_data) -> vtk.vtkActor:
        """Creates the actor for the surface with color mapping."""
        normals = vtkPolyDataNormals()
        normals.SetInputData(poly_data)
        normals.ComputePointNormalsOn()
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
        point_mapper = vtk.vtkPointGaussianMapper()
        point_mapper.SetInputData(points)
        point_mapper.SetScalarRange(data_range)
        point_mapper.SetScaleFactor(1)
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

    def OnCloseProject(self):
        """Cleanup the visualization when the project is closed."""
        self.DisplayMotorMap(False)
        self._config_params["mep_enabled"] = False
        self._config_params["enabled_once"] = False
        self._SaveUserParameters()
