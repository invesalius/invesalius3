import numpy as np
import pyacvd

# import os
import pyvista
from vtkmodules.vtkCommonColor import vtkColorSeries

# import Trekker
from vtkmodules.vtkCommonCore import (
    vtkFloatArray,
    vtkLookupTable,
)
from vtkmodules.vtkCommonDataModel import (
    vtkCellLocator,
    vtkDataObject,
    vtkDataSetAttributes,
    vtkPointLocator,
    vtkPolyData,
)
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import (
    vtkCellCenters,
    vtkCleanPolyData,
    vtkContourFilter,
    vtkPolyDataNormals,
    vtkProbeFilter,
    vtkTriangleFilter,
    vtkWindowedSincPolyDataFilter,
)
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter, vtkWarpVector
from vtkmodules.vtkFiltersModeling import vtkLinearSubdivisionFilter
from vtkmodules.vtkImagingCore import vtkImageFlip
from vtkmodules.vtkIOImage import vtkNIFTIImageReader
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkTextProperty,
    vtkWindowLevelLookupTable,
)

import invesalius.data.slice_ as sl
import invesalius.data.vtk_utils as vtk_utils
import invesalius.project as prj
from invesalius.data.converters import to_vtk


class Brain:
    def __init__(self, n_peels, window_width, window_level, affine, inv_proj):
        # Create arrays to access the peel data and peel Actors
        self.peel = []
        self.peelActors = []
        self.window_width = window_width
        self.window_level = window_level
        self.numberOfPeels = n_peels
        self.affine = affine
        self.inv_proj = inv_proj

    def from_mask(self, mask):
        mask = np.array(mask.matrix[1:, 1:, 1:])
        slic = sl.Slice()
        image = slic.matrix

        mask = to_vtk(mask, spacing=slic.spacing)
        image = to_vtk(image, spacing=slic.spacing)

        flip = vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()
        image = flip.GetOutput()

        flip = vtkImageFlip()
        flip.SetInputData(mask)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()
        mask = flip.GetOutput()

        # Image
        self.refImage = image

        self._do_surface_creation(mask)

    def from_mask_file(self, mask_path):
        slic = sl.Slice()
        image = slic.matrix
        image = np.flip(image, axis=1)
        image = to_vtk(image, spacing=slic.spacing)

        # Read the mask
        mask_reader = vtkNIFTIImageReader()
        mask_reader.SetFileName(mask_path)
        mask_reader.Update()

        mask = mask_reader.GetOutput()

        mask_sFormMatrix = mask_reader.GetSFormMatrix()

        # Image
        self.refImage = image

        self._do_surface_creation(mask, mask_sFormMatrix)

    def _do_surface_creation(self, mask, mask_sFormMatrix=None):
        if mask_sFormMatrix is None:
            mask_sFormMatrix = vtkMatrix4x4()

        value = np.mean(mask.GetScalarRange())

        # Use the mask to create isosurface
        mc = vtkContourFilter()
        mc.SetInputData(mask)
        mc.SetValue(0, value)
        mc.ComputeNormalsOn()
        mc.Update()

        # Mask isosurface
        refSurface = mc.GetOutput()

        # Create a uniformly meshed surface
        tmpPeel = downsample(refSurface)
        # Standard space coordinates

        # Apply coordinate transform to the meshed mask
        mask_ijk2xyz = vtkTransform()
        mask_ijk2xyz.SetMatrix(mask_sFormMatrix)

        mask_ijk2xyz_filter = vtkTransformPolyDataFilter()
        mask_ijk2xyz_filter.SetInputData(tmpPeel)
        mask_ijk2xyz_filter.SetTransform(mask_ijk2xyz)
        mask_ijk2xyz_filter.Update()

        # Smooth the mesh
        tmpPeel = smooth(mask_ijk2xyz_filter.GetOutput())
        # Configure calculation of normals
        tmpPeel = fixMesh(tmpPeel)
        # Remove duplicate points etc
        # tmpPeel = cleanMesh(tmpPeel)
        # Generate triangles
        tmpPeel = upsample(tmpPeel)

        tmpPeel = smooth(tmpPeel)
        tmpPeel = fixMesh(tmpPeel)
        tmpPeel = cleanMesh(tmpPeel)

        refImageSpace2_xyz_transform = vtkTransform()
        refImageSpace2_xyz_transform.SetMatrix(
            vtk_utils.numpy_to_vtkMatrix4x4(np.linalg.inv(self.affine))
        )

        self.refImageSpace2_xyz = vtkTransformPolyDataFilter()
        self.refImageSpace2_xyz.SetTransform(refImageSpace2_xyz_transform)

        xyz2_refImageSpace_transform = vtkTransform()
        xyz2_refImageSpace_transform.SetMatrix(vtk_utils.numpy_to_vtkMatrix4x4(self.affine))

        self.xyz2_refImageSpace = vtkTransformPolyDataFilter()
        self.xyz2_refImageSpace.SetTransform(xyz2_refImageSpace_transform)

        currentPeel = tmpPeel
        self.currentPeelNo = 0
        currentPeel = self.MapImageOnCurrentPeel(currentPeel)

        newPeel = vtkPolyData()
        newPeel.DeepCopy(currentPeel)
        newPeel.DeepCopy(currentPeel)
        self.peel_normals = vtkFloatArray()
        self.peel_centers = vtkFloatArray()
        self.peel.append(newPeel)
        self.currentPeelActor = vtkActor()
        if not np.all(np.equal(self.affine, np.eye(4))):
            affine_vtk = self.CreateTransformedVTKAffine()
            self.currentPeelActor.SetUserMatrix(affine_vtk)
        self.GetCurrentPeelActor(currentPeel)
        self.peelActors.append(self.currentPeelActor)
        # locator will later find the triangle on the peel surface where the coil's normal intersect
        self.locator = vtkCellLocator()
        self.PeelDown(currentPeel)

    def CreateTransformedVTKAffine(self):
        # Consistent with transformation applied in navigation.py under StartNavigation
        # accounts for non-unitary pixel spacing and transforms to invesalius 3D viewer
        # coordinate space
        prj_data = prj.Project()
        matrix_shape = tuple(prj_data.matrix_shape)
        spacing = tuple(prj_data.spacing)
        affine_inv_space = self.affine.copy()
        affine_inv_space[1, -1] -= spacing[1] * (matrix_shape[1] - 1)

        return vtk_utils.numpy_to_vtkMatrix4x4(affine_inv_space)

    def get_actor(self, n):
        return self.GetPeelActor(n)

    def SliceDown(self, currentPeel):
        # Warp using the normals
        warp = vtkWarpVector()
        warp.SetInputData(
            fixMesh(downsample(currentPeel))
        )  # fixMesh here updates normals needed for warping
        warp.SetInputArrayToProcess(
            0, 0, 0, vtkDataObject().FIELD_ASSOCIATION_POINTS, vtkDataSetAttributes().NORMALS
        )
        warp.SetScaleFactor(-1)
        warp.Update()

        out = vtkPolyData()
        out = upsample(warp.GetPolyDataOutput())
        out = smooth(out)
        out = fixMesh(out)
        out = cleanMesh(out)

        currentPeel = out
        return currentPeel

    # def sliceUp(self):
    #     # Warp using the normals
    #     warp = vtkWarpVector()
    #     # warp.SetInputData(fixMesh(downsample(currentPeel))) # fixMesh here updates normals needed for warping
    #     warp.SetInputArrayToProcess(0, 0, 0, vtkDataObject().FIELD_ASSOCIATION_POINTS,
    #                                 vtkDataSetAttributes().NORMALS)
    #     warp.SetScaleFactor(1)
    #     warp.Update()
    #
    #     out = vtkPolyData()
    #     out = upsample(warp.GetPolyDataOutput())
    #     out = smooth(out)
    #     out = fixMesh(out)
    #     out = cleanMesh(out)
    #
    #     currentPeel = out

    def MapImageOnCurrentPeel(self, currentPeel):
        self.xyz2_refImageSpace.SetInputData(currentPeel)
        self.xyz2_refImageSpace.Update()

        probe = vtkProbeFilter()
        probe.SetInputData(self.xyz2_refImageSpace.GetOutput())
        probe.SetSourceData(self.refImage)
        probe.Update()

        self.refImageSpace2_xyz.SetInputData(probe.GetOutput())
        self.refImageSpace2_xyz.Update()

        currentPeel = self.refImageSpace2_xyz.GetOutput()
        return currentPeel

    def PeelDown(self, currentPeel):
        for i in range(0, self.numberOfPeels):
            currentPeel = self.SliceDown(currentPeel)
            currentPeel = self.MapImageOnCurrentPeel(currentPeel)

            newPeel = vtkPolyData()
            newPeel.DeepCopy(currentPeel)
            self.peel.append(newPeel)

            # GetCurrentPeelActor()
            # newPeelActor = vtkActor()
            # newPeelActor = currentPeelActor
            # peelActors.push_back(newPeelActor)

            self.currentPeelNo += 1

    def TransformPeelPosition(self, p):
        peel_transform = vtkTransform()
        if not np.all(np.equal(self.affine, np.eye(4))):
            affine_vtk = self.CreateTransformedVTKAffine()
            peel_transform.SetMatrix(affine_vtk)
        refpeelspace = vtkTransformPolyDataFilter()
        refpeelspace.SetInputData(self.peel[p])
        refpeelspace.SetTransform(peel_transform)
        refpeelspace.Update()
        currentPeel = refpeelspace.GetOutput()
        return currentPeel

    def GetPeelActor(self, p):
        lut = vtkWindowLevelLookupTable()
        lut.SetWindow(self.window_width)
        lut.SetLevel(self.window_level)
        lut.Build()

        init = self.window_level - self.window_width / 2
        end = self.window_level + self.window_width / 2

        # Set mapper auto
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(self.peel[p])
        mapper.SetScalarRange(init, end)
        mapper.SetLookupTable(lut)
        mapper.InterpolateScalarsBeforeMappingOn()

        # Set actor
        self.currentPeelActor.SetMapper(mapper)

        currentPeel = self.TransformPeelPosition(p)

        self.locator.SetDataSet(currentPeel)
        self.locator.BuildLocator()
        self.peel_centers = GetCenters(currentPeel)
        self.peel_normals = GetNormals(currentPeel)

        return self.currentPeelActor

    def GetCurrentPeelActor(self, currentPeel):
        lut = vtkWindowLevelLookupTable()
        lut.SetWindow(self.window_width)
        lut.SetLevel(self.window_level)
        lut.Build()

        init = self.window_level - self.window_width / 2
        end = self.window_level + self.window_width / 2

        # Set mapper auto
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(currentPeel)
        mapper.SetScalarRange(init, end)
        mapper.SetLookupTable(lut)
        mapper.InterpolateScalarsBeforeMappingOn()

        # Set actor
        self.currentPeelActor.SetMapper(mapper)
        self.currentPeelActor.GetProperty().SetBackfaceCulling(1)
        self.currentPeelActor.GetProperty().SetOpacity(0.5)
        self.currentPeelActor.GetProperty().SetSpecular(0.25)

        return self.currentPeelActor


