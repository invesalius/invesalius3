import SimpleITK as sitk
import os

def load_dicom_series(folder):
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(folder)
    if not series_ids:
        raise ValueError("No DICOM series found in folder")
    
    series_file_names = reader.GetGDCMSeriesFileNames(folder, series_ids[0])
    reader.SetFileNames(series_file_names)
    image = reader.Execute()
    return image

def crop_image_by_coords(image, xi, xf, yi, yf, zi, zf):
    """
    Crop the entire 3D DICOM volume to the specified physical coordinates.
    The crop is applied to all slices in the volume.
    """
    # Convert physical space coordinates to voxel indices
    start_phys = (xi, yi, zi)
    end_phys = (xf, yf, zf)

    start_index = image.TransformPhysicalPointToIndex(start_phys)
    end_index = image.TransformPhysicalPointToIndex(end_phys)

    # Ensure proper voxel ordering
    start_voxel = [min(s, e) for s, e in zip(start_index, end_index)]
    end_voxel = [max(s, e) for s, e in zip(start_index, end_index)]

    # Clamp to image bounds
    img_size = image.GetSize()
    start_voxel = [max(0, min(s, img_size[i] - 1)) for i, s in enumerate(start_voxel)]
    end_voxel = [max(0, min(e, img_size[i] - 1)) for i, e in enumerate(end_voxel)]

    # Compute size (must be > 0)
    size = [max(1, end - start + 1) for start, end in zip(start_voxel, end_voxel)]

    # Check if region is valid
    for i in range(3):
        if start_voxel[i] < 0 or start_voxel[i] >= img_size[i]:
            raise ValueError(f"Start index {start_voxel[i]} out of bounds for axis {i} (size {img_size[i]})")
        if start_voxel[i] + size[i] > img_size[i]:
            size[i] = img_size[i] - start_voxel[i]

    # Crop the 3D volume (all slices)
    cropped = sitk.RegionOfInterest(image, size=size, index=start_voxel)
    return cropped

def save_image_as_nifti(image, output_path):
    sitk.WriteImage(image, output_path)

def save_as_dicom_series(image, reference_image, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    writer = sitk.ImageFileWriter()
    writer.KeepOriginalImageUIDOn()

    direction = image.GetDirection()
    origin = image.GetOrigin()
    spacing = image.GetSpacing()
    size = image.GetSize()

    for i in range(size[2]):
        # Extract a 2D slice and convert it to a 3D image with depth 1
        slice_2d = image[:, :, i]
        slice_3d = sitk.JoinSeries(slice_2d)
        slice_3d = sitk.Cast(slice_3d, sitk.sitkInt16)

        # Set correct spacing, origin, and direction for the slice
        slice_3d.SetSpacing((spacing[0], spacing[1], spacing[2]))
        slice_origin = [
            origin[0],
            origin[1],
            origin[2] + spacing[2] * i
        ]
        slice_3d.SetOrigin(slice_origin)
        slice_3d.SetDirection(direction)

        # Copy metadata from reference (patient info, acquisition settings)
        for key in reference_image.GetMetaDataKeys():
            slice_3d.SetMetaData(key, reference_image.GetMetaData(key))

        slice_3d.SetMetaData("0020|0032", "\\".join(map(str, slice_origin)))  # ImagePositionPatient
        slice_3d.SetMetaData("0020|0013", str(i + 1))  # InstanceNumber

        writer.SetFileName(os.path.join(output_folder, f"slice_{i:04d}.dcm"))
        writer.Execute(slice_3d)


