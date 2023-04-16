import os
import tempfile
import weakref
from typing import Optional, Tuple




try:
    import queue
except ImportError:
    import Queue as queue

import numpy
from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow
from vtkmodules.vtkFiltersCore import (
    vtkAppendPolyData,
    vtkCleanPolyData,
    vtkContourFilter,
    vtkMassProperties,
    vtkPolyDataConnectivityFilter,
    vtkPolyDataNormals,
    vtkQuadricDecimation,
)
from vtkmodules.vtkFiltersModeling import vtkFillHolesFilter
from vtkmodules.vtkImagingCore import vtkImageFlip, vtkImageResample
from vtkmodules.vtkImagingGeneral import vtkImageGaussianSmooth
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLPolyDataWriter

import invesalius.data.converters as converters
from invesalius_cy import cy_mesh


# TODO: Code duplicated from file {imagedata_utils.py}.
def ResampleImage3D(imagedata: vtkImageData, value: float) -> vtkImageData:
    """
    Resample vtkImageData matrix.
    """
    spacing = imagedata.GetSpacing()
    extent = imagedata.GetExtent()
    size = imagedata.GetDimensions()

    width = float(size[0])
    height = float(size[1]/value)

    resolution = (height/(extent[1]-extent[0])+1)*spacing[1]

    resample = vtkImageResample()
    resample.SetInputData(imagedata)
    resample.SetAxisMagnificationFactor(0, resolution)
    resample.SetAxisMagnificationFactor(1, resolution)

    return resample.GetOutput()


def pad_image(image: numpy.ndarray, pad_value: int, pad_bottom: bool, pad_top: bool) -> numpy.ndarray:
    dz, dy, dx = image.shape
    z_iadd = 0
    z_eadd = 0
    if pad_bottom:
        z_iadd = 1
        dz += 1
    if pad_top:
        z_eadd = 1
        dz += 1
    new_shape = dz, dy + 2, dx + 2

    paded_image = numpy.empty(shape=new_shape, dtype=image.dtype)
    paded_image[:] = pad_value
    paded_image[z_iadd: z_iadd + image.shape[0], 1:-1, 1:-1] = image

    return paded_image


