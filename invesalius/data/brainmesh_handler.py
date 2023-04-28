import pyacvd
import pyvista
import numpy as np
from typing import Tuple, List, Dict, Any, Union, Optional, overload
from vtkmodules.vtkCommonCore import vtkFloatArray
from vtkmodules.vtkCommonDataModel import (
    vtkCellLocator,
    vtkDataObject,
    vtkDataSetAttributes,
    vtkPolyData,
    vtkPointLocator,
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
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkWindowLevelLookupTable,
)
from vtkmodules.vtkCommonCore import (
    vtkLookupTable,
)
from vtkmodules.vtkCommonColor import (
    vtkColorSeries,
    vtkNamedColors
)
#import for vtkImageData
from vtkmodules.vtkCommonDataModel import (
    vtkImageData,
)
import invesalius.data.slice_ as sl
from invesalius.data.converters import to_vtk
import invesalius.data.vtk_utils as vtk_utils

class Brain:
    def __init__(self, n_peels: int, window_width: float, window_level: float, affine: np.ndarray, inv_proj: np.ndarray):
        # Create arrays to access the peel data and peel Actors
        self.peel: list = []
        self.peelActors: list = []
        self.window_width: float = window_width
        self.window_level: float = window_level
        self.numberOfPeels: int = n_peels
        self.affine: np.ndarray = affine
        self.inv_proj: np.ndarray = inv_proj

    def from_mask(self, mask: np.ndarray) -> None:
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
        self.refImage: vtkDataObject = image

        self._do_surface_creation(mask)


    def from_mask_file(self, mask_path: str) -> None:
            slic = sl.Slice()
            image: np.ndarray = slic.matrix
            image = np.flip(image, axis=1)
            image = to_vtk(image, spacing=slic.spacing)
    
            # Read the mask
            mask_reader: vtkNIFTIImageReader = vtkNIFTIImageReader()
            mask_reader.SetFileName(mask_path)
            mask_reader.Update()
    
            mask: vtkImageData = mask_reader.GetOutput()
    
            mask_sFormMatrix: vtkMatrix4x4 = mask_reader.GetSFormMatrix()
    
            # Image
            self.refImage: vtkImageData = image
    
            self._do_surface_creation(mask, mask_sFormMatrix)
    
    
    def _do_surface_creation(self, mask: vtkImageData, mask_sFormMatrix: Optional[vtkMatrix4x4] = None) -> None:
        if mask_sFormMatrix is None:
            mask_sFormMatrix = vtkMatrix4x4()

        value: float = np.mean(mask.GetScalarRange())

        # Use the mask to create isosurface
        mc: vtkContourFilter = vtkContourFilter()
        mc.SetInputData(mask)
        mc.SetValue(0, value)
        mc.ComputeNormalsOn()
        mc.Update()

        # Mask isosurface
        refSurface: vtkPolyData = mc.GetOutput()

        # Create a uniformly meshed surface
        tmpPeel: vtkPolyData = downsample(refSurface)
        # Standard space coordinates

        # Apply coordinate transform to the meshed mask
        mask_ijk2xyz: vtkTransform = vtkTransform()
        mask_ijk2xyz.SetMatrix(mask_sFormMatrix)

        mask_ijk2xyz_filter: vtkTransformPolyDataFilter = vtkTransformPolyDataFilter()
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

        refImageSpace2_xyz_transform: vtkTransform = vtkTransform()
        refImageSpace2_xyz_transform.SetMatrix(vtk_utils.numpy_to_vtkMatrix4x4(np.linalg.inv(self.affine)))

        self.refImageSpace2_xyz: vtkTransformPolyDataFilter = vtkTransformPolyDataFilter()
        self.refImageSpace2_xyz.SetTransform(refImageSpace2_xyz_transform)

        xyz2_refImageSpace_transform: vtkTransform = vtkTransform()
        xyz2_refImageSpace_transform.SetMatrix(vtk_utils.numpy_to_vtkMatrix4x4(self.affine))

        self.xyz2_refImageSpace: vtkTransformPolyDataFilter = vtkTransformPolyDataFilter()
        self.xyz2_refImageSpace.SetTransform(xyz2_refImageSpace_transform)

        currentPeel: vtkPolyData = tmpPeel
        self.currentPeelNo: int = 0
        currentPeel= self.MapImageOnCurrentPeel(currentPeel)

        newPeel: vtkPolyData = vtkPolyData()
        newPeel.DeepCopy(currentPeel)
        newPeel.DeepCopy(currentPeel)
        self.peel_normals: vtkFloatArray = vtkFloatArray()
        self.peel_centers: vtkFloatArray = vtkFloatArray()
        self.peel.append(newPeel)
        self.currentPeelActor: vtkActor = vtkActor()
        if not np.all(np.equal(self.affine, np.eye(4))):
            affine_vtk: vtkMatrix4x4 = self.CreateTransformedVTKAffine()
            self.currentPeelActor.SetUserMatrix(affine_vtk)
        self.GetCurrentPeelActor(currentPeel)
        self.peelActors.append(self.currentPeelActor)
        # locator will later find the triangle on the peel surface where the coil's normal intersect
        self.locator: vtkCellLocator = vtkCellLocator()
        self.PeelDown(currentPeel)
    

    def CreateTransformedVTKAffine(self) -> vtkMatrix4x4:
        affine_transformed: np.ndarray = self.affine.copy()
        matrix_shape: Tuple[int, int] = tuple(self.inv_proj.matrix_shape)
        affine_transformed[1, -1] -= matrix_shape[1]

        return vtk_utils.numpy_to_vtkMatrix4x4(affine_transformed)

    def get_actor(self, n: int) -> Any:
        return self.GetPeelActor(n)

    def SliceDown(self, currentPeel: vtkPolyData) -> vtkPolyData:
        # Warp using the normals
        warp: vtkWarpVector = vtkWarpVector()
        warp.SetInputData(fixMesh(downsample(currentPeel)))  # fixMesh here updates normals needed for warping
        warp.SetInputArrayToProcess(0, 0, 0, vtkDataObject().FIELD_ASSOCIATION_POINTS,
                                    vtkDataSetAttributes().NORMALS)
        warp.SetScaleFactor(-1)
        warp.Update()

        out: vtkPolyData = upsample(warp.GetPolyDataOutput())
        out = smooth(out)
        out = fixMesh(out)
        out = cleanMesh(out)

        currentPeel = out
        return currentPeel
   
    # def sliceUp(self) -> vtkPolyData:
    #     warp: vtkWarpVector = vtkWarpVector()
    #     # warp.SetInputData(fixMesh(downsample(currentPeel))) # fixMesh here updates normals needed for warping
    #     warp.SetInputArrayToProcess(0, 0, 0, vtkDataObject().FIELD_ASSOCIATION_POINTS,
    #                                 vtkDataSetAttributes().NORMALS)
    #     warp.SetScaleFactor(1)
    #     warp.Update()

    #     out: vtkPolyData = upsample(warp.GetPolyDataOutput())
    #     out = smooth(out)
    #     out = fixMesh(out)
    #     out = cleanMesh(out)

    #     currentPeel: vtkPolyData = out
    #     return currentPeel

    def MapImageOnCurrentPeel(self, currentPeel: vtkPolyData) -> vtkPolyData:
        self.xyz2_refImageSpace.SetInputData(currentPeel)
        self.xyz2_refImageSpace.Update()

        probe: vtkProbeFilter = vtkProbeFilter()
        probe.SetInputData(self.xyz2_refImageSpace.GetOutput())
        probe.SetSourceData(self.refImage)
        probe.Update()

        self.refImageSpace2_xyz.SetInputData(probe.GetOutput())
        self.refImageSpace2_xyz.Update()

        currentPeel = self.refImageSpace2_xyz.GetOutput()
        return currentPeel

    def PeelDown(self, currentPeel: vtkPolyData) -> None:
        for i in range(0, self.numberOfPeels):
            currentPeel = self.SliceDown(currentPeel)
            currentPeel = self.MapImageOnCurrentPeel(currentPeel)

            newPeel: vtkPolyData = vtkPolyData()
            newPeel.DeepCopy(currentPeel)
            self.peel.append(newPeel)

            # GetCurrentPeelActor()
            # newPeelActor = vtkActor()
            # newPeelActor = currentPeelActor
            # peelActors.push_back(newPeelActor)

            self.currentPeelNo += 1

    def TransformPeelPosition(self, p: int) -> vtkPolyData:
        peel_transform: vtkTransform = vtkTransform()
        if not np.all(np.equal(self.affine, np.eye(4))):
            affine_vtk: vtkMatrix4x4 = self.CreateTransformedVTKAffine()
            peel_transform.SetMatrix(affine_vtk)
        refpeelspace: vtkTransformPolyDataFilter = vtkTransformPolyDataFilter()
        refpeelspace.SetInputData(self.peel[p])
        refpeelspace.SetTransform(peel_transform)
        refpeelspace.Update()
        currentPeel: vtkPolyData = refpeelspace.GetOutput()
        return currentPeel

    def GetPeelActor(self, p: int) -> vtkActor:
        lut: vtkWindowLevelLookupTable = vtkWindowLevelLookupTable()
        lut.SetWindow(self.window_width)
        lut.SetLevel(self.window_level)
        lut.Build()

        init: float = self.window_level - self.window_width / 2
        end: float = self.window_level + self.window_width / 2

        # Set mapper auto
        mapper: vtkPolyDataMapper = vtkPolyDataMapper()
        mapper.SetInputData(self.peel[p])
        mapper.SetScalarRange(init, end)
        mapper.SetLookupTable(lut)
        mapper.InterpolateScalarsBeforeMappingOn()

        # Set actor
        self.currentPeelActor.SetMapper(mapper)

        currentPeel: vtkPolyData = self.TransformPeelPosition(p)

        self.locator.SetDataSet(currentPeel)
        self.locator.BuildLocator()
        self.peel_centers: np.ndarray = GetCenters(currentPeel)
        self.peel_normals: np.ndarray = GetNormals(currentPeel)

        return self.currentPeelActor

    def GetCurrentPeelActor(self, currentPeel: vtkPolyData) -> vtkActor:
        lut: vtkWindowLevelLookupTable = vtkWindowLevelLookupTable()
        lut.SetWindow(self.window_width)
        lut.SetLevel(self.window_level)
        lut.Build()

        init: float = self.window_level - self.window_width / 2
        end: float = self.window_level + self.window_width / 2

        # Set mapper auto
        mapper: vtkPolyDataMapper = vtkPolyDataMapper()
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
    def __init__(self, e_field_mesh: vtkPolyData) -> None:
        self.GetEfieldActor(e_field_mesh)

    def GetEfieldActor(self, mesh: vtkPolyData) -> vtkActor:
        self.e_field_mesh_normals: vtkFloatArray = vtkFloatArray()
        self.e_field_mesh_centers: vtkFloatArray = vtkFloatArray()

        self.locator_efield_Cell: vtkCellLocator = vtkCellLocator()
        self.locator_efield_Cell.SetDataSet(mesh)
        self.locator_efield_Cell.BuildLocator()

        self.locator_efield: vtkPointLocator = vtkPointLocator()
        self.locator_efield.SetDataSet(mesh)
        self.locator_efield.BuildLocator()

        self.e_field_mesh_normals = GetNormals(mesh)
        self.e_field_mesh_centers = GetCenters(mesh)
        self.e_field_mesh: vtkPolyData = mesh

        self.efield_mapper: vtkPolyDataMapper = vtkPolyDataMapper()
        self.lut: vtkLookupTable = CreateLUTTableForEfield(0, 0.001)

