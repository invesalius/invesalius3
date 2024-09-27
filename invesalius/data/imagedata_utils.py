# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

import math
import os
import tempfile

import gdcm
import imageio
import numpy as np
from scipy.ndimage import shift, zoom
from skimage.color import rgb2gray
from skimage.measure import label
from vtkmodules.util import numpy_support
from vtkmodules.vtkFiltersCore import vtkImageAppend
from vtkmodules.vtkImagingCore import vtkExtractVOI, vtkImageClip, vtkImageResample
from vtkmodules.vtkImagingGeneral import vtkImageGaussianSmooth
from vtkmodules.vtkInteractionImage import vtkImageViewer
from vtkmodules.vtkIOXML import vtkXMLImageDataReader, vtkXMLImageDataWriter

import invesalius.data.converters as converters
import invesalius.data.coordinates as dco
import invesalius.data.slice_ as sl
import invesalius.gui.dialogs as dlg
import invesalius.reader.bitmap_reader as bitmap_reader
from invesalius.data import vtk_utils as vtk_utils
from invesalius.i18n import tr as _

# TODO: Test cases which are originally in sagittal/coronal orientation
# and have gantry


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
    resample.SetInput(imagedata)
    resample.SetAxisMagnificationFactor(0, resolution)
    resample.SetAxisMagnificationFactor(1, resolution)

    return resample.GetOutput()


def ResampleImage2D(imagedata, px=None, py=None, resolution_percentage=None, update_progress=None):
    """
    Resample vtkImageData matrix.
    """

    extent = imagedata.GetExtent()
    # spacing = imagedata.GetSpacing()
    # dimensions = imagedata.GetDimensions()

    if resolution_percentage:
        factor_x = resolution_percentage
        factor_y = resolution_percentage
    else:
        if abs(extent[1] - extent[3]) < abs(extent[3] - extent[5]):
            f = extent[1]
        elif abs(extent[1] - extent[5]) < abs(extent[1] - extent[3]):
            f = extent[1]
        elif abs(extent[3] - extent[5]) < abs(extent[1] - extent[3]):
            f = extent[3]
        else:
            f = extent[1]

        factor_x = px / float(f + 1)
        factor_y = py / float(f + 1)

    resample = vtkImageResample()
    resample.SetInputData(imagedata)
    resample.SetAxisMagnificationFactor(0, factor_x)
    resample.SetAxisMagnificationFactor(1, factor_y)
    #  resample.SetOutputSpacing(spacing[0] * factor_x, spacing[1] * factor_y, spacing[2])
    if update_progress:
        message = _("Generating multiplanar visualization...")
        resample.AddObserver("ProgressEvent", lambda obj, evt: update_progress(resample, message))
    resample.Update()

    return resample.GetOutput()


def resize_slice(im_array, resolution_percentage):
    """
    Uses ndimage.zoom to resize a slice.

    input:
        im_array: slice as a numpy array.
        resolution_percentage: percentage of resize.
    """
    out = zoom(im_array, resolution_percentage, im_array.dtype, order=2)
    return out


def resize_image_array(image, resolution_percentage, as_mmap=False):
    out = zoom(image, resolution_percentage, image.dtype, order=2)
    if as_mmap:
        fd, fname = tempfile.mkstemp(suffix="_resized")
        out_mmap = np.memmap(fname, shape=out.shape, dtype=out.dtype, mode="w+")
        out_mmap[:] = out
        os.close(fd)
        return out_mmap
    return out


def read_dcm_slice_as_np2(filename, resolution_percentage=1.0):
    reader = gdcm.ImageReader()
    reader.SetFileName(filename)
    reader.Read()
    image = reader.GetImage()
    output = converters.gdcm_to_numpy(image)
    if resolution_percentage < 1.0:
        output = zoom(output, resolution_percentage)
    return output


