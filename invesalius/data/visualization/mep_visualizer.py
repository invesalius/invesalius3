import vtk
import numpy as np

import scipy.io
from vtkmodules.vtkCommonColor import vtkNamedColors
from vtkmodules.vtkCommonComputationalGeometry import vtkParametricTorus
from vtkmodules.vtkCommonCore import mutable, vtkPoints
from vtkmodules.vtkCommonDataModel import (
    vtkCellLocator,
    vtkIterativeClosestPointTransform,
    vtkPolyData,
)
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkCleanPolyData, vtkPolyDataNormals, vtkAppendPolyData
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkFiltersSources import (
    vtkArrowSource,
    vtkCylinderSource,
    vtkParametricFunctionSource,
    vtkRegularPolygonSource,
    vtkSphereSource,
)
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleTrackballActor,
    vtkInteractorStyleTrackballCamera,
)
from vtkmodules.vtkIOGeometry import vtkOBJReader, vtkSTLReader
from vtkmodules.vtkIOPLY import vtkPLYReader
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkCellPicker,
    vtkFollower,
    vtkPolyDataMapper,
    vtkProperty,
    vtkRenderer,
)
from vtkmodules.vtkIOImage import vtkPNGWriter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkRenderWindow,
    vtkRenderWindowInteractor,
    vtkRenderer,
    vtkWindowToImageFilter
)

from vtkmodules.vtkRenderingFreeType import vtkVectorText
from vtkmodules.wx.wxVTKRenderWindowInteractor import wxVTKRenderWindowInteractor
import time

from invesalius.data.markers.marker import Marker


class MEPVisualizer:

    def __init__(self, renderer, interactor):
        self.points = None
        self.surface = self.read_surface_data(actor_out=True)

        # configuration variables
        self.threshold_down = 0
        self.range_up = 1
        self.dims_size = 100
        self.gaussain_sharpness = .4
        self.gaussian_radius = 10
        self.bounds = None
        self.test_data_filename = 'data/MEP_data.txt'

        self.renderer = renderer
        self.interactor = interactor

        self.render_visualization()

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
        output.GetPointData().SetActiveScalars('MEP')

        return output

    def interpolate_data(self):
        """Interpolates point data onto a 3D grid and resamples the surface."""

        surface = self.surface
        points = self.points

        bounds = np.array(self.bounds)
        gaussian_sharpness = self.gaussain_sharpness
        gaussian_radius = self.gaussian_radius
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
        lut.SetTableRange(self.threshold_down, self.range_up)
        colorSeries = vtk.vtkColorSeries()
        seriesEnum = colorSeries.BREWER_SEQUENTIAL_YELLOW_ORANGE_BROWN_9
        colorSeries.SetColorScheme(seriesEnum)

        colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
        lut_map = vtk.vtkLookupTable()
        lut_map.DeepCopy(lut)
        # lut_map.SetTableValue(0, 1., 1., 1., 0.)
        lut_map.Build()
        return lut_map

    def update_surface_map(self, markers=None, clear_old=True):
        ''' Update the surface map based on the markers array '''
        # convert marker obj array to points we can process
        # TODO: this implementation should be updated and not be dependent on saving to text file
        if markers is not None:
            # check if only one marker is given
            if not isinstance(markers, list):
                markers = [markers]

            points = vtk.vtkPoints()
            for marker in markers:

                points.InsertNextPoint(marker.position)
            self.points_data = points

        # interpolate the data
        interpolated_data = self.interpolate_data()

        # create the map based on the given markers
        actor = self.create_colored_surface(interpolated_data)
        # point_actor = self.create_point_actor(self.points_data, self.data_range)

        # update the brain surface actor with the new mapping
        self.renderer.RemoveActor(self.surface)
        self.surface = actor
        self.renderer.AddActor(self.surface)

    def create_colorbar_actor(self, lut=None) -> vtk.vtkActor:
        if lut is None:
            lut = self.lut_setup()
        colorBarActor = vtk.vtkScalarBarActor()
        colorBarActor.SetLookupTable(lut)
        colorBarActor.SetNumberOfLabels(3)
        colorBarActor.SetLabelFormat("%4.2f")
        colorBarActor.SetTitle("MEP amplitude µV\n")

        # FIXME: Set the label text size to be a little bit smaller
        label_text_property = colorBarActor.GetLabelTextProperty()
        label_text_property.SetFontSize(5)
        # label_text_property.SetColor(0, 0, 0)

        colorBarActor.SetLabelTextProperty(label_text_property)

        # resize colorbar
        colorBarActor.SetWidth(0.1)
        colorBarActor.SetHeight(0.3)

        colorBarActor.SetVisibility(1)
        return colorBarActor

    def create_colored_surface(self, poly_data) -> vtk.vtkActor:
        """Creates the actor for the surface with color mapping."""
        normals = vtkPolyDataNormals()
        normals.SetInputData(poly_data)
        normals.ComputePointNormalsOn()
        normals.ComputeCellNormalsOff()
        normals.Update()

        data_range = (self.threshold_down, self.range_up)

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(normals.GetOutput())
        if data_range is None:
            data_range = (self.threshold_down, self.range_up)
        mapper.SetScalarRange(data_range)

        lut = self.lut_setup()
        mapper.SetLookupTable(lut)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetInterpolationToGouraud()
        return actor

    def set_surface_actor(self, surface_actor):
        # select the surface actor to overlay the mapping on
        self.surface = surface_actor
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

    def render_visualization(self):

        # Read data
        surface = self.surface
        self.bounds = np.array(surface.GetBounds())
        points = self.read_point_data()

        # Calculate data range and dims
        range_up = points.GetPointData().GetScalars().GetRange()[1]
        data_range = (self.threshold_down, self.range_up)
        dims = np.array([self.dims_size, self.dims_size, self.dims_size])

        # Interpolate and create actors (initially)
        interpolated_data = self.interpolate_data()
        actor = self.create_colored_surface(interpolated_data)
        point_actor = self.create_point_actor(points, data_range)

        # Colorbar setup
        colorBarActor = self.create_colorbar_actor()

        # Renderer setup
        self.renderer.AddActor(actor)
        self.renderer.AddActor(point_actor)
        self.renderer.AddActor(colorBarActor)

        # Picker for mouse interaction
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)
        picker.AddPickList(actor)  # Pick only on the surface actor
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
