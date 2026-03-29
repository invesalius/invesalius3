import logging
import os
import tempfile
import time

try:
    import queue
except ImportError:
    import Queue as queue

import numpy
import numpy as np
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow, vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import (
    vtkAppendPolyData,
    vtkCleanPolyData,
    vtkContourFilter,
    vtkMassProperties,
    vtkPolyDataConnectivityFilter,
    vtkPolyDataNormals,
    vtkQuadricDecimation,
    vtkTriangleFilter,
)
from vtkmodules.vtkFiltersModeling import vtkFillHolesFilter
from vtkmodules.vtkImagingCore import vtkImageFlip, vtkImageResample
from vtkmodules.vtkImagingGeneral import vtkImageGaussianSmooth
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLPolyDataWriter

import invesalius.data.converters as converters
import invesalius_rs as cy_mesh

logger = logging.getLogger(__name__)


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


def _configure_vtk_output_window():
    log_fd, log_path = tempfile.mkstemp("vtkoutput.txt")
    fow = vtkFileOutputWindow()
    fow.SetFileName(log_path)
    ow = vtkOutputWindow()
    ow.SetInstance(fow)
    os.close(log_fd)


def triangles_to_vtk_polydata(vertices, faces):
    import numpy as np

    polydata = vtkPolyData()
    if len(vertices) == 0 or len(faces) == 0:
        return polydata

    # Enforce float64 for VTK transformation precision alignment
    vertices = np.ascontiguousarray(vertices, dtype=np.float64)
    # Mirror in MT Y mapping flips handedness, so reverse winding to keep normals consistent.
    faces = faces[:, ::-1]
    faces = np.ascontiguousarray(faces, dtype=np.int64)

    vtk_points = vtkPoints()
    vtk_points.SetDataTypeToDouble()
    vtk_points.SetData(numpy_support.numpy_to_vtk(vertices, deep=1))

    face_cells = np.empty((faces.shape[0], 4), dtype=np.int64)
    face_cells[:, 0] = 3
    face_cells[:, 1:] = faces

    vtk_faces = vtkCellArray()
    vtk_faces.SetCells(
        faces.shape[0], numpy_support.numpy_to_vtkIdTypeArray(face_cells.reshape(-1), deep=1)
    )

    polydata.SetPoints(vtk_points)
    polydata.SetPolys(vtk_faces)
    return polydata


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
    _configure_vtk_output_window()

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

    pre_flip_image = image  # MT reads scalar data from pre-flip image coordinates

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

    if "tetrahedra" in algorithm:

        dims = pre_flip_image.GetDimensions()
        scalars = pre_flip_image.GetPointData().GetScalars()
        np_arr = numpy_support.vtk_to_numpy(scalars)

        # VTK point data is flattened: shape (Z, Y, X)
        np_arr = np_arr.reshape(dims[2], dims[1], dims[0])

        print("[PERF][MT] create_surface_piece")
        start = time.perf_counter()

        # Marching tetrahedra Rust backend uses a threshold of 127
        if np_arr.dtype != np.uint8:
            bin_mask = np.clip(np_arr, 0, 255).astype(np.uint8, copy=False)
        else:
            bin_mask = np_arr

        spacing_xyz = pre_flip_image.GetSpacing()
        vertices, faces = cy_mesh.marching_tetrahedra(bin_mask, spacing_xyz)
        duration = time.perf_counter() - start
        print(f"[PERF][MT] Rust extraction (sub-chunk): {duration:.4f}s")

        # Align MT vertices with vtkContourFilter world coordinates:
        # Rust emits coordinates in chunk-local index space scaled by spacing,
        # so apply only world-origin translation from image extent/origin.
        if len(vertices) > 0:
            vertices = np.asarray(vertices, dtype=np.float64)
            origin = pre_flip_image.GetOrigin()
            extent = pre_flip_image.GetExtent()
            tx = origin[0] + extent[0] * spacing_xyz[0]
            tz = origin[2] + extent[4] * spacing_xyz[2]
            vertices[:, 0] += tx
            # vtkImageFlip(axis=1, FlipAboutOriginOn) mirrors world Y about origin.
            vertices[:, 1] = -(origin[1] + extent[2] * spacing_xyz[1] + vertices[:, 1])
            vertices[:, 2] += tz

        polydata = triangles_to_vtk_polydata(vertices, faces)

        del pre_flip_image
        del image
    else:
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
        start = time.perf_counter()
        contour.Update()
        duration = time.perf_counter() - start
        print(f"[PERF] Extraction (vtkContourFilter): {duration:.4f}s")

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

    start = time.perf_counter()
    polydata_append.Update()
    duration = time.perf_counter() - start
    print(f"[PERF] Joining surface pieces: {duration:.4f}s")
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
    if "tetrahedra" in algorithm:
        clean.SetToleranceIsAbsolute(True)
        # Handle f32 float boundary math artifacts from Cython extraction
        clean.SetAbsoluteTolerance(1e-3)
        print(
            f"[PERF][MT] Pre-clean point count: {polydata.GetNumberOfPoints()}, "
            f"face count: {polydata.GetNumberOfCells()}"
        )
    start = time.perf_counter()
    clean.Update()
    duration = time.perf_counter() - start
    print(f"[PERF] Cleaning merged surface: {duration:.4f}s")

    del polydata
    polydata = clean.GetOutput()
    #  polydata.SetSource(None)
    del clean

    if decimate_reduction and "tetrahedra" in algorithm:
        print("Decimating (pre-smooth, MT only)", decimate_reduction)
        send_message("Decimating ...")
        decimation = vtkQuadricDecimation()
        decimation.SetInputData(polydata)
        decimation.SetTargetReduction(decimate_reduction)
        start = time.perf_counter()
        decimation.Update()
        duration = time.perf_counter() - start
        print(f"[PERF] Decimating (pre-smooth MT): {duration:.4f}s")
        del polydata
        polydata = decimation.GetOutput()
        del decimation

    if algorithm in ("ca_smoothing", "ca_smoothing_tetrahedra"):
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
        start = time.perf_counter()
        cy_mesh.ca_smoothing(
            mesh, options["angle"], options["max distance"], options["min weight"], options["steps"]
        )
        duration = time.perf_counter() - start
        print(f"[PERF] Context Aware smoothing: {duration:.4f}s")
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

    if decimate_reduction and "tetrahedra" not in algorithm:
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
        start = time.perf_counter()
        decimation.Update()
        duration = time.perf_counter() - start
        print(f"[PERF] Decimating: {duration:.4f}s")
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
        start = time.perf_counter()
        filled_polydata.Update()
        duration = time.perf_counter() - start
        print(f"[PERF] Filling holes: {duration:.4f}s")
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
    if "tetrahedra" in algorithm:
        tri_filter = vtkTriangleFilter()
        tri_filter.SetInputData(to_measure)
        tri_filter.PassVertsOff()
        tri_filter.PassLinesOff()
        tri_filter.Update()
        to_measure = tri_filter.GetOutput()

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