class E_field_brain:
    def __init__(self, mesh):
        self.GetEfieldActor(mesh)

    def GetEfieldActor(self, mesh):
        self.e_field_mesh_normals = vtkFloatArray()
        self.e_field_mesh_centers = vtkFloatArray()

        self.locator_efield_Cell = vtkCellLocator()
        self.locator_efield_Cell.SetDataSet(mesh)
        self.locator_efield_Cell.BuildLocator()

        self.locator_efield = vtkPointLocator()
        self.locator_efield.SetDataSet(mesh)
        self.locator_efield.BuildLocator()

        self.e_field_mesh_normals = GetNormals(mesh)
        self.e_field_mesh_centers = GetCenters(mesh)
        self.e_field_mesh = mesh

        self.efield_mapper = vtkPolyDataMapper()

        text_property = vtkTextProperty()
        text_property.SetFontSize(3)
        text_property.SetJustificationToCentered()

        self.efield_scalar_bar = vtkScalarBarActor()
        self.efield_scalar_bar.SetOrientationToVertical()
        self.efield_scalar_bar.SetTitle("E (V/m)")
        self.efield_scalar_bar.SetNumberOfLabels(2)
        self.efield_scalar_bar.SetTitleTextProperty(text_property)
        # self.lut = CreateLUTTableForEfield(0, 0.005)


