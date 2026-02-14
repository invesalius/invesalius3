import numpy as np
import nibabel as nib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple

# _ is usually injected by gettext in InVesalius, but we need a fallback for import safety
try:
    _
except NameError:
    def _(s): return s

class ValidationStatus(Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"

@dataclass
class ValidationResult:
    status: ValidationStatus
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    mask_type: Optional[str] = None  # "binary", "multi-label", "probability", "atlas", etc.
    
    @property
    def is_valid(self):
        return self.status != ValidationStatus.ERROR

def check_is_mask(nib_proxy, verbose=False) -> Tuple[bool, str]:
    """
    Check if a NIfTI image looks like a segmentation mask using robust heuristics.
    
    Args:
        nib_proxy: nibabel image proxy object
        verbose: if True, return additional diagnostic information
    
    Returns:
        (is_mask, reason)
        
    Examples:
        >>> img = nib.load('mask.nii.gz')
        >>> is_mask, reason = check_is_mask(img)
        >>> if is_mask:
        ...     print(f"Valid mask: {reason}")
    """
    dataobj = nib_proxy.dataobj
    header = nib_proxy.header
    
    # 1. Shape Check (Reject 4D+ if complex)
    shape = header.get_data_shape()
    if len(shape) > 3 and shape[3] > 1:
        # It's a time series or vector field
        return False, "Image is 4D (time-series or vector), expected 3D static volume."

    # 2. Empty Check
    if np.prod(shape) == 0:
        return False, "Image has zero volume."

    # 3. Two-Pass Data Inspection
    # We want to avoid loading 1GB+ files into RAM just to check uniqueness.
    # But strided sampling is dangerous for small masks.
    # Strategy: 
    # - If small (<100MB), load full.
    # - If large, read in chunks to find unique values safely.

    dtype = dataobj.dtype
    is_integer = np.issubdtype(dtype, np.integer)
    
    # 512^3 * 2 bytes approx 256MB. Let's be conservative. 100MB threshold.
    # Estimated size in bytes
    est_size = np.prod(shape) * dtype.itemsize
    
    # Increased from 2000 to 5000 to support large connectome parcellations
    MAX_UNIQUE_LABELS = 5000 if is_integer else 1000
    unique_vals = set()
    data_sample = None
    
    try:
        if est_size < 100 * 1024 * 1024: # < 100MB
            # Safe to load fully
            data_sample = np.asanyarray(dataobj)
            # Check for NaN values
            if np.any(np.isnan(data_sample)):
                return False, "Mask contains NaN values."
            # Flatten to 1D to speed up unique check
            unique_vals.update(np.unique(data_sample))
        else:
            # Chunked reading (e.g. slice by slice along Z)
            # This is slower but memory safe and 100% accurate for finding small labels
            nz = shape[2]
            exceeded_threshold = False
            for z in range(nz):
                slice_data = dataobj[..., z]
                # Check for NaN in this slice
                if np.any(np.isnan(slice_data)):
                    return False, "Mask contains NaN values."
                # Continue scanning ALL slices to ensure we don't miss rare labels
                # But stop adding to set once we exceed threshold to save memory
                if len(unique_vals) <= MAX_UNIQUE_LABELS:
                    unique_vals.update(np.unique(slice_data))
                else:
                    exceeded_threshold = True
                    # Keep scanning to verify it's truly a volume, not just a large atlas
            
            # If we exceeded threshold, it's likely a volume
            if exceeded_threshold:
                return False, f"Too many unique values (>{MAX_UNIQUE_LABELS}), likely a grayscale volume."
                
    except Exception as e:
        # Fallback for I/O errors or memory errors
        return False, f"Failed to analyze data: {str(e)}"

    # 4. Analyze Unique Values
    
    # Empty mask (only 0) or Single Label
    if len(unique_vals) <= 1:
        val = list(unique_vals)[0]
        # Check for NaN (shouldn't happen due to earlier check, but be safe)
        if np.isnan(val):
            return False, "Mask contains only NaN values."
        if val == 0:
            return True, "Empty mask (all zeros)"
        else:
            return True, f"Single label mask (label={val})"

    # Too many values -> Volume
    if len(unique_vals) > MAX_UNIQUE_LABELS:
        return False, f"Too many unique values ({len(unique_vals)}), likely a grayscale volume."
        
    # Check for probability maps (Float data in range [0, 1])
    min_val = min(unique_vals)
    max_val = max(unique_vals)
    
    if not is_integer:
        # Check if floats are effectively integers (with tolerance for rounding noise)
        # e.g., 1.0000001 should be treated as 1.0
        is_effectively_int = all(abs(float(x) - round(float(x))) < 1e-5 for x in unique_vals)
        
        if not is_effectively_int:
            # Continuous float values - check if it's a probability map
            if 0.0 <= min_val <= max_val <= 1.0:
                # Distinguish between continuous probability maps and discrete masks stored as float
                if 10 <= len(unique_vals) <= 1000:
                    return True, "Probability map (continuous values 0-1)"
                elif len(unique_vals) <= 10:
                    return True, "Discrete probability mask (few values in range 0-1)"
                else:
                    # Too many unique values for a probability map
                    return False, f"Too many unique float values ({len(unique_vals)}), likely a normalized volume."
            else:
                # Float values outside [0,1] with few unique values
                # Could be a mask with specific float labels, allow it
                if len(unique_vals) <= 100:
                    return True, f"Float mask with {len(unique_vals)} labels"
                else:
                    return False, f"Too many unique float values ({len(unique_vals)}), likely a volume."
    
    # Integer mask analysis
    # Check for large intensity values (likely HU values, not labels)
    if is_integer and max_val > 10000:
        return False, f"Integer values too large (max={max_val}), likely intensity values not labels."
    
    # Check for background: either 0 or negative values suggest mask structure
    has_zero_background = (0 in unique_vals)
    has_negative_labels = (min_val < 0)
    
    if not has_zero_background and not has_negative_labels:
        # No explicit background - could still be a mask if values are small integers
        if is_integer and max_val < 50 and len(unique_vals) < 50:
            return True, f"Mask without background label (labels 1-{int(max_val)})"
        else:
            return False, "No background (0) or negative labels found, likely a volume."
    
    # If we have the full data loaded (small file), check sparsity and density
    if data_sample is not None:
        non_zero_ratio = np.count_nonzero(data_sample) / data_sample.size
        
        # Warn about extremely sparse masks (possible corruption or mistake)
        if non_zero_ratio < 0.00001 and len(unique_vals) > 1:
            # Less than 0.001% non-zero - very suspicious
            return True, f"Warning: Extremely sparse mask ({non_zero_ratio*100:.6f}% non-zero)"
        
        # Dense volumes with many labels are likely not masks
        if non_zero_ratio > 0.7 and len(unique_vals) > 100:
            return False, f"Dense volume ({non_zero_ratio*100:.1f}% non-zero) with many labels ({len(unique_vals)}), likely not a mask."

    return True, "Valid mask structure"

def validate_mask_compatibility(mask_header, mask_affine, proj_shape, proj_spacing, proj_affine=None) -> ValidationResult:
    """
    Validate NIfTI mask compatibility with target volume.
    Incorporates robust orientation checks (LPS/RAS agnostic).
    
    Args:
        mask_header: NIfTI header object for the mask
        mask_affine: 4x4 affine transformation matrix for the mask
        proj_shape: tuple of (x, y, z) dimensions for the project volume
        proj_spacing: tuple of (x, y, z) voxel spacing for the project volume
        proj_affine: optional 4x4 affine transformation matrix for the project volume
        
    Returns:
        ValidationResult object with status, message, and details
    """
    mask_shape = mask_header.get_data_shape()
    
    # 1. Dimension Check (Blocking)
    # We strip 4th dim if it is 1, to be nice
    if len(mask_shape) == 4 and mask_shape[3] == 1:
        mask_shape = mask_shape[:3]
        
    if proj_shape is not None and mask_shape != proj_shape:
        return ValidationResult(
            ValidationStatus.ERROR,
            _("Dimension mismatch.\n\nProject: {} voxels\nMask:    {} voxels\n\nMasks must match the volume dimensions exactly.").format(proj_shape, mask_shape),
            {'type': 'dimension', 'proj': proj_shape, 'mask': mask_shape}
        )

    # 2. Spacing Check (Warning)
    mask_zooms = mask_header.get_zooms()[:3]
    if not np.allclose(mask_zooms, proj_spacing, atol=1e-3):
        return ValidationResult(
            ValidationStatus.WARNING,
            _("Voxel spacing mismatch.\n\nProject: {:.3f}mm\nMask:    {:.3f}mm\n\nThis may cause slight alignment errors.").format(proj_spacing[0], mask_zooms[0]),
             {'type': 'spacing', 'proj': proj_spacing, 'mask': mask_zooms}
        )

    # 3. Affine/Orientation Check
    if proj_affine is not None:
        # Check for degenerate affine matrices (non-invertible)
        mask_det = np.linalg.det(mask_affine[:3, :3])
        proj_det = np.linalg.det(proj_affine[:3, :3])
        
        if abs(mask_det) < 1e-10:
            return ValidationResult(
                ValidationStatus.ERROR,
                _("Corrupted mask affine matrix (determinant near zero, non-invertible)."),
                {'type': 'affine', 'determinant': mask_det}
            )
        
        if abs(proj_det) < 1e-10:
            return ValidationResult(
                ValidationStatus.ERROR,
                _("Corrupted project affine matrix (determinant near zero, non-invertible)."),
                {'type': 'affine', 'determinant': proj_det}
            )
        
        # Deconstruct affine
        proj_rot = proj_affine[:3, :3]
        mask_rot = mask_affine[:3, :3]
        proj_trans = proj_affine[:3, 3]
        mask_trans = mask_affine[:3, 3]

        # 3a. Rotation Check
        # Check if rotation matrices are similar
        # Strict equality fails for LPS vs RAS.
        # Better: check if they define the same grid axes. 
        # But even simpler: orientation mismatch is CRITICAL.
        # If user imports LPS mask into RAS volume, data will be flipped if we just ignore it.
        # We must detect if resampling/reorienting is needed. 
        # Since this simple importer doesn't resample, we must BLOCK if orientation doesn't match.
        
        # Check alignment of axes vectors (ignoring flip signs for now, just direction)
        # But actually, if we are not resampling, the raw affine matrices MUST be close.
        # OR we must trust the user knows what they are doing only if the discrepancy is just translation.
        
        # Let's compare "Orientation" (AxCodes).
        try:
            mask_axcodes = nib.aff2axcodes(mask_affine)
            proj_axcodes = nib.aff2axcodes(proj_affine)
        except Exception:
            # Fallback if affines are degenerate
            mask_axcodes = None
            proj_axcodes = None

        # Check for None axcodes (degenerate affines)
        if mask_axcodes is None or proj_axcodes is None:
            return ValidationResult(
                ValidationStatus.ERROR,
                _("Cannot determine orientation (degenerate affine matrix).\n\nMask orientation: {}\nProject orientation: {}").format(mask_axcodes, proj_axcodes),
                {'type': 'orientation', 'proj': proj_axcodes, 'mask': mask_axcodes}
            )

        if mask_axcodes != proj_axcodes:
             return ValidationResult(
                ValidationStatus.ERROR,
                _("Orientation mismatch ({} vs {}).\n\nThe mask is in a different anatomical orientation than the volume.").format(mask_axcodes, proj_axcodes),
                {'type': 'orientation', 'proj': proj_axcodes, 'mask': mask_axcodes}
            )

        # If orientations match, we still need to check if they are identical grids (no rotation relative to each other)
        # Since we already checked axcodes, broadly they are same direction.
        # Now check exact rotation matrix with tighter tolerance (1e-4 instead of 1e-2)
        # This catches sub-degree rotations that could cause misalignment
        if not np.allclose(mask_rot, proj_rot, atol=1e-4, rtol=1e-4):
             return ValidationResult(
                ValidationStatus.ERROR,
                _("Grid rotation mismatch.\n\nThe mask is rotated relative to the volume.\nThis could indicate different acquisition orientations."),
                {'type': 'rotation'}
            )

        # 3b. Translation Check (Warning vs Error)
        # Calculate Euclidean shift
        dist = np.linalg.norm(mask_trans - proj_trans)
        
        # Tolerance (tightened from 2.0mm to 0.5mm for WARNING threshold):
        # < 0.05 mm : Perfect (sub-voxel precision)
        # < 0.5 mm : Acceptable Warning (scanner precision issue)
        # >= 0.5 mm : Error (clinically significant misalignment)
        
        if dist > 0.05:
            severity = ValidationStatus.WARNING if dist < 0.5 else ValidationStatus.ERROR
            msg = _("Origin mismatch.\n\nThe mask is offset by {:.2f} mm from the volume.").format(dist)
            if severity == ValidationStatus.WARNING:
                msg += _("\n\nThis is likely due to scanner precision differences.\nVerify alignment visually before proceeding.")
            else:
                msg += _("\n\nThis is a clinically significant misalignment.\nThe mask must be re-registered to the volume.")
            
            return ValidationResult(
                severity,
                msg,
                {'type': 'translation', 'distance': dist}
            )

    return ValidationResult(ValidationStatus.OK)
