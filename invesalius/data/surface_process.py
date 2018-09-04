import multiprocessing
import tempfile
import time

import numpy
import vtk

import invesalius.i18n as i18n
import invesalius.data.converters as converters
from invesalius.data import cy_mesh
# import invesalius.data.imagedata_utils as iu

import weakref
from scipy import ndimage

# TODO: Code duplicated from file {imagedata_utils.py}.
def ResampleImage3D(imagedata, value):
    """
    Resample vtkImageData matrix.
    """
    spacing = imagedata.GetSpacing()
    extent = imagedata.GetExtent()
    size = imagedata.GetDimensions()

    width = float(size[0])
    height = float(size[1]/value)

    resolution = (height/(extent[1]-extent[0])+1)*spacing[1]

    resample = vtk.vtkImageResample()
    resample.SetInputData(imagedata)
    resample.SetAxisMagnificationFactor(0, resolution)
    resample.SetAxisMagnificationFactor(1, resolution)

    return resample.GetOutput()


def create_surface_piece(filename, shape, dtype, mask_filename, mask_shape,
                         mask_dtype, roi, spacing, mode, min_value, max_value,
                         decimate_reduction, smooth_relaxation_factor,
                         smooth_iterations, language, flip_image,
                         from_binary, algorithm, imagedata_resolution):
        if from_binary:
            mask = numpy.memmap(mask_filename, mode='r',
                                     dtype=mask_dtype,
                                     shape=mask_shape)
            a_mask = numpy.array(mask[roi.start + 1: roi.stop + 1,
                                           1:, 1:])
            image =  converters.to_vtk(a_mask, spacing, roi.start,
                                       "AXIAL")
            del a_mask
        else:
            image = numpy.memmap(filename, mode='r', dtype=dtype,
                                      shape=shape)
            mask = numpy.memmap(mask_filename, mode='r',
                                     dtype=mask_dtype,
                                     shape=mask_shape)
            a_image = numpy.array(image[roi])

            if algorithm == u'InVesalius 3.b2':
                a_mask = numpy.array(mask[roi.start + 1: roi.stop + 1,
                                               1:, 1:])
                a_image[a_mask == 1] = a_image.min() - 1
                a_image[a_mask == 254] = (min_value + max_value) / 2.0

                image =  converters.to_vtk(a_image, spacing, roi.start,
                                           "AXIAL")

                gauss = vtk.vtkImageGaussianSmooth()
                gauss.SetInputData(image)
                gauss.SetRadiusFactor(0.3)
                gauss.ReleaseDataFlagOn()
                gauss.Update()

                del image
                image = gauss.GetOutput()
                del gauss
                del a_mask
            else:
                image = converters.to_vtk(a_image, spacing, roi.start,
                                           "AXIAL")
            del a_image

        if imagedata_resolution:
            image = ResampleImage3D(image, imagedata_resolution)

        flip = vtk.vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()

        del image
        image = flip.GetOutput()
        del flip

        contour = vtk.vtkContourFilter()
        contour.SetInputData(image)
        if from_binary:
            contour.SetValue(0, 127) # initial threshold
        else:
            contour.SetValue(0, min_value) # initial threshold
            contour.SetValue(1, max_value) # final threshold
        contour.ComputeScalarsOn()
        contour.ComputeGradientsOn()
        contour.ComputeNormalsOn()
        contour.ReleaseDataFlagOn()
        contour.Update()

        polydata = contour.GetOutput()
        del image
        del contour

        filename = tempfile.mktemp(suffix='_%d_%d.vtp' % (roi.start, roi.stop))
        writer = vtk.vtkXMLPolyDataWriter()
        writer.SetInputData(polydata)
        writer.SetFileName(filename)
        writer.Write()

        print("Writing piece", roi, "to", filename)
        return filename


