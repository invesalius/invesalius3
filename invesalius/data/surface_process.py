import os
import tempfile

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
def ResampleImage3D(imagedata, value):
    """
    Resample vtkImageData matrix.
    """
    spacing = imagedata.GetSpacing()
    extent = imagedata.GetExtent()
    size = imagedata.GetDimensions()

    # width = float(size[0])
    height = float(size[1] / value)

    resolution = (height / (extent[1] - extent[0]) + 1) * spacing[1]

    resample = vtkImageResample()
    resample.SetInputData(imagedata)
    resample.SetAxisMagnificationFactor(0, resolution)
    resample.SetAxisMagnificationFactor(1, resolution)

    return resample.GetOutput()


def pad_image(image, pad_value, pad_bottom, pad_top):
    dz, dy, dx = image.shape
    z_iadd = 0
    # z_eadd = 0
    if pad_bottom:
        z_iadd = 1
        dz += 1
    if pad_top:
        # z_eadd = 1
        dz += 1
    new_shape = dz, dy + 2, dx + 2

    paded_image = numpy.empty(shape=new_shape, dtype=image.dtype)
    paded_image[:] = pad_value
    paded_image[z_iadd : z_iadd + image.shape[0], 1:-1, 1:-1] = image

    return paded_image


def create_surface_piece(
    filename,
    shape,
    dtype,
    mask_filename,
    mask_shape,
    mask_dtype,
    roi,
    spacing,
    mode,
    min_value,
    max_value,
    decimate_reduction,
    smooth_relaxation_factor,
    smooth_iterations,
    language,
    flip_image,
    from_binary,
    algorithm,
    imagedata_resolution,
    fill_border_holes,
):
    log_fd, log_path = tempfile.mkstemp("vtkoutput.txt")
    fow = vtkFileOutputWindow()
    fow.SetFileName(log_path)
    ow = vtkOutputWindow()
    ow.SetInstance(fow)
    os.close(log_fd)

    pad_bottom = roi.start == 0
    pad_top = roi.stop >= shape[0]

    if fill_border_holes:
        padding = (1, 1, pad_bottom)
    else:
        padding = (0, 0, 0)

    if from_binary:
        mask = numpy.memmap(mask_filename, mode="r", dtype=mask_dtype, shape=mask_shape)
        if fill_border_holes:
            a_mask = pad_image(mask[roi.start + 1 : roi.stop + 1, 1:, 1:], 0, pad_bottom, pad_top)
        else:
            a_mask = numpy.array(mask[roi.start + 1 : roi.stop + 1, 1:, 1:])
        image = converters.to_vtk(a_mask, spacing, roi.start, "AXIAL", padding=padding)
        del a_mask
    else:
        image = numpy.memmap(filename, mode="r", dtype=dtype, shape=shape)
        mask = numpy.memmap(mask_filename, mode="r", dtype=mask_dtype, shape=mask_shape)
        if fill_border_holes:
            a_image = pad_image(image[roi], numpy.iinfo(image.dtype).min, pad_bottom, pad_top)
        else:
            a_image = numpy.array(image[roi])
        #  if z_iadd:
        #  a_image[0, 1:-1, 1:-1] = image[0]
        #  if z_eadd:
        #  a_image[-1, 1:-1, 1:-1] = image[-1]

        if algorithm == "InVesalius 3.b2":
            a_mask = numpy.array(mask[roi.start + 1 : roi.stop + 1, 1:, 1:])
            a_image[a_mask == 1] = a_image.min() - 1
            a_image[a_mask == 254] = (min_value + max_value) / 2.0

            image = converters.to_vtk(a_image, spacing, roi.start, "AXIAL", padding=padding)

            gauss = vtkImageGaussianSmooth()
            gauss.SetInputData(image)
            gauss.SetRadiusFactor(0.3)
            gauss.ReleaseDataFlagOn()
            gauss.Update()

            del image
            image = gauss.GetOutput()
            del gauss
            del a_mask
        else:
            #  if z_iadd:
            #  origin = -spacing[0], -spacing[1], -spacing[2]
            #  else:
            #  origin = 0, -spacing[1], -spacing[2]
            image = converters.to_vtk(a_image, spacing, roi.start, "AXIAL", padding=padding)
        del a_image

    #  if imagedata_resolution:
    #  image = ResampleImage3D(image, imagedata_resolution)

    flip = vtkImageFlip()
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
    image = flip.GetOutput()
    del flip

    contour = vtkContourFilter()
    contour.SetInputData(image)
    if from_binary:
        contour.SetValue(0, 127)  # initial threshold
    else:
        contour.SetValue(0, min_value)  # initial threshold
        contour.SetValue(1, max_value)  # final threshold
    #  contour.ComputeScalarsOn()
    #  contour.ComputeGradientsOn()
    #  contour.ComputeNormalsOn()
    contour.ReleaseDataFlagOn()
    contour.Update()

    polydata = contour.GetOutput()
    del image
    del contour

    fd, filename = tempfile.mkstemp(suffix="_%d_%d.vtp" % (roi.start, roi.stop))
    writer = vtkXMLPolyDataWriter()
    writer.SetInputData(polydata)
    writer.SetFileName(filename)
    writer.Write()

    print("Writing piece", roi, "to", filename)
    print("MY PID MC", os.getpid())
    os.close(fd)
    return filename