def FixGantryTilt(matrix, spacing, tilt):
    """
    Fix gantry tilt given a vtkImageData and the tilt value. Return new
    vtkImageData.
    """
    angle = np.radians(tilt)
    spacing = spacing[0], spacing[1], spacing[2]
    gntan = math.tan(angle)

    for n, slice_ in enumerate(matrix):
        offset = gntan * n * spacing[2]
        matrix[n] = shift(slice_, (-offset / spacing[1], 0), cval=matrix.min())


def BuildEditedImage(imagedata, points):
    """
    Editing the original image in accordance with the edit
    points in the editor, it is necessary to generate the
    vtkPolyData via vtkContourFilter
    """
    init_values = None
    for point in points:
        x, y, z = point
        colour = points[point]
        imagedata.SetScalarComponentFromDouble(x, y, z, 0, colour)
        imagedata.Update()

        if not (init_values):
            xi = x
            xf = x
            yi = y
            yf = y
            zi = z
            zf = z
            init_values = 1

        if xi > x:
            xi = x
        elif xf < x:
            xf = x

        if yi > y:
            yi = y
        elif yf < y:
            yf = y

        if zi > z:
            zi = z
        elif zf < z:
            zf = z

    clip = vtkImageClip()
    clip.SetInput(imagedata)
    clip.SetOutputWholeExtent(xi, xf, yi, yf, zi, zf)
    clip.Update()

    gauss = vtkImageGaussianSmooth()
    gauss.SetInput(clip.GetOutput())
    gauss.SetRadiusFactor(0.6)
    gauss.Update()

    app = vtkImageAppend()
    app.PreserveExtentsOn()
    app.SetAppendAxis(2)
    app.SetInput(0, imagedata)
    app.SetInput(1, gauss.GetOutput())
    app.Update()

    return app.GetOutput()


def Export(imagedata, filename, bin=False):
    writer = vtkXMLImageDataWriter()
    writer.SetFileName(filename)
    if bin:
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAscii()
    # writer.SetInput(imagedata)
    # writer.Write()


def Import(filename):
    reader = vtkXMLImageDataReader()
    reader.SetFileName(filename)
    # TODO: Check if the code bellow is necessary
    reader.WholeSlicesOn()
    reader.Update()

    return reader.GetOutput()


def View(imagedata):
    viewer = vtkImageViewer()
    viewer.SetInput(imagedata)
    viewer.SetColorWindow(200)
    viewer.SetColorLevel(100)
    viewer.Render()

    import time

    time.sleep(10)


def ExtractVOI(imagedata, xi, xf, yi, yf, zi, zf):
    """
    Cropping the vtkImagedata according
    with values.
    """
    voi = vtkExtractVOI()
    voi.SetVOI(xi, xf, yi, yf, zi, zf)
    voi.SetInputData(imagedata)
    voi.SetSampleRate(1, 1, 1)
    voi.Update()
    return voi.GetOutput()


def create_dicom_thumbnails(image, window=None, level=None):
    pf = image.GetPixelFormat()
    np_image = converters.gdcm_to_numpy(image, pf.GetSamplesPerPixel() == 1)
    if window is None or level is None:
        _min, _max = np_image.min(), np_image.max()
        window = _max - _min
        level = _min + window / 2

    if image.GetNumberOfDimensions() >= 3:
        thumbnail_paths = []
        for i in range(np_image.shape[0]):
            thumb_image = zoom(np_image[i], 0.25)
            thumb_image = np.array(get_LUT_value_255(thumb_image, window, level), dtype=np.uint8)
            fd, thumbnail_path = tempfile.mkstemp(prefix="thumb_", suffix=".png")
            imageio.imsave(thumbnail_path, thumb_image)
            thumbnail_paths.append(thumbnail_path)
            os.close(fd)
        return thumbnail_paths
    else:
        fd, thumbnail_path = tempfile.mkstemp(prefix="thumb_", suffix=".png")
        if pf.GetSamplesPerPixel() == 1:
            thumb_image = zoom(np_image, 0.25)
            thumb_image = np.array(get_LUT_value_255(thumb_image, window, level), dtype=np.uint8)
        else:
            thumb_image = zoom(np_image, (0.25, 0.25, 1))
        imageio.imsave(thumbnail_path, thumb_image)
        os.close(fd)
        return thumbnail_path