def GetCenters(mesh: vtkPolyData) -> vtkPolyData:
    # Compute centers of triangles
    centerComputer: vtkCellCenters = vtkCellCenters()  # This computes centers of the triangles on the peel
    centerComputer.SetInputData(mesh)
    centerComputer.Update()

    # This stores the centers for easy access
    centers: vtkPolyData = centerComputer.GetOutput()
    return centers

def GetNormals(mesh: vtkPolyData) -> vtkFloatArray:
    # Compute normals of triangles
    normalComputer: vtkPolyDataNormals = vtkPolyDataNormals()  # This computes normals of the triangles on the peel
    normalComputer.SetInputData(mesh)
    normalComputer.ComputePointNormalsOff()
    normalComputer.ComputeCellNormalsOn()
    normalComputer.Update()
    # This converts to the normals to an array for easy access
    normals: vtkFloatArray = normalComputer.GetOutput().GetCellData().GetNormals()
    return normals

def CreateLUTTableForEfield(min_val: float, max_val: float) -> vtkLookupTable:
    lut: vtkLookupTable = vtkLookupTable()
    lut.SetTableRange(min_val, max_val)
    colorSeries: vtkColorSeries = vtkColorSeries()
    seriesEnum: int = colorSeries.BREWER_SEQUENTIAL_YELLOW_ORANGE_BROWN_9
    colorSeries.SetColorScheme(seriesEnum)
    colorSeries.BuildLookupTable(lut, colorSeries.ORDINAL)
    return lut