class Scalp:
    def __init__(self, mesh):
        self.mesh_normals = vtkFloatArray()
        self.mesh_centers = vtkFloatArray()

        self.locator_Cell = vtkCellLocator()
        self.locator_Cell.SetDataSet(mesh)
        self.locator_Cell.BuildLocator()

        self.locator = vtkPointLocator()
        self.locator.SetDataSet(mesh)
        self.locator.BuildLocator()

        self.mesh_normals = GetNormals(mesh)
        self.mesh_centers = GetCenters(mesh)


def GetCenters(mesh):
    # Compute centers of triangles
    centerComputer = vtkCellCenters()  # This computes centers of the triangles on the peel
    centerComputer.SetInputData(mesh)
    centerComputer.Update()

    # This stores the centers for easy access
    centers = centerComputer.GetOutput()
    return centers


def GetNormals(mesh):
    # Compute normals of triangles
    normalComputer = vtkPolyDataNormals()  # This computes normals of the triangles on the peel
    normalComputer.SetInputData(mesh)
    normalComputer.ComputePointNormalsOff()
    normalComputer.ComputeCellNormalsOn()
    normalComputer.Update()
    # This converts to the normals to an array for easy access
    normals = normalComputer.GetOutput().GetCellData().GetNormals()
    return normals


