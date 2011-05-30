import multiprocessing
import tempfile
import time

import numpy
import vtk

import i18n
import data.converters
from scipy import ndimage

class SurfaceProcess(multiprocessing.Process):

    def __init__(self, pipe, filename, shape, dtype, spacing, mode, min_value, max_value,
                 decimate_reduction, smooth_relaxation_factor,
                 smooth_iterations, language,  fill_holes, keep_largest, 
                 flip_image, q_in, q_out):

        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.spacing = spacing
        self.filename = filename
        self.mode = mode
        self.min_value = min_value
        self.max_value = max_value
        self.decimate_reduction = decimate_reduction
        self.smooth_relaxation_factor = smooth_relaxation_factor
        self.smooth_iterations = smooth_iterations
        self.language = language
        self.fill_holes = fill_holes
        self.keep_largest = keep_largest
        self.flip_image = flip_image
        self.q_in = q_in
        self.q_out = q_out
        self.dtype = dtype
        self.shape = shape

    def run(self):
        self.mask = numpy.memmap(self.filename, mode='r', dtype=self.dtype,
                                 shape=self.shape)
        while 1:
            roi = self.q_in.get()
            print roi
            if roi is None:
                break
            self.CreateSurface(roi)

    def SendProgress(self, obj, msg):
        prog = obj.GetProgress()
        self.pipe.send([prog, msg])

    def CreateSurface(self, roi):
        smoothed = numpy.array(self.mask[roi])
        image =  converters.to_vtk(smoothed, self.spacing, roi.start,
                                       "AXIAL")
        flip = vtk.vtkImageFlip()
        flip.SetInput(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.Update()
        # Create vtkPolyData from vtkImageData
        #print "Generating Polydata"
        #if self.mode == "CONTOUR":
        #print "Contour"
        #contour = vtk.vtkContourFilter()
        #contour.SetInput(image)
        #contour.SetValue(0, self.min_value) # initial threshold
        #contour.SetValue(1, self.max_value) # final threshold
        #contour.ComputeScalarsOn()
        #contour.ComputeGradientsOn()
        #contour.ComputeNormalsOn()
        #polydata = contour.GetOutput()
        #else: #mode == "GRAYSCALE":
        mcubes = vtk.vtkMarchingCubes()
        mcubes.SetInput(flip.GetOutput())
        mcubes.SetValue(0, self.min_value)
        mcubes.SetValue(1, self.max_value)
        mcubes.ComputeScalarsOff()
        mcubes.ComputeGradientsOff()
        mcubes.ComputeNormalsOff()
        polydata = mcubes.GetOutput()

        triangle = vtk.vtkTriangleFilter()
        triangle.SetInput(polydata)
        triangle.Update()
        polydata = triangle.GetOutput()

        bounds = polydata.GetBounds()
        origin = ((bounds[1] + bounds[0]) / 2.0, (bounds[3] + bounds[2])/2.0,
                  (bounds[5] + bounds[4]) / 2.0)

        print "Bounds is", bounds
        print "origin is", origin

        #print "Decimating"
        decimation = vtk.vtkDecimatePro()
        decimation.SetInput(polydata)
        decimation.SetTargetReduction(0.3)
        #decimation.PreserveTopologyOn()
        decimation.SplittingOff()
        decimation.BoundaryVertexDeletionOff()
        polydata = decimation.GetOutput()

        #decimation = vtk.vtkQuadricClustering()
        #decimation.SetInput(polydata)
        #decimation.AutoAdjustNumberOfDivisionsOff()
        #decimation.SetDivisionOrigin(0, 0, 0)
        #decimation.SetDivisionSpacing(self.spacing)
        #decimation.SetFeaturePointsAngle(80)
        #decimation.UseFeaturePointsOn()
        #decimation.UseFeatureEdgesOn()
        #ecimation.CopyCellDataOn()
        
        #print "Division", decimation.GetNumberOfDivisions()
        
        #polydata = decimation.GetOutput()

        #if self.smooth_iterations and self.smooth_relaxation_factor:
            #print "Smoothing"
            #smoother = vtk.vtkWindowedSincPolyDataFilter()
            #smoother.SetInput(polydata)
            #smoother.SetNumberOfIterations(self.smooth_iterations)
            #smoother.SetFeatureAngle(120)
            #smoother.SetNumberOfIterations(30)
            #smoother.BoundarySmoothingOn()
            #smoother.SetPassBand(0.01)
            #smoother.FeatureEdgeSmoothingOn()
            #smoother.NonManifoldSmoothingOn()
            #smoother.NormalizeCoordinatesOn()
            #smoother.Update()
            #polydata = smoother.GetOutput()

        print "Saving"
        filename = tempfile.mktemp(suffix='_%s.vtp' % (self.pid))
        writer = vtk.vtkXMLPolyDataWriter()
        writer.SetInput(polydata)
        writer.SetFileName(filename)
        writer.Write()

        self.q_out.put(filename)
