#!/usr/bin/env python
"""
Integration test for NIfTI mask import feature.
Tests the complete workflow from file selection to mask import.
"""

import sys
import tempfile
import numpy as np
import nibabel as nib
from pathlib import Path

# Add invesalius to path
sys.path.insert(0, str(Path(__file__).parent))

from invesalius.reader import nifti_utils
from invesalius.reader.nifti_utils import ValidationStatus

def create_test_nifti(data, affine=None, filename="test.nii.gz"):
    """Create a temporary NIfTI file for testing."""
    if affine is None:
        affine = np.eye(4)
    
    img = nib.Nifti1Image(data, affine)
    tmp_dir = tempfile.mkdtemp()
    filepath = Path(tmp_dir) / filename
    nib.save(img, filepath)
    return filepath

def test_binary_mask_detection():
    """Test 1: Binary mask detection"""
    print("\n=== Test 1: Binary Mask Detection ===")
    
    # Create a simple binary mask
    data = np.zeros((50, 50, 50), dtype=np.uint8)
    data[10:20, 10:20, 10:20] = 1
    
    filepath = create_test_nifti(data, filename="binary_mask.nii.gz")
    
    # Load and check
    img = nib.load(filepath)
    is_mask, reason = nifti_utils.check_is_mask(img)
    
    print(f"File: {filepath.name}")
    print(f"Is mask: {is_mask}")
    print(f"Reason: {reason}")
    print(f"Result: {'✓ PASS' if is_mask else '✗ FAIL'}")
    
    return is_mask

def test_multi_label_mask():
    """Test 2: Multi-label mask detection"""
    print("\n=== Test 2: Multi-Label Mask Detection ===")
    
    # Create multi-label mask
    data = np.zeros((50, 50, 50), dtype=np.uint8)
    data[10:20, 10:20, 10:20] = 1
    data[25:35, 25:35, 25:35] = 2
    data[40:45, 40:45, 40:45] = 3
    
    filepath = create_test_nifti(data, filename="multi_label_mask.nii.gz")
    
    # Load and check
    img = nib.load(filepath)
    is_mask, reason = nifti_utils.check_is_mask(img)
    
    print(f"File: {filepath.name}")
    print(f"Is mask: {is_mask}")
    print(f"Reason: {reason}")
    print(f"Unique labels: {np.unique(data)}")
    print(f"Result: {'✓ PASS' if is_mask else '✗ FAIL'}")
    
    return is_mask

def test_volume_rejection():
    """Test 3: Volume rejection (not a mask)"""
    print("\n=== Test 3: Volume Rejection ===")
    
    # Create a volume with many unique values
    data = np.random.randint(0, 1000, (50, 50, 50), dtype=np.int16)
    
    filepath = create_test_nifti(data, filename="ct_volume.nii.gz")
    
    # Load and check
    img = nib.load(filepath)
    is_mask, reason = nifti_utils.check_is_mask(img)
    
    print(f"File: {filepath.name}")
    print(f"Is mask: {is_mask}")
    print(f"Reason: {reason}")
    print(f"Unique values: {len(np.unique(data))}")
    print(f"Result: {'✓ PASS' if not is_mask else '✗ FAIL'}")
    
    return not is_mask

def test_probability_map():
    """Test 4: Probability map detection"""
    print("\n=== Test 4: Probability Map Detection ===")
    
    # Create probability map
    data = np.zeros((50, 50, 50), dtype=np.float32)
    for i in range(10):
        data[10+i, 10:20, 10:20] = i / 10.0
    
    filepath = create_test_nifti(data, filename="probability_map.nii.gz")
    
    # Load and check
    img = nib.load(filepath)
    is_mask, reason = nifti_utils.check_is_mask(img)
    
    print(f"File: {filepath.name}")
    print(f"Is mask: {is_mask}")
    print(f"Reason: {reason}")
    print(f"Value range: [{data.min():.2f}, {data.max():.2f}]")
    print(f"Result: {'✓ PASS' if is_mask and 'probability' in reason.lower() else '✗ FAIL'}")
    
    return is_mask and 'probability' in reason.lower()

