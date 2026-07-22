use ndarray::parallel::prelude::*;
use ndarray::ArrayViewMut3;
use num_traits::{AsPrimitive, NumCast};

pub fn brush_mask_internal<U>(
    mut out: ArrayViewMut3<U>,
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
    // If edit_mode is 0 (Include), we must iterate the whole volume because we have to erase everything *outside* the sphere.
    // If edit_mode is 1 (Exclude), we only iterate the bounding box because we only erase *inside* the sphere.

    let min_x = if edit_mode == 0 { 0 } else { ((cx - radius) / sx).floor().max(0.0) as usize };
    let max_x = if edit_mode == 0 { w - 1 } else { ((cx + radius) / sx).ceil().min((w - 1) as f64) as usize };

    let min_y = if edit_mode == 0 { 0 } else { ((cy - radius) / sy).floor().max(0.0) as usize };
    let max_y = if edit_mode == 0 { h - 1 } else { ((cy + radius) / sy).ceil().min((h - 1) as f64) as usize };

    let min_z = if edit_mode == 0 { 0 } else { ((cz - radius) / sz).floor().max(0.0) as usize };
    let max_z = if edit_mode == 0 { d - 1 } else { ((cz + radius) / sz).ceil().min((d - 1) as f64) as usize };

    let radius_sq = radius * radius;

    // Rayon parallel iteration over Z (depth) slices
    par_azip!((index (z, y, x), val in &mut out) {
        if z >= min_z && z <= max_z && y >= min_y && y <= max_y && x >= min_x && x <= max_x {
            // Only process voxels that are currently visible/active (> 0)
            if val.as_() > 0 {
                let dx = x as f64 * sx - cx;
                let dy = y as f64 * sy - cy;
                let dz = z as f64 * sz - cz;
                
                let dist_sq = dx * dx + dy * dy + dz * dz;
                let inside_sphere = dist_sq <= radius_sq;

                if edit_mode == 1 {
                    // EXCLUDE Mode (Erase): Erase voxels INSIDE the sphere
                    if inside_sphere {
                        *val = NumCast::from(0).unwrap();
                    }
                } else if edit_mode == 0 {
                    // INCLUDE Mode (Crop): Erase voxels OUTSIDE the sphere
                    if !inside_sphere {
                        *val = NumCast::from(0).unwrap();
                    }
                }
            }
        } else if edit_mode == 0 {
            // In INCLUDE mode, everything completely outside the bounding box must be erased too.
            if val.as_() > 0 {
                *val = NumCast::from(0).unwrap();
            }
        }
    });
}