def array2memmap(arr, filename=None):
    fd = None
    if filename is None:
        fd, filename = tempfile.mkstemp(prefix="inv3_", suffix=".dat")
    matrix = np.memmap(filename, mode="w+", dtype=arr.dtype, shape=arr.shape)
    matrix[:] = arr[:]
    matrix.flush()
    if fd:
        os.close(fd)
    return matrix


def bitmap2memmap(files, slice_size, orientation, spacing, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename.
    """
    message = _("Generating multiplanar visualization...")
    if len(files) > 1:
        update_progress = vtk_utils.ShowProgress(len(files) - 1, dialog_type="ProgressDialog")

    temp_fd, temp_file = tempfile.mkstemp()

    if orientation == "SAGITTAL":
        if resolution_percentage == 1.0:
            shape = slice_size[1], slice_size[0], len(files)
        else:
            shape = (
                math.ceil(slice_size[1] * resolution_percentage),
                math.ceil(slice_size[0] * resolution_percentage),
                len(files),
            )

    elif orientation == "CORONAL":
        if resolution_percentage == 1.0:
            shape = slice_size[1], len(files), slice_size[0]
        else:
            shape = (
                math.ceil(slice_size[1] * resolution_percentage),
                len(files),
                math.ceil(slice_size[0] * resolution_percentage),
            )
    else:
        if resolution_percentage == 1.0:
            shape = len(files), slice_size[1], slice_size[0]
        else:
            shape = (
                len(files),
                math.ceil(slice_size[1] * resolution_percentage),
                math.ceil(slice_size[0] * resolution_percentage),
            )

    if resolution_percentage == 1.0:
        matrix = np.memmap(temp_file, mode="w+", dtype="int16", shape=shape)

    cont = 0
    max_scalar = None
    min_scalar = None

    first_resample_entry = False

    for n, f in enumerate(files):
        image_as_array = bitmap_reader.ReadBitmap(f)
        image = converters.to_vtk(
            image_as_array,
            spacing=spacing,
            slice_number=1,
            orientation=orientation.upper(),
        )

        if resolution_percentage != 1.0:
            image_resized = ResampleImage2D(
                image,
                px=None,
                py=None,
                resolution_percentage=resolution_percentage,
                update_progress=None,
            )

            yx_shape = (
                image_resized.GetDimensions()[1],
                image_resized.GetDimensions()[0],
            )

            if not (first_resample_entry):
                shape = shape[0], yx_shape[0], yx_shape[1]
                matrix = np.memmap(temp_file, mode="w+", dtype="int16", shape=shape)
                first_resample_entry = True

            image = image_resized

        min_aux, max_aux = image.GetScalarRange()
        if min_scalar is None or min_aux < min_scalar:
            min_scalar = min_aux

        if max_scalar is None or max_aux > max_scalar:
            max_scalar = max_aux

        array = numpy_support.vtk_to_numpy(image.GetPointData().GetScalars())

        if array.dtype == "uint16":
            new_array = np.empty_like(array, dtype=np.int16)
            new_array = array - 32768
            array = new_array

        if orientation == "CORONAL":
            array.shape = matrix.shape[0], matrix.shape[2]
            matrix[:, n, :] = array[:, ::-1]
        elif orientation == "SAGITTAL":
            array.shape = matrix.shape[0], matrix.shape[1]
            # TODO: Verify if it's necessary to add the slices swapped only in
            # sagittal rmi or only in # Rasiane's case or is necessary in all
            # sagittal cases.
            matrix[:, :, n] = array[:, ::-1]
        else:
            array.shape = matrix.shape[1], matrix.shape[2]
            matrix[n] = array

        if len(files) > 1:
            update_progress(cont, message)
        cont += 1

    matrix.flush()
    scalar_range = min_scalar, max_scalar
    os.close(temp_fd)

    return matrix, scalar_range, temp_file


def dcm2memmap(files, slice_size, orientation, resolution_percentage):
    """
    From a list of dicom files it creates memmap file in the temp folder and
    returns it and its related filename.
    """
    if len(files) > 1:
        message = _("Generating multiplanar visualization...")
        update_progress = vtk_utils.ShowProgress(len(files) - 1, dialog_type="ProgressDialog")

    first_slice = read_dcm_slice_as_np2(files[0], resolution_percentage)
    slice_size = first_slice.shape[::-1]

    temp_fd, temp_file = tempfile.mkstemp()

    if orientation == "SAGITTAL":
        shape = slice_size[0], slice_size[1], len(files)
    elif orientation == "CORONAL":
        shape = slice_size[1], len(files), slice_size[0]
    else:
        shape = len(files), slice_size[1], slice_size[0]

    matrix = np.memmap(temp_file, mode="w+", dtype="int16", shape=shape)
    for n, f in enumerate(files):
        im_array = read_dcm_slice_as_np2(f, resolution_percentage)[::-1]

        if orientation == "CORONAL":
            matrix[:, shape[1] - n - 1, :] = im_array
        elif orientation == "SAGITTAL":
            # TODO: Verify if it's necessary to add the slices swapped only in
            # sagittal rmi or only in # Rasiane's case or is necessary in all
            # sagittal cases.
            matrix[:, :, n] = im_array
        else:
            matrix[n] = im_array
        if len(files) > 1:
            update_progress(n, message)

    matrix.flush()
    scalar_range = matrix.min(), matrix.max()
    os.close(temp_fd)

    return matrix, scalar_range, temp_file


def dcmmf2memmap(dcm_file, orientation):
    reader = gdcm.ImageReader()
    reader.SetFileName(dcm_file)
    reader.Read()
    image = reader.GetImage()
    xs, ys, zs = image.GetSpacing()
    pf = image.GetPixelFormat()
    samples_per_pixel = pf.GetSamplesPerPixel()
    np_image = converters.gdcm_to_numpy(image, pf.GetSamplesPerPixel() == 1)
    if samples_per_pixel == 3:
        np_image = image_normalize(rgb2gray(np_image), 0, 255)
    temp_fd, temp_file = tempfile.mkstemp()
    matrix = np.memmap(temp_file, mode="w+", dtype="int16", shape=np_image.shape)
    z, y, x = np_image.shape
    if orientation == "CORONAL":
        spacing = xs, zs, ys
        matrix.shape = y, z, x
        for n in range(z):
            matrix[:, n, :] = np_image[n][::-1]
    elif orientation == "SAGITTAL":
        spacing = zs, ys, xs
        matrix.shape = y, x, z
        for n in range(z):
            matrix[:, :, n] = np_image[n][::-1]
    else:
        spacing = xs, ys, zs
        matrix[:] = np_image[:, ::-1, :]

    matrix.flush()
    scalar_range = matrix.min(), matrix.max()
    os.close(temp_fd)

    return matrix, scalar_range, spacing, temp_file


def img2memmap(group):
    """
    From a nibabel image data creates a memmap file in the temp folder and
    returns it and its related filename.
    """

    temp_fd, temp_file = tempfile.mkstemp()

    data = group.get_fdata()

    # if scalar range is larger than uint16 maximum number, the image needs
    # to be rescalaed so that no negative values are created when converting to int16
    # maximum of 10000 was selected arbitrarily by testing with one MRI example
    # alternatively could test if "data.dtype == 'float64'" but maybe it is too specific
    if np.ptp(data) > (2**16 / 2 - 1):
        data = image_normalize(data, min_=0, max_=10000, output_dtype=np.int16)
        dlg.WarningRescalePixelValues()

    # images can have pixel intensities in small float numbers which after int conversion will
    # have to be binary (0, 1). To prevent that, rescale pixel values from 0-255
    elif data.max() < (2**3):
        data_temp = image_normalize(data, min_=0, max_=255, output_dtype=np.int16)
        status = dlg.DialogRescalePixelIntensity(data.max(), np.unique(data_temp).size)

        if status:
            data = data_temp
            # dlg.WarningRescalePixelValues()

    # Convert RAS+ to default InVesalius orientation ZYX
    data = np.swapaxes(data, 0, 2)
    data = np.fliplr(data)

    matrix = np.memmap(temp_file, mode="w+", dtype=np.int16, shape=data.shape)
    matrix[:] = data[:]
    matrix.flush()

    scalar_range = np.amin(matrix), np.amax(matrix)
    os.close(temp_fd)

    return matrix, scalar_range, temp_file


def get_LUT_value_255(data, window, level):
    shape = data.shape
    data_ = data.ravel()
    data = np.piecewise(
        data_,
        [
            data_ <= (level - 0.5 - (window - 1) / 2),
            data_ > (level - 0.5 + (window - 1) / 2),
        ],
        [0, 255, lambda data_: ((data_ - (level - 0.5)) / (window - 1) + 0.5) * (255)],
    )
    data.shape = shape
    return data


def get_LUT_value(data: np.ndarray, window: int, level: int) -> np.ndarray:
    shape = data.shape
    data_ = data.ravel()
    data = np.piecewise(
        data_,
        [data_ <= (level - 0.5 - (window - 1) / 2), data_ > (level - 0.5 + (window - 1) / 2)],
        [0, window, lambda data_: ((data_ - (level - 0.5)) / (window - 1) + 0.5) * (window)],
    )
    data.shape = shape
    return data


def get_LUT_value_normalized(img, a_min, a_max, b_min=0.0, b_max=1.0, clip=True):
    # based on https://docs.monai.io/en/latest/_modules/monai/transforms/intensity/array.html#ScaleIntensity

    print(a_min, a_max, b_min, b_max, clip)
    img = (img - a_min) / (a_max - a_min)
    img = img * (b_max - b_min) + b_min

    if clip:
        img = np.clip(img, b_min, b_max)

    return img


def image_normalize(image, min_=0.0, max_=1.0, output_dtype=np.int16):
    output = np.empty(shape=image.shape, dtype=output_dtype)
    imin, imax = image.min(), image.max()
    output[:] = (image - imin) * ((max_ - min_) / (imax - imin)) + min_
    return output


# TODO: Add a description of different coordinate systems, namely:
#       - the world coordinate system,
#       - the voxel coordinate system.
#       - InVesalius's internal coordinate system,
#
def convert_world_to_voxel(xyz, affine):
    """
    Convert a coordinate from the world space ((x, y, z); scanner space; millimeters) to the
    voxel space ((i, j, k)). This is achieved by multiplying a coordinate by the inverse
    of the affine transformation.

    More information: https://nipy.org/nibabel/coordinate_systems.html

    :param xyz: a list or array of 3 coordinates (x, y, z) in the world coordinates
    :param affine: a 4x4 array containing the image affine transformation in homogeneous coordinates
    :return: a 1x3 array with the point coordinates in image space (i, j, k)
    """
    # convert xyz coordinate to 1x4 homogeneous coordinates array
    xyz_homo = np.hstack((xyz, 1.0)).reshape([4, 1])
    ijk_homo = np.linalg.inv(affine) @ xyz_homo
    ijk = ijk_homo.T[np.newaxis, 0, :3]

    return ijk


def convert_invesalius_to_voxel(position):
    """
    Convert position from InVesalius space to the voxel space.

    The two spaces are otherwise identical, but InVesalius space has a reverted y-axis
    (increasing y-coordinate moves posterior in InVesalius space, but anterior in the voxel space).

    For instance, if the size of the voxel image is 256 x 256 x 160, the y-coordinate 0 in
    InVesalius space corresponds to the y-coordinate 255 in the voxel space.

    :param position: a vector of 3 coordinates (x, y, z) in InVesalius space.
    :return: a vector of 3 coordinates in the voxel space
    """
    slice = sl.Slice()
    return np.array(
        (position[0], slice.spacing[1] * (slice.matrix.shape[1] - 1) - position[1], position[2])
    )


def convert_invesalius_to_world(position, orientation):
    """
    Convert position and orientation from InVesalius space to the world space.

    The axis definition for the Euler angles returned is 'sxyz', see transformations.py for more
    information.

    Uses 'affine' matrix defined in the project created or opened by the user. If it is
    undefined, return Nones as the coordinates for both position and orientation.

    More information: https://nipy.org/nibabel/coordinate_systems.html

    :param position: a vector of 3 coordinates in InVesalius space.
    :param orientation: a vector of 3 Euler angles in InVesalius space.
    :return: a pair consisting of 3 coordinates and 3 Euler angles in the world space, or Nones if
             'affine' matrix is not defined in the project.
    """
    slice = sl.Slice()

    if slice.affine is None:
        position_world = (None, None, None)
        orientation_world = (None, None, None)

        return position_world, orientation_world

    position_voxel = convert_invesalius_to_voxel(position)

    M_invesalius = dco.coordinates_to_transformation_matrix(
        position=position_voxel,
        orientation=orientation,
        axes="sxyz",
    )
    M_world = np.linalg.inv(slice.affine) @ M_invesalius

    position_world, orientation_world = dco.transformation_matrix_to_coordinates(
        M_world,
        axes="sxyz",
    )

    return position_world, orientation_world


def create_grid(xy_range, z_range, z_offset, spacing):
    x = np.arange(xy_range[0], xy_range[1] + 1, spacing)
    y = np.arange(xy_range[0], xy_range[1] + 1, spacing)
    z = z_offset + np.arange(z_range[0], z_range[1] + 1, spacing)
    xv, yv, zv = np.meshgrid(x, y, -z)
    coord_grid = np.array([xv, yv, zv])
    # create grid of points
    grid_number = x.shape[0] * y.shape[0] * z.shape[0]
    coord_grid = coord_grid.reshape([3, grid_number]).T
    # sort grid from distance to the origin/coil center
    coord_list = coord_grid[np.argsort(np.linalg.norm(coord_grid, axis=1)), :]
    # make the coordinates homogeneous
    coord_list_w = np.append(coord_list.T, np.ones([1, grid_number]), axis=0)

    return coord_list_w


def create_spherical_grid(radius=10, subdivision=1):
    x = np.linspace(-radius, radius, int(2 * radius / subdivision) + 1)
    xv, yv, zv = np.meshgrid(x, x, x)
    coord_grid = np.array([xv, yv, zv])
    # create grid of points
    grid_number = x.shape[0] ** 3
    coord_grid = coord_grid.reshape([3, grid_number]).T

    sph_grid = coord_grid[np.linalg.norm(coord_grid, axis=1) < radius, :]
    sph_sort = sph_grid[np.argsort(np.linalg.norm(sph_grid, axis=1)), :]

    return sph_sort


def random_sample_sphere(radius=3, size=100):
    uvw = np.random.default_rng().normal(0, 1, (size, 3))
    norm = np.linalg.norm(uvw, axis=1, keepdims=True)
    # Change/remove **(1./3) to make samples more concentrated around the center
    r = np.random.default_rng().uniform(0, 1, (size, 1)) ** 1.5
    scale = radius * np.divide(r, norm)
    xyz = scale * uvw
    return xyz


def get_largest_connected_component(image):
    labels = label(image)
    assert labels.max() != 0
    largest_component = labels == np.argmax(np.bincount(labels.flat)[1:]) + 1
    return largest_component