def create_surface_piece(filename: str, shape: tuple, dtype: type, mask_filename: str, mask_shape: tuple,
                         mask_dtype: type, roi: slice, spacing: tuple, mode: str, min_value: int, max_value: int,
                         decimate_reduction: float, smooth_relaxation_factor: float,
                         smooth_iterations: int, language: str, flip_image: bool,
                         from_binary: bool, algorithm: str, imagedata_resolution: int, fill_border_holes: bool) -> str:


    log_path: str = tempfile.mktemp('vtkoutput.txt')
    fow: vtkFileOutputWindow = vtkFileOutputWindow()
    fow.SetFileName(log_path)
    ow: vtkOutputWindow = vtkOutputWindow()
    ow.SetInstance(fow)

    pad_bottom: bool = (roi.start == 0)
    pad_top: bool = (roi.stop >= shape[0])

    if fill_border_holes:
        padding: tuple = (1, 1, pad_bottom)
    else:
        padding: tuple = (0, 0, 0)

    if from_binary:
        mask: numpy.memmap = numpy.memmap(mask_filename, mode='r',
                                dtype=mask_dtype,
                                shape=mask_shape)
        if fill_border_holes:
            a_mask: numpy.array = pad_image(mask[roi.start + 1: roi.stop + 1, 1:, 1:], 0, pad_bottom, pad_top)
        else:
            a_mask: numpy.array = numpy.array(mask[roi.start + 1: roi.stop + 1, 1:, 1:])
        image: vtkImageData =  converters.to_vtk(a_mask, spacing, roi.start, "AXIAL", padding=padding)
        del a_mask
    else:
        image: numpy.memmap = numpy.memmap(filename, mode='r', dtype=dtype,
                                shape=shape)
        mask: numpy.memmap = numpy.memmap(mask_filename, mode='r',
                                dtype=mask_dtype,
                                shape=mask_shape)
        if fill_border_holes:
            a_image: numpy.array = pad_image(image[roi], numpy.iinfo(image.dtype).min, pad_bottom, pad_top)
        else:
            a_image: numpy.array = numpy.array(image[roi])
        #  if z_iadd:
            #  a_image[0, 1:-1, 1:-1] = image[0]
        #  if z_eadd:
            #  a_image[-1, 1:-1, 1:-1] = image[-1]

        if algorithm == u'InVesalius 3.b2':
            a_mask: numpy.array = numpy.array(mask[roi.start + 1: roi.stop + 1, 1:, 1:])
            a_image[a_mask == 1] = a_image.min() - 1
            a_image[a_mask == 254] = (min_value + max_value) / 2.0

            image: vtkImageData =  converters.to_vtk(a_image, spacing, roi.start, "AXIAL", padding=padding)

            gauss: vtkImageGaussianSmooth = vtkImageGaussianSmooth()
            gauss.SetInputData(image)
            gauss.SetRadiusFactor(0.3)
            gauss.ReleaseDataFlagOn()
            gauss.Update()

            del image
            image: vtkImageData = gauss.GetOutput()
            del gauss
            del a_mask
        else:
            #  if z_iadd:
                #  origin = -spacing[0], -spacing[1], -spacing[2]
            #  else:
                #  origin = 0, -spacing[1], -spacing[2]
            image: vtkImageData = converters.to_vtk(a_image, spacing, roi.start, "AXIAL", padding=padding)
        del a_image

    #  if imagedata_resolution:
        #  image = ResampleImage3D(image, imagedata_resolution)

    flip: vtkImageFlip = vtkImageFlip()
    flip.SetInputData(image)
    flip.SetFilteredAxis(1)
    flip.FlipAboutOriginOn()
    flip.ReleaseDataFlagOn()
    flip.Update()

    #  writer = vtkXMLImageDataWriter()
    #  writer.SetFileName('/tmp/camboja.vti')
    #  writer.SetInputData(flip.GetOutput())
    #  writer.Write()

    del image
    image: vtkImageData = flip.GetOutput()
    del flip

    contour: vtkContourFilter = vtkContourFilter()
    contour.SetInputData(image)
    if from_binary:
        contour.SetValue(0, 127) # initial threshold
    else:
        contour.SetValue(0, min_value) # initial threshold
        contour.SetValue(1, max_value) # final threshold
    #  contour.ComputeScalarsOn()
    #  contour.ComputeGradientsOn()
    #  contour.ComputeNormalsOn()
    contour.ReleaseDataFlagOn()
    contour.Update()

    polydata: vtkPolyData = contour.GetOutput()
    del image
    del contour

    filename: str = tempfile.mktemp(suffix='_%d_%d.vtp' % (roi.start, roi.stop))
    writer: vtkXMLPolyDataWriter = vtkXMLPolyDataWriter()
    writer.SetInputData(polydata)
    writer.SetFileName(filename)
    writer.Write()

    print("Writing piece", roi, "to", filename)
    print("MY PID MC", os.getpid())
    return filename

