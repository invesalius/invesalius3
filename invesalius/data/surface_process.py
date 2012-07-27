import multiprocessing
import tempfile
import time

import numpy
import vtk

import i18n
import converters
from scipy import ndimage

class SurfaceProcess(multiprocessing.Process):

    def __init__(self, pipe, filename, shape, dtype, mask_filename,
                 mask_shape, mask_dtype, spacing, mode, min_value, max_value,
                 decimate_reduction, smooth_relaxation_factor,
                 smooth_iterations, language, flip_image, q_in, q_out,
                 from_binary, algorithm):

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
        self.flip_image = flip_image
        self.q_in = q_in
        self.q_out = q_out
        self.dtype = dtype
        self.shape = shape
        self.from_binary = from_binary
        self.algorithm = algorithm

        self.mask_filename = mask_filename
        self.mask_shape = mask_shape
        self.mask_dtype = mask_dtype

    def run(self):
        if self.from_binary:
            self.mask = numpy.memmap(self.mask_filename, mode='r',
                                     dtype=self.mask_dtype,
                                     shape=self.mask_shape)
        else:
            self.image = numpy.memmap(self.filename, mode='r', dtype=self.dtype,
                                      shape=self.shape)
            self.mask = numpy.memmap(self.mask_filename, mode='r',
                                     dtype=self.mask_dtype,
                                     shape=self.mask_shape)


        while 1:
            roi = self.q_in.get()
            if roi is None:
                break
            self.CreateSurface(roi)

    def SendProgress(self, obj, msg):
        prog = obj.GetProgress()
        self.pipe.send([prog, msg])

    def CreateSurface(self, roi):
        if self.from_binary:
            a_mask = numpy.array(self.mask[roi.start + 1: roi.stop + 1,
                                           1:, 1:])
            image =  converters.to_vtk(a_mask, self.spacing, roi.start,
                                       "AXIAL")
        else:
            a_image = numpy.array(self.image[roi])

            if self.algorithm == u'InVesalius 3.b2':
                a_mask = numpy.array(self.mask[roi.start + 1: roi.stop + 1,
                                               1:, 1:])
                a_image[a_mask == 1] = a_image.min() - 1
                a_image[a_mask == 254] = (self.min_value + self.max_value) / 2.0

                image =  converters.to_vtk(a_image, self.spacing, roi.start,
                                           "AXIAL")

                gauss = vtk.vtkImageGaussianSmooth()
                gauss.SetInput(image)
                gauss.SetRadiusFactor(0.3)
                gauss.Update()

                image = gauss.GetOutput()
            else:
                image =  converters.to_vtk(a_image, self.spacing, roi.start,
                                           "AXIAL")

        flip = vtk.vtkImageFlip()
        flip.SetInput(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.Update()

        image = flip.GetOutput()

        #filename = tempfile.mktemp(suffix='_%s.vti' % (self.pid))
        #writer = vtk.vtkXMLImageDataWriter()
        #writer.SetInput(mask_vtk)
        #writer.SetFileName(filename)
        #writer.Write()

        #print "Writing piece", roi, "to", filename

        # Create vtkPolyData from vtkImageData
        #print "Generating Polydata"
        #if self.mode == "CONTOUR":
        #print "Contour"
        contour = vtk.vtkContourFilter()
        contour.SetInput(image)
        #contour.SetInput(flip.GetOutput())
        if self.from_binary:
            contour.SetValue(0, 127) # initial threshold
        else:
            contour.SetValue(0, self.min_value) # initial threshold
            contour.SetValue(1, self.max_value) # final threshold
        contour.ComputeScalarsOn()
        contour.ComputeGradientsOn()
        contour.ComputeNormalsOn()
        #contour.AddObserver("ProgressEvent", lambda obj,evt:
        #                    self.SendProgress(obj, _("Generating 3D surface...")))
        polydata = contour.GetOutput()
        #else: #mode == "GRAYSCALE":
            #mcubes = vtk.vtkMarchingCubes()
            #mcubes.SetInput(flip.GetOutput())
            #mcubes.SetValue(0, self.min_value)
            #mcubes.SetValue(1, self.max_value)
            #mcubes.ComputeScalarsOff()
            #mcubes.ComputeGradientsOff()
            #mcubes.ComputeNormalsOff()
            #mcubes.AddObserver("ProgressEvent", lambda obj,evt:
                                #self.SendProgress(obj, _("Generating 3D surface...")))
            #polydata = mcubes.GetOutput()

        #triangle = vtk.vtkTriangleFilter()
        #triangle.SetInput(polydata)
        #triangle.AddObserver("ProgressEvent", lambda obj,evt:
						#self.SendProgress(obj, _("Generating 3D surface...")))
        #triangle.Update()
        #polydata = triangle.GetOutput()

        #if self.decimate_reduction:
            
            ##print "Decimating"
            #decimation = vtk.vtkDecimatePro()
            #decimation.SetInput(polydata)
            #decimation.SetTargetReduction(0.3)
            #decimation.AddObserver("ProgressEvent", lambda obj,evt:
                            #self.SendProgress(obj, _("Generating 3D surface...")))
            ##decimation.PreserveTopologyOn()
            #decimation.SplittingOff()
            #decimation.BoundaryVertexDeletionOff()
            #polydata = decimation.GetOutput()

        self.pipe.send(None)
        
        filename = tempfile.mktemp(suffix='_%s.vtp' % (self.pid))
        writer = vtk.vtkXMLPolyDataWriter()
        writer.SetInput(polydata)
        writer.SetFileName(filename)
        writer.Write()

        print "Writing piece", roi, "to", filename

        self.q_out.put(filename)
