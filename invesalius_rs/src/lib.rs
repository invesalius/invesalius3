//! Rust extensions for InVesalius3
//!
//! This module provides high-performance implementations of computational
//! functions used in InVesalius3 medical imaging software.

use numpy::{PyArray3, PyArrayMethods, PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3, PyUntypedArrayMethods};
use pyo3::prelude::*;
use rayon::prelude::*;


/// Applies a mask cut operation with depth constraint on a 3D image array.
///
/// # Arguments
///
/// * `_py` - Python GIL token
/// * `image` - 3D array representing the image volume (not modified)
/// * `x_coords` - Array of x coordinates where mask is applied
/// * `y_coords` - Array of y coordinates where mask is applied
/// * `z_coords` - Array of z coordinates where mask is applied
/// * `sx` - Spacing for x axis
/// * `sy` - Spacing for y axis
/// * `sz` - Spacing for z axis
/// * `max_depth` - Maximum allowed depth for masking
/// * `mask` - 2D mask to apply in screen space
/// * `m` - 4x4 transformation matrix (world to screen)
/// * `mv` - 4x4 transformation matrix for depth calculation
/// * `out` - Output array to store the result (modified in-place)
/// * `edit_mode` - Edit mode: 0 for include (keep inside polygon), 1 for exclude
///
/// In include mode (edit_mode=0), voxels projecting outside the viewport are zeroed.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn mask_cut<'py>(
    _py: Python<'py>,
    _image: PyReadonlyArray3<'py, u8>,
    x_coords: PyReadonlyArray1<'py, i32>,
    y_coords: PyReadonlyArray1<'py, i32>,
    z_coords: PyReadonlyArray1<'py, i32>,
    sx: f32,
    sy: f32,
    sz: f32,
    max_depth: f32,
    mask: PyReadonlyArray2<'py, u8>,
    m: PyReadonlyArray2<'py, f64>,
    mv: PyReadonlyArray2<'py, f64>,
    out: &Bound<'py, PyArray3<u8>>,
    edit_mode: i32,
) -> PyResult<()> {
    let x_coords = x_coords.as_slice()?;
    let y_coords = y_coords.as_slice()?;
    let z_coords = z_coords.as_slice()?;

    let mask_shape = mask.shape();
    let h = mask_shape[0] as i32;
    let w = mask_shape[1] as i32;

    // Convert mask to owned data for thread-safe access
    let mask_data: Vec<u8> = mask.as_slice()?.to_vec();

    // Convert transformation matrices to flat arrays for thread-safe access
    let m_slice = m.as_slice()?;
    let mv_slice = mv.as_slice()?;

    // Copy matrices to owned arrays
    let m_arr: [f64; 16] = m_slice.try_into().map_err(|_| {
        pyo3::exceptions::PyValueError::new_err("M matrix must be 4x4")
    })?;
    let mv_arr: [f64; 16] = mv_slice.try_into().map_err(|_| {
        pyo3::exceptions::PyValueError::new_err("MV matrix must be 4x4")
    })?;

    let n = z_coords.len();

    // Collect voxels to zero in parallel
    let voxels_to_zero: Vec<(usize, usize, usize)> = (0..n)
        .into_par_iter()
        .filter_map(|i| {
            let x = x_coords[i];
            let y = y_coords[i];
            let z = z_coords[i];

            let p0 = (x as f32) * sx;
            let p1 = (y as f32) * sy;
            let p2 = (z as f32) * sz;
            let p3: f64 = 1.0;

            let p0_64 = p0 as f64;
            let p1_64 = p1 as f64;
            let p2_64 = p2 as f64;

            // World to screen transformation
            let _q0 = p0_64 * m_arr[0] + p1_64 * m_arr[1] + p2_64 * m_arr[2] + p3 * m_arr[3];
            let _q1 = p0_64 * m_arr[4] + p1_64 * m_arr[5] + p2_64 * m_arr[6] + p3 * m_arr[7];
            let _q2 = p0_64 * m_arr[8] + p1_64 * m_arr[9] + p2_64 * m_arr[10] + p3 * m_arr[11];
            let _q3 = p0_64 * m_arr[12] + p1_64 * m_arr[13] + p2_64 * m_arr[14] + p3 * m_arr[15];

            if _q3 <= 0.0 {
                return None;
            }

            let q0 = _q0 / _q3;
            let q1 = _q1 / _q3;

            // Depth calculation
            let _c0 = p0_64 * mv_arr[0] + p1_64 * mv_arr[1] + p2_64 * mv_arr[2] + p3 * mv_arr[3];
            let _c1 = p0_64 * mv_arr[4] + p1_64 * mv_arr[5] + p2_64 * mv_arr[6] + p3 * mv_arr[7];
            let _c2 = p0_64 * mv_arr[8] + p1_64 * mv_arr[9] + p2_64 * mv_arr[10] + p3 * mv_arr[11];
            let _c3 = p0_64 * mv_arr[12] + p1_64 * mv_arr[13] + p2_64 * mv_arr[14] + p3 * mv_arr[15];

            let c0 = _c0 / _c3;
            let c1 = _c1 / _c3;
            let c2 = _c2 / _c3;

            let dist = (c0 * c0 + c1 * c1 + c2 * c2).sqrt();

            if dist > max_depth as f64 {
                return None;
            }

            // Convert NDC to screen coordinates
            let px = (q0 / 2.0 + 0.5) * ((w - 1) as f64);
            let py = (q1 / 2.0 + 0.5) * ((h - 1) as f64);

            if px >= 0.0 && px <= w as f64 && py >= 0.0 && py <= h as f64 {
                // Voxel is on screen - check mask
                let px_int = px as usize;
                let py_int = py as usize;
                let mask_idx = py_int * (w as usize) + px_int;

                if mask_idx < mask_data.len() && mask_data[mask_idx] != 0 {
                    return Some((z as usize, y as usize, x as usize));
                }
            } else {
                // Voxel projects outside visible viewport
                if edit_mode == 0 {
                    // In include mode, off-screen voxels are outside any drawn polygon
                    return Some((z as usize, y as usize, x as usize));
                }
            }

            None
        })
        .collect();

    // Apply changes to output array
    // SAFETY: We need unsafe to get mutable access to the numpy array
    unsafe {
        let mut out_arr = out.as_array_mut();
        for (z, y, x) in voxels_to_zero {
            if let Some(elem) = out_arr.get_mut([z, y, x]) {
                *elem = 0;
            }
        }
    }

    Ok(())
}

/// Python module for InVesalius Rust extensions
#[pymodule]
fn invesalius_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(mask_cut, m)?)?;
    Ok(())
}