def test_dimension_validation():
    """Test 5: Dimension validation"""
    print("\n=== Test 5: Dimension Validation ===")
    
    # Create mask and project with matching dimensions
    mask_shape = (50, 50, 50)
    proj_shape = (50, 50, 50)
    spacing = (1.0, 1.0, 1.0)
    affine = np.eye(4)
    
    data = np.zeros(mask_shape, dtype=np.uint8)
    data[10:20, 10:20, 10:20] = 1
    
    filepath = create_test_nifti(data, affine, filename="matching_mask.nii.gz")
    img = nib.load(filepath)
    
    # Validate
    result = nifti_utils.validate_mask_compatibility(
        img.header, img.affine, proj_shape, spacing, affine
    )
    
    print(f"File: {filepath.name}")
    print(f"Mask shape: {mask_shape}")
    print(f"Project shape: {proj_shape}")
    print(f"Validation status: {result.status}")
    print(f"Result: {'✓ PASS' if result.status == ValidationStatus.OK else '✗ FAIL'}")
    
    return result.status == ValidationStatus.OK

def test_dimension_mismatch():
    """Test 6: Dimension mismatch detection"""
    print("\n=== Test 6: Dimension Mismatch Detection ===")
    
    # Create mask with different dimensions
    mask_shape = (60, 60, 60)
    proj_shape = (50, 50, 50)
    spacing = (1.0, 1.0, 1.0)
    affine = np.eye(4)
    
    data = np.zeros(mask_shape, dtype=np.uint8)
    data[10:20, 10:20, 10:20] = 1
    
    filepath = create_test_nifti(data, affine, filename="mismatched_mask.nii.gz")
    img = nib.load(filepath)
    
    # Validate
    result = nifti_utils.validate_mask_compatibility(
        img.header, img.affine, proj_shape, spacing, affine
    )
    
    print(f"File: {filepath.name}")
    print(f"Mask shape: {mask_shape}")
    print(f"Project shape: {proj_shape}")
    print(f"Validation status: {result.status}")
    print(f"Message: {result.message}")
    print(f"Result: {'✓ PASS' if result.status == ValidationStatus.ERROR else '✗ FAIL'}")
    
    return result.status == ValidationStatus.ERROR

def test_translation_warning():
    """Test 7: Translation offset warning"""
    print("\n=== Test 7: Translation Offset Warning ===")
    
    # Create mask with slight translation
    mask_shape = (50, 50, 50)
    proj_shape = (50, 50, 50)
    spacing = (1.0, 1.0, 1.0)
    
    proj_affine = np.eye(4)
    mask_affine = np.eye(4)
    mask_affine[0, 3] = 0.2  # 0.2mm offset
    
    data = np.zeros(mask_shape, dtype=np.uint8)
    data[10:20, 10:20, 10:20] = 1
    
    filepath = create_test_nifti(data, mask_affine, filename="offset_mask.nii.gz")
    img = nib.load(filepath)
    
    # Validate
    result = nifti_utils.validate_mask_compatibility(
        img.header, img.affine, proj_shape, spacing, proj_affine
    )
    
    print(f"File: {filepath.name}")
    print(f"Translation offset: 0.2mm")
    print(f"Validation status: {result.status}")
    print(f"Message: {result.message}")
    print(f"Result: {'✓ PASS' if result.status == ValidationStatus.WARNING else '✗ FAIL'}")
    
    return result.status == ValidationStatus.WARNING

def main():
    """Run all integration tests."""
    print("=" * 60)
    print("NIfTI Mask Import - Integration Tests")
    print("=" * 60)
    
    tests = [
        test_binary_mask_detection,
        test_multi_label_mask,
        test_volume_rejection,
        test_probability_map,
        test_dimension_validation,
        test_dimension_mismatch,
        test_translation_warning,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ EXCEPTION: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Tests passed: {passed}/{total}")
    print(f"Success rate: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n✗ {total - passed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