def cleanMesh(inp: vtkPolyData) -> vtkPolyData:
    cleaned: vtkCleanPolyData = vtkCleanPolyData()
    cleaned.SetInputData(inp)
    cleaned.Update()

    return cleaned.GetOutput()


def fixMesh(inp: vtkPolyData) -> vtkPolyData:
    normals: vtkPolyDataNormals = vtkPolyDataNormals()
    normals.SetInputData(inp)
    normals.SetFeatureAngle(160)
    normals.SplittingOn()
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()

    return normals.GetOutput()


def upsample(inp: vtkPolyData) -> vtkPolyData:
    triangles: vtkTriangleFilter = vtkTriangleFilter()
    triangles.SetInputData(inp)
    triangles.Update()

    subdivisionFilter: vtkLinearSubdivisionFilter = vtkLinearSubdivisionFilter()
    subdivisionFilter.SetInputData(triangles.GetOutput())
    subdivisionFilter.SetNumberOfSubdivisions(2)
    subdivisionFilter.Update()

    return subdivisionFilter.GetOutput()


def smooth(inp: vtkPolyData) -> vtkPolyData:
    smoother: vtkWindowedSincPolyDataFilter = vtkWindowedSincPolyDataFilter()
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


def downsample(inp: vtkPolyData) -> vtkPolyData:
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

    mesh: pyvista.PolyData = pyvista.PolyData(inp)

    # Create clustering object
    clus: pyacvd.Clustering = pyacvd.Clustering(mesh)
    # mesh is not dense enough for uniform remeshing
    # clus.subdivide(3)
    clus.cluster(3000)
    Remesh: pyvista.PolyData= clus.create_mesh()

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


