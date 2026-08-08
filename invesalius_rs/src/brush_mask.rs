use ndarray::parallel::prelude::*;
use ndarray::ArrayViewMut3;
use num_traits::{AsPrimitive, NumCast};

pub fn brush_mask_internal<U>(
    mut out: ArrayViewMut3<U>,
    orig: Option<ndarray::ArrayView3<U>>,
    spacing: (f64, f64, f64),
    center: (f64, f64, f64),
    radius: f64,
    edit_mode: i32,
) where
    U: PartialOrd + Copy + Send + Sync + NumCast + AsPrimitive<i32>,
{
    let dims = out.shape();
    let (d, h, w) = (dims[0], dims[1], dims[2]);
    let (sx, sy, sz) = spacing;
    let (cx, cy, cz) = center;

    // Optimization: Calculate Voxel Bounding Box to avoid iterating 125 Million voxels
    // We only need to iterate over the voxels that could possibly be inside the sphere.
    // For both Draw (0) and Erase (1) modes, we only modify voxels inside the sphere.

    let min_x = ((cx - radius) / sx).floor().max(0.0) as usize;
    let max_x = ((cx + radius) / sx).ceil().max(0.0).min((w - 1) as f64) as usize;

    let min_y = ((cy - radius) / sy).floor().max(0.0) as usize;
    let max_y = ((cy + radius) / sy).ceil().max(0.0).min((h - 1) as f64) as usize;

    let min_z = ((cz - radius) / sz).floor().max(0.0) as usize;
    let max_z = ((cz + radius) / sz).ceil().max(0.0).min((d - 1) as f64) as usize;

    let radius_sq = radius * radius;

    // Rayon parallel iteration over Z (depth) slices
    par_azip!((index (z, y, x), val in &mut out) {
        if z >= min_z && z <= max_z && y >= min_y && y <= max_y && x >= min_x && x <= max_x {
            // Erase mode (1) only applies to voxels > 0
            if edit_mode == 1 {
                if val.as_() > 0 {
                    let dx = x as f64 * sx - cx;
                    let dy = y as f64 * sy - cy;
                    let dz = z as f64 * sz - cz;
                    let dist_sq = dx * dx + dy * dy + dz * dz;
                    
                    if dist_sq <= radius_sq {
                        *val = NumCast::from(0).unwrap();
                    }
                }
            } else if edit_mode == 0 {
                // Crop/Reveal mode (0) applies to all voxels, setting them to original value
                let dx = x as f64 * sx - cx;
                let dy = y as f64 * sy - cy;
                let dz = z as f64 * sz - cz;
                let dist_sq = dx * dx + dy * dy + dz * dz;
                
                if dist_sq <= radius_sq {
                    if let Some(orig_array) = &orig {
                        let orig_val = orig_array[[z, y, x]];
                        if orig_val.as_() > 0 {
                            *val = orig_val;
                        }
                    } else {
                        // Fallback if no original mask passed
                        *val = NumCast::from(255).unwrap();
                    }
                }
            }
        }
    });
}
