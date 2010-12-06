import multiprocessing
import tempfile
import time

import numpy
import vtk

import i18n
import imagedata_utils

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

        self.mask = numpy.memmap(filename, mode='r', dtype=dtype,
                                 shape=shape)

    def run(self):
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
        smoothed = ndimage.gaussian_filter(self.mask[roi], (1, 1, 1))
        image = imagedata_utils.to_vtk(smoothed, self.spacing, roi.start,
                                       "AXIAL")

        # Create vtkPolyData from vtkImageData
        print "Generating Polydata"
        if self.mode == "CONTOUR":
            print "Contour"
            contour = vtk.vtkContourFilter()
            contour.SetInput(image)
            contour.SetValue(0, 127.5) # initial threshold
            contour.ComputeScalarsOn()
            contour.ComputeGradientsOn()
            contour.ComputeNormalsOn()
            polydata = contour.GetOutput()
        else: #mode == "GRAYSCALE":
            mcubes = vtk.vtkMarchingCubes()
            mcubes.SetInput(image)
            mcubes.SetValue(0, 127.5)
            mcubes.ComputeScalarsOn()
            mcubes.ComputeGradientsOn()
            mcubes.ComputeNormalsOn()
            polydata = mcubes.GetOutput()

        print "Decimating"
        if self.decimate_reduction:
            decimation = vtk.vtkDecimatePro()
            decimation.SetInput(polydata)
            decimation.SetTargetReduction(self.decimate_reduction)
            decimation.PreserveTopologyOn()
            decimation.SplittingOff()
            polydata = decimation.GetOutput()

        print "Smoothing"
        if self.smooth_iterations and self.smooth_relaxation_factor:
            smoother = vtk.vtkSmoothPolyDataFilter()
            smoother.SetInput(polydata)
            smoother.SetNumberOfIterations(self.smooth_iterations)
            smoother.SetFeatureAngle(80)
            smoother.SetRelaxationFactor(self.smooth_relaxation_factor)
            smoother.FeatureEdgeSmoothingOn()
            smoother.BoundarySmoothingOn()
            polydata = smoother.GetOutput()

        print "Saving"
        filename = tempfile.mktemp()
        writer = vtk.vtkXMLPolyDataWriter()
        writer.SetInput(polydata)
        writer.SetFileName(filename)
        writer.Write()
        print filename

        time.sleep(1)

        self.q_out.put(filename)