def join_process_surface(filenames, algorithm, smooth_iterations, smooth_relaxation_factor, decimate_reduction, keep_largest, fill_holes, options):
    print("Appending polydata")
    polydata_append = vtk.vtkAppendPolyData()
    for f in filenames:
        reader = vtk.vtkXMLPolyDataReader()
        reader.SetFileName(f)
        reader.Update()

        polydata = reader.GetOutput()

        polydata_append.AddInputData(polydata)
        del reader
        del polydata

    polydata_append.Update()
    #  polydata_append.GetOutput().ReleaseDataFlagOn()
    polydata = polydata_append.GetOutput()
    #polydata.Register(None)
    #  polydata.SetSource(None)
    del polydata_append

    clean = vtk.vtkCleanPolyData()
    #  clean.ReleaseDataFlagOn()
    #  clean.GetOutput().ReleaseDataFlagOn()
    clean_ref = weakref.ref(clean)
    #  clean_ref().AddObserver("ProgressEvent", lambda obj,evt:
                    #  UpdateProgress(clean_ref(), _("Creating 3D surface...")))
    clean.SetInputData(polydata)
    clean.PointMergingOn()
    clean.Update()

    del polydata
    polydata = clean.GetOutput()
    #  polydata.SetSource(None)
    del clean

    if algorithm == 'ca_smoothing':
        normals = vtk.vtkPolyDataNormals()
        normals_ref = weakref.ref(normals)
        #  normals_ref().AddObserver("ProgressEvent", lambda obj,evt:
                                  #  UpdateProgress(normals_ref(), _("Creating 3D surface...")))
        normals.SetInputData(polydata)
        #  normals.ReleaseDataFlagOn()
        #normals.SetFeatureAngle(80)
        #normals.AutoOrientNormalsOn()
        normals.ComputeCellNormalsOn()
        #  normals.GetOutput().ReleaseDataFlagOn()
        normals.Update()
        del polydata
        polydata = normals.GetOutput()
        #  polydata.SetSource(None)
        del normals

        clean = vtk.vtkCleanPolyData()
        #  clean.ReleaseDataFlagOn()
        #  clean.GetOutput().ReleaseDataFlagOn()
        clean_ref = weakref.ref(clean)
        #  clean_ref().AddObserver("ProgressEvent", lambda obj,evt:
                        #  UpdateProgress(clean_ref(), _("Creating 3D surface...")))
        clean.SetInputData(polydata)
        clean.PointMergingOn()
        clean.Update()

        del polydata
        polydata = clean.GetOutput()
        #  polydata.SetSource(None)
        del clean

        #  try:
            #  polydata.BuildLinks()
        #  except TypeError:
            #  polydata.BuildLinks(0)
        #  polydata = ca_smoothing.ca_smoothing(polydata, options['angle'],
                                             #  options['max distance'],
                                             #  options['min weight'],
                                             #  options['steps'])

        mesh = cy_mesh.Mesh(polydata)
        cy_mesh.ca_smoothing(mesh, options['angle'],
                             options['max distance'],
                             options['min weight'],
                             options['steps'])
        #  polydata = mesh.to_vtk()

        #  polydata.SetSource(None)
        #  polydata.DebugOn()
    else:
        #smoother = vtk.vtkWindowedSincPolyDataFilter()
        smoother = vtk.vtkSmoothPolyDataFilter()
        smoother_ref = weakref.ref(smoother)
        #  smoother_ref().AddObserver("ProgressEvent", lambda obj,evt:
                        #  UpdateProgress(smoother_ref(), _("Creating 3D surface...")))
        smoother.SetInputData(polydata)
        smoother.SetNumberOfIterations(smooth_iterations)
        smoother.SetRelaxationFactor(smooth_relaxation_factor)
        smoother.SetFeatureAngle(80)
        #smoother.SetEdgeAngle(90.0)
        #smoother.SetPassBand(0.1)
        smoother.BoundarySmoothingOn()
        smoother.FeatureEdgeSmoothingOn()
        #smoother.NormalizeCoordinatesOn()
        #smoother.NonManifoldSmoothingOn()
        #  smoother.ReleaseDataFlagOn()
        #  smoother.GetOutput().ReleaseDataFlagOn()
        smoother.Update()
        del polydata
        polydata = smoother.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        del smoother


    if decimate_reduction:
        print("Decimating", decimate_reduction)
        decimation = vtk.vtkQuadricDecimation()
        #  decimation.ReleaseDataFlagOn()
        decimation.SetInputData(polydata)
        decimation.SetTargetReduction(decimate_reduction)
        decimation_ref = weakref.ref(decimation)
        #  decimation_ref().AddObserver("ProgressEvent", lambda obj,evt:
                        #  UpdateProgress(decimation_ref(), _("Creating 3D surface...")))
        #decimation.PreserveTopologyOn()
        #decimation.SplittingOff()
        #decimation.BoundaryVertexDeletionOff()
        #  decimation.GetOutput().ReleaseDataFlagOn()
        decimation.Update()
        del polydata
        polydata = decimation.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        del decimation

    #to_measure.Register(None)
    #  to_measure.SetSource(None)

    if keep_largest:
        conn = vtk.vtkPolyDataConnectivityFilter()
        conn.SetInputData(polydata)
        conn.SetExtractionModeToLargestRegion()
        conn_ref = weakref.ref(conn)
        #  conn_ref().AddObserver("ProgressEvent", lambda obj,evt:
                #  UpdateProgress(conn_ref(), _("Creating 3D surface...")))
        conn.Update()
        #  conn.GetOutput().ReleaseDataFlagOn()
        del polydata
        polydata = conn.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        del conn

    #Filter used to detect and fill holes. Only fill boundary edges holes.
    #TODO: Hey! This piece of code is the same from
    #polydata_utils.FillSurfaceHole, we need to review this.
    if fill_holes:
        filled_polydata = vtk.vtkFillHolesFilter()
        #  filled_polydata.ReleaseDataFlagOn()
        filled_polydata.SetInputData(polydata)
        filled_polydata.SetHoleSize(300)
        filled_polydata_ref = weakref.ref(filled_polydata)
        #  filled_polydata_ref().AddObserver("ProgressEvent", lambda obj,evt:
                #  UpdateProgress(filled_polydata_ref(), _("Creating 3D surface...")))
        filled_polydata.Update()
        #  filled_polydata.GetOutput().ReleaseDataFlagOn()
        del polydata
        polydata = filled_polydata.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        #  polydata.DebugOn()
        del filled_polydata

    filename = tempfile.mktemp(suffix='_full.vtp')
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetInputData(polydata)
    writer.SetFileName(filename)
    writer.Write()

    return filename


