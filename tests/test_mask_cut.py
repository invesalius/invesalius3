"""
Unit tests for mask_cut function to verify the fix for GitHub issue #1084.

Tests that voxels projecting outside the viewport are correctly handled
based on edit_mode.
"""

import numpy as np
import pytest

from invesalius_cy.mask_cut import mask_cut


class TestMaskCutViewportClipping:
    """Tests for viewport clipping behavior in mask_cut."""

    def test_include_mode_zeros_offscreen_voxels(self):
        """
        In include mode (edit_mode=0), voxels projecting outside the 
        viewport should be zeroed out, not preserved.
        """
        # Create a simple 3D volume with all values = 1
        image = np.ones((10, 10, 10), dtype=np.uint8)
        out = image.copy()
        
        # Coordinates of all voxels
        z_coords, y_coords, x_coords = np.where(image > 0)
        x_coords = x_coords.astype(np.int32)
        y_coords = y_coords.astype(np.int32)
        z_coords = z_coords.astype(np.int32)
        
        # Spacing
        sx, sy, sz = 1.0, 1.0, 1.0
        
        # Max depth - allow all depths
        max_depth = 1000.0
        
        # Screen size
        w, h = 100, 100
        
        # Create an empty mask (no polygon selected)
        mask = np.zeros((h, w), dtype=np.uint8)
        
        # Create a projection matrix that projects ALL voxels OFF-SCREEN
        # This simulates the zoomed-in case where volume extends beyond viewport
        # By using a large translation, all voxels will project outside [-1, 1] NDC
        M = np.array([
            [1.0, 0.0, 0.0, 1000.0],  # Large X translation
            [0.0, 1.0, 0.0, 1000.0],  # Large Y translation  
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        MV = np.eye(4, dtype=np.float64)
        
        # In include mode (edit_mode=0), off-screen voxels should be zeroed
        edit_mode = 0  # include mode
        
        mask_cut(
            image, x_coords, y_coords, z_coords,
            sx, sy, sz, max_depth, mask, M, MV, out, edit_mode
        )
        
        # All voxels should be zero because they all project off-screen
        # and in include mode, off-screen voxels are outside the polygon
        assert np.sum(out) == 0, (
            f"In include mode, off-screen voxels should be zeroed. "
            f"Found {np.sum(out)} non-zero voxels."
        )

    def test_exclude_mode_preserves_offscreen_voxels(self):
        """
        In exclude mode (edit_mode=1), voxels projecting outside the 
        viewport should be preserved (not modified).
        """
        # Create a simple 3D volume with all values = 1
        image = np.ones((10, 10, 10), dtype=np.uint8)
        out = image.copy()
        
        # Coordinates of all voxels
        z_coords, y_coords, x_coords = np.where(image > 0)
        x_coords = x_coords.astype(np.int32)
        y_coords = y_coords.astype(np.int32)
        z_coords = z_coords.astype(np.int32)
        
        # Spacing
        sx, sy, sz = 1.0, 1.0, 1.0
        
        # Max depth
        max_depth = 1000.0
        
        # Screen size
        w, h = 100, 100
        
        # Create an empty mask
        mask = np.zeros((h, w), dtype=np.uint8)
        
        # Projection matrix that projects all voxels off-screen
        M = np.array([
            [1.0, 0.0, 0.0, 1000.0],
            [0.0, 1.0, 0.0, 1000.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        MV = np.eye(4, dtype=np.float64)
        
        # In exclude mode (edit_mode=1), off-screen voxels should be preserved
        edit_mode = 1  # exclude mode
        
        mask_cut(
            image, x_coords, y_coords, z_coords,
            sx, sy, sz, max_depth, mask, M, MV, out, edit_mode
        )
        
        # All voxels should still be 1 because in exclude mode,
        # off-screen voxels are not modified
        assert np.sum(out) == 1000, (
            f"In exclude mode, off-screen voxels should be preserved. "
            f"Found {np.sum(out)} non-zero voxels, expected 1000."
        )

    def test_onscreen_voxels_respect_mask(self):
        """
        Voxels that project on-screen should be zeroed only if they
        fall within the mask region.
        """
        # Create a 5x5x5 volume
        image = np.ones((5, 5, 5), dtype=np.uint8)
        out = image.copy()
        
        # Use a single voxel at center
        x_coords = np.array([2], dtype=np.int32)
        y_coords = np.array([2], dtype=np.int32)
        z_coords = np.array([2], dtype=np.int32)
        
        sx, sy, sz = 1.0, 1.0, 1.0
        max_depth = 1000.0
        
        w, h = 10, 10
        
        # Create mask with a region marked
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[4:6, 4:6] = 1  # Small region in center
        
        # Identity-like projection that maps voxel to center of screen
        # NDC (0,0) -> screen center (w/2, h/2) = (5, 5)
        M = np.array([
            [0.1, 0.0, 0.0, 0.0],  # Scale down
            [0.0, 0.1, 0.0, 0.0],
            [0.0, 0.0, 0.1, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        MV = np.eye(4, dtype=np.float64)
        
        edit_mode = 0  # include mode
        
        mask_cut(
            image, x_coords, y_coords, z_coords,
            sx, sy, sz, max_depth, mask, M, MV, out, edit_mode
        )
        
        # The voxel at (2,2,2) projects to screen and falls in mask region
        # So it should be zeroed
        assert out[2, 2, 2] == 0, "On-screen voxel in mask region should be zeroed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
