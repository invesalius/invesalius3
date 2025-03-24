import os
import random
import tempfile
import time

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
    vtkWindowedSincPolyDataFilter,
)
from vtkmodules.vtkFiltersModeling import vtkFillHolesFilter
from vtkmodules.vtkImagingCore import vtkImageFlip, vtkImageResample
from vtkmodules.vtkImagingGeneral import vtkImageGaussianSmooth
from vtkmodules.vtkIOXML import vtkXMLPolyDataReader, vtkXMLPolyDataWriter

import invesalius.data.converters as converters
from invesalius.gui.log import invLogger
from invesalius.utils import TempFileManager
from invesalius_cy import cy_mesh

logger = invLogger.getLogger("invesalius.surface_process")


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
    temp_manager = TempFileManager()
    logger.info(f"Creating surface piece for ROI {roi}")

    log_fd, log_path = tempfile.mkstemp("vtkoutput.txt")
    temp_manager.register_temp_file(log_path)
    logger.debug(f"Created and registered VTK log file: {log_path}")

    fow = vtkFileOutputWindow()
    fow.SetFileName(log_path)
    ow = vtkOutputWindow()
    ow.SetInstance(fow)
    os.close(log_fd)

    try:
        pad_bottom = roi.start == 0
        pad_top = roi.stop >= shape[0]

        if fill_border_holes:
            padding = (1, 1, pad_bottom)
        else:
            padding = (0, 0, 0)

        if from_binary:
            mask = numpy.memmap(mask_filename, mode="r", dtype=mask_dtype, shape=mask_shape)
            if fill_border_holes:
                a_mask = pad_image(
                    mask[roi.start + 1 : roi.stop + 1, 1:, 1:], 0, pad_bottom, pad_top
                )
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
                image = converters.to_vtk(a_image, spacing, roi.start, "AXIAL", padding=padding)
            del a_image

        flip = vtkImageFlip()
        flip.SetInputData(image)
        flip.SetFilteredAxis(1)
        flip.FlipAboutOriginOn()
        flip.ReleaseDataFlagOn()
        flip.Update()

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
        contour.ReleaseDataFlagOn()
        contour.Update()

        polydata = contour.GetOutput()
        del image
        del contour

        fd, piece_filename = tempfile.mkstemp(suffix="_%d_%d.vtp" % (roi.start, roi.stop))
        temp_manager.register_temp_file(piece_filename)
        logger.debug(f"Created and registered surface piece file: {piece_filename}")

        writer = vtkXMLPolyDataWriter()
        writer.SetInputData(polydata)
        writer.SetFileName(piece_filename)
        writer.Write()

        logger.info(f"Successfully wrote surface piece {roi} to {piece_filename}")
        os.close(fd)
        return piece_filename

    except Exception as e:
        logger.error(f"Error creating surface piece: {str(e)}")
        raise
    finally:
        logger.debug(f"Cleaning up VTK log file: {log_path}")
        temp_manager.decrement_refs(log_path)


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
    def send_message(msg, max_retries=3):
        """Send a message to the queue with retries and exponential backoff."""
        retry_count = 0
        base_delay = 0.1  # 100ms initial delay

        while retry_count < max_retries:
            try:
                msg_queue.put_nowait(msg)
                logger.debug(f"Progress message sent: {msg}")
                return True
            except queue.Full:
                retry_count += 1
                if retry_count == max_retries:
                    logger.warning(f"Message queue full, dropping message: {msg}")
                    return False

                # Exponential backoff with jitter
                delay = base_delay * (2 ** (retry_count - 1)) * (0.5 + random.random())
                logger.debug(
                    f"Queue full, retrying in {delay:.2f}s (attempt {retry_count}/{max_retries})"
                )
                time.sleep(delay)

        return False

    temp_manager = TempFileManager()
    logger.info("Starting surface joining process")
    logger.debug(f"Input piece files: {filenames}")

    log_fd, log_path = tempfile.mkstemp("vtkoutput.txt")
    temp_manager.register_temp_file(log_path)
    logger.debug(f"Created and registered VTK log file: {log_path}")

    try:
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
        polydata = polydata_append.GetOutput()
        del polydata_append

        send_message("Cleaning surface ...")
        clean = vtkCleanPolyData()
        clean.SetInputData(polydata)
        clean.PointMergingOn()
        clean.Update()

        del polydata
        polydata = clean.GetOutput()
        del clean

        if keep_largest:
            send_message("Keeping largest surface ...")
            connectivity = vtkPolyDataConnectivityFilter()
            connectivity.SetInputData(polydata)
            connectivity.SetExtractionModeToLargestRegion()
            connectivity.Update()
            del polydata
            polydata = connectivity.GetOutput()
            del connectivity

        if decimate_reduction:
            send_message("Decimating surface ...")
            decimate = vtkQuadricDecimation()
            decimate.SetInputData(polydata)
            decimate.SetTargetReduction(decimate_reduction)
            decimate.Update()
            del polydata
            polydata = decimate.GetOutput()
            del decimate

        if smooth_iterations and smooth_relaxation_factor:
            send_message("Smoothing surface ...")
            smooth = vtkWindowedSincPolyDataFilter()
            smooth.SetInputData(polydata)
            smooth.SetNumberOfIterations(smooth_iterations)
            smooth.SetFeatureEdgeSmoothing(False)
            smooth.SetFeatureAngle(120.0)
            smooth.SetEdgeAngle(90.0)
            smooth.SetPassBand(smooth_relaxation_factor)
            smooth.SetBoundarySmoothing(False)
            smooth.Update()
            del polydata
            polydata = smooth.GetOutput()
            del smooth

        if fill_holes:
            send_message("Filling holes ...")
            filled_polydata = vtkFillHolesFilter()
            filled_polydata.SetInputData(polydata)
            filled_polydata.SetHoleSize(300)
            filled_polydata.Update()
            del polydata
            polydata = filled_polydata.GetOutput()
            del filled_polydata

        to_measure = polydata

        normals = vtkPolyDataNormals()
        normals.SetInputData(polydata)
        normals.SetFeatureAngle(80)
        normals.SplittingOn()
        normals.AutoOrientNormalsOn()
        normals.NonManifoldTraversalOn()
        normals.ComputeCellNormalsOn()
        normals.Update()
        del polydata
        polydata = normals.GetOutput()
        del normals

        send_message("Calculating area and volume ...")
        measured_polydata = vtkMassProperties()
        measured_polydata.SetInputData(to_measure)
        measured_polydata.Update()
        volume = float(measured_polydata.GetVolume())
        area = float(measured_polydata.GetSurfaceArea())
        del measured_polydata

        fd, final_filename = tempfile.mkstemp(suffix="_full.vtp")
        temp_manager.register_temp_file(final_filename)
        logger.debug(f"Created and registered final surface file: {final_filename}")

        writer = vtkXMLPolyDataWriter()
        writer.SetInputData(polydata)
        writer.SetFileName(final_filename)
        writer.Write()

        logger.info(f"Successfully created final surface: {final_filename}")
        logger.debug(f"Surface metrics - Volume: {volume}, Area: {area}")

        os.close(fd)
        return final_filename, {"volume": volume, "area": area}

    except Exception as e:
        logger.error(f"Error joining surfaces: {str(e)}")
        raise
    finally:
        logger.debug(f"Cleaning up VTK log file: {log_path}")
        temp_manager.decrement_refs(log_path)

        logger.debug("Cleaning up intermediate piece files")
        for f in filenames:
            logger.debug(f"Removing piece file: {f}")
            temp_manager.decrement_refs(f)
