import vtk
import pyacvd
# import os
import pyvista
# import numpy as np
# import Trekker


class Brain:
    def __init__(self, img_path, mask_path, n_peels, affine_vtk):
        self.peel = []
        self.peelActors = []

        T1_reader = vtk.vtkNIFTIImageReader()
        T1_reader.SetFileName(img_path)
        T1_reader.Update()

        # self.refImage = vtk.vtkImageData()
        self.refImage = T1_reader.GetOutput()

        mask_reader = vtk.vtkNIFTIImageReader()
        mask_reader.SetFileName(mask_path)
        mask_reader.Update()

        mc = vtk.vtkContourFilter()
        mc.SetInputConnection(mask_reader.GetOutputPort())
        mc.SetValue(0, 1)
        mc.Update()

        refSurface = vtk.vtkPolyData()
        refSurface = mc.GetOutput()

        tmpPeel = vtk.vtkPolyData()
        tmpPeel = downsample(refSurface)

        mask_sFormMatrix = vtk.vtkMatrix4x4()
        mask_sFormMatrix = mask_reader.GetSFormMatrix()

        mask_ijk2xyz = vtk.vtkTransform()
        mask_ijk2xyz.SetMatrix(mask_sFormMatrix)

        mask_ijk2xyz_filter = vtk.vtkTransformPolyDataFilter()
        mask_ijk2xyz_filter.SetInputData(tmpPeel)
        mask_ijk2xyz_filter.SetTransform(mask_ijk2xyz)
        mask_ijk2xyz_filter.Update()

        tmpPeel = smooth(mask_ijk2xyz_filter.GetOutput())
        tmpPeel = fixMesh(tmpPeel)
        tmpPeel = cleanMesh(tmpPeel)
        tmpPeel = upsample(tmpPeel)
        tmpPeel = smooth(tmpPeel)
        tmpPeel = fixMesh(tmpPeel)
        tmpPeel = cleanMesh(tmpPeel)

        # sFormMatrix = vtk.vtkMatrix4x4()
        qFormMatrix = T1_reader.GetQFormMatrix()
        # sFormMatrix = T1_reader.GetSFormMatrix()

        refImageSpace2_xyz_transform = vtk.vtkTransform()
        refImageSpace2_xyz_transform.SetMatrix(qFormMatrix)

        self.refImageSpace2_xyz = vtk.vtkTransformPolyDataFilter()
        self.refImageSpace2_xyz.SetTransform(refImageSpace2_xyz_transform)

        xyz2_refImageSpace_transform = vtk.vtkTransform()
        qFormMatrix.Invert()
        xyz2_refImageSpace_transform.SetMatrix(qFormMatrix)

        self.xyz2_refImageSpace = vtk.vtkTransformPolyDataFilter()
        self.xyz2_refImageSpace.SetTransform(xyz2_refImageSpace_transform)

        # self.currentPeel = vtk.vtkPolyData()
        self.currentPeel = tmpPeel
        self.currentPeelNo = 0
        self.mapImageOnCurrentPeel()

        newPeel = vtk.vtkPolyData()
        newPeel.DeepCopy(self.currentPeel)
        self.peel_normals = vtk.vtkFloatArray()
        self.peel_centers = vtk.vtkFloatArray()
        self.peel.append(newPeel)
        self.currentPeelActor = vtk.vtkActor()
        self.currentPeelActor.SetUserMatrix(affine_vtk)
        self.getCurrentPeelActor()
        self.peelActors.append(self.currentPeelActor)
        self.locator = vtk.vtkCellLocator()  # This one will later find the triangle on the peel surface where the coil's normal intersect
        self.numberOfPeels = n_peels
        self.peelDown()

    def get_actor(self, n):
        return self.getPeelActor(n)

    def sliceDown(self):
        # Warp using the normals
        warp = vtk.vtkWarpVector()
        warp.SetInputData(fixMesh(downsample(self.currentPeel)))  # fixMesh here updates normals needed for warping
        warp.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject().FIELD_ASSOCIATION_POINTS,
                                    vtk.vtkDataSetAttributes().NORMALS)
        warp.SetScaleFactor(-1)
        warp.Update()

        out = vtk.vtkPolyData()
        out = upsample(warp.GetPolyDataOutput())
        out = smooth(out)
        out = fixMesh(out)
        out = cleanMesh(out)

        self.currentPeel = out

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

    def mapImageOnCurrentPeel(self):
        self.xyz2_refImageSpace.SetInputData(self.currentPeel)
        self.xyz2_refImageSpace.Update()

        probe = vtk.vtkProbeFilter()
        probe.SetInputData(self.xyz2_refImageSpace.GetOutput())
        probe.SetSourceData(self.refImage)
        probe.Update()

        self.refImageSpace2_xyz.SetInputData(probe.GetOutput())
        self.refImageSpace2_xyz.Update()

        self.currentPeel = self.refImageSpace2_xyz.GetOutput()

    def peelDown(self):
        for i in range(0, self.numberOfPeels):
            self.sliceDown()
            self.mapImageOnCurrentPeel()

            newPeel = vtk.vtkPolyData()
            newPeel.DeepCopy(self.currentPeel)
            self.peel.append(newPeel)

            # getCurrentPeelActor()
            # newPeelActor = vtk.vtkActor()
            # newPeelActor = currentPeelActor
            # peelActors.push_back(newPeelActor)

            self.currentPeelNo += 1

    def getPeelActor(self, p):
        colors = vtk.vtkNamedColors()
        # Create the color map
        colorLookupTable = vtk.vtkLookupTable()
        colorLookupTable.SetNumberOfColors(512)
        colorLookupTable.SetSaturationRange(0, 0)
        colorLookupTable.SetHueRange(0, 0)
        colorLookupTable.SetValueRange(0, 1)
        # colorLookupTable.SetTableRange(0, 1000)
        # colorLookupTable.SetTableRange(0, 250)
        colorLookupTable.SetTableRange(0, 200)
        # colorLookupTable.SetTableRange(0, 150)
        colorLookupTable.Build()

        # Set mapper auto
        mapper = vtk.vtkOpenGLPolyDataMapper()
        mapper.SetInputData(self.peel[p])
        # mapper.SetScalarRange(0, 1000)
        # mapper.SetScalarRange(0, 250)
        mapper.SetScalarRange(0, 200)
        # mapper.SetScalarRange(0, 150)
        mapper.SetLookupTable(colorLookupTable)
        mapper.InterpolateScalarsBeforeMappingOn()

        # Set actor
        self.currentPeelActor.SetMapper(mapper)

        self.currentPeel = self.peel[p]
        self.locator.SetDataSet(self.peel[p])
        self.locator.BuildLocator()
        self.getCenters()
        self.getNormals()

        return self.currentPeelActor

    def getCurrentPeelActor(self):
        colors = vtk.vtkNamedColors()

        # Create the color map
        colorLookupTable = vtk.vtkLookupTable()
        colorLookupTable.SetNumberOfColors(512)
        colorLookupTable.SetSaturationRange(0, 0)
        colorLookupTable.SetHueRange(0, 0)
        colorLookupTable.SetValueRange(0, 1)
        # colorLookupTable.SetTableRange(0, 1000)
        # colorLookupTable.SetTableRange(0, 250)
        colorLookupTable.SetTableRange(0, 200)
        # colorLookupTable.SetTableRange(0, 150)
        colorLookupTable.Build()

        # Set mapper auto
        mapper = vtk.vtkOpenGLPolyDataMapper()
        mapper.SetInputData(self.currentPeel)
        # mapper.SetScalarRange(0, 1000)
        # mapper.SetScalarRange(0, 250)
        mapper.SetScalarRange(0, 200)
        # mapper.SetScalarRange(0, 150)
        mapper.SetLookupTable(colorLookupTable)
        mapper.InterpolateScalarsBeforeMappingOn()

        # Set actor
        self.currentPeelActor.SetMapper(mapper)
        self.currentPeelActor.GetProperty().SetBackfaceCulling(1)
        self.currentPeelActor.GetProperty().SetOpacity(0.5)

        return self.currentPeelActor

    def getCenters(self):
        # Compute centers of triangles
        centerComputer = vtk.vtkCellCenters()  # This computes centers of the triangles on the peel
        centerComputer.SetInputData(self.currentPeel)
        centerComputer.Update()
        peel_centers = vtk.vtkFloatArray()  # This stores the centers for easy access
        peel_centers = centerComputer.GetOutput()
        self.peel_centers = peel_centers

    def getNormals(self):
        # Compute normals of triangles
        normalComputer = vtk.vtkPolyDataNormals()  # This computes normals of the triangles on the peel
        normalComputer.SetInputData(self.currentPeel)
        normalComputer.ComputePointNormalsOff()
        normalComputer.ComputeCellNormalsOn()
        normalComputer.Update()
        peel_normals = vtk.vtkFloatArray()  # This converts to the normals to an array for easy access
        peel_normals = normalComputer.GetOutput().GetCellData().GetNormals()
        self.peel_normals = peel_normals


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


