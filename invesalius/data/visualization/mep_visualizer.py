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
from scipy.spatial import cKDTree
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
    vtkResampleWithDataSet,
    vtkTriangleFilter,
)
from vtkmodules.vtkFiltersPoints import (
    vtkGaussianKernel,
    vtkPointInterpolator,
)

import invesalius.constants as const
import invesalius.data.transformations as transformations
import invesalius.gui.dialogs as dialogs
import invesalius.session as ses
from invesalius.data.markers.marker import MarkerType
from invesalius.data.surface_map import SurfaceMap
from invesalius.navigation.markers import MarkersControl
from invesalius.navigation.surface_painting import SurfacePainting
from invesalius.project import Project
from invesalius.pubsub import pub as Publisher


class MEPVisualizer:
    name = "MEP"

    def __init__(self):
        self.points_polydata = vtkPolyData()
        self.surface = None
        self.decimate_surface = None
        self.bounds = None

        self.marker_storage = []

        self.token = None
        self.brain_target_data = None
        self.painting = SurfacePainting()

        self._config_params = deepcopy(const.DEFAULT_MEP_CONFIG_PARAMS)
        self.__bind_events()
        self._LoadUserParameters()
        self.available = self._config_params["mep_enabled"]
        self.painting.register(self)

    # --- Event Handling ---

    def __bind_events(self):
        Publisher.subscribe(self._ResetConfigParams, "Reset MEP Config")
        Publisher.subscribe(self.UpdateConfig, "Save Preferences")
        # Publisher.subscribe(self.UpdateMEPPoints, "Update marker list")
        # Publisher.subscribe(self.SetBrainSurface, "Set MEP brain surface")
        Publisher.subscribe(self.UpdateMEPPoints, "Redraw MEP mapping")
        Publisher.subscribe(
            self.UpdateMEPPointsFromBrainTargets, "Redraw MEP mapping from brain targets"
        )
        Publisher.subscribe(self.SetBrainSurface, "Load brain surface actor")
        Publisher.subscribe(self.OnCloseProject, "Close project data")

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
        self.painting.set_available(self, self._config_params["mep_enabled"])

    def _SaveUserParameters(self):
        ses.Session().SetConfig("mep_configuration", self._config_params)

    def UpdateConfig(self):
        self._config_params = deepcopy(ses.Session().GetConfig("mep_configuration"))
        self.painting.set_available(self, self._config_params["mep_enabled"])
        self.UpdateVisualization()

    # --- Motor Map Display ---

    def default_surface(self):
        project = Project()
        return project.GetBrainSurface() or project.GetScalpSurface()

    def DisplayMotorMap(self, show: bool):
        self._config_params["mep_enabled"] = show
        self.painting.set_available(self, show)
        self._SaveUserParameters()
        if show and not self.painting.select(None, self.name):
            wx.MessageBox(
                "Please create or select a 3D surface.", "MEP Mapping", wx.OK | wx.ICON_INFORMATION
            )
            return False
        return True

    def start(self, surface, token):
        self.token = token
        self.surface = surface
        self.decimate_surface = surface.polydata
        self.surface_points = np.array(
            [
                self.decimate_surface.GetPoint(i)
                for i in range(self.decimate_surface.GetNumberOfPoints())
            ]
        )
        self.kdtree = cKDTree(self.surface_points)
        self.bounds = np.array(self.decimate_surface.GetBounds())
        self.points_polydata = vtkPolyData()
        self.marker_storage = []
        progress = dialogs.BrainSurfaceLoadingProgressWindow()
        try:
            progress.Update(value=20, msg="Preparing brain surface...")
            if self.brain_target_data is None:
                self.UpdateMEPPoints()
            else:
                self.UpdateMEPPointsFromBrainTargets(*self.brain_target_data)
        finally:
            progress.Close()
        Publisher.sendMessage("Press motor map button", pressed=True)

    def stop(self):
        self.token = None
        self.surface = None
        self.decimate_surface = None
        self.points_polydata = vtkPolyData()
        self.marker_storage = []
        self.bounds = None
        Publisher.sendMessage("Press motor map button", pressed=False)

    # --- Data Interpolation and Visualization ---

    def InterpolateData(self):
        polydata = self.decimate_surface
        points = self.points_polydata
        if not polydata:
            # TODO: Show modal dialog to select a surface from project
            return
        if not points:
            raise ValueError("MEP Visualizer: No point data found")
        if points.GetNumberOfPoints() == 0:
            empty = vtkPolyData()
            empty.ShallowCopy(polydata)
            scalars = vtkDoubleArray()
            scalars.SetName("MEP")
            scalars.SetNumberOfTuples(polydata.GetNumberOfPoints())
            scalars.FillComponent(0, 0)
            empty.GetPointData().SetScalars(scalars)
            return empty

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
        color_function.AddRGBPoint(0, *(np.array(const.CORTEX_COLOR) / 255.0))
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
        triangle_filter.SetInputData(self.surface.polydata)  # Use vtkPolyData directly
        triangle_filter.Update()  # Perform triangulation
        triangulated_polydata = triangle_filter.GetOutput()

        # Setup the decimation filter
        decimate_filter = vtkDecimatePro()
        decimate_filter.SetInputData(triangulated_polydata)
        decimate_filter.SetTargetReduction(0.6)  # Reduce the number of triangles by 60%
        decimate_filter.PreserveTopologyOn()  # Preserve the topology
        decimate_filter.Update()
        return decimate_filter.GetOutput()

    def SetBrainSurface(self, actor, index):
        self.painting.select(Project().surface_dict[index], self.name)

    def _FilterMarkers(self, markers_list):
        """
        Checks if the markers were updated and if those updated are of type coil_target
        """
        if not markers_list:
            return [], False

        # Convert to dicts for stable comparison
        markers = [m.to_dict() for m in markers_list]

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

    def projection_on_surface(self, position, orientation, step_size=5.0, max_steps=100):
        """
        Project a point along its orientation until it hits the brain surface.
        Then snap to nearest surface point via KDTree query.

        Parameters
        ----------
        position : (3,) array-like
            Initial 3D position of the point.
        orientation : (3,) array-like
            Euler angles (degrees).
        step_size : float
            Step size along orientation direction in mm.
        max_steps : int
            Maximum steps to take downward.
        """
        # === Build transform matrix ===
        a, b, g = np.radians(orientation[:3])
        r_ref = transformations.euler_matrix(a, b, g, axes="sxyz")
        t_ref = transformations.translation_matrix(position)
        m_point = transformations.concatenate_matrices(t_ref, r_ref)

        # Fix coordinate system
        m_point[1, -1] = -m_point[1, -1]

        # === Step 1: move downwards ===
        # Normal vector (coil z-axis in world coords)
        coil_normal = m_point[:3, 2]
        p = np.array(m_point[:3, -1])

        hit_point = None
        for _ in range(max_steps):
            # step down
            p = p - coil_normal * step_size
            # query distance to surface (cheap check)
            dist, idx = self.kdtree.query(p)
            if dist < step_size:  # close enough to surface
                hit_point = self.surface_points[idx]  # snap to surface vertex
                break

        if hit_point is None:
            # fallback: just return closest surface point
            dist, idx = self.kdtree.query(p)
            hit_point = self.surface_points[idx]

        return hit_point

    def UpdateMEPPoints(self):
        """
        Updates or creates the point data with MEP values from a list of markers.

        Args:
            markers (List[Marker]): The list of marker objects to add/update points for.
            clear_old (bool, default=False): If True, clears all existing points before updating.
        """
        if self.token is None:
            return
        if not self.surface:
            return

        self.brain_target_data = None
        markers, skip = self._FilterMarkers(MarkersControl().list)
        if skip:
            return
        if not markers:
            self.points_polydata = vtkPolyData()
            self.UpdateVisualization()
            return

        points = vtkPoints()

        point_data = self.points_polydata.GetPointData()
        mep_array = vtkDoubleArray()
        mep_array.SetName("MEP")
        point_data.AddArray(mep_array)

        for marker in markers:
            projected_point = self.projection_on_surface(marker.position, marker.orientation)
            if not marker.x_cortex and not marker.y_cortex and not marker.z_cortex:
                marker.cortex_position_orientation = [
                    projected_point[0],
                    -projected_point[1],
                    projected_point[2],
                    marker.orientation[0],
                    marker.orientation[1],
                    marker.orientation[2],
                ]

            points.InsertNextPoint(*projected_point)
            mep_value = marker.mep_value or 0
            mep_array.InsertNextValue(mep_value)
        MarkersControl().SaveState()

        self.points_polydata.SetPoints(points)
        self.points_polydata.GetPointData().SetActiveScalars("MEP")
        self.points_polydata.Modified()
        if self.token is not None:
            self.UpdateVisualization()

    def UpdateMEPPointsFromBrainTargets(self, marker_target, brain_target_list):
        """
        Updates or creates the point data with MEP values from a list of markers.

        Args:
            markers (List[Marker]): The list of marker objects to add/update points for.
            clear_old (bool, default=False): If True, clears all existing points before updating.
        """
        if self.token is None:
            return
        if not self.surface:
            return
        if marker_target.orientation is None or any(
            o is None for o in marker_target.orientation[:3]
        ):
            return
        self.brain_target_data = (marker_target, deepcopy(brain_target_list))
        brain_markers = []
        for m in brain_target_list:
            brain_markers.append(m)

        if not brain_markers:
            self.points_polydata = vtkPolyData()
            self.UpdateVisualization()
            return

        points = vtkPoints()

        point_data = self.points_polydata.GetPointData()
        mep_array = vtkDoubleArray()
        mep_array.SetName("MEP")
        point_data.AddArray(mep_array)

        for brain_marker in brain_markers:
            projected_point = self.projection_on_surface(
                brain_marker["position"], marker_target.orientation
            )
            points.InsertNextPoint(projected_point[0], projected_point[1], projected_point[2])
            mep_value = brain_marker["mep_value"] or 0
            mep_array.InsertNextValue(mep_value)
        MarkersControl().SaveState()

        self.points_polydata.SetPoints(points)
        self.points_polydata.GetPointData().SetActiveScalars("MEP")
        self.points_polydata.Modified()
        if self.token is not None:
            self.UpdateVisualization()

    def UpdateVisualization(self):
        if self.token is None or self.surface is None:
            return
        polydata = self.InterpolateData()
        self.painting.update(
            self.name,
            self.token,
            SurfaceMap(
                polydata,
                self._CustomColormap(),
                (self._config_params["threshold_down"], self._config_params["range_up"]),
                self.name,
                "\u00b5V",
            ),
        )

    def OnCloseProject(self):
        self.painting.set_available(self, False)
        self._config_params["mep_enabled"] = False
        self.brain_target_data = None
        self._SaveUserParameters()
