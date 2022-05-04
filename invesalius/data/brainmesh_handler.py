import vtk
import numpy as np
import invesalius.data.slice_ as sl
from invesalius.data.converters import to_vtk
import invesalius.data.vtk_utils as vtk_utils

try:
    import Trekker
    has_trekker = True
except ImportError:
    has_trekker = False
if has_trekker:
    import pyacvd
    import pyvista

class Brain:
    def __init__(self, n_peels, window_width, window_level, affine_vtk=None):
        # Create arrays to access the peel data and peel Actors
        self.peel = []
        self.peelActors = []
        self.window_width = window_width
        self.window_level = window_level
        self.numberOfPeels = n_peels
        self.affine_vtk = affine_vtk

    def from_mask(self, mask):
        mask= np.array(mask.matrix[1:, 1:, 1:])
        slic = sl.Slice()
        image = slic.matrix

        mask = to_vtk(mask, spacing=slic.spacing)
        image = to_vtk(image, spacing=slic.spacing)

        flip = vtk.vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()
        image = flip.GetOutput()

        flip = vtk.vtkImageFlip()
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
        image = to_vtk(image, spacing=slic.spacing)

        # Read the mask
        mask_reader = vtk.vtkNIFTIImageReader()
        mask_reader.SetFileName(mask_path)
        mask_reader.Update()

        mask = mask_reader.GetOutput()

        mask_sFormMatrix = mask_reader.GetSFormMatrix()

        # Image
        self.refImage = image

        self._do_surface_creation(mask, mask_sFormMatrix)


    def _do_surface_creation(self, mask, mask_sFormMatrix=None, qFormMatrix=None):
        if mask_sFormMatrix is None:
            mask_sFormMatrix = vtk.vtkMatrix4x4()

        if qFormMatrix is None:
            qFormMatrix = vtk.vtkMatrix4x4()

        value = np.mean(mask.GetScalarRange())

        # Use the mask to create isosurface
        mc = vtk.vtkContourFilter()
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
        mask_ijk2xyz = vtk.vtkTransform()
        mask_ijk2xyz.SetMatrix(mask_sFormMatrix)

        mask_ijk2xyz_filter = vtk.vtkTransformPolyDataFilter()
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

        refImageSpace2_xyz_transform = vtk.vtkTransform()
        refImageSpace2_xyz_transform.SetMatrix(qFormMatrix)

        self.refImageSpace2_xyz = vtk.vtkTransformPolyDataFilter()
        self.refImageSpace2_xyz.SetTransform(refImageSpace2_xyz_transform)

        xyz2_refImageSpace_transform = vtk.vtkTransform()
        qFormMatrix.Invert()
        xyz2_refImageSpace_transform.SetMatrix(qFormMatrix)

        self.xyz2_refImageSpace = vtk.vtkTransformPolyDataFilter()
        self.xyz2_refImageSpace.SetTransform(xyz2_refImageSpace_transform)

        currentPeel = tmpPeel
        self.currentPeelNo = 0
        currentPeel= self.MapImageOnCurrentPeel(currentPeel)

        newPeel = vtk.vtkPolyData()
        newPeel.DeepCopy(currentPeel)
        newPeel.DeepCopy(currentPeel)
        self.peel_normals = vtk.vtkFloatArray()
        self.peel_centers = vtk.vtkFloatArray()
        self.peel.append(newPeel)
        self.currentPeelActor = vtk.vtkActor()
        if self.affine_vtk:
            self.currentPeelActor.SetUserMatrix(self.affine_vtk)
        self.GetCurrentPeelActor(currentPeel)
        self.peelActors.append(self.currentPeelActor)
        # locator will later find the triangle on the peel surface where the coil's normal intersect
        self.locator = vtk.vtkCellLocator()
        self.PeelDown(currentPeel)

    def get_actor(self, n):
        return self.GetPeelActor(n)

    def SliceDown(self, currentPeel):
        # Warp using the normals
        warp = vtk.vtkWarpVector()
        warp.SetInputData(fixMesh(downsample(currentPeel)))  # fixMesh here updates normals needed for warping
        warp.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject().FIELD_ASSOCIATION_POINTS,
                                    vtk.vtkDataSetAttributes().NORMALS)
        warp.SetScaleFactor(-1)
        warp.Update()

        out = vtk.vtkPolyData()
        out = upsample(warp.GetPolyDataOutput())
        out = smooth(out)
        out = fixMesh(out)
        out = cleanMesh(out)

        currentPeel = out
        return currentPeel
    # def sliceUp(self):
    #     # Warp using the normals
    #     warp = vtk.vtkWarpVector()
    #     # warp.SetInputData(fixMesh(downsample(currentPeel))) # fixMesh here updates normals needed for warping
    #     warp.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject().FIELD_ASSOCIATION_POINTS,
    #                                 vtk.vtkDataSetAttributes().NORMALS)
    #     warp.SetScaleFactor(1)
    #     warp.Update()
    #
    #     out = vtk.vtkPolyData()
    #     out = upsample(warp.GetPolyDataOutput())
    #     out = smooth(out)
    #     out = fixMesh(out)
    #     out = cleanMesh(out)
    #
    #     currentPeel = out

    def MapImageOnCurrentPeel(self, currentPeel):
        self.xyz2_refImageSpace.SetInputData(currentPeel)
        self.xyz2_refImageSpace.Update()

        probe = vtk.vtkProbeFilter()
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

            newPeel = vtk.vtkPolyData()
            newPeel.DeepCopy(currentPeel)
            self.peel.append(newPeel)

            # GetCurrentPeelActor()
            # newPeelActor = vtk.vtkActor()
            # newPeelActor = currentPeelActor
            # peelActors.push_back(newPeelActor)

            self.currentPeelNo += 1

    def TransformPeelPosition(self, p):
        peel_transform = vtk.vtkTransform()
        if self.affine_vtk:
            peel_transform.SetMatrix(self.affine_vtk)
        refpeelspace = vtk.vtkTransformPolyDataFilter()
        refpeelspace.SetInputData(self.peel[p])
        refpeelspace.SetTransform(peel_transform)
        refpeelspace.Update()
        currentPeel = refpeelspace.GetOutput()
        return currentPeel

    def GetPeelActor(self, p):
        lut = vtk.vtkWindowLevelLookupTable()
        lut.SetWindow(self.window_width)
        lut.SetLevel(self.window_level)
        lut.Build()

        init = self.window_level - self.window_width / 2
        end = self.window_level + self.window_width / 2

        # Set mapper auto
        mapper = vtk.vtkPolyDataMapper()
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
        lut = vtk.vtkWindowLevelLookupTable()
        lut.SetWindow(self.window_width)
        lut.SetLevel(self.window_level)
        lut.Build()

        init = self.window_level - self.window_width / 2
        end = self.window_level + self.window_width / 2

        # Set mapper auto
        mapper = vtk.vtkPolyDataMapper()
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
    def __init__(self, e_field_mesh):
        self.efield_actor = self.GetEfieldActor(e_field_mesh)

    def GetEfieldActor(self, mesh):
        self.e_field_mesh_normals = vtk.vtkFloatArray()
        self.e_field_mesh_centers = vtk.vtkFloatArray()
        # Create a mapper and actor
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(mesh)
        self.efield_actor = vtk.vtkActor()
        self.efield_actor.SetMapper(mapper)

        affine = sl.Slice().affine
        matrix_shape = sl.Slice().matrix.shape
        spacing = sl.Slice().spacing
        img_shift = spacing[1] * (matrix_shape[1] - 1)
        affine = sl.Slice().affine.copy()
        affine[1, -1] -= img_shift
        #affine = np.identity(4)
        affine_vtk = vtk_utils.numpy_to_vtkMatrix4x4(affine)
        self.efield_actor.SetUserMatrix(affine_vtk)
        mesh = self.TransformPosition(mesh, affine_vtk)

        self.locator_efield_Cell = vtk.vtkCellLocator()
        self.locator_efield_Cell.SetDataSet(mesh)
        self.locator_efield_Cell.BuildLocator()

        self.locator_efield = vtk.vtkPointLocator()
        self.locator_efield.SetDataSet(mesh)
        self.locator_efield.BuildLocator()

        self.e_field_mesh_normals = GetNormals(mesh)
        self.e_field_mesh_centers = GetCenters(mesh)
        self.e_field_mesh = mesh
        return self.efield_actor

    def TransformPosition(self, mesh, affine_vtk):
        mesh_transform = vtk.vtkTransform()
        mesh_transform.SetMatrix(affine_vtk)

        refpeelspace = vtk.vtkTransformPolyDataFilter()
        refpeelspace.SetInputData(mesh)
        refpeelspace.SetTransform(mesh_transform)
        refpeelspace.Update()
        new_mesh = refpeelspace.GetOutput()
        return new_mesh

