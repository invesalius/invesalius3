import unittest
import numpy as np
import nibabel as nib
import tempfile
import os
import sys

# Update path to find invesalius modules
sys.path.append("/Users/prateekrai/invesalius3")

from invesalius.reader import nifti_utils
from invesalius.reader.nifti_utils import ValidationStatus

class TestNiftiUtilsHardening(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        
    def create_nifti(self, data, affine=None):
        if affine is None:
            affine = np.eye(4)
        img = nib.Nifti1Image(data, affine)
        path = os.path.join(self.tmp_dir, 'test.nii')
        nib.save(img, path)
        return nib.load(path) # Return proxy/image

    # ===== BASIC FUNCTIONALITY TESTS =====
    
    def test_check_is_mask_simple_integer(self):
        """Test basic binary mask with 0 and 1"""
        data = np.zeros((10, 10, 10), dtype=np.int16)
        data[2:5, 2:5, 2:5] = 1
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should be mask: {reason}")
        
    def test_check_is_mask_empty(self):
        """Test empty mask (all zeros)"""
        data = np.zeros((10, 10, 10), dtype=np.int16)
        img = self.create_nifti(data)
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask)
        self.assertIn("Empty", reason)

    def test_check_is_mask_prob_map(self):
        """Test probability map with float values in [0, 1]"""
        data = np.zeros((10, 10, 10), dtype=np.float32)
        # Create continuous probability values
        for i in range(10):
            data[5, 5, i] = i / 10.0
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should be mask (prob map): {reason}")
        self.assertIn("Probability map", reason)

    def test_check_is_mask_volume_rejection(self):
        """Test rejection of grayscale volume with many unique values"""
        data = np.random.rand(20, 20, 20) * 1000
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertFalse(is_mask, f"Should be rejected: {reason}")
        self.assertIn("Too many unique values", reason)

    def test_check_is_mask_dense_volume_rejection(self):
        """Test rejection of dense volume without background"""
        data = np.random.randint(1, 100, (10, 10, 10), dtype=np.int16)
        # Ensure 0 is NOT present
        data[data==0] = 1
        
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertFalse(is_mask, "Should be rejected because no background (0) found")
        self.assertIn("No background", reason)

    # ===== EDGE CASE TESTS =====
    
    def test_rare_label_mask(self):
        """Test mask with rare labels (small lesions)"""
        data = np.zeros((50, 50, 50), dtype=np.int16)
        data[10:15, 10:15, 10:15] = 1  # Main structure
        data[45, 45, 45] = 2  # Rare label (single voxel)
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept mask with rare labels: {reason}")
    
    def test_extremely_sparse_mask(self):
        """Test extremely sparse mask (small tumor)"""
        data = np.zeros((100, 100, 100), dtype=np.int16)
        data[50, 50, 50] = 1  # Only 1 voxel labeled
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept sparse mask: {reason}")
        self.assertIn("sparse", reason.lower())
    
    def test_multi_label_atlas_100_labels(self):
        """Test multi-label atlas with 100 labels"""
        data = np.zeros((20, 20, 20), dtype=np.int16)
        for i in range(100):
            x, y, z = i % 20, (i // 20) % 20, (i // 400) % 20
            data[x, y, z] = i
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept 100-label atlas: {reason}")
    
    def test_multi_label_atlas_2000_labels(self):
        """Test multi-label atlas with 2000 labels (edge of limit)"""
        data = np.zeros((50, 50, 50), dtype=np.int16)
        # Distribute 2000 labels across volume
        for i in range(2000):
            x = i % 50
            y = (i // 50) % 50
            z = (i // 2500) % 50
            data[x, y, z] = i
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept 2000-label atlas: {reason}")
    
    def test_negative_label_mask(self):
        """Test mask with negative labels"""
        data = np.zeros((10, 10, 10), dtype=np.int16)
        data[2:5, 2:5, 2:5] = 1
        data[6:8, 6:8, 6:8] = -1  # Negative label for "uncertain" region
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept mask with negative labels: {reason}")
    
    def test_mask_without_zero_background(self):
        """Test mask with labels starting at 1 (no explicit 0)"""
        data = np.ones((10, 10, 10), dtype=np.int16)
        data[2:5, 2:5, 2:5] = 2
        data[6:8, 6:8, 6:8] = 3
        # No zeros in this mask
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        # Should be rejected unless values are small
        # Actually with our fix, this should be accepted if values < 50
        self.assertTrue(is_mask, f"Should accept mask without background: {reason}")
    
    def test_float_rounding_noise(self):
        """Test mask with float rounding noise (e.g., 1.0000001)"""
        data = np.zeros((10, 10, 10), dtype=np.float32)
        data[2:5, 2:5, 2:5] = 1.0000001
        data[6:8, 6:8, 6:8] = 2.0
        data[1, 1, 1] = 2.9999998
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept mask with rounding noise: {reason}")
    
    def test_nan_mask_rejection(self):
        """Test rejection of mask containing NaN values"""
        data = np.zeros((10, 10, 10), dtype=np.float32)
        data[5, 5, 5] = np.nan
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertFalse(is_mask, "Should reject mask with NaN")
        self.assertIn("NaN", reason)
    
    def test_all_nan_mask_rejection(self):
        """Test rejection of mask with only NaN values"""
        data = np.full((10, 10, 10), np.nan, dtype=np.float32)
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertFalse(is_mask, "Should reject all-NaN mask")
        self.assertIn("NaN", reason)
    
    def test_single_nonzero_label(self):
        """Test mask with single non-zero label (no background)"""
        data = np.ones((10, 10, 10), dtype=np.int16)
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept single label mask: {reason}")
        self.assertIn("Single label", reason)
    
    def test_large_intensity_values_rejection(self):
        """Test rejection of mask with large intensity values (likely HU values)"""
        data = np.zeros((10, 10, 10), dtype=np.int16)
        data[2:5, 2:5, 2:5] = 1000
        data[6:8, 6:8, 6:8] = 2000
        data[1, 1, 1] = 15000  # Very large value
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertFalse(is_mask, "Should reject mask with large intensity values")
        self.assertIn("too large", reason.lower())
    
    def test_discrete_probability_mask(self):
        """Test discrete probability mask with few values in [0, 1]"""
        data = np.zeros((10, 10, 10), dtype=np.float32)
        data[2:5, 2:5, 2:5] = 0.5
        data[6:8, 6:8, 6:8] = 1.0
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        self.assertTrue(is_mask, f"Should accept discrete probability mask: {reason}")
        self.assertIn("probability", reason.lower())
    
    def test_normalized_ct_rejection(self):
        """Test rejection of normalized CT volume (many values in [0, 1])"""
        data = np.random.rand(20, 20, 20).astype(np.float32)
        img = self.create_nifti(data)
        
        is_mask, reason = nifti_utils.check_is_mask(img)
        # Should be rejected as too many unique values
        self.assertFalse(is_mask, "Should reject normalized CT volume")

    # ===== VALIDATION TESTS =====

    def test_validate_compatibility_perfect(self):
        """Test perfect compatibility (all parameters match)"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        affine = np.eye(4)
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape(shape)
        mask_header.set_zooms(spacing)
        
        res = nifti_utils.validate_mask_compatibility(mask_header, affine, shape, spacing, affine)
        self.assertEqual(res.status, ValidationStatus.OK)

    def test_validate_compatibility_dimension_mismatch(self):
        """Test dimension mismatch error"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        affine = np.eye(4)
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape((11, 10, 10)) # Mismatch
        
        res = nifti_utils.validate_mask_compatibility(mask_header, affine, shape, spacing, affine)
        self.assertEqual(res.status, ValidationStatus.ERROR)
        self.assertIn("Dimension mismatch", res.message)

    def test_validate_compatibility_minor_translation_warning(self):
        """Test minor translation offset (warning)"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        proj_affine = np.eye(4)
        mask_affine = np.eye(4)
        mask_affine[0, 3] = 0.2  # 0.2mm shift
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape(shape)
        mask_header.set_zooms(spacing)
        
        res = nifti_utils.validate_mask_compatibility(mask_header, mask_affine, shape, spacing, proj_affine)
        self.assertEqual(res.status, ValidationStatus.WARNING)
        self.assertIn("Origin mismatch", res.message)

    def test_validate_compatibility_major_translation_error(self):
        """Test major translation offset (error) - updated threshold"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        proj_affine = np.eye(4)
        mask_affine = np.eye(4)
        mask_affine[0, 3] = 1.0  # 1.0mm shift (now error with new threshold)
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape(shape)
        mask_header.set_zooms(spacing)
        
        res = nifti_utils.validate_mask_compatibility(mask_header, mask_affine, shape, spacing, proj_affine)
        self.assertEqual(res.status, ValidationStatus.ERROR)
        self.assertIn("Origin mismatch", res.message)
        self.assertIn("significant", res.message.lower())
    
    def test_validate_compatibility_degenerate_affine(self):
        """Test degenerate affine matrix (non-invertible)"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        proj_affine = np.eye(4)
        mask_affine = np.eye(4)
        mask_affine[:3, :3] = 0  # Degenerate (determinant = 0)
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape(shape)
        mask_header.set_zooms(spacing)
        
        res = nifti_utils.validate_mask_compatibility(mask_header, mask_affine, shape, spacing, proj_affine)
        self.assertEqual(res.status, ValidationStatus.ERROR)
        self.assertIn("Corrupted", res.message)
    
    def test_validate_compatibility_orientation_mismatch(self):
        """Test orientation mismatch (RAS vs LPS)"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        
        # RAS orientation
        proj_affine = np.eye(4)
        proj_affine[0, 0] = 1.0  # R
        proj_affine[1, 1] = 1.0  # A
        proj_affine[2, 2] = 1.0  # S
        
        # LPS orientation (flipped)
        mask_affine = np.eye(4)
        mask_affine[0, 0] = -1.0  # L
        mask_affine[1, 1] = -1.0  # P
        mask_affine[2, 2] = 1.0   # S
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape(shape)
        mask_header.set_zooms(spacing)
        
        res = nifti_utils.validate_mask_compatibility(mask_header, mask_affine, shape, spacing, proj_affine)
        self.assertEqual(res.status, ValidationStatus.ERROR)
        self.assertIn("Orientation mismatch", res.message)
    
    def test_validate_compatibility_rotation_mismatch(self):
        """Test subtle rotation mismatch"""
        shape = (10, 10, 10)
        spacing = (1.0, 1.0, 1.0)
        proj_affine = np.eye(4)
        
        # Small rotation (0.5 degrees around Z axis)
        angle = np.radians(0.5)
        mask_affine = np.eye(4)
        mask_affine[0, 0] = np.cos(angle)
        mask_affine[0, 1] = -np.sin(angle)
        mask_affine[1, 0] = np.sin(angle)
        mask_affine[1, 1] = np.cos(angle)
        
        mask_header = nib.Nifti1Header()
        mask_header.set_data_shape(shape)
        mask_header.set_zooms(spacing)
        
        res = nifti_utils.validate_mask_compatibility(mask_header, mask_affine, shape, spacing, proj_affine)
        self.assertEqual(res.status, ValidationStatus.ERROR)
        self.assertIn("rotation", res.message.lower())

if __name__ == '__main__':
    unittest.main()