def CreateLUTTableForEfield(min, max):
    lut = vtkLookupTable()
    lut.SetTableRange(min, max)
    colorSeries = vtkColorSeries()
    seriesEnum = colorSeries.BREWER_SEQUENTIAL_YELLOW_ORANGE_BROWN_9
    colorSeries.SetColorScheme(seriesEnum)
    colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
    return lut


def cleanMesh(inp):
    cleaned = vtkCleanPolyData()
    cleaned.SetInputData(inp)
    cleaned.Update()

    return cleaned.GetOutput()


def fixMesh(inp):
    normals = vtkPolyDataNormals()
    normals.SetInputData(inp)
    normals.SetFeatureAngle(160)
    normals.SplittingOn()
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()

    return normals.GetOutput()


def upsample(inp):
    triangles = vtkTriangleFilter()
    triangles.SetInputData(inp)
    triangles.Update()

    subdivisionFilter = vtkLinearSubdivisionFilter()
    subdivisionFilter.SetInputData(triangles.GetOutput())
    subdivisionFilter.SetNumberOfSubdivisions(2)
    subdivisionFilter.Update()

    return subdivisionFilter.GetOutput()


def smooth(inp):
    smoother = vtkWindowedSincPolyDataFilter()
    smoother.SetInputData(inp)
    smoother.SetNumberOfIterations(20)
    smoother.BoundarySmoothingOn()
    smoother.FeatureEdgeSmoothingOn()
    smoother.SetFeatureAngle(175)
    smoother.SetPassBand(0.1)
    smoother.NonManifoldSmoothingOn()
    smoother.NormalizeCoordinatesOn()
    smoother.Update()

    return smoother.GetOutput()


def downsample(inp):
    # surface = vtkSurface()
    # surface.CreateFromPolyData(inp)
    #
    # areas = vtkDoubleArray()
    # areas = surface.GetTrianglesAreas()
    # surfaceArea = 0
    #
    # for i in range(0, areas.GetSize()):
    #     surfaceArea += areas.GetValue(i)
    #
    # clusterNumber = surfaceArea / 20

    mesh = pyvista.PolyData(inp)

    # Create clustering object
    clus = pyacvd.Clustering(mesh)
    # mesh is not dense enough for uniform remeshing
    # clus.subdivide(3)
    clus.cluster(3000)
    Remesh = clus.create_mesh()

    # print(Remesh)

    # Remesh = vtkIsotropicDiscreteRemeshing()
    # Remesh.SetInput(surface)
    # Remesh.SetFileLoadSaveOption(0)
    # Remesh.SetNumberOfClusters(clusterNumber)
    # Remesh.SetConsoleOutput(0)
    # Remesh.GetMetric().SetGradation(0)
    # Remesh.SetDisplay(0)
    # Remesh.Remesh()

    # out = vtkPolyData()
    # out.SetPoints(Remesh.GetOutput().GetPoints())
    # out.SetPolys(Remesh.GetOutput().GetPolys())

    return Remesh
