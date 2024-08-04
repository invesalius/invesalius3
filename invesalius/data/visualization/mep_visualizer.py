
import invesalius.session as ses
from invesalius.pubsub import pub as Publisher
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
import vtk
import numpy as np


from vtkmodules.vtkIOGeometry import vtkSTLReader
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPointPicker,
    vtkPolyDataMapper,
    vtkProperty,
    vtkPropPicker,
    vtkRenderer,
    vtkWindowToImageFilter,
)
from invesalius.data.markers.marker import Marker

import random
import invesalius.constants as const

from copy import deepcopy


class MEPVisualizer:
    # TODO: find a way to not duplicate the brain actor
    # TODO: enable/disable colormapping based on toggle button
    # TODO: update config from prefrences

    def __init__(self, renderer: vtkRenderer, interactor):
        self._bind_events()
        self.points = vtk.vtkPolyData()
        self.surface = self.read_surface_data(actor_out=True)

        self.enabled = False
        self.dims_size = 100

        self._config_params = deepcopy(const.DEFAULT_MEP_CONFIG_PARAMS)
        self._load_user_parameters()

        self.renderer = renderer
        # self.mep_renderer = vtk.vtkRenderer() # Renderer for the MEP points, separated to not affect other actors
        self.mep_renderer = renderer
        self.interactor = interactor

    def _load_user_parameters(self):
        session = ses.Session()

        config = session.GetConfig('mep_configuration')
        if config is not None:
            self._config_params.update(config)
        else:
            session.SetConfig('mep_configuration', self._config_params)

    def _reset_config_params(self):
        session = ses.Session()
        session.SetConfig('mep_configuration', deepcopy(
            const.DEFAULT_MEP_CONFIG_PARAMS))

    def _save_user_parameters(self):
        session = ses.Session()
        session.SetConfig('mep_configuration', self._config_params)

    def _bind_events(self):
        # Publisher.subscribe(self.update_mep_points, 'Update MEP Points')
        Publisher.subscribe(self.display_motor_map, 'Show motor map')
        Publisher.subscribe(self._reset_config_params, 'Reset MEP Config')
        Publisher.subscribe(self.update_config, 'Save Preferences')

    def update_config(self):
        session = ses.Session()
        self._config_params = deepcopy(session.GetConfig('mep_configuration'))
        self.update_mep_points([], clear_old=False) # Just redraw without clearing old markers
        # self.render_visualization(self.surface)

    def display_motor_map(self, show: bool):
        """Controls the display of the motor map and enables/disables the MEP mapping."""
        if show:
            self._config_params["mep_enabled"] = True
            self._config_params["enabled_once"] = True
            # self.render_visualization(self.surface)
            self.mep_renderer.AddActor(self.colorBarActor)
            self.mep_renderer.AddActor(self.surface)
            # TODO: hide the surface actor by triggering a hide event
        else:
            self._config_params["mep_enabled"] = False
            if hasattr(self, 'colorBarActor'):  # Ensure it exists before removal
                self.mep_renderer.RemoveActor(self.colorBarActor)
                self.mep_renderer.RemoveActor(self.surface)
                print("Current actors: ", self.mep_renderer.GetActors())
            # FIXME: The colorbar actor wont get removed for some reason..

                # Remove all actors from the target guide renderer.
                # actors = self.mep_renderer.GetActors()
                # actors.InitTraversal()
                # actor = actors.GetNextItem()
                # while actor:
                #     if actor == self.surface:  # Skip the surface actor
                #         actor = actors.GetNextItem()
                #     self.mep_renderer.RemoveActor(actor)
                #     actor = actors.GetNextItem()

            # self.mep_renderer.RemoveActor(self.surface)

        self._save_user_parameters()
        self.interactor.Render()

    def read_surface_data(self, filename='data/T1.stl', actor_out=False):
        """Reads the surface data from an STL file."""
        reader = vtkSTLReader()
        reader.SetFileName(filename)
        reader.Update()
        output = reader.GetOutput()
        if actor_out:
            actor = vtk.vtkActor()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(output)
            actor.SetMapper(mapper)
            return actor
        return output

    def read_point_data(self, filename='D:/tms_mep_visualization/data/MEP_data.txt'):
        """Reads point data (coordinates and MEP amplitudes) from a text file."""
        reader = vtk.vtkDelimitedTextReader()
        reader.SetFileName(filename)
        reader.DetectNumericColumnsOn()
        reader.SetFieldDelimiterCharacters('\t')
        reader.SetHaveHeaders(True)

        table_points = vtk.vtkTableToPolyData()
        table_points.SetInputConnection(reader.GetOutputPort())
        table_points.SetXColumnIndex(0)
        table_points.SetYColumnIndex(1)
        table_points.SetZColumnIndex(2)
        table_points.Update()

        output = table_points.GetOutput()
        # Table points are now converted to polydata and MEP is the active scalar
        output.GetPointData().SetActiveScalars('MEP')

        return output

    def interpolate_data(self):
        """Interpolates point data onto a 3D grid and resamples the surface."""

        surface = self.surface
        points = self.points

        bounds = np.array(self._config_params['bounds'])
        gaussian_sharpness = self._config_params['gaussian_sharpness']
        gaussian_radius = self._config_params['gaussian_radius']
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

    def lut_setup(self):
        lut = vtk.vtkLookupTable()
        # lut.SetTableRange(self._config_params.threshold_down, self._config_params.range_up)
        lut.SetTableRange(
            self._config_params['colormap_range_uv']["min"],  self._config_params['colormap_range_uv']["max"])
        lut.SetNumberOfTableValues(4)
        colorSeries = vtk.vtkColorSeries()

        # FIXME: Add your custom colors
        # from vtkmodules.vtkCommonDataModel import vtkColor3ub
        # colorSeries.AddColor(vtkColor3ub(0, 0, 255))   # Blue
        # colorSeries.AddColor(vtkColor3ub(0, 255, 0))   # Green
        # colorSeries.AddColor(vtkColor3ub(255, 255, 0))   # Yellow
        # colorSeries.AddColor(vtkColor3ub(255, 0, 0))   # Red
        seriesEnum = colorSeries.BREWER_SEQUENTIAL_YELLOW_ORANGE_BROWN_9
        colorSeries.SetColorScheme(seriesEnum)

        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        lut_map = vtk.vtkLookupTable()
        lut_map.DeepCopy(lut)
        # lut_map.SetTableValue(0, 1., 1., 1., 0.)
        lut_map.Build()
        return lut_map

    def update_mep_points(self, markers: list[Marker], clear_old=True):
        """Updates or creates the point data with MEP values from a list of markers.

        Args:
            markers (List[Marker]): The list of marker objects to add/update points for.
            clear_old (bool, default=False): If True, clears all existing points before updating.
        """

        points = self.points.GetPoints()

        if clear_old:
            self.points.SetPoints(vtk.vtkPoints())
            points = self.points.GetPoints()
            # remove old actors
            self._cleanup_visualization()

        # 1. Get or create the points data structure
        if points is None:
            points = vtk.vtkPoints()
            print('Added new points object')
        elif points.GetNumberOfPoints() == 0 or clear_old:
            # print('No points found or clear_old is True')
            self.points.SetPoints(vtk.vtkPoints())
            points = self.points.GetPoints()
        else:
            print(
                f'Current point count is now {points.GetNumberOfPoints()} points')

        # 2. Add or update MEP values for each marker
        point_data = self.points.GetPointData()
        mep_array = point_data.GetArray('MEP')

        if not mep_array:
            mep_array = vtk.vtkDoubleArray()
            mep_array.SetName('MEP')
            point_data.AddArray(mep_array)

        for marker in markers:
            # 3. Create a new point (vtkIdType is VTK's integer type for point IDs)
            new_point_id = points.GetNumberOfPoints()  # Get the ID of the next point
            # points.InsertNextPoint(marker.position)
            points.InsertNextPoint(
                marker.position[0], -marker.position[1], marker.position[2])

            # 4. Generate a random MEP value (Or get it from marker object)
            if hasattr(marker, "mep_value"):
                mep_value = marker.mep_value
                if mep_value is None:
                    # mep_value = 0
                    # Adjust range as needed
                    mep_value = random.uniform(
                        0,  self._config_params['colormap_range_uv']["max"]) / self._config_params['colormap_range_uv']["max"]
                    self.mep_value = mep_value  # Save the value for later
            # 5. Add the MEP value to the 'MEP' array
            mep_array.InsertNextValue(mep_value)

        # Update points data
        self.points.SetPoints(points)
        self.points.GetPointData().SetActiveScalars('MEP')
        self.points.Modified()

        # 6. (Optional) If visualization needs an immediate update
        # self.render_visualization(self.surface)

    def update_surface_map(self):
        ''' Update the surface map based on the markers array '''
        if self.enabled is False:  # Skips processing if MEP mapping is disabled
            return
        # interpolate the data
        interpolated_data = self.interpolate_data()

        # create the map based on the given markers
        actor = self.create_colored_surface(interpolated_data)
        # point_actor = self.create_point_actor(self.points_data, self.data_range)

        # update the brain surface actor with the new mapping
        self.mep_renderer.RemoveActor(self.surface)
        self.surface = self.set_surface_actor(actor)
        self.mep_renderer.AddActor(self.surface)

    def create_colorbar_actor(self, lut=None) -> vtk.vtkActor:
        if lut is None:
            lut = self.lut_setup()
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
        return colorBarActor

    def create_colored_surface(self, poly_data) -> vtk.vtkActor:
        """Creates the actor for the surface with color mapping."""
        normals = vtkPolyDataNormals()
        normals.SetInputData(poly_data)
        normals.ComputePointNormalsOn()
        normals.ComputeCellNormalsOff()
        normals.Update()

        data_range = (
            self._config_params['threshold_down'],  self._config_params['range_up'])

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        if data_range is None:
            data_range = (
                self._config_params['threshold_down'],  self._config_params['range_up'])
        mapper.SetScalarRange(data_range)

        lut = self.lut_setup()
        mapper.SetLookupTable(lut)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetInterpolationToGouraud()
        return actor

    def set_surface_actor(self, surface_actor):
        # select the surface actor to overlay the mapping on
        # deep copy
        from copy import deepcopy
        self.surface = deepcopy(surface_actor)
        # re render or do the mapping?
        # TODO: not sure yet
        pass

    def create_point_actor(self, points, data_range):
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

        lut = self.lut_setup()
        point_mapper.SetLookupTable(lut)

        point_actor = vtkActor()
        point_actor.SetMapper(point_mapper)
        return point_actor

    def _cleanup_visualization(self):
        """Removes all actors from the renderer except the initial surface."""
        actors = self.mep_renderer.GetActors()
        actors.InitTraversal()
        actor = actors.GetNextItem()
        while actor:
            if actor == self.surface:
                actor = actors.GetNextItem()
            self.mep_renderer.RemoveActor(actor)
            actor = actors.GetNextItem()

    def render_visualization(self, surface):

        # Read data
        if surface is None:
            print('No surface data found')
            return
        self.surface = surface
        self._config_params['bounds'] = list(np.array(surface.GetBounds()))
        # points = self.read_point_data()
        points = self.points

        # Calculate data range and dims
        range_up = points.GetPointData().GetScalars().GetRange()[1]
        data_range = (
            self._config_params['threshold_down'], self._config_params['range_up'])
        dim_size = self.dims_size
        dims = np.array(
            [dim_size, dim_size, dim_size])  # Number of points in each dimension

        # Interpolate and create actors (initially)
        interpolated_data = self.interpolate_data()
        self.colored_surface = self.create_colored_surface(interpolated_data)
        point_actor = self.create_point_actor(points, data_range)

        # Colorbar setup
        self.colorBarActor = self.create_colorbar_actor()

        # Renderer setup
        self.mep_renderer.AddActor(self.colored_surface)
        self.mep_renderer.AddActor(point_actor)
        self.mep_renderer.AddActor(self.colorBarActor)

        # Picker for mouse interaction
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)
        # picker.AddPickList(actor)  # Pick only on the surface actor
        picker.PickFromListOn()

        # Start the interactor
        # iren.Start()


def add_points_to_file(filename, new_coords, points_range):
    """Appends new points and MEP values to the text file."""
    new_mep_values = np.random.uniform(
        points_range[0], points_range[1], len(new_coords))
    # Combine coordinates and MEPs
    new_data = np.hstack((new_coords, new_mep_values[:, np.newaxis]))
    with open(filename, 'a') as f:
        np.savetxt(f, new_data, delimiter='\t', fmt='%f')  # Append to file
