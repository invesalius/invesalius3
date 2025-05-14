from invesalius.data.slice_ import Slice
from invesalius.data.mask import Mask
from scipy.ndimage import generate_binary_structure
import numpy as np
from invesalius.project import Project  # Import the Project class
from invesalius_cy import floodfill

def create_new_mask_from_selection(old_mask_name, new_mask_name, slice_number, pixel_coord):
    """
    Creates a new mask by selecting parts of an existing mask.

    Args:
        old_mask_name (str): The name of the existing mask to select from.
        new_mask_name (str): The name of the new mask to create.
        slice_number (int): The slice number to operate on.
        pixel_coord (tuple): The (x, y, z) pixel coordinate to start the selection.

    Returns:
        Mask: The newly created mask object.
    """
    # Get the current Slice instance
    slice_instance = Slice()

    # Get the current project instance
    project = Project()

    # Find the old mask by name
    old_mask_index = next(
        (index for index, mask in project.mask_dict.items() if mask.name == old_mask_name), None
    )
    if old_mask_index is None:
        raise ValueError(f"Mask with name '{old_mask_name}' not found.")

    # Select the old mask
    slice_instance.SelectCurrentMask(old_mask_index)

    # Get the current mask matrix
    old_mask = slice_instance.current_mask
    old_mask_matrix = old_mask.matrix[1:, 1:, 1:]

    # Create a new mask
    new_mask = slice_instance.create_new_mask(name=new_mask_name, add_to_project=False)
    new_mask_matrix = new_mask.matrix[1:, 1:, 1:]

    # Generate the binary structure for 3D connectivity
    bstruct = np.array(generate_binary_structure(3, 6), dtype="uint8")

    # Perform flood fill to select parts of the old mask
    floodfill.floodfill_threshold(
        old_mask_matrix,
        [pixel_coord],
        226,  # Threshold lower bound
        3071,  # Threshold upper bound
        254,  # Fill value
        bstruct,
        new_mask_matrix,
    )

    # Add the new mask to the project
    slice_instance._add_mask_into_proj(new_mask)

    # Return the new mask
    return new_mask

def get_median_axial_slice():
    """
    Get the slice number of the median axial slice.

    Returns:
        int: The slice number of the median axial slice.
    """
    # Get the current Slice instance
    slice_instance = Slice()

    # Get the total number of slices in the axial orientation
    total_slices = slice_instance.GetNumberOfSlices(orientation="AXIAL")

    # Calculate the median slice number
    median_slice = total_slices // 2

    return median_slice

def get_center_pixel_value(slice_number):
    """
    Get the center pixel value of a given slice.

    Args:
        slice_number (int): The slice number to retrieve the center pixel value from.

    Returns:
        int or float: The value of the center pixel in the specified slice.
    """
    # Get the current Slice instance
    slice_instance = Slice()
    print("MASK_NAME:"+slice_instance.__get_mask_name__())

    # Retrieve the slice matrix using the get_image_slice method
    # Assuming "AXIAL" orientation for the slice
    slice_matrix = slice_instance.get_image_slice(orientation="AXIAL", slice_number=slice_number)

    # Calculate the center coordinates of the slice
    center_x = slice_matrix.shape[0] // 2
    center_y = slice_matrix.shape[1] // 2

    # Return the center pixel value
    return slice_matrix[center_x, center_y]