class SurfaceProcess(multiprocessing.Process):

    def __init__(self, pipe, filename, shape, dtype, mask_filename,
                 mask_shape, mask_dtype, spacing, mode, min_value, max_value,
                 decimate_reduction, smooth_relaxation_factor,
                 smooth_iterations, language, flip_image, q_in, q_out,
                 from_binary, algorithm, imagedata_resolution):

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
        self.imagedata_resolution = imagedata_resolution

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
            del a_mask
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
                gauss.SetInputData(image)
                gauss.SetRadiusFactor(0.3)
                gauss.ReleaseDataFlagOn()
                gauss.Update()

                del image
                image = gauss.GetOutput()
                del gauss
                del a_mask
            else:
                image = converters.to_vtk(a_image, self.spacing, roi.start,
                                           "AXIAL")
            del a_image

        if self.imagedata_resolution:
            # image = iu.ResampleImage3D(image, self.imagedata_resolution)
            image = ResampleImage3D(image, self.imagedata_resolution)

        flip = vtk.vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()

        del image
        image = flip.GetOutput()
        del flip

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
        contour.SetInputData(image)
        #contour.SetInput(flip.GetOutput())
        if self.from_binary:
            contour.SetValue(0, 127) # initial threshold
        else:
            contour.SetValue(0, self.min_value) # initial threshold
            contour.SetValue(1, self.max_value) # final threshold
        contour.ComputeScalarsOn()
        contour.ComputeGradientsOn()
        contour.ComputeNormalsOn()
        contour.ReleaseDataFlagOn()
        contour.Update()
        #contour.AddObserver("ProgressEvent", lambda obj,evt:
        #                    self.SendProgress(obj, _("Generating 3D surface...")))
        polydata = contour.GetOutput()
        del image
        del contour

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
        writer.SetInputData(polydata)
        writer.SetFileName(filename)
        writer.Write()

        print("Writing piece", roi, "to", filename)
        del polydata
        del writer

        self.q_out.put(filename)