def join_process_surface(filenames: list, algorithm: str, smooth_iterations: int, smooth_relaxation_factor: float, decimate_reduction: float, keep_largest: bool, fill_holes: bool, options: dict, msg_queue: queue.Queue) -> None:
    def send_message(msg: str) -> None:
        try:
            msg_queue.put_nowait(msg)
        except queue.Full as e:
            print(e)

    log_path: str = tempfile.mktemp('vtkoutput.txt')
    fow: vtkFileOutputWindow = vtkFileOutputWindow()
    fow.SetFileName(log_path)
    ow: vtkOutputWindow = vtkOutputWindow()
    ow.SetInstance(fow)

    send_message('Joining surfaces ...')
    polydata_append: vtkAppendPolyData = vtkAppendPolyData()
    for f in filenames:
        reader: vtkXMLPolyDataReader = vtkXMLPolyDataReader()
        reader.SetFileName(f)
        reader.Update()

        polydata: vtkPolyData = reader.GetOutput()

        polydata_append.AddInputData(polydata)
        del reader
        del polydata

    polydata_append.Update()
    #  polydata_append.GetOutput().ReleaseDataFlagOn()
    polydata: vtkPolyData = polydata_append.GetOutput()
    #polydata.Register(None)
    #  polydata.SetSource(None)
    del polydata_append

    send_message('Cleaning surface ...')
    clean: vtkCleanPolyData = vtkCleanPolyData()
    #  clean.ReleaseDataFlagOn()
    #  clean.GetOutput().ReleaseDataFlagOn()
    clean_ref: weakref.ref = weakref.ref(clean)
    #  clean_ref().AddObserver("ProgressEvent", lambda obj,evt:
                    #  UpdateProgress(clean_ref(), _("Creating 3D surface...")))
    clean.SetInputData(polydata)
    clean.PointMergingOn()
    clean.Update()

    del polydata
    polydata: vtkPolyData = clean.GetOutput()
    #  polydata.SetSource(None)
    del clean

    if algorithm == 'ca_smoothing':
        send_message('Calculating normals ...')
        normals: vtkPolyDataNormals = vtkPolyDataNormals()
        normals_ref: weakref.ref = weakref.ref(normals)
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
        polydata: vtkPolyData = normals.GetOutput()
        #  polydata.SetSource(None)
        del normals

        clean: vtkCleanPolyData = vtkCleanPolyData()
        #  clean.ReleaseDataFlagOn()
        #  clean.GetOutput().ReleaseDataFlagOn()
        clean_ref: weakref.ref = weakref.ref(clean)
        #  clean_ref().AddObserver("ProgressEvent", lambda obj,evt:
                        #  UpdateProgress(clean_ref(), _("Creating 3D surface...")))
        clean.SetInputData(polydata)
        clean.PointMergingOn()
        clean.Update()

        del polydata
        polydata: vtkPolyData = clean.GetOutput()
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

        send_message('Context Aware smoothing ...')
        mesh = cy_mesh.Mesh(polydata)
        cy_mesh.ca_smoothing(mesh, options['angle'],
                             options['max distance'],
                             options['min weight'],
                             options['steps'])
        #  polydata = mesh.to_vtk()

        #  polydata.SetSource(None)
        #  polydata.DebugOn()
    #  else:
        #  #smoother = vtkWindowedSincPolyDataFilter()
        #  send_message('Smoothing ...')
        #  smoother: vtkSmoothPolyDataFilter = vtkSmoothPolyDataFilter()
        #  smoother_ref: weakref.ref = weakref.ref(smoother)
        #  #  smoother_ref().AddObserver("ProgressEvent", lambda obj,evt:
                        #  #  UpdateProgress(smoother_ref(), _("Creating 3D surface...")))
        #  smoother.SetInputData(polydata)
        #  smoother.SetNumberOfIterations(smooth_iterations: int)
        #  smoother.SetRelaxationFactor(smooth_relaxation_factor: float)
        #  smoother.SetFeatureAngle(80)
        #  #smoother.SetEdgeAngle(90.0)
        #  #smoother.SetPassBand(0.1)
        #  smoother.BoundarySmoothingOn()
        #  smoother.FeatureEdgeSmoothingOn()
        #  #smoother.NormalizeCoordinatesOn()
        #  #smoother.NonManifoldSmoothingOn()
        #  #  smoother.ReleaseDataFlagOn()
        #  #  smoother.GetOutput().ReleaseDataFlagOn()
        #  smoother.Update()
        #  del polydata
        #  polydata: vtkPolyData = smoother.GetOutput()
        #  #polydata.Register(None)
        #  #  polydata.SetSource(None)
        #  del smoother


    if not decimate_reduction:
        print("Decimating", decimate_reduction)
        send_message('Decimating ...')
        decimation: vtkQuadricDecimation = vtkQuadricDecimation()
        #  decimation.ReleaseDataFlagOn()
        decimation.SetInputData(polydata)
        decimation.SetTargetReduction(decimate_reduction)
        decimation_ref: weakref.ref = weakref.ref(decimation)
        #  decimation_ref().AddObserver("ProgressEvent", lambda obj,evt:
                        #  UpdateProgress(decimation_ref(), _("Creating 3D surface...")))
        #decimation.PreserveTopologyOn()
        #decimation.SplittingOff()
        #decimation.BoundaryVertexDeletionOff()
        #  decimation.GetOutput().ReleaseDataFlagOn()
        decimation.Update()
        del polydata
        polydata: vtkPolyData = decimation.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        del decimation

    #to_measure.Register(None)
    #  to_measure.SetSource(None)

    if keep_largest:
        send_message('Finding the largest ...')
        conn: vtkPolyDataConnectivityFilter = vtkPolyDataConnectivityFilter()
        conn.SetInputData(polydata)
        conn.SetExtractionModeToLargestRegion()
        conn_ref: weakref.ref = weakref.ref(conn)
        #  conn_ref().AddObserver("ProgressEvent", lambda obj,evt:
                #  UpdateProgress(conn_ref(), _("Creating 3D surface...")))
        conn.Update()
        #  conn.GetOutput().ReleaseDataFlagOn()
        del polydata
        polydata: vtkPolyData = conn.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        del conn

    #Filter used to detect and fill holes. Only fill boundary edges holes.
    #TODO: Hey! This piece of code is the same from
    #polydata_utils.FillSurfaceHole, we need to review this.
    if fill_holes:
        send_message('Filling holes ...')
        filled_polydata: vtkFillHolesFilter = vtkFillHolesFilter()
        #  filled_polydata.ReleaseDataFlagOn()
        filled_polydata.SetInputData(polydata)
        filled_polydata.SetHoleSize(300)
        filled_polydata_ref: weakref.ref = weakref.ref(filled_polydata)
        #  filled_polydata_ref().AddObserver("ProgressEvent", lambda obj,evt:
                #  UpdateProgress(filled_polydata_ref(), _("Creating 3D surface...")))
        filled_polydata.Update()
        #  filled_polydata.GetOutput().ReleaseDataFlagOn()
        del polydata
        polydata: vtkPolyData = filled_polydata.GetOutput()
        #polydata.Register(None)
        #  polydata.SetSource(None)
        #  polydata.DebugOn()
        del filled_polydata

    to_measure: vtkPolyData = polydata

    normals: vtkPolyDataNormals = vtkPolyDataNormals()
    #  normals.ReleaseDataFlagOn()
    #  normals_ref: weakref.ref = weakref.ref(normals)
    #  normals_ref().AddObserver("ProgressEvent", lambda obj,evt:
                    #  UpdateProgress(normals_ref(), _("Creating 3D surface...")))
    normals.SetInputData(polydata)
    normals.SetFeatureAngle(80)
    normals.SplittingOn()
    normals.AutoOrientNormalsOn()
    normals.NonManifoldTraversalOn()
    normals.ComputeCellNormalsOn()
    #  normals.GetOutput().ReleaseDataFlagOn()
    normals.Update()
    del polydata
    polydata: vtkPolyData = normals.GetOutput()
    #polydata.Register(None)
    #  polydata.SetSource(None)
    del normals


    #  # Improve performance
    #  stripper: vtkStripper = vtkStripper()
    #  #  stripper.ReleaseDataFlagOn()
    #  #  stripper_ref: weakref.ref = weakref.ref(stripper)
    #  #  stripper_ref().AddObserver("ProgressEvent", lambda obj,evt:
                    #  #  UpdateProgress(stripper_ref(), _("Creating 3D surface...")))
    #  stripper.SetInputData(polydata)
    #  stripper.PassThroughCellIdsOn()
    #  stripper.PassThroughPointIdsOn()
    #  #  stripper.GetOutput().ReleaseDataFlagOn()
    #  stripper.Update()
    #  del polydata
    #  polydata: vtkPolyData = stripper.GetOutput()
    #  #polydata.Register(None)
    #  #  polydata.SetSource(None)
    #  del stripper

    send_message('Calculating area and volume ...')
    measured_polydata: vtkMassProperties = vtkMassProperties()
    measured_polydata.SetInputData(to_measure)
    measured_polydata.Update()
    volume: float =  float(measured_polydata.GetVolume())
    area: float =  float(measured_polydata.GetSurfaceArea())
    del measured_polydata

    filename: str = tempfile.mktemp(suffix='_full.vtp')
    writer: vtkXMLPolyDataWriter = vtkXMLPolyDataWriter()
    writer.SetInputData(polydata)
    writer.SetFileName(filename)
    writer.Write()
    del writer

    print("MY PID", os.getpid())
    return filename, {'volume': volume, 'area': area}