def join_process_surface(
    filenames,
    algorithm,
    smooth_iterations,
    smooth_relaxation_factor,
    decimate_reduction,
    keep_largest,
    fill_holes,
    options,
    msg_queue,
):
    def send_message(msg):
        try:
            msg_queue.put_nowait(msg)
        except queue.Full as e:
            print(e)

    log_fd, log_path = tempfile.mkstemp("vtkoutput.txt")
    fow = vtkFileOutputWindow()
    fow.SetFileName(log_path)
    ow = vtkOutputWindow()
    ow.SetInstance(fow)
    os.close(log_fd)

    send_message("Joining surfaces ...")
    polydata_append = vtkAppendPolyData()
    for f in filenames:
        reader = vtkXMLPolyDataReader()
        reader.SetFileName(f)
        reader.Update()

        polydata = reader.GetOutput()

        polydata_append.AddInputData(polydata)
        del reader
        del polydata

    polydata_append.Update()
    #  polydata_append.GetOutput().ReleaseDataFlagOn()
    polydata = polydata_append.GetOutput()
    # polydata.Register(None)
    #  polydata.SetSource(None)
    del polydata_append

    send_message("Cleaning surface ...")
    clean = vtkCleanPolyData()
    #  clean.ReleaseDataFlagOn()
    #  clean.GetOutput().ReleaseDataFlagOn()
    # clean_ref = weakref.ref(clean)
    #  clean_ref().AddObserver("ProgressEvent", lambda obj,evt:
    #  UpdateProgress(clean_ref(), _("Creating 3D surface...")))
    clean.SetInputData(polydata)
    clean.PointMergingOn()
    clean.Update()

    del polydata
    polydata = clean.GetOutput()
    #  polydata.SetSource(None)
    del clean

    if algorithm == "ca_smoothing":
        send_message("Calculating normals ...")
        normals = vtkPolyDataNormals()
        # normals_ref = weakref.ref(normals)
        #  normals_ref().AddObserver("ProgressEvent", lambda obj,evt:
        #  UpdateProgress(normals_ref(), _("Creating 3D surface...")))
        normals.SetInputData(polydata)
        #  normals.ReleaseDataFlagOn()
        # normals.SetFeatureAngle(80)
        # normals.AutoOrientNormalsOn()
        normals.ComputeCellNormalsOn()
        #  normals.GetOutput().ReleaseDataFlagOn()
        normals.Update()
        del polydata
        polydata = normals.GetOutput()
        #  polydata.SetSource(None)
        del normals

        clean = vtkCleanPolyData()
        #  clean.ReleaseDataFlagOn()
        #  clean.GetOutput().ReleaseDataFlagOn()
        # clean_ref = weakref.ref(clean)
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

        send_message("Context Aware smoothing ...")
        mesh = cy_mesh.Mesh(polydata)
        cy_mesh.ca_smoothing(
            mesh, options["angle"], options["max distance"], options["min weight"], options["steps"]
        )
        #  polydata = mesh.to_vtk()

        #  polydata.SetSource(None)
        #  polydata.DebugOn()
    #  else:
    #  #smoother = vtkWindowedSincPolyDataFilter()
    #  send_message('Smoothing ...')
    #  smoother = vtkSmoothPolyDataFilter()
    #  smoother_ref = weakref.ref(smoother)
    #  #  smoother_ref().AddObserver("ProgressEvent", lambda obj,evt:
    #  #  UpdateProgress(smoother_ref(), _("Creating 3D surface...")))
    #  smoother.SetInputData(polydata)
    #  smoother.SetNumberOfIterations(smooth_iterations)
    #  smoother.SetRelaxationFactor(smooth_relaxation_factor)
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
    #  polydata = smoother.GetOutput()
    #  #polydata.Register(None)
    #  #  polydata.SetSource(None)
    #  del smoother

    if not decimate_reduction:
        print("Decimating", decimate_reduction)
        send_message("Decimating ...")
        decimation = vtkQuadricDecimation()
        #  decimation.ReleaseDataFlagOn()
        decimation.SetInputData(polydata)
        decimation.SetTargetReduction(decimate_reduction)
        # decimation_ref = weakref.ref(decimation)
        #  decimation_ref().AddObserver("ProgressEvent", lambda obj,evt:
        #  UpdateProgress(decimation_ref(), _("Creating 3D surface...")))
        # decimation.PreserveTopologyOn()
        # decimation.SplittingOff()
        # decimation.BoundaryVertexDeletionOff()
        #  decimation.GetOutput().ReleaseDataFlagOn()
        decimation.Update()
        del polydata
        polydata = decimation.GetOutput()
        # polydata.Register(None)
        #  polydata.SetSource(None)
        del decimation

    # to_measure.Register(None)
    #  to_measure.SetSource(None)

    if keep_largest:
        send_message("Finding the largest ...")
        conn = vtkPolyDataConnectivityFilter()
        conn.SetInputData(polydata)
        conn.SetExtractionModeToLargestRegion()
        # conn_ref = weakref.ref(conn)
        #  conn_ref().AddObserver("ProgressEvent", lambda obj,evt:
        #  UpdateProgress(conn_ref(), _("Creating 3D surface...")))
        conn.Update()
        #  conn.GetOutput().ReleaseDataFlagOn()
        del polydata
        polydata = conn.GetOutput()
        # polydata.Register(None)
        #  polydata.SetSource(None)
        del conn

    # Filter used to detect and fill holes. Only fill boundary edges holes.
    # TODO: Hey! This piece of code is the same from
    # polydata_utils.FillSurfaceHole, we need to review this.
    if fill_holes:
        send_message("Filling holes ...")
        filled_polydata = vtkFillHolesFilter()
        #  filled_polydata.ReleaseDataFlagOn()
        filled_polydata.SetInputData(polydata)
        filled_polydata.SetHoleSize(300)
        # filled_polydata_ref = weakref.ref(filled_polydata)
        #  filled_polydata_ref().AddObserver("ProgressEvent", lambda obj,evt:
        #  UpdateProgress(filled_polydata_ref(), _("Creating 3D surface...")))
        filled_polydata.Update()
        #  filled_polydata.GetOutput().ReleaseDataFlagOn()
        del polydata
        polydata = filled_polydata.GetOutput()
        # polydata.Register(None)
        #  polydata.SetSource(None)
        #  polydata.DebugOn()
        del filled_polydata

    to_measure = polydata

    normals = vtkPolyDataNormals()
    #  normals.ReleaseDataFlagOn()
    #  normals_ref = weakref.ref(normals)
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
    polydata = normals.GetOutput()
    # polydata.Register(None)
    #  polydata.SetSource(None)
    del normals

    #  # Improve performance
    #  stripper = vtkStripper()
    #  #  stripper.ReleaseDataFlagOn()
    #  #  stripper_ref = weakref.ref(stripper)
    #  #  stripper_ref().AddObserver("ProgressEvent", lambda obj,evt:
    #  #  UpdateProgress(stripper_ref(), _("Creating 3D surface...")))
    #  stripper.SetInputData(polydata)
    #  stripper.PassThroughCellIdsOn()
    #  stripper.PassThroughPointIdsOn()
    #  #  stripper.GetOutput().ReleaseDataFlagOn()
    #  stripper.Update()
    #  del polydata
    #  polydata = stripper.GetOutput()
    #  #polydata.Register(None)
    #  #  polydata.SetSource(None)
    #  del stripper

    send_message("Calculating area and volume ...")
    measured_polydata = vtkMassProperties()
    measured_polydata.SetInputData(to_measure)
    measured_polydata.Update()
    volume = float(measured_polydata.GetVolume())
    area = float(measured_polydata.GetSurfaceArea())
    del measured_polydata

    fd, filename = tempfile.mkstemp(suffix="_full.vtp")
    writer = vtkXMLPolyDataWriter()
    writer.SetInputData(polydata)
    writer.SetFileName(filename)
    writer.Write()
    del writer

    print("MY PID", os.getpid())
    os.close(fd)
    return filename, {"volume": volume, "area": area}