def GetCenters(mesh):
        # Compute centers of triangles
        centerComputer = vtk.vtkCellCenters()  # This computes centers of the triangles on the mesh
        centerComputer.SetInputData(mesh)
        centerComputer.Update()

        # This stores the centers for easy access
        centers = centerComputer.GetOutput()
        return centers

def GetNormals(mesh):
        # Compute normals of triangles
        normalComputer = vtk.vtkPolyDataNormals()  # This computes normals of the triangles on the mesh
        normalComputer.SetInputData(mesh)
        normalComputer.ComputePointNormalsOff()
        normalComputer.ComputeCellNormalsOn()
        normalComputer.Update()
        # This converts to the normals to an array for easy access
        normals = normalComputer.GetOutput().GetCellData().GetNormals()
        return normals

def cleanMesh(inp):
    cleaned = vtk.vtkCleanPolyData()
    cleaned.SetInputData(inp)
    cleaned.Update()

    return cleaned.GetOutput()


def fixMesh(inp):
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(inp)
    normals.SetFeatureAngle(160)
    normals.SplittingOn()
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()

    return normals.GetOutput()


def upsample(inp):
    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputData(inp)
    triangles.Update()

    subdivisionFilter = vtk.vtkLinearSubdivisionFilter()
    subdivisionFilter.SetInputData(triangles.GetOutput())
    subdivisionFilter.SetNumberOfSubdivisions(2)
    subdivisionFilter.Update()

    return subdivisionFilter.GetOutput()


def smooth(inp):
    smoother = vtk.vtkWindowedSincPolyDataFilter()
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
    # surface = vtk.vtkSurface()
    # surface.CreateFromPolyData(inp)
    #
    # areas = vtk.vtkDoubleArray()
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

    # Remesh = vtk.vtkIsotropicDiscreteRemeshing()
    # Remesh.SetInput(surface)
    # Remesh.SetFileLoadSaveOption(0)
    # Remesh.SetNumberOfClusters(clusterNumber)
    # Remesh.SetConsoleOutput(0)
    # Remesh.GetMetric().SetGradation(0)
    # Remesh.SetDisplay(0)
    # Remesh.Remesh()

    # out = vtk.vtkPolyData()
    # out.SetPoints(Remesh.GetOutput().GetPoints())
    # out.SetPolys(Remesh.GetOutput().GetPolys())

    return Remesh


